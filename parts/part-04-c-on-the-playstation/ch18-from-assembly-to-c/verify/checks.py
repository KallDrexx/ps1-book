"""Chapter 18 checks: From Assembly to C.
Build: CMake + PSn00bSDK (the harness's cmake path). Static: the ELF exports main/expand5/rgb888_to_bgr555/stop_here, the
assembly lives in a .s file (not C), annotated.s is real annotated compiler output for expand5.
Dynamic (probe.lua): expand5 and rgb888_to_bgr555 are called DIRECTLY with all 32 channel values / edge+random colors
(callee-saved registers checked); then the real program runs on three patched colors of `clear_rgb888`, and the probe
records every call to rgb888_to_bgr555 (argument, return value) and, in a fourth run, FORCES a different return
value: the screen must follow it (so the C code really uses the assembly's result). Screenshots are solid-color checks."""
import re

from harness import *

M = 0xFFFFFFFF
FORCE_BGR555 = 0x03E0
SHIPPED = 0x00FF8040
COLORS = {"shipped": None, "teal": 0x00104060, "gold": 0x00F0C818}   # patched values of clear_rgb888
SENTINEL = 0x5A000000 | 0x000000FF                                     # asm would give blue; the probe forces green

config(
    title="From Assembly to C",
    build="cmake", exe="game.exe", sym="", elf="game.elf",
    break_at="stop_here", max_frames=300, settle_frames=2, shots=["end"],
)


def ref_rgb(v):
    r, g, b = (v >> 16) & 255, (v >> 8) & 255, v & 255
    return (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)


def ch8(c5): return (c5 << 3) | (c5 >> 2)


def rgb_of_bgr555(c):
    return (ch8(c & 31), ch8((c >> 5) & 31), ch8((c >> 10) & 31))


def rgb_of_888(v):
    return rgb_of_bgr555(ref_rgb(v))


def patch(v):
    return {"clear_rgb888": v}


# ---- static checks ----------------------------------------------------------------------
@static_check("the ELF exports main, expand5, rgb888_to_bgr555 and stop_here",
              hint="Keep main() and stop_here() from the starter; write expand5 in expand.c; add rgb555.s to "
                   "psn00bsdk_add_executable(...) in CMakeLists.txt so rgb888_to_bgr555 is linked.")
def _(ctx):
    ctx.require_symbols("main", "expand5", "rgb888_to_bgr555", "stop_here", "clear_rgb888",
                        hint="A missing rgb888_to_bgr555: add rgb555.s to psn00bsdk_add_executable(...) in "
                             "CMakeLists.txt AND call it from main(). A missing expand5: call it from main(). "
                             "The linker drops (-gc-sections) any function nothing calls.")


@static_check("rgb888_to_bgr555 comes from an assembly (.s) file with .globl, not from C",
              hint="Link the assembly routine from rgb555.s (or your own port of Chapter 9). Do not rewrite it in C.")
def _(ctx):
    asm = [f for f in ctx.source_files("**/*.s") if f.name != "annotated.s" and "build" not in f.parts]
    expect_true(asm, "a .s file in the project", "none")
    ok = False
    for f in asm:
        t = f.read_text(errors="replace")
        if re.search(r"^\s*\.globl\s+rgb888_to_bgr555\b", t, re.M) and re.search(r"^rgb888_to_bgr555:", t, re.M):
            ok = True
    expect_true(ok, "`.globl rgb888_to_bgr555` and the label in a .s file", "not found")
    for f in ctx.source_files("**/*.c"):
        t = re.sub(r"/\*.*?\*/|//[^\n]*", "", f.read_text(errors="replace"), flags=re.S)
        expect_true(not re.search(r"\brgb888_to_bgr555\s*\([^;{)]*\)\s*\{", t), "no C definition of rgb888_to_bgr555",
                    f"defined in {f.name}")


@static_check("clear_rgb888 is as shipped (0x00FF8040)",
              hint="Do not edit the initial color; the verifier patches its own.")
def _(ctx):
    off = ctx.symbols["clear_rgb888"] - ctx.exe.load_addr
    expect_eq(int.from_bytes(ctx.exe.code[off:off + 4], "little"), SHIPPED, "clear_rgb888 in the executable", fmt="hex")


@static_check("annotated.s exists, defines expand5, and carries your annotations",
              hint="Generate it with `make asm` (or the gcc -O2 -S command in the chapter), copy expand.O2.s to "
                   "annotated.s, and add # comments explaining it.")
def _(ctx):
    p = ctx.project / "annotated.s"
    expect_true(p.is_file(), "annotated.s in the project directory", "missing")
    lines = p.read_text(errors="replace").splitlines()
    expect_true(any(re.match(r"\s*expand5:", l) for l in lines), "a `expand5:` label", "label not found")
    notes = [l for l in lines if l.lstrip().startswith("#") or re.search(r"\S\s+#\s*\S", l)]
    expect_true(len(notes) >= 8, "at least 8 lines with # annotations", f"{len(notes)}")
    insn = [l for l in lines if re.match(r"\s+(sll|srl|sra|or|and|andi|ori|jr|addiu|addu|lw|sw|move|nop)\b", l)]
    expect_true(len(insn) >= 3, "at least 3 real instruction lines (sll, srl, or, jr ...)", f"{len(insn)}",
                hint="annotated.s must still contain the compiler's instructions, not just prose.")


