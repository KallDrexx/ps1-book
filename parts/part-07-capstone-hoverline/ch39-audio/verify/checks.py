"""Chapter 39 checks: Audio (SPU samples, engine pitch, events, CD music).
Build: CMake + PSn00bSDK; the CMake rule runs tools/assets/mkassets.py --music. The emulator BOOTS THE .cue.

HOW THE SPU IS OBSERVED (README 5.9). Lua cannot read the SPU's registers, so probe.lua puts a write breakpoint on 0x1F801C00..0x1F801DFF and on the CD controller's four
registers (0x1F801800..03): for each store it records the value (the register the store instruction names) and the index of the pose it belongs to. checks.py replays that
log (example/audio_ref.py: Replay) to know every voice register at every key-on, every key-off and every CD command. SPU RAM is read at the end of the run from an SPU dump
that PCSX-Redux writes (PCSX.SPU.Logger.exportSPD).
HOW THE RUN IS DRIVEN (README 5.9): the probe writes a pose (position, speed) into `ship` at the end of every frame; START enters the game. The expected key-ons come from the
Python model: the event rules of README 5.6 over the section sequence of the poses, the pitch formula of README 5.5.
Runs: main (track 1, the generated sounds), alt (the same script with ENGINE/BOOST/THUD at other sample rates and other audio_cfg values: nothing may be hard-coded),
loop (an idle run long enough for the CD track to end)."""

import atexit
import json
import math
import os
import shutil
import struct
import sys
import tempfile
import zlib
from pathlib import Path

from harness import *

ROOT_DIR = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR / "tools" / "assets"))
sys.path.insert(0, str(HERE.parent / "example"))
import mkassets      # noqa: E402
import formats       # noqa: E402
import audio_ref as M  # noqa: E402

MAX_FRAMES = 1500
SAMPLES = ["ENGINE", "BOOST", "THUD", "BEEP", "GO"]
SMP = {n: i for i, n in enumerate(SAMPLES)}
CAP = 60 * 4096
DEFAULT_CFG = dict(idle_mul=2048, span_mul=6400, engine_vol=0x1800, sfx_vol=0x3000, music_track=2, music_vol=0x6000)
CFG_OFF = {k: 4 * i for i, k in enumerate(["idle_mul", "span_mul", "engine_vol", "sfx_vol", "music_track", "music_vol"])}
ALT_CFG = dict(idle_mul=3000, span_mul=4000, engine_vol=0x1000, sfx_vol=0x2200, music_track=2, music_vol=0x5000)
ALT_RATES = {"ENGINE": 16000, "BOOST": 32000, "THUD": 11025}

config(
    title="Audio: SPU samples, engine pitch, events, CD music",
    build="cmake", exe="game.exe", sym="", elf="game.elf", iso="hoverline.cue",
    break_at=None, max_frames=MAX_FRAMES, timeout=420,
)

_TMP = Path(tempfile.mkdtemp(prefix="ch39ref-"))
atexit.register(shutil.rmtree, _TMP, True)
FILES, MANIFESTS = mkassets.build(_TMP / "assets", seed=1, music=True)
TRK = formats.parse_trk(FILES["TRACK.TRK"])
MAN = MANIFESTS["TRACK.TRK"]
SECS = TRK["sections"]
N = len(SECS)
BOOST = MAN["boost_sections"]


def vag_blocks(data):
    return data[48:]


def with_rate(data, rate):
    return data[:16] + struct.pack(">I", rate) + data[20:]


ALT_FILES = {n + ".VAG": with_rate(FILES[n + ".VAG"], r) for n, r in ALT_RATES.items()}


# ---- the scripted run --------------------------------------------------------------------------------------------------------------------------
def heading(dx, dz):
    """The nose heading in whole units (0 along +z, 1024 along +x): only used to point the posed ship along the track."""
    return int(round(math.atan2(dx, dz) * 2048 / math.pi)) % 4096


def interp(u, lat, hover=120):
    i0 = math.floor(u)
    f = u - i0
    a, b = SECS[i0 % N], SECS[(i0 + 1) % N]
    near = SECS[round(u) % N]
    p = []
    for k in range(3):
        c = a["centre"][k] + (b["centre"][k] - a["centre"][k]) * f
        c += (near["right"][k] * lat) / 4096 + (near["up"][k] * hover) / 4096
        p.append(round(c))
    d = [b["centre"][k] - a["centre"][k] for k in range(3)]
    return p, heading(d[0], d[2])


def make_poses(script):
    """script items: ('at', u, lat, speed, count) | ('run', u0, u1, step, lat_fn_or_const) | ('speeds', list_of_speeds) | ('flip', n)."""
    out = []

    def add(u, lat, speed=0, kind=""):
        p, yaw = interp(u, lat)
        out.append(dict(x=p[0], y=p[1], z=p[2], speed=speed, yaw=yaw, kind=kind, u=u, lat=lat))

    for it in script:
        if it[0] == "at":
            _, u, lat, speed, cnt = it
            for _ in range(cnt):
                add(u, lat, speed, "at")
        elif it[0] == "run":
            _, u0, u1, step, lat = it
            k, u = 0, u0
            while (u - u1) * (1 if step > 0 else -1) < 0:
                add(u, lat(k) if callable(lat) else lat, 0, "run")
                u += step
                k += 1
        elif it[0] == "speeds":
            for s in it[2]:
                add(it[1], 0, s, "speed")
    return out


