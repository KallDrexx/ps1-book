"""Chapter 14 checks: rendering polygons (the "Polygon Gallery").
Phase 1 (probe.lua + directcall.lua): pack_color and pack_vertex are called DIRECTLY with random arguments.
Phase 2: the real program runs on three galleries: the shipped one and two that the verifier patches into the data
tables (new origin, colours and vertices; one with reversed triangle winding). The probe logs every GP0/GP1 word, so
the polygon packets (command byte, word count, exact words) are checked; the screenshot is sampled at flat centroids,
at Gouraud sample points whose colour is interpolated from the vertex colours, and on background points.
Hard-coded pictures or constants cannot pass: VRAM is reachable only through GP0 and everything comes from the tables.
Packets are compared by what the GPU draws (11-bit coordinates, equivalent vertex orders accepted; see canonical()).
Dither is OFF in the book's draw mode; the tolerances (flat 10, Gouraud 20) also cover dithered output."""
import struct

from harness import *

M = 0xFFFFFFFF
SCREEN_W, SCREEN_H = 320, 240
TOL_FLAT, TOL_GOURAUD, TOL_BG = 10, 20, 10
LABELS = ["main", "done", "gpu_init", "gpu_clear", "pack_color", "pack_vertex",
          "origin", "bg_color", "flat_tri", "flat_quad", "gouraud_tri", "gouraud_quad"]

# Each set: origin, background, flat_tri (colour, [v1,v2,v3]), flat_quad (colour, [v1..v4]),
#           gouraud_tri [(colour, v)] x3, gouraud_quad [(colour, v)] x4. Vertices are (x, y) relative to the origin.
SETS = {
    "shipped": dict(
        origin=(160, 120), bg=0x181830,
        ft=(0xFFA000, [(-90, -100), (-30, -20), (-150, -20)]),
        fq=(0x20C0A0, [(30, -100), (140, -90), (20, -20), (130, -15)]),
        gt=[(0xFF0000, (-90, 10)), (0x00FF00, (-30, 95)), (0x0000FF, (-150, 95))],
        gq=[(0xFF0000, (30, 10)), (0xFFFF00, (140, 10)), (0x0000FF, (30, 95)), (0xFFFFFF, (140, 95))]),
    "alt1": dict(      # same places, other colours, the triangles' vertex order reversed
        origin=(160, 120), bg=0x602010,
        ft=(0x40FF40, [(-90, -100), (-150, -20), (-30, -20)]),
        fq=(0xE02080, [(30, -100), (140, -90), (20, -20), (130, -15)]),
        gt=[(0x00FFFF, (-90, 10)), (0xFF00FF, (-150, 95)), (0xFFFF00, (-30, 95))],
        gq=[(0x000000, (30, 10)), (0xFF8000, (140, 10)), (0x8000FF, (30, 95)), (0x00FF80, (140, 95))]),
    "alt2": dict(      # moved origin, skewed quads, another triangle winding
        origin=(166, 122), bg=0x002840,
        ft=(0x8080FF, [(-90, -100), (-30, -20), (-150, -20)]),
        fq=(0xFFFF80, [(28, -98), (138, -100), (26, -22), (140, -14)]),
        gt=[(0xFF8000, (-90, 10)), (0x0080FF, (-30, 95)), (0x80FF00, (-150, 95))],
        gq=[(0xFF0000, (30, 12)), (0x00FF00, (130, 6)), (0x0000FF, (24, 92)), (0xFFFFFF, (136, 98))]),
}

config(
    title="Rendering Polygons: the Polygon Gallery",
    main="main.s", exe="main.ps-exe", sym="main.sym",
    break_at="done", shots=["end"], max_frames=300,
)


def rgb(c): return ((c >> 16) & 255, (c >> 8) & 255, c & 255)
def bgr(c):
    r, g, b = rgb(c)
    return (b << 16) | (g << 8) | r
def vword(v): return ((v[1] & 0xFFFF) << 16) | (v[0] & 0xFFFF)
def s32(v): return struct.pack("<i", v)


