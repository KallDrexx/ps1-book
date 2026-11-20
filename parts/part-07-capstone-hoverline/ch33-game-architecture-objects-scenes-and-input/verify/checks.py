"""Chapter 33 checks: Game Architecture: Objects, Scenes, and Input Events (the Hoverline skeleton).
Build: CMake + PSn00bSDK; the CMake rule runs tools/assets/mkassets.py. The emulator BOOTS THE .cue.
MAIN RUN (probe.lua): the program is driven by frame_no. The probe reads the state through the symbols (README 7.2): the scene's list walked from
`object_head`, the shape table, the texture store; it holds START for 20 frames (title -> game, edge-triggered: exactly one change), presses it once
(game -> title) and twice more (title -> game), holds UP+RIGHT+R1+R2 (Chapter 28's fly camera), then poses the camera by writing cam_eye / cam_yaw at
the end of a frame and records the next one: submitted_objects, every node's `visible` flag, prims, a screenshot. The poses are computed here from SCENE.BIN
(equality at exactly cull_radius + radius, one unit either side, the 32-bit wrap-around cases, the 32000-unit guard of the always-drawn arch, ...).
Everything the program must show is derived in Python from the generated SCENE.BIN (formats.parse_scene) and the manifests, with exact integers.
ALT RUN: a second disc: a different SCENE.BIN (the track-2 scene, shuffled, a different shape table order with a duplicate shape and another radius, other cull
radius, scaled and tilted objects): hard-coded counts, shape indices, positions or radii fail.
DIRECT CALLS (probe_direct.lua): obj_insert / obj_append / obj_remove / obj_count on caller-provided nodes in scratch RAM; cull_test with overflow cases;
scene_load on crafted bad files (documented error codes), on files that fail after validation, and on a file at the limits."""
import atexit
import json
import math
import os
import random
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
import scenegen      # noqa: E402
import tim as T      # noqa: E402

W, H, CX, CY = 320, 240, 160, 120
BG = (24, 24, 48)
DRAW_LIMIT = 32000
NEAR_Z = 128
PROJ_H = 320
EYE0 = (23883, -1500, -2500)
YAW0 = 66
BOX = ((-80000, -30000, -80000), (80000, 2000, 80000))     # the default [cam_min, cam_max]
MAX_FRAMES = 700

config(
    title="Game Architecture: Objects, Scenes, and Input Events",
    build="cmake", exe="game.exe", sym="", elf="game.elf", iso="hoverline.cue",
    break_at=None, max_frames=MAX_FRAMES, timeout=90,
)

STATE = ["main", "game_state", "state_changes", "submitted_objects", "proj_h", "store", "load_status", "tpk_status", "object_head", "object_count",
         "object_pool", "scene_shapes", "scene_shape_count", "scene_cull_radius", "scene_status", "scene_shp_status", "cam_eye", "cam_yaw", "cam_target",
         "cam_up", "cam_speed", "cam_turn", "cam_min", "cam_max", "view_mtx", "prims_submitted", "prims_dropped", "frame_no", "frame_done", "ot_frames",
         "obj_insert", "obj_append", "obj_remove", "obj_count", "cull_test", "scene_load", "scene_unload"]

STATUS = {100: "cd_init() failed (CdInit)", 1: "tpk_load failed (PROPS.TPK; Chapter 31's loader is given: is the file on the disc?)",
          2: "the scene failed: scene_status has the code (-1 read, -2 align, -3 magic, -4 header, -5 shape, -6 object, -7 shp, -8 store)",
          3: "LOGO.TIM could not be loaded (title.c is given: is the file on the disc?)"}


# ---- the book's assets and the alternate scene, built once (the cameras depend on them) ----------------------------------------------------
class Model:
    """A scene as the program should see it: the SCENE.BIN bytes plus the parsed tables."""

    def __init__(self, data, files):
        self.data = data
        d = formats.parse_scene(data)
        self.shapes, self.objects, self.cull = d["shapes"], d["objects"], d["cull_radius"]
        self.bbox = {n: formats.parse_shp(files[n])["bbox"] for n, _ in self.shapes}

    def radius(self, o):
        return (self.shapes[o["shape"]][1] * o["scale"]) >> 12

    def visible(self, o, eye):
        """THE cull rule (README 5.6), in Python's exact integers."""
        d = [o["pos"][i] - eye[i] for i in range(3)]
        if max(abs(v) for v in d) > DRAW_LIMIT:
            return False
        if o["flags"] & 1:
            return True
        return sum(v * v for v in d) <= (self.cull + self.radius(o)) ** 2


def make_alt_scene(files):
    """Track 2's scene, with a different shape table (order, a duplicate PYLON.SHP with another radius), cull radius, shuffled objects, extra scaled/tilted ones."""
    base = formats.parse_scene(scenegen.generate(files["TRACK2.TRK"]))
    remap = {0: 1, 1: 3, 2: 0}                        # pylon, arch, tower -> table [TOWER, PYLON, PYLON(900), ARCH]
    rnd = random.Random(33)
    objs = []
    for o in base["objects"]:
        sh = remap[o["shape"]]
        if sh == 1 and rnd.random() < 0.4:
            sh = 2
        objs.append(dict(shape=sh, flags=o["flags"], pos=o["pos"], rot=o["rot"], scale=4096))
    objs.append(dict(shape=1, flags=0, pos=(-3000, -100, 1500), rot=(0, 700, 0), scale=2048))       # a half-size pylon
    objs.append(dict(shape=0, flags=0, pos=(4000, 0, -2500), rot=(300, 100, 0), scale=8192))        # a double-size tilted tower
    objs.append(dict(shape=2, flags=1, pos=(-30000, 0, 30000), rot=(0, 0, 0), scale=4096))          # an always-drawn pylon, far away
    objs.append(dict(shape=3, flags=0, pos=(9000, -500, 9000), rot=(0, 2048, 0), scale=3000))
    rnd.shuffle(objs)
    shapes = [("TOWER.SHP", 1500), ("PYLON.SHP", 401), ("PYLON.SHP", 900), ("ARCH.SHP", 962)]
    return formats.build_scene(shapes, objs, 12000)


_TMP = Path(tempfile.mkdtemp(prefix="ch33ref-"))
atexit.register(shutil.rmtree, _TMP, True)
FILES, MANIFESTS = mkassets.build(_TMP / "assets", seed=1)
MAIN = Model(FILES["SCENE.BIN"], FILES)
ALT_BIN = make_alt_scene(FILES)
ALT = Model(ALT_BIN, FILES)
LOGO = T.parse(FILES["LOGO.TIM"])


def s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


def rot_y(ry, x, z):
    a = 2 * math.pi * ry / 4096
    return x * math.cos(a) + z * math.sin(a), -x * math.sin(a) + z * math.cos(a)


