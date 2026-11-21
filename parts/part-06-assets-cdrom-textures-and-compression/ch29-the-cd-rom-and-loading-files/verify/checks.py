"""Chapter 29 checks: The CD-ROM and Loading Files ("Ship from Disc").
Build: CMake + PSn00bSDK, which also generates MODEL.BIN (tools/assets/shpgen.py --model-bin) and builds hoverline.bin/.cue
with mkpsxiso. The emulator BOOTS THE .cue: no EXE is side-loaded, so SYSTEM.CNF, HOVER.EXE and \\DATA\\MODEL.BIN must be right.
STATIC: the state symbols exist; the disc image (parsed here with a small ISO9660 reader) holds SYSTEM.CNF (BOOT line), HOVER.EXE
(= the built exe) and DATA/MODEL.BIN (= the generator's bytes, sha256 from the manifest); the EXE does not contain the model's
vertex or face table (the model must come from the disc).
DYNAMIC (probe.lua, boots hoverline.cue, 500 frames): no CPU exception, load_status 0; CdSearchFile/CdRead were entered and the
CD controller's registers written; the buffer cd_load_file returned holds the disc file's bytes; model_info equals MODEL.BIN.json
(counts and first/last vertex); every frame the matrix is a rotation about the model's origin at (0, 0, cam_z), the angles advance
by rot_step; the picture's silhouette is the hull of the projected vertices and every front face shows its color at its center;
the polygons found by walking the ordering table are exactly the front faces (triangles as POLY_F3, quads as POLY_F4).
A second disc (a pyramid: 5 vertices, 4 triangles and 1 quad) is built here with the same exe and must show up the same way:
a program that hard-codes the ship, its counts or its file size fails.
DIRECT CALLS (probe_direct.lua): cd_load_file for SYSTEM.CNF, HOVER.EXE and \\DATA\\MODEL.BIN (size = the directory entry's, the bytes
= the file's, the buffer at least ceil(size/2048) sectors, 4-byte aligned), with a NULL size pointer, and for names that do not
exist (NULL, size 0, no sector read); model_parse on crafted images (counts are big-endian, 255 vertices, bad magic, V = 0 or 256,
short or long images, an enormous face count, a face index out of range, a misaligned pointer; *m untouched on failure)."""
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
import formats       # noqa: E402
import shpgen        # noqa: E402

W, H = 320, 240
CX, CY = W // 2, H // 2
BG = (16, 16, 32)
MAX_FRAMES = 500
SHOT_FRAMES = (12, 70)
AREA_MARGIN = 250                 # |NCLIP| below this: nearly edge-on, not judged
MIN_FACE_AREA = 500               # a face must be this large (NCLIP units) for its center color to be checked
BBOX_TOL = 5

config(
    title="The CD-ROM and Loading Files",
    build="cmake", exe="game.exe", sym="", elf="game.elf", iso="hoverline.cue",
    break_at=None, max_frames=MAX_FRAMES, timeout=90,
)

STATE = ["main", "cd_load_file", "model_parse", "model_info", "model", "model_buf", "model_size", "load_status", "rot",
         "rot_step", "cam_z", "proj_h", "mtx", "prims_submitted", "frame_no", "frame_done", "screen_xy", "screen_z"]


# ---- references ---------------------------------------------------------------------------------------------------------------
def ship_bytes():
    return shpgen.make_model_bin()


def pyramid_bytes():
    """An alternative MODEL.BIN: 5 vertices, 4 triangles and a quad, made with the generator's own mesh helper."""
    c0 = (0, -10, 0)
    apex, b = (0, -170, 0), [(-130, 90, -130), (130, 90, -130), (-130, 90, 130), (130, 90, 130)]
    m = shpgen.Mesh("ALT")
    for p in [apex] + b:
        m._v(p)
    out = []
    cols = [(230, 60, 60), (60, 200, 80), (70, 110, 240), (240, 210, 50), (200, 70, 220)]
    for pts, col in [([apex, b[0], b[1]], cols[0]), ([apex, b[1], b[3]], cols[1]), ([apex, b[3], b[2]], cols[2]),
                     ([apex, b[2], b[0]], cols[3]), ([b[0], b[1], b[2], b[3]], cols[4])]:
        before = len(m.prims)
        m.add("F3" if len(pts) == 3 else "F4", pts, [(0, 0, 0)], inside=c0)
        out.append((tuple(m.prims[before]["v"]), col))
    return formats.build_model_bin(m.verts, out)


