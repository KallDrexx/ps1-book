"""Chapter 23 checks: Fixed-Point Math (fixed.h/fixed.c).
STATIC: the symbols exist, the driver (main.c) and the benchmark (bench.c) are as shipped, fixed.c uses no floating
point (no soft-float libgcc symbol is referenced by its object file, no `float`/`double` in its source).
DYNAMIC (probe.lua): the checker generates 192 cases in Python (seed printed; CH23_SEED=n repeats a run) and PATCHES them
into the `tests` table. The given driver runs them (answers in `results`), and the probe also calls every case DIRECTLY
with sentinels in the callee-saved registers. Both answers are compared with the Python references below: exact for
fx_from_int/mul/div/lerp, within 1 LSB for fx_sqrt, within the error of the SDK's sine for fx_rotate. The benchmark loops
(bench.c, given) are timed by the probe: instructions executed and emulator cycles between entry and return."""
import math
import os
import re
import struct
import time
from pathlib import Path

from harness import *

HERE = Path(__file__).resolve().parent
N = 192
OP = {"from_int": 0, "mul": 1, "div": 2, "lerp": 3, "sqrt": 4, "rotate": 5}
FN = {0: "fx_from_int", 1: "fx_mul", 2: "fx_div", 3: "fx_lerp", 4: "fx_sqrt", 5: "fx_rotate"}
INT_MIN, INT_MAX = -(1 << 31), (1 << 31) - 1
SEED = int(os.environ.get("CH23_SEED", int(time.time()) % 100000))
MIN_RATIO = 5.0
BENCH_N = 128

config(
    title="Fixed-Point Math",
    build="cmake", exe="game.exe", sym="", elf="game.elf",
    break_at="stop_here", max_frames=600,
    reads={"results": N * 8, "bench_float_result": ("bench_float_result", 4), "bench_fixed_result": ("bench_fixed_result", 4)},
)


# ---- the references (the contracts in the README) ------------------------------------------------------------------
def s32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


def tdiv(a, b):                       # C division: truncates toward zero
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def ref_from_int(n): return s32(n << 12)
def ref_mul(a, b): return (a * b) >> 12                       # Python's >> floors, like the arithmetic shift
def ref_lerp(a, b, t): return a + (((b - a) * t) >> 12)


def ref_div(a, b):
    if b == 0:
        return INT_MAX if a > 0 else (INT_MIN if a < 0 else 0)
    return tdiv(a << 12, b)


def ref_sqrt(x): return math.isqrt(x << 12) if x > 0 else 0


def ref_rotate(x, y, angle):
    t = 2 * math.pi * (angle % 4096) / 4096
    c, s = math.cos(t), math.sin(t)
    return x * c - y * s, x * s + y * c


def rot_tol(x, y, angle):
    """isin()/icos() are a cheap polynomial, off by up to 12.5 LSB (0.3%); quarter turns are exact."""
    if angle % 1024 == 0:
        return 1
    return 2 + (abs(x) + abs(y)) * 13 / 4096


