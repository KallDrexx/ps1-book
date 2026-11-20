#include <stdint.h>
#include <psxe/display.h>
#include <psxe/ot.h>
#include <psxe/gfx.h>
#include <psxe/input.h>

#define NUM_COLOURS 6

/* State the verifier reads and patches. Do not change the layout or the initial values. */
typedef struct {
	int32_t x, y;              /* top-left corner of the square */
	int32_t colour;            /* index into cursor_colours */
	int32_t speed, fast;       /* pixels per frame: normal, and while Square is held */
	int32_t home_x, home_y;    /* where Start puts the cursor */
	int32_t size;              /* side of the square, in pixels */
} Cursor;

Cursor cursor_state = { 152, 112, 0, 2, 4, 152, 112, 16 };

const uint8_t cursor_colours[NUM_COLOURS][3] = {
	{ 230,  40,  40 }, {  40, 200,  60 }, {  60, 110, 255 },
	{ 240, 220,  40 }, { 220,  60, 220 }, {  40, 220, 220 },
};

/* TODO (README 7.4): the rules of the cursor. Called once per frame, after input_update(). */
static void cursor_update(void)
{
}

static void cursor_draw(void)
{
	const Cursor *c = &cursor_state;
	const uint8_t *rgb = cursor_colours[c->colour];

	gfx_quad_f4(c->x, c->y, c->size, c->size, rgb[0], rgb[1], rgb[2], 0);
}

int main(void)
{
	display_init();
	input_init();

	for (;;) {
		input_update();
		cursor_update();
		display_clear(24, 24, 32);
		ot_begin_frame();
		cursor_draw();
		ot_draw();
		display_swap();
	}
	return 0;
}
