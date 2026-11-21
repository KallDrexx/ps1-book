#include <stdint.h>
#include <psxe/display.h>
#include <psxe/ot.h>
#include <psxe/gfx.h>
#include <psxe/input.h>

#define NUM_COLORS 6

/* State the verifier reads and patches. Do not change the layout or the initial values. */
typedef struct {
	int32_t x, y;              /* top-left corner of the square */
	int32_t color;            /* index into cursor_colors */
	int32_t speed, fast;       /* pixels per frame: normal, and while Square is held */
	int32_t home_x, home_y;    /* where Start puts the cursor */
	int32_t size;              /* side of the square, in pixels */
} Cursor;

Cursor cursor_state = { 152, 112, 0, 2, 4, 152, 112, 16 };

const uint8_t cursor_colors[NUM_COLORS][3] = {
	{ 230,  40,  40 }, {  40, 200,  60 }, {  60, 110, 255 },
	{ 240, 220,  40 }, { 220,  60, 220 }, {  40, 220, 220 },
};

static int clamp(int v, int lo, int hi)
{
	return v < lo ? lo : (v > hi ? hi : v);
}

static void cursor_update(void)
{
	Cursor *c = &cursor_state;
	int step = input_held(INPUT_SQUARE) ? c->fast : c->speed;

	if (input_held(INPUT_LEFT))  c->x -= step;
	if (input_held(INPUT_RIGHT)) c->x += step;
	if (input_held(INPUT_UP))    c->y -= step;
	if (input_held(INPUT_DOWN))  c->y += step;

	if (input_pressed(INPUT_CROSS))
		c->color = (c->color + 1) % NUM_COLORS;
	if (input_released(INPUT_START)) {
		c->x = c->home_x;
		c->y = c->home_y;
	}
	c->x = clamp(c->x, 0, SCREEN_W - c->size);
	c->y = clamp(c->y, 0, SCREEN_H - c->size);
}

static void cursor_draw(void)
{
	const Cursor *c = &cursor_state;
	const uint8_t *rgb = cursor_colors[c->color];

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
