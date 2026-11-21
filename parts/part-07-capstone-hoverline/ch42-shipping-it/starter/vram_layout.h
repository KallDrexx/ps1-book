#ifndef VRAM_LAYOUT_H
#define VRAM_LAYOUT_H

#include <stdint.h>
#include <psxgpu.h>

/* The VRAM plan for the track tiles (README 5 and your vram_layout.md).
   The verifier reads the table `vram_layout` from RAM: one TileSlot per texture id of TRACK.TPK, in id order, 12 bytes each.
   Units: x and w are 16-bit VRAM units (as in a TIM), y and h are lines. */
typedef struct {
	uint16_t x, y;                   /* where the tile's image goes in VRAM */
	uint16_t w, h;                   /* its size: w in units (4 bpp: texels / 4), h in lines */
	uint16_t tpage;                  /* the texture-page word polygons use for this tile (abr = 0) */
	uint16_t clut;                   /* the CLUT word polygons use for this tile */
} TileSlot;
_Static_assert(sizeof(TileSlot) == 12, "TileSlot is 12 bytes: the verifier reads it from RAM");

/* Helpers for the two words: a 4-bpp page word for an image at (x, y), and the CLUT word for a CLUT at (x, y). */
#define TPAGE_4BPP(x, y)  getTPage(0, 0, (x), (y))
#define CLUT_AT(x, y)     getClut((x), (y))

#define LAYOUT_TILE_COUNT 8          /* TRACK.TPK holds 8 tiles */

/* The plan, solution version (vram_layout.md has the picture):
     tiles: one texture page, x 576..639, y 256..383: two rows of four 16 x 64 tiles (id i at column i % 4, row i / 4)
     CLUTs: one row of eight 16 x 1 CLUTs at y = 488, x = 64 + 16 * i (below the framebuffers, left of the other CLUTs) */
#define LAYOUT_INIT { \
	{ 576, 256, 16, 64, TPAGE_4BPP(576, 256), CLUT_AT(64, 488) }, /* id 0 */ \
	{ 592, 256, 16, 64, TPAGE_4BPP(592, 256), CLUT_AT(80, 488) }, /* id 1 */ \
	{ 608, 256, 16, 64, TPAGE_4BPP(608, 256), CLUT_AT(96, 488) }, /* id 2 */ \
	{ 624, 256, 16, 64, TPAGE_4BPP(624, 256), CLUT_AT(112, 488) }, /* id 3 */ \
	{ 576, 320, 16, 64, TPAGE_4BPP(576, 320), CLUT_AT(128, 488) }, /* id 4 */ \
	{ 592, 320, 16, 64, TPAGE_4BPP(592, 320), CLUT_AT(144, 488) }, /* id 5 */ \
	{ 608, 320, 16, 64, TPAGE_4BPP(608, 320), CLUT_AT(160, 488) }, /* id 6 */ \
	{ 624, 320, 16, 64, TPAGE_4BPP(624, 320), CLUT_AT(176, 488) }, /* id 7 */ \
}

extern const TileSlot vram_layout[LAYOUT_TILE_COUNT];

#endif
