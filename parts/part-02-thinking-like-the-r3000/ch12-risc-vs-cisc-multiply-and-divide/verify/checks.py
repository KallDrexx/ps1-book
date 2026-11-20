"""Chapter 12 checks: Fast Routines (word-at-a-time memcpy/memset/strlen, shift-based multiplies, udiv10).
Phase 1 (probe.lua + tools/verify-lib/directcall.lua): every routine is called DIRECTLY on random data at all
alignments, with guard bytes around each buffer; results are compared with Python references, and the executed
instruction count of each call is measured (budgets below). Phase 2: the real driver ran and its results are checked.
Static checks: labels, banned instructions (mult/div family in the shift-based routines, div/divu in udiv10),
the shipped data. The probe also watches the EXECUTED instructions of every call, so a multiply hidden behind a jump
is caught, and checks the mfhi/mflo -> mult/div spacing rule in udiv10 on the path actually taken."""
import struct

from harness import *

BUF = ["my_memcpy", "my_memset", "my_strlen"]
MULK = {"mul320": 320, "mul1024": 1024, "mul10": 10, "mul100": 100, "mul_m5": -5, "mul1000": 1000, "mul65537": 65537}
ROUTINES = BUF + list(MULK) + ["udiv10"]
BASE = ["bytes_memcpy", "bytes_memset", "bytes_strlen"]
LABELS = ["main", "done", *ROUTINES, *BASE, "routines_end", "results", "msg", "msg_end", "copy_pre", "copy_dst",
          "copy_post", "fill_pre", "fill_dst", "fill_post"]
M32 = 0xFFFFFFFF
MSG = b"Strength reduction beats the divider."

config(
    title="RISC vs. CISC, Multiply and Divide",
    main="main.s", exe="main.ps-exe", sym="main.sym",
    break_at="done",
    reads={"results": 20, "copy": ("copy_pre", 50), "fill": ("fill_pre", 18)},
    max_frames=300,
)

BANNED = {0x18: "mult", 0x19: "multu", 0x1A: "div", 0x1B: "divu", 0x10: "mfhi", 0x11: "mthi", 0x12: "mflo", 0x13: "mtlo"}


def funct_name(i):
    return BANNED.get(i.word & 0x3F) if (i.word >> 26) == 0 else None


def op_of(i): return i.word >> 26


@static_check("program defines main, done, every routine, the byte-wise baselines and the data labels, in order",
              hint="Keep every label the starter declares, in the starter's order: routines after `done`, then the "
                   "baselines, then `routines_end`; the data follows it.")
def _(ctx):
    ctx.require_symbols(*LABELS)
    s = ctx.symbols
    order = ["main", "done", *ROUTINES, *BASE, "routines_end"]
    for a, b in zip(order, order[1:]):
        expect_true(s[a] < s[b], f"{a} before {b}", f"{a} 0x{s[a]:08X}, {b} 0x{s[b]:08X}")


@static_check("no mult/multu/div/divu/mfhi/mflo/mthi/mtlo in the shift-based routines (everything before udiv10)",
              hint="my_memcpy, my_memset, my_strlen and the mulK routines are strength-reduction exercises: use shifts, "
                   "adds and subtracts. The multiplier unit is allowed only in udiv10.")
def _(ctx):
    for i in ctx.disassemble_range("my_memcpy", "udiv10"):
        n = funct_name(i)
        if n:
            raise CheckFailure(expected="no multiply/divide unit in the shift-based routines",
                               actual=f"`{n}` at 0x{i.addr:08X}", message="banned instruction")


@static_check("udiv10 does not use div/divu (or mthi/mtlo)",
              hint="udiv10 may use multu + mfhi (multiply by the reciprocal) or a shifts-and-adds approximation, but not the "
                   "36-cycle divider: that is the whole point of the routine.")
def _(ctx):
    for i in ctx.disassemble_range("udiv10", "bytes_memcpy"):
        n = funct_name(i)
        if n in ("div", "divu", "mthi", "mtlo"):
            raise CheckFailure(expected="no div/divu in udiv10", actual=f"`{n}` at 0x{i.addr:08X}")


