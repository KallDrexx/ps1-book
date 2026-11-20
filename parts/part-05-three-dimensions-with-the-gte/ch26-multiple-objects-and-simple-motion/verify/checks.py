"""Chapter 26 checks: Multiple Objects and Simple Motion ("Bouncing Cubes").
Build: CMake + PSn00bSDK.
STATIC: the state symbols exist; the program's OWN objects (project + psxe, never the SDK's libraries) contain GTE commands
(RTPS or RTPT, NCLIP, AVSZ3 or AVSZ4); no floating point; the reference solution's psxe mirrors common/psxe.
DYNAMIC (probe.lua): every time the program calls frame_done() the probe records all 45 words of objects[], the CPU cycles
between render_begin() and render_end(), and the quads found by WALKING the ordering table handed to DrawOTag (slot, colour,
four corners). The Python reference below is the contract of README section 7:
  * physics: per object, per frame: vy += gravity; y += vy; if y > (floor_y - radius) << 12 then y = that, vy = -fx_mul(vy,
    bounce), bounces++; each angle = (angle + step) & 4095. Compared EXACTLY, every frame, in the shipped run (300 frames) and
    in a run whose start state, gravity, restitution, floor height, sizes, steps, colours, camera and lens are all patched;
  * drawing: object matrix = RotMatrix(angles) with its columns scaled by size, translation (x, y >> 12, z), composed with the
    camera matrix (identity rotation, translation cam); corners projected as the GTE's RTPS does (the divider of psx-spx);
    a face is drawn iff NCLIP of its corners 0, 1, 2 is positive; its OT slot is (AVSZ4 of the four SZ) >> 7 (+-1);
    the floor is 8 x 6 tiles at slot 63 whose corners and checker colours follow the same projection;
  * the picture: tile centres and visible face centres have the right colour.
Runs: shipped numbers (300 frames); patched everything (150 frames); a frozen scene (gravity 0, no spin) for the picture."""
import re
import shutil
import struct
import subprocess
from pathlib import Path

from harness import *

ROOT_DIR = Path(__file__).resolve().parents[4]

W, H = 320, 240
CX, CY = W // 2, H // 2
BG = (24, 24, 48)
BOOT = 45                         # frames the SDK needs before main (about 34) plus margin
N = 300
MARGIN = 700                      # |NCLIP| below this: the face is nearly edge-on, not judged
TOL_CORNER = 2                    # px: the matrix is built by ScaleMatrix/CompMatrixLV, whose rounding differs slightly
OT_LEN = 64
OTZ_SHIFT = 7
COLS, ROWS, TILE = 8, 6, 2048
NF = 15
FIELDS = ["x", "y", "z", "vy", "ax", "ay", "az", "sx", "sy", "sz", "size", "radius", "bounce", "colour", "bounces"]
FACES = [(0, 1, 2, 3), (5, 4, 7, 6), (4, 0, 6, 2), (1, 5, 3, 7), (4, 5, 0, 1), (2, 3, 6, 7)]
SHADE = [256, 208, 176, 232, 192, 160]
FLOOR_COLORS = [(72, 72, 96), (168, 168, 190)]


def pack(r, g, b):
    return r | g << 8 | b << 16