def make_cams(m, main):
    """The camera poses (label, (x, y, z), yaw) for a scene: ordinary views, then every boundary the rule has."""
    cams = []
    R = lambda o: m.cull + m.radius(o)
    plain = [(i, o) for i, o in enumerate(m.objects) if not o["flags"] & 1]
    always = [(i, o) for i, o in enumerate(m.objects) if o["flags"] & 1]
    if main:
        cams.append(("the start position", EYE0, YAW0))
    cams += [("middle of the world, looking +z", (0, -1500, 0), 0), ("west edge, looking +x", (-24000, -1500, 0), 1024),
             ("north, looking -x", (6000, -4000, 18000), 3072), ("south-east, looking back", (20000, -800, -12000), 3000),
             ("nothing within reach", (70000, -1500, 70000), 0)]
    # exact boundary of the largest and of the smallest culled shape, along an axis
    big = max(plain, key=lambda t: m.radius(t[1]))
    small = min(plain, key=lambda t: m.radius(t[1]))
    for tag, (i, o) in (("largest", big), ("smallest", small)):
        r = R(o)
        x, y, z = o["pos"]
        for dr, what in ((0, "exactly at"), (1, "one unit outside"), (-1, "one unit inside")):
            cams.append((f"{what} the radius of the {tag} shape (object {i}), x axis", (x + r + dr, y, z), 3072))
        cams.append((f"exactly at the radius of the {tag} shape (object {i}), z axis", (x, y, z - r), 0))
        cams.append((f"just outside the radius of the {tag} shape (object {i}), z axis", (x, y, z - r - 1), 0))
        a = round(r * 0.6)
        b = math.isqrt(r * r - a * a)
        cams.append((f"diagonal, a^2+b^2 just inside R^2 (object {i})", (x + a, y, z - b), 3300))
        cams.append((f"diagonal, a^2+b^2 just outside R^2 (object {i})", (x + a, y, z - b - 1), 3300))
    # 32-bit wrap-around: dx = 65536 squares to 2^32 = 0; (40000, 40000) sums past 2^31
    near = sorted(plain, key=lambda t: abs(t[1]["pos"][0]))[:1]
    for i, o in near:
        x, y, z = o["pos"]
        cams.append((f"dx = 65536 from object {i}: dx*dx wraps to 0 in 32 bits", (x + 65536, y, z), 3072))
        cams.append((f"dx = -65536 from object {i}", (x - 65536, y, z), 1024))
        cams.append((f"dx = dz = 40000 from object {i}: the sum passes 2^31", (x + 40000, y, z + 40000), 3072))
        cams.append((f"dx = dz = -40000 from object {i}", (x - 40000, y, z - 40000), 1024))
        cams.append((f"dx = 46341 from object {i}: dx*dx just passes 2^31", (x + 46341, y, z), 3072))
    # the always-drawn objects: drawn at 32000, not at 32001
    for i, o in always[:2]:
        x, y, z = o["pos"]
        cams.append((f"always-drawn object {i} at exactly 32000 units", (x + 32000, y, z), 3072))
        cams.append((f"always-drawn object {i} at 32001 units", (x + 32001, y, z), 3072))
        cams.append((f"always-drawn object {i} from close by", (x, y - 800, z - 2500), 0))
    # close-ups and the densest view
    rnd = random.Random(7)
    for i, o in rnd.sample(plain, 3):
        x, y, z = o["pos"]
        cams.append((f"close to object {i}, looking at it", (x - 1500, y - 600, z - 3000), 170))
    # clamp the poses into the camera's box: a pose outside would be moved by the program (and is not what this check is about)
    out = []
    for lab, e, yaw in cams:
        assert all(BOX[0][k] <= e[k] <= BOX[1][k] for k in range(3)), (lab, e)
        out.append((lab, e, yaw))
    return out


MAIN_CAMS = make_cams(MAIN, True)
ALT_CAMS = make_cams(ALT, False)


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


def params_lua(cams):
    return "PARAMS = " + lua_val({"cams": [{"x": e[0], "y": e[1], "z": e[2], "yaw": yaw} for _, e, yaw in cams]}) + "\n"


(_TMP / "params_main.lua").write_text(params_lua(MAIN_CAMS))
os.environ["CH33_PARAMS"] = str(_TMP / "params_main.lua")      # the default run's probe reads its camera list from here (the child process inherits it)


# ---- the disc image -------------------------------------------------------------------------------------------------------------------
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
    """alt.bin / alt.cue next to hoverline.*: the same exe and files, SCENE.BIN replaced by the alternate scene."""
    bdir = ctx.build.build_dir
    if (bdir / "alt.cue").exists():
        return
    xml = next(iter(sorted(bdir.glob("cd_image_*.xml"))), None)
    if xml is None:
        raise CheckFailure(expected="CMake's configured iso xml", actual="not found", hint="Use psn00bsdk_add_cd_image.")
    (bdir / "alt").mkdir(exist_ok=True)
    (bdir / "alt" / "SCENE.BIN").write_bytes(ALT_BIN)
    text, k = re.subn(r'(<file\s+name="SCENE.BIN"[^>]*?source=")[^"]*(")', lambda m: m.group(1) + str(bdir / "alt" / "SCENE.BIN") + m.group(2),
                      xml.read_text(), flags=re.I)
    expect_eq(k, 1, "iso.xml has one <file name=\"SCENE.BIN\" source=...> entry", hint="Appendix E.2: the scene lives in <dir name=\"DATA\">.")
    (bdir / "alt.xml").write_text(text)
    p = subprocess.run(["mkpsxiso", "-y", "-q", "-o", "alt.bin", "-c", "alt.cue", "alt.xml"], cwd=bdir, capture_output=True, text=True, timeout=60, env=tool_env())
    expect_eq(p.returncode, 0, "mkpsxiso builds the alternative disc", hint=(p.stdout + p.stderr)[-400:])


# ---- observing the runs ---------------------------------------------------------------------------------------------------------------------
def observe(ctx, name):
    name = "main" if name.startswith("main") else "alt"
    if name == "main":
        r = ctx.result
    else:
        alt_disc(ctx)
        gen = ctx.work / "params_alt.lua"
        gen.write_text(params_lua(ALT_CAMS) + "dofile(" + json.dumps(str(ctx.chapter_dir / "verify" / "probe.lua")) + ")\n")
        r = ctx.run("alt", iso="alt.cue", probe=gen)
    r.require_finished()
    exc = r.record("exception")
    if exc:
        raise CheckFailure(expected="no CPU exception", actual=f"CPU exception {exc['code']} at pc 0x{exc['epc']:08X}, address 0x{exc['badvaddr']:08X}",
                           hint="A load through a NULL or dangling pointer (a removed node? the end of the list?), or through a misaligned address?")
    info = r.record("info")
    expect_true(info is not None, "the program reaches its frame loop", f"status {r.data.get('status')}",
                hint="Does it hang in cd_load_file or scene_load? Booting + loading takes about 400 emulated frames.")
    return r, info


def node(w):
    """A node's twelve words -> dict."""
    return dict(next=w[0], shape=s32(w[1]), flags=s32(w[2]), pos=(s32(w[3]), s32(w[4]), s32(w[5])), rot=(s32(w[6]), s32(w[7]), s32(w[8])), scale=s32(w[9]),
                radius=s32(w[10]), visible=s32(w[11]))


def lua_words(rec):
    """Lua arrays come back as dicts with string keys '1'..'12' (plus 'addr'); make them lists."""
    if isinstance(rec, list):
        return rec
    return [rec[str(i)] for i in range(1, 13)]


def decode_nodes(info):
    return [dict(node(lua_words(n)), addr=n["addr"]) for n in info["list"]["nodes"]]


def info_words(info):
    return info


# ---- checks: the project ----------------------------------------------------------------------------------------------------------------------
@static_check("the state symbols and the given modules are linked", hint="main.c's asm block keeps the state alive; do not delete a declaration the verifier reads.")
def _(ctx):
    ctx.require_symbols(*STATE)


@static_check("the disc holds LOGO.TIM, PROPS.TPK, the three shapes and SCENE.BIN in \\DATA; the scene and the models are read at run time, not compiled in",
              hint="iso.xml lists the files of README 7.1; the CMake rule runs tools/assets/mkassets.py.")
