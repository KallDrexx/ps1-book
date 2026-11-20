/* Chapter 30 worked example: the SDK's own TIM helper and two textured quads.
   Loads \DATA\CRATE.TIM from the disc, uploads it with GetTimInfo + LoadImage, prints what it found (TTY),
   and draws the crate on a plain rectangle (left) and on a trapezoid (right) that imitates a face seen at an angle.
   The trapezoid shows the affine wobble: the texture's diagonal bends at the seam where the two triangles meet. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <psxgpu.h>
#include <psxe/display.h>
#include <psxe/ot.h>
#include "cdrom.h"

static void quad(int16_t x0, int16_t y0, int16_t x1, int16_t y1, int16_t x2, int16_t y2, int16_t x3, int16_t y3,
                 uint16_t tpage, uint16_t clut)
{
	POLY_FT4 *p = (POLY_FT4 *) ot_alloc(sizeof(POLY_FT4));

	if (!p)
		return;
	setPolyFT4(p);
	setRGB0(p, 128, 128, 128);
	setXY4(p, x0, y0, x1, y1, x2, y2, x3, y3);
	setUV4(p, 0, 0, 63, 0, 0, 63, 63, 63);       /* the crate is 64 x 64 texels at u0 = v0 = 0 (page 11, 8 bpp) */
	p->tpage = tpage;
	p->clut = clut;
	ot_add(p, 10);
}

int main(void)
{
	TIM_IMAGE tim;
	uint32_t size;
	void *buf;
	uint16_t tpage = 0, clut = 0;

	display_init();
	if (cd_init() && (buf = cd_load_file("\\DATA\\CRATE.TIM;1", &size)) &&
	    GetTimInfo(buf, &tim) == 0) {                /* the SDK's TIM parser: checks the magic only; fills rectangles and data pointers */
		if (tim.mode & 8) {                          /* flags bit 3: a CLUT block is present */
			LoadImage(tim.crect, tim.caddr);
			DrawSync(0);
		}
		LoadImage(tim.prect, tim.paddr);
		DrawSync(0);
		tpage = getTPage(tim.mode & 3, 0, tim.prect->x, tim.prect->y);   /* pmode 0/1/2 = tp 0/1/2 */
		clut = getClut(tim.crect->x, tim.crect->y);
		printf("mode %d  image (%d,%d) %dx%d units  clut (%d,%d) %dx%d\n", (int) tim.mode, tim.prect->x, tim.prect->y,
		       tim.prect->w, tim.prect->h, tim.crect->x, tim.crect->y, tim.crect->w, tim.crect->h);
		printf("tpage 0x%04X  clut 0x%04X\n", tpage, clut);
	} else {
		printf("load failed\n");
	}
	for (;;) {
		display_clear(16, 16, 32);
		ot_begin_frame();
		quad(40, 60, 140, 60, 40, 160, 140, 160, tpage, clut);            /* a plain rectangle */
		quad(190, 50, 290, 80, 190, 170, 290, 140, tpage, clut);          /* a trapezoid: the far edge (right) is shorter */
		ot_draw();
		display_swap();
	}
	return 0;
}
