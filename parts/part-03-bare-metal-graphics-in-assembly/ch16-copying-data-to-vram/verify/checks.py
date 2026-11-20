"""Chapter 16 checks: copying data to VRAM ("Picture Show").
Phase 1 (probe.lua + directcall.lua): bpp24_halfwords and vram_upload(ptr, x, y, w, h) are called DIRECTLY with harness-chosen
arguments (odd widths, odd pixel counts, the right and bottom edges, h at 16($sp)). The probe records the GPU transcript and
compares VRAM itself: the rectangle must equal the RAM buffer, nothing outside it may change.
Phase 2: the real program runs in both modes on the shipped images and on images the verifier patches in (random pixels, other
size/placement of the 16-bpp image), so hard-coded pictures cannot pass. VRAM is compared with the image bytes read back from
RAM; the screenshot is compared pixel by pixel (the 24-bpp screenshot is bytes R,G,B: confirmed in this chapter)."""
import random

from harness import *

M = 0xFFFFFFFF
BG = 0x303038
BG555 = ((0x30 >> 3) | ((0x30 >> 3) << 5) | ((0x38 >> 3) << 10))
IMG16_BYTES, IMG24_BYTES = 96 * 64 * 2, 320 * 240 * 3
LABELS = ["main", "done", "vram_upload", "bpp24_halfwords", "gpu_init", "gpu_clear", "mode", "img16", "img16_x", "img16_y",
          "img16_w", "img16_h", "img24", "img24_w", "img24_h"]

config(
    title="Copying Data to VRAM: Picture Show",
    main="main.s", exe="main.ps-exe", sym="main.sym",
    break_at="done", shots=["end"], max_frames=300, vram=True,
    reads={"img16": ("img16", IMG16_BYTES), "img24": ("img24", IMG24_BYTES), "mode": ("mode", 4),
           "x": ("img16_x", 4), "y": ("img16_y", 4), "w": ("img16_w", 4), "h": ("img16_h", 4)},
)

rng = random.Random(1616)
RAND16 = bytes(rng.randrange(256) for _ in range(IMG16_BYTES))
RAND24 = bytes(rng.randrange(256) for _ in range(IMG24_BYTES))
# name -> patches. Run "m0b": a 128x48 picture at (170,180) -> other size and place, random pixels (bit 15 random too).
RUNS = {
    "m0": {},
    "m0b": {"img16": RAND16, "img16_x": 170, "img16_y": 180, "img16_w": 128, "img16_h": 48},
    "m1": {"mode": 1},
    "m1b": {"mode": 1, "img24": RAND24},
}


def run(ctx, name):
    r = ctx.result if name == "m0" else ctx.run(name, patches=RUNS[name])
    r.require_break()
    return r


def s32(v): return v - (1 << 32) if v & 0x80000000 else v
def hexs(ws): return ", ".join(f"0x{w & M:08X}" for w in ws)
def seed(ctx): return f" (probe seed {ctx.result.record('seed')})"
def units(c): return c["w"] * c["h"]
def want_words(c): return (units(c) + 1) // 2


# ---- direct calls ----------------------------------------------------------------------------------------------
def calls_of(ctx, fn):
    r = ctx.result
    recs = [c for c in (r.record("calls") or []) if c["fn"] == fn]
    if not recs:
        r.require_finished()
        raise CheckFailure(expected=f"direct calls to {fn}", actual="none were made",
                           hint=f"Keep the labels main and {fn}.")
    return recs


def ctext(c): return f"vram_upload(ptr, x={c['x']}, y={c['y']}, w={c['w']}, h={c['h']})"


def uploads(ctx):
    out = calls_of(ctx, "vram_upload")
    for c in out:
        expect_true(not c.get("exception"), "no CPU exception", f"{ctext(c)} raised {c.get('exception')}")
        expect_true(c["returned"], "the routine returns (jr $ra)",
                    f"{ctext(c)} did not return within {c['limit']} instructions",
                    hint="A loop that never ends? Inside the data phase GPUSTAT bit 26 reads 0, so waiting for it per word "
                         "hangs forever. Wait once before the packet." + seed(ctx))
    return out


def gp0_plain(c): return [e[1] & M for e in c["log"] if e[0] == 0]
def data_info(c): return [e for e in c["log"] if e[0] == 2]


