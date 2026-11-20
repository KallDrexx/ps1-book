"""Chapter 10 checks: the stack and the O32 ABI.
Phase 1 (probe.lua + tools/verify-lib/directcall.lua): factorial, fibonacci and sum6 are called DIRECTLY
(random arguments, seed printed) with sentinel-seeded callee-saved registers and $ra aimed at a trampoline.
The probe tracks the lowest $sp, every re-entry of a recursive routine (its $sp, the frame size it implies),
puts sum6's 5th/6th arguments at 16($sp)/20($sp), and on every re-entry scribbles over the callee's home area
[$sp, $sp+16) and over the 64 bytes below $sp (what a legitimate callee may do). Phase 2: the real driver
runs on several patched data sets."""
import struct

from harness import *

M = 0xFFFFFFFF
ROUTINES = ["factorial", "fibonacci", "sum6"]
NRES = 5
SP0 = 0x801F0000          # $sp the probe gives to every direct call (directcall.lua)
MIN_FRAME, MAX_FRAME = 16, 128   # 24 is the usual minimum; 16 is legal if $ra lives in the caller's home area

config(
    title="The Stack and the MIPS ABI",
    main="main.s", exe="main.ps-exe", sym="main.sym",
    break_at="done", reads={"results": 4 * NRES},
    max_frames=300,
)


def s32(v):
    v &= M
    return v - (1 << 32) if v & 0x80000000 else v


def ref_fact(n):
    r = 1
    for i in range(2, n + 1):
        r = (r * i) & M
    return r


def ref_fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a & M


def ref_sum6(a, b, c, d, e, f): return (a + b + c + d + e - f) & M


SHIPPED = dict(n=6, k=12, args=(10, 20, 30, 40, 50, 60))
SETS = {
    "shipped": SHIPPED,
    "small": dict(n=1, k=1, args=(1, 2, 3, 4, 5, 6)),
    "deeper": dict(n=10, k=15, args=(0xFFFFFFFF, 7, 0x80000000, 1, 1000, 5)),
    "zero": dict(n=0, k=0, args=(0, 0, 0, 0, 0, 1)),
}
POISON = b"\xAA" * (4 * NRES)


def patch(s):
    return {"drv_n": struct.pack("<I", s["n"]), "drv_k": struct.pack("<I", s["k"]),
            "drv_args": struct.pack("<6I", *s["args"]), "results": POISON}


def op_of(i): return i.word >> 26


# ---- static checks ------------------------------------------------------------------------
@static_check("program defines main, done, factorial, fibonacci, sum6, results and the driver's data",
              hint="Keep every label the starter declares. Routines go after `done`, in the order factorial, "
                   "fibonacci, sum6, and before the data. Data must be word-aligned.")
def _(ctx):
    ctx.require_symbols("main", "done", "results", "drv_n", "drv_k", "drv_args", *ROUTINES)
    s = ctx.symbols
    for n in ("results", "drv_n", "drv_k", "drv_args"):
        expect_true(s[n] % 4 == 0, f"{n} word-aligned", f"0x{s[n]:08X}")
    order = ["main", "done", "factorial", "fibonacci", "sum6", "drv_n"]
    addrs = [s[n] for n in order]
    expect_true(addrs == sorted(addrs) and len(set(addrs)) == len(addrs), "labels in the order " + " < ".join(order),
                ", ".join(f"{n}=0x{s[n]:08X}" for n in order))


@static_check("data tables are as shipped (inputs unedited, results zero)",
              hint="Do not edit drv_* or pre-fill `results`; the verifier patches its own data.")
def _(ctx):
    def raw(sym, n):
        off = ctx.symbols[sym] - ctx.exe.load_addr
        return ctx.exe.code[off:off + 4 * n]
    expect_eq(raw("drv_n", 1), struct.pack("<I", SHIPPED["n"]), "drv_n in the executable")
    expect_eq(raw("drv_k", 1), struct.pack("<I", SHIPPED["k"]), "drv_k in the executable")
    expect_eq(raw("drv_args", 6), struct.pack("<6I", *SHIPPED["args"]), "drv_args in the executable")
    expect_true(not any(raw("results", NRES)), "results all zero", "results contains data")


