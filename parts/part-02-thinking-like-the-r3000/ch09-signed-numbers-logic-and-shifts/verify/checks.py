"""Chapter 9 checks: the Bit Toolkit.
Phase 1 (probe.lua + tools/verify-lib/directcall.lua): each routine is called DIRECTLY with edge cases
and random values (seed printed), callee-saved registers seeded with sentinels, $ra aimed at a
trampoline. Compared against the Python reference functions below. Phase 2: the real driver runs on
several patched data sets. Static checks forbid mult/div (and memory access inside the routines)."""
import struct

from harness import *

M = 0xFFFFFFFF
ROUTINES = ["abs", "sign_extend", "popcount", "rgb888_to_bgr555", "bgr555_unpack", "swap_endian32"]
NRES = 13

config(
    title="Signed Numbers, Logic, and Bit Shifting",
    main="main.s", exe="main.ps-exe", sym="main.sym",
    break_at="done", reads={"results": 4 * NRES},
    max_frames=300,
)


# ---- Python reference implementations (the contracts in the chapter) -------------------
def s32(v):
    v &= M
    return v - (1 << 32) if v & 0x80000000 else v


def ref_abs(v): return abs(s32(v)) & M


def ref_sign_extend(v, bits):
    f = v & ((1 << bits) - 1)
    if f >> (bits - 1):
        f -= 1 << bits
    return f & M


def ref_popcount(v): return bin(v & M).count("1")


def ref_rgb(v):
    r, g, b = (v >> 16) & 255, (v >> 8) & 255, v & 255
    return (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)


def ch8(c5): return (c5 << 3) | (c5 >> 2)


def ref_unpack(v):
    r5, g5, b5 = v & 31, (v >> 5) & 31, (v >> 10) & 31
    return (ch8(r5) << 16) | (ch8(g5) << 8) | ch8(b5), (v >> 15) & 1


def ref_swap(v):
    return int.from_bytes((v & M).to_bytes(4, "little"), "big")


def ref_driver(val, bits, rgb, bgr):
    val &= M
    sv = s32(val)
    out = [ref_abs(val), ref_sign_extend(val, bits), ref_popcount(val), ref_rgb(rgb)]
    out += list(ref_unpack(bgr)) + [ref_swap(val)]
    lo8, lo16 = val & 255, val & 0xFFFF
    out += [(lo8 - 256 if lo8 & 128 else lo8) & M, lo8,
            (lo16 - 65536 if lo16 & 0x8000 else lo16) & M, lo16]
    out += [(sv >> 3) & M, int(sv / 8) & M]       # floor vs. toward zero
    return out


SHIPPED = dict(val=0xFFFFFC85, bits=8, rgb=0x00FF8040, bgr=0x0000C3A5)
SETS = {
    "shipped": SHIPPED,
    "positive": dict(val=0x12345678, bits=16, rgb=0x00102030, bgr=0x00007FFF),
    "intmin": dict(val=0x80000000, bits=32, rgb=0x00FFFFFF, bgr=0x00008000),
    "neg_small": dict(val=0xFFFFFFF9, bits=3, rgb=0x00F8F8F8, bgr=0x0000001F),
    "mixed": dict(val=0xDEADBEEF, bits=1, rgb=0x00070809, bgr=0x00000421),
}
POISON = b"\xAA" * (4 * NRES)


def patch(s):
    return {"drv_val": struct.pack("<I", s["val"]), "drv_bits": struct.pack("<I", s["bits"]),
            "drv_rgb": struct.pack("<I", s["rgb"]), "drv_bgr": struct.pack("<I", s["bgr"]),
            "results": POISON}


# ---- static checks ------------------------------------------------------------------------
@static_check("program defines main, done, the six routines, results and the driver's data",
              hint="Keep every label the starter declares. Routines go after `done` and before the data "
                   "(`drv_val` ...). Data must be word-aligned.")
def _(ctx):
    ctx.require_symbols("main", "done", "results", "drv_val", "drv_bits", "drv_rgb", "drv_bgr", *ROUTINES)
    s = ctx.symbols
    for n in ("results", "drv_val", "drv_bits", "drv_rgb", "drv_bgr"):
        expect_true(s[n] % 4 == 0, f"{n} word-aligned", f"0x{s[n]:08X}")
    expect_true(s["main"] < s["done"], "main before done", f"main 0x{s['main']:08X}, done 0x{s['done']:08X}")
    for r in ROUTINES:
        expect_true(s["done"] < s[r] < s["drv_val"], f"{r} between `done` and `drv_val`", f"0x{s[r]:08X}",
                    hint="Routines live after the driver's `done` loop and before the data block.")


@static_check("data tables are as shipped (inputs unedited, results zero)",
              hint="Do not edit drv_* or pre-fill `results`; the verifier patches its own data.")
