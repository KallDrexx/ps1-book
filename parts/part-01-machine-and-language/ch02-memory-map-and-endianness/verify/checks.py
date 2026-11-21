"""Chapter 2 checks: the `results` block holds the exact little-endian layout,
written with the required store widths, aliases, and without hard-coding."""
from pathlib import Path

from harness import *

# offset -> expected bytes (little-endian layout of the values in the chapter)
LAYOUT = {
    0x00: bytes.fromhex("78563412"),   # sw 0x12345678
    0x04: bytes.fromhex("EFBE"),       # sh 0xBEEF
    0x06: bytes.fromhex("FECA"),       # sh 0xCAFE
    0x08: bytes.fromhex("11223344"),   # four sb
    0x0C: bytes.fromhex("EFBEADDE"),   # sw 0xDEADBEEF
    0x10: bytes.fromhex("78563412"),   # bytes of the word at 0x00, read with lbu
    0x14: bytes.fromhex("EFBEADDE"),   # bytes of the word at 0x0C, read with lbu
    0x18: bytes.fromhex("0DF0AD0B"),   # sw 0x0BADF00D via the KSEG1 alias
    0x1C: bytes.fromhex("577E"),       # sh 0x7E57 via the KUSEG alias
    0x20: bytes.fromhex("FECA0D60"),   # lw of scratchpad word 0x600DCAFE
}
USED = 0x24
# perturb.lua swaps these source words at their first read: (source, copy offset, new value)
PERTURB = Path(__file__).resolve().parent / "perturb.lua"
SWAPS = [("results+0x00", 0x10, 0x8BADF00D), ("results+0x0C", 0x14, 0x0C0FFEE5),
         ("0x1F800000", 0x20, 0x5CA77E12)]
SCRATCH_VALUE = 0x600DCAFE

# the only opcodes allowed between main and done
OPS = {0x0F: "lui", 0x0D: "ori", 0x2B: "sw", 0x29: "sh", 0x28: "sb", 0x23: "lw", 0x24: "lbu"}

config(
    title="Memory, the Memory Map, and Endianness",
    main="main.s", exe="main.ps-exe", sym="main.sym",
    break_at="done", reads={"results": 64, "scratch": (0x1F800000, 4)},
    max_frames=120,
)


def op(insn):
    return insn.word >> 26


def code(ctx):
    return ctx.disassemble_range("main", "done")


@static_check("program defines main, done and results",
              hint="Keep the labels the starter declares.")
def _(ctx):
    ctx.require_symbols("main", "done", "results")
    expect_true(ctx.symbols["results"] % 4 == 0, "results word-aligned",
                hex(ctx.symbols["results"]))


@static_check("results block starts out all zero in the executable",
              hint="Do not pre-fill `results` with .byte/.word data; your code must write it.")
def _(ctx):
    ctx.require_symbols("results")
    off = ctx.symbols["results"] - ctx.exe.load_addr
    blob = ctx.exe.code[off:off + 64]
    expect_true(len(blob) == 64 and not any(blob), "64 zero bytes", blob.hex())


@static_check("main..done uses only lui, ori, sw, sh, sb, lw, lbu and nop",
              hint="Build values with lui/ori (not li/la/addiu: armips turns those into addiu for big "
                   "values) and use no branches, arithmetic, or loops. Chapter 3 adds the rest.")
def _(ctx):
    ctx.require_symbols("main", "done")
    insns = code(ctx)
    expect_true(len(insns) > 0, "instructions between main and done", "none",
                hint="Write your code between `main:` and `done:`.")
    bad = [f"{i.addr:08X}: {i.text}" for i in insns if i.word != 0 and op(i) not in OPS]
    expect_true(not bad, "only the allowed instructions", "; ".join(bad[:4]))


@static_check("instruction mix: at least 12 sb, 3 sh, 5 sw, 8 lbu, 1 lw",
              hint="The project needs byte, halfword and word stores and byte loads; "
                   "each part of the layout names the instruction to use.")
def _(ctx):
    insns = code(ctx)
    n = {name: sum(1 for i in insns if OPS.get(op(i)) == name) for name in OPS.values()}
    need = {"sb": 12, "sh": 3, "sw": 5, "lbu": 8, "lw": 1}
    short = [f"{k}: {n[k]} (need {v})" for k, v in need.items() if n[k] < v]
    expect_true(not short, "enough of each memory instruction", "; ".join(short))


@static_check("part C builds a KSEG1 (0xA...) and a KUSEG (0x0...) address",
              hint="Use `lui` with 0xA000 | (results >> 16 & 0x1FFF) for KSEG1 and results >> 16 & 0x1FFF for KUSEG.")
def _(ctx):
    hi = (ctx.symbols["results"] >> 16) & 0x1FFF
    imms = [i.word & 0xFFFF for i in code(ctx) if op(i) == 0x0F]
    expect_true((0xA000 | hi) in imms, f"a lui of 0x{0xA000 | hi:04X}", "not found")
    expect_true(hi in imms, f"a lui of 0x{hi:04X}", "not found")


@check("program reaches `done`", hint="A hang or crash before done; run with -v.")
def _(ctx):
    ctx.result.require_break()


def fmt(b):
    return b.hex(" ").upper()


@check("results holds the expected little-endian bytes",
       hint="Compare each offset with the table in the chapter. Reversed bytes mean you stored "
            "them in big-endian order; a wrong width (sw instead of sh) overwrites a neighbour.")
