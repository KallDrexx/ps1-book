#include <stdint.h>
#include <psxgpu.h>
#include "display.h"
#include "ot.h"

#define NUM_QUADS 16

typedef struct {
	int16_t x, y, w, h;
	uint8_t r, g, b, pad;
	int32_t depth;          /* 0 = nearest .. OT_LENGTH-1 = farthest */
} Quad;                     /* 16 bytes */

/* State the verifier reads and patches. Do not change the initial values. */
Quad scene[NUM_QUADS] = {
	{   8,   8, 90, 70,  25, 255, 255, 0, 10 },
	{  80,   4, 90, 70,  33,  15, 153, 0, 54 },
	{ 136,  10, 90, 70, 140,  25, 255, 0,  6 },
	{ 209,   6, 90, 70, 153,  15, 119, 0, 50 },
	{  13,  53, 90, 70,  25, 255, 169, 0, 18 },
	{  71,  59, 90, 70,  15, 153,  50, 0,  2 },
	{ 142,  56, 90, 70, 226, 255,  25, 0, 42 },
	{ 206,  60, 90, 70, 153,  15,  15, 0, 34 },
	{   6, 106, 90, 70, 255, 198,  25, 0, 58 },
	{  78, 102, 90, 70,  15, 101, 153, 0, 22 },
	{ 140, 109, 90, 70,  54, 255,  25, 0, 46 },
	{ 201, 104, 90, 70, 153,  67,  15, 0, 14 },
	{  11, 160, 90, 70, 226,  25, 255, 0, 26 },
	{  74, 156, 90, 70,  15,  50, 153, 0, 30 },
	{ 136, 153, 90, 70, 255,  25, 112, 0, 38 },
	{ 212, 158, 90, 70,  84, 153,  15, 0, 62 },
};
volatile uint32_t frame_no    = 0;   /* frames drawn so far */
volatile uint32_t copies      = 1;   /* times the whole scene is submitted per frame */
volatile uint32_t depth_step  = 1;   /* added to every depth after each frame */

static void draw_scene(void)
{
	/* The linker drops what nothing uses; this keeps the pieces linked until you call them. */
	void *volatile linked[] = { (void *) ot_alloc, (void *) ot_add, scene };
	(void) linked; (void) copies;
	/* TODO (README 7.3): submit every quad, `copies` times, as a POLY_F4 at its depth.
	   Stop for the frame when ot_alloc returns NULL. */
}

static void advance(void)
{
	(void) frame_no; (void) depth_step;
	/* TODO (README 7.4): frame_no, and every depth moves by depth_step, modulo OT_LENGTH. */
}

int main(void)
{
	display_init();

	for (;;) {
		display_clear(24, 24, 32);
		ot_begin_frame();
		draw_scene();
		ot_draw();
		display_swap();
		advance();
	}
	return 0;
}
