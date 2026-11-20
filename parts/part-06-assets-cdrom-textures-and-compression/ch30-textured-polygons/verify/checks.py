"""Chapter 30 checks: Textured Polygons ("Crates and Logos").
Build: CMake + PSn00bSDK; the disc holds \\DATA\\CRATE.TIM (8 bpp), PANEL.TIM and LOGO.TIM (4 bpp), made by tools/assets/mkassets.py.
The emulator BOOTS THE .cue.
STATIC: the state symbols exist; the disc holds the three TIMs, byte for byte what the generator makes; their pixel and CLUT data are not
compiled into the EXE.
MAIN RUN (the default placement, the cube spinning, 100 frames after the boot): load_status 0; tim_info equals the TIM headers (parsed here
with tools/assets/tim.py); tex[] holds the texture-page word, CLUT word, texel origin and size that Appendix E.3.4 gives; a VRAM dump taken at
the end shows each TIM's CLUT and image block, exactly, at the rectangle the TIM's own header names; the matrix is a rotation about the
cube's centre; at every sampled frame the polygons found by walking the ordering table are exactly the front faces, each a POLY_FT4 (0x2C)
with neutral colour, the face's texture's tpage and clut, corner UVs in the order top-left, top-right, bottom-left, bottom-right at the
texture's first and last texels (so nothing is mirrored), corners where the projection puts them, in the right ordering-table slot; at three
frames the screenshot is compared with the texture itself, point by point (inverse affine mapping through the polygon the program drew).
ALT RUN: a second disc whose TIMs sit elsewhere in VRAM (other pages, a page in the lower half, other CLUT rows) and whose face-to-texture
table, pose and spin are patched at run time: everything above must hold again. A program that hard-codes a placement, a texture per face or
a flat colour fails.
DIRECT CALLS (probe_direct.lua): tim_parse on valid and damaged TIM images (flags, block sizes, VRAM bounds, CLUT alignment, texture page
limits, trailing bytes, misaligned pointer; *t untouched on failure) and tex_from_tim on crafted descriptions."""
import hashlib
import json
import re
import struct
import subprocess
import sys
import os
from pathlib import Path

from harness import *

ROOT_DIR = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT_DIR / "tools" / "assets"))
import mkassets      # noqa: E402
import img2tim       # noqa: E402
import tim as T      # noqa: E402

W, H = 320, 240
CX, CY = W // 2, H // 2
BG = (16, 16, 32)
MAX_FRAMES = 560
SHOT_FRAMES = (12, 40, 70)
ALT_SHOT = 20
ALT_PATCH = dict(rot=[300, 520, 60], rot_step=[0, 0, 0], face_tex=[2, 0, 1, 1, 2, 0])
DEFAULT_PERM = [0, 1, 2, 0, 1, 2]
NAMES = ("CRATE", "PANEL", "LOGO")                   # texture index -> file
AREA_MARGIN = 250                                    # |NCLIP| below this: nearly edge-on, not judged
SAMPLE_MIN_AREA = 3000                               # NCLIP units (twice the pixel area): faces at least this large are sampled
EDGE_PX = 2.5                                        # sample points keep this far from a triangle's edges
VERT_TOL = 3                                         # pixels: drawn corner vs projected corner
SLOT_TOL = 2
COLOUR_TOL = 18                                      # per channel, 0..255: a texel matches the screen pixel within this

# Alternative placements for the second disc: (bpp, x, y, clut_x, clut_y), keyed by file.
ALT_PLACE = {"CRATE.TIM": (8, 576, 256, 32, 500), "PANEL.TIM": (4, 848, 264, 48, 501), "LOGO.TIM": (4, 964, 320, 0, 502)}

config(
    title="Textured Polygons",
    build="cmake", exe="game.exe", sym="", elf="game.elf", iso="hoverline.cue",
    break_at=None, max_frames=MAX_FRAMES, timeout=90, vram=True,
)

STATE = ["main", "tim_parse", "tim_upload", "tex_from_tim", "tim_info", "tex", "face_tex", "faces", "cube", "load_status", "rot", "rot_step",
         "cam_z", "proj_h", "mtx", "prims_submitted", "frame_no", "frame_done", "screen_xy", "screen_z", "ot_frames"]


# ---- references ---------------------------------------------------------------------------------------------------------------
_REF = {}


def reference(ctx):
    """(files {name: bytes}, pngdir): the generator's TIMs and PNGs, built once into the work directory."""
    if "files" not in _REF:
        out = ctx.work / "refassets"
        files, _ = mkassets.build(out, seed=1, keep_png=True)
        _REF["files"] = {n: files[n + ".TIM"] for n in NAMES}
        _REF["png"] = out / "png"
    return _REF["files"], _REF["png"]


def alt_files(ctx):
    _, png = reference(ctx)
    out = {}
    for n in NAMES:
        bpp, x, y, cx, cy = ALT_PLACE[n + ".TIM"]
        out[n] = img2tim.convert(png / (n.lower() + ".png"), bpp, x, y, cx, cy)
    return out


