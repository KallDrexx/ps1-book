#include <stdint.h>
#include <psxgpu.h>
#include "display.h"

/* Depth of each square: 0 = nearest, OT_LEN-1 = farthest. Predict the picture, then edit. */
#define Z_RED   5
#define Z_GREEN 3
#define Z_BLUE  1

#define OT_LEN 8

static uint32_t ot[OT_LEN];     /* the ordering table */
static POLY_F4  sq[3];          /* the primitives: static, DrawOTag reads them after it returns */

static void square(POLY_F4 *p, int x, int y, uint8_t r, uint8_t g, uint8_t b, int z)
{
	setPolyF4(p);                       /* length 5, code 0x28 */
	setXYWH(p, x, y, 100, 100);
	setRGB0(p, r, g, b);
	addPrim(&ot[z], p);                 /* insert at the head of slot z */
}

int main(void)
{
	display_init();

	for (;;) {
		display_clear(24, 24, 32);
		ClearOTagR(ot, OT_LEN);
		square(&sq[0],  60,  60, 255,  40,  40, Z_RED);
		square(&sq[1], 110,  90,  40, 255,  40, Z_GREEN);
		square(&sq[2], 160, 120,  40,  40, 255, Z_BLUE);
		DrawOTag(&ot[OT_LEN - 1]);      /* start at the LAST entry */
		display_swap();
	}
	return 0;
}
