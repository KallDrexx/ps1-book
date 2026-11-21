"""Chapter 41 checks: Handling, Game Loop, and Polish (drag, skid, auto-pitch; the countdown / race / results state machine, laps, the timer text).
Build: CMake + PSn00bSDK; the CMake rule runs tools/assets/mkassets.py. The emulator BOOTS THE .cue.

THE MODEL: example/handling_ref.py (+ collide_ref.py of Chapter 40 and ship_ref.py of Chapter 37): exact integer arithmetic, the same as README 5 and the headers. Runs:
  unit    the reader's functions called DIRECTLY from the probe (directcall.lua) with crafted arguments: handling_drag, handling_skid, handling_pitch_target, handling_auto_pitch,
          race_section_step, race_tick, race_countdown_tick, race_format_time, race_format_text. Every result is compared with the model. Track images are copied into free RAM
          (track 1, track 2, and a copy of track 1 whose sections 10..20 have their next / prev links swapped and whose section 70 has a flat `up`).
  drive   the whole game on track 1, one lap (race_cfg.laps = 1) flown by a pilot that lives in probe.lua and steers from the program's own state; every frame is recorded and
          REPLAYED with the model (ship_update, collide_ship, auto-pitch, race_tick from the previous frame's state), then the facts that do not depend on the model are checked.
  ghost   the program's lap logic fed with a scripted route: the probe puts the ship on section after section (jumps are allowed: a lap needs 112 steps, not 112 seconds of driving),
          incl. a backward excursion over the line, two races in a row (the best lap persists), three laps; then the same on track 2 with two laps."""

import atexit
import json
import math
import os
import random
import re
import shutil
import struct
import sys
import tempfile
from pathlib import Path

from harness import *

ROOT_DIR = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR / "tools" / "assets"))
sys.path.insert(0, str(HERE.parent / "example"))
import mkassets      # noqa: E402
import formats       # noqa: E402
import handling_ref as H  # noqa: E402

C = H.C
SR = H.SR
SEED = int(os.environ.get("CH41_SEED") or random.randrange(1, 10 ** 6))
RNG = random.Random(SEED)
print(f"[ch41 unit-test seed {SEED}; CH41_SEED={SEED} repeats it]")

config(
    title="Handling, Game Loop and Polish: drag, skid, auto-pitch, countdown, laps, results",
    build="cmake", exe="game.exe", sym="", elf="game.elf", iso="hoverline.cue",
    break_at=None, max_frames=3800, timeout=420,
)

_TMP = Path(tempfile.mkdtemp(prefix="ch41ref-"))
atexit.register(shutil.rmtree, _TMP, True)
FILES, MANIFESTS = mkassets.build(_TMP / "assets", seed=1)
IMG1, IMG2 = FILES["TRACK.TRK"], FILES["TRACK2.TRK"]
T1, T2 = formats.parse_trk(IMG1), formats.parse_trk(IMG2)


def patched_image():
    """Track 1 with the links of sections 10..20 swapped (next <-> prev: `next` runs DOWN the indices there) and a flat `up` at section 70."""
    d = bytearray(IMG1)
    off_v, off_f, off_s, off_vis = struct.unpack_from("<IIII", d, 0x28)
    for sec in range(10, 21):
        o = off_s + 64 * sec
        nx, pv = struct.unpack_from("<HH", d, o + 0x2C)
        struct.pack_into("<HH", d, o + 0x2C, pv, nx)
    struct.pack_into("<hhh", d, off_s + 64 * 70 + 0x20, 3000, 100, -2500)
    return bytes(d)


IMG3 = patched_image()
T3 = formats.parse_trk(IMG3)
TR = {1: T1, 2: T2, 3: T3}
IMGS = {1: IMG1, 2: IMG2, 3: IMG3}

# RAM for the direct calls (free in every build: the program ends below 0x80040000, the heap above it stays below 0x80150000, the stack is at 0x801F0000)
IMG_ADDR = {1: 0x80180000, 2: 0x80190000, 3: 0x801A0000}
TRK_ADDR = {1: 0x801B0000, 2: 0x801B0040, 3: 0x801B0080}
SHIP_A, RACE_A, UP_A, VEL_A, TGT_A, BUF_A = 0x801B1000, 0x801B3000, 0x801B3100, 0x801B3200, 0x801B3220, 0x801B3300
MASK32 = (1 << 32) - 1
SHIP_FIELDS = SR.SHIP_FIELDS
RFIELDS = H.Race.FIELDS + [f"lap_ticks[{i}]" for i in range(H.MAX_LAPS)]
GARBAGE = 0x7EADBEEF


def track_struct(n):
    d, a = IMGS[n], IMG_ADDR[n]
    off_v, off_f, off_s, off_vis = struct.unpack_from("<IIII", d, 0x28)
    t = TR[n]
    return [a + off_v, a + off_f, a + off_s, a + off_vis, len(t["sections"]), len(t["vertices"]), len(t["faces"]), struct.unpack_from("<H", d, 0x1E)[0],
            t["start_section"], t["flags"], t["texture_count"], t["total_length"]]


def s32(v):
    return C.wrap32(v)


def show(v):
    return "(" + ", ".join(str(x) for x in v) + ")"


# ---------------------------------------------------------------------------------------------------------------------------------------------
# the unit calls
UNIT = []


def add_call(kind, tag, fn, a0=None, a1=None, a2=None, a3=None, writes=(), reads=(), limit=None, **extra):
    c = dict(kind=kind, tag=tag, fn=fn, a0=a0, a1=a1, a2=a2, a3=a3, writes=list(writes), reads=list(reads), **extra)
    if limit:
        c["limit"] = limit
    UNIT.append(c)


def w_words(addr, words):
    return dict(addr=addr, words=[v % (1 << 32) for v in words])


def w_sym(sym, words):
    return dict(sym=sym, words=[v % (1 << 32) for v in words])


def u32(v):
    return v % (1 << 32)


def hcfg_words(c):
    return [c["drag"], c["grip"], c["pitch_smooth"], 0]


def rcfg_words(c):
    return [c["laps"], c["wrong_way"], c["count_from"], 0]


def rand_ship(r):
    pos = [r.randint(-30000, 30000) for _ in range(3)]
    return pos + [r.randint(0, 4095) for _ in range(3)] + [r.randint(-200000, 200000) for _ in range(3)] + [r.randint(0, 245760), r.randrange(1 << 24),
                                                                                                          r.randint(-300, 300) << 12, r.randint(-100000, 100000), r.randint(-20000, 20000)]