def describe(data):
    """(Tim, expected Tex words [tpage, clut, u, v, w, h]) of a TIM image, from the reference library."""
    t = T.parse(data)
    bpp = t.bpp
    u0, v0 = T.uv_origin(t.image.x, t.image.y, bpp)
    mult = {4: 4, 8: 2, 16: 1}[bpp]
    return t, dict(tpage=T.tsb(t.image.x, t.image.y, bpp), clut=T.cba(t.clut.x, t.clut.y) if t.clut else 0, u=u0, v=v0, w=t.image.w * mult, h=t.image.h)


def project(row):
    """Float projection of the cube's corners through the matrix the program recorded (m: rows, then t): [(x, y, z)] by corner index."""
    m = [[row[4 + 3 * i + j] / 4096.0 for j in range(3)] for i in range(3)]
    t = row[13:16]
    pts = []
    for c in range(8):
        v = [4096 if c & 1 else -4096, 4096 if c & 2 else -4096, 4096 if c & 4 else -4096]
        x, y, z = (sum(m[i][j] * v[j] for j in range(3)) + t[i] for i in range(3))
        pts.append((CX + x * 256 / z, CY + y * 256 / z, z))
    return pts


FACES = [[0, 1, 2, 3], [5, 4, 7, 6], [4, 0, 6, 2], [1, 5, 3, 7], [4, 5, 0, 1], [2, 3, 6, 7]]


def nclip(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])


def visible_faces(row):
    """([(face, corners (x, y, z) x4, area)] of the faces that clearly face the camera, the same for the nearly edge-on ones)."""
    pts = project(row)
    out, unsure = [], []
    for f, idx in enumerate(FACES):
        ps = [pts[i] for i in idx]
        area = nclip(ps[0], ps[1], ps[2])
        if abs(area) < AREA_MARGIN:
            unsure.append((f, ps, area))
        elif area > 0:
            out.append((f, ps, area))
    return out, unsure


