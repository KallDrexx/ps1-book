"""Chapter 28 checks: The Camera (camera_look_at and a free-fly camera).
Build: CMake + PSn00bSDK.
STATIC: the state symbols exist; the program's OWN objects contain GTE commands; no floating point; the reference
solution's psxe mirrors common/psxe.
DYNAMIC. Three kinds of run:
  * direct (direct.lua): camera_look_at(eye, target, up) is CALLED from the probe with ~36 argument triples held in a scratch
    buffer: specials (the axes, rolled and upside-down ups, |up| tiny and huge, differences of 32000, eye == target, the degenerate
    cases) and a seeded random set. Each result is compared with the float reference below, entry by entry (tolerance in
    `entry_tol`), the translation with -R * eye of the reader's OWN rows, and orthonormality / handedness are checked on
    every result. The callee-saved registers must survive and the arguments must be untouched.
  * base (probe.lua): the shipped numbers, 300 frames, with a pad script (RIGHT, L1, UP, R1, LEFT, DOWN, opposite pairs).
  * patched: another start eye / up / speed / clamp box and another place for the center cube, with a script that runs
    into every clamp.
  In the two program runs the probe records, every frame, the eye, target, up, view_mtx, the objects, and the quads found by
  walking the ordering table. Checks: the view matrix is camera_look_at's answer for the recorded eye/target/up; the target is
  the center cube; the eye moves exactly as the movement rule says (README 7.2), clamps included; every cube face and floor
  tile is where the reference puts it THROUGH THE READER'S view matrix (so the composition order is judged); the center cube's
  pixels are centered on the screen; the frame stays inside its cycle budget."""
import math
import re
import shutil
import struct
import subprocess
from pathlib import Path

from harness import *

ROOT_DIR = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent

W, H = 320, 240
CX, CY = W // 2, H // 2
BG = (24, 24, 48)
BOOT = 45
N = 300
MARGIN = 700                      # |NCLIP| below this: nearly edge-on, not judged
TOL_CORNER = 3                    # px
OT_LEN = 64
OTZ_SHIFT = 7
COLS, ROWS, TILE = 8, 6, 2048
NF = 15
CENTRE = 1
FIELDS = ["x", "y", "z", "vy", "ax", "ay", "az", "sx", "sy", "sz", "size", "radius", "bounce", "colour", "bounces"]
FACES = [(0, 1, 2, 3), (5, 4, 7, 6), (4, 0, 6, 2), (1, 5, 3, 7), (4, 5, 0, 1), (2, 3, 6, 7)]
SHADE = [256, 208, 176, 232, 192, 160]
FLOOR_COLORS = [(72, 72, 96), (168, 168, 190)]
DEGEN = 1 / 32                    # sin(angle between forward and up) below this: up is "parallel" to forward
CENTRE_TOL = 16                   # px: the centroid of the center cube's pixels vs the screen center (other cubes may hide part of it)
NEAR_Z = 400                      # a corner nearer than this (view z) is not judged: the GTE gives garbage behind the eye


def pack(r, g, b):
    return r | g << 8 | b << 16


SHIPPED_OBJS = [
    [-4400, -3000 * 4096, -1200, 0, 300, 0, 120, 0, 56, 0, 1200, 1500, 3277, pack(224, 48, 48), 0],
    [0, -4000 * 4096, 1800, -60 * 4096, 0, 500, 200, 40, 0, 0, 1700, 2125, 2867, pack(48, 200, 64), 0],
    [4400, -2500 * 4096, 0, 30 * 4096, 700, 150, 0, 0, 0, -48, 2200, 2750, 3482, pack(64, 96, 240), 0],
]
GRAVITY, FLOOR_Y, PROJ_H = 4 * 4096, 4096, 256

