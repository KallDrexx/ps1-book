"""Chapter 15 checks: drawing subroutines and stack parameters ("Low-Poly Landscape").
Phase 1 (probe.lua + directcall.lua): draw_flat_tri (7 arguments), draw_flat_quad (9) and draw_gouraud_tri (9) are
called DIRECTLY, arguments 0-3 in $a0-$a3 and the rest at 16($sp), 20($sp), ... with junk around them. The probe records
every GP0/GP1 word each call writes, so the exact packet, the number of GPUSTAT reads and the ABI (exception, return,
$sp/$s0-$s7/$gp/$fp preserved) are checked per call.
Phase 2: the real program runs on three scenes: the one the reader ships in `scene`, read back from RAM, and two other
landscapes that the verifier writes over the table (different polygon counts, shapes, colours, vertex orders). The GP0
transcript must contain exactly the table's polygons, in order; the screenshot is sampled inside the polygons (the
topmost polygon at each point decides the expected colour; points near any edge are skipped) and on background points.
A hard-coded picture cannot pass: the table changes. Packets are compared by what the GPU draws (11-bit coordinates,
equivalent vertex orders accepted; see canonical())."""
import math
import random
import struct

from harness import *

M = 0xFFFFFFFF
SCREEN_W, SCREEN_H = 320, 240
TOL_FLAT, TOL_GOURAUD, TOL_BG = 10, 20, 10
MARGIN = 3.0            # pixels: samples closer than this to any polygon edge are skipped
SCENE_MAX = 64
T_FLAT_TRI, T_FLAT_QUAD, T_GOURAUD_TRI = 0, 1, 2
NVERTS = {T_FLAT_TRI: 3, T_FLAT_QUAD: 4, T_GOURAUD_TRI: 3}
CMD = {T_FLAT_TRI: 0x20, T_FLAT_QUAD: 0x28, T_GOURAUD_TRI: 0x30}
FN = {T_FLAT_TRI: "draw_flat_tri", T_FLAT_QUAD: "draw_flat_quad", T_GOURAUD_TRI: "draw_gouraud_tri"}
LEN = {0x20: 4, 0x28: 5, 0x30: 6, 0x38: 8, 0x02: 3, 0x60: 3}
LABELS = ["main", "done", "gpu_init", "gpu_clear", "draw_flat_tri", "draw_flat_quad", "draw_gouraud_tri", "scene"]

config(
    title="Drawing Subroutines and Stack Parameters: the Low-Poly Landscape",
    main="main.s", exe="main.ps-exe", sym="main.sym",
    break_at="done", shots=["end"], max_frames=300,
    reads={"tbl": ("scene", 8 + SCENE_MAX * 32)},
)


# ---- scene model ----------------------------------------------------------------------------------------------
def rgb(c): return ((c >> 16) & 255, (c >> 8) & 255, c & 255)
def bgr(c):
    r, g, b = rgb(c)
    return (b << 16) | (g << 8) | r
def vword(x, y): return ((y & 0xFFFF) << 16) | (x & 0xFFFF)
def s16(v): return (v & 0xFFFF) - 0x10000 if v & 0x8000 else v & 0xFFFF
def s32(v): return v - (1 << 32) if v & 0x80000000 else v


def decode_scene(words):
    """words: u32 list of the table as found in RAM -> dict(bg, entries) or raises CheckFailure."""
    count = words[0]
    expect_true(20 <= count <= SCENE_MAX, f"20 to {SCENE_MAX} polygons in the scene table", f"count word = {count}",
                hint="`scene` starts with the polygon count; the scene must have at least 20 polygons.")
    entries = []
    for i in range(count):
        w = words[2 + 8 * i: 10 + 8 * i]
        t = w[0]
        expect_true(t in NVERTS, f"scene entry {i}: type 0, 1 or 2", str(t), hint="Types: 0 flat triangle, 1 flat quad, 2 Gouraud triangle.")
        verts = [(s16(v & 0xFFFF), s16(v >> 16)) for v in w[4:4 + NVERTS[t]]]
        entries.append(dict(type=t, cols=[c & 0xFFFFFF for c in w[1:4]], verts=verts))
    return dict(bg=words[1] & 0xFFFFFF, entries=entries)


