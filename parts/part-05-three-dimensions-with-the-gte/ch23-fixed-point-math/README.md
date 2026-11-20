# Chapter 23: Fixed-Point Math

## 1. Concept

The PS1 has no floating-point unit. Fractions are stored as **scaled integers**: the value times a fixed power of two. The GTE, the PS1's 3D coprocessor, works in exactly this way, with 4096 meaning 1.0. Every multiply then needs a matching shift, and every divide a matching pre-shift.

## 2. Why it matters

All of Part V is arithmetic on fractions: rotation matrices, perspective division, camera vectors, gravity. Written with `float` on this CPU, each add or multiply becomes a library call of about 85 instructions. Written in fixed point, it is one or two. The benchmark in this chapter measures the gap.

You also need to know where fixed point bites: products that overflow 32 bits, shifts that round the wrong way, and divisions that lose all their precision. Those bugs look like jittering vertices and exploding physics.

## 3. Learning objectives

After this chapter you can:

- explain what the PS1's missing FPU means and what the compiler does with `float` instead;
- read and write Q notation (4.12, 20.12) and convert between integers, fixed point and floats;
- add, subtract, multiply, divide and interpolate fixed-point values without overflow in the intermediates;
- choose a rounding rule and state it as part of a function's contract;
- compute an integer square root with Newton's method;
- use angles in 4096ths of a turn with the SDK's `isin`/`icos`, and say how accurate they are;
- measure the cost of code in executed instructions.

## 4. Prerequisites

[Chapter 9](../../part-02-thinking-like-the-r3000/ch09-signed-numbers-logic-and-shifts/README.md) (arithmetic vs. logical shifts, rounding toward -infinity), [Chapter 10](../../part-02-thinking-like-the-r3000/ch10-the-stack-and-the-mips-abi/README.md) (callee-saved registers), [Chapter 12](../../part-02-thinking-like-the-r3000/ch12-risc-vs-cisc-multiply-and-divide/README.md) (`mult`, `div`, HI/LO, costs), and the C project layout of [Chapters 18](../../part-04-c-on-the-playstation/ch18-from-assembly-to-c/README.md) and [21](../../part-04-c-on-the-playstation/ch21-working-with-multiple-files/README.md).

## 5. Explanation

### 5.1 No FPU: what happens to `float`

The R3000A has coprocessor 0 (system control) and, on the PS1, coprocessor 2 (the GTE). Coprocessor 1, the slot where MIPS machines put a floating-point unit, is not there. There is no float register and no `add.s`.

If you write `float c = a * b;` GCC still compiles it, using **soft-float**: every operation becomes a call into the toolchain's soft-float `libgcc`.

| C | libgcc call |
|---|---|
| `a + b` | `__addsf3` |
| `a * b` | `__mulsf3` |
| `(float)n` | `__floatsisf` |
| `(int)f` | `__fixsfsi` |
| `a < b` | `__ltsf2` |

(`sf` is single float, `df` is double.) It works, and it is slow, because the call does by hand what an FPU does in silicon. A 32-bit IEEE float looks like this:

```
 31 30      23 22                      0
+--+----------+-------------------------+
| s| exponent |        mantissa         |      value = (-1)^s * 1.mantissa * 2^(exponent - 127)
+--+----------+-------------------------+
  1     8                23 bits
```

To add two floats, software must unpack both, compare exponents, shift one mantissa to align, add, **normalise** (shift until the leading 1 is in place), round, check for overflow, NaN and infinity, and pack the result. A multiply is similar. That is what each `__addsf3`/`__mulsf3` call does, hundreds of times per frame if you use floats for vertices.

Measured in this chapter's benchmark, one loop iteration with one float multiply and one float add executes **177 instructions**. The fixed-point iteration (one `fx_mul`, one add) executes **14**.