def sweep():
    up = [min(CAP, round(k * CAP / 60) + (k * 37) % 255) for k in range(61)]
    up[-1] = CAP
    down = [min(CAP, round(k * CAP / 60) + (k * 53) % 255) for k in range(60, -1, -3)]
    down[-1] = 0
    return up, down


def script_events():
    s = []
    s += [("at", 0, 0, 0, 4)]                                                    # on the start line: nothing happens
    s += [("at", 22, 0, 0, 2), ("run", 22, 31, 0.5, 0)]                          # teleport, then through the first boost pad (sections 28, 29)
    s += [("at", 70, 150, 0, 2), ("run", 70, 79, 0.5, lambda k: 150 * math.sin(k * 0.5))]   # the second pad (76, 77), swaying inside the road
    s += [("at", 40, 0, 0, 2), ("at", 40, 700, 0, 3), ("at", 40, 0, 0, 2), ("at", 40, -700, 0, 3), ("at", 40, 0, 0, 2)]   # off the right edge, back, off the left edge
    s += [("at", 40, 595, 0, 2), ("at", 40, 640, 0, 2), ("at", 40, 580, 0, 1)]   # just inside, just outside (|lateral| > half_width: 600)
    s += [("run", 40, 44, 0.5, 800), ("at", 44, 0, 0, 2)]                        # drive along OUTSIDE the road across sections: one thud only
    s += [("at", 10, 900, 0, 1), ("at", 50, 900, 0, 2), ("at", 50, 0, 0, 2)]    # off-road, teleport while off-road (no second thud), back
    s += [("at", 55, 0, 0, 1)]
    for i in range(14):                                                           # a thud on every other frame: more than 23 one-shots, the voices wrap
        s += [("at", 55, 900, 0, 1), ("at", 55, 0, 0, 1)]
    s += [("at", 29, 0, 0, 3), ("at", 60, 0, 0, 2), ("at", 77, 0, 0, 5), ("at", 60, 0, 0, 2), ("at", 28, 0, 0, 2)]   # teleports onto the pads and a hold on one
    s += [("at", 20, 0, 0, 2)]
    return s


def script_main():
    up, down = sweep()
    s = script_events()
    s += [("at", 10, 0, 0, 3), ("speeds", 10, up), ("speeds", 10, down)]         # the speed sweep: up to the cap and down again
    s += [("at", 10, 0, 0, 2), ("at", 10, 700, 0, 1), ("at", 10, 700, 0, 90)]     # one thud, then silence: the sample must end by itself
    s += [("at", 10, 0, 0, 2)]
    return s


def script_alt():
    up, down = sweep()
    s = [("at", 0, 0, 0, 3), ("at", 22, 0, 0, 2), ("run", 22, 31, 0.5, 0), ("at", 40, 0, 0, 2), ("at", 40, 700, 0, 3), ("at", 40, 0, 0, 2), ("at", 40, -700, 0, 2), ("at", 40, 0, 0, 2), ("at", 40, 700, 0, 2), ("at", 40, 0, 0, 2)]
    s += [("at", 70, 0, 0, 2), ("run", 70, 78, 0.5, 0)]
    s += [("at", 10, 0, 0, 3), ("speeds", 10, up[::2]), ("speeds", 10, down[::2]), ("at", 10, 0, 0, 2)]
    return s


POSES = {"main": make_poses(script_main()), "alt": make_poses(script_alt()), "loop": make_poses([("at", 10, 0, 0, 1550)])}


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


def direct_calls():
    calls = []
    speeds = [-1000000, -1, 0, 1, 255, 256, 257, 1000, 4096, 12345, 65536, 100000, 245759, CAP, 400000, 1000000, 1300000, 1 << 24]
    for rate, idle, span in ((22050, 2048, 6400), (16000, 3000, 4000), (44100, 1024, 1500), (11025, 4096, 6400), (32000, 2048, 6400)):
        for sp in speeds:
            calls.append(dict(fn="audio_pitch_for_speed", a0=sp % (1 << 32), rate=rate, idle=idle, span=span, tag=sp))
    calls += [dict(fn="audio_voice_alloc") for _ in range(50)]
    return calls


def params_for(name, patch=None, spd=None, shots=()):
    poses = POSES.get(name, [])
    d = {"poses": [[p["x"], p["y"], p["z"], p["speed"], p["yaw"]] for p in poses], "patch": patch or {}, "start_frame": 6,
         "title_return": name != "loop", "shots": [list(s) for s in shots]}
    if name == "main":
        d["calls"] = direct_calls()
    if spd:
        d["spd"] = str(spd)
    return d


def patch_for(cfg):
    return {f"audio_cfg+{CFG_OFF[k]}": v for k, v in cfg.items() if cfg[k] != DEFAULT_CFG[k]}


