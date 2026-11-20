"""Chapter 31 checks: Compression: LZSS Texture Packs ("Eight Textures, One File").
Build: CMake + PSn00bSDK. The CMake rule runs tools/assets/mkassets.py (TRACK.TPK), unpacks it with the REFERENCE tool into a folder of eight TIMs
(00.tim .. 07.tim) and packs that folder with the READER's tpkpack.py into \\DATA\\TEXTURES.TPK. The emulator BOOTS THE .cue.
HOST (no emulator): the disc's TEXTURES.TPK, made by the reader's packer, decodes with the REFERENCE decoder (tools/assets/lzss.py via formats.parse_tpk):
magic, header fields, size table, CRC-32, padding, every TIM byte for byte; it is at most 1/0.85 the size of the reference packer's output (so it really uses
references); the packer is run again on crafted folders: one texture, 255 textures (and 256: an error), incompressible random data longer than the ring, a
16 KB run of zeros, a pattern that repeats at distance 3000, odd sizes, file-name order, ignored files, and every error case (no .tim files, bad TIM, ...).
MAIN RUN (the boot disc, 14 frames after the boot): load_status 0; store holds 8 textures whose tpage/clut/u/v/w/h are what Appendix E.3.4 gives for each TIM;
the CRC-32 of the decompressed blob, computed here from RAM at tpk_raw, equals the CRC-32 of the original TIMs' concatenation (and the bytes are equal);
VRAM holds every CLUT and image exactly at the rectangle its TIM names; the polygons found by walking the ordering table are eight POLY_FT4, one per grid cell, with
the texture's tpage, clut and corner UVs; the screenshot shows each texture in its cell; the cycles spent in lzss_decode stay under a budget (2x the reference).
ALT RUN: a second disc whose pack was built by tools/assets/tpkpack_ref.py (the reference compressor: a different encoding) from eight other textures (4, 8 and
16 bpp, in another order, at other VRAM rectangles): everything above again. Hard-coded textures, or an unpacker that only reads your own packer's output, fail.
DIRECT CALLS (probe_direct.lua): lzss_decode on valid streams (the worked example, all literals, zeros, random data, wrap-around, runs, the real textures) and on
damaged ones (truncated, truncated inside a reference, a trailing byte, overrunning the output, ...), with guard bytes round the output buffer;
tpk_crc32; tpk_parse on good and damaged headers; tpk_unpack (good, too small a buffer, bad magic, bad CRC, damaged stream); tpk_load of a missing file."""
import json
import re
import struct
import subprocess
import sys
import zlib
from pathlib import Path

from harness import *

ROOT_DIR = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT_DIR / "tools" / "assets"))
import mkassets      # noqa: E402
import img2tim       # noqa: E402
import formats       # noqa: E402
import lzss          # noqa: E402
import tim as T      # noqa: E402

W, H = 320, 240
BG = (16, 16, 32)
MAX_FRAMES = 700
SHOT = "f10"
COLS, CELL_W, CELL_H, QUAD, QUAD_X, QUAD_Y = 4, 80, 120, 64, 8, 28
COLOUR_TOL = 18
RATIO_MIN = 0.85                        # the reader's packer must reach 85% of the reference packer's compression ratio
# Cycles spent inside lzss_decode (entry to return) for the 16,896-byte pack: the reference solution needs about 557,000 (33 per output byte);
# the budget is 2x.
DECODE_BUDGET = 1_115_000
PACKER_TIMEOUT = 90

config(
    title="Compression: LZSS Texture Packs",
    build="cmake", exe="game.exe", sym="", elf="game.elf", iso="hoverline.cue",
    break_at=None, max_frames=MAX_FRAMES, timeout=90, vram=True,
)

STATE = ["main", "tpk_load", "tpk_unpack", "tpk_parse", "lzss_decode", "tpk_crc32", "tpk_free_raw", "store", "load_status", "tpk_raw",
         "tpk_raw_size", "prims_submitted", "frame_no", "frame_done", "ot_frames"]

# Alternative pack for the second disc: (texture, bpp, x, y, clut_x, clut_y), in texture-id order. All 64 x 64, no two rectangles overlap.
ALT_SET = [("crate", 8, 576, 256, 32, 500), ("sky16", 16, 640, 256, 0, 0), ("panel", 4, 768, 0, 0, 501), ("hull_a", 4, 784, 0, 0, 502),
           ("hull_b", 4, 800, 0, 0, 503), ("tower", 4, 816, 0, 0, 504), ("wall_a", 4, 832, 128, 0, 505), ("glow", 4, 848, 128, 0, 506)]

STATUS = {100: "cd_init() failed (CdInit)",
          -1: "TPK_ERR_READ: cd_load_file returned NULL (path \\DATA\\TEXTURES.TPK;1), or the starter's placeholder in load_textures() is still there.",
          -2: "TPK_ERR_MAGIC: tpk_parse did not see \"TPK1\"", -3: "TPK_ERR_HEADER: tpk_parse rejected the header or size table",
          -4: "TPK_ERR_MEM: malloc failed", -5: "TPK_ERR_DATA: lzss_decode rejected the stream",
          -6: "TPK_ERR_CRC: the decompressed bytes do not match the header's CRC-32 (decoder or CRC bug)",
          -7: "TPK_ERR_TIM: tim_parse rejected a texture of the pack", -8: "TPK_ERR_SPACE: dst_size < raw_size"}


# ---- references ---------------------------------------------------------------------------------------------------------------
_REF = {}


def reference(ctx):
    """(tims of the shipped pack, pngdir): the eight tiles as the generator makes them (the folder the CMake rule packs)."""
    if "tims" not in _REF:
        out = ctx.work / "refassets"
        files, _ = mkassets.build(out, seed=1, keep_png=True)
        _REF["tims"] = formats.parse_tpk(files["TRACK.TPK"])["tims"]
        _REF["png"] = out / "png"
    return _REF["tims"], _REF["png"]


def alt_tims(ctx):
    _, png = reference(ctx)
    return [img2tim.convert(png / (n + ".png"), bpp, x, y, cx, cy) for n, bpp, x, y, cx, cy in ALT_SET]


def describe(data):
    """Expected Tex words [tpage, clut, u, v, w, h] of a TIM image, from the reference library."""
    t = T.parse(data)
    u0, v0 = T.uv_origin(t.image.x, t.image.y, t.bpp)
    mult = {4: 4, 8: 2, 16: 1}[t.bpp]
    return [T.tsb(t.image.x, t.image.y, t.bpp), T.cba(t.clut.x, t.clut.y) if t.clut else 0, u0, v0, t.image.w * mult, t.image.h]


