"""Chapter 17 checks: "Bouncing Gem" (animation: VBlank, double buffering, a moving shape).
Three emulator runs of 150 frames (OpenBIOS takes ~31 before `main`): the shipped initial state and two states the verifier patches into `gem_state`
(a hard-coded trajectory cannot pass). The probe records gem_state at the top of every frame-loop iteration (label `frame`),
at every emulated VBlank, and every GP0 E3h / GP1 05h write. Checks: exact motion and bounce rules, one iteration and one
display-start write per VBlank, alternating buffers (draw into the hidden one, then show it), and screenshots that agree
with gem_state (gem pixels at the reported centre, shading, bar-graph length)."""
from harness import *

R, XMIN, XMAX, YMIN, YMAX = 24, 24, 295, 24, 215
BAR_N, WARM = 60, 4   # WARM: loop iterations / VBlanks ignored after the program starts (a stale VBlank may flip once early)
BG, SIDE, TOP, BOT, BAR = (0x10, 0x18, 0x30), (0x20, 0xB0, 0xF0), (0xA0, 0xF0, 0xFF), (0x10, 0x40, 0xA0), (0xF0, 0xD0, 0x20)
SHOTS = {"a": 60, "b": 120}

config(
    title="Animation in Assembly: Bouncing Gem",
    main="main.s", exe="main.ps-exe", sym="main.sym",
    break_at=None, max_frames=150, shots=[("a", SHOTS["a"]), ("b", SHOTS["b"])],
)

# name -> initial gem_state words (x, y, vx, vy, frame, buf). "base" keeps the program's own values.
STATES = {
    "base": None,
    "p1": (250, 40, -5, 4, 0, 1),
    "p2": (30, 200, 7, -6, 0, 1),
}


def run(ctx, name):
    if name == "base":
        r = ctx.result
    else:
        r = ctx.run(name, patches={"gem_state": words(*STATES[name])})
    r.require_finished()
    if r.record("runaway"):
        raise CheckFailure(expected="about one frame-loop iteration per VBlank", actual=str(r.record("runaway")),
                           hint="Wait for VBlank (I_STAT bit 0) once per frame, and acknowledge it.")
    return r