def raw(ctx, sym, n):
    off = ctx.symbols[sym] - ctx.exe.load_addr
    return ctx.exe.code[off:off + n]


@static_check("the data is as shipped (message, guard bytes, buffers at odd addresses)",
              hint="Do not edit the data section: the buffers sit at odd addresses and have guard bytes on purpose.")
def _(ctx):
    s = ctx.symbols
    expect_eq(raw(ctx, "msg", len(MSG) + 1), MSG + b"\0", "the message")
    expect_eq(raw(ctx, "copy_pre", 1) + raw(ctx, "copy_post", 1) + raw(ctx, "fill_pre", 1) + raw(ctx, "fill_post", 1),
              b"\xA5" * 4, "guard bytes")
    expect_true(s["copy_dst"] % 4 == 1 and s["fill_dst"] % 4 == 1, "buffers at addresses = 1 mod 4",
                f"copy_dst 0x{s['copy_dst']:08X}, fill_dst 0x{s['fill_dst']:08X}")
    expect_eq(s["copy_post"] - s["copy_dst"], 48, "copy_dst size")
    expect_eq(s["fill_post"] - s["fill_dst"], 16, "fill_dst size")


@static_check("the driver calls the routines with jal/jalr",
              hint="`main` must call my_memcpy, my_memset, my_strlen, mul320, mul1000 and udiv10.")
def _(ctx):
    insns = ctx.disassemble_range("main", "done")
    targets = {((i.addr + 4) & 0xF0000000) | ((i.word & 0x03FFFFFF) << 2) for i in insns if op_of(i) == 3}
    for r in ("my_memcpy", "my_memset", "my_strlen", "mul320", "mul1000", "udiv10"):
        expect_true(ctx.symbols[r] in targets, f"a `jal {r}` in the driver", "no call to it")


@static_check("armips reports no warnings",
              hint="Usually a load delay: a loaded register used by the very next instruction.")
def _(ctx):
    bad = [l.strip() for l in ctx.build_log.splitlines() if "warning" in l.lower()]
    expect_true(not bad, "no warnings", "; ".join(bad[:2]))


# ---- dynamic ---------------------------------------------------------------------------------
def calls_of(ctx):
    r = ctx.result
    r.require_break()
    cs = r.record("calls")
    expect_true(cs, "the probe recorded direct calls", "none", hint="The routines must exist and `main` must run.")
    return cs, r.record("seed")


def describe(c):
    k = c["kind"]
    if k == "memcpy":
        return f"{c['fn']}(n={c['n']}, src alignment {c['so']}, dst alignment {c['dof']})"
    if k == "memset":
        return f"{c['fn']}(n={c['n']}, dst alignment {c['dof']}, value 0x{c['val'] & M32:X})"
    if k == "strlen":
        return f"{c['fn']}(length {c['n']}, alignment {c['so']})"
    return f"{c['fn']}(0x{c['x'] & M32:08X})"


def expected_out(c):
    if c["kind"] == "memcpy":
        return c["src_hex"]
    return ("%02x" % (c["val"] & 0xFF)) * c["n"]


def diff_at(a, b):
    for k in range(0, min(len(a), len(b)), 2):
        if a[k:k + 2] != b[k:k + 2]:
            return k // 2
    return min(len(a), len(b)) // 2


HINT = {
    "memcpy": "Any alignment and length must work. Copy bytes until dst is word-aligned, then lw/sw (only possible when "
              "src and dst are then both aligned, i.e. (src ^ dst) & 3 == 0), then bytes for the tail. Return dst in $v0. "
              "When src and dst disagree mod 4 a byte loop is a correct fallback.",
    "memset": "Replicate the low 8 bits of a1 into all four bytes of a word (shift and OR), byte-store until dst is aligned, "
              "sw the words, byte-store the tail. Return dst in $v0.",
    "strlen": "Byte-wise until the pointer is word-aligned, then a word at a time: a word contains a zero byte iff "
              "(w - 0x01010101) & ~w & 0x80808080 is non-zero. Then locate the zero byte in that word. Return the length.",
}


