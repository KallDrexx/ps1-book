#include <psxgpu.h>
#include <psxe/display.h>

static DISPENV disp[2];
static DRAWENV draw[2];
static int     back;      /* index of the buffer being drawn into */

void display_init_mode(int pal)
{
	ResetGraph(0);
	SetVideoMode(pal ? MODE_PAL : MODE_NTSC);

	/* Buffer 0 at VRAM (0,0), buffer 1 at (0,240). */
	SetDefDispEnv(&disp[0], 0, 0,        SCREEN_W, SCREEN_H);
	SetDefDrawEnv(&draw[0], 0, 0,        SCREEN_W, SCREEN_H);
	SetDefDispEnv(&disp[1], 0, SCREEN_H, SCREEN_W, SCREEN_H);
	SetDefDrawEnv(&draw[1], 0, SCREEN_H, SCREEN_W, SCREEN_H);
	draw[0].isbg = 1;
	draw[1].isbg = 1;

	back = 0;
	PutDispEnv(&disp[1]);   /* show the (empty) other buffer while we draw into 0 */
	SetDispMask(1);
}

void display_init(void)
{
	display_init_mode(0);
}

void display_clear(uint8_t r, uint8_t g, uint8_t b)
{
	setRGB0(&draw[back], r, g, b);
	PutDrawEnv(&draw[back]);
}

void display_swap(void)
{
	DrawSync(0);
	VSync(0);
	PutDispEnv(&disp[back]);
	back ^= 1;
}