_def = _TMP / "params_main.lua"
SPD_MAIN = _TMP / "main.spd"
_def.write_text("PARAMS = " + lua_val(params_for("main", spd=SPD_MAIN)) + "\n")
os.environ["CH39_PARAMS"] = str(_def)


def probe_gen(ctx, name, params):
    gen = ctx.work / f"probe_{name}.lua"
    gen.write_text("PARAMS = " + lua_val(params) + "\ndofile(" + json.dumps(str(HERE / "probe.lua")) + ")\n")
    return gen


def alt_disc(ctx):
    """The same disc with ENGINE/BOOST/THUD stored at other sample rates (only the VAG header's rate field differs)."""
    bdir = ctx.build.build_dir
    if (bdir / "alt.cue").exists():
        return
    import re
    import subprocess
    xml = next(iter(sorted(bdir.glob("cd_image_*.xml"))), None)
    if xml is None:
        raise CheckFailure(expected="CMake's configured iso xml", actual="not found", hint="Use psn00bsdk_add_cd_image.")
    (bdir / "alt").mkdir(exist_ok=True)
    text = xml.read_text()
    for fn, data in ALT_FILES.items():
        (bdir / "alt" / fn).write_bytes(data)
        text, k = re.subn(r'(<file\s+name="%s"[^>]*?source=")[^"]*(")' % re.escape(fn), lambda m: m.group(1) + str(bdir / "alt" / fn) + m.group(2), text, flags=re.I)
        expect_eq(k, 1, f"iso.xml has one <file name=\"{fn}\" source=...> entry", hint="Appendix E.2: the sounds live in <dir name=\"DATA\">.")
    (bdir / "alt.xml").write_text(text)
    p = subprocess.run(["mkpsxiso", "-y", "-q", "-o", "alt.bin", "-c", "alt.cue", "alt.xml"], cwd=bdir, capture_output=True, text=True, timeout=60, env=tool_env())
    expect_eq(p.returncode, 0, "mkpsxiso builds the alternative disc", hint=(p.stdout + p.stderr)[-400:])


class Run:
    pass


_runs = {}


def run_of(ctx, name):
    if name in _runs:
        return _runs[name]
    if name == "main":
        r = ctx.result
    elif name == "alt":
        alt_disc(ctx)
        spd = ctx.work / "alt.spd"
        r = ctx.run(name, probe=probe_gen(ctx, name, params_for(name, patch_for(ALT_CFG), spd)), iso="alt.cue", max_frames=MAX_FRAMES)
    else:
        r = ctx.run(name, probe=probe_gen(ctx, name, params_for(name)), max_frames=2700)
    r.require_finished()
    exc = r.record("exception")
    if exc:
        raise CheckFailure(expected="no CPU exception", actual=f"CPU exception {exc['code']} at pc 0x{exc['epc']:08X}, address 0x{exc['badvaddr']:08X}",
                           hint="A NULL sample buffer, a voice number above 23, or a store through a bad pointer.")
    info = r.record("info") or {}
    expect_true(info.get("load_status") == 0, "the program loads everything and enters the game", f"status {r.data.get('status')}, info {info}",
                hint="Booting + loading takes about 400 emulated frames; does cd_load_file hang?")
    o = Run()
    o.r, o.name, o.info = r, name, info
    o.rows = r.record("rows") or []
    o.rep = M.replay(r.record("log") or [])
    o.samples = [dict(addr=info["samples"][4 * i], size=info["samples"][4 * i + 1], rate=info["samples"][4 * i + 2], loop=info["samples"][4 * i + 3]) for i in range(5)]
    o.cfg = dict(DEFAULT_CFG, **(ALT_CFG if name == "alt" else {}))
    o.files = dict(FILES, **(ALT_FILES if name == "alt" else {}))
    o.spd = Path(ctx.work / "alt.spd") if name == "alt" else SPD_MAIN
    _runs[name] = o
    return o


def rate_of(o, name):
    return struct.unpack(">I", o.files[name + ".VAG"][16:20])[0]


def show(v):
    return "(" + ", ".join(str(x) for x in v) + ")"


