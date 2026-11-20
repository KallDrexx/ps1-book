"""Chapter 8 checks: factorial / sum_array / max_array as real subroutines.
Phase 1 (probe.lua): the harness calls each routine DIRECTLY, many times, with random and edge-case
arguments, with $ra aimed at a return trampoline, callee-saved registers ($s0-$s7, $gp, $sp, $fp)
seeded with sentinels and caller-saved ones filled with garbage. Checks: results, the return
actually happened, nothing callee-saved changed, the array was only read, bounded instruction count.
Phase 2: the whole program runs on several patched data sets; the driver must call the routines
and store their results."""
import math
import struct

from harness import *

M = 0xFFFFFFFF

config(
    title="Subroutines",
    main="main.s", exe="main.ps-exe", sym="main.sym",
    break_at="done", reads={"results": 40},
    max_frames=300,
)

# ---- shipped data and patchable data sets ----------------------------------
SHIPPED = {
    "drv_n": [5, 0, 12, 7],
    "drv_len1": [6],
    "drv_arr1": [3, 9, -4, 12, 7, 1, 0, 0],
    "drv_len2": [4],
    "drv_arr2": [-5, -9, -2, -7, 0, 0, 0, 0],
}
SIZES = {"drv_n": 4, "drv_len1": 1, "drv_arr1": 8, "drv_len2": 1, "drv_arr2": 8}
POISON = b"\xAA" * 40


def sw(vals): return struct.pack(f"<{len(vals)}i", *vals)


def data_patch(n, len1, arr1, len2, arr2):
    return {"drv_n": sw(n), "drv_len1": sw([len1]), "drv_arr1": sw(arr1 + [0] * (8 - len(arr1))),
            "drv_len2": sw([len2]), "drv_arr2": sw(arr2 + [0] * (8 - len(arr2))), "results": POISON}


SETS = {
    "shipped": dict(n=[5, 0, 12, 7], len1=6, arr1=[3, 9, -4, 12, 7, 1], len2=4, arr2=[-5, -9, -2, -7]),
    "edges":   dict(n=[20, 1, 13, 2], len1=8, arr1=[-2147483648, 2147483647, 5, -1, 0, 100, -100, 7],
                    len2=1, arr2=[-42]),
    "small":   dict(n=[0, 0, 1, 3], len1=1, arr1=[-17], len2=8,
                    arr2=[-1, -2, -3, -4, -5, -6, -7, -8]),
    "mixed":   dict(n=[11, 6, 9, 4], len1=7, arr1=[1000, -1000, 33, 44, -55, 66, 1], len2=5,
                    arr2=[7, 7, 7, 7, 7]),
}


def to_signed(v):
    v &= M
    return v - (1 << 32) if v & 0x80000000 else v


def expected_results(s):
    a1, a2 = s["arr1"][: s["len1"]], s["arr2"][: s["len2"]]
    return [math.factorial(n) & M for n in s["n"]] + [
        sum(a1) & M, max(a1) & M, sum(a2) & M, max(a2) & M, 0, s["arr1"][0] & M]


# ---- static checks ----------------------------------------------------------
@static_check("program defines main, done, the three routines, results and the driver's data",
              hint="Keep every label the starter declares: main, done, factorial, sum_array, max_array, "
                   "results, drv_n, drv_len1, drv_arr1, drv_len2, drv_arr2. Data must be word-aligned.")
def _(ctx):
    ctx.require_symbols("main", "done", "factorial", "sum_array", "max_array", "results",
                        "drv_n", "drv_len1", "drv_arr1", "drv_len2", "drv_arr2")
    for n in ("results", "drv_n", "drv_len1", "drv_arr1", "drv_len2", "drv_arr2"):
        expect_true(ctx.symbols[n] % 4 == 0, f"{n} word-aligned", f"0x{ctx.symbols[n]:08X}")
    s = ctx.symbols
    expect_true(s["main"] < s["done"], "main before done", f"main 0x{s['main']:08X}, done 0x{s['done']:08X}",
                hint="The driver lives between `main` and `done`; the routines go after `done`.")
    for r in ("factorial", "sum_array", "max_array"):
        expect_true(s[r] > s["done"], f"{r} placed after `done` (so the driver cannot fall into it)",
                    f"0x{s[r]:08X}")


@static_check("data tables are as shipped (inputs unedited, results zero)",
              hint="Do not edit drv_* or pre-fill `results`; the verifier patches its own data.")
