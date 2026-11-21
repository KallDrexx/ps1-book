/* Chapter 24 worked example: a tunnel. Perspective only, no rotation.
 * Eight square frames, 1.0 apart in depth, drift toward the camera. Each corner is (+-1, +-1, z);
 * the screen position is  center + x * h / z.  Watch the frames bunch up in the distance and
 * spread out as they come near: that is the divide by z. */
#include <stdint.h>
#include <psxgpu.h>
#include <psxe/display.h>
#include <psxe/ot.h>
#include <psxe/fixed.h>

#define FRAMES  8
#define H       200                 /* projection distance, pixels */
#define NEAR    (FX_ONE)            /* a frame closer than this is moved to the far end */

static int16_t sx(fx x, fx z) { return SCREEN_W / 2 + ((fx_div(x, z) * H) >> FX_SHIFT); }
static int16_t sy(fx y, fx z) { return SCREEN_H / 2 + ((fx_div(y, z) * H) >> FX_SHIFT); }

static void line(int16_t x0, int16_t y0, int16_t x1, int16_t y1, uint8_t shade, int depth)
{
	LINE_F2 *l = (LINE_F2 *) ot_alloc(sizeof(LINE_F2));

	if (!l)
		return;
	setLineF2(l);
	setRGB0(l, shade, shade, shade);
	setXY2(l, x0, y0, x1, y1);
	ot_add(l, depth);
}

int main(void)
{
	fx z0 = 2 * FX_ONE;                              /* depth of the nearest frame */

	display_init();
	for (;;) {
		display_clear(0, 0, 24);
		ot_begin_frame();
		for (int i = 0; i < FRAMES; i++) {
			fx z = z0 + i * FX_ONE;
			int16_t l = sx(-FX_ONE, z), r = sx(FX_ONE, z), t = sy(-FX_ONE, z), b = sy(FX_ONE, z);
			uint8_t shade = 255 - i * 28;            /* farther = dimmer */

			line(l, t, r, t, shade, i);
			line(r, t, r, b, shade, i);
			line(r, b, l, b, shade, i);
			line(l, b, l, t, shade, i);
		}
		z0 -= FX_ONE / 20;                           /* toward the camera */
		if (z0 < NEAR)
			z0 += FX_ONE;                            /* the next frame has taken its place */
		ot_draw();
		display_swap();
	}
	return 0;
}
