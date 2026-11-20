"""Chapter 3 checks: every result word follows from the inputs. The verifier
replaces the input table with other values and requires the results to follow."""
import struct

from harness import *

NAMES = ["a+b", "a-b", "b-a", "a+100", "a-100", "0x12345678+a", "c+0x20", "h zero-ext",
         "h sign-ext", "s zero-ext", "s sign-ext", "h+s signed", "-a"]
M = 0xFFFFFFFF

# (a, b, c, h, s) sets; the first is the starter's table
SETS = {
    "base": (1000, 2500, 0x7FFFFFF0, 0xFF38, 0xFB),
    "p1": (0x00012345, 0x00000777, 0xFFFFFFF0, 0x7ABC, 0x85),
    "p2": (0x80000000, 0x7FFFFFFF, 0x7FFFFFE0, 0x8001, 0x7F),
}

config(
    title="Registers, Loads, Stores, and Arithmetic",
    main="main.s", exe="main.ps-exe", sym="main.sym",
    break_at="done", reads={"results": 64, "inputs": 16}, max_frames=120,
)


def s16(v): return v - 0x10000 if v & 0x8000 else v
def s8(v): return v - 0x100 if v & 0x80 else v


def table(a, b, c, h, s):
    return struct.pack("<IIIHBB", a, b, c, h, s, 0)


def expected(a, b, c, h, s):
    return [(a + b) & M, (a - b) & M, (b - a) & M, (a + 100) & M, (a - 100) & M,
            (0x12345678 + a) & M, (c + 0x20) & M, h, s16(h) & M, s, s8(s) & M,
            (s16(h) + s8(s)) & M, (-a) & M]


# opcodes (and SPECIAL functs) allowed between main and done
OPS = {0x0F: "lui", 0x0D: "ori", 0x23: "lw", 0x21: "lh", 0x25: "lhu", 0x20: "lb", 0x24: "lbu",
       0x2B: "sw", 0x29: "sh", 0x28: "sb", 0x08: "addi", 0x09: "addiu"}
SPECIAL = {0x20: "add", 0x21: "addu", 0x22: "sub", 0x23: "subu"}


def name(insn):
    w = insn.word
    if w == 0:
        return "nop"
    if w >> 26 == 0:
        return SPECIAL.get(w & 0x3F)
    return OPS.get(w >> 26)


def code(ctx):
    return ctx.disassemble_range("main", "done")


def counts(ctx):
    n = {}
    for i in code(ctx):
        n[name(i)] = n.get(name(i), 0) + 1
    return n


def fmt_words(ws):
    return " ".join(f"{w:08X}" for w in ws)


def compare(mem, want, what):
    got = [struct.unpack_from("<I", mem, 4 * i)[0] for i in range(len(want))]
    for i, (g, w) in enumerate(zip(got, want)):
        if g != w:
            raise CheckFailure(expected=f"results[{i}] ({NAMES[i]}) = 0x{w:08X}",
                               actual=f"results[{i}] = 0x{g:08X}",
                               message=f"results[{i}] ({NAMES[i]}) is wrong {what}")


@static_check("program defines main, done, inputs and results",
              hint="Keep the labels the starter declares.")
def _(ctx):
    ctx.require_symbols("main", "done", "inputs", "results")
    expect_true(ctx.symbols["results"] % 4 == 0 and ctx.symbols["inputs"] % 4 == 0,
                "word-aligned tables", "misaligned")


@static_check("results block starts out all zero in the executable",
              hint="Do not pre-fill `results`; your code must compute and store every value.")
def _(ctx):
    off = ctx.symbols["results"] - ctx.exe.load_addr
    blob = ctx.exe.code[off:off + 64]
    expect_true(len(blob) == 64 and not any(blob), "64 zero bytes", blob.hex())


@static_check("main..done uses only Chapter 2-3 instructions (no branches, shifts, logic or mul/div)",
              hint="Allowed: lui ori lw lh lhu lb lbu sw sh sb add addu addi addiu sub subu nop "
                   "(li/la/move/subiu/negu expand to these). Loops and branches come in Chapter 4.")
def _(ctx):
    insns = code(ctx)
    expect_true(len(insns) > 0, "instructions between main and done", "none",
                hint="Write your code between `main:` and `done:`.")
    bad = [f"{i.addr:08X}: {i.text}" for i in insns if name(i) is None]
    expect_true(not bad, "only the allowed instructions", "; ".join(bad[:4]))