def expected_info(data):
    d = formats.parse_model_bin(data)
    v = d["verts"]
    return [len(v), len(d["faces"]), *v[0], *v[-1]]


def project(verts, row):
    """Float projection of model vertices through the matrix the program recorded (m: rows, then t)."""
    m = [[row[4 + 3 * i + j] / 4096.0 for j in range(3)] for i in range(3)]
    t = row[13:16]
    pts = []
    for v in verts:
        x, y, z = (sum(m[i][j] * v[j] for j in range(3)) + t[i] for i in range(3))
        pts.append((CX + x * 256 / z, CY + y * 256 / z, z))
    return pts


def nclip(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])


def ch8(c5):
    return (c5 << 3) | (c5 >> 2)


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


# ---- static checks --------------------------------------------------------------------------------------------------------------
@static_check("the state symbols exist", hint="Keep the functions and globals the starter declares (cd_load_file, model_parse, model_info ...).")
def _(ctx):
    ctx.require_symbols(*STATE)


@static_check("the disc image has SYSTEM.CNF, HOVER.EXE and DATA\\MODEL.BIN",
              hint="Check iso.xml: the three <file> entries, 8.3 upper-case names, MODEL.BIN inside <dir name=\"DATA\">.")
def _(ctx):
    iso = disc(ctx)
    for p in ("\\SYSTEM.CNF", "\\HOVER.EXE", "\\DATA\\MODEL.BIN"):
        expect_true(p in iso.files, f"{p} on the disc", f"found {sorted(iso.files)}")
    cnf = iso.read("\\SYSTEM.CNF").decode("ascii", "replace")
    expect_true(re.search(r"^BOOT\s*=\s*cdrom:\\?HOVER\.EXE;1\s*$", cnf, re.M | re.I), "SYSTEM.CNF has BOOT=cdrom:\\HOVER.EXE;1", repr(cnf),
                hint="Appendix E.2: BOOT=cdrom:\\HOVER.EXE;1")
    expect_eq(iso.read("\\HOVER.EXE"), (ctx.build.build_dir / "game.exe").read_bytes(), "HOVER.EXE on the disc is the built game.exe",
              hint="iso.xml's source for HOVER.EXE must be game.exe.")
    model = ship_bytes()
    expect_eq(hashlib.sha256(iso.read("\\DATA\\MODEL.BIN")).hexdigest(), hashlib.sha256(model).hexdigest(),
              "MODEL.BIN on the disc is what shpgen.py --model-bin makes",
              hint="The CMake rule generates build/assets/MODEL.BIN; iso.xml must point at it.")


@static_check("the model is not inside the program",
              hint="MODEL.BIN's vertices and faces must be read from the disc at run time, not compiled into the EXE.")
def _(ctx):
    exe = (ctx.build.build_dir / "game.exe").read_bytes()
    for name, data in (("ship", ship_bytes()), ("pyramid", pyramid_bytes())):
        v = struct.unpack(">I", data[4:8])[0]
        for what, chunk in (("vertex table", data[8:8 + 8 * v]), ("face table", data[12 + 8 * v:])):
            expect_true(chunk not in exe, f"the {name}'s {what} is not in game.exe", "found its bytes in the executable")


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


# ---- dynamic checks: the main run -----------------------------------------------------------------------------------------------
STATUS = {1: "cd_init() failed (CdInit)", 2: "cd_load_file() returned NULL for \\DATA\\MODEL.BIN;1",
          3: "model_parse() rejected the file (the counts are big-endian: Appendix E.7)"}