def _(ctx):
    iso = Iso(ctx.build.build_dir / "hoverline.bin")
    for n in ("LOGO.TIM", "PROPS.TPK", "PYLON.SHP", "ARCH.SHP", "TOWER.SHP", "SCENE.BIN"):
        expect_true("\\DATA\\" + n in iso.files, f"\\DATA\\{n} is on the disc", ", ".join(sorted(iso.files)), "Add the <file> entry to iso.xml.")
        expect_eq(iso.read("\\DATA\\" + n), FILES[n], f"\\DATA\\{n} is the generated file", hint="The disc must carry the generator's bytes.")
    exe = (ctx.build.build_dir / "game.exe").read_bytes()
    for what, blob in (("the object table of SCENE.BIN", FILES["SCENE.BIN"][0x50:0x50 + 24 * 3]), ("PYLON.SHP", FILES["PYLON.SHP"][0x40:0x80])):
        expect_true(blob not in exe, f"{what} is not inside the program", "found in game.exe", "Read the file from the disc at run time.")


def check_load(ctx, name, m):
    r, info = observe(ctx, name)
    expect_eq(info["load_status"], 0, f"{name}: load_status",
              hint=STATUS.get(info["load_status"], "") + f" (tpk_status {info['tpk_status']}, scene_status {info['scene_status']}, scene_shp_status {info['scene_shp_status']}).")
    expect_eq(info["scene_status"], 0, f"{name}: scene_status", fmt="dec")
    return r, info


def check_list(ctx, name, m):
    r, info = check_load(ctx, name, m)
    expect_eq(info["object_count"], len(m.objects), f"{name}: object_count (the objects in SCENE.BIN)", fmt="dec", hint="One node per object entry.")
    expect_eq(info["list"]["cyclic"], False, f"{name}: the list ends (a NULL next)", hint="obj_append must set o->next = NULL; a cycle means a node was linked twice.")
    nodes = decode_nodes(info)
    expect_eq(len(nodes), len(m.objects), f"{name}: nodes found by walking object_head -> next -> ...", fmt="dec",
              hint="The list holds fewer/more nodes than the file has objects: obj_append/obj_insert/scene_load.")
    pool, lo, hi = info["pool"], info["pool"], info["pool"] + 48 * 128
    expect_eq(info["head"], nodes[0]["addr"], f"{name}: object_head is the first node", fmt="hex")
    seen = set()
    for i, (n, o) in enumerate(zip(nodes, m.objects)):
        label = f"{name}: node {i}"
        expect_true(lo <= n["addr"] < hi and (n["addr"] - lo) % 48 == 0, f"{label} lives in object_pool", f"0x{n['addr']:08X}",
                    "The nodes come from object_pool (no malloc): scene.h.")
        expect_true(n["addr"] not in seen, f"{label} is a distinct node", "the same node twice")
        seen.add(n["addr"])
        expect_eq(n["shape"], o["shape"], f"{label}: shape index", fmt="dec", hint="The list is in the FILE's order: node i is object entry i (append at the tail).")
        expect_eq(n["flags"], o["flags"], f"{label}: flags", fmt="dec")
        expect_eq(n["pos"], o["pos"], f"{label}: position", fmt="dec", hint="s32 x, y, z at offsets 0x10.. of the object entry (Appendix E.9).")
        expect_eq(n["rot"], o["rot"], f"{label}: rotation", fmt="dec", hint="s16 values: sign-extend them.")
        expect_eq(n["scale"], o["scale"], f"{label}: scale", fmt="dec")
        expect_eq(n["radius"], m.radius(o), f"{label}: radius = the table's radius * scale >> 12", fmt="dec",
                  hint="The radius comes from the shape TABLE entry of this object's shape index.")
        expect_eq(n["visible"], 0, f"{label}: visible is 0 before the first game frame", fmt="dec")
    expect_eq(nodes[-1]["next"], 0, f"{name}: the last node's next is NULL", fmt="hex")
    return r, info


@check("main disc: the list walked from object_head holds one node per SCENE.BIN object, in file order, with the file's fields; nodes come from object_pool",
       hint="scene_load: validate, load the shapes, then obj_append one node per entry (rotation fields are s16, position s32, radius = table radius * scale >> 12).")
def _(ctx):
    check_list(ctx, "main disc", MAIN)


def check_shapes(ctx, name, m):
    r, info = observe(ctx, name)
    expect_eq(info["shape_count"], len(m.shapes), f"{name}: scene_shape_count", fmt="dec")
    expect_eq(info["cull_radius"], m.cull, f"{name}: scene_cull_radius", fmt="dec", hint="From the file header (offset 0x14), not a constant.")
    for i, ((n, rad), got) in enumerate(zip(m.shapes, info["shapes"])):
        raw = bytes(got["name"], "latin-1") if isinstance(got["name"], str) else bytes(got["name"])
        expect_eq(raw.split(b"\0")[0].decode(), n, f"{name}: shape {i}: name", hint="scene_shapes[i].name = the table's 12 bytes, NUL-padded.")
        expect_eq(got["radius"], rad, f"{name}: shape {i}: radius", fmt="dec")
    st = info["store"]
    man = MANIFESTS["PROPS.TPK"]["textures"]
    expect_eq(st[0], len(man), f"{name}: store.count (PROPS.TPK)", fmt="dec")
    for i, t in enumerate(man):
        w = [st[1 + 6 * i + k] for k in range(6)]
        want = [t["tsb_abr0"], t["cba"], t["uv_origin"][0], t["uv_origin"][1], t["width"], t["height"]]
        expect_eq(w, want, f"{name}: store.tex[{i}] (tpage, clut, u, v, w, h)", fmt="hex", hint="Chapter 31's loader is given: is PROPS.TPK on the disc?")


@check("main disc: the shape table (names, radii), the cull radius from the header, and the texture store of PROPS.TPK",
       hint="scene_load copies the 12-byte name and the radius of every table entry, and the header's cull_radius.")
def _(ctx):
    check_shapes(ctx, "main disc", MAIN)


@check("alt disc: another SCENE.BIN (track 2's objects, shuffled, 4 shapes with a duplicate and another radius, cull radius 12000, scaled and tilted objects): list, order, fields, shapes",
       hint="Hard-coded counts, shape indices, positions, radii or the cull radius fail here: everything comes from the file.")
def _(ctx):
    check_list(ctx, "alt disc", ALT)
    check_shapes(ctx, "alt disc", ALT)


# ---- state machine ----------------------------------------------------------------------------------------------------------------------------
def snaps(r):
    return {s["name"]: s for s in (r.record("snaps") or [])}


@check("title screen: game_state is STATE_TITLE (0) at boot, nothing of the scene is drawn or culled, the logo and the gradient are on screen",
       hint="The title is title_draw() (given); game_draw must not call draw_scene() in STATE_TITLE and submitted_objects must be 0.")
def _(ctx):
    r, info = observe(ctx, "main")
    expect_eq(info["game_state"], 0, "game_state at frame 3", fmt="dec", hint="The initial state is STATE_TITLE (0).")
    sn = snaps(r)
    t = sn["title"]
    expect_eq((t["game_state"], t["state_changes"], t["submitted"], t["prims"]), (0, 0, 0, 0), "title: (game_state, state_changes, submitted_objects, prims_submitted)", fmt="dec")
    expect_eq(sum(t["visible"]), 0, "title: no node is marked visible (the scene was not culled or drawn)", fmt="dec")
    img = r.screenshot("title")
    # the backdrop: a vertical gradient (8,8,40) at the top to (96,24,96) at the bottom
    expect_pixel(img, 4, 2, (8, 8, 40), tol=14)
    expect_pixel(img, 316, 236, (96, 24, 96), tol=14)
    # the logo: opaque texels of LOGO.TIM at 1:1, top-left at (96, 56)
    w, h, px = T.decode_rgba(LOGO)
    expect_eq((w, h), (128, 64), "LOGO.TIM size", fmt="dec")
    n = bad = 0
    for v in range(1, h, 3):
        for u in range(1, w, 3):
            rr, gg, bb, a = px[v * w + u]
            if a < 255 or (rr, gg, bb) == (0, 0, 0):
                continue
            n += 1
            got = img.pixel(96 + u, 56 + v)
            # the quad's UVs run 0..127 over 128 pixels (the first to the LAST texel), so the GPU may be one texel off: accept the neighbours
            near = [px[vv * w + uu][:3] for vv in (v - 1, v) for uu in (u - 1, u)]
            if min(max(abs(got[0] - c[0]), abs(got[1] - c[1]), abs(got[2] - c[2])) for c in near) > 24:
                bad += 1
    expect_true(n > 100, "enough opaque logo texels to sample", str(n))
    expect_true(bad <= n // 50, "the logo's texels are on screen at (96, 56)", f"{bad} of {n} sampled texels differ",
                "title_draw() is given and needs LOGO.TIM in VRAM: did title_load() run, and is anything drawn over the title?")