def make_unit_calls():
    r = RNG
    # ---- handling_drag
    for i in range(70):
        speed = r.choice([0, 1, 63, 64, 100, 4095, 4096, 12345, 193536, 245760, r.randint(-200000, 3000000), r.randint(-2 ** 26, 2 ** 26)])
        dt = r.choice([4096, 4096, 4915, 1, 2048, 8192, 40000, 0])
        c = dict(drag=r.choice([64, 64, 0, 1, 4095, 4096, 5000, r.randint(0, 300), r.randint(0, 10 ** 5)]), grip=1024, pitch_smooth=1024)
        add_call("drag", f"drag #{i}", "handling_drag", u32(speed), dt, writes=[w_sym("handling_cfg", hcfg_words(c))], speed=speed, dt=dt, h=c)
    # ---- handling_skid
    for i in range(80):
        vel = [r.randint(-300000, 300000) for _ in range(3)]
        tgt = [r.choice([v + r.randint(-3, 3), r.randint(-250000, 250000)]) for v in vel] if r.random() < 0.3 else [r.randint(-250000, 250000) for _ in range(3)]
        dt = r.choice([4096, 4096, 4915, 1, 2048, 8192, 40000, 0])
        c = dict(drag=64, grip=r.choice([1024, 1024, 4096, 0, 1, 2000, 4095, 8192, r.randint(0, 5000)]), pitch_smooth=1024)
        add_call("skid", f"skid #{i}", "handling_skid", VEL_A, TGT_A, dt,
                 writes=[w_words(VEL_A, vel), w_words(TGT_A, tgt), w_sym("handling_cfg", hcfg_words(c))],
                 reads=[dict(name="vel", addr=VEL_A, n=3), dict(name="tgt", addr=TGT_A, n=3)], vel=vel, tgt=tgt, dt=dt, h=c)
    # ---- handling_pitch_target
    ups = []
    for n in (1, 2):
        for sec in range(len(TR[n]["sections"])):
            ups.append((list(TR[n]["sections"][sec]["up"]), r.randrange(1 << 24)))
    for _ in range(60):
        ups.append(([r.randint(-4096, 4096), r.choice([r.randint(-4096, -256), r.randint(-4096, 4096), -256, -255, -300]), r.randint(-4096, 4096)], r.randrange(1 << 24)))
    ups += [([4096, -256, 0], 1024 << 12), ([-4096, -256, 0], 1024 << 12), ([0, -256, 4096], 0), ([0, -256, -4096], 0), ([0, -4096, 0], 123456), ([0, 0, 0], 0),
            ([1000, -3900, 3000], 3 << 12), ([-1837, -3650, -285], 0), ([2000, -2000, 2000], 2048 << 12), ([0, -1000, 4000], 100 << 12), ([0, -1000, -4000], 100 << 12)]
    for i, (up, yaw) in enumerate(ups):
        add_call("pitch", f"pitch_target #{i}", "handling_pitch_target", UP_A, yaw, writes=[w_words(UP_A, up)], limit=20000, up=up, yaw=yaw)
    # ---- handling_auto_pitch
    for i in range(60):
        n = r.choice([1, 2, 3])
        N = len(TR[n]["sections"])
        sec = r.choice([r.randrange(N), r.randrange(N), 70 if n == 3 else r.randrange(N), -1, N, 99999])
        ship = rand_ship(r)
        dt = r.choice([4096, 4096, 4915, 2048, 40000])
        c = dict(drag=64, grip=1024, pitch_smooth=r.choice([1024, 1024, 0, 4096, 6000, r.randint(0, 3000)]))
        add_call("autopitch", f"auto_pitch #{i}", "handling_auto_pitch", SHIP_A, TRK_ADDR[n], u32(sec), dt, limit=30000,
                 writes=[w_words(SHIP_A, ship), w_words(TRK_ADDR[n], track_struct(n)), w_sym("handling_cfg", hcfg_words(c))], reads=[dict(name="ship", addr=SHIP_A, n=14)],
                 n=n, sec=sec, ship=ship, dt=dt, h=c)
    # ---- race_section_step
    for n in (1, 2, 3):
        N = len(TR[n]["sections"])
        pairs = []
        for s in range(N):
            S = TR[n]["sections"][s]
            pairs += [(s, S["next"]), (s, S["prev"]), (s, s), (s, (s + 1) % N), (s, (s - 1) % N), (s, r.randrange(N))]
        pairs += [(-1, 0), (0, -1), (N, 0), (0, N), (99999, 3), (3, 99999), (-1, -1), (N - 1, 0), (0, N - 1)]
        for k, (p, q) in enumerate(pairs):
            add_call("step", f"section_step track{n} #{k}", "race_section_step", TRK_ADDR[n], u32(p), u32(q), writes=[w_words(TRK_ADDR[n], track_struct(n))], n=n, p=p, q=q)
    # ---- race_tick: short sequences from crafted states
    for sq in range(70):
        n = r.choice([1, 2, 3])
        T = TR[n]
        N = len(T["sections"])
        cfg = dict(laps=r.choice([3, 3, 1, 2, 8, 0, 99, 4]), wrong_way=r.choice([2, 2, 1, 0, 3, -1, 5]), count_from=3, reserved=0)
        laps = H.clamp(cfg["laps"], 1, H.MAX_LAPS)
        rc = H.Race()
        rc.lap = r.randrange(laps)
        rc.lap_ticks = [r.randint(100, 9000) if i < rc.lap else 0 for i in range(H.MAX_LAPS)]
        rc.ticks = sum(rc.lap_ticks) + r.randint(0, 3000)
        rc.progress = rc.lap * N + r.choice([N - 3, N - 2, N - 1, N - 1, r.randint(0, N - 1), -2, 0])
        if rc.lap == 0 and rc.progress < 0 and r.random() < 0.5:
            rc.progress = -1
        rc.furthest = rc.progress + r.choice([0, 0, 1, 2, 3, 5])
        rc.prev_section = r.choice([r.randrange(N), r.randrange(N), -1])
        rc.wrong_way = r.randint(0, 1)
        if r.random() < 0.1:
            rc.finished, rc.lap, rc.total = 1, laps, rc.ticks
            rc.lap_ticks = [r.randint(100, 9000) if i < laps else 0 for i in range(H.MAX_LAPS)]
        best = r.choice([0, 0, r.randint(50, 12000), 100, 130])
        if rc.lap and r.random() < 0.4:
            best = min(rc.lap_ticks[:rc.lap]) + r.choice([-1, 0, 1, 50])
            best = max(best, 1)
        S = T["sections"]
        for k in range(6):
            p = rc.prev_section
            if p < 0:
                sec = r.randrange(N)
            else:
                sec = r.choice([S[p]["next"], S[p]["next"], S[p]["next"], S[p]["prev"], p, r.randrange(N), -1])
            before, bbefore = rc.copy(), best
            flags, best = H.tick(rc, T, sec, best, cfg)
            add_call("rtick", f"race_tick seq {sq} step {k}", "race_tick", RACE_A, TRK_ADDR[n], u32(sec), limit=20000,
                     writes=[w_words(RACE_A, before.words()), w_words(TRK_ADDR[n], track_struct(n)), w_sym("race_cfg", rcfg_words(cfg)), w_sym("race_best", [bbefore])],
                     reads=[dict(name="race", addr=RACE_A, n=19), dict(name="best", sym="race_best", n=1)],
                     n=n, sec=sec, before=before.words(), best=bbefore, cfg=cfg, want=rc.words(), want_best=best, want_flags=flags)
    # ---- race_tick: the tick that finishes the race, with race_best equal to / next to the best lap (a tie is not a new best)
    for sq in range(16):
        n = r.choice([1, 2, 3])
        T = TR[n]
        N = len(T["sections"])
        cfg = dict(laps=r.choice([1, 2, 3, 3, 8]), wrong_way=2, count_from=3, reserved=0)
        laps = H.clamp(cfg["laps"], 1, H.MAX_LAPS)
        rc = H.Race()
        rc.lap = laps - 1
        rc.lap_ticks = [r.randint(100, 9000) if i < rc.lap else 0 for i in range(H.MAX_LAPS)]
        final = r.randint(60, 9000)
        rc.ticks = sum(rc.lap_ticks) + final - 1
        rc.progress = laps * N - 1
        rc.furthest = rc.progress + r.choice([0, 0, 1])
        rc.prev_section = r.randrange(N)
        sec = T["sections"][rc.prev_section]["next"]
        low = min(rc.lap_ticks[:rc.lap] + [final])
        best = r.choice([low, low, low + 1, max(low - 1, 1), 0])
        before, bbefore = rc.copy(), best
        flags, best = H.tick(rc, T, sec, best, cfg)
        add_call("rtick", f"race_tick finishing {sq}", "race_tick", RACE_A, TRK_ADDR[n], u32(sec), limit=20000,
                 writes=[w_words(RACE_A, before.words()), w_words(TRK_ADDR[n], track_struct(n)), w_sym("race_cfg", rcfg_words(cfg)), w_sym("race_best", [bbefore])],
                 reads=[dict(name="race", addr=RACE_A, n=19), dict(name="best", sym="race_best", n=1)],
                 n=n, sec=sec, before=before.words(), best=bbefore, cfg=cfg, want=rc.words(), want_best=best, want_flags=flags)
    # ---- race_countdown_tick
    for i in range(60):
        hz = r.choice([60, 50])
        cf = r.choice([3, 3, 1, 9, 0, 12, 5, 2])
        cfg = dict(laps=3, wrong_way=2, count_from=cf, reserved=0)
        cfc = H.clamp(cf, 1, 9)
        cd = r.choice([0, 1, hz - 1, hz, hz + 1, 2 * hz, cfc * hz - 2, cfc * hz - 1, cfc * hz, cfc * hz + 5, r.randint(0, 10 * hz)])
        rc = H.Race()
        rc.cd_ticks = cd
        rc.ticks = r.randint(0, 9)
        before = rc.copy()
        flags = H.countdown_tick(rc, hz, cfg)
        add_call("cd", f"countdown #{i}", "race_countdown_tick", RACE_A, hz, writes=[w_words(RACE_A, before.words()), w_sym("race_cfg", rcfg_words(cfg))],
                 reads=[dict(name="race", addr=RACE_A, n=19)], hz=hz, cfg=cfg, before=before.words(), want=rc.words(), want_flags=flags)
    # ---- race_format_time
    ticks = [-1, -2, -100000, -2 ** 31, 0, 1, 2, 5, 59, 60, 61, 599, 600, 3599, 3600, 3725, 6000, 215999, 216000, 359999, 360000, 360001, 2 ** 30, 2 ** 31 - 1, 12345, 99999, 4321]
    for i, t in enumerate(ticks + [r.randint(0, 400000) for _ in range(20)]):
        for hz in (60, 50):
            add_call("ftime", f"format_time {t} @{hz}", "race_format_time", BUF_A, u32(t), hz, limit=100000, writes=[w_words(BUF_A, [0x58585858] * 3)], reads=[dict(name="buf", addr=BUF_A, n=3)],
                     ticks=t, hz=hz)
    # ---- race_format_text
    for i in range(110):
        state = r.choice([0, 1, 2, 3, 3, 2, 1, 7, -1, 4])
        hz = r.choice([60, 50])
        cfg = dict(laps=r.choice([3, 3, 1, 8, 0, 99, 4, 2]), wrong_way=2, count_from=r.choice([3, 3, 1, 9, 0, 20]), reserved=0)
        laps = H.clamp(cfg["laps"], 1, H.MAX_LAPS)
        rc = H.Race()
        rc.cd_ticks = r.choice([0, 59, 60, 125, 179, 180, r.randint(0, 600)])
        rc.lap = r.randint(0, laps)
        rc.ticks = r.choice([0, 1, 59, 3725, r.randint(0, 40000)])
        rc.wrong_way = r.randint(0, 1)
        rc.finished = r.randint(0, 1)
        rc.total = r.choice([0, rc.ticks, r.randint(1, 30000)])
        rc.new_best = r.randint(0, 1)
        rc.lap_ticks = [r.choice([0, r.randint(100, 20000)]) for _ in range(H.MAX_LAPS)]
        best = r.choice([0, 0, r.randint(1, 50000), 3725])
        add_call("ftext", f"format_text #{i} state {state}", "race_format_text", RACE_A, u32(state), hz, limit=600000,
                 writes=[w_words(RACE_A, rc.words()), w_sym("race_cfg", rcfg_words(cfg)), w_sym("race_best", [best]), w_sym("race_text", [0x41414141] * (H.LINES * 8))],
                 reads=[dict(name="text", sym="race_text", n=H.LINES * 8)], state=state, hz=hz, cfg=cfg, race=rc.words(), best=best)