# ---- test generation --------------------------------------------------------------------------------------------------
def gen_cases(seed):
    rng = random.Random(seed)

    def rbits(w):
        v = rng.getrandbits(w)
        return v if rng.random() < 0.5 else -v

    def clamp(v): return max(INT_MIN, min(INT_MAX, v))

    c = []
    # from_int (12)
    for n in (0, 1, -1, 524287, -524288, 100, -100, 4095):
        c.append((OP["from_int"], n, 0, 0))
    while len(c) < 12:
        c.append((OP["from_int"], rng.randint(-524288, 524287), 0, 0))
    # mul (46): the product often needs more than 32 bits
    mul = [(0, 12345), (4096, 4096), (4096, -4096), (-4096, -4096), (1, 1), (-1, 1), (1, -1), (2048, 1), (-2048, 3),
           (409600, 409600), (1 << 26, 1 << 16), (-(1 << 26), 1 << 16), (46340 * 4096, 4096), (3 * 4096 + 5, -(7 * 4096 + 9)),
           (INT_MAX, 4096), (INT_MIN, 4096), (INT_MAX, 2048), (0x00A00000, 0x00010000)]
    for a, b in mul:
        c.append((OP["mul"], a, b, 0))
    while len(c) < 12 + 46:
        wa = rng.randint(1, 31)
        wb = rng.randint(1, min(31, 43 - wa))
        a, b = rbits(wa), rbits(wb)
        if INT_MIN <= (a * b) >> 12 <= INT_MAX:
            c.append((OP["mul"], a, b, 0))
    # div (36): zero divisors, the 32-bit/64-bit boundary at |a| = 2^19, negative quotients, big quotients
    div = [(5000, 0), (-5000, 0), (0, 0), (INT_MAX, 0), (INT_MIN, 0), (4096, 4096), (4096, 3 * 4096), (-4096, 3 * 4096),
           (4096, -3 * 4096), (-4096, -3 * 4096), (1, 1), (1, 4096), (0, 5), (-1, 4096 * 5), (524287, 7), (-524288, 4096),
           (524288, 4096 * 3), (-524289, 4096 * 3), (1000 * 4096, 3 * 4096), (-1000 * 4096, 3 * 4096), (INT_MAX, 4096 * 2048)]
    for a, b in div:
        c.append((OP["div"], a, b, 0))
    while len(c) < 12 + 46 + 36:
        a, b = rbits(rng.randint(1, 31)), rbits(rng.randint(1, 31))
        if b != 0 and INT_MIN <= tdiv(a << 12, b) <= INT_MAX:
            c.append((OP["div"], a, b, 0))
    # lerp (28)
    lerp = [(0, 100 * 4096, 0), (0, 100 * 4096, 4096), (0, 100 * 4096, 2048), (-50 * 4096, 50 * 4096, 2048),
            (10 * 4096, 20 * 4096, -4096), (10 * 4096, 20 * 4096, 8192), (-7, 7, 2048), (5, 5, 3333), (1000, 0, 1),
            (-3 * 4096 - 1, -4 * 4096 + 3, 1234)]
    for a, b, t in lerp:
        c.append((OP["lerp"], a, b, t))
    while len(c) < 12 + 46 + 36 + 28:
        a, b, t = rbits(rng.randint(1, 30)), rbits(rng.randint(1, 30)), rng.randint(-8192, 12288)
        if INT_MIN <= ref_lerp(a, b, t) <= INT_MAX and INT_MIN <= b - a <= INT_MAX:
            c.append((OP["lerp"], a, b, t))
    # sqrt (30)
    sq = [0, 1, 2, 3, 4095, 4096, 8192, 16384, 9 * 4096, 1 << 20, (1 << 20) + 1, (1 << 20) - 1, INT_MAX, INT_MAX - 1,
          -1, -4096, INT_MIN, 10 ** 9, 123456789]
    for v in sq:
        c.append((OP["sqrt"], v, 0, 0))
    while len(c) < 12 + 46 + 36 + 28 + 30:
        c.append((OP["sqrt"], rng.getrandbits(rng.randint(1, 31)), 0, 0))
    # rotate (40)
    rot = [(4096, 0, 0), (4096, 0, 1024), (4096, 0, 2048), (4096, 0, 3072), (0, 4096, 1024), (3 * 4096, 4 * 4096, 512),
           (2000 * 4096, 2000 * 4096, 2560), (-2000 * 4096, 1999 * 4096, 4095), (0, 0, 700), (4096, 4096, -1024),
           (4096, 0, 4096 + 1024), (5000, -7000, -1), (100 * 4096, 0, 300), (1, 1, 123)]
    for x, y, a in rot:
        c.append((OP["rotate"], x, y, a))
    while len(c) < N:
        c.append((OP["rotate"], rng.randint(-2000 * 4096, 2000 * 4096), rng.randint(-2000 * 4096, 2000 * 4096),
                  rng.randint(0, 4095)))
    assert len(c) == N
    return c


import random

