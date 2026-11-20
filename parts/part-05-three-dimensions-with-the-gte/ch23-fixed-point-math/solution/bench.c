#include "bench.h"

/* Given: do not edit.  The verifier times each loop with the emulator's cycle counter. */

static float fa[BENCH_N], fb[BENCH_N];
static fx    xa[BENCH_N], xb[BENCH_N];

float bench_float_result;
fx    bench_fixed_result;

void bench_init(void)
{
	uint32_t s = 1;
	for (int i = 0; i < BENCH_N; i++) {
		s = s * 1103515245u + 12345u;
		xa[i] = 2048 + ((s >> 16) & 4095);               /* 0.5 .. 1.5 */
		s = s * 1103515245u + 12345u;
		xb[i] = 2048 + ((s >> 16) & 4095);
		fa[i] = (float)xa[i] * (1.0f / 4096.0f);         /* the same numbers as floats (exact) */
		fb[i] = (float)xb[i] * (1.0f / 4096.0f);
	}
}

__attribute__((noinline)) float bench_float(void)
{
	float acc = 0.0f;
	for (int i = 0; i < BENCH_N; i++)
		acc += fa[i] * fb[i];
	bench_float_result = acc;
	return acc;
}

__attribute__((noinline)) fx bench_fixed(void)
{
	fx acc = 0;
	for (int i = 0; i < BENCH_N; i++)
		acc += fx_mul(xa[i], xb[i]);
	bench_fixed_result = acc;
	return acc;
}
