"""Chapter 19 checks: Double Buffering with Display and Draw Environments.
Build: CMake + PSn00bSDK. Three emulator runs of 130 frames (OpenBIOS takes ~32 before `main`): the shipped initial state and two states the
verifier patches into hue, hue_step and rect_x (frame_no is zero-initialized, in .bss, so not patchable), so a hard-coded color or trajectory cannot pass.
probe.lua records the state variables at every GP1 05h (display start) write and at every VBlank. Checks: the state follows the stated update
rules, the display start alternates 0 / 240 once per VBlank (one loop iteration per frame), and screenshots show a solid background of
exactly the color the hue state implies (sampled on a grid: a torn frame or a stale rectangle fails) with the white rectangle where
rect_x says."""
import re

from harness import *

HUE_RANGE, RECT_W, RECT_H, RECT_Y, RECT_MAX = 1536, 32, 32, 104, 288
SHOT_A, SHOT_B = 70, 100
config(
    title="Double Buffering with Display and Draw Environments",
    build="cmake", exe="game.exe", sym="", elf="game.elf",
    break_at=None, max_frames=130, shots=[("a", SHOT_A), ("b", SHOT_B)],
)

SHIPPED = {"frame_no": 0, "hue": 256, "hue_step": 12, "rect_x": 16}
# name -> patched initial values (None = the program's own)
STATES = {
    "base": None,
    "p1": {"hue": 900, "hue_step": 24, "rect_x": 150},
    "p2": {"hue": 1500, "hue_step": 40, "rect_x": 270},   # hue wraps; the rectangle wraps from 288 to 0
}


def ch8(c5): return (c5 << 3) | (c5 >> 2)


def hue_rgb(h):
    seg, f = h >> 8, h & 255
    c = [(255, f, 0), (255 - f, 255, 0), (0, 255, f), (0, 255 - f, 255), (f, 0, 255), (255, 0, 255 - f)][seg]
    return tuple(ch8(v >> 3) for v in c)       # what the GPU fill leaves in a 15-bit framebuffer


def run(ctx, name):
    if name == "base":
        r = ctx.result
    else:
        r = ctx.run(name, patches={k: v for k, v in STATES[name].items()})
    r.require_finished()
    if r.record("runaway"):
        raise CheckFailure(expected="one frame-loop iteration per VBlank", actual=str(r.record("runaway")),
                           hint="display_swap() must wait for VBlank: VSync(0).")
    return r


def init_state(name):
    s = dict(SHIPPED)
    s.update(STATES[name] or {})
    return s


def events(r):
    """05h writes made from inside display_swap() as dicts (display_init's write, if any, is dropped)."""
    ev = [dict(vf=e[0], n=e[1], hue=e[2], x=e[3], step=e[4], v=e[5]) for e in (r.record("ev") or []) if e[6] > 0]
    expect_true(len(ev) >= 40, "at least 40 display-start writes in 130 frames", str(len(ev)),
                hint="PutDispEnv (GP1 05h) must run once per frame; is display_swap() implemented, and is the display on?")
    return ev


@static_check("symbols", hint="Keep main and the four state variables from the starter; implement display_init, display_clear, display_swap.")
def _(ctx):
    ctx.require_symbols("main", "display_init", "display_clear", "display_swap", "frame_no", "hue", "hue_step", "rect_x")


@static_check("state variables start as shipped", hint="Do not edit the initial values; the verifier patches its own.")
def _(ctx):
    for k, want in SHIPPED.items():
        if k == "frame_no":
            continue        # zero-initialized: lives in .bss, not in the executable image
        off = ctx.symbols[k] - ctx.exe.load_addr
        expect_eq(int.from_bytes(ctx.exe.code[off:off + 4], "little"), want, f"initial {k}", fmt="dec")


@static_check("display.c uses the environment API", hint="See README 7.2: SetDefDispEnv/SetDefDrawEnv, PutDispEnv/PutDrawEnv, DrawSync, VSync, isbg.")
def _(ctx):
    txt = "".join(re.sub(r"/\*.*?\*/|//[^\n]*", "", f.read_text(errors="replace"), flags=re.S)
                  for f in ctx.source_files("**/display.c") if "build" not in f.parts)
    expect_true(txt, "a display.c in the project", "missing")
    for name in ("ResetGraph", "SetDefDispEnv", "SetDefDrawEnv", "PutDispEnv", "PutDrawEnv", "DrawSync", "VSync", "SetDispMask", "isbg"):
        expect_true(re.search(r"\b%s\b" % name, txt), f"`{name}` in display.c", "not found")


@check("state follows the update rules", hint="Per frame: frame_no+1, hue=(hue+hue_step)%1536, rect_x+1 (back to 0 after 288). The first frame shown uses the initial values.")
def _(ctx):
    for name in STATES:
        ev = events(run(ctx, name))
        want = init_state(name)
        first = ev[0]
        expect_eq((first["n"], first["hue"], first["x"], first["step"]),
                  (want["frame_no"], want["hue"], want["rect_x"], want["hue_step"]),
                  f"state when the first frame is shown ({name})",
                  hint="Draw with the initial values first, then advance after display_swap(). Do not overwrite the variables.")
        for a, b in zip(ev, ev[1:]):
            exp = (a["n"] + 1, (a["hue"] + a["step"]) % HUE_RANGE, 0 if a["x"] >= RECT_MAX else a["x"] + 1)
            expect_eq((b["n"], b["hue"], b["x"]), exp, f"(frame_no, hue, rect_x) after frame {a['n']} ({name})",
                      hint="advance(): use hue_step (not a constant) and wrap rect_x.")