CASES = gen_cases(SEED)
TABLE = b"".join(struct.pack("<4i", *t) for t in CASES)


def judge(case, got0, got1=None):
    """None if (got0, got1) is acceptable for this case, else the expected value as text."""
    op, a, b, c = case
    if op == OP["from_int"]: e = ref_from_int(a)
    elif op == OP["mul"]: e = ref_mul(a, b)
    elif op == OP["div"]: e = ref_div(a, b)
    elif op == OP["lerp"]: e = ref_lerp(a, b, c)
    elif op == OP["sqrt"]:
        e = ref_sqrt(a)
        return None if abs(got0 - e) <= 1 else f"{e} (or {e - 1}..{e + 1})"
    else:
        ex, ey = ref_rotate(a, b, c)
        tol = rot_tol(a, b, c)
        if abs(got0 - ex) <= tol and abs(got1 - ey) <= tol:
            return None
        return f"({ex:.1f}, {ey:.1f}) +/- {tol:.1f}"
    return None if got0 == e else str(e)


def desc(case):
    op, a, b, c = case
    n = FN[op]
    if op in (OP["from_int"], OP["sqrt"]): return f"{n}({a})"
    if op == OP["lerp"]: return f"{n}({a}, {b}, {c})"
    if op == OP["rotate"]: return f"{n}({a}, {b}, angle={c})"
    return f"{n}({a}, {b})"


def run(ctx):
    r = ctx.run("main", patches={"tests": TABLE})
    try:
        r.require_break()
    except CheckFailure as e:
        if "(break)" in str(e.actual):
            e.hint = ("Exception 9 (break) is GCC's trap for an integer divide by zero. fx_div(a, 0) must be handled before the "
                      "division (and fx_sqrt must never divide by a zero guess). " + (e.hint or ""))
        raise
    return r


def indices(op): return [i for i, t in enumerate(CASES) if t[0] == op]


def results(r):
    w = r.words("results", N * 2, signed=True)
    return [(w[2 * i], w[2 * i + 1]) for i in range(N)]


def direct(r):
    calls = r.record("calls")
    expect_true(calls and len(calls) == N, f"{N} direct calls recorded", str(len(calls or [])),
                "Does `main` still run? The probe calls your functions when main is first reached.")
    return calls


def s(v): return s32(v)


def compare(ctx, op, what, hint):
    """Driver answers and direct-call answers against the reference for every case of `op`."""
    r = run(ctx)
    res, calls = results(r), direct(r)
    bad = []
    for i in indices(op):
        case = CASES[i]
        for src, vals in (("driver", res[i]), ("direct call", None)):
            if vals is None:
                rec = calls[i]
                vals = (s(rec["o0"]), s(rec["o1"])) if op == OP["rotate"] else (s(rec["v0"]), 0)
            miss = judge(case, vals[0], vals[1])
            if miss is not None:
                got = f"({vals[0]}, {vals[1]})" if op == OP["rotate"] else str(vals[0])
                bad.append(f"{desc(case)} -> {got}, expected {miss}  [{src}]")
                break
    if bad:
        raise CheckFailure(expected=f"{what}: all {len(indices(op))} cases correct", actual=f"{len(bad)} wrong; first: {bad[0]}",
                           message="\n".join(bad[:4]) + (f"\n... {len(bad) - 4} more" if len(bad) > 4 else ""),
                           hint=f"{hint}  (seed {SEED}: CH23_SEED={SEED} repeats this run)")


# ---- static checks ------------------------------------------------------------------------------------------------
@static_check("symbols", hint="Keep main, tests, results, stop_here, the six fx_ functions and the two bench_ functions. The linker drops functions nobody calls: the driver in main.c calls them all.")
def _(ctx):
    ctx.require_symbols("main", "tests", "results", "stop_here", "bench_init", "bench_float", "bench_fixed",
                        *FN.values())


def _norm(p):
    return re.sub(r"\s+", " ", p.read_text(errors="replace")).strip() if p.exists() else None


