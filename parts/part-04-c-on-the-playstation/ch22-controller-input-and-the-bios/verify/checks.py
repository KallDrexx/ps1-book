"""Chapter 22 checks: Controller Input and the BIOS ("Cursor").
STATIC: libpsxe.a (now four modules) exports only the module APIs, the headers are guarded/self-contained/define nothing,
input.c really goes through the BIOS pad driver (it references InitPAD and StartPAD), main.c is thin, data as shipped.
DYNAMIC: the harness presses buttons on PCSX-Redux's pad (`inputs=`: pad overrides; active-low on the wire, the BIOS driver
fills the guest's buffer). The probe records cursor_state every frame and calls input_held/pressed/released directly.
Four scripted runs: base (shipped numbers), patched (speeds, home, color read from the state, not from constants),
clamp (big steps and a bigger sprite against all four edges) and edges (the three queries against the held series)."""
import re
import struct
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]

from harness import *

SW, SH = 320, 240
BG = (24, 24, 32)
NCOL = 6
PALETTE = [(230, 40, 40), (40, 200, 60), (60, 110, 255), (240, 220, 40), (220, 60, 220), (40, 220, 220)]
SHIPPED = dict(x=152, y=112, color=0, speed=2, fast=4, home_x=152, home_y=112, size=16)
FIELDS = ["x", "y", "color", "speed", "fast", "home_x", "home_y", "size"]
STATE_SZ = 4 * len(FIELDS)
MAIN_BUDGET = 70
LAG_TOL = 1             # frames of slack on the length of a measured hold


def state_bytes(**kw):
    d = dict(SHIPPED, **kw)
    return struct.pack("<8i", *(d[k] for k in FIELDS))


# ---- scripted runs: (start frame, buttons, hold frames); every gap between steps is >= 8 frames --------------------
SCRIPT_BASE = [
    (60, ("RIGHT",), 20), (92, ("DOWN",), 15), (112, ("UP", "LEFT"), 10), (130, ("SQUARE", "RIGHT"), 10),
    (148, ("SQUARE",), 10), (166, ("CROSS",), 30), (204, ("CROSS",), 3), (213, ("CROSS",), 3), (222, ("CROSS",), 3),
    (236, ("LEFT", "RIGHT"), 10), (252, ("START",), 12), (284, ("CROSS",), 3), (293, ("CROSS",), 3), (302, ("CROSS",), 3),
]
SCRIPT_PATCH = [(60, ("RIGHT",), 10), (80, ("SQUARE", "DOWN"), 10), (100, ("START",), 10), (118, ("CROSS",), 5)]
SCRIPT_CLAMP = [(60, ("LEFT",), 8), (78, ("UP",), 8), (96, ("RIGHT",), 10), (116, ("DOWN",), 10)]
SCRIPT_EDGES = [(70, ("CROSS",), 30), (90, ("UP",), 12), (115, ("CROSS",), 1)]
RUNS = {
    "base": dict(script=SCRIPT_BASE, patch=None, frames=330, shots=[("a", 100), ("b", 160), ("c", 200), ("d", 232), ("e", 276), ("f", 325)]),
    "patch": dict(script=SCRIPT_PATCH, patch=dict(x=100, y=100, color=3, speed=3, fast=7, home_x=50, home_y=60), frames=135, shots=[]),
    "clamp": dict(script=SCRIPT_CLAMP, patch=dict(x=150, y=100, speed=40, fast=40, home_x=150, home_y=100, size=32), frames=145,
                  shots=[("end", 140)]),
    "edges": dict(script=SCRIPT_EDGES, patch=None, frames=145, shots=[]),
}

config(
    title="Controller Input and the BIOS",
    build="cmake", exe="game.exe", sym="", elf="game.elf",
    break_at=None, max_frames=330,
)