def observe(ctx, name):
    """(RunResult, rows) of the main run ('main') or the pyramid disc ('alt'); fails with a precise message when it never got going."""
    if name == "main":
        r = ctx.result
    else:
        r = ctx.run("alt", iso="alt.cue")
    r.require_finished()
    exc = r.record("exception")
    if exc:
        raise CheckFailure(expected="no CPU exception", actual=f"CPU exception {exc['code']} at pc 0x{exc['epc']:08X}, address 0x{exc['badvaddr']:08X}",
                           hint="A load or store through a bad or misaligned pointer? A buffer too small for the sectors read?")
    rows = r.record("rows") or []
    expect_true(len(rows) >= 60, "the frame loop runs (60+ frames) after loading",
                f"{len(rows)} frames; boot + load take about 400 emulated frames",
                hint="Does the program hang inside cd_load_file (CdReadSync with no timeout)?")
    st = rows[0][17]
    expect_eq(st, 0, "load_status", hint=STATUS.get(st, "") + ". The screen is red when loading fails.")
    return r, rows


def alt_disc(ctx):
    """Build alt.bin/alt.cue next to hoverline.*: the same exe and layout with the pyramid as MODEL.BIN."""
    bdir = ctx.build.build_dir
    if (bdir / "alt.cue").exists():
        return
    xml = next(iter(sorted(bdir.glob("cd_image_*.xml"))), None)
    if xml is None:
        raise CheckFailure(expected="CMake's configured iso xml", actual="not found", hint="Use psn00bsdk_add_cd_image.")
    (bdir / "alt").mkdir(exist_ok=True)
    (bdir / "alt" / "MODEL.BIN").write_bytes(pyramid_bytes())
    text = xml.read_text()
    new, n = re.subn(r'(<file\s+name="MODEL\.BIN"[^>]*?source=")[^"]*(")', lambda m: m.group(1) + str(bdir / "alt" / "MODEL.BIN") + m.group(2),
                     text, flags=re.I)
    expect_eq(n, 1, "iso.xml has one <file name=\"MODEL.BIN\" source=...> entry", hint="Appendix E.2")
    (bdir / "alt.xml").write_text(new)
    p = subprocess.run(["mkpsxiso", "-y", "-q", "-o", "alt.bin", "-c", "alt.cue", "alt.xml"], cwd=bdir, capture_output=True, text=True,
                       timeout=60, env=tool_env())
    expect_eq(p.returncode, 0, "mkpsxiso builds the alternative disc", hint=(p.stdout + p.stderr)[-400:])


@check("boots from the disc, loads and parses the model", hint="Run with -v. load_status says which step failed.")
def _(ctx):
    r, rows = observe(ctx, "main")
    expect_true(r.record("size") > 0, "model_size > 0", str(r.record("size")))


@check("the file is read through the CD library (CdSearchFile, CdRead, the controller)",
       hint="cd_load_file must call CdSearchFile for the file's position and CdRead for its sectors.")
def _(ctx):
    r, rows = observe(ctx, "main")
    c = r.record("calls")
    expect_true(c.get("cd_load_file", 0) >= 1, "cd_load_file called", str(c.get("cd_load_file")))
    expect_true(c.get("CdSearchFile", 0) >= 1, "CdSearchFile called", str(c.get("CdSearchFile")), hint="The file's position and size come from the directory.")
    expect_true(c.get("CdRead", 0) + c.get("CdReadRetry", 0) >= 1, "CdRead (or CdReadRetry) called", f"{c.get('CdRead')} / {c.get('CdReadRetry')}")
    expect_true(c.get("CdReadSync", 0) >= 1, "CdReadSync called", str(c.get("CdReadSync")), hint="Wait for the read to finish (and notice errors).")
    expect_true(r.record("cd_reg_writes", 0) > 50, "the CD controller's registers are written", str(r.record("cd_reg_writes")))
    iso = disc(ctx)
    want = iso.read("\\DATA\\MODEL.BIN")
    expect_eq(r.record("size"), len(want), "model_size is the size in the directory entry", hint="Return the directory's size, not a rounded one.")
    buf = r.record("buf")
    expect_true(0x80000000 <= buf < 0x80200000 and buf % 4 == 0, "model_buf is an aligned RAM address", f"0x{buf:08X}")
    got = bytes(r.record("bytes") or [])
    expect_eq(got, want, "the bytes at model_buf are the disc's MODEL.BIN", fmt="hex",
              hint="Did the read land in another buffer, or only part of the file?")


