"""Chapter 34 checks: Track Geometry (TRACK.TRK at world scale).
Build: CMake + PSn00bSDK; the CMake rule runs tools/assets/mkassets.py. The emulator BOOTS THE .cue.
MAIN RUN (probe.lua): driven by frame_no. It reads the loaded Track through the `track` symbol, taps Start (title -> game), holds Select for 20 frames
(wire_mode toggles once), taps it again, flies with UP + RIGHT, then writes harness-chosen poses into cam_eye / cam_yaw and, one frame later, records for each:
view_mtx, track_stats, the per-vertex arrays (trk_vstate, trk_rel, trk_sxy, trk_sz), the packets of the ordering table DrawOTag was given, and a screenshot.
Everything the program must produce is derived here, in exact integers, from the generated .TRK (formats.parse_trk): the camera-relative vector of every vertex,
the GTE projection (bit-exact RTPS), the face rules in README 5.6 and the packets with their ordering-table slots.
ALT RUN: a second disc whose TRACK.TRK is track 2 (104 sections) translated by (+60000, 0, +45000) so that every ABSOLUTE x and z exceeds 16 bits, with
every face color field zeroed (the legend comes from the FLAGS) and the camera box widened: hard-coded counts, the absolute-vertex shortcut and the
color-field shortcut all fail there.
DIRECT CALLS (probe_direct.lua): track_parse on crafted files (documented codes, check order, limits, the input and *out left alone), the accessors, track_colour,
track_draw windows (wrap, count cut, empty, negative first) and the primitive budget over several calls."""
import atexit
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
import trkgen        # noqa: E402

W, H, CX, CY = 320, 240, 160, 120
BG = (24, 24, 48)
PROJ_H = 320
FAR = 32767
NEAR_Z = 128
MAX_W, MAX_H = 1023, 511
OTZ_SHIFT = 7
COL = dict(floor=(70, 72, 80), wall=(40, 60, 120), boost=(0, 200, 255), start=(240, 240, 240), wire=(255, 255, 0), other=(255, 0, 255))
MAX_FRAMES = 1300

config(
    title="Track Geometry: TRACK.TRK at world scale",
    build="cmake", exe="game.exe", sym="", elf="game.elf", iso="hoverline.cue",
    break_at=None, max_frames=MAX_FRAMES, timeout=240,
)

STATE = ["main", "game_state", "load_status", "track", "track_status", "wire_mode", "track_stats", "trk_rel", "trk_sxy", "trk_sz", "trk_vstate",
         "cam_eye", "cam_yaw", "cam_min", "cam_max", "view_mtx", "prims_submitted", "prims_dropped", "frame_no", "frame_done", "ot_frames", "ot_begin_frame",
         "render_begin", "track_parse", "track_vertex", "track_face", "track_section", "track_colour", "track_draw", "DrawOTag", "object_count"]

STATUS = {100: "cd_init() failed (CdInit)", 1: "tpk_load failed", 2: "the scene failed (Chapter 33's code is given)", 3: "LOGO.TIM could not be loaded",
          4: "TRACK.TRK failed: track_status has the code (-1 read, -2 align, -3 magic, -4 header, -5 vertex, -6 face, -7 section, -8 vis)"}


# ---- the book's assets, the alternate track, the primitive buffer size ---------------------------------------------------------------------
_TMP = Path(tempfile.mkdtemp(prefix="ch34ref-"))
atexit.register(shutil.rmtree, _TMP, True)
FILES, MANIFESTS = mkassets.build(_TMP / "assets", seed=1)
TRK1 = formats.parse_trk(FILES["TRACK.TRK"])
MAN1 = MANIFESTS["TRACK.TRK"]
SHIFT = (60000, 0, 45000)


def make_alt_track():
    """Track 2, translated, face color fields zeroed."""
    t = formats.parse_trk(FILES["TRACK2.TRK"])
    verts = [(x + SHIFT[0], y + SHIFT[1], z + SHIFT[2]) for x, y, z in t["vertices"]]
    secs = []
    for s in t["sections"]:
        s = dict(s)
        s["centre"] = tuple(c + d for c, d in zip(s["centre"], SHIFT))
        secs.append(s)
    faces = [dict(f, color=(0, 0, 0)) for f in t["faces"]]
    vis = [s["vis"] for s in t["sections"]]
    total = sum(s["length"] for s in secs)
    return formats.build_trk("TRACK2S", verts, faces, secs, vis, t["start_section"], total, t["texture_count"])


ALT_BIN = make_alt_track()
TRK2 = formats.parse_trk(ALT_BIN)
MAN2 = MANIFESTS["TRACK2.TRK"]
TRK2_ORIG = formats.parse_trk(FILES["TRACK2.TRK"])


def prim_buf_size(project):
    """PRIM_BUF_SIZE of the project's psxe copy (the reader may size it differently)."""
    text = (Path(project) / "psxe" / "include" / "psxe" / "ot.h").read_text()
    m = re.search(r"#define\s+PRIM_BUF_SIZE\s+(\d+)", text)
    return int(m.group(1)) if m else 2048


def s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


def s16(v):
    return v - 65536 if v & 0x8000 else v


# ---- the GTE and the rules, in Python's exact integers --------------------------------------------------------------------------------------
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
    """RT = m (3x3, 4.12), TR = 0, one vertex (s16 triple), H = PROJ_H, offsets (CX, CY)."""
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
    """MATRIX (32 bytes, 8 words) -> (3x3 list, t)."""
    h = []
    for x in w[:5]:
        h += [s16(x & 0xFFFF), s16(x >> 16)]
    m = [h[0:3], h[3:6], h[6:9]]
    return m, [s32(x) for x in w[5:8]]


class Ref:
    """THE rules of README 5.6 for one track_draw call."""

    def __init__(self, trk, eye, m, first, count, wire, used=0, cap=2048):
        self.trk, self.eye, self.m, self.wire = trk, eye, m, wire
        nv = len(trk["vertices"])
        self.state = [0] * nv                       # 0 unseen, 1 ok, 2 far
        self.rel, self.sxy, self.sz = [None] * nv, [None] * nv, [None] * nv
        self.stats = dict(seen=0, far=0, near=0, back=0, big=0, dropped=0, drawn=0, wire=0)
        self.packets = []                           # (slot, words, face index, kind) in the order they were linked
        self.faces = {}                             # face index -> bucket name
        n = len(trk["sections"])
        gone = False
        self.used = used
        if n <= 0 or count <= 0:
            return
        count = min(count, n)
        first %= n
        for k in range(count):
            s = trk["sections"][(first + k) % n]
            for j in range(s["face_count"]):
                fi = s["first_face"] + j
                gone = self.face(fi, trk["faces"][fi], cap, gone)

    def prepare(self, i):
        if self.state[i]:
            return
        v = self.trk["vertices"][i]
        d = [v[k] - self.eye[k] for k in range(3)]
        if max(abs(c) for c in d) > FAR:
            self.state[i] = 2
            return
        self.state[i] = 1
        self.rel[i] = tuple(d)
        self.sxy[i] = None
        sx, sy, sz = rtps(self.m, d)
        self.sxy[i], self.sz[i] = (sx, sy), sz

    def face(self, fi, f, cap, gone):
        st = self.stats
        st["seen"] += 1
        vs = f["v"]
        for i in vs:
            self.prepare(i)
        if any(self.state[i] == 2 for i in vs):
            st["far"] += 1
            self.faces[fi] = "far"
            return gone
        if any(self.sz[i] < NEAR_Z for i in vs):
            st["near"] += 1
            self.faces[fi] = "near"
            return gone
        p = [self.sxy[i] for i in vs]
        if nclip(p[0], p[1], p[2]) <= 0:
            st["back"] += 1
            self.faces[fi] = "back"
            return gone
        xs, ys = [q[0] for q in p], [q[1] for q in p]
        if max(xs) - min(xs) > MAX_W or max(ys) - min(ys) > MAX_H:
            st["big"] += 1
            self.faces[fi] = "big"
            return gone
        size = 24 + (32 if self.wire else 0)
        if gone or size > cap - self.used:
            st["dropped"] += 1
            self.faces[fi] = "dropped"
            return True
        self.used += size
        otz = (0x100 * sum(self.sz[i] for i in vs)) >> 12
        slot = min(max(otz >> OTZ_SHIFT, 0), 63)
        w = [pack_xy(*q) for q in p]
        if self.wire:
            lw = [(0x48 << 24) | gpu_word(COL["wire"]), w[0], w[1], w[3], w[2], w[0], 0x55555555]
            self.packets.append((slot, tuple(lw), fi, "L5"))
            st["wire"] += 1
        self.packets.append((slot, tuple([(0x28 << 24) | gpu_word(flag_colour(f["flags"]))] + w), fi, "F4"))
        st["drawn"] += 1
        self.faces[fi] = "drawn"
        return gone

    def stat_list(self):
        s = self.stats
        return [s["seen"], s["far"], s["near"], s["back"], s["big"], s["dropped"], s["drawn"], s["wire"]]

    def draw_order(self):
        """Packets in the order the GPU draws them: slot 63 first, newest-linked first within a slot."""
        idx = sorted(range(len(self.packets)), key=lambda i: (-self.packets[i][0], -i))
        return [self.packets[i] for i in idx]