def patch(s):
    g = SETS[s]
    ft_c, ft_v = g["ft"]
    fq_c, fq_v = g["fq"]
    return {
        "origin": s32(g["origin"][0]) + s32(g["origin"][1]),
        "bg_color": s32(g["bg"]),
        "flat_tri": s32(ft_c) + b"".join(s32(a) + s32(b) for a, b in ft_v),
        "flat_quad": s32(fq_c) + b"".join(s32(a) + s32(b) for a, b in fq_v),
        "gouraud_tri": b"".join(s32(c) + s32(v[0]) + s32(v[1]) for c, v in g["gt"]),
        "gouraud_quad": b"".join(s32(c) + s32(v[0]) + s32(v[1]) for c, v in g["gq"]),
    }


def run_set(ctx, s):
    r = ctx.result if s == "shipped" else ctx.run(s, patches=patch(s))
    r.require_break()
    return r


def expected_packets(g):
    """cmd -> expected GP0 words (colours as BBGGRR in the command word)."""
    ft_c, ft_v = g["ft"]
    fq_c, fq_v = g["fq"]
    out = {
        0x20: [(0x20 << 24) | bgr(ft_c)] + [vword(v) for v in ft_v],
        0x28: [(0x28 << 24) | bgr(fq_c)] + [vword(v) for v in fq_v],
    }
    for cmd, key in ((0x30, "gt"), (0x38, "gq")):
        words = []
        for i, (c, v) in enumerate(g[key]):
            words += [((cmd << 24) if i == 0 else 0) | bgr(c), vword(v)]
        out[cmd] = words
    return out


LEN = {0x20: 4, 0x28: 5, 0x30: 6, 0x38: 8, 0x02: 3, 0x60: 3}


def parse_gp0(log):
    """Split the GP0 words into packets: (command, [words], gpustat_reads_before_the_first_word).
    Unknown commands count as single words (E1h-E5h are single words anyway)."""
    words = [(v & M, rd) for p, v, o, rd in log if p == 0]
    out, i = [], 0
    while i < len(words):
        w, rd = words[i]
        cmd = w >> 24
        n = LEN.get(cmd, 1)
        out.append((cmd, [x for x, _ in words[i:i + n]], rd))
        i += n
    return out


def packets_of(r):
    log = r.record("gpu")
    if log is None:
        r.require_finished()
        raise CheckFailure(expected="a GPU transcript from the probe", actual="none", hint="Keep the label `done`.")
    return parse_gp0(log)


# ---- geometry (all in screen pixels) -----------------------------------------------------------------
def to_screen(g, v): return (g["origin"][0] + v[0], g["origin"][1] + v[1])
def lerp_pt(pts, w): return (sum(p[0] * k for p, k in zip(pts, w)), sum(p[1] * k for p, k in zip(pts, w)))
def lerp_col(cols, w): return tuple(sum(rgb(c)[i] * k for c, k in zip(cols, w)) for i in range(3))


def seg_dist(p, a, b):
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    return ((p[0] - ax - t * dx) ** 2 + (p[1] - ay - t * dy) ** 2) ** 0.5


def tri_dist(p, t):
    """0 if p is inside the triangle, else the distance to it."""
    a, b, c = t
    def side(u, v): return (v[0] - u[0]) * (p[1] - u[1]) - (v[1] - u[1]) * (p[0] - u[0])
    s = [side(a, b), side(b, c), side(c, a)]
    if all(x >= 0 for x in s) or all(x <= 0 for x in s):
        return 0.0
    return min(seg_dist(p, a, b), seg_dist(p, b, c), seg_dist(p, c, a))


def triangles(g):
    """Screen triangles with their vertex colours (None for flat ones)."""
    S = lambda v: to_screen(g, v)
    ft = [S(v) for v in g["ft"][1]]
    fq = [S(v) for v in g["fq"][1]]
    gt = [S(v) for _, v in g["gt"]]
    gq = [S(v) for _, v in g["gq"]]
    gtc = [c for c, _ in g["gt"]]
    gqc = [c for c, _ in g["gq"]]
    return dict(ft=[(ft, None)], fq=[((fq[0], fq[1], fq[2]), None), ((fq[1], fq[2], fq[3]), None)],
                gt=[(gt, gtc)], gq=[((gq[0], gq[1], gq[2]), gqc[0:3]), ((gq[1], gq[2], gq[3]), gqc[1:4])])


