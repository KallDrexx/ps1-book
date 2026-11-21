"""Chapter 13 checks: the GPU, VRAM and command packets.
Phase 1 (probe.lua + tools/verify-lib/directcall.lua): gpu_init, gpu_clear and gpu_rect are called DIRECTLY with
random arguments (seed printed on failure), the 5th argument `h` on the stack, sentinels in the callee-saved
registers. The probe records, per call, every word written to GP0/GP1 (the transcript), the number of GPUSTAT reads
before the first GP0 word, and a diff of the whole 1024x512 VRAM. Checks compare both with what the hardware must do.
Phase 2: the real program runs on three color tables (the shipped one and two the verifier patches in), and the
screenshot is sampled. Hard-coded colors or a pre-baked picture cannot pass: VRAM is reachable only through GP0 and
the colors come from the patched tables."""
import struct

from harness import *

M = 0xFFFFFFFF
BARS, BAR_W, BAR_Y, BAR_H = 8, 40, 24, 192
SCREEN_W, SCREEN_H = 320, 240
BG = 0x202020
BAR_COLORS = [0xFFFFFF, 0xFFFF00, 0x00FFFF, 0x00FF00, 0xFF00FF, 0xFF0000, 0x0000FF, 0x808080]
SETS = {
    "shipped": (BG, BAR_COLORS),
    "alt1": (0x500000, [0x102030, 0xE0A010, 0x30C050, 0x7010B0, 0xF0F0F0, 0x00A0A0, 0xC03060, 0x404040]),
    "alt2": (0x003060, [0xFF8000, 0x80FF00, 0x0080FF, 0xFF0080, 0x00FF80, 0x8000FF, 0xFFFFFF, 0x000000][::-1]),
}
LABELS = ["main", "done", "gpu_init", "gpu_clear", "gpu_rect", "bg_color", "bar_colors"]

config(
    title="The GPU, VRAM, and Command Packets",
    main="main.s", exe="main.ps-exe", sym="main.sym",
    break_at="done", shots=["end"], max_frames=300,
)


def rgb(c): return ((c >> 16) & 255, (c >> 8) & 255, c & 255)
def raw555(c):
    r, g, b = rgb(c)
    return (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)
def bgr(c):
    r, g, b = rgb(c)
    return (b << 16) | (g << 8) | r


def patch(s):
    bg, bars = SETS[s]
    return {"bg_color": struct.pack("<I", bg), "bar_colors": struct.pack("<8I", *bars)}


def run_set(ctx, s):
    return ctx.result if s == "shipped" else ctx.run(s, patches=patch(s))


def calls_of(ctx, fn):
    r = ctx.result
    recs = [c for c in (r.record("calls") or []) if c["fn"] == fn]
    if not recs:
        r.require_finished()
        raise CheckFailure(expected=f"direct calls to {fn}", actual="none were made",
                           hint="Keep the labels main, gpu_init, gpu_clear and gpu_rect.")
    return recs


def seed(ctx): return f" (probe seed {ctx.result.record('seed')})"
def argtxt(c): return f"{c['fn']}(0x{c.get('a0', 0) & M:08X}, x={c.get('a1')}, y={c.get('a2')}, w={c.get('a3')}, h={c.get('h')})"


# ---- static ------------------------------------------------------------------------------------
@static_check("program defines main, done, gpu_init, gpu_clear, gpu_rect, bg_color and bar_colors",
              hint="Keep every label the starter declares; the verifier calls the routines by name and patches the two tables.")
def _(ctx):
    ctx.require_symbols(*LABELS)
    expect_true(ctx.symbols["bar_colors"] % 4 == 0 and ctx.symbols["bg_color"] % 4 == 0,
                "word-aligned color tables", "unaligned", hint="Put `.align 4` before the data.")


@static_check("armips reports no warnings", hint="Usually a load delay: a loaded register used by the very next instruction.")
def _(ctx):
    expect_true("warning" not in ctx.build_log.lower(), "no warnings", "armips printed a warning (run ./verify.sh -v)")


# ---- run / ABI -----------------------------------------------------------------------------------
@check("program reaches `done` without a CPU exception or hang",
       hint="An infinite loop or a crash stops the run; use -v to see the emulator log.")
def _(ctx):
    ctx.result.require_break()


@check("every direct call returns with $s0-$s7, $gp, $sp and $fp unchanged",
       hint="The routines are leaf routines: use only $t, $a and $v registers; do not touch $sp.")
