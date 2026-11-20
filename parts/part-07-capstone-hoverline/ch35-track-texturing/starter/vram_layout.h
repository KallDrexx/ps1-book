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

/* TODO (README 7.3, steps 2-3): YOUR plan, one entry per texture id 0..7 of TRACK.TPK, in this order:
     { x, y, w_units, h_lines, tpage word, CLUT word }
   Decide the places on paper first (vram_layout.md), then write the numbers here. Keep clear of the framebuffers, of LOGO.TIM and PROPS.TPK
   (README 5.2 lists what is already in VRAM), keep every tile inside one texture page, and give every tile its own CLUT place.
   Example of one entry (NOT a valid choice: it sits in the framebuffer):
     { 0, 0, 16, 64, TPAGE_4BPP(0, 0), CLUT_AT(0, 500) }                                                                                          */
#define LAYOUT_INIT { \
	{ 0, 0, 0, 0, 0, 0 }, /* id 0 asphalt */ \
	{ 0, 0, 0, 0, 0, 0 }, /* id 1 asphalt_worn */ \
	{ 0, 0, 0, 0, 0, 0 }, /* id 2 lane_stripe */ \
	{ 0, 0, 0, 0, 0, 0 }, /* id 3 boost */ \
	{ 0, 0, 0, 0, 0, 0 }, /* id 4 start_line */ \
	{ 0, 0, 0, 0, 0, 0 }, /* id 5 wall_a */ \
	{ 0, 0, 0, 0, 0, 0 }, /* id 6 wall_b */ \
	{ 0, 0, 0, 0, 0, 0 }, /* id 7 glow */ \
}

extern const TileSlot vram_layout[LAYOUT_TILE_COUNT];

#endif