# Sample weights: near each vertex, in the middle, and between two vertices (never closer than 0.1 to an edge).
WEIGHTS = [(0.8, 0.1, 0.1), (0.1, 0.8, 0.1), (0.1, 0.1, 0.8), (1 / 3, 1 / 3, 1 / 3), (0.45, 0.45, 0.10),
           (0.45, 0.10, 0.45), (0.10, 0.45, 0.45)]


def samples(g, key):
    """[(x, y, expected rgb, what)] for the polygon `key`."""
    out = []
    flat_col = {"ft": g["ft"][0], "fq": g["fq"][0]}
    for ti, (tri, cols) in enumerate(triangles(g)[key]):
        for wi, w in enumerate(WEIGHTS):
            x, y = lerp_pt(tri, w)
            if cols is None:
                if wi != 3:
                    continue                      # flat polygons: the centroid of each triangle
                exp = rgb(flat_col[key])
            else:
                exp = lerp_col(cols, w)
            out.append((int(round(x)), int(round(y)), tuple(int(round(e)) for e in exp),
                        f"triangle {ti + 1}, weights " + "/".join(f"{k:.2f}" for k in w)))
    return out


def pixel_check(ctx, key, tol, hint):
    for s in SETS:
        r = run_set(ctx, s)
        img = r.screenshot()
        expect_eq((img.width, img.height), (SCREEN_W, SCREEN_H), "screenshot size")
        g = SETS[s]
        for x, y, exp, what in samples(g, key):
            expect_pixel(img, x, y, exp, tol=tol, what=f"gallery '{s}': {what}, pixel ({x},{y})", hint=hint)


# ---- static ----------------------------------------------------------------------------------------
@static_check("program defines main, done, gpu_init, gpu_clear, pack_color, pack_vertex and the five data tables",
              hint="Keep every label the starter declares; the verifier calls pack_color/pack_vertex by name and patches the tables.")
def _(ctx):
    ctx.require_symbols(*LABELS)
    for n in ("origin", "bg_color", "flat_tri", "flat_quad", "gouraud_tri", "gouraud_quad"):
        expect_true(ctx.symbols[n] % 4 == 0, f"{n} word-aligned", "unaligned", hint="Put `.align 4` before the data.")


@static_check("armips reports no warnings", hint="Usually a load delay: a loaded register used by the very next instruction.")
def _(ctx):
    expect_true("warning" not in ctx.build_log.lower(), "no warnings", "armips printed a warning (run ./verify.sh -v)")


# ---- run / ABI ---------------------------------------------------------------------------------------
@check("program reaches `done` without a CPU exception or hang",
       hint="An infinite loop or a crash stops the run; use -v to see the emulator log.")
def _(ctx):
    ctx.result.require_break()


def seed(ctx): return f" (probe seed {ctx.result.record('seed')})"


def calls_of(ctx, fn):
    r = ctx.result
    recs = [c for c in (r.record("calls") or []) if c["fn"] == fn]
    if not recs:
        r.require_finished()
        raise CheckFailure(expected=f"direct calls to {fn}", actual="none were made", hint="Keep the labels main, pack_color and pack_vertex.")
    return recs


def abi_ok(c, txt):
    exc = c.get("exception")
    expect_true(not exc, "no CPU exception", f"{txt} raised {exc}")
    expect_true(c["returned"], "the routine returns (jr $ra)", f"{txt} did not return in 200 instructions")
    expect_true(not c["clobbered"], "callee-saved registers preserved", f"{txt} changed {', '.join(c['clobbered'])}",
                hint="Both routines are leaf routines: use only $t, $a and $v registers.")


@check("pack_color(color, cmd) returns (cmd << 24) | 0x00BBGGRR, ignoring the colour's top byte",
       hint="Swap red and blue of 0x00RRGGBB, then OR in the command byte shifted left by 24. Result in $v0.")
