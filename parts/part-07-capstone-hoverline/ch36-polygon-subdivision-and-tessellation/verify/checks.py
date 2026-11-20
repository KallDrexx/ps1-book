"""Chapter 36 checks: Polygon Subdivision and Tessellation (levels by depth, recursive quad splitting, exact UV midpoints, crack prevention, budget, debug outlines).
Build: CMake + PSn00bSDK; the CMake rule runs tools/assets/mkassets.py. The emulator BOOTS THE .cue.
THE MODEL (class Ref): Chapter 34's exact GTE pipeline (camera-relative s32 d = v - eye, RTPS, the far / near / back / big rules) plus this chapter's rules, derived here from the
generated files only: the section level from the four road-edge vertices' depth, the budget rule, the recursive split (edge midpoints (a + b) >> 1 in 3D and in UV, centre = mid of the
top and bottom midpoints, children in Z order, five new vertices projected per split), the leaf rules, the backing quad behind every subdivided face, the packets (POLY_FT4 / F4 / outlines).
MAIN RUN (probe.lua): driven by frame_no. Start leaves the title; TRIANGLE is pressed, pressed again and held (the debug toggle is edge-triggered); then harness-chosen poses (cam_eye, cam_yaw,
wire_mode, subdiv_debug, subdiv_reserve written at the end of a frame) are recorded one frame later: view_mtx, track_stats, subdiv_stats, the packets of the ordering table, the CPU cycles
of track_draw, a screenshot. Checks:
  - every pose's counters and packets equal the model's (levels, leaves, backing quads, budget cuts, positions, UVs, tpage / CLUT words, outlines in the colour of their depth);
  - the UV words alone (a multiset) equal the model's exact midpoints, so a rounding error or dropped UVs is named as such;
  - the gap detector: with debug off, every pixel along every seam between two drawn faces (and its neighbours across the seam) is not the background colour;
  - the budget rule with a patched reserve; no prims_dropped in the normal poses; the guard bytes; the toggle.
ALT RUN: a second disc, as in Chapter 35 (track 2 translated far from the origin, texture ids permuted, two untextured sections, hostile TIM positions)."""

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
Z1, Z2, RESERVE = 4000, 2000, 8192          # SUBDIV_Z1, SUBDIV_Z2, SUBDIV_RESERVE (subdiv.h, given)
LEVEL_COL = [(255, 255, 0), (0, 255, 255), (255, 0, 255)]      # the outline of a quad produced at depth 0, 1, 2
COL = dict(floor=(70, 72, 80), wall=(40, 60, 120), boost=(0, 200, 255), start=(240, 240, 240), wire=(255, 255, 0), other=(255, 0, 255))
FB = [(0, 0, 320, 240, "framebuffer 0"), (0, 240, 320, 240, "framebuffer 1")]
MAX_FRAMES = 1500
SHIFT = (60000, 0, 45000)
UNTEX_SECTIONS = (2, 3)       # alt disc: the faces of these sections have tex = 0xFF

config(
    title="Polygon Subdivision and Tessellation: recursive quad splitting, exact UVs, no cracks",
    build="cmake", exe="game.exe", sym="", elf="game.elf", iso="hoverline.cue",
    break_at=None, max_frames=MAX_FRAMES, timeout=300, vram=False,
)

STATE = ["main", "game_state", "load_status", "track", "track_status", "wire_mode", "track_stats", "view_mtx", "cam_eye", "cam_yaw", "prims_submitted", "prims_dropped",
         "frame_no", "frame_done", "ot_frames", "track_parse", "track_draw", "DrawOTag", "vram_layout", "track_tex", "tex_status", "track_tex_count", "track_tex_load",
         "track_face_uv", "subdiv_stats", "subdiv_debug", "subdiv_reserve", "subdiv_face", "subdiv_level", "subdiv_section_level", "subdiv_budget_level", "subdiv_mid"]


# ---- the book's assets, the alternate disc ---------------------------------------------------------------------------------------------------
_TMP = Path(tempfile.mkdtemp(prefix="ch36ref-"))
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


# ---- the plan (given in this chapter; read from the program, as in Chapter 35) ----------------------------------------------------------------
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


# ---- the model: Chapter 34's rules + subdivision ------------------------------------------------------------------------------------------------
def sgn(v):
    return (v > 0) - (v < 0)