# ---- the disc ----------------------------------------------------------------------------------------------------------------------------------
@check("disc_has_audio_track", hint="Appendix E.2: a <track type=\"audio\" source=\"assets/MUSIC.WAV\"/> after the data track; MUSIC.WAV comes from `mkassets.py --music` (musicgen.py).")
def _(ctx):
    bdir = ctx.build.build_dir
    cue = (bdir / "hoverline.cue").read_text().replace("\r", "")
    expect_true("TRACK 02 AUDIO" in cue, "hoverline.cue lists TRACK 02 AUDIO", cue.strip().replace("\n", " | "), "The iso.xml needs the audio track after the data track.")
    tracks = [l for l in cue.splitlines() if l.strip().startswith("TRACK")]
    expect_eq(len(tracks), 2, "tracks on the disc (the data track and one audio track)")
    idx = {}
    cur = None
    for l in cue.splitlines():
        t = l.split()
        if t[:1] == ["TRACK"]:
            cur = int(t[1])
        elif t[:1] == ["INDEX"]:
            mm, ss, ff = (int(x) for x in t[2].split(":"))
            idx[(cur, int(t[1]))] = (mm * 60 + ss) * 75 + ff
    start = idx[(2, 1)]
    binsize = (bdir / "hoverline.bin").stat().st_size
    pcm = MANIFESTS["MUSIC.WAV"]["frames"] * 4
    audio_bytes = binsize - start * 2352
    expect_eq(audio_bytes, (pcm + 2351) // 2352 * 2352, "bytes of audio after INDEX 01 of track 02 in hoverline.bin (the WAV's PCM, rounded up to whole sectors)",
              hint="The audio track must be the generated MUSIC.WAV (44.1 kHz 16-bit stereo).")
    expect_true(idx[(2, 1)] - idx.get((2, 0), idx[(2, 1)]) in (0, 150), "the pregap of the audio track is 0 or 2 seconds (150 sectors)", str(idx), "")


# ---- the samples in SPU RAM --------------------------------------------------------------------------------------------------------------------
def check_samples(o):
    expect_eq(o.info["audio_status"], 0, "audio_status after audio_init", hint="A sample could not be read or has a bad header: AUDIO_ERR_* in audio.h.")
    lo = []
    for i, n in enumerate(SAMPLES):
        s = o.samples[i]
        blocks = vag_blocks(o.files[n + ".VAG"])
        expect_true(s["addr"] >= 0x1010 and s["addr"] % 8 == 0, f"{n}: addr {s['addr']:#x} is 8-byte aligned and at or above 0x1010 (the capture buffers and the SDK's dummy block are below)",
                    f"{s['addr']:#x}", "README 5.1: samples start at SPU_RAM_FIRST.")
        expect_eq(s["size"], len(blocks), f"{n}: size (the header's size field)")
        expect_eq(s["rate"], rate_of(o, n), f"{n}: rate (the header's big-endian rate field)")
        expect_eq(s["loop"], 1 if n == "ENGINE" else 0, f"{n}: loop flag (the last block's repeat bit)")
        lo.append((s["addr"], s["addr"] + len(blocks), n))
    lo.sort()
    for a, b in zip(lo, lo[1:]):
        expect_true(a[1] <= b[0], f"{a[2]} and {b[2]} do not overlap in SPU RAM", f"{a[2]} ends at {a[1]:#x}, {b[2]} starts at {b[0]:#x}", "")


def check_ram(o):
    expect_true(o.spd.exists() and o.spd.stat().st_size > 400000, "the probe wrote an SPU dump", str(o.info.get("spd_ok")), "")
    ram = M.spd_ram(o.spd.read_bytes())
    for i, n in enumerate(SAMPLES):
        s, blocks = o.samples[i], vag_blocks(o.files[n + ".VAG"])
        got = ram.read(s["addr"], len(blocks))
        if got != blocks:
            bad = next(k for k in range(len(blocks)) if got[k] != blocks[k])
            raise CheckFailure(expected=f"{n}.VAG's {len(blocks)} ADPCM bytes at SPU RAM {s['addr']:#x} (crc32 {zlib.crc32(blocks):08x})",
                               actual=f"crc32 {zlib.crc32(got):08x}; first difference at byte {bad} (block {bad // 16})",
                               hint="Upload the data AFTER the 48-byte header, in whole 64-byte transfers, at the address you store in audio_samples[].")


@check("samples_in_table", hint="audio_upload_sample fills audio_samples[id]: byte address, size, rate (big-endian header fields) and the loop flag.")
def _(ctx):
    check_samples(run_of(ctx, "main"))


@check("spu_ram_holds_the_vag_data", hint="The five .VAG bodies must be in SPU RAM exactly as in the files (compared with an SPU dump taken at the end of the run).")
def _(ctx):
    o = run_of(ctx, "main")
    check_samples(o)
    check_ram(o)


# ---- key-ons -----------------------------------------------------------------------------------------------------------------------------------
def real_keyons(o):
    return [k for k in o.rep.keyons if k["addr"] != 0x200]       # SpuInit keys every voice on at the SDK's dummy block (0x1000 / 8 = 0x200)


def sample_of(o, addr_units):
    for i, s in enumerate(o.samples):
        if s["addr"] and s["addr"] // 8 == addr_units:
            return i
    return None


def engine_keyons(o):
    return [k for k in real_keyons(o) if k["voice"] == 0]


def oneshots(o):
    return [k for k in real_keyons(o) if k["voice"] != 0]


def volume_ok(v, want):
    return v == want


