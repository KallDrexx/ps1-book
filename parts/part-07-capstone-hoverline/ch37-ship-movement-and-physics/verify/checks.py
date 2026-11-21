"""Chapter 37 checks: Ship Movement and Physics (a rigid body on the start line: thrust, brake, yaw with damping, banking, a fixed time step, NTSC / PAL, a chase camera).
Build: CMake + PSn00bSDK; the CMake rule runs tools/assets/mkassets.py (SHIP.SHP, SHIP.TPK, TRACK.TRK ...). The emulator BOOTS THE .cue.
THE MODEL: example/ship_ref.py, exact integer arithmetic (PSn00bSDK's isin ported as in Chapters 24 and 28), the same as README 5 and ship.h. Four emulator runs:
  default  NTSC, the book's constants, a scripted pad (driven by the program's own ship_ticks): CROSS 2.0 s, LEFT 1.0 s, coast, SQUARE 0.9 s, RIGHT 0.6 s.
  pal      the same script in seconds (50 ticks per second), video_mode = 1 written at the entry of `main`: GP1(08h) bit 3, dt_scale 4915.
  alt      NTSC, EVERY constant of ship_cfg patched (including the start section 37 and the hover height), R1 pressed once at tick 60 (subdivision on: about 30 frames per second,
           two ticks per frame): the world must still advance one tick per vertical blank.
  unit     ship_update, ship_forward, ship_matrix, chase_camera_update, heading_angle, pitch_angle called DIRECTLY from the probe with crafted states (the pad and the time step
           as arguments, no emulated pad): edge cases and random cases, all compared exactly with the model.
Every ship_update call of a driven run is recorded (arguments, state before, state after): each one must equal the model (exact), consecutive calls must chain, the pad
sequence must be the script, and the start state must be the model's place().
Independent of the port of isin: the velocity direction against math.sin / math.cos, the roll's sign against the turn, the camera behind and above in the +y-down world, the
ship's orange engine pods in the screenshots (position and a tilt that follows the bank)."""

import atexit
import json
import math
import os
import random
import shutil
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
import ship_ref as M  # noqa: E402

CPU_HZ = 33868800
W, H, CX, CY = 320, 240, 160, 120
BG = (24, 24, 48)
PROJ_H = 320
MAX_FRAMES = 1800
SCRATCH = 0x801C0000          # a Ship for the direct calls
SCRATCH_OUT = 0x801C0200      # a MATRIX / output words
SEED = int(os.environ.get("CH37_SEED") or random.randrange(1, 10 ** 6))
RNG = random.Random(SEED)
print(f"[ch37 unit-test seed {SEED}; CH37_SEED={SEED} repeats it]")

config(
    title="Ship Movement and Physics: thrust, steering, banking, fixed time step, NTSC / PAL, chase camera",
    build="cmake", exe="game.exe", sym="", elf="game.elf", iso="hoverline.cue",
    break_at=None, max_frames=MAX_FRAMES, timeout=240, vram=False,
)

_TMP = Path(tempfile.mkdtemp(prefix="ch37ref-"))
atexit.register(shutil.rmtree, _TMP, True)
FILES, MANIFESTS = mkassets.build(_TMP / "assets", seed=1)
TRK = formats.parse_trk(FILES["TRACK.TRK"])
CFG = dict(M.CFG0)
CFG_WORDS = [CFG[k] for k in M.CFG_ORDER]
CROSS, SQUARE, LEFT, RIGHT = M.INPUT["CROSS"], M.INPUT["SQUARE"], M.INPUT["LEFT"], M.INPUT["RIGHT"]

# the patched constants of the alt run (every one differs from the default)
ALT = dict(thrust=2000, brake=4500, speed_cap=40 * 4096, yaw_accel=12000, yaw_damp=800, roll_gain=10, roll_smooth=700, hover=200,
           back_dist=1100, cam_height=400, look_ahead=900, start_section=37, reserved=0)
ALT_WORDS = [ALT[k] for k in M.CFG_ORDER]
ALT_R1_TICK = 60

# ---- the scripts (seconds -> ticks) ------------------------------------------------------------------------------------------------------
SCRIPT = M.SCRIPT
END_S = M.END


def script_ticks(hz):
    return [[b, round(t0 * hz), round(t1 * hz)] for b, t0, t1 in SCRIPT]


SHOTS = [["cruise", 60], ["left", 140], ["right", 296]]            # NTSC ticks: straight at full speed, in the left turn, in the right turn
SHOTS_PAL = [[n, round(t * 5 / 6)] for n, t in SHOTS]


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


def write_params(name, params):
    p = _TMP / f"params_{name}.lua"
    p.write_text("PARAMS = " + lua_val(params) + "\n")
    return p


def probe_for(name, params):
    """A probe file that sets PARAMS, then loads the real probe."""
    gen = _TMP / f"probe_{name}.lua"
    gen.write_text("PARAMS = " + lua_val(params) + "\ndofile(" + json.dumps(str(HERE / "probe.lua")) + ")\n")
    return gen


def game_params(pal=0, cfg=None, subdiv=0, r1_tick=None):
    hz = 50 if pal else 60
    d = {"mode": "game", "pal": pal, "subdiv": subdiv, "cfg": {i: v for i, v in enumerate(cfg)} if cfg else {},
         "ticks": script_ticks(hz), "end_tick": round(END_S * hz), "end_frame": 520, "shots": SHOTS_PAL if pal else SHOTS, "frame_sz": 64 * 4 + 32768 + 16}
    if r1_tick:
        d["r1_tick"] = r1_tick
    return d


