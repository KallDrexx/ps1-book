#include <stdint.h>
#include <psxgpu.h>
#include "display.h"

#define HUE_RANGE 1536    /* six colour segments of 256 steps */
#define RECT_W    32
#define RECT_H    32
#define RECT_Y    104
#define RECT_MAX  (SCREEN_W - RECT_W)

/* State the verifier reads (and patches the initial values of). */
volatile uint32_t frame_no = 0;     /* frames drawn so far */
volatile uint32_t hue      = 256;   /* 0..1535 */
volatile uint32_t hue_step = 12;    /* hue added per frame */
volatile int32_t  rect_x   = 16;    /* rectangle's left edge, 0..RECT_MAX */

static void hue_to_rgb(uint32_t h, uint8_t *r, uint8_t *g, uint8_t *b)
{
	uint32_t seg = h >> 8, f = h & 255;

	switch (seg) {
	case 0:  *r = 255;     *g = f;       *b = 0;       break;
	case 1:  *r = 255 - f; *g = 255;     *b = 0;       break;
	case 2:  *r = 0;       *g = 255;     *b = f;       break;
	case 3:  *r = 0;       *g = 255 - f; *b = 255;     break;
	case 4:  *r = f;       *g = 0;       *b = 255;     break;
	default: *r = 255;     *g = 0;       *b = 255 - f; break;
	}
}

/* Stopgap: one flat rectangle sent straight to the GPU. Chapter 20 replaces
   this with an ordering table. static: DrawPrim starts a DMA and returns
   without waiting, so the packet must outlive this function. */
static void draw_rect(int32_t x)
{
	static TILE tile;

	setTile(&tile);
	setXY0(&tile, x, RECT_Y);
	setWH(&tile, RECT_W, RECT_H);
	setRGB0(&tile, 255, 255, 255);
	DrawPrim((uint32_t *) &tile);
}

static void advance(void)
{
	frame_no++;
	hue = (hue + hue_step) % HUE_RANGE;
	rect_x = (rect_x >= RECT_MAX) ? 0 : rect_x + 1;
}

int main(void)
{
	display_init();

	for (;;) {
		uint8_t r, g, b;

		hue_to_rgb(hue, &r, &g, &b);
		display_clear(r, g, b);
		draw_rect(rect_x);
		display_swap();
		advance();
	}
	return 0;
}
