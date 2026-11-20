"""Chapter 25 checks: The GTE Coprocessor ("Solid Cube").
Build: CMake + PSn00bSDK.
STATIC: the state symbols exist; the program's OWN objects (project + psxe, never the SDK's libraries) contain GTE commands
(RTPS or RTPT, NCLIP, AVSZ3 or AVSZ4) and do not call the CPU maths of Chapter 23 (fx_mul/fx_div/fx_rotate); no floating
point; the reference solution's psxe mirrors common/psxe.
DYNAMIC (probe.lua): every time the program calls frame_done() the probe records the angles, the matrix the program uploaded,
the eight projected corners and depths, the GTE flags, the counters, the CPU cycles spent between render_begin() and
render_end(), and the quads found by WALKING the ordering table handed to DrawOTag (slot, colour, four corners).
The Python reference below is the contract of README section 7:
  * the matrix is RotMatrix's (Rx * Ry * Rz, SDK isin/icos), translation (0, 0, cam_z);
  * the corners are projected exactly as the GTE's RTPS does (the 'unr' divider ported from psx-spx);
  * a face is drawn iff NCLIP of its corners 0, 1, 2 is positive; the reference decides it from the REFERENCE matrix, so a face
    whose area is within a margin of zero (edge-on) is not judged;
  * a drawn quad goes to OT slot clamp((SZ0+SZ1+SZ2+SZ3) / 4 / 4 >> 7) (AVSZ4 with ZSF4 = 256, shifted by 7), +-1.
Runs: shipped numbers (120 frames); six poses with the rotation frozen (screenshots at face centres, a grid scan for hidden
colours); a recoloured pose; patched lens, cube size, speeds and a third axis; a cube straddling the camera (GTE flags)."""
import math
import re
import shutil
import struct
import subprocess
from pathlib import Path

from harness import *

ROOT_DIR = Path(__file__).resolve().parents[4]

W, H = 320, 240
CX, CY = W // 2, H // 2
BG = (16, 16, 32)
N = 120
BOOT = 45                         # frames the SDK needs before main (about 34) plus margin
MARGIN = 700                      # |NCLIP| below this: the face is nearly edge-on, not judged
TOL_XY = 1
OT_LEN = 64
OTZ_SHIFT = 7

SHIPPED = dict(size=4096, step=(24, 40, 0), rot=(128, 256, 0), cam_z=6 * 4096, h=256)
FACES = [(0, 1, 2, 3), (5, 4, 7, 6), (4, 0, 6, 2), (1, 5, 3, 7), (4, 5, 0, 1), (2, 3, 6, 7)]
COLORS = [(224, 48, 48), (48, 200, 64), (64, 96, 240), (240, 220, 48), (220, 64, 220), (48, 220, 220)]
RECOLOR = [COLORS[3], COLORS[5], COLORS[0], COLORS[4], COLORS[1], COLORS[2]]
POSES = [(1050, 500, 0), (3050, 1600, 2050), (650, 450, 250), (1050, 2900, 300), (2550, 2500, 2150), (250, 1450, 1200)]
LENS = dict(size=5000, step=(-37, 61, 53), rot=(1000, 3000, 2000), cam_z=22528, h=200)

config(
    title="The GTE Coprocessor",
    build="cmake", exe="game.exe", sym="", elf="game.elf",
    break_at=None, max_frames=BOOT + N,
)

STATE = ["cube", "faces", "face_colors", "rot", "rot_step", "cam_z", "proj_h", "mtx", "screen_xy", "screen_z", "gte_flags",
         "prims_submitted", "faces_drawn", "face_mask", "frame_no", "render_begin", "render_end", "frame_done"]


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
    """RotMatrix(): Rx * Ry * Rz, so a vector is turned about Z first, then Y, then X."""
    sx, cx, sy, cy, sz, cz = isin(ax), icos(ax), isin(ay), icos(ay), isin(az), icos(az)
    X = [[4096, 0, 0], [0, cx, -sx], [0, sx, cx]]
    Y = [[cy, 0, sy], [0, 4096, 0], [-sy, 0, cy]]
    Z = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 4096]]
    return matmul(matmul(X, Y), Z)