def _(ctx):
    def raw(sym, n):
        off = ctx.symbols[sym] - ctx.exe.load_addr
        return ctx.exe.code[off:off + 4 * n]
    for k, v in SHIPPED.items():
        got = raw(k, SIZES[k])
        want = sw(v)
        expect_eq(got, want, f"{k} in the executable")
    expect_true(not any(raw("results", 10)), "results all zero", "results contains data")


def driver(ctx): return ctx.disassemble_range("main", "done")


@static_check("the driver calls the routines with jal/jalr",
              hint="`main` must call factorial, sum_array and max_array with `jal` (or `jalr` through a "
                   "register). Falling into them or copy-pasting their bodies into the driver does not count.")
def _(ctx):
    insns = driver(ctx)
    calls = [i for i in insns if (i.word >> 26) == 3 or ((i.word >> 26) == 0 and (i.word & 0x3F) == 9)]
    targets = {((i.addr + 4) & 0xF0000000) | ((i.word & 0x03FFFFFF) << 2) for i in calls if (i.word >> 26) == 3}
    uses_jalr = any((i.word >> 26) == 0 for i in calls)
    expect_true(calls, "jal/jalr between main and done", "none")
    for r in ("factorial", "sum_array", "max_array"):
        expect_true(ctx.symbols[r] in targets or uses_jalr, f"a `jal {r}` in the driver", "no call to it")


@static_check("armips reports no warnings",
              hint="Usually a load delay: a loaded register used by the very next instruction. "
                   "Careful with `lw $a0` directly before `jal` when the callee uses $a0 at once.")
def _(ctx):
    bad = [l.strip() for l in ctx.build_log.splitlines() if "warning" in l.lower()]
    expect_true(not bad, "no warnings", "; ".join(bad[:2]))


# ---- dynamic helpers ---------------------------------------------------------
def calls_of(ctx):
    r = ctx.result
    r.require_break()
    cs = r.record("calls")
    expect_true(cs, "the probe recorded direct calls", "none",
                hint="The routines must exist and the program must start at `main`.")
    return cs, r.record("seed")


def describe(c):
    if c["fn"] == "factorial":
        return f"factorial({c['a0']})"
    return f"{c['fn']}(ptr, len={c['len']}) on {c['vals'][:c['len']]}"


def want(c):
    if c["fn"] == "factorial":
        return math.factorial(c["a0"]) & M
    v = c["vals"][: c["len"]]
    return (sum(v) & M) if c["fn"] == "sum_array" else (max(v) & M)


def each(ctx, fn):
    cs, seed = calls_of(ctx)
    seen = 0
    for c in cs:
        if c["fn"] == fn:
            seen += 1
            yield c, seed
    expect_true(seen > 0, f"direct calls of {fn}", "none")


# ---- dynamic checks ----------------------------------------------------------
@check("program reaches `done`",
       hint="A hang means a loop that never ends, or a routine that never returns. Run with -v.")
def _(ctx):
    ctx.result.require_break()


def result_check(ctx, fn):
    returned = 0
    for c, seed in each(ctx, fn):
        if not c["returned"]:
            continue  # reported by the "returns" check
        returned += 1
        if (c["v0"] & M) != want(c):
            raise CheckFailure(
                expected=f"$v0 = {want(c)} (0x{want(c):08X})", actual=f"$v0 = {c['v0'] & M} (0x{c['v0'] & M:08X})",
                message=f"{describe(c)} gave the wrong result (probe seed {seed})")
    expect_true(returned > 0, f"at least one call of {fn} returns", "no call returned",
                hint=f"Every direct call of {fn} ran over 4000 instructions without reaching the address in $ra. "
                     "Check the loop reads its counter from $a0/$a1 and that the routine ends with `jr $ra`.")


@check("factorial(a0) returns n! in $v0 for n = 0, 1, 2, 12, 13, 20 and random n",
       hint="Read n from $a0 (not from a data table), return in $v0. 0! and 1! are 1; 13! and up wrap mod 2^32. "
            "Do not assume $v0 or any temporary starts at 0: the harness fills them with garbage.")
def _(ctx): result_check(ctx, "factorial")


@check("sum_array(a0 = ptr, a1 = len) returns the sum, including len 0 and wrap-around",
       hint="Zero elements sum to 0 and must read no memory. Sums wrap modulo 2^32. Initialise $v0 yourself.")
def _(ctx): result_check(ctx, "sum_array")


