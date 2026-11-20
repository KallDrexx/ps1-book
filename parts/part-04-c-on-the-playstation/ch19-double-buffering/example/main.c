#include <stdint.h>
#include <psxgpu.h>
#include "display.h"

/* 0: the clear and the rectangle are done within VBlank, so even one buffer
   looks fine. 1: the frame's work spans a VBlank (an extra VSync stands in
   for a lot of drawing), and the TV shows the half-finished buffer. */
#define LONG_FRAME 0

static void draw_rect(int x, int y)
{
	static TILE tile;       /* DrawPrim's DMA reads it after the call returns */

	setTile(&tile);
	setXY0(&tile, x, y);
	setWH(&tile, 32, 32);
	setRGB0(&tile, 255, 255, 255);
	DrawPrim((uint32_t *) &tile);
}

int main(void)
{
	int x = 0;

	display_init();

	for (;;) {
		display_clear(64, 64, 96);
#if LONG_FRAME
		VSync(0);
#endif
		draw_rect(x, 104);
		display_swap();
		x = (x + 2) % (SCREEN_W - 32);
	}
	return 0;
}