def _(ctx):
    for c in calls_of(ctx, "pack_color"):
        a0, a1 = c["a0"] & M, c["a1"] & M
        txt = f"pack_color(0x{a0:08X}, 0x{a1:02X})"
        abi_ok(c, txt)
        want = ((a1 & 0xFF) << 24) | bgr(a0 & 0xFFFFFF)
        expect_eq(c["v0"] & M, want, f"{txt} in $v0", fmt="hex", hint="Bits 31-24 of the colour must not leak into the result." + seed(ctx))


@check("pack_vertex(x, y) returns (y << 16) | (x & 0xFFFF), also for negative x and y",
       hint="Mask x to 16 bits before OR-ing: a negative x is sign-extended in its register and would overwrite y.")
def _(ctx):
    for c in calls_of(ctx, "pack_vertex"):
        x, y = (c["a0"] + (1 << 31)) % (1 << 32) - (1 << 31), (c["a1"] + (1 << 31)) % (1 << 32) - (1 << 31)
        txt = f"pack_vertex({x}, {y})"
        abi_ok(c, txt)
        expect_eq(c["v0"] & M, ((y & 0xFFFF) << 16) | (x & 0xFFFF), f"{txt} in $v0", fmt="hex", hint="" + seed(ctx))


# ---- the packets ---------------------------------------------------------------------------------------
@check("the drawing offset: GP0(E5h) with the origin (signed 11-bit x, y << 11) is sent before the first polygon, in every gallery",
       hint="E5h word = 0xE5000000 | ((y & 0x7FF) << 11) | (x & 0x7FF), from the `origin` table (the verifier moves it).")
def _(ctx):
    for s in SETS:
        r = run_set(ctx, s)
        pk = packets_of(r)
        first = next((i for i, (cmd, w, rd) in enumerate(pk) if cmd in (0x20, 0x28, 0x30, 0x38)), None)
        expect_true(first is not None, "polygon packets in the transcript", "none (no 20h/28h/30h/38h command word)")
        offs = [w[0] & 0xFFFFFF for cmd, w, rd in pk[:first] if cmd == 0xE5]
        ox, oy = SETS[s]["origin"]
        want = ((oy & 0x7FF) << 11) | (ox & 0x7FF)
        expect_true(offs and offs[-1] == want, f"gallery '{s}': last E5h before the first polygon = 0x{want:06X} (origin {ox},{oy})",
                    f"0x{offs[-1]:06X}" if offs else "no E5h word",
                    hint="gpu_init resets the offset to 0; set it again from `origin` after it. The polygon words hold the table's (relative) coordinates.")


def s11(v):
    v &= 0x7FF
    return v - 0x800 if v & 0x400 else v


def canonical(cmd, words):
    """What the GPU actually draws from a packet, independent of equivalent choices: vertex coordinates are the
    sign-extended low 11 bits of each half (so x & 0x7FF and x & 0xFFFF are both fine), a triangle's vertices may come
    in any order, and a quad's in any order that keeps the same diagonal (v2-v3). Gouraud colour words after the
    first must have 00 on top. Returns None for a malformed packet."""
    if len(words) != LEN[cmd]:
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


def packet_check(ctx, cmd, label, nwords, hint):
    for s in SETS:
        r = run_set(ctx, s)
        want = expected_packets(SETS[s])[cmd]
        found = [w for c, w, rd in packets_of(r) if c == cmd]
        expect_true(found, f"gallery '{s}': a GP0 packet with command 0x{cmd:02X} ({label}, {nwords} words)",
                    "none sent", hint=hint)
        ok = canonical(cmd, want) in [canonical(cmd, f) for f in found]
        expect_true(ok, f"gallery '{s}': the {label} packet = " + ", ".join(f"0x{w:08X}" for w in want)
                    + " (or an equivalent vertex order)",
                    " | ".join(", ".join(f"0x{w:08X}" for w in f) for f in found), hint=hint)


@check("flat triangle: GP0 20h, 4 words (colour, v1, v2, v3)",
       hint="Words: 0x20BBGGRR, then one (y<<16)|(x&0xFFFF) word per vertex, in table order.")
def _(ctx): packet_check(ctx, 0x20, "flat triangle", 4, "Words: 0x20BBGGRR, v1, v2, v3.")