# ---- dynamic helpers --------------------------------------------------------------------
def direct(ctx):
    r = ctx.result
    r.require_break()
    cs = r.record("calls")
    expect_true(cs, "the probe recorded direct calls", "none", hint="main() must be reached.")
    return cs, r.record("seed")


def shot_color(r):
    img = r.screenshot()
    return img, tuple(round(v) for v in img.region_mean(0, 0, img.width, img.height))


def solid(img, rgb):
    expect_true(img.width >= 256 and img.height >= 200, "a picture of at least 256x200",
                f"{img.width}x{img.height}", hint="SetDefDispEnv(&disp, 0, 0, 320, 240).")
    expect_region(img, 0, 0, img.width, img.height, rgb, tol=10, min_fraction=0.99)


# ---- dynamic checks ---------------------------------------------------------------------
@check("program reaches stop_here() and the display is on",
       hint="A hang or crash before stop_here(). Run with -v.")
def _(ctx):
    r = ctx.result
    r.require_break()
    expect_true(r.frames < 300, "reached stop_here()", f"{r.frames} frames")


@check("direct calls return without clobbering saved registers",
       hint="expand5/rgb888_to_bgr555 are leaf routines: use only $t, $a, $v registers.")
def _(ctx):
    cs, seed = direct(ctx)
    for c in cs:
        expect_true(c["returned"], f"{c['fn']}(0x{c['a0']:X}) returns", "did not return (seed %s)" % seed)
        expect_true(not c["clobbered"], "callee-saved registers preserved",
                    f"{c['fn']} changed {','.join(c['clobbered'])} (seed {seed})")


@check("expand5(c) = c<<3 | c>>2 for every c in 0..31",
       hint="Widen a 5-bit channel: shift left 3 and copy the top 3 bits into the bottom 3.")
def _(ctx):
    cs, seed = direct(ctx)
    n = 0
    for c in cs:
        if c["fn"] != "expand5":
            continue
        n += 1
        expect_eq(c["v0"] & M, ch8(c["a0"]), f"expand5({c['a0']})", fmt="dec")
    expect_eq(n, 32, "expand5 calls recorded", fmt="dec")


@check("rgb888_to_bgr555 meets the Chapter 9 contract (direct calls)",
       hint="v0 = 0x0BBBBBGGGGGRRRRR; the low 3 bits of each channel dropped; the top byte of a0 ignored.")
def _(ctx):
    cs, seed = direct(ctx)
    n = 0
    for c in cs:
        if c["fn"] != "rgb888_to_bgr555":
            continue
        n += 1
        expect_eq(c["v0"] & M, ref_rgb(c["a0"]), f"rgb888_to_bgr555(0x{c['a0']:08X}) (seed {seed})", fmt="hex")
    expect_true(n >= 20, "rgb888_to_bgr555 direct calls", str(n))


def used_asm(ctx, name, value):
    r = ctx.result if name == "shipped" else ctx.run(name, patches=patch(value))
    r.require_break()
    ents = r.record("asm_calls")
    expect_true(ents, "main() calls rgb888_to_bgr555 at least once", "never called",
                hint="Compute the clear color with rgb888_to_bgr555; do not hard-code it.")
    return r, ents


def color_check(ctx, name):
    value = SHIPPED if COLORS[name] is None else COLORS[name]
    r, ents = used_asm(ctx, name, value)
    args = [e["a0"] & 0xFFFFFF for e in ents]
    expect_true(value in args, f"the routine is called with clear_rgb888 = 0x{value:06X}",
                ", ".join(f"0x{a:06X}" for a in args),
                hint="Pass the *current value* of clear_rgb888 to rgb888_to_bgr555 (read the variable at run time).")
    img = r.screenshot()
    solid(img, rgb_of_888(value))


@check("shipped color 0x00FF8040: asm called with it, screen is solid and the right color",
       hint="Clear color = expand5 of each field of the routine's result, via setRGB0 and isbg = 1.")
def _(ctx):
    color_check(ctx, "shipped")


@check("patched color 1: screen follows clear_rgb888",
       hint="A hard-coded color fails this: the verifier changes clear_rgb888 in the executable.")
def _(ctx):
    color_check(ctx, "teal")


@check("patched color 2: screen follows clear_rgb888",
       hint="A hard-coded color fails this: the verifier changes clear_rgb888 in the executable.")
def _(ctx):
    color_check(ctx, "gold")


@check("the screen uses the assembly routine's RESULT (verifier overwrites $v0 on return)",
       hint="Do not recompute the color in C and ignore the routine's return value. Use what it returns.")
def _(ctx):
    r = ctx.run("forced", patches=patch(SENTINEL))
    r.require_break()
    ents = r.record("asm_calls")
    expect_true(ents, "rgb888_to_bgr555 called", "never called")
    expect_true(any(e.get("forced") for e in ents), "the probe could override the return value",
                "the routine was never seen returning",
                hint="rgb888_to_bgr555 must return with `jr $ra` to its caller.")
    solid(r.screenshot(), rgb_of_bgr555(FORCE_BGR555))