@check("max_array(a0 = ptr, a1 = len) returns the signed maximum, including all-negative arrays",
       hint="Start from the first element, not from 0, and compare signed (slt, not sltu). "
            "-2147483648 and 2147483647 are in the tests.")
def _(ctx): result_check(ctx, "max_array")


@check("every routine returns through $ra",
       hint="The harness sets $ra to a trampoline. A routine that ends with a fixed `j`, never returns, "
            "or overwrites $ra before `jr $ra` never reaches it.")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if not c["returned"]:
            raise CheckFailure(expected="the call returns to the address in $ra",
                               actual=(exception_text(c.get("exception"))[2:] or
                                       f"still running after {c['instrs']} instructions"),
                               message=f"{describe(c)} never returned (probe seed {seed})")


@check("callee-saved registers ($s0-$s7, $gp, $sp, $fp) are unchanged by every call",
       hint="If a routine needs a $s register it must save and restore it (Chapter 10 shows how). "
            "Until then use $t0-$t9, $a0-$a3, $v0-$v1: those are caller-saved and free to use.")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if c["returned"] and c["clobbered"]:
            raise CheckFailure(expected="$s0-$s7, $gp, $sp, $fp all unchanged",
                               actual="changed: " + ", ".join("$" + n for n in c["clobbered"]),
                               message=f"{describe(c)} clobbered a callee-saved register (probe seed {seed})")


@check("sum_array and max_array only read their array (nothing written, nothing read out of range)",
       hint="The array and a guard zone around it are checked after every call. A routine that stores into "
            "the array, or runs past `len`, fails (a run past `len` also gives wrong answers on the guard data).")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if c["fn"] != "factorial" and c["returned"] and not c["mem_intact"]:
            raise CheckFailure(expected="array and guard words unchanged", actual="memory was modified",
                               message=f"{describe(c)} wrote to memory it should only read (probe seed {seed})")


@check("routines run in linear time (instruction budget)",
       hint="Budget: 32 instructions per loop step (or recursion level) plus 40. A routine that runs far "
            "longer than that is doing something quadratic or looping on the wrong counter.")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if not c["returned"]:
            continue
        steps = c["a0"] if c["fn"] == "factorial" else c["len"]
        budget = 32 * steps + 40
        expect_true(c["instrs"] <= budget, f"{describe(c)} within {budget} instructions",
                    f"{c['instrs']} instructions")


def run_set(ctx, key):
    s = SETS[key]
    r = ctx.run(key, patches=data_patch(**s))
    r.require_break()
    got = struct.unpack("<10I", r.mem("results"))
    exp = expected_results(s)
    names = [f"factorial({n})" for n in s["n"]] + [
        "sum_array(arr1, len1)", "max_array(arr1, len1)", "sum_array(arr2, len2)",
        "max_array(arr2, len2)", "sum_array(arr1, 0)", "max_array(arr1, 1)"]
    for i in range(10):
        if got[i] != exp[i]:
            raise CheckFailure(expected=f"results[{i}] = {names[i]} = {exp[i]} (0x{exp[i]:08X}) [data set '{key}']",
                               actual=f"results[{i}] = {got[i]} (0x{got[i]:08X})",
                               message=f"driver result {i} is wrong")
    return r


@check("driver: `results` holds the right values for the shipped data",
       hint="results[0..3] = factorial of drv_n[0..3]; [4] sum(arr1,len1); [5] max(arr1,len1); [6] sum(arr2,len2); "
            "[7] max(arr2,len2); [8] sum(arr1,0) = 0; [9] max(arr1,1) = arr1[0].")
def _(ctx):
    run_set(ctx, "shipped")


@check("driver: results follow patched data (inputs, lengths, arrays) and the driver really calls the routines",
       hint="The data tables are replaced before the run, so storing constants fails. The driver must load "
            "its arguments from drv_n / drv_arr1 / drv_len1 / ... and call the routines (counted at run time: "
            "4 factorial, 3 sum_array, 3 max_array calls).")
def _(ctx):
    for key in ("edges", "small", "mixed"):
        r = run_set(ctx, key)
        e = r.record("entries")
        expect_true(e["factorial"] >= 4 and e["sum_array"] >= 3 and e["max_array"] >= 3,
                    "routine entries >= factorial 4, sum_array 3, max_array 3",
                    f"factorial {e['factorial']}, sum_array {e['sum_array']}, max_array {e['max_array']}")