make_unit_calls()
NUNIT = len(UNIT)


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


def probe_gen(ctx, name, params):
    gen = ctx.work / f"probe_{name}.lua"
    gen.write_text("PARAMS = " + lua_val(params) + "\ndofile(" + json.dumps(str(HERE / "probe.lua")) + ")\n")
    return gen


UNIT_IMAGES = []
for _n in (1, 2, 3):
    _f = _TMP / f"image{_n}.trk"
    _f.write_bytes(IMGS[_n])
    UNIT_IMAGES.append(dict(addr=IMG_ADDR[_n], file=str(_f)))
UNIT_KEYS = ("fn", "a0", "a1", "a2", "a3", "limit", "tag", "writes", "reads")
UNIT_PARAMS = {"mode": "unit", "images": UNIT_IMAGES, "calls": [{k: c[k] for k in UNIT_KEYS if k in c and c[k] is not None} for c in UNIT]}


def exception_of(r):
    try:
        return r.record("exception")
    except Exception:
        return None


def unit_records(ctx):
    r = ctx.run("unit", probe=probe_gen(ctx, "unit", UNIT_PARAMS), max_frames=900)
    r.require_finished()
    exc = exception_of(r)
    if exc:
        raise CheckFailure(expected="no CPU exception in the direct calls", actual=f"exception {exc['code']} at pc 0x{exc['epc']:08X}, address 0x{exc['badvaddr']:08X}",
                           hint="Which function? Run with -v. A NULL or wild pointer, an index out of range, a misaligned word access.")
    recs = r.record("calls")
    expect_eq(len(recs), NUNIT, "direct calls made")
    return list(zip(UNIT, recs))


def kind_cases(ctx, *kinds):
    out = []
    for case, rec in unit_records(ctx):
        if case["kind"] in kinds:
            expect_true(rec["returned"], f"{case['tag']}: the call returns", "no return within the instruction limit", "An endless loop, or a scan that is far too long?")
            expect_true(not rec["clobbered"], f"{case['tag']}: callee-saved registers preserved", str(rec["clobbered"]), "$s0-$s7, $sp, $fp, $gp must survive a call.")
            out.append((case, rec))
    return out


def text_of(words, n_lines):
    raw = b"".join(struct.pack("<I", w % (1 << 32)) for w in words)
    out = []
    for i in range(n_lines):
        line = raw[i * 32:(i + 1) * 32]
        z = line.find(b"\0")
        out.append(None if z < 0 else line[:z].decode("latin-1"))
    return out


# ---- checks: the pure functions ----------------------------------------------------------------------------------------------------------
@check("air_resistance", hint="handling_drag: speed - fx_mul(speed, min(fx_mul(drag, dt), 4096)); the constant is handling_cfg.drag; no clamping of the result.")
def _(ctx):
    for case, rec in kind_cases(ctx, "drag"):
        want = H.drag(case["speed"], case["dt"], case["h"])
        expect_eq(s32(rec["v0"]), want, f"{case['tag']}: speed {case['speed']}, dt {case['dt']}, drag {case['h']['drag']}")