# the default run's PARAMS go through the environment (the default run starts before any check)
os.environ["CH37_PARAMS"] = str(write_params("default", game_params()))
RUN_ARGS = {
    "pal": dict(probe=probe_for("pal", game_params(pal=1))),
    "alt": dict(probe=probe_for("alt", game_params(cfg=ALT_WORDS, r1_tick=ALT_R1_TICK))),
}


def s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


# ---- the recorded runs -------------------------------------------------------------------------------------------------------------------
def run_of(ctx, name):
    r = ctx.result if name == "default" else ctx.run(name, **RUN_ARGS[name])
    r.require_finished()
    return r


def exception_of(r):
    try:
        return r.record("exception")
    except Exception:
        return None


def calls_of(r):
    cs = r.record("calls") or []
    if any("after" not in c for c in cs):
        raise CheckFailure(expected="every ship_update call returns", actual="a call never returned", hint="Does ship_update return normally?", message="a ship_update call never returned")
    if not cs:
        raise CheckFailure(expected="ship_update called every tick of the game", actual="ship_update was never called in the game state",
                           hint="game_update: run ship_update(&ship, input_buttons(), dt_scale) frame_ticks times per game frame.")
    return cs


def rows_of(r):
    return r.record("rows") or []


def cfg_for(name):
    return ALT if name == "alt" else CFG


def hz_for(name):
    return 50 if name == "pal" else 60


def start_model(cfg):
    sec = cfg["start_section"] if cfg["start_section"] >= 0 else TRK["start_section"]
    s = TRK["sections"][sec]
    return M.place(s["centre"], s["up"], s["forward"], cfg["hover"]), sec


def show(v):
    return "(" + ", ".join(str(x) for x in v) + ")"


