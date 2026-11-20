#include <psxgte.h>   /* isin, icos */
#include <psxe/fixed.h>

fx fx_from_int(int32_t n)
{
	return n << FX_SHIFT;
}

fx fx_mul(fx a, fx b)
{
	return (fx)(((int64_t)a * b) >> FX_SHIFT);
}

fx fx_div(fx a, fx b)
{
	if (b == 0)
		return a > 0 ? INT32_MAX : (a < 0 ? INT32_MIN : 0);
	/* Fast path: a * 4096 fits in 32 bits, so one `div` (36 cycles) does it. */
	if (a >= -(1 << 19) && a < (1 << 19))
		return (a << FX_SHIFT) / b;
	return (fx)(((int64_t)a << FX_SHIFT) / b);          /* libgcc's __divdi3: slow */
}

fx fx_lerp(fx a, fx b, fx t)
{
	return a + fx_mul(b - a, t);
}

fx fx_sqrt(fx x)
{
	if (x <= 0)
		return 0;
	uint64_t n = (uint64_t)x << FX_SHIFT;                /* sqrt(x/4096) * 4096 = sqrt(x * 4096) */
	int bits = 32 - __builtin_clz((uint32_t)x) + FX_SHIFT;
	uint64_t g = (uint64_t)1 << ((bits + 1) / 2);        /* never below the root */
	for (;;) {
		uint64_t next = (g + n / g) / 2;
		if (next >= g)
			return (fx)g;
		g = next;
	}
}

void fx_rotate(fx x, fx y, int32_t angle, fx_vec2 *out)
{
	int64_t c = icos(angle), s = isin(angle);
	out->x = (fx)((x * c - y * s) >> FX_SHIFT);
	out->y = (fx)((x * s + y * c) >> FX_SHIFT);
}