def check_info(ctx, name, data):
    r, rows = observe(ctx, name)
    want = expected_info(data)
    got = r.record("info")
    expect_eq(got[:2], want[:2], f"{name}: [vertex_count, face_count]", hint="Counts are big-endian (Appendix E.7): assemble them from single bytes, most significant first.")
    expect_eq(got[2:5], want[2:5], f"{name}: first vertex", hint="Vertices are little-endian s16 at 0x08, 8 bytes each.")
    expect_eq(got[5:8], want[5:8], f"{name}: last vertex", hint="The last vertex is at 8 + 8 * (vertex_count - 1).")


@check("model_info matches the generator's manifest (MODEL.BIN.json)",
       hint="vertex_count and face_count are big-endian u32; the vertices are little-endian s16; face_count follows the vertices.")
def _(ctx):
    data = ship_bytes()
    man = shpgen.model_bin_manifest(data)
    r, rows = observe(ctx, "main")
    got = r.record("info")
    expect_eq(got[0], man["vertex_count"], "vertex_count (manifest)", hint="Big-endian! Read the four bytes yourself; do not cast.")
    expect_eq(got[1], man["face_count"], "face_count (manifest)", hint="It sits right after the vertices, at 8 + 8 * vertex_count.")
    expect_eq(got[2:5], man["first_vertex"], "first_vertex (manifest)")
    expect_eq(got[5:8], man["last_vertex"], "last_vertex (manifest)")


def check_motion_and_matrix(r, rows, name):
    step = r.record("rotstep")
    cam_z = r.record("cam_z")
    expect_true(any(step) and all(abs(s) <= 64 for s in step), f"{name}: rot_step is a slow turn", str(step), hint="Non-zero, at most 64 units (5.6 degrees) per frame.")
    for a, b in zip(rows, rows[1:]):
        expect_eq([b[i] for i in (1, 2, 3)], [(a[i] + step[i - 1]) & 4095 for i in (1, 2, 3)], f"{name}: rot advances by rot_step (frame {b[0]})",
                  hint="rot += rot_step, wrapped with & 4095, once per frame.")
    for row in rows[::7]:
        m = [row[4 + 3 * i:7 + 3 * i] for i in range(3)]
        for i in range(3):
            n2 = sum(c * c for c in m[i]) / 4096.0 ** 2
            expect_true(0.94 < n2 < 1.06, f"{name}: frame {row[0]}: matrix row {i} has length 1.0", f"{n2:.3f}", hint="RotMatrix(&rot, &mtx) then TransMatrix.")
        expect_eq(row[13:16], [0, 0, cam_z], f"{name}: frame {row[0]}: translation (0, 0, cam_z)", hint="TransMatrix(&mtx, &pos) with pos = {0, 0, cam_z}.")