# objects[]: x y z vy  ax ay az  sx sy sz  size radius bounce colour bounces
SHIPPED = dict(
    objs=[
        [-4400, -3000 * 4096, -1200, 0, 300, 0, 120, 0, 56, 0, 1200, 1500, 3277, pack(224, 48, 48), 0],
        [0, -4000 * 4096, 1800, -60 * 4096, 0, 500, 200, 40, 0, 0, 1700, 2125, 2867, pack(48, 200, 64), 0],
        [4400, -2500 * 4096, 0, 30 * 4096, 700, 150, 0, 0, 0, -48, 2200, 2750, 3482, pack(64, 96, 240), 0],
    ],
    gravity=4 * 4096, floor_y=4096, cam=(0, 0, 14336), h=256, floors=FLOOR_COLORS,
)
PATCHED = dict(
    objs=[
        [-3000, -1000 * 4096, -3000, 70 * 4096, 1000, 2000, 3000, -30, 45, 61, 1000, 1250, 3900, pack(200, 120, 40), 0],
        [1500, -2000 * 4096, 800, -20 * 4096, 4000, 100, 2500, 0, -77, 0, 1440, 1800, 2000, pack(40, 220, 200), 0],
        [4000, 0, 2500, 0, 77, 3333, 1, 100, 100, 100, 1900, 2375, 3600, pack(220, 40, 160), 0],
    ],
    gravity=22528, floor_y=5000, cam=(300, 300, 16000), h=200, floors=[(30, 100, 40), (200, 200, 90)],
)
# frozen scene: no gravity, no spin; three poses with different numbers of visible faces
STILL = dict(
    objs=[
        [-4600, -1500 * 4096, 0, 0, 1050, 500, 0, 0, 0, 0, 1200, 1500, 3277, pack(224, 48, 48), 0],
        [0, -2200 * 4096, 1500, 0, 3050, 1600, 2050, 0, 0, 0, 1700, 2125, 2867, pack(48, 200, 64), 0],
        [4600, -900 * 4096, -800, 0, 650, 450, 250, 0, 0, 0, 2200, 2750, 3482, pack(64, 96, 240), 0],
    ],
    gravity=0, floor_y=4096, cam=(0, 0, 14336), h=256, floors=FLOOR_COLORS,
)
for _o in STILL["objs"]:
    _o[3] = 0

config(
    title="Multiple Objects and Simple Motion",
    build="cmake", exe="game.exe", sym="", elf="game.elf",
    break_at=None, max_frames=BOOT + N, timeout=40,
)

STATE = ["objects", "gravity", "floor_y", "cam", "proj_h", "cube", "faces", "face_shade", "floor_colors",
         "frame_no", "render_begin", "render_end", "frame_done"]


# ---- the reference -------------------------------------------------------------------------------------------------------
def isin(a):
    """PSn00bSDK isin(): 4096 = one turn, result 4.12 (a port of the library routine)."""
    t = (a - 1024) & 0x7FF
    if t & 0x400:
        t -= 0x800
    p = (t * t) >> 6
    v = ((19900 - ((879 * p) >> 12)) * p) >> 16
    return v - 4096 if a & 0x800 else 4096 - v


def icos(a):
    return isin(a + 1024)


def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) >> 12 for j in range(3)] for i in range(3)]


def rot_matrix(ax, ay, az):
    sx, cx, sy, cy, sz, cz = isin(ax), icos(ax), isin(ay), icos(ay), isin(az), icos(az)
    X = [[4096, 0, 0], [0, cx, -sx], [0, sx, cx]]
    Y = [[cy, 0, sy], [0, 4096, 0], [-sy, 0, cy]]
    Z = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 4096]]
    return matmul(matmul(X, Y), Z)