def _(ctx):
    def raw(sym, n):
        off = ctx.symbols[sym] - ctx.exe.load_addr
        return ctx.exe.code[off:off + 4 * n]
    for k, key in (("drv_val", "val"), ("drv_bits", "bits"), ("drv_rgb", "rgb"), ("drv_bgr", "bgr")):
        expect_eq(raw(k, 1), struct.pack("<I", SHIPPED[key]), f"{k} in the executable")
    expect_true(not any(raw("results", NRES)), "results all zero", "results contains data")


def op_of(i): return i.word >> 26
def funct_of(i): return i.word & 0x3F


@static_check("no mult/div/HI/LO instructions anywhere (shifts and logic only)",
              hint="This chapter is about shifts, masks and adds. mult, multu, div, divu, mfhi, mflo, mthi and "
                   "mtlo are not allowed in the driver or the routines (Chapter 12 covers them).")
def _(ctx):
    for i in ctx.disassemble_range("main", "drv_val"):
        if op_of(i) == 0 and (funct_of(i) in (0x10, 0x11, 0x12, 0x13) or 0x18 <= funct_of(i) <= 0x1B):
            raise CheckFailure(expected="no mult/div/mfhi/mflo/mthi/mtlo", actual=f"0x{i.addr:08X}: {i.text}",
                               message="a multiply/divide/HI/LO instruction was used")


@static_check("the routines use registers only (no loads or stores, so no lookup tables)",
              hint="The six routines are pure register code. A table lookup (for popcount, say) would "
                   "also pass the tests, but defeats the exercise. The driver may load and store freely.")
def _(ctx):
    for i in ctx.disassemble_range("done", "drv_val"):
        op = op_of(i)
        if op >= 0x20:
            raise CheckFailure(expected="no load/store between `done` and `drv_val`",
                               actual=f"0x{i.addr:08X}: {i.text}", message="a routine accesses memory")


@static_check("the driver calls each routine with jal/jalr",
              hint="`main` must call all six routines with `jal` (or `jalr`). Inlining them does not count.")
def _(ctx):
    insns = ctx.disassemble_range("main", "done")
    calls = [i for i in insns if op_of(i) == 3 or (op_of(i) == 0 and funct_of(i) == 9)]
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
def calls_of(ctx):
    r = ctx.result
    r.require_break()
    cs = r.record("calls")
    expect_true(cs, "the probe recorded direct calls", "none", hint="The routines must exist and `main` must run.")
    return cs, r.record("seed")


def describe(c):
    a0 = f"0x{c['a0']:08X}"
    return f"{c['fn']}({a0}, bits={c['a1']})" if c["fn"] == "sign_extend" else f"{c['fn']}({a0})"


def want(c):
    fn, a = c["fn"], c["a0"]
    return {"abs": lambda: ref_abs(a), "popcount": lambda: ref_popcount(a), "swap_endian32": lambda: ref_swap(a),
            "rgb888_to_bgr555": lambda: ref_rgb(a), "bgr555_unpack": lambda: ref_unpack(a)[0],
            "sign_extend": lambda: ref_sign_extend(a, c["a1"])}[fn]()


def result_check(ctx, fn):
    cs, seed = calls_of(ctx)
    n = 0
    for c in cs:
        if c["fn"] != fn or not c["returned"]:
            continue
        n += 1
        w = want(c)
        if (c["v0"] & M) != w:
            raise CheckFailure(expected=f"$v0 = 0x{w:08X} ({s32(w)})", actual=f"$v0 = 0x{c['v0'] & M:08X} ({s32(c['v0'])})",
                               message=f"{describe(c)} gave the wrong result (probe seed {seed})")
        if fn == "bgr555_unpack":
            w1 = ref_unpack(c["a0"])[1]
            if (c["v1"] & M) != w1:
                raise CheckFailure(expected=f"$v1 = {w1} (bit 15 of the input)", actual=f"$v1 = 0x{c['v1'] & M:08X}",
                                   message=f"{describe(c)} gave the wrong mask bit (probe seed {seed})",
                                   hint="$v1 must be exactly 0 or 1: bit 15 of the input, nothing else.")
    expect_true(n > 0, f"at least one call of {fn} returns", "no call returned",
                hint=f"Every direct call of {fn} ran too long without reaching the address in $ra. "
                     "Is the routine's body still a TODO, or does it loop forever?")


# ---- dynamic checks ------------------------------------------------------------------------
@check("program reaches `done`", hint="A hang is a loop that never ends. Run with -v.")
def _(ctx): ctx.result.require_break()


@check("abs(a0): |a0| for 0, -1, +/-5, random; abs(0x80000000) stays 0x80000000",
       hint="Branch-free: m = a0 >> 31 (arithmetic); (a0 xor m) - m. The most negative number has no positive twin.")
def _(ctx): result_check(ctx, "abs")


@check("sign_extend(a0 = value, a1 = bits) for every width 1..32, ignoring bits above the field",
       hint="Shift the field to the top (sllv by 32 - bits), then back down with an ARITHMETIC shift (srav). "
            "bits = 32 shifts by 0; bits = 1 gives 0 or -1. Bits above the field are garbage: ignore them.")
def _(ctx): result_check(ctx, "sign_extend")