# ---- the disc image ---------------------------------------------------------------------------------------------------------
class Iso:
    """Reads mkpsxiso's raw 2352-byte Mode 2 Form 1 images: 24 bytes of sync/header/subheader, then 2048 data bytes."""

    def __init__(self, path):
        self.d = Path(path).read_bytes()
        pvd = self.sector(16)
        if pvd[1:6] != b"CD001":
            raise CheckFailure(expected="an ISO9660 volume descriptor at sector 16", actual="none", hint="mkpsxiso failed?")
        self.files = {}
        self._walk(struct.unpack_from("<I", pvd, 156 + 2)[0], struct.unpack_from("<I", pvd, 156 + 10)[0], "\\")

    def sector(self, lba, n=1):
        return b"".join(self.d[(lba + i) * 2352 + 24:(lba + i) * 2352 + 24 + 2048] for i in range(n))

    def _walk(self, lba, size, prefix):
        data = self.sector(lba, (size + 2047) // 2048)
        pos = 0
        while pos < size:
            ln = data[pos]
            if ln == 0:
                pos = (pos // 2048 + 1) * 2048
                continue
            rec = data[pos:pos + ln]
            pos += ln
            nlen = rec[32]
            name = rec[33:33 + nlen]
            if name in (b"\x00", b"\x01"):
                continue
            nm = name.decode("ascii").split(";")[0]
            elba, esize = struct.unpack_from("<I", rec, 2)[0], struct.unpack_from("<I", rec, 10)[0]
            if rec[25] & 2:
                self._walk(elba, esize, prefix + nm + "\\")
            else:
                self.files[prefix + nm] = (elba, esize)

    def read(self, path):
        lba, size = self.files[path]
        return self.sector(lba, (size + 2047) // 2048)[:size]


def disc(ctx):
    return Iso(ctx.build.build_dir / "hoverline.bin")


def lua_val(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (bytes, bytearray)):
        return "{" + ",".join(str(b) for b in v) + "}"
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, dict):
        return "{" + ",".join(f"[{json.dumps(k)}]={lua_val(x)}" for k, x in v.items()) + "}"
    return "{" + ",".join(lua_val(x) for x in v) + "}"




# ---- static checks --------------------------------------------------------------------------------------------------------------
@static_check("the state symbols exist", hint="Keep the functions and globals the starter declares (tim_parse, tex_from_tim, tim_info, tex, face_tex ...).")
def _(ctx):
    ctx.require_symbols(*STATE)


@static_check("the disc image has SYSTEM.CNF, HOVER.EXE and the three TIMs in DATA",
              hint="Check iso.xml: CRATE.TIM, PANEL.TIM and LOGO.TIM inside <dir name=\"DATA\">, sources under assets/.")
def _(ctx):
    iso = disc(ctx)
    files, _ = reference(ctx)
    for p in ("\\SYSTEM.CNF", "\\HOVER.EXE") + tuple(f"\\DATA\\{n}.TIM" for n in NAMES):
        expect_true(p in iso.files, f"{p} on the disc", f"found {sorted(iso.files)}")
    expect_eq(iso.read("\\HOVER.EXE"), (ctx.build.build_dir / "game.exe").read_bytes(), "HOVER.EXE on the disc is the built game.exe")
    for n in NAMES:
        expect_eq(hashlib.sha256(iso.read(f"\\DATA\\{n}.TIM")).hexdigest(), hashlib.sha256(files[n]).hexdigest(), f"{n}.TIM is what mkassets.py makes",
                  hint="The CMake rule runs tools/assets/mkassets.py into build/assets; iso.xml must point there.")


@static_check("the textures are not inside the program",
              hint="The TIMs must be read from the disc at run time, not compiled into the EXE (xxd -i).")
def _(ctx):
    exe = (ctx.build.build_dir / "game.exe").read_bytes()
    files, _ = reference(ctx)
    for n in NAMES:
        t = T.parse(files[n])
        expect_true(t.image.data not in exe, f"{n}'s pixel data is not in game.exe", "found its bytes in the executable")
        if t.clut:
            expect_true(t.clut.data not in exe, f"{n}'s CLUT is not in game.exe", "found its bytes in the executable")


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


# ---- the alternative disc ----------------------------------------------------------------------------------------------------------
def alt_disc(ctx):
    """Build alt.bin/alt.cue next to hoverline.*: the same exe and layout with the TIMs moved to other VRAM rectangles."""
    bdir = ctx.build.build_dir
    if (bdir / "alt.cue").exists():
        return
    xml = next(iter(sorted(bdir.glob("cd_image_*.xml"))), None)
    if xml is None:
        raise CheckFailure(expected="CMake's configured iso xml", actual="not found", hint="Use psn00bsdk_add_cd_image.")
    (bdir / "alt").mkdir(exist_ok=True)
    text = xml.read_text()
    for n, data in alt_files(ctx).items():
        (bdir / "alt" / f"{n}.TIM").write_bytes(data)
        text, k = re.subn(r'(<file\s+name="' + n + r'\.TIM"[^>]*?source=")[^"]*(")', lambda m: m.group(1) + str(bdir / "alt" / f"{n}.TIM") + m.group(2),
                          text, flags=re.I)
        expect_eq(k, 1, f"iso.xml has one <file name=\"{n}.TIM\" source=...> entry", hint="Appendix E.2")
    (bdir / "alt.xml").write_text(text)
    p = subprocess.run(["mkpsxiso", "-y", "-q", "-o", "alt.bin", "-c", "alt.cue", "alt.xml"], cwd=bdir, capture_output=True, text=True,
                       timeout=60, env=tool_env())
    expect_eq(p.returncode, 0, "mkpsxiso builds the alternative disc", hint=(p.stdout + p.stderr)[-400:])


def lua_patch(ctx):
    gen = ctx.work / "probe_alt_gen.lua"
    gen.write_text("PATCH = " + lua_val(dict(ALT_PATCH, shots=[ALT_SHOT])) + "\ndofile(" + json.dumps(str(ctx.chapter_dir / "verify" / "probe.lua")) + ")\n")
    return gen


STATUS = {100: "cd_init() failed (CdInit)", 1: "loading \\DATA\\CRATE.TIM;1 failed (cd_load_file returned NULL, or tim_parse rejected it)",
          2: "loading \\DATA\\PANEL.TIM;1 failed (cd_load_file returned NULL, or tim_parse rejected it)",
          3: "loading \\DATA\\LOGO.TIM;1 failed (cd_load_file returned NULL, or tim_parse rejected it)"}


def observe(ctx, name):
    """(RunResult, rows, textures) of the main run or the alt run; fails with a precise message when it never got going.
    rows are the probe rows from frame 3 on; textures are the three TIM images on that disc (bytes)."""
    if name == "main":
        r = ctx.result
        files, _ = reference(ctx)
    else:
        alt_disc(ctx)
        r = ctx.run("alt", iso="alt.cue", probe=lua_patch(ctx))
        files = alt_files(ctx)
    r.require_finished()
    exc = r.record("exception")
    if exc:
        raise CheckFailure(expected="no CPU exception", actual=f"CPU exception {exc['code']} at pc 0x{exc['epc']:08X}, address 0x{exc['badvaddr']:08X}",
                           hint="A load or store through a bad or misaligned pointer? Texture data read past its buffer?")
    rows = [x for x in (r.record("rows") or []) if x[0] >= 3]
    expect_true(len(rows) >= 40, "the frame loop runs (40+ frames) after loading",
                f"{len(rows)} frames; boot + load take about 400 emulated frames",
                hint="Does the program hang inside cd_load_file or LoadImage / DrawSync?")
    st = rows[0][17]
    expect_eq(st, 0, "load_status", hint=STATUS.get(st, "") + " The screen is red when loading fails.")
    return r, rows, files


# ---- dynamic checks: loading and VRAM -------------------------------------------------------------------------------------------------
def info_words(data, ptr_check=True):
    t = T.parse(data)
    c = t.clut
    return [t.bpp, c.x if c else 0, c.y if c else 0, c.w if c else 0, c.h if c else 0, t.image.x, t.image.y, t.image.w, t.image.h]


def check_loading(ctx, name):
    r, rows, files = observe(ctx, name)
    info = r.record("tim_info")
    tex = r.record("tex")
    for i, n in enumerate(NAMES):
        want = info_words(files[n])
        got = info[11 * i:11 * i + 9]
        expect_eq(got, want, f"{name}: tim_info[{i}] ({n}) [bpp, clut x y w h, image x y w h]",
                  hint="Read the header and block fields little-endian; widths are in 16-bit units, exactly as the file says.")
        clut_ptr, img_ptr = info[11 * i + 9], info[11 * i + 10]
        expect_true(0x80000000 <= img_ptr < 0x80200000 and img_ptr % 4 == 0, f"{name}: {n}: img_data is an aligned RAM address", f"0x{img_ptr:08X}")
        expect_eq(clut_ptr != 0, bool(want[3]), f"{name}: {n}: clut_data is set exactly when the TIM has a CLUT", f"0x{clut_ptr:08X}")
        _, wt = describe(files[n])
        expect_eq(tex[6 * i:6 * i + 6], [wt[k] for k in ("tpage", "clut", "u", "v", "w", "h")], f"{name}: tex[{i}] ({n}) [tpage, clut, u, v, w, h]",
                  fmt="dec", hint="Appendix E.3.4: tpage = x/64 | y/256 << 4 | tp << 7; clut = x/16 | y << 6; u = (x mod 64) * (4 at 4 bpp, 2 at 8 bpp); v = y mod 256; w in texels.")
    return r, rows, files


@check("boots from the disc, loads the three TIMs; tim_info and tex[] describe them",
       hint="tim_parse reads the header and both blocks; tex_from_tim applies the formulas of Appendix E.3.4.")
def _(ctx):
    check_loading(ctx, "main")


def check_vram(ctx, name):
    r, rows, files = observe(ctx, name)
    vram = r.vram()
    for n in NAMES:
        t = T.parse(files[n])
        if t.clut:
            vram.expect_rect(t.clut.x, t.clut.y, t.clut.w, t.clut.h, t.clut.data)
        vram.expect_rect(t.image.x, t.image.y, t.image.w, t.image.h, t.image.data)


@check("VRAM holds each TIM's CLUT and image at the rectangle its own header names, byte for byte",
       hint="LoadImage with the RECT from the block header (x and w in 16-bit units), the data pointer after the 12-byte block header; DrawSync afterwards.")
def _(ctx):
    check_vram(ctx, "main")


@check("an alternative disc (TIMs at other places in VRAM): tim_info, tex[] and VRAM follow the headers",
       hint="Nothing about where the textures sit may be built into the program: read the rectangles from the file.")
def _(ctx):
    check_loading(ctx, "alt")
    check_vram(ctx, "alt")


# ---- dynamic checks: motion, primitives, picture ---------------------------------------------------------------------------------------
def check_motion(r, rows, name, frozen=False):
    step = r.record("rotstep")
    cam_z = r.record("cam_z")
    if not frozen:
        expect_true(any(step) and all(abs(s) <= 64 for s in step), f"{name}: rot_step is a slow turn", str(step), hint="Non-zero, at most 64 units per frame.")
    for a, b in zip(rows, rows[1:]):
        if frozen:
            expect_eq([b[i] for i in (1, 2, 3)], [a[i] for i in (1, 2, 3)], f"{name}: rot stays put when rot_step is 0 (frame {b[0]})",
                      hint="Do not add anything else to rot; read rot_step every frame.")
        else:
            expect_eq([b[i] for i in (1, 2, 3)], [(a[i] + step[i - 1]) & 4095 for i in (1, 2, 3)], f"{name}: rot advances by rot_step (frame {b[0]})",
                      hint="rot += rot_step, wrapped with & 4095, once per frame.")
    for row in rows[::9]:
        m = [row[4 + 3 * i:7 + 3 * i] for i in range(3)]
        for i in range(3):
            n2 = sum(c * c for c in m[i]) / 4096.0 ** 2
            expect_true(0.94 < n2 < 1.06, f"{name}: frame {row[0]}: matrix row {i} has length 1.0", f"{n2:.3f}", hint="RotMatrix(&rot, &mtx) then TransMatrix.")
        expect_eq(row[13:16], [0, 0, cam_z], f"{name}: frame {row[0]}: translation (0, 0, cam_z)", hint="TransMatrix(&mtx, &pos) with pos = {0, 0, cam_z}.")


def prim_list(row):
    flat = row[19]
    return [flat[i:i + 23] for i in range(0, len(flat), 23)]


def check_prims(row, perm, files, name):
    """Walk one frame's polygons: exactly the front faces, each a correct POLY_FT4. Returns {face: prim}."""
    vis, edge = visible_faces(row)
    unsure = len(edge)
    prims = prim_list(row)
    fr = row[0]
    expect_eq(row[16], len(prims), f"{name}: frame {fr}: prims_submitted = polygons linked", hint="Count what you link.")
    expect_true(abs(len(prims) - len(vis)) <= unsure, f"{name}: frame {fr}: {len(vis)} faces face the camera (+-{unsure} edge-on)", f"{len(prims)} polygons",
                hint="Back-face culling with NCLIP (> 0 is front): one POLY_FT4 per front face.")
    found = {}
    for p in prims:
        slot, code, r, g, b = p[:5]
        expect_eq(code, 0x2C, f"{name}: frame {fr}: polygon command byte", fmt="hex", hint="POLY_FT4 is 0x2C: setPolyFT4(p).")
        expect_eq([r, g, b], [128, 128, 128], f"{name}: frame {fr}: colour is neutral (0x80)", hint="setRGB0(p, 128, 128, 128): texel * 128 / 128.")
        corners = [(p[5 + 4 * k], p[6 + 4 * k]) for k in range(4)]
        match = None
        for f, ps, area in vis + edge:
            if all(abs(corners[k][0] - ps[k][0]) <= VERT_TOL and abs(corners[k][1] - ps[k][1]) <= VERT_TOL for k in range(4)):
                match = (f, ps)
        if match is None:
            vis_near = [f for f, ps, a in vis if all(abs(corners[k][0] - ps[k][0]) <= 12 and abs(corners[k][1] - ps[k][1]) <= 12 for k in range(4))]
            raise CheckFailure(expected=f"a polygon at each front face's projected corners (+-{VERT_TOL} px), corners in the face table's order",
                               actual=f"a polygon at {corners} matches no front face" + (" (a face is close: corner order?)" if vis_near else ""),
                               hint="Corners are faces[f][0..3] in that order, from screen_xy.")
        f, ps = match
        expect_true(f not in found, f"{name}: frame {fr}: face {f} is drawn once", "twice")
        found[f] = p
        t, tx = describe(files[NAMES[perm[f]]])
        got_tpage, got_clut = p[22], p[21]
        expect_eq(got_tpage & 0x1FF, tx["tpage"], f"{name}: frame {fr}: face {f} ({NAMES[perm[f]]}) tpage word (x/64, y/256, abr, tp)", fmt="hex",
                  hint="p->tpage = tex.tpage: from the TIM's image rectangle: x/64 | y/256 << 4 | tp << 7 (tp: 0 = 4 bpp, 1 = 8 bpp).")
        expect_eq(got_clut, tx["clut"], f"{name}: frame {fr}: face {f} ({NAMES[perm[f]]}) clut word (x/16, y)", fmt="hex",
                  hint="p->clut = tex.clut: x/16 | y << 6, from the TIM's CLUT rectangle.")
        u0, v0, u1, v1 = tx["u"], tx["v"], tx["u"] + tx["w"] - 1, tx["v"] + tx["h"] - 1
        want = [(u0, v0), (u1, v0), (u0, v1), (u1, v1)]
        got = [(p[7 + 4 * k], p[8 + 4 * k]) for k in range(4)]
        hint = ("Corner k of a face is top-left, top-right, bottom-left, bottom-right as seen from outside: u = u0 (k even) or u0 + w - 1 (k odd); "
                "v = v0 (k < 2) or v0 + h - 1.")
        if got == [(u1, v0), (u0, v0), (u1, v1), (u0, v1)]:
            hint = "The texture is mirrored left-right: corner 0 must take the LEFT edge. " + hint
        expect_eq(got, want, f"{name}: frame {fr}: face {f} ({NAMES[perm[f]]}) corner UVs", hint=hint)
        otz = int(sum(z for _, _, z in ps) * 256 // 4096)
        expect_true(abs(slot - min(63, max(0, otz >> 7))) <= SLOT_TOL, f"{name}: frame {fr}: face {f} is in ordering-table slot ~{min(63, otz >> 7)}",
                    str(slot), hint="Slot = OTZ >> 7, OTZ from AVSZ4 of the face's four screen_z values.")
    return found


def tex_pixels(data):
    t = T.parse(data)
    w, h, px = T.decode_rgba(t)
    return w, h, px


def check_picture(r, rows, perm, files, name, frames):
    """Compare the screenshot with the textures: for points inside each large front face, the pixel is the texel the affine mapping gives."""
    byframe = {row[0]: row for row in rows}
    cache = {}
    for fr in frames:
        row = byframe[fr]
        img = r.screenshot(f"f{fr}")
        found = check_prims(row, perm, files, name)
        tested = 0
        for f, p in found.items():
            area = nclip((p[5], p[6]), (p[9], p[10]), (p[13], p[14]))
            if area < SAMPLE_MIN_AREA:
                continue
            key = NAMES[perm[f]]
            if key not in cache:
                cache[key] = tex_pixels(files[key])
            tw, th, px = cache[key]
            _, tx = describe(files[key])
            V = [(p[5 + 4 * k], p[6 + 4 * k]) for k in range(4)]
            UV = [(p[7 + 4 * k] - tx["u"], p[8 + 4 * k] - tx["v"]) for k in range(4)]
            ok = bad = 0
            first_bad = None
            seen = set()                                        # screen colours at the sample points: a flat polygon shows one
            xs = [v[0] for v in V]
            ys = [v[1] for v in V]
            for y in range(max(0, min(ys)), min(H, max(ys) + 1)):
                for x in range(max(0, min(xs)), min(W, max(xs) + 1)):
                    for tri in ((0, 1, 2), (1, 2, 3)):
                        a, b, c = (V[i] for i in tri)
                        den = nclip(a, b, c)
                        if den == 0:
                            continue
                        w0 = nclip((x, y), b, c) / den                  # barycentric weights
                        w1 = nclip(a, (x, y), c) / den
                        w2 = 1 - w0 - w1
                        if min(w0, w1, w2) < 0:
                            continue
                        # distance to each edge = weight * height; height_i = |den| / |edge_i|
                        dist = [w0 * abs(den) / max(1.0, ((b[0] - c[0]) ** 2 + (b[1] - c[1]) ** 2) ** 0.5),
                                w1 * abs(den) / max(1.0, ((a[0] - c[0]) ** 2 + (a[1] - c[1]) ** 2) ** 0.5),
                                w2 * abs(den) / max(1.0, ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5)]
                        if min(dist) < EDGE_PX or (x + y) % 3:
                            break
                        u = w0 * UV[tri[0]][0] + w1 * UV[tri[1]][0] + w2 * UV[tri[2]][0]
                        v = w0 * UV[tri[0]][1] + w1 * UV[tri[1]][1] + w2 * UV[tri[2]][1]
                        ix, iy = int(u), int(v)
                        got = img.pixel(x, y)
                        seen.add(tuple(got[:3]))
                        hit = False
                        for dy in (-1, 0, 1):
                            for dx in (-1, 0, 1):
                                jx, jy = min(tw - 1, max(0, ix + dx)), min(th - 1, max(0, iy + dy))
                                e = px[jy * tw + jx]
                                if max(abs(got[i] - e[i]) for i in range(3)) <= COLOUR_TOL:
                                    hit = True
                        if hit:
                            ok += 1
                        else:
                            bad += 1
                            first_bad = first_bad or (x, y, got, px[min(th - 1, max(0, iy)) * tw + min(tw - 1, max(0, ix))][:3])
                        break
            tested += 1
            expect_true(ok + bad >= 25, f"{name}: frame {fr}: face {f} has enough sample points", f"{ok + bad}")
            expect_true(ok >= 0.9 * (ok + bad), f"{name}: frame {fr}: face {f} shows the {key} texture ({ok} of {ok + bad} sample points match)",
                        f"{ok} of {ok + bad}; e.g. pixel {first_bad[:2]} is {first_bad[2]}, the texel there is {first_bad[3]}" if first_bad else "",
                        hint="Right colours but the wrong picture: UVs. Wrong colours: the CLUT word or the CLUT upload. Garbage: tpage or the image upload. "
                             "Flat colour: the polygon is not textured.")
            # The 3 x 3-texel tolerance lets one mid-grey 'match' a low-contrast texture (the panel); a textured face shows several colours.
            need = min(3, len({q[:3] for q in px}))
            expect_true(len(seen) >= need, f"{name}: frame {fr}: face {f} is textured ({len(seen)} distinct colours where the {key} texture has several)",
                        f"{len(seen)} colour(s)", hint="Flat colour: the polygon is not textured (code 0x2C, tpage and UVs).")
        expect_true(tested >= 1, f"{name}: frame {fr}: at least one large face to sample", "none", hint="Is the cube drawn?")


@check("the cube spins about its centre; the matrix is a rotation",
       hint="rot += rot_step each frame; RotMatrix + TransMatrix(0, 0, cam_z).")
def _(ctx):
    r, rows, _ = observe(ctx, "main")
    check_motion(r, rows, "cube")
    expect_eq(r.record("face_tex"), DEFAULT_PERM, "face_tex starts as the book's table", hint="Do not change the initial values.")


@check("polygons: one POLY_FT4 per front face with the right tpage, clut, UVs, corners and slot",
       hint="See 7.2: setPolyFT4, neutral colour, corners faces[f][0..3], UVs at the texture's first and last texels, tpage and clut from tex[face_tex[f]].")
def _(ctx):
    r, rows, files = observe(ctx, "main")
    for row in rows[::4]:
        check_prims(row, DEFAULT_PERM, files, "cube")


@check("picture: every large front face shows its texture (crate, panel, logo), not mirrored",
       hint="Compare the screenshot with the TIM: wrong palette, wrong page or mirrored UVs all show up here.")
def _(ctx):
    r, rows, files = observe(ctx, "main")
    check_picture(r, rows, DEFAULT_PERM, files, "cube", SHOT_FRAMES)


@check("alt run: another face-to-texture table, another pose, frozen: polygons and picture follow",
       hint="face_tex[] is read every frame (nothing about the default table is built in); rot_step = 0 stops the cube.")
def _(ctx):
    r, rows, files = observe(ctx, "alt")
    check_motion(r, rows, "alt cube", frozen=True)
    for row in rows[::6]:
        check_prims(row, ALT_PATCH["face_tex"], files, "alt cube")
    check_picture(r, rows, ALT_PATCH["face_tex"], files, "alt cube", (ALT_SHOT,))


# ---- dynamic checks: direct calls -------------------------------------------------------------------------------------------------------
def tim_image(pmode, clut=None, img=(704, 0, 16, 4), flags=None, clut_bnum=None, img_bnum=None, magic=0x10, tail=b"", cut=0):
    """Hand-made TIM image. clut / img = (x, y, w, h); data is a counting pattern. Sizes can be falsified for the bad cases."""
    fl = (pmode | (8 if clut else 0)) if flags is None else flags
    out = struct.pack("<II", magic, fl)
    for blk, bnum in ((clut, clut_bnum), (img, img_bnum)):
        if blk is None:
            continue
        x, y, w, h = blk
        n = 12 + w * h * 2
        out += struct.pack("<IHHHH", n if bnum is None else bnum, x, y, w, h)
        out += bytes((i * 7 + x) & 255 for i in range(w * h * 2))
    out += tail
    return out[:len(out) - cut] if cut else out


GOOD = [
    ("4 bpp, 8x2 pixels at (320,16), CLUT at (0,480)", tim_image(0, (0, 480, 16, 1), (320, 16, 2, 2)), 4, (0, 480, 16, 1), (320, 16, 2, 2)),
    ("4 bpp, 128x64 at (964,320): a texture in the lower page row", tim_image(0, (0, 502, 16, 1), (964, 320, 32, 64)), 4, (0, 502, 16, 1), (964, 320, 32, 64)),
    ("8 bpp, 64x64 at (704,0), CLUT at (0,496)", tim_image(1, (0, 496, 256, 1), (704, 0, 32, 64)), 8, (0, 496, 256, 1), (704, 0, 32, 64)),
    ("8 bpp, CLUT with 2 rows", tim_image(1, (16, 500, 256, 2), (640, 128, 16, 32)), 8, (16, 500, 256, 2), (640, 128, 16, 32)),
    ("8 bpp, 64x16 at (740,0): crosses x = 768, still inside its 128-unit page", tim_image(1, (0, 496, 256, 1), (740, 0, 32, 16)), 8, (0, 496, 256, 1),
     (740, 0, 32, 16)),
    ("16 bpp, 64x64 at (832,0), no CLUT", tim_image(2, None, (832, 0, 64, 64)), 16, None, (832, 0, 64, 64)),
    ("4 bpp, exactly one page (256x256) at (320,256)", tim_image(0, (0, 480, 16, 1), (320, 256, 64, 256)), 4, (0, 480, 16, 1), (320, 256, 64, 256)),
]
BAD = [
    ("bad magic", tim_image(0, (0, 480, 16, 1), (320, 16, 2, 2), magic=0x11)),
    ("24 bpp (not a texture)", tim_image(3, None, (320, 16, 6, 2))),
    ("mixed mode (pmode 4)", tim_image(4, (0, 480, 16, 1), (320, 16, 2, 2), flags=4 | 8)),
    ("an unknown flag bit", tim_image(0, (0, 480, 16, 1), (320, 16, 2, 2), flags=0 | 8 | 16)),
    ("4 bpp without a CLUT", tim_image(0, None, (320, 16, 2, 2))),
    ("16 bpp with a CLUT", tim_image(2, (0, 480, 16, 1), (832, 0, 4, 2))),
    ("one block byte-count too small", tim_image(0, (0, 480, 16, 1), (320, 16, 2, 2), img_bnum=12 + 2 * 2 * 2 - 2)),
    ("CLUT bnum does not match w*h", tim_image(0, (0, 480, 16, 1), (320, 16, 2, 2), clut_bnum=12 + 16)),
    ("file 4 bytes short", tim_image(0, (0, 480, 16, 1), (320, 16, 2, 2), cut=4)),
    ("4 trailing bytes", tim_image(0, (0, 480, 16, 1), (320, 16, 2, 2), tail=bytes(4))),
    ("image runs off the right of VRAM (x + w > 1024)", tim_image(1, (0, 480, 256, 1), (1000, 0, 32, 4))),
    ("image runs off the bottom of VRAM (y + h > 512)", tim_image(0, (0, 480, 16, 1), (320, 500, 2, 16))),
    ("CLUT x is not a multiple of 16", tim_image(0, (8, 480, 16, 1), (320, 16, 2, 2))),
    ("4 bpp CLUT is not 16 entries wide", tim_image(0, (0, 480, 32, 1), (320, 16, 2, 2))),
    ("8 bpp CLUT is not 256 entries wide", tim_image(1, (0, 480, 16, 1), (320, 16, 2, 2))),
    ("image crosses the right edge of its texture page (4 bpp, x = 60, 32 texels)", tim_image(0, (0, 480, 16, 1), (316, 0, 8, 4))),
    ("image crosses the bottom of its texture page (y = 250, 16 lines)", tim_image(0, (0, 480, 16, 1), (320, 250, 2, 16))),
    ("zero width", tim_image(0, (0, 480, 16, 1), (320, 16, 0, 2))),
    ("smaller than the headers", tim_image(0, (0, 480, 16, 1), (320, 16, 2, 2))[:16]),
]


TEX_CASES = [
    ("8 bpp image (704,0), CLUT (0,496)", (8, 0, 496, 256, 1, 704, 0, 32, 64)),
    ("4 bpp image (736,0), CLUT (0,497): u0 = 128", (4, 0, 497, 16, 1, 736, 0, 16, 64)),
    ("4 bpp image (964,320), CLUT (0,502): second page row, u0 = 16, v0 = 64", (4, 0, 502, 16, 1, 964, 320, 32, 64)),
    ("8 bpp image (576,256), CLUT (32,500)", (8, 32, 500, 256, 1, 576, 256, 32, 64)),
    ("8 bpp image (1000,490): last page column, CLUT (240,511)", (8, 240, 511, 256, 1, 1000, 490, 24, 20)),
    ("8 bpp image (740,0): crosses a 64-unit boundary inside its page, u0 = 72", (8, 0, 496, 256, 1, 740, 0, 32, 16)),
    ("16 bpp image (832,0), no CLUT", (16, 0, 0, 0, 0, 832, 0, 64, 64)),
    ("16 bpp image (900,300): u0 = 4, v0 = 44", (16, 0, 0, 0, 0, 900, 300, 100, 64)),
]


def direct_cases():
    parse = []
    for name, img, *_ in GOOD:
        parse.append(dict(name=name, data=img, misalign=False))
    for name, img in BAD:
        parse.append(dict(name=name, data=img, misalign=False))
    parse.append(dict(name="a pointer that is not 4-byte aligned", data=GOOD[0][1], misalign=True))
    tex = [dict(name=n, info=list(w) + [0, 0]) for n, w in TEX_CASES]
    return dict(parse=parse, tex=tex)


def direct_run(ctx):
    cases = direct_cases()
    gen = ctx.work / "probe_direct_gen.lua"
    gen.write_text("CASES = " + lua_val(cases) + "\ndofile(" + json.dumps(str(ctx.chapter_dir / "verify" / "probe_direct.lua")) + ")\n")
    r = ctx.run("direct", probe=gen, max_frames=900)
    r.require_finished()
    exc = r.record("exception")
    if exc:
        raise CheckFailure(expected="no CPU exception in a direct call", actual=f"exception {exc['code']} in {exc.get('fn')} ({exc.get('name')}) at pc "
                           f"0x{exc['epc']:08X}, address 0x{exc['badvaddr']:08X}", hint="Reading past the end of the image? A misaligned word read?")
    recs = r.record("cases")
    expect_true(recs and len(recs) == len(cases["parse"]) + len(cases["tex"]), "all direct calls completed",
                f"{len(recs or [])} of {len(cases['parse']) + len(cases['tex'])} (status {r.data.get('status')})", hint="A call that never returns?")
    return cases, recs


@check("tim_parse: accepts valid TIMs (4, 8, 16 bpp), rejects damaged ones; *t untouched on failure",
       hint="Validate before you trust: magic, flags, block sizes (bnum = 12 + 2wh), VRAM bounds, CLUT width and alignment, the texture page, the exact size.")
def _(ctx):
    cases, recs = direct_run(ctx)
    nparse = len(cases["parse"])
    untouched = [0xA5A5A5A5] * 11
    for k, rec in enumerate(recs[:nparse]):
        name = cases["parse"][k]["name"]
        if k < len(GOOD):
            _, _, bpp, clut, img = GOOD[k]
            expect_eq(rec["v0"], 1, f"tim_parse accepts: {name}")
            base = rec["data_addr"]
            c = clut or (0, 0, 0, 0)
            exp = [bpp, *c, *img, base + 20 if clut else 0, 0]
            exp[10] = base + 8 + (12 + 2 * clut[2] * clut[3] if clut else 0) + 12
            if clut:
                exp[9] = base + 8 + 12
            expect_eq(rec["info"], exp, f"TimInfo for: {name} [bpp, clut x y w h, image x y w h, clut_data, img_data]", fmt="dec",
                      hint="Fields are little-endian, widths in 16-bit units; the data pointers point into the image, just after each 12-byte block header.")
        else:
            expect_eq(rec["v0"], 0, f"tim_parse rejects: {name}", hint="Return 0 for anything that is not a usable TIM texture.")
            expect_eq(rec["info"], untouched, f"*t untouched after: {name}", fmt="hex", hint="Write *t only once the whole image has been validated.")


@check("tex_from_tim: tpage word, clut word, texel origin and size for crafted placements",
       hint="tpage = x/64 | y/256 << 4 | tp << 7; clut = x/16 | y << 6; u = (x mod 64) * (4, 2, 1); v = y mod 256; w = image w * (4, 2, 1).")
def _(ctx):
    cases, recs = direct_run(ctx)
    for rec, (name, w) in zip(recs[len(cases["parse"]):], TEX_CASES):
        bpp, cx, cy, cw, ch, ix, iy, iw, ih = w
        mult = {4: 4, 8: 2, 16: 1}[bpp]
        exp = [T.tsb(ix, iy, bpp), T.cba(cx, cy) if cw else 0, (ix % 64) * mult, iy % 256, iw * mult, ih]
        expect_eq(rec["tex"], exp, f"Tex for: {name} [tpage, clut, u, v, w, h]", fmt="dec")
