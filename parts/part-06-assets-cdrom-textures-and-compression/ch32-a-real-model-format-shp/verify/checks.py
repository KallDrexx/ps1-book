"""Chapter 32 checks: A Real Model Format: .SHP ("The Ship, Textured").
Build: CMake + PSn00bSDK; the CMake rule runs tools/assets/mkassets.py (SHIP.SHP + SHIP.TPK). The emulator BOOTS THE .cue.
MAIN RUN (the boot disc): the probe poses the ship by writing spin_step = 0, render_mode and the three angles at the end of a frame, and records the
frame drawn with them: 3 poses x 2 modes (flat fallback, textured). Per scenario it records screen_xy / screen_z / mtx and the packets found by walking the
ordering table DrawOTag was given. Checks against the generator's manifest and the reference parser (tools/assets/formats.py):
  load and counts: load_status 0; shp_info (counts per primitive type, vertex/normal/prim/texture counts, name) equals SHIP.SHP.json; store.tex[] holds the
  TPK's textures with the tpage/clut/u/v/w/h of Appendix E.3.4;
  geometry: mtx is the SDK's RotMatrix of the angles with translation (0, 0, cam_z); screen_xy / screen_z follow a float projection of the file's vertices;
  packets: for every record the verifier derives the expected packet from the FILE and from the program's own screen_xy/screen_z (integer NCLIP, culling rule,
  double-sided flag, AVSZ3/AVSZ4 slot rule, per-type kind, colors, absolute UVs, tpage and clut from the manifest's tsb/cba, the semi-transparency bit) and the
  multiset of packets in the table must be exactly that, in both modes;
  picture: the screenshot's silhouette matches the projected vertices; sample points of the top-most polygons have the color the packet
  (and, for textures, the TIM) says; the perceptual hash (dHash 16x16) is within a tolerance of a reference render of the solution (verify/ref/*.png).
ALT RUN: a second disc: SHIP.SHP is the alternate ship (shpgen --variant 1: other counts, no canopy, two more GT4) and SHIP.TPK holds the same three textures
at other VRAM places (one in a different page, one 8 bpp): everything above again except the hash. Hard-coded counts or TSB/CBA fail here.
DIRECT CALLS (probe_direct.lua): shp_parse on the shipped files and on crafted bad ones (bad magic, truncated, misaligned, header lies, prims_size overflow,
wrong prim_count, bad tag, bad record size, index or texture index out of range) with the documented codes; shp_decode on every record; shp_record_size;
shp_packet_size; shp_fill for every type with and without a texture.
SHP_UPDATE_REFS=1 (environment) rewrites verify/ref/*.png from the run instead of comparing: use it only on the reference solution."""
import json
import math
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

from harness import *
from image import fmt_rgb

ROOT_DIR = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT_DIR / "tools" / "assets"))
import mkassets      # noqa: E402
import img2tim       # noqa: E402
import formats       # noqa: E402
import layout        # noqa: E402
import shpgen        # noqa: E402
import tim as T      # noqa: E402

REF_DIR = Path(__file__).resolve().parent / "ref"
W, H, CX, CY = 320, 240, 160, 120
BG = (16, 16, 32)
MAX_FRAMES = 700
TYPES = formats.PRIM_TYPES
HASH_N = 16                              # dHash of 16 x 16 cells: 256 bits
HASH_MAX = 14                            # tolerance, in bits of 256; measured on the solution: other OT slot shifts (2, 4, 5) 0-2, a 1-pixel shift of the picture <= 4, 3 pixels <= 12; a different pose >= 32

config(
    title="A Real Model Format: .SHP",
    build="cmake", exe="game.exe", sym="", elf="game.elf", iso="hoverline.cue",
    break_at=None, max_frames=MAX_FRAMES, timeout=90,
)

STATE = ["main", "shp_info", "shp", "store", "load_status", "tpk_status", "shp_status", "render_mode", "angle_x", "angle_y", "angle_z", "spin_step",
         "cam_z", "proj_h", "mtx", "screen_xy", "screen_z", "prims_submitted", "frame_no", "frame_done", "ot_frames",
         "shp_parse", "shp_decode", "shp_record_size", "shp_packet_size", "shp_fill"]

# Alternate texture placement (texture-id order hull_a, hull_b, wing): other pages, one 8 bpp texture. Registered in layout.SETS so that the
# generator's own manifest code computes the expected TSB / CBA / UV origins.
ALT_SET = [("hull_a", 4, 704, 256, 0, 490), ("hull_b", 8, 768, 0, 0, 493), ("wing", 4, 848, 288, 32, 492)]
layout.SETS["shipalt"] = ALT_SET

STATUS = {100: "cd_init() failed (CdInit)", 1: "tpk_load failed (see tpk_status; Chapter 31's loader is given, so is the file on the disc?)",
          2: "the .SHP could not be read or parsed: see shp_status: -1 read, -2 align, -3 magic, -4 header, -5 prim list, -6 index, -7 texture, -8 store"}

# ---- references -----------------------------------------------------------------------------------------------------------------
_REF = {}


def assets(ctx):
    if "files" not in _REF:
        out = ctx.work / "refassets"
        files, manifests = mkassets.build(out, seed=1, keep_png=True)
        _REF.update(files=files, manifests=manifests, png=out / "png")
    return _REF


def alt_files(ctx):
    a = assets(ctx)
    if "alt" not in _REF:
        data = shpgen.make_ship(1).build()
        man = shpgen.shp_manifest("SHIP", data, "shipalt")
        tims = [img2tim.convert(a["png"] / (n + ".png"), bpp, x, y, cx, cy) for n, bpp, x, y, cx, cy in ALT_SET]
        _REF["alt"] = dict(shp=data, tpk=formats.build_tpk(tims), man=man, tims=tims)
    return _REF["alt"]


def main_model(ctx):
    a = assets(ctx)
    data = a["files"]["SHIP.SHP"]
    tims = formats.parse_tpk(a["files"]["SHIP.TPK"])["tims"]
    return dict(shp=data, man=a["manifests"]["SHIP.SHP"], tims=tims)


def model_for(ctx, name):
    return main_model(ctx) if name == "main" else alt_files(ctx)


# ---- the disc image ---------------------------------------------------------------------------------------------------------------
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


def disc(ctx):
    return Iso(ctx.build.build_dir / "hoverline.bin")