@check("skid_blend", hint="handling_skid: g = min(fx_mul(grip, dt), 4096); vel[i] += fx_mul(target[i] - vel[i], g) for the three axes, in place; target untouched; the constant is handling_cfg.grip.")
def _(ctx):
    for case, rec in kind_cases(ctx, "skid"):
        want = H.skid(case["vel"], case["tgt"], case["dt"], case["h"])
        got = [s32(v) for v in rec["out"]["vel"]]
        expect_true(got == want, f"{case['tag']}: vel {show(case['vel'])} -> {show(want)} (target {show(case['tgt'])}, dt {case['dt']}, grip {case['h']['grip']})", show(got),
                    "g is clamped to 4096 AFTER the dt scaling; fx_mul keeps a 64-bit product and floors (arithmetic shift).")
        expect_true([s32(v) for v in rec["out"]["tgt"]] == case["tgt"], f"{case['tag']}: the target is left alone", show([s32(v) for v in rec["out"]["tgt"]]), "target is const.")


@check("pitch_target_from_the_road", hint="handling_pitch_target: flat plane (up.y > -256) gives 0; g = (-(up.x*hx + up.z*hz)) / up.y (truncating), clamped to +-32767; y = g*4096 / isqrt(4096^2 + g^2); "
                                         "the smallest p in -256..256 minimising |isin(p) + y|; result p << 12.")
def _(ctx):
    for case, rec in kind_cases(ctx, "pitch"):
        want = H.pitch_target(case["up"], case["yaw"])
        expect_eq(s32(rec["v0"]), want, f"{case['tag']}: up {show(case['up'])}, yaw {case['yaw']} (whole units: {want >> 12})")


@check("auto_pitch_follows_the_section", hint="handling_auto_pitch: not a section -> nothing; else pitch += fx_mul(target - pitch, min(fx_mul(pitch_smooth, dt), 4096)) with target from the section's up and the ship's yaw; "
                                              "nothing else of the ship changes.")
def _(ctx):
    for case, rec in kind_cases(ctx, "autopitch"):
        s = list(case["ship"])
        H.auto_pitch(s, TR[case["n"]], case["sec"], case["dt"], case["h"])
        got = [s32(v) for v in rec["out"]["ship"]]
        bad = next(((SHIP_FIELDS[i], got[i], s[i]) for i in range(14) if got[i] != s[i]), None)
        expect_true(bad is None, f"{case['tag']}: section {case['sec']}, ship after = {show(s)}", show(got), f"first difference (field, got, expected): {bad}. Input ship {show(case['ship'])}, dt {case['dt']}.")


@check("calls_are_cheap", hint="The pitch target is asked every tick: a scan of 513 angles costs ~40,000 instructions. isin rises strictly over -256..256, so a binary search needs about ten evaluations. "
                               "race_tick and the format functions are cheap too.")
def _(ctx):
    limits = {"pitch": 2500, "autopitch": 3000, "rtick": 1500, "step": 400, "drag": 200, "skid": 400}
    worst = {}
    for case, rec in unit_records(ctx):
        k = case["kind"]
        if k in limits:
            worst[k] = max(worst.get(k, 0), rec["instrs"])
    for k, lim in limits.items():
        if k in worst:
            expect_true(worst[k] <= lim, f"{k}: at most {lim} instructions per call", f"{worst[k]}", "A scan over all the angles, or a loop over the whole track?")


@check("section_step_follows_links", hint="race_section_step: +1 if cur is prev's `next`, -1 if it is prev's `prev` (the links, not index +- 1: the verifier swaps them in some sections), else 0; an index that is not a section gives 0.")
def _(ctx):
    for case, rec in kind_cases(ctx, "step"):
        want = H.section_step(TR[case["n"]], case["p"], case["q"])
        expect_eq(s32(rec["v0"]), want, f"{case['tag']}: from section {case['p']} to {case['q']}")


def check_rtick(ctx, fields, what):
    for case, rec in kind_cases(ctx, "rtick"):
        got = [s32(v) for v in rec["out"]["race"]]
        want = case["want"]
        bad = [(RFIELDS[i], got[i], want[i]) for i in range(19) if RFIELDS[i] in fields and got[i] != want[i]]
        if "race_best" in fields and s32(rec["out"]["best"][0]) != case["want_best"]:
            bad.append(("race_best", s32(rec["out"]["best"][0]), case["want_best"]))
        if "flags" in fields and s32(rec["v0"]) != case["want_flags"]:
            bad.append(("return value", s32(rec["v0"]), case["want_flags"]))
        ctxt = (f"{case['tag']}: track {case['n']} ({len(TR[case['n']]['sections'])} sections), ship_section {case['sec']}, laps {case['cfg']['laps']}, wrong_way {case['cfg']['wrong_way']}, "
                f"race_best {case['best']}, race before = {dict(zip(RFIELDS, case['before']))}")
        expect_true(not bad, f"{what}: no field differs from the rules", f"differences (field, got, expected): {bad}", ctxt)


@check("lap_counting", hint="race_tick: ticks++; step by the links from the previous section; progress += step; a lap completes when progress >= (lap + 1) * section_count (the track's own count); "
                            "lap_ticks[lap] = ticks minus the earlier laps; prev_section follows; a negative section changes nothing but the clock.")
def _(ctx):
    check_rtick(ctx, {"ticks", "lap", "progress", "furthest", "prev_section", "lap_ticks[0]", "lap_ticks[1]", "lap_ticks[2]", "lap_ticks[3]", "lap_ticks[4]", "lap_ticks[5]", "lap_ticks[6]",
                      "lap_ticks[7]", "flags"}, "lap counting")


@check("wrong_way_warning", hint="race_tick: wrong_way = 1 exactly when furthest - progress >= max(race_cfg.wrong_way, 1), computed every tick after the step.")
def _(ctx):
    check_rtick(ctx, {"wrong_way"}, "wrong-way flag")


@check("finish_and_best_lap", hint="At lap >= laps (laps clamped to 1..8): finished = 1, total = ticks, best_lap = the fastest lap of this race; race_best and new_best only when best_lap < race_best or race_best is 0 "
                                    "(a tie is not a new best).")
def _(ctx):
    check_rtick(ctx, {"finished", "total", "best_lap", "new_best", "race_best", "flags"}, "finish and best lap")


@check("countdown_ticks", hint="race_countdown_tick: beep = cd_ticks % hz == 0 (before the increment); cd_ticks++; GO once cd_ticks >= count_from * hz (count_from clamped to 1..9); GO wins over a beep. Nothing else changes.")
def _(ctx):
    for case, rec in kind_cases(ctx, "cd"):
        got = [s32(v) for v in rec["out"]["race"]]
        ctxt = f"{case['tag']}: hz {case['hz']}, count_from {case['cfg']['count_from']}, cd_ticks before {case['before'][0]}"
        expect_true(got == case["want"], f"race after = {show(case['want'])}", show(got), ctxt)
        expect_eq(s32(rec["v0"]), case["want_flags"], f"the return value ({ctxt})")


@check("time_text", hint="race_format_time: \"M:SS.cc\": ticks limited to 0..360000, cs = ticks * 100 / hz (integer), limited to 599999; M = cs / 6000, SS = (cs / 100) % 60, cc = cs % 100; a negative time is \"-:--.--\".")
def _(ctx):
    for case, rec in kind_cases(ctx, "ftime"):
        want = H.format_time(case["ticks"], case["hz"])
        got = text_of(rec["out"]["buf"], 1)[0]
        expect_true(got == want, f"{case['tag']}: the text", repr(got), "Check the NUL terminator, the limits, the rounding down (hundredths = floor).")