def encode_scene(sc):
    out = [len(sc["entries"]), sc["bg"]]
    for e in sc["entries"]:
        vs = [vword(x, y) for x, y in e["verts"]] + [0] * (4 - len(e["verts"]))
        out += [e["type"]] + e["cols"] + [0] * (3 - len(e["cols"])) + vs
    return b"".join(struct.pack("<I", w & M) for w in out)


def gen_scene(seed, n, bg):
    """A deterministic pseudo-random landscape: n polygons of the three types, inside the screen, any winding."""
    rng = random.Random(seed)
    entries = []
    def colour(): return (rng.randrange(0x20, 0xE0) << 16) | (rng.randrange(0x20, 0xE0) << 8) | rng.randrange(0x20, 0xE0)
    for i in range(n):
        t = [T_FLAT_TRI, T_FLAT_QUAD, T_GOURAUD_TRI, T_FLAT_TRI, T_GOURAUD_TRI][rng.randrange(5)]
        cx, cy = rng.randrange(50, 270), rng.randrange(50, 190)
        if t == T_FLAT_QUAD:                       # a trapezoid: always convex, vertices in Z order
            h, w0, w1, sh = rng.randrange(14, 32), rng.randrange(12, 36), rng.randrange(12, 36), rng.randrange(-8, 9)
            verts = [(cx - w0, cy - h), (cx + w0, cy - h), (cx - w1 + sh, cy + h), (cx + w1 + sh, cy + h)]
        else:
            a0 = rng.uniform(0, 6.28)
            verts = []
            for k in range(3):
                a = a0 + k * 2.0944 + rng.uniform(-0.4, 0.4)
                r = rng.uniform(16, 42)
                verts.append((int(round(cx + r * math.cos(a))), int(round(cy + r * math.sin(a)))))
            if rng.random() < 0.5:
                verts.reverse()                    # the other winding
        entries.append(dict(type=t, cols=[colour(), colour(), colour()] if t == T_GOURAUD_TRI else [colour(), 0, 0], verts=verts))
    return dict(bg=bg, entries=entries)


EXTRA = {"alt1": gen_scene(15, 26, 0x182848), "alt2": gen_scene(2024, 20, 0xD8C890)}
SCENES = ["shipped", "alt1", "alt2"]


def get_scene(ctx, name):
    if name == "shipped":
        r = ctx.result
        r.require_finished()
        return decode_scene(r.words("tbl", 2 + SCENE_MAX * 8))
    return EXTRA[name]


def run_scene(ctx, name):
    r = ctx.result if name == "shipped" else ctx.run(name, patches={"scene": encode_scene(EXTRA[name])})
    r.require_break()
    return r


def expected_packet(e):
    t, c, v = e["type"], e["cols"], e["verts"]
    cmd = CMD[t]
    if t == T_GOURAUD_TRI:
        words = []
        for i in range(3):
            words += [((cmd << 24) if i == 0 else 0) | bgr(c[i]), vword(*v[i])]
        return cmd, words
    return cmd, [(cmd << 24) | bgr(c[0])] + [vword(*p) for p in v]


# ---- packets ---------------------------------------------------------------------------------------------------
def s11(v):
    v &= 0x7FF
    return v - 0x800 if v & 0x400 else v


