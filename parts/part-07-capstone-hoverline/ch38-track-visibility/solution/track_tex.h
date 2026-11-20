#ifndef TRACK_TEX_H
#define TRACK_TEX_H

#include <stdint.h>
#include "tim.h"
#include "track.h"
#include "vram_layout.h"

/* Return codes of track_tex_load (also kept in tex_status). 0 is success; every failure is negative. */
#define TT_ERR_READ   -1     /* the file could not be read from the disc */
#define TT_ERR_PACK   -2     /* tpk_parse or tpk_unpack said no (the pack is damaged) */
#define TT_ERR_COUNT  -3     /* the pack holds more textures than vram_layout has slots */
#define TT_ERR_TIM    -4     /* a texture inside the pack is not a usable TIM */
#define TT_ERR_SLOT   -5     /* a slot of vram_layout is unusable: a rectangle outside VRAM, or its CLUT not 16-aligned, or its tpage word not the page of (x, y) */
#define TT_ERR_FIT    -6     /* a tile does not fit its slot: other bpp than the tpage word says, or other w or h than the slot says */

/* State the verifier reads. Do not change the names or types. */
extern int32_t tex_status;                  /* what track_tex_load returned; TT_ERR_READ until it has run */
extern int32_t track_tex_count;             /* tiles uploaded: 0 after a failure */
extern Tex     track_tex[LAYOUT_TILE_COUNT]; /* per texture id: the tpage word, CLUT word, texel origin (u, v) and size (w, h) polygons need */

/* Load TRACK.TPK (Chapter 31's tpk_parse / tpk_unpack), check every tile against its slot of vram_layout, and upload each tile's
   image and CLUT to the slot's place with tim_upload_at (NOT to the rectangle the TIM names). Fill track_tex[id] for every id.
   Every id is checked (its TIM, then its slot, then the fit) before the first upload; on any failure track_tex_count is 0 and every face is drawn flat.
   Frees every buffer it allocates. Returns 0 or the first error in the order of the codes above, per texture id.
   Checks per id: the image rectangle and the CLUT's (from the CLUT word, so its x is a multiple of 16) inside VRAM; tpage word == getTPage of (x, y)
   for the bpp it declares; TIM bpp == bpp of the tpage word; TIM w and h == the slot's. */
int track_tex_load(const char *path);

/* Texture, UVs and words for one face. Returns 1 and fills the outputs when the face is textured, 0 when it must be drawn flat:
   tex == TRK_UNTEXTURED, tex >= track_tex_count (including: no textures loaded). Otherwise:
   uv[8] = u0 v0 u1 v1 u2 v2 u3 v3, ABSOLUTE texel coordinates inside the page (the tile's origin + the face's texture-local UVs),
   mirrored in U when the face has TRK_FLIP_H (README 5.6); *tpage and *clut = the tile's words. */
int track_face_uv(const TrkFace *f, uint8_t uv[8], uint16_t *tpage, uint16_t *clut);

#endif