@static_check("factorial and fibonacci contain a call to themselves (recursion), fibonacci at least two",
              hint="Recursion means the routine calls its own label: `jal factorial` inside factorial, and "
                   "`jal fibonacci` twice inside fibonacci (for n-1 and n-2). A `jalr` also counts. A loop is not "
                   "recursion, and neither is a helper label that calls itself.")
def _(ctx):
    s = ctx.symbols
    for name, nxt, need in (("factorial", "fibonacci", 1), ("fibonacci", "sum6", 2)):
        insns = ctx.disassemble_range(name, nxt)
        n = sum(1 for i in insns if (op_of(i) == 3 and
                (((i.addr + 4) & 0xF0000000) | ((i.word & 0x03FFFFFF) << 2)) == s[name])
                or (op_of(i) == 0 and (i.word & 0x3F) == 9))
        expect_true(n >= need, f"at least {need} `jal {name}` (or `jalr`) inside {name}", f"{n}")


@static_check("the driver calls all three routines with jal/jalr",
              hint="`main` must call factorial, fibonacci and sum6 with `jal` (or `jalr`).")
def _(ctx):
    insns = ctx.disassemble_range("main", "done")
    calls = [i for i in insns if op_of(i) == 3 or (op_of(i) == 0 and (i.word & 0x3F) == 9)]
    targets = {((i.addr + 4) & 0xF0000000) | ((i.word & 0x03FFFFFF) << 2) for i in calls if op_of(i) == 3}
    uses_jalr = any(op_of(i) == 0 for i in calls)
    for r in ROUTINES:
        expect_true(ctx.symbols[r] in targets or uses_jalr, f"a `jal {r}` in the driver", "no call to it")


@static_check("armips reports no warnings",
              hint="Usually a load delay: a loaded register used by the very next instruction.")
def _(ctx):
    bad = [l.strip() for l in ctx.build_log.splitlines() if "warning" in l.lower()]
    expect_true(not bad, "no warnings", "; ".join(bad[:2]))


# ---- dynamic helpers -----------------------------------------------------------------------
def calls_of(ctx, fn=None):
    r = ctx.result
    r.require_finished()          # the direct calls are recorded even if the driver later hangs
    cs = r.record("calls")
    expect_true(cs, "the probe recorded direct calls", "none", hint="The routines must exist and `main` must run.")
    return [c for c in cs if fn is None or c["fn"] == fn], r.record("seed")


def describe(c):
    if c["fn"] == "sum6":
        return "sum6(" + ", ".join(f"0x{c[k]:08X}" for k in ("a0", "a1", "a2", "a3", "e", "f")) + ")"
    return f"{c['fn']}({c['a0']})"


def want(c):
    if c["fn"] == "factorial": return ref_fact(c["a0"])
    if c["fn"] == "fibonacci": return ref_fib(c["a0"])
    return ref_sum6(c["a0"], c["a1"], c["a2"], c["a3"], c["e"], c["f"])


HINTS = {
    "factorial": "n! = n * (n-1)!, with 0! = 1! = 1. Save n (in $s0) and $ra before the recursive call. If the answer is "
                 "right for small n only, a saved value is probably in the 16-byte home area at 0..15($sp), which every "
                 "callee may overwrite: keep your own data at 16($sp) and up.",
    "fibonacci": "fib(0)=0, fib(1)=1, else fib(n-1)+fib(n-2). Between the two calls you must keep n and fib(n-1) alive: "
                 "$s0 and $s1, saved in your frame. Keep your saves at 16($sp) and up (0..15 is the callee's home area).",
    "sum6": "a+b+c+d+e-f. a..d arrive in $a0-$a3; e is at 16($sp) and f at 20($sp) as the callee sees them "
            "(above your own frame, if you have one: add the frame size).",
}


