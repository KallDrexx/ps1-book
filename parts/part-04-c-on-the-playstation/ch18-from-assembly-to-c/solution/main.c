#include <stdint.h>
#include <psxgpu.h>
#include "expand.h"

/* Implemented in rgb555.s (Chapter 9, ported to gas). */
extern uint32_t rgb888_to_bgr555(uint32_t rgb);

/* Color to clear to, 0x00RRGGBB. Writable data: the verifier patches it. */
volatile uint32_t clear_rgb888 = 0x00FF8040;

static DISPENV disp;
static DRAWENV draw;

__attribute__((noinline)) void stop_here(void)
{
	__asm__ volatile("" ::: "memory");   /* keeps the call; the verifier stops here */
}

int main(void)
{
	ResetGraph(0);
	SetDefDispEnv(&disp, 0, 0, 320, 240);
	SetDefDrawEnv(&draw, 0, 0, 320, 240);

	uint32_t bgr = rgb888_to_bgr555(clear_rgb888);

	setRGB0(&draw, expand5(bgr & 31),
	               expand5((bgr >> 5) & 31),
	               expand5((bgr >> 10) & 31));
	draw.isbg = 1;

	PutDispEnv(&disp);
	PutDrawEnv(&draw);
	SetDispMask(1);
	DrawSync(0);

	stop_here();
	for (;;)
		VSync(0);
}
