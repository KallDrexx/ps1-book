#include <stdint.h>
#include <psxgpu.h>
#include "expand.h"

/* Implemented in rgb555.s (Chapter 9's routine, ported to gas). */
extern uint32_t rgb888_to_bgr555(uint32_t rgb);

/* Colour to clear to, 0x00RRGGBB. Writable data on purpose: the verifier patches it. */
volatile uint32_t clear_rgb888 = 0x00FF8040;

static DISPENV disp;
static DRAWENV draw;

__attribute__((noinline)) void stop_here(void)
{
	__asm__ volatile("" ::: "memory");   /* the verifier stops here; keep the call */
}

int main(void)
{
	ResetGraph(0);
	SetDefDispEnv(&disp, 0, 0, 320, 240);
	SetDefDrawEnv(&draw, 0, 0, 320, 240);

	uint32_t rgb = clear_rgb888;   /* read at run time: the verifier patches the variable */
	(void)rgb;

	/* TODO 1: call rgb888_to_bgr555 with rgb.
	 * TODO 2: split the 15-bit result into r, g, b and widen each with expand5.
	 * TODO 3: setRGB0(&draw, r, g, b) and draw.isbg = 1.                          */

	PutDispEnv(&disp);
	PutDrawEnv(&draw);
	SetDispMask(1);
	DrawSync(0);

	stop_here();
	for (;;)
		VSync(0);
}
