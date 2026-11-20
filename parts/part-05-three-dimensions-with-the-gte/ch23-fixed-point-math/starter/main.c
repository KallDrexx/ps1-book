#include "fixed.h"
#include "bench.h"

/* Given: the test-table driver.  Do not edit.
 *
 * The verifier writes a table of cases into `tests` before the run (the initial contents below are
 * placeholders: -1 means "no case").  The driver calls your function for every case and stores the
 * answer in `results`; the verifier reads it back and compares it with a Python reference. */

enum { OP_FROM_INT, OP_MUL, OP_DIV, OP_LERP, OP_SQRT, OP_ROTATE };

#define MAX_TESTS 192

typedef struct { int32_t op, a, b, c; } Test;

/* OP_FROM_INT n=a | OP_MUL a,b | OP_DIV a,b | OP_LERP a,b,t=c | OP_SQRT a | OP_ROTATE x=a,y=b,angle=c */
Test tests[MAX_TESTS] = { [0 ... MAX_TESTS - 1] = { -1, 0, 0, 0 } };

/* results[i][0] is the answer; OP_ROTATE also fills results[i][1] (the new y). */
int32_t results[MAX_TESTS][2];

__attribute__((noinline)) void stop_here(void)
{
	__asm__ volatile("" ::: "memory");   /* the verifier stops here */
}

static void run_tests(void)
{
	for (int i = 0; i < MAX_TESTS; i++) {
		const Test *t = &tests[i];
		fx_vec2 v;

		switch (t->op) {
		case OP_FROM_INT: results[i][0] = fx_from_int(t->a);              break;
		case OP_MUL:      results[i][0] = fx_mul(t->a, t->b);             break;
		case OP_DIV:      results[i][0] = fx_div(t->a, t->b);             break;
		case OP_LERP:     results[i][0] = fx_lerp(t->a, t->b, t->c);      break;
		case OP_SQRT:     results[i][0] = fx_sqrt(t->a);                  break;
		case OP_ROTATE:
			fx_rotate(t->a, t->b, t->c, &v);
			results[i][0] = v.x;
			results[i][1] = v.y;
			break;
		}
	}
}

int main(void)
{
	bench_init();
	run_tests();
	bench_float();
	bench_fixed();
	stop_here();
	for (;;)
		;
}