@static_check("instruction mix: each load width, sw, addu/subu, addiu and lui are all used",
              hint="The project needs lw, lh, lhu, lb, lbu; addu (or add), subu (or sub); an "
                   "immediate add (addiu/addi) at least twice; and lui for the 32-bit constant.")
def _(ctx):
    n = counts(ctx)
    g = lambda *k: sum(n.get(x, 0) for x in k)
    need = [("lw", g("lw"), 3), ("lh", g("lh"), 1), ("lhu", g("lhu"), 1), ("lb", g("lb"), 1),
            ("lbu", g("lbu"), 1), ("sw", g("sw"), 15), ("addu/add", g("addu", "add"), 3),
            ("subu/sub", g("subu", "sub"), 3), ("addiu/addi", g("addiu", "addi"), 2),
            ("lui", g("lui"), 1)]
    short = [f"{k}: {have} (need {v})" for k, have, v in need if have < v]
    expect_true(not short, "enough of each instruction", "; ".join(short))


@static_check("armips reports no warnings",
              hint="The usual one is a load delay: armips warns when a loaded register is used by the "
                   "very next instruction. Put an unrelated instruction or a nop between the load and "
                   "its first use.")
def _(ctx):
    bad = [l.strip() for l in ctx.build_log.splitlines() if "warning" in l.lower()]
    expect_true(not bad, "no warnings", "; ".join(bad[:2]))


@check("program reaches `done`",
       hint="A hang or crash before done. An `add`/`addi`/`sub` that overflows raises an exception "
            "(use addu/addiu/subu), and a misaligned lw/sw faults. Run with -v.")
def _(ctx):
    try:
        ctx.result.require_break()
    except CheckFailure as e:
        e.hint = ("An add/addi/sub that overflows raises an exception and the program never reaches "
                  "done (use addu/addiu/subu); so does a misaligned lw/sw. Run with -v.")
        raise


@check("results hold the right values for the starter's inputs",
       hint="Read the message: it names the failing expression. Common causes: lb/lbu or lh/lhu mixed "
            "up, operands in the wrong order for subu, or a load used before its delay has passed.")
def _(ctx):
    base = table(*SETS["base"])
    off = ctx.symbols["inputs"] - ctx.exe.load_addr
    expect_eq(ctx.exe.code[off:off + 16], base, "inputs table in the executable",
              hint="The `inputs` table was edited; restore it from the starter.")
    compare(ctx.result.mem("results"), expected(*SETS["base"]), "for the starter inputs")


def perturbed(ctx, key):
    r = ctx.run(key, patches={"inputs": table(*SETS[key])})
    compare(r.mem("results"), expected(*SETS[key]),
            f"after the verifier changed the inputs to a,b,c,h,s = "
            f"{tuple(hex(x) for x in SETS[key])}")
    return r


@check("results follow the inputs (verifier changes the table: ordinary values)",
       hint="Your results are fixed numbers, not computed. Load each operand from `inputs`, compute "
            "with registers, and store.")
def _(ctx):
    perturbed(ctx, "p1")


@check("results follow the inputs (extreme values: wraparound, sign bits)",
       hint="Edge cases: addu wraps silently, a-b can be negative, 0x8001 as lh is negative, 0x7F as "
            "lb is positive. A wrong load flavour or add/sub (trapping) variant shows up here.")
def _(ctx):
    perturbed(ctx, "p2")


@check("results stay inside the 13 words (rest of the block untouched)",
       hint="Stores outside results[0..12] (offsets 0x00-0x33) clobber the unused tail.")
def _(ctx):
    r = ctx.run("poison", patches={"results": b"\xAA" * 64})
    mem = r.mem("results")
    compare(mem, expected(*SETS["base"]), "when results starts out filled with 0xAA "
            "(every word must be written by your code)")
    expect_eq(mem[52:], b"\xAA" * 12, "bytes 0x34-0x3F of results", hint="You wrote past the 13th word.")


@check("a and b are swapped in the inputs table; c, h and s are untouched",
       hint="Store the loaded a into inputs+4 and the loaded b into inputs+0 (after you finished using "
            "them for the results, or from registers that still hold them).")
def _(ctx):
    a, b, c, h, s = SETS["p1"]
    r = ctx.run("p1", patches={"inputs": table(*SETS["p1"])})
    want = table(b, a, c, h, s)
    got = r.mem("inputs")
    expect_eq(got, want, "inputs table after the run (a and b swapped)", fmt="auto")