@check("vram_upload sends ONE packet: A0h, destination (y << 16 | x), size (h << 16 | w), then exactly ceil(w*h / 2) data words",
       hint="Three header words, then the pixels, two per word. One word too many would be read as a new command; one too few "
            "leaves the GPU waiting for data, and the next packet becomes pixels.")
def _(ctx):
    for c in uploads(ctx):
        t = ctext(c)
        expect_true(not [e for e in c["log"] if e[0] == 1], f"{t}: no GP1 writes", "a GP1 (control) word was written",
                    hint="vram_upload only talks to GP0.")
        g = gp0_plain(c)
        expect_true(len(g) == 3, f"{t}: three header words before the data (A0h, dest, size)", f"{len(g)} non-data GP0 words: {hexs(g)}")
        expect_eq(g[0] >> 24, 0xA0, f"{t}: command byte", fmt="hex", hint="GP0 A0h = copy rectangle CPU -> VRAM.")
        expect_eq(g[1], (c["y"] << 16) | c["x"], f"{t}: destination word", fmt="hex", hint="Destination = y << 16 | x." + seed(ctx))
        expect_eq(g[2], (c["h"] << 16) | c["w"], f"{t}: size word", fmt="hex", hint="Size = h << 16 | w (h is on the stack)." + seed(ctx))
        di = data_info(c)
        n = di[0][1] if di else c["ndata"]
        expect_eq(n, want_words(c), f"{t}: number of data words (w*h = {units(c)} pixels, two per word, rounded up)",
                  hint="words = (w*h + 1) >> 1." + seed(ctx))
        expect_eq(c["pending"], 0, f"{t}: data words still missing", hint="Send every word of the rectangle.")


@check("the rectangle in VRAM equals the RAM buffer exactly, pixel for pixel (two pixels per word, low half = left pixel)",
       hint="Compare with the buffer at ptr: pixel i of the row-major image goes to column i mod w, row i div w.")
def _(ctx):
    for c in uploads(ctx):
        if c["bad"]:
            fb = c["first_bad"]
            raise CheckFailure(expected=f"{ctext(c)}: all {units(c)} pixels equal the buffer",
                               actual=f"{c['bad']} pixel(s) differ; first at VRAM ({fb[0]},{fb[1]}): got 0x{fb[2]:04X}, want 0x{fb[3]:04X}",
                               hint="Odd width or odd pixel count? Row-major order, no padding between rows." + seed(ctx))


@check("nothing outside the rectangle changes: no extra words, no wrong destination (odd sizes, right and bottom edges)",
       hint="Pixels outside x..x+w-1, y..y+h-1 must keep their old value.")
def _(ctx):
    for c in uploads(ctx):
        if c["outside"]:
            fo = c["first_outside"]
            raise CheckFailure(expected=f"{ctext(c)}: no pixel outside the rectangle changes",
                               actual=f"{c['outside']} changed; first at VRAM ({fo[0]},{fo[1]}): 0x{fo[2]:04X} -> 0x{fo[3]:04X}",
                               hint="Wrong x/y in the destination word, or too many data words." + seed(ctx))


@check("vram_upload waits for GPUSTAT bit 26 before its first word",
       hint="Read 0x1F801814 and wait for bit 26 once, then send the three header words and the data without polling again.")
def _(ctx):
    for c in uploads(ctx):
        first = next((e for e in c["log"] if e[0] == 0), None)
        expect_true(first is not None and first[2] > c["r0"], f"{ctext(c)}: a GPUSTAT read before the first word", "none")


@check("ABI: vram_upload returns with $sp, $s0-$s7, $gp and $fp unchanged (h is read from 16($sp))",
       hint="Save every $s register you use in a frame and restore it, and $sp, before jr $ra. h is argument 4: 16($sp) at entry.")
def _(ctx):
    for fn in ("vram_upload", "bpp24_halfwords"):
        for c in calls_of(ctx, fn):
            t = ctext(c) if fn == "vram_upload" else f"bpp24_halfwords({c['px']})"
            expect_true(not c.get("exception"), "no CPU exception", f"{t} raised {c.get('exception')}")
            expect_true(c["returned"], "the routine returns", f"{t} did not return")
            expect_true(not c["clobbered"], f"{t}: callee-saved registers preserved", "changed " + ", ".join(c["clobbered"]),
                        hint="$s0-$s7, $gp, $fp and $sp belong to the caller." + seed(ctx))


@check("bpp24_halfwords(px) = px * 3 / 2 (a 24-bpp line of px pixels is that many 16-bit VRAM units; px even)",
       hint="3 bytes per pixel = 1.5 units: px + (px >> 1). 320 pixels -> 480 units.")