@check("Start is edge-triggered: holding it for 20 frames changes the state exactly once (title -> game); holding it 12 frames in the game goes back to the title once; a short press returns to the game",
       hint="Use input_pressed(INPUT_START) (the frame it went down), not input_held: a held button would flip the state every frame.")
def _(ctx):
    r, info = observe(ctx, "main")
    tr = [tuple(x) for x in r.record("trace")]
    hold = [t for t in tr if t[0] <= 34]
    changes = [t[2] for t in hold]
    expect_eq(hold[0][1:], (0, 0), "before Start: (game_state, state_changes)", fmt="dec")
    expect_true(max(changes) == 1, "20 frames of Start: state_changes ends at 1", f"max {max(changes)} (rows {hold[:12]})",
                "A level-triggered test (input_held) re-fires every frame while the button is down.")
    expect_true(all(b >= a for a, b in zip(changes, changes[1:])), "state_changes never decreases", str(changes))
    expect_eq(hold[-1][1:], (1, 1), "after the hold: (game_state, state_changes)", fmt="dec", hint="Start pressed in the title: STATE_GAME.")
    hold2 = [t for t in tr if 36 <= t[0] <= 56]
    expect_true(max(t[2] for t in hold2) == 2, "12 frames of Start in the game: state_changes ends at 2", f"max {max(t[2] for t in hold2)} (rows {hold2[:14]})",
                "A level-triggered test bounces: game -> title -> game -> ... while the button stays down.")
    expect_eq(hold2[-1][1:], (0, 2), "after the second hold: (game_state, state_changes)", fmt="dec")
    sn = snaps(r)
    expect_eq((sn["game1"]["game_state"], sn["game1"]["state_changes"]), (1, 1), "snapshot game1", fmt="dec")
    expect_eq((sn["title2"]["game_state"], sn["title2"]["state_changes"], sn["title2"]["submitted"]), (0, 2, 0), "after the second hold: back to the title", fmt="dec",
              hint="In STATE_GAME a press of Start returns to STATE_TITLE (README 5.8).")
    expect_eq((sn["game2"]["game_state"], sn["game2"]["state_changes"]), (1, 3), "after a short press (2 frames): the game again", fmt="dec")
    # pictures: the game frame has the scene's background and none of the title's colours; the second title is the title again
    g, t2 = r.screenshot("game1"), r.screenshot("title2")
    expect_pixel(g, 4, 2, BG, tol=10)
    expect_pixel(g, 316, 236, BG, tol=10)
    yellow = g.count_not_matching(0, 0, W, H, (255, 224, 48), tol=16) if hasattr(g, "count_not_matching") else None
    if yellow is not None:
        expect_eq(W * H - yellow, 0, "no pixel of the title's 'press start' bar in the game frame", fmt="dec")
    expect_pixel(t2, 4, 2, (8, 8, 40), tol=14)
    expect_true(sn["game1"]["submitted"] > 0, "the game frame draws objects (submitted_objects > 0)", str(sn["game1"]["submitted"]))


@check("the fly camera still works (Chapter 28): D-pad world-relative at cam_speed, R1 lowers, R2 turns; one move per held frame",
       hint="camera_update() is given; game_update must call it every GAME frame (and not in the title).")
def _(ctx):
    r, info = observe(ctx, "main")
    rows = [tuple(x) for x in r.record("fly")]
    moves = []
    for a, b in zip(rows, rows[1:]):
        d = tuple(b[k] - a[k] for k in range(1, 5))
        if d != (0, 0, 0, 0):
            moves.append(d)
    expect_true(len(moves) >= 8, "at least 8 frames of movement while UP+RIGHT+R1+R2 are held", f"{len(moves)}")
    expect_true(len(moves) <= 12, "no movement after they were released", f"{len(moves)}")
    for d in moves:
        expect_eq(d, (200, 200, 200, 24), "per frame: (dx, dy, dz, dyaw) = (cam_speed, cam_speed, cam_speed, cam_turn)", fmt="dec",
                  hint="RIGHT +x, R1 +y (down), UP +z, R2 yaw +cam_turn.")
    expect_eq(rows[0][1:4], EYE0, "the camera starts at the book's start position", fmt="dec", hint="camera.c is given: cam_eye is its initial value.")


# ---- the cull ---------------------------------------------------------------------------------------------------------------------------------
def check_cull(ctx, name, m, cams):
    r, info = observe(ctx, name)
    sc = r.record("scenarios") or []
    expect_eq(len(sc), len(cams), f"{name}: every camera pose was recorded", fmt="dec", hint=f"status {r.data.get('status')}")
    for s, (lab, eye, yaw) in zip(sc, cams):
        expect_eq(tuple(s["eye"]), eye, f"{name}: [{lab}] cam_eye as posed", fmt="dec", hint="The probe writes cam_eye; with no pad input camera_update() leaves it (inside its box).")
        expect_eq(s["game_state"], 1, f"{name}: [{lab}] game_state", fmt="dec")
        want = [1 if m.visible(o, eye) else 0 for o in m.objects]
        got = [int(v) for v in s["visible"]]
        if got != want:
            bad = [i for i in range(min(len(got), len(want))) if got[i] != want[i]]
            i = bad[0] if bad else 0
            o = m.objects[i]
            d = [o["pos"][k] - eye[k] for k in range(3)]
            raise CheckFailure(expected=f"[{lab}] visible = {want} (object {i}: d = {d}, |d|^2 = {sum(v * v for v in d)}, (cull + radius)^2 = {(m.cull + m.radius(o)) ** 2}, "
                                        f"flags {o['flags']})",
                               actual=f"visible = {got}",
                               hint="The rule of README 5.6: any |d| > 32000 -> not drawn (even OBJ_ALWAYS_DRAW); ALWAYS_DRAW -> drawn; else dx^2+dy^2+dz^2 <= (cull_radius + object radius)^2 "
                                    "in unsigned 32-bit after the per-axis test, inclusive. Wrong at the boundary? Overflow? Radius forgotten?")
        expect_eq(s["submitted"], sum(want), f"{name}: [{lab}] submitted_objects = the number of visible objects", fmt="dec",
                  hint="Count the objects that passed cull_test this frame.")
    return r, info, sc


@check("main disc: for every camera pose submitted_objects and every node's visible flag equal the Python cull (exact integers): equality, one unit either side, 32-bit wrap-arounds, the always-drawn arch",
       hint="cull_test: d = pos - eye in s32; any |d| > 32000 -> 0; ALWAYS_DRAW -> 1; else the u32 sum of squares <= (cull_radius + radius)^2.")
def _(ctx):
    check_cull(ctx, "main disc", MAIN, MAIN_CAMS)


@check("alt disc: the same on the other scene (other cull radius, per-shape radii from the table, scaled objects, an always-drawn object far away)",
       hint="The radius used is the TABLE's radius times the object's scale >> 12; the cull radius is the file's.")
def _(ctx):
    check_cull(ctx, "alt disc", ALT, ALT_CAMS)


