"""Chapter 42 checks: Shipping It (a release build, the disc image, region handling, the release papers).

Build: `make release` (the reader's target) -> release/. The emulator BOOTS release/hoverline.cue; symbols come from release/hoverline.elf.

What is checked, and how:
  release folder   the files named in README 5.1; SHA256SUMS agrees with them
  disc image       the .cue (data track + one audio track) and the .bin are parsed here with a small ISO 9660 reader (no external tool): PVD identifiers, the root
                   directory, SYSTEM.CNF, HOVER.EXE, every asset BYTE-EXACT against what tools/assets generates, the audio track against MUSIC.WAV, no Sony license data
  MANIFEST.txt     every file on the disc, sha256 and size
  reproducible     the project is copied (without build output) to a fresh directory and `make release` is run again there, with another time zone: the .bin, .cue and
                   MANIFEST.txt must be byte-identical to the first build
  NOTICES.TXT      on the disc, in release/, and mentioning every shipped file; RELEASE.md has one section per emulator with an honest Status line
  play (NTSC)      the release disc boots, the countdown takes count_from * 60 ticks, the game plays, the debug keys and the debug readout are gone
  play (PAL)       the same with the GPU put in PAL mode just before main (probe.lua: GP1(08h), what a PAL BIOS leaves behind): the program has to detect it
                   (video_mode, dt_scale, a 150-tick countdown)
NOT checked here (no headless mode, or no hardware): DuckStation, Mednafen, a real console. A note is printed; RELEASE.md is where you record them."""

import atexit
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from harness import *
import harness as _h

ROOT_DIR = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR / "tools" / "assets"))
import mkassets      # noqa: E402

config(
    title="Shipping It: release build, disc image, region handling, release papers",
    build=["make", "release"], exe="", sym="", elf="release/hoverline.elf", iso="release/hoverline.cue",
    break_at=None, max_frames=1500, timeout=240,
)

_TMP = Path(tempfile.mkdtemp(prefix="ch42ref-"))
atexit.register(shutil.rmtree, _TMP, True)
FILES, _MAN = mkassets.build(_TMP / "assets", seed=1, music=True)   # what the generators make: the reference for the disc's contents
DATA_FILES = ["LOGO.TIM", "PROPS.TPK", "PYLON.SHP", "ARCH.SHP", "TOWER.SHP", "SCENE.BIN", "TRACK.TRK", "TRACK2.TRK", "TRACK.TPK", "SHIP.SHP", "SHIP.TPK",
              "ENGINE.VAG", "BOOST.VAG", "THUD.VAG", "BEEP.VAG", "GO.VAG"]
NOTE = ("[ch42 note] DuckStation and Mednafen were NOT run: neither has a headless mode that can be scripted here, and a check that cannot run is not faked. "
        "Record what you saw with them in RELEASE.md.")
print(NOTE)

SECT = 2352
RELEASE_FILES = ["hoverline.bin", "hoverline.cue", "hoverline.elf", "MANIFEST.txt", "SHA256SUMS", "NOTICES.TXT", "RELEASE.md"]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rel(ctx):
    return ctx.project / "release"


def need(path, hint):
    if not path.is_file():
        raise CheckFailure(expected=f"{path.parent.name}/{path.name} exists", actual="missing", hint=hint)
    return path