@check("engine_starts_on_voice_0", hint="Entering the game key-ons ENGINE_VOICE once: the ENGINE sample's start address (in 8-byte units), volume engine_vol both sides, pitch for speed 0.")
def _(ctx):
    o = run_of(ctx, "main")
    check_samples(o)
    ks = engine_keyons(o)
    expect_eq(len(ks), 1, "key-ons of voice 0 during the whole run (one, when the game is entered; the title and the return to it make none)",
              hint="Start the hum when the state becomes GAME, not every frame.")
    k = ks[0]
    expect_eq(k["pose"], 0, "the engine key-on happens when the game is entered (before the first scripted pose)")
    expect_eq(k["addr"], o.samples[0]["addr"] // 8, "start-address register of voice 0 at key-on (ENGINE addr / 8)", fmt="hex",
              hint="The unit of the start-address register: README 5.3.")
    expect_eq((k["vol_l"], k["vol_r"]), (o.cfg["engine_vol"],) * 2, "volume registers of voice 0 (engine_vol, left and right)", fmt="hex")
    expect_eq(k["pitch"], M.pitch_for_speed(0, rate_of(o, "ENGINE"), o.cfg["idle_mul"], o.cfg["span_mul"]), "pitch register of voice 0 at key-on (the idle pitch)", fmt="hex")
    expect_true(k["adsr1"] != 0 or k["adsr2"] != 0, "the envelope registers of voice 0 were written before key-on", "both 0", "SPU_CH_ADSR1/2: see README 5.3.")
    rows = o.rows
    low = [r["pose"] for r in rows if r["stats"][9] <= 0]
    expect_true(not low, "the engine envelope level (audio_stats.env_engine) is above 0 in every frame of the run (the voice is audible)", f"0 at poses {low[:5]}",
                hint="Was the whole ENGINE sample uploaded, loop blocks included (README 5.2)? Are the envelope registers the ones of README 5.3?")
    ends = [r["pose"] for r in rows if r["stats"][8] & 1]
    expect_true(len(ends) >= 3, "ENDX bit 0 (the engine voice reached a loop-end block) is seen in at least 3 frames", f"seen in {len(ends)} frames",
                hint="ENDX is set by the SPU each time a block with the end flag (bit 0) is played; the engine loops once every 788 blocks, 1 s at its native rate and 2 s at the idle pitch.")


@check("engine_pitch_follows_speed", hint="The engine pitch is the formula of README 5.5, written to voice 0 in every game frame.")
def _(ctx):
    o = run_of(ctx, "main")
    check_samples(o)
    rate = rate_of(o, "ENGINE")
    pw = o.rep.pitch_writes.get(0, [])
    last = {}
    for pose, v in pw:
        last[pose] = v
    seen = []
    for r in o.rows:
        if r["state"] != 1 or r["pose"] == 0:
            continue
        want = M.pitch_for_speed(r["speed"], rate, o.cfg["idle_mul"], o.cfg["span_mul"])
        expect_true(r["pose"] in last, f"pose {r['pose']}: the pitch of voice 0 is written in every game frame", "no store to the pitch register of voice 0 in this frame",
                    "audio_engine_update(ship.speed) once per game frame, after ship_update.")
        expect_eq(last[r["pose"]], want, f"pitch register of voice 0 at pose {r['pose']} (ship.speed {r['speed']} = {r['speed'] / 4096:.2f} units/tick)", fmt="hex",
                  hint="README 5.5: follow the formula step by step, in its order.")
        seen.append((r["pose"], r["speed"], last[r["pose"]]))
    sweep_rows = [(p, s, v) for (p, s, v), pose in zip(seen, [POSES["main"][p - 1] for p, _, _ in seen]) if pose["kind"] == "speed"]
    expect_true(len(sweep_rows) >= 80, "the speed sweep was driven", str(len(sweep_rows)), "")
    half = 61
    rising, falling = sweep_rows[:half], sweep_rows[half:]
    for seg, cmp, nm in ((rising, lambda a, b: b >= a, "non-decreasing"), (falling, lambda a, b: b <= a, "non-increasing")):
        for a, b in zip(seg, seg[1:]):
            expect_true(cmp(a[2], b[2]), f"the pitch is {nm} with speed (speed {a[1]} -> {b[1]})", f"{a[2]:#x} -> {b[2]:#x}", "More speed must never lower the pitch.")
    distinct = len({v for _, _, v in rising})
    expect_true(distinct >= 40, "at least 40 different pitch values over the 61 speeds of the rising sweep", str(distinct), "Does the pitch really depend on the speed? Is a shift throwing away the resolution?")
    expect_eq(rising[0][2], M.pitch_for_speed(0, rate, o.cfg["idle_mul"], o.cfg["span_mul"]), "pitch at speed 0 (the idle pitch)", fmt="hex")
    expect_eq(rising[-1][2], M.pitch_for_speed(CAP, rate, o.cfg["idle_mul"], o.cfg["span_mul"]), "pitch at the speed cap (60 units per tick)", fmt="hex")
    expect_true(rising[-1][2] <= 0x3FFF and rising[-1][2] > rising[0][2], "the pitch rises from idle to the cap and stays within 0x3FFF", f"{rising[0][2]:#x} .. {rising[-1][2]:#x}", "")
    for r in o.rows:
        if r["state"] == 1 and r["pose"] > 0:
            expect_eq(r["stats"][6], last[r["pose"]], "audio_stats.engine_pitch equals the value written to the register", fmt="hex")