def canonical(cmd, words):
    """What the GPU draws from a packet, independent of equivalent choices: coordinates are the sign-extended low 11
    bits of each half (x & 0x7FF and x & 0xFFFF are both fine), a triangle's vertices may come in any order and a
    quad's in any order that keeps the same diagonal (v2-v3). Gouraud colour words after the first must have 00 on
    top. Returns None for a malformed packet."""
    if cmd not in LEN or len(words) != LEN[cmd]:
        return None
    if cmd & 0x10:
        cols, verts = words[0::2], words[1::2]
        if any(c >> 24 for c in cols[1:]):
            return None
        cols = [c & 0xFFFFFF for c in cols]
    else:
        verts = words[1:]
        cols = [words[0] & 0xFFFFFF] * len(verts)
    pts = [(c, s11(v), s11(v >> 16)) for c, v in zip(cols, verts)]
    if len(pts) == 3:
        return tuple(sorted(pts))
    return (tuple(sorted((pts[0], pts[3]))), tuple(sorted((pts[1], pts[2]))))


def parse_gp0(log):
    """Split the GP0 words into packets: (command, [words], gpustat_reads_before_the_first_word)."""
    words = [(v & M, rd) for p, v, o, rd in log if p == 0]
    out, i = [], 0
    while i < len(words):
        w, rd = words[i]
        cmd = w >> 24
        n = LEN.get(cmd, 1)
        out.append((cmd, [x for x, _ in words[i:i + n]], rd))
        i += n
    return out


def hexs(ws): return ", ".join(f"0x{w & M:08X}" for w in ws)


# ---- direct calls -----------------------------------------------------------------------------------------------
def seed(ctx): return f" (probe seed {ctx.result.record('seed')})"


def calls_of(ctx, fn):
    r = ctx.result
    recs = [c for c in (r.record("calls") or []) if c["fn"] == fn]
    if not recs:
        r.require_finished()
        raise CheckFailure(expected=f"direct calls to {fn}", actual="none were made", hint="Keep the labels main and " + fn + ".")
    return recs


def call_text(c):
    a = c["args"]
    if c["fn"] == "draw_gouraud_tri":
        return f"draw_gouraud_tri(0x{a[0]:06X},{s32(a[1])},{s32(a[2])}, 0x{a[3]:06X},{s32(a[4])},{s32(a[5])}, 0x{a[6]:06X},{s32(a[7])},{s32(a[8])})"
    return f"{c['fn']}(0x{a[0]:06X}, " + ", ".join(str(s32(v)) for v in a[1:]) + ")"


def expected_call(c):
    a = c["args"]
    if c["fn"] == "draw_gouraud_tri":
        cols = [a[0], a[3], a[6]]
        verts = [(s32(a[1]), s32(a[2])), (s32(a[4]), s32(a[5])), (s32(a[7]), s32(a[8]))]
        words = []
        for i in range(3):
            words += [((0x30 << 24) if i == 0 else 0) | bgr(cols[i] & 0xFFFFFF), vword(*verts[i])]
        return 0x30, words
    cmd = 0x20 if c["fn"] == "draw_flat_tri" else 0x28
    verts = [(s32(a[i]), s32(a[i + 1])) for i in range(1, len(a), 2)]
    return cmd, [(cmd << 24) | bgr(a[0] & 0xFFFFFF)] + [vword(*p) for p in verts]


def gp0_of(c): return [(v & M, rd) for p, v, o, rd in c["words"] if p == 0]


def packet_call_check(ctx, fn, nstack):
    for c in calls_of(ctx, fn):
        txt = call_text(c)
        expect_true(not c.get("exception"), "no CPU exception", f"{txt} raised {c.get('exception')}")
        expect_true(c["returned"], "the routine returns (jr $ra)", f"{txt} did not return within 600 instructions")
        expect_true(not [1 for p, *_ in c["words"] if p == 1], f"{txt}: no GP1 writes", "a GP1 (control) word was written",
                    hint="A drawing routine sends only GP0 words.")
        cmd, want = expected_call(c)
        got = gp0_of(c)
        expect_true(got, f"{txt}: GP0 words " + hexs(want), "no word was written to GP0", hint="Send the packet to 0x1F801810.")
        ok = len(got) == len(want) and got[0][0] >> 24 == cmd and canonical(cmd, [w for w, _ in got]) == canonical(cmd, want)
        expect_true(ok, f"{txt}: exactly one packet = " + hexs(want) + " (or an equivalent vertex order)",
                    hexs([w for w, _ in got]),
                    hint=f"Arguments 0-3 are in $a0-$a3, the other {nstack} at 16($sp), 20($sp), ... as the CALLER's $sp sees them: "
                         "after you move $sp, add the frame size. A wrong offset reads junk." + seed(ctx))