def run(ctx, name):
    spec = RUNS[name]
    inputs = [(f, b, hold) for f, bs, hold in spec["script"] for b in bs]
    patches = {"cursor_state": state_bytes(**spec["patch"])} if spec["patch"] else {}
    r = ctx.run(name, inputs=inputs, patches=patches, max_frames=spec["frames"], shots=spec["shots"])
    r.require_finished()
    return r


def states(r):
    st = r.record("st") or []
    expect_true(len(st) >= 40, "cursor_state readable on at least 40 frames", str(len(st)),
                "Keep the global `cursor_state` and keep the frame loop running.")
    return {s[0]: s for s in st}


def at(sts, f):
    """State sampled at frame f: (x, y, color)."""
    expect_true(f in sts, f"a sample for frame {f}", "missing")
    return tuple(sts[f][1:4])


@static_check("symbols", hint="Keep main, cursor_state and cursor_colors. The linker drops functions nobody calls: the cursor rules must use input_held, input_pressed and input_released.")
def _(ctx):
    ctx.require_symbols("main", "cursor_state", "cursor_colors", "input_init", "input_update", "input_held",
                        "input_pressed", "input_released", "display_init", "display_clear", "display_swap",
                        "ot_begin_frame", "ot_draw", "gfx_quad_f4")


@static_check("data layout as shipped", hint="Do not edit cursor_state's layout or initial values, or the color table.")
def _(ctx):
    base, code = ctx.exe.load_addr, ctx.exe.code
    o = ctx.symbols["cursor_state"] - base
    expect_bytes(code[o:o + STATE_SZ], state_bytes(), "initial `cursor_state` (8 x int32)")
    o = ctx.symbols["cursor_colors"] - base
    expect_bytes(code[o:o + 3 * NCOL], bytes(c for rgb in PALETTE for c in rgb), "`cursor_colors` table")


# ---- structure: the archive and the headers (as in Chapter 21, with one more module) --------------------------------
API = {
    "display": {"display_init", "display_clear", "display_swap"},
    "ot": {"ot_begin_frame", "ot_alloc", "ot_add", "ot_draw", "ot_frames"},
    "gfx": {"gfx_quad_f4"},
    "input": {"input_init", "input_update", "input_held", "input_pressed", "input_released"},
}
HEADERS = list(API)


def _tool(name):
    import shutil
    p = shutil.which(name)
    if not p:
        raise HarnessError(f"{name} not on PATH (source tools/env.sh)")
    return p


def _find_lib(ctx):
    libs = list(ctx.build.build_dir.rglob("libpsxe.a"))
    expect_true(libs, "the build produces libpsxe.a", "no libpsxe.a in the build directory",
                "psxe/CMakeLists.txt: add src/input.c to add_library(psxe STATIC ...).")
    return libs[0]


def _nm_members(path, *flags):
    import subprocess
    out = subprocess.run([_tool("mipsel-none-elf-nm"), *flags, str(path)], capture_output=True, text=True).stdout
    cur, res = "", {}
    for line in out.splitlines():
        if line.endswith(":") and not line.startswith(" "):
            cur = line[:-1]
            res.setdefault(cur, set())
        elif line.strip():
            parts = line.split()
            res[cur].add((parts[-2] if len(parts) >= 3 else parts[0], parts[-1]))
    return res


def _module_of(member):
    return next((k for k in API if re.search(r"(^|[/\\.])" + k + r"\.", member)), None)


@static_check("libpsxe.a exports only the module API, module by module (everything else is static)",
              hint="Declare the helpers and state variables of input.c `static`. The archive exports only the names in the README tables.")