UNR = [max(0, (0x40000 // (i + 0x100) + 1) // 2 - 0x101) for i in range(0x101)]


def gte_divide(h, sz):
    """The GTE's reciprocal-based divide (psx-spx 'GTE Division Inaccuracy'): about h * 65536 / sz, saturated to 0x1FFFF."""
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
    """RTPS with sf = 1: returns (sx, sy, sz, divide_overflow)."""
    mac = [((t[i] << 12) + sum(m[i][k] * v[k] for k in range(3))) >> 12 for i in range(3)]
    ir = [sat(x, -32768, 32767) for x in mac]
    sz = sat(mac[2], 0, 65535)
    n, ovf = gte_divide(h, sz)
    sx = sat((n * ir[0] + (CX << 16)) >> 16, -0x400, 0x3FF)
    sy = sat((n * ir[1] + (CY << 16)) >> 16, -0x400, 0x3FF)
    return sx, sy, sz, ovf


def nclip(p0, p1, p2):
    return p0[0] * p1[1] + p1[0] * p2[1] + p2[0] * p0[1] - p0[0] * p2[1] - p1[0] * p0[1] - p2[0] * p1[1]


def corner(i, size):
    return (size if i & 1 else -size, size if i & 2 else -size, size if i & 4 else -size)


def ref_slot(sz4):
    otz = sat((256 * sum(sz4)) >> 12, 0, 65535)
    return sat(otz >> OTZ_SHIFT, 0, OT_LEN - 1)


def ref_frame(d, k):
    """Everything the reference says about frame k of a run described by d."""
    ang = [(d["rot"][i] + k * d["step"][i]) & 4095 for i in range(3)]
    m = rot_matrix(*ang)
    t = (0, 0, d["cam_z"])
    pts = [rtps(m, t, corner(i, d["size"]), d["h"]) for i in range(8)]
    xy = [(p[0], p[1]) for p in pts]
    areas = [nclip(xy[f[0]], xy[f[1]], xy[f[2]]) for f in FACES]
    return dict(ang=ang, m=m, xy=xy, sz=[p[2] for p in pts], areas=areas, ovf=any(p[3] for p in pts))


# ---- reading the runs ------------------------------------------------------------------------------------------------------
def sv(*a):
    return struct.pack("<4h", *a, 0)


def patches_for(colors=None, **kw):
    d = dict(SHIPPED, **kw)
    p = {
        "cube": b"".join(sv(*corner(i, d["size"])) for i in range(8)),
        "rot": sv(*d["rot"]), "rot_step": sv(*d["step"]),
        "cam_z": words(d["cam_z"]), "proj_h": words(d["h"]),
    }
    if colors:
        p["face_colors"] = bytes(v for c in colors for v in c)
    return p


def run_of(ctx, name):
    if name == "base":
        return ctx.result, dict(SHIPPED, colors=COLORS), N
    if name == "lens":
        d = dict(SHIPPED, **LENS, colors=COLORS)
        return ctx.run("lens", patches=patches_for(**LENS), max_frames=BOOT + 70), d, 70
    if name == "flags":
        d = dict(SHIPPED, cam_z=3000, colors=COLORS)
        return ctx.run("flags", patches=patches_for(cam_z=3000), max_frames=BOOT + 12), d, 12
    if name.startswith("pose"):
        i = int(name[4:])
        d = dict(SHIPPED, rot=POSES[i], step=(0, 0, 0), colors=COLORS)
        return ctx.run(name, patches=patches_for(rot=POSES[i], step=(0, 0, 0)), max_frames=BOOT + 8), d, 8
    if name == "recolor":
        i = 4
        d = dict(SHIPPED, rot=POSES[i], step=(0, 0, 0), colors=RECOLOR)
        return ctx.run(name, patches=patches_for(rot=POSES[i], step=(0, 0, 0), colors=RECOLOR), max_frames=BOOT + 8), d, 8
    raise KeyError(name)


def rows_of(r, what, n):
    rows = r.record("rows") or []
    expect_true(len(rows) >= n - 10, f"{what}: frame_done() is called every frame ({n - 10}+ times observed)",
                f"{len(rows)} calls", "main's loop (given) calls frame_done() after frame_no++ and display_swap(); did the program get there?")
    return rows


class Row:
    def __init__(self, r):
        self.n = r[0]
        self.rot = tuple(r[1:4])
        self.m = [r[4:7], r[7:10], r[10:13]]
        self.t = tuple(r[13:16])
        self.xy = [(r[16 + 2 * i], r[17 + 2 * i]) for i in range(8)]
        self.sz = list(r[32:40])
        self.flags, self.prims, self.drawn, self.mask, self.cycles = r[40], r[41], r[42], r[43], r[44]
        flat = r[45] if isinstance(r[45], list) else []
        self.quads = [dict(slot=flat[i], code=flat[i + 1], rgb=tuple(flat[i + 2:i + 5]), xy=list(flat[i + 5:i + 13]))
                      for i in range(0, len(flat), 13)]


def observe(ctx, name):
    r, d, n = run_of(ctx, name)
    rows = [Row(x) for x in rows_of(r, name, n)]
    t = r.record("tables")
    return r, d, rows, t


def face_of_rgb(colors, rgb):
    for f, c in enumerate(colors):
        if max(abs(a - b) for a, b in zip(c, rgb)) <= 10:
            return f
    return None


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
              hint="Scanned: every .obj of your project and of psxe/ (never the SDK's libraries). Use gte_rtps()/gte_rtpt(), gte_nclip() and gte_avsz3()/gte_avsz4() (README 5.3 to 5.9).")
def _(ctx):
    objdump = _tool("mipsel-none-elf-objdump")
    seen = set()
    for o in _objects(ctx):
        dis = subprocess.run([objdump, "-d", str(o)], capture_output=True, text=True).stdout
        for m in re.finditer(r"\t(?:cop2|c2)\s+0x([0-9a-fA-F]+)", dis):
            seen.add(int(m.group(1), 16) & 0x3F)
    names = {COP2_NAMES[c] for c in seen if c in COP2_NAMES}
    expect_true(names & {"RTPS", "RTPT"}, "a perspective transform command (RTPS or RTPT)", f"GTE commands found: {sorted(names) or 'none'}",
                "gte_rtps() transforms one corner: gte_ldv0(&cube[i]); gte_rtps(); gte_stsxy(...).")
    expect_true("NCLIP" in names, "a normal-clip command (NCLIP)", f"GTE commands found: {sorted(names)}", "gte_nclip() after loading three screen points with gte_ldsxy3.")
    expect_true(names & {"AVSZ3", "AVSZ4"}, "an average-Z command (AVSZ3 or AVSZ4)", f"GTE commands found: {sorted(names)}",
                "gte_avsz4() after gte_ldsz4: the depth of the quad.")


@static_check("the CPU does not redo the GTE's work: main calls no fx_mul, fx_div or fx_rotate",
              hint="Chapter 24's software pipeline is what the GTE replaces. Do not call psxe/fixed.h's arithmetic in the render path.")
def _(ctx):
    nm = _tool("mipsel-none-elf-nm")
    for o in _objects(ctx):
        if o.name.startswith("main"):
            und = set(subprocess.run([nm, "--undefined-only", str(o)], capture_output=True, text=True).stdout.split())
            bad = sorted(und & {"fx_mul", "fx_div", "fx_rotate", "fx_lerp", "fx_sqrt"})
            expect_true(not bad, f"{o.name} references no CPU fixed-point routine", f"references {bad}")


@static_check("integers only: no floating point in the program's objects",
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


# ---- dynamic checks -----------------------------------------------------------------------------------------------------------
def check_tables(name, d, t, colors_expected):
    expect_eq(t["faces"], [v for f in FACES for v in f], f"{name}: faces[] at frame 1", hint="Do not change the face table: it is part of the contract.")
    expect_eq(t["colors"], [v for c in colors_expected for v in c], f"{name}: face_colors[] at frame 1", hint="Do not change the colour table.")
    expect_eq(t["cube"], [v for i in range(8) for v in (*corner(i, d["size"]), 0)], f"{name}: cube[] at frame 1", hint="Do not change the cube table.")
    expect_eq(t["cam_z"], d["cam_z"], f"{name}: cam_z", hint="Read it, do not write it.")
    expect_eq(t["proj_h"], d["h"], f"{name}: proj_h", hint="Read it, do not write it.")
    expect_eq(t["step"], list(d["step"]), f"{name}: rot_step", hint="Read it, do not write it.")


def check_frames(ctx, name):
    r, d, rows, t = observe(ctx, name)
    check_tables(name, d, t, d["colors"])
    expect_eq([x.n for x in rows], list(range(1, len(rows) + 1)), f"{name}: frame_no at each frame_done() call",
              hint="frame_no is 1 at the first call and grows by 1 per frame; main's loop (given) does it.")
    for x in rows:
        exp = tuple((d["rot"][i] + x.n * d["step"][i]) & 4095 for i in range(3))
        expect_true(x.rot == exp, f"{name}: rot at frame {x.n} = {exp}", str(x.rot),
                    "update_angles(): add rot_step to rot every frame and keep each angle in 0..4095 with `& 4095` (steps may be negative).")
    return r, d, rows, t


def check_counters(name, d, rows):
    total = 0
    for x in rows:
        total += x.prims
        expect_true(0 <= x.prims <= 3, f"{name}, frame {x.n}: prims_submitted is 0..3 (a convex cube shows at most 3 faces)", str(x.prims),
                    "Cull the faces whose NCLIP is not positive before building a quad.")
        expect_eq(x.drawn, total, f"{name}, frame {x.n}: faces_drawn is the running total of prims_submitted",
                  hint="prims_submitted counts this frame (reset each frame); faces_drawn counts since start.")
        expect_eq(bin(x.mask).count("1"), x.prims, f"{name}, frame {x.n}: face_mask has one bit per quad submitted",
                  hint="Set bit f of face_mask for each face f you link into the table; clear it every frame.")
        expect_eq(len(x.quads), x.prims, f"{name}, frame {x.n}: quads found in the ordering table = prims_submitted",
                  hint="Every quad you count must be linked with ot_add, and nothing else may be.")


def check_matrix(ctx, name):
    r, d, rows, t = check_frames(ctx, name)
    for x in rows:
        ref = rot_matrix(*x.rot)
        worst = max(abs(x.m[i][j] - ref[i][j]) for i in range(3) for j in range(3))
        expect_true(worst <= 4, f"{name}, frame {x.n}: mtx = RotMatrix(rot) (max difference {worst} <= 4)",
                    f"mtx = {x.m}, reference = {ref}", "RotMatrix(&rot, &mtx), then TransMatrix; rot holds the angles in 4096 units per turn.")
        expect_eq(x.t, (0, 0, d["cam_z"]), f"{name}, frame {x.n}: mtx translation", hint="TransMatrix(&mtx, &pos) with pos = (0, 0, cam_z).")


def check_projection(ctx, name):
    r, d, rows, t = check_frames(ctx, name)
    for x in rows:
        m = [list(row) for row in x.m]
        ref = [rtps(m, x.t, corner(i, d["size"]), d["h"]) for i in range(8)]
        for i in range(8):
            gx, gy, gz = x.xy[i][0], x.xy[i][1], x.sz[i]
            ok = abs(gx - ref[i][0]) <= TOL_XY and abs(gy - ref[i][1]) <= TOL_XY and gz == ref[i][2]
            if not ok:
                why = ""
                if abs(gx - (ref[i][0] - CX)) <= 2 and abs(gy - (ref[i][1] - CY)) <= 2:
                    why = " The screen offset (160, 120) is missing: gte_SetGeomOffset."
                raise CheckFailure(
                    expected=f"{name}, frame {x.n}: corner {i} at ({ref[i][0]}, {ref[i][1]}) depth {ref[i][2]} (from your own mtx, h = {d['h']})",
                    actual=f"({gx}, {gy}) depth {gz}",
                    hint="InitGeom(), gte_SetGeomOffset(160, 120), gte_SetGeomScreen(proj_h), upload mtx with gte_SetRotMatrix/gte_SetTransMatrix, "
                         "then gte_ldv0(&cube[i]); gte_rtps(); gte_stsxy(...); gte_stsz(...)." + why)


def visible_faces(d, x, colors):
    """(sure_visible, sure_hidden) face sets from the reference matrix; faces within MARGIN of edge-on are in neither."""
    ref = ref_frame(d, x.n)
    vis = {f for f in range(6) if ref["areas"][f] >= MARGIN}
    hid = {f for f in range(6) if ref["areas"][f] <= -MARGIN}
    return ref, vis, hid


def check_culling(ctx, name):
    r, d, rows, t = check_frames(ctx, name)
    check_counters(name, d, rows)
    judged = 0
    for x in rows:
        ref, vis, hid = visible_faces(d, x, d["colors"])
        drawn = []
        for q in x.quads:
            f = face_of_rgb(d["colors"], q["rgb"])
            expect_true(f is not None, f"{name}, frame {x.n}: every quad has the colour of one face", str(q["rgb"]),
                        "setRGB0 from face_colors[f] (not from a constant).")
            expect_eq(q["code"], 0x28, f"{name}, frame {x.n}: quads are POLY_F4 (code 0x28)", hint="setPolyF4 then setRGB0.")
            drawn.append(f)
        expect_eq(len(set(drawn)), len(drawn), f"{name}, frame {x.n}: no face is drawn twice", hint="One quad per visible face.")
        missing = sorted(vis - set(drawn))
        extra = sorted(set(drawn) & hid)
        judged += len(vis) + len(hid)
        hint = ("A face is drawn only if NCLIP of its corners 0, 1, 2 (gte_ldsxy3 + gte_nclip + gte_stopz) is POSITIVE: "
                "positive means clockwise on the screen, which the face table is built for (README 5.6).")
        if extra and not missing:
            hint += " You are drawing faces that point away from the camera: the test is missing or has the wrong sign."
        if missing and extra:
            hint += " Visible faces missing and hidden ones drawn: the sign of the test is inverted."
        expect_true(not missing and not extra, f"{name}, frame {x.n}: faces drawn = those facing the camera {sorted(vis)}",
                    f"drawn {sorted(drawn)}; areas (NCLIP) {ref['areas']}", hint)
    expect_true(judged >= 3 * len(rows) * 0.6, f"{name}: the frames judged cover enough faces", str(judged))


def check_sorting(ctx, name):
    r, d, rows, t = check_frames(ctx, name)
    spread = 0
    for x in rows:
        for q in x.quads:
            f = face_of_rgb(d["colors"], q["rgb"])
            sz4 = [x.sz[i] for i in FACES[f]]
            want = ref_slot(sz4)
            expect_true(abs(q["slot"] - want) <= 1, f"{name}, frame {x.n}: face {f} is in OT slot {want} (+-1)",
                        f"slot {q['slot']}; the corner depths are {sz4}",
                        "AVSZ4 of the face's four SZ values gives OTZ (about the mean SZ / 4); slot = OTZ >> 7, farther = larger slot (README 5.9).")
        if len(x.quads) >= 2:
            slots = {q["slot"] for q in x.quads}
            wants = {ref_slot([x.sz[i] for i in FACES[face_of_rgb(d["colors"], q["rgb"])]]) for q in x.quads}
            if len(wants) > 1:
                spread += 1
                expect_true(len(slots) > 1, f"{name}, frame {x.n}: faces at different depths go to different slots", f"slots {sorted(slots)}",
                            "Sort by each face's own average Z, not by a constant.")
    return spread


def lit_colors(img, step=2):
    """Colour -> pixel count over a grid of the whole picture."""
    out = {}
    for y in range(0, img.height, step):
        for x in range(0, img.width, step):
            c = img.pixel(x, y)
            out[c] = out.get(c, 0) + 1
    return out


def check_picture(ctx, name, shot_frames):
    r, d, rows, t = observe(ctx, name)
    colors = d["colors"]
    for fr in shot_frames:
        row = rows[fr - 1]
        ref, vis, hid = visible_faces(d, row, colors)
        img = r.screenshot(f"f{fr}")
        expect_true((img.width, img.height) == (W, H), "the picture is 320 x 240", f"{img.width} x {img.height}")
        for c in ((0, 0), (W - 1, 0), (0, H - 1), (W - 1, H - 1)):
            expect_true(colors_close(img.pixel(*c), BG, 12), f"{name}, frame {fr}: corner {c} is the background {BG}", str(img.pixel(*c)),
                        "display_clear(16, 16, 32) every frame.")
        for f in sorted(vis):
            xs = [ref["xy"][i][0] for i in FACES[f]]
            ys = [ref["xy"][i][1] for i in FACES[f]]
            px, py = round(sum(xs) / 4), round(sum(ys) / 4)
            got = img.pixel(px, py)
            expect_true(colors_close(got, colors[f], 24), f"{name}, frame {fr}: the centre of face {f}, ({px}, {py}), is colour {colors[f]}", str(got),
                        "Each face is its own POLY_F4 with face_colors[f]; check the face table's corner order and the culling sign.")
        counts = lit_colors(img)
        for c, n in counts.items():
            if colors_close(c, BG, 14):
                continue
            who = [f for f in range(6) if colors_close(c, colors[f], 14)]
            expect_true(who, f"{name}, frame {fr}: every non-background pixel has a face colour", f"colour {c} x{n} is neither background nor a face colour")
            for f in who:
                expect_true(f not in hid, f"{name}, frame {fr}: hidden face {f} ({colors[f]}) is not visible anywhere", f"{n} grid pixels have its colour",
                            "A face turned away from the camera must not be drawn (NCLIP <= 0).")
        for f in vis:
            expect_true(any(colors_close(c, colors[f], 14) and n >= 30 for c, n in counts.items()), f"{name}, frame {fr}: face {f} fills an area of the picture",
                        "almost nothing")


# ---- the checks ------------------------------------------------------------------------------------------------------------------
@check("frame loop: frame_no 1..120, rot advances by rot_step, 0 to 3 quads per frame, counters agree (shipped numbers)",
       hint="update_angles(): rot += rot_step with `& 4095`; prims_submitted resets every frame; faces_drawn accumulates; face_mask names the faces.")
def _(ctx):
    r, d, rows, t = check_frames(ctx, "base")
    check_counters("base", d, rows)


@check("matrix: mtx is RotMatrix(rot) with translation (0, 0, cam_z), every frame",
       hint="RotMatrix(&rot, &mtx); TransMatrix(&mtx, &pos); then upload with gte_SetRotMatrix and gte_SetTransMatrix.")
def _(ctx):
    check_matrix(ctx, "base")


@check("projection: screen_xy and screen_z equal what the GTE computes from your mtx (shipped numbers)",
       hint="InitGeom, gte_SetGeomOffset(160, 120), gte_SetGeomScreen(proj_h); per corner gte_ldv0, gte_rtps, gte_stsxy, gte_stsz.")
def _(ctx):
    check_projection(ctx, "base")


@check("culling: exactly the faces whose NCLIP is positive are drawn, never more than 3 (120 frames)",
       hint="Per face: gte_ldsxy3 of corners 0, 1, 2; gte_nclip(); gte_stopz(&area); draw only if area > 0.")
def _(ctx):
    check_culling(ctx, "base")


@check("sorting: every quad sits in the OT slot of its own average depth (AVSZ4, >> 7), farther = larger",
       hint="gte_ldsz4 of the four corners' SZ, gte_avsz4(), gte_stotz(&otz), ot_add(p, otz >> 7).")
def _(ctx):
    spread = check_sorting(ctx, "base")
    expect_true(spread >= 20, "the run has frames whose visible faces lie at different depths", f"{spread} frames",
                "(a problem with the checker's reference if this fails with a correct program)")


@check("picture (spinning, frames 30 and 95): face centres have the face colours; no hidden face colour appears anywhere",
       hint="One POLY_F4 per visible face, coloured face_colors[f], corners from screen_xy[faces[f][0..3]] in that order.")
def _(ctx):
    check_picture(ctx, "base", (30, 95))


def pose_runs():
    return [f"pose{i}" for i in range(len(POSES))]


@check("six frozen poses: faces drawn and sorted as the reference says, face centres coloured, no hidden colour anywhere",
       hint="rot_step is patched to 0, so each pose holds: the drawing must follow rot and the face table.")
def _(ctx):
    kinds = set()
    for name in pose_runs():
        check_matrix(ctx, name)
        check_projection(ctx, name)
        check_culling(ctx, name)
        check_sorting(ctx, name)
        r, d, rows, t = observe(ctx, name)
        ref, vis, hid = visible_faces(d, rows[0], d["colors"])
        expect_true(len(vis) + len(hid) == 6, f"{name}: the pose is clear of edge-on faces (checker design)", f"{ref['areas']}")
        kinds.add(len(vis))
        check_picture(ctx, name, (2,))
    expect_true(kinds == {1, 2, 3}, "the poses show one, two and three faces", f"visible-face counts seen: {sorted(kinds)} (checker design)")


@check("colours come from face_colors[]: a recoloured, frozen pose is drawn in the new colours",
       hint="Read face_colors[f] when you build each quad; do not hard-code the colours or their order.")
def _(ctx):
    check_culling(ctx, "recolor")
    check_picture(ctx, "recolor", (2,))


@check("patched lens, cube size, speeds and a third axis: matrix, projection, culling, sorting and picture follow the data",
       hint="Nothing may be hard-coded: h = proj_h, translation z = cam_z, size from cube[], speeds from rot_step (all three axes).")
def _(ctx):
    check_matrix(ctx, "lens")
    check_projection(ctx, "lens")
    check_culling(ctx, "lens")
    check_sorting(ctx, "lens")
    check_picture(ctx, "lens", (30,))


@check("GTE flags: no error bits in the shipped run; a cube straddling the camera reports divide overflow (bit 17) and the summary bit 31",
       hint="After each gte_rtps(), read the flag register with gte_stflg and OR it into gte_flags (reset every frame).")
def _(ctx):
    r, d, rows, t = observe(ctx, "base")
    for x in rows:
        expect_eq(x.flags & 0xFFFFE000, 0, f"base, frame {x.n}: gte_flags error bits (13..31; bit 12, IR0 saturation, is harmless) with the cube at z = 6.0", hint="gte_flags is the OR of the flag registers of this frame's eight transforms, 0 when nothing overflowed.", fmt="hex")
    r, d, rows, t = observe(ctx, "flags")
    for x in rows:
        ref = ref_frame(d, x.n)
        expect_true(ref["ovf"], "flags run: the reference sees a divide overflow (checker design)", "none")
        expect_true(x.flags & (1 << 17), f"flags run, frame {x.n}: gte_flags has bit 17 (divide overflow)", f"{x.flags:#010x}",
                    "gte_stflg(&f) after each gte_rtps(); OR the values; do not reset in between within the frame.")
        expect_true(x.flags & (1 << 31), f"flags run, frame {x.n}: gte_flags has bit 31 (error summary)", f"{x.flags:#010x}")


# The budget: the reference solution spends about SOLUTION_CYCLES CPU cycles per frame between render_begin() and render_end()
# (matrix, 8 transforms, 6 culling tests, up to 3 quads). The limit is twice that.
SOLUTION_CYCLES = 2850
BUDGET = 2 * SOLUTION_CYCLES


@check(f"frame time: CPU cycles between render_begin() and render_end() stay under the budget ({BUDGET})",
       hint="RotMatrix is the expensive call: build and upload the matrix once per frame, not per face or per corner.")
def _(ctx):
    r, d, rows, t = observe(ctx, "base")
    cyc = sorted(x.cycles for x in rows[1:])
    med = cyc[len(cyc) // 2]
    expect_true(med > 0, "render_begin() and render_end() were reached", "0 cycles", "Keep the markers in main's loop around the 3D work.")
    expect_true(max(cyc) <= BUDGET, f"cycles per frame <= {BUDGET} (the reference solution needs about {SOLUTION_CYCLES})",
                f"median {med}, worst {max(cyc)}", "Call RotMatrix once per frame (not per face or per corner); transform each corner once.")