def _(ctx):
    for c in ctx.result.record("calls"):
        exc = c.get("exception")
        expect_true(not exc, "no CPU exception", f"{argtxt(c)} raised {exc}", hint="Bad address or an alignment problem.")
        expect_true(c["returned"], f"{c['fn']} returns (jr $ra)", f"{argtxt(c)} did not return in 400 instructions",
                    hint="A wait loop that never ends? Test bit 26 of GPUSTAT, and branch while it is clear.")
        expect_true(not c["clobbered"], "callee-saved registers preserved",
                    f"{argtxt(c)} changed {', '.join(c['clobbered'])}")


# ---- gpu_init ----------------------------------------------------------------------------------
def init_log(ctx):
    return calls_of(ctx, "gpu_init")[0]["log"]


@check("gpu_init: GP1(00h) reset first, then display on, start (0,0), 2560x240 ranges, mode 320x240 NTSC 15-bit",
       hint="Sequence: GP1 00h reset, 03h on (bit 0 = 0), 05h start 0,0, 06h x2-x1 = 2560, 07h y2-y1 = 240, "
            "08h = 0x08000001. See the GP1 table in section 5.")
def _(ctx):
    gp1 = [v & M for p, v, o in init_log(ctx) if p == 1]
    expect_true(gp1 and gp1[0] == 0, "the first GP1 word is 0x00000000 (reset)", f"0x{gp1[0]:08X}" if gp1 else "no GP1 writes")
    last = {}
    for v in gp1:
        last[v >> 24] = v & 0xFFFFFF
    for cmd in (3, 5, 6, 7, 8):
        expect_true(cmd in last, f"a GP1({cmd:02X}h) word", "missing",
                    hint=f"gpu_init never writes GP1(0x{cmd:02X}) = 0x{cmd:02X}pppppp to 0x1F801814.")
    expect_eq(last[3] & 1, 0, "GP1(03h) bit 0 (0 = display enabled)", hint="03h with bit 0 set turns the display OFF.")
    expect_eq(last[5], 0, "GP1(05h) display start x | y<<10", hint="Show VRAM from (0,0).", fmt="hex")
    x1, x2 = last[6] & 0xFFF, last[6] >> 12
    expect_eq(x2 - x1, 2560, "horizontal range length x2-x1 (GPU clocks)",
              hint="320 pixels at 8 GPU clocks per pixel: 2560. Ch 1 uses 0x260..0xC60.")
    y1, y2 = last[7] & 0x3FF, last[7] >> 10
    expect_eq(y2 - y1, 240, "vertical range length y2-y1 (scanlines)", hint="240 lines, e.g. 16..256.")
    expect_eq(last[8], 0x000001, "GP1(08h) parameter: 320 wide, 240 high, NTSC, 15-bit, no interlace",
              hint="Bits 0-1 = 1 (320), bit 2 = 0 (240 lines), bit 3 = 0 (NTSC), bit 4 = 0 (15-bit), bit 5 = 0 (no interlace).",
              fmt="hex")


@check("gpu_init: draw mode E1h (bit 10 set), drawing area (0,0)-(319,239), drawing offset (0,0) with GP0 E3h/E4h/E5h",
       hint="GP0 E3h = 0xE3000000 | y<<10 | x (top-left); E4h the same for the bottom-right corner (inclusive); "
            "E5h = offset. Without them gpu_rect clips wrongly.")
def _(ctx):
    gp0 = [v & M for p, v, o in init_log(ctx) if p == 0]
    last = {}
    for v in gp0:
        last[v >> 24] = v & 0xFFFFFF
    for cmd in (0xE1, 0xE3, 0xE4, 0xE5):
        expect_true(cmd in last, f"a GP0({cmd:02X}h) word", "missing")
    expect_true(last[0xE1] & 0x400, "E1h bit 10 set (drawing to the display area allowed)", f"E1h parameter 0x{last[0xE1]:06X}",
                hint="0xE1000400: the libraries always allow drawing into the displayed area.")
    expect_eq(last[0xE3], 0, "E3h top-left", fmt="hex")
    expect_eq(last[0xE4], (239 << 10) | 319, "E4h bottom-right (239<<10 | 319)", fmt="hex",
              hint="The corner is inclusive: 319 and 239, not 320 and 240.")
    expect_eq(last[0xE5], 0, "E5h drawing offset", fmt="hex")