def _(ctx):
    for c in calls_of(ctx, "bpp24_halfwords"):
        expect_eq(c["v0"], c["px"] * 3 // 2, f"bpp24_halfwords({c['px']})", hint="Return px + (px >> 1) in $v0." + seed(ctx))


# ---- static ----------------------------------------------------------------------------------------------------
@static_check("program defines main, done, vram_upload, bpp24_halfwords and the data labels the verifier patches",
              hint="Keep every label the starter declares: the verifier calls the routines by name and patches mode, the sizes and the images.")
def _(ctx):
    ctx.require_symbols(*LABELS)
    for n in ("img16", "img24"):
        expect_true(ctx.symbols[n] % 4 == 0, f"{n} word-aligned", "unaligned", hint="Put `.align 4` before `.incbin`.")


@static_check("armips reports no warnings", hint="Usually a load delay: a loaded register used by the very next instruction.")
def _(ctx):
    expect_true("warning" not in ctx.build_log.lower(), "no warnings", "armips printed a warning (run ./verify.sh -v)")


@static_check("bpp24_halfwords uses shifts and adds only (no mult/div)",
              hint="px * 3 / 2 = px + (px >> 1): Chapter 12's strength reduction.")
def _(ctx):
    start = ctx.symbols["bpp24_halfwords"]
    insns = [i for i in ctx.disassemble() if i.addr >= start]
    body = []
    for k, i in enumerate(insns[:40]):
        body.append(i)
        if mnemonic(i) in ("jr", "j", "jal"):
            body.append(insns[k + 1])
            break
    bad = [i.text for i in body if mnemonic(i) in ("mult", "multu", "div", "divu", "mflo", "mfhi")]
    expect_true(not bad, "no multiply/divide instruction in bpp24_halfwords", ", ".join(bad))


@check("program reaches `done` without a CPU exception or hang",
       hint="An infinite loop or a crash stops the run; use -v to see the emulator log. A wait on bit 26 inside the data phase never ends.")
def _(ctx):
    ctx.result.require_break()


# ---- real runs -------------------------------------------------------------------------------------------------
def packets(r):
    """The recorded GP0 transcript split into packets: list of (command, [header words], n_data_words)."""
    log = r.record("gpu")
    if log is None:
        r.require_finished()
        raise CheckFailure(expected="a GPU transcript from the probe", actual="none", hint="Keep the label `done`.")
    out, i = [], 0
    while i < len(log):
        port, v, rd = log[i]
        if port == 1:
            i += 1
            continue
        if port == 2:
            out[-1][2] = v
            i += 1
            continue
        cmd = (v & M) >> 24
        n = 3 if cmd in (0xA0, 0x02, 0xC0) else 1
        words = [e[1] & M for e in log[i:i + n] if e[0] == 0]
        out.append([cmd, words, 0])
        i += len(words)
    return out


def gp1_words(r): return [e[1] & M for e in (r.record("gpu") or []) if e[0] == 1]


def a0_packets(r): return [p for p in packets(r) if p[0] == 0xA0]


def screen_image(r):
    img = r.screenshot()
    expect_eq((img.width, img.height), (320, 240), "screenshot size", hint="320x240: GP1(08h), the ranges from gpu_init.")
    return img


@check("part 1: the 16-bpp picture arrives in VRAM exactly (shipped image, then another size, position and random pixels)",
       hint="Read x, y, w, h from img16_x/y/w/h and pass them to vram_upload; the picture is img16 (w*h pixels).")
def _(ctx):
    for name in ("m0", "m0b"):
        r = run(ctx, name)
        x, y, w, h = r.u32("x"), r.u32("y"), r.u32("w"), r.u32("h")
        pk = a0_packets(r)
        expect_eq(len(pk), 1, f"run {name}: number of A0h packets in the whole program", hint="One upload for the picture.")
        cmd, hw, nd = pk[0]
        expect_eq(hw[1:], [(y << 16) | x, (h << 16) | w], f"run {name}: destination and size words", fmt="hex",
                  hint="Use the table values (the verifier patches them), not constants.")
        expect_eq(nd, (w * h + 1) // 2, f"run {name}: data words")
        r.vram().expect_rect(x, y, w, h, r.mem("img16")[:w * h * 2],
                             hint=f"run {name}: VRAM rect ({x},{y}) {w}x{h} must equal the bytes at img16 (patched: random pixels).")


@check("part 1: the screen shows the picture at its place on a 0x303038 background (display 320x240, 15-bit)",
       hint="gpu_clear the whole 320x240 area with 0x303038 first, then upload; the display stays in 15-bit mode.")
def _(ctx):
    for name in ("m0", "m0b"):
        r = run(ctx, name)
        x, y, w, h = r.u32("x"), r.u32("y"), r.u32("w"), r.u32("h")
        img = screen_image(r)
        expect_eq(r.data["shots"]["end"]["bpp"], 16, f"run {name}: screenshot colour depth", hint="Part 1 stays in 15-bit mode.")
        src = r.mem("img16")
        for j in range(h):
            for i in range(w):
                v = src[2 * (j * w + i)] | (src[2 * (j * w + i) + 1] << 8)
                expect_pixel(img, x + i, y + j, rgb_from_bgr555(v), tol=8, what=f"run {name}: picture pixel ({i},{j}) at screen ({x + i},{y + j})",
                             hint="Flipped, shifted, or the display start/mode is not the one gpu_init set up.")
        vr = r.vram()
        for yy in range(0, 240, 3):
            for xx in range(0, 320, 3):
                if x <= xx < x + w and y <= yy < y + h:
                    continue
                expect_eq(vr.raw(xx, yy), BG555, f"run {name}: background pixel ({xx},{yy})", fmt="hex",
                          hint="gpu_clear(0x303038, 0, 0, 320, 240) before the upload; the upload must not spill.")


@check("part 2: the display is switched to 24-bit colour: GP1(08h) with bit 4 set, still 320x240 NTSC",
       hint="GP1 08h value 0x08000011: bits 0-1 = 1 (320 wide), bit 2 = 0 (240 high), bit 3 = 0 (NTSC), bit 4 = 1 (24-bit).")
def _(ctx):
    for name in ("m1", "m1b"):
        r = run(ctx, name)
        modes = [w for w in gp1_words(r) if w >> 24 == 0x08]
        expect_true(modes, f"run {name}: a GP1(08h) display-mode write", "none")
        expect_eq(modes[-1] & 0x7F, 0x11, f"run {name}: last GP1(08h) value (low 7 bits)", fmt="hex")
        expect_eq(r.data["shots"]["end"]["bpp"], 24, f"run {name}: the emulator shows a 24-bit display")


@check("part 2: one upload of the whole picture: A0h at (0,0), size 480 x 240 (units!), 57600 data words, and VRAM equals img24 exactly",
       hint="A 320-pixel line is 480 16-bit units: compute it with bpp24_halfwords and upload w=480. The rectangle width is in VRAM units, "
            "not pixels.")
def _(ctx):
    for name in ("m1", "m1b"):
        r = run(ctx, name)
        calls = (r.record("entries") or {}).get("bpp24_halfwords", 0)
        expect_true(calls >= 1, f"run {name}: main calls bpp24_halfwords(img24_w) for the width in units",
                    "main never called it (a hard-coded 480?)", hint="jal bpp24_halfwords with $a0 = img24_w; use $v0 as w.")
        pk = a0_packets(r)
        expect_eq(len(pk), 1, f"run {name}: number of A0h packets", hint="Upload the 24-bit picture with a single vram_upload.")
        cmd, hw, nd = pk[0]
        expect_eq(hw[1:], [0, (240 << 16) | 480], f"run {name}: destination and size words", fmt="hex",
                  hint="Destination (0,0); size 480 | 240 << 16.")
        expect_eq(nd, 57600, f"run {name}: data words (480 * 240 / 2)")
        r.vram().expect_rect(0, 0, 480, 240, r.mem("img24"),
                             hint=f"run {name}: the 24-bit bytes must land in VRAM unchanged.")


@check("part 2: the screenshot is the picture (bytes R, G, B), at every pixel, also for random pixels",
       hint="In 24-bit mode VRAM is read as bytes R,G,B per pixel, first byte of the line = red of pixel 0.")
def _(ctx):
    for name in ("m1", "m1b"):
        r = run(ctx, name)
        img = screen_image(r)
        src = r.mem("img24")
        for j in range(240):
            for i in range(320):
                o = 3 * (j * 320 + i)
                expect_pixel(img, i, j, (src[o], src[o + 1], src[o + 2]), tol=2, what=f"run {name}: pixel ({i},{j})",
                             hint="Wrong width in units (480), wrong row order or the display is not in 24-bit mode.")