UNR = [max(0, (0x40000 // (i + 0x100) + 1) // 2 - 0x101) for i in range(0x101)]


def gte_divide(h, sz):
    if h >= sz * 2:
        return 0x1FFFF, True
    z = 16 - sz.bit_length()
    n, d = h << z, sz << z
    u = UNR[(d - 0x7FC0) >> 7] + 0x101
    d = (0x2000080 - d * u) >> 8
    d = (0x0000080 + d * u) >> 8
    return min(0x1FFFF, (n * d + 0x8000) >> 16), False


def sat(v, lo, hi):
    return max(lo, min(hi, v))


def rtps(m, t, v, h):
    """RTPS with sf = 1: returns (sx, sy, sz)."""
    mac = [((t[i] << 12) + sum(m[i][k] * v[k] for k in range(3))) >> 12 for i in range(3)]
    ir = [sat(x, -32768, 32767) for x in mac]
    sz = sat(mac[2], 0, 65535)
    n, _ = gte_divide(h, sz)
    sx = sat((n * ir[0] + (CX << 16)) >> 16, -0x400, 0x3FF)
    sy = sat((n * ir[1] + (CY << 16)) >> 16, -0x400, 0x3FF)
    return sx, sy, sz


def nclip(p0, p1, p2):
    return p0[0] * p1[1] + p1[0] * p2[1] + p2[0] * p0[1] - p0[0] * p2[1] - p1[0] * p0[1] - p2[0] * p1[1]


def corner(i):
    return (4096 if i & 1 else -4096, 4096 if i & 2 else -4096, 4096 if i & 4 else -4096)


def ref_step(o, g, floor_y):
    """One frame of the integer model (README 5.5): returns the new 15 fields."""
    x, y, z, vy, ax, ay, az, sx, sy, sz, size, radius, bounce, colour, bounces = o
    vy += g
    y += vy
    limit = (floor_y - radius) << 12
    if y > limit:
        y = limit
        vy = -((vy * bounce) >> 12)          # fx_mul: exact product, arithmetic shift
        bounces += 1
    return [x, y, z, vy, (ax + sx) & 4095, (ay + sy) & 4095, (az + sz) & 4095, sx, sy, sz, size, radius, bounce, colour, bounces]


def ref_states(d, n):
    """states[k] = the three objects after k frames (states[0] = the start)."""
    cur = [list(o) for o in d["objs"]]
    out = [[list(o) for o in cur]]
    for _ in range(n):
        cur = [ref_step(o, d["gravity"], d["floor_y"]) for o in cur]
        out.append([list(o) for o in cur])
    return out


def object_matrix(o, cam):
    """RotMatrix, ScaleMatrix (columns * size >> 12), TransMatrix, then CompMatrixLV with the camera matrix (identity rotation)."""
    m = rot_matrix(o[4], o[5], o[6])
    m = [[sat((m[i][j] * o[10]) >> 12, -32768, 32767) for j in range(3)] for i in range(3)]
    t = (o[0] + cam[0], (o[1] >> 12) + cam[1], o[2] + cam[2])
    return m, t


def colour_rgb(c):
    return (c & 255, (c >> 8) & 255, (c >> 16) & 255)


def face_rgb(o, f):
    return tuple((v * SHADE[f]) >> 8 for v in colour_rgb(o[13]))


def ref_cube(o, d):
    m, t = object_matrix(o, d["cam"])
    pts = [rtps(m, t, corner(i), d["h"]) for i in range(8)]
    xy = [(p[0], p[1]) for p in pts]
    sz = [p[2] for p in pts]
    areas = [nclip(xy[f[0]], xy[f[1]], xy[f[2]]) for f in FACES]
    return dict(xy=xy, sz=sz, areas=areas)


def ref_floor(d):
    """Projected tile corners, [row][col] -> (sx, sy); and each tile's four corners in drawing order."""
    m = [[4096, 0, 0], [0, 4096, 0], [0, 0, 4096]]
    t = tuple(d["cam"])
    v = [[rtps(m, t, ((c - COLS // 2) * TILE, d["floor_y"], (r - ROWS // 2) * TILE), d["h"])[:2] for c in range(COLS + 1)] for r in range(ROWS + 1)]
    tiles = []
    for r in range(ROWS):
        for c in range(COLS):
            tiles.append(dict(r=r, c=c, xy=[v[r + 1][c], v[r + 1][c + 1], v[r][c], v[r][c + 1]], parity=(r + c) & 1))
    return tiles


def ref_slot(sz4):
    otz = sat((256 * sum(sz4)) >> 12, 0, 65535)
    return sat(otz >> OTZ_SHIFT, 0, OT_LEN - 1)


# ---- patching and reading the runs ------------------------------------------------------------------------------------------------
def patches_for(d):
    return {
        "objects": b"".join(struct.pack("<15i", *o) for o in d["objs"]),
        "gravity": words(d["gravity"]), "floor_y": words(d["floor_y"]),
        "cam": words(*d["cam"]), "proj_h": words(d["h"]),
        "floor_colors": bytes(v for c in d["floors"] for v in c),
    }


RUNS = {
    "base": (SHIPPED, N, None),
    "patched": (PATCHED, 150, True),
    "still": (STILL, 12, True),
}


def run_of(ctx, name):
    d, n, patch = RUNS[name]
    if not patch:
        return ctx.result, d, n
    return ctx.run(name, patches=patches_for(d), max_frames=BOOT + n), d, n


class Row:
    def __init__(self, r):
        self.n = r[0]
        self.objs = [list(r[1 + NF * i: 1 + NF * (i + 1)]) for i in range(3)]
        self.cycles = r[1 + 3 * NF]
        flat = r[2 + 3 * NF] if isinstance(r[2 + 3 * NF], list) else []
        self.quads = [dict(slot=flat[i], code=flat[i + 1], rgb=tuple(flat[i + 2:i + 5]), xy=list(flat[i + 5:i + 13]))
                      for i in range(0, len(flat), 13)]


def observe(ctx, name):
    r, d, n = run_of(ctx, name)
    raw = r.record("rows") or []
    expect_true(len(raw) >= n - 10, f"{name}: frame_done() is called every frame ({n - 10}+ times observed)",
                f"{len(raw)} calls", "main's loop (given) calls frame_done() after frame_no++ and display_swap(); did the program get there?")
    return r, d, [Row(x) for x in raw], r.record("tables")


def drawn_quads(x):
    """Split a frame's quads into floor quads (slot 63) and the rest."""
    return [q for q in x.quads if q["slot"] == OT_LEN - 1], [q for q in x.quads if q["slot"] != OT_LEN - 1]


def near(a, b, tol):
    return all(abs(p - q) <= tol for p, q in zip(a, b))


# ---- static checks -----------------------------------------------------------------------------------------------------------
@static_check("the state symbols exist", hint="Keep the starter's declarations, the keep-alive `__asm__ volatile(...)` line at the top of main, and the three marker functions.")
def _(ctx):
    miss = ctx.symbols.require(*STATE)
    if miss:
        raise CheckFailure(
            expected="symbols defined: " + ", ".join(STATE), actual="missing: " + ", ".join(miss),
            hint="The linker drops data nothing reads. Keep the starter's declarations and the `__asm__ volatile(...)` line "
                 "that keeps them alive, and read the values from these variables (constants in their place fail the patched runs).")


def _objects(ctx):
    objs = sorted(ctx.build.build_dir.rglob("*.obj")) + sorted(ctx.build.build_dir.rglob("*.o"))
    expect_true(objs, "the program's object files are available", "none found in the build directory")
    return objs


def _tool(name):
    p = shutil.which(name)
    if not p:
        raise HarnessError(f"{name} not on PATH (source tools/env.sh)")
    return p


COP2_NAMES = {0x01: "RTPS", 0x06: "NCLIP", 0x2D: "AVSZ3", 0x2E: "AVSZ4", 0x30: "RTPT"}


@static_check("the program uses the GTE: RTPS or RTPT, NCLIP and AVSZ3/AVSZ4 appear in its own objects",
              hint="Scanned: every .obj of your project and of psxe/ (never the SDK's libraries). Use gte_rtps()/gte_rtpt(), gte_nclip() and gte_avsz3()/gte_avsz4().")
def _(ctx):
    objdump = _tool("mipsel-none-elf-objdump")
    seen = set()
    for o in _objects(ctx):
        dis = subprocess.run([objdump, "-d", str(o)], capture_output=True, text=True).stdout
        for m in re.finditer(r"\t(?:cop2|c2)\s+0x([0-9a-fA-F]+)", dis):
            seen.add(int(m.group(1), 16) & 0x3F)
    names = {COP2_NAMES[c] for c in seen if c in COP2_NAMES}
    expect_true(names & {"RTPS", "RTPT"}, "a perspective transform command (RTPS or RTPT)", f"GTE commands found: {sorted(names) or 'none'}",
                "gte_rtps() transforms one vertex: gte_ldv0(&v); gte_rtps(); gte_stsxy(...).")
    expect_true("NCLIP" in names, "a normal-clip command (NCLIP)", f"GTE commands found: {sorted(names)}", "gte_nclip() after loading three screen points with gte_ldsxy3.")
    expect_true(names & {"AVSZ3", "AVSZ4"}, "an average-Z command (AVSZ3 or AVSZ4)", f"GTE commands found: {sorted(names)}",
                "gte_avsz4() after gte_ldsz4: the depth of a cube face.")


@static_check("integers only: no floating point in the program's objects (the physics is fixed point)",
              hint="Soft-float helpers (__mulsf3, __floatsisf, ...) in your objects mean a float or double crept in. Use psxe/fixed.h.")
def _(ctx):
    nm = _tool("mipsel-none-elf-nm")
    for o in _objects(ctx):
        und = subprocess.run([nm, "--undefined-only", str(o)], capture_output=True, text=True).stdout.split()
        soft = [n for n in und if re.fullmatch(r"__\w*(sf|df)(\d|si|di|ti)?\d*|__\w*(si|di)(sf|df)\d*", n)]
        expect_true(not soft, f"{o.name} references no soft-float helper", f"references {soft}")


@static_check("the reference solution's psxe mirrors common/psxe (the copy later chapters start from)",
              hint="Keep solution/psxe's five modules identical to common/psxe.")
def _(ctx):
    if not ctx.solution:
        return
    ref = ROOT_DIR / "common" / "psxe"
    for m in ("display", "ot", "gfx", "input", "fixed"):
        for rel in (f"include/psxe/{m}.h", f"src/{m}.c"):
            p, q = ref / rel, ctx.project / "psxe" / rel
            expect_true(q.exists() and q.read_bytes() == p.read_bytes(), f"solution/psxe/{rel} == common/psxe/{rel}", "differs or missing")


# ---- dynamic checks -----------------------------------------------------------------------------------------------------------
def check_tables(name, d, t):
    expect_eq(t["gravity"], d["gravity"], f"{name}: gravity", hint="Read it, do not write it.")
    expect_eq(t["floor_y"], d["floor_y"], f"{name}: floor_y", hint="Read it, do not write it.")
    expect_eq(t["cam"], list(d["cam"]), f"{name}: cam", hint="Read it, do not write it.")
    expect_eq(t["proj_h"], d["h"], f"{name}: proj_h", hint="Read it, do not write it.")
    expect_eq(t["shade"], SHADE, f"{name}: face_shade[]", hint="Do not change the shade table.")
    expect_eq(t["faces"], [v for f in FACES for v in f], f"{name}: faces[]", hint="Do not change the face table.")
    expect_eq(t["cube"], [v for i in range(8) for v in (*corner(i), 0)], f"{name}: cube[]", hint="Do not change the cube table.")
    expect_eq(t["floor_colors"], [v for c in d["floors"] for v in c], f"{name}: floor_colors[]", hint="Do not change the floor colours.")


def check_frames(ctx, name):
    r, d, rows, t = observe(ctx, name)
    check_tables(name, d, t)
    expect_eq([x.n for x in rows], list(range(1, len(rows) + 1)), f"{name}: frame_no at each frame_done() call",
              hint="frame_no is 1 at the first call and grows by 1 per frame; main's loop (given) does it.")
    return r, d, rows


def check_model(ctx, name, only=None):
    """Every field of every object, every frame, against the integer model (only = the field names to compare)."""
    r, d, rows = check_frames(ctx, name)
    states = ref_states(d, len(rows))
    names = only or FIELDS
    for x in rows:
        for i in range(3):
            for fi, fname in enumerate(FIELDS):
                if fname not in names:
                    continue
                want, got = states[x.n][i][fi], x.objs[i][fi]
                if want != got:
                    raise CheckFailure(
                        expected=f"{name}, frame {x.n}: objects[{i}].{fname} = {want}", actual=str(got),
                        hint=HINTS.get(fname, "Compare with the update rule of README 5.5."))
    return r, d, rows, states


HINTS = {
    "vy": "Order matters: vy += gravity; y += vy; then the floor test. On contact: y = (floor_y - radius) << 12 and vy = -fx_mul(vy, bounce) (README 5.5).",
    "y": "Order matters: vy += gravity; y += vy; then the floor test. y is 20.12: the floor limit is (floor_y - radius) << 12 (README 5.5).",
    "bounces": "Add 1 to bounces each time the floor test fires, and only then.",
    "ax": "ax = (ax + sx) & 4095, from the object's own sx; one update per frame.",
    "ay": "ay = (ay + sy) & 4095, from the object's own sy; one update per frame.",
    "az": "az = (az + sz) & 4095, from the object's own sz; one update per frame.",
}


# ---- drawing checks ------------------------------------------------------------------------------------------------------------------
def check_cubes(ctx, name):
    """The cube quads in the ordering table against the reference: which faces, their colours, corners and slots."""
    r, d, rows = check_frames(ctx, name)       # drawn from the program's OWN state: physics is judged by its own check
    judged = 0
    for x in rows:
        _, cube_q = drawn_quads(x)
        st = x.objs
        seen = {}
        for q in cube_q:
            expect_eq(q["code"], 0x28, f"{name}, frame {x.n}: quads are POLY_F4 (code 0x28)", hint="setPolyF4 then setRGB0.")
            key = None
            for i in range(3):
                for f in range(6):
                    if near(q["rgb"], face_rgb(st[i], f), 1):
                        key = (i, f)
            expect_true(key is not None, f"{name}, frame {x.n}: every cube quad has a face colour (colour field x shade)", str(q["rgb"]),
                        "colour channel * face_shade[f] >> 8 for each of the object's three channels.")
            expect_true(key not in seen, f"{name}, frame {x.n}: object {key[0]} face {key[1]} is drawn once", "drawn twice")
            seen[key] = q
        for i in range(3):
            rc = ref_cube(st[i], d)
            for f in range(6):
                a = rc["areas"][f]
                q = seen.get((i, f))
                if abs(a) < MARGIN:
                    continue
                judged += 1
                if a > 0:
                    expect_true(q is not None, f"{name}, frame {x.n}: object {i} face {f} faces the camera (NCLIP {a}) and is drawn", "not drawn",
                                "Per face: gte_ldsxy3 of corners 0, 1, 2; gte_nclip(); gte_stopz(&area); draw only if area > 0.")
                    want = [v for c in FACES[f] for v in rc["xy"][c]]
                    expect_true(near(q["xy"], want, TOL_CORNER), f"{name}, frame {x.n}: object {i} face {f} corners {want} (+-{TOL_CORNER} px)", str(q["xy"]),
                                "Each object needs ITS OWN matrix in the GTE when its corners are transformed: build it from this object's angles, size and position, "
                                "compose it with the camera, and upload both parts before the object's first gte_rtps().")
                    want_slot = ref_slot([rc["sz"][c] for c in FACES[f]])
                    expect_true(abs(q["slot"] - want_slot) <= 1, f"{name}, frame {x.n}: object {i} face {f} is in OT slot {want_slot} (+-1)", f"slot {q['slot']}",
                                "slot = (AVSZ4 of the face's four SZ) >> 7: farther = larger.")
                    expect_true(q["slot"] < OT_LEN - 1, f"{name}, frame {x.n}: object {i} face {f} is nearer than the floor (slot < 63)", f"slot {q['slot']}")
                else:
                    expect_true(q is None, f"{name}, frame {x.n}: object {i} face {f} points away (NCLIP {a}) and is not drawn", "drawn",
                                "A face is drawn only if its NCLIP is positive.")
    expect_true(judged >= 4 * len(rows), f"{name}: the frames judged cover enough faces", str(judged))


def check_floor(ctx, name):
    r, d, rows, t = observe(ctx, name)
    tiles = ref_floor(d)
    for x in rows:
        floor_q, _ = drawn_quads(x)
        expect_eq(len(floor_q), COLS * ROWS, f"{name}, frame {x.n}: floor quads in slot {OT_LEN - 1} ({COLS} x {ROWS} tiles)",
                  hint="One POLY_F4 per tile, all linked at the farthest slot (OT_LENGTH - 1) so every cube is drawn over them.")
        left = list(floor_q)
        for tl in tiles:
            want = [v for p in tl["xy"] for v in p]
            hit = next((q for q in left if near(q["xy"], want, 1)), None)
            expect_true(hit is not None, f"{name}, frame {x.n}: floor tile (col {tl['c']}, row {tl['r']}) has a quad with corners {want}", "none",
                        "The floor's matrix is the camera's: identity rotation, translation cam. Tile (c, r) spans x = (c - 4) * 2048 .. +2048, z = (r - 3) * 2048 .. +2048 at y = floor_y; "
                        "corners in Z order: far-left, far-right, near-left, near-right.")
            left.remove(hit)
            expect_true(near(hit["rgb"], d["floors"][tl["parity"]], 1), f"{name}, frame {x.n}: tile (col {tl['c']}, row {tl['r']}) has colour {d['floors'][tl['parity']]}",
                        str(hit["rgb"]), "Checkerboard: colour (col + row) & 1 from floor_colors[].")


# ---- the picture ---------------------------------------------------------------------------------------------------------------------
def bbox_of(rc, pad=4):
    xs = [p[0] for p in rc["xy"]]
    ys = [p[1] for p in rc["xy"]]
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def inside(p, bb):
    return bb[0] <= p[0] <= bb[2] and bb[1] <= p[1] <= bb[3]


def check_picture(ctx, name, shot_frames, min_faces=1, min_tiles=14):
    r, d, rows, t = observe(ctx, name)
    states = [None] + [x.objs for x in rows]
    tiles = ref_floor(d)
    faces_seen = 0
    for fr in shot_frames:
        img = r.screenshot(f"f{fr}")
        expect_true((img.width, img.height) == (W, H), "the picture is 320 x 240", f"{img.width} x {img.height}")
        for c in ((0, 0), (W - 1, 0)):
            expect_true(colors_close(img.pixel(*c), BG, 12), f"{name}, frame {fr}: corner {c} is the background {BG}", str(img.pixel(*c)),
                        "display_clear(24, 24, 48) every frame.")
        st = states[fr]
        rcs = [ref_cube(st[i], d) for i in range(3)]
        boxes = [bbox_of(rc) for rc in rcs]
        per_parity = [0, 0]
        for tl in tiles:
            cx = round(sum(p[0] for p in tl["xy"]) / 4)
            cy = round(sum(p[1] for p in tl["xy"]) / 4)
            if not (2 <= cx < W - 2 and 2 <= cy < H - 2) or any(inside((cx, cy), b) for b in boxes):
                continue
            got = img.pixel(cx, cy)
            want = d["floors"][tl["parity"]]
            expect_true(colors_close(got, want, 14), f"{name}, frame {fr}: floor tile (col {tl['c']}, row {tl['r']}) centre ({cx}, {cy}) is colour {want}", str(got),
                        "Alternate the two floor_colors[] by (col + row) & 1; the floor must be drawn behind the cubes (slot 63) and inside the screen.")
            per_parity[tl["parity"]] += 1
        expect_true(min(per_parity) >= min_tiles // 2, f"{name}, frame {fr}: enough tiles of both colours are visible to judge ({min_tiles // 2}+ each)", str(per_parity), "(checker design)")
        for i in range(3):
            for f in range(6):
                if abs(rcs[i]["areas"][f]) < MARGIN or rcs[i]["areas"][f] < 0:
                    continue
                pts = [rcs[i]["xy"][c] for c in FACES[f]]
                cx, cy = round(sum(p[0] for p in pts) / 4), round(sum(p[1] for p in pts) / 4)
                if not (0 <= cx < W and 0 <= cy < H) or any(inside((cx, cy), boxes[j]) for j in range(3) if j != i):
                    continue
                want = face_rgb(st[i], f)
                got = img.pixel(cx, cy)
                expect_true(colors_close(got, want, 14), f"{name}, frame {fr}: object {i} face {f} centre ({cx}, {cy}) is colour {want}", str(got),
                            "Cubes are drawn over the floor: slot of the face's average depth, always nearer than the floor's slot 63.")
                faces_seen += 1
    expect_true(faces_seen >= min_faces * len(shot_frames), f"{name}: enough cube faces were judged in the pictures", str(faces_seen), "(checker design)")


# ---- the checks ------------------------------------------------------------------------------------------------------------------------
@check("physics: y, velocity and bounce count follow the integer model exactly, 300 frames, all three cubes",
       hint="Per object per frame: vy += gravity; y += vy; if y > (floor_y - radius) << 12 { y = that; vy = -fx_mul(vy, bounce); bounces++ }.")
def _(ctx):
    r, d, rows, states = check_model(ctx, "base", only=["x", "y", "z", "vy", "bounces", "size", "radius", "bounce", "colour"])
    expect_true(len(rows) >= N - 10, "about 300 frames were observed", str(len(rows)))
    for i in range(3):
        expect_true(states[len(rows)][i][14] >= 3, f"object {i} bounces at least 3 times in the run (checker design)", str(states[len(rows)][i][14]))


@check("floor: no cube's lowest point (y + radius) ever goes below floor_y; each stays above it until it bounces",
       hint="Clamp y to (floor_y - radius) << 12 in the same frame the test fires, before drawing.")
def _(ctx):
    for name in ("base", "patched"):
        r, d, rows = check_frames(ctx, name)
        for x in rows:
            for i, o in enumerate(x.objs):
                low = o[1] + (o[11] << 12)
                expect_true(low <= d["floor_y"] << 12, f"{name}, frame {x.n}: objects[{i}].y + radius <= floor_y (in 20.12)",
                            f"{low / 4096:.1f} > {d['floor_y']}", "A cube that sinks into the floor: the contact test is missing, or runs after the position is used.")


@check("spin: each axis' angle advances by its own step and wraps at 4096, independently per object (shipped and patched steps)",
       hint="One update per frame: ax = (ax + sx) & 4095 and the same for y and z, using this object's own sx, sy, sz.")
def _(ctx):
    for name in ("base", "patched"):
        check_model(ctx, name, only=["ax", "ay", "az", "sx", "sy", "sz"])


@check("patched start state, gravity, restitution, floor height, sizes and spins: the model still matches exactly (150 frames)",
       hint="Nothing may be hard-coded: every number comes from objects[], gravity and floor_y.")
def _(ctx):
    r, d, rows, states = check_model(ctx, "patched")
    for i in range(3):
        expect_true(states[len(rows)][i][14] >= 1, f"patched: object {i} bounces at least once (checker design)", str(states[len(rows)][i][14]))


@check("each cube has its own matrix: every visible face's quad has the reference corners (+-2 px), colour and OT slot; hidden faces are not drawn",
       hint="Per cube: RotMatrix + ScaleMatrix + TransMatrix, CompMatrixLV with the camera, upload (gte_SetRotMatrix/gte_SetTransMatrix), THEN its eight gte_rtps().")
def _(ctx):
    check_cubes(ctx, "base")


@check("the same with every start value, the camera and the lens patched, and with a frozen scene",
       hint="The camera is `cam` (translation added to every world position) and `proj_h`; nothing may be a constant.")
def _(ctx):
    check_cubes(ctx, "patched")
    check_cubes(ctx, "still")


@check("floor: 8 x 6 quads at the farthest slot, corners from the projected grid, alternating checker colours (shipped and patched camera)",
       hint="Upload the camera matrix, transform the 9 x 7 grid corners, then one POLY_F4 per tile at slot OT_LENGTH - 1 with colour (col + row) & 1.")
def _(ctx):
    check_floor(ctx, "base")
    check_floor(ctx, "patched")


@check("picture: tile centres show the alternating colours; visible face centres show the cube colours (cubes in front of the floor)",
       hint="Floor at slot 63, cubes at the slots of their own depth: a cube resting on the floor must hide the tiles behind it.")
def _(ctx):
    check_picture(ctx, "base", (3, 40, 97, 210, 290))
    check_picture(ctx, "patched", (3, 40, 97), min_faces=1)
    check_picture(ctx, "still", (3, 5), min_faces=3)


SOLUTION_CYCLES = 29750
BUDGET = 2 * SOLUTION_CYCLES


@check(f"frame time: CPU cycles between render_begin() and render_end() stay under the budget ({BUDGET})",
       hint="Build each object's matrix once per frame; 63 floor corners and 24 cube corners are all the transforms a frame needs.")
def _(ctx):
    r, d, rows, t = observe(ctx, "base")
    cyc = sorted(x.cycles for x in rows[1:])
    med = cyc[len(cyc) // 2]
    expect_true(med > 0, "render_begin() and render_end() were reached", "0 cycles", "Keep the markers in main's loop around the 3D work.")
    expect_true(max(cyc) <= BUDGET, f"cycles per frame <= {BUDGET} (the reference solution needs about {SOLUTION_CYCLES})",
                f"median {med}, worst {max(cyc)}", "Transform each vertex once per frame; do not rebuild matrices per face.")