**Can you use floats?** Yes, and sometimes you should. Setup code that runs once (the benchmark's `bench_init` converts integers to floats) is fine, and so is a host-side tool. Per-vertex or per-pixel code is not.

### 5.2 Q notation

A **fixed-point number** is an integer whose bits are read as if there were a binary point somewhere inside them. **Q notation** names the split: `m.n` means `m` integer bits and `n` fraction bits (sign included in `m`). The stored integer is `value * 2^n`:

```
4.12 in a 16-bit register (the GTE's vectors and matrices):

   15        12 11                    0
  +------------+------------------------+
  | s  i  i  i | f f f f f f f f f f f f |      raw = value * 4096
  +------------+------------------------+      1.0 = 0x1000 = 4096,  0.5 = 2048,  -1.0 = -4096
   4 int bits       12 fraction bits
```

This book uses two formats:

| Format | Stored in | Range | Step (1 LSB) | Where |
|---|---|---|---|---|
| **4.12** | `int16_t` | -8.0 to +7.99976 | 1/4096 = 0.000244 | GTE rotation matrices, `SVECTOR` entries when used as fractions, `isin`/`icos` results (which fit easily) |
| **20.12** | `int32_t` | -524288.0 to +524287.99976 | 1/4096 | CPU-side math: this chapter's `fx` type |

Both have the same resolution. 20.12 simply has room: the same 12 fraction bits, 20 integer bits. For comparison:

| Format | Range | Step |
|---|---|---|
| 8.8 in `int16_t` | -128 to 127.996 | 0.0039 |
| 16.16 in `int32_t` | -32768 to 32767.99998 | 0.0000153 |

More fraction bits give finer steps and a smaller range; the 32 bits are a budget you divide.

Naming varies. psx-spx writes 4.12 as **1.3.12** (sign, 3 integer bits, 12 fraction bits) and 20.12 as **1.19.12**. Texts that use TI-style Q notation do not count the sign bit and write Q3.12 and Q19.12. All of these mean the same thing: 12 fraction bits, 4096 = 1.0.

Conversions:

```
  raw   = (int)(value * 4096)         from a real number, at build time
  value = raw / 4096.0                to look at it in a debugger
  raw   = n << 12                     from an integer
  n     = raw >> 12                   back to an integer (floors)
```

### 5.3 Add and subtract: no shift

Same format on both sides, so the scale factors agree:

```
  1.5 + 2.25  ->  6144 + 9216 = 15360 = 3.75 * 4096
```

Plain `+` and `-`. The only danger is overflow, which wraps silently. Multiplying a fixed-point value by a plain **integer** also needs no shift (`3 * 1.5` is `3 * 6144`), and neither does comparing two fixed-point values. Only multiply and divide of two *scaled* values need fixing up.

### 5.4 Multiply: widen, multiply, shift

If `a` and `b` are both scaled by 4096, their product is scaled by 4096 * 4096. One factor of 4096 must go:

```
   a (20.12)      x   b (20.12)     =   a*b (40.24 in 64 bits)
   |<-20->|<-12->|    |<-20->|<-12->|    |<------ 40 ------>|<------ 24 ------>|
                                                              shift right 12
                                         result keeps 12 fraction bits  ->  20.12
```

The product of two 32-bit values needs up to **64 bits**. The R3000's `mult` produces exactly that, in HI:LO (Chapter 12). The pitfall is in C:

```c
fx r = (a * b) >> 12;                 // WRONG: a * b is computed in 32 bits and wraps first
fx r = ((int64_t)a * b) >> 12;        // right: widen BEFORE the multiply
fx r = (int64_t)(a * b) >> 12;        // WRONG: the cast comes too late
```

Test it with `100.0 * 100.0`: raw `409600 * 409600 = 1.7e11`, far above 2^31, but the answer (40,960,000) fits easily. The 32-bit version returns garbage. `example/` shows the wrong result.

The compiler turns the right version into `mult`, `mflo`, `mfhi`, two shifts and an `or` that stitch bits 12 to 43 of the product together. That is seven instructions, no libgcc call (the benchmark's `fx_mul`). A 4.12 times 4.12 multiply of two 16-bit values needs no widening: `(a * b) >> 12` is exact in 32 bits.

**Rounding.** The shift discards the low 12 bits. `>>` on a signed value is an *arithmetic* shift (Chapter 9) and **rounds toward minus infinity**:

| a * b (exact) | `>> 12` | `/ 4096` (C division) | Nearest |
|---|---|---|---|
| +0.5 LSB | 0 | 0 | 1 (tie) |
| -0.5 LSB | **-1** | 0 | 0 (tie) |
| +3.7 LSB | 3 | 3 | 4 |
| -3.7 LSB | **-4** | -3 | -4 |

Three policies exist:

- **Floor** (`>> 12`): the cheapest, with a bias of -0.5 LSB per multiply on average. This is what we use.
- **Truncate toward zero** (`/ 4096`): symmetric, but the compiler adds a fix-up for negative values.
- **Round to nearest** (`(p + 2048) >> 12`): one extra add, no bias.

A bias of half an LSB per operation is invisible in one multiply and obvious after thousands of accumulations. Whatever you pick, **write it in the function's contract**. This chapter's verifier checks the exact policy: `fx_mul(-1, 2048)` must be `-1`, not `0`.

### 5.5 Divide: pre-shift, then divide

For `a / b` with both scaled by 4096 the scale cancels, so the result would have no fraction bits. To keep 12, scale the numerator first:

```
  (a << 12) / b       a = 1.0 (4096), b = 3.0 (12288):   (4096 << 12) / 12288 = 1365   (0.3333 * 4096)
```

The shift is where it goes wrong. `a << 12` overflows 32 bits as soon as `|a| >= 2^19`, which is **128.0**. Options:

| Approach | Cost | Catch |
|---|---|---|
| `((int64_t)a << 12) / b` | libgcc's 64-bit divide: about 90 instructions measured | Always correct; slow |
| 32-bit `(a << 12) / b` when `|a| < 2^19` | one `div`: 36 cycles (Chapter 12) | Needs the range test |
| Pre-shift both: `(a << 6) / (b >> 6)` | one `div` | Throws away the low 6 bits of `b`; a small `b` ruins the precision |
| Multiply by a reciprocal: `r = fx_div(ONE, b)` once, then `fx_mul(a, r)` per use | one `mult` per use | Costs one division up front; slightly less exact |

The reference solution uses the second row with a fall-back to the first. The last row is how real engines divide: **avoid divides**, and when dividing many values by the same number, divide once.

Division by zero: the R3000 itself does not trap (Chapter 12), but GCC follows every integer `div` with a test of the divisor and a `break 7`, unless it can prove the divisor is non-zero. `break` raises exception 9 (breakpoint). A game that hits it stops dead. This chapter's contract **saturates** instead, so a degenerate case (a zero-length vector, a point on the camera plane) produces a huge value, not a crash.

### 5.6 Overflow and precision

Both are budgets. You pay in range for precision and in precision for range.

- **Range.** A 20.12 value stops at 524288.0, a 4.12 value at 8.0. Check the *largest value any intermediate takes*, not only the result. `(x*c - y*s)` for `x, y` up to 2000.0 (raw 2^23) and `c, s` up to 4096 reaches 2^36 before the shift; only the 64-bit widening makes it safe.
- **Order of operations.** `a * b / c` computed as `(a * b) / c` keeps precision; `a * (b / c)` throws away the low bits of the quotient first. Multiply first, divide last, as long as the intermediate fits.
- **Accumulated error.** Every multiply loses up to 1 LSB (0.000244). A chain of ten multiplies can drift by a few thousandths. That is invisible on a 320-pixel screen, but a rotation matrix multiplied by itself 1000 times will not stay orthogonal.
- **Saturation vs. wrap.** Integer overflow wraps. The GTE saturates its results and sets flag bits (Chapter 25); the CPU does not.

### 5.7 Linear interpolation

**Lerp** (linear interpolation) walks from `a` to `b` as `t` goes from 0 to 1:

```
  lerp(a, b, t) = a + (b - a) * t
```

With `t` in 20.12 this is `a + fx_mul(b - a, t)`. Two properties come for free with this form: `t = 0` gives exactly `a`, and `t = 1.0` gives exactly `b`, because `fx_mul(d, 4096)` is exactly `d`. The other common form, `a*(1-t) + b*t`, costs two multiplies and rounds twice, but it never forms `b - a`, so it is safe when `a` and `b` are far apart (opposite extremes of the range). That is why the contract says `b - a` must fit in 32 bits. Values of `t` outside 0..1 extrapolate. Lerp is how you move a camera toward a target, fade colours, and animate between keyframes.

### 5.8 Square root with Newton's method

We want `fx_sqrt(x)` for `x` in 20.12. The root of the real value `x/4096`, expressed in 20.12 again, is `sqrt(x/4096) * 4096 = sqrt(x * 4096)`. So the task is an **integer** square root of `n = x << 12` (up to 43 bits, so use `uint64_t`).

**Newton's method** improves a guess `g` for `sqrt(n)` by averaging `g` with `n / g`:

```
  g' = (g + n / g) / 2          n = 10:   g = 4  ->  (4 + 2) / 2 = 3  ->  (3 + 3) / 2 = 3   stop.   floor(sqrt(10)) = 3
```

If `g` is too big, `n / g` is too small and the average lands in between. With integer division, once `g` is at or above the root the sequence **decreases** until it reaches `floor(sqrt(n))`, and then stops decreasing. So:

1. Start at a guess **at or above** the root. `1 << ceil(bits(n) / 2)` always is; `bits(n)` comes from `__builtin_clz`, the count-leading-zeros builtin.
2. Compute `next = (g + n / g) / 2`.
3. If `next >= g`, `g` is the answer; otherwise set `g = next` and repeat.

Convergence is quadratic (the number of correct bits roughly doubles each step), so the loop runs a handful of times. A guess *below* the root breaks the stop test: the first step jumps above the root, so `next >= g` fires at once and returns a wrong, too-small answer. For `x <= 0` return 0. The SDK has `SquareRoot12` too; writing your own shows what it does.

### 5.9 Angles, sine and cosine

3D math needs angles. The PS1 uses **4096 units per full turn**, so one unit is 0.088 degrees:

| Angle | Units |
|---|---|
| 0 | 0 |
| 45 degrees | 512 |
| 90 degrees | 1024 |
| 180 degrees | 2048 |
| 270 degrees | 3072 |
| 360 degrees | 4096 (same as 0) |

A power of two makes wrapping free: `angle & 4095` is `angle mod 4096`, for negative angles too.

PSn00bSDK provides `isin(a)` and `icos(a)` (in `psxgte.h`; `rsin`, `rcos`, `csin` and `ccos` are macros for the same two functions). They take an angle in these units and return an `int` between -4096 and 4096, a **4.12** value: 4096 is 1.0. `hisin`/`hicos` use 131072 units per turn: finer angles, the same polynomial, the same result accuracy.

> The SDK 0.24 header documents the angle as "131072 = 360 degrees" for `isin` and "4194304 = 360 degrees" for `hisin`. The code uses 4096 and 131072 (disassemble `isin.c.obj` in `libpsxgte` to see the masks), so the header figures are 32 times the real ones. 4096 matches Sony's convention, and it is what this chapter's verifier tests.

How good are they? They are not table lookups but a small polynomial (a parabola, corrected). Measured against the true sine over all 4096 angles, **the worst error is 12.5 LSB (0.3 percent)**. The result is exact at 0, 90, 180 and 270 degrees. For graphics this is plenty. It is not plenty if you rotate a vector repeatedly and expect a circle.

The alternative is a **lookup table**: precompute `round(4096 * sin(...))` once and index it. Memory buys accuracy (indexing to the nearest entry, 16-bit values):

| Entries | Bytes | Worst error |
|---|---|---|
| 4096 | 8 KB | 0.5 LSB |
| 1024 | 2 KB | 13 LSB |
| 256 | 512 B | 50 LSB |

So `isin` is about as accurate as a 2 KB table, costs no memory and takes about 25 instructions. A table is faster (one load) and can be exact. Sine has quarter-wave symmetry (`sin(a + 1024) = cos(a)`, `sin(2048 - a) = sin(a)`, `sin(-a) = -sin(a)`), so a table needs only a quarter of the entries. Making your own is a stretch goal.

**2D rotation** by angle `t` turns `(x, y)` into

```
  x' = x cos t - y sin t
  y' = x sin t + y cos t
```

With `c = icos(t)` and `s = isin(t)` in 4.12, each product is 20.12 times 4.12 (a 4.12 value is just a 20.12 value with a small range), so it scales by 4096 and the final `>> 12` is the same as in `fx_mul`. Sum the two products in 64 bits **before** shifting: one shift per output, and half the rounding error of two `fx_mul` calls.

The direction: with `y` pointing up this turns counter-clockwise. On the PS1's screen `y` points down, so the picture turns clockwise.

### 5.10 The contracts at a glance

| Function | Result | Rounding |
|---|---|---|
| `fx_from_int(n)` | `n << 12` | exact |
| `fx_mul(a, b)` | `(a * b) >> 12`, product in 64 bits | floor |
| `fx_div(a, b)` | `(a << 12) / b`, numerator in 64 bits when needed | toward zero; `b == 0` saturates |
| `fx_lerp(a, b, t)` | `a + fx_mul(b - a, t)` | as `fx_mul` |
| `fx_sqrt(x)` | `floor(sqrt(x << 12))`; 0 for `x <= 0` | floor (+/- 1 accepted) |
| `fx_rotate(x, y, angle, &out)` | as in 5.9, one shift per component | floor |

Two different policies (floor for the shift, truncation for `/`) coexist because that is what the hardware and the C operators give for free.

## 6. Worked example

`example/main.c` runs five experiments and leaves the answers in `table`. Predict each row, run it and look:

```sh
cd parts/part-05-three-dimensions-with-the-gte/ch23-fixed-point-math/example
make run
```

| Row | Shows |
|---|---|
| 0 | `100.0 * 100.0`: the 32-bit version, the 64-bit version, the right answer |
| 1 | `-1 LSB * 0.5`: `>> 12` against `/ 4096` |
| 2 | `1.0 / 3.0`, then times 3: it does not come back to 1.0 |
| 3 | The IEEE bit patterns of `0.1f`, `0.2f` and their sum; split them into sign, exponent and mantissa by hand |
| 4 | The step, 1.0 and the 16-bit maximum in raw 4.12 |

It is not checked by `verify.sh`.

## 7. Project: `fixed.h` and `fixed.c`

Work in `starter/fixed.c`. The header `fixed.h` is given, and so are `main.c` (a **test-table driver**: it runs a table of cases through your functions and stores the answers in `results`) and `bench.c` (the benchmark). **Do not edit those three.** The stubs compile and return wrong answers.

`fixed.h` and `fixed.c` are a standalone module in this chapter. In Chapter 24 they move into the `psxe` library, where the software cube uses them.

### 7.1 The contracts

`fx` is `int32_t`, 20.12. `FX_ONE` is 4096. Inputs stay inside the stated range; outside it the result is undefined.

| Function | Contract |
|---|---|
| `fx fx_from_int(int32_t n)` | `n * 4096`. Range: -524288 to 524287. |
| `fx fx_mul(fx a, fx b)` | `floor(a * b / 4096)`, exact in 64 bits. The result must fit in 32 bits. |
| `fx fx_div(fx a, fx b)` | `a * 4096 / b` truncated toward zero. `b == 0`: `INT32_MAX` if `a > 0`, `INT32_MIN` if `a < 0`, 0 if `a == 0`. The result must fit in 32 bits. |
| `fx fx_lerp(fx a, fx b, fx t)` | `a + fx_mul(b - a, t)`, with `b - a` fitting in 32 bits. |
| `fx fx_sqrt(fx x)` | `floor(sqrt(x * 4096))`, accepted within 1; 0 for `x <= 0`; every positive `int32_t`. |
| `void fx_rotate(fx x, fx y, int32_t angle, fx_vec2 *out)` | Rotates by `angle` (4096 = one turn; any value, taken modulo 4096). `out->x = x cos - y sin`, `out->y = x sin + y cos`. Range: `|x|, |y| <= 2000.0`. Accepted within `2 + (|x| + |y|) * 13/4096` LSB of the true rotation (the SDK's `isin` is that accurate), and within 1 LSB at quarter turns. |

All six are plain functions: no globals, no allocation, no floating point.

### 7.2 Your steps

1. **`fx_from_int` and `fx_mul`.** Run `verify.sh`: the mul check names the first wrong case. Try the 32-bit version once on purpose.
2. **`fx_lerp`** from `fx_mul`. It is one line.
3. **`fx_div`**: the zero case first, then the widened division. Add the 32-bit fast path when `a` is small.
4. **`fx_sqrt`** with Newton's method (5.8). Print or trace the guesses for a few inputs in the debugger.
5. **`fx_rotate`** with `isin`/`icos` from `<psxgte.h>`.
6. Read the benchmark's ratio in the verifier's output and compare it with your own estimate.

### 7.3 Rules

- Integers only in `fixed.c`: no `float`, `double`, or libgcc soft-float helper in its object file.
- Do not edit `main.c`, `bench.c` or `bench.h`.
- Do not use `SquareRoot12` or `SquareRoot0` for `fx_sqrt`; write it.

### 7.4 Hints

- Cast **one operand** to `int64_t` before multiplying; the other converts automatically.
- `(int64_t)a << 12` is a shift in 64 bits; `(int64_t)(a << 12)` is not.
- Newton's loop needs no iteration count: stop when `next >= g`.
- `__builtin_clz(x)` gives the number of leading zeros of a non-zero 32-bit value.
- Quarter-turn angles are exact in the SDK; they make the best first test of `fx_rotate`.

### 7.5 Stretch goals

- Round-to-nearest `fx_mul` (`+ 2048` before the shift): measure how much the benchmark sum changes and what it costs.
- A quarter-wave sine table (256 entries, generated by a host-side Python script into a C array) with `fx_sin`/`fx_cos` on top of it, using the symmetries of 5.9. Compare its error with `isin`.
- `fx_div` by reciprocal: `fx_recip(b)` and a division-free path for repeated divisors.
- Make `fx_sqrt` start from a better guess and count the iterations saved.

## 8. Verification

```sh
parts/part-05-three-dimensions-with-the-gte/ch23-fixed-point-math/verify/verify.sh
```

The verifier generates 192 test cases in Python (a seed is printed on failure; `CH23_SEED=n` repeats a run), **patches them into the `tests` table of your executable**, and lets the given driver run them. It also calls every case **directly** from the emulator, with sentinel values in the callee-saved registers. Both sets of answers are compared with Python references.

| Check | What it means | If it fails |
|---|---|---|
| `symbols` | `main`, `tests`, `results`, the six `fx_` functions, the bench functions exist. | A name was removed. |
| `main.c ... and bench.c ... as shipped` | The driver and the benchmark are unchanged. | You edited them; restore them. |
| `fixed.c uses no floating point` | No `float`/`double` in the source, no soft-float symbol (`__mulsf3`, `__floatsisf`, ...) in `fixed.c`'s object file. | Integers only. |
| `fx_from_int`, `fx_mul`, `fx_div`, `fx_lerp` | **Exact** match (including the rounding rules and the zero divisor). Cases include products above 2^31 and numerators above 2^19. | The message shows the case, your answer and the expected one. |
| `fx_sqrt` | Within 1 of `floor(sqrt(x << 12))`, including 0, negative numbers, and `INT32_MAX`. | Wrong start guess or stop test. |
| `fx_rotate` | Within the tolerance of 7.1 of the true rotation: angles from 0 to 4095, negative and over 4096, large and tiny vectors. | Wrong units, wrong sign, shifted twice, or overflow. |
| `every function returns and keeps ...` | Each direct call returns within 60,000 instructions and preserves `$s0`-`$s7`, `$gp`, `$sp`, `$fp`. | An endless loop in Newton. |
| `the driver really calls your functions` | Every case went through your code. | `main.c` edited. |
| `the benchmark: both loops give the right sums` | The float loop yields its exact float32 result. The fixed loop yields the exact sum of `floor(a*b / 4096)`. | `fx_mul` is wrong in the loop's range. |
| `the benchmark: fixed point is at least 5x faster` | The probe counts **instructions executed** and **emulator cycles** between entry and return of `bench_float` and `bench_fixed`; the lower of the two ratios must be 5 or more. | `fx_mul` is slow: a loop, a divide, or a float. |

The benchmark is **deterministic** (no wall clock): the same 128 multiply-accumulates run in each loop, over data produced by an integer generator. The loops are fixed in `bench.c`, so the float side cannot be shortened. The reference solution measures **12.5x** by instruction count and **10.0x** by cycles (about 177 against 14 instructions per iteration). The threshold of 5x leaves room for a clumsier but reasonable `fx_mul`; it rejects a loop-based one.

A pass ends with `CHAPTER 23: PASSED (13/13 checks)`.

## 9. Common pitfalls

- **Multiplying in 32 bits.** `(a * b) >> 12` wraps before the shift. Cast first.
- **`/ 4096` for `>> 12`.** Different rounding for negatives. Both are defensible; the contract says `>>`.
- **`a << 12` overflow in division.** From 128.0 up. Widen before shifting.
- **Dividing by zero.** GCC's `break` trap stops the program; guard `b == 0` and never divide by an unchecked guess.
- **Multiplying two values and shifting twice.** Rotate with one shift on the sum.
- **Mixing formats.** Adding a 20.12 and an integer, or a 4.12 and a 20.12, without shifting. Keep a comment on every variable's format.
- **Newton from a guess that is too small.** Start at or above the root, or the stop test lies.
- **Angles in degrees or radians.** The SDK wants 4096 per turn.
- **Using floats "just for now".** They link and run, which is why they sneak into hot loops. Measure.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- psx-spx, "Geometry Transformation Engine": the 1.3.12 and 1.15.16 number formats and saturation: <https://psx-spx.consoledev.net/>
- PSn00bSDK reference: `psxgte.h` (`isin`, `icos`, `hisin`, `SquareRoot12`).
- Randy Yates, "Fixed-Point Arithmetic: An Introduction": Q notation and rounding in depth.
- Hacker's Delight (Warren), chapter 11: integer square root, including Newton's method.
- Pikuma, "PlayStation Programming", the fixed-point lesson (the reference course for the part).