def _(ctx):
    lib = _find_lib(ctx)
    got = {}
    for m, v in _nm_members(lib, "--defined-only", "-g").items():
        key = _module_of(m)
        expect_true(key, "every object in the archive is display, ot, gfx or input", f"unexpected object '{m}'",
                    "One source file per module.")
        got.setdefault(key, set()).update(n for _t, n in v)
    for k, want in API.items():
        have = got.get(k, set())
        expect_true(want <= have, f"module {k} defines {sorted(want)}", f"missing {sorted(want - have)}", f"{k}.c must define the whole API of {k}.h.")
        hdr = ctx.project / "psxe" / "include" / "psxe" / f"{k}.h"
        htxt = re.sub(r"/\*.*?\*/|//.*", "", hdr.read_text(errors="replace"), flags=re.S) if hdr.exists() else ""
        stray = sorted(n for n in have - want if not (n.startswith(k + "_") and re.search(r"\b" + re.escape(n) + r"\b", htxt)))
        expect_true(not stray, f"module {k} exports only its API ({sorted(want)}, plus any {k}_* declared in {k}.h)", f"also exports {stray}",
                    "Put `static` in front of file-private functions and variables (the pad buffer, the two button words).")


@static_check("input.c goes through the BIOS pad driver (InitPAD and StartPAD)",
              hint="input_init() must hand the BIOS two buffers with InitPAD(buf1, len1, buf2, len2), then StartPAD().")
def _(ctx):
    lib = _find_lib(ctx)
    und = None
    for m, v in _nm_members(lib, "--undefined-only").items():
        if _module_of(m) == "input":
            und = {n for _t, n in v}
    expect_true(und is not None, "input.c is part of libpsxe.a", "no input object")
    miss = sorted({"InitPAD", "StartPAD"} - und)
    expect_true(not miss, "input.c calls InitPAD and StartPAD", f"does not reference {miss}",
                "Chapter 22 reads the pad through the BIOS driver: InitPAD(buf, 34, buf2, 34); StartPAD();")


@static_check("headers: include guards, self-contained, define nothing",
              hint="Each psxe/include/psxe/*.h needs #ifndef/#define/#endif (or #pragma once), its own #includes, and only declarations.")
def _(ctx):
    import os, subprocess, tempfile
    gcc = _tool("mipsel-none-elf-gcc")
    inc = ctx.project / "psxe" / "include"
    sdk_inc = Path(os.environ.get("PSN00BSDK_LIBS", ROOT_DIR / ".toolchain/opt/psn00bsdk/lib/libpsn00b")).parents[1] / "include" / "libpsn00b"
    flags = ["-ffreestanding", "-march=r3000", "-msoft-float", "-fno-pic", "-mno-abicalls", "-I", str(inc), "-I", str(sdk_inc), "-Werror"]
    w = Path(tempfile.mkdtemp(prefix="hdr", dir=ctx.work))
    guards = {}
    for h in HEADERS:
        expect_true((inc / "psxe" / f"{h}.h").exists(), f"psxe/include/psxe/{h}.h exists", "missing")
        src = re.sub(r"/\*.*?\*/|//.*", "", (inc / "psxe" / f"{h}.h").read_text(errors="replace"), flags=re.S)
        lines = [l.strip() for l in src.splitlines() if l.strip()]
        g = None
        if any(re.fullmatch(r"#\s*pragma\s+once", l) for l in lines):
            g = "#pragma once"
        elif len(lines) >= 3:
            m1, m2 = re.fullmatch(r"#\s*ifndef\s+(\w+)", lines[0]), re.fullmatch(r"#\s*define\s+(\w+)", lines[1])
            if m1 and m2 and m1.group(1) == m2.group(1) and re.match(r"#\s*endif\b", lines[-1]):
                g = m1.group(1)
        expect_true(g, f"{h}.h has an include guard", "no #ifndef X / #define X ... #endif around the whole file", "Wrap the whole header in a guard.")
        expect_true(g == "#pragma once" or g not in guards, f"{h}.h's guard macro is unique", f"{g} is also used by {guards.get(g)}.h")
        guards[g] = h
        f = w / f"one_{h}.c"
        f.write_text(f"#include <psxe/{h}.h>\n#include <psxe/{h}.h>\n")
        r = subprocess.run([gcc, *flags, "-c", str(f), "-o", str(w / f"one_{h}.o")], capture_output=True, text=True)
        expect_true(r.returncode == 0, f"{h}.h compiles alone and when included twice", r.stderr.strip()[:300], "Add the guard and the #includes the header needs.")
    f = w / "all.c"
    f.write_text("".join(f"#include <psxe/{h}.h>\n" for h in HEADERS))
    r = subprocess.run([gcc, *flags, "-c", str(f), "-o", str(w / "all.o")], capture_output=True, text=True)
    expect_true(r.returncode == 0, "the four headers compile together", r.stderr.strip()[:300], "Conflicting includes?")
    defined = {n for ns in _nm_members(w / "all.o", "--defined-only").values() for _t, n in ns}
    expect_true(not defined, "the headers define no functions or variables", f"defines {sorted(defined)}", "Declarations only (extern, prototypes, macros).")