@check("hud_and_results_text", hint="race_format_text: empties the 12 lines, then per state (TITLE best lap, COUNTDOWN 'GET READY n', RACE lap / time / last+best / WRONG WAY, RESULTS laps / total / best / NEW BEST LAP): README 5.8, exact text.")
def _(ctx):
    for case, rec in kind_cases(ctx, "ftext"):
        rc = H.Race.from_words(case["race"])
        want = H.format_text(rc, case["state"], case["hz"], case["best"], case["cfg"])
        got = text_of(rec["out"]["text"], H.LINES)
        bad = [(i, got[i], want[i]) for i in range(H.LINES) if got[i] != want[i]]
        expect_true(not bad, f"{case['tag']}: the {H.LINES} lines of race_text", f"differences (line, got, expected): {bad}",
                    f"state {case['state']}, hz {case['hz']}, laps {case['cfg']['laps']}, count_from {case['cfg']['count_from']}, race_best {case['best']}, race {dict(zip(RFIELDS, case['race']))}")


# ---------------------------------------------------------------------------------------------------------------------------------------------
# the game runs
PIN = {}
for _i, _k in enumerate(["thrust", "brake", "speed_cap", "yaw_accel", "yaw_damp", "roll_gain", "roll_smooth", "hover", "back_dist", "cam_height", "look_ahead", "start_section", "reserved"]):
    PIN[f"ship_cfg+{4 * _i}"] = C.CFG0[_k]
for _i, _k in enumerate(["radius", "wall_damp", "yaw_fix", "boost_impulse", "thud_gap", "off_limit"]):
    PIN[f"collide_cfg+{4 * _i}"] = C.CFG[_k]
for _i, _k in enumerate(["drag", "grip", "pitch_smooth", "reserved"]):
    PIN[f"handling_cfg+{4 * _i}"] = H.HCFG0[_k]


def pin(laps, count_from=3):
    d = dict(PIN)
    d["race_cfg+0"], d["race_cfg+4"], d["race_cfg+8"], d["race_cfg+12"] = laps, 2, count_from, 0
    return d


_pose_cache = {}


def ghost_pose(T, sec):
    key = (id(T), sec)
    if key not in _pose_cache:
        S = T["sections"][sec]
        pos = [S["centre"][i] + ((S["up"][i] * 120) >> 12) for i in range(3)]
        yaw = SR.heading_angle(S["forward"][0], S["forward"][2]) << 12
        pitch = SR.pitch_angle(S["forward"][1]) << 12
        _pose_cache[key] = pos + [0, yaw, pitch, 0, 0]
    return _pose_cache[key]


def hold(path, v, k):
    path.extend([v] * k)


def route_race1(N):
    p = []
    hold(p, 0, 4)
    for v in (-1, -2, -3, -2, -1, 0):               # a backward excursion over the start line: the warning, no lap
        hold(p, v, 2)
    for v in range(1, N + 3):                       # lap 1, slowly; the line is crossed at N
        hold(p, v, 2)
    for v in (N + 1, N, N - 1, N, N + 1, N + 2):    # back over the line and forward again: the lap is neither lost nor counted twice
        hold(p, v, 2)
    for v in range(N + 3, 2 * N):
        hold(p, v, 2)
    for v in range(2 * N, 3 * N + 1):               # lap 3 at one section per tick: the best lap, exactly N ticks
        hold(p, v, 1)
    return p


def route_race2(N):
    p = [0]
    for v in range(1, 3 * N + 1):                   # every lap at one section per tick: N ticks, the first N + 1 (a tie with race 1's best)
        p.append(v)
    return p


def route_track2(N):
    p = [0, 0, 0]
    for v in range(1, 2 * N + 1):
        p.append(v)
    return p


def ghost_for(T, route):
    N = len(T["sections"])
    s0 = T["start_section"]
    return [ghost_pose(T, (s0 + v) % N) for v in route]


R1 = route_race1(len(T1["sections"]))
R2 = route_race2(len(T1["sections"]))
R3 = route_track2(len(T2["sections"]))

RUNS = {
    "drive": dict(track=1, laps=1, params={"patch": pin(1), "start_frame": 6, "bot": True, "results_wait": 20, "race_wait": 30, "tail": 10}, frames=3800),
    "ghost": dict(track=1, laps=3, params={"patch": pin(3), "start_frame": 6, "ghosts": [ghost_for(T1, R1), ghost_for(T1, R2)], "results_wait": 20, "tail": 10},
                  frames=len(R1) + len(R2) + 1000),
    "track2": dict(track=2, laps=2, params={"patch": pin(2), "start_frame": 12, "track2": True, "ghosts": [ghost_for(T2, R3)], "results_exit": "START", "tail": 20}, frames=len(R3) + 800),
}

_runs = {}

# the default session of the harness is the driven lap (probe.lua reads its parameters from this file)
_def = _TMP / "params_drive.lua"
_def.write_text("PARAMS = " + lua_val(dict(RUNS["drive"]["params"], mode="game")) + "\n")
os.environ["CH41_PARAMS"] = str(_def)


class Run:
    pass


def run_of(ctx, name):
    if name in _runs:
        return _runs[name]
    spec = RUNS[name]
    if name == "drive":
        r = ctx.result
    else:
        r = ctx.run(name, probe=probe_gen(ctx, name, dict(spec["params"], mode="game")), max_frames=spec["frames"])
    r.require_finished()
    exc = exception_of(r)
    if exc:
        raise CheckFailure(expected="no CPU exception", actual=f"CPU exception {exc['code']} at pc 0x{exc['epc']:08X}, address 0x{exc['badvaddr']:08X}",
                           hint="A NULL track, a section index out of range, a store through a bad pointer.")
    o = Run()
    o.r, o.name, o.spec = r, name, spec
    o.T = T1 if spec["track"] == 1 else T2
    o.cfg = dict(laps=spec["laps"], wrong_way=2, count_from=3, reserved=0)
    o.info = r.record("info") or {}
    o.rows = r.record("rows") or []
    o.hz = o.info.get("hz", 60)
    expect_true(o.info.get("load_status") == 0, "the program loads everything and starts", f"info {o.info}", "Booting + loading takes about 400 emulated frames.")
    expect_true(len(o.rows) > 100, "the game left the title and the probe recorded frames", f"{len(o.rows)} rows",
                "START on the title must enter the countdown (game_update, set_state).")
    _runs[name] = o
    return o


def rrace(row):
    return H.Race.from_words(row["race"])


def model_frame(o, prev, row, best):
    """Replays one frame from the previous frame's recorded state. Returns (race, best, sfx, state_after, ticks_run) or None when it cannot (multi-tick race frames)."""
    st = prev["state"]
    rc = rrace(prev)
    sfx = []
    if st == H.COUNTDOWN:
        state = st
        for _ in range(row["ticks"]):
            ev = H.countdown_tick(rc, o.hz, o.cfg)
            if ev == H.BEEP:
                sfx.append(100 + 3)
            if ev == H.GO:
                sfx.append(100 + 4)
                state = H.RACE
                break
        return rc, best, sfx, state
    return None


def check_run_basics(o):
    expect_true(o.rows[0]["state"] == H.COUNTDOWN, "the first frame off the title is the countdown", f"state {o.rows[0]['state']}", "START on the title -> STATE_COUNTDOWN.")


def sequence_of_states(rows):
    seq = []
    for row in rows:
        if not seq or seq[-1] != row["state"]:
            seq.append(row["state"])
    return seq


