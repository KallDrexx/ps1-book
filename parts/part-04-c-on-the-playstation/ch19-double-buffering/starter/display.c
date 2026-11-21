#include <psxgpu.h>
#include "display.h"

/* TODO: two DISPENVs, two DRAWENVs, and the index of the buffer being drawn into. */

void display_init(void)
{
	/* TODO (README 7.2): ResetGraph, the two environment pairs at (0,0) and (0,240),
	   isbg on both draw environments, show buffer 1, SetDispMask(1). */
}

void display_clear(uint8_t r, uint8_t g, uint8_t b)
{
	(void) r; (void) g; (void) b;
	/* TODO: set the clear color of the back buffer's DRAWENV, then PutDrawEnv it. */
}

void display_swap(void)
{
	/* TODO: DrawSync, VSync, PutDispEnv of the buffer just drawn, then flip. */
}
