/* Pad viewer: sixteen squares, one per bit of the pad's button word. Lit = the button is down.
   Raw BIOS driver, no library. The squares are in bit order, bit 0 (SELECT) at the left. */
#include <stdint.h>
#include <psxapi.h>
#include <psxgpu.h>
#include <psxpad.h>

static uint8_t pad_buf[2][34];

int main(void)
{
	DISPENV disp;
	DRAWENV draw;
	TILE    t;

	ResetGraph(0);
	SetDefDispEnv(&disp, 0, 0, 320, 240);
	SetDefDrawEnv(&draw, 0, 0, 320, 240);
	setRGB0(&draw, 20, 20, 30);
	draw.isbg = 1;
	PutDispEnv(&disp);
	PutDrawEnv(&draw);
	SetDispMask(1);

	EnterCriticalSection();
	InitPAD(pad_buf[0], 34, pad_buf[1], 34);
	StartPAD();
	ChangeClearPAD(0);
	ExitCriticalSection();

	for (;;) {
		const PADTYPE *pad = (const PADTYPE *) pad_buf[0];
		uint16_t raw = pad->btn;                      /* 0 = down, 1 = up */
		int ok = (pad->stat == 0 && pad->type == PAD_ID_DIGITAL);

		VSync(0);
		for (int bit = 0; bit < 16; bit++) {
			int down = ok && !(raw & (1 << bit));     /* active-low: a 0 bit is a press */

			setTile(&t);
			setXY0(&t, 12 + bit * 19, 100);
			setWH(&t, 16, 16);
			setRGB0(&t, down ? 255 : 50, down ? 200 : 50, down ? 40 : 60);
			DrawPrim((uint32_t *) &t);
		}
	}
	return 0;
}
