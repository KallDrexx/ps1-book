"""Chapter 4 checks: three loops whose results must follow patched inputs.
The verifier rewrites `inputs` and `values` in the executable before running, so
hard-coded answers fail. Static checks inspect branch structure and delay slots."""
import struct

from harness import *

M = 0xFFFFFFFF
NAMES = ["sum 1..n", "max", "min", "count signed < limit", "count unsigned < limit"]

# (n, count, seed, step, limit, values[16]); "base" is the starter's data
PAD = [0] * 16
SETS = {
    "base": (100, 10, -20, 7, 100, [12, -5, 40, 7, -99, 63, 0, 8, -1, 25] + [0] * 6),
    "zero": (0, 1, 0, 1, 0, [5] + [0] * 15),
    "big": (1000, 16, -16, 1, 0x80000000,
            [3, -3, 0x7FFFFFFF, -0x80000000, 9, 0, -1, 1, 100, -100, 77, -77, 5, -5, 0x12345, 2]),
    "edge": (1, 2, 0x7FFFFFF0, 3, 0x80000000, [7, -7] + [0] * 14),
    "ties": (3000, 8, 5, -1, 0, [4, 4, 4, 4, 4, 4, 4, 4] + [0] * 8),
    "mid": (77, 5, 1000, 0x10000000, 0x40000000, [-50, 90, 10, -90, 30] + [0] * 11),
}


def s32(v): return v - (1 << 32) if v & 0x80000000 else v


def inputs_blob(n, count, seed, step, limit):
    return struct.pack("<IIIII", n & M, count, seed & M, step & M, limit & M)


def values_blob(vals):
    return struct.pack("<16i", *[s32(v & M) for v in vals])


def seq_of(seed, step):
    return [(seed + i * step) & M for i in range(64)]


def expected(n, count, seed, step, limit, vals):
    sq = seq_of(seed, step)
    used = [s32(v & M) for v in vals[:count]]
    return ([sum(range(1, n + 1)) & M, max(used) & M, min(used) & M,
             sum(1 for v in sq if s32(v) < s32(limit & M)),
             sum(1 for v in sq if v < (limit & M))], sq)


config(
    title="Control Flow: Branches and Jumps",
    main="main.s", exe="main.ps-exe", sym="main.sym",
    break_at="done", reads={"results": 32, "seq": 256, "inputs": 20, "values": 64},
    max_frames=300,
)

# ---- instruction classification --------------------------------------------
OPS = {0x0F: "lui", 0x0D: "ori", 0x23: "lw", 0x21: "lh", 0x25: "lhu", 0x20: "lb", 0x24: "lbu",
       0x2B: "sw", 0x29: "sh", 0x28: "sb", 0x08: "addi", 0x09: "addiu",
       0x0A: "slti", 0x0B: "sltiu", 0x04: "beq", 0x05: "bne", 0x06: "blez", 0x07: "bgtz",
       0x02: "j"}
SPECIAL = {0x20: "add", 0x21: "addu", 0x22: "sub", 0x23: "subu", 0x2A: "slt", 0x2B: "sltu"}
COND = {"beq", "bne", "blez", "bgtz", "bltz", "bgez"}


def name(insn):
    w = insn.word
    if w == 0:
        return "nop"
    op = w >> 26
    if op == 0:
        return SPECIAL.get(w & 0x3F)
    if op == 1:
        return {0: "bltz", 1: "bgez"}.get((w >> 16) & 31)
    return OPS.get(op)