# ---- pictures -------------------------------------------------------------------------------------------------------------------------------
def project(eye, yaw, p):
    a = 2 * math.pi * yaw / 4096
    d = [p[i] - eye[i] for i in range(3)]
    z = d[0] * math.sin(a) + d[2] * math.cos(a)
    x = d[0] * math.cos(a) - d[2] * math.sin(a)
    if z < 1:
        return None
    return CX + x * PROJ_H / z, CY + d[1] * PROJ_H / z, z


def centre_of(m, o):
    n = m.shapes[o["shape"]][0]
    b = m.bbox[n]
    c = [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2]
    s = o["scale"] / 4096
    x, z = rot_y(o["rot"][1], c[0] * s, c[2] * s)
    return (o["pos"][0] + x, o["pos"][1] + c[1] * s, o["pos"][2] + z)


def rect_of(m, o, eye, yaw):
    """The screen rectangle of the object's bounding box (None if a corner is not in front of the camera: it may cover anything)."""
    n = m.shapes[o["shape"]][0]
    b = m.bbox[n]
    s = o["scale"] / 4096
    xs, ys = [], []
    for cx in (b[0], b[3]):
        for cy in (b[1], b[4]):
            for cz in (b[2], b[5]):
                x, z = rot_y(o["rot"][1], cx * s, cz * s)
                p = project(eye, yaw, (o["pos"][0] + x, o["pos"][1] + cy * s, o["pos"][2] + z))
                if p is None or p[2] < NEAR_Z * 2:
                    return None
                xs.append(p[0])
                ys.append(p[1])
    return min(xs), min(ys), max(xs), max(ys)


def ink(img, x, y, r):
    for yy in range(max(0, int(y) - r), min(H, int(y) + r + 1)):
        for xx in range(max(0, int(x) - r), min(W, int(x) + r + 1)):
            p = img.pixel(xx, yy)
            if max(abs(p[0] - BG[0]), abs(p[1] - BG[1]), abs(p[2] - BG[2])) > 12:
                return True
    return False


def check_pictures(ctx, name, m, cams):
    r, info = observe(ctx, name)
    sc = r.record("scenarios") or []
    solid = n_ink = n_empty = 0
    for s, (lab, eye, yaw) in zip(sc, cams):
        img = r.screenshot("s%d" % s["k"])
        vis = [m.visible(o, eye) for o in m.objects]
        if not any(vis):
            bad = img.count_not_matching(0, 0, W, H, BG, tol=10)
            expect_eq(bad, 0, f"{name}: [{lab}] nothing is visible: every pixel is the background", fmt="dec",
                      hint="A culled object must leave no trace on screen.")
            n_empty += 1
            continue
        rects = []
        any_unbounded = False
        for o, v in zip(m.objects, vis):
            if v:
                rc = rect_of(m, o, eye, yaw)
                if rc is None:
                    any_unbounded = True
                else:
                    rects.append(rc)
        for i, (o, v) in enumerate(zip(m.objects, vis)):
            if m.shapes[o["shape"]][0] == "ARCH.SHP" or o["rot"][0] or o["rot"][2]:
                continue                                   # a hollow arch has no solid centre; tilted objects are not modelled here
            p = project(eye, yaw, centre_of(m, o))
            if p is None or p[2] < NEAR_Z * 10 or not (16 <= p[0] <= W - 16 and 16 <= p[1] <= H - 16):
                continue
            rc = rect_of(m, o, eye, yaw)
            if rc is None or rc[3] - rc[1] < 12 or rc[2] - rc[0] < 2.5:
                continue                                   # too thin or too small to be sure that a rasteriser fills a pixel
            if v:
                n_ink += 1
                expect_true(ink(img, p[0], p[1], 3), f"{name}: [{lab}] object {i} (visible) has ink at its projected centre ({p[0]:.0f}, {p[1]:.0f})", "background only",
                            "It passed the cull: is it drawn with the right matrix (camera-relative translation, rotation, scale)?")
            elif not any_unbounded and not any(rc[0] - 8 <= p[0] <= rc[2] + 8 and rc[1] - 8 <= p[1] <= rc[3] + 8 for rc in rects):
                solid += 1
                expect_true(not ink(img, p[0], p[1], 3), f"{name}: [{lab}] object {i} (culled) leaves no ink at its projected centre ({p[0]:.0f}, {p[1]:.0f})",
                            "something is drawn there", "A culled object must not be drawn.")
    expect_true(n_ink >= 8, f"{name}: enough visible objects were checked for ink", str(n_ink))
    expect_true(solid >= 1 or name == "alt disc", f"{name}: at least one culled object was checked for absence of ink", str(solid))
    expect_true(n_empty >= 2, f"{name}: at least two poses see nothing", str(n_empty))
    return r


@check("pictures (main disc): visible objects have ink where their centre projects (camera-relative placement, rotation); culled ones leave none; empty views are all background",
       hint="Compose view rotation * object rotation (and scale); the object's position, relative to the eye, becomes the translation (README 5.7).")
def _(ctx):
    check_pictures(ctx, "main disc", MAIN, MAIN_CAMS)


@check("pictures (alt disc): the same for the other scene (scaled objects, other radii)",
       hint="The scale (4.12) goes into the object's matrix with ScaleMatrix.")
def _(ctx):
    check_pictures(ctx, "alt disc", ALT, ALT_CAMS)


@check("the primitive buffer is never overrun: the guard bytes behind both ot_frames are intact, and prims_dropped is non-negative in every pose",
       hint="render_shp (given) stops at ot_alloc == NULL; do not write packets yourself.")
def _(ctx):
    r, info = observe(ctx, "main")
    for g in r.record("guards") or []:
        expect_eq(list(g), [0xA5] * 16, "guard bytes after a primitive buffer", fmt="hex")
    for s in r.record("scenarios") or []:
        expect_true(s["dropped"] >= 0 and s["prims"] >= 0, "counters", f"{s['prims']} {s['dropped']}")


# ---- direct calls -----------------------------------------------------------------------------------------------------------------------------
SRC, POOL, HEAD, VEC, DOUT, OBJ = 0x80180000, 0x801E0000, 0x801E1000, 0x801E2000, 0x801E2100, 0x801E2200
FILL = 0xA5
GUARD = 16
_REF = {}


def lua_cases(cases):
    return [dict(name=c["name"], fn=c["fn"], args=c["args"], writes=c.get("writes", []), reads=c.get("reads", [])) for c in cases]


def node_bytes(i, nxt):
    """Node i of a scratch pool: next, shape = 100 + i, flags = i, x/y/z, rotation, scale, radius, visible: all distinctive."""
    w = [nxt, 100 + i, i, 1000 * i + 1, 1000 * i + 2, 1000 * i + 3, 7 + i, 8 + i, 9 + i, 4096 + i, 500 + i, 0]
    return struct.pack("<12I", *w)


