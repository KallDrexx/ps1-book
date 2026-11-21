#include <stdint.h>
#include <psxgpu.h>
#include "display.h"

#define HUE_RANGE 1536    /* six color segments of 256 steps */
#define RECT_W    32
#define RECT_H    32
#define RECT_Y    104
#define RECT_MAX  (SCREEN_W - RECT_W)

/* State the verifier reads (and patches the initial values of). Do not change them. */
volatile uint32_t frame_no = 0;     /* frames drawn so far */
volatile uint32_t hue      = 256;   /* 0..1535 */
volatile uint32_t hue_step = 12;    /* hue added per frame */
volatile int32_t  rect_x   = 16;    /* rectangle's left edge, 0..RECT_MAX */

static void hue_to_rgb(uint32_t h, uint8_t *r, uint8_t *g, uint8_t *b)
{
	(void) h;
	*r = *g = *b = 0;
	/* TODO (README 7.3): the six-segment hue table. */
}

static void draw_rect(int32_t x)
{
	(void) x;
	/* TODO (README 7.4): a white RECT_W x RECT_H TILE at (x, RECT_Y), sent with DrawPrim. */
}

static void advance(void)
{
	(void) frame_no; (void) hue_step;   /* the linker drops variables nothing reads */
	/* TODO (README 7.5): frame_no, hue and rect_x for the next frame. */
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