@check("pitch_function_direct_calls", hint="audio_pitch_for_speed is a pure function of (speed, the ENGINE rate, idle_mul, span_mul): the probe calls it with 90 combinations (negative speeds, the clamp, other rates).")
def _(ctx):
    o = run_of(ctx, "main")
    calls = [c for c in (o.r.record("calls") or []) if c.get("fn") == "audio_pitch_for_speed"]
    expect_true(len(calls) == 90, "the probe made 90 direct calls", str(len(calls)), "Is the symbol audio_pitch_for_speed in the program?")
    for c in calls:
        speed = c["tag"]
        want = M.pitch_for_speed(speed, c["rate"], c["idle"], c["span"])
        expect_true(c.get("returned", True), f"audio_pitch_for_speed({speed}) returned", "never returned", "An endless loop in the function?")
        got = c["v0"] & 0xFFFFFFFF
        expect_eq(got, want, f"audio_pitch_for_speed({speed}) with rate {c['rate']}, idle_mul {c['idle']}, span_mul {c['span']}", fmt="hex",
                  hint="README 5.5: integer division for the base, negative speeds, and the clamp.")
        clob = c.get("clobbered") or []
        expect_true(not clob, "audio_pitch_for_speed preserves the callee-saved registers", str(clob), "")


@check("voice_allocation_round_robin", hint="audio_voice_alloc returns 1, 2, ... 23, 1, 2, ...: never the engine's voice 0, never above 23.")
def _(ctx):
    o = run_of(ctx, "main")
    calls = [c for c in (o.r.record("calls") or []) if c.get("fn") == "audio_voice_alloc"]
    expect_eq(len(calls), 50, "direct calls of audio_voice_alloc")
    got = [c["v0"] & 0xFFFFFFFF for c in calls]
    want = [(i % 23) + 1 for i in range(50)]
    expect_eq(got, want, "the first 50 voices handed out", hint="The first call after audio_init returns 1; audio_init resets the cursor.")


# ---- events ------------------------------------------------------------------------------------------------------------------------------------
def event_reference(o):
    rows = [r for r in o.rows if r["pose"] > 0 and r["state"] == 1]
    entry = o.info["entry"]
    secs = [M.nearest(SECS, r["pos"]) for r in rows]
    evs = M.events_for(TRK, secs, [r["pos"] for r in rows], M.nearest(SECS, entry["pos"]), entry["pos"])
    return rows, secs, evs


def check_sections(o, rows, secs):
    bad = [(r["pose"], r["section"], s) for r, s in zip(rows, secs) if r["section"] != s]
    expect_true(not bad, "ship_section (Chapter 38) equals the nearest section of the posed ship on every frame", f"{len(bad)} differ; first: pose {bad[0][0]} got {bad[0][1]} want {bad[0][2]}" if bad else "",
                "Chapter 38's track_nearest_update: the audio events are driven by it.")


def expected_oneshots(o, rows, evs):
    out, i = [], 0
    for r, ev in zip(rows, evs):
        for e in ev:
            smp = "BOOST" if e == "boost" else "THUD"
            out.append(dict(pose=r["pose"], sample=smp, voice=(i % 23) + 1))
            i += 1
    return out


