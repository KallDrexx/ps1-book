"""Chapter 11 checks: the Vertex Table.
Phase 1 (probe.lua + tools/verify-lib/directcall.lua): vt_translate, vt_bbox, vt_pack and vt_unpack are called
DIRECTLY on scratch buffers with guard bytes (random data, seed printed; packed buffers at every alignment 0..3),
compared byte-for-byte with the Python reference below. Phase 2: the real driver runs on several patched vertex
tables. Static checks: struct table alignment and shipped data, byte-wise / unaligned instructions in the packing
routines. Finally answers.md is checked against what the book's own example/ program does when it is run here."""
import random
import re
import struct
from pathlib import Path

from harness import *
from harness import build_project, run_emulator
from symbols import Symbols

M16 = 0xFFFF
ROUTINES = ["vt_translate", "vt_bbox", "vt_pack", "vt_unpack"]
N = 8
HERE = Path(__file__).resolve().parent

config(
    title="Data Layout and Memory Alignment",
    main="main.s", exe="main.ps-exe", sym="main.sym",
    break_at="done",
    reads={"vertices": 8 * N, "bbox": 12, "pk": ("pk_pre", 6 * N + 2), "roundtrip": 8 * N},
    max_frames=300,
)


# ---- Python reference implementations (the contracts in the chapter) -------------------
def s16(v):
    v &= M16
    return v - 0x10000 if v & 0x8000 else v


def svectors(tab):                       # flat list of u16 -> list of (x, y, z, pad) u16 tuples
    return [tuple(tab[i:i + 4]) for i in range(0, len(tab), 4)]


def pack_svectors(vs):
    return b"".join(struct.pack("<4H", *(c & M16 for c in v)) for v in vs)


def ref_translate(vs, off):
    return [((x + off[0]) & M16, (y + off[1]) & M16, (z + off[2]) & M16, p) for x, y, z, p in vs]


def ref_bbox(vs):
    xs, ys, zs = ([s16(v[i]) for v in vs] for i in range(3))
    return [min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)]


def ref_pack(vs): return b"".join(struct.pack("<3H", x, y, z) for x, y, z, _ in vs)