def alt_disc(ctx):
    """alt.bin / alt.cue next to hoverline.*: the same exe, SHIP.SHP and SHIP.TPK replaced by the alternate ship's files."""
    bdir = ctx.build.build_dir
    if (bdir / "alt.cue").exists():
        return
    xml = next(iter(sorted(bdir.glob("cd_image_*.xml"))), None)
    if xml is None:
        raise CheckFailure(expected="CMake's configured iso xml", actual="not found", hint="Use psn00bsdk_add_cd_image.")
    (bdir / "alt").mkdir(exist_ok=True)
    alt = alt_files(ctx)
    text = xml.read_text()
    for name, data in (("SHIP.SHP", alt["shp"]), ("SHIP.TPK", alt["tpk"])):
        (bdir / "alt" / name).write_bytes(data)
        text, k = re.subn(r'(<file\s+name="%s"[^>]*?source=")[^"]*(")' % re.escape(name), lambda m: m.group(1) + str(bdir / "alt" / name) + m.group(2),
                          text, flags=re.I)
        expect_eq(k, 1, f"iso.xml has one <file name=\"{name}\" source=...> entry", hint="Appendix E.2: both files live in <dir name=\"DATA\">.")
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


# ---- geometry and packets, computed from the FILE ------------------------------------------------------------------------------------
def s16(v):
    return v - 65536 if v & 0x8000 else v


def s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


def rot_matrix(ax, ay, az):
    """The SDK's RotMatrix: R = Rx * Ry * Rz (angles in 4096ths of a turn), verified against the solution's matrix."""
    ax, ay, az = [2 * math.pi * a / 4096 for a in (ax, ay, az)]

    def rx(a): c, s = math.cos(a), math.sin(a); return [[1, 0, 0], [0, c, -s], [0, s, c]]
    def ry(a): c, s = math.cos(a), math.sin(a); return [[c, 0, s], [0, 1, 0], [-s, 0, c]]
    def rz(a): c, s = math.cos(a), math.sin(a); return [[c, -s, 0], [s, c, 0], [0, 0, 1]]
    def mul(A, B): return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return mul(rx(ax), mul(ry(ay), rz(az)))


def project_float(verts, sc, cam_z, proj_h):
    R = rot_matrix(sc["ax"], sc["ay"], sc["az"])
    out = []
    for x, y, z in verts:
        X = R[0][0] * x + R[0][1] * y + R[0][2] * z
        Y = R[1][0] * x + R[1][1] * y + R[1][2] * z
        Z = R[2][0] * x + R[2][1] * y + R[2][2] * z + cam_z
        out.append((CX + X * proj_h / Z, CY + Y * proj_h / Z, Z))
    return out


def unpack_xy(w):
    return (s16(w & 0xFFFF), s16(w >> 16))


def nclip(a, b, c):
    return a[0] * b[1] + b[0] * c[1] + c[0] * a[1] - a[0] * c[1] - b[0] * a[1] - c[0] * b[1]


def ot_slot(szs):
    """AVSZ3 / AVSZ4 with the SDK's default ZSF3 = 0x155, ZSF4 = 0x100, then >> 3 and the table clamp (0..63)."""
    otz = (0x155 * sum(szs)) >> 12 if len(szs) == 3 else (0x100 * sum(szs)) >> 12
    return min(max(otz >> 3, 0), 63)


KINDS = {0x20: "F3", 0x28: "F4", 0x30: "G3", 0x38: "G4", 0x24: "FT3", 0x2C: "FT4", 0x34: "GT3", 0x3C: "GT4"}
PACKET_WORDS = {"F3": 4, "F4": 5, "G3": 6, "G4": 8, "FT3": 7, "FT4": 9, "GT3": 9, "GT4": 12}


def decode_packet(words):
    """The words after the OT tag -> dict(kind, semi, rgb[], xy[], uv[], clut, tpage), or None for an unknown code."""
    code = words[0] >> 24
    kind = KINDS.get(code & ~2)
    if kind is None:
        return None
    n = 3 if kind.endswith("3") else 4
    gour = kind[0] == "G"
    tex = "T" in kind
    stride = 1 + 1 + (1 if tex else 0) + 0
    rgb, xy, uv = [], [], []
    clut = tpage = None
    pos = 0
    for k in range(n):
        if k == 0 or gour:
            w = words[pos]
            rgb.append((w & 255, (w >> 8) & 255, (w >> 16) & 255))
            pos += 1
        xy.append(unpack_xy(words[pos]))
        pos += 1
        if tex:
            w = words[pos]
            uv.append((w & 255, (w >> 8) & 255))
            if k == 0:
                clut = w >> 16
            if k == 1:
                tpage = w >> 16
            pos += 1
    return dict(kind=kind, semi=bool(code & 2), rgb=rgb, xy=xy, uv=uv, clut=clut, tpage=tpage)


def packets_of(prims):
    """The flat probe list (slot, len, words...)* -> list of (slot, dict) in drawing order; unknown packets raise."""
    out, i = [], 0
    while i < len(prims):
        slot, ln = prims[i], prims[i + 1]
        words = prims[i + 2:i + 2 + ln]
        i += 2 + ln
        pk = decode_packet(words)
        if pk is None:
            raise CheckFailure(expected="only F3 F4 G3 G4 FT3 FT4 GT3 GT4 packets in the table", actual=f"a packet with command byte 0x{words[0] >> 24:02X} in slot {slot}",
                               hint="Every primitive is one of the eight polygon types (command bytes 0x20 0x24 0x28 0x2C 0x30 0x34 0x38 0x3C, +2 when semi-transparent).")
        expect_eq(ln, PACKET_WORDS[pk["kind"]], f"tag length of a {pk['kind']} packet in slot {slot}", hint="setPolyXX sets it; it is the packet's size in words minus the tag.")
        out.append((slot, pk))
    return out


def expected_packets(model, sc, textures):
    """Expected (slot, packet) list for a scenario, computed from the file and the program's own screen_xy / screen_z (see README 6)."""
    shp = formats.parse_shp(model["shp"])
    sxy = [unpack_xy(w) for w in sc["sxy"]]
    sz = sc["sz"]
    man_tex = model["man"]["textures"]
    out = []
    for p in shp["prims"]:
        v = p["v"]
        area = nclip(sxy[v[0]], sxy[v[1]], sxy[v[2]])
        if area == 0 or (area < 0 and not p["flags"] & formats.F_DOUBLE_SIDED):
            continue
        textured_prim = "T" in p["type"]
        use_tex = textured_prim and sc["mode"] == 1 and textures
        kind = p["type"] if (not textured_prim or use_tex) else p["type"].replace("T", "")
        n = len(v)
        pk = dict(kind=kind, semi=bool(p["flags"] & formats.F_SEMI_TRANS), xy=[sxy[i] for i in v], rgb=[tuple(c) for c in p["colors"]],
                  uv=[], clut=None, tpage=None)
        if use_tex:
            t = man_tex[p["tex"]]
            pk["uv"] = [(u + t["uv_origin"][0], vv + t["uv_origin"][1]) for u, vv in p["uv"]]
            pk["clut"], pk["tpage"] = t["cba"], t["tsb_abr0"]
        out.append((ot_slot([sz[i] for i in v]), pk))
    return out


def pkey(pk):
    return (pk["kind"], pk["semi"], tuple(pk["xy"]), tuple(pk["rgb"]), tuple(pk["uv"]), pk["clut"], pk["tpage"])


