"""Chapter 7 checks: n! computed twice (plain and tight) from runtime-patched inputs.
Static: allowed instructions, delay-slot rules (v1 all nop, v2 no nop and no no-op).
Dynamic: results for several input sets, poisoned outputs, v2 independent of v1, every
v2 delay-slot instruction is load-bearing (replace it with nop -> results must break),
and the probe's instruction counts (v2 executes fewer instructions than v1)."""
import math
import struct

from harness import *

M = 0xFFFFFFFF
COUNT_MAX = 8

SETS = {
    "base":  [5, 0, 1, 12, 7, 13, 2, 10],
    "edges": [0, 1, 2, 3, 12, 13, 15, 20],
    "max":   [12, 12, 20, 20, 13, 13, 12, 20],
    "one0":  [0],
    "one1":  [1],
    "one6":  [6],
    "three": [4, 3, 11],
    "down":  [12, 11, 10, 9, 8, 7, 6, 5],
}


def fact(n): return math.factorial(n) & M


def blob(ns):
    full = list(ns) + [0] * (COUNT_MAX - len(ns))
    return struct.pack("<9I", len(ns), *full)


POISON = b"\xAA" * 32


def patches(key, extra=None):
    p = {"inputs": blob(SETS[key]), "out_v1": POISON, "out_v2": POISON}
    p.update(extra or {})
    return p


config(
    title="The Pipeline and Delay Slots",
    main="main.s", exe="main.ps-exe", sym="main.sym",
    break_at="done", reads={"out_v1": 32, "out_v2": 32, "inputs": 36},
    max_frames=300,
)

# ---- instruction classification --------------------------------------------
OPS = {0x0F: "lui", 0x0D: "ori", 0x23: "lw", 0x2B: "sw", 0x09: "addiu",
       0x0A: "slti", 0x0B: "sltiu", 0x04: "beq", 0x05: "bne", 0x06: "blez", 0x07: "bgtz",
       0x02: "j"}
SPECIAL = {0x21: "addu", 0x23: "subu", 0x2A: "slt", 0x2B: "sltu",
           0x18: "mult", 0x19: "multu", 0x12: "mflo"}