@static_check("main.c (the driver) and bench.c (the benchmark) are as shipped",
              hint="Do not edit main.c, bench.c or bench.h: the verifier times your fixed.c through those loops. All your work goes in fixed.c.")
def _(ctx):
    ref = HERE.parent / "solution"
    for f in ("main.c", "bench.c", "bench.h"):
        mine, shipped = _norm(ctx.project / f), _norm(ref / f)
        expect_true(mine is not None, f"{f} exists", "missing")
        expect_true(mine == shipped, f"{f} unchanged", "it was edited", f"Restore {f} from the book (it is identical in starter/ and solution/).")


@static_check("fixed.c uses no floating point",
              hint="The point of the chapter: integers only. Soft-float calls (__mulsf3, __floatsisf, ...) cost about 85 instructions each in the benchmark.")
def _(ctx):
    src = ctx.source_text("fixed.c", strip_comments=False)
    src = re.sub(r"/\*.*?\*/|//[^\n]*", " ", src, flags=re.S)   # C comments may say "float" or "1.0"
    m = re.search(r"\b(float|double)\b|\b\d+\.\d*[fF]?\b|\b\d*\.\d+[fF]?\b", src)
    expect_true(not m, "no float/double in fixed.c", f"found `{m.group(0)}`" if m else "")
    import shutil, subprocess
    nm = shutil.which("mipsel-none-elf-nm")
    objs = list(ctx.build.build_dir.rglob("fixed.c.obj"))
    expect_true(objs and nm, "fixed.c's object file is available", "not found")
    out = subprocess.run([nm, "--undefined-only", str(objs[0])], capture_output=True, text=True).stdout.split()
    soft = [n for n in out if re.fullmatch(r"__\w*(sf|df)(\d|si|di|ti)?\d*|__\w*(si|di)(sf|df)\d*", n)]
    expect_true(not soft, "no soft-float helper referenced from fixed.o", f"references {soft}")


# ---- dynamic checks ------------------------------------------------------------------------------------------------
@check("fx_from_int: n * 4096", hint="n << 12.")
def _(ctx):
    compare(ctx, OP["from_int"], "fx_from_int", "n << 12 (range -524288..524287).")


@check("fx_mul: exact, 64-bit product, shifted right 12 (rounds toward -infinity)",
       hint="((int64_t)a * b) >> 12. A 32-bit product overflows when a*b >= 2^31: 100.0 * 100.0 is 1.7e11. Casting AFTER the multiply is too late.")
def _(ctx):
    compare(ctx, OP["mul"], "fx_mul", "Widen BEFORE multiplying, then shift right with >> (an arithmetic shift), not / 4096.")


@check("fx_div: (a << 12) / b truncated toward zero; division by zero saturates",
       hint="(a << 12) overflows 32 bits when |a| >= 2^19: widen to 64 bits first. Check b == 0 before dividing (the R3000 has no divide trap, and GCC adds `break 7`).")
def _(ctx):
    compare(ctx, OP["div"], "fx_div", "Widen the numerator to int64_t before shifting; return INT32_MAX / INT32_MIN / 0 for b == 0.")


@check("fx_lerp: a + (b - a) * t, with t in 20.12",
       hint="a + fx_mul(b - a, t). t = 0 must give a and t = 4096 must give b exactly.")
def _(ctx):
    compare(ctx, OP["lerp"], "fx_lerp", "a + fx_mul(b - a, t).")


@check("fx_sqrt: floor(sqrt(x * 4096)) within 1; x <= 0 gives 0",
       hint="sqrt of the 20.12 value x is sqrt(x << 12) as an integer: take the integer square root of a 64-bit number.")
def _(ctx):
    compare(ctx, OP["sqrt"], "fx_sqrt", "isqrt((uint64_t)x << 12), with Newton's method (start at or above the root, stop when the guess stops decreasing).")


@check("fx_rotate: matches cos/sin rotation (4096 = one full turn)",
       hint="c = icos(angle), s = isin(angle); x' = (x*c - y*s) >> 12 and y' = (x*s + y*c) >> 12, summed in 64 bits. Angles in 4096ths of a turn, not degrees.")
