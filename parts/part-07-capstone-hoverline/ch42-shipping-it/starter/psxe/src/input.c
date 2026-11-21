#include <psxapi.h>
#include <psxpad.h>
#include <psxe/input.h>

#define PAD_BUF_SIZE 34

static uint8_t  pad_buf[2][PAD_BUF_SIZE];   /* the BIOS driver fills these from its VBlank handler */
static uint16_t now, before;                /* active-high: bit set = down */

void input_init(void)
{
	EnterCriticalSection();
	InitPAD(pad_buf[0], PAD_BUF_SIZE, pad_buf[1], PAD_BUF_SIZE);
	StartPAD();
	ChangeClearPAD(0);
	ExitCriticalSection();
	now = before = 0;
}

void input_update(void)
{
	const PADTYPE *pad = (const PADTYPE *) pad_buf[0];

	before = now;
	now = 0;
	/* stat 0 = a pad answered. Digital (4), analog stick (5) and DualShock analog (7) share the layout. */
	if (pad->stat == 0 && (pad->type == PAD_ID_DIGITAL || pad->type == PAD_ID_ANALOG_STICK || pad->type == PAD_ID_ANALOG))
		now = (uint16_t) ~pad->btn;          /* the pad sends 0 = down: invert */
}

uint16_t input_buttons(void) { return now; }
int input_held(uint16_t mask)     { return (now & mask) != 0; }
int input_pressed(uint16_t mask)  { return ((now & ~before) & mask) != 0; }
int input_released(uint16_t mask) { return ((before & ~now) & mask) != 0; }