@static_check("the reference solution mirrors common/psxe (the copy later chapters start from)", hint="Keep solution/psxe's display, ot, gfx and input files identical to common/psxe.")
def _(ctx):
    if not ctx.solution:
        return
    # common/psxe keeps growing (Chapter 24 adds the `fixed` module), so compare this chapter's four modules only.
    ref = ROOT_DIR / "common" / "psxe"
    for m in HEADERS:
        for rel in (f"include/psxe/{m}.h", f"src/{m}.c"):
            p, q = ref / rel, ctx.project / "psxe" / rel
            expect_true(q.exists() and q.read_bytes() == p.read_bytes(), f"solution/psxe/{rel} == common/psxe/{rel}", "differs or missing")


def code_lines(path):
    t = re.sub(r"/\*.*?\*/", "", path.read_text(errors="replace"), flags=re.S)
    t = re.sub(r"//.*", "", t)
    return [l for l in t.splitlines() if l.strip()]


SDK_USE = r"\b(ClearOTagR|DrawOTag|ResetGraph|PutDispEnv|PutDrawEnv|VSync|DrawSync|addPrim|setPolyF4|InitPAD|StartPAD|StopPAD|ChangeClearPAD|PADTYPE|EnterCriticalSection)\b"


@static_check(f"main.c is thin: at most {MAIN_BUDGET} code lines, no SDK graphics or pad calls, the only .c outside psxe/",
              hint="main.c holds the state, the cursor rules and the loop. Pad access lives in psxe/src/input.c.")
def _(ctx):
    m = ctx.project / "main.c"
    expect_true(m.exists(), "main.c exists", "missing")
    n = len(code_lines(m))
    expect_true(n <= MAIN_BUDGET, f"main.c <= {MAIN_BUDGET} non-blank, non-comment lines", f"{n} lines", "Move pad code into psxe/src/input.c.")
    txt = re.sub(r"/\*.*?\*/|//.*", "", m.read_text(errors="replace"), flags=re.S)
    hit = sorted(set(re.findall(SDK_USE, txt)))
    bad_inc = [h for h in ("psxgpu.h", "psxapi.h", "psxpad.h") if h in txt]
    expect_true(not hit and not bad_inc, "main.c uses only psxe headers", f"SDK use in main.c: {hit or bad_inc}", "Call input_* and display_*/ot_*/gfx_*.")
    others = [p.relative_to(ctx.project).as_posix() for p in ctx.project.glob("**/*.c")
              if "build" not in p.relative_to(ctx.project).parts and p.relative_to(ctx.project).parts[0] != "psxe" and p.name != "main.c"]
    expect_true(not others, "no other .c files outside psxe/", str(others), "Library code belongs in psxe/src/.")


# ---- dynamic ---------------------------------------------------------------------------------------------------------
@check("the BIOS pad driver is started once: InitPAD (two buffers in RAM), StartPAD",
       hint="input_init(): InitPAD(buf1, 34, buf2, 34); StartPAD(); ChangeClearPAD(0). Call it once, after display_init().")