def ref_unpack(b):
    return pack_svectors([(*struct.unpack_from("<3H", b, 6 * i), 0) for i in range(len(b) // 6)])


def cube(h=100):
    return [(h if i & 1 else -h, h if i & 2 else -h, h if i & 4 else -h, 0) for i in range(8)]


SHIPPED_OFF = (10, -20, 30, 0)
SHIPPED = dict(verts=[tuple(c & M16 for c in v) for v in cube()], off=tuple(c & M16 for c in SHIPPED_OFF))
SETS = {
    "shipped": SHIPPED,
    "negative": dict(verts=[(0xFFF0 - 100 * i, 0x8000 + i, 0xFFFF - i, 0x1234 + i) for i in range(8)],
                     off=(0xFFFF, 0xFF00, 0x0005, 0x4444)),
    "wrap": dict(verts=[(0x7FFF, 0x8000, 0x7FF0 + i, 0xBEEF) for i in range(8)], off=(1, 0xFFFF, 0x0010, 0)),
}
_rng = random.Random(2024)
SETS["random"] = dict(verts=[tuple(_rng.randrange(65536) for _ in range(4)) for _ in range(8)],
                      off=tuple(_rng.randrange(65536) for _ in range(4)))
SETS["varied"] = dict(verts=[(_rng.randrange(-300, 300) & M16, _rng.randrange(-300, 300) & M16,
                              _rng.randrange(-300, 300) & M16, 0) for _ in range(8)], off=(0, 0, 0, 0))


def patch(s):
    return {"vertices": pack_svectors(s["verts"]), "vt_offset": struct.pack("<4H", *s["off"]),
            "bbox": b"\xAA" * 12, "pk_pre": b"\xA5" + b"\xEE" * (6 * N) + b"\xA5", "roundtrip": b"\xEE" * (8 * N)}


# ---- static checks ------------------------------------------------------------------------
LABELS = ["main", "done", *ROUTINES, "routines_end", "vertices", "vt_offset", "bbox", "pk_pre", "packed",
          "pk_post", "roundtrip"]


@static_check("program defines main, done, the four routines and the data labels, in order",
              hint="Keep every label the starter declares. Routines go after `done`, in the starter's order, before "
                   "`routines_end`; the data follows it.")
def _(ctx):
    ctx.require_symbols(*LABELS)
    s = ctx.symbols
    order = ["main", "done", *ROUTINES, "routines_end"]
    for a, b in zip(order, order[1:]):
        expect_true(s[a] < s[b], f"{a} before {b}", f"{a} 0x{s[a]:08X}, {b} 0x{s[b]:08X}")


def raw(ctx, sym, n):
    off = ctx.symbols[sym] - ctx.exe.load_addr
    return ctx.exe.code[off:off + n]


@static_check("the struct table `vertices` is 8-byte aligned (and so are vt_offset and roundtrip)",
              hint="Each SVECTOR is 8 bytes, so put `.align 8` in front of the table; the table starts at a multiple "
                   "of 8 and every element does too. (armips: `.align n` takes a BYTE count, a power of two.)")
def _(ctx):
    for n in ("vertices", "vt_offset", "roundtrip"):
        a = ctx.symbols[n]
        expect_true(a % 8 == 0, f"{n} at a multiple of 8", f"{n} = 0x{a:08X} (remainder {a % 8})")


@static_check("`vertices` holds the cube: 8 SVECTORs, corner i = (+-100, +-100, +-100, pad 0)",
              hint="Vertex i: x = +100 if bit 0 of i is set else -100; y from bit 1; z from bit 2; pad 0. Eight "
                   "`.halfword x, y, z, 0` lines. Negative halfwords are fine for armips.")
def _(ctx):
    want = pack_svectors(cube())
    got = raw(ctx, "vertices", 64)
    expect_eq(got.hex(), want.hex(), "the 64 bytes at `vertices`")
    expect_eq(ctx.symbols["vt_offset"] - ctx.symbols["vertices"], 64, "`vt_offset` right after the 8 structs (64 bytes)")


@static_check("the other data is as shipped (offset, guard bytes, `packed` at an odd address)",
              hint="Do not edit vt_offset, pk_pre/packed/pk_post or roundtrip: the verifier patches its own data. "
                   "`packed` sits at an odd address on purpose.")
def _(ctx):
    s = ctx.symbols
    expect_eq(raw(ctx, "vt_offset", 8), struct.pack("<4H", *SHIPPED["off"]), "vt_offset in the executable")
    expect_eq(s["packed"] - s["pk_pre"], 1, "packed - pk_pre")
    expect_eq(s["pk_post"] - s["packed"], 6 * N, "pk_post - packed")
    expect_true(s["packed"] % 2 == 1, "`packed` at an odd address", f"0x{s['packed']:08X}")
    expect_eq(raw(ctx, "pk_pre", 1) + raw(ctx, "pk_post", 1), b"\xA5\xA5", "guard bytes")
    expect_true(not any(raw(ctx, "packed", 6 * N)) and not any(raw(ctx, "roundtrip", 8 * N)) and not any(raw(ctx, "bbox", 12)),
                "output buffers all zero", "an output buffer contains data")


def op_of(i): return i.word >> 26
def funct_of(i): return i.word & 0x3F


@static_check("the packing routines use unaligned-capable instructions (lwl/lwr, swl/swr or byte loads/stores)",
              hint="vt_pack writes to an address with no alignment guarantee: swr+swl for the word and sb for the rest "
                   "(or all sb). vt_unpack reads from one: lwr+lwl (or lbu). Plain sw/sh/lw/lh there would crash on "
                   "an odd address.")
def _(ctx):
    names = {0x22: "lwl", 0x26: "lwr", 0x2A: "swl", 0x2E: "swr", 0x20: "lb", 0x24: "lbu", 0x28: "sb"}
    pk = {names[op_of(i)] for i in ctx.disassemble_range("vt_pack", "vt_unpack") if op_of(i) in names}
    un = {names[op_of(i)] for i in ctx.disassemble_range("vt_unpack", "routines_end") if op_of(i) in names}
    expect_true(pk & {"swl", "swr", "sb"}, "vt_pack uses swl/swr or sb", f"only: {sorted(pk) or 'none'}")
    expect_true(un & {"lwl", "lwr", "lb", "lbu"}, "vt_unpack uses lwl/lwr or lb/lbu", f"only: {sorted(un) or 'none'}")


@static_check("the driver calls each routine with jal/jalr",
              hint="`main` must call all four routines with `jal` (or `jalr`).")
def _(ctx):
    insns = ctx.disassemble_range("main", "done")
    targets = {((i.addr + 4) & 0xF0000000) | ((i.word & 0x03FFFFFF) << 2) for i in insns if op_of(i) == 3}
    uses_jalr = any(op_of(i) == 0 and funct_of(i) == 9 for i in insns)
    for r in ROUTINES:
        expect_true(ctx.symbols[r] in targets or uses_jalr, f"a `jal {r}` in the driver", "no call to it")


@static_check("armips reports no warnings",
              hint="Usually a load delay: a loaded register used by the very next instruction. (lwr followed directly by "
                   "lwl into the same register is the one legal exception.)")
def _(ctx):
    bad = [l.strip() for l in ctx.build_log.splitlines() if "warning" in l.lower()]
    expect_true(not bad, "no warnings", "; ".join(bad[:2]))


# ---- answers.md ----------------------------------------------------------------------------
def demo(ctx):
    """Build and run the book's example/ crash program; returns its probe records (cached on the context)."""
    if getattr(ctx, "_ch11_demo", None) is None:
        ex = ctx.chapter_dir / "example"
        cfg = ctx.cfg.replace(build="armips", main="main.s", exe="main.ps-exe", sym="main.sym", break_at=None,
                              reads={}, patches={}, probe=HERE / "demo.lua", max_frames=120)
        work = ctx.work / "demo"
        work.mkdir(parents=True, exist_ok=True)
        b = build_project(ex, cfg, work)
        if not b.ok:
            raise HarnessError("the book's example/ program does not build:\n" + b.log)
        r = run_emulator(cfg, b, Symbols.load(str(b.sym_path)), work, "demo", timeout=ctx.timeout)
        ctx._ch11_demo = r
    return ctx._ch11_demo


def parse_answers(text):
    out = {}
    for line in text.splitlines():
        m = re.match(r"^\s*([a-z_]+)\s*:\s*(.*?)\s*$", line)
        if m and m.group(1) not in out:
            out[m.group(1)] = m.group(2)
    return out


def must_match(got, want, key, what, shown, hint):
    """Like expect_eq, but never prints the right value: the point is to read it off Cop0 yourself."""
    if got != want:
        raise CheckFailure(expected=f"{key}: {what} when example/ crashes", actual=f"{key}: {shown} (not it)",
                           message=f"answers.md: {key} does not match what the example produces", hint=hint)


@check("answers.md: exception_code, bad_address and faulting_instruction match the book's misaligned-load example",
       hint="Run example/ (make run, or the debugger from Chapter 6). When it stops at the exception handler, read Cop0: "
            "Cause bits 6..2 (the exception code), BadVAddr (the address that was not aligned) and EPC (the faulting "
            "instruction's address; look at the instruction there). Fill in the three lines in answers.md.")
def _(ctx):
    path = ctx.project / "answers.md"
    if not path.exists():
        raise CheckFailure(expected="an answers.md in your project folder", actual="no such file")
    a = parse_answers(path.read_text(errors="replace"))
    r = demo(ctx)
    r.require_finished()
    code = r.record("code")
    expect_true(code is not None, "the example raises an exception", "it did not (was example/ edited?)")
    bad, insn = r.record("badvaddr"), r.record("insn")
    mnem = {0x23: "lw", 0x21: "lh", 0x25: "lhu", 0x2B: "sw", 0x29: "sh"}.get(insn >> 26, "?")
    try:
        got_code = int(a.get("exception_code", ""), 0)
    except ValueError:
        raise CheckFailure(expected=f"exception_code: <number>", actual=f"exception_code: {a.get('exception_code', '(missing)')!r}",
                           message="exception_code is missing or not a number")
    must_match(got_code, code, "exception_code", "the code in Cop0 Cause, bits 6..2", str(got_code),
               "Read Cause in the debugger and take bits 6..2 (Cause >> 2 & 31).")
    try:
        got_bad = int(a.get("bad_address", ""), 0)
    except ValueError:
        raise CheckFailure(expected="bad_address: 0x<hex>", actual=f"bad_address: {a.get('bad_address', '(missing)')!r}",
                           message="bad_address is missing or not a number")
    must_match(got_bad, bad, "bad_address", "the address in Cop0 BadVAddr", f"0x{got_bad:08X}",
               "BadVAddr is Cop0 register 8: the address the load tried to use. Cross-check it against the label "
               "`bytes` in example/build/main.sym plus the offset the program adds.")
    got_m = a.get("faulting_instruction", "").lower()
    must_match(got_m, mnem, "faulting_instruction", "the mnemonic of the instruction at Cop0 EPC", got_m or "(empty)",
               "EPC (Cop0 register 14) is the address of the instruction that faulted. Which load is it?")


@check("answers.md: a short explanation in your own words (at least 10 words)",
       hint="Fill in the `explanation:` line: why does the CPU refuse this load, and what would you use instead if the "
            "data really can sit at any address?")
def _(ctx):
    path = ctx.project / "answers.md"
    a = parse_answers(path.read_text(errors="replace")) if path.exists() else {}
    words = re.findall(r"[A-Za-z0-9_'\-]+", a.get("explanation", ""))
    expect_true(len(words) >= 10 and len(set(w.lower() for w in words)) >= 6, "an explanation of at least 10 words",
                f"{len(words)} words", hint="Two sentences are plenty. No particular wording is required.")


# ---- dynamic helpers -----------------------------------------------------------------------
def calls_of(ctx):
    r = ctx.result
    r.require_break()
    cs = r.record("calls")
    expect_true(cs, "the probe recorded direct calls", "none", hint="The routines must exist and `main` must run.")
    return cs, r.record("seed")


def describe(c):
    fn = c["fn"]
    if fn in ("vt_pack", "vt_unpack"):
        return f"{fn}(count={c['n']}, buffer alignment {c['off']} mod 4)"
    return f"{fn}(count={c['n']})"


def expected_out(c):
    fn = c["fn"]
    if fn == "vt_translate":
        return pack_svectors(ref_translate(svectors(c["tab"]), c["off"]))
    if fn == "vt_bbox":
        return struct.pack("<6H", *(v & M16 for v in ref_bbox(svectors(c["tab"]))))
    if fn == "vt_pack":
        return ref_pack(svectors(c["tab"]))
    return ref_unpack(bytes(c["bytes"]))


HINTS = {
    "vt_translate": "For each vertex: lh x, y, z, add dx, dy, dz, and sh them back. sh keeps the low 16 bits, which "
                    "is the wraparound the contract asks for (32767 + 1 = -32768). The pad field is left alone. "
                    "Stride is 8 bytes.",
    "vt_bbox": "Start min and max from vertex 0, then compare each later vertex per axis with SIGNED slt (lh sign-"
               "extends). Output order: min x, min y, min z, max x, max y, max z, as halfwords.",
    "vt_pack": "Per vertex: x, y, z little-endian, 6 bytes, no pad. Read the aligned table with lw + lhu; write at "
               "any alignment with swr/swl for x and y and sb for z (or sb everywhere). Return 6 * count in $v0.",
    "vt_unpack": "Read x and y with lwr 0(a0) / lwl 3(a0), z with two lbu; build a word (z low half, 0 high half) and "
                 "store both words at the 8-byte slot. The pad must come out 0.",
}


def readable(fn, hx):
    """Signed-decimal view of a hex string of 16-bit little-endian values, grouped per vertex."""
    b = bytes.fromhex(hx)
    vals = [s16(v) for v in struct.unpack_from(f"<{len(b) // 2}H", b)]
    if fn == "vt_bbox":
        return f"min {vals[:3]} max {vals[3:]}"
    g = 3 if fn == "vt_pack" else 4
    return " ".join(str(tuple(vals[i:i + g])) for i in range(0, len(vals), g))


def result_check(ctx, fn):
    cs, seed = calls_of(ctx)
    n = 0
    for c in cs:
        if c["fn"] != fn or not c["returned"]:
            continue
        n += 1
        want = expected_out(c).hex()
        if c["out"] != want:
            raise CheckFailure(expected=readable(fn, want), actual=readable(fn, c["out"]),
                               message=f"{describe(c)} produced the wrong bytes (probe seed {seed}); "
                                       f"input: {c.get('tab') or c.get('bytes')}"
                                       + (f", offset {c['off']}" if fn == "vt_translate" else ""),
                               hint=HINTS[fn])
        if fn == "vt_pack" and (c["v0"] & 0xFFFFFFFF) != 6 * c["n"]:
            raise CheckFailure(expected=f"$v0 = {6 * c['n']}", actual=f"$v0 = {c['v0'] & 0xFFFFFFFF}",
                               message=f"{describe(c)} returned the wrong byte count (probe seed {seed})", hint=HINTS[fn])
    expect_true(n > 0, f"at least one call of {fn} returns", "no call returned",
                hint=f"Every direct call of {fn} ran too long without reaching the address in $ra (still a TODO stub "
                     "that returns without work counts as returning; a loop that never ends does not).")


# ---- dynamic checks ------------------------------------------------------------------------
@check("program reaches `done`", hint="A hang is a loop that never ends. Run with -v.")
def _(ctx): ctx.result.require_break()


@check("no CPU exception while the routines run",
       hint="Code 4 = a load (lh/lw) from a misaligned address, 5 = a store (sh/sw). The message gives the address and "
            "pc. In vt_pack/vt_unpack the packed buffer can start at ANY address: use lwl/lwr, swl/swr or byte ops "
            "there. In the others, check your pointer arithmetic (stride 8, offsets 0, 2, 4).")
def _(ctx):
    r = ctx.result
    r.require_finished()
    for c in r.record("calls") or []:
        if c.get("exception"):
            raise CheckFailure(expected="no exception", actual=exception_text(c["exception"])[2:],
                               message=f"during the direct call {describe(c)} (probe seed {r.record('seed')}); "
                                       "the run stops at the first exception")
    ex = r.record("exception")
    if ex:
        raise CheckFailure(expected="no exception", actual=exception_text(ex)[2:], message="while running the driver")


@check("vt_translate adds the offset to x, y, z (16-bit wraparound, pad untouched)", hint=HINTS["vt_translate"])
def _(ctx): result_check(ctx, "vt_translate")


@check("vt_bbox gives signed min/max per axis as six halfwords", hint=HINTS["vt_bbox"])
def _(ctx): result_check(ctx, "vt_bbox")


@check("vt_pack writes x,y,z (6 bytes per vertex) to a buffer at ANY alignment and returns 6*count", hint=HINTS["vt_pack"])
def _(ctx): result_check(ctx, "vt_pack")


@check("vt_unpack reads packed data from ANY alignment and rebuilds SVECTORs with pad = 0", hint=HINTS["vt_unpack"])
def _(ctx): result_check(ctx, "vt_unpack")


@check("routines write only where they should, and do not modify their inputs",
       hint="Guard bytes surround every buffer. Writing 8 bytes per vertex into the packed buffer (instead of 6), "
            "an off-by-one on the count, or changing the table in vt_pack/vt_bbox/vt_unpack are all caught here.")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if not c["returned"]:
            continue
        if not c["guard_ok"]:
            raise CheckFailure(expected="the guard bytes around the output are untouched", actual="a guard byte changed",
                               message=f"{describe(c)} wrote outside its output (probe seed {seed})")
        if c["fn"] != "vt_translate" and not c["in_ok"]:
            raise CheckFailure(expected="the input is unchanged", actual="the input was modified",
                               message=f"{describe(c)} modified its input (probe seed {seed})")
        if c["fn"] == "vt_translate" and not c["in_ok"]:
            raise CheckFailure(expected="the offset SVECTOR is unchanged", actual="the offset was modified",
                               message=f"{describe(c)} modified the offset (probe seed {seed})")


@check("every routine returns through $ra",
       hint="The harness sets $ra to a trampoline; the routines are leaves, so just `jr $ra`.")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if not c["returned"]:
            raise CheckFailure(expected="the call returns to the address in $ra",
                               actual=(exception_text(c.get("exception"))[2:] or
                                       f"still running after {c['instrs']} instructions"),
                               message=f"{describe(c)} never returned (probe seed {seed})")


@check("callee-saved registers ($s0-$s7, $gp, $sp, $fp) are unchanged by every call",
       hint="These are leaf routines: use $t0-$t9, $a0-$a3, $v0-$v1 only.")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if c["returned"] and c["clobbered"]:
            raise CheckFailure(expected="$s0-$s7, $gp, $sp, $fp all unchanged",
                               actual="changed: " + ", ".join("$" + n for n in c["clobbered"]),
                               message=f"{describe(c)} clobbered a callee-saved register (probe seed {seed})")


@check("instruction budget: at most 60 instructions per vertex (+100)",
       hint="Generous. Going over means a loop that runs far too often (a byte-by-byte loop per vertex is fine).")
def _(ctx):
    cs, seed = calls_of(ctx)
    for c in cs:
        if c["returned"]:
            b = 60 * c["n"] + 100
            expect_true(c["instrs"] <= b, f"{describe(c)} within {b} instructions", f"{c['instrs']} instructions")


def run_set(ctx, key):
    s = SETS[key]
    r = ctx.run(key, patches=patch(s))
    r.require_break()
    vs = ref_translate(s["verts"], s["off"])
    pk = ref_pack(vs)
    want = {"vertices (translated in place)": (r.mem("vertices"), pack_svectors(vs)),
            "bbox": (r.mem("bbox"), struct.pack("<6H", *(v & M16 for v in ref_bbox(vs)))),
            "packed (pk_pre..pk_post: guard, 48 bytes, guard)": (r.mem("pk"), b"\xA5" + pk + b"\xA5"),
            "roundtrip (unpacked, pad 0)": (r.mem("roundtrip"), ref_unpack(pk))}
    for name, (got, exp) in want.items():
        if bytes(got) != exp:
            raise CheckFailure(expected=f"{name} = {exp.hex()}", actual=bytes(got).hex(),
                               message=f"data set '{key}': vertices {[tuple(s16(c) for c in v) for v in s['verts']]}, "
                                       f"offset {[s16(c) for c in s['off']]}")
    return r


@check("driver: vertices, bbox, packed and roundtrip are right for the shipped cube",
       hint="Cube + offset (10, -20, 30): translated corners, bbox (-90,-120,-70)..(110,80,130), 48 packed bytes, "
            "and `roundtrip` equal to the translated table.")
def _(ctx): run_set(ctx, "shipped")


@check("driver: results follow patched data (negative coordinates, 16-bit wraparound, non-zero pads)",
       hint="The vertex table and offset are replaced before the run, so constants fail. Coordinates are SIGNED 16-bit; "
            "sums wrap (0x7FFF + 1 = 0x8000 = -32768) and the pad field never changes in `vertices`, but is 0 after unpack.")
def _(ctx):
    for key in ("negative", "wrap", "random", "varied"):
        run_set(ctx, key)


@check("driver: it calls all four routines",
       hint="`main` must really call vt_translate, vt_bbox, vt_pack and vt_unpack.")
def _(ctx):
    r = ctx.result
    r.require_break()
    ent = r.record("entries") or {}
    for n in ROUTINES:
        expect_true(ent.get(n, 0) >= 1, f"{n} entered during the driver run", "never entered")
