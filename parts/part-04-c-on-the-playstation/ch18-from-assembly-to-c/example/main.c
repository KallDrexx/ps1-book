#include <stdint.h>
#include <psxgpu.h>
#include "expand.h"

/* Assembly (callback.s), which itself calls expand5() above. */
extern uint32_t sum_expanded(uint32_t c1, uint32_t c2);

static DISPENV disp;
static DRAWENV draw;

int main(void)
{
	ResetGraph(0);
	SetDefDispEnv(&disp, 0, 0, 320, 240);
	SetDefDrawEnv(&draw, 0, 0, 320, 240);

	/* sum_expanded(0, 31) = 0 + 255; (0, 0) = 0; (8, 8) = 66 + 66: a pink screen (255, 0, 132). */
	setRGB0(&draw, sum_expanded(0, 31), sum_expanded(0, 0), sum_expanded(8, 8));
	draw.isbg = 1;

	PutDispEnv(&disp);
	PutDrawEnv(&draw);
	SetDispMask(1);

	for (;;)
		VSync(0);
}
