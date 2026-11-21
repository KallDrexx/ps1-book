"""Chapter 35 checks: Track Texturing (manual VRAM layout, per-face UVs, flipped tiles).
Build: CMake + PSn00bSDK; the CMake rule runs tools/assets/mkassets.py. The emulator BOOTS THE .cue.
THE READER'S PLAN is read from the running program: the symbol `vram_layout` (one 12-byte TileSlot per texture id of TRACK.TPK) and `track_tex` (what the loader derived).
RULES on the plan (derived here from the shipped TIMs, never typed in): every tile and CLUT inside VRAM, tiles inside one texture page, the tpage / CLUT words consistent with the
rectangles, no overlap between tiles, CLUTs, the two framebuffers and what the program loads anyway (LOGO.TIM, PROPS.TPK).
MAIN RUN (probe.lua): driven by frame_no. Start leaves the title; then harness-chosen camera poses (cam_eye / cam_yaw written at the end of a frame) are recorded one frame later:
view_mtx, track_stats, the packets of the ordering table DrawOTag was given, a screenshot. At the end the whole VRAM is dumped.
  - the tiles sit in VRAM exactly where vram_layout says (rectangle compared byte for byte with the TPK's TIM data), CLUTs too, LOGO and PROPS survive;
  - every packet of every pose equals the Python model (the exact GTE projection of Chapter 34, then POLY_FT4: UVs from the face + the tile origin, mirrored for FLIP_H,
    tpage and CLUT words from the plan; untextured faces: POLY_F4 in the legend colour);
  - the picture shows the texels: sampled pixels of top-most faces are looked up in the TIM through the polygon's affine map, flipped and unflipped hypotheses compared.
ALT RUN: a second disc: TRACK.TRK = track 2 translated by (+60000, 0, +45000) with all texture indices permuted and two sections untextured (0xFF), and TRACK.TPK = the same
eight tiles in REVERSED order whose own TIM headers name hostile places (on the framebuffers): hard-coded ids, a loader that trusts the TIM's own position, a missing fallback all fail there."""
import atexit
import dataclasses
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from harness import *
from image import fmt_rgb

ROOT_DIR = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT_DIR / "tools" / "assets"))
import mkassets      # noqa: E402
import formats       # noqa: E402
import tim as T      # noqa: E402

W, H, CX, CY = 320, 240, 160, 120
BG = (24, 24, 48)
PROJ_H = 320
FAR = 32767
NEAR_Z = 128
MAX_W, MAX_H = 1023, 511
OTZ_SHIFT = 7
COL = dict(floor=(70, 72, 80), wall=(40, 60, 120), boost=(0, 200, 255), start=(240, 240, 240), wire=(255, 255, 0), other=(255, 0, 255))
FB = [(0, 0, 320, 240, "framebuffer 0"), (0, 240, 320, 240, "framebuffer 1")]
MAX_FRAMES = 1300
SHIFT = (60000, 0, 45000)
UNTEX_SECTIONS = (2, 3)       # alt disc: the faces of these sections have tex = 0xFF

config(
    title="Track Texturing: a manual VRAM layout, UVs and flipped tiles",
    build="cmake", exe="game.exe", sym="", elf="game.elf", iso="hoverline.cue",
    break_at=None, max_frames=MAX_FRAMES, timeout=240, vram=True,
)

STATE = ["main", "game_state", "load_status", "track", "track_status", "wire_mode", "track_stats", "view_mtx", "cam_eye", "cam_yaw", "prims_submitted", "prims_dropped",
         "frame_no", "frame_done", "ot_frames", "track_parse", "track_draw", "DrawOTag", "vram_layout", "track_tex", "tex_status", "track_tex_count", "track_tex_load",
         "track_face_uv"]


# ---- the book's assets, the alternate disc ---------------------------------------------------------------------------------------------------
_TMP = Path(tempfile.mkdtemp(prefix="ch35ref-"))
atexit.register(shutil.rmtree, _TMP, True)
FILES, MANIFESTS = mkassets.build(_TMP / "assets", seed=1)
TRK1 = formats.parse_trk(FILES["TRACK.TRK"])
MAN1 = MANIFESTS["TRACK.TRK"]
TPK1 = formats.parse_tpk(FILES["TRACK.TPK"])
NTILE = TPK1["count"]
NAMES = ["asphalt", "asphalt_worn", "lane_stripe", "boost", "start_line", "wall_a", "wall_b", "glow"]      # tools/assets/layout.py order = TRACK.TPK ids
PERM = [NTILE - 1 - i for i in range(NTILE)]            # alt disc: old id -> new id


def make_alt():
    """(TRACK.TRK bytes, TRACK.TPK bytes, tims by id) of the alternate disc."""
    t = formats.parse_trk(FILES["TRACK2.TRK"])
    verts = [(x + SHIFT[0], y + SHIFT[1], z + SHIFT[2]) for x, y, z in t["vertices"]]
    secs = []
    for s in t["sections"]:
        s = dict(s)
        s["centre"] = tuple(c + d for c, d in zip(s["centre"], SHIFT))
        secs.append(s)
    faces = []
    for f in t["faces"]:
        f = dict(f, color=(0, 0, 0))
        if f["tex"] != 0xFF:
            f["tex"] = PERM[f["tex"]]
        faces.append(f)
    for si in UNTEX_SECTIONS:
        s = secs[si]
        for j in range(s["first_face"], s["first_face"] + s["face_count"]):
            faces[j]["tex"] = 0xFF
    vis = [s["vis"] for s in t["sections"]]
    total = sum(s["length"] for s in secs)
    trk = formats.build_trk("TRACK2S", verts, faces, secs, vis, t["start_section"], total, t["texture_count"])
    tims = [None] * NTILE
    for old, b in enumerate(TPK1["tims"]):
        tm = T.parse(b)
        new = PERM[old]
        tm.image = dataclasses.replace(tm.image, x=16 * new, y=16 * new)          # on top of framebuffer 0
        tm.clut = dataclasses.replace(tm.clut, x=16 * new, y=300 + new)           # on top of framebuffer 1
        tims[new] = T.build(tm)
    return trk, formats.build_tpk(tims), tims


ALT_TRK_BIN, ALT_TPK_BIN, ALT_TIMS = make_alt()
TRK2 = formats.parse_trk(ALT_TRK_BIN)
MAN2 = MANIFESTS["TRACK2.TRK"]
MAIN_TIMS = TPK1["tims"]


