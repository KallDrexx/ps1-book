"""Chapter 24 checks: 3D Projection Fundamentals ("Software Cube").
Build: CMake + PSn00bSDK. STATIC: the state symbols exist; the CPU does the 3D (no GTE function in the sources, no GTE
function of the SDK referenced by any object of the program, no COP2 instruction in any object of the program: the SDK's own
libraries are not scanned); no floating point; common/psxe is mirrored in the solution.
DYNAMIC (probe.lua): the probe records, every time the program calls frame_done(), frame_no, angle_x, angle_y and the
projected[] array, for 120 frames, in three runs (shipped numbers; patched cube size, edge table, steps and start angles;
patched projection distance, camera distance and size). The Python reference below uses the SAME fixed-point rules as the
README (the SDK's isin/icos ported bit for bit, fx_rotate's single shift, fx_div's truncation); a correct program matches it
within 1 pixel on every frame. If it does not, the checker tries a few common mistakes and names the one that fits.
Screenshots at frames 30 and 95 of every run: each edge of the (recorded) edge table is drawn between the projected corners,
and no other pixel is lit."""
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
LINE = (255, 255, 255)
N = 120
SHOT_FRAMES = (30, 95)
TOL = 1

SHIPPED = dict(size=4096, step_x=24, step_y=40, ax=128, ay=256, cam_z=6 * 4096, h=256)
EDGES = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)]
MOTION = dict(size=2800, step_x=-37, step_y=61, ax=1000, ay=3000)             # run 2 (also its own edge table)
EDGES2 = [(0, 7), (1, 6), (2, 5), (3, 4), (0, 3), (4, 7), (1, 2), (5, 6), (0, 5), (1, 4), (2, 7), (3, 6)]
LENS = dict(size=5000, cam_z=22528, h=200, step_x=17, step_y=-29)             # run 3

config(
    title="3D Projection Fundamentals",
    build="cmake", exe="game.exe", sym="", elf="game.elf",
    break_at=None, max_frames=400,
)

STATE = ["cube", "edges", "projected", "angle_x", "angle_y", "step_x", "step_y", "cam_z", "proj_h", "frame_no", "frame_done"]


# ---- the reference (README section 7.2: the contract) ----------------------------------------------------------------
def isin(a):
    """PSn00bSDK isin(): 4096 = one turn, result 4.12. A port of the library routine, instruction by instruction."""
    t = (a - 1024) & 0x7FF
    if t & 0x400:
        t -= 0x800
    p = (t * t) >> 6
    v = ((19900 - ((879 * p) >> 12)) * p) >> 16
    return v - 4096 if a & 0x800 else 4096 - v


def icos(a):
    return isin(a + 1024)


def fx_div(a, b):
    if b == 0:
        return 0x7FFFFFFF if a > 0 else (-0x80000000 if a < 0 else 0)
    n, d = a << 12, b
    q = abs(n) // abs(d)
    return q if (n < 0) == (d < 0) else -q


def rot(u, v, angle):
    c, s = icos(angle), isin(angle)
    return (u * c - v * s) >> 12, (u * s + v * c) >> 12