def check_events(o, kind, minimum=4):
    rows, secs, evs = event_reference(o)
    check_sections(o, rows, secs)
    check_samples(o)
    exp = expected_oneshots(o, rows, evs)
    got = []
    for k in oneshots(o):
        sm = sample_of(o, k["addr"])
        got.append(dict(pose=k["pose"], sample=SAMPLES[sm] if sm is not None else f"addr {k['addr'] * 8:#x}", voice=k["voice"], k=k))
    want_kind = [e for e in exp if e["sample"] == kind]
    got_kind = [g for g in got if g["sample"] == kind]
    expect_true(len(want_kind) >= minimum, f"the script raises at least {minimum} {kind} events", str(len(want_kind)), "")
    expect_eq(len(got_kind), len(want_kind), f"key-ons of the {kind} sample over the run",
              hint="README 5.6: both events fire on a change, not on every frame the condition holds.")
    for g, w in zip(got_kind, want_kind):
        expect_eq((g["pose"], g["voice"]), (w["pose"], w["voice"]), f"the {kind} key-ons in order: (pose, voice)",
                  hint="One key-on per event, in the frame the event happens, on the next round-robin voice (shared with the other sample).")
        k = g["k"]
        expect_eq(k["pitch"], M.sfx_pitch(o.samples[SMP[kind]]["rate"]), f"pitch register of the {kind} key-on at pose {g['pose']} (rate * 4096 / 44100)", fmt="hex")
        expect_eq((k["vol_l"], k["vol_r"]), (o.cfg["sfx_vol"],) * 2, f"volume registers of the {kind} key-on at pose {g['pose']}", fmt="hex")
        expect_eq(k["addr"], o.samples[SMP[kind]]["addr"] // 8, f"start-address register of the {kind} key-on at pose {g['pose']}", fmt="hex")
    return rows, evs, exp, got


@check("boost_chime_events", hint="BOOST.VAG plays once each time the nearest section changes into a section that has a boost face; the script crosses 4 boost sections and teleports onto 3.")
def _(ctx):
    o = run_of(ctx, "main")
    check_events(o, "BOOST")


@check("collision_thud_events", hint="THUD.VAG plays once when the ship's lateral offset first exceeds the section's half width; the script goes out right, left, along the verge, teleports while out, and chatters.")
def _(ctx):
    o = run_of(ctx, "main")
    check_events(o, "THUD")


@check("no_stray_key_ons", hint="Every key-on of the run is the engine's (once), a chime, or a thud: nothing every frame, no other voice, no other sample.")
def _(ctx):
    o = run_of(ctx, "main")
    rows, evs, exp, got = check_events(o, "THUD")
    others = [k for k in real_keyons(o) if k["voice"] != 0 and sample_of(o, k["addr"]) not in (SMP["BOOST"], SMP["THUD"])]
    expect_true(not others, "no key-on of any sample other than BOOST and THUD on voices 1..23", str(others[:2]), "")
    expect_eq(len(oneshots(o)), len(exp), "one-shot key-ons over the whole run (all of them)", hint="One key-on per event; a voice must not be retriggered every frame.")
    stats = o.rows[-1]["stats"]
    expect_eq(stats[0], len(exp), "audio_stats.sfx_played at the end", hint="audio_play_sfx counts the one-shots it starts.")
    expect_eq(stats[1], 1, "audio_stats.engine_starts at the end")
    expect_eq(stats[3] + stats[4], len(exp), "audio_stats.events_boost + events_thud at the end")
    used = {k["voice"] for k in oneshots(o)}
    expect_true(used == set(range(1, 24)), "all of voices 1..23 were used (the script raises more than 23 one-shots) and voice 0 never", f"used {sorted(used)}", "Round robin over 1..23.")


@check("one_shot_ends_by_itself", hint="The THUD sample ends with a flag-01 block: the SPU mutes the voice and sets its ENDX bit, with no help from the program (no key-off).")
def _(ctx):
    o = run_of(ctx, "main")
    ks = [k for k in oneshots(o) if sample_of(o, k["addr"]) == SMP["THUD"]]
    expect_true(ks, "a thud was played", "none", "")
    last = ks[-1]
    after = [r for r in o.rows if r["pose"] >= last["pose"] and r["state"] == 1]
    expect_true(len(after) >= 80, "the script holds still for 80 frames after the last thud", str(len(after)), "")
    expect_true(after[1]["stats"][10] > 0, "the one-shot's envelope level is above 0 in the frame after it starts (it is audible; the SPU needs a moment to run the attack)", str(after[1]["stats"][10]),
                "README 5.3: the envelope registers and the volume are written before the key-on.")
    expect_eq(after[-1]["stats"][10], 0, "the one-shot's envelope level 80 frames later (the 0.35 s sample has ended and the SPU muted the voice)",
              hint="Does the sample end with the 00 01 end block (the book's wav2vag writes it)? Did the program upload the whole data including the last block?")
    v = last["voice"]
    expect_true(after[-1]["stats"][8] >> v & 1, f"the ENDX bit of voice {v} is set at the end", f"endx {after[-1]['stats'][8]:#x}", "The SPU sets ENDX when it plays a block with the end flag.")
    n = len(after)
    keyoffs = [ko for ko in o.rep.keyoffs if ko[2] > last["order"] and ko[1] == v]
    expect_true(not keyoffs, "the program does not key the one-shot off itself", str(keyoffs[:2]), "")


# ---- the title --------------------------------------------------------------------------------------------------------------------------------
@check("engine_stops_on_the_title", hint="Going back to the title (START) keys voice 0 off (SPU_KEY_OFF1 bit 0) and does not key it on again.")
def _(ctx):
    o = run_of(ctx, "main")
    last_pose = max(r["pose"] for r in o.rows)
    offs = [ko for ko in o.rep.keyoffs if ko[1] == 0 and ko[0] > last_pose]
    expect_true(offs, "a key-off of voice 0 after the last pose (the probe presses START)", "none", "set_state(STATE_TITLE) calls audio_engine_stop().")
    expect_eq(len(engine_keyons(o)), 1, "engine key-ons in total")
    expect_true(not [k for k in real_keyons(o) if k["pose"] == 0 and k["voice"] != 0], "nothing but the engine starts when the game is entered", "", "")


# ---- music ------------------------------------------------------------------------------------------------------------------------------------
@check("music_plays_from_the_cd", hint="README 5.7: the drive's matrix, the SPU's CD volume, the mode, then one CdlPlay with the music track, sent once at start-up.")
def _(ctx):
    o = run_of(ctx, "main")
    cd = o.rep.cd
    plays = [c for c in cd if c[1] == 0x03]
    expect_true(len(plays) >= 1, "a CdlPlay (command 0x03) reaches the CD controller", f"commands seen: {sorted({hex(c[1]) for c in cd})}", "audio_music_start sends it: README 5.7.")
    expect_eq(len(plays), 1, "CdlPlay commands in the main run (the track is 24 s long, the run is shorter)", hint="Start the music once.")
    expect_eq(plays[0][2], [o.cfg["music_track"]], "the parameter of CdlPlay: the track number (audio_cfg.music_track)", hint="Track 1 is the data track; the music is track 2.")
    modes = [c for c in cd if c[1] == 0x0E and c[0] == 0]
    expect_true(modes and modes[-1][2] and modes[-1][2][0] & 1, "the last CdlSetmode before the music has the CdlModeDA bit (bit 0)", str(modes[-1:] if modes else None),
                "The mode bits: README 5.7.")
    expect_true(cd.index(plays[0]) > cd.index(modes[-1]), "CdlSetmode comes before CdlPlay", "", "")
    expect_true(modes[-1][2][0] & 2, "the auto-pause bit (CdlModeAP, bit 1) is set so the program learns when the track ends", str(modes[-1][2]), "")
    rg = o.rep.regs
    expect_eq((rg.get(0x1DB0), rg.get(0x1DB2)), (o.cfg["music_vol"],) * 2, "SPU CD input volume registers (0x1F801DB0 / B2): music_vol", fmt="hex",
              hint="SpuInit leaves them at 0x7FFF; the music volume is set by SpuSetCommonCDVolume.")
    expect_true(rg.get(0x1DAA, 0) & 1 and rg.get(0x1DAA, 0) & 0x8000, "SPU control register: SPU enabled (bit 15) and CD audio enabled (bit 0)", f"{rg.get(0x1DAA, 0):#06x}", "SpuInit sets 0xC001; do not clear it.")
    atv = o.rep.cd_atv
    expect_eq((atv.get("l_to_l"), atv.get("r_to_r"), atv.get("l_to_r"), atv.get("r_to_l")), (128, 128, 0, 0), "the CD volume matrix left at {128, 0, 128, 0} (left to left, right to right)",
              hint="README 5.7: the drive's volume matrix must be set.")
    for c in plays:
        expect_true(c[0] == 0, "the music starts before the game is entered (from the title)", f"pose {c[0]}", "")


@check("music_restarts_when_the_track_ends", hint="CdlModeAP makes the drive pause at the end of the track and raise an interrupt; the auto-pause callback sets a flag and audio_update sends CdlPlay again.")
def _(ctx):
    o = run_of(ctx, "loop")
    plays = [c for c in o.rep.cd if c[1] == 0x03]
    expect_true(len(plays) >= 2, "a second CdlPlay arrives after the 24 s track has ended (about 1500 frames after the first)", f"{len(plays)} CdlPlay commands in {o.rows[-1]['n']} frames",
                "audio_update must send CdlPlay again after the callback reported the end.")
    st = o.rows[-1]["stats"]
    expect_eq(st[7], len(plays) - 1, "audio_stats.music_restarts equals the extra CdlPlay commands")
    expect_eq(plays[1][2], [o.cfg["music_track"]], "the restart plays the same track")
    vb = o.info.get("play_vb") or []
    gap = vb[1] - vb[0] if len(vb) >= 2 else None
    expect_true(gap is not None and gap >= 1300, "the second CdlPlay comes after the 24 s track has played (at least 1300 vertical blanks after the first)",
                f"{gap} blanks after the first" if gap is not None else str(vb), "Restart when the auto-pause callback reports the end of the track, not on a timer.")


# ---- another disc ------------------------------------------------------------------------------------------------------------------------------
@check("nothing_hard_coded_alt_disc", hint="The same script on a disc where ENGINE, BOOST and THUD have other sample rates, with other idle_mul / span_mul / volumes patched in: pitches and key-ons must follow.")
def _(ctx):
    o = run_of(ctx, "alt")
    check_samples(o)
    check_ram(o)
    rate = rate_of(o, "ENGINE")
    expect_eq(rate, 16000, "the alternative ENGINE.VAG's rate", hint="(disc built by the verifier)")
    ks = engine_keyons(o)
    expect_eq(len(ks), 1, "engine key-ons")
    expect_eq(ks[0]["pitch"], M.pitch_for_speed(0, 16000, 3000, 4000), "engine pitch at key-on with rate 16000, idle_mul 3000", fmt="hex", hint="Rate from the file, constants from audio_cfg.")
    expect_eq((ks[0]["vol_l"], ks[0]["vol_r"]), (0x1000, 0x1000), "engine volume (patched engine_vol)", fmt="hex")
    last = {}
    for pose, v in o.rep.pitch_writes.get(0, []):
        last[pose] = v
    for r in o.rows:
        if r["state"] == 1 and r["pose"] > 0:
            expect_eq(last.get(r["pose"]), M.pitch_for_speed(r["speed"], 16000, 3000, 4000), f"engine pitch at pose {r['pose']} (speed {r['speed']})", fmt="hex")
    check_events(o, "BOOST", 4)
    check_events(o, "THUD", 3)
    plays = [c for c in o.rep.cd if c[1] == 0x03]
    expect_eq(len(plays), 1, "CdlPlay commands")
    expect_eq((o.rep.regs.get(0x1DB0), o.rep.regs.get(0x1DB2)), (0x5000, 0x5000), "SPU CD volume (patched music_vol)", fmt="hex")
