"""Chapter 20 checks: Primitives and Ordering Tables.
Build: CMake + PSn00bSDK. Four emulator runs: the shipped scene, two scenes the verifier patches into `scene` (new depths AND a
permutation of the colors) and `depth_step`, and an overflow run with `copies` patched to 20 (320 quads against room for 85).
probe.lua breaks on ClearOTagR and DrawOTag (arguments recorded), WALKS the DMA linked list from DrawOTag's argument exactly as
the DMA would (so the order in which the GPU receives the packets is observed, not inferred) and watches the guard bytes after both
primitive buffers. Checks: the list holds the 16 quads farthest-first, the head is the last entry of a ClearOTagR table, the two
frames alternate, the packets are bump-allocated, screenshots show the nearest quad's color at every sampled point (all
pairwise overlaps included), and the overflow run neither crashes nor writes past a buffer."""
import itertools
import struct

from harness import *

NQ, OT_LENGTH, PRIM_BUF, GUARD, FRAME_SZ, GUARD_OFF = 16, 64, 2048, 16, 2320, 2304
POLY_F4 = 24
PK = 7          # probe record per packet: node, len, code, r, g, b, table entry walked just before it
BG = (24, 24, 32)
SHOT_A, SHOT_B = 70, 100
COPIES_OVER = 20

# x, y, w, h, r, g, b, depth  (shipped `scene`)
SHIPPED = [
    (8, 8, 90, 70, 25, 255, 255, 10), (80, 4, 90, 70, 33, 15, 153, 54), (136, 10, 90, 70, 140, 25, 255, 6),
    (209, 6, 90, 70, 153, 15, 119, 50), (13, 53, 90, 70, 25, 255, 169, 18), (71, 59, 90, 70, 15, 153, 50, 2),
    (142, 56, 90, 70, 226, 255, 25, 42), (206, 60, 90, 70, 153, 15, 15, 34), (6, 106, 90, 70, 255, 198, 25, 58),
    (78, 102, 90, 70, 15, 101, 153, 22), (140, 109, 90, 70, 54, 255, 25, 46), (201, 104, 90, 70, 153, 67, 15, 14),
    (11, 160, 90, 70, 226, 25, 255, 26), (74, 156, 90, 70, 15, 50, 153, 30), (136, 153, 90, 70, 255, 25, 112, 38),
    (212, 158, 90, 70, 84, 153, 15, 62),
]


def pack(rows):
    return b"".join(struct.pack("<4h4Bi", x, y, w, h, r, g, b, 0, d) for x, y, w, h, r, g, b, d in rows)


def recolor(shift, depths):
    """Same geometry, colors rotated by `shift` positions, new depths."""
    return [(x, y, w, h, *SHIPPED[(i + shift) % NQ][4:7], depths[i]) for i, (x, y, w, h, *_rest) in enumerate(SHIPPED)]


D1 = [(i * 37 + 5) % OT_LENGTH for i in range(NQ)]          # 37 is odd: all distinct mod 64
D2 = [63 - 4 * ((i * 5) % NQ) for i in range(NQ)]            # 63..3, distinct, spans the whole range
STATES = {
    "base": None,
    "p1": {"scene": pack(recolor(5, D1)), "depth_step": 7},
    "p2": {"scene": pack(recolor(11, D2)), "depth_step": 3},
}
TABLES = {"base": SHIPPED, "p1": recolor(5, D1), "p2": recolor(11, D2)}
STEPS = {"base": 1, "p1": 7, "p2": 3}
assert len(set(D1)) == NQ and len(set(D2)) == NQ

config(
    title="Primitives and Ordering Tables",
    build="cmake", exe="game.exe", sym="", elf="game.elf",
    break_at=None, max_frames=130, shots=[("a", SHOT_A), ("b", SHOT_B)],
    reads={"ot_frames": 2 * FRAME_SZ},
)


def ch8(c5): return (c5 << 3) | (c5 >> 2)
def seen(rgb): return tuple(ch8(c >> 3) for c in rgb)


