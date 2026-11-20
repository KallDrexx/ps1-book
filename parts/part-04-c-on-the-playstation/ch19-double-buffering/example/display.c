#include <psxgpu.h>
#include "display.h"

/* ONE buffer: the TV shows VRAM (0,0) and the GPU draws into the same place.
   Your project's display.c keeps two of each and swaps them. */
static DISPENV disp;
static DRAWENV draw;

void display_init(void)
{
	ResetGraph(0);
	SetDefDispEnv(&disp, 0, 0, SCREEN_W, SCREEN_H);
	SetDefDrawEnv(&draw, 0, 0, SCREEN_W, SCREEN_H);
	draw.isbg = 1;
	PutDispEnv(&disp);      /* never changes: there is nothing to swap */
	SetDispMask(1);
}

void display_clear(uint8_t r, uint8_t g, uint8_t b)
{
	setRGB0(&draw, r, g, b);
	PutDrawEnv(&draw);      /* clears the very buffer the TV is showing */
}

void display_swap(void)
{
	DrawSync(0);
	VSync(0);
}