class Ref:
    """One track_draw call. README 5.4 to 5.8 of this chapter on top of Chapter 34's pipeline. """

    def __init__(self, trk, eye, m, wire, dbg, reserve, cap, texf, opts=()):
        self.trk, self.eye, self.m, self.wire, self.dbg, self.reserve, self.texf, self.opts = trk, eye, m, wire, dbg, reserve, texf, opts
        nv = len(trk["vertices"])
        self.state = [0] * nv
        self.sxy, self.sz = [None] * nv, [None] * nv
        self.stats = dict(seen=0, far=0, near=0, back=0, big=0, dropped=0, drawn=0, wire=0)
        self.sd = dict(l0=0, l1=0, l2=0, d0=0, d1=0, d2=0, near=0, back=0, big=0, dropped=0, cuts=0, outlines=0, backings=0)
        self.packets = []                 # (slot, words, face index, kind, depth) in the order they were linked
        self.leaves = []                  # drawn leaves: (face index, depth, uv tuple of 8) in the order of the recursion
        self.face_info = {}               # face index -> dict(level, leaves_drawn, expected)
        self.sec_level = []
        self.rel = {}
        self.prims_dropped = 0
        self.recovered = 0                # faces with a vertex nearer than NEAR_Z of which some leaf was drawn anyway
        self.used, self.cap, self.gone = 0, cap, False
        for s in trk["sections"]:
            lvl = self.section_level(s)
            self.sec_level.append(lvl)
            for j in range(s["face_count"]):
                fi = s["first_face"] + j
                self.face(fi, trk["faces"][fi], lvl)

    # -- Chapter 34
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
        self.rel[i] = d

    # -- the criterion (README 5.4)
    def section_level(self, s):
        z = None
        for i in s["edges"]:
            self.prepare(i)
            if self.state[i] == 1 and self.sz[i] >= NEAR_Z and (z is None or self.sz[i] < z):
                z = self.sz[i]
        return 0 if z is None else (2 if z < Z2 else 1 if z < Z1 else 0)

    def outlined(self):
        return bool(self.wire or self.dbg)

    def leaf_bytes(self, textured):
        return (40 if textured else 24) + (32 if self.outlined() else 0)

    def emit(self, fi, f, tx, sxy, uvs, otz, depth):
        """Link one quad; False when the buffer is full."""
        size = self.leaf_bytes(bool(tx)) if depth >= 0 else (40 if tx else 24)
        if self.gone or size > self.cap - self.used:
            self.gone = True
            self.prims_dropped += 1
            return False
        self.used += size
        slot = min(max(otz >> OTZ_SHIFT, 0), 63)
        w = [pack_xy(*q) for q in sxy]
        if depth >= 0 and self.outlined():
            col = LEVEL_COL[depth] if self.dbg else COL["wire"]
            lw = [(0x48 << 24) | gpu_word(col), w[0], w[1], w[3], w[2], w[0], 0x55555555]
            self.packets.append((slot, tuple(lw), fi, "L5", depth))
            self.stats["wire"] += 1
            self.sd["outlines"] += bool(self.dbg)
        if tx:
            uv, tpage, clut = tx
            words = (0x2C000000 | 0x808080, w[0], uvs[0] | (uvs[1] << 8) | (clut << 16), w[1], uvs[2] | (uvs[3] << 8) | (tpage << 16),
                     w[2], uvs[4] | (uvs[5] << 8), w[3], uvs[6] | (uvs[7] << 8))
            self.packets.append((slot, words, fi, "FT4", depth))
        else:
            self.packets.append((slot, tuple([(0x28 << 24) | gpu_word(flag_colour(f["flags"]))] + w), fi, "F4", depth))
        return True

    def face(self, fi, f, level):
        st, sd = self.stats, self.sd
        st["seen"] += 1
        vs = f["v"]
        for i in vs:
            self.prepare(i)
        if any(self.state[i] == 2 for i in vs):
            st["far"] += 1
            return
        sd["l%d" % level] += 1
        tx = self.texf(f)
        info = self.face_info[fi] = dict(level=level, eff=0, drawn=0)
        if level > 0:
            near = any(self.sz[i] < NEAR_Z for i in vs)
            if not near:
                p = [self.sxy[i] for i in vs]
                if nclip(p[0], p[1], p[2]) <= 0:
                    st["back"] += 1
                    return
            l2 = level
            while l2 > 0 and self.cap - self.used < self.reserve + (self.leaf_bytes(bool(tx)) << (2 * l2)) + self.leaf_bytes(bool(tx)):
                l2 -= 1
            if l2 != level:
                sd["cuts"] += 1
            level = l2
            info["eff"] = level
            if level > 0:
                self.split_face(fi, f, tx, level)
                return
        # level 0: Chapter 35
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
        otz = (0x100 * sum(self.sz[i] for i in vs)) >> 12
        uvs = tx[0] if tx else [0] * 8
        if not self.emit(fi, f, tx, p, uvs, otz, 0):
            st["dropped"] += 1
            return
        sd["d0"] += 1
        st["drawn"] += 1
        info["drawn"] += 1
        self.leaves.append((fi, 0, tuple(uvs)))

    # -- README 5.5 / 5.6
    def split_face(self, fi, f, tx, level):
        verts = []
        for k, i in enumerate(f["v"]):
            verts.append(dict(p=list(self.rel[i]), u=tx[0][2 * k] if tx else 0, v=tx[0][2 * k + 1] if tx else 0, sxy=self.sxy[i], sz=self.sz[i]))
        F = dict(fi=fi, f=f, tx=tx, level=level, maxotz=0, drawn=0, dropped=0, near=0, big=0, back=0)
        self.recurse(F, verts, 0)
        # the backing quad: the whole face once, behind its leaves (README 5.8), when the face as a whole could be drawn
        p = [v["sxy"] for v in verts]
        xs, ys = [a[0] for a in p], [a[1] for a in p]
        back_ok = all(v["sz"] >= NEAR_Z for v in verts) and max(xs) - min(xs) <= MAX_W and max(ys) - min(ys) <= MAX_H
        if F["drawn"] and back_ok and "nobacking" not in self.opts:
            uvs = tx[0] if tx else [0] * 8
            if self.emit(fi, f, tx, p, uvs, F["maxotz"], -1):
                self.sd["backings"] += 1
                self.leaves.append((fi, -1, tuple(uvs)))
            else:
                self.sd["dropped"] += 1
        st = self.stats
        if F["drawn"]:
            st["drawn"] += 1
        elif F["dropped"]:
            st["dropped"] += 1
        elif F["near"]:
            st["near"] += 1
        elif F["big"]:
            st["big"] += 1
        else:
            st["back"] += 1
        self.face_info[fi]["drawn"] = F["drawn"]
        self.recovered += bool(F["drawn"] and any(self.sz[i] < NEAR_Z for i in f["v"]))

    def mid(self, a, b):
        return dict(p=[(a["p"][k] + b["p"][k]) >> 1 for k in range(3)], u=(a["u"] + b["u"]) >> 1, v=(a["v"] + b["v"]) >> 1)

    def project(self, v):
        sx, sy, sz = rtps(self.m, v["p"])
        v["sxy"], v["sz"] = (sx, sy), sz

    def children(self, q):
        m01, m02, m13, m23 = self.mid(q[0], q[1]), self.mid(q[0], q[2]), self.mid(q[1], q[3]), self.mid(q[2], q[3])
        c = self.mid(m01, m23)
        for v in (m01, m02, m13, m23, c):
            self.project(v)
        return [[q[0], m01, m02, c], [m01, q[1], c, m13], [m02, c, q[2], m23], [c, m13, m23, q[3]]], c

    def recurse(self, F, q, depth):
        if depth == F["level"]:
            self.leaf(F, q, depth)
            return
        kids, c = self.children(q)
        for k in kids:
            self.recurse(F, k, depth + 1)

    def leaf(self, F, q, depth):
        sd = self.sd
        if any(v["sz"] < NEAR_Z for v in q):
            F["near"] += 1
            sd["near"] += 1
            return
        p = [v["sxy"] for v in q]
        if nclip(p[0], p[1], p[2]) <= 0:
            F["back"] += 1
            sd["back"] += 1
            return
        xs, ys = [a[0] for a in p], [a[1] for a in p]
        if max(xs) - min(xs) > MAX_W or max(ys) - min(ys) > MAX_H:
            F["big"] += 1
            sd["big"] += 1
            return
        out = list(p)
        uvs = []
        for v in q:
            uvs += [v["u"], v["v"]]
        otz = (0x100 * sum(v["sz"] for v in q)) >> 12
        if not self.emit(F["fi"], F["f"], F["tx"], out, uvs, otz, depth):
            F["dropped"] += 1
            sd["dropped"] += 1
            return
        sd["d%d" % depth] += 1
        F["drawn"] += 1
        F["maxotz"] = max(F["maxotz"], otz)
        self.leaves.append((F["fi"], depth, tuple(uvs)))

    # -- reports
    def stat_list(self):
        s = self.stats
        return [s["seen"], s["far"], s["near"], s["back"], s["big"], s["dropped"], s["drawn"], s["wire"]]

    def sd_list(self):
        s = self.sd
        return [s["l0"], s["l1"], s["l2"], s["d0"], s["d1"], s["d2"], s["near"], s["back"], s["big"], s["dropped"], s["cuts"], s["outlines"], s["backings"]]

    def seams(self):
        """[(a, b, face1, face2, level1, level2)] for every edge shared by two faces that were BOTH drawn completely (all 4^level leaves)."""
        edges = {}
        for fi, info in self.face_info.items():
            f = self.trk["faces"][fi]
            full = 4 ** info["eff"] if info["eff"] else 1
            if info["drawn"] != full or self.state[f["v"][0]] != 1:
                continue
            v = f["v"]
            for a, b in ((v[0], v[1]), (v[1], v[3]), (v[3], v[2]), (v[2], v[0])):
                edges.setdefault((min(a, b), max(a, b)), []).append(fi)
        out = []
        for (a, b), fs in edges.items():
            if len(fs) == 2:
                out.append((a, b, fs[0], fs[1], self.face_info[fs[0]]["eff"], self.face_info[fs[1]]["eff"]))
        return out