def silhouette(img):
    xs, ys = [], []
    for y in range(H):
        for x in range(W):
            p = img.pixel(x, y)
            if abs(p[0] - BG[0]) + abs(p[1] - BG[1]) + abs(p[2] - BG[2]) > 24:
                xs.append(x)
                ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def check_picture(r, rows, data, name):
    d = formats.parse_model_bin(data)
    verts, faces = d["verts"], d["faces"]
    byframe = {row[0]: row for row in rows}
    for fr in SHOT_FRAMES:
        row = byframe[fr]
        img = r.screenshot(f"f{fr}")
        pts = project(verts, row)
        bb = silhouette(img)
        expect_true(bb is not None, f"{name}: frame {fr}: something is drawn", "the screen is empty")
        exp = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
        for k, lab in enumerate(("left", "top", "right", "bottom")):
            expect_true(abs(bb[k] - exp[k]) <= BBOX_TOL, f"{name}: frame {fr}: silhouette {lab} edge ~{exp[k]:.0f}", f"{bb[k]}",
                        hint="The model's outline is the hull of its projected vertices: wrong vertices, matrix or screen offset?")
        front_tri = front_quad = unsure = 0
        for idx, col in faces:
            ps = [pts[i] for i in idx]
            area = nclip(ps[0], ps[1], ps[2])
            if abs(area) < AREA_MARGIN:
                unsure += 1
                continue
            if area < 0:
                continue
            if len(idx) == 3:
                front_tri += 1
            else:
                front_quad += 1
            if area >= MIN_FACE_AREA:
                cx = sum(p[0] for p in ps) / len(ps)
                cy = sum(p[1] for p in ps) / len(ps)
                expect_pixel(img, int(round(cx)), int(round(cy)), col, tol=14)
        prims = row[19]
        got_tri = got_quad = 0
        i = 0
        while i < len(prims):
            code = prims[i + 1]
            npts = 4 if code == 0x28 else 3
            got_quad += code == 0x28
            got_tri += code == 0x20
            i += 5 + 2 * npts
        expect_eq(row[16], got_tri + got_quad, f"{name}: frame {fr}: prims_submitted = polygons linked", hint="Count what you link.")
        expect_true(abs(got_tri - front_tri) + abs(got_quad - front_quad) <= unsure,
                    f"{name}: frame {fr}: {front_tri} triangles and {front_quad} quads face the camera (+-{unsure} edge-on)",
                    f"{got_tri} triangles, {got_quad} quads",
                    hint="Back-face culling with NCLIP (> 0 is front); a face with 3 corners is POLY_F3, with 4 POLY_F4.")


@check("the model spins slowly about its origin", hint="rot += rot_step each frame; RotMatrix + TransMatrix(0, 0, cam_z).")
def _(ctx):
    r, rows = observe(ctx, "main")
    check_motion_and_matrix(r, rows, "ship")
    a, b = {x[0]: x for x in rows}[SHOT_FRAMES[0]], {x[0]: x for x in rows}[SHOT_FRAMES[1]]
    expect_true(max(abs(a[4 + i] - b[4 + i]) for i in range(9)) > 150, "the matrix changes between frames 12 and 70", "identical")


@check("picture: the ship's silhouette, front faces and flat colors",
       hint="Compare with the projected vertices; each front face shows its own color from the file.")
def _(ctx):
    r, rows = observe(ctx, "main")
    check_picture(r, rows, ship_bytes(), "ship")


@check("a different MODEL.BIN on the disc (a pyramid) is loaded, parsed and drawn",
       hint="Nothing about the ship may be built into the program: counts, sizes, colors and faces all come from the file.")
def _(ctx):
    data = pyramid_bytes()
    alt_disc(ctx)
    check_info(ctx, "alt", data)
    r, rows = observe(ctx, "alt")
    expect_eq(r.record("size"), len(data), "model_size of the pyramid file")
    expect_eq(bytes(r.record("bytes") or []), data, "the bytes at model_buf are the pyramid file", fmt="hex")
    check_picture(r, rows, data, "pyramid")


# ---- dynamic checks: direct calls ------------------------------------------------------------------------------------------------
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


def model_image(verts, faces, nv=None, nf=None, magic=b"MDL1", le=False):
    """Build a MODEL.BIN image by hand (counts big-endian unless `le`)."""
    nv = len(verts) if nv is None else nv
    nf = len(faces) if nf is None else nf
    cnt = (lambda n: struct.pack("<I", n)) if le else (lambda n: struct.pack(">I", n))
    out = magic + cnt(nv)
    for v in verts:
        out += struct.pack("<hhhh", *v, 0)
    out += cnt(nf)
    for f in faces:
        out += bytes(f)
    return out