def _(ctx):
    compare(ctx, OP["rotate"], "fx_rotate", "Both products widened to int64_t before the multiply; one shift at the end.")


@check("every function returns and keeps $s0-$s7, $gp, $sp, $fp",
       hint="The O32 rule (Chapter 10): callee-saved registers must come back unchanged. In C this only fails if you write inline assembly.")
def _(ctx):
    r = run(ctx)
    for rec in direct(r):
        expect_true(rec["returned"], f"{rec['fn']} returns", "did not return within the instruction limit",
                    "An endless loop? In fx_sqrt, Newton's loop must stop when the guess stops decreasing.")
        expect_true(not rec["clobbered"], f"{rec['fn']} preserves callee-saved registers", f"changed {rec['clobbered']}")


@check("the driver really calls your functions",
       hint="Do not edit main.c; every case of the table goes through the function under test.")
def _(ctx):
    r = run(ctx)
    ent = r.record("entries") or {}
    for op, name in FN.items():
        n = len(indices(op))
        expect_true(ent.get(name, 0) >= n, f"{name} entered at least {n} times by the driver", str(ent.get(name, 0)))


EXPECT_BENCH = None


def bench_expected():
    s_, fa, fb, xa, xb = 1, [], [], [], []

    def f32(v): return struct.unpack("<f", struct.pack("<f", v))[0]
    for _ in range(BENCH_N):
        s_ = (s_ * 1103515245 + 12345) & 0xFFFFFFFF
        a = 2048 + ((s_ >> 16) & 4095)
        s_ = (s_ * 1103515245 + 12345) & 0xFFFFFFFF
        b = 2048 + ((s_ >> 16) & 4095)
        xa.append(a); xb.append(b); fa.append(a / 4096); fb.append(b / 4096)
    acc = 0.0
    for a, b in zip(fa, fb):
        acc = f32(acc + f32(a * b))
    fx = sum((a * b) >> 12 for a, b in zip(xa, xb))
    return acc, fx


@check("the benchmark: both loops give the right sums",
       hint="bench_fixed sums fx_mul(xa[i], xb[i]) over 128 values; the sum must equal the Python sum of floor(a*b/4096). A wrong fx_mul shows up here too.")
def _(ctx):
    r = run(ctx)
    ef, ex = bench_expected()
    got_f = struct.unpack("<f", struct.pack("<I", r.u32("bench_float_result")))[0]
    got_x = r.s32("bench_fixed_result")
    expect_true(got_f == ef, f"float sum {ef!r}", f"{got_f!r}", "bench.c was edited or the soft-float loop did not run.")
    expect_true(got_x == ex, f"fixed sum {ex} (= {ex / 4096:.4f})", f"{got_x}", "Your fx_mul gives a different sum from floor(a*b / 4096).")


@check(f"the benchmark: fixed point is at least {MIN_RATIO:g}x faster than soft-float",
       hint="The loop is a multiply-accumulate: fx_mul must stay a few instructions. No loops, no 64-bit divide, no float inside fx_mul.")
def _(ctx):
    r = run(ctx)
    fl, fi = r.record("bench_float"), r.record("bench_fixed")
    expect_true(fl and fi, "both benchmark loops timed", "no timing recorded", "Is bench_float/bench_fixed still called by main?")
    ri, rc = fl["instrs"] / max(fi["instrs"], 1), fl["cycles"] / max(fi["cycles"], 1)
    print(f"        float: {fl['instrs']} instrs, {fl['cycles']} cycles   fixed: {fi['instrs']} instrs, {fi['cycles']} cycles   "
          f"ratio: {ri:.1f}x instrs, {rc:.1f}x cycles  ({BENCH_N} iterations)")
    worst = min(ri, rc)
    expect_true(worst >= MIN_RATIO, f"float/fixed ratio >= {MIN_RATIO:g}",
                f"{ri:.1f}x by instructions, {rc:.1f}x by cycles ({fi['instrs'] // BENCH_N} instructions per fixed iteration)")
