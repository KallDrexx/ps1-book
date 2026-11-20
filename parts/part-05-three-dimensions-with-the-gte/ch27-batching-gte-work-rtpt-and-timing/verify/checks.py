"""Chapter 27 checks: Batching GTE Work: RTPT and Timing ("The 64-Cube Field").
Build: CMake + PSn00bSDK.
STATIC: the state symbols exist; the program's OWN objects (project + psxe, never the SDK's libraries) contain an RTPT command;
no floating point; the reference solution's psxe mirrors common/psxe.
DYNAMIC (probe.lua): every time the program calls frame_done() the probe records the 64 matrices the program holds (cube_mtx),
screen_xy[64][8], screen_z[64][8], the CPU cycles between transform_begin() and transform_end() and between render_begin() and
render_end(), the cycles the program measured itself (field_cycles[]), and how many RTPS / RTPT commands were really executed
inside the transform window (execution breakpoints on every RTPS / RTPT instruction found in the loaded program).
The contract (README section 7):
  * the given code turns cubes[] into cube_mtx[] (RotMatrix * size, translation = position + cam) once per frame;
  * for every cube, both paths leave in screen_xy / screen_z exactly what RTPS gives for that cube's matrix: the GTE's divide
    (the 'unr' divider of psx-spx) is ported below and compared BIT FOR BIT, for every cube and corner, every frame;
  * the two paths (path = 0, path = 1: patched into the same build) therefore agree word for word;
  * path 1 really batches: at least 2 RTPT per cube, at most 2 RTPS per cube, every corner covered;
  * path 1 spends at least MIN_SAVING of path 0's cycles less in the transform section, and the frame fits the budget.
Runs: the shipped poses, path 0 and path 1 (24 frames each); patched poses, camera and lens, with a cube around the camera,
path 0 and path 1 (14 frames each)."""
import random
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
BOOT = 45                         # frames the SDK needs before main (about 34) plus margin
N = 24                            # frames recorded in the shipped runs
NQ = 14                           # frames recorded in the patched runs
NC = 64
TOL_MTX = 8                       # cube_mtx entries vs the reference RotMatrix * size

# ---- the numbers the reference solution measured (README 7.5) ----
REF_PATH0 = 25640                 # cycles of the transform section, path 0 (RTPS per corner)
REF_PATH1 = 17640                 # path 1, the reference solution (3 x RTPT per cube); a saving of 31 %
MIN_SAVING = 0.15                 # the required saving of path 1 against path 0 (the reference achieves 0.31; a plain loop 0.20)
REF_FRAME = 116300                # render_begin() .. render_end(), reference solution, path 1
FRAME_BUDGET = 2 * REF_FRAME

SHIPPED = dict(cam=(0, 0, 8192), h=256)
FIELDS = 10                       # int32 words per Cube: x y z ax ay az sx sy sz size

config(
    title="Batching GTE Work: RTPT and Timing",
    build="cmake", exe="game.exe", sym="", elf="game.elf",
    break_at=None, max_frames=BOOT + N, timeout=40,
)

STATE = ["cubes", "cube", "path", "cam", "proj_h", "cube_mtx", "screen_xy", "screen_z", "field_cycles", "frame_no",
         "render_begin", "render_end", "transform_begin", "transform_end", "frame_done"]


# ---- the reference ---------------------------------------------------------------------------------------------------------
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
    """RotMatrix(): Rx * Ry * Rz."""
    sx, cx, sy, cy, sz, cz = isin(ax), icos(ax), isin(ay), icos(ay), isin(az), icos(az)
    X = [[4096, 0, 0], [0, cx, -sx], [0, sx, cx]]
    Y = [[cy, 0, sy], [0, 4096, 0], [-sy, 0, cy]]
    Z = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 4096]]
    return matmul(matmul(X, Y), Z)