# ---- the state machine --------------------------------------------------------------------------------------------------------------------
@check("state_machine_in_order", hint="TITLE -START-> COUNTDOWN -GO-> RACE -last lap-> RESULTS -CROSS-> COUNTDOWN -> RACE -START-> TITLE; state_changes counts every change, once per change.")
def _(ctx):
    o = run_of(ctx, "drive")
    seq = sequence_of_states(o.rows)
    expect_eq(seq, [1, 2, 3, 1, 2, 0], "the states the game went through (1 countdown, 2 race, 3 results, 0 title), after the title", hint="Entering and leaving each state: README 5.7.")
    prev = None
    for row in o.rows:
        if prev is not None:
            want = prev["changes"] + (1 if row["state"] != prev["state"] else 0)
            expect_eq(row["changes"], want, f"state_changes at frame {row['n']} (the state went {prev['state']} -> {row['state']})", hint="One increment per change, none while the state stays.")
        prev = row
    expect_eq(o.rows[0]["changes"], 1, "state_changes after START on the title")
    g = run_of(ctx, "ghost")
    expect_eq(sequence_of_states(g.rows), [1, 2, 3, 1, 2, 3], "the states of the ghost run (two complete races)")


@check("countdown_freezes_and_beeps", hint="During the countdown the ship does not move and the pad does not steer; a beep (SMP_BEEP) on countdown ticks 0, hz, 2 hz; GO (SMP_GO) when the countdown ends, "
                                          "which is the tick the state becomes RACE; race.cd_ticks counts the ticks run.")
def _(ctx):
    for name in ("drive", "ghost", "track2"):
        o = run_of(ctx, name)
        groups, cur = [], None
        for i, row in enumerate(o.rows):
            if row["state"] == H.COUNTDOWN:
                if cur is None:
                    cur = []
                    groups.append(cur)
                cur.append(row)
            elif cur is not None:
                cur.append(row)                        # the first frame of the race: its tick ends the countdown
                cur = None
        for rows in groups:
            body = [r for r in rows if r["state"] == H.COUNTDOWN]
            first = body[0]
            want_beeps, prev_cd = [], 0
            for row in body:
                expect_true(row["ship"] == first["ship"], f"{name}: the ship stays put in the countdown (frame {row['n']})", show(row["ship"]), f"it started at {show(first['ship'])}")
                for tickno in range(prev_cd, row["race"][0]):
                    if tickno % o.hz == 0 and tickno < 3 * o.hz:
                        want_beeps.append(row["n"])
                prev_cd = row["race"][0]
            got_beeps = [r["n"] for r in body if 103 in r["sfx"]]
            expect_eq(len(got_beeps), 3, f"{name}: beeps during one countdown (SMP_BEEP = 3)", hint="One per second: ticks 0, 60, 120.")
            expect_eq(got_beeps, want_beeps, f"{name}: the frames that beep", hint="A beep exactly on the tick of the second boundary, not before or after.")
            last = rows[-1]
            expect_eq(last["state"], H.RACE, f"{name}: the countdown ends in the race")
            expect_true(104 in last["sfx"], f"{name}: the GO sound (SMP_GO = 4) on the frame the race begins", f"{last['sfx']}", "audio_play_sfx(SMP_GO) then set_state(STATE_RACE).")
            expect_eq(last["race"][0], 3 * o.hz, f"{name}: race.cd_ticks when GO sounds", hint="count_from * hz = 180 at NTSC.")
            expect_eq(last["race"][1], 0, f"{name}: race.ticks when GO sounds (no race tick yet)")


def replay_race_frame(o, prev, row, best):
    """Model of one RACE frame from the recorded state of the previous frame, with the ticks the program really ran and the pad it really got."""
    ship = list(prev["ship"])
    section = prev["section"]
    race = rrace(prev)
    sfx, state = [], H.RACE
    cs = C.State.from_words(prev["cs"])
    for k in range(len(row["pads"])):
        ship = H.update(ship, row["pads"][k], 4096)
        section, _ = C.collide_ship(o.T, cs, ship, section, prev["sticks"] + k)
        H.auto_pitch(ship, o.T, section, 4096)
        flags, best = H.tick(race, o.T, section, best, o.cfg)
        if flags & H.FINISH:
            state = H.RESULTS
            break
        if flags & H.LAP:
            sfx.append(203)
    return dict(ship=ship, section=section, race=race, cs=cs, sfx=sfx, state=state, best=best)


def compare_frame(row, m, check_ship=True):
    if row["state"] != m["state"]:
        return f"state: got {row['state']}, expected {m['state']}"
    if check_ship:
        for i, name in enumerate(SHIP_FIELDS):
            if row["ship"][i] != m["ship"][i]:
                if name == "yaw" and abs(((row["ship"][i] - m["ship"][i] + (1 << 23)) % (1 << 24)) - (1 << 23)) == 0:
                    continue
                return f"ship.{name}: got {row['ship'][i]}, expected {m['ship'][i]}"
        if row["section"] != m["section"]:
            return f"ship_section: got {row['section']}, expected {m['section']}"
        want_cs = m["cs"].words()
        for k, name in enumerate(["hits", "thuds", "boosts", "respawns", "on_boost", "last_hit", "dist_left", "dist_right", "face"]):
            if abs(row["cs"][k] - want_cs[k]) > (1 if name.startswith("dist") else 0):
                return f"collide_state.{name}: got {row['cs'][k]}, expected {want_cs[k]}"
    w = m["race"].words()
    for i, name in enumerate(RFIELDS):
        if row["race"][i] != w[i]:
            return f"race.{name}: got {row['race'][i]}, expected {w[i]}"
    if row["best"] != m["best"]:
        return f"race_best: got {row['best']}, expected {m['best']}"
    if row["sfx"] != m["sfx"]:
        return f"sounds raised this frame: got {row['sfx']}, expected {m['sfx']} (200 + sample id: 3 = SMP_BEEP)"
    return None


def replay_run(o):
    """Replays every frame. Returns (checked, problems). A ghost frame (posed) cannot be replayed from the previous recorded ship, because the probe moved the ship between the frames:
    its race part is replayed from the section the program itself computed."""
    checked, problems = 0, []
    prev = None
    for row in o.rows:
        if prev is not None and prev["state"] == H.RACE:
            if row["state"] == H.TITLE and not row["pads"]:
                pass                                   # START aborted the race: no tick runs on that frame
            elif not row["pads"]:
                problems.append(f"frame {row['n']}: the race state ran no tick")
            elif row["posed"]:
                rc = rrace(prev)
                flags, nb = H.tick(rc, o.T, row["section"], prev["best"], o.cfg)
                m = dict(race=rc, best=nb, sfx=[203] if (flags & H.LAP and not flags & H.FINISH) else [], state=H.RESULTS if flags & H.FINISH else H.RACE)
                bad = compare_frame(row, m, check_ship=False) or (f"the ghost frame ran {len(row['pads'])} ticks" if len(row["pads"]) != 1 else None)
                checked += 1
                if bad:
                    problems.append(f"frame {row['n']} (race tick {prev['race'][1] + 1}): {bad}")
            else:
                bad = compare_frame(row, replay_race_frame(o, prev, row, prev["best"]))
                checked += 1
                if bad:
                    problems.append(f"frame {row['n']} (race tick {prev['race'][1] + 1}): {bad}")
        elif prev is not None and prev["state"] == H.COUNTDOWN:
            rc, b, sfx, st = model_frame(o, prev, row, prev["best"])
            bad = compare_frame(row, dict(race=rc, best=b, sfx=sfx, state=st), check_ship=False)
            checked += 1
            if bad:
                problems.append(f"frame {row['n']} (countdown): {bad}")
        prev = row
    return checked, problems


@check("frames_replay_with_the_model", hint="Every frame starts from the previous frame's state: ship_update, collide_ship, handling_auto_pitch, race_tick, in that order per tick; the model must agree on the ship, "
                                           "ship_section, collide_state, the race words, race_best and the sounds raised.")