def sg(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


def step(p, v, lo, hi):
    p += v
    if p < lo:
        p, v = lo, -v
    if p > hi:
        p, v = hi, -v
    return p, v


def trace(r):
    t = r.record("trace") or []
    if not t:
        raise CheckFailure(expected="the loop label `frame` is executed", actual="never",
                           hint="Keep a label named `frame` at the top of your frame loop.")
    return t


def bg_near(img, x, y):
    return all(abs(a - b) <= 16 for a, b in zip(img.pixel(x, y), BG))


@static_check("labels", hint="Keep the starter's labels: gem_state, frame, main, done.")
def _(ctx):
    ctx.require_symbols("gem_state", "frame", "main", "done")


@check("motion rules", hint="Each frame: position += velocity; outside [24,295] x [24,215] clamp to the edge and negate that velocity.")
def _(ctx):
    for name in STATES:
        t = trace(run(ctx, name))
        if len(t) < 60:
            raise CheckFailure(expected="at least 60 frames in 150 VBlanks", actual=f"{len(t)} loop iterations ({name})",
                               hint="Is the loop waiting for several VBlanks per frame, or stuck?")
        if STATES[name] is not None:
            expect_eq([sg(v) for v in t[0]], list(STATES[name]), f"gem_state at the first loop iteration ({name})",
                      hint="Do not overwrite the initial gem_state; the verifier patches it.")
        for n in range(len(t) - 1):
            x, y, vx, vy, f, b = [sg(v) for v in t[n]]
            nx, nvx = step(x, vx, XMIN, XMAX)
            ny, nvy = step(y, vy, YMIN, YMAX)
            got = [sg(v) for v in t[n + 1]]
            expect_eq(got[:4], [nx, ny, nvx, nvy], f"(x, y, vx, vy) after iteration {n + 1} from {(x, y, vx, vy)} ({name})",
                      hint="Move by the velocity, then clamp and reflect on each axis.")
            expect_eq(got[4:], [f + 1, b ^ 1], f"(frame, buf) after iteration {n + 1} ({name})",
                      hint="frame counts +1 per displayed frame; buf toggles 0/1 at every swap.")


@check("the gem bounces off every edge", hint="Velocity must change sign when the gem reaches an edge, and positions stay in bounds.")
def _(ctx):
    for name in STATES:
        t = [[sg(v) for v in row] for row in trace(run(ctx, name))]
        for row in t:
            expect_true(XMIN <= row[0] <= XMAX and YMIN <= row[1] <= YMAX, "x in 24..295, y in 24..215",
                        f"x={row[0]}, y={row[1]} ({name})", "Clamp the position at the edge.")
        flips_x = sum(1 for a, b in zip(t, t[1:]) if a[2] != b[2])
        flips_y = sum(1 for a, b in zip(t, t[1:]) if a[3] != b[3])
        expect_true(flips_x >= 1 and flips_y >= 1, "at least one bounce on each axis", f"{flips_x} on x, {flips_y} on y ({name})",
                    "Reflect both axes.")
        moved = sum(1 for a, b in zip(t, t[1:]) if (a[0], a[1]) != (b[0], b[1]))
        expect_eq(moved, len(t) - 1, f"frames in which the gem moved ({name})", hint="It must move every frame.")


@check("one update per VBlank", hint="Poll I_STAT bit 0 (IRQ0) once per frame and acknowledge it: write a 0 to that bit.")
def _(ctx):
    for name in STATES:
        r = run(ctx, name)
        s = r.record("samples")
        start = next((x[0] for x in s if x[1] > 0), 10**9)
        late = [x for x in s if x[0] >= start + WARM]
        pairs = list(zip(late, late[1:]))
        fast = [(a[0], a[1], b[1], a[6], b[6]) for a, b in pairs if b[1] - a[1] > 1 or b[6] - a[6] > 1]
        expect_true(not fast, "at most one frame-loop iteration and one frame-counter step per VBlank",
                    f"{len(fast)} VBlanks with more, e.g. (vsync, iter before, after, frame before, after) = {fast[:3]} ({name})",
                    "Too fast: no wait, or the I_STAT bit is never cleared (acknowledge it by writing 0 to bit 0).")
        missed = [a[0] for a, b in pairs if b[1] == a[1] or b[6] == a[6]]
        budget = max(2, len(pairs) // 20)
        expect_true(len(missed) <= budget, f"one frame per VBlank (an occasional missed VBlank is tolerated: at most {budget})",
                    f"{len(missed)} VBlanks without a new frame, e.g. at vsync {missed[:5]} ({name})",
                    "Too slow: the loop waits for more than one VBlank per frame (work too long, or waiting twice).")


def phases(r):
    """Per loop iteration n: the E3h and 05h writes {n: [(vsync, value)]}."""
    e3, d5 = {}, {}
    for it, vf, port, v in r.record("ev"):
        if it == 0:
            continue
        (e3 if port == 0 else d5).setdefault(it, []).append((vf, v))
    return e3, d5


@check("two framebuffers, swapped once per frame",
       hint="Draw into the hidden buffer (E3h drawing area at y = buf*240), then GP1 05h shows it. One 05h write per frame.")
def _(ctx):
    for name in STATES:
        r = run(ctx, name)
        t = trace(r)
        e3, d5 = phases(r)
        shown = []
        for n in range(WARM, len(t) - 1):
            it = n + 1
            expect_eq(len(d5.get(it, [])), 1, f"GP1 05h writes in loop iteration {it} ({name})",
                      hint="Change the display start exactly once per frame, after the frame is drawn.")
            want_y = 240 * (sg(t[n][5]) & 1)
            expect_true(len(e3.get(it, [])) >= 1, "a GP0 E3h (drawing area) write in every loop iteration",
                        f"none in iteration {it} ({name})", "Set the drawing area to the back buffer every frame.")
            e3ys = sorted({(v >> 10) & 0x3FF for _, v in e3[it]})
            e3y = e3ys[0] if len(e3ys) == 1 else e3ys
            d5v = d5[it][0][1]
            d5x, d5y = d5v & 0x3FF, (d5v >> 10) & 0x1FF
            expect_eq(e3y, want_y, f"drawing area top (every E3h y) in iteration {it}, gem_state.buf={sg(t[n][5])} ({name})",
                      hint="Draw into the back buffer: buf=0 is VRAM line 0, buf=1 is line 240.")
            expect_eq((d5x, d5y), (0, want_y), f"display start in iteration {it} = the buffer just drawn ({name})",
                      hint="GP1 05h: (y << 10) | x, with x = 0 and y = the line of the buffer you just drew.")
            shown.append(d5y)
        expect_true(set(shown) == {0, 240} and all(a != b for a, b in zip(shown, shown[1:])),
                    "display start alternating 0, 240, 0, 240", str(shown[:6]) + "...", "Swap buffers every frame.")


def centre_check(img, x, y, what):
    expect_pixel(img, x, y, SIDE, tol=24)
    expect_pixel(img, x, y - 18, tuple(int(a + 0.75 * (b - a)) for a, b in zip(SIDE, TOP)), tol=32)
    expect_pixel(img, x, y + 18, tuple(int(a + 0.75 * (b - a)) for a, b in zip(SIDE, BOT)), tol=32)
    expect_true(bg_near(img, x - R - 4, y), "background just left of the gem", str(img.pixel(x - R - 4, y)) + " " + what,
                "The back buffer must be cleared every frame.")


@check("screenshots show the gem where gem_state says",
       hint="The picture shown at VBlank k is the frame drawn from gem_state sampled at VBlank k-1: a Gouraud diamond at (x, y).")
def _(ctx):
    for name in STATES:
        r = run(ctx, name)
        s = {x[0]: x for x in r.record("samples")}
        centres = {}
        for tag, k in SHOTS.items():
            img = r.screenshot(tag)
            expect_eq((img.width, img.height), (320, 240), "screenshot size")
            st = s[k - 1]
            x, y, f = st[2], st[3], st[6]
            centres[tag] = (x, y)
            centre_check(img, x, y, f"(shot {tag}, gem_state x={x} y={y}, {name})")
            # bar graph: yellow run starting at x = 10 on row 8
            want = (f % BAR_N + 1) * 5
            n = 0
            while 10 + n < 320 and all(abs(a - b) <= 24 for a, b in zip(img.pixel(10 + n, 8), BAR)):
                n += 1
            expect_true(abs(n - want) <= 2, f"bar length {want} px for frame counter {f}", f"{n} px ({name}, shot {tag})",
                        "Bar width = ((frame % 60) + 1) * 5, drawn from x = 10 on rows 4..11.")
        (ax, ay), (bx, by) = centres["a"], centres["b"]
        expect_true(abs(ax - bx) + abs(ay - by) > 10, "the two screenshots show the gem in different places",
                    f"{centres}", "The gem must move.")
        # the gem of shot b must not be left over in shot a (no ghost / clear failure)
        img = r.screenshot("a")
        if abs(ax - bx) + abs(ay - by) > R + 6:
            expect_true(bg_near(img, bx, by), "shot a has no gem at shot b's position", str(img.pixel(bx, by)),
                        "Old gems are left behind: clear the whole back buffer each frame.")