V3 = [(1, -2, 3), (-300, 200, -100), (32767, -32768, 5)]
F2 = [(0, 1, 2, 0xFF, 10, 20, 30, 0), (2, 1, 0, 1, 40, 50, 60, 0)]
V255 = [(i, -i, 2 * i) for i in range(255)]

PARSE_CASES = [
    # name, image, misalign, expected (nv, nf) or None for "must be rejected"
    ("a small valid model (3 vertices, 2 faces)", model_image(V3, F2), False, (3, 2)),
    ("255 vertices, 1 face", model_image(V255, [(254, 0, 1, 0xFF, 1, 2, 3, 0)]), False, (255, 1)),
    ("no faces", model_image(V3, []), False, (3, 0)),
    ("bad magic", model_image(V3, F2, magic=b"MDL2"), False, None),
    ("counts written little-endian", model_image(V3, F2, le=True), False, None),
    ("0 vertices", model_image([], []), False, None),
    ("256 vertices", model_image([(0, 0, 0)] * 256, []), False, None),
    ("one byte short", model_image(V3, F2)[:-1], False, None),
    ("8 bytes too long", model_image(V3, F2) + bytes(8), False, None),
    ("face_count 0xFFFFFFFF", model_image(V3, F2, nf=0xFFFFFFFF), False, None),
    ("a face index equal to vertex_count", model_image(V3, [(0, 1, 3, 0xFF, 1, 2, 3, 0)]), False, None),
    ("a quad's 4th index out of range", model_image(V3, [(0, 1, 2, 9, 1, 2, 3, 0)]), False, None),
    ("an image smaller than the header", b"MDL1\x00\x00\x00\x01", False, None),
    ("a pointer that is not 4-byte aligned", model_image(V3, F2), True, None),
]


def direct_cases(ctx):
    iso = disc(ctx)
    cd = []
    for nm, path, null in (("SYSTEM.CNF", "\\SYSTEM.CNF;1", False), ("HOVER.EXE", "\\HOVER.EXE;1", False), ("MODEL.BIN", "\\DATA\\MODEL.BIN;1", False),
                           ("MODEL.BIN with a NULL size pointer", "\\DATA\\MODEL.BIN;1", True),
                           ("missing file", "\\DATA\\NOFILE.BIN;1", False), ("missing directory", "\\NODIR\\MODEL.BIN;1", False),
                           ("MODEL.BIN again, after the failures", "\\DATA\\MODEL.BIN;1", False)):
        cd.append(dict(name=nm, path=path.encode(), null_size=null))
    parse = [dict(name=n, data=img, misalign=mis) for n, img, mis, _ in PARSE_CASES]
    return dict(cd=cd, parse=parse)


def direct_run(ctx):
    cases = direct_cases(ctx)
    gen = ctx.work / "probe_direct_gen.lua"
    gen.write_text("CASES = " + lua_val(cases) + "\ndofile(" + json.dumps(str(ctx.chapter_dir / "verify" / "probe_direct.lua")) + ")\n")
    r = ctx.run("direct", probe=gen, max_frames=900)
    r.require_finished()
    exc = r.record("exception")
    if exc:
        raise CheckFailure(expected="no CPU exception in a direct call", actual=f"exception {exc['code']} in {exc.get('fn')} ({exc.get('name')}) at pc "
                           f"0x{exc['epc']:08X}, address 0x{exc['badvaddr']:08X}", hint="Misaligned or wild pointer; a buffer overrun?")
    recs = r.record("cases")
    expect_true(recs and len(recs) == len(cases["cd"]) + len(cases["parse"]), "all direct calls completed",
                f"{len(recs or [])} of {len(cases['cd']) + len(cases['parse'])} (status {r.data.get('status')})",
                hint="A call that never returns: a wait without a timeout?")
    return cases, recs