def result_check(ctx, fn):
    cs, seed = calls_of(ctx, fn)
    n = 0
    for c in cs:
        if not c["returned"]:
            continue
        n += 1
        w = want(c)
        if (c["v0"] & M) != w:
            raise CheckFailure(expected=f"$v0 = {w} (0x{w:08X})", actual=f"$v0 = {c['v0'] & M} (0x{c['v0'] & M:08X})",
                               message=f"{describe(c)} gave the wrong result (probe seed {seed})", hint=HINTS[fn])
    expect_true(n > 0, f"at least one call of {fn} returns", "no call returned",
                hint=f"Every direct call of {fn} ran too long without reaching the address in $ra. Is the body "
                     "still a TODO, or does it recurse forever, or is $ra never restored?")


# ---- dynamic checks ------------------------------------------------------------------------
@check("program reaches `done`", hint="A hang is a loop that never ends (or recursion without a base case). Run with -v.")
def _(ctx): ctx.result.require_break()


@check("no CPU exception while the routines run",
       hint="Typical causes: a lw/sw at an address that is not a multiple of 4 (misaligned $sp, or a pointer in a clobbered "
            "$s register; code 4 = load, 5 = store), or a jump through a $ra that was not restored or was overwritten "
            "(code 10 or a runaway). Check every save/restore pair, and keep your saves at 16($sp) and up.")
def _(ctx):
    r = ctx.result
    r.require_finished()
    for c in r.record("calls") or []:
        if c.get("exception"):
            raise CheckFailure(expected="no exception", actual=exception_text(c["exception"])[2:],
                               message=f"during the direct call {describe(c)} (probe seed {r.record('seed')}); "
                                       "the run stops at the first exception")
    cr = (r.record("phase2") or {}).get("crash")
    if cr:
        what = (exception_text(cr)[2:] if cr["code"] >= 0
                else f"ran outside the program (at 0x{cr['epc']:08X}) and never came back")
        raise CheckFailure(expected="no exception, no runaway", actual=what,
                           message=("while running the driver" if cr["phase"] == 2 else f"during the direct call of {cr['fn']}"))


@check("factorial(n) = n! mod 2^32 for n = 0, 1, 2 ... 100 and random n, called directly",
       hint=HINTS["factorial"])
def _(ctx): result_check(ctx, "factorial")


@check("fibonacci(n) is right for n = 0 ... 15 and random n (fib(15) = 610)", hint=HINTS["fibonacci"])
def _(ctx): result_check(ctx, "fibonacci")


@check("sum6 reads e and f from 16($sp) and 20($sp): a+b+c+d+e-f on random values",
       hint=HINTS["sum6"])
def _(ctx): result_check(ctx, "sum6")


@check("factorial and fibonacci really recurse (they are re-entered with a deeper $sp)",
       hint="A loop gives the right answer but never re-enters the routine. factorial(n) must be entered about n times "
            "and fibonacci(n) at least fib(n) times, each time with a smaller $sp (a frame was pushed).")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if not c["returned"] or c["fn"] == "sum6":
            continue
        n = c["a0"]
        need = max(0, n - 1) if c["fn"] == "factorial" else max(0, ref_fib(n) - 1) if n >= 3 else 0
        if c["nested"] < need:
            raise CheckFailure(expected=f">= {need} re-entries of {c['fn']} below the caller's $sp",
                               actual=f"{c['nested']} re-entries",
                               message=f"{describe(c)} did not recurse enough (probe seed {seed})")


@check("every call returns through $ra", hint="The harness sets $ra to a trampoline. Restore your saved $ra before `jr $ra`.")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if not c["returned"]:
            raise CheckFailure(expected="the call returns to the address in $ra",
                               actual=(exception_text(c.get("exception"))[2:] or
                                       f"still running after {c['instrs']} instructions"),
                               message=f"{describe(c)} never returned (probe seed {seed})")