def list_cases():
    cases = []

    def case(name, fn, order, arg_node=None, a0_null=False, expect=None):
        """order: node indices in the list at the call; arg_node: the node passed (None: NULL)."""
        mem = bytearray()
        nxt = {}
        for k, i in enumerate(order):
            nxt[i] = POOL + 48 * order[k + 1] if k + 1 < len(order) else 0
        for i in range(6):
            mem += node_bytes(i, nxt.get(i, 0xDEAD0000 + i))
        head = POOL + 48 * order[0] if order else 0
        a1 = POOL + 48 * arg_node if arg_node is not None else 0
        cases.append(dict(name=f"{fn}: {name}", fn=fn, args=[0 if a0_null else HEAD, a1, 0, 0], tag="list", op=fn, order=list(order), arg=arg_node, a0_null=a0_null,
                          writes=[[HEAD, struct.pack("<I", head)], [POOL, bytes(mem)]], reads=[[HEAD, 4], [POOL, 6 * 48]], mem0=bytes(mem), head0=head))

    case("into an empty list", "obj_insert", [], 3)
    case("before [1, 2]", "obj_insert", [1, 2], 0)
    case("before a single node", "obj_insert", [4], 5)
    case("onto an empty list", "obj_append", [], 2)
    case("after [1, 2, 3]", "obj_append", [1, 2, 3], 0)
    case("after a single node", "obj_append", [1], 5)
    case("after four nodes (the new node's old next was garbage)", "obj_append", [0, 1, 2, 3], 4)
    for pos in range(5):
        case(f"node at position {pos} of [0, 1, 2, 3, 4]", "obj_remove", [0, 1, 2, 3, 4], [0, 1, 2, 3, 4][pos])
    case("the only node", "obj_remove", [3], 3)
    case("the head of two", "obj_remove", [2, 5], 2)
    case("the tail of two", "obj_remove", [2, 5], 5)
    case("a node that is not in the list (returns 0, nothing changes)", "obj_remove", [0, 1, 2], 4)
    case("from an empty list", "obj_remove", [], 0)
    case("a NULL node", "obj_remove", [0, 1], None)
    case("with a NULL head pointer", "obj_remove", [0, 1], 0, a0_null=True)
    for order in ([], [4], [0, 1, 2, 3, 4, 5]):
        nxt = {i: (POOL + 48 * order[k + 1] if k + 1 < len(order) else 0) for k, i in enumerate(order)}
        mem = b"".join(node_bytes(i, nxt.get(i, 0xDEAD0000 + i)) for i in range(6))
        cases.append(dict(name=f"obj_count: {len(order)} nodes", fn="obj_count", args=[POOL + 48 * order[0] if order else 0, 0, 0, 0], tag="count", n=len(order),
                          writes=[[POOL, mem]], reads=[]))
    return cases


def expect_list_state(c, rec):
    """Python's model of the call, compared with the memory and the return value."""
    order = list(c["order"])
    mem = {i: list(struct.unpack_from("<12I", c["mem0"], 48 * i)) for i in range(6)}
    nxt = {i: mem[i][0] for i in range(6)}
    ret = 0
    if c["op"] == "obj_insert":
        nxt[c["arg"]] = POOL + 48 * order[0] if order else 0
        order.insert(0, c["arg"])
    elif c["op"] == "obj_append":
        nxt[c["arg"]] = 0
        if order:
            nxt[order[-1]] = POOL + 48 * c["arg"]
        order.append(c["arg"])
    else:
        a = c["arg"]
        if not c["a0_null"] and a is not None and a in order:
            ret = 1
            k = order.index(a)
            if k > 0:
                nxt[order[k - 1]] = nxt[a]
            nxt[a] = 0
            order.remove(a)
    head = POOL + 48 * order[0] if order else 0
    for i in range(6):
        mem[i][0] = nxt[i]
    want_mem = b"".join(struct.pack("<12I", *mem[i]) for i in range(6))
    got_head = struct.unpack("<I", bytes.fromhex(rec["reads"][0]))[0]
    got_mem = bytes.fromhex(rec["reads"][1])
    label = c["name"]
    if c["op"] == "obj_remove":
        expect_eq(rec["v0"], ret, f"{label}: return value", fmt="dec", hint="1 if the node was in the list (and is now unlinked), else 0.")
    expect_eq(got_head, head, f"{label}: the head pointer afterwards", fmt="hex", hint=f"list {c['order']}, node {c['arg']}: the head pointer must be updated when the first node changes.")
    if got_mem != want_mem:
        for i in range(6):
            g, w = struct.unpack_from("<12I", got_mem, 48 * i), struct.unpack_from("<12I", want_mem, 48 * i)
            if g != w:
                expect_eq(list(g), list(w), f"{label}: node {i}", fmt="hex", hint="Only `next` fields may change: o->next of the new/removed node, and the previous node's next.")


@check("list operations on caller-provided nodes: obj_insert (head), obj_append (tail), obj_remove by pointer (head, middle, tail, only, absent, NULL), obj_count",
       hint="No hidden allocation: the nodes are the caller's. obj_remove returns 1 and clears the removed node's next, 0 and changes nothing when the node is not in the list.")
def _(ctx):
    cases, recs = direct(ctx)["list"]
    for c, rec in zip(cases, recs):
        if c["tag"] == "list":
            expect_list_state(c, rec)
        else:
            expect_eq(s32(rec["v0"]), c["n"], c["name"], fmt="dec")


def expected_cull(o, eye, cull):
    d = [o["pos"][i] - eye[i] for i in range(3)]
    if max(abs(v) for v in d) > DRAW_LIMIT:
        return 0, d
    if o["flags"] & 1:
        return 1, d
    return int(sum(v * v for v in d) <= (cull + o["radius"]) ** 2), d


def cull_cases():
    rnd = random.Random(1234)
    tests = []

    def add(label, pos, eye, cull, radius, flags=0):
        tests.append((label, dict(pos=pos, flags=flags, radius=radius), eye, cull))

    for r, c in ((401, 20000), (1500, 20000), (12000, 20000), (0, 20000), (3000, 17000)):
        R = r + c
        add(f"dx = R exactly (radius {r}, cull {c})", (5000 + R, 100, -200), (5000, 100, -200), c, r)
        add(f"dx = R + 1", (5000 + R + 1, 100, -200), (5000, 100, -200), c, r)
        add(f"dz = -R exactly", (5000, 100, -200 - R), (5000, 100, -200), c, r)
        add(f"dy = R + 1", (5000, 100 + R + 1, -200), (5000, 100, -200), c, r)
        a = round(R * 0.6)
        b = math.isqrt(R * R - a * a)
        add(f"diagonal just inside", (a, 0, b), (0, 0, 0), c, r)
        add(f"diagonal just outside", (a, 0, b + 1), (0, 0, 0), c, r)
    add("dx = 65536: dx*dx is 2^32 = 0 in 32 bits", (65536, 0, 0), (0, 0, 0), 20000, 401)
    add("dx = -65536", (-65536, 5, 5), (0, 0, 0), 20000, 401)
    add("dx = 65536 + 100", (65636, 0, 0), (0, 0, 0), 20000, 401)
    add("dy = 65536", (0, 65536, 0), (0, 0, 0), 20000, 1500)
    add("dx = dz = 40000: the sum passes 2^31", (40000, 0, 40000), (0, 0, 0), 20000, 401)
    add("dx = dy = dz = 40000", (40000, 40000, 40000), (0, 0, 0), 20000, 401)
    add("dx = 46341: dx*dx just passes 2^31", (46341, 0, 0), (0, 0, 0), 20000, 401)
    add("dx = 1,000,000 and dy = -1,000,000 (squares of about 2^40)", (1000000, -1000000, 1000000), (-1000000, 1000000, -1000000), 20000, 401)
    add("dx = 1,999,999", (999999, 0, 0), (-1000000, 0, 0), 20000, 401)
    add("negative coordinates, inside", (-30000, -500, -12000), (-31000, -400, -11000), 20000, 401)
    for lab, d, fl in (("32000", 32000, 1), ("32001", 32001, 1), ("-32000", -32000, 1), ("-32001", -32001, 1)):
        add(f"always-drawn at dx = {lab}", (d, 0, 0), (0, 0, 0), 20000, 962, fl)
    add("always-drawn at dz = 32000, dy = 32001", (0, 32001, 32000), (0, 0, 0), 20000, 962, 1)
    add("always-drawn at 0", (0, 0, 0), (0, 0, 0), 20000, 962, 1)
    add("always-drawn, every axis 32000", (32000, -32000, 32000), (0, 0, 0), 20000, 962, 1)
    add("not always-drawn, d = (32000, 0, 0), R = 32000 (cull 20000, radius 12000)", (32000, 0, 0), (0, 0, 0), 20000, 12000)
    add("not always-drawn, d = (0, 0, 0)", (7, 8, 9), (7, 8, 9), 20000, 0)
    for k in range(60):
        c = rnd.choice((5000, 12000, 20000))
        r = rnd.choice((0, 400, 1500, 6000, 12000))
        R = c + r
        eye = (rnd.randint(-1000000, 1000000), rnd.randint(-1000000, 1000000), rnd.randint(-1000000, 1000000))
        if k % 3 == 0:
            pos = tuple(e + rnd.randint(-R - 40, R + 40) for e in eye)       # near the sphere
        elif k % 3 == 1:
            pos = tuple(e + rnd.choice((-1, 1)) * rnd.randint(30000, 70000) for e in eye)   # the wrap-around band
        else:
            pos = tuple(rnd.randint(-1000000, 1000000) for _ in range(3))
        add(f"random {k}", pos, eye, c, r, rnd.choice((0, 0, 0, 1)))
    out = []
    for lab, o, eye, cull in tests:
        want, d = expected_cull(o, eye, cull)
        ob = struct.pack("<12I", 0, 0, o["flags"], *[v & 0xFFFFFFFF for v in o["pos"]], 0, 0, 0, 4096, o["radius"] & 0xFFFFFFFF, 0)
        eb = struct.pack("<4I", *[v & 0xFFFFFFFF for v in eye], 0)
        out.append(dict(name=f"cull_test: {lab}", fn="cull_test", args=[OBJ, VEC, cull, DOUT], tag="cull", want=want, d=d, o=o, eye=eye, cull=cull,
                        writes=[[OBJ, ob], [VEC, eb], [DOUT - GUARD, bytes([FILL]) * (16 + 2 * GUARD)]], reads=[[DOUT - GUARD, GUARD], [DOUT, 12], [DOUT + 16, GUARD]]))
    return out