# ---- poses ----------------------------------------------------------------------------------------------------------------------------------
def yaw_of(fx, fz):
    return round(math.atan2(fx, fz) * 4096 / (2 * math.pi)) % 4096


def sec_pose(trk, i, back=2400, height=900, wire=0, lab=None, dyaw=0):
    s = trk["sections"][i]
    f, u = s["forward"], s["up"]
    eye = tuple(round(s["centre"][k] - f[k] * back / 4096 + u[k] * height / 4096) for k in range(3))
    return dict(label=lab or f"section {i}, {back} units behind, {height} up", x=eye[0], y=eye[1], z=eye[2], yaw=(yaw_of(f[0], f[2]) + dyaw) % 4096, wire=wire)


def make_poses(trk, man, alt):
    nsec = len(trk["sections"])
    boosts = man["boost_sections"]
    out = [sec_pose(trk, trk["start_section"], 2400, 860, lab="the start line from behind"),
           sec_pose(trk, boosts[0], 2500, 900, lab=f"boost pad of section {boosts[0]}"),
           sec_pose(trk, boosts[-1], 1800, 700, lab=f"boost pad of section {boosts[-1]}"),
           sec_pose(trk, nsec // 2, 2000, 800, lab="the far side of the lap"),
           sec_pose(trk, (nsec * 3) // 4, 3000, 1000, lab="three quarters round"),
           sec_pose(trk, 20, 400, 150, lab="low and close: near-plane and oversized faces"),
           sec_pose(trk, 40, 300, 120, lab="on the road, looking along it", dyaw=0),
           sec_pose(trk, 70, 1500, 600, lab="looking away from the track", dyaw=2048),
           sec_pose(trk, trk["start_section"], 2400, 860, wire=1, lab="the start line, wireframe on"),
           sec_pose(trk, boosts[0], 2500, 900, wire=1, lab="boost pad, wireframe on")]
    # a corner of the world: many vertices are more than 32767 units away
    bb = [min(v[k] for v in trk["vertices"]) for k in range(3)] + [max(v[k] for v in trk["vertices"]) for k in range(3)]
    out.append(dict(label="at one end of the track, looking along its length (the far end is > 32767 away)", x=bb[0] - 3000, y=(bb[1] + bb[4]) // 2 - 700, z=(bb[2] + bb[5]) // 2,
                    yaw=1024, wire=0))
    out.append(dict(label="at the other end, looking back", x=bb[3] + 3000, y=(bb[1] + bb[4]) // 2 - 700, z=(bb[2] + bb[5]) // 2, yaw=3072, wire=0))
    # exact boundaries: vertex V is 32767 away (kept) or 32768 away (far) on one axis
    vi = 200 if len(trk["vertices"]) > 200 else len(trk["vertices"]) // 2
    V = trk["vertices"][vi]
    for axis, (name, delta) in enumerate((("x", 0), ("y", 0), ("z", 0))):
        if axis == 1 and not alt:
            continue                                   # the default camera box keeps |y| small: the y boundary needs the widened box of the alt run
        for sgn in (1, -1):
            for dist in (FAR, FAR + 1):
                e = list(V)
                e[axis] = V[axis] + sgn * dist
                for k in (0, 1, 2):
                    if k != axis:
                        e[k] = V[k] - (900 if k == 1 else 0)
                out.append(dict(label=f"vertex {vi}: d.{name} = {-sgn * dist} (|d| = {dist})", x=e[0], y=e[1], z=e[2],
                                yaw=(yaw_of(-sgn * dist, 0) if axis == 0 else (0 if axis == 2 else 1024)), wire=0))
    return out


# ---- the disc image ---------------------------------------------------------------------------------------------------------------------------
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
    """alt.bin / alt.cue next to hoverline.*: the same exe and files, TRACK.TRK replaced by the translated track 2."""
    bdir = ctx.build.build_dir
    if (bdir / "alt.cue").exists():
        return
    xml = next(iter(sorted(bdir.glob("cd_image_*.xml"))), None)
    if xml is None:
        raise CheckFailure(expected="CMake's configured iso xml", actual="not found", hint="Use psn00bsdk_add_cd_image.")
    (bdir / "alt").mkdir(exist_ok=True)
    (bdir / "alt" / "TRACK.TRK").write_bytes(ALT_BIN)
    text, k = re.subn(r'(<file\s+name="TRACK.TRK"[^>]*?source=")[^"]*(")', lambda m: m.group(1) + str(bdir / "alt" / "TRACK.TRK") + m.group(2), xml.read_text(), flags=re.I)
    expect_eq(k, 1, "iso.xml has one <file name=\"TRACK.TRK\" source=...> entry", hint="Appendix E.2: the track lives in <dir name=\"DATA\">.")
    (bdir / "alt.xml").write_text(text)
    p = subprocess.run(["mkpsxiso", "-y", "-q", "-o", "alt.bin", "-c", "alt.cue", "alt.xml"], cwd=bdir, capture_output=True, text=True, timeout=60, env=tool_env())
    expect_eq(p.returncode, 0, "mkpsxiso builds the alternative disc", hint=(p.stdout + p.stderr)[-400:])


def lua_val(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (bytes, bytearray)):
        return json.dumps(bytes(v).hex())
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, dict):
        return "{" + ",".join(f"[{json.dumps(k)}]={lua_val(x)}" for k, x in v.items()) + "}"
    return "{" + ",".join(lua_val(x) for x in v) + "}"


def params_lua(poses, box=None, cap=32768):
    d = {"poses": [{k: p[k] for k in ("x", "y", "z", "yaw", "wire")} for p in poses], "frame_sz": 64 * 4 + cap + 16}
    if box:
        d["box"] = box
    return "PARAMS = " + lua_val(d) + "\n"


MAIN_POSES = make_poses(TRK1, MAN1, False)
ALT_POSES = make_poses(TRK2, MAN2, True)
ALT_BOX = {"min": [-300000, -300000, -300000], "max": [300000, 300000, 300000]}
os.environ["CH34_PARAMS"] = str(_TMP / "params_main.lua")      # the default run's probe reads its pose list from here (the child process inherits it)


# ---- observing the runs -------------------------------------------------------------------------------------------------------------------------
def observe(ctx, name):
    name = "main" if name.startswith("main") else "alt"
    if name == "main":
        r = ctx.result
    else:
        alt_disc(ctx)
        gen = ctx.work / "params_alt.lua"
        gen.write_text(params_lua(ALT_POSES, ALT_BOX, prim_buf_size(ctx.project)) + "dofile(" + json.dumps(str(ctx.chapter_dir / "verify" / "probe.lua")) + ")\n")
        r = ctx.run("alt", iso="alt.cue", probe=gen)
    r.require_finished()
    exc = r.record("exception")
    if exc:
        raise CheckFailure(expected="no CPU exception", actual=f"CPU exception {exc['code']} at pc 0x{exc['epc']:08X}, address 0x{exc['badvaddr']:08X}",
                           hint="A load through a NULL or dangling pointer, a misaligned halfword/word access to the file image, or a trapping add (use unsigned or wider arithmetic)?")
    info = r.record("info")
    expect_true(info is not None, "the program reaches its frame loop", f"status {r.data.get('status')}",
                hint="Does it hang in cd_load_file? Booting + loading takes about 400 emulated frames.")
    return r, info


def model_of(name):
    return (TRK1, MAN1, MAIN_POSES) if name == "main" else (TRK2, MAN2, ALT_POSES)


def words(lst, n):
    """Lua arrays come back as dicts with string keys '1'..'n'."""
    if isinstance(lst, list):
        return lst
    return [lst[str(i)] for i in range(1, n + 1)]


def as_list(v):
    if isinstance(v, list):
        return v
    if not v:
        return []
    return [v[str(i)] for i in range(1, len(v) + 1)]


# ---- checks: the project -----------------------------------------------------------------------------------------------------------------------
@static_check("the state symbols and the given modules are linked", hint="main.c's asm block keeps the state alive; do not delete a declaration the verifier reads.")
def _(ctx):
    (_TMP / "params_main.lua").write_text(params_lua(MAIN_POSES, None, prim_buf_size(ctx.project)))     # read by the main run's probe (CH34_PARAMS)
    ctx.require_symbols(*STATE)


@static_check("the disc holds TRACK.TRK in \\DATA (and Chapter 33's files); the track is read at run time, not compiled in",
              hint="iso.xml lists the files of README 5.1; the CMake rule runs tools/assets/mkassets.py.")
def _(ctx):
    iso = Iso(ctx.build.build_dir / "hoverline.bin")
    for n in ("LOGO.TIM", "PROPS.TPK", "PYLON.SHP", "ARCH.SHP", "TOWER.SHP", "SCENE.BIN", "TRACK.TRK"):
        expect_true("\\DATA\\" + n in iso.files, f"\\DATA\\{n} is on the disc", ", ".join(sorted(iso.files)), "Add the <file> entry to iso.xml.")
        expect_eq(iso.read("\\DATA\\" + n), FILES[n], f"\\DATA\\{n} is the generated file", hint="The disc must carry the generator's bytes.")
    exe = (ctx.build.build_dir / "game.exe").read_bytes()
    expect_true(FILES["TRACK.TRK"][0x60:0x60 + 96] not in exe and FILES["TRACK.TRK"][0x1FE0:0x1FE0 + 96] not in exe, "the track is not inside the program", "found in game.exe",
                "Read the file from the disc at run time.")


@static_check("the primitive buffer is large enough for the whole track's fill packets (psxe's PRIM_BUF_SIZE >= 560 * 24 bytes)",
              hint="The Chapter 21 library has 2048 bytes: the track needs up to 13,440 bytes of POLY_F4, 31,360 with the wireframe. Edit PRIM_BUF_SIZE in psxe/include/psxe/ot.h.")
def _(ctx):
    n = prim_buf_size(ctx.project)
    expect_true(n >= 560 * 24, "PRIM_BUF_SIZE", f"{n}", "Raise it (README 5.7).")


def check_info(ctx, name):
    r, info = observe(ctx, name)
    trk, man, _ = model_of(name)
    expect_eq(info["load_status"], 0, f"{name}: load_status", hint=STATUS.get(info["load_status"], "") + f" (track_status {info['track_status']}).")
    expect_eq(info["track_status"], 0, f"{name}: track_status", fmt="dec", hint="track_parse must return 0 for the generated file.")
    t = [s32(x) for x in words(info["track"], 12)]
    unsigned = [x & 0xFFFFFFFF for x in t]
    expect_eq(t[4:], [man["section_count"], man["vertex_count"], man["face_count"], man["vis_entries"], man["start_section"], 1, man["texture_count"], man["total_length"]],
              f"{name}: Track (section_count, vertex_count, face_count, vis_count, start_section, flags, texture_count, total_length) = the manifest's", fmt="dec",
              hint="Counts come from the header (offsets 0x18..0x24, 0x38), never from constants: the alt disc has another track.")
    base = unsigned[0]
    expect_true(0x80000000 <= base < 0x80200000, f"{name}: the vertex table lives in RAM", f"0x{base:08X}")
    expect_eq(unsigned[1:4], [base + 12 * t[5], base + 12 * t[5] + 24 * t[6], base + 12 * t[5] + 24 * t[6] + 64 * t[4]], f"{name}: faces, sections and vis follow the vertices in place",
              fmt="hex", hint="The tables are used IN PLACE: pointers into the file image (vertices = image + 0x60, faces = vertices + 12 * vertex_count, ...).")
    return r, info


@check("main disc: track_parse of the disc's TRACK.TRK: Track counts equal the trkgen manifest (112 sections, 672 vertices, 560 faces), tables used in place",
       hint="Read the u16 counts at 0x18..0x24 and the offsets at 0x28..0x34; the Track points into the file image.")
def _(ctx):
    r, info = check_info(ctx, "main")
    expect_eq(info["object_count"], 35, "Chapter 33's scene still loads (object_count)", fmt="dec")
    expect_eq(info["proj_h"], PROJ_H, "proj_h", fmt="dec")


@check("alt disc: track 2, translated far from the origin (104 sections): counts and layout come from the file",
       hint="Hard-coded counts fail here: the alt track has 104 sections, 624 vertices, 520 faces.")
def _(ctx):
    check_info(ctx, "alt")


# ---- states and input ----------------------------------------------------------------------------------------------------------------------------
def snaps(r):
    return {s["name"]: s for s in (r.record("snaps") or [])}


@check("wireframe toggle: Select is edge-triggered: held 20 frames in the game -> wire_mode 1 exactly once; a 2-frame press -> back to 0; the game state stays STATE_GAME",
       hint="In game_update, toggle wire_mode on the press edge of Select (pressed, not held: held would flip it every frame).")
def _(ctx):
    r, info = observe(ctx, "main")
    expect_eq((info["game_state"], info["wire_mode"]), (0, 0), "at boot (game_state, wire_mode)", fmt="dec")
    tr = [tuple(x) for x in as_list(r.record("trace"))]
    sn = snaps(r)
    expect_eq((sn["title"]["game_state"], sn["title"]["wire_mode"]), (0, 0), "title: (game_state, wire_mode)", fmt="dec")
    expect_eq((sn["game"]["game_state"], sn["game"]["wire_mode"], sn["game"]["state_changes"]), (1, 0, 1), "game: (game_state, wire_mode, state_changes)", fmt="dec",
              hint="Start in the title -> STATE_GAME once.")
    hold = [t for t in tr if 14 <= t[0] <= 40]
    changes = sum(1 for a, b in zip(hold, hold[1:]) if a[2] != b[2])
    expect_eq(changes, 1, "20 frames of Select: wire_mode changes exactly once", fmt="dec", hint=f"rows {hold[:10]}... A level-triggered test flips it every frame.")
    expect_eq(sn["wire"]["wire_mode"], 1, "after the hold: wire_mode", fmt="dec")
    expect_eq(sn["wire_off"]["wire_mode"], 0, "after a short press: wire_mode", fmt="dec")
    expect_true(all(t[1] == 1 for t in tr), "game_state stays STATE_GAME while Select is used", str(tr[:5]))
    expect_true(sn["wire"]["stats"][7] > 0, "wire mode links line packets (track_stats.wire_prims > 0)", str(sn["wire"]["stats"]))
    expect_eq(sn["game"]["stats"][7], 0, "wire mode off: no line packets", fmt="dec")


@check("the fly camera still works (Chapter 28/33): UP + RIGHT move the eye cam_speed per frame",
       hint="game_update must still call camera_update() every GAME frame.")
def _(ctx):
    r, info = observe(ctx, "main")
    rows = [tuple(x) for x in as_list(r.record("fly"))]
    moves = [tuple(b[k] - a[k] for k in range(1, 5)) for a, b in zip(rows, rows[1:]) if any(b[k] != a[k] for k in range(1, 5))]
    expect_true(8 <= len(moves) <= 12, "8..12 frames of movement while UP + RIGHT are held", f"{len(moves)}")
    for d in moves:
        expect_eq(d, (200, 0, 200, 0), "per frame: (dx, dy, dz, dyaw)", fmt="dec", hint="RIGHT +x, UP +z, cam_speed = 200.")
    expect_eq(tuple(info["eye"]), (23883, -1500, -2500), "the camera starts behind the start line", fmt="dec")


# ---- the draw ---------------------------------------------------------------------------------------------------------------------------------
def pose_records(ctx, name):
    r, info = observe(ctx, name)
    trk, man, poses = model_of(name)
    sc = as_list(r.record("scenarios"))
    expect_eq(len(sc), len(poses), f"{name}: every pose was recorded", fmt="dec", hint=f"status {r.data.get('status')}")
    cap = prim_buf_size(ctx.project)
    out = []
    for s, p in zip(sc, poses):
        eye = (p["x"], p["y"], p["z"])
        expect_eq(tuple(s["eye"]), eye, f"{name}: [{p['label']}] cam_eye as posed", fmt="dec", hint="The probe writes cam_eye; with no pad input camera_update() leaves it inside its box.")
        expect_eq((s["game_state"], s["wire_mode"]), (1, p["wire"]), f"{name}: [{p['label']}] (game_state, wire_mode)", fmt="dec")
        m, t = view_from_words(words(s["view"], 8))
        ref = Ref(trk, eye, m, 0, len(trk["sections"]), p["wire"], 0, cap)
        out.append((s, p, ref, eye))
    return r, info, out


def vertex_rows(s, nv):
    v = as_list(s["v"])
    return [tuple(v[6 * i:6 * i + 6]) for i in range(nv)]


def check_stats(ctx, name):
    r, info, recs = pose_records(ctx, name)
    trk, man, poses = model_of(name)
    seen_far = seen_back = seen_big = seen_near = 0
    for s, p, ref, eye in recs:
        lab = f"{name}: [{p['label']}]"
        got = [x for x in as_list(s["stats"])]
        want = ref.stat_list()
        expect_eq(got, want, f"{lab}: track_stats (seen, far, near, back, big, dropped, drawn, wire_prims)", fmt="dec",
                  hint="Each face lands in exactly ONE bucket, tested in this order: any vertex far; any view z < 128; NCLIP area <= 0; wider than 1023 or taller than 511; "
                       "buffer full; drawn. All four vertices are classified before the first test.")
        expect_eq(s["prims"], ref.stats["drawn"] + ref.stats["wire"], f"{lab}: prims_submitted = packets linked", fmt="dec")
        expect_eq(s["dropped"], ref.stats["dropped"], f"{lab}: prims_dropped = faces dropped", fmt="dec")
        seen_far += ref.stats["far"]
        seen_back += ref.stats["back"]
        seen_big += ref.stats["big"]
        seen_near += ref.stats["near"]
    expect_true(seen_far > 0 and seen_back > 0 and seen_near > 0, f"{name}: the poses exercise the far, back-face and near-plane rules", f"far {seen_far}, back {seen_back}, near {seen_near}")
    return r, recs


@check("main disc: for every pose track_stats (seen / far / near / back / big / dropped / drawn / wire) and the packet counters equal the Python rules, in the order far -> near -> NCLIP -> size -> budget",
       hint="One test after another per face; a face counted in an earlier bucket is not tested again. Far means any |vertex - eye| component above 32767.")
def _(ctx):
    check_stats(ctx, "main")


@check("alt disc (track 2, translated by (+60000, 0, +45000), every absolute x and z above 16 bits): the same rules and counts",
       hint="The shortcut `load the absolute vertex, put the eye in TR` truncates coordinates above 32767: use d = vertex - eye in 32 bits.")
def _(ctx):
    check_stats(ctx, "alt")


def check_relative(ctx, name):
    r, info, recs = pose_records(ctx, name)
    trk, man, poses = model_of(name)
    nv = len(trk["vertices"])
    n_far = n_ok = 0
    for s, p, ref, eye in recs:
        lab = f"{name}: [{p['label']}]"
        rows = vertex_rows(s, nv)
        far_expected = []
        for i, (st, rx, ry, rz, sxy, sz) in enumerate(rows):
            v = trk["vertices"][i]
            d = tuple(v[k] - eye[k] for k in range(3))
            want_state = 2 if max(abs(c) for c in d) > FAR else 1
            expect_eq(st, want_state, f"{lab}: trk_vstate[{i}] (1 = camera-relative |d| <= 32767, 2 = far; d = {d})", fmt="dec",
                      hint="d = vertex - eye in 32-bit arithmetic; far when ANY component's magnitude is above 32767; every vertex of a drawn face is classified (also when an earlier vertex of the face was far).")
            if want_state == 1:
                n_ok += 1
                expect_eq((rx, ry, rz), d, f"{lab}: trk_rel[{i}] = vertex - eye, the SVECTOR the GTE was given", fmt="dec",
                          hint="Subtract the eye in s32, THEN narrow to s16. The absolute vertex (or one with the eye already in TR) is wrong.")
                expect_true(all(-FAR <= c <= FAR for c in (rx, ry, rz)), f"{lab}: trk_rel[{i}] within +-32767", str((rx, ry, rz)))
                sx, sy, sz_w = rtps(view_from_words(words(s["view"], 8))[0], d)
                expect_eq((s16(sxy & 0xFFFF), s16(sxy >> 16), sz), (sx, sy, sz_w), f"{lab}: vertex {i} projected (sx, sy, sz)", fmt="dec",
                          hint="RT = the view matrix's ROTATION, TR = 0, then RTPS on the camera-relative SVECTOR (README 5.5). Do not use view_mtx.t.")
            else:
                n_far += 1
        # the pose is meaningful: the boundary poses flip a vertex between 32767 and 32768
    expect_true(n_ok > 0 and n_far > 0, f"{name}: both kinds of vertex occur", f"ok {n_ok}, far {n_far}")


@check("main disc: after the transform setup every loaded vertex is camera-relative, within +-32767 and exactly vertex - eye; far vertices are classified, not loaded; projections are bit-exact (rotation-only RT, TR = 0)",
       hint="Per vertex: d = v - cam_eye in s32; if any |d| > 32767 -> far; else trk_rel[i] = d, gte_ldv0, gte_rtps, store sxy and sz. RT is view_mtx's rotation with t = 0.")
def _(ctx):
    check_relative(ctx, "main")


@check("alt disc: three-plus camera positions more than 50000 units from the origin, exact +-32767 / 32768 boundaries on every axis: the same",
       hint="The boundary poses put a vertex exactly 32767 away (kept) or 32768 away (far) on one axis.")
def _(ctx):
    r, info, recs = pose_records(ctx, "alt")
    far = [p for s, p, ref, eye in recs if max(abs(c) for c in eye) > 50000]
    expect_true(len(far) >= 3, "at least three alt poses are more than 50000 units from the origin", str(len(far)))
    check_relative(ctx, "alt")


@check("boundaries: the +-32767 / 32768 poses flip exactly the vertex they were built for, on each axis, in both directions",
       hint="`abs(d) > 32767` is far; 32767 itself is kept (s16 holds it).")
def _(ctx):
    for name in ("main", "alt"):
        r, info, recs = pose_records(ctx, name)
        trk, man, poses = model_of(name)
        vi = 200
        states = {}
        for s, p, ref, eye in recs:
            m = re.match(r"vertex 200: d\.(\w) = (-?\d+)", p["label"])
            if m:
                states[(m.group(1), int(m.group(2)))] = vertex_rows(s, len(trk["vertices"]))[vi][0]
        expect_true(len(states) >= (8 if name == "alt" else 4), f"{name}: boundary poses recorded", str(len(states)))
        for (ax, d), st in states.items():
            expect_eq(st, 1 if abs(d) <= FAR else 2, f"{name}: vertex {vi} with d.{ax} = {d}", fmt="dec",
                      hint="Kept when |d| <= 32767, far when 32768. (-32768 fits an s16 but the rule is symmetric.)")


# ---- the packets -------------------------------------------------------------------------------------------------------------------------------
def decode_pk(flat):
    flat = as_list(flat)
    out, i = [], 0
    while i < len(flat):
        slot, ln = flat[i], flat[i + 1]
        out.append((slot, tuple(flat[i + 2:i + 2 + ln])))
        i += 2 + ln
    return out


def check_packets(ctx, name):
    r, info, recs = pose_records(ctx, name)
    trk, man, poses = model_of(name)
    total = 0
    for s, p, ref, eye in recs:
        lab = f"{name}: [{p['label']}]"
        got = decode_pk(s["pk"])
        want = [(sl, w) for sl, w, fi, k in ref.packets]
        for sl, w in got:
            expect_true(len(w) in (5, 7) and (w[0] >> 24) in (0x28, 0x48), f"{lab}: only POLY_F4 (0x28) and polyline (0x48) packets", f"slot {sl}: command 0x{w[0] >> 24:02X}, {len(w)} words",
                        "The track draws filled quads and (with wire_mode) outlines, nothing else.")
        if sorted(got) != sorted(want):
            gs, ws = set(got), set(want)
            missing = [x for x in want if x not in gs]
            extra = [x for x in got if x not in ws]
            ex = (missing or extra)[0]
            kind = "missing" if missing else "unexpected"
            raise CheckFailure(expected=f"{lab}: {len(want)} packets (e.g. slot {ex[0]}: {[hex(x) for x in ex[1]]})", actual=f"{len(got)} packets; {kind} {len(missing) if missing else len(extra)} (first: slot {ex[0]}, words {[hex(x) for x in ex[1]]})",
                               hint="POLY_F4: code 0x28 + the legend color, the four projected corners in the file's order v0..v3; slot = (ZSF4 AVSZ4 of the four view z) >> 7; wire: command 0x48, "
                                    "corners v0 v1 v3 v2 v0, terminator 0x55555555, same slot as its face.")
        # the outline is drawn after its fill
        if p["wire"]:
            pos = {}
            for idx, (sl, w) in enumerate(got):
                pos.setdefault((sl, tuple(w[1:5]) if len(w) == 5 else None), idx)
            fills = {}
            for idx, (sl, w) in enumerate(got):
                if len(w) == 5:
                    fills[(sl, w[1:5])] = idx
            for idx, (sl, w) in enumerate(got):
                if len(w) == 7:
                    q = (sl, (w[1], w[2], w[4], w[3]))
                    f = fills.get(q)
                    expect_true(f is not None and f < idx, f"{lab}: the outline of a face comes AFTER its fill in the table walk (drawn on top)", f"fill at {f}, outline at {idx}",
                                "Link the outline first and the fill second: addPrim puts the newest packet first in a slot.")
        total += len(got)
    expect_true(total > 200, f"{name}: enough packets were compared", str(total))


@check("main disc: for every pose the ordering table holds exactly the Python-computed packets (color by flag, the four corners, the slot); outlines come after their fills",
       hint="Legend: START white (240,240,240), BOOST (0,200,255), WALL (40,60,120), FLOOR (70,72,80); the corners are the projected vertices v0..v3 of the face record.")
def _(ctx):
    check_packets(ctx, "main")


@check("alt disc: the same packets (color fields in the file are zero: the color comes from the flags)",
       hint="Do not read TrkFace.color: derive the color from flags with track_colour().")
def _(ctx):
    check_packets(ctx, "alt")


# ---- pictures ----------------------------------------------------------------------------------------------------------------------------------
def tri_in(p, a, b, c):
    d1 = (p[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[1] - b[1])
    d2 = (p[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (p[1] - c[1])
    d3 = (p[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[1] - a[1])
    neg = d1 < 0 or d2 < 0 or d3 < 0
    pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (neg and pos)


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def unpack_xy(w):
    return (s16(w & 0xFFFF), s16(w >> 16))


def check_pictures(ctx, name):
    r, info, recs = pose_records(ctx, name)
    trk, man, poses = model_of(name)
    n_samples = n_boost = n_wire = 0
    for s, p, ref, eye in recs:
        lab = f"{name}: [{p['label']}]"
        img = r.screenshot("s%d" % s["k"])
        order = ref.draw_order()
        polys = []
        for slot, w, fi, kind in [(a, b, c, d) for (a, b, c, d) in order]:
            if kind == "F4":
                polys.append(("F4", [unpack_xy(x) for x in w[1:5]], (w[0] & 255, (w[0] >> 8) & 255, (w[0] >> 16) & 255), fi))
            else:
                polys.append(("L5", [unpack_xy(x) for x in w[1:6]], COL["wire"], fi))
        fills = [q for q in polys if q[0] == "F4"]

        def winner(pt):
            col = BG
            for kind, pts, c, fi in polys:
                if kind == "F4":
                    if tri_in(pt, pts[0], pts[1], pts[2]) or tri_in(pt, pts[1], pts[2], pts[3]):
                        col = c
                elif any(seg_dist(pt, pts[i], pts[i + 1]) <= 0.7 for i in range(4)):
                    col = c
            return col

        def clear(pt, margin):
            for kind, pts, c, fi in fills:
                loop = [pts[0], pts[1], pts[3], pts[2], pts[0]]
                if any(seg_dist(pt, loop[i], loop[i + 1]) < margin for i in range(4)):
                    return False
            return True

        # centers of drawn faces (boost and start faces first): the color at a safely interior point is the painter's winner
        cand = []
        for kind, pts, c, fi in fills:
            cx_, cy_ = sum(q[0] for q in pts) / 4, sum(q[1] for q in pts) / 4
            area = abs(nclip(pts[0], pts[1], pts[2]))
            if 2 <= cx_ < W - 2 and 2 <= cy_ < H - 2 and area > 60:
                pri = 0 if trk["faces"][fi]["flags"] & 12 else 1
                cand.append((pri, -area, fi, (round(cx_), round(cy_))))
        cand.sort()
        used = 0
        for pri, _a, fi, pt in cand:
            if used >= 70:
                break
            if not p["wire"] and not clear(pt, 2.0):
                continue
            if p["wire"]:
                continue
            want = winner(pt)
            got = img.pixel(*pt)
            expect_true(max(abs(got[k] - want[k]) for k in range(3)) <= 14, f"{lab}: pixel {pt} (center of face {fi}, flags {trk['faces'][fi]['flags']}) is {fmt_rgb(want)}",
                        fmt_rgb(got), "The face's color comes from its flags; faces are linked at the slot of the average view z, nearer ones are drawn later.")
            used += 1
            n_samples += 1
            if want == COL["boost"]:
                n_boost += 1
        if p["wire"]:
            hits = tried = 0
            for kind, pts, c, fi in polys:
                if kind != "L5" or tried >= 40:
                    continue
                a, b = pts[0], pts[1]
                mid = (round((a[0] + b[0]) / 2), round((a[1] + b[1]) / 2))
                if not (3 <= mid[0] < W - 3 and 3 <= mid[1] < H - 3) or math.hypot(a[0] - b[0], a[1] - b[1]) < 12:
                    continue
                if winner(mid) != COL["wire"]:
                    continue                                     # something nearer covers this edge
                tried += 1
                if any(max(abs(img.pixel(mid[0] + dx, mid[1] + dy)[k] - COL["wire"][k]) for k in range(3)) <= 40 for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                    hits += 1
            expect_true(tried >= 8, f"{lab}: enough uncovered outline edges to sample", str(tried))
            expect_true(hits >= tried * 0.9, f"{lab}: the outline is on screen: yellow pixels at {tried} edge midpoints", f"{hits} of {tried}",
                        "The overlay is one 5-point polyline per face in yellow (255,255,0), drawn after the fill.")
            n_wire += tried
    expect_true(n_samples >= 60, f"{name}: enough face colors were sampled", str(n_samples))
    expect_true(n_boost >= 2, f"{name}: boost-pad colored pixels (0,200,255) were found at projected boost faces", str(n_boost))
    expect_true(n_wire >= 30, f"{name}: outline edges were sampled", str(n_wire))


@check("main disc pictures: the color at the center of drawn faces (painter's order) matches the legend, including the cyan boost pads; wireframe edges are yellow",
       hint="Floor gray, wall blue, boost cyan, start white; nearer faces are drawn later (OT slot from AVSZ4 of the four view z).")
def _(ctx):
    check_pictures(ctx, "main")


@check("alt disc pictures: the same (color fields zeroed in the file: black faces mean the color field was used)",
       hint="Use track_colour(flags).")
def _(ctx):
    check_pictures(ctx, "alt")


@check("the primitive buffers are never overrun (guard bytes intact) in every pose; prims_dropped matches the model",
       hint="ot_alloc returns NULL when the buffer is full: count the face as dropped and stop allocating for the rest of the frame.")
def _(ctx):
    for name in ("main", "alt"):
        r, info = observe(ctx, name)
        for g in as_list(r.record("guards")):
            expect_eq(list(as_list(g)), [0xA5] * 16, f"{name}: guard bytes after a primitive buffer", fmt="hex")


@check("the whole track is drawn and timed: track_draw returns in a sane time and its CPU cycles are recorded (README 5.7 reports them; not a pass/fail limit)",
       hint="Chapter 38's window exists because this is slow.")
def _(ctx):
    r, info, recs = pose_records(ctx, "main")
    s, p, ref, eye = recs[0]
    expect_true(s["draw_cycles"] > 0, "the probe measured track_draw", str(s["draw_cycles"]))
    expect_true(s["draw_cycles"] < 30_000_000, "track_draw returns in a sane time", str(s["draw_cycles"]))


# ---- direct calls ----------------------------------------------------------------------------------------------------------------------------
SRC, OUT = 0x80180000, 0x801E0000
FILL = 0xA5
_REF = {}
TINY, TINY_META = trkgen.generate(1, 4)
TINY_D = formats.parse_trk(TINY)


def patch(blob, *edits):
    b = bytearray(blob)
    for off, fmt, val in edits:
        struct.pack_into(fmt, b, off, val)
    return bytes(b)


def parse_case(name, blob, want, size=None, addr=SRC, kind="parse", **kw):
    return dict(name=f"track_parse: {name}", fn="track_parse", args=[addr, len(blob) if size is None else size, OUT, 0], kind=kind, want=want, blob=blob, addr=addr,
                writes=[[addr, blob], [OUT, bytes([FILL]) * 48]], reads=[[OUT, 48], [addr, len(blob) if len(blob) <= 4096 else 0]], **kw)


def limit_file(ns=1, nv=4, nf=1, nvis=1):
    """A consistent file with these counts (everything else minimal)."""
    verts = [((i * 7) % 900, -(i % 50), (i * 13) % 900) for i in range(nv)]
    faces = [dict(v=(i % nv, (i + 1) % nv, (i + 2) % nv, (i + 3) % nv), flags=1, tex=0xFF, uv=[(0, 0)] * 4, color=(1, 2, 3)) for i in range(nf)]
    secs = [dict(centre=(0, 0, 0), half_width=600, length=1000, forward=(0, 0, 4096), right=(4096, 0, 0), up=(0, -4096, 0), first_face=0, face_count=1, next=(i + 1) % ns,
                 prev=(i - 1) % ns, flags=0, edges=(0, 1, 2, 3 % nv)) for i in range(ns)]
    vis = [[] for _ in range(ns)]
    vis[0] = [i % ns for i in range(nvis)]
    return formats.build_trk("LIMIT", verts, faces, secs, vis, 0, 1000 * ns, 8)


def parse_cases():
    t = TINY
    ns, nv, nf, nvis = struct.unpack_from("<HHHH", t, 0x18)
    off_v, off_f, off_s, off_vis = struct.unpack_from("<IIII", t, 0x28)
    assert (ns, nv, nf) == (4, 24, 20) and off_v == 0x60
    cases = [parse_case("a genuine tiny track (4 sections, 24 vertices, 20 faces)", t, 0)]
    c = lambda *a, **k: cases.append(parse_case(*a, **k))
    # ---- order of the checks
    c("misaligned image (address + 2)", t, -2, addr=SRC + 2)
    c("misaligned AND bad magic: ALIGN first", t.replace(b"TRK1", b"XXXX", 1), -2, addr=SRC + 1)
    c("3 bytes long", t[:3], -3)
    c("0 bytes long", t[:0], -3)
    c("bad magic (TRK2)", t.replace(b"TRK1", b"TRK2", 1), -3)
    c("bad magic AND a bad header: MAGIC first", patch(t.replace(b"TRK1", b"TRK0", 1), (0x18, "<H", 0)), -3)
    c("magic only, 4 bytes", t[:4], -4)
    c("0x5C bytes: shorter than the header", t[:0x5C], -4)
    c("bad header AND a bad vertex: HEADER first", patch(t, (0x18, "<H", 0), (0x60, "<i", 5_000_000)), -4)
    c("bad vertex AND a bad face: VERTEX first", patch(t, (0x60, "<i", 5_000_000), (off_f, "<H", 99)), -5)
    c("bad face AND a bad section: FACE first", patch(t, (off_f, "<H", 99), (off_s + 0x2C, "<H", 99)), -6)
    c("bad section AND a bad visibility entry: SECTION first", patch(t, (off_s + 0x2C, "<H", 99), (off_vis, "<H", 99)), -7)
    # ---- header
    c("file_size one more than the real size", patch(t, (4, "<I", len(t) + 1)), -4)
    c("size argument 4 bytes short", t[:-4], -4, size=len(t) - 4)
    c("size argument 4 bytes long (trailing bytes)", t + bytes(4), -4, size=len(t) + 4)
    c("file_size fixed up but 4 bytes of garbage after the visibility list", patch(t + bytes(4), (4, "<I", len(t) + 4)), -4)
    c("section_count 0", patch(t, (0x18, "<H", 0)), -4)
    c("section_count 161", patch(t, (0x18, "<H", 161)), -4)
    c("section_count 65535", patch(t, (0x18, "<H", 65535)), -4)
    c("vertex_count 0", patch(t, (0x1A, "<H", 0)), -4)
    c("vertex_count 1025", patch(t, (0x1A, "<H", 1025)), -4)
    c("face_count 0", patch(t, (0x1C, "<H", 0)), -4)
    c("face_count 1025", patch(t, (0x1C, "<H", 1025)), -4)
    c("vis_count 8193", patch(t, (0x1E, "<H", 8193)), -4)
    c("start_section = section_count", patch(t, (0x20, "<H", ns)), -4)
    c("start_section 65535", patch(t, (0x20, "<H", 65535)), -4)
    c("vertices_offset 0x64", patch(t, (0x28, "<I", 0x64)), -4)
    c("faces_offset 4 too high", patch(t, (0x2C, "<I", off_f + 4)), -4)
    c("sections_offset 4 too low", patch(t, (0x30, "<I", off_s - 4)), -4)
    c("vis_offset 4 too high", patch(t, (0x34, "<I", off_vis + 4)), -4)
    c("vis_offset 0xFFFFFFF0 (the sum wraps in 32 bits)", patch(t, (0x34, "<I", 0xFFFFFFF0)), -4)
    c("vertex_count one too high (the tables no longer tile the file)", patch(t, (0x1A, "<H", nv + 1)), -4)
    c("vis_count one too high", patch(t, (0x1E, "<H", nvis + 3)), -4)
    # ---- vertices
    last = off_v + 12 * (nv - 1)
    c("vertex 5: x = 1,000,001", patch(t, (off_v + 60, "<i", 1_000_001)), -5)
    c("vertex 23: z = -1,000,001", patch(t, (last + 8, "<i", -1_000_001)), -5)
    c("vertex 0: y = 0x7FFFFFFF", patch(t, (off_v + 4, "<i", 0x7FFFFFFF)), -5)
    c("vertex 0: x = 0x80000000", patch(t, (off_v, "<i", -0x80000000)), -5)
    c("vertex 7: y = +1,000,000 exactly (accepted)", patch(t, (off_v + 84 + 4, "<i", 1_000_000)), 0)
    c("vertex 8: x = -1,000,000 exactly (accepted)", patch(t, (off_v + 96, "<i", -1_000_000)), 0)
    # ---- faces
    F = lambda i, o=0: off_f + 24 * i + o
    c("face 0: v0 = vertex_count", patch(t, (F(0), "<H", nv)), -6)
    c("face 19: v3 = 0xFFFF", patch(t, (F(19, 6), "<H", 0xFFFF)), -6)
    c("face 7: v1 = vertex_count", patch(t, (F(7, 2), "<H", nv)), -6)
    c("face 3: v2 = vertex_count - 1 (accepted)", patch(t, (F(3, 4), "<H", nv - 1)), 0)
    c("face 2: flags bit 5", patch(t, (F(2, 8), "<H", 0x21)), -6)
    c("face 2: flags bit 15", patch(t, (F(2, 8), "<H", 0x8001)), -6)
    c("face 2: flags 0", patch(t, (F(2, 8), "<H", 0)), -6)
    c("face 2: BOOST only (no FLOOR)", patch(t, (F(2, 8), "<H", 4)), -6)
    c("face 2: START | WALL (no FLOOR)", patch(t, (F(2, 8), "<H", 8 | 2)), -6)
    c("face 2: FLOOR | WALL (accepted)", patch(t, (F(2, 8), "<H", 3)), 0)
    c("face 2: WALL | FLIP_H (accepted)", patch(t, (F(2, 8), "<H", 0x12)), 0)
    c("face 4: tex = texture_count (8)", patch(t, (F(4, 10), "<B", 8)), -6)
    c("face 4: tex 9", patch(t, (F(4, 10), "<B", 9)), -6)
    c("face 4: tex 254", patch(t, (F(4, 10), "<B", 254)), -6)
    c("face 4: tex 255 = untextured (accepted)", patch(t, (F(4, 10), "<B", 255)), 0)
    c("face 4: tex 7 (accepted)", patch(t, (F(4, 10), "<B", 7)), 0)
    c("texture_count 0 while the faces name textures", patch(t, (0x24, "<H", 0)), -6)
    # ---- sections
    S = lambda i, o=0: off_s + 64 * i + o
    c("section 1: next = section_count", patch(t, (S(1, 0x2C), "<H", ns)), -7)
    c("section 2: prev = 0xFFFF", patch(t, (S(2, 0x2E), "<H", 0xFFFF)), -7)
    c("section 3: first_face 16 + face_count 5 = 21 > 20", patch(t, (S(3, 0x28), "<H", 16), (S(3, 0x2A), "<H", 5)), -7)
    c("section 3: first_face 0xFFFF + face_count 2 (a 16-bit sum would wrap to 1)", patch(t, (S(3, 0x28), "<H", 0xFFFF), (S(3, 0x2A), "<H", 2)), -7)
    c("section 0: face_count 0xFFFF", patch(t, (S(0, 0x2A), "<H", 0xFFFF)), -7)
    c("section 3: first_face 15 + face_count 5 = 20 (accepted)", patch(t, (S(3, 0x28), "<H", 15), (S(3, 0x2A), "<H", 5)), 0)
    c("section 1: edges[2] = vertex_count", patch(t, (S(1, 0x36 + 4), "<H", nv)), -7)
    c("section 1: edges[3] = 0xFFFF", patch(t, (S(1, 0x36 + 6), "<H", 0xFFFF)), -7)
    c("section 0: edges[0] = vertex_count - 1 (accepted)", patch(t, (S(0, 0x36), "<H", nv - 1)), 0)
    c("section 2: flags bit 2", patch(t, (S(2, 0x30), "<H", 4)), -7)
    c("section 2: flags JUNCTION | START (accepted)", patch(t, (S(2, 0x30), "<H", 3)), 0)
    c("section 1: vis_first = vis_count of the file, vis_count 1", patch(t, (S(1, 0x32), "<H", nvis), (S(1, 0x34), "<H", 1)), -7)
    c("section 1: vis_first 0xFFFF, vis_count 2 (a 16-bit sum would wrap)", patch(t, (S(1, 0x32), "<H", 0xFFFF), (S(1, 0x34), "<H", 2)), -7)
    c("section 1: vis slice ends exactly at the end of the list (accepted)", patch(t, (S(1, 0x32), "<H", nvis - 2), (S(1, 0x34), "<H", 2)), 0)
    # ---- visibility
    c("visibility entry 0 = section_count", patch(t, (off_vis, "<H", ns)), -8)
    c("the last visibility entry = 0xFFFF", patch(t, (off_vis + 2 * (nvis - 1), "<H", 0xFFFF)), -8)
    # ---- limits
    cases.append(parse_case("at the section limit (160 sections)", limit_file(ns=160), 0, kind="limit"))
    cases.append(parse_case("one over the section limit (161)", limit_file(ns=161), -4, kind="limit"))
    cases.append(parse_case("at the vertex limit (1024)", limit_file(nv=1024), 0, kind="limit"))
    cases.append(parse_case("one over the vertex limit (1025)", limit_file(nv=1025), -4, kind="limit"))
    cases.append(parse_case("at the face limit (1024)", limit_file(nf=1024), 0, kind="limit"))
    cases.append(parse_case("one over the face limit (1025)", limit_file(nf=1025), -4, kind="limit"))
    cases.append(parse_case("at the visibility limit (8192 entries)", limit_file(nvis=8192), 0, kind="limit"))
    cases.append(parse_case("one over the visibility limit (8193)", limit_file(nvis=8193), -4, kind="limit"))
    for cs in cases:
        if cs["kind"] == "limit":
            cs["reads"][1] = [SRC, 0]
    return cases


def accessor_cases():
    cases = []
    for fn, count, stride in (("track_vertex", MAN1["vertex_count"], 12), ("track_face", MAN1["face_count"], 24), ("track_section", MAN1["section_count"], 64)):
        for i in (-1, 0, 1, count // 2, count - 1, count, count + 1, 65535, 65536, 1 << 20, -100000, -(1 << 31)):
            cases.append(dict(name=f"{fn}({i})", fn=fn, args=["track", i & 0xFFFFFFFF, 0, 0], kind="acc", i=i, count=count, stride=stride, which=fn, writes=[], reads=[["track", 48]]))
    return cases


def colour_cases():
    cases = []
    for flags in list(range(64)) + [0x8000, 0xFFFF, 0x0100]:
        cases.append(dict(name=f"track_colour(0x{flags:04X})", fn="track_colour", args=[flags, 0, 0, 0], kind="col", flags=flags, writes=[], reads=[]))
    return cases


def window_setup():
    """view_mtx (a yaw rotation, t deliberately non-zero), cam_eye at section 20, wire_mode."""
    s = TRK1["sections"][20]
    f, u = s["forward"], s["up"]
    eye = tuple(round(s["centre"][k] - f[k] * 1800 / 4096 + u[k] * 800 / 4096) for k in range(3))
    yaw = yaw_of(f[0], f[2])
    a = 2 * math.pi * yaw / 4096
    sn, cs = round(math.sin(a) * 4096), round(math.cos(a) * 4096)
    m = [[cs, 0, -sn], [0, 4096, 0], [sn, 0, cs]]
    t = (1234, -5678, 9999)
    vb = struct.pack("<9h", *[x for r in m for x in r]) + b"\0\0" + struct.pack("<3i", *t)
    return eye, m, vb


def window_cases(ctx):
    eye, m, vb = window_setup()
    sym = ctx.symbols
    cases = []

    def setup(wire):
        return [["view_mtx", vb], ["cam_eye", struct.pack("<4i", *eye, 0)], ["wire_mode", struct.pack("<i", wire)]]

    def begin():
        cases.append(dict(name="render_begin", fn="render_begin", args=[0, 0, 0, 0], kind="noop", writes=[], reads=[]))
        cases.append(dict(name="ot_begin_frame", fn="ot_begin_frame", args=[0, 0, 0, 0], kind="noop", writes=[], reads=[]))

    nv = len(TRK1["vertices"])
    for first, count, wire in ((0, 112, 0), (10, 5, 0), (110, 5, 0), (5, 0, 0), (5, -2, 0), (-3, 4, 0), (100, 500, 0), (111, 1, 0), (0, 1, 0), (50, 1, 0), (-1, 112, 0),
                               (112, 3, 0), (10, 20, 1), (0, 112, 1)):
        begin()
        cases.append(dict(name=f"track_draw(first {first}, count {count}, wire {wire})", fn="track_draw", args=["track", first & 0xFFFFFFFF, count & 0xFFFFFFFF, 0], kind="win",
                          first=first, count=count, wire=wire, writes=setup(wire),
                          reads=[["track_stats", 32], ["trk_vstate", nv], ["prims_submitted", 4], ["prims_dropped", 4]]))
    # the primitive buffer over several calls: render_begin resets the counters, ot_begin_frame is NOT called between the draws
    begin()
    for k in range(6):
        cases.append(dict(name="render_begin", fn="render_begin", args=[0, 0, 0, 0], kind="noop", writes=[], reads=[]))
        cases.append(dict(name=f"track_draw(0, 112, wire 1), call {k + 1} on the same frame", fn="track_draw", args=["track", 0, 112, 0], kind="budget", k=k, writes=setup(1),
                          reads=[["track_stats", 32], ["prims_submitted", 4], ["prims_dropped", 4]]))
    fs = sym["ot_frames"]
    cap = prim_buf_size(ctx.project)
    fr = 64 * 4 + cap + 16
    cases.append(dict(name="guards", fn="render_begin", args=[0, 0, 0, 0], kind="guards", writes=[], reads=[[fs + 64 * 4 + cap, 16], [fs + fr + 64 * 4 + cap, 16]]))
    return cases


def direct(ctx):
    if "direct" in _REF:
        return _REF["direct"]
    allc = parse_cases() + accessor_cases() + colour_cases() + window_cases(ctx)
    gen = ctx.work / "probe_direct_gen.lua"
    gen.write_text("CASES = " + lua_val([dict(name=c["name"], fn=c["fn"], args=c["args"], writes=c["writes"], reads=c["reads"]) for c in allc]) + "\ndofile("
                   + json.dumps(str(ctx.chapter_dir / "verify" / "probe_direct.lua")) + ")\n")
    r = ctx.run("direct", probe=gen, max_frames=1100)
    r.require_finished()
    exc = r.record("exception")
    if exc:
        raise CheckFailure(expected="no CPU exception in a direct call", actual=f"exception {exc['code']} in {exc.get('fn')} ({exc.get('name')}) at pc "
                           f"0x{exc['epc']:08X}, address 0x{exc['badvaddr']:08X}",
                           hint="Reading past the end of the file? A cast to a wider type on a misaligned address (read fields byte by byte)? Indexing a table before checking the index?")
    recs = r.record("cases")
    expect_true(recs and len(recs) == len(allc), "all direct calls completed", f"{len(recs or [])} of {len(allc)} (status {r.data.get('status')})",
                hint="A call that never returns: a loop that does not advance?")
    _REF["direct"] = list(zip(allc, as_list(recs)))
    return _REF["direct"]


@check("track_parse accepts the good files and rejects every damaged one with the documented code, in order: ALIGN -2, MAGIC -3, HEADER -4, VERTEX -5, FACE -6, SECTION -7, VIS -8; *out is zeroed on failure; the file is not modified",
       hint="Validate in the order of track.h before anything else: alignment, magic, header (counts, limits, offsets, exact size), vertices, faces, sections, visibility. Do the arithmetic in 32 bits (u16 + u16 can wrap a 16-bit sum).")
def _(ctx):
    for c, rec in direct(ctx):
        if c["kind"] != "parse":
            continue
        expect_eq(s32(rec["v0"]), c["want"], c["name"], fmt="dec",
                  hint="Codes: 0 ok, -2 ALIGN, -3 MAGIC, -4 HEADER, -5 VERTEX, -6 FACE, -7 SECTION, -8 VIS. Widen u16 values before adding them.")
        out = bytes.fromhex(rec["reads"][0])
        if c["want"] != 0:
            expect_eq(out, bytes(48), f"{c['name']}: *out is all zero after a failure", hint="Zero *out first (or on every failure path).")
        else:
            w = struct.unpack("<12i", out)
            blob = c["blob"]
            ns, nv, nf, nvis = struct.unpack_from("<HHHH", blob, 0x18)
            want = [c["addr"] + 0x60, c["addr"] + 0x60 + 12 * nv, c["addr"] + 0x60 + 12 * nv + 24 * nf, c["addr"] + 0x60 + 12 * nv + 24 * nf + 64 * ns]
            expect_eq([x & 0xFFFFFFFF for x in w[:4]], want, f"{c['name']}: table pointers point INTO the image", fmt="hex", hint="No copy: vertices = data + 0x60, ...")
            start, flags, ntex = struct.unpack_from("<HHH", blob, 0x20)
            expect_eq(list(w[4:]), [ns, nv, nf, nvis, start, flags, ntex, struct.unpack_from("<I", blob, 0x38)[0]], f"{c['name']}: counts, start, flags, texture_count, total_length",
                      fmt="dec")
        if rec["reads"][1]:
            expect_eq(bytes.fromhex(rec["reads"][1]), c["blob"], f"{c['name']}: the input is not modified", hint="The parser is read-only.")


@check("track_vertex / track_face / track_section return the address of record i of the loaded track, or NULL for any index below 0 or at or above the count",
       hint="Check both ends of the range, comparing as signed ints (a size_t or unsigned comparison lets -1 through).")
def _(ctx):
    for c, rec in direct(ctx):
        if c["kind"] != "acc":
            continue
        t = [x & 0xFFFFFFFF for x in struct.unpack("<12I", bytes.fromhex(rec["reads"][0]))]
        base = t[{"track_vertex": 0, "track_face": 1, "track_section": 2}[c["which"]]]
        want = base + c["stride"] * c["i"] if 0 <= c["i"] < c["count"] else 0
        expect_eq(rec["v0"] & 0xFFFFFFFF, want, c["name"], fmt="hex", hint="NULL for an index outside 0 .. count-1.")


@check("track_colour(flags): START white, else BOOST cyan, else WALL blue, else FLOOR gray, else magenta (the legend), as a GPU word r | g << 8 | b << 16",
       hint="Test the flags in the order START, BOOST, WALL, FLOOR. A boost pad is FLOOR | BOOST, the start line FLOOR | START.")
def _(ctx):
    for c, rec in direct(ctx):
        if c["kind"] != "col":
            continue
        want = gpu_word(flag_colour(c["flags"]))
        expect_eq(rec["v0"] & 0xFFFFFF, want, c["name"], fmt="hex", hint="(255,0,255) for none of the four flags; FLIP_H changes nothing.")


@check("track_draw(t, first, count): windows of sections: wrap modulo section_count, count cut to the section count, count <= 0 draws nothing, negative first; stats and vertices seen equal the model; view_mtx.t is not used",
       hint="Section k of the window is (first + k) mod section_count (first normalized to 0..n-1 even when negative); count > n draws each section once. The matrix is the ROTATION of view_mtx, TR = 0.")
def _(ctx):
    eye, m, vb = window_setup()
    cap = prim_buf_size(ctx.project)
    n_win = 0
    for c, rec in direct(ctx):
        if c["kind"] != "win":
            continue
        ref = Ref(TRK1, eye, m, c["first"], c["count"], c["wire"], 0, cap)
        stats = list(struct.unpack("<8i", bytes.fromhex(rec["reads"][0])))
        expect_eq(stats, ref.stat_list(), f"{c['name']}: track_stats", fmt="dec", hint="seen, far, near, back, big, dropped, drawn, wire_prims")
        vs = list(bytes.fromhex(rec["reads"][1]))
        expect_eq(vs, ref.state, f"{c['name']}: trk_vstate (which vertices the window touched, and how)", fmt="dec", hint="Only vertices of faces in the window are classified; trk_vstate is reset every call.")
        sub, dr = [struct.unpack("<i", bytes.fromhex(x))[0] for x in rec["reads"][2:4]]
        expect_eq((sub, dr), (ref.stats["drawn"] + ref.stats["wire"], ref.stats["dropped"]), f"{c['name']}: (prims_submitted, prims_dropped) after render_begin", fmt="dec")
        n_win += 1
    expect_true(n_win >= 12, "the window cases ran", str(n_win))


@check("the primitive budget: repeated draws on one frame fill the buffer; faces that find it full are counted dropped (once full, all later faces of the call), the guard bytes survive",
       hint="When ot_alloc returns NULL, count the face in faces_dropped and prims_dropped, and allocate nothing more in this track_draw.")
def _(ctx):
    eye, m, vb = window_setup()
    cap = prim_buf_size(ctx.project)
    used, dropped_any = 0, 0
    k = 0
    for c, rec in direct(ctx):
        if c["kind"] == "budget":
            ref = Ref(TRK1, eye, m, 0, 112, 1, used, cap)
            used = ref.used
            stats = list(struct.unpack("<8i", bytes.fromhex(rec["reads"][0])))
            expect_eq(stats, ref.stat_list(), f"{c['name']}: track_stats", fmt="dec", hint="seen, far, near, back, big, dropped, drawn, wire_prims")
            dr = struct.unpack("<i", bytes.fromhex(rec["reads"][2]))[0]
            expect_eq(dr, ref.stats["dropped"], f"{c['name']}: prims_dropped", fmt="dec")
            dropped_any += ref.stats["dropped"]
        elif c["kind"] == "guards":
            for g in rec["reads"]:
                expect_eq(bytes.fromhex(g), bytes([0xA5]) * 16, "guard bytes behind a primitive buffer", hint="Never write past ot_alloc's block.")
    if cap <= 40000:
        expect_true(dropped_any > 0, "six wireframe draws overflow the buffer (the model predicts drops)", str(dropped_any))