# ---------------------------------------------------------------------------------------------------------------------------------------
# A small ISO 9660 reader for MODE2/2352 images (data lives at +24 of a Form 1 sector)
# ---------------------------------------------------------------------------------------------------------------------------------------
class Disc:
    def __init__(self, data):
        self.d = data
        if len(data) % SECT:
            raise CheckFailure(expected="a .bin whose size is a multiple of 2352 (raw sectors)", actual=f"{len(data)} bytes", hint="The data track is MODE2/2352.")
        self.sectors = len(data) // SECT

    def sector(self, lba):
        o = lba * SECT
        if o + SECT > len(self.d):
            raise CheckFailure(expected=f"sector {lba} inside the image", actual=f"image has {self.sectors} sectors")
        return self.d[o:o + SECT]

    def read(self, lba, size):
        out = bytearray()
        for i in range((size + 2047) // 2048):
            out += self.sector(lba + i)[24:24 + 2048]
        return bytes(out[:size])

    def pvd(self):
        s = self.sector(16)
        if s[:12] != b"\x00" + b"\xff" * 10 + b"\x00" or s[15] != 2:
            raise CheckFailure(expected="sector 16 is a raw MODE 2 sector", actual=f"header {s[:16].hex()}")
        p = s[24:24 + 2048]
        if p[0] != 1 or p[1:6] != b"CD001":
            raise CheckFailure(expected="a primary volume descriptor at sector 16", actual=p[:8].hex())
        return p

    @staticmethod
    def records(blob):
        pos = 0
        while pos < len(blob):
            n = blob[pos]
            if n == 0:
                pos = (pos // 2048 + 1) * 2048
                continue
            r = blob[pos:pos + n]
            name = r[33:33 + r[32]]
            yield dict(name=name, flags=r[25], lba=struct.unpack_from("<I", r, 2)[0], size=struct.unpack_from("<I", r, 10)[0])
            pos += n

    def listing(self, lba, size, prefix=""):
        """{path: (lba, size)} of every file below the directory (names without ;1, upper case)."""
        out = {}
        for r in self.records(self.read(lba, size)):
            if r["name"] in (b"\x00", b"\x01"):
                continue
            nm = r["name"].decode("ascii", "replace")
            if r["flags"] & 2:
                out.update(self.listing(r["lba"], r["size"], prefix + nm + "/"))
            else:
                out[prefix + nm.split(";")[0]] = (r["lba"], r["size"])
        return out

    def files(self):
        p = self.pvd()
        root = struct.unpack_from("<II", p, 156 + 2)[0], struct.unpack_from("<I", p, 156 + 10)[0]
        return self.listing(*root)

    def file(self, path):
        f = self.files().get(path)
        if f is None:
            raise CheckFailure(expected=f"{path} on the disc", actual="not found", hint="List of files: " + ", ".join(sorted(self.files())))
        return self.read(*f)


_disc_cache = {}


def disc(ctx):
    b = need(rel(ctx) / "hoverline.bin", "make release must leave the image in release/.")
    key = (b, b.stat().st_mtime_ns)
    if key not in _disc_cache:
        _disc_cache[key] = Disc(b.read_bytes())
    return _disc_cache[key]


def msf(s):
    m, sec, f = (int(x) for x in s.split(":"))
    return (m * 60 + sec) * 75 + f


def cue_tracks(text):
    tracks, cur, fname = [], None, None
    for line in text.splitlines():
        t = line.split()
        if not t:
            continue
        if t[0] == "FILE":
            fname = re.search(r'"([^"]*)"', line).group(1)
        elif t[0] == "TRACK":
            cur = dict(num=int(t[1]), mode=t[2], index={}, file=fname)
            tracks.append(cur)
        elif t[0] == "INDEX" and cur is not None:
            cur["index"][int(t[1])] = msf(t[2])
    return tracks


# ---------------------------------------------------------------------------------------------------------------------------------------
@static_check("release folder: the files of README 5.1, and SHA256SUMS agrees with them",
              hint="`make release` leaves hoverline.bin, hoverline.cue, hoverline.elf, MANIFEST.txt, SHA256SUMS, NOTICES.TXT and RELEASE.md in release/. "
                   "SHA256SUMS is in `sha256sum -c` format (hash, two spaces, name) for every other file there.")
def _(ctx):
    r = rel(ctx)
    missing = [n for n in RELEASE_FILES if not (r / n).is_file()]
    expect_true(not missing, "all files present", "missing: " + ", ".join(missing))
    sums = {}
    for line in (r / "SHA256SUMS").read_text().splitlines():
        m = re.fullmatch(r"([0-9a-f]{64}) [ *](\S+)", line.strip())
        expect_true(m, "lines of the form '<64 hex>  <name>'", repr(line))
        sums[m.group(2)] = m.group(1)
    for n in RELEASE_FILES:
        if n == "SHA256SUMS":
            continue
        expect_true(n in sums, f"{n} listed in SHA256SUMS", "not listed")
        expect_eq(sums[n], sha((r / n).read_bytes()), f"hash of {n}")


@static_check("cue sheet: one data track, one audio track, both inside the .bin",
              hint="The cue sheet names hoverline.bin (relative), TRACK 01 MODE2/2352 with INDEX 01 00:00:00, TRACK 02 AUDIO with its INDEX 01 inside the image.")
def _(ctx):
    cue = need(rel(ctx) / "hoverline.cue", "release/hoverline.cue")
    tr = cue_tracks(cue.read_text())
    expect_eq([t["num"] for t in tr], [1, 2], "tracks in the cue sheet")
    expect_eq(tr[0]["mode"], "MODE2/2352", "track 1 mode")
    expect_eq(tr[0]["index"].get(1), 0, "track 1 INDEX 01")
    expect_eq(tr[1]["mode"], "AUDIO", "track 2 mode")
    for t in tr:
        expect_eq(t["file"], "hoverline.bin", "FILE of track %d" % t["num"], hint="A relative name, so the pair can be moved or zipped.")
    d = disc(ctx)
    expect_true(1 in tr[1]["index"] and tr[1]["index"][1] < d.sectors, "track 2 INDEX 01 inside the .bin", f"{tr[1]['index']} of {d.sectors} sectors")
    wav = FILES["MUSIC.WAV"]
    pos = wav.find(b"data")
    n = struct.unpack_from("<I", wav, pos + 4)[0]
    pcm = wav[pos + 8:pos + 8 + n]
    start = tr[1]["index"][1] * SECT
    expect_true(d.d[start:start + n] == pcm, "the audio track holds MUSIC.WAV's samples", "different bytes",
                hint="The CD-DA track is the generated music, unchanged (mkassets.py --music).")


@static_check("disc image: identifiers, SYSTEM.CNF, HOVER.EXE, the copyright file",
              hint="PVD system and application identifiers read PLAYSTATION; SYSTEM.CNF has BOOT = cdrom:\\HOVER.EXE;1; the copyright identifier names a file that exists in the root.")
def _(ctx):
    d = disc(ctx)
    p = d.pvd()
    sysid, appid = p[8:40].decode("ascii").strip(), p[574:702].decode("ascii").strip()
    vol = p[40:72].decode("ascii").strip()
    expect_eq(sysid, "PLAYSTATION", "system identifier")
    expect_eq(appid, "PLAYSTATION", "application identifier")
    expect_true(re.fullmatch(r"[A-Z0-9_]{1,32}", vol or "-"), "a volume identifier of capitals, digits and _", repr(vol))
    files = d.files()
    cnf = d.file("SYSTEM.CNF").decode("ascii", "replace")
    boot = None
    for line in cnf.replace("\r", "\n").split("\n"):
        k, _, v = line.partition("=")
        if k.strip().upper() == "BOOT":
            boot = v.strip()
    expect_true(boot, "a BOOT line in SYSTEM.CNF", repr(cnf))
    m = re.fullmatch(r"cdrom:\\?([A-Z0-9_.]+);1", boot, re.I)
    expect_true(m, r"BOOT = cdrom:\NAME.EXE;1", repr(boot))
    exe = d.file(m.group(1).upper())
    expect_true(exe[:8] == b"PS-X EXE", "the boot file is a PS-X EXE", exe[:8])
    expect_eq(len(exe), 0x800 + struct.unpack_from("<I", exe, 0x1C)[0], "HOVER.EXE size = 2048 + the header's text size", hint="No padding or leftovers.")
    cr = p[702:739].decode("ascii").strip()
    expect_true(cr, "a copyright file identifier", "empty", hint="Name your NOTICES.TXT there.")
    expect_true(cr.split(";")[0].upper() in files, f"the copyright identifier {cr!r} names a file in the root", "no such file",
                hint="An identifier that points nowhere is a bug a licensing tool will find before you do.")


@static_check("disc image: every asset is there, byte for byte what the generators make",
              hint="DATA\\ holds the 16 generated assets, unchanged: the disc is built from the generator's output, never from a stale copy.")
def _(ctx):
    d = disc(ctx)
    for n in DATA_FILES:
        got = d.file("DATA/" + n)
        expect_true(got == FILES[n], f"DATA/{n} equals the generated file ({len(FILES[n])} bytes)", f"{len(got)} bytes, different content")


@static_check("disc image: no Sony license data, no Sony text",
              hint="The system area (LBA 0-15; the license text is in 4, the logo in 5-11) is Sony's on a retail disc: the book's image leaves it all zero, and no file "
                   "but NOTICES.TXT (which may name Sony to disclaim it) carries Sony's license text. A retail console needs a modchip or an ODE; emulators do not care.")
def _(ctx):
    d = disc(ctx)
    used = [i for i in range(16) if any(d.sector(i)[24:24 + 2048])]
    expect_true(not used, "a system area (sectors 0-15) of zeros", f"data in sector(s) {used}")
    raw = bytearray(d.d.lower())
    f = d.files().get("NOTICES.TXT")
    if f:                                     # the notice is allowed to say "not licensed by Sony Computer Entertainment"
        lba, size = f
        raw[lba * SECT:(lba + (size + 2047) // 2048) * SECT] = bytes((size + 2047) // 2048 * SECT)
    for needle in (b"sony computer entertainment", b"licensed by"):
        expect_true(raw.find(needle) < 0, f"no {needle.decode()!r} (any case) in the image outside NOTICES.TXT", f"found at byte {raw.find(needle)}")


@static_check("MANIFEST.txt lists every file on the disc with its sha256 and size",
              hint="One line per file: sha256, size in bytes, path (DATA/LOGO.TIM or DATA\\LOGO.TIM). Derive it from the build, never by hand.")
def _(ctx):
    d = disc(ctx)
    lines = (need(rel(ctx) / "MANIFEST.txt", "MANIFEST.txt")).read_text().splitlines()
    got = {}
    for ln in lines:
        t = ln.split()
        if not t:
            continue
        expect_true(len(t) == 3 and re.fullmatch(r"[0-9a-f]{64}", t[0]) and t[1].isdigit(), "'<sha256> <size> <path>' per line", repr(ln))
        got[t[2].replace("\\", "/").lstrip("/").split(";")[0].upper()] = (t[0], int(t[1]))
    for path, (lba, size) in sorted(d.files().items()):
        expect_true(path.upper() in got, f"{path} in MANIFEST.txt", "missing")
        data = d.read(lba, size)
        expect_eq(got[path.upper()], (sha(data), size), f"manifest entry of {path}")


@static_check("NOTICES.TXT: on the disc and in release/, names every shipped file and disclaims Sony",
              hint="Say what every file is and where it came from (generator scripts), which software it was built with, and that the disc is not licensed by or affiliated with Sony.")
def _(ctx):
    d = disc(ctx)
    on_disc = d.file("NOTICES.TXT")
    expect_true(on_disc == need(rel(ctx) / "NOTICES.TXT", "release/NOTICES.TXT").read_bytes(), "release/NOTICES.TXT equals the file on the disc", "they differ")
    text = on_disc.decode("utf-8", "replace")
    expect_true(len(text.split()) >= 80, "a real notice (at least 80 words)", f"{len(text.split())} words")
    expect_true("TODO" not in text.upper(), "no TODO left", "TODO found")
    names = {Path(p).name.upper() for p in d.files()} - {"SYSTEM.CNF", "NOTICES.TXT"}
    low = text.upper()
    miss = sorted(n for n in names if n not in low and ("*" + os.path.splitext(n)[1]) not in low)
    expect_true(not miss, "every other file on the disc named (a group may be written '*.VAG')", "not named: " + ", ".join(miss))
    expect_true(re.search(r"\bnot\s+(licensed|licenced|endorsed|published|approved|affiliated)", text, re.I), "a statement that the disc is not licensed / endorsed by Sony",
                "no such sentence")
    expect_true(re.search(r"original|generated|synthesi[sz]ed", text, re.I), "the origin of the content (original / generated)", "not stated")
    expect_true(re.search(r"PSn00bSDK", text), "the SDK named (and its license obligations met)", "PSn00bSDK is not mentioned")


@static_check("RELEASE.md: a section per emulator, honest status lines",
              hint="Sections 'PCSX-Redux', 'DuckStation', 'Mednafen' and 'Real hardware', each with a line 'Status: tested' or 'Status: not tested' and notes: the version and what you saw if tested, why not if not.")
def _(ctx):
    src = need(ctx.project / "RELEASE.md", "RELEASE.md in the project root")
    expect_true(src.read_bytes() == need(rel(ctx) / "RELEASE.md", "release/RELEASE.md").read_bytes(), "release/RELEASE.md is a copy of RELEASE.md", "they differ")
    text = src.read_text()
    expect_true("TODO" not in text.upper(), "no TODO left", "TODO found")
    parts = re.split(r"(?m)^#{2,3}\s+", text)
    secs = {}
    for p in parts[1:]:
        title, _, body = p.partition("\n")
        secs[title.strip().lower()] = body
    for want in ("pcsx-redux", "duckstation", "mednafen", "real hardware"):
        key = next((k for k in secs if want in k), None)
        expect_true(key is not None, f"a section about {want}", "headings: " + ", ".join(secs))
        body = secs[key]
        m = re.search(r"(?im)^\s*\**status\**\s*:\s*\**\s*(not tested|tested)\b", body)
        expect_true(m, f"'Status: tested' or 'Status: not tested' in the {want} section", "no Status line")
        words = len(re.sub(r"(?im)^\s*\**status.*$", "", body).split())
        if m.group(1).lower() == "tested":
            expect_true(words >= 20 and re.search(r"\d", body), f"{want}: a version and what happened (20 words, a number)", f"{words} words")
        else:
            expect_true(words >= 10, f"{want}: say why it was not tested (10 words)", f"{words} words")


# ---------------------------------------------------------------------------------------------------------------------------------------
def _fresh_build(project, tag, tz):
    dst = _TMP / tag
    shutil.copytree(project, dst, ignore=shutil.ignore_patterns("build", "build-release", "release", ".git", "__pycache__"))
    env = _h.tool_env()
    env["TZ"] = tz
    env["LC_ALL"] = "C"
    p = subprocess.run(["make", "release"], cwd=dst, env=env, capture_output=True, text=True, timeout=300)
    if p.returncode:
        raise CheckFailure(expected="`make release` works from a clean copy of the project", actual="failed:\n" + (p.stdout + p.stderr)[-1500:],
                           hint="A build that only works next to leftovers of an earlier build is not a release build.")
    return dst / "release"


@static_check("reproducible: a clean copy, another directory, another time zone: identical .bin, .cue and MANIFEST.txt",
              hint="mkpsxiso stamps the volume with the time of the build and every file with its modification time unless the project file fixes them. "
                   "The SDK's bundled mkpsxiso is older than the pinned one and ignores the date attribute of files and directories. Compare two builds with cmp.")
def _(ctx):
    stale = sorted(str(p.relative_to(ctx.project)) for p in ctx.project.rglob("*")
                   if p.is_file() and p.suffix.lower() in (".bin", ".cue", ".iso", ".img", ".exe", ".elf", ".ps-exe")
                   and not {"build", "build-release", "release"} & set(p.relative_to(ctx.project).parts))
    expect_true(not stale, "no prebuilt image or executable in the source tree", ", ".join(stale),
                hint="`make release` must make the release from sources and the generators, in a clean checkout.")
    other = _fresh_build(ctx.project, "repro", "Pacific/Auckland")
    for n in ("hoverline.bin", "hoverline.cue", "MANIFEST.txt"):
        a, b = (rel(ctx) / n).read_bytes(), (other / n).read_bytes()
        if a != b:
            where = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), min(len(a), len(b)))
            raise CheckFailure(expected=f"{n} identical in two builds", actual=f"differs (first difference at byte {where} of {len(a)}"
                               + (f", sector {where // SECT}, offset {where % SECT}" if n.endswith("bin") else "") + ")")


# ---------------------------------------------------------------------------------------------------------------------------------------
def _params(ctx, name, params):
    f = ctx.work / f"params_{name}.lua"
    f.write_text("PARAMS = " + _h._lua_literal(params) + "\n")
    g = ctx.work / f"probe_{name}.lua"
    g.write_text(f"dofile({str(f)!r})\ndofile({str(HERE / 'probe.lua')!r})\n")
    return g


_def = _TMP / "params_ntsc.lua"
_def.write_text("PARAMS = {race_frames = 90}\n")
os.environ["CH42_PARAMS"] = str(_def)

_runs = {}


def run_of(ctx, pal):
    if pal not in _runs:
        r = ctx.run("pal", probe=_params(ctx, "pal", {"pal": True, "race_frames": 90}), max_frames=1500) if pal else ctx.result
        r.require_finished()
        exc = r.records.get("exception")
        if exc:
            raise CheckFailure(expected="no CPU exception", actual=f"exception {exc['code']} at pc 0x{exc['epc']:08X}, address 0x{exc['badvaddr']:08X}")
        rows = r.records.get("rows") or []
        expect_true(rows, "a game that reaches the countdown", "the title never ended", hint="Does the release disc boot? (Run it: make release && pcsx-redux -iso release/hoverline.cue)")
        _runs[pal] = r
    return _runs[pal]


def analyse(r, pal):
    rows, info = r.records["rows"], r.records["info"]
    hz = 50 if pal else 60
    first_cd = next(i for i, x in enumerate(rows) if x["state"] == 1)
    race_i = next((i for i, x in enumerate(rows) if x["state"] == 2), None)
    return rows, info, hz, first_cd, race_i


def boot_checks(ctx, pal):
    r = run_of(ctx, pal)
    rows, info, hz, first_cd, race_i = analyse(r, pal)
    expect_eq(info.get("load_status"), 0, "load_status (everything loaded from the release disc)", hint="A red screen or a stuck title: a file missing from the disc?")
    expect_eq(info.get("video_mode"), 1 if pal else 0, "video_mode on a " + ("PAL" if pal else "NTSC") + " console",
              hint="Ask the GPU what the console is, once, at the start of main (README 5.4).")
    expect_eq(info.get("dt_scale"), 4915 if pal else 4096, "dt_scale (the time-step factor: 60 / 50 in 4.12 for PAL)")
    expect_true(race_i is not None, "the countdown ends in the race", "state never became RACE (2)")
    ticks = sum(x["ticks"] for x in rows[first_cd + 1:race_i + 1])
    want = 3 * hz
    expect_true(want <= ticks <= want + 3, f"a countdown of {want} ticks (3 s at {hz} Hz)", f"{ticks} ticks",
                hint="Time is counted in ticks and race_hz() is 50 on PAL: if the program thinks it is NTSC the countdown is 20% too long.")
    return rows, race_i


def play_checks(ctx, pal):
    rows, race_i = boot_checks(ctx, pal)
    race = rows[race_i:]
    expect_true(len(race) >= 60, "at least 60 frames of race recorded", f"{len(race)}")
    expect_true(max(x["speed"] for x in race) > 0, "the ship accelerates when X is held", "speed stayed 0")
    expect_true(all(x["text"] for x in race[2:]), "the race HUD (race_text) is drawn", "empty text")


@check("play on an NTSC console: boots, countdown 180 ticks, race", hint="The release disc must boot and play like the development disc.")
def _(ctx):
    play_checks(ctx, False)


@check("play on a PAL console: region detected, countdown 150 ticks, race",
       hint="The GPU is in PAL mode when main starts, as a PAL BIOS leaves it. video_mode must come from the console (README 5.4), not from a constant.")
def _(ctx):
    play_checks(ctx, True)


def white_count(img, x0, y0, x1, y1):
    n = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            if min(img.pixel(x, y)) >= 220:
                n += 1
    return n


@check("release build: the debug keys do nothing", hint="Select (wireframe), Triangle (subdivision outlines) and R1 (subdivision) are development tools: compile them out of the release (HOVERLINE_RELEASE).")
def _(ctx):
    rows, race_i = boot_checks(ctx, False)
    expect_true(race_i is not None and len(rows) > race_i + 40, "a race long enough to press the keys in", "too short")
    for k in ("wire", "dbg", "sub"):
        expect_true(all(x[k] == 0 for x in rows), f"{ {'wire': 'wire_mode', 'dbg': 'subdiv_debug', 'sub': 'subdiv_enabled'}[k] } stays 0 while the keys are pressed",
                    "it changed")


@check("release build: no debug readout on the screen, the race HUD still there",
       hint="The SEC / PRIMS and edge-distance lines at the top left are for development. Leave them out of the release (and do not format them either).")
def _(ctx):
    _rows, _race_i = boot_checks(ctx, False)
    img = ctx.result.screenshot("race")
    top = white_count(img, 8, 8, 8 + 22 * 8, 8 + 22)           # where the two readout lines are drawn in development
    hud = white_count(img, 8, 44, 8 + 20 * 8, 44 + 12)         # the first line of the race text
    expect_true(hud >= 20, "the race text visible at (8, 44)", f"{hud} white pixels there")
    expect_true(top <= 8, "no readout text at (8, 8)", f"{top} white pixels in the readout area")