def ref_comp_size(tims):
    return formats.parse_tpk(formats.build_tpk(tims))["comp_size"]


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
        return json.dumps(bytes(v).hex())
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, dict):
        return "{" + ",".join(f"[{json.dumps(k)}]={lua_val(x)}" for k, x in v.items()) + "}"
    return "{" + ",".join(lua_val(x) for x in v) + "}"


# ---- the reader's packer, run as a program ------------------------------------------------------------------------------------
def tim16(pixels):
    """A valid 16-bpp TIM at VRAM (704, 0) whose image holds `pixels` (bytes; a multiple of 4 long, so that w*h is even)."""
    assert len(pixels) % 4 == 0
    for w in (64, 50, 32, 16, 8, 4, 2):
        if (len(pixels) // 2) % w == 0:
            break
    return T.build(T.Tim(16, T.Block(704, 0, w, len(pixels) // 2 // w, bytes(pixels))))


def run_packer(ctx, folder, out, timeout=PACKER_TIMEOUT):
    """Run `python tpkpack.py folder -o out` in the reader's project; returns the CompletedProcess."""
    script = ctx.project / "tpkpack.py"
    expect_true(script.exists(), "tpkpack.py exists in your project", "missing", hint="The packer is tpkpack.py, next to CMakeLists.txt.")
    try:
        return subprocess.run([sys.executable, str(script), str(folder), "-o", str(out)], capture_output=True, text=True, timeout=timeout,
                              cwd=ctx.work, env=tool_env())
    except subprocess.TimeoutExpired:
        raise CheckFailure(expected=f"tpkpack.py finishes in {timeout} s", actual="timed out",
                           hint="A pure-Python search of all 4095 earlier positions for every byte is too slow: see the hints (bytes.rfind).")


def pack_ok(ctx, name, tims, names=None, timeout=PACKER_TIMEOUT):
    """Write `tims` as files into a fresh folder (names default to 00.tim...), pack with the reader's tpkpack.py; the .TPK bytes."""
    folder = ctx.work / "pk_" / name
    if folder.exists():
        for f in folder.rglob("*"):
            if f.is_file():
                f.unlink()
    folder.mkdir(parents=True, exist_ok=True)
    names = names or [f"{i:03d}.tim" for i in range(len(tims))]
    for n, t in zip(names, tims):
        (folder / n).write_bytes(t)
    out = ctx.work / "pk_" / (name + ".tpk")
    out.unlink(missing_ok=True)
    p = run_packer(ctx, folder, out, timeout)
    expect_eq(p.returncode, 0, f"{name}: tpkpack.py exit status", hint=(p.stderr or p.stdout)[-300:])
    expect_true(out.exists(), f"{name}: tpkpack.py wrote the output file", "no file")
    return out.read_bytes(), folder


def decode_with_reference(blob, tims, what):
    """Parse a .TPK with the reference code (magic, sizes, decompression, CRC-32) and require exactly `tims` in it."""
    try:
        d = formats.parse_tpk(blob)
    except (formats.FormatError, lzss.LzssError, struct.error, IndexError) as e:
        raise CheckFailure(expected=f"{what}: a .TPK the reference decoder accepts", actual=str(e),
                           hint="Appendix E.5 and E.6: header fields, size table, LZSS stream, CRC-32 of the RAW blob, stream length = comp_size.")
    expect_eq(d["count"], len(tims), f"{what}: count")
    expect_eq(d["sizes"], [len(t) for t in tims], f"{what}: size table (the TIM sizes, in order)")
    for i, (a, b) in enumerate(zip(d["tims"], tims)):
        if a != b:
            first = next(k for k in range(min(len(a), len(b))) if a[k] != b[k]) if a[:len(b)] != b[:len(a)] else min(len(a), len(b))
            raise CheckFailure(expected=f"{what}: texture {i} equal to the input TIM", actual=f"differs at byte {first}",
                               hint="Compressor bug: a reference with the wrong position/length, or the ring started wrong.")
    expect_eq(len(blob) % 4, 0, f"{what}: file size is a multiple of 4", hint="Pad with zero bytes after the stream (E.6).")
    pad = len(blob) - 20 - 4 * d["count"] - d["comp_size"]
    expect_eq(blob[len(blob) - pad:], bytes(pad), f"{what}: padding bytes are zero")
    return d


# ---- static checks ----------------------------------------------------------------------------------------------------------------
@static_check("the state symbols exist", hint="Keep the functions and globals the starter declares (store, load_status, tpk_raw, tpk_raw_size, lzss_decode ...).")
def _(ctx):
    ctx.require_symbols(*STATE)


@static_check("the disc image has SYSTEM.CNF, HOVER.EXE and \\DATA\\TEXTURES.TPK",
              hint="iso.xml: TEXTURES.TPK inside <dir name=\"DATA\">, source assets/TEXTURES.TPK (written by the CMake rule that runs tpkpack.py).")
def _(ctx):
    iso = disc(ctx)
    for p in ("\\SYSTEM.CNF", "\\HOVER.EXE", "\\DATA\\TEXTURES.TPK"):
        expect_true(p in iso.files, f"{p} on the disc", f"found {sorted(iso.files)}")
    expect_eq(iso.read("\\HOVER.EXE"), (ctx.build.build_dir / "game.exe").read_bytes(), "HOVER.EXE on the disc is the built game.exe")


@static_check("the textures are not inside the program",
              hint="The pack must be read from the disc and decompressed at run time, not compiled into the EXE.")
def _(ctx):
    exe = (ctx.build.build_dir / "game.exe").read_bytes()
    tims, _ = reference(ctx)
    for i, data in enumerate(tims):
        t = T.parse(data)
        expect_true(t.image.data not in exe, f"texture {i}'s pixel data is not in game.exe", "found its bytes in the executable")


@static_check("host: your tpkpack.py's TEXTURES.TPK decodes with the REFERENCE decompressor, CRC-32 and all, to the eight TIMs",
              hint="tpkpack.py FOLDER -o OUT: header (E.6), size table, one LZSS stream (E.5) of the concatenated TIMs, CRC-32 of the raw bytes, zero padding.")
def _(ctx):
    tims, _ = reference(ctx)
    blob = disc(ctx).read("\\DATA\\TEXTURES.TPK")
    d = decode_with_reference(blob, tims, "TEXTURES.TPK")
    expect_eq(d["crc32"], zlib.crc32(b"".join(tims)) & 0xFFFFFFFF, "the header's CRC-32 is the CRC-32 of the TIMs' concatenation", fmt="hex",
              hint="zlib.crc32 of the UNcompressed blob.")
    expect_eq(d["raw_size"], sum(len(t) for t in tims), "raw_size")


@static_check(f"host: the pack is within {int(RATIO_MIN * 100)}% of the reference packer's compression ratio (LZSS references are really produced)",
              hint="An all-literal stream is valid but 12% larger than the raw data. Search the previous 4095 bytes for the longest match (3..18) at each position.")
def _(ctx):
    tims, _ = reference(ctx)
    d = decode_with_reference(disc(ctx).read("\\DATA\\TEXTURES.TPK"), tims, "TEXTURES.TPK")
    ref = ref_comp_size(tims)
    raw = d["raw_size"]
    mine, theirs = raw / d["comp_size"], raw / ref
    expect_true(mine >= RATIO_MIN * theirs, f"compression ratio >= {RATIO_MIN} x the reference's ({theirs:.2f}, comp_size {ref})",
                f"ratio {mine:.2f} (comp_size {d['comp_size']}, raw {raw})")


@static_check("host: edge cases through the packer: 1 texture, random data past the ring size, a long run, a repeat at distance 3000, odd sizes",
              hint="A stream the reference decoder rejects, or a CRC/size-table mistake, shows here with the case name.")
def _(ctx):
    import random
    seed = 31
    print(f"  (edge-case seed {seed})")
    rnd = random.Random(seed)
    tiny = tim16(b"\x34\x12\x78\x56")
    blob, _ = pack_ok(ctx, "one_tiny", [tiny], timeout=30)
    decode_with_reference(blob, [tiny], "1 tiny texture (24 bytes)")
    noise = tim16(bytes(rnd.randrange(256) for _ in range(5120)))
    blob, _ = pack_ok(ctx, "noise", [noise])
    decode_with_reference(blob, [noise], "5 KB of random data (incompressible, crosses the ring wrap)")
    zeros = tim16(bytes(16384))
    blob, _ = pack_ok(ctx, "zeros", [zeros])
    d = decode_with_reference(blob, [zeros], "16 KB of zeros")
    expect_true(d["comp_size"] <= 0.2 * d["raw_size"], "a 16 KB run of zeros compresses to at most 20%", f"comp_size {d['comp_size']} of {d['raw_size']}",
                hint="Matches of 18 bytes: a reference into the zero-filled ring, then references to the bytes just written.")
    pat = bytes(rnd.randrange(256) for _ in range(3000))
    rep = tim16(pat * 5)
    blob, _ = pack_ok(ctx, "repeat", [rep])
    d = decode_with_reference(blob, [rep], "a 3000-byte pattern repeated 5 times")
    expect_true(d["comp_size"] <= 0.5 * d["raw_size"], "a pattern that repeats at distance 3000 compresses to at most 50%", f"comp_size {d['comp_size']} of {d['raw_size']}",
                hint="The window is 4095 bytes: matches at distance 3000 are allowed (and the ring position is absolute, not the distance).")
    odd = [tim16(bytes(rnd.randrange(256) for _ in range(n)) if k % 2 else bytes((i // 7) & 255 for i in range(n)))
           for k, n in enumerate((4, 12, 100, 4000, 4100, 20))]
    blob, _ = pack_ok(ctx, "odd", odd)
    decode_with_reference(blob, odd, "six textures of odd sizes (mixed noise and ramps)")
    one, _ = pack_ok(ctx, "one_real", [reference(ctx)[0][0]])
    decode_with_reference(one, [reference(ctx)[0][0]], "1 real tile")


@static_check("host: texture ids: files in plain string order of their names; .TIM and .tim both count; other files and subfolders are ignored",
              hint="sorted(names) of the files whose suffix.lower() == '.tim'; the size table follows that order.")
def _(ctx):
    names = ["b.tim", "a.tim", "C.TIM", "10.tim", "9.tim"]
    tims = {n: tim16(bytes(4 * (k + 1))) for k, n in enumerate(names)}       # sizes 24, 28, 32, 36, 40: they identify the order
    folder = ctx.work / "pk_" / "order"
    folder.mkdir(parents=True, exist_ok=True)
    for f in folder.iterdir():
        if f.is_file():
            f.unlink()
    for n, t in tims.items():
        (folder / n).write_bytes(t)
    (folder / "notes.txt").write_bytes(b"not a texture")
    (folder / "sub").mkdir(exist_ok=True)
    (folder / "sub" / "z.tim").write_bytes(tim16(bytes(400)))
    out = ctx.work / "pk_" / "order.tpk"
    out.unlink(missing_ok=True)
    p = run_packer(ctx, folder, out, 30)
    expect_eq(p.returncode, 0, "order: tpkpack.py exit status", hint=(p.stderr or p.stdout)[-300:])
    want = [tims[n] for n in sorted(names)]
    decode_with_reference(out.read_bytes(), want, "order (10.tim 9.tim C.TIM a.tim b.tim)")


@static_check("host: 255 textures pack; 256 is an error; at most 255 per pack",
              hint="Appendix E.6: count is 1..255. Refuse 256 with a message and status 1, and write no file.")
def _(ctx):
    tims = [tim16(bytes([i, i ^ 0x55, 7, 9])) for i in range(255)]
    blob, folder = pack_ok(ctx, "n255", tims, timeout=30)
    decode_with_reference(blob, tims, "255 textures")
    (folder / "extra.tim").write_bytes(tim16(bytes(4)))
    out = ctx.work / "pk_" / "n256.tpk"
    out.unlink(missing_ok=True)
    p = run_packer(ctx, folder, out, 30)
    expect_true(p.returncode != 0 and not out.exists(), "256 textures: non-zero exit status and no output file",
                f"exit {p.returncode}, file {'written' if out.exists() else 'absent'}")


@static_check("host: errors: no .tim files, a missing folder, a file that is not a TIM: status 1, a message, no output file",
              hint="A finished packer fails loudly (see the contract in 7.2); remove the placeholder fallback of the starter's main().")
def _(ctx):
    cases = []
    empty = ctx.work / "pk_" / "e_empty"
    empty.mkdir(parents=True, exist_ok=True)
    for f in empty.iterdir():
        f.unlink()
    cases.append(("an empty folder", empty))
    txt = ctx.work / "pk_" / "e_txt"
    txt.mkdir(parents=True, exist_ok=True)
    (txt / "readme.txt").write_bytes(b"hello")
    cases.append(("a folder with no .tim file", txt))
    cases.append(("a folder that does not exist", ctx.work / "pk_" / "e_missing"))
    good = tim16(bytes(8))
    for label, bad in (("a .tim with the wrong magic", b"\x11\x00\x00\x00" + bytes(20)), ("a .tim whose size is not a multiple of 4", good + b"\x00"),
                       ("an empty .tim file", b""), ("a .tim of 16 bytes (shorter than the smallest TIM)", good[:16])):
        f = ctx.work / "pk_" / ("e_" + str(len(cases)))
        f.mkdir(parents=True, exist_ok=True)
        for old in f.iterdir():
            old.unlink()
        (f / "a.tim").write_bytes(good)
        (f / "b.tim").write_bytes(bad)
        cases.append((label + " next to a good one", f))
    for label, folder in cases:
        out = ctx.work / "pk_" / "e_out.tpk"
        out.unlink(missing_ok=True)
        p = run_packer(ctx, folder, out, 30)
        expect_true(p.returncode != 0, f"{label}: non-zero exit status", f"exit {p.returncode}", hint="Return 1 and print the reason to stderr.")
        expect_true(not out.exists(), f"{label}: no output file is written", "the file exists", hint="Write the output only after everything has succeeded.")
        expect_true(p.stderr.strip() != "", f"{label}: a message on stderr", "silent")


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
    """Build alt.bin/alt.cue next to hoverline.*: the same exe, TEXTURES.TPK replaced by a pack made with the REFERENCE packer."""
    bdir = ctx.build.build_dir
    if (bdir / "alt.cue").exists():
        return
    xml = next(iter(sorted(bdir.glob("cd_image_*.xml"))), None)
    if xml is None:
        raise CheckFailure(expected="CMake's configured iso xml", actual="not found", hint="Use psn00bsdk_add_cd_image.")
    (bdir / "alt").mkdir(exist_ok=True)
    (bdir / "alt" / "TEXTURES.TPK").write_bytes(formats.build_tpk(alt_tims(ctx)))
    text, k = re.subn(r'(<file\s+name="TEXTURES\.TPK"[^>]*?source=")[^"]*(")', lambda m: m.group(1) + str(bdir / "alt" / "TEXTURES.TPK") + m.group(2),
                      xml.read_text(), flags=re.I)
    expect_eq(k, 1, "iso.xml has one <file name=\"TEXTURES.TPK\" source=...> entry", hint="Appendix E.2")
    (bdir / "alt.xml").write_text(text)
    p = subprocess.run(["mkpsxiso", "-y", "-q", "-o", "alt.bin", "-c", "alt.cue", "alt.xml"], cwd=bdir, capture_output=True, text=True,
                       timeout=60, env=tool_env())
    expect_eq(p.returncode, 0, "mkpsxiso builds the alternative disc", hint=(p.stdout + p.stderr)[-400:])


def observe(ctx, name):
    """(RunResult, rows, tims) of the main run or the alt run; fails with a precise message when it never got going.
    rows are the probe rows from frame 3 on: [frame_no, load_status, prims_submitted, emu_frame, prims]."""
    if name == "main":
        r = ctx.result
        tims, _ = reference(ctx)
    else:
        alt_disc(ctx)
        r = ctx.run("alt", iso="alt.cue")
        tims = alt_tims(ctx)
    r.require_finished()
    exc = r.record("exception")
    if exc:
        raise CheckFailure(expected="no CPU exception", actual=f"CPU exception {exc['code']} at pc 0x{exc['epc']:08X}, address 0x{exc['badvaddr']:08X}",
                           hint="A load or store through a bad or misaligned pointer? The decoder writing or reading outside its buffers?")
    rows = [x for x in (r.record("rows") or []) if x[0] >= 3]
    expect_true(len(rows) >= 10, "the frame loop runs (10+ frames) after loading", f"{len(rows)} frames (status {r.data.get('status')})",
                hint="Does the program hang inside cd_load_file, lzss_decode or LoadImage / DrawSync? Booting + loading takes about 400 emulated frames.")
    st = rows[0][1]
    expect_eq(st, 0, f"{name}: load_status", hint=STATUS.get(st, "") + " The screen is red when loading fails.")
    return r, rows, tims


# ---- dynamic checks: the unpacked blob, the store, VRAM -----------------------------------------------------------------------------
def check_blob(ctx, name):
    r, rows, tims = observe(ctx, name)
    store = r.record("store")
    ptr_size = r.record("tpk_raw")
    raw = b"".join(tims)
    expect_eq(store[0], len(tims), f"{name}: store.count", hint="tpk_load sets out->count to the header's count.")
    expect_eq(ptr_size[1], len(raw), f"{name}: tpk_raw_size is the sum of the TIM sizes", hint="main.c copies store.raw_size after tpk_load.")
    expect_true(0x80000000 <= ptr_size[0] < 0x80200000 and ptr_size[0] % 4 == 0, f"{name}: tpk_raw is an aligned RAM address", f"0x{ptr_size[0]:08X}")
    expect_eq(store[1], ptr_size[0], f"{name}: tpk_raw is store.raw", fmt="hex")
    got = r.mem("raw")
    expect_eq(zlib.crc32(got) & 0xFFFFFFFF, zlib.crc32(raw) & 0xFFFFFFFF, f"{name}: CRC-32 of the decompressed blob (computed from RAM at tpk_raw)", fmt="hex",
              hint="The decoder produced different bytes: compare with the TIMs' concatenation (first difference: "
                   + str(next((i for i in range(min(len(got), len(raw))) if got[i] != raw[i]), "none")) + ").")
    expect_eq(got, raw, f"{name}: the decompressed blob equals the concatenated TIMs")
    return r, rows, tims, store


def check_store(ctx, name):
    r, rows, tims, store = check_blob(ctx, name)
    words = store[3:]
    for i, data in enumerate(tims):
        got = words[6 * i:6 * i + 6]
        expect_eq(got, describe(data), f"{name}: store.tex[{i}] [tpage, clut, u, v, w, h]", fmt="dec",
                  hint="tex_from_tim of Chapter 30 on the TIM at offset sum(sizes[0..i-1]) of the blob; the id is the position in the pack.")
    return r, rows, tims


def check_vram(ctx, name):
    r, rows, tims = observe(ctx, name)
    vram = r.vram()
    for data in tims:
        t = T.parse(data)
        if t.clut:
            vram.expect_rect(t.clut.x, t.clut.y, t.clut.w, t.clut.h, t.clut.data)
        vram.expect_rect(t.image.x, t.image.y, t.image.w, t.image.h, t.image.data)


@check("boots from the disc; the pack unpacks: the CRC-32 and the bytes of the blob in RAM equal the original TIMs; store.tex[] describes the 8 textures",
       hint="tpk_load: read the file, tpk_parse, malloc raw_size, tpk_unpack (lzss_decode + CRC), then tim_parse / tim_upload / tex_from_tim for each texture.")
def _(ctx):
    check_store(ctx, "main")


@check("VRAM holds each texture's CLUT and image at the rectangle its TIM names, byte for byte",
       hint="tim_upload (Chapter 30) on every TIM in the blob, in id order; the packer must keep the TIM bytes verbatim.")
def _(ctx):
    check_vram(ctx, "main")


@check("an alternative disc (a pack built by the reference packer: other textures, 4/8/16 bpp, other places in VRAM): blob, store and VRAM",
       hint="The unpacker must decode ANY valid stream, not only your packer's; nothing about the shipped textures may be built in.")
def _(ctx):
    check_store(ctx, "alt")
    check_vram(ctx, "alt")


# ---- dynamic checks: polygons and picture ------------------------------------------------------------------------------------------------
def prim_list(row):
    return [row[4][i:i + 23] for i in range(0, len(row[4]), 23)]


def check_prims(rows, tims, name):
    """Every sampled frame: one POLY_FT4 per texture, in id order, in its grid cell, with the texture's tpage, clut and corner UVs."""
    for row in rows[::3]:
        prims = prim_list(row)
        fr = row[0]
        expect_eq(row[2], len(tims), f"{name}: frame {fr}: prims_submitted", hint="One quad per texture.")
        expect_eq(len(prims), len(tims), f"{name}: frame {fr}: polygons in the ordering table")
        for i, data in enumerate(tims):
            tpage, clut, u, v, w, h = describe(data)
            x0, y0 = (i % COLS) * CELL_W + QUAD_X, (i // COLS) * CELL_H + QUAD_Y
            want_xy = [(x0, y0), (x0 + QUAD, y0), (x0, y0 + QUAD), (x0 + QUAD, y0 + QUAD)]
            want_uv = [(u, v), (u + w - 1, v), (u, v + h - 1), (u + w - 1, v + h - 1)]
            mine = [p for p in prims if (p[5], p[6]) == want_xy[0]]
            expect_eq(len(mine), 1, f"{name}: frame {fr}: one polygon at grid cell {i} (corner {want_xy[0]})",
                      hint="Texture id i goes in cell (i % 4, i / 4): store.tex[i].")
            p = mine[0]
            expect_eq(p[1], 0x2C, f"{name}: cell {i}: command byte", fmt="hex")
            expect_eq([(p[5 + 4 * k], p[6 + 4 * k]) for k in range(4)], want_xy, f"{name}: cell {i}: corners")
            expect_eq([(p[7 + 4 * k], p[8 + 4 * k]) for k in range(4)], want_uv, f"{name}: cell {i}: corner UVs (texture {i}: u0 {u}, v0 {v}, {w} x {h})",
                      hint="Texture i's tex[] entry is wrong or in the wrong place (the starter's draw_grid is given).")
            expect_eq(p[22] & 0x1FF, tpage, f"{name}: cell {i}: tpage word", fmt="hex", hint="tex_from_tim of texture i's own TIM.")
            expect_eq(p[21], clut, f"{name}: cell {i}: clut word", fmt="hex")


def check_picture(r, tims, name):
    img = r.screenshot(SHOT)
    for i, data in enumerate(tims):
        t = T.parse(data)
        tw, th, px = T.decode_rgba(t)
        x0, y0 = (i % COLS) * CELL_W + QUAD_X, (i // COLS) * CELL_H + QUAD_Y
        ok = bad = 0
        first_bad = None
        seen = set()
        for y in range(3, QUAD - 3, 3):
            for x in range(3, QUAD - 3, 3):
                tx, ty = x * tw // QUAD, y * th // QUAD
                around = [px[min(th - 1, max(0, ty + dy)) * tw + min(tw - 1, max(0, tx + dx))] for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
                if any(q[3] == 0 for q in around):
                    continue                                         # near a transparent texel: not judged
                got = img.pixel(x0 + x, y0 + y)
                seen.add(tuple(got[:3]))
                if any(max(abs(got[c] - q[c]) for c in range(3)) <= COLOUR_TOL for q in around):
                    ok += 1
                else:
                    bad += 1
                    first_bad = first_bad or (x, y, got, px[ty * tw + tx][:3])
        expect_true(ok + bad >= 100, f"{name}: cell {i} has enough sample points", f"{ok + bad}")
        expect_true(ok >= 0.9 * (ok + bad), f"{name}: cell {i} shows texture {i} ({ok} of {ok + bad} sample points match)",
                    f"{ok} of {ok + bad}; e.g. pixel ({x0 + first_bad[0]}, {y0 + first_bad[1]}) is {first_bad[2]}, the texel there is {first_bad[3]}" if first_bad else "",
                    hint="Right shapes, wrong colours: the CLUT. Noise: the page or the image upload. A texture that is not the one in the pack: ids or order.")
        need = min(3, len({q[:3] for q in px}))
        expect_true(len(seen) >= need, f"{name}: cell {i} is textured ({len(seen)} distinct colours)", f"{len(seen)}", hint="A flat quad: not textured.")


@check("polygons: one POLY_FT4 per texture in its grid cell, with that texture's tpage, clut and corner UVs",
       hint="The grid code is given: it draws store.tex[0..count-1]. A wrong entry in store.tex shows up as a wrong word or UV here.")
def _(ctx):
    r, rows, tims = observe(ctx, "main")
    check_prims(rows, tims, "main")


@check("picture: the eight cells show the eight textures",
       hint="Compare the screenshot with the TIMs: a wrong palette, page or order shows up here.")
def _(ctx):
    r, rows, tims = observe(ctx, "main")
    check_picture(r, tims, "main")


@check("alt run: polygons and picture for the reference-packed pack",
       hint="Texture ids follow the pack's order; 8-bpp and 16-bpp textures need their own tpage and clut words.")
def _(ctx):
    r, rows, tims = observe(ctx, "alt")
    check_prims(rows, tims, "alt")
    check_picture(r, tims, "alt")


@check(f"performance: lzss_decode takes under {DECODE_BUDGET:,} cycles for the 16,896-byte pack, and is called",
       hint="A byte loop with three checks per item is fine; look for a function call per byte, a division, a modulo, or a memset of the ring per item.")
def _(ctx):
    r, rows, tims = observe(ctx, "main")
    calls, cycles = r.record("decode_calls"), r.record("decode_cycles")
    if calls and cycles:
        print(f"  (lzss_decode: {cycles:,} cycles in {calls} call(s), {cycles / sum(len(t) for t in tims):.1f} per output byte)")
    expect_true(calls and calls >= 1, "lzss_decode is called while loading", f"{calls} calls",
                hint="tpk_unpack must call lzss_decode (noinline), once for the whole blob.")
    expect_true(cycles <= DECODE_BUDGET, f"lzss_decode cycles <= {DECODE_BUDGET:,}", f"{cycles:,} cycles for {calls} call(s) "
                f"({cycles / sum(len(t) for t in tims):.1f} per output byte)", hint="See the performance notes in 5.7.")


# ---- dynamic checks: direct calls -------------------------------------------------------------------------------------------------------
SRC, DST, HDR, STORE, STR = 0x80180000, 0x801A0010, 0x801E0000, 0x801D0000, 0x801F0000
GUARD = 16
FILL = 0xA5


def literal_stream(data):
    """A valid all-literal stream (every flag bit 1): the format allows it."""
    out = bytearray()
    for i in range(0, len(data), 8):
        chunk = data[i:i + 8]
        out.append((1 << len(chunk)) - 1 if len(chunk) < 8 else 0xFF)
        out += chunk
    return bytes(out)


def ref_item(pos, length):
    return bytes((pos & 255, ((pos >> 4) & 0xF0) | (length - 3)))


DECODE_GOOD = []     # (name, stream, expected output)
DECODE_BAD = []      # (name, stream bytes in memory, src_size, dst_size)


def build_decode_cases():
    import random
    rnd = random.Random(31)
    text = b"to be or not to be, that is the question: whether 'tis nobler in the mind to suffer"
    noise = bytes(rnd.randrange(256) for _ in range(5000))
    pat = bytes(rnd.randrange(256) for _ in range(3000)) * 5
    ramp = bytes((i * i >> 3) & 255 for i in range(300))
    DECODE_GOOD.clear()
    DECODE_BAD.clear()
    DECODE_GOOD.append(("the worked example of E.5 (14 bytes -> ABRACADABRA ABRACADABRA)", bytes.fromhex("7f414252414341 44eef10120eef8".replace(" ", "")),
                        b"ABRACADABRA ABRACADABRA"))
    DECODE_GOOD.append(("all literals (valid: every flag bit 1), 43 bytes", literal_stream(text[:43]), text[:43]))
    DECODE_GOOD.append(("three references into the never-written (zero) ring", bytes([0]) + ref_item(0xFFF, 3) + ref_item(0x064, 18) + ref_item(0x7D0, 5), bytes(26)))
    DECODE_GOOD.append(("text with repeats, 82 bytes (ends in the middle of a flag byte)", lzss.compress(text), text))
    DECODE_GOOD.append(("a run of one byte, 300 x 'A' (references to bytes just written)", lzss.compress(b"A" * 300), b"A" * 300))
    DECODE_GOOD.append(("1000 zeros (references only)", lzss.compress(bytes(1000)), bytes(1000)))
    DECODE_GOOD.append(("5000 random bytes (crosses the ring wrap)", lzss.compress(noise), noise))
    DECODE_GOOD.append(("a 3000-byte pattern 5 times (matches at distance 3000)", lzss.compress(pat), pat))
    DECODE_GOOD.append(("a ramp", lzss.compress(ramp), ramp))
    run = lzss.compress(b"A" * 300)
    s_text = lzss.compress(text)
    DECODE_BAD.append(("truncated: the last byte is missing (the byte after src_size is the right one: do not read it)", s_text, len(s_text) - 1, len(text)))
    DECODE_BAD.append(("truncated inside the last reference", run, len(run) - 1, 300))
    DECODE_BAD.append(("one byte too many in the input", s_text + b"\x00", len(s_text) + 1, len(text)))
    DECODE_BAD.append(("a reference that runs past dst_size by one byte", run, len(run), 299))
    DECODE_BAD.append(("dst_size 100 for a 300-byte stream", run, len(run), 100))
    DECODE_BAD.append(("ten literals, dst_size 5", literal_stream(text[:10]), len(literal_stream(text[:10])), 5))
    DECODE_BAD.append(("the stream ends 5 bytes before dst_size", s_text, len(s_text), len(text) + 5))
    DECODE_BAD.append(("an empty stream, dst_size 10", b"\x00" * 4, 0, 10))
    DECODE_BAD.append(("a flag byte and a literal, dst_size 1, plus a stray byte", b"\x01A\x01", 3, 1))


def decode_case(name, stream, src_size, dst_size, tag):
    return dict(name=name, fn="lzss_decode", args=[SRC, src_size, DST, dst_size], tag=tag,
                writes=[[SRC, stream], [DST - GUARD, bytes([FILL]) * (dst_size + 2 * GUARD)]],
                reads=[[DST - GUARD, GUARD], [DST, dst_size], [DST + dst_size, GUARD]])


def pack_bytes(tims):
    return formats.build_tpk(tims)


def direct_cases(ctx):
    build_decode_cases()
    cases = []
    for name, stream, out in DECODE_GOOD:
        cases.append(decode_case(name, stream, len(stream), len(out), "decode_ok"))
    for name, stream, src_size, dst_size in DECODE_BAD:
        cases.append(decode_case(name, stream, src_size, dst_size, "decode_bad"))
    tims, _ = reference(ctx)
    raw = b"".join(tims)
    big = lzss.compress(raw)
    cases.append(decode_case("the 16,896 bytes of the shipped textures (reference-compressed)", big, len(big), len(raw), "decode_real"))
    # CRC-32
    rnd_crc = bytes((i * 131 + (i >> 3) * 17) & 255 for i in range(1000))
    for name, data, src in (("\"123456789\"", b"123456789", SRC), ("no bytes", b"", SRC), ("1000 bytes", rnd_crc, SRC),
                            ("777 bytes at an odd address", rnd_crc[:777], SRC + 1), ("the 16,896 bytes of the textures", raw, SRC)):
        cases.append(dict(name=name, fn="tpk_crc32", args=[src, len(data), 0, 0], tag="crc", data=data, writes=[[src, data]], reads=[]))
    # tpk_parse and tpk_unpack on small packs made by the reference packer
    small = tims[:3]
    good = pack_bytes(small)
    count = 3
    table_end = 20 + 4 * count
    comp_size = struct.unpack_from("<I", good, 12)[0]
    extra = len(good) - table_end - comp_size

    def mut(off, val, fmt="<I", base=good):
        b = bytearray(base)
        struct.pack_into(fmt, b, off, val)
        return bytes(b)

    sizes = [len(t) for t in small]
    raw_size = sum(sizes)
    parse_good = [("a good pack", good, len(good)),
                  ("3 bytes of zero padding after the stream are allowed", good[:len(good) - extra] + bytes(3), len(good) - extra + 3),
                  ("no padding at all is fine too", good[:len(good) - extra], len(good) - extra)]
    parse_bad = [("bad magic (TPK2)", good.replace(b"TPK1", b"TPK2", 1), len(good), -2),
                 ("3 bytes long", good[:3], 3, -2),
                 ("valid magic but shorter than the fixed header (12 bytes)", good[:12], 12, -3),
                 ("count 0", mut(4, 0), len(good), -3),
                 ("count 256", mut(4, 256), len(good), -3),
                 ("the size table runs past the end of the file", good, table_end - 1, -3),
                 ("a size of 0 in the table", mut(20 + 4, 0), len(good), -3),
                 ("a size that is not a multiple of 4 (and raw_size adjusted to match)", mut(8, raw_size + 1, base=mut(20, sizes[0] + 1)), len(good), -3),
                 ("sizes do not add up to raw_size", mut(8, raw_size + 4), len(good), -3),
                 ("raw_size above 1 MiB (sizes adjusted to match)", mut(8, 0x200000, base=mut(20, 0x200000 - sizes[1] - sizes[2])), len(good), -3),
                 ("comp_size 0", mut(12, 0), len(good), -3),
                 ("comp_size larger than the rest of the file", mut(12, comp_size + 8), len(good), -3),
                 ("4 stray bytes after the stream", good + bytes(4), len(good) + 4, -3)]
    for name, blob, size in parse_good:
        cases.append(dict(name="tpk_parse: " + name, fn="tpk_parse", args=[SRC, size, HDR, 0], tag="parse_ok", blob=blob, size=size,
                          writes=[[SRC, blob], [HDR, bytes([FILL]) * 1040]], reads=[[HDR, 16 + 4 * 3], [HDR + 16 + 255 * 4, 4]]))
    for name, blob, size, want in parse_bad:
        cases.append(dict(name="tpk_parse: " + name, fn="tpk_parse", args=[SRC, size, HDR, 0], tag="parse_bad", want=want,
                          writes=[[SRC, blob], [HDR, bytes([FILL]) * 1040]], reads=[]))
    raw3 = b"".join(small)

    def unpack(name, blob, size, dst_size, want, tag="unpack"):
        cases.append(dict(name="tpk_unpack: " + name, fn="tpk_unpack", args=[SRC, size, DST, dst_size], tag=tag, want=want, raw=raw3, dst_size=dst_size,
                          writes=[[SRC, blob], [DST - GUARD, bytes([FILL]) * (dst_size + 2 * GUARD)]],
                          reads=[[DST - GUARD, GUARD], [DST, dst_size], [DST + dst_size, GUARD]]))

    stream_mid = 20 + 4 * count + comp_size // 2
    unpack("a good pack, dst_size = raw_size", good, len(good), raw_size, 0)
    unpack("a good pack, a larger buffer (the extra bytes stay untouched)", good, len(good), raw_size + 64, 0)
    unpack("dst_size one byte short: error, nothing written", good, len(good), raw_size - 1, -8)
    unpack("bad magic", good.replace(b"TPK1", b"TPKX", 1), len(good), raw_size, -2)
    unpack("the CRC field is wrong", mut(16, struct.unpack_from("<I", good, 16)[0] ^ 1), len(good), raw_size, -6)
    unpack("a damaged byte in the middle of the stream (DATA or CRC error)", good[:stream_mid] + bytes([good[stream_mid] ^ 0x5A]) + good[stream_mid + 1:],
           len(good), raw_size, -5)
    unpack("the file is cut short (the stream does not fit)", good, len(good) - 8, raw_size, -3)
    # tpk_load: a missing file, then the real one, then tpk_free_raw
    cases.append(dict(name="tpk_load: a file that is not on the disc", fn="tpk_load", args=[STR, STORE, 0, 0], tag="load_missing",
                      writes=[[STR, b"\\DATA\\NOPE.TPK;1\x00"], [STORE, bytes([FILL]) * 12]], reads=[[STORE, 12]]))
    cases.append(dict(name="tpk_load: the shipped pack, called again", fn="tpk_load", args=[STR, STORE, 0, 0], tag="load_again",
                      writes=[[STR, b"\\DATA\\TEXTURES.TPK;1\x00"], [STORE, bytes([FILL]) * 12]], reads=[[STORE, 12 + 12 * 8]]))
    cases.append(dict(name="tpk_free_raw", fn="tpk_free_raw", args=[STORE, 0, 0, 0], tag="free", reads=[[STORE, 12]]))
    return cases


def direct_run(ctx):
    if "direct" in _REF:
        return _REF["direct"]
    cases = direct_cases(ctx)
    wire = []
    for c in cases:
        wire.append(dict(name=c["name"], fn=c["fn"], args=c["args"], writes=c.get("writes", []), reads=c.get("reads", [])))
    gen = ctx.work / "probe_direct_gen.lua"
    gen.write_text("CASES = " + lua_val(wire) + "\ndofile(" + json.dumps(str(ctx.chapter_dir / "verify" / "probe_direct.lua")) + ")\n")
    r = ctx.run("direct", probe=gen, max_frames=900)
    r.require_finished()
    exc = r.record("exception")
    if exc:
        raise CheckFailure(expected="no CPU exception in a direct call", actual=f"exception {exc['code']} in {exc.get('fn')} ({exc.get('name')}) at pc "
                           f"0x{exc['epc']:08X}, address 0x{exc['badvaddr']:08X}",
                           hint="Reading past the end of the stream? A write outside dst? A misaligned word read (use byte reads for the file image)?")
    recs = r.record("cases")
    expect_true(recs and len(recs) == len(cases), "all direct calls completed", f"{len(recs or [])} of {len(cases)} (status {r.data.get('status')})",
                hint="A call that never returns (an endless loop on a damaged stream?)")
    _REF["direct"] = (cases, recs)
    return cases, recs


def s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


def guards_ok(rec, case, dst_size):
    pad = bytes([FILL]) * GUARD
    expect_eq(bytes.fromhex(rec["reads"][0]), pad, f"{case['name']}: the {GUARD} bytes BEFORE dst are untouched", hint="An out-of-bounds write.")
    expect_eq(bytes.fromhex(rec["reads"][2]), pad, f"{case['name']}: the {GUARD} bytes AFTER dst[dst_size] are untouched",
              hint="The decoder wrote past dst_size: check every item (literal and each byte of a reference) against dst_size.")


@check("lzss_decode: valid streams (E.5's example, all literals, zeros, random, wrap-around, runs, the real textures) decode exactly; guard bytes intact",
       hint="Appendix E.5: ring of 4096 zeros, cursor 4078, flag bits LSB first with 1 = literal, reference = 12-bit absolute position + (length - 3).")
def _(ctx):
    cases, recs = direct_run(ctx)
    for c, rec in zip(cases, recs):
        if c["tag"] not in ("decode_ok", "decode_real"):
            continue
        dst_size = c["args"][3]
        out = bytes.fromhex(rec["reads"][1])
        want = next((o for n, s, o in DECODE_GOOD if n == c["name"]), None)
        if want is None:
            want = b"".join(reference(ctx)[0])
        expect_eq(s32(rec["v0"]), 0, f"lzss_decode accepts: {c['name']}", hint="Return TPK_OK (0); -5 is TPK_ERR_DATA.")
        if out != want:
            first = next((i for i in range(len(want)) if out[i] != want[i]), 0)
            raise CheckFailure(expected=f"{c['name']}: {len(want)} correct bytes", actual=f"first difference at output byte {first}: got 0x{out[first]:02X}, want 0x{want[first]:02X}",
                               hint="Wrong ring start (4078)? Absolute position read as a distance? Flag bits MSB first? A zero ring not zeroed?")
        guards_ok(rec, c, dst_size)


@check("lzss_decode: damaged streams are rejected with TPK_ERR_DATA (-5); nothing is written outside dst, nothing is read past src_size",
       hint="Check before every read: a flag byte, a literal, both bytes of a reference; and before every write: len <= dst_size - o. Return TPK_ERR_DATA.")
def _(ctx):
    cases, recs = direct_run(ctx)
    for c, rec in zip(cases, recs):
        if c["tag"] != "decode_bad":
            continue
        expect_eq(s32(rec["v0"]), -5, f"lzss_decode rejects: {c['name']}", hint="Return TPK_ERR_DATA (-5).")
        guards_ok(rec, c, c["args"][3])


@check("tpk_crc32: zlib's CRC-32 for \"123456789\", nothing, 1000 bytes, an odd address, the real textures",
       hint="Reflected polynomial 0xEDB88320, start 0xFFFFFFFF, final complement; process bytes (the pointer may be odd).")
def _(ctx):
    cases, recs = direct_run(ctx)
    for c, rec in zip(cases, recs):
        if c["tag"] != "crc":
            continue
        expect_eq(rec["v0"], zlib.crc32(c["data"]) & 0xFFFFFFFF, f"tpk_crc32 of {c['name']}", fmt="hex")


@check("tpk_parse: good headers (padding 0..3) fill the struct; damaged ones return TPK_ERR_MAGIC / TPK_ERR_HEADER as tpk.h says",
       hint="The checks of tpk.h in order: magic, fixed header, count, size table inside the file, each size, the sum, raw_size, comp_size, the end of the file.")
def _(ctx):
    cases, recs = direct_run(ctx)
    for c, rec in zip(cases, recs):
        if c["tag"] == "parse_ok":
            expect_eq(s32(rec["v0"]), 0, f"{c['name']}: returns TPK_OK", hint="TPK_ERR_MAGIC -2, TPK_ERR_HEADER -3: see tpk.h.")
            h = bytes.fromhex(rec["reads"][0])
            d = formats.parse_tpk(pack_bytes(reference(ctx)[0][:3]))
            expect_eq(list(struct.unpack_from("<4I", h, 0)), [3, d["raw_size"], d["comp_size"], d["crc32"]],
                      f"{c['name']}: count, raw_size, comp_size, crc32", hint="Little-endian u32 fields at 0x04, 0x08, 0x0C, 0x10.")
            expect_eq(list(struct.unpack_from("<3I", h, 16)), d["sizes"], f"{c['name']}: sizes[0..2]", hint="Copied from the table at 0x14.")
            expect_eq(struct.unpack("<I", bytes.fromhex(rec["reads"][1]))[0], SRC + 20 + 12, f"{c['name']}: stream points at 0x14 + 4 * count in the file image", fmt="hex")
        elif c["tag"] == "parse_bad":
            expect_eq(s32(rec["v0"]), c["want"], f"{c['name']}: return code", hint="See tpk.h: TPK_ERR_MAGIC -2, TPK_ERR_HEADER -3.")


@check("tpk_unpack: good packs fill dst exactly (writes only raw_size bytes); too small a buffer, bad magic, bad CRC, damaged stream are errors",
       hint="parse, then dst_size >= raw_size (TPK_ERR_SPACE, nothing written), then lzss_decode, then the CRC-32 (TPK_ERR_CRC).")
def _(ctx):
    cases, recs = direct_run(ctx)
    for c, rec in zip(cases, recs):
        if c["tag"] != "unpack":
            continue
        want, dst_size, raw = c["want"], c["dst_size"], c["raw"]
        code = s32(rec["v0"])
        if c["name"].find("damaged byte") >= 0:
            expect_true(code in (-5, -6), f"{c['name']}: error code", f"{code}", hint="TPK_ERR_DATA (-5) or TPK_ERR_CRC (-6).")
        else:
            expect_eq(code, want, f"{c['name']}: return code", hint="TPK_OK 0, MAGIC -2, HEADER -3, DATA -5, CRC -6, SPACE -8.")
        guards_ok(rec, c, dst_size)
        out = bytes.fromhex(rec["reads"][1])
        if want == 0:
            expect_eq(out[:len(raw)], raw, f"{c['name']}: dst holds the TIMs", hint="lzss_decode wrote the wrong bytes.")
            expect_eq(out[len(raw):], bytes([FILL]) * (dst_size - len(raw)), f"{c['name']}: bytes after raw_size are untouched",
                      hint="Decode exactly raw_size bytes.")
        if want == -8:
            expect_eq(out, bytes([FILL]) * dst_size, f"{c['name']}: nothing was written", hint="Check dst_size before decoding.")


@check("tpk_load: a missing file returns TPK_ERR_READ with count 0 and raw NULL; loading the shipped pack again works; tpk_free_raw clears raw",
       hint="Set out->count = 0 and out->raw = NULL first; cd_load_file returns NULL for a missing file; free what you hold on every error path.")
def _(ctx):
    cases, recs = direct_run(ctx)
    by = {c["tag"]: (c, rec) for c, rec in zip(cases, recs) if c["tag"] in ("load_missing", "load_again", "free")}
    c, rec = by["load_missing"]
    expect_eq(s32(rec["v0"]), -1, "tpk_load of a missing file: return code", hint="TPK_ERR_READ (-1).")
    head = struct.unpack("<iII", bytes.fromhex(rec["reads"][0]))
    expect_eq((head[0], head[1], head[2]), (0, 0, 0), "after the failure: count 0, raw NULL, raw_size 0", hint="Initialise *out before anything can fail.")
    c, rec = by["load_again"]
    expect_eq(s32(rec["v0"]), 0, "tpk_load of \\DATA\\TEXTURES.TPK;1 a second time", hint="A second load must work (no static state left over, nothing leaked).")
    data = bytes.fromhex(rec["reads"][0])
    count, rawp, rawsz = struct.unpack_from("<iII", data, 0)
    tims, _ = reference(ctx)
    expect_eq(count, 8, "store.count after the second load")
    expect_true(0x80000000 <= rawp < 0x80200000, "store.raw is a RAM address", f"0x{rawp:08X}")
    expect_eq(rawsz, sum(len(t) for t in tims), "store.raw_size")
    expect_eq(list(struct.unpack_from("<48H", data, 12)), [v for t in tims for v in describe(t)], "store.tex[] after the second load", fmt="dec")
    c, rec = by["free"]
    head = struct.unpack("<iII", bytes.fromhex(rec["reads"][0]))
    expect_eq((head[1], head[2]), (0, 0), "tpk_free_raw sets raw to NULL and raw_size to 0")
    expect_eq(head[0], 8, "tpk_free_raw leaves count (the textures are in VRAM and tex[] stays valid)")
