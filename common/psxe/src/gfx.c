#include <psxgpu.h>
#include <psxe/gfx.h>
#include <psxe/ot.h>

int gfx_quad_f4(int16_t x, int16_t y, int16_t w, int16_t h,
                uint8_t r, uint8_t g, uint8_t b, int depth)
{
	POLY_F4 *p = (POLY_F4 *) ot_alloc(sizeof(POLY_F4));

	if (!p)
		return -1;
	setPolyF4(p);
	setXYWH(p, x, y, w, h);
	setRGB0(p, r, g, b);
	ot_add(p, depth);
	return 0;
}