def _(ctx):
    for name in ("drive", "ghost", "track2"):
        o = run_of(ctx, name)
        checked, problems = replay_run(o)
        expect_true(checked > 150, f"{name}: frames replayed", f"{checked}", "")
        expect_true(not problems, f"{name}: every frame equals ship_update + collide_ship + auto-pitch + race_tick of the model", f"{len(problems)} frames differ; first: {problems[:3]}",
                    "Read the first difference: a ship field means the handling (drag, skid, pitch), a race field the lap logic, a sound the game_update wiring.")
        mt = sum(1 for r in o.rows if r["state"] == H.RACE and len(r["pads"]) > 1)
        expect_true(mt <= len(o.rows) // 20, f"{name}: frames with several ticks are rare", f"{mt}", "The emulator does not charge GPU time; a slow frame of your own would run more ticks.")


# ---- facts that do not depend on the model ----------------------------------------------------------------------------------------------
def index_progress(rows, N, first_sec):
    """Progress by index arithmetic (valid on the generated tracks, where `next` is index + 1): per row, the signed ring distance between two frames' sections."""
    p = 0
    prev = first_sec
    out = []
    for row in rows:
        d = (row["section"] - prev) % N
        if d > N // 2:
            d -= N
        p += d
        prev = row["section"]
        out.append(p)
    return out


@check("laps_cross_the_start_line", hint="A lap is N forward section steps from the section the race began on (N = the track's section_count): lap = floor(furthest progress / N), counted on the frame the ship "
                                         "enters the start section again; going back over the line and forward again does not count twice.")
def _(ctx):
    for name in ("drive", "ghost", "track2"):
        o = run_of(ctx, name)
        T = o.T
        N = len(T["sections"])
        laps_cfg = o.cfg["laps"]
        # each race: the rows from its first RACE row until its RESULTS row
        races, cur = [], None
        for i, row in enumerate(o.rows):
            if row["state"] == H.RACE and (cur is None):
                cur = [i]
            if row["state"] == H.RESULTS and cur is not None:
                cur.append(i)
                races.append(cur)
                cur = None
        expect_true(len(races) >= 1, f"{name}: a race finished", f"{races}", "The pilot or the ghost must finish the race: laps counted, then RESULTS.")
        for a, b in races:
            seg = o.rows[a:b + 1]
            first = o.rows[a - 1]["section"]
            prog = index_progress(seg, N, first)
            mx = 0
            for row, pv in zip(seg, prog):
                mx = max(mx, pv)
                want_lap = min(mx // N, laps_cfg)
                expect_eq(row["race"][2], want_lap, f"{name}: laps completed at frame {row['n']} (furthest progress {mx} of {N} sections per lap)", hint="The lap changes on the frame the ship enters the start section for the (lap + 1)-th time.")
            expect_eq(seg[-1]["race"][2], laps_cfg, f"{name}: laps at the results", hint="race_cfg.laps (patched to this run's value).")


@check("race_clock_counts_ticks", hint="race.ticks = the race ticks run since GO = the number of ship_update calls of the RACE state; the lap times add up to the total; the total is race.ticks at the finish.")
def _(ctx):
    for name in ("drive", "ghost", "track2"):
        o = run_of(ctx, name)
        expect_true(any(r["state"] == H.RACE for r in o.rows) and any(r["state"] == H.RESULTS for r in o.rows),
                    f"{name}: the run reaches RACE and RESULTS", "never", "The countdown must end (race_countdown_tick, game_update) and the race must finish (race_tick).")
        ticks = 0
        for row in o.rows:
            if row["state"] == H.COUNTDOWN:
                ticks = 0
            if row["state"] == H.RACE or (row["state"] == H.RESULTS and row["pads"]):
                ticks += len(row["pads"])
                expect_eq(row["race"][1], ticks, f"{name}: race.ticks at frame {row['n']}")
            if row["state"] == H.RESULTS:
                rc = rrace(row)
                laps = o.cfg["laps"]
                expect_eq(rc.total, rc.ticks, f"{name}: total = the race ticks at the finish")
                expect_eq(sum(rc.lap_ticks[:laps]), rc.total, f"{name}: the lap times add up to the total")
                expect_eq(rc.best_lap, min(rc.lap_ticks[:laps]), f"{name}: best_lap is the fastest lap of the race")


@check("one_lap_in_a_window", hint="The pilot flies the generated track in one lap of 112,770 units: not faster than the top speed allows (drag-limited 47.25 plus boosts, at most 60) and not absurdly slow; "
                                   "RESULTS shows the three counters of README 5.8.")
def _(ctx):
    o = run_of(ctx, "drive")
    res = next(r for r in o.rows if r["state"] == H.RESULTS)
    total = res["race"][8]
    tl = o.T["total_length"]
    lo = tl * 4096 // (60 * 4096)
    hi = 4500
    expect_true(lo <= total <= hi, f"lap time in ticks between {lo} and {hi}", f"{total}", "Too fast: the speed cap or the drag is not applied. Too slow: the ship crawls or hits the walls (skid, pitch?).")
    expect_true(res["race"][9] == total, "the best lap of a one-lap race is the lap", f"best_lap {res['race'][9]}, total {total}", "")
    expect_eq(res["race"][10], 1, "new_best on the first finished race since power-on", hint="race_best was 0.")
    expect_eq(res["best"], total, "race_best after the first race")


@check("top_speed_is_drag_limited", hint="With thrust 0.75 per tick and a drag of 1/64 per tick the speed settles near 47.25 (not the cap of 60); only a boost pad goes above it, briefly.")
def _(ctx):
    o = run_of(ctx, "drive")
    sp = [r["ship"][9] for r in o.rows if r["state"] == H.RACE]
    top = max(sp)
    expect_true(top <= 53 * 4096, "no speed above 47.25 + one boost impulse (about 53.0)", f"{top / 4096:.2f}", "No drag? The speed would run to the cap (60).")
    settled = sorted(sp)[len(sp) * 3 // 4]
    expect_true(40 * 4096 <= settled <= 49 * 4096, "most of the lap is flown near the drag-limited top speed (75th percentile of the speeds)", f"{settled / 4096:.2f}", "Drag too strong or too weak, or the pilot is braking all the time.")


@check("ship_slides_in_turns", hint="vel is not forward * speed any more: in a turn the velocity direction lags the facing (skid). The sine of the angle between them (horizontal) must reach a few percent.")
def _(ctx):
    o = run_of(ctx, "drive")
    best = 0.0
    for r in o.rows:
        if r["state"] != H.RACE:
            continue
        s = r["ship"]
        f = SR.forward(s)
        vx, vz = s[6], s[8]
        nv = math.hypot(vx, vz)
        nf = math.hypot(f[0], f[2])
        if nv > 20 * 4096 and nf > 0:
            best = max(best, abs(vx * f[2] - vz * f[0]) / (nv * nf))
    expect_true(best > 0.03, "the velocity direction departs from the facing by at least 1.7 degrees somewhere in the lap", f"{best:.4f}", "vel = forward * speed exactly? Then grip 4096: no skid.")
    expect_true(best < 0.9, "the ship does not slide sideways like a puck", f"{best:.3f}", "The skid is too loose.")


@check("pitch_follows_the_road", hint="The nose eases toward the slope of the road under the ship: |pitch - target| stays small on average once the ship has run for a while.")
def _(ctx):
    o = run_of(ctx, "drive")
    errs = []
    for r in o.rows:
        if r["state"] != H.RACE or r["section"] < 0 or r["race"][1] < 60:
            continue
        up = o.T["sections"][r["section"]]["up"]
        errs.append(abs(H.pitch_target(up, r["ship"][10]) - r["ship"][11]) >> 12)
    mean = sum(errs) / len(errs)
    expect_true(mean < 12, "mean pitch error against the target, in whole angle units (1 unit = 0.088 degrees)", f"{mean:.2f}", "handling_auto_pitch not called, or in the wrong state, or the wrong section.")
    expect_true(max(abs(r["ship"][11]) for r in o.rows if r["state"] == H.RACE) >> 12 > 20, "the pitch really changes with the road (more than 20 units somewhere)", "flat", "The pitch never moves?")


@check("text_matches_the_race", hint="Every frame's race_text equals race_format_text of that frame's state and race words (README 5.8): the timer, laps, WRONG WAY, the countdown number and the results.")
def _(ctx):
    for name in ("drive", "ghost", "track2"):
        o = run_of(ctx, name)
        for row in o.rows:
            want = H.format_text(rrace(row), row["state"], o.hz, row["best"], o.cfg)
            got = [(t if t is not None else "?") for t in row["text"]]
            expect_true(got == want, f"{name}: frame {row['n']} (state {row['state']}): the text on screen", f"{[l for l in got if l]}", f"expected {[l for l in want if l]}")


@check("results_screen", hint="At the finish the state is RESULTS: the lap times, the total and the best lap of this run; 'NEW BEST LAP' only for a race that beat race_best; race_best survives a restart.")
def _(ctx):
    g = run_of(ctx, "ghost")
    res = [r for r in g.rows if r["state"] == H.RESULTS]
    first = next(r for r in res if r["race"][10] == 1 or r["race"][7] == 1)
    r1 = [r for r in res if r["n"] < next(x["n"] for x in g.rows if x["state"] == H.COUNTDOWN and x["n"] > res[0]["n"])][-1]
    r2 = res[-1]
    N = len(T1["sections"])
    expect_eq(r1["race"][2], 3, "race 1: laps completed")
    expect_eq(r1["race"][10], 1, "race 1: new_best (the first race since power-on)")
    expect_eq(r1["race"][9], N, "race 1: the best lap is the third, flown at one section per tick (N ticks)")
    expect_eq(r1["best"], N, "race_best after race 1")
    expect_true("NEW BEST LAP" in r1["text"], "race 1: the results say NEW BEST LAP", f"{[l for l in r1['text'] if l]}", "README 5.8.")
    expect_eq(r2["race"][2], 3, "race 2: laps completed")
    expect_eq(r2["race"][10], 0, "race 2: new_best is 0 (its best lap TIES race_best: not better)")
    expect_eq(r2["best"], N, "race_best after race 2 (kept)")
    expect_true("NEW BEST LAP" not in r2["text"], "race 2: no NEW BEST LAP", f"{[l for l in r2['text'] if l]}", "A tie is not a new best.")
    c2 = next(x for x in g.rows if x["state"] == H.COUNTDOWN and x["n"] > r1["n"])
    expect_eq(c2["race"][1:2] + c2["race"][2:5], [0, 0, 0, 0], "the restart: ticks, lap, progress, furthest are zero again", hint="race_reset on entering the countdown.")
    expect_eq(c2["race"][5], -1, "the restart: prev_section = -1")
    expect_eq(c2["best"], N, "race_best survives the restart")
    expect_true(any(l.startswith("RESULTS") for l in r1["text"]), "the results screen has its title", f"{r1['text'][:3]}", "")


@check("restart_and_abort", hint="RESULTS: CROSS restarts (a new countdown, ship back on the start line), START goes to the title; START during the race aborts to the title, where the best lap is shown.")
def _(ctx):
    o = run_of(ctx, "drive")
    rows = o.rows
    # the second countdown starts on the start line: the ship equals the first countdown's
    cds = [i for i, r in enumerate(rows) if r["state"] == 1 and (i == 0 or rows[i - 1]["state"] != 1)]
    expect_eq(len(cds), 2, "countdowns started", hint="START, then the restart from RESULTS.")
    expect_true(rows[cds[0]]["ship"] == rows[cds[1]]["ship"], "the restart puts the ship back on the start line", show(rows[cds[1]]["ship"]), f"first: {show(rows[cds[0]]['ship'])}")
    last = rows[-1]
    expect_eq(last["state"], 0, "the run ends on the title (START aborted the second race)")
    expect_true(last["text"][0].startswith("BEST LAP "), "the title shows the best lap", f"{last['text'][0]!r}", "race_format_text(STATE_TITLE): 'BEST LAP m:ss.cc' when race_best > 0.")
    expect_eq(last["best"], rows[[i for i, r in enumerate(rows) if r["state"] == 3][0]]["race"][8], "race_best (one lap) = the first race's total")


@check("wrong_way_warning_in_the_game", hint="Driving backward over the start line raises race.wrong_way after two sections behind the furthest point and the text WRONG WAY; coming forward again clears it; no lap is counted.")
def _(ctx):
    g = run_of(ctx, "ghost")
    race1 = []
    for row in g.rows:
        if race1 and row["state"] != H.RACE:
            race1.append(row)                           # the frame that finishes it
            break
        if row["state"] == H.RACE:
            race1.append(row)
    flagged = [r for r in race1 if r["race"][6] == 1]
    expect_true(len(flagged) >= 4, "the warning is raised during the backward excursion", f"{len(flagged)} frames", "wrong_way = furthest - progress >= 2.")
    for r in flagged[:4]:
        expect_true("WRONG WAY" in r["text"], f"frame {r['n']}: the text says WRONG WAY while the flag is set", f"{[l for l in r['text'] if l]}", "README 5.8.")
    early = [r for r in race1[:40]]
    expect_true(any(r["race"][6] == 0 for r in early[-8:]), "the warning clears when the ship is back at the start", "still set", "wrong_way is recomputed every tick.")
    expect_true(all(r["race"][2] == 0 for r in early), "no lap is counted in the backward excursion", f"{[r['race'][2] for r in early]}", "A lap needs N net forward steps.")
    after = [r for r in race1 if r["race"][2] == 1]
    expect_true(any(r["race"][6] == 1 for r in after), "going back over the line after lap 1 raises the warning again", "never", "")
    expect_eq(max(r["race"][2] for r in race1), 3, "laps completed in race 1 despite the excursions")


@check("second_track", hint="LEFT / RIGHT on the title pick the track; the race uses that track's own section count (104 on track 2) and the configured number of laps.")
def _(ctx):
    o = run_of(ctx, "track2")
    expect_true(all(r["sel"] == 2 for r in o.rows), "track_selected is 2 during the whole run", f"{set(r['sel'] for r in o.rows)}", "game_update: RIGHT -> track_switch(2).")
    res = [r for r in o.rows if r["state"] == H.RESULTS]
    expect_true(len(res) > 0, "two laps of track 2 finish", "never", "N = track.section_count, not 112; laps from race_cfg.")
    expect_eq(res[0]["race"][2], 2, "laps completed on track 2")
    expect_eq(res[0]["race"][8], len(R3), "the total ticks of two laps (the ghost's route: 3 ticks at the start, then one section per tick)", hint="")
    expect_true("TOTAL " + H.format_time(len(R3), 60) in res[0]["text"], "the results text shows the total", f"{[l for l in res[0]['text'] if l]}", "race_format_time.")
    expect_eq(sequence_of_states(o.rows), [1, 2, 3, 0], "START on the results screen goes to the title (not to a new race)", hint="RESULTS: START -> STATE_TITLE; CROSS -> STATE_COUNTDOWN.")
    expect_true(o.rows[-1]["text"][0] == "BEST LAP " + H.format_time(res[0]["race"][9], 60), "the title then shows the best lap", f"{o.rows[-1]['text'][0]!r}", "race_format_text(STATE_TITLE).")