@check("cull_test(o, eye, cull_radius, &d): d = pos - eye always filled; |d| > 32000 on any axis -> 0 (even always-drawn); always-drawn -> 1; else the squared sum <= (cull + radius)^2, with no 32-bit overflow",
       hint="Test each axis against 32000 first: then every square is below 2^30 and the u32 sum below 2^32. Without it, dx = 65536 squares to 0 and the object is 'at distance 0'.")
def _(ctx):
    cases, recs = direct(ctx)["cull"]
    for c, rec in zip(cases, recs):
        got = (s32(rec["v0"]) != 0)
        label = c["name"]
        pad = bytes([FILL]) * GUARD
        expect_eq(bytes.fromhex(rec["reads"][0]), pad, f"{label}: the bytes before *d are untouched")
        expect_eq(bytes.fromhex(rec["reads"][2]), pad, f"{label}: the bytes after *d are untouched", hint="VECTOR is 16 bytes: write vx, vy, vz only.")
        dd = list(struct.unpack("<3i", bytes.fromhex(rec["reads"][1])))
        expect_eq(dd, c["d"], f"{label}: *d = pos - eye", fmt="dec", hint="Fill d even when the object is culled; s32 subtraction.")
        expect_eq(got, bool(c["want"]), f"{label}: result (pos {c['o']['pos']}, eye {c['eye']}, cull {c['cull']}, radius {c['o']['radius']}, flags {c['o']['flags']})",
                  fmt="dec", hint="Guard on each axis first (32000), then ALWAYS_DRAW, then u32 sum <= (cull + radius)^2 (inclusive).")


def scene_cases(ctx):
    good = FILES["SCENE.BIN"]
    ns, no = struct.unpack_from("<HH", good, 8)
    cases = []
    sym = ctx.symbols
    state_reads = [[sym["object_count"], 4], [sym["object_head"], 4], [sym["scene_shape_count"], 4], [sym["scene_shp_status"], 4]]

    def patch(blob, off, fmt, val):
        b = bytearray(blob)
        struct.pack_into(fmt, b, off, val)
        return bytes(b)

    def case(name, blob, want, addr=SRC, kind="bad", extra=(), **kw):
        cases.append(dict(name=f"scene_load: {name}", fn="scene_load", args=[addr, len(blob), 0, 0], tag="scene", kind=kind, want=want, blob=blob,
                          writes=[[SRC, blob]] + [list(e) for e in extra], reads=list(state_reads), **kw))

    shp_off, obj_off = 0x20, 0x20 + 16 * ns

    # validation: nothing is touched, the loaded scene (the book's, 35 objects) stays
    case("misaligned image (address + 2)", good, -2, addr=SRC + 2)
    case("3 bytes long", good[:3], -3)
    case("bad magic (SCN2)", good.replace(b"SCN1", b"SCN2", 1), -3)
    case("magic only, 4 bytes", good[:4], -4)
    case("0x1C bytes: shorter than the header", good[:0x1C], -4)
    case("file_size one more than the file", patch(good, 4, "<I", len(good) + 1), -4)
    case("size argument larger than file_size (trailing bytes)", good + bytes(4), -4)
    case("shape_count 0", patch(good, 8, "<H", 0), -4)
    case("shape_count 17", patch(good, 8, "<H", 17), -4)
    case("shape_count 65535", patch(good, 8, "<H", 65535), -4)
    case("object_count 0", patch(good, 10, "<H", 0), -4)
    case("object_count 129", patch(good, 10, "<H", 129), -4)
    case("object_count 65535 (24 * count wraps a 16-bit multiply)", patch(good, 10, "<H", 65535), -4)
    case("object_count one too low (bytes left over)", patch(good, 10, "<H", no - 1), -4)
    case("shapes_offset 0x24", patch(good, 12, "<I", 0x24), -4)
    case("objects_offset off by 16", patch(good, 16, "<I", obj_off + 16), -4)
    case("objects_offset 0xFFFFFFF0 (the sum wraps in 32 bits)", patch(good, 16, "<I", 0xFFFFFFF0), -4)
    cut = good[:-24]
    case("the last object cut off (file_size fixed up, count not)", patch(cut, 4, "<I", len(cut)), -4)
    case("cull_radius 0", patch(good, 20, "<I", 0), -4)
    case("cull_radius 20001", patch(good, 20, "<I", 20001), -4)
    case("cull_radius 0xFFFFFFFF", patch(good, 20, "<I", 0xFFFFFFFF), -4)
    case("an empty shape name", patch(good, shp_off, "<B", 0), -5)
    case("a 12-character shape name with no NUL", good[:shp_off] + b"ABCDEFGHIJ.S" + good[shp_off + 12:], -5)
    case("a lower-case letter in a name", patch(good, shp_off + 1, "<B", ord("y")), -5)
    case("a backslash in a name", patch(good, shp_off + 2, "<B", ord("\\")), -5)
    case("a semicolon in the second shape's name", patch(good, shp_off + 16 + 4, "<B", ord(";")), -5)
    case("shape radius 0", patch(good, shp_off + 12, "<I", 0), -5)
    case("shape radius 6001", patch(good, shp_off + 12, "<I", 6001), -5)
    case("the last shape's radius 0xFFFFFFFF", patch(good, shp_off + 16 * (ns - 1) + 12, "<I", 0xFFFFFFFF), -5)
    case("object 0: shape = shape_count", patch(good, obj_off, "<H", ns), -6)
    case("the last object: shape 0xFFFF", patch(good, obj_off + 24 * (no - 1), "<H", 0xFFFF), -6)
    case("object 3: flags 2", patch(good, obj_off + 24 * 3 + 2, "<H", 2), -6)
    case("object 3: flags 0x8001", patch(good, obj_off + 24 * 3 + 2, "<H", 0x8001), -6)
    case("object 1: scale 0", patch(good, obj_off + 24 + 22, "<H", 0), -6)
    case("object 1: scale 8193", patch(good, obj_off + 24 + 22, "<H", 8193), -6)
    case("object 1: scale 0xFFFF", patch(good, obj_off + 24 + 22, "<H", 0xFFFF), -6)
    case("object 2: x = 1,000,001", patch(good, obj_off + 48 + 4, "<i", 1000001), -6)
    case("object 2: y = -1,000,001", patch(good, obj_off + 48 + 8, "<i", -1000001), -6)
    case("object 2: z = INT_MAX", patch(good, obj_off + 48 + 12, "<i", 2147483647), -6)
    case("object 2: z = INT_MIN", patch(good, obj_off + 48 + 12, "<i", -2147483648), -6)
    case("error priority: a bad cull_radius and a bad shape name -> HEADER first", patch(patch(good, 20, "<I", 0), shp_off, "<B", 0), -4)
    case("error priority: a bad shape radius and a bad object -> SHAPE first", patch(patch(good, shp_off + 12, "<I", 0), obj_off, "<H", 99), -5)
    case("error priority: object 5 flags and object 2 scale -> object 2 (the walk goes in order)",
         patch(patch(good, obj_off + 24 * 5 + 2, "<H", 4), obj_off + 48 + 22, "<H", 0), -6)

    # failures after the validation: the old scene is discarded, the new one is empty
    def one(shapes, objs, cull=20000):
        return formats.build_scene(shapes, objs, cull)

    ob = lambda shape=0, **kw: dict(shape=shape, flags=0, pos=(0, 0, 0), rot=(0, 0, 0), scale=4096, **kw)
    case("a shape that is not on the disc (NOPE.SHP): READ", one([("NOPE.SHP", 100)], [ob()]), -1, kind="empty")
    case("the second of two shapes is not on the disc: READ, and the first is released", one([("PYLON.SHP", 401), ("NOPE.SHP", 100)], [ob(), ob(1)]), -1, kind="empty")
    case("a 'shape' that is SCENE.BIN: SHP (scene_shp_status -3, no SHP1 magic)", one([("SCENE.BIN", 100)], [ob()]), -7, kind="empty", shp=-3)
    case("a table entry named LOGO.TIM: SHP", one([("LOGO.TIM", 100)], [ob()]), -7, kind="empty", shp=-3)
    tower = one([("TOWER.SHP", 1500)], [ob()])
    case("TOWER.SHP needs 2 textures but store.count is 1: STORE", tower, -8, kind="empty", extra=[(sym["store"], struct.pack("<i", 1))])
    # a file at every limit, and a scene that replaces the loaded one
    lim = one([("PYLON.SHP", 6000), ("TOWER.SHP", 1), ("ARCH.SHP", 962)] + [("PYLON.SHP", 10)] * 13,
              [dict(shape=1, flags=1, pos=(1000000, -1000000, 1000000), rot=(1, -2, 3), scale=8192),
               dict(shape=0, flags=0, pos=(-1000000, 1000000, -1000000), rot=(-4096, 4095, 0), scale=1),
               dict(shape=15, flags=0, pos=(0, 0, 0), rot=(0, 0, 0), scale=4096)] + [ob(2)] * 125, cull=20000)
    case("a scene at every limit (16 shapes, 128 objects, radius 6000, scale 1 and 8192, coordinates +-1,000,000, cull 20000): loads", lim, 0, kind="limit",
         extra=[(sym["store"], struct.pack("<i", len(MANIFESTS["PROPS.TPK"]["textures"])))])
    return cases


