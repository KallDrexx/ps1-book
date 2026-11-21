#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "cdrom.h"
#include "tim.h"
#include "tpk.h"

/* TODO (README 5.7 and 7.2): the five unfinished functions below. tim_parse, tim_upload, tex_from_tim (tim.c) and cd_load_file (cdrom.c) are
   Chapter 29 and 30's finished work. Until you write these, everything fails with an error code and the screen stays red. */

/* TODO: little-endian 32-bit read from a byte pointer (the file image may start at any address, so do not read it through a uint32_t pointer). */

uint32_t tpk_crc32(const uint8_t *p, size_t n)
{
	(void) p; (void) n;
	return 0;                                /* TODO: README 5.5 */
}

__attribute__((noinline)) int lzss_decode(const uint8_t *src, size_t src_size, uint8_t *dst, size_t dst_size)
{
	(void) src; (void) src_size; (void) dst; (void) dst_size;
	return TPK_ERR_DATA;                     /* TODO: README 5.3 and 5.7: the decoder, with every bounds check of tpk.h */
}

int tpk_parse(const void *file, size_t size, TpkHeader *h)
{
	(void) file; (void) size; (void) h;
	return TPK_ERR_MAGIC;                    /* TODO: README 5.5: the checks listed in tpk.h, in that order */
}

int tpk_unpack(const void *file, size_t size, uint8_t *dst, size_t dst_size)
{
	(void) file; (void) size; (void) dst; (void) dst_size;
	return TPK_ERR_MAGIC;                    /* TODO: parse, space check, lzss_decode, CRC */
}

int tpk_load(const char *path, TpkTextures *out)
{
	(void) path;
	out->count = 0;
	out->raw = NULL;
	out->raw_size = 0;
	return TPK_ERR_READ;                     /* TODO: cd_load_file, tpk_parse, malloc, tpk_unpack, free the file, then the textures */
}

void tpk_free_raw(TpkTextures *out)
{
	free(out->raw);
	out->raw = NULL;
	out->raw_size = 0;
}
