#ifndef TPK_H
#define TPK_H

#include <stddef.h>
#include <stdint.h>
#include "tim.h"

/* Return codes. 0 is success; every failure is negative. */
#define TPK_OK          0
#define TPK_ERR_READ   -1     /* the file could not be read from the disc */
#define TPK_ERR_MAGIC  -2     /* the file does not start with "TPK1" (or is shorter than 4 bytes) */
#define TPK_ERR_HEADER -3     /* header or size table inconsistent, see tpk_parse */
#define TPK_ERR_MEM    -4     /* malloc failed */
#define TPK_ERR_DATA   -5     /* the LZSS stream is damaged: truncated, overruns the output, or has bytes left over */
#define TPK_ERR_CRC    -6     /* the stream decoded, but the CRC-32 of the result is not the header's */
#define TPK_ERR_TIM    -7     /* a texture inside the pack is not a usable TIM (tim_parse said no) */
#define TPK_ERR_SPACE  -8     /* the destination buffer is smaller than the header's raw_size */

#define TPK_MAX      255          /* most textures in one pack (Appendix E.6) */
#define TPK_MAX_RAW  (1u << 20)   /* largest raw_size this loader accepts: 1 MiB */

/* The fields of a .TPK header (Appendix E.6), copied out of the file image. */
typedef struct {
	uint32_t count;               /* number of textures, 1..TPK_MAX */
	uint32_t raw_size;            /* bytes after decompression */
	uint32_t comp_size;           /* bytes of the LZSS stream */
	uint32_t crc32;               /* CRC-32 of the decompressed bytes */
	uint32_t sizes[TPK_MAX];      /* sizes[i] = bytes of texture i's TIM; only the first `count` are meaningful */
	const uint8_t *stream;        /* the LZSS stream: points INTO the file image */
} TpkHeader;

/* The global texture store: texture id -> everything a polygon needs. Ids are positions in the pack, 0..count-1. */
typedef struct {
	int32_t  count;               /* textures loaded; 0 when tpk_load failed */
	uint8_t *raw;                 /* the decompressed blob (all the TIMs, one after the other), malloc'ed; NULL on failure */
	uint32_t raw_size;
	Tex      tex[TPK_MAX];        /* tex[id], filled by tex_from_tim */
} TpkTextures;

/* CRC-32 as zlib computes it (reflected polynomial 0xEDB88320, start and end 0xFFFFFFFF). tpk_crc32(p, 0) is 0. */
uint32_t tpk_crc32(const uint8_t *p, size_t n);

/* Decode the book's LZSS (Appendix E.5): `src_size` bytes of stream in, exactly `dst_size` bytes out.
   Returns TPK_OK, or TPK_ERR_DATA when the stream is truncated (a flag byte, a literal or a reference cut short), when a
   reference would run past dst_size, or when bytes of src remain once dst_size bytes are out.
   Never writes outside dst[0 .. dst_size), never reads outside src[0 .. src_size). Keep `noinline`: the verifier
   measures the cycles spent between entering and leaving this function. */
__attribute__((noinline)) int lzss_decode(const uint8_t *src, size_t src_size, uint8_t *dst, size_t dst_size);

/* Check a .TPK file image and fill *h. `size` is the file's exact size in bytes. Returns TPK_OK or
   TPK_ERR_MAGIC: fewer than 4 bytes, or the first four are not "TPK1";
   TPK_ERR_HEADER: any of: the file is shorter than 0x14 + 4*count; count is 0 or above TPK_MAX; a size is 0, not a multiple of 4,
                   or the sum of the sizes is not raw_size; raw_size is 0 or above TPK_MAX_RAW; comp_size is 0, or the stream
                   does not fit in the file, or the file has 4 or more bytes after the stream (0..3 padding bytes are fine).
   Checked in that order. *h is unspecified after a failure. */
int tpk_parse(const void *file, size_t size, TpkHeader *h);

/* Parse the header, check dst_size >= raw_size (TPK_ERR_SPACE, nothing written), decode into dst with lzss_decode and
   compare the CRC-32 (TPK_ERR_CRC). Returns TPK_OK or the first error, in that order. Writes only dst[0 .. raw_size). */
int tpk_unpack(const void *file, size_t size, uint8_t *dst, size_t dst_size);

/* The whole job: cd_load_file(path), unpack into a malloc'ed buffer, then for every texture tim_parse, tim_upload and
   tex_from_tim into out->tex[id]. Frees the file image on every path.
   Success: TPK_OK, out->count textures, out->raw / out->raw_size the decompressed blob (still allocated).
   Failure: the negative code, out->count = 0, out->raw = NULL, out->raw_size = 0, nothing leaked. A missing file is TPK_ERR_READ. */
int tpk_load(const char *path, TpkTextures *out);

/* Release out->raw (the uploaded textures stay in VRAM; tex[] stays valid). */
void tpk_free_raw(TpkTextures *out);

#endif