def _(ctx):
    r = run(ctx, "base")
    ip = r.record("initpad")
    expect_true(ip, "InitPAD called", "never called", "main() must call input_init(), which calls InitPAD.")
    n, a0, a1, a2, a3 = ip
    expect_eq(n, 1, "InitPAD calls", fmt="dec", hint="Call input_init() once.")
    for a in (a0, a2):
        expect_true(0x80010000 <= a < 0x80200000, "pad buffer inside RAM", hex(a), "Pass the addresses of two arrays.")
    expect_true(a1 >= 8 and a3 >= 8, "buffer lengths of at least 8 bytes", f"{a1}, {a3}", "The SDK examples use 34 bytes for each buffer.")
    expect_eq(r.record("startpad"), 1, "StartPAD calls", fmt="dec", hint="StartPAD() after InitPAD().")


@check("input_update is called once per frame",
       hint="Call input_update() exactly once per iteration of the frame loop, before the queries.")
def _(ctx):
    sts = states(run(ctx, "base"))
    fr = sorted(sts)
    d = [sts[b][4] - sts[a][4] for a, b in zip(fr, fr[1:]) if a >= 45]
    bad = [x for x in d if x != 1]
    expect_true(len(d) > 100 and len(bad) <= 2, "one input_update per vsync after start-up", f"{len(bad)} frames with another count: {bad[:5]}")


def check_segment(sts, start, buttons, hold, spx, pre, name):
    """The cursor moved by `speed` per frame in the pressed directions for ~hold frames (+-LAG_TOL frames)."""
    x0, y0, _c = pre
    x1, y1, _c = at(sts, start + hold + 6)
    dirs = {"LEFT": (-1, 0), "RIGHT": (1, 0), "UP": (0, -1), "DOWN": (0, 1)}
    ex = sum(dirs[b][0] for b in buttons if b in dirs)
    ey = sum(dirs[b][1] for b in buttons if b in dirs)
    for label, got, e in (("x", x1 - x0, ex), ("y", y1 - y0, ey)):
        want = e * spx * hold
        expect_true(abs(got - want) <= spx * LAG_TOL, f"{name}: {label} moves {want} px (+-{spx * LAG_TOL})", f"moved {got} px ({x0},{y0}) -> ({x1},{y1})",
                    "Per frame: held directions move by `speed` (`fast` while Square is held), applied once per frame.")
    steps = [(sts[f][1] - sts[f - 1][1], sts[f][2] - sts[f - 1][2]) for f in range(start - 1, start + hold + 5) if f in sts and f - 1 in sts]
    ok = {0, spx, -spx}
    bad = [s for s in steps if s[0] not in ok or s[1] not in ok]
    expect_true(not bad, f"{name}: every frame moves 0 or exactly {spx} px per axis", f"odd steps {bad[:4]}", "No acceleration, no easing: a fixed step per frame.")


@check("D-pad: 2 px per frame, one axis or both (diagonal), opposite directions cancel",
       hint="For each held direction add or subtract `speed` once per frame; LEFT+RIGHT cancels.")
def _(ctx):
    sts = states(run(ctx, "base"))
    check_segment(sts, 60, ("RIGHT",), 20, 2, at(sts, 59), "RIGHT 20 frames")
    check_segment(sts, 92, ("DOWN",), 15, 2, at(sts, 91), "DOWN 15 frames")
    check_segment(sts, 112, ("UP", "LEFT"), 10, 2, at(sts, 111), "UP+LEFT 10 frames (diagonal)")
    x, y, _ = at(sts, 125)
    expect_true(x < at(sts, 111)[0] and y < at(sts, 111)[1], "the diagonal moved both axes", f"({x},{y})")
    check_segment(sts, 236, ("LEFT", "RIGHT"), 10, 2, at(sts, 235), "LEFT+RIGHT 10 frames")


@check("Square doubles the speed (4 px per frame) and does not move the cursor by itself",
       hint="While Square is held the step is `fast` instead of `speed`. Square alone changes nothing.")
def _(ctx):
    sts = states(run(ctx, "base"))
    check_segment(sts, 130, ("SQUARE", "RIGHT"), 10, 4, at(sts, 129), "SQUARE+RIGHT 10 frames")
    check_segment(sts, 148, ("SQUARE",), 10, 4, at(sts, 147), "SQUARE alone")