SHIPPED = dict(
    objs=SHIPPED_OBJS, eye=(0, 0, -14336), up=(0, -4096, 0), speed=100,
    cmin=(-12000, -9000, -20000), cmax=(12000, 3000, -5000),
    inputs=[(60, "RIGHT", 40), (60, "L1", 25), (110, "UP", 50), (110, "R1", 30), (170, "LEFT", 60), (170, "DOWN", 20),
            (250, "LEFT", 10), (250, "RIGHT", 10)],
)
_p_objs = [list(o) for o in SHIPPED_OBJS]
_p_objs[CENTRE][0], _p_objs[CENTRE][2] = -2500, 3000
PATCHED = dict(
    objs=_p_objs, eye=(1000, -1000, -12000), up=(2000, -3000, 0), speed=250,
    cmin=(-3000, -3000, -13000), cmax=(3000, 1000, -9000),
    inputs=[(60, "RIGHT", 30), (60, "L1", 40), (100, "DOWN", 40), (100, "R1", 60), (170, "UP", 30)],
)
RUNS = {"base": (SHIPPED, N, False), "patched": (PATCHED, 230, True)}
# The first loop iteration that sees a button pressed at frame f is the one whose frame_done runs at vsync frame f + PRESS_LAG.
PRESS_LAG = 1

config(
    title="The Camera",
    build="cmake", exe="game.exe", sym="", elf="game.elf",
    break_at=None, max_frames=BOOT + N, timeout=40,
    inputs=SHIPPED["inputs"],
)

STATE = ["objects", "gravity", "floor_y", "proj_h", "cube", "faces", "face_shade", "floor_colors", "frame_no",
         "render_begin", "render_end", "frame_done", "cam_eye", "cam_target", "cam_up", "cam_speed", "cam_min", "cam_max",
         "view_mtx", "camera_look_at"]


# ---- the reference: the look-at matrix in floating point ------------------------------------------------------------------
def vsub(a, b): return [a[i] - b[i] for i in range(3)]
def dot(a, b): return sum(a[i] * b[i] for i in range(3))
def vcross(a, b): return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
def vlen(a): return math.sqrt(dot(a, a))
def vnorm(a):
    l = vlen(a)
    return [x / l for x in a]


def ref_view(eye, target, up):
    """Rows right, down, forward (as floats, unit) and the translation -R * eye. Also: sin of the angle used, and which up."""
    d = vsub(target, eye)
    f = [0.0, 0.0, 1.0] if not any(d) else vnorm(d)
    u = vnorm(up) if any(up) else None
    used = "given"
    if u is None or vlen(vcross(f, u)) < DEGEN:
        used = "fallback +z"
        u = [0.0, 0.0, 1.0]
        if vlen(vcross(f, u)) < DEGEN:
            used = "fallback -y"
            u = [0.0, -1.0, 0.0]
    r = vnorm(vcross(f, u))
    dn = vcross(f, r)
    rows = [r, dn, f]
    t = [-dot(rw, eye) for rw in rows]
    return rows, t, vlen(vcross(f, u)), used


def entry_tol(sin):
    """Allowed |difference| per matrix entry, in 1/4096. VectorNormalS is good to about 0.8% (it indexes a 192-entry table);
    one Newton step brings the reference solution to 3 or better. The cross product forward x up divides the 4.12 error of
    forward by sin(angle), hence the 1/sin term."""
    return 8 + math.ceil(2 / max(sin, 0.05))


def check_view(label, eye, target, up, m, t, need_exact_fallback=True):
    """m: 9 s16 row-major, t: 3 s32 -> raises CheckFailure unless it is the look-at of the reference."""
    rows, tref, sin, used = ref_view(eye, target, up)
    tol = entry_tol(sin)
    for i in range(3):
        for j in range(3):
            want = round(rows[i][j] * 4096)
            expect_true(abs(m[3 * i + j] - want) <= tol, f"{label}: view_mtx.m[{i}][{j}] = {want} (+-{tol}; row {i} = {['right', 'down', 'forward'][i]})",
                        str(m[3 * i + j]), "Rows are right, down, forward (README 5.2). Transposed? Negated? A swapped cross product?")
    mine = [m[0:3], m[3:6], m[6:9]]
    for i in range(3):
        want = -dot(mine[i], eye) / 4096
        expect_true(abs(t[i] - want) <= 3, f"{label}: view_mtx.t[{i}] = -(row {i} . eye) = {want:.1f} (+-3), from your own rows", str(t[i]),
                    "t = -R * eye: the eye is rotated like any other point, then negated. Not -eye, not +R*eye.")
        expect_true(abs(t[i] - tref[i]) <= abs(eye[0]) * tol / 4096 + abs(eye[1]) * tol / 4096 + abs(eye[2]) * tol / 4096 + 4,
                    f"{label}: view_mtx.t[{i}] = {tref[i]:.0f} (reference)", str(t[i]), "t = -R * eye.")
    return rows, used