@check("draw_flat_tri(color, x0,y0, x1,y1, x2,y2) sends one 20h packet: 4 words from 7 arguments (3 on the stack)",
       hint="Words: 0x20BBGGRR, v0, v1, v2. y1, x2, y2 are at 16, 20, 24 ($sp at entry).")
def _(ctx): packet_call_check(ctx, "draw_flat_tri", 3)


@check("draw_flat_quad(color, x0,y0 ... x3,y3) sends one 28h packet: 5 words from 9 arguments (5 on the stack)",
       hint="Words: 0x28BBGGRR, v0, v1, v2, v3. y1, x2, y2, x3, y3 are at 16, 20, 24, 28, 32 ($sp at entry).")
def _(ctx): packet_call_check(ctx, "draw_flat_quad", 5)


@check("draw_gouraud_tri(c0,x0,y0, c1,x1,y1, c2,x2,y2) sends one 30h packet: 6 words from 9 arguments (5 on the stack)",
       hint="Words: 0x30BBGGRR, v0, 0x00BBGGRR, v1, 0x00BBGGRR, v2. x1, y1, c2, x2, y2 are at 16..32 ($sp at entry); c1 is $a3.")
def _(ctx): packet_call_check(ctx, "draw_gouraud_tri", 5)


@check("ABI: every routine returns with $sp, $s0-$s7, $gp and $fp unchanged",
       hint="Save every $s register you use (and $ra if you call anything) in your frame and restore all of them and $sp before jr $ra.")
def _(ctx):
    for fn in FN.values():
        for c in calls_of(ctx, fn):
            expect_true(not c.get("exception"), "no CPU exception", f"{call_text(c)} raised {c.get('exception')}")
            expect_true(c["returned"], "the routine returns", f"{call_text(c)} did not return in 600 instructions")
            expect_true(not c["clobbered"], f"{call_text(c)}: callee-saved registers preserved",
                        "changed " + ", ".join(c["clobbered"]), hint="$s0-$s7, $gp, $fp and $sp belong to the caller." + seed(ctx))


@check("one GPU wait per packet: GPUSTAT is read before the first word and never between the words of a packet",
       hint="Wait once at the top of the routine (lw 0x1F801814, test bit 26, loop), then send all the words without waiting again.")
def _(ctx):
    for fn in FN.values():
        for c in calls_of(ctx, fn):
            g = gp0_of(c)
            if not g:
                continue
            txt = call_text(c)
            expect_true(g[0][1] > c["r0"], f"{txt}: a GPUSTAT read before the first word", "none")
            expect_true(len({rd for _, rd in g}) == 1, f"{txt}: no GPUSTAT read between the words of the packet",
                        f"{max(rd for _, rd in g) - g[0][1]} extra read(s) inside the packet",
                        hint="Bit 26 means \"ready for a new command\": wait once per packet, before its first word.")


# ---- static ----------------------------------------------------------------------------------------------------
@static_check("program defines main, done, gpu_init, gpu_clear, the three draw routines and the `scene` table",
              hint="Keep every label the starter declares; the verifier calls the routines by name and patches `scene`.")
def _(ctx):
    ctx.require_symbols(*LABELS)
    expect_true(ctx.symbols["scene"] % 4 == 0, "scene word-aligned", "unaligned", hint="Put `.align 4` before the data.")