@check("the display is 320x240, 15 bits per pixel (screenshot of the real run)",
       hint="A different size means gpu_init's GP1(06h)/(07h)/(08h) words are wrong; check the vertical range and mode.")
def _(ctx):
    info = ctx.result.screenshot_info()
    img = ctx.result.screenshot()
    expect_eq((img.width, img.height), (SCREEN_W, SCREEN_H), "screenshot size")
    expect_eq(info.get("bpp"), 16, "bits per pixel")


# ---- the packets ---------------------------------------------------------------------------------
def expected_words(c, cmd):
    return [(cmd << 24) | bgr(c["a0"] & 0xFFFFFF), ((c["a2"] & 0xFFFF) << 16) | (c["a1"] & 0xFFFF),
            ((c["h"] & 0xFFFF) << 16) | (c["a3"] & 0xFFFF)]


def packet_check(ctx, fn, cmd):
    for c in calls_of(ctx, fn):
        if any(o != 0x2B for p, v, o in c["log"]):   # the probe decodes the value from an `sw` (opcode 2Bh) only
            raise CheckFailure(expected="every GPU port write is one `sw` of a whole word",
                               actual="a write with another instruction (sb/sh/swl/swr?)",
                               hint="GP0 and GP1 are 32-bit ports: build the word in a register and store it with sw.",
                               message=f"{argtxt(c)} wrote a GPU port without sw" + seed(ctx))
        got = [(p, v & M) for p, v, o in c["log"]]
        want = [(0, w) for w in expected_words(c, cmd)]
        if got != want:
            raise CheckFailure(
                expected="GP0 words " + ", ".join(f"0x{w:08X}" for _, w in want),
                actual=("GP0/GP1 words " + ", ".join(f"{'GP0' if p == 0 else 'GP1'}:0x{w:08X}" for p, w in got)) if got else "no writes to the GPU",
                hint=f"{fn} sends exactly three words to GP0: 0x{cmd:02X}BBGGRR, (y<<16)|x, (h<<16)|w. The color argument is "
                     f"0x00RRGGBB, so swap red and blue; h is the 5th argument at 16($sp).",
                message=f"{argtxt(c)} wrote the wrong packet" + seed(ctx))


@check("gpu_clear sends one GP0(02h) fill-rectangle packet with the right words",
       hint="Words: 0x02BBGGRR, y<<16|x, h<<16|w. Do not round w or x yourself: the GPU does.")
def _(ctx): packet_check(ctx, "gpu_clear", 0x02)


@check("gpu_rect sends one GP0(60h) monochrome-rectangle packet with the right words",
       hint="Words: 0x60BBGGRR, y<<16|x, h<<16|w.")
def _(ctx): packet_check(ctx, "gpu_rect", 0x60)


@check("gpu_init, gpu_clear and gpu_rect wait for GPUSTAT bit 26 before sending their first GP0 word",
       hint="Read 0x1F801814 (lw, then a nop for the load delay), test bit 26 (0x04000000), and loop while it is 0.")
def _(ctx):
    for fn in ("gpu_init", "gpu_clear", "gpu_rect"):
        for c in calls_of(ctx, fn):
            expect_true(c["reads_before_gp0"] >= 1, f"{fn} reads GPUSTAT (0x1F801814) before its first GP0 write",
                        f"it did not, in {argtxt(c)}")


# ---- the effect in VRAM -------------------------------------------------------------------------
def diff_check(ctx, fn, expected_rect):
    for c in calls_of(ctx, fn):
        x0, y0, x1, y1 = expected_rect(c)
        d = c["diff"]
        n_want = max(0, x1 - x0 + 1) * max(0, y1 - y0 + 1)
        want_val = raw555(c["a0"] & 0xFFFFFF)
        vals = [v & 0x7FFF for v in d["vals"]]
        if n_want == 0:
            expect_eq(d["n"], 0, f"pixels changed by {argtxt(c)}, which lies outside the drawing area",
                      hint="gpu_init must set the drawing area to (0,0)-(319,239); gpu_rect is clipped to it.")
            continue
        expect_true(d["n"] == n_want and (d["x0"], d["y0"], d["x1"], d["y1"]) == (x0, y0, x1, y1),
                    f"{argtxt(c)} changes exactly x {x0}..{x1}, y {y0}..{y1} ({n_want} pixels)",
                    f"{d['n']} pixels, x {d['x0']}..{d['x1']}, y {d['y0']}..{d['y1']}",
                    hint="Fill rectangle rounds x down and w up to multiples of 16; the monochrome rectangle is "
                         "pixel-exact and clipped to the drawing area." + seed(ctx))
        expect_true(vals == [want_val], f"every changed pixel = 0x{want_val:04X} (15-bit of 0x{c['a0'] & 0xFFFFFF:06X})",
                    ", ".join(f"0x{v:04X}" for v in vals), hint="Wrong color: red and blue swapped?" + seed(ctx))