def check_orthonormal(label, m):
    mine = [m[0:3], m[3:6], m[6:9]]
    for i in range(3):
        l2 = dot(mine[i], mine[i]) / 4096
        expect_true(abs(l2 - 4096) <= 48, f"{label}: row {i} has length 1.0 (|row|^2 / 4096 = 4096 +-48)", f"{l2:.0f}",
                    "Normalize right and forward; down = forward x right of two unit vectors needs no more.")
        for j in range(i + 1, 3):
            d = dot(mine[i], mine[j]) / 4096
            expect_true(abs(d) <= 48, f"{label}: rows {i} and {j} are perpendicular (dot / 4096 = 0 +-48)", f"{d:.0f}",
                        "right = normalize(forward x up) is perpendicular to forward by construction; down = forward x right.")
    det = dot(vcross(mine[0], mine[1]), mine[2]) / 4096 / 4096 / 4096
    expect_true(abs(det - 1) < 0.03, f"{label}: right x down = forward (a rotation, det +1)", f"det = {det:.3f}",
                "A mirror image (det -1): a swapped cross-product order or a negated row.")


# ---- the physics and the projection (Chapter 26's, with a view matrix) ---------------------------------------------------------
def isin(a):
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
        return 0x1FFFF
    z = 16 - sz.bit_length()
    n, d = h << z, sz << z
    u = UNR[(d - 0x7FC0) >> 7] + 0x101
    d = (0x2000080 - d * u) >> 8
    d = (0x0000080 + d * u) >> 8
    return min(0x1FFFF, (n * d + 0x8000) >> 16)


def sat(v, lo, hi):
    return max(lo, min(hi, v))


def rtps(m, t, v, h):
    mac = [((t[i] << 12) + sum(m[i][k] * v[k] for k in range(3))) >> 12 for i in range(3)]
    ir = [sat(x, -32768, 32767) for x in mac]
    sz = sat(mac[2], 0, 65535)
    n = gte_divide(h, sz) if sz else 0x1FFFF
    sx = sat((n * ir[0] + (CX << 16)) >> 16, -0x400, 0x3FF)
    sy = sat((n * ir[1] + (CY << 16)) >> 16, -0x400, 0x3FF)
    return sx, sy, sz


def nclip(p0, p1, p2):
    return p0[0] * p1[1] + p1[0] * p2[1] + p2[0] * p0[1] - p0[0] * p2[1] - p1[0] * p0[1] - p2[0] * p1[1]


def corner(i):
    return (4096 if i & 1 else -4096, 4096 if i & 2 else -4096, 4096 if i & 4 else -4096)


def ref_step(o, g, floor_y):
    x, y, z, vy, ax, ay, az, sx, sy, sz, size, radius, bounce, colour, bounces = o
    vy += g
    y += vy
    limit = (floor_y - radius) << 12
    if y > limit:
        y = limit
        vy = -((vy * bounce) >> 12)
        bounces += 1
    return [x, y, z, vy, (ax + sx) & 4095, (ay + sy) & 4095, (az + sz) & 4095, sx, sy, sz, size, radius, bounce, colour, bounces]


def view_parts(row):
    return [list(row.m[0:3]), list(row.m[3:6]), list(row.m[6:9])], list(row.t)