# ---- poses -------------------------------------------------------------------------------------------------------------------------------------
def yaw_of(fx, fz):
    return round(math.atan2(fx, fz) * 4096 / (2 * math.pi)) % 4096


def sec_pose(trk, i, back=2400, height=900, wire=0, lab=None, dyaw=0, dbg=0, reserve=RESERVE):
    s = trk["sections"][i]
    f, u = s["forward"], s["up"]
    eye = tuple(round(s["centre"][k] - f[k] * back / 4096 + u[k] * height / 4096) for k in range(3))
    return dict(label=lab or f"section {i}, {back} units behind, {height} up", x=eye[0], y=eye[1], z=eye[2], yaw=(yaw_of(f[0], f[2]) + dyaw) % 4096, wire=wire, dbg=dbg, reserve=reserve)


def wall_pose(trk, i, side, dist=900, lab=None):
    """Stand `dist` units from the middle of the wall of section i, level with it, on the other side of the road, and look straight at it (side -1: left wall, +1: right wall)."""
    s = trk["sections"][i]
    face = trk["faces"][s["first_face"] + (0 if side < 0 else 4)]
    c = [sum(trk["vertices"][v][k] for v in face["v"]) / 4 for k in range(3)]
    r = s["right"]
    n = math.hypot(r[0], r[2])
    hx, hz = side * r[0] / n, side * r[2] / n
    eye = (round(c[0] - hx * dist), round(c[1]), round(c[2] - hz * dist))
    return dict(label=lab or f"the {'left' if side < 0 else 'right'} wall of section {i}", x=eye[0], y=eye[1], z=eye[2], yaw=yaw_of(hx, hz), wire=0, dbg=0, reserve=RESERVE)