def prim_buf_size(project):
    text = (Path(project) / "psxe" / "include" / "psxe" / "ot.h").read_text()
    m = re.search(r"#define\s+PRIM_BUF_SIZE\s+(\d+)", text)
    return int(m.group(1)) if m else 2048


def s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


def s16(v):
    return v - 65536 if v & 0x8000 else v


# ---- the GTE (Chapter 34's exact model) ---------------------------------------------------------------------------------------------------------
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


def rtps(m, v):
    mac = [sum(m[i][k] * v[k] for k in range(3)) >> 12 for i in range(3)]
    ir = [sat(x, -32768, 32767) for x in mac]
    sz = sat(mac[2], 0, 65535)
    n = gte_divide(PROJ_H, sz) if sz else 0x1FFFF
    sx = sat((n * ir[0] + (CX << 16)) >> 16, -0x400, 0x3FF)
    sy = sat((n * ir[1] + (CY << 16)) >> 16, -0x400, 0x3FF)
    return sx, sy, sz


def nclip(a, b, c):
    return a[0] * b[1] + b[0] * c[1] + c[0] * a[1] - a[0] * c[1] - b[0] * a[1] - c[0] * b[1]


def pack_xy(x, y):
    return (x & 0xFFFF) | ((y & 0xFFFF) << 16)


def unpack_xy(w):
    return (s16(w & 0xFFFF), s16(w >> 16))


def flag_colour(flags):
    if flags & 8:
        return COL["start"]
    if flags & 4:
        return COL["boost"]
    if flags & 2:
        return COL["wall"]
    if flags & 1:
        return COL["floor"]
    return COL["other"]


def gpu_word(rgb):
    return rgb[0] | (rgb[1] << 8) | (rgb[2] << 16)


def view_from_words(w):
    h = []
    for x in w[:5]:
        h += [s16(x & 0xFFFF), s16(x >> 16)]
    return [h[0:3], h[3:6], h[6:9]]


# ---- the plan the reader declared ---------------------------------------------------------------------------------------------------------------
class Slot:
    def __init__(self, i, x, y, w, h, tpage, clut):
        self.id, self.x, self.y, self.w, self.h, self.tpage, self.clut = i, x, y, w, h, tpage, clut
        self.cx, self.cy = (clut & 63) * 16, clut >> 6
        self.u0, self.v0 = (x % 64) * 4, y % 256

    def __repr__(self):
        return f"id {self.id}: ({self.x},{self.y}) {self.w}x{self.h} tpage 0x{self.tpage:04X} clut 0x{self.clut:04X} = ({self.cx},{self.cy})"