def first_diff(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return M.SHIP_FIELDS[i], x, y
    return None


# ---- checks on the driven runs ------------------------------------------------------------------------------------------------------------
@check("runs_ok", hint="The program must boot from the disc, load SHIP.SHP / SHIP.TPK, enter the game on START and call ship_update every tick.")
def _(ctx):
    for name in ("default", "pal", "alt"):
        r = run_of(ctx, name)
        exc = exception_of(r)
        if exc:
            raise CheckFailure(expected="no exception", actual=str(exc), hint="A crash in ship code or in the matrix / camera calls.", message=f"CPU exception in the {name} run")
        info = r.record("info")
        expect_eq(info.get("load_status"), 0, f"load_status ({name})", hint="load_status 5 = SHIP.TPK / SHIP.SHP could not be loaded or parsed (main.c).")
        expect_true(len(calls_of(r)) >= round(END_S * hz_for(name)) - 2, "ship_update called once per tick for the whole script",
                    f"{len(calls_of(r))} calls", "Does game_update call ship_update frame_ticks times per frame in the game state?")
        g = r.record("guards")
        for f in g:
            expect_true(all(b == 0xA5 for b in f), "guard bytes intact", str(f), "Something wrote past a primitive buffer.")


@check("start_pose", hint="ship_place: pos = centre + ((up * hover) >> 12), yaw and pitch from the section's forward, everything else 0.")
def _(ctx):
    for name in ("default", "alt"):
        r = run_of(ctx, name)
        cfg = cfg_for(name)
        want, sec = start_model(cfg)
        got = calls_of(r)[0]["before"]
        d = first_diff(got, want)
        expect_true(d is None, f"start state on section {sec} ({name}) = {show(want)}", show(got),
                    f"first difference: {d}. Section centre {TRK['sections'][sec]['centre']}, up {TRK['sections'][sec]['up']}, forward {TRK['sections'][sec]['forward']}.")
        # independent of the port: the hover height along the section's up and the heading from the forward vector
        s = TRK["sections"][sec]
        up = s["up"]
        n = math.sqrt(sum(c * c for c in up))
        h = sum((got[i] - s["centre"][i]) * up[i] for i in range(3)) / n
        expect_true(abs(h - cfg["hover"]) <= 3, f"hover {cfg['hover']} above the road along up", f"{h:.1f}", "Add up * hover >> 12 to the section centre (up has NEGATIVE y: the ship ends above the road).")
        ang = math.atan2(s["forward"][0], s["forward"][2]) * 4096 / (2 * math.pi) % 4096
        yaw = got[10] / 4096
        expect_true(min(abs(ang - yaw), 4096 - abs(ang - yaw)) <= 1.5, f"yaw = heading of the section's forward ({ang:.1f})", f"{yaw:.1f}", "yaw: +z toward +x is positive (RotMatrix vy).")


@check("update_matches_model", hint="Every ship_update call must equal the model: input, yaw velocity, damping, yaw, roll, thrust / brake, cap, vel, position with the fraction.")
def _(ctx):
    for name in ("default", "pal", "alt"):
        r = run_of(ctx, name)
        cfg = cfg_for(name)
        cs = calls_of(r)
        for i, c in enumerate(cs):
            want = M.update(c["before"], c["pad"], c["dt"], cfg)
            d = first_diff(c["after"], want)
            expect_true(d is None, f"call {i} ({name}) pad {c['pad']:#06x} dt {c['dt']}: state {show(want)}", show(c["after"]),
                        f"first difference: {d}. State before: {show(c['before'])}.")
            if i:
                expect_true(c["before"] == cs[i - 1]["after"], "the state carries over between ticks", f"call {i}: {show(c['before'])} vs {show(cs[i - 1]['after'])}",
                            "Does anything else change the ship between ticks?")


@check("pad_script", hint="CROSS accelerates, LEFT / RIGHT steer, SQUARE brakes: the pad word given to ship_update must carry the scripted buttons.")
def _(ctx):
    for name in ("default", "pal"):
        r = run_of(ctx, name)
        hz = hz_for(name)
        cs = calls_of(r)
        expect_true(len(cs) >= round(END_S * hz) - 2, f"ship_update called every tick ({name})", str(len(cs)), "")
        for b, t0, t1 in SCRIPT:
            bit = M.INPUT[b]
            lo, hi = int((t0 + 0.15) * hz), int((t1 - 0.05) * hz)       # allow the pad's frame or two of latency
            miss = [i for i in range(lo, hi) if not cs[i]["pad"] & bit]
            expect_true(not miss, f"{b} held in ticks {lo}..{hi - 1} ({name})", f"missing in {len(miss)} ticks, first {miss[:3]}",
                        "Pass input_buttons() (or an equivalent mask) to ship_update. CROSS = INPUT_CROSS ...")
            early = [i for i in range(0, max(0, int((t0 - 0.15) * hz))) if cs[i]["pad"] & bit]
            late = [i for i in range(int((t1 + 0.15) * hz), len(cs)) if cs[i]["pad"] & bit]
            expect_true(not early and not late, f"{b} not held outside its window ({name})", f"early {early[:3]} late {late[:3]}", "Is a button mapped twice?")


@check("speed_cap", hint="speed = clamp(speed, 0, speed_cap) after thrust and brake; the cap is exact.")
def _(ctx):
    for name in ("default", "pal", "alt"):
        r = run_of(ctx, name)
        cap = cfg_for(name)["speed_cap"]
        sp = [c["after"][9] for c in calls_of(r)]
        expect_eq(max(sp), cap, f"top speed ({name})", hint="No cap, a cap that is too low, or one that is applied before the thrust.")
        expect_true(min(sp) >= 0, "speed never negative", str(min(sp)), "Braking must stop at 0, not reverse.")
        n2 = [math.sqrt(sum(v * v for v in c["after"][6:9])) for c in calls_of(r)]
        expect_true(max(n2) <= cap * 1.01, "|vel| <= speed_cap (+ 1%: the sin / cos table is not exactly unit length)", f"{max(n2):.0f} > {cap}", "vel = forward * speed.")


@check("brake_stops_at_zero", hint="SQUARE removes `brake` per tick; at 0 it stays 0 (the ship stops, it does not reverse).")
def _(ctx):
    r = run_of(ctx, "default")
    cs = calls_of(r)
    brake_idx = [i for i, c in enumerate(cs) if c["pad"] & SQUARE]
    expect_true(brake_idx, "SQUARE was held", "never", "The script presses SQUARE.")
    stopped = [i for i in brake_idx if cs[i]["after"][9] == 0]
    expect_true(len(stopped) >= 5, "speed reaches exactly 0 while braking and stays there", f"{len(stopped)} ticks at 0", "Clamp speed at 0 after braking.")
    for i in stopped:
        c = cs[i]
        expect_true(c["after"][6:9] == [0, 0, 0] and c["after"][0:3] == c["before"][0:3] and c["after"][3:6] == c["before"][3:6], "a stopped ship does not move",
                    f"tick {i}: {show(c['after'])}", "vel = forward * 0 = 0.")
    mid = [i for i in brake_idx if 0 < cs[i]["after"][9] < cs[i]["before"][9]]
    expect_true(len(mid) >= 5, "the speed falls in steps while braking", f"{len(mid)} ticks", "Subtract fx_mul(brake, dt) while SQUARE is held.")


@check("no_drag", hint="Without CROSS or SQUARE the speed does not change in this chapter (resistance comes in Chapter 41).")
def _(ctx):
    for name in ("default", "pal"):
        r = run_of(ctx, name)
        coast = [c for c in calls_of(r) if not c["pad"] & (CROSS | SQUARE) and c["before"][9] > 0]
        expect_true(len(coast) >= 20, "there are coasting ticks", str(len(coast)), "The script coasts after the turn.")
        for c in coast:
            expect_eq(c["after"][9], c["before"][9], f"speed while coasting ({name})", hint="No drag, no friction: speed is constant when nothing is held.")


@check("steering_and_banking", hint="LEFT turns the nose toward -x (yaw falls) and rolls the left wing down; RIGHT mirrors it; the roll follows the yaw rate and returns to 0.")
def _(ctx):
    r = run_of(ctx, "default")
    cs = calls_of(r)
    L = [c["after"] for c in cs if c["pad"] & LEFT]
    R = [c["after"] for c in cs if c["pad"] & RIGHT]
    expect_true(L and R, "LEFT and RIGHT were held", "no", "The script steers.")
    expect_true(all(a[13] < 0 for a in L[3:]), "LEFT: yaw_vel < 0", str([a[13] for a in L[:5]]), "LEFT is the negative direction.")
    expect_true(all(a[13] > 0 for a in R[3:]), "RIGHT: yaw_vel > 0", str([a[13] for a in R[:5]]), "RIGHT is the positive direction.")
    peak_l, peak_r = min(a[12] for a in L), max(a[12] for a in R)
    expect_true(peak_l <= -150 * 4096 and peak_r >= 150 * 4096, "banks into the turn by about 20 degrees (roll < 0 left, > 0 right)", f"{peak_l >> 12} / {peak_r >> 12} units",
                "roll target = yaw_vel * roll_gain, smoothed: left wing down is NEGATIVE roll.")
    # the yaw changes the way the nose points: left decreases it (mod a turn)
    yaw0 = L[0][10] >> 12
    yaw1 = L[-1][10] >> 12
    dyaw = (yaw1 - yaw0 + 2048) % 4096 - 2048
    expect_true(-1500 < dyaw < -600, "LEFT for one second turns the nose by about -840 units (-74 degrees)", f"{dyaw}", "yaw += yaw_vel * dt; LEFT adds a NEGATIVE yaw_accel.")
    # decay: after the last steering tick the yaw rate and the roll fade out
    last_l = max(i for i, c in enumerate(cs) if c["pad"] & LEFT)
    for k in (60,):
        a = cs[min(len(cs) - 1, last_l + k)]["after"]
        expect_true(a[13] == 0 and abs(a[12]) < 8 * 4096, "yaw damping and roll smoothing decay to ~0 within a second of letting go", f"yaw_vel {a[13]}, roll {a[12] >> 12} units", "The damping and the dead zone of README 5.5, step 2; the roll smoothing of step 4.")


@check("heading_and_velocity", hint="The velocity points along the ship's nose: (sin yaw cos pitch, -sin pitch, cos yaw cos pitch) * speed (checked against math.sin / math.cos).")
def _(ctx):
    for name in ("default", "pal", "alt"):
        r = run_of(ctx, name)
        worst = 0.0
        for c in calls_of(r):
            a = c["after"]
            if a[9] < 8 * 4096:
                continue
            yaw, pitch = a[10] / (1 << 24) * 2 * math.pi, a[11] / (1 << 24) * 2 * math.pi
            f = (math.sin(yaw) * math.cos(pitch), -math.sin(pitch), math.cos(yaw) * math.cos(pitch))
            for i in range(3):
                worst = max(worst, abs(a[6 + i] - f[i] * a[9]) / 4096)
        expect_true(worst < 0.5, f"|vel - forward * speed| < 0.5 unit ({name})", f"{worst:.2f} units", "forward = (sin yaw, 0, cos yaw): +z toward +x for positive yaw. Is x/z swapped, or a sign flipped?")


@check("time_step", hint="dt_scale = 4096 for NTSC and 4915 for PAL (60/50 * 4096, rounded down); the physics step is one tick per video frame.")
def _(ctx):
    for name, dt, vm in (("default", 4096, 0), ("pal", 4915, 1), ("alt", 4096, 0)):
        r = run_of(ctx, name)
        info = r.record("info")
        expect_eq(info["video_mode"], vm, f"video_mode ({name})")
        expect_eq(info["dt_scale"], dt, f"dt_scale ({name})", hint="dt_scale = video_mode ? 4915 : 4096, set before the game runs.")
        bad = [c["dt"] for c in calls_of(r) if c["dt"] != dt]
        expect_true(not bad, f"every ship_update call gets dt {dt} ({name})", str(bad[:3]), "Pass dt_scale to ship_update.")


@check("pal_runs_at_50hz", hint="video_mode = 1 must program the GPU's PAL bit (SetVideoMode, GP1(08h) bit 3): the emulated frame period becomes 1/50 s.")
def _(ctx):
    def median(xs):
        xs = sorted(xs)
        return xs[len(xs) // 2]
    n = median(run_of(ctx, "default").record("vbl_cycles")[60:])
    p = median(run_of(ctx, "pal").record("vbl_cycles")[60:])
    expect_true(abs(n - CPU_HZ / 60) / (CPU_HZ / 60) < 0.02, "NTSC frame period ~ 564,480 cycles (60 Hz)", f"{n}", "The default run must be NTSC.")
    expect_true(abs(p - CPU_HZ / 50) / (CPU_HZ / 50) < 0.02, "PAL frame period ~ 677,376 cycles (50 Hz)", f"{p}", "Call SetVideoMode(MODE_PAL) after ResetGraph when video_mode is 1.")


@check("pal_same_distance_per_second", hint="The ship must cover the same ground per SECOND in PAL and NTSC: per-tick quantities are scaled by dt_scale (4915 / 4096).")
def _(ctx):
    n, p = run_of(ctx, "default"), run_of(ctx, "pal")
    cn, cp = calls_of(n), calls_of(p)
    expect_true(len(cn) >= 300 and len(cp) >= 250, "ship_update called every tick of both runs", f"{len(cn)} and {len(cp)} calls", "")
    start = cn[0]["before"][:3]
    for t in (1.0, 2.0, 3.0, 4.0, 5.0):
        a, b = cn[round(t * 60) - 1]["after"], cp[round(t * 50) - 1]["after"]
        dist = math.dist(a[:3], b[:3])
        trav = math.dist(a[:3], start)
        tol = 0.025 * trav + 20                # Euler's error is O(dt): the two time steps differ by about 1-2 %
        expect_true(dist <= tol, f"t = {t:.0f} s: PAL position within {tol:.0f} units of NTSC", f"{dist:.0f} units apart after {trav:.0f} units of travel",
                    f"NTSC {show(a[:3])} (tick {round(t * 60)}), PAL {show(b[:3])} (tick {round(t * 50)}). Scale the thrust, the steering and the position step by dt_scale.")
        expect_true(abs(a[9] - b[9]) <= 0.06 * 245760, f"t = {t:.0f} s: the speeds agree", f"{a[9]} vs {b[9]}", "Speeds are per NTSC tick.")


@check("fixed_timestep", hint="The world advances ONE tick per vertical blank, whatever the frame rate: ship_ticks follows the elapsed blanks (ticks per frame = blanks since the last frame).")
def _(ctx):
    for name in ("default", "alt"):
        r = run_of(ctx, name)
        rows = rows_of(r)
        expect_true(len(rows) > 30, "game frames recorded", str(len(rows)), "")
        r0 = rows[0]
        worst_lo, worst_hi = 0, 0
        for row in rows:
            lag = (row["vbl"] - r0["vbl"]) - (row["sticks"] - r0["sticks"])
            worst_lo, worst_hi = min(worst_lo, lag), max(worst_hi, lag)
        expect_true(-2 <= worst_lo and worst_hi <= 5, f"ship_ticks keeps up with the vertical blanks ({name})",
                    f"blanks - ticks ranges {worst_lo}..{worst_hi}", "Run frame_ticks (VSync(-1) delta, 1..MAX_TICKS) ship_update calls per frame.")
        s = sum(row["ticks"] for row in rows[1:])
        expect_eq(rows[-1]["sticks"] - rows[0]["sticks"], s, f"ship_ticks counts the ticks run ({name})")
    alt = rows_of(run_of(ctx, "alt"))
    expect_true(alt[0]["subdiv"] == 0 and alt[-1]["subdiv"] == 1 and sum(1 for a, b in zip(alt, alt[1:]) if a["subdiv"] != b["subdiv"]) == 1,
                "R1 toggles subdiv_enabled exactly once (edge-triggered; it was held for 6 frames)", f"{alt[0]['subdiv']} .. {alt[-1]['subdiv']}", "The R1 toggle in game_update is given: keep it edge-triggered (input_pressed).")
    slow = [row["ticks"] for row in alt if row["subdiv"] == 1]
    expect_true(slow and sorted(slow)[len(slow) // 2] >= 2, "with subdivision on the frames take 2+ blanks, so 2+ ticks run per frame", f"median {sorted(slow)[len(slow) // 2] if slow else None}",
                "Physics must not depend on how long a frame takes.")
    fast = [row["ticks"] for row in rows_of(run_of(ctx, "default"))]
    expect_true(sorted(fast)[len(fast) // 2] == 1, "default: one tick per frame (60 frames per second)", f"median {sorted(fast)[len(fast) // 2]}", "subdiv_enabled must default to 0.")


@check("chase_camera_behind_and_above", hint="eye = pos - forward * back_dist + (0, -cam_height, 0): BEHIND the nose and ABOVE (-y) the ship; the target is ahead of it.")
def _(ctx):
    for name in ("default", "pal", "alt"):
        r = run_of(ctx, name)
        cfg = cfg_for(name)
        for row in rows_of(r):
            s = row["ship"]
            eye, tgt = row["eye"], row["tgt"]
            want_eye, want_tgt = M.chase(s, cfg)
            expect_true(eye == want_eye and tgt == want_tgt, f"frame {row['n']} ({name}): eye {show(want_eye)}, target {show(want_tgt)}", f"eye {show(eye)}, target {show(tgt)}",
                        "eye = pos - (f * back_dist >> 12) - (0, cam_height, 0) per axis; target = pos + (f * look_ahead >> 12).")
            yaw, pitch = s[10] / (1 << 24) * 2 * math.pi, s[11] / (1 << 24) * 2 * math.pi
            f = (math.sin(yaw) * math.cos(pitch), -math.sin(pitch), math.cos(yaw) * math.cos(pitch))
            rel = [eye[i] - s[i] for i in range(3)]
            dot = sum(rel[i] * f[i] for i in range(3))
            expect_true(dot < -0.9 * cfg["back_dist"], f"frame {row['n']} ({name}): the eye is behind the ship", f"dot(eye - pos, forward) = {dot:.0f}", "Subtract forward * back_dist.")
            expect_true(eye[1] < s[1] - 0.5 * cfg["cam_height"], f"frame {row['n']} ({name}): the eye is above the ship (-y)", f"eye.y {eye[1]} vs ship.y {s[1]}",
                        "+y is DOWN: above means a smaller y.")
            expect_true(sum((tgt[i] - s[i]) * f[i] for i in range(3)) > 0, f"frame {row['n']} ({name}): the target is ahead of the ship", "behind", "target = pos + forward * look_ahead.")


@check("start_line_default_frame_rate", hint="Measured, not a goal: with subdivision off the game runs at one tick per frame (60 / 50 frames per second) on the first three seconds of the route.")
def _(ctx):
    for name in ("default", "pal"):
        hz = hz_for(name)
        rows = [row for row in rows_of(run_of(ctx, name))[1:] if row["sticks"] < 3 * hz]
        slow = sum(1 for row in rows if row["ticks"] > 1)
        expect_true(slow <= 0.02 * len(rows), f"at most 2% of the frames of the first 3 s take more than one blank ({name})", f"{slow} of {len(rows)}",
                    "A frame over one blank means the game runs at 30 Hz. Is subdiv_enabled still 0 by default?")


# ---- the pictures -----------------------------------------------------------------------------------------------------------------------
def ember_pixels(img):
    pts = []
    for y in range(img.height):
        for x in range(img.width):
            r, g, b = img.pixel(x, y)
            if r >= 170 and 25 <= g <= 140 and b <= 70 and r - g >= 60:
                pts.append((x, y))
    return pts


def project_ship(row):
    """Screen position of the ship origin for a row: the camera's right / down / forward from the look-at definition, in floats."""
    eye, tgt, pos = row["eye"], row["tgt"], row["ship"][:3]
    f = [tgt[i] - eye[i] for i in range(3)]
    n = math.sqrt(sum(c * c for c in f))
    f = [c / n for c in f]
    up = (0.0, -1.0, 0.0)
    rt = [f[1] * up[2] - f[2] * up[1], f[2] * up[0] - f[0] * up[2], f[0] * up[1] - f[1] * up[0]]
    n = math.sqrt(sum(c * c for c in rt))
    rt = [c / n for c in rt]
    dn = [f[1] * rt[2] - f[2] * rt[1], f[2] * rt[0] - f[0] * rt[2], f[0] * rt[1] - f[1] * rt[0]]
    d = [pos[i] - eye[i] for i in range(3)]
    z = sum(d[i] * f[i] for i in range(3))
    return CX + PROJ_H * sum(d[i] * rt[i] for i in range(3)) / z, CY + PROJ_H * sum(d[i] * dn[i] for i in range(3)) / z, z


@check("ship_and_track_drawn", hint="The picture must show the track and the ship (its orange engine pods) where the chase camera puts it, tilted with the bank.")
def _(ctx):
    r = run_of(ctx, "default")
    rows = rows_of(r)
    tilt = {}
    expect_true(len(r.record("shots")) == 3, "three screenshots taken (ticks 60, 140, 296)", str(len(r.record("shots"))), "The ship's tick counter must advance in the game state.")
    for sh in r.record("shots"):
        img = r.screenshot(sh["name"])
        row = rows[sh["row"] - 1]
        track_frac = 1.0 - (img.fraction_matching(0, 0, img.width, img.height, BG, 12))
        expect_true(sh["name"] != "cruise" or track_frac > 0.35, f"{sh['name']}: the track fills much of the picture", f"{track_frac:.0%} non-background", "Is draw_track still called?")
        sx, sy, z = project_ship(row)
        em = ember_pixels(img)
        near = [p for p in em if abs(p[0] - sx) <= 80 and abs(p[1] - sy) <= 70]
        expect_true(len(near) >= 25, f"{sh['name']}: engine-pod pixels around the ship's screen position ({sx:.0f}, {sy:.0f})", f"{len(near)} pixels",
                    "draw_ship: ship_matrix, d = ship.pos - cam_eye as the translation, CompMatrixLV with the view ROTATION, then render_shp(&ship_shp, &ship_store).")
        expect_true(len(near) >= 0.8 * len(em), f"{sh['name']}: no ship-colored pixels elsewhere", f"{len(near)} of {len(em)} near the ship", "")
        mx = sum(p[0] for p in near) / len(near)
        lp = [p[1] for p in near if p[0] < mx]
        rp = [p[1] for p in near if p[0] >= mx]
        expect_true(lp and rp, f"{sh['name']}: two engine pods", f"{len(lp)} left, {len(rp)} right", "")
        tilt[sh["name"]] = sum(lp) / len(lp) - sum(rp) / len(rp)          # > 0: the left pod is lower on the screen
    expect_true(abs(tilt["cruise"]) <= 4, "straight flight: the pods are level", f"{tilt['cruise']:.1f} px", "roll must be ~0 when not steering.")
    expect_true(tilt["left"] >= 8, "turning left: the LEFT pod is lower (left wing down)", f"{tilt['left']:.1f} px", "Roll into the turn; positive roll = right wing down.")
    expect_true(tilt["right"] <= -8, "turning right: the RIGHT pod is lower", f"{tilt['right']:.1f} px", "Roll into the turn.")


# ---- direct calls ---------------------------------------------------------------------------------------------------------------------------
def rand_state(rng, cap=245760):
    return [rng.randint(-200000, 200000) for _ in range(3)] + [rng.randint(0, 4095) for _ in range(3)] + [rng.randint(-cap, cap) for _ in range(3)] + \
           [rng.randint(0, cap), rng.randint(0, M.TURN - 1), rng.randint(-1024, 1024) << 12, rng.randint(-300 << 12, 300 << 12), rng.randint(-150000, 150000)]


def cfg_words(cfg):
    return [cfg[k] for k in M.CFG_ORDER]


def make_unit_calls():
    cs = []

    def upd(tag, state, pad, dt, cfg=None):
        cfg = cfg or CFG
        cs.append(dict(tag=tag, kind="update", fn="ship_update", a0=SCRATCH, a1=pad, a2=dt, state=state, pad=pad, dt=dt, cfg=cfg,
                       writes=[dict(addr=SCRATCH, words=state), dict(sym="ship_cfg", words=cfg_words(cfg))], reads=[dict(name="ship", addr=SCRATCH, n=14)]))

    base = [1000, -500, 2000, 100, 200, 300, 0, 0, 0, 0, 1024 << 12, 0, 0, 0]
    cap = CFG["speed_cap"]
    for dt in (4096, 4915):
        upd(f"thrust dt{dt}", list(base), CROSS, dt)
        upd(f"cap: speed one below the cap + CROSS dt{dt}", base[:9] + [cap - 100] + base[10:], CROSS, dt)
        upd(f"cap: at the cap + CROSS dt{dt}", base[:9] + [cap] + base[10:], CROSS, dt)
        upd(f"brake clamp: 1500 + SQUARE dt{dt}", base[:9] + [1500] + base[10:], SQUARE, dt)
        upd(f"brake at 0 dt{dt}", list(base), SQUARE, dt)
        upd(f"CROSS and SQUARE together dt{dt}", base[:9] + [100000] + base[10:], CROSS | SQUARE, dt)
        upd(f"coast: no drag dt{dt}", base[:9] + [123456] + base[10:], 0, dt)
        upd(f"LEFT from rest dt{dt}", list(base), LEFT, dt)
        upd(f"RIGHT from rest dt{dt}", list(base), RIGHT, dt)
        upd(f"LEFT + RIGHT cancel dt{dt}", list(base), LEFT | RIGHT, dt)
        upd(f"damping decay of a big yaw_vel dt{dt}", base[:13] + [1000000], 0, dt)
        upd(f"damping decay, negative dt{dt}", base[:13] + [-1000000], 0, dt)
        upd(f"yaw_vel +15 is dead dt{dt}", base[:13] + [15], 0, dt)
        upd(f"yaw_vel -15 is dead dt{dt}", base[:13] + [-15], 0, dt)
        upd(f"yaw_vel +20 stays dt{dt}", base[:13] + [20], 0, dt)
        upd(f"yaw wraps past one turn dt{dt}", base[:10] + [M.TURN - 100, 0, 0, 500000], 0, dt)
        upd(f"yaw wraps below zero dt{dt}", base[:10] + [100, 0, 0, -500000], 0, dt)
        upd(f"roll follows a yaw rate dt{dt}", base[:13] + [200000], 0, dt)
        upd(f"roll returns to 0 dt{dt}", base[:12] + [-200 << 12, 0], 0, dt)
        upd(f"pitched nose-up flight dt{dt}", [0, 0, 0, 0, 0, 0, 0, 0, 0, 100000, 1024 << 12, 300 << 12, 0, 0], CROSS, dt)
        upd(f"pitched nose-down flight dt{dt}", [0, 0, 0, 0, 0, 0, 0, 0, 0, 100000, 3000 << 12, -300 << 12, 0, 0], 0, dt)
        upd(f"negative velocity carries the fraction dt{dt}", [-5, -5, -5, 4000, 10, 0, 0, 0, 0, 150000, 2048 << 12, 0, 0, 0], 0, dt)
        upd(f"other buttons are ignored dt{dt}", list(base), M.INPUT["UP"] | M.INPUT["START"] | M.INPUT["L1"] | M.INPUT["CIRCLE"], dt)
    for k in range(120):
        pad = 0
        for b in (CROSS, SQUARE, LEFT, RIGHT):
            if RNG.random() < 0.4:
                pad |= b
        pad |= RNG.choice([0, 0, M.INPUT["UP"], M.INPUT["R2"]])
        upd(f"random {k}", rand_state(RNG), pad, RNG.choice([4096, 4915, 3000, 2048, 6000]))
    for k in range(12):
        cfg = dict(CFG, thrust=RNG.randint(200, 9000), brake=RNG.randint(200, 12000), speed_cap=RNG.randint(10, 100) * 4096, yaw_accel=RNG.randint(1000, 20000),
                   yaw_damp=RNG.randint(100, 2000), roll_gain=RNG.randint(1, 30), roll_smooth=RNG.randint(100, 3000))
        st = rand_state(RNG, cfg["speed_cap"])
        st[9] = min(st[9], cfg["speed_cap"])
        upd(f"patched constants {k}", st, CROSS | RNG.choice([0, LEFT, RIGHT, SQUARE]), RNG.choice([4096, 4915]), cfg)

    for k in range(10):
        st = rand_state(RNG)
        if k == 0:
            st[10], st[11] = 1024 << 12, 0
        if k == 1:
            st[10], st[11] = 1024 << 12, 300 << 12
        cs.append(dict(tag=f"forward {k}", kind="forward", fn="ship_forward", a0=SCRATCH, a1=SCRATCH_OUT, state=st,
                       writes=[dict(addr=SCRATCH, words=st)], reads=[dict(name="f", addr=SCRATCH_OUT, n=3)]))
    mats = [(1024 << 12, 300 << 12, 0), (0, 0, -300 << 12), (2048 << 12, -200 << 12, 100 << 12), (3000 << 12, 400 << 12, 250 << 12), (0, 0, 0)]
    mats += [(RNG.randint(0, M.TURN - 1), RNG.randint(-1024, 1024) << 12, RNG.randint(-400, 400) << 12) for _ in range(5)]
    for k, (yaw, pitch, roll) in enumerate(mats):
        st = [0] * 10 + [yaw, pitch, roll, 0]
        cs.append(dict(tag=f"matrix {k}", kind="matrix", fn="ship_matrix", a0=SCRATCH, a1=SCRATCH_OUT, state=st,
                       writes=[dict(addr=SCRATCH, words=st), dict(addr=SCRATCH_OUT, words=[0x7BAD7BAD] * 8)], reads=[dict(name="m", addr=SCRATCH_OUT, n=8)]))
    for k in range(6):
        st = rand_state(RNG)
        st[11] = RNG.choice([0, 0, 83 << 12, -200 << 12])
        cfg = dict(CFG) if k < 3 else dict(CFG, back_dist=RNG.randint(300, 2000), cam_height=RNG.randint(50, 600), look_ahead=RNG.randint(300, 2000))
        st[0:3] = [RNG.randint(-30000, 30000) for _ in range(3)]
        cs.append(dict(tag=f"chase {k}", kind="chase", fn="chase_camera_update", a0=SCRATCH, state=st, cfg=cfg,
                       writes=[dict(addr=SCRATCH, words=st), dict(sym="ship_cfg", words=cfg_words(cfg))],
                       reads=[dict(name="eye", sym="cam_eye", n=3), dict(name="tgt", sym="cam_target", n=3), dict(name="view", sym="view_mtx", n=8)]))
    for k, (x, z) in enumerate([(0, 4096), (4096, 0), (0, -4096), (-4096, 0), (410, 4042), (-3000, -2500)]):
        cs.append(dict(tag=f"heading {k}", kind="heading", fn="heading_angle", a0=x, a1=z, limit=900000, writes=[], reads=[]))
    for k, y in enumerate([0, -522, 522, -4096, 4096]):
        cs.append(dict(tag=f"pitch {k}", kind="pitch", fn="pitch_angle", a0=y, limit=900000, writes=[], reads=[]))
    return cs


UNIT_CASES = make_unit_calls()
RUN_ARGS["unit"] = dict(probe=probe_for("unit", {"mode": "unit", "calls": [{k: c[k] for k in ("fn", "a0", "a1", "a2", "limit", "tag", "writes", "reads") if k in c} for c in UNIT_CASES]}))


def unit_records(ctx):
    r = ctx.run("unit", **RUN_ARGS["unit"])
    r.require_finished()
    exc = exception_of(r)
    if exc:
        raise CheckFailure(expected="no exception", actual=str(exc), hint="Which function? Run with -v. A GTE function needs InitGeom (the probe enables COP2).", message="CPU exception in a direct call")
    recs = r.record("calls")
    expect_eq(len(recs), len(UNIT_CASES), "direct calls made")
    return list(zip(UNIT_CASES, recs))


def kind_cases(ctx, kind):
    out = []
    for case, rec in unit_records(ctx):
        if case["kind"] == kind:
            expect_true(rec["returned"], f"{case['tag']}: the call returns", "no return within the instruction limit", "An endless loop?")
            expect_true(not rec["clobbered"], f"{case['tag']}: callee-saved registers preserved", str(rec["clobbered"]), "$s0-$s7, $sp, $fp, $gp must survive a call.")
            out.append((case, rec))
    return out


@check("unit_ship_update", hint="ship_update(&ship, pad, dt) on crafted states: caps, brake clamp, yaw damping and dead zone, wrap, banking, PAL step, constants read from ship_cfg.")
def _(ctx):
    for case, rec in kind_cases(ctx, "update"):
        want = M.update(case["state"], case["pad"], case["dt"], case["cfg"])
        got = rec["out"]["ship"]
        d = first_diff(got, want)
        expect_true(d is None, f"{case['tag']}: state after = {show(want)}", show(got),
                    f"first difference (field, got, expected): {d}. Input {show(case['state'])}, pad {case['pad']:#06x}, dt {case['dt']}.")


@check("unit_forward_and_matrix", hint="forward = (sin yaw cos pitch, -sin pitch, cos yaw cos pitch); the ship matrix is Ry * (Rx * Rz): yaw about the WORLD y axis, then pitch, then roll.")
def _(ctx):
    for case, rec in kind_cases(ctx, "forward"):
        want = M.forward(case["state"])
        got = rec["out"]["f"]
        expect_true(got == want, f"{case['tag']}: forward {show(want)}", show(got), f"yaw {case['state'][10] >> 12}, pitch {case['state'][11] >> 12}")
    for case, rec in kind_cases(ctx, "matrix"):
        want = M.ship_matrix(case["state"])
        w = rec["out"]["m"]
        half = []
        for x in w[:5]:
            half += [x & 0xFFFF, (x >> 16) & 0xFFFF]
        half = [h - 65536 if h & 0x8000 else h for h in half[:9]]
        got = [half[0:3], half[3:6], half[6:9]]
        err = max(abs(got[i][j] - want[i][j]) for i in range(3) for j in range(3))
        expect_true(err <= 1, f"{case['tag']}: matrix {want}", f"{got} (max error {err})", "M = MulMatrix0(Ry, Rx * Rz): the two RotMatrix calls are (pitch, 0, roll) and (0, yaw, 0). RotMatrix alone is Rx*Ry*Rz: pitch about the world x axis AFTER the yaw.")
        expect_true(w[5:8] == [0, 0, 0], f"{case['tag']}: the matrix's translation is 0", str(w[5:8]), "out->t = 0.")
    # the order matters: with yaw 90 degrees and pitch, Rx*Ry*Rz would give a different forward column
    c, rec = [x for x in kind_cases(ctx, "matrix") if x[0]["tag"] == "matrix 0"][0]
    w = rec["out"]["m"]
    half = []
    for x in w[:5]:
        half += [x & 0xFFFF, (x >> 16) & 0xFFFF]
    half = [h - 65536 if h & 0x8000 else h for h in half[:9]]
    fz = [half[2], half[5], half[8]]            # the third column is the nose
    expect_true(abs(fz[1] + M.isin(300)) <= 3 and abs(fz[0] - M.icos(300)) <= 3 and abs(fz[2]) <= 3, "yaw 90, pitch 300: the nose points at +x, raised by the pitch (about 26 degrees up)", f"{fz}", "Yaw first (about the world y axis), then pitch: Ry * Rx.")


@check("unit_chase_camera", hint="eye = pos - forward * back_dist + (0, -cam_height, 0); target = pos + forward * look_ahead; the look-at matrix then points from the eye to the target.")
def _(ctx):
    for case, rec in kind_cases(ctx, "chase"):
        eye, tgt = M.chase(case["state"], case["cfg"])
        expect_true(rec["out"]["eye"] == eye, f"{case['tag']}: eye {show(eye)}", show(rec["out"]["eye"]), "Is +y flipped? ABOVE the ship is a SMALLER y.")
        expect_true(rec["out"]["tgt"] == tgt, f"{case['tag']}: target {show(tgt)}", show(rec["out"]["tgt"]), "target = pos + (f * look_ahead >> 12).")
        v = rec["out"]["view"]
        half = []
        for x in v[:5]:
            half += [x & 0xFFFF, (x >> 16) & 0xFFFF]
        half = [h - 65536 if h & 0x8000 else h for h in half[:9]]
        d = [tgt[i] - eye[i] for i in range(3)]
        n = math.sqrt(sum(c * c for c in d))
        fwd = half[6:9]
        err = max(abs(fwd[i] - d[i] / n * 4096) for i in range(3))
        expect_true(err <= 24, f"{case['tag']}: the view's forward row points from the eye to the target", f"{fwd} vs {[round(c / n * 4096) for c in d]}", "Call camera_look_at(&cam_eye, &cam_target, &cam_up) with cam_up = (0, -4096, 0).")


@check("unit_angles", hint="heading_angle(x, z): among the angles with isin(a) x + icos(a) z > 0, the one that minimizes |isin(a) z - icos(a) x|; pitch_angle(y): minimizes |isin(p) + y|, -1024..1024.")
def _(ctx):
    for case, rec in kind_cases(ctx, "heading"):
        want = M.heading_angle(case["a0"], case["a1"])
        expect_eq(s32(rec["v0"]), want, f"{case['tag']}: heading_angle({case['a0']}, {case['a1']})", hint="0 along +z, 1024 along +x, the first minimum of the cross product on a tie.")
    for case, rec in kind_cases(ctx, "pitch"):
        want = M.pitch_angle(case["a0"])
        expect_eq(s32(rec["v0"]), want, f"{case['tag']}: pitch_angle({case['a0']})", hint="Nose up (negative y) is a positive angle.")
