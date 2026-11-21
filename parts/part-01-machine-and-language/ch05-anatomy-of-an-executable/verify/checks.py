"""Chapter 5 checks: a host-side PSX-EXE inspector (exeinfo.py) and a hand-written header.

Part a: exeinfo.py is run on EXEs that this file generates at verify time (valid ones with
varied fields and instruction mixes, and malformed ones with exactly one defect each), so
nothing can be hard-coded.  Part b: the header of the reader's built EXE is checked field by
field, then the program is run to prove the BIOS really used those fields.
"""
import random
import re
import struct
import subprocess
import sys

from harness import *

config(
    title="Anatomy of an Executable: The PSX-EXE Format",
    main="main.s", exe="main.ps-exe", sym="main.sym",
    break_at="done", reads={"results": 16, "table": 32},
    max_frames=300,
)

M = 0xFFFFFFFF
MAGIC = b"PS-X EXE"
REGIONS = ["Sony Computer Entertainment Inc. for Japan area",
           "Sony Computer Entertainment Inc. for Europe area",
           "Sony Computer Entertainment Inc. for North America area"]
DEFAULT_LOAD = 0x80010000
REGS = ("zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 "
        "t8 t9 k0 k1 gp sp fp ra").split()


# ---------------------------------------------------------------------------
# Reference encoder / disassembler (the spec for part a)
# ---------------------------------------------------------------------------
R_SH = {"sll": 0x00, "srl": 0x02, "sra": 0x03}                    # rd, rt, sa
R_3 = {"addu": 0x21, "subu": 0x23, "and": 0x24, "or": 0x25, "xor": 0x26, "nor": 0x27,
       "slt": 0x2A, "sltu": 0x2B}                                  # rd, rs, rt
I_ARITH = {"addiu": 0x09, "slti": 0x0A, "sltiu": 0x0B, "andi": 0x0C, "ori": 0x0D, "xori": 0x0E}
I_MEM = {"lb": 0x20, "lh": 0x21, "lw": 0x23, "lbu": 0x24, "lhu": 0x25, "sb": 0x28, "sh": 0x29, "sw": 0x2B}
I_BR2 = {"beq": 0x04, "bne": 0x05}
I_BR1 = {"blez": 0x06, "bgtz": 0x07}
J_OPS = {"j": 0x02, "jal": 0x03}
FORMS = (["sh"] * len(R_SH) + ["r3"] * len(R_3) + ["jr"] + ["arith"] * len(I_ARITH) + ["lui"] +
         ["mem"] * len(I_MEM) + ["br2"] * 2 + ["br1"] * 2 + ["regimm"] * 2 + ["j"] * 2)


def rand_insn(rng, addr):
    """Random supported instruction word at `addr`."""
    rs, rt, rd = (rng.randrange(32) for _ in range(3))
    imm = rng.choice([0, 1, 0x7FFF, 0x8000, 0xFFFF, rng.randrange(0x10000), rng.randrange(0x10000)])
    sa = rng.randrange(32)
    kind = rng.choice(FORMS)
    if kind == "sh":
        return (rt << 16) | (rd << 11) | (sa << 6) | rng.choice(list(R_SH.values()))
    if kind == "r3":
        return (rs << 21) | (rt << 16) | (rd << 11) | rng.choice(list(R_3.values()))
    if kind == "jr":
        return (rs << 21) | 0x08
    if kind == "arith":
        return (rng.choice(list(I_ARITH.values())) << 26) | (rs << 21) | (rt << 16) | imm
    if kind == "lui":
        return (0x0F << 26) | (rt << 16) | imm
    if kind == "mem":
        return (rng.choice(list(I_MEM.values())) << 26) | (rs << 21) | (rt << 16) | imm
    if kind == "br2":
        return (rng.choice(list(I_BR2.values())) << 26) | (rs << 21) | (rt << 16) | imm
    if kind == "br1":
        return (rng.choice(list(I_BR1.values())) << 26) | (rs << 21) | imm
    if kind == "regimm":
        return (1 << 26) | (rs << 21) | (rng.choice([0, 1]) << 16) | imm
    return (rng.choice(list(J_OPS.values())) << 26) | rng.randrange(1 << 26)


def sx16(v): return v - 0x10000 if v & 0x8000 else v