@static_check("armips reports no warnings", hint="Usually a load delay: a loaded register used by the very next instruction.")
def _(ctx):
    expect_true("warning" not in ctx.build_log.lower(), "no warnings", "armips printed a warning (run ./verify.sh -v)")


@check("program reaches `done` without a CPU exception or hang",
       hint="An infinite loop or a crash stops the run; use -v to see the emulator log.")
def _(ctx):
    ctx.result.require_break()


# ---- geometry --------------------------------------------------------------------------------------------------
def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:                 # a repeated vertex (a degenerate edge)
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def outline(e):
    v = e["verts"]
    return [v[0], v[1], v[3], v[2]] if len(v) == 4 else list(v)


def classify(p, e):
    """'in' / 'out' when p is at least MARGIN pixels from every edge of the polygon, else None (too close to call)."""
    o = outline(e)
    n = len(o)
    d = min(seg_dist(p, o[i], o[(i + 1) % n]) for i in range(n))
    if d < MARGIN:
        return None
    s = [(o[(i + 1) % n][0] - o[i][0]) * (p[1] - o[i][1]) - (o[(i + 1) % n][1] - o[i][1]) * (p[0] - o[i][0]) for i in range(n)]
    return "in" if all(x > 0 for x in s) or all(x < 0 for x in s) else "out"


def bary(p, t):
    (x1, y1), (x2, y2), (x3, y3) = t
    det = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    l1 = ((y2 - y3) * (p[0] - x3) + (x3 - x2) * (p[1] - y3)) / det
    l2 = ((y3 - y1) * (p[0] - x3) + (x1 - x3) * (p[1] - y3)) / det
    return (l1, l2, 1 - l1 - l2)


WEIGHTS = [(0.8, 0.1, 0.1), (0.1, 0.8, 0.1), (0.1, 0.1, 0.8), (1 / 3, 1 / 3, 1 / 3), (0.45, 0.45, 0.10),
           (0.45, 0.10, 0.45), (0.10, 0.45, 0.45)]


def colour_at(e, p):
    if e["type"] == T_GOURAUD_TRI:
        w = bary(p, e["verts"])
        return tuple(sum(rgb(c)[i] * k for c, k in zip(e["cols"], w)) for i in range(3)), TOL_GOURAUD
    return rgb(e["cols"][0]), TOL_FLAT


def samples(sc):
    """[(x, y, expected rgb, tolerance, what)]: interior points of every polygon, where the polygon is topmost."""
    es = sc["entries"]
    out = []
    for i, e in enumerate(es):
        v = e["verts"]
        tris = [(v[0], v[1], v[2])] + ([(v[1], v[2], v[3])] if len(v) == 4 else [])
        for ti, tri in enumerate(tris):
            if (tri[1][0] - tri[0][0]) * (tri[2][1] - tri[0][1]) == (tri[2][0] - tri[0][0]) * (tri[1][1] - tri[0][1]):
                continue                    # zero area: nothing to sample (and no barycentric coordinates)
            for w in WEIGHTS:
                p = (sum(q[0] * k for q, k in zip(tri, w)), sum(q[1] * k for q, k in zip(tri, w)))
                p = (round(p[0]), round(p[1]))
                if not (0 <= p[0] < SCREEN_W and 0 <= p[1] < SCREEN_H):
                    continue
                cls = [classify(p, f) for f in es]
                if cls[i] != "in" or any(c is None for c in cls[i + 1:]):
                    continue
                top = max(j for j in range(i, len(es)) if cls[j] == "in")
                col, tol = colour_at(es[top], p)
                out.append((p[0], p[1], tuple(int(round(c)) for c in col), tol, f"polygon {top}, point ({p[0]},{p[1]})"))
    return out


# ---- the scene runs --------------------------------------------------------------------------------------------
@check("the scene table has at least 20 polygons of valid types (shipped table, read back from RAM)",
       hint="`scene`: count word, background colour, then 8-word entries (type, 3 colours, 4 packed vertices).")