COND = {"beq", "bne", "blez", "bgtz", "bltz", "bgez"}
STORES = {"sw"}
BLOCKS = {"v1": ("fact_v1", "fact_v1_end"), "v2": ("fact_v2", "fact_v2_end")}


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
    n, w = name(insn), insn.word
    if n in COND:
        off = w & 0xFFFF
        off = off - 0x10000 if off & 0x8000 else off
        return insn.addr + 4 + 4 * off
    if n == "j":
        return ((insn.addr + 4) & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
    return None


def dest(insn):
    """Destination GPR number, or None if the instruction writes no GPR."""
    n, w = name(insn), insn.word
    rd, rt = (w >> 11) & 31, (w >> 16) & 31
    if n in ("addu", "subu", "slt", "sltu", "mflo"):
        return rd
    if n in ("lui", "ori", "lw", "addiu", "slti", "sltiu"):
        return rt
    return None


def is_noop(insn):
    """True for the architectural no-ops a delay slot could be 'filled' with."""
    n, w = name(insn), insn.word
    if w == 0:
        return True
    d = dest(insn)
    if d == 0:
        return True
    rs, rt, rd, imm = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31, w & 0xFFFF
    if n in ("addiu", "ori") and rt == rs and imm == 0:
        return True
    if n in ("addu", "subu") and rd == rs and rt == 0:
        return True
    if n == "addu" and rd == rt and rs == 0:
        return True
    return False


def block(ctx, which):
    return ctx.disassemble_range(*BLOCKS[which])


def slots(insns):
    """[(branch_insn, delay_slot_insn_or_None)] for every branch/jump in the block."""
    out = []
    for k, i in enumerate(insns):
        if target(i) is not None:
            out.append((i, insns[k + 1] if k + 1 < len(insns) else None))
    return out


# ---- static checks ---------------------------------------------------------
@static_check("program defines main, both blocks, done, inputs, out_v1 and out_v2",
              hint="Keep the labels the starter declares, in this order: main, fact_v1, fact_v1_end, "
                   "fact_v2, fact_v2_end, done. Tables must be word-aligned.")
def _(ctx):
    ctx.require_symbols("main", "fact_v1", "fact_v1_end", "fact_v2", "fact_v2_end", "done",
                        "inputs", "out_v1", "out_v2")
    s = ctx.symbols
    order = [s["main"], s["fact_v1"], s["fact_v1_end"], s["fact_v2"], s["fact_v2_end"], s["done"]]
    expect_true(order == sorted(order), "labels in order main <= fact_v1 < fact_v1_end <= fact_v2 < "
                "fact_v2_end <= done", " ".join(f"0x{a:08X}" for a in order))
    for n in ("inputs", "out_v1", "out_v2"):
        expect_true(s[n] % 4 == 0, f"{n} word-aligned", f"0x{s[n]:08X}")


@static_check("data tables are as shipped (outputs zero, inputs unedited)",
              hint="Do not pre-fill out_v1/out_v2 and do not edit `inputs`; the verifier supplies its own data.")
def _(ctx):
    def raw(sym, n):
        off = ctx.symbols[sym] - ctx.exe.load_addr
        return ctx.exe.code[off:off + n]
    expect_eq(raw("inputs", 36), blob(SETS["base"]), "inputs table in the executable")
    expect_true(not any(raw("out_v1", 32)) and not any(raw("out_v2", 32)),
                "out_v1 and out_v2 all zero", "an output block contains data")


@static_check("both blocks use only the allowed instructions",
              hint="Allowed: lui ori lw sw addiu addu subu slt sltu slti sltiu mult multu mflo "
                   "beq bne blez bgtz bltz bgez j nop (li/la/move/b/beqz/bnez expand to these). "
                   "No shifts, logic ops, jal/jr, and no lookup tables: the work must be real multiplication.")
def _(ctx):
    for which in ("v1", "v2"):
        insns = block(ctx, which)
        expect_true(insns, f"instructions in {BLOCKS[which][0]} .. {BLOCKS[which][1]}", "none",
                    hint=f"Write version {which[1]} between its two labels.")
        bad = [f"{i.addr:08X}: {i.text}" for i in insns if name(i) is None]
        expect_true(not bad, f"only allowed instructions in {which}", "; ".join(bad[:4]))


@static_check("branches stay inside their own block, and each block has a loop",
              hint="Branch only to labels within the same version (fact_vN .. fact_vN_end; the end label "
                   "itself is fine). A delay slot may not be the first instruction after the block, "
                   "and each version needs a backward branch.")
def _(ctx):
    for which in ("v1", "v2"):
        insns = block(ctx, which)
        lo, hi = ctx.symbols[BLOCKS[which][0]], ctx.symbols[BLOCKS[which][1]]
        back = 0
        for b, slot in slots(insns):
            t = target(b)
            expect_true(lo <= t <= hi, f"{which}: target inside 0x{lo:08X}..0x{hi:08X}",
                        f"{b.text} at {b.addr:08X} -> 0x{t:08X}")
            expect_true(slot is not None, f"{which}: a delay slot inside the block after {b.text}",
                        f"the branch at {b.addr:08X} is the last instruction of the block")
            expect_true(target(slot) is None, f"{which}: no branch inside a delay slot",
                        f"{slot.text} at {slot.addr:08X}")
            if t <= b.addr:
                back += 1
        expect_true(back >= 1, f"{which}: at least one backward branch", "0")


@static_check("version 1: a nop in every delay slot",
              hint="Version 1 is the plain baseline: the word after every branch or jump is a `nop`. "
                   "(Pseudo-branches like b/bnez/blt are fine; their slot still needs a nop.)")
def _(ctx):
    bad = [f"{b.addr:08X}: {b.text} / {s.text if s else '-'}"
           for b, s in slots(block(ctx, "v1")) if s is None or s.word != 0]
    expect_true(not bad, "nop after every branch/jump in version 1", "; ".join(bad[:3]))


@static_check("version 2: no nop in any delay slot, and no filler that does nothing",
              hint="Put real work in every delay slot: an instruction that must run on both paths. "
                   "A `nop` or a disguised no-op (`move $t0,$t0`, `addiu $t0,$t0,0`, an instruction "
                   "that only writes $zero) does not count.")
def _(ctx):
    sl = slots(block(ctx, "v2"))
    expect_true(sl, "at least one branch in version 2", "none")
    bad = [f"{b.addr:08X}: {b.text} / {s.text}" for b, s in sl if is_noop(s)]
    expect_true(not bad, "useful instruction in every delay slot of version 2", "; ".join(bad[:3]))


@static_check("version 2 really multiplies",
              hint="Version 2 must use mult/multu with mflo, not a lookup table or repeated addition.")
def _(ctx):
    names = [name(i) for i in block(ctx, "v2")]
    expect_true(("mult" in names or "multu" in names) and "mflo" in names, "mult/multu and mflo",
                f"found: {sorted(set(n for n in names if n in ('mult', 'multu', 'mflo')))}")


@static_check("armips reports no warnings",
              hint="Usually a load delay: a loaded register used by the very next instruction. "
                   "Put an unrelated instruction or a nop between them.")
def _(ctx):
    bad = [l.strip() for l in ctx.build_log.splitlines() if "warning" in l.lower()]
    expect_true(not bad, "no warnings", "; ".join(bad[:2]))


# ---- dynamic checks --------------------------------------------------------
def compare(r, ns, what, outs=("out_v1", "out_v2")):
    for o in outs:
        got = struct.unpack("<8I", r.mem(o))
        for i in range(COUNT_MAX):
            if i < len(ns):
                want = fact(ns[i])
                if got[i] != want:
                    raise CheckFailure(
                        expected=f"{o}[{i}] = {ns[i]}! mod 2^32 = {want} (0x{want:08X})",
                        actual=f"{o}[{i}] = {got[i]} (0x{got[i]:08X})",
                        message=f"{o}[{i}] (n = {ns[i]}) is wrong {what}")
            elif got[i] != 0xAAAAAAAA:
                raise CheckFailure(expected=f"{o}[{i}] untouched (0xAAAAAAAA)",
                                   actual=f"{o}[{i}] = 0x{got[i]:08X}",
                                   message=f"{o} written past `count` {what}")


def perturbed(ctx, key, outs=("out_v1", "out_v2")):
    r = ctx.run(key, patches=patches(key))
    compare(r, SETS[key], f"for inputs {SETS[key]}", outs)
    return r


@check("program reaches `done`",
       hint="A hang usually means a loop that never ends: the counter is not changed, the exit "
            "condition is backwards, or a branch jumps to the wrong label. Run with -v.")
def _(ctx):
    ctx.result.require_break()


@check("both versions are right for the starter's inputs",
       hint="The message names the first wrong word. 0! and 1! must be 1; n >= 13 wraps modulo 2^32.")
def _(ctx):
    r = ctx.run("base", patches=patches("base"))
    compare(r, SETS["base"], "for the starter's inputs")


@check("edge cases: 0!, 1!, 2!, 12! (largest exact) and 13!..20! (wrap mod 2^32)",
       hint="12! = 479001600 is the largest factorial that fits 32 bits; larger ones wrap, which "
            "multu/mflo does for free. n = 0 and 1 must give 1 without multiplying.")
def _(ctx):
    perturbed(ctx, "edges")
    perturbed(ctx, "max")


@check("different counts and orders follow the patched data",
       hint="`count` is read at run time (1..8); outputs beyond it must stay untouched.")
def _(ctx):
    for k in ("one0", "one1", "one6", "three", "down"):
        perturbed(ctx, k)


@check("version 2 does not depend on version 1",
       hint="With version 1 skipped entirely, version 2 must still set up its own pointers and "
            "constants and produce every result. Do not reuse registers or results left by version 1.")
def _(ctx):
    v2 = ctx.symbols["fact_v2"]
    j = 0x08000000 | ((v2 >> 2) & 0x03FFFFFF)
    skip = struct.pack("<II", j, 0)  # j fact_v2 ; nop
    p = patches("base", {"fact_v1": skip})
    r = ctx.run("skipv1", patches=p)
    compare(r, SETS["base"], "when version 1 is skipped", outs=("out_v2",))
    expect_eq(r.mem("out_v1"), POISON, "out_v1 when version 1 never ran")


@check("every delay-slot instruction in version 2 is load-bearing",
       hint="Replacing a delay-slot instruction with a nop must change the outcome. If the results "
            "stay correct, that instruction is not doing needed work there; move real work into it.")
def _(ctx):
    sl = slots(block(ctx, "v2"))
    expect_true(sl, "at least one branch in version 2", "none")
    ns = SETS["base"]
    # Skip version 1 so a slot instruction that re-creates a value version 1 happened to leave
    # in a register (needed for independence) is not misjudged as dead.
    v2 = ctx.symbols["fact_v2"]
    skip = struct.pack("<II", 0x08000000 | ((v2 >> 2) & 0x03FFFFFF), 0)  # j fact_v2 ; nop
    for b, s in sl:
        r = ctx.run(f"mut{s.addr:x}",
                    patches=patches("base", {"fact_v1": skip, s.addr: struct.pack("<I", 0)}),
                    max_frames=40)
        same = False
        if r.break_hit:
            try:
                compare(r, ns, "", outs=("out_v2",))
                same = True
            except CheckFailure:
                same = False
        if same:
            raise CheckFailure(
                expected=f"results change when the delay slot at 0x{s.addr:08X} becomes a nop",
                actual="results unchanged",
                message=f"`{s.text}` in the delay slot of `{b.text}` (0x{b.addr:08X}) does no needed work")


def counts(ctx, key="base"):
    r = ctx.run(key, patches=patches(key))
    return r, r.record("n1"), r.record("n2"), r.record("mul2")


@check("version 2 executes fewer instructions than version 1",
       hint="Both versions are counted by the probe on the same inputs. Remove every delay-slot nop by "
            "moving real work into it, and fold loop bookkeeping into load-delay and delay slots.")
def _(ctx):
    for key in ("base", "edges", "max"):
        r, n1, n2, mul2 = counts(ctx, key)
        ns = SETS[key]
        expect_true(n1 and n1 > 0, "version 1 instructions counted", str(n1))
        expect_true(n2 and n2 > 0, "version 2 instructions counted", str(n2))
        expect_true(n2 < n1, f"version 2 < version 1 ({key}: {ns})",
                    f"v1 = {n1}, v2 = {n2}",
                    hint="Version 2 must run in strictly fewer instructions than version 1.")


@check("version 2 is genuinely tight (instruction budget and real multiplies)",
       hint="Budget: at most 14 instructions per input plus 6 per multiplication. A bare nop-removal "
            "is not enough if it leaves the loop longer than that. Version 2 must also multiply at "
            "least max(n-2, 0) times per input (no table lookups).")
def _(ctx):
    for key in ("base", "edges", "max"):
        r, n1, n2, mul2 = counts(ctx, key)
        ns = SETS[key]
        need = sum(max(n - 2, 0) for n in ns)
        budget = 14 * len(ns) + 6 * need
        expect_true(mul2 is not None and mul2 >= need, f"at least {need} multiplies in version 2 ({key})",
                    str(mul2))
        expect_true(n2 <= budget, f"version 2 <= {budget} instructions ({key})", f"{n2}")


@check("input table is left unchanged",
       hint="Read `inputs` into registers; do not modify it.")
def _(ctx):
    r = ctx.run("base", patches=patches("base"))
    expect_eq(r.mem("inputs"), blob(SETS["base"]), "inputs after the run")
