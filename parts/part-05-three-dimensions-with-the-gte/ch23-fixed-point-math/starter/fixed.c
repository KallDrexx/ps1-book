#include <psxgte.h>   /* isin(), icos(): the SDK's sine and cosine (4096 = one full turn, results in 4.12) */
#include "fixed.h"

/* TODO (README 7): implement the six functions to the contracts in fixed.h.
 * Integers only: no float, no double. Every stub below compiles but returns the wrong answer. */

fx fx_from_int(int32_t n)
{
	(void)n;
	return 0;
}

fx fx_mul(fx a, fx b)
{
	(void)a; (void)b;
	return 0;
}

fx fx_div(fx a, fx b)
{
	(void)a; (void)b;
	return 0;
}

fx fx_lerp(fx a, fx b, fx t)
{
	(void)a; (void)b; (void)t;
	return 0;
}

fx fx_sqrt(fx x)
{
	(void)x;
	return 0;
}

void fx_rotate(fx x, fx y, int32_t angle, fx_vec2 *out)
{
	(void)x; (void)y; (void)angle;
	out->x = 0;
	out->y = 0;
}