def make_poses(trk, man, alt):
    nsec = len(trk["sections"])
    boosts = man["boost_sections"]
    st = trk["start_section"]
    out = [sec_pose(trk, st, 2400, 860, lab="the start line from behind"),
           sec_pose(trk, st, 1300, 450, lab="the start line, close"),
           sec_pose(trk, st, 700, 250, lab="the start line, very close"),
           sec_pose(trk, boosts[0], 2500, 900, lab=f"boost pad of section {boosts[0]}"),
           sec_pose(trk, boosts[-1], 1500, 500, lab=f"boost pad of section {boosts[-1]}"),
           sec_pose(trk, nsec // 2, 2000, 800, lab="the far side of the lap"),
           sec_pose(trk, (nsec * 3) // 4, 3000, 1000, lab="three quarters round"),
           sec_pose(trk, 20, 400, 150, lab="low and close"),
           sec_pose(trk, 40, 300, 120, lab="on the road, looking along it"),
           sec_pose(trk, 70, 1500, 600, lab="looking away from the track", dyaw=2048),
           sec_pose(trk, st, 2400, 860, wire=1, lab="the start line, wireframe on"),
           sec_pose(trk, st, 1300, 450, dbg=1, lab="the start line, close, debug outlines"),
           sec_pose(trk, 30, 1800, 700, dbg=1, wire=1, lab="debug and wireframe together"),
           sec_pose(trk, 50, 1200, 400, dbg=1, lab="debug outlines, section 50"),
           sec_pose(trk, st, 700, 250, reserve=40000, lab="the start line, very close, nothing split (reserve 40000: the cost baseline)"),
           sec_pose(trk, 40, 300, 120, reserve=40000, lab="on the road, nothing split (reserve 40000: the cost baseline)"),
           sec_pose(trk, st, 1300, 450, reserve=24000, lab="the start line, close, reserve 24000 (budget cuts)"),
           sec_pose(trk, st, 1300, 450, reserve=29000, lab="the start line, close, reserve 29000 (budget cuts everything)")]
    for i, side in ((3, -1), (7, 1), (11, -1), (4, 1)):
        out.append(wall_pose(trk, i, side, dist=700))
    if alt:
        for i in UNTEX_SECTIONS:
            out.append(sec_pose(trk, i, 900, 400, lab=f"section {i}: untextured faces (tex = 0xFF)"))
        out.append(wall_pose(trk, 5, -1))
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
    d = {"poses": [{k: p[k] for k in ("x", "y", "z", "yaw", "wire", "dbg", "reserve")} for p in poses], "frame_sz": 64 * 4 + cap + 16, "layout_bytes": layout_bytes}
    return "PARAMS = " + lua_val(d) + "\n"


MAIN_POSES = make_poses(TRK1, MAN1, False)
ALT_POSES = make_poses(TRK2, MAN2, True)
os.environ["CH36_PARAMS"] = str(_TMP / "params_main.lua")


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
        r = ctx.run("alt", iso="alt.cue", probe=gen)
    r.require_finished()
    exc = r.record("exception")
    if exc:
        raise CheckFailure(expected="no CPU exception", actual=f"CPU exception {exc['code']} at pc 0x{exc['epc']:08X}, address 0x{exc['badvaddr']:08X}",
                           hint="A wild pointer, a misaligned halfword/word access, an array overrun in the recursion (a face has at most 25 vertices), or a GTE load of an unaligned SVECTOR.")
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
    expect_true((ctx.symbols.size("subdiv_stats") or 0) == 52, "subdiv_stats is 13 words (52 bytes)", f"{ctx.symbols.size('subdiv_stats')} bytes", "SubdivStats in subdiv.h is given: keep its 13 fields.")


@static_check("the disc holds TRACK.TPK and TRACK.TRK in \\DATA (and Chapter 33's files), as the generators wrote them",
              hint="iso.xml lists the files; the CMake rule runs tools/assets/mkassets.py.")
def _(ctx):
    iso = Iso(ctx.build.build_dir / "hoverline.bin")
    for n in ("LOGO.TIM", "PROPS.TPK", "PYLON.SHP", "ARCH.SHP", "TOWER.SHP", "SCENE.BIN", "TRACK.TRK", "TRACK.TPK"):
        expect_true("\\DATA\\" + n in iso.files, f"\\DATA\\{n} is on the disc", ", ".join(sorted(iso.files)), "Add the <file> entry to iso.xml.")
        expect_eq(iso.read("\\DATA\\" + n), FILES[n], f"\\DATA\\{n} is the generated file", hint="The disc must carry the generator's bytes.")


@static_check("the primitive buffer holds textured quads: psxe's PRIM_BUF_SIZE >= 560 * 40 bytes", hint="POLY_FT4 is 40 bytes: PRIM_BUF_SIZE in psxe/include/psxe/ot.h is 32768 in this chapter.")
def _(ctx):
    n = prim_buf_size(ctx.project)
    expect_true(n >= 560 * 40, "PRIM_BUF_SIZE", f"{n}", "Raise it.")


# ---- runtime: the shared observation ---------------------------------------------------------------------------------------------------------
def check_boot(ctx, name):
    r, info, layout = observe(ctx, name)
    trk, man, poses, tims = model_of(name)
    expect_eq(info["load_status"], 0, f"{name}: load_status", fmt="dec", hint=f"track_status {info['track_status']}.")
    expect_eq((info["tex_status"], info["tex_count"]), (0, NTILE), f"{name}: (tex_status, track_tex_count): the given Chapter 35 loader still works", fmt="dec")
    return r, info, layout


_CACHE = {}


def pose_records(ctx, name):
    key = (name, str(ctx.work))
    if key not in _CACHE:
        _CACHE[key] = _pose_records(ctx, name)
    return _CACHE[key]


def _pose_records(ctx, name):
    r, info, layout = check_boot(ctx, name)
    trk, man, poses, tims = model_of(name)
    sc = as_list(r.record("scenarios"))
    expect_eq(len(sc), len(poses), f"{name}: every pose was recorded", fmt="dec", hint=f"status {r.data.get('status')}")
    cap = prim_buf_size(ctx.project)
    texf = make_texf(layout, NTILE)
    out = []
    for s, p in zip(sc, poses):
        eye = (p["x"], p["y"], p["z"])
        expect_eq(tuple(s["eye"]), eye, f"{name}: [{p['label']}] cam_eye as posed", fmt="dec")
        expect_eq((s["game_state"], s["wire_mode"], s["dbg"], s["reserve"]), (1, p["wire"], p["dbg"], p["reserve"]), f"{name}: [{p['label']}] (game_state, wire_mode, subdiv_debug, subdiv_reserve)", fmt="dec")
        ref = Ref(trk, eye, view_from_words(as_list(s["view"])), p["wire"], p["dbg"], p["reserve"], cap, texf)
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


def level_of(face_info_level):
    return face_info_level


# ---- the toggle ----------------------------------------------------------------------------------------------------------------------------------
@check("the debug toggle: TRIANGLE flips subdiv_debug once per press (a held button toggles once)",
       hint="game_update: `if (input_pressed(INPUT_TRIANGLE)) subdiv_debug ^= 1;` in the game state, next to Select's wire_mode (input_held would flip it every frame).")
def _(ctx):
    r, info, layout = observe(ctx, "main")
    t = as_list(r.record("toggles"))
    expect_eq(list(t), [1, 0, 1], "subdiv_debug after press 1, press 2, and a button held for 10 frames", fmt="dec")


# ---- the levels ---------------------------------------------------------------------------------------------------------------------------------
def check_levels(ctx, name):
    r, recs, layout = pose_records(ctx, name)
    total = dict(l0=0, l1=0, l2=0, d1=0, d2=0)
    recovered = 0
    for s, p, ref in recs:
        recovered += ref.recovered
        lab = f"{name}: [{p['label']}]"
        expect_eq(as_list(s["sd"]), ref.sd_list(), f"{lab}: subdiv_stats (faces by level 0/1/2, quads drawn by depth 0/1/2, leaves near/back/big/dropped, budget cuts, outlines, backing quads)", fmt="dec",
                  hint="README 5.4: the level of a section comes from the smallest depth `sz` among its four road-edge vertices (edges[0..3]) that are VS_OK and not nearer than TRK_NEAR_Z: "
                       f"2 below {Z2}, 1 below {Z1}, else 0; every face of the section gets it. Then the budget rule (5.7), then the leaf rules (5.6).")
        expect_eq(as_list(s["stats"]), ref.stat_list(), f"{lab}: track_stats (seen, far, near, back, big, dropped, drawn, wire)", fmt="dec",
                  hint="A subdivided face is counted once: drawn if any leaf was linked, else dropped, near, big, back (the first that applies).")
        expect_eq(s["dropped"], ref.prims_dropped, f"{lab}: prims_dropped", fmt="dec")
        for k in total:
            total[k] += ref.sd[k]
    expect_true(total["l2"] >= 10 and total["l1"] >= 20 and total["l0"] >= 400, f"{name}: the poses exercise all three levels (faces level 0 / 1 / 2: {total['l0']} / {total['l1']} / {total['l2']})", str(total))
    expect_true(recovered >= 3, f"{name}: the poses include faces with a vertex nearer than {NEAR_Z} whose children are drawn anyway (Chapter 35 dropped such a face whole): {recovered}", str(recovered))
    return recs


@check("main disc: faces are split by distance: near sections at level 2, middle ones at level 1, far ones not at all (counts equal the model's, pose by pose)",
       hint="See the failing pose: compare subdiv_stats with README 5.4 (the criterion), 5.6 (leaf rules) and 5.7 (budget).")
def _(ctx):
    check_levels(ctx, "main")


@check("alt disc (track 2 translated far from the origin): the same levels",
       hint="The criterion must use the camera-relative depth of the vertices (the GTE's sz), never absolute coordinates.")
def _(ctx):
    check_levels(ctx, "alt")


# ---- the packets --------------------------------------------------------------------------------------------------------------------------------
def check_packets(ctx, name):
    r, recs, layout = pose_records(ctx, name)
    ft4 = f4 = sub = 0
    for s, p, ref in recs:
        lab = f"{name}: [{p['label']}]"
        got = decode_pk(s["pk"])
        for sl, w in got:
            code = w[0] >> 24
            expect_true(code in (0x28, 0x2C, 0x48), f"{lab}: only POLY_F4 (0x28), POLY_FT4 (0x2C) and polylines (0x48)", f"slot {sl}: command 0x{code:02X}")
        want = [mask_packet(sl, w) for sl, w, fi, k, dp in ref.packets]
        have = [mask_packet(sl, w) for sl, w in got]
        if sorted(have) != sorted(want):
            gs, ws = set(have), set(want)
            missing = [x for x in want if x not in gs]
            extra = [x for x in have if x not in ws]
            ex = (missing or extra)[0]
            kind = "missing" if missing else "unexpected"
            fi = dp = None
            if missing:
                fi, dp = next(((fi, dp) for sl, w, fi, k, dp in ref.packets if mask_packet(sl, w) == ex), (None, None))
            face = ref.trk["faces"][fi] if fi is not None else None
            more = f" (face {fi}, depth {dp}, level {ref.face_info[fi]['level']}: flags 0x{face['flags']:02X}, tex {face['tex']}, uv {face['uv']})" if face else ""
            raise CheckFailure(expected=f"{lab}: {len(want)} packets; e.g. slot {ex[0]}: {[hex(x) for x in ex[1]]}{more}",
                               actual=f"{len(have)} packets; {kind} {len(missing) if missing else len(extra)} (first: slot {ex[0]}, words {[hex(x) for x in ex[1]]})",
                               hint="A leaf: corners in Z order (children keep the parent's order: [q0 m01 m02 c], [m01 q1 c m13], [m02 c q2 m23], [c m13 m23 q3]), positions = the RTPT of the integer "
                                    "midpoints, the backing quad: the whole face once, in the slot of its farthest leaf, linked after them (README 5.8), UVs = exact integer midpoints, tpage / CLUT words of the face's tile.")
        # the backing quad must be DRAWN before (under) its face's leaves of the same slot: the table is walked in drawing order, so its
        # position in the slot must come first (the multiset comparison above cannot see the order; a backing quad on top hides no crack and the leaves)
        owner = {}
        for sl, w, fi, k, dp in ref.packets:
            if k != "L5":
                owner.setdefault(mask_packet(sl, w), []).append((fi, dp))
        seen_leaf = set()
        for sl, w in got:
            key = mask_packet(sl, w)
            if not owner.get(key):
                continue
            fi, dp = owner[key].pop(0)
            if dp >= 0:
                seen_leaf.add((sl, fi))
            elif (sl, fi) in seen_leaf:
                raise CheckFailure(expected=f"{lab}: the backing quad of face {fi} drawn before (under) its leaves in slot {sl}",
                                   actual="it is drawn after a leaf of its face in the same slot: it covers the leaves",
                                   hint="README 5.8: link the backing quad AFTER the leaves (addPrim / ot_add puts the newest packet of a slot first in the drawing order).")
        for sl, w, fi, k, dp in ref.packets:
            ft4 += k == "FT4"
            f4 += k == "F4"
            sub += k != "L5" and dp > 0
    expect_true(ft4 > 300, f"{name}: enough textured packets were compared", str(ft4))
    expect_true(sub > 100, f"{name}: subdivided quads (depth 1 or 2) were among them", str(sub))
    if name == "alt":
        expect_true(f4 > 0, "alt: faces with tex = 0xFF were drawn flat (POLY_F4), subdivided like the rest", str(f4))


@check("main disc: for every pose the ordering table holds exactly the modelled packets (leaf quads at their depth, backing quads, positions, UVs, words, outlines)",
       hint="See the failing pose. The level check (stats) passed first, so the rule is right and the numbers are not: midpoints, projection, dilation, UVs.")
def _(ctx):
    check_packets(ctx, "main")


@check("alt disc: the same packets (track translated, texture ids permuted, two untextured sections)",
       hint="Flat faces are subdivided too: leaves are POLY_F4 in the flag colour, nothing to interpolate.")
def _(ctx):
    check_packets(ctx, "alt")


# ---- exact UVs ---------------------------------------------------------------------------------------------------------------------------------
def uvwords(w):
    return tuple(w[k] & 0xFFFF for k in (2, 4, 6, 8))[:4] if len(w) == 9 else None


def check_uvs(ctx, name):
    r, recs, layout = pose_records(ctx, name)
    nchk = 0
    for s, p, ref in recs:
        lab = f"{name}: [{p['label']}]"
        have = sorted(tuple((w[k] & 255, (w[k] >> 8) & 255) for k in (2, 4, 6, 8)) for sl, w in decode_pk(s["pk"]) if len(w) == 9)
        want = sorted(tuple((uv[2 * k], uv[2 * k + 1]) for k in range(4)) for fi, dp, uv in ref.leaves if ref.texf(ref.trk["faces"][fi]))
        if have != want:
            hs, ws = {}, {}
            for x in have:
                hs[x] = hs.get(x, 0) + 1
            for x in want:
                ws[x] = ws.get(x, 0) + 1
            miss = [x for x in want if hs.get(x, 0) < ws[x]]
            fi_dp = next(((fi, dp) for fi, dp, uv in ref.leaves if tuple((uv[2 * k], uv[2 * k + 1]) for k in range(4)) == miss[0]), (None, None)) if miss else (None, None)
            fa = ref.trk["faces"][fi_dp[0]] if fi_dp[0] is not None else None
            raise CheckFailure(expected=f"{lab}: every quad's four (u, v) are exact midpoints of its parent's; e.g. a quad of face {fi_dp[0]} at depth {fi_dp[1]} with texels {miss[0] if miss else '?'}"
                                        + (f" (the face's own UVs after FLIP_H and the tile origin: {[ (fa['uv'][k]) for k in range(4)]})" if fa else ""),
                               actual=f"{len(have)} textured quads in the table, {len(want)} expected; {len(miss)} expected UV sets missing",
                               hint="(a + b) >> 1 on the ABSOLUTE texels (after FLIP_H, with the tile origin): exact, so no rounding up, no dropped UVs (a quad with the parent's UVs is a texture squeezed "
                                    "into every quarter), the centre is the midpoint of the top and bottom midpoints.")
        nchk += len(want)
    expect_true(nchk > 300, f"{name}: enough subdivided and plain quads' UVs compared", str(nchk))


@check("main disc: the UVs of every quad are exact: each child's corners are the parent's corner / edge-midpoint / centre texels, (a + b) >> 1, children in Z order",
       hint="Subdivide the texture coordinates exactly like the positions, from the face's FINAL UVs (mirrored for FLIP_H, tile origin added). Compare with the model's expected texels in the failure.")
def _(ctx):
    check_uvs(ctx, "main")


@check("alt disc: the same exact UVs",
       hint="Same rule; the permuted ids change only the tile, not the arithmetic.")
def _(ctx):
    check_uvs(ctx, "alt")


# ---- the gap detector ----------------------------------------------------------------------------------------------------------------------------
def near_bg(c, tol=6):
    return all(abs(a - b) <= tol for a, b in zip(c, BG))


def seam_points(sxy_a, sxy_b, skip=3):
    (x0, y0), (x1, y1) = sxy_a, sxy_b
    n = max(abs(x1 - x0), abs(y1 - y0))
    pts = []
    for i in range(skip, n - skip + 1):
        t = i / n
        pts.append((round(x0 + (x1 - x0) * t), round(y0 + (y1 - y0) * t), abs(x1 - x0) >= abs(y1 - y0)))
    return pts


def face_extent(ref, fi):
    """the smaller side of the bounding box of the face's four projected corners (parent quad, before any split)"""
    pts = [ref.sxy[i] for i in ref.trk["faces"][fi]["v"]]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(max(xs) - min(xs), max(ys) - min(ys))


def sweep_seams(ref, img):
    """(samples, mixed samples, background hits): every seam of two completely drawn faces that are both at least 6 pixels across (thinner faces, seen
    almost edge-on near the horizon, can miss a whole pixel row by themselves, which is not a crack): every pixel along it and one pixel to each side."""
    n = nm = 0
    bad = []
    for a, b, f1, f2, l1, l2 in ref.seams():
        mixed = l1 != l2
        if min(face_extent(ref, f1), face_extent(ref, f2)) < 6:
            continue
        offs = (-1, 0, 1)
        for x, y, horiz in seam_points(ref.sxy[a], ref.sxy[b]):
            for off in offs:
                px, py = (x, y + off) if horiz else (x + off, y)
                if not (0 <= px < W and 0 <= py < H):
                    continue
                n += 1
                nm += mixed
                if near_bg(img.pixel(px, py)):
                    bad.append((px, py, f1, f2, l1, l2))
    return n, nm, bad


def tile_colours_clear_of_bg():
    near = 0
    for b in MAIN_TIMS:
        w, h, px = T.decode_rgba(T.parse(b))
        near += sum(1 for q in px if near_bg(q[:3]))
    return near


@check("the gap detector: with debug off, every pixel along every seam between two drawn faces, and its neighbours across the seam, is not the background colour (no cracks), including seams between levels",
       hint="A T-junction: the finer face's edge midpoints are not on the coarser neighbour's straight edge after rounding, so pixels between them are covered by neither. "
            "README 5.8: draw the whole face once behind its quads (the backing quad): it tiles exactly with the neighbour, so a slit shows the face's own texture, never the background.")
def _(ctx):
    expect_eq(tile_colours_clear_of_bg(), 0, "no tile pixel looks like the background colour (the detector cannot be fooled by a texel)", fmt="dec")
    for name in ("main", "alt"):
        r, recs, layout = pose_records(ctx, name)
        total = mixed = 0
        for s, p, ref in recs:
            if p["dbg"] or p["wire"]:
                continue
            img = r.screenshot("s%d" % s["k"])
            n, nm, bad = sweep_seams(ref, img)
            total += n
            mixed += nm
            if bad:
                px, py, f1, f2, l1, l2 = bad[0]
                raise CheckFailure(expected=f"{name}: [{p['label']}] no background-coloured pixel along any seam",
                                   actual=f"{len(bad)} background pixels along seams; first at ({px}, {py}) on the edge between face {f1} (drawn at level {l1}) and face {f2} (level {l2})",
                                   hint="A crack. Seams inside one section can't crack (same level, shared vertices); the cracks are between sections of different levels (a T-junction).")
        expect_true(total > 2000, f"{name}: enough seam pixels were sampled ({total})", str(total))
        expect_true(mixed > 200, f"{name}: seams between faces of DIFFERENT levels were sampled ({mixed} pixels)", str(mixed), hint="The poses must put a level change on the screen.")


# ---- the budget -----------------------------------------------------------------------------------------------------------------------------------
@check("the primitive budget: no quad is dropped in the normal poses; with a patched subdiv_reserve the budget rule cuts the level (counted in budget_cuts) and still nothing overflows",
       hint="README 5.7: while level > 0 and ot_bytes_left() < subdiv_reserve + (4^level + 1) * leaf_bytes: level--.")
def _(ctx):
    for name in ("main", "alt"):
        r, recs, layout = pose_records(ctx, name)
        cuts = 0
        for s, p, ref in recs:
            lab = f"{name}: [{p['label']}]"
            expect_eq(s["dropped"], 0, f"{lab}: prims_dropped (the budget rule keeps every pose inside the buffer, with outlines too)", fmt="dec")
            if p["reserve"] == RESERVE:
                if not (p["wire"] or p["dbg"]):
                    expect_eq(ref.sd["cuts"], 0, f"{lab}: budget_cuts in a normal pose (no outlines)", fmt="dec", hint="The criterion alone keeps the track inside the buffer.")
            else:
                cuts += s["sd"][10]
                expect_true(s["sd"][10] > 0, f"{lab}: the patched reserve cut at least one face's level", str(s["sd"][10]))
            expect_true(s["prims"] * 24 <= prim_buf_size(ctx.project) * 3, f"{lab}: prims_submitted is plausible", str(s["prims"]))
        if name == "main":
            expect_true(cuts > 0, "main: budget cuts happened in the reserve poses", str(cuts))


# ---- the debug outlines ---------------------------------------------------------------------------------------------------------------------------
@check("debug outlines: with subdiv_debug every quad drawn has an outline in the colour of its depth (yellow 0, cyan 1, magenta 2); counts per colour equal the model's; the picture shows them",
       hint="track_emit picks the colour by `depth` when subdiv_debug is on (COL_LEVEL0..2); depth 0 is the wireframe yellow.")
def _(ctx):
    r, recs, layout = pose_records(ctx, "main")
    seen = [0, 0, 0]
    for s, p, ref in recs:
        if not p["dbg"]:
            continue
        lab = f"[{p['label']}]"
        cols = {gpu_word(c): i for i, c in enumerate(LEVEL_COL)}
        count = [0, 0, 0]
        for sl, w in decode_pk(s["pk"]):
            if w[0] >> 24 == 0x48:
                col = w[0] & 0xFFFFFF
                expect_true(col in cols, f"{lab}: an outline has one of the three level colours", f"0x{col:06X}")
                count[cols[col]] += 1
        want = [sum(1 for pk in ref.packets if pk[3] == "L5" and pk[4] == d) for d in range(3)]
        expect_eq(count, want, f"{lab}: outlines per depth (0, 1, 2)", fmt="dec")
        expect_eq(as_list(s["sd"])[11], sum(want), f"{lab}: subdiv_stats.outlines", fmt="dec")
        img = r.screenshot("s%d" % s["k"])
        for d, col in enumerate(LEVEL_COL):
            if want[d] >= 4:
                hits = sum(1 for y in range(0, H, 1) for x in range(0, W, 1) if all(abs(a - b) <= 16 for a, b in zip(img.pixel(x, y), col)))
                expect_true(hits >= 20, f"{lab}: the picture contains the depth-{d} outline colour {col}", str(hits))
                seen[d] += 1
    expect_true(all(seen), "all three depth colours were seen in pictures", str(seen))


# ---- cost -----------------------------------------------------------------------------------------------------------------------------------------
@check("cost: track_draw (CPU cycles from its entry to DrawOTag) stays under 1.6 million in every pose, and subdividing the near faces costs less than twice the same pose with nothing split",
       hint="Project the five new vertices of a split with RTPTs, not 25 RTPS; do not recompute a face's vertices per leaf; cull a leaf before building its packet; keep the recursion free of divisions.")
def _(ctx):
    worst, where = 0, ""
    pairs = {}
    for name in ("main", "alt"):
        r, recs, layout = pose_records(ctx, name)
        for s, p, ref in recs:
            if s["cycles"] > worst:
                worst, where = s["cycles"], f"{name}: [{p['label']}]"
            if name == "main":
                pairs[p["label"]] = s["cycles"]
    expect_true(worst <= 1600000, f"worst track_draw: {worst} cycles ({worst / 564480:.2f} NTSC frames) at {where}", str(worst))
    for near, base in (("the start line, very close", "the start line, very close, nothing split (reserve 40000: the cost baseline)"),
                       ("on the road, looking along it", "on the road, nothing split (reserve 40000: the cost baseline)")):
        c, b = pairs[near], pairs[base]
        expect_true(c < 2 * b, f"[{near}] with subdivision {c} cycles vs {b} without: +{c - b} cycles (x{c / b:.2f})", f"{c} vs {b}")


@check("the primitive buffers: guard bytes intact after every pose", hint="Never write past ot_alloc's block; budget for the outline (32 bytes) too.")
def _(ctx):
    for name in ("main", "alt"):
        r, info, layout = observe(ctx, name)
        for g in as_list(r.record("guards")):
            expect_eq(list(as_list(g)), [0xA5] * 16, f"{name}: guard bytes behind a primitive buffer", fmt="hex")