@check("flat quad: GP0 28h, 5 words (colour, v1, v2, v3, v4)",
       hint="Words: 0x28BBGGRR, v1, v2, v3, v4 (Z order).")
def _(ctx): packet_check(ctx, 0x28, "flat quad", 5, "Words: 0x28BBGGRR, v1, v2, v3, v4 (Z order).")


@check("Gouraud triangle: GP0 30h, 6 words (c1, v1, c2, v2, c3, v3)",
       hint="Only the FIRST colour word carries the command byte: 0x30BBGGRR, v1, 0x00BBGGRR, v2, 0x00BBGGRR, v3.")
def _(ctx): packet_check(ctx, 0x30, "Gouraud triangle", 6, "Only the first colour word carries the command: 0x30BBGGRR, v1, 0x00BBGGRR, v2, 0x00BBGGRR, v3.")


@check("Gouraud quad: GP0 38h, 8 words (c1, v1, c2, v2, c3, v3, c4, v4)",
       hint="Only the FIRST colour word carries the command byte: 0x38BBGGRR, v1, c2, v2, c3, v3, c4, v4.")
def _(ctx): packet_check(ctx, 0x38, "Gouraud quad", 8, "Only the first colour word carries the command: 0x38BBGGRR, v1, c2, v2, c3, v3, c4, v4.")


@check("each polygon packet is preceded by a read of GPUSTAT (wait for bit 26)",
       hint="Call a wait routine (lw 0x1F801814, nop, test bit 26, loop) before the first word of every polygon packet.")
def _(ctx):
    pk = packets_of(run_set(ctx, "shipped"))
    prev = -1
    for cmd, w, rd in pk:
        if cmd in (0x20, 0x28, 0x30, 0x38):
            expect_true(rd > prev, f"a GPUSTAT read before the 0x{cmd:02X} packet", "none since the previous packet")
        prev = rd


# ---- the picture -----------------------------------------------------------------------------------------
@check("flat triangle and flat quad: the centroid of each (triangle) is the polygon's colour, whatever the winding",
       hint="One colour in the whole polygon. Gallery 'alt1' reverses the triangle's vertex order: the GPU draws both windings.")
def _(ctx):
    pixel_check(ctx, "ft", TOL_FLAT, "Flat triangle missing or wrong colour here.")
    pixel_check(ctx, "fq", TOL_FLAT, "Flat quad missing or wrong colour here; vertices in Z order v1 v2 / v3 v4.")


@check("Gouraud triangle: near each vertex, at the centre and between vertices, the colour is the interpolated one",
       hint="Three colour words, one per vertex. A flat colour or the wrong vertex/colour pairing fails here.")
def _(ctx): pixel_check(ctx, "gt", TOL_GOURAUD, "Gouraud triangle: colour does not match the interpolation of the vertex colours.")


@check("Gouraud quad: interpolated colours inside both of its triangles (v1 v2 v3 and v2 v3 v4)",
       hint="Four colour/vertex pairs in Z order: v1 v2 / v3 v4. Swapping v3 and v4 draws a different shape.")
def _(ctx): pixel_check(ctx, "gq", TOL_GOURAUD, "Gouraud quad: wrong colour; check the vertex order and the colour words.")


@check("background untouched: every pixel away from the polygons is bg_color, in every gallery",
       hint="gpu_clear the whole screen with bg_color first; polygons must not spill (watch the drawing offset and the vertex words).")
def _(ctx):
    for s in SETS:
        r = run_set(ctx, s)
        img = r.screenshot()
        g = SETS[s]
        tris = [t for k in ("ft", "fq", "gt", "gq") for t, _ in triangles(g)[k]]
        n = 0
        for y in range(2, SCREEN_H, 6):
            for x in range(2, SCREEN_W, 6):
                if min(tri_dist((x, y), t) for t in tris) < 5:
                    continue
                n += 1
                expect_pixel(img, x, y, rgb(g["bg"]), tol=TOL_BG, what=f"gallery '{s}': background pixel ({x},{y})",
                             hint="Something was drawn here: wrong origin offset, wrong vertex word, or a stray packet.")
        expect_true(n > 100, "enough background samples", str(n))