def _(ctx):
    mem = ctx.result.mem("results")
    for off, want in LAYOUT.items():
        got = mem[off:off + len(want)]
        if got != want:
            raise CheckFailure(expected=f"results+0x{off:02X}: {fmt(want)}",
                               actual=f"results+0x{off:02X}: {fmt(got)}",
                               message=f"wrong bytes at results+0x{off:02X}")


@check("scratchpad word 0x1F800000 holds 0x600DCAFE",
       hint="Store the word with sw to 0x1F800000 (lui 0x1F80, offset 0).")
def _(ctx):
    expect_eq(ctx.result.u32("scratch"), SCRATCH_VALUE, "scratchpad word")


@check("every layout byte is written by the program, not left to the zero fill",
       hint="Your program passes only if it writes the bytes itself; data pre-placed in the file "
            "is overwritten by the verifier before the run.")
def _(ctx):
    r = ctx.run("poison", patches={"results": b"\xAA" * 64})
    mem = r.mem("results")
    for off, want in LAYOUT.items():
        got = mem[off:off + len(want)]
        if got != want:
            raise CheckFailure(expected=f"results+0x{off:02X}: {fmt(want)} (with results pre-filled by AA)",
                               actual=f"results+0x{off:02X}: {fmt(got)}",
                               message="a byte depends on data that was already in the file")


def events(ctx, key):
    base = ctx.result.record("results")
    return [((a & 0x1FFFFFFF) - (base & 0x1FFFFFFF), a, w) for a, w in ctx.result.record(key)]


@check("each value was stored with the required width (sw / sh / sb)",
       hint="The bytes may be right with the wrong instruction. Use sb for the four bytes at 0x08 and the "
            "copies at 0x10-0x17, sh for the halfwords at 0x04, 0x06 and 0x1C, sw for the words.")
def _(ctx):
    got = {(o, w) for o, a, w in events(ctx, "writes") if 0 <= o < 64}
    want = {(0x00, 4), (0x04, 2), (0x06, 2), (0x0C, 4), (0x18, 4), (0x1C, 2), (0x20, 4)}
    want |= {(o, 1) for o in list(range(0x08, 0x0C)) + list(range(0x10, 0x18))}
    missing = sorted(want - got)
    expect_true(not missing, "all required (offset, width) stores",
                "missing " + ", ".join(f"+0x{o:02X}/{w}B" for o, w in missing[:6]))


@check("the endianness proof reads the words back with byte loads",
       hint="Use lbu from results+0..3 and results+0xC..0xF, not constants.")
def _(ctx):
    got = {(o, w) for o, a, w in events(ctx, "reads") if 0 <= o < 16}
    want = {(o, 1) for o in list(range(0, 4)) + list(range(0xC, 0x10))}
    missing = sorted(want - got)
    expect_true(not missing, "an lbu of each of those 8 bytes",
                "missing " + ", ".join(f"+0x{o:02X}" for o, _ in missing[:6]))


@check("the copies come from the loads, not from constants",
       hint="The verifier changed the words at +0x00, +0x0C and 0x1F800000 just before your first load "
            "of each. The copies at +0x10-0x17 and +0x20 must show the new bytes, so build them from "
            "lbu/lw results, not from lui/ori constants. A register stored on the line right after its "
            "load (load delay) also fails here.")
def _(ctx):
    r = ctx.run("perturb", probe=PERTURB)
    mem = r.mem("results")
    for i, (src, dst, new) in enumerate(SWAPS, 1):
        if not r.record(f"swapped{i}"):
            raise CheckFailure(expected=f"a load of the word at {src} after it holds its value",
                               actual="no such load", message=f"{src} was never read back")
        want = new.to_bytes(4, "little")
        got = mem[dst:dst + 4]
        if got != want:
            raise CheckFailure(expected=f"results+0x{dst:02X}: {fmt(want)} (after the verifier changed {src})",
                               actual=f"results+0x{dst:02X}: {fmt(got)}",
                               message=f"results+0x{dst:02X} does not follow the value loaded from {src}")


@check("part C writes through the KSEG1 and KUSEG aliases",
       hint="The same RAM byte is reachable at 0x8001xxxx, 0xA001xxxx and 0x0001xxxx. "
            "Store the word at +0x18 via the 0xA... address and the halfword at +0x1C via the 0x0... address.")
def _(ctx):
    seg = {o: (a >> 29) for o, a, w in events(ctx, "writes")}
    expect_eq(seg.get(0x18), 5, "segment bits of the +0x18 store (101 = KSEG1)", fmt="dec")
    expect_eq(seg.get(0x1C), 0, "segment bits of the +0x1C store (000 = KUSEG)", fmt="dec")


@check("scratchpad was written with sw and read back with lw",
       hint="sw to 0x1F800000, then lw from it, then sw into results+0x20.")
def _(ctx):
    w = [(a, wd) for a, wd in ctx.result.record("writes") if 0x1F800000 <= a < 0x1F800004]
    r = [(a, wd) for a, wd in ctx.result.record("reads") if 0x1F800000 <= a < 0x1F800004]
    expect_true((0x1F800000, 4) in w, "sw at 0x1F800000", str(w))
    expect_true((0x1F800000, 4) in r, "lw at 0x1F800000", str(r))