def describe_pk(pk):
    s = f"{pk['kind']}{' semi' if pk['semi'] else ''} xy={pk['xy']} rgb={pk['rgb']}"
    if pk["uv"]:
        s += f" uv={pk['uv']} clut=0x{pk['clut']:04X} tpage=0x{pk['tpage']:04X}"
    return s


# ---- observing a run ------------------------------------------------------------------------------------------------------------------
def observe(ctx, name):
    """(RunResult, info, scenarios) of the main run or the alt run."""
    if name == "main":
        r = ctx.result
    else:
        alt_disc(ctx)
        r = ctx.run("alt", iso="alt.cue")
    r.require_finished()
    exc = r.record("exception")
    if exc:
        raise CheckFailure(expected="no CPU exception", actual=f"CPU exception {exc['code']} at pc 0x{exc['epc']:08X}, address 0x{exc['badvaddr']:08X}",
                           hint="A load through a bad or misaligned pointer? An index past the vertex list or screen_xy[]? A record walked with the wrong stride?")
    info = r.record("info")
    expect_true(info is not None, "the program reaches its frame loop", f"status {r.data.get('status')}",
                hint="Does it hang in cd_load_file, tpk_load or shp_parse? Booting + loading takes about 400 emulated frames.")
    expect_eq(info["load_status"], 0, f"{name}: load_status",
              hint=STATUS.get(info["load_status"], "") + f" (tpk_status {info['tpk_status']}, shp_status {info['shp_status']}). The screen is red when loading fails.")
    sc = r.record("scenarios") or []
    expect_eq(len(sc), 6, f"{name}: the six posed frames were recorded", hint="The loop must call frame_done() once per frame and keep running.")
    return r, info, sc


# ---- static checks ----------------------------------------------------------------------------------------------------------------------
@static_check("the state symbols and the API exist", hint="Keep every global and function the starter declares (shp_info, render_mode, angle_x/y/z, spin_step, ... shp_fill).")
def _(ctx):
    ctx.require_symbols(*STATE)


@static_check("the disc image has SYSTEM.CNF, HOVER.EXE, \\DATA\\SHIP.SHP and \\DATA\\SHIP.TPK",
              hint="iso.xml: both files inside <dir name=\"DATA\">, sources assets/SHIP.SHP and assets/SHIP.TPK (written by the CMake rule that runs mkassets.py).")
def _(ctx):
    iso = disc(ctx)
    m = main_model(ctx)
    for p in ("\\SYSTEM.CNF", "\\HOVER.EXE", "\\DATA\\SHIP.SHP", "\\DATA\\SHIP.TPK"):
        expect_true(p in iso.files, f"{p} on the disc", f"found {sorted(iso.files)}")
    expect_eq(iso.read("\\DATA\\SHIP.SHP"), m["shp"], "SHIP.SHP on the disc is the generator's file")
    expect_eq(iso.read("\\HOVER.EXE"), (ctx.build.build_dir / "game.exe").read_bytes(), "HOVER.EXE on the disc is the built game.exe")


@static_check("the model is not inside the program", hint="The .SHP must be read from the disc at run time, not compiled into the EXE.")
def _(ctx):
    exe = (ctx.build.build_dir / "game.exe").read_bytes()
    shp = formats.parse_shp(main_model(ctx)["shp"])
    blob = b"".join(struct.pack("<hhhh", *v, 0) for v in shp["vertices"][:12])
    expect_true(blob not in exe, "the first vertices of SHIP.SHP are not in game.exe", "found their bytes in the executable")


# ---- dynamic checks on a run --------------------------------------------------------------------------------------------------------------
def check_info(ctx, name):
    r, info, sc = observe(ctx, name)
    m = model_for(ctx, name)
    man = m["man"]
    w = info["shp_info"]
    got = dict(zip(TYPES, w[:8]))
    expect_eq(got, man["prim_counts"], f"{name}: shp_info.prim_counts (F3 F4 G3 G4 FT3 FT4 GT3 GT4) vs the generator manifest", fmt="dec",
              hint="Count the records by TYPE TAG while you validate them. A parser that treats every record as one type, or walks with the wrong stride, gets this wrong.")
    expect_eq(w[8:12], [man["vertex_count"], man["normal_count"], man["prim_count"], man["texture_count"]],
              f"{name}: shp_info vertex/normal/prim/texture counts", fmt="dec", hint="From the header (offsets 0x18..0x1E of E.8.1).")
    nm = bytes(b for word in w[12:16] for b in struct.pack("<I", word)).split(b"\0")[0].decode("ascii")
    expect_eq(nm, man["name"], f"{name}: shp_info.name")
    store = info["store"]
    expect_eq(store[0], len(m["tims"]), f"{name}: store.count", hint="Chapter 31's loader is given: is SHIP.TPK what tpk_load read?")
    for i, data in enumerate(m["tims"]):
        t = T.parse(data)
        u0, v0 = T.uv_origin(t.image.x, t.image.y, t.bpp)
        mult = {4: 4, 8: 2, 16: 1}[t.bpp]
        want = [T.tsb(t.image.x, t.image.y, t.bpp), T.cba(t.clut.x, t.clut.y) if t.clut else 0, u0, v0, t.image.w * mult, t.image.h]
        expect_eq(store[1 + 6 * i:7 + 6 * i], want, f"{name}: store.tex[{i}] [tpage, clut, u, v, w, h]", fmt="dec")
    return r, info, sc


@check("boots from the disc; shp_info (counts per primitive type, vertices, normals, name) equals the generator manifest; the store holds the TPK's textures",
       hint="shp_parse: validate, then count the records of each type while walking them; main.c copies the counts into shp_info.")
def _(ctx):
    check_info(ctx, "main")


@check("alt disc (another ship: other counts; the same textures at other VRAM places, one 8 bpp): shp_info and the store follow the files",
       hint="Hard-coded counts or texture placements cannot pass: everything comes from the file and the TIMs.")
def _(ctx):
    check_info(ctx, "alt")