@check("$sp is identical after every call (the epilogue undoes the prologue exactly)",
       hint="Every `addiu $sp, $sp, -N` needs a matching `addiu $sp, $sp, N` on EVERY return path.")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if c["returned"] and "sp" in c["clobbered"]:
            raise CheckFailure(expected=f"$sp = 0x{SP0:08X} on return", actual="$sp changed",
                               message=f"{describe(c)} returned with a different $sp (probe seed {seed})")


@check("callee-saved registers ($s0-$s7, $gp, $fp) are unchanged by every call",
       hint="Save every $s register you use in your frame and reload it in the epilogue. $s registers are the point of "
            "this chapter: recursion needs them, and the caller's values must survive.")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        bad = [n for n in c["clobbered"] if n != "sp"]
        if c["returned"] and bad:
            raise CheckFailure(expected="$s0-$s7, $gp, $fp all unchanged", actual="changed: " + ", ".join("$" + n for n in bad),
                               message=f"{describe(c)} clobbered a callee-saved register (probe seed {seed})")


@check("$sp stays 8-byte aligned: every re-entry and the lowest $sp reached",
       hint="Frame sizes must be multiples of 8 (round up: 20 bytes becomes 24). The O32 ABI wants an 8-byte aligned stack.")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if c["misaligned"]:
            raise CheckFailure(expected="$sp % 8 == 0 whenever the routine is entered", actual=f"entered with $sp = 0x{c['misaligned']:08X}",
                               message=f"{describe(c)} (probe seed {seed})")
        if c["min_sp"] % 8:
            raise CheckFailure(expected="the lowest $sp reached is a multiple of 8", actual=f"0x{c['min_sp']:08X}",
                               message=f"{describe(c)} pushed a frame that is not a multiple of 8 bytes (probe seed {seed})")


@check(f"frame sizes are sane: {MIN_FRAME}..{MAX_FRAME} bytes per recursive frame, sum6 at most 64",
       hint="A non-leaf frame holds the saved $ra (4), the saved $s registers (4 each) and the caller-reserved 16-byte home "
            "area for ITS callees: at least 24 once rounded to 8 (16 only if you keep $ra and n in the 16 bytes your "
            "own caller reserved above your entry $sp). More than 128 is a sign something is wrong. "
            "sum6 is a leaf and needs no frame at all.")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if not c["returned"]:
            continue
        used = SP0 - c["min_sp"]
        if c["fn"] == "sum6":
            expect_true(0 <= used <= 64, f"sum6 uses at most 64 bytes of stack", f"{used} bytes",
                        hint="sum6 is a leaf: no calls, so no $ra to save and no frame needed.")
        elif c["nested"] > 0:
            expect_true(MIN_FRAME <= c["fmin"] and c["fmax"] <= MAX_FRAME, f"frame size {MIN_FRAME}..{MAX_FRAME} bytes",
                        f"frames of {c['fmin']}..{c['fmax']} bytes in {describe(c)} (seed {seed})")
            depth = c["nested"] if c["fn"] == "factorial" else None
            if depth is not None:
                expect_true(used >= MIN_FRAME * depth, f"at least {MIN_FRAME * depth} bytes of stack for {describe(c)}",
                            f"{used} bytes", hint="Each active call needs its own frame: the stack must grow with the depth.")
        else:
            expect_true(used <= MAX_FRAME, f"at most {MAX_FRAME} bytes of stack", f"{used} bytes")


@check("instruction budget: at most 80 instructions per entry (plus a little)",
       hint="Generous: a frame costs about 10 instructions. Over budget means a loop that runs too often, or a "
            "recursion that recomputes far more than the plain definition.")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if not c["returned"]:
            continue
        budget = 80 * (c["nested"] + 1) + 100
        expect_true(c["instrs"] <= budget, f"{describe(c)} within {budget} instructions", f"{c['instrs']} instructions")