@check("X changes the color once per PRESS: a 30-frame hold counts once, three taps count three, 6 colors wrap",
       hint="Use input_pressed(INPUT_CROSS) (the edge), not input_held: held would step the color every frame.")
def _(ctx):
    sts = states(run(ctx, "base"))
    c = {f: s[3] for f, s in sts.items()}
    expect_eq(c[165], 0, "color before the first press", fmt="dec",
              hint="Nothing pressed X yet: if the color changed at start-up, input_update trusted the zeroed buffer (README 5.3).")
    window = [c[f] for f in range(165, 200)]
    changes = sum(1 for a, b in zip(window, window[1:]) if a != b)
    expect_true(changes == 1 and c[200] == 1, "one 30-frame hold: exactly one change, 0 -> 1", f"{changes} changes, color {c[200]}",
                "A held button is not a new press: act only on the frame input_pressed() is true.")
    expect_eq(c[232], 4, "color after three more taps", fmt="dec", hint="Each press, however short, advances the color by one.")
    expect_eq(c[276], 4, "Start and the D-pad leave the color alone", fmt="dec")
    expect_eq(c[325], 1, "three more taps: 4 -> 5 -> 0 -> 1 (the table has 6 colors)", fmt="dec",
              hint="color = (color + 1) % 6.")
    expect_true(all(0 <= v < NCOL for v in c.values()), "color always in 0..5", str(sorted(set(c.values()))))


@check("Start puts the cursor back at (home_x, home_y) when it is RELEASED, and keeps the color",
       hint="On input_released(INPUT_START): x = home_x; y = home_y. Read home from cursor_state, do not hard-code it. Nothing happens while Start is still down.")
def _(ctx):
    sts = states(run(ctx, "base"))
    expect_true(at(sts, 250)[:2] != (152, 112), "the cursor was away from home before Start", str(at(sts, 250)))
    expect_eq(at(sts, 260)[:2], at(sts, 250)[:2], "Start still down (frame 260): the cursor has not moved", fmt="dec",
              hint="Start acts on the frame it is released (input_released), not while it is held.")
    expect_eq(at(sts, 276)[:2], (152, 112), "position after Start is released (shipped home)", fmt="dec")
    s = states(run(ctx, "patch"))
    expect_true(at(s, 108)[:2] != (50, 60), "patched run: Start still down, not home yet", str(at(s, 108)))
    expect_eq(at(s, 116)[:2], (50, 60), "position after Start with home patched to (50, 60)", fmt="dec",
              hint="home_x and home_y are fields of cursor_state: use them.")


@check("speeds, size and color come from cursor_state (patched: speed 3, fast 7, color 3 -> 4)",
       hint="No constants in the rules: read c->speed, c->fast, c->size and the current color from the struct.")
def _(ctx):
    sts = states(run(ctx, "patch"))
    check_segment(sts, 60, ("RIGHT",), 10, 3, at(sts, 59), "RIGHT with speed 3")
    check_segment(sts, 80, ("SQUARE", "DOWN"), 10, 7, at(sts, 79), "SQUARE+DOWN with fast 7")
    expect_eq(at(sts, 130)[2], 4, "color after one press from 3", fmt="dec")


@check("the cursor is clamped to the screen on all four edges (every frame), also for a 32 px square",
       hint="After moving: x in 0..SCREEN_W-size, y in 0..SCREEN_H-size. Clamp, do not wrap and do not stop early.")
