#pragma once
/* The benchmark (given, do not edit): the same mul-add loop, once in soft-float and once in fixed point. */
#include "fixed.h"

#define BENCH_N 128

extern float bench_float_result;   /* sum of fa[i] * fb[i] */
extern fx    bench_fixed_result;   /* sum of fx_mul(xa[i], xb[i]) */

void bench_init(void);             /* fills both pairs of arrays from the same integers (outside the timing) */
float bench_float(void);
fx    bench_fixed(void);
