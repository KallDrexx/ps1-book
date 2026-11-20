#ifndef PSXE_FIXED_H
#define PSXE_FIXED_H

/* psxe/fixed.h: 20.12 fixed-point arithmetic (Chapter 23).
 *
 * An `fx` is an int32_t holding value * 4096: 1.0 is 4096, 0.5 is 2048, -1.0 is -4096.
 * The contracts below are what verify.sh tests. "Range" is the input range the tests stay in;
 * outside it the result is whatever your code happens to produce.
 */
#include <stdint.h>

typedef int32_t fx;

#define FX_SHIFT 12
#define FX_ONE   (1 << FX_SHIFT)
#define FX_HALF  (FX_ONE / 2)

typedef struct { fx x, y; } fx_vec2;

/* n -> n * 4096.  Range: -524288 <= n <= 524287. */
fx fx_from_int(int32_t n);

/* a * b.  Exact product, shifted right by 12 with an arithmetic shift (rounds toward -infinity).
 * The product a*b may need 64 bits; the result must fit in 32.  (-0.5 * 1 LSB = -1 LSB, not 0.) */
fx fx_mul(fx a, fx b);

/* a / b.  (a * 4096) / b truncated toward zero, as C's `/` does.  The result must fit in 32 bits.
 * b == 0 saturates: a > 0 gives INT32_MAX, a < 0 gives INT32_MIN, a == 0 gives 0. */
fx fx_div(fx a, fx b);

/* a + (b - a) * t, with t in 20.12 (0 gives a, FX_ONE gives b exactly; other t extrapolate).
 * Computed as a + fx_mul(b - a, t).  Range: b - a fits in 32 bits. */
fx fx_lerp(fx a, fx b, fx t);

/* Square root of x as a 20.12 value: floor(sqrt(x * 4096)).  x <= 0 gives 0.  Any positive int32.
 * Accepted: within 1 LSB of the floor. */
fx fx_sqrt(fx x);

/* Rotate (x, y) by `angle` around the origin, counter-clockwise when y points up
 * (clockwise on the PS1 screen, where y points down).  angle: 4096 = one full turn.
 * c = icos(angle), s = isin(angle) (the SDK's 4.12 results);
 * out->x = (x*c - y*s) >> 12, out->y = (x*s + y*c) >> 12, each with ONE shift of the 64-bit sum.
 * Range: |x|, |y| <= 2000.0.  Accepted: within the error of isin()/icos() against the true sine. */
void fx_rotate(fx x, fx y, int32_t angle, fx_vec2 *out);

#endif