def buf_check(ctx, fn, kind):
    cs, seed = calls_of(ctx)
    n = 0
    for c in cs:
        if c["fn"] != fn or not c["returned"]:
            continue
        n += 1
        if kind == "strlen":
            if (c["v0"] & M32) != c["n"]:
                raise CheckFailure(expected=f"$v0 = {c['n']}", actual=f"$v0 = {c['v0'] & M32}",
                                   message=f"{describe(c)} returned the wrong length (probe seed {seed})", hint=HINT[kind])
            continue
        want = expected_out(c)
        if c["out"] != want:
            k = diff_at(c["out"], want)
            raise CheckFailure(expected=f"byte {k} = 0x{want[2 * k:2 * k + 2] or '--'}",
                               actual=f"byte {k} = 0x{c['out'][2 * k:2 * k + 2] or '--'}",
                               message=f"{describe(c)} wrote wrong data (first difference at byte {k}; probe seed {seed})",
                               hint=HINT[kind])
        if (c["v0"] & M32) != c["dst"]:
            raise CheckFailure(expected=f"$v0 = dst (0x{c['dst']:08X})", actual=f"$v0 = 0x{c['v0'] & M32:08X}",
                               message=f"{describe(c)} must return the destination pointer", hint=HINT[kind])
    expect_true(n > 0, f"at least one call of {fn} returns", "no call returned",
                hint="Each direct call must reach the address in $ra (a stub that returns without work is a return; "
                     "a loop that never ends is not).")


@check("program reaches `done`", hint="A hang is a loop that never ends. Run with -v.")
def _(ctx): ctx.result.require_break()


@check("no CPU exception while the routines run",
       hint="Code 4 = a load from a misaligned address, 5 = a store. lw/sw need a multiple of 4: byte-store a head "
            "until the pointer is aligned. Buffers are passed at every alignment 0..3.")
def _(ctx):
    r = ctx.result
    r.require_finished()
    for c in r.record("calls") or []:
        if c.get("exception"):
            raise CheckFailure(expected="no exception", actual=exception_text(c["exception"])[2:],
                               message=f"during the direct call {describe(c)} (probe seed {r.record('seed')})")
    ex = r.record("exception")
    if ex:
        raise CheckFailure(expected="no exception", actual=exception_text(ex)[2:], message="while running the driver")


@check("my_memcpy copies any length between any alignments and returns dst", hint=HINT["memcpy"])
def _(ctx): buf_check(ctx, "my_memcpy", "memcpy")


@check("my_memset fills any length at any alignment with the low byte of a1 and returns dst", hint=HINT["memset"])
def _(ctx): buf_check(ctx, "my_memset", "memset")


@check("my_strlen measures strings at any alignment (bytes 0x01, 0x7F, 0x80, 0xFF included)", hint=HINT["strlen"])
def _(ctx): buf_check(ctx, "my_strlen", "strlen")


@check("memcpy/memset write only inside the destination and never modify the source",
       hint="Guard bytes (0xA5) surround every buffer. A word loop that overruns by a word, or a head/tail that "
            "miscounts, shows up here.")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if not c["returned"] or c["kind"] not in ("memcpy", "memset"):
            continue
        if not c["guard_ok"]:
            raise CheckFailure(expected="guard bytes around the destination untouched", actual="a guard byte changed",
                               message=f"{describe(c)} wrote outside its destination (probe seed {seed})")
        if not c["in_ok"]:
            raise CheckFailure(expected="source unchanged", actual="source modified",
                               message=f"{describe(c)} modified its source (probe seed {seed})")


@check("the multiply routines equal x * K (mod 2^32) for edge and random x, including negative and large K",
       hint="K: mul320=320, mul1024=1024, mul10=10, mul100=100, mul_m5=-5, mul1000=1000, mul65537=65537. Shift-and-add "
            "is exact modulo 2^32 for signed and unsigned x alike. For a negative K negate the result with subu from $zero.")