@check("display start alternates (0,0) / (0,240), one write per VBlank",
       hint="Two framebuffers at VRAM y = 0 and 240. PutDispEnv once per frame, after VSync, showing the buffer just drawn.")
def _(ctx):
    for name in STATES:
        ev = events(run(ctx, name))
        ys = [((e["v"] >> 10) & 0x1FF, e["v"] & 0x3FF) for e in ev]
        expect_true(all(x == 0 for _, x in ys), "display start x = 0", str({x for _, x in ys}))
        seq = [y for y, _ in ys]
        expect_true(set(seq) == {0, 240}, "display start y takes the values 0 and 240", str(sorted(set(seq))),
                    "A single buffer never alternates: build two DISPENVs, at y = 0 and y = 240.")
        bad = [i for i, (a, b) in enumerate(zip(seq, seq[1:])) if a == b]
        expect_true(not bad, "y alternates at every write", f"{len(bad)} repeats, first after write {bad[:3]} ({name})",
                    "Flip the buffer index at every swap.")
        for e in ev:
            expect_eq((e["v"] >> 10) & 0x1FF, 240 * (e["n"] & 1), f"buffer shown for frame {e['n']} ({name})",
                      hint="Frame 0 is drawn into buffer 0 (y = 0), frame 1 into buffer 1 (y = 240), and so on.")


@check("one iteration per VBlank", hint="display_swap() must call VSync(0) exactly once per frame, and the frame must be drawn within one frame time.")
def _(ctx):
    for name in STATES:
        ev = events(run(ctx, name))
        gaps = [b["vf"] - a["vf"] for a, b in zip(ev, ev[1:])]
        bad = [(a["vf"], g) for a, g in zip(ev, gaps) if g != 1]
        expect_true(len(bad) <= 2, "consecutive display-start writes one VBlank apart (at most 2 irregular gaps tolerated)",
                    f"{len(bad)} irregular gaps (vsync, gap) {bad[:4]} ({name})",
                    "Gap 0: no VSync (loop runs faster than the display). Gap 2+: the frame took too long, or two VSyncs per frame.")


def state_shown(ev, k):
    """The frame on screen at the VBlank that ends emulated frame k-1: the last display-start write before frame k."""
    cand = [e for e in ev if e["vf"] < k]
    return cand[-1] if cand else None


def white_run(img, y):
    xs = [x for x in range(img.width) if all(abs(a - 255) <= 12 for a in img.pixel(x, y))]
    return (xs[0], len(xs)) if xs else (None, 0)


@check("screenshots: one solid background color (no tearing), the right hue, the rectangle where rect_x says",
       hint="Per shot: every sampled pixel outside the rectangle has the color hue_to_rgb(hue) gives; white 32x32 rectangle at (rect_x, 104).")
def _(ctx):
    for name in STATES:
        r = run(ctx, name)
        ev = events(r)
        shots = {}
        for tag, k in (("a", SHOT_A), ("b", SHOT_B)):
            img = r.screenshot(tag)
            expect_eq((img.width, img.height), (320, 240), "screenshot size", hint="Display 320x240.")
            st = state_shown(ev, k)
            bg = hue_rgb(st["hue"])
            what = f"(shot {tag}, {name}, frame_no={st['n']}, hue={st['hue']}, rect_x={st['x']})"
            bad = []
            for y in range(2, 240, 8):
                for x in range(2, 320, 8):
                    if st["x"] - 3 <= x <= st["x"] + RECT_W + 3 and RECT_Y - 3 <= y <= RECT_Y + RECT_H + 3:
                        continue
                    if any(abs(a - b) > 2 for a, b in zip(img.pixel(x, y), bg)):
                        bad.append((x, y, img.pixel(x, y)))
            expect_true(not bad, f"all {30 * 40} sampled background pixels = {bg}",
                        f"{len(bad)} differ, e.g. {bad[:3]} {what}",
                        "Several colors in one frame means tearing or a missing clear: clear the back buffer every frame "
                        "(isbg + PutDrawEnv) and swap only after VSync. A wrong color: check hue_to_rgb and the isbg clear.")
            left, n = white_run(img, RECT_Y + RECT_H // 2)
            expect_true(left is not None and abs(left - st["x"]) <= 1 and abs(n - RECT_W) <= 2,
                        f"white rectangle {RECT_W} wide starting at x = {st['x']}", f"left={left}, width={n} {what}",
                        "TILE at (rect_x, 104), 32x32, color 255,255,255, sent with DrawPrim after the clear.")
            expect_pixel(img, st["x"] + RECT_W // 2, RECT_Y + 2, (255, 255, 255), tol=12)
            expect_pixel(img, st["x"] + RECT_W // 2, RECT_Y + RECT_H - 3, (255, 255, 255), tol=12)
            shots[tag] = (st, bg, left)
        (sa, bga, la), (sb, bgb, lb) = shots["a"], shots["b"]
        expect_eq(sb["n"] - sa["n"], SHOT_B - SHOT_A, f"frames between the two screenshots ({name})",
                  hint="One frame per VBlank.")
        expect_true(max(abs(a - b) for a, b in zip(bga, bgb)) >= 16, "background color differs between the shots",
                    f"{bga} vs {bgb} ({name})", "The background must cycle: hue += hue_step every frame.")
        want = (sb["x"] - sa["x"])
        expect_true(abs((lb - la) - want) <= 1, f"rectangle moved {want} px between the shots ({name}; 1 px per frame)",
                    f"{lb - la} px", "rect_x += 1 per frame.")
        if name == "base":
            expect_eq(want, 30, "1 px per frame x 30 frames = 30 px", hint="Wrap-around must not happen here.")