def _(ctx):
    sts = states(run(ctx, "clamp"))
    xs, ys = [s[1] for s in sts.values()], [s[2] for s in sts.values()]
    expect_true(min(xs) >= 0 and max(xs) <= SW - 32 and min(ys) >= 0 and max(ys) <= SH - 32, "x in 0..288 and y in 0..208 on every frame",
                f"x {min(xs)}..{max(xs)}, y {min(ys)}..{max(ys)}", "Clamp after the move (and after Start).")
    expect_eq(at(sts, 74)[0], 0, "x after LEFT (speed 40)", fmt="dec")
    expect_eq(at(sts, 92)[1], 0, "y after UP", fmt="dec")
    expect_eq(at(sts, 114)[0], SW - 32, "x after RIGHT", fmt="dec", hint="Limit = SCREEN_W - size = 288, not 304 or 320.")
    expect_eq(at(sts, 138)[1], SH - 32, "y after DOWN", fmt="dec", hint="Limit = SCREEN_H - size = 208.")


def shown(ctx, name, tag, f):
    """Screenshot `tag` of run `name` taken at frame f: the sprite is where cursor_state says, in the color it says."""
    r = run(ctx, name)
    sts = states(r)
    x, y, c = at(sts, f)
    size = 32 if name == "clamp" else 16
    img = r.screenshot(tag)
    expect_eq((img.width, img.height), (SW, SH), "screenshot size")
    rgb = tuple(((v >> 3) << 3) | (v >> 5) for v in PALETTE[c])
    expect_region(img, x + 2, y + 2, size - 4, size - 4, rgb, tol=16, min_fraction=0.99)
    for ox, oy in ((-4, size // 2), (size + 3, size // 2), (size // 2, -4), (size // 2, size + 3)):
        px, py = x + ox, y + oy
        if 0 <= px < SW and 0 <= py < SH:
            expect_pixel(img, px, py, tuple(((v >> 3) << 3) | (v >> 5) for v in BG), tol=10)
    # nowhere else: the rest of the screen is background
    bg = tuple(((v >> 3) << 3) | (v >> 5) for v in BG)
    outside = img.count_not_matching(0, 0, SW, SH, bg, 12)
    expect_true(abs(outside - size * size) <= 2 * size + 4, f"only one {size}x{size} square is drawn", f"{outside} non-background pixels")


@check("screenshots: one square at the position and in the color cursor_state reports (six moments, three runs)",
       hint="The picture must follow the state: draw with gfx_quad_f4 at (x, y), size x size, color cursor_colors[color].")
def _(ctx):
    for tag, f in (("a", 100), ("b", 160), ("c", 200), ("d", 232), ("e", 276), ("f", 325)):
        shown(ctx, "base", tag, f)
    shown(ctx, "clamp", "end", 140)


@check("input_held / input_pressed / input_released, called directly every frame, agree with each other",
       hint="held = down now. pressed = down now and up last reading. released = up now and down last reading. Queries must not change state.")
def _(ctx):
    r = run(ctx, "edges")
    q = r.record("q") or []
    expect_true(len(q) >= 70, "the probe could call the three queries on >= 70 frames", str(len(q)),
                "The program needs display_clear() in its frame loop, and its rules must call input_held, input_pressed and input_released (the linker drops unused functions).")
    # row layout: [frame, then for fn in (held, pressed, released) for mask in (CROSS, UP, UP|CROSS, 0, SQUARE) 2 repeats]
    def col(fn, mi, rep=0): return 1 + fn * 10 + mi * 2 + rep
    frames = [row[0] for row in q]
    for row in q:
        for k in range(1, len(row), 2):
            expect_eq(row[k], row[k + 1], f"a query asked twice in frame {row[0]} gives the same answer (slot {k})", fmt="dec",
                      hint="Queries must be free of side effects: do not clear an edge flag when it is read.")
        expect_true(all(v in (0, 1) for v in row[1:]), "results are 0 or 1", str(row[1:]), "Return 1 for true and 0 for false.")
    names = ("CROSS", "UP")
    for mi, nm in enumerate(names):
        h = [row[col(0, mi)] for row in q]
        p = [row[col(1, mi)] for row in q]
        rl = [row[col(2, mi)] for row in q]
        prev = [0] + h[:-1]
        expect_eq(p, [int(a and not b) for a, b in zip(h, prev)], f"input_pressed({nm}) is held-now-and-not-held-before on every frame", fmt="dec",
                  hint="pressed fires for exactly one frame per press.")
        expect_eq(rl, [int(b and not a) for a, b in zip(h, prev)], f"input_released({nm}) is held-before-and-not-held-now on every frame", fmt="dec",
                  hint="released fires for exactly one frame per release.")
    hc = [row[col(0, 0)] for row in q]
    hu = [row[col(0, 1)] for row in q]

    def run_lengths(s):
        out, i = [], 0
        while i < len(s):
            if s[i]:
                j = i
                while j < len(s) and s[j]:
                    j += 1
                out.append((frames[i], j - i))
                i = j
            else:
                i += 1
        return out
    rc, ru = run_lengths(hc), run_lengths(hu)
    expect_eq(len(rc), 2, "CROSS: two separate presses seen (30 frames, then 1 frame)", fmt="dec", hint=str(rc))
    expect_true(70 <= rc[0][0] <= 73 and abs(rc[0][1] - 30) <= LAG_TOL, "CROSS held ~30 frames, starting within 3 frames of the injected press", str(rc),
                "input_update() must read the BIOS buffer every frame, and `held` must stay true while the button is down.")
    expect_true(115 <= rc[1][0] <= 118 and 1 <= rc[1][1] <= 2, "a one-frame tap is seen as 1 frame", str(rc))
    expect_eq(len(ru), 1, "UP: one press seen, overlapping the CROSS hold", fmt="dec", hint=str(ru))
    expect_true(90 <= ru[0][0] <= 93 and abs(ru[0][1] - 12) <= LAG_TOL, "UP held ~12 frames", str(ru))
    for row in q:
        c, u, both = row[col(0, 0)], row[col(0, 1)], row[col(0, 2)]
        expect_eq(both, int(c or u), f"input_held(UP|CROSS) = any of the two (frame {row[0]})", fmt="dec", hint="A mask with several bits is true if ANY of them qualifies.")
        expect_eq(row[col(1, 2)], int(row[col(1, 0)] or row[col(1, 1)]), f"input_pressed(UP|CROSS) = any (frame {row[0]})", fmt="dec")
        expect_eq(row[col(2, 2)], int(row[col(2, 0)] or row[col(2, 1)]), f"input_released(UP|CROSS) = any (frame {row[0]})", fmt="dec")
        for fn in range(3):
            expect_eq(row[col(fn, 3)], 0, f"query with an empty mask (frame {row[0]})", fmt="dec", hint="An empty mask never qualifies.")
            expect_eq(row[col(fn, 4)], 0, f"Square was never pressed (frame {row[0]})", fmt="dec", hint="Only the buttons of `mask` count.")


@check("raw pad polarity and start-up: an idle pad reports nothing down, also before the first poll",
       hint="The BIOS buffer is active-low (0 = pressed): invert it (now = ~btn), and only after checking stat == 0 and the type.")
def _(ctx):
    # idle pad: nothing held on the frames before the first press
    r = run(ctx, "edges")
    q = r.record("q") or []
    first = [row for row in q if row[0] < 69]
    expect_true(first, "queries on idle frames", "none recorded", "The probe calls input_held/pressed/released from display_clear: all three must exist in the program.")
    for row in first:
        expect_true(all(v == 0 for v in row[1:]), f"idle pad: no button reported down (frame {row[0]})", str(row[1:]),
                    "Idle buttons read as 1 bits in the raw buffer. If every query is true now, you forgot to invert.")
    # start-up: before the driver's first poll the buffer is all zero ("every button down" if trusted)
    sts = states(run(ctx, "base"))
    expect_eq(at(sts, 59), (SHIPPED["x"], SHIPPED["y"], SHIPPED["color"]), "state before the first scripted press (frame 59): untouched",
              fmt="dec", hint="Nothing was pressed yet. A color or position change here means input_update trusted the buffer before the "
                              "first poll (all zero bits = every button down): check stat == 0 and the type first (README 5.3).")