def parse_layout(hexstr):
    b = bytes.fromhex(hexstr)
    return [Slot(i, *struct.unpack_from("<6H", b, 12 * i)) for i in range(len(b) // 12)]


def others():
    """What the program loads besides the track tiles: LOGO.TIM and PROPS.TPK, at the places their own TIMs name."""
    out = []
    lg = T.parse(FILES["LOGO.TIM"])
    out.append((lg.image.x, lg.image.y, lg.image.w, lg.image.h, "LOGO.TIM image"))
    out.append((lg.clut.x, lg.clut.y, lg.clut.w, lg.clut.h, "LOGO.TIM CLUT"))
    for i, b in enumerate(formats.parse_tpk(FILES["PROPS.TPK"])["tims"]):
        t = T.parse(b)
        out.append((t.image.x, t.image.y, t.image.w, t.image.h, f"PROPS.TPK texture {i} image"))
        out.append((t.clut.x, t.clut.y, t.clut.w, t.clut.h, f"PROPS.TPK texture {i} CLUT"))
    return out


def overlap(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def getTPage4(x, y):
    return ((x & 0x3C0) >> 6) | ((y & 0x100) >> 4) | ((y & 0x200) << 2)


def layout_rects(layout):
    out = []
    for s in layout:
        out.append((s.x, s.y, s.w, s.h, f"tile {s.id} image"))
        out.append((s.cx, s.cy, 16, 1, f"tile {s.id} CLUT"))
    return out


def plan_problem(layout):
    """None when the declared plan obeys every rule, else a (what, hint) pair."""
    tims = [T.parse(b) for b in MAIN_TIMS]
    if len(layout) < NTILE:
        return (f"vram_layout has {len(layout)} entries, TRACK.TPK has {NTILE} tiles", "LAYOUT_TILE_COUNT must be at least the number of tiles in the pack.")
    for s, t in zip(layout, tims):
        if (s.w, s.h) != (t.image.w, t.image.h):
            return (f"{s!r}: the slot is {s.w}x{s.h} but tile {s.id} is {t.image.w} units x {t.image.h} lines (4 bpp: 64 texels = 16 units)",
                    "w is in 16-bit units, not texels: a 64-texel 4-bpp tile is 16 units wide.")
        if not (0 <= s.x and s.x + s.w <= 1024 and 0 <= s.y and s.y + s.h <= 512):
            return (f"{s!r}: the tile leaves VRAM (1024 x 512)", "VRAM is 1024 units wide and 512 lines tall.")
        if s.x % 64 + s.w > 64 or s.y % 256 + s.h > 256:
            return (f"{s!r}: the tile runs past the end of its texture page (a page is 64 units x 256 lines at 4 bpp, starting on a multiple of 64 / 256)",
                    "A tile must lie inside ONE page: x % 64 + w <= 64 and y % 256 + h <= 256, or its UVs would need to be above 255.")
        if s.tpage != getTPage4(s.x, s.y):
            return (f"{s!r}: the tpage word is not that of a 4-bpp tile at ({s.x},{s.y}) with abr = 0",
                    "README 5.4 has the formula; TPAGE_4BPP in vram_layout.h builds the word from the tile's own x and y.")
        if not (s.cx + 16 <= 1024 and s.cy < 512):
            return (f"{s!r}: the CLUT leaves VRAM", "A 4-bpp CLUT is 16 x 1 units.")
    rects = layout_rects(layout[:NTILE])
    for r in rects:
        for f in FB:
            if overlap(r, f):
                return (f"{r[4]} ({r[0]},{r[1]} {r[2]}x{r[3]}) overlaps {f[4]} (the display / draw buffers at (0,0) and (0,240), each 320 x 240)",
                        "Everything the GPU draws lands there: textures in the framebuffers are overwritten every frame.")
        for o in others():
            if overlap(r, o):
                return (f"{r[4]} ({r[0]},{r[1]} {r[2]}x{r[3]}) overlaps {o[4]} ({o[0]},{o[1]} {o[2]}x{o[3]}), which the program loads anyway",
                        "main.c loads LOGO.TIM and PROPS.TPK at the places their TIMs name; keep out of those rectangles.")
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            if overlap(a, b):
                return (f"{a[4]} ({a[0]},{a[1]} {a[2]}x{a[3]}) overlaps {b[4]} ({b[0]},{b[1]} {b[2]}x{b[3]})", "Two things cannot share VRAM pixels.")
    return None


# ---- the rules of Chapter 34 + the textured packets --------------------------------------------------------------------------------------------
class Ref:
    """One track_draw call: README 5.6 of Chapter 34, with POLY_FT4 for textured faces."""

    def __init__(self, trk, eye, m, wire, cap, texf):
        self.trk, self.eye, self.m, self.wire, self.texf = trk, eye, m, wire, texf
        nv = len(trk["vertices"])
        self.state = [0] * nv
        self.sxy, self.sz = [None] * nv, [None] * nv
        self.stats = dict(seen=0, far=0, near=0, back=0, big=0, dropped=0, drawn=0, wire=0)
        self.packets = []                 # (slot, words, face index, kind) in the order they were linked
        self.used, self.cap, self.gone = 0, cap, False
        for s in trk["sections"]:
            for j in range(s["face_count"]):
                fi = s["first_face"] + j
                self.face(fi, trk["faces"][fi])

    def prepare(self, i):
        if self.state[i]:
            return
        v = self.trk["vertices"][i]
        d = [v[k] - self.eye[k] for k in range(3)]
        if max(abs(c) for c in d) > FAR:
            self.state[i] = 2
            return
        self.state[i] = 1
        sx, sy, sz = rtps(self.m, d)
        self.sxy[i], self.sz[i] = (sx, sy), sz

    def face(self, fi, f):
        st = self.stats
        st["seen"] += 1
        vs = f["v"]
        for i in vs:
            self.prepare(i)
        if any(self.state[i] == 2 for i in vs):
            st["far"] += 1
            return
        if any(self.sz[i] < NEAR_Z for i in vs):
            st["near"] += 1
            return
        p = [self.sxy[i] for i in vs]
        if nclip(p[0], p[1], p[2]) <= 0:
            st["back"] += 1
            return
        xs, ys = [q[0] for q in p], [q[1] for q in p]
        if max(xs) - min(xs) > MAX_W or max(ys) - min(ys) > MAX_H:
            st["big"] += 1
            return
        tx = self.texf(f)
        size = (40 if tx else 24) + (32 if self.wire else 0)
        if self.gone or size > self.cap - self.used:
            st["dropped"] += 1
            self.gone = True
            return
        self.used += size
        otz = (0x100 * sum(self.sz[i] for i in vs)) >> 12
        slot = min(max(otz >> OTZ_SHIFT, 0), 63)
        w = [pack_xy(*q) for q in p]
        if self.wire:
            lw = [(0x48 << 24) | gpu_word(COL["wire"]), w[0], w[1], w[3], w[2], w[0], 0x55555555]
            self.packets.append((slot, tuple(lw), fi, "L5"))
            st["wire"] += 1
        if tx:
            uv, tpage, clut = tx
            words = (0x2C000000 | 0x808080, w[0], uv[0] | (uv[1] << 8) | (clut << 16), w[1], uv[2] | (uv[3] << 8) | (tpage << 16),
                     w[2], uv[4] | (uv[5] << 8), w[3], uv[6] | (uv[7] << 8))
            self.packets.append((slot, words, fi, "FT4"))
        else:
            self.packets.append((slot, tuple([(0x28 << 24) | gpu_word(flag_colour(f["flags"]))] + w), fi, "F4"))
        st["drawn"] += 1

    def stat_list(self):
        s = self.stats
        return [s["seen"], s["far"], s["near"], s["back"], s["big"], s["dropped"], s["drawn"], s["wire"]]

    def draw_order(self):
        idx = sorted(range(len(self.packets)), key=lambda i: (-self.packets[i][0], -i))
        return [self.packets[i] for i in idx]


def make_texf(layout, count):
    """face -> (uv[8], tpage, clut) or None, from the DECLARED plan (E.10.3: FLIP_H mirrors U inside the face's own U range)."""
    def texf(f):
        if f["tex"] == 0xFF or f["tex"] >= count:
            return None
        s = layout[f["tex"]]
        us = [u for u, v in f["uv"]]
        lo, hi = min(us), max(us)
        out = []
        for u, v in f["uv"]:
            if f["flags"] & 16:
                u = lo + hi - u
            out += [s.u0 + u, s.v0 + v]
        return out, s.tpage, s.clut
    return texf


def mask_packet(slot, w):
    """POLY_FT4's third and fourth UV words have 16 padding bits: compare only the UVs."""
    if len(w) == 9:
        w = list(w)
        w[6] &= 0xFFFF
        w[8] &= 0xFFFF
        w = tuple(w)
    return (slot, w)


# ---- poses -------------------------------------------------------------------------------------------------------------------------------------
def yaw_of(fx, fz):
    return round(math.atan2(fx, fz) * 4096 / (2 * math.pi)) % 4096


def sec_pose(trk, i, back=2400, height=900, wire=0, lab=None, dyaw=0):
    s = trk["sections"][i]
    f, u = s["forward"], s["up"]
    eye = tuple(round(s["centre"][k] - f[k] * back / 4096 + u[k] * height / 4096) for k in range(3))
    return dict(label=lab or f"section {i}, {back} units behind, {height} up", x=eye[0], y=eye[1], z=eye[2], yaw=(yaw_of(f[0], f[2]) + dyaw) % 4096, wire=wire)


def wall_pose(trk, i, side, dist=900, lab=None):
    """Stand `dist` units from the middle of the wall of section i, level with it, on the other side of the road, and look straight at it (side -1: left wall, +1: right wall)."""
    s = trk["sections"][i]
    face = trk["faces"][s["first_face"] + (0 if side < 0 else 4)]
    c = [sum(trk["vertices"][v][k] for v in face["v"]) / 4 for k in range(3)]
    r = s["right"]
    n = math.hypot(r[0], r[2])
    hx, hz = side * r[0] / n, side * r[2] / n
    eye = (round(c[0] - hx * dist), round(c[1]), round(c[2] - hz * dist))
    return dict(label=lab or f"the {'left' if side < 0 else 'right'} wall of section {i}", x=eye[0], y=eye[1], z=eye[2], yaw=yaw_of(hx, hz), wire=0)


def make_poses(trk, man, alt):
    nsec = len(trk["sections"])
    boosts = man["boost_sections"]
    st = trk["start_section"]
    out = [sec_pose(trk, st, 2400, 860, lab="the start line from behind"),
           sec_pose(trk, st, 1300, 450, lab="the start line, close"),
           sec_pose(trk, boosts[0], 2500, 900, lab=f"boost pad of section {boosts[0]}"),
           sec_pose(trk, boosts[-1], 1500, 500, lab=f"boost pad of section {boosts[-1]}"),
           sec_pose(trk, nsec // 2, 2000, 800, lab="the far side of the lap"),
           sec_pose(trk, (nsec * 3) // 4, 3000, 1000, lab="three quarters round"),
           sec_pose(trk, 20, 400, 150, lab="low and close"),
           sec_pose(trk, 40, 300, 120, lab="on the road, looking along it"),
           sec_pose(trk, 70, 1500, 600, lab="looking away from the track", dyaw=2048),
           sec_pose(trk, st, 2400, 860, wire=1, lab="the start line, wireframe on")]
    # walls: odd sections are mirrored (FLIP_H); sections 3, 7, 11 .. carry the hazard stripes (tile 6), which are not symmetric
    for i, side in ((3, -1), (7, 1), (11, -1), (15, 1), (19, -1), (4, 1), (1, -1), (8, -1)):
        out.append(wall_pose(trk, i, side))
    if alt:
        for i in UNTEX_SECTIONS:
            out.append(sec_pose(trk, i, 900, 400, lab=f"section {i}: untextured faces (tex = 0xFF)"))
        out.append(wall_pose(trk, 5, -1))
        out.append(wall_pose(trk, 15, 1))
    return out


# ---- the disc image ----------------------------------------------------------------------------------------------------------------------------
class Iso:
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
            name = rec[33:33 + rec[32]]
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


def alt_disc(ctx):
    bdir = ctx.build.build_dir
    if (bdir / "alt.cue").exists():
        return
    xml = next(iter(sorted(bdir.glob("cd_image_*.xml"))), None)
    if xml is None:
        raise CheckFailure(expected="CMake's configured iso xml", actual="not found", hint="Use psn00bsdk_add_cd_image.")
    (bdir / "alt").mkdir(exist_ok=True)
    text = xml.read_text()
    for name, blob in (("TRACK.TRK", ALT_TRK_BIN), ("TRACK.TPK", ALT_TPK_BIN)):
        (bdir / "alt" / name).write_bytes(blob)
        text, k = re.subn(r'(<file\s+name="%s"[^>]*?source=")[^"]*(")' % re.escape(name), lambda m: m.group(1) + str(bdir / "alt" / name) + m.group(2), text, flags=re.I)
        expect_eq(k, 1, f"iso.xml has one <file name=\"{name}\" source=...> entry", hint="Both files live in <dir name=\"DATA\">.")
    (bdir / "alt.xml").write_text(text)
    p = subprocess.run(["mkpsxiso", "-y", "-q", "-o", "alt.bin", "-c", "alt.cue", "alt.xml"], cwd=bdir, capture_output=True, text=True, timeout=60, env=tool_env())
    expect_eq(p.returncode, 0, "mkpsxiso builds the alternative disc", hint=(p.stdout + p.stderr)[-400:])


def lua_val(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, dict):
        return "{" + ",".join(f"[{json.dumps(k)}]={lua_val(x)}" for k, x in v.items()) + "}"
    return "{" + ",".join(lua_val(x) for x in v) + "}"


def params_lua(poses, cap, layout_bytes):
    d = {"poses": [{k: p[k] for k in ("x", "y", "z", "yaw", "wire")} for p in poses], "frame_sz": 64 * 4 + cap + 16, "layout_bytes": layout_bytes}
    return "PARAMS = " + lua_val(d) + "\n"


MAIN_POSES = make_poses(TRK1, MAN1, False)
ALT_POSES = make_poses(TRK2, MAN2, True)
os.environ["CH35_PARAMS"] = str(_TMP / "params_main.lua")


# ---- observing the runs ------------------------------------------------------------------------------------------------------------------------
def layout_bytes(ctx):
    n = ctx.symbols.size("vram_layout")
    return min(max(n or 12 * NTILE, 12 * NTILE), 12 * 64)


def as_list(v):
    if isinstance(v, list):
        return v
    if not v:
        return []
    return [v[str(i)] for i in range(1, len(v) + 1)]


def observe(ctx, name):
    name = "main" if name.startswith("main") else "alt"
    if name == "main":
        r = ctx.result
    else:
        alt_disc(ctx)
        gen = ctx.work / "params_alt.lua"
        gen.write_text(params_lua(ALT_POSES, prim_buf_size(ctx.project), layout_bytes(ctx)) + "dofile(" + json.dumps(str(ctx.chapter_dir / "verify" / "probe.lua")) + ")\n")
        r = ctx.run("alt", iso="alt.cue", probe=gen, vram=True)
    r.require_finished()
    exc = r.record("exception")
    if exc:
        raise CheckFailure(expected="no CPU exception", actual=f"CPU exception {exc['code']} at pc 0x{exc['epc']:08X}, address 0x{exc['badvaddr']:08X}",
                           hint="A wild pointer, a misaligned halfword/word access, or a loop that overruns an array (the loader walks vram_layout and track_tex by texture id).")
    info = r.record("info")
    expect_true(info is not None, "the program reaches its frame loop", f"status {r.data.get('status')}", hint="Does it hang in cd_load_file or in an upload? Booting + loading takes about 400 emulated frames.")
    layout = parse_layout(info["layout"])
    return r, info, layout


def model_of(name):
    return (TRK1, MAN1, MAIN_POSES, MAIN_TIMS) if name == "main" else (TRK2, MAN2, ALT_POSES, ALT_TIMS)


# ---- static checks -----------------------------------------------------------------------------------------------------------------------------
@static_check("the state symbols and the given modules are linked", hint="main.c's asm block keeps the state alive; do not delete a declaration the verifier reads.")
def _(ctx):
    (_TMP / "params_main.lua").write_text(params_lua(MAIN_POSES, prim_buf_size(ctx.project), layout_bytes(ctx)))
    ctx.require_symbols(*STATE)
    expect_true((ctx.symbols.size("vram_layout") or 0) >= 12 * NTILE, "the vram_layout table has one 12-byte TileSlot per tile", f"{ctx.symbols.size('vram_layout')} bytes",
                "LAYOUT_TILE_COUNT must be at least 8 (TRACK.TPK's tiles); the table is `const TileSlot vram_layout[LAYOUT_TILE_COUNT]`.")


@static_check("the disc holds TRACK.TPK and TRACK.TRK in \\DATA (and Chapter 33's files), as the generators wrote them; the tiles are read at run time, not compiled in",
              hint="iso.xml lists the files; the CMake rule runs tools/assets/mkassets.py.")
def _(ctx):
    iso = Iso(ctx.build.build_dir / "hoverline.bin")
    for n in ("LOGO.TIM", "PROPS.TPK", "PYLON.SHP", "ARCH.SHP", "TOWER.SHP", "SCENE.BIN", "TRACK.TRK", "TRACK.TPK"):
        expect_true("\\DATA\\" + n in iso.files, f"\\DATA\\{n} is on the disc", ", ".join(sorted(iso.files)), "Add the <file> entry to iso.xml.")
        expect_eq(iso.read("\\DATA\\" + n), FILES[n], f"\\DATA\\{n} is the generated file", hint="The disc must carry the generator's bytes.")
    exe = (ctx.build.build_dir / "game.exe").read_bytes()
    px = T.parse(MAIN_TIMS[6]).image.data
    expect_true(px[:64] not in exe, "the tile pixels are not inside the program", "found in game.exe", "Load TRACK.TPK from the disc at run time.")


@static_check("the primitive buffer holds textured quads: psxe's PRIM_BUF_SIZE >= 560 * 40 bytes", hint="POLY_FT4 is 40 bytes (POLY_F4 was 24): edit PRIM_BUF_SIZE in psxe/include/psxe/ot.h.")
def _(ctx):
    n = prim_buf_size(ctx.project)
    expect_true(n >= 560 * 40, "PRIM_BUF_SIZE", f"{n}", "Raise it.")


def strip_comments(t):
    return re.sub(r"<!--.*?-->", "", t, flags=re.S)


@static_check("vram_layout.md exists and is a plan: the five sections, every tile named, each tile's x and y stated",
              hint="Fill in starter/vram_layout.md (the comments say what each section needs). Names: asphalt, asphalt_worn, lane_stripe, boost, start_line, wall_a, wall_b, glow.")
def _(ctx):
    p = Path(ctx.project) / "vram_layout.md"
    expect_true(p.exists(), "vram_layout.md exists in the project", "missing", "Keep the template and fill it in.")
    text = strip_comments(p.read_text())
    heads = [h.lower() for h in re.findall(r"^#{1,6}\s+(.*)$", text, flags=re.M)]
    for key, what in (("framebuffer", "a framebuffer map"), ("tile", "a tile table"), ("free", "free-space accounting"), ("rationale", "the rationale"), ("flip", "the flip-flag usage")):
        expect_true(any(key in h for h in heads), f"a heading about {what} (contains '{key}')", f"headings: {heads}", "Keep the template's headings.")
    low = text.lower()
    for n in NAMES:
        expect_true(n in low, f"the tile '{n}' is mentioned", "missing", "The tile table has one row per tile id.")
    body = re.sub(r"\s+", " ", text)
    expect_true(len(body) >= 1400, "the plan is more than a template (>= 1400 characters without comments)", f"{len(body)}", "Say what you chose and why: a few lines per section.")


# ---- runtime checks ----------------------------------------------------------------------------------------------------------------------------
def check_boot(ctx, name):
    r, info, layout = observe(ctx, name)
    trk, man, poses, tims = model_of(name)
    expect_eq(info["load_status"], 0, f"{name}: load_status", fmt="dec", hint=f"track_status {info['track_status']}.")
    t = [s32(x) for x in as_list(info["track"])]
    expect_eq(t[4:6] + t[6:8], [man["section_count"], man["vertex_count"], man["face_count"], man["vis_entries"]], f"{name}: the Track counts equal the manifest's", fmt="dec")
    expect_eq((info["tex_status"], info["tex_count"]), (0, NTILE), f"{name}: (tex_status, track_tex_count)", fmt="dec",
              hint="track_tex_load returns 0 and counts the tiles it uploaded (-1 read, -2 pack, -3 count, -4 TIM, -5 slot, -6 fit).")
    return r, info, layout


@check("vram_layout.md states the plan the program declares: every tile's x and y appear in the document",
       hint="The tile table needs one row per tile with its VRAM x and y (units, lines) and its CLUT's x and y: the same numbers as vram_layout.h.")
def _(ctx):
    r, info, layout = observe(ctx, "main")
    text = strip_comments((Path(ctx.project) / "vram_layout.md").read_text())
    nums = set(re.findall(r"\d+", text))
    for s_ in layout[:NTILE]:
        for what, v in (("x", s_.x), ("y", s_.y), ("CLUT x", s_.cx), ("CLUT y", s_.cy)):
            expect_true(str(v) in nums, f"vram_layout.md contains tile {s_.id}'s {what} = {v}", "missing", "Keep the document and the header in step.")


@check("the plan: vram_layout (read from RAM) obeys the rules: inside VRAM, one page per tile, consistent tpage and CLUT words, no overlap with the framebuffers, LOGO, PROPS, or itself",
       hint="README 5: the framebuffers are (0,0) and (0,240), 320 x 240 each; a 4-bpp 64 x 64 tile is 16 units x 64 lines; a page starts on x % 64 == 0, y % 256 == 0.")
def _(ctx):
    r, info, layout = observe(ctx, "main")
    pr = plan_problem(layout)
    if pr:
        raise CheckFailure(expected="a legal plan", actual=pr[0], hint=pr[1])


@check("the loader's table: track_tex[id] = (tpage, clut, u, v, w, h) derived from the declared slot (the tile's texel origin in its page, 64 x 64 texels)",
       hint="Copy the slot's words; the texel origin is the position INSIDE the page, in texels (README 5.4).")
def _(ctx):
    for name in ("main", "alt"):
        r, info, layout = check_boot(ctx, name)
        pr = plan_problem(layout)
        expect_true(pr is None, "the plan is legal (see the plan check)", pr[0] if pr else "")
        got = struct.unpack("<%dH" % (6 * NTILE), bytes.fromhex(info["tex"])[:12 * NTILE])
        for i, s in enumerate(layout[:NTILE]):
            want = (s.tpage, s.clut, s.u0, s.v0, 64, 64)
            expect_eq(tuple(got[6 * i:6 * i + 6]), want, f"{name}: track_tex[{i}] (tpage, clut, u, v, w, h)", fmt="hex",
                      hint=f"{s!r}: u, v, w and h are in texels, not VRAM units (README 5.4, the UV origin).")


def check_vram(ctx, name):
    r, info, layout = check_boot(ctx, name)
    pr = plan_problem(layout)
    expect_true(pr is None, "the plan is legal (see the plan check)", pr[0] if pr else "")
    vram = r.vram()
    trk, man, poses, tims = model_of(name)
    for i, b in enumerate(tims):
        t = T.parse(b)
        s = layout[i]
        vram.expect_rect(s.x, s.y, s.w, s.h, t.image.data, hint=f"{name}: tile {i} must be at {s!r}: the pixels of the TPK's tile {i}, copied to the declared place "
                                                               f"(tim_upload_at with the slot's x, y, not the TIM's own {t.image.x},{t.image.y}).")
        vram.expect_rect(s.cx, s.cy, 16, 1, t.clut.data, hint=f"{name}: the CLUT of tile {i} must be at ({s.cx},{s.cy}) (the slot's CLUT word), not at the TIM's own ({t.clut.x},{t.clut.y}).")
    lg = T.parse(FILES["LOGO.TIM"])
    vram.expect_rect(lg.image.x, lg.image.y, lg.image.w, lg.image.h, lg.image.data, hint="LOGO.TIM's pixels were overwritten: a tile or CLUT overlaps them, or something uploaded there.")
    vram.expect_rect(lg.clut.x, lg.clut.y, lg.clut.w, lg.clut.h, lg.clut.data, hint="LOGO.TIM's CLUT was overwritten.")
    for i, b in enumerate(formats.parse_tpk(FILES["PROPS.TPK"])["tims"]):
        t = T.parse(b)
        vram.expect_rect(t.image.x, t.image.y, t.image.w, t.image.h, t.image.data, hint=f"PROPS.TPK texture {i} was overwritten.")
        vram.expect_rect(t.clut.x, t.clut.y, t.clut.w, t.clut.h, t.clut.data, hint=f"PROPS.TPK CLUT {i} was overwritten.")


@check("main disc: VRAM holds every tile and CLUT byte for byte at the declared place; LOGO.TIM and PROPS.TPK survive",
       hint="Upload with tim_upload_at at the slot's x, y and the CLUT word's place; wait for the GPU (DrawSync) before the file image is freed.")
def _(ctx):
    check_vram(ctx, "main")


@check("alt disc (the tiles in reversed order, each TIM naming a place ON the framebuffers): the same, so the loader must relocate, not trust the TIM",
       hint="A loader that uploads at the TIM's own coordinates writes the tiles into the framebuffers and leaves the declared place empty.")
def _(ctx):
    check_vram(ctx, "alt")


# ---- the draw ----------------------------------------------------------------------------------------------------------------------------------
def pose_records(ctx, name):
    r, info, layout = check_boot(ctx, name)
    trk, man, poses, tims = model_of(name)
    pr = plan_problem(layout)
    expect_true(pr is None, "the plan is legal (see the plan check)", pr[0] if pr else "")
    sc = as_list(r.record("scenarios"))
    expect_eq(len(sc), len(poses), f"{name}: every pose was recorded", fmt="dec", hint=f"status {r.data.get('status')}")
    cap = prim_buf_size(ctx.project)
    texf = make_texf(layout, NTILE)
    out = []
    for s, p in zip(sc, poses):
        eye = (p["x"], p["y"], p["z"])
        expect_eq(tuple(s["eye"]), eye, f"{name}: [{p['label']}] cam_eye as posed", fmt="dec")
        expect_eq((s["game_state"], s["wire_mode"]), (1, p["wire"]), f"{name}: [{p['label']}] (game_state, wire_mode)", fmt="dec")
        ref = Ref(trk, eye, view_from_words(as_list(s["view"])), p["wire"], cap, texf)
        out.append((s, p, ref))
    return r, out, layout


def decode_pk(flat):
    flat = as_list(flat)
    out, i = [], 0
    while i < len(flat):
        slot, ln = flat[i], flat[i + 1]
        out.append((slot, tuple(flat[i + 2:i + 2 + ln])))
        i += 2 + ln
    return out


def check_packets(ctx, name):
    r, recs, layout = pose_records(ctx, name)
    ft4 = f4 = flipped = 0
    for s, p, ref in recs:
        lab = f"{name}: [{p['label']}]"
        expect_eq(as_list(s["stats"]), ref.stat_list(), f"{lab}: track_stats (seen, far, near, back, big, dropped, drawn, wire)", fmt="dec",
                  hint="The Chapter 34 rules, unchanged by texturing; dropped counts a face the buffer cannot hold (a textured quad needs 40 bytes, 72 with its outline).")
        got = decode_pk(s["pk"])
        for sl, w in got:
            code = w[0] >> 24
            expect_true(code in (0x28, 0x2C, 0x48), f"{lab}: only POLY_F4 (0x28), POLY_FT4 (0x2C) and polylines (0x48)", f"slot {sl}: command 0x{code:02X}",
                        "Textured and opaque: 0x2C (not 0x2D raw texture, not 0x2E semi-transparent).")
            if code == 0x2C:
                for k in (2, 4, 6, 8):
                    u, v = w[k] & 255, (w[k] >> 8) & 255
                    expect_true(0 <= u <= 255 and 0 <= v <= 255, f"{lab}: UV in the page", f"({u}, {v})")
                tp = w[4] >> 16
                ids = [s_.id for s_ in layout[:NTILE] if s_.tpage == tp and s_.clut == (w[2] >> 16)]
                expect_true(ids, f"{lab}: the (tpage 0x{tp:04X}, clut 0x{w[2] >> 16:04X}) pair belongs to one tile of the plan", "no tile has this pair",
                            hint="Which UV word carries the CLUT word and which the tpage word? README 5.7 has the packet.")
                for k in (2, 4, 6, 8):
                    u, v = w[k] & 255, (w[k] >> 8) & 255
                    inside = any(s_.u0 <= u <= s_.u0 + 63 and s_.v0 <= v <= s_.v0 + 63 for s_ in layout[:NTILE] if s_.id in ids)
                    expect_true(inside, f"{lab}: the UV ({u}, {v}) lies inside the tile {ids} (texel box u {layout[ids[0]].u0}..{layout[ids[0]].u0 + 63}, v {layout[ids[0]].v0}..{layout[ids[0]].v0 + 63})",
                                "outside", "UVs are absolute inside the PAGE: origin of the tile + the face's 0..63 values (README 5.6). Outside the tile means other pixels, or another tile.")
        want = [mask_packet(sl, w) for sl, w, fi, k in ref.packets]
        have = [mask_packet(sl, w) for sl, w in got]
        if sorted(have) != sorted(want):
            gs, ws = set(have), set(want)
            missing = [x for x in want if x not in gs]
            extra = [x for x in have if x not in ws]
            ex = (missing or extra)[0]
            kind = "missing" if missing else "unexpected"
            fi = next((fi for sl, w, fi, k in ref.packets if mask_packet(sl, w) == ex), None) if missing else None
            face = ref.trk["faces"][fi] if fi is not None else None
            more = f" (face {fi}: flags 0x{face['flags']:02X}, tex {face['tex']}, uv {face['uv']})" if face else ""
            raise CheckFailure(expected=f"{lab}: {len(want)} packets; e.g. slot {ex[0]}: {[hex(x) for x in ex[1]]}{more}",
                               actual=f"{len(have)} packets; {kind} {len(missing) if missing else len(extra)} (first: slot {ex[0]}, words {[hex(x) for x in ex[1]]})",
                               hint="Compare the words with README 5.7 (the POLY_FT4 packet: neutral color, corners v0..v3 as stored, where the two words go) and "
                                    "README 5.6 (the UV rule and the FLIP_H mirror). Faces with tex 0xFF stay POLY_F4 in the flag color, as in Chapter 34.")
        for sl, w, fi, k in ref.packets:
            ft4 += k == "FT4"
            f4 += k == "F4"
            flipped += k == "FT4" and bool(ref.trk["faces"][fi]["flags"] & 16)
    expect_true(ft4 > 200, f"{name}: enough textured packets were compared", str(ft4))
    expect_true(flipped > 20, f"{name}: flipped faces were among them (FLIP_H)", str(flipped))
    if name == "alt":
        expect_true(f4 > 0, "alt: faces with tex = 0xFF were drawn flat (POLY_F4)", str(f4))
    return r


@check("main disc: for every pose the ordering table holds exactly the modelled packets: POLY_FT4 with the face's UVs + tile origin (mirrored for FLIP_H), the plan's tpage and CLUT words",
       hint="See the hint of the failing pose: compare your u0 v0 .. u3 v3 with the face record and the tile's origin.")
def _(ctx):
    check_packets(ctx, "main")


@check("alt disc (track 2 translated, texture indices permuted, two untextured sections): the same packets",
       hint="The texture index is the face's own: no 'wall = tile 5'. tex = 0xFF -> POLY_F4 with the legend color of the FLAGS (the face's color field is zero here).")
def _(ctx):
    check_packets(ctx, "alt")


# ---- pictures ----------------------------------------------------------------------------------------------------------------------------------
def inside_margin(pt, poly, margin=1.5):
    """True/False strictly inside / outside a convex loop; None when within `margin` pixels of an edge."""
    sign = 0
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        c = (b[0] - a[0]) * (pt[1] - a[1]) - (b[1] - a[1]) * (pt[0] - a[0])
        ln = math.hypot(b[0] - a[0], b[1] - a[1]) or 1
        if abs(c) / ln < margin:
            return None
        if sign == 0:
            sign = 1 if c > 0 else -1
        elif (c > 0) != (sign > 0):
            return False
    return True


def bary(p, a, b, c):
    d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if d == 0:
        return None
    l1 = ((b[1] - c[1]) * (p[0] - c[0]) + (c[0] - b[0]) * (p[1] - c[1])) / d
    l2 = ((c[1] - a[1]) * (p[0] - c[0]) + (a[0] - c[0]) * (p[1] - c[1])) / d
    return l1, l2, 1 - l1 - l2


def close(a, b, tol):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


class Tile:
    def __init__(self, tim_bytes):
        w, h, px = T.decode_rgba(T.parse(tim_bytes))
        self.w, self.h, self.px = w, h, px

    def near(self, lu, lv, r=1):
        out = []
        cu, cv = int(round(lu)), int(round(lv))
        for dv in range(-r, r + 1):
            for du in range(-r, r + 1):
                x, y = cu + du, cv + dv
                if 0 <= x < self.w and 0 <= y < self.h:
                    out.append(self.px[y * self.w + x][:3])
        return out


WEIGHTS = [(1 / 3, 1 / 3, 1 / 3), (0.6, 0.2, 0.2), (0.2, 0.6, 0.2), (0.2, 0.2, 0.6), (0.45, 0.45, 0.10)]


def check_pictures(ctx, name):
    r, recs, layout = pose_records(ctx, name)
    trk, man, poses, tims = model_of(name)
    tiles = [Tile(b) for b in tims]
    ok = bad = 0
    first_bad = None
    stats = dict(flip_n=0, flip_ok=0, flip_disc=0, flip_disc_ok=0, flat_n=0, flat_ok=0, unflip_disc=0, unflip_disc_ok=0)
    for s, p, ref in recs:
        img = r.screenshot("s%d" % s["k"])
        order = ref.draw_order()
        polys = []
        for slot, w, fi, kind in order:
            if kind == "L5":
                continue
            f = ref.trk["faces"][fi]
            pts = [unpack_xy(x) for x in ([w[1], w[2], w[3], w[4]] if kind == "F4" else [w[1], w[3], w[5], w[7]])]
            polys.append((kind, pts, f, w, fi))
        loops = [[q[1][0], q[1][1], q[1][3], q[1][2]] for q in polys]
        for idx, (kind, pts, f, w, fi) in enumerate(polys):
            later = loops[idx + 1:]
            for tri in ((0, 1, 2), (1, 2, 3)):
                a, b, c = (pts[k] for k in tri)
                if abs(nclip(a, b, c)) < 120:
                    continue
                for wt in WEIGHTS:
                    px = (round(wt[0] * a[0] + wt[1] * b[0] + wt[2] * c[0]), round(wt[0] * a[1] + wt[1] * b[1] + wt[2] * c[1]))
                    if not (0 <= px[0] < W and 0 <= px[1] < H):
                        continue
                    if inside_margin(px, [a, b, c]) is not True:
                        continue
                    if any(inside_margin(px, lp, 2.0) is not False for lp in later):
                        continue
                    col = img.pixel(*px)
                    if kind == "F4":
                        stats["flat_n"] += 1
                        stats["flat_ok"] += close(col, flag_colour(f["flags"]), 24)
                        continue
                    t = tiles[f["tex"]]
                    sl = layout[f["tex"]]
                    uvw = [(w[2] & 255, (w[2] >> 8) & 255), (w[4] & 255, (w[4] >> 8) & 255), (w[6] & 255, (w[6] >> 8) & 255), (w[8] & 255, (w[8] >> 8) & 255)]
                    L = bary(px, a, b, c)
                    if L is None:
                        continue
                    lu = sum(L[k] * uvw[tri[k]][0] for k in range(3)) - sl.u0
                    lv = sum(L[k] * uvw[tri[k]][1] for k in range(3)) - sl.v0
                    cands = t.near(lu, lv)
                    # the other hypothesis: the same face with FLIP_H toggled (mirrored vs as stored)
                    us = [u for u, v in f["uv"]]
                    lo, hi = min(us), max(us)
                    mirrored = [(lo + hi - u, v) for u, v in f["uv"]]
                    other = list(f["uv"]) if f["flags"] & 16 else mirrored
                    uvo = [(sl.u0 + u, sl.v0 + v) for u, v in other]
                    lu2 = sum(L[k] * uvo[tri[k]][0] for k in range(3)) - sl.u0
                    lv2 = sum(L[k] * uvo[tri[k]][1] for k in range(3)) - sl.v0
                    cands2 = t.near(lu2, lv2)
                    good = any(close(col, c_, 26) for c_ in cands)
                    ok += good
                    bad += not good
                    if not good and first_bad is None:
                        first_bad = (f"{name}: [{p['label']}] face {fi} (tex {f['tex']}, flags 0x{f['flags']:02X}): the picture at {px} is {fmt_rgb(col)}, "
                                     f"the tile's texels there are about {fmt_rgb(cands[len(cands) // 2]) if cands else '?'}")
                    differs = bool(cands) and bool(cands2) and not any(close(c1, c2, 40) for c1 in cands for c2 in cands2)
                    if f["flags"] & 16:
                        stats["flip_n"] += 1
                        stats["flip_ok"] += good
                        if differs:
                            stats["flip_disc"] += 1
                            stats["flip_disc_ok"] += good and not any(close(col, c_, 26) for c_ in cands2)
                    elif differs:
                        stats["unflip_disc"] += 1
                        stats["unflip_disc_ok"] += good and not any(close(col, c_, 26) for c_ in cands2)
    expect_true(ok >= 150, f"{name}: enough textured sample points were looked up in the tiles", f"{ok} ok, {bad} off")
    expect_true(bad <= max(2, (ok + bad) // 12), f"{name}: sampled pixels show the texel their polygon's UVs select ({ok} ok, {bad} off)", first_bad,
                hint="The packets passed, so the VRAM content or the CLUT is wrong at draw time: tile uploaded to another place, the CLUT not uploaded, or the tpage word's page differs from the upload.")
    expect_true(stats["flip_disc"] >= 20, f"{name}: enough sample points where a flipped face differs from its unflipped version", str(stats["flip_disc"]))
    expect_true(stats["flip_disc_ok"] >= 0.85 * stats["flip_disc"], f"{name}: on flipped faces the picture is the MIRRORED tile ({stats['flip_disc_ok']} of {stats['flip_disc']} distinguishing points)",
                f"{stats['flip_disc_ok']} of {stats['flip_disc']}", "FLIP_H: u -> u_min + u_max - u for every corner; the hazard-stripe wall (tile 6) shows the difference.")
    expect_true(stats["unflip_disc"] >= 20, f"{name}: enough sample points where an unflipped face differs from its mirror image (the start line)", str(stats["unflip_disc"]))
    expect_true(stats["unflip_disc_ok"] >= 0.85 * stats["unflip_disc"], f"{name}: unflipped faces are NOT mirrored ({stats['unflip_disc_ok']} of {stats['unflip_disc']})",
                f"{stats['unflip_disc_ok']} of {stats['unflip_disc']}", "Only faces with the FLIP_H flag are mirrored.")
    if name == "alt":
        expect_true(stats["flat_n"] >= 10 and stats["flat_ok"] >= 0.9 * stats["flat_n"], "alt: untextured faces show the legend color of their flags",
                    f"{stats['flat_ok']} of {stats['flat_n']}", "tex = 0xFF -> flat quad, color from the flags.")


@check("main disc, pictures: the screenshot shows the tiles: sampled pixels equal the texels the packets select; flipped faces show the mirrored tile, unflipped ones do not",
       hint="If the packets check passes and this fails, VRAM or the CLUT is at fault at draw time (the tile is not where the tpage word points).")
def _(ctx):
    check_pictures(ctx, "main")


@check("alt disc, pictures: the same (and untextured faces in the legend color)",
       hint="Same causes; tiles of the alt disc are in another order, so a table by position fails here.")
def _(ctx):
    check_pictures(ctx, "alt")


@check("the primitive buffers: guard bytes intact after every pose", hint="Never write past ot_alloc's block; a textured quad is 40 bytes, with its outline 72.")
def _(ctx):
    for name in ("main", "alt"):
        r, info, layout = observe(ctx, name)
        for g in as_list(r.record("guards")):
            expect_eq(list(as_list(g)), [0xA5] * 16, f"{name}: guard bytes behind a primitive buffer", fmt="hex")


@check("the game still starts: Start leaves the title (game_state 1) and Select / fly camera are untouched", hint="game_update is given.")
def _(ctx):
    r, info, layout = observe(ctx, "main")
    expect_eq(info["game_state"], 0, "at boot: game_state (STATE_TITLE)", fmt="dec")
    sc = as_list(r.record("scenarios"))
    expect_true(sc and all(s["game_state"] == 1 for s in sc), "all poses are in STATE_GAME", str([s["game_state"] for s in sc][:4]))