def kdisc_hash(data):
    h = 0
    for b in data:
        h = (h * 31 + b) % 4294967296
    return h


@check("cd_load_file: finds files, returns whole-sector buffers, reports the directory size",
       hint="CdSearchFile -> size and position; sectors = ceil(size / 2048); malloc(sectors * 2048); CdlSetloc; CdRead; wait.")
def _(ctx):
    iso = disc(ctx)
    cases, recs = direct_run(ctx)
    for rec in recs[:len(cases["cd"])]:
        nm = rec["name"]
        path = next(c for c in cases["cd"] if c["name"] == nm)["path"].decode()
        key = path.split(";")[0]
        if key in iso.files:
            want = iso.read(key)
            expect_true(rec["v0"] != 0, f"{nm}: a buffer is returned", "NULL")
            expect_true(0x80000000 <= rec["v0"] < 0x80200000 and rec["v0"] % 4 == 0, f"{nm}: the buffer is aligned RAM", f"0x{rec['v0']:08X}",
                        hint="malloc returns aligned blocks; CdRead needs a 4-byte-aligned buffer.")
            if "NULL size" not in nm:
                expect_eq(rec["size_word"], len(want), f"{nm}: *size", hint="The size from the directory entry, in bytes.")
                expect_eq(rec["hash"], kdisc_hash(want), f"{nm}: the bytes returned are the file's", fmt="hex")
                expect_eq(rec["tail"], list(want[-16:]), f"{nm}: the file's last bytes", hint="Was the last (partial) sector read?")
            else:
                expect_eq(rec["head"][:16], list(want[:16]), f"{nm}: the file's first bytes")
            sectors = (len(want) + 2047) // 2048
            expect_true(max(rec["mallocs"] or [0]) >= sectors * 2048, f"{nm}: a buffer of {sectors * 2048} bytes ({sectors} sectors) is allocated",
                        f"largest malloc request {max(rec['mallocs'] or [0])}",
                        hint="The drive writes whole 2048-byte sectors: a buffer of `size` bytes is overrun by up to 2047 bytes.")
            expect_true(rec["search"] >= 1 and rec["reads"] >= 1, f"{nm}: CdSearchFile and CdRead (or CdReadRetry) are used", f"{rec['search']} / {rec['reads']}")
        else:
            expect_eq(rec["v0"], 0, f"{nm}: returns NULL", hint="CdSearchFile returns NULL when the name is not found.")
            expect_eq(rec["size_word"], 0, f"{nm}: *size is 0 on failure", hint="Set *size = 0 first, set it again only on success.")
            expect_eq(rec["reads"], 0, f"{nm}: no sectors are read", hint="Do not CdRead after a failed search.")
            expect_true(rec["frames"] < 300, f"{nm}: fails quickly", f"{rec['frames']} frames")


@check("model_parse: big-endian counts, limits, exact size, bounds, alignment; *m untouched on failure",
       hint="Read the counts byte by byte; validate before you trust them; never read past `size`.")
def _(ctx):
    cases, recs = direct_run(ctx)
    for rec, (name, img, mis, want) in zip(recs[len(cases["cd"]):], PARSE_CASES):
        if want is None:
            expect_eq(rec["v0"], 0, f"model_parse rejects: {name}", hint="Return 0 for anything that is not a valid MODEL.BIN image.")
            expect_eq(rec["model"], [0xA5A5A5A5] * 4, f"*m untouched after: {name}", hint="Write *m only once the whole image has been validated.")
        else:
            expect_eq(rec["v0"], 1, f"model_parse accepts: {name}")
            nv, nf = want
            base = rec["data_addr"]
            expect_eq(rec["model"], [nv, nf, base + 8, base + 12 + 8 * nv], f"Model for: {name} [vertex_count, face_count, verts, faces]",
                      fmt="hex", hint="verts = data + 8; faces = data + 12 + 8 * vertex_count (past face_count).")