@check("gpu_clear paints the 16-pixel-granular rectangle in VRAM, even outside the drawing area",
       hint="Widths like 20 become 32 and 1 becomes 16: that is the hardware, not a bug. The fill ignores the drawing area.")
def _(ctx):
    diff_check(ctx, "gpu_clear", lambda c: (c["a1"] & ~15, c["a2"], (c["a1"] & ~15) + ((c["a3"] + 15) & ~15) - 1, c["a2"] + c["h"] - 1))


@check("gpu_rect paints exactly its rectangle, clipped to the drawing area (0,0)-(319,239)",
       hint="gpu_init must set E3h/E4h; a rectangle half outside shows only its inside part, one fully outside shows nothing.")
def _(ctx):
    diff_check(ctx, "gpu_rect", lambda c: (c["a1"], c["a2"], min(c["a1"] + c["a3"] - 1, 319), min(c["a2"] + c["h"] - 1, 239)))


# ---- the real program ----------------------------------------------------------------------------
@check("the program calls gpu_init once, gpu_clear, and gpu_rect exactly 8 times",
       hint="main: gpu_init, one gpu_clear of the whole screen, then one gpu_rect per bar. The 40-pixel bars need gpu_rect.")
def _(ctx):
    e = ctx.result.record("entries") or {}
    expect_eq(e.get("gpu_init"), 1, "calls to gpu_init")
    expect_true((e.get("gpu_clear") or 0) >= 1, "at least one call to gpu_clear", str(e.get("gpu_clear")))
    expect_eq(e.get("gpu_rect"), BARS, "calls to gpu_rect")


def bar_check(ctx, name):
    bg, bars = SETS[name]
    r = run_set(ctx, name)
    r.require_break()
    img = r.screenshot()
    expect_eq((img.width, img.height), (SCREEN_W, SCREEN_H), "screenshot size")
    for i, col in enumerate(bars):
        expect_region(img, i * BAR_W, BAR_Y, BAR_W, BAR_H, rgb(col), tol=10, min_fraction=1.0,
                      what=f"bar {i} (x {i * BAR_W}..{i * BAR_W + BAR_W - 1}) in color table '{name}'",
                      hint="Bars are 40 px wide, y 24..215, in table order, left to right. The colors come from bar_colors in memory.")
    expect_region(img, 0, 0, SCREEN_W, BAR_Y, rgb(bg), tol=10, min_fraction=1.0, what="top border (y 0..23)",
                  hint="gpu_clear the whole 320x240 display with bg_color before the bars.")
    expect_region(img, 0, BAR_Y + BAR_H, SCREEN_W, SCREEN_H - BAR_Y - BAR_H, rgb(bg), tol=10, min_fraction=1.0,
                  what="bottom border (y 216..239)", hint="Same border color below the bars.")


@check("shipped colors: 8 bars of 40x192 at y=24 in table order, border in bg_color",
       hint="The table is bar_colors (0x00RRGGBB words). Bar i starts at x = 40*i.")
def _(ctx): bar_check(ctx, "shipped")


@check("patched color table 1: the picture follows the table, not constants in your code",
       hint="The verifier overwrites bar_colors and bg_color in the executable. Read them from memory with lw.")
def _(ctx): bar_check(ctx, "alt1")


@check("patched color table 2: same, with different colors",
       hint="As above. A hard-coded color in main shows up here.")
def _(ctx): bar_check(ctx, "alt2")


@check("the real run sends rectangles through GP0 only (>= 8 bar packets after init)",
       hint="VRAM is reachable only through the GP0 port.")
def _(ctx):
    log = ctx.result.record("phase2")["log"]
    rects = [v for p, v, o in log if p == 0 and (v & M) >> 24 == 0x60]
    expect_true(len(rects) >= BARS, f"at least {BARS} GP0(60h) command words", str(len(rects)))