def _(ctx):
    sc = get_scene(ctx, "shipped")
    expect_true(len(sc["entries"]) >= 20, "at least 20 polygons", str(len(sc["entries"])))


@check("the program sends the table's polygons to the GPU, in table order and nothing else polygon-shaped (3 scenes)",
       hint="Walk the table from the count word: for each entry call the routine its type names. The verifier writes two "
            "different landscapes over `scene`, so the count, shapes and colours must all come from the table.")
def _(ctx):
    for name in SCENES:
        sc = get_scene(ctx, name)
        r = run_scene(ctx, name)
        log = r.record("gpu")
        if log is None:
            r.require_finished()
            raise CheckFailure(expected="a GPU transcript from the probe", actual="none", hint="Keep the label `done`.")
        pk = [(c, w) for c, w, rd in parse_gp0(log) if c in (0x20, 0x28, 0x30, 0x38)]
        want = [expected_packet(e) for e in sc["entries"]]
        expect_eq(len(pk), len(want), f"scene '{name}': number of polygon packets", hint="One packet per table entry; the count word says how many.")
        for i, ((c, w), (wc, ww)) in enumerate(zip(pk, want)):
            expect_true(c == wc and canonical(c, w) == canonical(wc, ww),
                        f"scene '{name}', polygon {i} (type {sc['entries'][i]['type']}): " + hexs(ww) + " (or an equivalent vertex order)",
                        hexs(w), hint="Wrong type dispatch, colours, vertices (unpack the signed 16-bit halves) or order.")


@check("every routine is called for the entries of its type (a flat triangle by draw_flat_tri, ...)",
       hint="Do the drawing through the three routines, not inline code in main.")
def _(ctx):
    for name in SCENES:
        sc = get_scene(ctx, name)
        r = run_scene(ctx, name)
        ent = r.record("entries") or {}
        for t, fn in FN.items():
            n = sum(1 for e in sc["entries"] if e["type"] == t)
            expect_true(ent.get(fn, 0) >= n, f"scene '{name}': {fn} entered at least {n} times", str(ent.get(fn, 0)),
                        hint="main must call the routine for each entry of that type.")


@check("the picture: inside every polygon the colour is the polygon's (interpolated for Gouraud), where it is topmost",
       hint="Sampled points inside each polygon, at least 3 px from every edge, compared with the topmost polygon there.")
def _(ctx):
    for name in SCENES:
        sc = get_scene(ctx, name)
        r = run_scene(ctx, name)
        img = r.screenshot()
        expect_eq((img.width, img.height), (SCREEN_W, SCREEN_H), "screenshot size")
        pts = samples(sc)
        expect_true(len(pts) >= len(sc["entries"]), f"scene '{name}': enough interior samples", str(len(pts)),
                    hint="The polygons are too small or too hidden to sample; make them bigger.")
        for x, y, exp, tol, what in pts:
            expect_pixel(img, x, y, exp, tol=tol, what=f"scene '{name}': {what}", hint="Wrong polygon, colour, position or draw order.")


@check("background untouched: pixels away from every polygon are the table's background colour, in every scene",
       hint="gpu_clear the whole screen with the table's background colour first; polygons must not spill.")
def _(ctx):
    for name in SCENES:
        sc = get_scene(ctx, name)
        r = run_scene(ctx, name)
        img = r.screenshot()
        n = 0
        for y in range(2, SCREEN_H, 6):
            for x in range(2, SCREEN_W, 6):
                if any(classify((x, y), e) != "out" for e in sc["entries"]):
                    continue
                n += 1
                expect_pixel(img, x, y, rgb(sc["bg"]), tol=TOL_BG, what=f"scene '{name}': background pixel ({x},{y})",
                             hint="Something was drawn here (or the screen was not cleared with the table's colour).")
        expect_true(n > 100, f"scene '{name}': enough background samples", str(n))
