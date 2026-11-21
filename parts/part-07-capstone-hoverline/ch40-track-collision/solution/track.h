#ifndef TRACK_H
#define TRACK_H

#include <stddef.h>
#include <stdint.h>

/* ---- the .TRK records, exactly as the file stores them (Appendix E.10; little-endian, like the R3000) ----------------- */

typedef struct { int32_t x, y, z; } TrkVertex;              /* 12 bytes, world units, +Y down */

#define TRK_FLOOR   0x0001        /* face flags (E.10.3) */
#define TRK_WALL    0x0002
#define TRK_BOOST   0x0004
#define TRK_START   0x0008
#define TRK_FLIP_H  0x0010        /* texture mirrored in U: Chapter 35 (track_face_uv) */
#define TRK_FLAGS_KNOWN (TRK_FLOOR | TRK_WALL | TRK_BOOST | TRK_START | TRK_FLIP_H)
#define TRK_UNTEXTURED  0xFF

typedef struct {                                            /* 24 bytes */
	uint16_t v[4];                                          /* +0x00 vertex indices, Z order */
	uint16_t flags;                                         /* +0x08 */
	uint8_t  tex;                                           /* +0x0A texture index, or TRK_UNTEXTURED */
	uint8_t  pad;                                           /* +0x0B */
	uint8_t  uv[8];                                         /* +0x0C u0 v0 u1 v1 u2 v2 u3 v3 (Chapter 35: texture-local, 0..63) */
	uint8_t  color[4];                                      /* +0x14 r g b 0 */
} TrkFace;

#define TRK_SEC_JUNCTION 0x0001   /* section flags (E.10.4) */
#define TRK_SEC_START    0x0002
#define TRK_SEC_FLAGS_KNOWN (TRK_SEC_JUNCTION | TRK_SEC_START)

typedef struct {                                            /* 64 bytes */
	int32_t  centre[3];                                     /* +0x00 */
	uint16_t half_width;                                    /* +0x0C */
	uint16_t length;                                        /* +0x0E */
	int16_t  forward[4];                                    /* +0x10 4.12 unit vector, 4th entry padding */
	int16_t  right[4];                                      /* +0x18 */
	int16_t  up[4];                                         /* +0x20 */
	uint16_t first_face;                                    /* +0x28 */
	uint16_t face_count;                                    /* +0x2A */
	uint16_t next;                                          /* +0x2C */
	uint16_t prev;                                          /* +0x2E */
	uint16_t flags;                                         /* +0x30 */
	uint16_t vis_first;                                     /* +0x32 */
	uint16_t vis_count;                                     /* +0x34 */
	uint16_t edges[4];                                      /* +0x36 left_start, right_start, left_end, right_end (vertex indices) */
	uint16_t pad;                                           /* +0x3E */
} TrkSection;

_Static_assert(sizeof(TrkVertex) == 12, "TrkVertex must be 12 bytes (the file's vertex record)");
_Static_assert(sizeof(TrkFace) == 24, "TrkFace must be 24 bytes (the file's face record)");
_Static_assert(sizeof(TrkSection) == 64, "TrkSection must be 64 bytes (the file's section record)");

/* ---- the parsed track ------------------------------------------------------------------------------------------------ */

/* The tables are used IN PLACE: the pointers point into the file image, which must therefore stay allocated (and
   4-byte aligned) as long as the Track is used. The verifier reads this struct through the `track` symbol: 12 words,
   in this order. */
typedef struct {
	const TrkVertex  *vertices;                             /* +0  */
	const TrkFace    *faces;                                /* +4  */
	const TrkSection *sections;                             /* +8  */
	const uint16_t   *vis;                                  /* +12 the visibility list (Chapter 38) */
	int32_t section_count;                                  /* +16 */
	int32_t vertex_count;                                   /* +20 */
	int32_t face_count;                                     /* +24 */
	int32_t vis_count;                                      /* +28 */
	int32_t start_section;                                  /* +32 */
	int32_t flags;                                          /* +36 header flags (bit 0 LOOP) */
	int32_t texture_count;                                  /* +40 */
	int32_t total_length;                                   /* +44 */
} Track;
_Static_assert(sizeof(Track) == 48, "the verifier reads 12 words at the `track` symbol");

/* Return codes of track_parse. 0 is success; every failure is negative. */
#define TRK_OK            0
#define TRK_ERR_READ     -1   /* the file could not be read from the disc (set by main.c, never by track_parse) */
#define TRK_ERR_ALIGN    -2   /* the image is not 4-byte aligned */
#define TRK_ERR_MAGIC    -3   /* fewer than 4 bytes, or the first four are not "TRK1" */
#define TRK_ERR_HEADER   -4   /* header inconsistent with itself, with the file size or with the limits below */
#define TRK_ERR_VERTEX   -5   /* a vertex coordinate is outside +-TRK_MAX_COORD */
#define TRK_ERR_FACE     -6   /* a face record is bad: vertex index, flags or texture index */
#define TRK_ERR_SECTION  -7   /* a section record is bad: links, face range, edges, flags, visibility slice */
#define TRK_ERR_VIS      -8   /* a visibility-list entry is not a section index */

/* The program's limits (not format facts: they size the arrays of track_render.c and keep the arithmetic safe). */
#define TRK_MAX_SECTIONS    160
#define TRK_MAX_VERTICES   1024
#define TRK_MAX_FACES      1024
#define TRK_MAX_VIS        8192
#define TRK_MAX_COORD   1000000      /* |x|, |y|, |z| of a vertex */

/* State the verifier reads. */
extern Track   track;            /* the loaded track: all zero until track_parse succeeds */
extern int32_t track_status;     /* what track_parse returned for the disc's file (main.c) */

/* Check a TRK image of exactly `size` bytes and, if it is valid, fill *out (the tables point INTO `data`).
   On any failure *out is set to all zero. Nothing is copied, nothing is allocated, nothing is modified.
   Checks in this order, returning at the first failure (README 5.4):
     TRK_ERR_ALIGN    `data` is not a multiple of 4;
     TRK_ERR_MAGIC    size < 4, or no "TRK1";
     TRK_ERR_HEADER   size < 0x60; file_size != size; section_count, vertex_count or face_count 0 or above its TRK_MAX_*;
                      vis_count above TRK_MAX_VIS; start_section >= section_count; the four offsets differ from
                      0x60, +12*vertex_count, +24*face_count, +64*section_count; size != vis_offset + 2*vis_count rounded up to 4;
     TRK_ERR_VERTEX   a coordinate below -TRK_MAX_COORD or above TRK_MAX_COORD (vertices in table order);
     TRK_ERR_FACE     walking the faces: a vertex index >= vertex_count; flags with a bit outside TRK_FLAGS_KNOWN; neither
                      TRK_FLOOR nor TRK_WALL; TRK_BOOST or TRK_START without TRK_FLOOR; tex >= texture_count and not TRK_UNTEXTURED;
     TRK_ERR_SECTION  walking the sections: next or prev >= section_count; first_face + face_count > face_count of the file;
                      an edges[] entry >= vertex_count; a flag outside TRK_SEC_FLAGS_KNOWN; vis_first + vis_count > the file's vis_count;
     TRK_ERR_VIS      walking the visibility list: an entry >= section_count.
   (Within a record, check its fields in the order listed.) */
int track_parse(const void *data, size_t size, Track *out);

/* Bounds-checked access: NULL when `i` is negative or not below the count. */
const TrkVertex  *track_vertex(const Track *t, int i);
const TrkFace    *track_face(const Track *t, int i);
const TrkSection *track_section(const Track *t, int i);

#endif
