#!/usr/bin/env python3
"""handling_ref.py -- the reference model of Chapter 41 (handling.h, race.h / README 5): exact integer arithmetic, what handling.c and race.c do.

  python3 handling_ref.py           a worked example (the numbers of README 6): drag and skid on a straight, the pitch target of section 0, a race clock
  from handling_ref import *        what verify/checks.py imports

A track is the dict of tools/assets/formats.parse_trk. A ship is a list of 14 ints in ship_ref.SHIP_FIELDS order (px py pz fx fy fz vx vy vz speed yaw pitch roll yaw_vel).
Everything is a plain function of its arguments; the state a program keeps between ticks is the Race object.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "ch40-track-collision", "example"))
import collide_ref as C  # noqa: E402
from collide_ref import isin, icos, fx_mul, cdiv, forward, MASK, CFG0, wrap32  # noqa: E402,F401
import ship_ref as SR  # noqa: E402

HCFG0 = dict(drag=64, grip=1024, pitch_smooth=1024, reserved=0)
RCFG0 = dict(laps=3, wrong_way=2, count_from=3, reserved=0)
PITCH_LIMIT = 256
MAX_LAPS, LINES = 8, 12
LAP, FINISH = 1, 2
BEEP, GO = 1, 2
TITLE, COUNTDOWN, RACE, RESULTS = 0, 1, 2, 3
INPUT = SR.INPUT


def scaled(k, dt):
    return min(fx_mul(k, dt), 4096)


def drag(speed, dt, h=HCFG0):
    return speed - fx_mul(speed, scaled(h["drag"], dt))


def skid(vel, target, dt, h=HCFG0):
    g = scaled(h["grip"], dt)
    return [vel[i] + fx_mul(target[i] - vel[i], g) for i in range(3)]


def pitch_target(up, yaw):
    """The specification (a scan of the 513 angles; the C code does a binary search and must agree)."""
    if up[1] > -256:
        return 0
    a = yaw >> 12
    hx, hz = isin(a), icos(a)
    num = up[0] * hx + up[2] * hz
    g = max(-32767, min(32767, cdiv(-num, up[1])))
    y = cdiv(g * 4096, C.math.isqrt(4096 * 4096 + g * g))
    best, be = -PITCH_LIMIT, None
    for p in range(-PITCH_LIMIT, PITCH_LIMIT + 1):
        e = abs(isin(p) + y)
        if be is None or e < be:
            best, be = p, e
    return best << 12


def auto_pitch(s, T, sec, dt, h=HCFG0):
    """Modifies s in place."""
    if not 0 <= sec < len(T["sections"]):
        return
    S = T["sections"][sec]
    s[11] += fx_mul(pitch_target(S["up"], s[10]) - s[11], scaled(h["pitch_smooth"], dt))


def update(s, pad, dt, cfg=CFG0, h=HCFG0):
    """Chapter 41's ship_update: Chapter 37's with the drag before the clamp and the skid before the move. A new list is returned."""
    s = list(s)
    steer = (1 if pad & INPUT["RIGHT"] else 0) - (1 if pad & INPUT["LEFT"] else 0)
    yv = s[13]
    yv += fx_mul(steer * cfg["yaw_accel"], dt)
    yv -= fx_mul(yv, fx_mul(cfg["yaw_damp"], dt))
    if -SR.YAW_DEAD < yv < SR.YAW_DEAD:
        yv = 0
    s[13] = yv
    s[10] = (s[10] + fx_mul(yv, dt)) & MASK
    s[12] += fx_mul(yv * cfg["roll_gain"] - s[12], fx_mul(cfg["roll_smooth"], dt))
    sp = s[9]
    if pad & INPUT["CROSS"]:
        sp += fx_mul(cfg["thrust"], dt)
    if pad & INPUT["SQUARE"]:
        sp -= fx_mul(cfg["brake"], dt)
    sp = drag(sp, dt, h)
    sp = max(0, min(sp, cfg["speed_cap"]))
    s[9] = sp
    f = forward(s)
    v = skid(s[6:9], [fx_mul(f[i], sp) for i in range(3)], dt, h)
    for i in range(3):
        s[6 + i] = v[i]
        t = s[3 + i] + fx_mul(v[i], dt)
        s[i] += t >> 12
        s[3 + i] = t & 4095
    return s


# ---------------------------------------------------------------- the race
def section_step(T, prev, cur):
    n = len(T["sections"])
    if not (0 <= prev < n and 0 <= cur < n):
        return 0
    if T["sections"][prev]["next"] == cur:
        return 1
    if T["sections"][prev]["prev"] == cur:
        return -1
    return 0


class Race:
    FIELDS = ["cd_ticks", "ticks", "lap", "progress", "furthest", "prev_section", "wrong_way", "finished", "total", "best_lap", "new_best"]

    def __init__(self):
        for f in self.FIELDS:
            setattr(self, f, 0)
        self.prev_section = -1
        self.lap_ticks = [0] * MAX_LAPS

    @classmethod
    def from_words(cls, w):
        r = cls()
        for i, f in enumerate(cls.FIELDS):
            setattr(r, f, w[i])
        r.lap_ticks = list(w[len(cls.FIELDS):len(cls.FIELDS) + MAX_LAPS])
        return r

    def words(self):
        return [getattr(self, f) for f in self.FIELDS] + list(self.lap_ticks)

    def copy(self):
        return Race.from_words(self.words())


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def tick(r, T, section, best, cfg=RCFG0):
    """One race_tick. r is modified in place; returns (flags, race_best)."""
    flags = 0
    laps = clamp(cfg["laps"], 1, MAX_LAPS)
    limit = max(cfg["wrong_way"], 1)
    r.ticks += 1
    step = 0
    if section >= 0:
        if r.prev_section >= 0:
            step = section_step(T, r.prev_section, section)
        r.prev_section = section
    r.progress += step
    r.furthest = max(r.furthest, r.progress)
    r.wrong_way = 1 if r.furthest - r.progress >= limit else 0
    if not r.finished and r.progress >= (r.lap + 1) * len(T["sections"]):
        r.lap_ticks[r.lap] = r.ticks - sum(r.lap_ticks[:r.lap])
        r.lap += 1
        flags |= LAP
        if r.lap >= laps:
            r.finished = 1
            r.total = r.ticks
            r.best_lap = min(r.lap_ticks[:laps])
            if best == 0 or r.best_lap < best:
                best = r.best_lap
                r.new_best = 1
            flags |= FINISH
    return flags, best


def countdown_tick(r, hz, cfg=RCFG0):
    cf = clamp(cfg["count_from"], 1, 9)
    beep = r.cd_ticks % hz == 0
    r.cd_ticks += 1
    if r.cd_ticks >= cf * hz:
        return GO
    return BEEP if beep else 0


def format_time(ticks, hz):
    if ticks < 0:
        return "-:--.--"
    cs = min(clamp(ticks, 0, 360000) * 100 // hz, 599999)
    return "%d:%02d.%02d" % (cs // 6000, (cs // 100) % 60, cs % 100)


def format_text(r, state, hz, best, cfg=RCFG0):
    """The 12 lines race_format_text writes (empty strings for the empty ones)."""
    out = [""] * LINES
    laps = clamp(cfg["laps"], 1, MAX_LAPS)
    cf = clamp(cfg["count_from"], 1, 9)
    bt = format_time(best if best > 0 else -1, hz)
    if state == TITLE:
        if best > 0:
            out[0] = "BEST LAP " + format_time(best, hz)
    elif state == COUNTDOWN:
        out[0] = "GET READY %d" % max(cf - r.cd_ticks // hz, 1)
    elif state == RACE:
        last = r.lap_ticks[r.lap - 1] if r.lap > 0 else -1
        out[0] = "LAP %d/%d" % (min(r.lap + 1, laps), laps)
        out[1] = "TIME " + format_time(r.ticks, hz)
        out[2] = "LAST %s  BEST %s" % (format_time(last, hz), bt)
        if r.wrong_way:
            out[3] = "WRONG WAY"
    elif state == RESULTS:
        out[0] = "RESULTS"
        for k in range(1, laps + 1):
            out[k] = "LAP %d  %s" % (k, format_time(r.lap_ticks[k - 1], hz))
        out[laps + 1] = "TOTAL " + format_time(r.total, hz)
        out[laps + 2] = "BEST " + bt
        if r.new_best:
            out[laps + 3] = "NEW BEST LAP"
    return out


if __name__ == "__main__":
    import hashlib
    sys.path.insert(0, os.path.join(_HERE, "..", "..", "..", "..", "tools", "assets"))
    import mkassets
    import formats
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        files, _ = mkassets.build(__import__("pathlib").Path(d), seed=1)
    T = formats.parse_trk(files["TRACK.TRK"])
    print("drag: speed 40.0 -> ", drag(40 * 4096, 4096), "(", drag(40 * 4096, 4096) / 4096, ")")
    print("terminal speed under thrust 0.75: ", end="")
    sp = 0
    for _ in range(2000):
        sp = max(0, min(drag(sp + 3072, 4096), 60 * 4096))
    print(sp, sp / 4096)
    S = T["sections"][0]
    print("section 0 up", S["up"], " forward", S["forward"], " pitch target at yaw 0:", pitch_target(S["up"], 0) >> 12, "units")
    print("time 3725 ticks:", format_time(3725, 60), "  PAL:", format_time(3725, 50))
