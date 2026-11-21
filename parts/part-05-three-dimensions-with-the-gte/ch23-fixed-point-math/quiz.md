# Chapter 23 Quiz

**1.** The PS1's CPU has no floating-point unit. What does GCC generate for `c = a * b` with `float` operands, and roughly how does it compare with a fixed-point multiply?

<details><summary>Answer</summary>

A call to `__mulsf3` in libgcc (soft-float), which unpacks the sign, exponent and mantissa, multiplies the mantissas, normalizes, rounds and repacks, all in integer instructions. A float multiply plus a float add cost about 177 instructions per iteration of this chapter's loop; the fixed-point equivalent (`fx_mul` plus an add) costs about 14.
</details>

**2.** In 4.12 format, what are the raw values of 1.0, 0.25, -2.5, and the largest and smallest representable numbers? What is the step between neighboring values?

<details><summary>Answer</summary>

1.0 = 4096, 0.25 = 1024, -2.5 = -10240. The `int16_t` raw range -32768 to 32767 gives -8.0 up to 32767/4096 = 7.99976. The step is 1/4096 = 0.000244.
</details>

**3.** What is wrong with `fx r = (a * b) >> 12;` for 20.12 values, and what is the fix? What is `100.0 * 100.0` in raw units?

<details><summary>Answer</summary>

`a * b` is computed in 32 bits and wraps before the shift. With `a = b = 409600` the product is about 1.7e11, far beyond 2^31. Widen one operand first: `((int64_t)a * b) >> 12`. The result is 40,960,000 (10000.0), which fits easily; only the intermediate needs 64 bits.
</details>

**4.** What do `-1 * 2048 >> 12` (that is, `-2048 >> 12`) and `-2048 / 4096` give in C? Which rule does `fx_mul` follow, and what does it cost in accuracy?

<details><summary>Answer</summary>

`-2048 >> 12` is `-1` (an arithmetic shift rounds toward minus infinity); `-2048 / 4096` is `0` (C division truncates toward zero). `fx_mul` floors, so each multiply is biased by about -0.5 LSB on average, which adds up over long accumulations. Rounding to nearest (`+ 2048` before the shift) removes the bias at the price of one add.
</details>

**5.** Why does `(a << 12) / b` fail for `a = 200.0`, and what are two ways to fix it?

<details><summary>Answer</summary>

`a = 200.0` is 819200, and `819200 << 12` is 3.4e9, above `INT32_MAX`. The shift overflows whenever `|a| >= 2^19` (128.0). Fixes: widen to 64 bits (`((int64_t)a << 12) / b`, correct but slow because it calls libgcc's 64-bit divide), or use the 32-bit path when `a` is small and pre-shift or use a reciprocal otherwise. Pre-shifting both operands loses precision when `b` is small.
</details>

**6.** `fx_sqrt(2 * 4096)` should return the square root of 2 in 20.12. What integer square root does the function actually compute, and why must Newton's starting guess be at least the root?

<details><summary>Answer</summary>

`isqrt(8192 << 12) = isqrt(33554432) = 5792`, and 5792/4096 = 1.414. The scaling follows from `sqrt(x/4096) * 4096 = sqrt(x * 4096)`. Newton's iteration `g' = (g + n/g) / 2` decreases monotonically toward `floor(sqrt(n))` from a guess at or above the root, so "stop when `next >= g`" is correct. From below, the first step overshoots and the stop test fires immediately with a wrong answer.
</details>

**7.** In this SDK, what angle does `isin(1024)` represent, and what does it return? What is the worst-case error of `isin` against the true sine, and what would a table need to match it?

<details><summary>Answer</summary>

4096 units are a full turn, so 1024 is 90 degrees, and `isin(1024)` is 4096 (1.0 in 4.12). The worst error over all angles is about 12.5 LSB (0.3 percent), exact at the quarter turns. A nearest-entry lookup table needs about 1024 entries (2 KB of 16-bit values) for 13 LSB, and 4096 entries for 0.5 LSB.
</details>

**8.** `fx_lerp(a, b, t)` is `a + fx_mul(b - a, t)`. Why are `t = 0` and `t = FX_ONE` exact, and what input range does this form need to respect that `a*(1-t) + b*t` does not?

<details><summary>Answer</summary>

`fx_mul(d, 0)` is 0 and `fx_mul(d, 4096)` is `(d * 4096) >> 12 = d` exactly, so the results are `a` and `a + (b - a) = b`. The cost is one multiply, but the difference `b - a` must fit in 32 bits: for `a = -2^31 + 5` and `b = 2^31 - 5` it wraps. The two-term form never subtracts the endpoints, at the price of two multiplies and two roundings.
</details>