@check("popcount(a0) counts the 1 bits (0..32)",
       hint="Loop: add (a0 & 1), shift right (srl, logical) until a0 is 0. 0xFFFFFFFF -> 32, 0x80000000 -> 1.")
def _(ctx): result_check(ctx, "popcount")


@check("rgb888_to_bgr555(0x??RRGGBB) = (B>>3)<<10 | (G>>3)<<5 | (R>>3), bit 15 clear, bits 16..31 clear",
       hint="Take the top 5 bits of each 8-bit channel, move them to bits 0-4 (R), 5-9 (G), 10-14 (B). Bits 24-31 "
            "of the input are garbage; the result must be only 15 bits wide.")
def _(ctx): result_check(ctx, "rgb888_to_bgr555")


@check("bgr555_unpack(a0) = 0x00RRGGBB with c8 = (c5 << 3) | (c5 >> 2), and $v1 = bit 15",
       hint="Mask each 5-bit field, then replicate the top bits into the bottom: 31 -> 255, 0 -> 0, 16 -> 132. "
            "Bits 16..31 of the input are garbage. $v1 is 0 or 1.")
def _(ctx): result_check(ctx, "bgr555_unpack")


@check("swap_endian32(a0) reverses the four bytes (0x11223344 -> 0x44332211)",
       hint="Four masked shifts or'd together: byte 0 up 24, byte 1 up 8, byte 2 down 8, byte 3 down 24.")
def _(ctx): result_check(ctx, "swap_endian32")


@check("every routine returns through $ra",
       hint="The harness sets $ra to a trampoline. A routine that ends in a fixed `j`, or overwrites $ra, never reaches it.")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if not c["returned"]:
            raise CheckFailure(expected="the call returns to the address in $ra",
                               actual=(exception_text(c.get("exception"))[2:] or
                                       f"still running after {c['instrs']} instructions"),
                               message=f"{describe(c)} never returned (probe seed {seed})")


@check("callee-saved registers ($s0-$s7, $gp, $sp, $fp) are unchanged by every call",
       hint="Use only $t0-$t9, $a0-$a3, $v0-$v1 in these routines; the $s registers belong to the caller.")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if c["returned"] and c["clobbered"]:
            raise CheckFailure(expected="$s0-$s7, $gp, $sp, $fp all unchanged",
                               actual="changed: " + ", ".join("$" + n for n in c["clobbered"]),
                               message=f"{describe(c)} clobbered a callee-saved register (probe seed {seed})")


@check("instruction budget: at most 400 instructions per call",
       hint="Generous: a loop over the 32 bits fits. Going over means a loop that runs far too often.")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if not c["returned"]:
            continue
        budget = 400
        expect_true(c["instrs"] <= budget, f"{describe(c)} within {budget} instructions", f"{c['instrs']} instructions")


def run_set(ctx, key):
    s = SETS[key]
    r = ctx.run(key, patches=patch(s))
    r.require_break()
    got = struct.unpack(f"<{NRES}I", r.mem("results"))
    exp = ref_driver(s["val"], s["bits"], s["rgb"], s["bgr"])
    names = ["abs(val)", "sign_extend(val, bits)", "popcount(val)", "rgb888_to_bgr555(rgb)",
             "bgr555_unpack(bgr) in $v0", "bgr555_unpack(bgr) in $v1", "swap_endian32(val)",
             "lb val", "lbu val", "lh val", "lhu val", "val >> 3 (arithmetic)", "val / 8 toward zero"]
    for i in range(NRES):
        if got[i] != exp[i]:
            raise CheckFailure(expected=f"results[{i}] = {names[i]} = 0x{exp[i]:08X} ({s32(exp[i])}) [data set '{key}', "
                                        f"val=0x{s['val']:08X} bits={s['bits']} rgb=0x{s['rgb']:08X} bgr=0x{s['bgr']:04X}]",
                               actual=f"results[{i}] = 0x{got[i]:08X} ({s32(got[i])})",
                               message=f"driver result {i} is wrong")
    return r


@check("driver: `results` holds the right values for the shipped data (incl. lb/lbu/lh/lhu, sra, divide by 8)",
       hint="[0..6] the six routines ([4],[5] = bgr555_unpack's $v0,$v1); [7..10] lb lbu lh lhu of drv_val; "
            "[11] drv_val sra 3; [12] drv_val / 8 rounded toward ZERO (sra alone rounds toward -infinity).")
def _(ctx): run_set(ctx, "shipped")


@check("driver: results follow patched data and the driver really calls all six routines",
       hint="The data words are replaced before the run, so storing constants fails. Positive, INT_MIN, "
            "small-negative and bits=1 / bits=32 cases are included.")
def _(ctx):
    for key in ("positive", "intmin", "neg_small", "mixed"):
        r = run_set(ctx, key)
        e = r.record("entries")
        low = {k: v for k, v in e.items() if v < 1}
        expect_true(not low, "every routine entered at least once by the driver",
                    "never entered: " + ", ".join(low))