def check_geometry(ctx, name):
    r, info, sc = observe(ctx, name)
    m = model_for(ctx, name)
    shp = formats.parse_shp(m["shp"])
    for s in sc:
        tag = f"{name} pose {s['index']}"
        expect_eq(s["load_status"], 0, f"{tag}: load_status")
        raw = struct.pack("<8I", *s["mtx"])
        mt = struct.unpack("<9h", raw[:18])
        R = rot_matrix(s["ax"], s["ay"], s["az"])
        err = max(abs(R[i][j] * 4096 - mt[3 * i + j]) for i in range(3) for j in range(3))
        expect_true(err <= 24, f"{tag}: mtx's rotation is RotMatrix({s['ax']}, {s['ay']}, {s['az']})", f"largest element off by {err:.1f} (of 4096)",
                    hint="upload_matrix: RotMatrix(&rot, &mtx) from angle_x/y/z (int32, 4096 = one turn), then TransMatrix(&mtx, &(0, 0, cam_z)).")
        expect_eq(list(struct.unpack("<3i", raw[20:32])), [0, 0, info["cam_z"]], f"{tag}: mtx.t is (0, 0, cam_z)", hint="TransMatrix(&mtx, &pos) with pos = {0, 0, cam_z}.")
        fl = project_float(shp["vertices"], s, info["cam_z"], info["proj_h"])
        expect_eq(len(s["sxy"]), len(fl), f"{tag}: screen_xy entries recorded")
        for i, (f, w, z) in enumerate(zip(fl, s["sxy"], s["sz"])):
            x, y = unpack_xy(w)
            expect_true(abs(x - f[0]) <= 2.5 and abs(y - f[1]) <= 2.5, f"{tag}: screen_xy[{i}] is the projection of vertex {i}", f"({x}, {y}) vs float ({f[0]:.1f}, {f[1]:.1f})",
                        hint="gte_ldv0(&shp.verts[i]); gte_rtps(); gte_stsxy(&screen_xy[i]); gte_stsz(&screen_z[i]) for every vertex of the file.")
            expect_true(abs(z - f[2]) <= 4, f"{tag}: screen_z[{i}] is the vertex's depth", f"{z} vs {f[2]:.1f}")


@check("pose and projection: mtx is RotMatrix(angles) + (0, 0, cam_z); screen_xy / screen_z are the vertices projected (3 poses x 2 modes)",
       hint="Chapter 29's transform_vertices, over the .SHP's vertex list (8-byte SVECTORs, ready for gte_ldv0).")
def _(ctx):
    check_geometry(ctx, "main")


def check_packets(ctx, name):
    r, info, sc = observe(ctx, name)
    m = model_for(ctx, name)
    for s in sc:
        tag = f"{name} pose {s['index']} ({'textured' if s['mode'] else 'flat fallback'})"
        got = packets_of(s["prims"])
        exp = expected_packets(m, s, True)
        expect_eq(s["prims_submitted"], len(got), f"{tag}: prims_submitted equals the packets in the table", hint="Count a primitive when (and only when) you link it.")
        gk, ek = {}, {}
        for slot, pk in got:
            gk.setdefault(pkey(pk), []).append(slot)
        for slot, pk in exp:
            ek.setdefault(pkey(pk), []).append(slot)
        missing = [k for k in ek if k not in gk]
        extra = [k for k in gk if k not in ek]
        if missing or extra:
            by = lambda keys, src: describe_pk(next(pk for _, pk in src if pkey(pk) == keys[0]))
            what = []
            if missing:
                what.append(f"{len(missing)} expected packet(s) missing, e.g. {by(missing, exp)}")
            if extra:
                what.append(f"{len(extra)} unexpected packet(s), e.g. {by(extra, got)}")
            raise CheckFailure(expected=f"{tag}: {len(exp)} packets: every front-facing (or double-sided) record, built as its own type"
                               + (" (flat fallback: FT -> F, GT -> G, colors as stored)" if not s["mode"] else " with tpage/clut/UVs from the store"),
                               actual="; ".join(what),
                               hint="Culling: skip area <= 0 unless double-sided (then only area == 0). Kind: the record's type (textured only in render_mode 1). "
                                    "UV: texture-local + the texture's (u, v). tpage/clut: from store.tex[tex]. Colors as stored. Quads: v0 v1 v2 v3 as stored.")
        for k, slots in ek.items():
            expect_eq(sorted(gk[k]), sorted(slots), f"{tag}: ordering-table slot of {k[0]} at {k[2][0]}", fmt="dec",
                      hint="slot = OTZ >> 3, OTZ from AVSZ3 (triangles) or AVSZ4 (quads) of the vertices' screen_z (README 7.2).")
    return sc


@check("the packets: for every record the right primitive type, colors, absolute UVs, tpage/clut, semi-transparency bit, culling and OT slot, in both modes at 3 poses",
       hint="Per record: shp_decode, NCLIP cull, AVSZ slot, shp_packet_size + shp_fill with the store's Tex (mode 1) or NULL (mode 0).")
def _(ctx):
    check_packets(ctx, "main")


@check("alt disc: the same, for the other ship and the other texture placement (TSB/CBA/UV origins computed from the TIMs)",
       hint="A hard-coded tpage or clut fails here: the alternate textures sit in other pages (one is 8 bpp), so every tpage/clut/UV differs.")
def _(ctx):
    check_packets(ctx, "alt")


@check("textured primitives carry the manifest's TSB and CBA (and UV origin): every textured packet of the textured runs, main and alt",
       hint="TSB = (x/64) | ((y/256) << 4) | (tp << 7); CBA = (clut_x/16) | (clut_y << 6): tex_from_tim of Chapter 30 already computed them into store.tex[].")
def _(ctx):
    n = 0
    for name in ("main", "alt"):
        r, info, sc = observe(ctx, name)
        man = model_for(ctx, name)["man"]
        want = {(t["tsb"], t["cba"]) for t in man["textured_prims"]}
        for s in sc:
            if s["mode"] != 1:
                continue
            for _, pk in packets_of(s["prims"]):
                if pk["tpage"] is not None:
                    n += 1
                    expect_true((pk["tpage"], pk["clut"]) in want, f"{name}: a {pk['kind']} packet's (tpage, clut) is one the manifest lists",
                                f"(0x{pk['tpage']:04X}, 0x{pk['clut']:04X}) not in {[(hex(a), hex(b)) for a, b in sorted(want)]}",
                                hint="Swapped TSB and CBA? tpage and clut taken from the wrong texture?")
    expect_true(n > 10, "textured packets were seen", f"{n}")


# ---- the picture -------------------------------------------------------------------------------------------------------------------------
def shot(r, s):
    return r.screenshot("s%d" % s["index"])


def inside(pt, poly):
    """Strictly inside a convex polygon given as a vertex loop, margin 1 pixel (integer cross products)."""
    sign = 0
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        c = (b[0] - a[0]) * (pt[1] - a[1]) - (b[1] - a[1]) * (pt[0] - a[0])
        ln = math.hypot(b[0] - a[0], b[1] - a[1]) or 1
        if abs(c) / ln < 1.5:
            return None                        # too close to an edge: undecided
        if sign == 0:
            sign = 1 if c > 0 else -1
        elif (c > 0) != (sign > 0):
            return False
    return True


def loop(pk):
    xy = pk["xy"]
    return xy if len(xy) == 3 else [xy[0], xy[1], xy[3], xy[2]]


def area_abs(pk):
    pts = loop(pk)
    return abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))) / 2


def close(a, b, tol):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def texels_near(tims, idx, lu, lv, r=2):
    """The opaque texels of texture idx within r texels of local (lu, lv): the rasterizer's exact pick is one of them."""
    w, h, px = T.decode_rgba(T.parse(tims[idx]))
    out = []
    for dv in range(-r, r + 1):
        for du in range(-r, r + 1):
            x, y = int(lu) + du, int(lv) + dv
            if 0 <= x < w and 0 <= y < h and px[y * w + x][3]:
                out.append(px[y * w + x][:3])
    return out