def run_set(ctx, key):
    s = SETS[key]
    r = ctx.run(key, patches=patch(s))
    r.require_break()
    got = struct.unpack(f"<{NRES}I", r.mem("results"))
    exp = [ref_fact(s["n"]), 1, ref_fib(s["k"]), 0, ref_sum6(*s["args"])]
    names = ["factorial(drv_n)", "factorial(0)", "fibonacci(drv_k)", "fibonacci(0)", "sum6(drv_args)"]
    hints = [HINTS["factorial"], HINTS["factorial"], HINTS["fibonacci"], HINTS["fibonacci"],
             "The driver must put a..d in $a0-$a3 and e, f at 16($sp), 20($sp) in a 24-byte frame (16 home + 2 words) "
             "that it pops after the call."]
    for i in range(NRES):
        if got[i] != exp[i]:
            raise CheckFailure(expected=f"results[{i}] = {names[i]} = {exp[i]} [data set '{key}': n={s['n']} k={s['k']} "
                                        f"args={[hex(a) for a in s['args']]}]",
                               actual=f"results[{i}] = {got[i]} (0x{got[i]:08X})", message=f"driver result {i} is wrong",
                               hint=hints[i])
    return r


@check("driver: `results` holds factorial, fibonacci and sum6 for the shipped data",
       hint="[0] factorial(drv_n) [1] factorial(0) [2] fibonacci(drv_k) [3] fibonacci(0) [4] sum6(drv_args), "
            "with e and f passed on the stack.")
def _(ctx): run_set(ctx, "shipped")


@check("driver: results follow patched data and the driver really calls all three routines",
       hint="The data words are replaced before the run, so storing constants fails.")
def _(ctx):
    for key in ("small", "deeper", "zero"):
        r = run_set(ctx, key)
        e = r.record("entries")
        low = {k: v for k, v in e.items() if v < 1}
        expect_true(not low, "every routine entered at least once by the driver", "never entered: " + ", ".join(low))


@check("driver: sum6 is called with e at 16($sp) and f at 20($sp), and $sp is the same at `done` as at `main`",
       hint="Reserve 24 bytes (`addiu $sp, $sp, -24`), store e at 16($sp) and f at 20($sp) BEFORE the jal, and give the "
            "24 bytes back afterwards. A driver that leaves $sp moved is a leak: the stack drifts by one frame per call.")
def _(ctx):
    r = ctx.result
    r.require_break()
    p2 = r.record("phase2")
    sh = SHIPPED["args"]
    s6 = p2.get("sum6")
    expect_true(s6 is not None, "sum6 entered by the driver", "never entered")
    expect_true(s6["sp"] % 8 == 0, "$sp 8-aligned at the call to sum6", f"0x{s6['sp']:08X}")
    expect_eq((s6["e"], s6["f"]), (sh[4], sh[5]), "stack words 16($sp) and 20($sp) at sum6's entry",
              hint="e (5th argument) goes at 16($sp), f (6th) at 20($sp), in the caller's frame, before the jal.")
    expect_eq((s6["a0"], s6["a1"], s6["a2"], s6["a3"]), tuple(sh[:4]), "$a0-$a3 at sum6's entry")
    expect_eq(p2["done_sp"], p2["main_sp"], "$sp at `done` equals $sp at `main`", fmt="hex")


@check("driver run: the stack stays inside RAM, above the program, within 4 KB of its start",
       hint="The whole shipped run (recursion included) needs well under 4 KB of stack.")
def _(ctx):
    ctx.result.require_break()
    p2 = ctx.result.record("phase2")
    used = p2["main_sp"] - p2["min_sp"]
    expect_true(0 <= used <= 4096, "at most 4096 bytes of stack used by the driver run", f"{used} bytes")