# ---- geometry: sample points -------------------------------------------------------------
def inter(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None


def near_edge(px, py, m=3):
    for x, y, w, h, *_ in SHIPPED:
        if y - m <= py <= y + h + m and (abs(px - x) < m or abs(px - x - w) < m):
            return True
        if x - m <= px <= x + w + m and (abs(py - y) < m or abs(py - y - h) < m):
            return True
    return False


def pair_points():
    """For every pair of quads that overlap: the point of their intersection farthest from every quad edge."""
    pts = {}
    for a, b in itertools.combinations(range(NQ), 2):
        i = inter(SHIPPED[a], SHIPPED[b])
        if i:
            cand = [(x, y) for x in range(i[0], i[2]) for y in range(i[1], i[3]) if not near_edge(x, y)]
            if cand:
                cx, cy = (i[0] + i[2]) / 2, (i[1] + i[3]) / 2
                pts[(a, b)] = min(cand, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
            else:
                pts[(a, b)] = None
    return pts


PAIRS = pair_points()
GRID = [(x, y) for y in range(2, 240, 6) for x in range(2, 320, 6) if not near_edge(x, y)]
POINTS = sorted(set(GRID) | {p for p in PAIRS.values() if p})


def covering(tab, px, py):
    return [i for i, (x, y, w, h, *_r) in enumerate(tab) if x <= px < x + w and y <= py < y + h]


def top_at(tab, depths, px, py):
    c = covering(tab, px, py)
    return min(c, key=lambda i: depths[i]) if c else None     # smallest depth = nearest = drawn last


# ---- run helpers ---------------------------------------------------------------------------
def run(ctx, name):
    if name == "base":
        r = ctx.result
    elif name == "over":
        r = ctx.run("over", patches={"copies": COPIES_OVER}, shots=(), max_frames=90)
    else:
        r = ctx.run(name, patches=STATES[name])
    r.require_finished()
    if r.record("runaway"):
        raise CheckFailure(expected="one frame-loop iteration per VBlank", actual=str(r.record("runaway")),
                           hint="display_swap() must wait for VBlank.")
    return r


def draws(r, want=30):
    dw = r.record("dw") or []
    expect_true(len(dw) >= want, f"at least {want} DrawOTag calls", str(len(dw)),
                hint="ot_draw() must call DrawOTag once per frame (and the frame loop must run).")
    return dw


@static_check("symbols", hint="Keep main, scene, ot_frames, copies, depth_step, frame_no; write the four ot_* functions.")
def _(ctx):
    ctx.require_symbols("main", "ot_begin_frame", "ot_alloc", "ot_add", "ot_draw", "scene", "ot_frames",
                        "copies", "depth_step", "frame_no")


@static_check("ClearOTagR and DrawOTag are linked in",
              hint="ot_begin_frame() must call ClearOTagR and ot_draw() must call DrawOTag (the linker drops the SDK routines otherwise).")
def _(ctx):
    ctx.require_symbols("ClearOTagR", "DrawOTag",
                        hint="ot_begin_frame() must call ClearOTagR and ot_draw() must call DrawOTag (the linker drops unused SDK routines).")


@static_check("data layout as shipped", hint="Do not edit the scene table, copies, depth_step or the OtFrame layout in ot.h.")
def _(ctx):
    base = ctx.exe.load_addr
    code = ctx.exe.code
    o = ctx.symbols["scene"] - base
    expect_bytes(code[o:o + 16 * NQ], pack(SHIPPED), "initial `scene` table")
    for k, want in (("copies", 1), ("depth_step", 1)):
        o = ctx.symbols[k] - base
        expect_eq(int.from_bytes(code[o:o + 4], "little"), want, f"initial {k}", fmt="dec")
    o = ctx.symbols["ot_frames"] - base
    for f in range(2):
        g = code[o + f * FRAME_SZ + GUARD_OFF:o + f * FRAME_SZ + GUARD_OFF + GUARD]
        expect_bytes(g, bytes([0xA5]) * GUARD, f"guard bytes after primitive buffer {f}")
    sz = ctx.symbols.size("ot_frames")
    if sz is not None:
        expect_eq(sz, 2 * FRAME_SZ, "sizeof ot_frames", fmt="dec", hint="OtFrame: ot[64], prim[2048], guard[16]; two of them.")


# ---- dynamic checks ------------------------------------------------------------------------
@check("ClearOTagR builds a 64-entry table each frame, the two frames alternate, DrawOTag starts at its LAST entry",
       hint="ot_begin_frame clears the current frame's table, all OT_LENGTH slots; ot_draw starts DrawOTag at that table's last entry, then switches frames.")
def _(ctx):
    r = run(ctx, "base")
    cl, dw = r.record("cl") or [], draws(r)
    base = ctx.symbols["ot_frames"]
    ots = [0x80000000 | base, 0x80000000 | (base + FRAME_SZ)]
    used = []
    for d in dw:
        n = d[1]
        mine = [c for c in cl if c[0] == n]      # extra clears (e.g. both tables at start-up) are fine: the last one counts
        expect_true(mine, f"a ClearOTagR before DrawOTag (frame_no={n})", "none",
                    "ot_begin_frame() must call ClearOTagR every frame.")
        c = mine[-1]
        expect_eq(c[2], OT_LENGTH, f"ClearOTagR length (frame_no={n})", fmt="dec", hint="Use the whole table: OT_LENGTH.")
        expect_true(c[1] in ots, f"the table cleared is ot_frames[0].ot or ot_frames[1].ot (frame_no={n})", hex(c[1]))
        expect_eq(d[2], c[1] + 4 * (OT_LENGTH - 1), f"DrawOTag head (frame_no={n})", fmt="hex",
                  hint="A ClearOTagR table links entry i to entry i-1: the walk starts at the LAST entry, &ot[OT_LENGTH-1].")
        used.append(c[1])
    expect_true(all(a != b for a, b in zip(used, used[1:])), "consecutive frames use different OtFrames",
                f"{sum(a == b for a, b in zip(used, used[1:]))} repeats",
                "Switch to the other OtFrame in ot_draw(), once per frame: one table per display buffer.")


@check("the DMA list holds the 16 quads farthest-first (every frame, three scenes)",
       hint="Walk the list: slot 63 first ... slot 0 last. Smallest depth = nearest = drawn last. Quads at equal depth would be a tie.")
def _(ctx):
    for name in STATES:
        r = run(ctx, name)
        tab = TABLES[name]
        for d in draws(r, 40):
            vf, n, head, gok, nodes, term, depths, prims = d
            ctx_s = f"({name}, frame_no={n})"
            expect_true(term, "the list ends with the terminator 0x00FFFFFF", "no terminator within 3000 nodes " + ctx_s,
                        "ClearOTagR sets entry 0's pointer to 0xFFFFFF; do not overwrite it.")
            expect_eq(nodes, OT_LENGTH + NQ, f"nodes walked = 64 table entries + 16 packets {ctx_s}", fmt="dec")
            pk = [prims[i:i + PK] for i in range(0, len(prims), PK)]
            expect_eq(len(pk), NQ, f"packets in the list {ctx_s}", fmt="dec", hint="One POLY_F4 per quad, each added once.")
            expect_true(all(p[1] == 5 and p[2] == 0x28 for p in pk), "every packet has length 5 and code 0x28 (POLY_F4)",
                        str([(p[1], hex(p[2])) for p in pk[:3]]) + ctx_s, "setPolyF4(p) before ot_add().")
            want_depths = [(tab[i][7] + STEPS[name] * n) % OT_LENGTH for i in range(NQ)]
            expect_eq(depths, want_depths, f"scene depths {ctx_s}", hint="Per frame every depth = (depth + depth_step) % OT_LENGTH, after the frame is drawn.")
            order = sorted(range(NQ), key=lambda i: -depths[i])
            want = [tuple(tab[i][4:7]) for i in order]
            got = [(p[3], p[4], p[5]) for p in pk]
            expect_eq(got, want, f"packet colors in DMA order {ctx_s}",
                      hint="Far to near: the quad with the largest depth first. A reversed or submission-order list fails here.")
            slots = [(p[6] - (head - 4 * (OT_LENGTH - 1))) // 4 for p in pk]
            expect_eq(slots, [depths[i] for i in order], f"table slot of each packet = its quad's depth {ctx_s}",
                      hint="ot_add(p, depth) must addPrim into ot[depth]: the table does the sorting, not your code.")


@check("packets are bump-allocated from the frame's primitive buffer",
       hint="ot_alloc hands out consecutive 24-byte blocks from ot_frames[cur].prim, starting at index 0 every frame.")
def _(ctx):
    r = run(ctx, "base")
    base = ctx.symbols["ot_frames"]
    for d in draws(r, 40):
        head, prims = d[2], d[7]
        f = 0 if (head & 0x1FFFFFFF) < (base & 0x1FFFFFFF) + FRAME_SZ else 1
        pbase = (base & 0x1FFFFFFF) + f * FRAME_SZ + OT_LENGTH * 4
        addrs = sorted((prims[i] & 0x1FFFFFFF) for i in range(0, len(prims), PK))
        expect_eq(addrs, [pbase + POLY_F4 * k for k in range(NQ)], f"packet addresses (frame_no={d[1]})", fmt="hex",
                  hint="Reset the bump pointer in ot_begin_frame and advance it by sizeof(POLY_F4) per allocation.")


@check("overflow: 320 quads against room for 85 - no crash, no write past a buffer",
       hint="ot_alloc must return NULL when the request does not fit, and draw_scene must stop on NULL.")
def _(ctx):
    r = run(ctx, "over")
    dw = draws(r, 30)
    cap = PRIM_BUF // POLY_F4
    for d in dw:
        expect_true(d[3], "guard bytes intact while drawing", f"a guard byte changed (frame_no={d[1]})",
                    "ot_alloc wrote past the end of the primitive buffer.")
        n = len(d[7]) // PK
        expect_true(NQ * 3 <= n <= cap, f"between 48 and {cap} packets per frame", f"{n} (frame_no={d[1]})",
                    "Accept requests while they fit, refuse the rest. Never more than PRIM_BUF_SIZE / 24.")
    m = r.mem("ot_frames")
    for f in range(2):
        expect_bytes(m[f * FRAME_SZ + GUARD_OFF:f * FRAME_SZ + GUARD_OFF + GUARD], bytes([0xA5]) * GUARD, f"guard {f} at the end")
    expect_true(r.frames >= 85, "the run reached its frame limit", f"{r.frames} frames")


@check("pacing: one frame per VBlank", hint="The OT work must fit in one frame; display_swap does the VSync.")
def _(ctx):
    for name in STATES:
        ev = run(ctx, name).record("ev") or []
        expect_true(len(ev) >= 40, "at least 40 frames shown", str(len(ev)), "PutDispEnv once per frame.")
        bad = [(a[0], b[0] - a[0]) for a, b in zip(ev, ev[1:]) if b[0] - a[0] != 1]
        expect_true(len(bad) <= 2, "consecutive frames one VBlank apart", f"{len(bad)} irregular gaps {bad[:4]} ({name})")


def shown_frame(ev, k):
    c = [e for e in ev if e[0] < k]
    return c[-1][1] if c else None


@check("screenshots: at every sampled point the color of the nearest quad (all overlaps, three scenes)",
       hint="Nearest = smallest depth = last in the DMA list. Each sample is far from any quad edge.")
def _(ctx):
    expect_true(all(p is not None for p in PAIRS.values()), "every overlapping pair has a sample point", "geometry bug in checks.py")
    for name in STATES:
        r = run(ctx, name)
        ev, dw = r.record("ev") or [], draws(r, 40)
        by_n = {d[1]: d for d in dw}
        tab = TABLES[name]
        for tag, k in (("a", SHOT_A), ("b", SHOT_B)):
            img = r.screenshot(tag)
            expect_eq((img.width, img.height), (320, 240), "screenshot size")
            n = shown_frame(ev, k)
            d = by_n.get(n)
            expect_true(d is not None, f"a DrawOTag record for the frame shown (frame_no={n})", "missing")
            depths = d[6]
            bad, nover = [], 0
            for (px, py) in POINTS:
                t = top_at(tab, depths, px, py)
                want = seen(tab[t][4:7]) if t is not None else seen(BG)
                nover += t is not None and len(covering(tab, px, py)) > 1
                got = img.pixel(px, py)
                if any(abs(a - b) > 6 for a, b in zip(got, want)):
                    near = min([(i, sum((a - b) ** 2 for a, b in zip(got, seen(tab[i][4:7])))) for i in range(NQ)], key=lambda p: p[1])
                    bad.append((px, py, "want quad %s" % t, "got %s (looks like quad %d)" % (got, near[0])))
            expect_true(not bad, f"all {len(POINTS)} sampled points show the nearest quad ({nover} are in overlaps)",
                        f"{len(bad)} wrong, e.g. {bad[:3]} (shot {tag}, {name}, frame_no={n})",
                        "Wrong quad on top: the OT order or depth direction is wrong. Background wrong: isbg clear missing.")