def sample_points(pk, later):
    """Centroid of the first triangle of a packet, when no later-drawn polygon (or edge) is near it; else None."""
    tri = pk["xy"][:3]
    c = (sum(p[0] for p in tri) / 3.0, sum(p[1] for p in tri) / 3.0)
    for other in later:
        res = inside(c, loop(other))
        if res is None or res:
            return None
    return c


def check_picture(ctx, name):
    r, info, sc = observe(ctx, name)
    m = model_for(ctx, name)
    shp = formats.parse_shp(m["shp"])
    for s in sc:
        tag = f"{name} pose {s['index']} ({'textured' if s['mode'] else 'flat'})"
        img = shot(r, s)
        expect_eq((img.width, img.height), (W, H), f"{tag}: screenshot size")
        got = packets_of(s["prims"])
        # silhouette: the bounding box of the non-background pixels against the projected vertices of the drawn polygons
        xs = [p[0] for _, pk in got for p in pk["xy"]]
        ys = [p[1] for _, pk in got for p in pk["xy"]]
        nb = [(x, y) for y in range(H) for x in range(W) if not colors_close(img.pixel(x, y), BG, 6)]
        expect_true(len(nb) > 2000, f"{tag}: the ship is on screen", f"{len(nb)} non-background pixels", hint="A blank picture: nothing drawn, or the scene is clipped away.")
        bx0, bx1 = min(p[0] for p in nb), max(p[0] for p in nb)
        by0, by1 = min(p[1] for p in nb), max(p[1] for p in nb)
        expect_true(abs(bx0 - min(xs)) <= 4 and abs(bx1 - max(xs)) <= 4 and abs(by0 - min(ys)) <= 4 and abs(by1 - max(ys)) <= 4,
                    f"{tag}: silhouette bounding box equals the projected polygons'", f"picture x {bx0}..{bx1}, y {by0}..{by1} vs projected x {min(xs)}..{max(xs)}, y {min(ys)}..{max(ys)}",
                    hint="Wrong vertices, a polygon missing, or the whole thing off-center?")
        # sample points of the top-most polygons
        ok = bad = tex_ok_here = 0
        first_bad = None
        for i, (slot, pk) in enumerate(got):
            if area_abs(pk) < 60 or pk["semi"]:
                continue
            c = sample_points(pk, [o for _, o in got[i + 1:]])
            if c is None:
                continue
            px = img.pixel(int(round(c[0])), int(round(c[1])))
            if pk["kind"] in ("F3", "F4"):
                want = pk["rgb"][0]
                tol = 20
            elif "T" not in pk["kind"]:
                want = tuple(sum(col[k] for col in pk["rgb"][:3]) // 3 for k in range(3))
                tol = 36
            else:
                # a texel: locate the texture by its tpage/clut, then sample the TIM at the average local UV
                idx = next((t["index"] for t in m["man"]["textures"] if t["tsb_abr0"] == pk["tpage"] and t["cba"] == pk["clut"]), None)
                if idx is None:
                    continue
                t = m["man"]["textures"][idx]
                lu = sum(u for u, _ in pk["uv"][:3]) / 3.0 - t["uv_origin"][0]
                lv = sum(v for _, v in pk["uv"][:3]) / 3.0 - t["uv_origin"][1]
                near = texels_near(m["tims"], idx, lu, lv)
                if not near:
                    continue
                cols = pk["rgb"][:3] if pk["kind"][0] == "G" else pk["rgb"][:1]
                mod = tuple(sum(col[k] for col in cols) / len(cols) for k in range(3))
                cands = [tuple(min(255, tx[k] * mod[k] / 128.0) for k in range(3)) for tx in near]
                want = min(cands, key=lambda c: max(abs(c[k] - px[k]) for k in range(3)))
                tol = 30
            if colors_close(px, want, tol):
                ok += 1
                tex_ok_here += "T" in pk["kind"]
            else:
                bad += 1
                first_bad = first_bad or f"{describe_pk(pk)}: picture at ({c[0]:.0f}, {c[1]:.0f}) is {fmt_rgb(px)}, expected about {fmt_rgb(want)}"
        expect_true(ok >= 4, f"{tag}: enough top-most polygons to sample", f"{ok}")
        expect_true(bad <= max(1, ok // 8), f"{tag}: sample points have the color their packet says ({ok} ok, {bad} off)", first_bad,
                    hint="The picture and the packets disagree: wrong colors written, textures not uploaded, or the CLUT wrong.")
        # a textured render must show texels: top-most textured polygons whose picture matched their texture
        if s["mode"] == 1:
            print(f"  ({tag}: {tex_ok_here} textured sample points matched)")
            expect_true(tex_ok_here >= 1, f"{tag}: at least one top-most textured polygon shows its texture", "none did (or none was visible)",
                        hint="Textured primitives drawn untextured? The CLUT not uploaded? tpage or clut wrong?")
    return r, info, sc


@check("pictures (main disc): silhouette = projected polygons; top-most polygons show their packet's color or texel (textured renders show texels)",
       hint="If the packets check passes and this fails, VRAM or the draw environment is at fault; if both fail, fix the packets first.")
def _(ctx):
    check_picture(ctx, "main")


@check("pictures (alt disc): the same for the other ship and the other texture placement",
       hint="Textures that come from the file's own TIM headers show correctly wherever they sit in VRAM.")
def _(ctx):
    check_picture(ctx, "alt")


def pil_image(path):
    from PIL import Image as PI
    im = PI.open(path).convert("RGB")
    return Image(im.width, im.height, im.tobytes())


@check("perceptual hash: the three poses in both modes are within the tolerance of the reference renders (verify/ref/*.png)",
       hint="The reference is the book's solution. A different valid draw order stays within the tolerance; a wrong pose, a missing polygon class or untextured polygons do not.")
def _(ctx):
    r, info, sc = observe(ctx, "main")
    update = os.environ.get("SHP_UPDATE_REFS")
    for s in sc:
        img = shot(r, s)
        path = REF_DIR / f"pose{(s['index'] - 1) % 3 + 1}_{'tex' if s['mode'] else 'flat'}.png"
        if update:
            REF_DIR.mkdir(exist_ok=True)
            img.save_png(path)
            continue
        expect_true(path.exists(), f"reference {path.name} exists", "missing")
        ref = pil_image(path)
        d = hamming(dhash(img, HASH_N), dhash(ref, HASH_N))
        expect_true(d <= HASH_MAX, f"{path.name}: dHash distance to the reference <= {HASH_MAX}", f"distance {d}",
                    hint="Same pose (angles written by the probe), same camera (cam_z, proj_h), same mode: is the picture really the ship?")


# ---- direct calls --------------------------------------------------------------------------------------------------------------------------
SRC, OUT, PKT, SXY, TEX, PRIMBUF = 0x80180000, 0x801E0000, 0x801E1000, 0x801E2000, 0x801E3000, 0x801E4000
GUARD, FILL = 16, 0xA5
SHP_FMT = "<17sx4H2x4I6h8H"                   # struct Shp as the compiler lays it out (72 bytes)
PRIM_FMT = "<BBH4HHH8B16B"                    # struct ShpPrim (40 bytes)
NV = {t: (3 if t.endswith("3") else 4) for t in TYPES}


def le(fmt, *a):
    return struct.pack(fmt, *a)


def patch(b, off, fmt, *vals):
    b = bytearray(b)
    struct.pack_into(fmt, b, off, *vals)
    return bytes(b)


def rec_offsets(data):
    """Byte offsets of every record of a good .SHP."""
    poff = struct.unpack_from("<I", data, 0x28)[0]
    n = struct.unpack_from("<H", data, 0x1C)[0]
    offs, pos = [], poff
    for _ in range(n):
        offs.append(pos)
        pos += formats.PRIM_SIZE[TYPES[data[pos]]]
    return offs


def shp_cases(ctx):
    a = assets(ctx)
    good = a["files"]["SHIP.SHP"]
    alt = alt_files(ctx)["shp"]
    cases = []
    R = formats.parse_shp(good)
    offs = rec_offsets(good)
    poff = struct.unpack_from("<I", good, 0x28)[0]
    first = {t: next(i for i, p in enumerate(R["prims"]) if p["type"] == t) for t in TYPES}
    nv, nn, npr = len(R["vertices"]), len(R["normals"]), len(R["prims"])

    def parse(name, blob, size=None, want=0, addr=SRC, kind="parse_bad", ref=None):
        size = len(blob) if size is None else size
        cases.append(dict(name="shp_parse: " + name, fn="shp_parse", args=[addr, size, OUT, 0], tag=kind, want=want, ref=ref, blob=blob,
                          writes=[[addr, blob], [OUT, bytes([FILL]) * 80]], reads=[[OUT, 72]]))

    for nm, blob in (("the shipped SHIP.SHP", good), ("the alternate ship", alt), ("PYLON.SHP", a["files"]["PYLON.SHP"]),
                     ("ARCH.SHP (no textures)", a["files"]["ARCH.SHP"]), ("TOWER.SHP", a["files"]["TOWER.SHP"])):
        parse("good: " + nm, blob, kind="parse_ok", ref=blob)
    # alignment, magic
    parse("misaligned image (address + 2)", good, want=-2, addr=SRC + 2)
    parse("3 bytes long", good[:3], want=-3)
    parse("bad magic (SHP2)", good.replace(b"SHP1", b"SHP2", 1), want=-3)
    parse("magic only, 4 bytes", good[:4], want=-4)
    parse("0x3C bytes: shorter than the header", good[:0x3C], want=-4)
    # header lies
    parse("file_size field one more than the file", patch(good, 4, "<I", len(good) + 1), want=-4)
    parse("size argument larger than file_size (trailing bytes)", good + bytes(4), want=-4)
    parse("vertex_count 0", patch(good, 0x18, "<H", 0), want=-4)
    parse("vertex_count 65535 (offsets no longer add up)", patch(good, 0x18, "<H", 65535), want=-4)
    parse("vertex_count one too high", patch(good, 0x18, "<H", nv + 1), want=-4)
    parse("normal_count one too low", patch(good, 0x1A, "<H", nn - 1), want=-4)
    parse("prim_count 0", patch(good, 0x1C, "<H", 0), want=-4)
    parse("texture_count 256", patch(good, 0x1E, "<H", 256), want=-4)
    parse("vertices_offset 0x44", patch(good, 0x20, "<I", 0x44), want=-4)
    parse("normals_offset off by 8", patch(good, 0x24, "<I", struct.unpack_from("<I", good, 0x24)[0] + 8), want=-4)
    parse("prims_offset off by 4", patch(good, 0x28, "<I", poff + 4), want=-4)
    parse("prims_size one too large", patch(good, 0x2C, "<I", len(good) - poff + 1), want=-4)
    parse("prims_size 0xFFFFFFF0 (prims_offset + prims_size wraps in 32 bits)", patch(good, 0x2C, "<I", 0xFFFFFFF0), want=-4)
    big = formats.build_shp("BIG", [(i, i, i) for i in range(257)], [(0, -4096, 0)], [dict(type="F3", flags=0, v=(0, 1, 2), n=0, colors=[(1, 2, 3)])])
    parse("257 vertices: more than the program's arrays hold", big, want=-4)
    none = formats.build_shp("NONE", [(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, -4096, 0)], [])
    parse("no primitives", none, want=-4)
    # primitive list
    parse("prim_count one too high (the list ends early)", patch(good, 0x1C, "<H", npr + 1), want=-5)
    parse("prim_count one too low (a record is left over)", patch(good, 0x1C, "<H", npr - 1), want=-5)
    parse("type tag 8 in the first record", patch(good, poff, "<B", 8), want=-5)
    parse("type tag 255 in the last record", patch(good, offs[-1], "<B", 255), want=-5)
    gt4 = offs[first["GT4"]]
    parse("a GT4 record whose size field says 40", patch(good, gt4 + 2, "<H", 40), want=-5)
    parse("a G3 record whose size field says 0", patch(good, offs[first["G3"]] + 2, "<H", 0), want=-5)
    parse("a F3 record tagged F4 (tag and size disagree)", patch(good, offs[first["F3"]], "<B", 1), want=-5)
    cut = good[:-4]
    cut = patch(patch(cut, 4, "<I", len(cut)), 0x2C, "<I", len(cut) - poff)
    parse("the last record is cut off (file_size and prims_size fixed up)", cut, want=-5)
    parse("a record that would overrun the file (last record's tag changed to GT4)", patch(good, offs[-1], "<B", 7), want=-5)
    # indices
    for t in ("F3", "F4", "GT4"):
        i = first[t]
        off = offs[i]
        parse(f"a {t} with vertex index = vertex_count", patch(good, off + 4, "<H", nv), want=-6)
        nvv = NV[t]
        parse(f"a {t} with its last vertex index = 65535", patch(good, off + 4 + 2 * (nvv - 1), "<H", 65535), want=-6)
        parse(f"a {t} with normal index = normal_count", patch(good, off + 4 + 2 * nvv, "<H", nn), want=-6)
    last = offs[-1]
    parse("the LAST record has a bad vertex index", patch(good, last + 4, "<H", 5000), want=-6)
    # textures
    for t in ("FT3", "FT4", "GT3", "GT4"):
        off = offs[first[t]]
        nvv = NV[t]
        tex_off = off + 4 + 2 * nvv + 2 + (2 if nvv == 4 else 0) + 2 * nvv
        parse(f"a {t} with texture index = texture_count (3)", patch(good, tex_off, "<H", 3), want=-7)
    parse("a vertex index error is reported before a texture error", patch(patch(good, offs[first["GT3"]] + 4, "<H", nv),
          offs[first["GT3"]] + 4 + 6 + 2 + 6, "<H", 9), want=-6)
    # shp_decode on every record
    for nm, blob in (("ship", good), ("alt", alt)):
        for i, off in enumerate(rec_offsets(blob)):
            cases.append(dict(name=f"shp_decode: {nm} record {i}", fn="shp_decode", args=[SRC + off, OUT, 0, 0], tag="decode", blob=blob, offset=off, index=i,
                              writes=[[SRC, blob], [OUT, bytes([FILL]) * (40 + GUARD)]], reads=[[OUT, 40], [OUT + 40, GUARD]]))
    for t in list(range(10)) + [255]:
        cases.append(dict(name=f"shp_record_size({t})", fn="shp_record_size", args=[t, 0, 0, 0], tag="rec_size", t=t, writes=[], reads=[]))
    for t in range(8):
        for tx in (0, 1):
            cases.append(dict(name=f"shp_packet_size({t}, {tx})", fn="shp_packet_size", args=[t, tx, 0, 0], tag="pkt_size", t=t, tx=tx, writes=[], reads=[]))
    cases.append(dict(name="shp_packet_size(8, 1)", fn="shp_packet_size", args=[8, 1, 0, 0], tag="pkt_size", t=8, tx=1, writes=[], reads=[]))
    # shp_fill: each type, with and without a texture, semi-transparency on and off, negative coordinates
    sxy_vals = [(-20, 30), (100, -7), (5, 200), (319, 239), (-300, -2)]
    sxy_bytes = b"".join(struct.pack("<I", (y << 16 & 0xFFFFFFFF) | (x & 0xFFFF)) for x, y in sxy_vals)
    tex = (0x00AA, 0x7B0C, 64, 32, 64, 32)
    for t in range(8):
        for tx in (0, 1):
            for flags in (0, 2, 3):
                if flags == 3 and t not in (1, 7):
                    continue
                if tx == 0 and flags == 3:
                    continue
                kind = TYPES[t] if tx or "T" not in TYPES[t] else TYPES[t].replace("T", "")
                psize = 4 * (PACKET_WORDS[kind] + 1)
                v = [3, 0, 2, 4][:NV[TYPES[t]]] + [0] * (4 - NV[TYPES[t]])
                uvs = [(0, 0), (63, 0), (0, 31), (63, 31)]
                rgb = [(200, 20, 30), (40, 210, 50), (60, 70, 220), (250, 240, 10)]
                pb = struct.pack(PRIM_FMT, t, flags, formats.PRIM_SIZE[TYPES[t]], *v, 7, 1, *[c for uv in uvs for c in uv],
                                 *[c for col in rgb for c in (*col, 0)])
                cases.append(dict(name=f"shp_fill: {TYPES[t]}{' with a texture' if tx else ' without a texture'}{', semi-transparent' if flags & 2 else ''}",
                                  fn="shp_fill", args=[PKT, PRIMBUF, SXY, TEX if tx else 0], tag="fill", t=t, tx=tx, flags=flags, v=v, uvs=uvs, rgb=rgb, tex=tex,
                                  writes=[[PKT - GUARD, bytes([FILL]) * (64 + 2 * GUARD)], [PRIMBUF, pb], [SXY, sxy_bytes], [TEX, struct.pack("<6H", *tex)]],
                                  reads=[[PKT - GUARD, GUARD], [PKT, psize], [PKT + psize, GUARD]]))
    return cases, sxy_vals


def direct_run(ctx):
    if "direct" in _REF:
        return _REF["direct"]
    cases, sxy = shp_cases(ctx)
    wire = [dict(name=c["name"], fn=c["fn"], args=c["args"], writes=c.get("writes", []), reads=c.get("reads", [])) for c in cases]
    gen = ctx.work / "probe_direct_gen.lua"
    gen.write_text("CASES = " + lua_val(wire) + "\ndofile(" + json.dumps(str(ctx.chapter_dir / "verify" / "probe_direct.lua")) + ")\n")
    r = ctx.run("direct", probe=gen, max_frames=900)
    r.require_finished()
    exc = r.record("exception")
    if exc:
        raise CheckFailure(expected="no CPU exception in a direct call", actual=f"exception {exc['code']} in {exc.get('fn')} ({exc.get('name')}) at pc "
                           f"0x{exc['epc']:08X}, address 0x{exc['badvaddr']:08X}",
                           hint="Reading past the end of the file? A cast to a wider type on a misaligned address (read fields byte by byte)? Writing outside the packet?")
    recs = r.record("cases")
    expect_true(recs and len(recs) == len(cases), "all direct calls completed", f"{len(recs or [])} of {len(cases)} (status {r.data.get('status')})",
                hint="A call that never returns: a loop that does not advance on a damaged record?")
    _REF["direct"] = (cases, recs, sxy)
    return cases, recs, sxy


def parse_struct(rec):
    return struct.unpack(SHP_FMT, bytes.fromhex(rec["reads"][0]))


@check("shp_parse: the shipped files parse and the Shp struct matches the reference parser (name, counts, pointers into the image, bbox, counts per type)",
       hint="Fill every Shp field: pointers INTO the file image (vertices at +0x40, normals, first record), bbox from the header, counts[] by type tag.")
def _(ctx):
    cases, recs, _ = direct_run(ctx)
    n = 0
    for c, rec in zip(cases, recs):
        if c["tag"] != "parse_ok":
            continue
        n += 1
        expect_eq(s32(rec["v0"]), 0, f"{c['name']}: returns SHP_OK", fmt="dec")
        d = formats.parse_shp(c["ref"])
        name, vn, nn, pn, tn, pv, pnr, pp, psz, *rest = parse_struct(rec)
        bbox, counts = rest[:6], rest[6:]
        label = c["name"]
        expect_eq(name.split(b"\0")[0].decode(), d["name"], f"{label}: name")
        expect_eq([vn, nn, pn, tn], [len(d["vertices"]), len(d["normals"]), len(d["prims"]), d["texture_count"]], f"{label}: vertex/normal/prim/texture counts", fmt="dec")
        poff = struct.unpack_from("<I", c["ref"], 0x28)[0]
        expect_eq([pv, pnr, pp, psz], [SRC + 0x40, SRC + 0x40 + 8 * len(d["vertices"]), SRC + poff, len(c["ref"]) - poff], f"{label}: verts / normals / prims pointers and prims_size", fmt="hex",
                  hint="Pointers point into the image you were given (data + offset), not copies.")
        expect_eq(list(bbox), list(d["bbox"]), f"{label}: bbox", fmt="dec")
        want = [sum(1 for p in d["prims"] if p["type"] == t) for t in TYPES]
        expect_eq(list(counts), want, f"{label}: counts[] per type", fmt="dec", hint="Counts indexed by the type tag: F3 F4 G3 G4 FT3 FT4 GT3 GT4.")
    expect_true(n == 5, "five good files were tried", f"{n}")


@check("shp_parse: every damaged file is rejected with the documented code (ALIGN -2, MAGIC -3, HEADER -4, PRIM -5, INDEX -6, TEXTURE -7)",
       hint="The order of shp.h: alignment, magic, header consistency (including sums that cannot wrap), the record walk (tag, size, fit, count, leftovers), then indices, then texture.")
def _(ctx):
    cases, recs, _ = direct_run(ctx)
    for c, rec in zip(cases, recs):
        if c["tag"] != "parse_bad":
            continue
        expect_eq(s32(rec["v0"]), c["want"], c["name"], fmt="dec",
                  hint="Codes: -2 ALIGN, -3 MAGIC, -4 HEADER, -5 PRIM, -6 INDEX, -7 TEXTURE. Never read a byte that the checks so far have not proved is inside the file.")


def prim_dict(rec_bytes, size_ret):
    f = struct.unpack(PRIM_FMT, rec_bytes)
    return dict(type=f[0], flags=f[1], size=f[2], v=list(f[3:7]), normal=f[7], tex=f[8], uv=[(f[9 + 2 * i], f[10 + 2 * i]) for i in range(4)],
                rgb=[tuple(f[17 + 4 * i:21 + 4 * i]) for i in range(4)])


@check("shp_decode: every record of the ship and of the alternate ship decodes to the reference's fields; it returns the record size and writes nothing else",
       hint="Per type (E.8.2): indices at +4, then the normal, a pad for quads, UVs and the texture index for textured types, then the colors: 1 for F/FT, one per vertex for G/GT.")
def _(ctx):
    cases, recs, _ = direct_run(ctx)
    for c, rec in zip(cases, recs):
        if c["tag"] != "decode":
            continue
        d = formats.parse_shp(c["blob"])["prims"][c["index"]]
        t = d["type"]
        nvv = NV[t]
        got = prim_dict(bytes.fromhex(rec["reads"][0]), rec["v0"])
        label = c["name"]
        expect_eq(rec["v0"], formats.PRIM_SIZE[t], f"{label}: returns the record's size", fmt="dec")
        expect_eq((got["type"], got["flags"], got["size"]), (TYPES.index(t), d["flags"], formats.PRIM_SIZE[t]), f"{label}: type, flags, size", fmt="dec")
        expect_eq(got["v"][:nvv], list(d["v"]), f"{label} ({t}): vertex indices", fmt="dec")
        expect_eq(got["normal"], d["n"], f"{label} ({t}): normal index", fmt="dec")
        if "uv" in d:
            expect_eq(got["uv"][:nvv], [tuple(x) for x in d["uv"]], f"{label} ({t}): texture-local UVs", fmt="dec")
            expect_eq(got["tex"], d["tex"], f"{label} ({t}): texture index", fmt="dec")
        cols = [tuple(x) + (0,) for x in d["colors"]]
        expect_eq(got["rgb"][:len(cols)], cols, f"{label} ({t}): colors (r, g, b, 0)", fmt="dec")
        expect_eq(bytes.fromhex(rec["reads"][1]), bytes([FILL]) * GUARD, f"{label}: bytes after the 40-byte ShpPrim are untouched", hint="Write only the struct.")


@check("shp_record_size and shp_packet_size: 16 20 24 32 24 32 32 44 and 0 above 7; the GPU packet sizes of the eight types, with and without a texture",
       hint="File record sizes are NOT packet sizes: sizeof(POLY_F3) is 20, POLY_GT4 is 52. Without a texture FT3 -> F3, FT4 -> F4, GT3 -> G3, GT4 -> G4.")
def _(ctx):
    cases, recs, _ = direct_run(ctx)
    for c, rec in zip(cases, recs):
        if c["tag"] == "rec_size":
            want = formats.PRIM_SIZE[TYPES[c["t"]]] if c["t"] < 8 else 0
            expect_eq(rec["v0"], want, c["name"], fmt="dec")
        elif c["tag"] == "pkt_size":
            if c["t"] >= 8:
                want = 0
            else:
                kind = TYPES[c["t"]] if c["tx"] or "T" not in TYPES[c["t"]] else TYPES[c["t"]].replace("T", "")
                want = 4 * (PACKET_WORDS[kind] + 1)
            expect_eq(rec["v0"], want, c["name"], fmt="dec")


@check("shp_fill: all eight types, with and without a texture: command byte, tag length, colors, signed coordinates, texture-local UV + the texture's origin, tpage, clut, semi-transparency",
       hint="Per packet kind: command byte and length (setPolyXX), colors, x and y from sxy (low half x, high half y, SIGNED 16-bit), and for a texture the local UV plus the texture's origin and its tpage and clut words; the semi-transparency bit for flag bit 1.")
def _(ctx):
    cases, recs, sxy = direct_run(ctx)
    for c, rec in zip(cases, recs):
        if c["tag"] != "fill":
            continue
        t = TYPES[c["t"]]
        kind = t if c["tx"] or "T" not in t else t.replace("T", "")
        n = NV[kind]
        pad = bytes([FILL]) * GUARD
        expect_eq(bytes.fromhex(rec["reads"][0]), pad, f"{c['name']}: the {GUARD} bytes before the packet are untouched")
        expect_eq(bytes.fromhex(rec["reads"][2]), pad, f"{c['name']}: the {GUARD} bytes after the packet are untouched", hint="Write only shp_packet_size bytes.")
        raw = bytes.fromhex(rec["reads"][1])
        words = struct.unpack("<%dI" % (PACKET_WORDS[kind] + 1), raw)
        expect_eq(words[0] >> 24, PACKET_WORDS[kind], f"{c['name']}: the tag's length byte", fmt="dec", hint="setPolyXX sets it.")
        pk = decode_packet(list(words[1:]))
        expect_true(pk is not None and pk["kind"] == kind, f"{c['name']}: command byte of a {kind}", f"0x{words[1] >> 24:02X}")
        expect_eq(pk["semi"], bool(c["flags"] & 2), f"{c['name']}: semi-transparency bit")
        expect_eq(pk["xy"], [sxy[i] for i in c["v"][:n]], f"{c['name']}: vertices", fmt="dec", hint="sxy[v[k]]: x = (int16_t) low half, y = high half >> 16: negative values!")
        want_rgb = c["rgb"][:n] if kind[0] == "G" else c["rgb"][:1]
        expect_eq(pk["rgb"], want_rgb, f"{c['name']}: colors", fmt="dec")
        if "T" in kind:
            tp, cl, u0, v0, _, _ = c["tex"]
            expect_eq(pk["uv"], [(u + u0, v + v0) for u, v in c["uvs"][:n]], f"{c['name']}: UVs (local + texture origin)", fmt="dec")
            expect_eq((pk["tpage"], pk["clut"]), (tp, cl), f"{c['name']}: tpage and clut from the Tex", fmt="hex")