def _(ctx):
    cs, seed = calls_of(ctx)
    seen = set()
    for c in cs:
        if c["kind"] != "mul" or not c["returned"]:
            continue
        seen.add(c["fn"])
        want = (c["x"] * MULK[c["fn"]]) & M32
        if (c["v0"] & M32) != want:
            raise CheckFailure(expected=f"0x{want:08X}", actual=f"0x{c['v0'] & M32:08X}",
                               message=f"{c['fn']}(0x{c['x'] & M32:08X}) is wrong (probe seed {seed})")
    expect_true(seen == set(MULK), "all seven multiply routines return", f"returned: {sorted(seen)}")


@check("udiv10 gives x/10 in $v0 and x%10 in $v1 for edge and random unsigned x (0, 9, 10, 0xFFFFFFFF ...)",
       hint="Multiply by 0xCCCCCCCD with multu, take HI, shift right by 3: that is x/10 for every 32-bit x. The "
            "remainder is x - q*10 (q*10 = (q<<3) + (q<<1)).")
def _(ctx):
    cs, seed = calls_of(ctx)
    n = 0
    for c in cs:
        if c["kind"] != "udiv" or not c["returned"]:
            continue
        n += 1
        x = c["x"] & M32
        want = (x // 10, x % 10)
        got = (c["v0"] & M32, c["v1"] & M32)
        if got != want:
            raise CheckFailure(expected=f"q={want[0]} r={want[1]}", actual=f"q={got[0]} r={got[1]}",
                               message=f"udiv10({x}) is wrong (probe seed {seed})")
    expect_true(n > 0, "udiv10 returns", "no call returned")


@check("the multiply/divide unit runs only in udiv10, and only multu/mult/mfhi/mflo there (as executed)",
       hint="The rule is about the instructions a call executes, wherever they sit: jumping to a multu/divu elsewhere "
            "in the program counts. my_memcpy, my_memset, my_strlen and the mulK routines: shifts and adds only. "
            "udiv10: no div/divu/mthi/mtlo.")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if c["fn"].startswith("bytes_"):
            continue
        used = [n for n in (c.get("md_used") or "").split(",") if n]
        bad = [n for n in used if n in ("div", "divu", "mthi", "mtlo")] if c["fn"] == "udiv10" else used
        if bad:
            raise CheckFailure(expected="no " + "/".join(bad) + f" executed by {c['fn']}", actual="executed: " + ", ".join(bad),
                               message=f"during {describe(c)}")


@check("udiv10 leaves 2 instructions between mfhi/mflo and a following mult/div (on the path it executes)",
       hint="MIPS I leaves the mfhi/mflo result undefined if a mult/div starts within two instructions after it; psx-spx "
            "notes a similar not-understood rule for the PS1. Emulators do not model it, real hardware may. Put two "
            "other instructions in between (a branch and its delay slot count).")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if c["fn"] == "udiv10" and c.get("hazard"):
            raise CheckFailure(expected="at least 2 instructions between mfhi/mflo and the next mult/div",
                               actual=f"mult/div/mthi/mtlo at 0x{c['hazard'] & M32:08X} within 2 instructions of mfhi/mflo",
                               message=f"during {describe(c)}")


@check("every routine returns through $ra", hint="The harness sets $ra to a trampoline; just `jr $ra`.")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if not c["returned"]:
            raise CheckFailure(expected="the call returns to the address in $ra",
                               actual=(exception_text(c.get("exception"))[2:] if c.get("exception") else
                                       f"still running after {c['instrs']} instructions"),
                               message=f"{describe(c)} never returned (probe seed {seed})")


@check("callee-saved registers ($s0-$s7, $gp, $sp, $fp) are unchanged by every call",
       hint="These are leaf routines: use $t0-$t9, $a0-$a3, $v0-$v1 only.")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if c["returned"] and c["clobbered"]:
            raise CheckFailure(expected="$s0-$s7, $gp, $sp, $fp unchanged",
                               actual="changed: " + ", ".join("$" + n for n in c["clobbered"]),
                               message=f"{describe(c)} clobbered a callee-saved register (probe seed {seed})")


def budget_check(ctx, kind, limit_per_byte, base_fn, base_per_byte, what):
    cs, seed = calls_of(ctx)
    base = [c for c in cs if c["fn"] == base_fn][0]
    expect_true(base["returned"] and base["instrs"] >= base_per_byte * base["n"] * 0.9,
                f"the byte-wise baseline {base_fn} still costs about {base_per_byte} instructions per byte",
                f"{base['instrs']} instructions for {base['n']} bytes", hint="Do not edit the given baselines.")
    got = 0
    for c in cs:
        if c["fn"].startswith("my_") and c["kind"] == kind and c.get("budget") and c["returned"]:
            got += 1
            right = (c["v0"] & M32) == c["n"] if kind == "strlen" else c["out"] == expected_out(c)
            expect_true(right, "a correct result (a budget only counts for working code)", "wrong result",
                        hint="Fix the correctness check above first.")
            limit = limit_per_byte * c["n"]
            expect_true(c["instrs"] < limit, f"{describe(c)} under {limit:.0f} instructions ({what})",
                        f"{c['instrs']} instructions (byte-wise baseline: about {base_per_byte * c['n']})",
                        hint="Use whole words in the main loop. Both pointers are word-aligned after a short byte head "
                             "when src and dst agree mod 4, so the budget applies to those cases.")
    expect_true(got > 0, "budget cases ran", "none returned")


@check("my_memcpy on 1 KB uses less than 1/3 of the byte-wise baseline's instructions (aligned and co-aligned cases)",
       hint="Baseline: 6 instructions per byte. Budget: under 2 per byte, so a lw/sw loop of about 5 per word passes. "
            "Check your loop for a nop in a delay slot or per-word overhead you can move out.")
def _(ctx): budget_check(ctx, "memcpy", 2.0, "bytes_memcpy", 6, "baseline/3")


@check("my_memset on 1 KB uses less than 1/3 of the byte-wise baseline's instructions",
       hint="Baseline: 4 instructions per byte. Budget: under 4/3 per byte. A word loop (sw, bne, delay-slot addiu) "
            "costs 3 per 4 bytes.")
def _(ctx): budget_check(ctx, "memset", 4 / 3, "bytes_memset", 4, "baseline/3")


@check("my_strlen on 1000 bytes uses less than 60% of the byte-wise baseline's instructions",
       hint="Baseline: 4 instructions per byte. Budget: under 2.4 per byte. The zero-byte test costs about 8 "
            "instructions per word (2 per byte), so it only just fits: remove every nop and per-word overhead you can.")
def _(ctx): budget_check(ctx, "strlen", 2.4, "bytes_strlen", 4, "60% of baseline")


@check("each mulK routine takes at most 8 instructions, udiv10 at most 24 (no loops)",
       hint="A fixed shift-and-add sequence of 2 to 5 operations plus `jr $ra` and its delay slot. udiv10 by "
            "multiply-by-reciprocal is about 10 instructions; a 32-iteration shift-subtract loop is far over.")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if not c["returned"]:
            continue
        lim = 8 if c["kind"] == "mul" else 24 if c["kind"] == "udiv" else None
        if lim:
            expect_true(c["instrs"] <= lim, f"{describe(c)} within {lim} instructions", str(c["instrs"]))


@check("the driver's results are right (strlen, memcpy to an odd address, memset, mul320, mul1000, udiv10)",
       hint="Each routine works alone but the driver output is wrong: check the labels and that you left the driver alone.")
def _(ctx):
    r = ctx.result
    r.require_break()
    expect_eq(list(r.words("results", 5, signed=True)), [len(MSG), 77 * 320, -3000, 123456, 7], "results[0..4]")
    copy = r.mem("copy")
    expect_eq(copy, b"\xA5" + MSG + b"\0" + b"\0" * (48 - len(MSG) - 1) + b"\xA5", "copy buffer (with guards)")
    expect_eq(r.mem("fill"), b"\xA5" + b"\x5A" * 13 + b"\0" * 3 + b"\xA5", "fill buffer (with guards)")


@check("the routines are actually entered by the driver",
       hint="`main` must call my_memcpy, my_memset, my_strlen, mul320, mul1000 and udiv10.")
def _(ctx):
    e = ctx.result.record("entries") or {}
    for n in ("my_memcpy", "my_memset", "my_strlen", "mul320", "mul1000", "udiv10"):
        expect_true(e.get(n, 0) >= 1, f"{n} entered by the driver", str(e.get(n, 0)))
