#include <stdint.h>

/* Chapter 23 worked example: five small experiments with 20.12 numbers. Not checked by verify.sh.
 * Build with `make`, run with `make run`, and look at `table` in the debugger's memory view (Chapter 6).
 * Predict every row before you look. */

#define ONE 4096

typedef struct { int32_t a, b, c; } Row;

Row table[8] = { { 1, 1, 1 } };      /* non-zero initial value: lives in .data, easy to find */

volatile float f_a = 0.1f, f_b = 0.2f;
volatile int32_t one_hundred = 100 * ONE;
volatile int32_t minus_lsb = -1, half = ONE / 2;

__attribute__((noinline)) void stop_here(void) { __asm__ volatile("" ::: "memory"); }

int main(void)
{
	/* 0: 100.0 * 100.0.  {32-bit product (overflows), 64-bit product >> 12, the right answer 10000.0 = 40960000} */
	table[0].a = (one_hundred * one_hundred) >> 12;
	table[0].b = (int32_t)(((int64_t)one_hundred * one_hundred) >> 12);
	table[0].c = 10000 * ONE;

	/* 1: -1 LSB * 0.5.  {>> 12 (floors), / 4096 (truncates toward zero)}  and the exact value -0.5 LSB */
	table[1].a = (int32_t)(((int64_t)minus_lsb * half) >> 12);
	table[1].b = (int32_t)(((int64_t)minus_lsb * half) / 4096);
	table[1].c = 0;

	/* 2: 1.0 / 3.0 in 20.12, and 3 * that: 1.0 does not come back */
	table[2].a = (int32_t)(((int64_t)ONE << 12) / (3 * ONE));
	table[2].b = 3 * table[2].a;
	table[2].c = ONE;

	/* 3: IEEE float: the bit patterns of 0.1f, 0.2f and their sum (split them into sign, exponent, mantissa by hand) */
	float sum = f_a + f_b;
	union { float f; uint32_t u; } x;
	x.f = f_a;  table[3].a = (int32_t)x.u;
	x.f = f_b;  table[3].b = (int32_t)x.u;
	x.f = sum;  table[3].c = (int32_t)x.u;

	/* 4: 4.12 steps: the smallest positive value, 1.0 and the largest value of a 16-bit GTE register */
	table[4].a = 1;
	table[4].b = ONE;
	table[4].c = 32767;

	stop_here();
	for (;;)
		;
}