def direct(ctx):
    if "direct" in _REF:
        return _REF["direct"]
    lst, cull, scene = list_cases(), cull_cases(), scene_cases(ctx)
    allc = lst + cull + scene
    gen = ctx.work / "probe_direct_gen.lua"
    gen.write_text("CASES = " + lua_val(lua_cases(allc)) + "\ndofile(" + json.dumps(str(ctx.chapter_dir / "verify" / "probe_direct.lua")) + ")\n")
    r = ctx.run("direct", probe=gen, max_frames=900)
    r.require_finished()
    exc = r.record("exception")
    if exc:
        raise CheckFailure(expected="no CPU exception in a direct call", actual=f"exception {exc['code']} in {exc.get('fn')} ({exc.get('name')}) at pc "
                           f"0x{exc['epc']:08X}, address 0x{exc['badvaddr']:08X}",
                           hint="A NULL head or node dereferenced? Reading past the end of the file? A cast to a wider type on a misaligned address (read fields byte by byte)?")
    recs = r.record("cases")
    expect_true(recs and len(recs) == len(allc), "all direct calls completed", f"{len(recs or [])} of {len(allc)} (status {r.data.get('status')})",
                hint="A call that never returns: a loop that does not advance? obj_remove walking a cycle?")
    _REF["direct"] = dict(list=(lst, recs[:len(lst)]), cull=(cull, recs[len(lst):len(lst) + len(cull)]), scene=(scene, recs[len(lst) + len(cull):]))
    return _REF["direct"]


@check("scene_load rejects every damaged SCENE.BIN with the documented code and leaves the loaded scene alone (ALIGN -2, MAGIC -3, HEADER -4, SHAPE -5, OBJECT -6)",
       hint="Validate in the order of scene.h before touching any state: alignment, magic, header (counts, offsets, exact size, cull radius), the shape table, then the objects in order.")
def _(ctx):
    cases, recs = direct(ctx)["scene"]
    for c, rec in zip(cases, recs):
        if c["kind"] != "bad":
            continue
        expect_eq(s32(rec["v0"]), c["want"], c["name"], fmt="dec",
                  hint="Codes: -2 ALIGN, -3 MAGIC, -4 HEADER, -5 SHAPE, -6 OBJECT. Compare sizes without overflow: counts are u16 and bounded first, offsets are u32.")
        cnt, head = [struct.unpack("<i", bytes.fromhex(x))[0] for x in rec["reads"][:2]]
        expect_eq(cnt, len(MAIN.objects), f"{c['name']}: the loaded scene is untouched (object_count)", fmt="dec", hint="A rejected file must change nothing.")


@check("scene_load: failures after the validation (a missing shape file, a shape that is not a .SHP, too few textures) return -1 / -7 / -8 and leave an EMPTY scene; a scene at every limit loads",
       hint="After validation: scene_unload() the old scene, load the shapes; on any failure scene_unload() again (object_head NULL, object_count 0, no leaked buffers).")
def _(ctx):
    cases, recs = direct(ctx)["scene"]
    sym = ctx.symbols
    for c, rec in zip(cases, recs):
        if c["kind"] == "bad":
            continue
        expect_eq(s32(rec["v0"]), c["want"], c["name"], fmt="dec", hint="-1 READ, -7 SHP (scene_shp_status has shp_parse's code), -8 STORE.")
        cnt, head, shapes, shp = [struct.unpack("<i", bytes.fromhex(x))[0] for x in rec["reads"][:4]]
        if "shp" in c:
            expect_eq(shp, c["shp"], f"{c['name']}: scene_shp_status", fmt="dec", hint="scene_shp_status = the code shp_parse returned.")
        if c["kind"] == "empty":
            expect_eq((cnt, head, shapes), (0, 0, 0), f"{c['name']}: (object_count, object_head, scene_shape_count) afterwards", fmt="dec",
                      hint="A failed load leaves the scene empty.")
        else:
            d = formats.parse_scene(c["blob"])
            expect_eq((cnt, shapes), (len(d["objects"]), len(d["shapes"])), f"{c['name']}: (object_count, scene_shape_count)", fmt="dec")
            expect_true(head != 0, "object_head is set", "NULL")