def object_matrix(o, view):
    """Chapter 26's object matrix composed with the view: R = Rv * Rw, T = Rv * Tw + Tv (what CompMatrixLV(&view, &obj, &out) does)."""
    rv, tv = view
    m = rot_matrix(o[4], o[5], o[6])
    m = [[sat((m[i][j] * o[10]) >> 12, -32768, 32767) for j in range(3)] for i in range(3)]
    tw = (o[0], o[1] >> 12, o[2])
    r = matmul(rv, m)
    t = tuple(sum(rv[i][k] * tw[k] for k in range(3)) // 4096 + tv[i] for i in range(3))
    return r, t


def colour_rgb(c):
    return (c & 255, (c >> 8) & 255, (c >> 16) & 255)


def face_rgb(o, f):
    return tuple((v * SHADE[f]) >> 8 for v in colour_rgb(o[13]))


def ref_cube(o, view):
    m, t = object_matrix(o, view)
    pts = [rtps(m, t, corner(i), PROJ_H) for i in range(8)]
    xy = [(p[0], p[1]) for p in pts]
    sz = [p[2] for p in pts]
    areas = [nclip(xy[f[0]], xy[f[1]], xy[f[2]]) for f in FACES]
    ok = all(s >= NEAR_Z for s in sz) and all(abs(p[0]) < 1000 and abs(p[1]) < 1000 for p in xy)
    return dict(xy=xy, sz=sz, areas=areas, ok=ok)


def ref_floor(view):
    rv, tv = view
    v = [[rtps(rv, tv, ((c - COLS // 2) * TILE, FLOOR_Y, (r - ROWS // 2) * TILE), PROJ_H) for c in range(COLS + 1)] for r in range(ROWS + 1)]
    tiles = []
    for r in range(ROWS):
        for c in range(COLS):
            cs = [v[r + 1][c], v[r + 1][c + 1], v[r][c], v[r][c + 1]]
            ok = all(p[2] >= NEAR_Z and abs(p[0]) < 1000 and abs(p[1]) < 1000 for p in cs)
            tiles.append(dict(r=r, c=c, xy=[(p[0], p[1]) for p in cs], parity=(r + c) & 1, ok=ok))
    return tiles


def ref_slot(sz4):
    otz = sat((256 * sum(sz4)) >> 12, 0, 65535)
    return sat(otz >> OTZ_SHIFT, 0, OT_LEN - 1)


# ---- reading the runs ------------------------------------------------------------------------------------------------------------
def patches_for(d):
    return {
        "objects": b"".join(struct.pack("<15i", *o) for o in d["objs"]),
        "cam_eye": words(*d["eye"]), "cam_up": words(*d["up"]), "cam_speed": words(d["speed"]),
        "cam_min": words(*d["cmin"]), "cam_max": words(*d["cmax"]),
    }


def run_of(ctx, name):
    d, n, patch = RUNS[name]
    if not patch:
        return ctx.result, d, n
    return ctx.run(name, patches=patches_for(d), inputs=d["inputs"], max_frames=BOOT + n), d, n


class Row:
    def __init__(self, r):
        self.n, self.vf = r[0], r[1]
        self.objs = [list(r[2 + NF * i: 2 + NF * (i + 1)]) for i in range(3)]
        b = 2 + 3 * NF
        self.eye, self.target, self.up = list(r[b:b + 3]), list(r[b + 3:b + 6]), list(r[b + 6:b + 9])
        self.m, self.t = list(r[b + 9:b + 18]), list(r[b + 18:b + 21])
        self.cycles = r[b + 21]
        flat = r[b + 22] if isinstance(r[b + 22], list) else []
        self.quads = [dict(slot=flat[i], code=flat[i + 1], rgb=tuple(flat[i + 2:i + 5]), xy=list(flat[i + 5:i + 13])) for i in range(0, len(flat), 13)]

    def view(self):
        return [list(self.m[0:3]), list(self.m[3:6]), list(self.m[6:9])], list(self.t)


def observe(ctx, name):
    r, d, n = run_of(ctx, name)
    raw = r.record("rows") or []
    expect_true(len(raw) >= n - 10, f"{name}: frame_done() is called every frame ({n - 10}+ times observed)",
                f"{len(raw)} calls" + exception_text(r.record("exception")),
                "main's loop (given) calls frame_done() after frame_no++ and display_swap(); did the program get there? "
                "An arithmetic overflow: VectorNormalS fed a vector whose squares sum to 2^31 or more (README 5.5).")
    rows = [Row(x) for x in raw]
    expect_eq([x.n for x in rows], list(range(1, len(rows) + 1)), f"{name}: frame_no at each frame_done() call", hint="frame_no counts the frames the loop completed.")
    return r, d, rows, r.record("tables")


def clampv(v, lo, hi):
    return [max(lo[i], min(hi[i], v[i])) for i in range(3)]


def held_at(script, vf):
    """The set of button names the harness holds for the loop iteration whose frame_done() runs at vsync frame vf."""
    return {b for (f, b, n) in script if f + PRESS_LAG <= vf < f + n + PRESS_LAG}


def simulate_eye(d, rows):
    """Replay README 7.2's movement rule from the start eye, with the held set of every frame; returns the eye after each frame."""
    eye = list(d["eye"])
    out = []
    for x in rows:
        h = held_at(d["inputs"], x.vf)
        dx = ("RIGHT" in h) - ("LEFT" in h)
        dy = ("R1" in h) - ("L1" in h)
        dz = ("UP" in h) - ("DOWN" in h)
        eye = clampv([eye[0] + dx * d["speed"], eye[1] + dy * d["speed"], eye[2] + dz * d["speed"]], d["cmin"], d["cmax"])
        out.append(list(eye))
    return out


def near(a, b, tol):
    return all(abs(p - q) <= tol for p, q in zip(a, b))


# ---- static checks -----------------------------------------------------------------------------------------------------------------
@static_check("the state symbols exist", hint="Keep the starter's declarations, the keep-alive `__asm__ volatile(...)` line in main, the three marker functions, and `camera_look_at` (noinline).")
def _(ctx):
    miss = ctx.symbols.require(*STATE)
    if miss:
        raise CheckFailure(
            expected="symbols defined: " + ", ".join(STATE), actual="missing: " + ", ".join(miss),
            hint="The linker drops data nothing reads. Keep the starter's declarations and the `__asm__ volatile(...)` line "
                 "that keeps them alive; define camera_look_at as a global, non-inline function.")


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
              hint="Scanned: every .obj of your project and of psxe/ (never the SDK's libraries). The scene code of Chapter 26 stays on the GTE.")
def _(ctx):
    objdump = _tool("mipsel-none-elf-objdump")
    seen = set()
    for o in _objects(ctx):
        dis = subprocess.run([objdump, "-d", str(o)], capture_output=True, text=True).stdout
        for m in re.finditer(r"\t(?:cop2|c2)\s+0x([0-9a-fA-F]+)", dis):
            seen.add(int(m.group(1), 16) & 0x3F)
    names = {COP2_NAMES[c] for c in seen if c in COP2_NAMES}
    expect_true(names & {"RTPS", "RTPT"}, "a perspective transform command (RTPS or RTPT)", f"GTE commands found: {sorted(names) or 'none'}", "gte_rtps().")
    expect_true("NCLIP" in names, "a normal-clip command (NCLIP)", f"GTE commands found: {sorted(names)}", "gte_nclip().")
    expect_true(names & {"AVSZ3", "AVSZ4"}, "an average-Z command (AVSZ3 or AVSZ4)", f"GTE commands found: {sorted(names)}", "gte_avsz4().")


@static_check("integers only: no floating point in the program's objects (the camera is fixed point too)",
              hint="Soft-float helpers (__mulsf3, __floatsisf, ...) in your objects mean a float or double crept in.")
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


# ---- direct calls ----------------------------------------------------------------------------------------------------------------------
def direct_calls(ctx):
    r = ctx.run("direct", probe=str(HERE / "direct.lua"), inputs=(), max_frames=BOOT + 80, break_at=None)
    calls = r.record("calls") or []
    bad = next((c for c in calls if c.get("exception")), None)
    if bad:
        raise CheckFailure(expected=f"{label_of(bad)} returns", actual="it raised a CPU exception" + exception_text(bad["exception"]),
                           hint="Arithmetic overflow inside VectorNormalS: its input's x*x + y*y + z*z must stay below 2^31 (and each "
                                "component within +-32767). Shift the vector right first (README 5.5).")
    expect_true(len(calls) >= 30, "camera_look_at was called at least 30 times by the probe", f"{len(calls)} calls",
                "Define `void camera_look_at(const VECTOR *eye, const VECTOR *target, const VECTOR *up)` as a global, non-inline function and call it from main's loop.")
    return calls


def label_of(c):
    return f"camera_look_at(eye {tuple(c['eye'])}, target {tuple(c['target'])}, up {tuple(c['up'])})"


@check("camera_look_at is a well-behaved C function: it returns, keeps $s0-$s7/$fp/$sp, and leaves eye, target and up unchanged",
       hint="The probe calls it with the O32 convention (pointers in $a0-$a2) and sentinel values in the callee-saved registers.")
def _(ctx):
    for c in direct_calls(ctx):
        expect_true(c.get("returned"), f"{label_of(c)} returns", "did not return")
        expect_true(c["kept"], f"{label_of(c)} preserves $s0-$s7, $fp, $sp", "a callee-saved register changed",
                    "Registers $s0-$s7 must be saved and restored by a function that uses them; the compiler does it for you in C.")
        expect_eq((c["eye2"], c["target2"], c["up2"]), (c["eye"], c["target"], c["up"]), f"{label_of(c)}: the arguments are const",
                  hint="Do not normalize or write into the caller's vectors; copy them first.")


@check("the view matrix: rows right, down, forward and t = -R * eye match the float reference for 30+ triples (axes, rolls, |up| tiny and huge, 32000-unit differences)",
       hint="The five look-at steps of README 5.4, with the rows and t of README 7.2.")
def _(ctx):
    n = 0
    for c in direct_calls(ctx):
        rows, tref, sin, used = ref_view(c["eye"], c["target"], c["up"])
        if used != "given" or not any(vsub(c["target"], c["eye"])):
            continue
        check_view(label_of(c), c["eye"], c["target"], c["up"], c["view"][:9], c["view"][9:])
        n += 1
    expect_true(n >= 28, "at least 28 ordinary triples were judged", str(n))


@check("degenerate cases: up parallel to forward (and up = 0) falls back to +z, then -y; eye == target looks along +z; the result is still a rotation",
       hint="The fallback table of README 5.4: test |forward x up| against 1/32 with both vectors normalized, and never feed a zero vector to the normalizer.")
def _(ctx):
    n = 0
    for c in direct_calls(ctx):
        rows, tref, sin, used = ref_view(c["eye"], c["target"], c["up"])
        if used == "given" and any(vsub(c["target"], c["eye"])):
            continue
        check_view(label_of(c) + f" [{used}]", c["eye"], c["target"], c["up"], c["view"][:9], c["view"][9:])
        n += 1
    expect_true(n >= 6, "the degenerate triples were judged (up = forward, up = -forward, sin 1/64, +z also parallel, eye == target, no up)", str(n))


@check("every result is orthonormal and right-handed: unit rows, mutually perpendicular, right x down = forward",
       hint="One Newton step after VectorNormalS keeps the rows within 1%; down = forward x right (unit vectors) needs no extra normalize.")
def _(ctx):
    for c in direct_calls(ctx):
        check_orthonormal(label_of(c), c["view"][:9])


# ---- the program's camera ----------------------------------------------------------------------------------------------------------------
@check("every frame: view_mtx is camera_look_at's answer for the recorded cam_eye, cam_target and cam_up (shipped and patched start)",
       hint="Per frame: update the eye, set cam_target, call camera_look_at(&cam_eye, &cam_target, &cam_up) BEFORE drawing, and draw with view_mtx.")
def _(ctx):
    for name in ("base", "patched"):
        r, d, rows, t = observe(ctx, name)
        expect_eq(t["gravity"], GRAVITY, f"{name}: gravity", hint="Do not change the scene tables.")
        expect_eq(t["cube"], [v for i in range(8) for v in (*corner(i), 0)], f"{name}: cube[]", hint="Do not change the cube table.")
        for x in rows[::3]:
            check_view(f"{name}, frame {x.n}", x.eye, x.target, x.up, x.m, x.t)
        check_orthonormal(f"{name}, last frame", rows[-1].m)
        expect_eq(rows[0].up, list(d["up"]), f"{name}: cam_up is never written by the program", hint="cam_up is input.")


@check("the camera looks at the center cube: every frame cam_target == (x, y >> 12, z) of objects[1]",
       hint="Set cam_target after update_objects(), from the center cube's position in plain units; its y is stored as 20.12 (README 7.2).")
def _(ctx):
    for name in ("base", "patched"):
        r, d, rows, t = observe(ctx, name)
        for x in rows:
            o = x.objs[CENTRE]
            expect_eq(x.target, [o[0], o[1] >> 12, o[2]], f"{name}, frame {x.n}: cam_target", hint="Use the cube's CURRENT position (after this frame's update) and y >> 12.")
        moved = {x.target[1] for x in rows}
        expect_true(len(moved) > 20, f"{name}: the target follows the bouncing cube (more than 20 different heights)", str(len(moved)))


@check("the pad moves the eye exactly: D-pad = x/z, R1 lowers, L1 raises, cam_speed per frame, opposite buttons cancel, clamped to [cam_min, cam_max]",
       hint="The movement rule of README 7.2: one axis per button pair (y points down), cam_speed per frame, then clamp each component.")
def _(ctx):
    for name in ("base", "patched"):
        r, d, rows, t = observe(ctx, name)
        expect_eq(t["speed"], d["speed"], f"{name}: cam_speed is read, not written", hint="Do not write cam_speed.")
        sim = simulate_eye(d, rows)
        for x, want in zip(rows, sim):
            held = sorted(held_at(d["inputs"], x.vf))
            expect_eq(x.eye, want, f"{name}, frame {x.n} (vsync {x.vf}, buttons {held}): cam_eye", hint=
                      "README 7.2: each held direction moves its axis by cam_speed, opposite buttons cancel, then each component is clamped to [cam_min, cam_max]. "
                      "input_update() once per frame, input_held() for the buttons.")
        if name == "patched":
            final = sim[-1]
            expect_true(final[2] == d["cmax"][2] or any(s[2] == d["cmin"][2] for s in sim), "patched: the script reaches the z clamps (checker design)", str(final))
            for axis, key in enumerate("xyz"):
                hit = [s[axis] for s in sim if s[axis] in (d["cmin"][axis], d["cmax"][axis])]
                expect_true(hit, f"patched: the script runs into a clamp on {key} (checker design)", "none")
        else:
            moved = [i for i in range(1, len(rows)) if rows[i].eye != rows[i - 1].eye]
            expect_true(len(moved) >= 100, "base: the eye moves on at least 100 frames (checker design)", str(len(moved)))


@check("the view reaches every object: cube faces and floor tiles are where the reference puts them THROUGH YOUR view matrix (+-3 px), hidden faces are absent",
       hint="Floor: the view matrix alone. Cubes: the object's matrix composed with the view, view first (README 5.6).")
def _(ctx):
    judged_faces = judged_tiles = 0
    for name in ("base", "patched"):
        r, d, rows, t = observe(ctx, name)
        for x in rows[::2]:
            view = x.view()
            floor_q = [q for q in x.quads if q["slot"] == OT_LEN - 1]
            cube_q = [q for q in x.quads if q["slot"] != OT_LEN - 1]
            seen = {}
            for q in cube_q:
                key = None
                for i in range(3):
                    for f in range(6):
                        if near(q["rgb"], face_rgb(x.objs[i], f), 1):
                            key = (i, f)
                expect_true(key is not None, f"{name}, frame {x.n}: every cube quad has a face color", str(q["rgb"]), "color channel * face_shade[f] >> 8.")
                seen[key] = q
            for i in range(3):
                rc = ref_cube(x.objs[i], view)
                if not rc["ok"]:
                    continue
                for f in range(6):
                    a = rc["areas"][f]
                    q = seen.get((i, f))
                    if abs(a) < MARGIN:
                        continue
                    judged_faces += 1
                    if a > 0:
                        want = [v for c in FACES[f] for v in rc["xy"][c]]
                        expect_true(q is not None, f"{name}, frame {x.n}: object {i} face {f} faces the camera (NCLIP {a}) and is drawn", "not drawn",
                                    "Back-face culling uses the screen-space NCLIP; it only works if the view matrix was applied before RTPS.")
                        expect_true(near(q["xy"], want, TOL_CORNER), f"{name}, frame {x.n}: object {i} face {f} corners {want} (+-{TOL_CORNER} px)", str(q["xy"]),
                                    "Composition order (README 5.6): the view goes first; the other order applies the cube's rotation and size to the camera's translation.")
                        expect_true(q["slot"] < OT_LEN - 1, f"{name}, frame {x.n}: object {i} face {f} is nearer than the floor", f"slot {q['slot']}")
                    else:
                        expect_true(q is None, f"{name}, frame {x.n}: object {i} face {f} points away (NCLIP {a}) and is not drawn", "drawn", "A face is drawn only if its NCLIP is positive.")
            left = list(floor_q)
            for tl in ref_floor(view):
                if not tl["ok"]:
                    continue
                want = [v for p in tl["xy"] for v in p]
                a = nclip(tl["xy"][0], tl["xy"][1], tl["xy"][2])
                if a <= 0:
                    continue
                hit = next((q for q in left if near(q["xy"], want, TOL_CORNER)), None)
                expect_true(hit is not None, f"{name}, frame {x.n}: floor tile (col {tl['c']}, row {tl['r']}) has a quad with corners {want} (+-{TOL_CORNER} px)", "none",
                            "The floor is object zero: its matrix is the view matrix itself (identity world).")
                left.remove(hit)
                judged_tiles += 1
    expect_true(judged_faces >= 400, "enough cube faces were judged (checker design)", str(judged_faces))
    expect_true(judged_tiles >= 1500, "enough floor tiles were judged (checker design)", str(judged_tiles))


# ---- the picture ------------------------------------------------------------------------------------------------------------------------------
def green_pixels(img):
    """(count, mean x, mean y) of the pixels colored like the center cube's faces (g well above r and b)."""
    sx = sy = n = 0
    for y in range(img.height):
        for x in range(img.width):
            r_, g_, b_ = img.pixel(x, y)
            if g_ > r_ + 50 and g_ > b_ + 50:
                sx += x
                sy += y
                n += 1
    return n, (sx / n if n else 0), (sy / n if n else 0)


@check(f"picture: the center cube's pixels are centered on the screen, whatever the eye does (centroid within {CENTRE_TOL} px of ({CX}, {CY}))",
       hint="The view matrix must turn the eye->target direction into +z: the target then projects to the screen center. A fixed camera, or a transposed or un-translated view, drifts as the eye moves.")
def _(ctx):
    judged = 0
    for name, shots in (("base", (3, 60, 100, 140, 180, 215, 260, 295)), ("patched", (3, 60, 100, 140, 180, 215))):
        r, d, rows, t = observe(ctx, name)
        for fr in shots:
            img = r.screenshot(f"f{fr}")
            expect_true((img.width, img.height) == (W, H), "the picture is 320 x 240", f"{img.width} x {img.height}")
            expect_true(colors_close(img.pixel(0, 0), BG, 12), f"{name}, frame {fr}: corner (0, 0) is the background {BG}", str(img.pixel(0, 0)), "display_clear(24, 24, 48) every frame.")
            x = rows[fr - 1]
            n, mx, my = green_pixels(img)
            judged += 1
            expect_true(n >= 300, f"{name}, frame {fr}: the center cube is visible (300+ pixels)", f"{n} pixels")
            expect_true(abs(mx - CX) <= CENTRE_TOL and abs(my - CY) <= CENTRE_TOL,
                        f"{name}, frame {fr} (eye {x.eye}): centroid of the center cube ({n} px) within {CENTRE_TOL} px of ({CX}, {CY})", f"({mx:.1f}, {my:.1f})",
                        "The target must land in the middle of the screen. Check the sign of the translation and the order of the rows.")
    expect_true(judged == 14, "all 14 screenshots were judged (checker design)", str(judged))


@check("the scene is still Chapter 26's: the integer physics of all three cubes matches the model, every frame",
       hint="The camera must not disturb update_objects().")
def _(ctx):
    for name in ("base", "patched"):
        r, d, rows, t = observe(ctx, name)
        cur = [list(o) for o in d["objs"]]
        for x in rows:
            cur = [ref_step(o, GRAVITY, FLOOR_Y) for o in cur]
            expect_eq(x.objs, cur, f"{name}, frame {x.n}: objects[]", hint="Update order: vy += g; y += vy; floor test; spin.")


SOLUTION_CYCLES = 34300
BUDGET = 2 * SOLUTION_CYCLES


@check("frame time: CPU cycles between render_begin() and render_end() stay under the budget",
       hint="One camera_look_at per frame (not per object), one matrix per object.")
def _(ctx):
    r, d, rows, t = observe(ctx, "base")
    cyc = sorted(x.cycles for x in rows[1:])
    med = cyc[len(cyc) // 2]
    expect_true(med > 0, "render_begin() and render_end() were reached", "0 cycles", "Keep the markers in main's loop around the 3D work.")
    expect_true(max(cyc) <= BUDGET, f"cycles per frame <= {BUDGET} (the reference solution needs about {SOLUTION_CYCLES})", f"median {med}, worst {max(cyc)}", "Call camera_look_at once per frame.")
