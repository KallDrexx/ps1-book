#include <stdint.h>
#include <stdlib.h>
#include <psxgpu.h>
#include <psxe/display.h>
#include <psxe/ot.h>
#include "cdrom.h"
#include "tim.h"
#include "tpk.h"

#define TPK_PATH "\\DATA\\TEXTURES.TPK;1"
#define GRID_COLS 4
#define GRID_ROWS 2
#define CELL_W 80                    /* the 320 x 240 screen as 4 x 2 cells of 80 x 120 */
#define CELL_H 120
#define QUAD   64                    /* every texture is drawn into a 64 x 64 square ... */
#define QUAD_X 8                     /* ... at (col * 80 + 8, row * 120 + 28) */
#define QUAD_Y 28

/* State the verifier reads and patches. Do not change the names, types or order. */
TpkTextures store;                   /* the global texture store: texture id -> Tex */
int32_t  load_status;                /* 0 = loaded; 100 = CdInit failed; otherwise the negative code tpk_load returned */
uint8_t *tpk_raw;                    /* the decompressed blob, as tpk_load left it ... */
uint32_t tpk_raw_size;               /* ... and its size: the verifier computes the CRC-32 of these bytes */
int32_t  prims_submitted;            /* quads linked into the table this frame */
int32_t  frame_no;                   /* frames completed */

__attribute__((noinline)) void frame_done(void) { __asm__ volatile("" ::: "memory"); }

static void load_textures(void)
{
	if (!cd_init()) {
		load_status = 100;
		return;
	}
	/* TODO (README 7.3, last step): load_status = tpk_load(TPK_PATH, &store);
	   The placeholder below keeps the screen red until your loader works; remove it. */
	load_status = TPK_ERR_READ;
	tpk_raw = store.raw;
	tpk_raw_size = store.raw_size;
}

/* Given: texture id i is drawn in grid cell (i % 4, i / 4), stretched over a 64 x 64 square. */
static void draw_grid(void)
{
	prims_submitted = 0;
	for (int i = 0; i < store.count && i < GRID_COLS * GRID_ROWS; i++) {
		const Tex *t = &store.tex[i];
		int x0 = (i % GRID_COLS) * CELL_W + QUAD_X, y0 = (i / GRID_COLS) * CELL_H + QUAD_Y;
		int u1 = t->u + t->w - 1, v1 = t->v + t->h - 1;
		POLY_FT4 *p = (POLY_FT4 *) ot_alloc(sizeof(POLY_FT4));

		if (!p)
			break;
		setPolyFT4(p);
		setRGB0(p, 128, 128, 128);                     /* neutral: the texel's own colour */
		setXY4(p, x0, y0, x0 + QUAD, y0, x0, y0 + QUAD, x0 + QUAD, y0 + QUAD);
		setUV4(p, t->u, t->v, u1, t->v, t->u, v1, u1, v1);
		p->clut = t->clut;
		p->tpage = t->tpage;
		ot_add(p, 0);
		prims_submitted++;
	}
}

int main(void)
{
	display_init();
	load_textures();
	/* Keeps the state above linked in even where your code does not read it. Leave this line in. */
	__asm__ volatile("" :: "r"(&store), "r"(&load_status), "r"(&tpk_raw), "r"(&tpk_raw_size), "r"(&prims_submitted),
	                 "r"(lzss_decode), "r"(tpk_crc32), "r"(tpk_parse), "r"(tpk_unpack), "r"(tpk_load), "r"(tpk_free_raw));

	for (;;) {
		if (load_status)
			display_clear(96, 0, 0);                   /* red screen: loading failed */
		else
			display_clear(16, 16, 32);
		ot_begin_frame();
		if (!load_status)
			draw_grid();
		ot_draw();
		display_swap();
		frame_no++;
		frame_done();
	}
	return 0;
}