def ref_disasm(w, addr):
    """-> (mnemonic, [tokens]); register tokens are str, numeric tokens are (exact value, bits).

    Signed immediates (addiu/slti/sltiu, memory offsets) carry their sign-extended value, unsigned
    ones (andi/ori/xori/lui) their raw value, so a printed number must have the right sign."""
    if w == 0:
        return "nop", []
    op, rs, rt, rd = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
    sa, fn, imm = (w >> 6) & 31, w & 63, w & 0xFFFF
    R = REGS
    if op == 0:
        for n, f in R_SH.items():
            if f == fn: return n, [R[rd], R[rt], (sa, 5)]
        for n, f in R_3.items():
            if f == fn: return n, [R[rd], R[rs], R[rt]]
        if fn == 0x08: return "jr", [R[rs]]
    elif op == 1 and rt in (0, 1):
        return ("bltz", "bgez")[rt], [R[rs], ((addr + 4 + 4 * sx16(imm)) & M, 32)]
    elif op in (2, 3):
        return ("j", "jal")[op - 2], [(((addr + 4) & 0xF0000000) | ((w & 0x3FFFFFF) << 2), 32)]
    elif op in I_BR2.values():
        n = [k for k, v in I_BR2.items() if v == op][0]
        return n, [R[rs], R[rt], ((addr + 4 + 4 * sx16(imm)) & M, 32)]
    elif op in I_BR1.values():
        n = [k for k, v in I_BR1.items() if v == op][0]
        return n, [R[rs], ((addr + 4 + 4 * sx16(imm)) & M, 32)]
    elif op in I_ARITH.values():
        n = [k for k, v in I_ARITH.items() if v == op][0]
        return n, [R[rt], R[rs], (sx16(imm) if n in ("addiu", "slti", "sltiu") else imm, 16)]
    elif op == 0x0F:
        return "lui", [R[rt], (imm, 16)]
    elif op in I_MEM.values():
        n = [k for k, v in I_MEM.items() if v == op][0]
        return n, [R[rt], (sx16(imm), 16), R[rs]]
    return ".word", [(w, 32)]


TOKEN = re.compile(r"-?0[xX][0-9a-fA-F]+|-?\d+|\.?[A-Za-z_]\w*")


def line_matches(text, want):
    """Compare a printed instruction (text after the hex word) with the reference."""
    mn, toks = want
    got = TOKEN.findall(text.strip().lower())
    if not got or got[0] != mn or len(got) - 1 != len(toks):
        return False
    for g, t in zip(got[1:], toks):
        if isinstance(t, str):
            if g != t: return False
        else:
            try: v = int(g, 0)
            except ValueError: return False
            if v != t[0]: return False
    return True