def ref_vertex(p, ax, ay, cam_z, h, mode="ok"):
    x, y, z = p
    sgn = -1 if mode == "reverse" else 1
    if mode == "yx":
        z, x = rot(z, x, sgn * ay)
        y, z = rot(y, z, sgn * ax)
    else:
        y, z = rot(y, z, sgn * ax)
        z, x = rot(z, x, sgn * ay)
    z += cam_z
    if mode == "ortho":                                   # no divide: scale by h / cam_z
        return CX + ((x * h) // cam_z), CY + ((y * h) // cam_z)
    sx = ((fx_div(x, z) * h) >> 12)
    sy = ((fx_div(y, z) * h) >> 12)
    if mode == "flip":
        sy = -sy
    if mode == "nocentre":
        return sx, sy
    return CX + sx, CY + sy


def corner(i, size):
    return (size if i & 1 else -size, size if i & 2 else -size, size if i & 4 else -size)


MODES = {
    "reverse": "the rotation direction is reversed (check the sign in fx_rotate's use: README 5.3)",
    "yx": "you rotate about Y first, then X (the contract is X first, then Y)",
    "ortho": "there is no perspective divide by z (the farther corners must come closer to the centre)",
    "flip": "y is flipped (on the PS1 screen y grows downwards, so do not negate it)",
    "nocentre": "the screen centre (160, 120) is not added",
}


# ---- reading the run -----------------------------------------------------------------------------------------------
def cube_patch(size):
    return struct.pack("<24h", *(v for i in range(8) for v in corner(i, size)))


def patches_for(**kw):
    d = dict(SHIPPED, **kw)
    edges = kw.get("edges")
    p = {
        "cube": cube_patch(d["size"]),
        "step_x": words(d["step_x"]), "step_y": words(d["step_y"]),
        "angle_x": words(d["ax"]), "angle_y": words(d["ay"]),
        "cam_z": words(d["cam_z"]), "proj_h": words(d["h"]),
    }
    if edges:
        p["edges"] = bytes(v for e in edges for v in e)
    return p


def run_of(ctx, name):
    if name == "base":
        return ctx.result, dict(SHIPPED), EDGES
    if name == "motion":
        d = dict(SHIPPED, **MOTION)
        return ctx.run("motion", patches=patches_for(edges=EDGES2, **MOTION)), d, EDGES2
    d = dict(SHIPPED, **LENS)
    return ctx.run("lens", patches=patches_for(**LENS)), d, EDGES


def rows_of(r, what):
    rows = r.record("rows") or []
    expect_true(rows, "frame_done() is called every frame", f"{what}: it was never called",
                "main's loop (given) calls frame_done() after frame_no++ and display_swap(); did the program reach it?")
    return rows


# ---- static checks -----------------------------------------------------------------------------------------------------
@static_check("the state symbols exist", hint="Keep cube, edges, projected, angle_x/y, step_x/y, cam_z, proj_h, frame_no and frame_done() from the starter.")
def _(ctx):
    miss = ctx.symbols.require(*STATE)
    if miss:
        raise CheckFailure(
            expected="symbols defined: " + ", ".join(STATE), actual="missing: " + ", ".join(miss),
            hint="The linker drops data nothing reads. Keep the starter's declarations and the `__asm__ volatile(...)` "
                 "line at the top of main() that keeps them alive, and read the values from these variables: a constant "
                 "in their place (6 * 4096 instead of cam_z, 256 instead of proj_h) fails the patched runs.")


def _strip(txt):
    return re.sub(r"/\*.*?\*/|//[^\n]*", " ", txt, flags=re.S)


GTE_NAMES = (r"gte_\w+|RotTransPers\w*|RotTrans\w*|RotMatrix\w*|TransMatrix|ScaleMatrix|ApplyMatrix\w*|MulMatrix\w*|CompMatrix\w*|"
             r"SetRotMatrix|SetTransMatrix|SetGeomOffset|SetGeomScreen|InitGeom|NormalClip|OuterProduct\w*|RotAverage\w*|RotNclip\w*|"
             r"LocalLight|DpqColor|NormalColor\w*|ctc2|mtc2|mfc2|cfc2|lwc2|swc2|cop2|COP2|inline_c\.h|gtereg\.h")


def _program_sources(ctx):
    return [p for p in ctx.source_files("**/*") if p.suffix in (".c", ".h", ".s", ".S", ".inc")]


@static_check("no GTE in the sources (the CPU does the 3D this chapter)",
              hint="Chapter 24 rotates and projects with integer maths on the CPU. The GTE arrives in Chapter 25. (isin and icos from <psxgte.h> are plain integer maths and are allowed.)")
def _(ctx):
    for p in _program_sources(ctx):
        txt = _strip(p.read_text(errors="replace"))
        m = re.search(r"\b(" + GTE_NAMES + r")\b", txt)
        expect_true(not m, f"{p.relative_to(ctx.project)} has no GTE call", f"found `{m.group(0)}`" if m else "",
                    "Use fx_rotate/fx_div/fx_mul from psxe/fixed.h instead.")


def _objects(ctx):
    objs = sorted(ctx.build.build_dir.rglob("*.obj")) + sorted(ctx.build.build_dir.rglob("*.o"))
    expect_true(objs, "the program's object files are available", "none found in the build directory")
    return objs


def _tool(name):
    p = shutil.which(name)
    if not p:
        raise HarnessError(f"{name} not on PATH (source tools/env.sh)")
    return p


@static_check("no GTE instruction or SDK GTE routine in the program's own objects",
              hint="Scanned: every .obj of your project and of psxe/ (never the SDK's libraries). Forbidden: COP2 instructions (mtc2, mfc2, ctc2, cfc2, lwc2, swc2, cop2) and any libpsxgte routine other than isin/icos.")
def _(ctx):
    import os
    objdump, nm = _tool("mipsel-none-elf-objdump"), _tool("mipsel-none-elf-nm")
    libs = os.environ.get("PSN00BSDK_LIBS", str(ROOT_DIR / ".toolchain/opt/psn00bsdk/lib/libpsn00b"))
    gte_lib = next(iter(sorted((Path(libs) / "release").glob("libpsxgte_exe_gprel.a"))), None)
    expect_true(gte_lib, "the SDK's libpsxgte is found", "not found")
    out = subprocess.run([nm, "--defined-only", "-g", str(gte_lib)], capture_output=True, text=True).stdout
    sdk_gte = {l.split()[-1] for l in out.splitlines() if len(l.split()) == 3} - {"isin", "icos", "hisin", "hicos"}
    cop2 = re.compile(r"\t(mtc2|mfc2|ctc2|cfc2|lwc2|swc2|cop2|bc2[ft]l?)\b")
    for o in _objects(ctx):
        dis = subprocess.run([objdump, "-d", str(o)], capture_output=True, text=True).stdout
        m = cop2.search(dis)
        expect_true(not m, f"{o.name} has no COP2 instruction", f"`{m.group(1)}` in {o.name}" if m else "",
                    "The GTE is coprocessor 2. This chapter must not touch it.")
        und = subprocess.run([nm, "--undefined-only", str(o)], capture_output=True, text=True).stdout.split()
        bad = sorted(set(und) & sdk_gte)
        expect_true(not bad, f"{o.name} calls no SDK GTE routine", f"references {bad}", "RotTransPers, RotMatrix, InitGeom ... are for Chapter 25.")


@static_check("integers only: no floating point in the program's objects",
              hint="Soft-float helpers (__mulsf3, __floatsisf, ...) in your objects mean a float or double crept in. Use fx and integers.")
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


# ---- dynamic checks -------------------------------------------------------------------------------------------------------
def check_tables(ctx, name):
    r, d, edges = run_of(ctx, name)
    rows = rows_of(r, name)
    t = r.record("tables")
    want_cube = [v for i in range(8) for v in corner(i, d["size"])]
    expect_eq(t["cube"], want_cube, f"{name}: cube[] at frame 1", hint="The program must not change the cube table: rotate copies, not the table itself.")
    expect_eq(t["edges"], [v for e in edges for v in e], f"{name}: edges[] at frame 1", hint="Do not change the edge table.")
    for k, key in (("cam_z", "cam_z"), ("proj_h", "h"), ("step_x", "step_x"), ("step_y", "step_y")):
        expect_eq(t[k], d[key], f"{name}: {k}", hint="Read these from memory; do not write them.")
    return r, d, edges, rows


def check_angles(ctx, name):
    r, d, edges, rows = check_tables(ctx, name)
    expect_eq([row[0] for row in rows], list(range(1, N + 1)), f"{name}: frame_no at each frame_done() call",
              hint="frame_no must be 1 at the first call and grow by 1 per frame; main's loop is given.")
    for row in rows:
        k = row[0]
        ex, ey = (d["ax"] + k * d["step_x"]) & 4095, (d["ay"] + k * d["step_y"]) & 4095
        expect_true((row[1], row[2]) == (ex, ey), f"angle_x, angle_y at frame {k} = ({ex}, {ey})", f"({row[1]}, {row[2]})",
                    "update_angles(): add the step each frame and keep the angle in 0..4095 with `& 4095` (steps may be negative).")


def check_projection(ctx, name):
    r, d, edges, rows = check_tables(ctx, name)
    bad = []
    for row in rows:
        k, ax, ay = row[0], row[1], row[2]
        got = [(row[3 + 2 * i], row[4 + 2 * i]) for i in range(8)]
        ref = [ref_vertex(corner(i, d["size"]), ax, ay, d["cam_z"], d["h"]) for i in range(8)]
        worst = max(max(abs(g[0] - e[0]), abs(g[1] - e[1])) for g, e in zip(got, ref))
        if worst > TOL:
            bad.append((k, ax, ay, got, ref, worst))
    if not bad:
        return
    k, ax, ay, got, ref, worst = bad[0]
    i = max(range(8), key=lambda i: max(abs(got[i][0] - ref[i][0]), abs(got[i][1] - ref[i][1])))
    why = ""
    for mode, text in MODES.items():
        alt = [ref_vertex(corner(j, d["size"]), ax, ay, d["cam_z"], d["h"], mode) for j in range(8)]
        if all(abs(g[0] - e[0]) <= 2 and abs(g[1] - e[1]) <= 2 for g, e in zip(got, alt)):
            why = f" This is what you get if {text}."
            break
    consts = [("cam_z", SHIPPED["cam_z"], d["h"]), ("proj_h", d["cam_z"], SHIPPED["h"]), ("cam_z and proj_h", SHIPPED["cam_z"], SHIPPED["h"])]
    for what, cz, h in consts if not why and (d["cam_z"], d["h"]) != (SHIPPED["cam_z"], SHIPPED["h"]) else ():
        alt = [ref_vertex(corner(j, d["size"]), ax, ay, cz, h) for j in range(8)]
        if all(abs(g[0] - e[0]) <= TOL and abs(g[1] - e[1]) <= TOL for g, e in zip(got, alt)):
            why = f" This is what you get with the shipped {what} as a constant: read the variables (this run sets cam_z = {d['cam_z']}, proj_h = {d['h']})."
            break
    raise CheckFailure(
        expected=f"{name}: all {len(rows)} frames within {TOL} px of the reference; corner {i} at frame {k} "
                 f"(angle_x={ax}, angle_y={ay}) should be {ref[i]}",
        actual=f"{len(bad)} frames differ; corner {i} at frame {k} is {got[i]} (off by {worst} px)",
        hint="Order: rotate about X, then about Y, then add cam_z, divide by z, multiply by proj_h, add (160, 120)." + why)


@check("frame loop: frame_no counts 1..120 and the angles advance by the steps (shipped numbers)",
       hint="update_angles(): angle += step each frame, wrapped with & 4095.")
def _(ctx):
    check_angles(ctx, "base")


@check("projected[] matches the reference on 120 frames of the spin (shipped numbers)",
       hint="rotate about X then Y with fx_rotate, z += cam_z, x*proj_h/z with fx_div, plus the screen centre.")
def _(ctx):
    check_projection(ctx, "base")


@check("patched cube size, edge table, steps and start angles: the program follows its data",
       hint="Nothing may be hard-coded: size comes from cube[], speeds from step_x/step_y, start from angle_x/y; negative steps wrap.")
def _(ctx):
    check_angles(ctx, "motion")
    check_projection(ctx, "motion")


@check("patched projection distance, camera distance and size: the perspective follows its data",
       hint="Use proj_h and cam_z as the projection distance h and the z offset; do not use constants.")
def _(ctx):
    check_angles(ctx, "lens")
    check_projection(ctx, "lens")


def seg_dist(px, py, a, b):
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def check_picture(ctx, name):
    r, d, edges, rows = check_tables(ctx, name)
    for f in SHOT_FRAMES:
        row = rows[f - 1]
        pts = [(row[3 + 2 * i], row[4 + 2 * i]) for i in range(8)]
        img = r.screenshot(f"f{f}")
        expect_true((img.width, img.height) == (W, H), "the picture is 320 x 240", f"{img.width} x {img.height}")
        for c in ((0, 0), (W - 1, 0), (0, H - 1), (W - 1, H - 1)):
            expect_true(colors_close(img.pixel(*c), BG, 12), f"frame {f}: corner {c} is the background {BG}", str(img.pixel(*c)),
                        "display_clear(16, 16, 32) every frame.")
        def lit(x, y):
            return img.in_bounds(x, y) and colors_close(img.pixel(x, y), LINE, 48)
        for ei, (a, b) in enumerate(edges):
            for t in (0.2, 0.4, 0.5, 0.6, 0.8):
                x = round(pts[a][0] + (pts[b][0] - pts[a][0]) * t)
                y = round(pts[a][1] + (pts[b][1] - pts[a][1]) * t)
                ok = any(lit(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1))
                expect_true(ok, f"frame {f}: edge {a}-{b} is drawn near ({x}, {y}) (white)", "no white pixel there",
                            "One white LINE_F2 per entry of edges[], from projected[a] to projected[b], linked with ot_add.")
        stray = []
        for y in range(H):
            row_px = img.rgb[y * W * 3:(y + 1) * W * 3]
            for x in range(W):
                o = x * 3
                if max(abs(row_px[o] - BG[0]), abs(row_px[o + 1] - BG[1]), abs(row_px[o + 2] - BG[2])) > 40:
                    if min(seg_dist(x, y, pts[a], pts[b]) for a, b in edges) > 2.0:
                        stray.append((x, y))
        expect_true(len(stray) <= 3, f"frame {f}: nothing is drawn away from the edges", f"{len(stray)} stray pixels, e.g. {stray[:4]}",
                    "Only the 12 lines; no extra primitives, and the screen is cleared every frame.")


@check("picture: the 12 lines join the projected corners and nothing else is lit (shipped numbers)",
       hint="LINE_F2 packets: setLineF2, setRGB0(255,255,255), setXY2 from projected[a] to projected[b], ot_add.")
def _(ctx):
    check_picture(ctx, "base")


@check("picture follows the data (patched cube, edge table and lens)",
       hint="The drawing must come from projected[] and edges[], not from constants.")
def _(ctx):
    check_picture(ctx, "motion")
    check_picture(ctx, "lens")
