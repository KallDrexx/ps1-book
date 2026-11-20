#ifndef SHP_H
#define SHP_H

#include <stddef.h>
#include <stdint.h>
#include <psxgte.h>
#include "tim.h"

/* Return codes. 0 is success; every failure is negative. */
#define SHP_OK          0
#define SHP_ERR_READ   -1     /* the file could not be read from the disc (main.c) */
#define SHP_ERR_ALIGN  -2     /* the image is not 4-byte aligned */
#define SHP_ERR_MAGIC  -3     /* fewer than 4 bytes, or the first four are not "SHP1" */
#define SHP_ERR_HEADER -4     /* header inconsistent with itself or with the file size, see shp_parse */
#define SHP_ERR_PRIM   -5     /* the primitive list is damaged: bad tag, wrong size, overrun, wrong count */
#define SHP_ERR_INDEX  -6     /* a vertex index or a normal index is out of range */
#define SHP_ERR_TEXTURE -7    /* a textured record names a texture >= texture_count */
#define SHP_ERR_STORE  -8     /* the .SHP needs more textures than the .TPK holds (main.c) */

#define SHP_MAX_VERTS 256     /* the program's screen_xy[] / screen_z[] arrays hold this many */

/* The eight record types of Appendix E.8, in tag order. */
enum { SHP_F3, SHP_F4, SHP_G3, SHP_G4, SHP_FT3, SHP_FT4, SHP_GT3, SHP_GT4, SHP_TYPES };

/* Record flags (bit 0..2). */
#define SHP_DOUBLE_SIDED 1
#define SHP_SEMI_TRANS   2
#define SHP_UNLIT        4

/* One primitive record, decoded. Only the fields that the record's type has are meaningful; the rest are unspecified.
   Triangles use v[0..2] / uv[0..2] / rgb[0..2]; a flat type uses rgb[0] only; rgb[k] = { r, g, b, 0 } as stored. */
typedef struct {
	uint8_t  type;                /* 0..7, SHP_F3 ... SHP_GT4 */
	uint8_t  flags;
	uint16_t size;                /* bytes of the record in the file */
	uint16_t v[4];                /* vertex indices, Z order for quads */
	uint16_t normal;              /* index into the normal list */
	uint16_t tex;                 /* texture id in the .TPK (textured types only) */
	uint8_t  uv[4][2];            /* texture-LOCAL u, v */
	uint8_t  rgb[4][4];
} ShpPrim;                        /* 40 bytes: the verifier reads it from RAM, do not reorder */

/* A parsed .SHP. Every pointer points INTO the file image that was parsed: free that, not these. */
typedef struct {
	char           name[17];      /* the header's 16 bytes, NUL-terminated here */
	uint16_t       vertex_count, normal_count, prim_count, texture_count;
	const SVECTOR *verts;         /* vertex list: 8 bytes each, the SVECTOR layout */
	const SVECTOR *normals;       /* normal list: 8 bytes each, 4.12 */
	const uint8_t *prims;         /* the first primitive record */
	uint32_t       prims_size;
	int16_t        bbox[6];       /* min x y z, max x y z */
	uint16_t       counts[SHP_TYPES];   /* how many records of each type the walk found */
} Shp;

/* Bytes of a record of this type (16 20 24 32 24 32 32 44), or 0 for a tag above 7. */
uint32_t shp_record_size(unsigned type);

/* Decode the record at `rec` into *p and return its size in bytes (shp_record_size(rec[0])).
   Precondition: rec[0] <= 7 and the whole record is inside the file; it reads nothing else, one byte at a time. */
uint32_t shp_decode(const uint8_t *rec, ShpPrim *p);

/* Validate a .SHP image of exactly `size` bytes and fill *s. Checks, in this order, returning at the first failure:
     SHP_ERR_ALIGN    `data` is not a multiple of 4;
     SHP_ERR_MAGIC    size < 4, or no "SHP1";
     SHP_ERR_HEADER   size < 0x40; file_size != size; vertex_count 0 or above SHP_MAX_VERTS; prim_count 0; texture_count above 255;
                      vertices_offset != 0x40; normals_offset != 0x40 + 8*vertex_count; prims_offset != normals_offset + 8*normal_count;
                      prims_offset + prims_size != size;
     SHP_ERR_PRIM     walking prim_count records from prims_offset: fewer than 4 bytes left; a tag above 7; a size field that is not the
                      type's size; a record that does not fit in what remains; or, after prim_count records, bytes left over;
     SHP_ERR_INDEX    in a record that passed the tests above: a vertex index >= vertex_count or a normal index >= normal_count;
     SHP_ERR_TEXTURE  a textured record with tex >= texture_count.
   Per record the order is: PRIM tests, then INDEX, then TEXTURE. *s is unspecified after a failure. */
int shp_parse(const void *data, size_t size, Shp *s);

/* The GPU packet built from a record: sizeof(POLY_F3) ... sizeof(POLY_GT4). With tex != NULL the record's own type decides;
   with tex == NULL (the flat fallback) a textured type becomes the untextured packet of the same shape and colour kind:
   FT3 -> F3, FT4 -> F4, GT3 -> G3, GT4 -> G4. Returns 0 for a bad type. */
uint32_t shp_packet_size(unsigned type, int textured);

/* Fill the packet at `pkt` (shp_packet_size bytes, not initialised) from record *p. `sxy[i]` is the screen position of vertex i as
   gte_stsxy stored it (x in the low 16 bits, y in the high 16). The packet's OT tag length and command byte are set (setPolyXX),
   but the packet is NOT linked. tex != NULL: add the texture's (u, v) to every UV, set tpage and clut from it (textured types only).
   Colours are the record's: flat types use rgb[0] for the whole polygon, Gouraud types one colour per vertex.
   SHP_SEMI_TRANS sets the primitive's semi-transparency bit. */
void shp_fill(void *pkt, const ShpPrim *p, const int32_t *sxy, const Tex *tex);

#endif