UNR = [max(0, (0x40000 // (i + 0x100) + 1) // 2 - 0x101) for i in range(0x101)]


def gte_divide(h, sz):
    """The GTE's reciprocal-based divide (psx-spx 'GTE Division Inaccuracy'): about h * 65536 / sz, saturated to 0x1FFFF."""
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
    """RTPS with sf = 1: returns (sx, sy, sz)."""
    mac = [((t[i] << 12) + sum(m[i][k] * v[k] for k in range(3))) >> 12 for i in range(3)]
    ir = [sat(x, -32768, 32767) for x in mac]
    sz = sat(mac[2], 0, 65535)
    n = gte_divide(h, sz)
    sx = sat((n * ir[0] + (CX << 16)) >> 16, -0x400, 0x3FF)
    sy = sat((n * ir[1] + (CY << 16)) >> 16, -0x400, 0x3FF)
    return sx, sy, sz


def corner(i):
    return (4096 if i & 1 else -4096, 4096 if i & 2 else -4096, 4096 if i & 4 else -4096)


def tile_color(i):
    return (64 + ((i * 37) & 127), 64 + ((i * 53) & 127), 64 + ((i * 71) & 127))


# ---- the runs ---------------------------------------------------------------------------------------------------------------
def make_patched_poses():
    """Poses unlike the shipped ones: scattered, mixed sizes, one cube straddling the camera plane (divide overflow)."""
    rnd = random.Random(2701)
    cubes = []
    for i in range(NC):
        size = rnd.choice([120, 200, 320, 480])
        cubes.append([rnd.randint(-6000, 6000), rnd.randint(-4500, 4500), rnd.randint(-3500, 5000),
                      rnd.randint(0, 4095), rnd.randint(0, 4095), rnd.randint(0, 4095),
                      rnd.randint(-70, 70), rnd.randint(-70, 70), rnd.randint(-70, 70), size])
    cubes[5][2:3] = [-8800]       # z + cam.z = 200 with h = 200: corners on both sides of H / 2
    cubes[5][9] = 500
    cubes[40][2] = -9000          # z + cam.z = 0: corners behind the camera
    cubes[40][9] = 300
    return cubes


PATCHED_CUBES = make_patched_poses()
PATCHED = dict(cam=(300, -200, 9000), h=200)


def patches_for(path, cubes=None, cam=None, h=None):
    p = {"path": words(path)}
    if cubes is not None:
        p["cubes"] = b"".join(struct.pack("<10i", *c) for c in cubes)
        p["cam"] = struct.pack("<3i", *cam)
        p["proj_h"] = words(h)
    return p


def run_of(ctx, name):
    path = int(name[-1])
    if name.startswith("base"):
        return ctx.run(name, patches=patches_for(path), max_frames=BOOT + N)
    return ctx.run(name, patches=patches_for(path, PATCHED_CUBES, PATCHED["cam"], PATCHED["h"]), max_frames=BOOT + NQ)


class Row:
    def __init__(self, r):
        self.n = r[0]
        o = 1
        self.m, self.t = [], []
        for c in range(NC):
            v = r[o:o + 12]
            self.m.append([v[0:3], v[3:6], v[6:9]])
            self.t.append(tuple(v[9:12]))
            o += 12
        self.xy = [[(r[o + 16 * c + 2 * k], r[o + 16 * c + 2 * k + 1]) for k in range(8)] for c in range(NC)]
        o += NC * 16
        self.sz = [r[o + 8 * c:o + 8 * c + 8] for c in range(NC)]
        o += NC * 8
        self.tcyc, self.rcyc, self.fc0, self.fc1, self.rtps_n, self.rtpt_n = r[o:o + 6]


def observe(ctx, name):
    r = run_of(ctx, name)
    want = N if name.startswith("base") else NQ
    rows = r.record("rows") or []
    expect_true(len(rows) >= want - 6, f"{name}: frame_done() is called every frame ({want - 6}+ times observed)", f"{len(rows)} calls",
                "main's loop (given) calls frame_done() after display_swap(); did the program get there?")
    return r, [Row(x) for x in rows], r.record("tables")


def pose_expect(tables, n):
    """cubes[] as the given update_cubes() leaves it when the probe sees frame n (the table is read after frame 1)."""
    out = []
    for c in range(NC):
        x, y, z, ax, ay, az, sx, sy, sz, size = tables["cubes"][c * FIELDS:(c + 1) * FIELDS]
        k = n - 1
        out.append((x, y, z, (ax + k * sx) & 4095, (ay + k * sy) & 4095, (az + k * sz) & 4095, size))
    return out


# ---- static checks ---------------------------------------------------------------------------------------------------------------
@static_check("the state symbols exist", hint="Keep the starter's declarations, the keep-alive `__asm__ volatile(...)` line at the top of main, and the five marker functions.")
def _(ctx):
    miss = ctx.symbols.require(*STATE)
    if miss:
        raise CheckFailure(
            expected="symbols defined: " + ", ".join(STATE), actual="missing: " + ", ".join(miss),
            hint="The linker drops data nothing reads. Keep the starter's declarations and the `__asm__ volatile(...)` line that keeps them alive.")


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


@static_check("the program uses RTPT: the command appears in its own objects",
              hint="Scanned: every .obj of your project and of psxe/ (never the SDK's libraries). Write gte_ldv3c(...); gte_rtpt(); ... in transform_field_rtpt() (README 5.5, 7.3).")
def _(ctx):
    objdump = _tool("mipsel-none-elf-objdump")
    seen = set()
    for o in _objects(ctx):
        dis = subprocess.run([objdump, "-d", str(o)], capture_output=True, text=True).stdout
        for m in re.finditer(r"\t(?:cop2|c2)\s+0x([0-9a-fA-F]+)", dis):
            seen.add(int(m.group(1), 16) & 0x3F)
    names = {COP2_NAMES[c] for c in seen if c in COP2_NAMES}
    expect_true("RTPT" in names, "the batched transform command (RTPT)", f"GTE commands found: {sorted(names) or 'none'}",
                "gte_rtpt() transforms the three vertices loaded with gte_ldv3c / gte_ldv3.")


@static_check("every GTE command comes at least two instructions after the last write to a GTE register (the nops inside the macros)",
              hint="gte_rtpt() and friends start with two nops for a reason: a GTE register write is not interlocked, and psx-spx gives lwc2 a two-instruction delay (README 5.5). "
                   "If you write your own cop2 sequence, put two instructions (the next batch's work, not a GTE access) between the last lwc2/mtc2/ctc2 and the command.")
def _(ctx):
    objdump = _tool("mipsel-none-elf-objdump")
    for o in _objects(ctx):
        dis = subprocess.run([objdump, "-d", "-z", str(o)], capture_output=True, text=True).stdout   # -z: do not elide runs of nops
        seq = []                          # (mnemonic, address text) of the whole object, in order
        for line in dis.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and re.fullmatch(r"\s*[0-9a-f]+:", parts[0]):
                seq.append((parts[2].strip(), parts[0].strip()))
        for i, (mn, at) in enumerate(seq):
            if mn in ("cop2", "c2"):
                for back in (1, 2):
                    if i - back >= 0 and seq[i - back][0] in ("lwc2", "mtc2", "ctc2"):
                        raise CheckFailure(
                            expected=f"{o.name}, command at {at}: no lwc2/mtc2/ctc2 within the two instructions before it",
                            actual=f"{seq[i - back][0]} at {seq[i - back][1]}, {back} instruction(s) before the command",
                            hint="Use the SDK's gte_rtpt() (it begins with two nops), or leave two other instructions between the register write and the command.")


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


# ---- dynamic checks ---------------------------------------------------------------------------------------------------------------
def check_frames_and_poses(name, rows, t, d):
    expect_eq([x.n for x in rows], list(range(1, len(rows) + 1)), f"{name}: frame_no at each frame_done() call",
              hint="frame_no is 1 at the first call and grows by 1 per frame; main's loop (given) does it.")
    expect_eq(t["path"], d["path"], f"{name}: path", hint="The verifier patches `path`; read it, do not overwrite it.")
    for x in rows:
        poses = pose_expect(t, x.n)
        for c in range(NC):
            px, py, pz, ax, ay, az, size = poses[c]
            expect_eq(x.t[c], (px + d["cam"][0], py + d["cam"][1], pz + d["cam"][2]), f"{name}, frame {x.n}: cube_mtx[{c}] translation",
                      hint="cube_mtx[] is built by the given code from cubes[] and cam; do not change either, or the matrices.")
            ref = [[(v * size) >> 12 for v in row] for row in rot_matrix(ax, ay, az)]
            worst = max(abs(x.m[c][i][j] - ref[i][j]) for i in range(3) for j in range(3))
            expect_true(worst <= TOL_MTX, f"{name}, frame {x.n}: cube_mtx[{c}] = RotMatrix * size (max difference {worst} <= {TOL_MTX})",
                        f"{x.m[c]} vs {ref}", "Leave update_cubes() and build_matrices() as given.")


def check_reference(name, rows, t, d):
    """Every cube, every corner, every frame: bit-exact RTPS."""
    for x in rows:
        for c in range(NC):
            m = [list(r) for r in x.m[c]]
            for k in range(8):
                rx, ry, rz = rtps(m, x.t[c], corner(k), d["h"])
                gx, gy = x.xy[c][k]
                gz = x.sz[c][k]
                if (gx, gy, gz) != (rx, ry, rz):
                    hint = ("A store that runs past the end of a row overwrites a neighbour (screen_xy[i][8] is cube i + 1's corner 0; the last cube's goes beyond the arrays): "
                            "if the first entries are wrong and later ones are right, look for that. Each corner of each cube: gte_ldv0 / gte_rtps (path 0) or gte_ldv3c / gte_rtpt (path 1), then store SXY and SZ in "
                            "screen_xy[cube][corner] and screen_z[cube][corner].")
                    if k >= 6:
                        hint += (" Corners 6 and 7 are the last, partial batch: with three corners per command a third of eight corners "
                                 "does not divide evenly. Repeat a corner (batch 5, 6, 7) or finish with RTPS, and make sure the three stores land "
                                 "in screen_xy[cube][5..7] (or only the two you need).")
                    elif x.xy[c] == x.xy[0] and x.sz[c] == x.sz[0] and c > 0:
                        hint += " This cube holds exactly the results of cube 0: are you reusing results or skipping the matrix upload (load_matrix(i))?"
                    elif x.xy[c][k] == (0, 0) and gz == 0:
                        hint += " Nothing was stored for this corner."
                    raise CheckFailure(
                        expected=f"{name}, frame {x.n}: cube {c}, corner {k} at ({rx}, {ry}) depth {rz} (RTPS of your own cube_mtx[{c}], h = {d['h']})",
                        actual=f"({gx}, {gy}) depth {gz}", hint=hint)


def check_same(a, b, na, nb):
    for xa, xb in zip(a, b):
        for c in range(NC):
            for k in range(8):
                same = xa.xy[c][k] == xb.xy[c][k] and xa.sz[c][k] == xb.sz[c][k]
                expect_true(same, f"frame {xa.n}: cube {c} corner {k} is the same in {na} and {nb}",
                            f"{na}: {xa.xy[c][k]} z {xa.sz[c][k]}   {nb}: {xb.xy[c][k]} z {xb.sz[c][k]}",
                            "The two paths must leave identical screen_xy and screen_z.")


def d_of(name, t):
    if name.startswith("base"):
        return dict(path=int(name[-1]), cam=tuple(t["cam"]), h=t["proj_h"])
    return dict(path=int(name[-1]), cam=PATCHED["cam"], h=PATCHED["h"])


def median(v):
    v = sorted(v)
    return v[len(v) // 2]


# ---- the checks ---------------------------------------------------------------------------------------------------------------------
@check("poses: cube_mtx[] follows cubes[] (RotMatrix * size, translation = position + cam) every frame",
       hint="The matrices are built for you each frame; if this fails, update_cubes() or build_matrices() was changed.")
def _(ctx):
    r, rows, t = observe(ctx, "base0")
    check_frames_and_poses("base0", rows, t, d_of("base0", t))


@check("path 0 (RTPS per corner, given) leaves exactly what the GTE computes: all 64 cubes x 8 corners, 24 frames, bit for bit",
       hint="Path 0 is the Chapter 25 code and is the baseline: leave transform_field_rtps() as given.")
def _(ctx):
    r, rows, t = observe(ctx, "base0")
    check_reference("path 0", rows, t, d_of("base0", t))


@check("path 1 (RTPT) leaves exactly what the GTE computes: all 64 cubes x 8 corners, 24 frames, bit for bit",
       hint="gte_ldv3c(&cube[c]); gte_rtpt(); gte_stsxy3c(&screen_xy[i][c]); gte_stsz3c(&screen_z[i][c]) for c = 0, 3 and a last batch that covers 6 and 7.")
def _(ctx):
    r, rows, t = observe(ctx, "base1")
    check_reference("path 1", rows, t, d_of("base1", t))


@check("the two paths agree word for word: screen_xy and screen_z of every cube and corner, every frame",
       hint="Same cubes, same matrices, same corners: the batching must not change a single bit.")
def _(ctx):
    _, a, _ = observe(ctx, "base0")
    _, b, _ = observe(ctx, "base1")
    check_same(a, b, "path 0", "path 1")


@check("patched poses, camera and lens (a cube straddling the camera plane, one behind it): both paths equal the reference and each other",
       hint="Nothing may be hard-coded: the matrices, cam and proj_h are patched; saturating and overflowing corners must match too.")
def _(ctx):
    outs = {}
    for p in (0, 1):
        r, rows, t = observe(ctx, f"patch{p}")
        d = d_of(f"patch{p}", t)
        check_frames_and_poses(f"patched path {p}", rows, t, d)
        check_reference(f"patched path {p}", rows, t, d)
        outs[p] = rows
    check_same(outs[0], outs[1], "path 0", "path 1")


@check("path 1 really batches: at least 2 RTPT per cube, at most 2 RTPS per cube, every corner transformed (commands counted at run time)",
       hint="Count the GTE commands in the transform section: path 0 must execute 512 RTPS; path 1 at least 128 RTPT (2 per cube) and at most 128 RTPS.")
def _(ctx):
    _, a, _ = observe(ctx, "base0")
    _, b, _ = observe(ctx, "base1")
    for x in a[1:]:                       # the probe arms its command counters at the first frame_done()
        expect_true(x.rtps_n == 512 and x.rtpt_n == 0, f"path 0, frame {x.n}: 512 RTPS and no RTPT in the transform section", f"{x.rtps_n} RTPS, {x.rtpt_n} RTPT",
                    "Path 0 is the given baseline; leave it alone.")
    for x in b[1:]:
        expect_true(x.rtpt_n >= 2 * NC, f"path 1, frame {x.n}: at least {2 * NC} RTPT per frame", f"{x.rtpt_n} RTPT, {x.rtps_n} RTPS",
                    "Three corners per RTPT: at least two batches per cube; transforming one cube and copying it, or RTPS per corner, does not qualify.")
        expect_true(x.rtps_n <= 2 * NC, f"path 1, frame {x.n}: at most {2 * NC} RTPS per frame", f"{x.rtps_n} RTPS",
                    "At most the two leftover corners per cube may use RTPS.")
        expect_true(x.rtps_n + 3 * x.rtpt_n >= 8 * NC, f"path 1, frame {x.n}: enough commands for 8 corners per cube", f"{x.rtps_n} RTPS + {x.rtpt_n} RTPT x 3",
                    "Every corner of every cube has to be transformed each frame.")


@check(f"cycles: the transform section of path 1 takes at least {int(MIN_SAVING * 100)} % fewer CPU cycles than path 0 (same build)",
       hint="Both paths run the same cubes through the same loop; RTPT does three transforms for one command and saves loads, stores and waits.")
def _(ctx):
    _, a, _ = observe(ctx, "base0")
    _, b, _ = observe(ctx, "base1")
    c0 = median([x.tcyc for x in a[2:]])
    c1 = median([x.tcyc for x in b[2:]])
    expect_true(0.9 * REF_PATH0 <= c0 <= 1.1 * REF_PATH0, f"path 0 costs about {REF_PATH0} cycles for the field (the given baseline)", f"{c0}",
                "Do not change path 0 or the shared code in the transform section.")
    saving = 1 - c1 / c0
    expect_true(saving >= MIN_SAVING, f"path 1 saves >= {MIN_SAVING:.0%} of path 0's {c0} cycles (the reference solution: {REF_PATH0} -> {REF_PATH1}, {1 - REF_PATH1 / REF_PATH0:.0%})",
                f"path 0 {c0}, path 1 {c1}: a saving of {saving:.1%}",
                "Batch every cube's corners: three RTPT (corners 0-2, 3-5, 5-7) or two RTPT and two RTPS; no per-corner loop around RTPS.")
    print(f"        measured: path 0 = {c0} cycles, path 1 = {c1} cycles for 64 cubes: {saving:.1%} fewer ({c0 / c1:.2f}x faster); "
          f"per cube {c0 / NC:.0f} vs {c1 / NC:.0f}")


@check("the program's own timer agrees with the verifier's cycle count (field_cycles[path], both paths, within 3 %)",
       hint="field_cycles[] is written by the given loop from root counter 0 around the transform; do not change the timer code or the markers.")
def _(ctx):
    for p in (0, 1):
        _, rows, _ = observe(ctx, f"base{p}")
        for x in rows[3:]:
            own = x.fc0 if p == 0 else x.fc1
            expect_true(abs(own - x.tcyc) <= 0.03 * x.tcyc + 20, f"path {p}, frame {x.n}: field_cycles[{p}] = {x.tcyc} (+-3 %)", f"{own}",
                        "Keep `t0 = RC0_COUNT; ...; t1 = RC0_COUNT` around the call of the transform in main.")


@check(f"frame budget: the whole frame's work (render_begin() to render_end()) stays under {FRAME_BUDGET} cycles in both paths",
       hint=f"The reference solution needs about {REF_FRAME} (the 64 matrices cost most of it). Budget = 2 x that.")
def _(ctx):
    for p in (0, 1):
        _, rows, _ = observe(ctx, f"base{p}")
        w = max(x.rcyc for x in rows[2:])
        expect_true(0 < w <= FRAME_BUDGET, f"path {p}: cycles per frame <= {FRAME_BUDGET}", f"worst {w}", "Do not add work to the frame loop.")


@check("picture: a coloured tile at the middle of each of the 64 cubes, in both paths",
       hint="The tiles are drawn by the given code from screen_xy: the picture is right when your results are.")
def _(ctx):
    for p in (0, 1):
        r = ctx.run(f"shot{p}", patches=patches_for(p), max_frames=BOOT + 14, shots=[("f", BOOT + 10)])
        rows = [Row(x) for x in (r.record("rows") or [])]
        expect_true(len(rows) >= 8, f"path {p}: frames observed", str(len(rows)))
        img = r.screenshot("f")
        expect_true((img.width, img.height) == (W, H), "the picture is 320 x 240", f"{img.width} x {img.height}")
        for pt in ((0, 0), (W - 1, 0), (0, H - 1), (W - 1, H - 1)):
            expect_true(colors_close(img.pixel(*pt), BG, 12), f"path {p}: corner {pt} is the background {BG}", str(img.pixel(*pt)),
                        "display_clear(16, 16, 32) every frame (given).")
        # the screenshot shows the frame whose results the probe saw as the last row before it; tiles are 8 x 8, cubes move at most
        # a pixel or two per frame, so compare with the nearest recorded frame's centres
        x, best = None, None
        for cand in rows:
            miss = 0
            for c in range(NC):
                a, b = cand.xy[c][0], cand.xy[c][7]
                px, py = (a[0] + b[0]) >> 1, (a[1] + b[1]) >> 1
                if 0 <= px < W and 0 <= py < H and not colors_close(img.pixel(px, py), tile_color(c), 28):
                    miss += 1
            if best is None or miss < best:
                best, x = miss, cand
        expect_true(best == 0, f"path {p}: all 64 tiles are at the centres of their cubes, in their colours",
                    f"{best} of 64 tile centres do not show the tile colour (nearest frame {x.n})",
                    "Path 0 draws them correctly from the given code, so wrong or missing screen_xy words of corners 0 and 7 are the usual cause.")