def target(insn):
    """Branch/jump destination address, or None if the instruction is not one."""
    n, w = name(insn), insn.word
    if n in COND:
        off = w & 0xFFFF
        off = off - 0x10000 if off & 0x8000 else off
        return insn.addr + 4 + 4 * off
    if n == "j":
        return ((insn.addr + 4) & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
    return None


def code(ctx):
    return ctx.disassemble_range("main", "done")


def fmt_words(ws): return " ".join(f"{w:08X}" for w in ws)


def compare(r, want, what):
    res, sq = want
    mem = r.mem("results")
    got = [struct.unpack_from("<I", mem, 4 * i)[0] for i in range(5)]
    for i, (g, w) in enumerate(zip(got, res)):
        if g != w:
            raise CheckFailure(expected=f"results[{i}] ({NAMES[i]}) = {w} (0x{w:08X})",
                               actual=f"results[{i}] = {g} (0x{g:08X})",
                               message=f"results[{i}] ({NAMES[i]}) is wrong {what}")
    gs = struct.unpack("<64I", r.mem("seq"))
    for i, (g, w) in enumerate(zip(gs, sq)):
        if g != w:
            raise CheckFailure(expected=f"seq[{i}] = 0x{w:08X}", actual=f"seq[{i}] = 0x{g:08X}",
                               message=f"seq[{i}] is wrong {what}")


def patches(key):
    n, count, seed, step, limit, vals = SETS[key]
    return {"inputs": inputs_blob(n, count, seed, step, limit), "values": values_blob(vals)}


# ---- static checks ---------------------------------------------------------
@static_check("program defines main, done, inputs, values, results and seq",
              hint="Keep the labels the starter declares; tables must be word-aligned.")
def _(ctx):
    ctx.require_symbols("main", "done", "inputs", "values", "results", "seq")
    for s in ("inputs", "values", "results", "seq"):
        expect_true(ctx.symbols[s] % 4 == 0, f"{s} word-aligned", f"0x{ctx.symbols[s]:08X}")


@static_check("data tables are as shipped (results and seq zero, inputs/values unedited)",
              hint="Do not pre-fill `results` or `seq`, and do not edit the input tables; the verifier "
                   "supplies its own values anyway.")
def _(ctx):
    base = SETS["base"]
    def blob(sym, n):
        off = ctx.symbols[sym] - ctx.exe.load_addr
        return ctx.exe.code[off:off + n]
    expect_eq(blob("inputs", 20), inputs_blob(*base[:5]), "inputs table in the executable")
    expect_eq(blob("values", 64), values_blob(base[5]), "values table in the executable")
    expect_true(not any(blob("results", 32)), "results all zero", blob("results", 32).hex())
    expect_true(not any(blob("seq", 256)), "seq all zero", "seq contains data")


@static_check("main..done uses only Chapter 2-4 instructions (no shifts, logic, mul/div, jal/jr)",
              hint="Allowed: Chapter 3's set plus beq bne blez bgtz bltz bgez slt slti sltu sltiu j and nop "
                   "(li/la/move/b/beqz expand to these). Shifts and multiplies would allow closed-form "
                   "shortcuts; calls (jal/jr) come in Chapter 8.")
def _(ctx):
    insns = code(ctx)
    expect_true(insns, "instructions between main and done", "none",
                hint="Write your code between `main:` and `done:`.")
    bad = [f"{i.addr:08X}: {i.text}" for i in insns if name(i) is None]
    expect_true(not bad, "only the allowed instructions", "; ".join(bad[:4]))


@static_check("every branch and jump has a nop in its delay slot",
              hint="The instruction after a branch or jump always executes. This chapter requires a `nop` "
                   "there (Chapter 7 teaches filling it usefully). Follow each branch, jump or "
                   "pseudo-branch (`b`, `bnez`, `blt`, ...) with `nop`.")
def _(ctx):
    insns = code(ctx)
    bad = []
    for k, i in enumerate(insns):
        if target(i) is not None:
            nxt = insns[k + 1] if k + 1 < len(insns) else None
            if nxt is None or nxt.word != 0:
                bad.append(f"{i.addr:08X}: {i.text}")
    expect_true(not bad, "nop after every branch/jump", "no nop after " + "; ".join(bad[:3]))


@static_check("branch targets stay inside main..done and the code has at least 3 loops",
              hint="Branch only to labels between `main` and `done`. Each of the three parts needs a loop: "
                   "a branch or jump that goes backwards to an earlier address.")
def _(ctx):
    insns = code(ctx)
    lo, hi = ctx.symbols["main"], ctx.symbols["done"]
    back = 0
    for i in insns:
        t = target(i)
        if t is None:
            continue
        expect_true(lo <= t <= hi, f"target inside 0x{lo:08X}..0x{hi:08X}",
                    f"{i.text} at {i.addr:08X} -> 0x{t:08X}")
        if t <= i.addr:
            back += 1
    expect_true(back >= 3, "at least 3 backward branches/jumps", f"{back}",
                hint="Sum, max/min and the fill are three separate loops.")


@static_check("instruction mix: signed slt, unsigned sltu and conditional branches are used",
              hint="Part c needs both a signed compare (slt/slti) and an unsigned one (sltu/sltiu) and "
                   "branches or counters built on them; the loops need conditional branches.")
def _(ctx):
    n = {}
    for i in code(ctx):
        n[name(i)] = n.get(name(i), 0) + 1
    g = lambda *k: sum(n.get(x, 0) for x in k)
    short = []
    if g("slt", "slti") < 2: short.append(f"slt/slti: {g('slt', 'slti')} (need 2)")
    if g("sltu", "sltiu") < 1: short.append("sltu/sltiu: 0 (need 1)")
    if sum(n.get(x, 0) for x in COND) < 3: short.append("conditional branches (need 3)")
    expect_true(not short, "enough of each", "; ".join(short))


@static_check("armips reports no warnings",
              hint="Usually a load delay: armips warns when a loaded register is used by the very next "
                   "instruction. Put an unrelated instruction or a nop between them.")
def _(ctx):
    bad = [l.strip() for l in ctx.build_log.splitlines() if "warning" in l.lower()]
    expect_true(not bad, "no warnings", "; ".join(bad[:2]))


# ---- dynamic checks --------------------------------------------------------
@check("program reaches `done`",
       hint="A hang usually means a loop that never ends: the counter is not changed, the exit "
            "condition is backwards, or a branch jumps to the wrong label. Run with -v; for a closer "
            "look single-step in PCSX-Redux.")
def _(ctx):
    ctx.result.require_break()


@check("results and seq are right for the starter's data",
       hint="The message names the first wrong value. Sum off by n or n+1: loop bounds. max/min wrong: "
            "slt operand order. Counts: slt vs sltu, or counting the wrong comparison.")
def _(ctx):
    compare(ctx.result, expected(*SETS["base"]), "for the starter data")


def perturbed(ctx, key, hint=None):
    r = ctx.run(key, patches=patches(key))
    n, count, seed, step, limit, vals = SETS[key]
    compare(r, expected(*SETS[key]),
            f"after the verifier changed the data to n={n}, count={count}, seed={seed}, step={step}, "
            f"limit=0x{limit & M:X}, values={vals[:count]}")
    return r


@check("loops handle the degenerate cases (n = 0, one element, zero limit)",
       hint="With n = 0 the sum must stay 0 (test before the first pass, not after). With count = 1 "
            "max = min = values[0].")
def _(ctx):
    perturbed(ctx, "zero")
    perturbed(ctx, "edge")


@check("results follow the data (large n, extreme values, sign boundary)",
       hint="Values like 0x80000000 and 0x7FFFFFFF break compares that use the wrong signedness; "
            "limit 0x80000000 makes slt and sltu disagree on 48 entries.")
def _(ctx):
    perturbed(ctx, "big")
    perturbed(ctx, "mid")


@check("ties and a long sum (n = 3000, equal values, negative step)",
       hint="Equal values must not break max/min; a 3000-iteration loop must still finish.")
def _(ctx):
    perturbed(ctx, "ties")


@check("every word of results and seq is written by your code",
       hint="The verifier fills both blocks with 0xAA first. Unwritten words, or stores outside "
            "results[0..4] / seq[0..63], show up here.")
def _(ctx):
    p = patches("base")
    p["results"] = b"\xAA" * 32
    p["seq"] = b"\xAA" * 256
    r = ctx.run("poison", patches=p)
    compare(r, expected(*SETS["base"]), "when results and seq start filled with 0xAA")
    expect_eq(r.mem("results")[20:], b"\xAA" * 12, "bytes 0x14-0x1F of results",
              hint="You wrote past the fifth result word.")


@check("input tables are left unchanged",
       hint="Loops must copy values into registers and count there; do not modify inputs or values.")
def _(ctx):
    r = ctx.run("p", patches=patches("big"))
    n, count, seed, step, limit, vals = SETS["big"]
    expect_eq(r.mem("inputs"), inputs_blob(n, count, seed, step, limit), "inputs after the run")
    expect_eq(r.mem("values"), values_blob(vals), "values after the run")