# ---------------------------------------------------------------------------
# EXE builder
# ---------------------------------------------------------------------------
def build_exe(words=None, load=DEFAULT_LOAD, pc=None, gp=0, sp_base=0x801FFF00, sp_off=0,
              size=None, nwords=0x200, region=REGIONS[2], magic=MAGIC, trailing=b"", payload=None):
    payload = payload if payload is not None else b"".join(struct.pack("<I", w) for w in words)
    payload = payload.ljust(((len(payload) + 0x7FF) // 0x800) * 0x800, b"\0")
    if size is None:
        size = len(payload)
    hdr = bytearray(0x800)
    hdr[:8] = magic
    struct.pack_into("<IIII", hdr, 0x10, load if pc is None else pc, gp, load, size)
    struct.pack_into("<II", hdr, 0x30, sp_base, sp_off)
    hdr[0x4C:0x4C + len(region)] = region.encode()
    return bytes(hdr) + payload + trailing


def sample_words(seed, addr, n=0x200):
    rng = random.Random(seed)
    ws = [rand_insn(rng, addr + 4 * i) for i in range(n)]
    return ws


def with_special(ws, specials):
    ws = list(ws)
    for i, w in specials.items():
        ws[i] = w
    return ws


# valid samples: (name, kwargs, words)
def valid_samples():
    out = []
    ws = with_special(sample_words(11, 0x80010000), {0: 0, 1: 0x3C08A001, 2: 0x35088000, 3: 0x0C004000, 4: 0})
    out.append(("default load, North America", dict(load=0x80010000, pc=0x80010000), ws))
    ws = with_special(sample_words(22, 0x80123800), {0: 0x40086000, 1: 0x0000000C, 5: 0x27BDFFE8})
    out.append(("load 0x80123800, pc inside image, Europe, GP set",
                dict(load=0x80123800, pc=0x80123810, gp=0x8012B800, region=REGIONS[1], sp_base=0x801FFF00,
                     sp_off=0x100), ws))
    ws = sample_words(33, 0x80018000, 0x800)
    out.append(("Japan, 8 KB image",
                dict(load=0x80018000, pc=0x80018FFC, gp=0xDEAD0000, region=REGIONS[0], sp_base=0x801FFFF0),
                ws))
    ws = sample_words(44, 0x801F0000, 0x200)
    out.append(("image ends exactly at the top of RAM, trailing bytes after payload",
                dict(load=0x801F0000, pc=0x801F0000, sp_base=0, trailing=b"\xEE" * 0x100), ws))
    return out


def invalid_samples():
    ws = sample_words(55, 0x80010000)
    good = dict(words=ws, load=0x80010000, pc=0x80010000)
    return [
        ("magic", "magic wrong (PS-X EXF)", build_exe(**good, magic=b"PS-X EXF")),
        ("magic", "magic lower-case", build_exe(**good, magic=b"ps-x exe")),
        ("short", "empty file", b""),
        ("short", "100 bytes", build_exe(**good)[:100]),
        ("short", "header cut at 0x400", build_exe(**good)[:0x400]),
        ("size", "size field larger than the file", build_exe(**good, size=0x1000)[:0x800 + 0x800]),
        ("size", "size not a multiple of 0x800", build_exe(**good, size=0x900)),
        ("load", "load address in KUSEG (0x00010000)", build_exe(**{**good, "load": 0x10000, "pc": 0x10000})),
        ("load", "image runs past the 2 MB of RAM", build_exe(words=ws, load=0x801FF800, pc=0x801FF800, size=0x1000,
                                                              payload=b"\0" * 0x1000)),
        ("pc", "pc one word past the end of the image", build_exe(**{**good, "pc": 0x80010000 + 0x800})),
        ("pc", "pc below the load address", build_exe(**{**good, "pc": 0x8000FFFC})),
        ("pc", "pc not word-aligned", build_exe(**{**good, "pc": 0x80010002})),
        ("region", "unknown region string", build_exe(**good, region="Sony Computer Entertainment Inc. for Mars area")),
        ("region", "no region string", build_exe(**good, region="")),
    ]


# ---------------------------------------------------------------------------
# Running exeinfo.py
# ---------------------------------------------------------------------------
KEYS = {"magic", "pc", "gp", "load", "size", "sp", "region"}
DIS = re.compile(r"^\s*([0-9A-Fa-f]{8}):?\s+([0-9A-Fa-f]{8})\s+(.*\S)\s*$")


def run_exeinfo(ctx, data, name):
    script = ctx.project / "exeinfo.py"
    if not script.is_file():
        raise CheckFailure(expected="exeinfo.py next to main.s", actual="file not found",
                           message="exeinfo.py is missing", hint="Keep exeinfo.py in the project directory.")
    p = ctx.work / "exeinfo-in" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    try:
        r = subprocess.run([sys.executable, str(script), str(p)], capture_output=True, text=True,
                           errors="replace", stdin=subprocess.DEVNULL, timeout=10, cwd=str(p.parent))
    except subprocess.TimeoutExpired:
        raise CheckFailure(expected="exeinfo.py finishes in 10 s", actual="timeout",
                           message=f"exeinfo.py hung on '{name}'", hint="Look for a loop that never ends.")
    return r


def parse_ok(r, what):
    """Parse a successful exeinfo run -> (fields, [(addr, word, text)])."""
    if r.returncode != 0:
        first = (r.stdout.strip().splitlines() or r.stderr.strip().splitlines() or ["(no output)"])[0]
        raise CheckFailure(expected=f"exit status 0 for {what}", actual=f"exit {r.returncode}: {first[:100]}",
                           message=f"exeinfo.py rejected a valid EXE ({what})",
                           hint="Run it by hand on the file; check each rule against the chapter's table. "
                                "A traceback on stderr shows up here as the first line.")
    fields, insns = {}, []
    for line in r.stdout.splitlines():
        m = DIS.match(line)
        if m:
            insns.append((int(m[1], 16), int(m[2], 16), m[3]))
            continue
        m = re.match(r"^\s*(\w+)\s*:\s*(.*?)\s*$", line)
        if m and m[1].lower() in KEYS:
            fields[m[1].lower()] = m[2]
    return fields, insns


def num(s):
    try:
        return int(s.split()[0], 0)
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Part a: exeinfo.py
# ---------------------------------------------------------------------------
@static_check("exeinfo.py exists and runs",
              hint="Put exeinfo.py next to main.s; usage: python3 exeinfo.py FILE.")
def _(ctx):
    name, kw, ws = valid_samples()[0]
    r = run_exeinfo(ctx, build_exe(ws, **kw), "a.ps-exe")
    if "Traceback" in r.stderr:
        raise CheckFailure(expected="no Python exception", actual=r.stderr.strip().splitlines()[-1][:120],
                           message="exeinfo.py crashed", hint="Fix the exception on the last line first.")
    expect_true(r.stdout.strip() != "", "some output on stdout", "nothing printed")


@static_check("exeinfo.py prints the header fields of valid EXEs",
              hint="One 'key: value' line each for magic, pc, gp, load, size, sp, region. Numbers as 0x... hex. "
                   "'sp' is the base plus the offset; 'size' is the payload size, not the file size. "
                   "Mind the byte order: every field is little-endian.")
def _(ctx):
    for name, kw, ws in valid_samples():
        data = build_exe(ws, **kw)
        fields, _insns = parse_ok(run_exeinfo(ctx, data, "v.ps-exe"), name)
        pc, gp, load, size, base, off = struct.unpack_from("<6I", data, 0x10)[0], *struct.unpack_from("<III", data, 0x14), *struct.unpack_from("<II", data, 0x30)
        want = {"pc": pc, "gp": gp, "load": load, "size": size, "sp": (base + off) & M}
        missing = [k for k in ("magic", "pc", "gp", "load", "size", "sp", "region") if k not in fields]
        expect_true(not missing, "all seven keys printed", f"missing: {', '.join(missing)}",
                    hint="Lines look like 'pc: 0x80010000'; keys are lower-case.")
        for k, v in want.items():
            expect_eq(num(fields[k]), v, f"'{k}' for sample '{name}'", fmt="hex")
        expect_eq(fields["magic"].strip(), "PS-X EXE", f"'magic' for sample '{name}'")
        expect_eq(fields["region"].strip(), kw.get("region", REGIONS[2]), f"'region' for sample '{name}'")


@static_check("exeinfo.py disassembles the first 16 instructions from the load address",
              hint="Print 'ADDR: WORD  mnemonic operands' for the first 16 words of the payload (file offset "
                   "0x800), ADDR starting at the load address. Branch/jump targets are absolute addresses. "
                   "Words you do not know print as '.word 0x...'. Registers use ABI names (t0, sp, ...).")
def _(ctx):
    for name, kw, ws in valid_samples():
        data = build_exe(ws, **kw)
        fields, insns = parse_ok(run_exeinfo(ctx, data, "d.ps-exe"), name)
        load = kw["load"]
        expect_eq(len(insns), 16, f"number of disassembly lines for '{name}'",
                  hint="Exactly 16 lines of the form ADDR: WORD text.")
        for i, (addr, word, text) in enumerate(insns):
            w = ws[i]
            if addr != load + 4 * i or word != w:
                raise CheckFailure(expected=f"{load + 4 * i:08X}: {w:08X}", actual=f"{addr:08X}: {word:08X}",
                                   message=f"line {i + 1} of '{name}' shows the wrong address or word",
                                   hint="Words are little-endian in the file; addresses start at the load address.")
            want = ref_disasm(w, load + 4 * i)
            if not line_matches(text, want):
                ops = [t if isinstance(t, str) else str(t[0]) if t[0] < 0 else f"0x{t[0]:X}" for t in want[1]]
                if want[0] in I_MEM:
                    ops = [ops[0], f"{ops[1]}({ops[2]})"]
                shown = want[0] + " " + ", ".join(ops)
                raise CheckFailure(expected=f"{shown}   (word {w:08X} at {load + 4 * i:08X})",
                                   actual=text.strip(),
                                   message=f"instruction {i + 1} of '{name}' decoded wrongly",
                                   hint="Re-check the bit fields of that format (R/I/J), the sign of the immediate "
                                        "(section 5.5) and the branch offset: target = address of next "
                                        "instruction + 4 * signed offset.")


@static_check("exeinfo.py rejects malformed EXEs with the right category",
              hint="Print 'INVALID: <category>' as the FIRST line and exit with status 1. Categories (checked "
                   "in this order): short, magic, size, load, pc, region. Each bad file has one defect.")
def _(ctx):
    for cat, what, data in invalid_samples():
        r = run_exeinfo(ctx, data, "bad.ps-exe")
        lines = r.stdout.strip().splitlines()
        first = lines[0] if lines else "(no output)"
        m = re.match(r"^INVALID:\s*(\w+)", first)
        if r.returncode != 1 or not m:
            raise CheckFailure(expected=f"exit 1 and 'INVALID: {cat}'", actual=f"exit {r.returncode}, '{first[:60]}'",
                               message=f"malformed file not reported ({what})",
                               hint="Validate before printing anything else; never crash on short input.")
        expect_eq(m[1].lower(), cat, f"category for '{what}'",
                  hint="Check the rules in the chapter's table, in the listed order.")


@static_check("exeinfo.py agrees with your hand-built EXE",
              hint="Run it on build/main.ps-exe and compare with the header you wrote.")
def _(ctx):
    data = ctx.exe.data
    fields, insns = parse_ok(run_exeinfo(ctx, data, "mine.ps-exe"), "your main.ps-exe")
    expect_eq(num(fields.get("load", "")), ctx.exe.load_addr, "load for your EXE", fmt="hex")
    expect_eq(num(fields.get("pc", "")), ctx.exe.pc, "pc for your EXE", fmt="hex")
    expect_eq(len(insns), 16, "disassembly lines for your EXE")
    for i, (addr, word, text) in enumerate(insns):
        w = struct.unpack_from("<I", data, 0x800 + 4 * i)[0]
        expect_eq(word, w, f"word {i} for your EXE", fmt="hex")
        if not line_matches(text, ref_disasm(w, ctx.exe.load_addr + 4 * i)):
            raise CheckFailure(expected=str(ref_disasm(w, ctx.exe.load_addr + 4 * i)), actual=text,
                               message=f"instruction {i} of your EXE decoded wrongly")


# ---------------------------------------------------------------------------
# Part b: the hand-written header
# ---------------------------------------------------------------------------
def header_ok(ctx):
    pr = [p for p in ctx.exe.problems()]
    if pr:
        raise CheckFailure(expected="a header that passes basic validation", actual="; ".join(pr[:3]),
                           message="the header is not valid yet", hint="Fix the static header checks first.")


@static_check("program defines main, done, table and results",
              hint="Keep the labels the starter declares.")
def _(ctx):
    ctx.require_symbols("main", "done", "table", "results")


@static_check("the header is written by hand: no .include or .incbin in the sources",
              hint="Emit the 2 KB header yourself with .ascii/.word/.fill. common/psxexe.inc, and any other "
                   "ready-made header, is off limits in this chapter.")
def _(ctx):
    txt = ctx.source_text()
    bad = re.findall(r"\.(?:include|incbin|import)\b[^\n]*", txt, flags=re.I)
    expect_true(not bad, "no .include / .incbin", "; ".join(bad[:2]))


@static_check("header starts with the magic 'PS-X EXE' followed by 8 zero bytes",
              hint="Offset 0x00: the 8 ASCII characters P S - X (space) E X E; offsets 0x08-0x0F: zero.")
def _(ctx):
    d = ctx.exe.data
    expect_eq(d[:8], MAGIC, "bytes 0x00-0x07")
    expect_eq(d[8:16], b"\0" * 8, "bytes 0x08-0x0F")


@static_check("file is a 2048-byte header plus a payload whose size field is exact",
              hint="File size = 0x800 + size field; the size field is a multiple of 0x800 and counts the payload "
                   "only (use `__exe_end - LOAD`; keep `.align 0x800` before `__exe_end`).")
def _(ctx):
    e = ctx.exe
    expect_true(e.text_size > 0 and e.text_size % 0x800 == 0, "size field a positive multiple of 0x800",
                f"0x{e.text_size:X}")
    expect_eq(len(e.data), 0x800 + e.text_size, "file size", fmt="hex")


@static_check("load address is non-default, 2 KB aligned, and the image fits in RAM",
              hint="Pick any 2048-aligned address from 0x80011000 to 0x801E0000. It must differ from the "
                   "default 0x80010000. Change .definelabel LOAD, .create and the header word together.")
def _(ctx):
    e = ctx.exe
    expect_true(e.load_addr != DEFAULT_LOAD, "load address other than 0x80010000", f"0x{e.load_addr:08X}")
    expect_true(e.load_addr % 0x800 == 0, "2048-byte aligned", f"0x{e.load_addr:08X}")
    expect_true(0x80011000 <= e.load_addr <= 0x801E0000, "between 0x80011000 and 0x801E0000",
                f"0x{e.load_addr:08X}")
    expect_true(e.load_addr + e.text_size <= 0x80200000, "image ends inside the 2 MB of RAM",
                f"ends at 0x{e.load_addr + e.text_size:08X}")


@static_check("initial PC is the address of `main`, inside the image",
              hint="Offset 0x10 holds a 32-bit address: `.word main`.")
def _(ctx):
    e = ctx.exe
    expect_eq(e.pc, ctx.symbols["main"], "initial PC", fmt="hex")
    expect_true(e.load_addr <= e.pc < e.load_addr + e.text_size, "PC inside the loaded image", f"0x{e.pc:08X}")


@static_check("initial GP is load address + 0x8000; SP base is 0x801FFF00 with offset 0",
              hint="GP at 0x14 = LOAD + 0x8000. SP base at 0x30 = 0x801FFF00, SP offset at 0x34 = 0 "
                   "(PCSX-Redux's side-loader ignores the offset, so a split base/offset would not run the same).")
def _(ctx):
    e = ctx.exe
    expect_eq(e.gp, (e.load_addr + 0x8000) & M, "initial GP", fmt="hex")
    expect_eq(e.sp_base, 0x801FFF00, "SP base (0x30)", fmt="hex")
    expect_eq(e.sp_off, 0, "SP offset (0x34)", fmt="hex")


@static_check("region marker is one of the three standard strings at 0x4C; the rest of the header is zero",
              hint="Offset 0x4C: the ASCII text 'Sony Computer Entertainment Inc. for North America area' (or "
                   "Japan / Europe), then zeros up to 0x800. Bytes 0x20-0x2F and 0x38-0x4B are zero.")
def _(ctx):
    d = ctx.exe.data
    hit = [r for r in REGIONS if d[0x4C:0x4C + len(r)] == r.encode()]
    expect_true(hit, "a standard region string at 0x4C", repr(d[0x4C:0x4C + 56]))
    n = len(hit[0])
    expect_eq(d[0x4C + n:0x800], b"\0" * (0x800 - 0x4C - n), "bytes after the marker")
    expect_eq(d[0x20:0x30] + d[0x38:0x4C], b"\0" * 36, "unused fields 0x20-0x2F and 0x38-0x4B")


@check("program starts at the header's entry point and reaches `done`",
       hint="If the header is wrong the loader may refuse the file or run garbage: the run times out. "
            "Check the load address (header word, .org and .create must agree) and the PC.")
def _(ctx):
    header_ok(ctx)
    ctx.result.require_break()


@check("GP, SP and the program's own address as seen at run time match the header",
       hint="results[0] is $gp, results[1] is $sp, results[2] the address of `main` as assembled, all read by "
            "the program itself. A mismatch means the header says one thing and the code another.")
def _(ctx):
    header_ok(ctx)
    r, e = ctx.result, ctx.exe
    expect_eq(r.u32("results", 0), e.gp, "$gp at run time", fmt="hex",
              hint="Offset 0x14 of the header is loaded into $gp by the loader.")
    expect_eq(r.u32("results", 1), e.sp_base, "$sp at run time", fmt="hex",
              hint="The loader sets $sp from the SP base at 0x30 (plus the offset at 0x34, which is 0 here).")
    expect_eq(r.u32("results", 2), e.pc, "address of main vs. header PC", fmt="hex")
    expect_eq(r.u32("results", 2), ctx.symbols["main"], "address of main", fmt="hex")


@check("the code and data landed at the load address (checksum of `table`, even after the data is changed)",
       hint="The program sums 8 words at `table`; the verifier replaces them. A wrong sum means the payload "
            "was loaded somewhere other than the address the code was assembled for.")
def _(ctx):
    header_ok(ctx)
    orig = struct.unpack("<8I", ctx.result.mem("table"))
    expect_eq(ctx.result.u32("results", 3), sum(orig) & M, "sum of the shipped table", fmt="hex")
    for key, tbl in (("t1", [1, 2, 3, 4, 5, 6, 7, 8]), ("t2", [0xFFFFFFFF, 1, 0x80000000, 0x80000000, 7, 0, 0, 9])):
        try:
            r = ctx.run(key, patches={"table": struct.pack("<8I", *tbl)})
        except ValueError as ex:
            raise CheckFailure(expected="`table` inside the loaded image",
                               actual=str(ex), message="the label `table` is not where the header says the image is",
                               hint="The load address in the header must match the address the code was assembled at (.org).")
        expect_eq(r.u32("results", 3), sum(tbl) & M, f"sum for table {tbl}", fmt="hex")
