#!/usr/bin/env python3
"""ship_ref.py -- the reference model of Chapter 37 (ship.h / README 5): exact integer arithmetic, bit for bit what ship.c does.

  python3 ship_ref.py                  print the trajectory of the scripted run (NTSC, then PAL) every 15 ticks
  from ship_ref import *               what verify/checks.py imports

Units: positions in world units + a 12-bit fraction, speeds 4.12 units per NTSC tick, angles 12.12 (1 turn = 1 << 24).
"""
import math

INPUT = dict(SELECT=0x1, START=0x8, UP=0x10, RIGHT=0x20, DOWN=0x40, LEFT=0x80, L2=0x100, R2=0x200, L1=0x400, R1=0x800,
             TRIANGLE=0x1000, CIRCLE=0x2000, CROSS=0x4000, SQUARE=0x8000)
DT_NTSC, DT_PAL = 4096, 4915
TURN = 1 << 24
MASK = TURN - 1
YAW_DEAD = 16

CFG0 = dict(thrust=3072, brake=6144, speed_cap=60 * 4096, yaw_accel=8192, yaw_damp=512, roll_gain=16, roll_smooth=1024,
            hover=120, back_dist=900, cam_height=250, look_ahead=1200, start_section=-1, reserved=0)
CFG_ORDER = list(CFG0)
SHIP_FIELDS = ["px", "py", "pz", "fx", "fy", "fz", "vx", "vy", "vz", "speed", "yaw", "pitch", "roll", "yaw_vel"]


def s32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


def isin(a):
    """PSn00bSDK's isin (4096 units per turn, 4.12 result), as ported in Chapter 24 / 28."""
    t = (a - 1024) & 0x7FF
    if t & 0x400:
        t -= 0x800
    p = (t * t) >> 6
    v = ((19900 - ((879 * p) >> 12)) * p) >> 16
    return v - 4096 if a & 0x800 else 4096 - v


def icos(a):
    return isin(a + 1024)


def fx_mul(a, b):
    return (a * b) >> 12


def heading_angle(x, z):
    best, be = 0, 0x7FFFFFFF
    for a in range(4096):
        s, c = isin(a), icos(a)
        if s * x + c * z <= 0:
            continue
        e = abs(s * z - c * x)
        if e < be:
            best, be = a, e
    return best


def pitch_angle(y):
    best, be = -1024, 1 << 30
    for p in range(-1024, 1025):
        e = abs(isin(p) + y)
        if e < be:
            best, be = p, e
    return best


def forward(s):
    a, p = s[10] >> 12, s[11] >> 12
    return [fx_mul(isin(a), icos(p)), -isin(p), fx_mul(icos(a), icos(p))]


def place(centre, up, fwd, hover):
    """The start state (ship_place): a list of 14 ints in SHIP_FIELDS order."""
    pos = [centre[i] + ((up[i] * hover) >> 12) for i in range(3)]
    return pos + [0, 0, 0, 0, 0, 0, 0, heading_angle(fwd[0], fwd[2]) << 12, pitch_angle(fwd[1]) << 12, 0, 0]


def update(s, pad, dt, cfg=CFG0):
    """One ship_update tick: s is a list of 14 ints, a new list is returned."""
    s = list(s)
    steer = (1 if pad & INPUT["RIGHT"] else 0) - (1 if pad & INPUT["LEFT"] else 0)
    yv = s[13]
    yv += fx_mul(steer * cfg["yaw_accel"], dt)
    yv -= fx_mul(yv, fx_mul(cfg["yaw_damp"], dt))
    if -YAW_DEAD < yv < YAW_DEAD:
        yv = 0
    s[13] = yv
    s[10] = (s[10] + fx_mul(yv, dt)) & MASK
    s[12] += fx_mul(yv * cfg["roll_gain"] - s[12], fx_mul(cfg["roll_smooth"], dt))
    sp = s[9]
    if pad & INPUT["CROSS"]:
        sp += fx_mul(cfg["thrust"], dt)
    if pad & INPUT["SQUARE"]:
        sp -= fx_mul(cfg["brake"], dt)
    sp = min(sp, cfg["speed_cap"])
    sp = max(sp, 0)
    s[9] = sp
    f = forward(s)
    for i in range(3):
        v = fx_mul(f[i], sp)
        s[6 + i] = v
        t = s[3 + i] + fx_mul(v, dt)
        s[i] += t >> 12
        s[3 + i] = t & 4095
    return s


def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) >> 12 for j in range(3)] for i in range(3)]


def rot_matrix(ax, ay, az):
    """SDK RotMatrix: Rx * Ry * Rz."""
    sx, cx, sy, cy, sz, cz = isin(ax), icos(ax), isin(ay), icos(ay), isin(az), icos(az)
    X = [[4096, 0, 0], [0, cx, -sx], [0, sx, cx]]
    Y = [[cy, 0, sy], [0, 4096, 0], [-sy, 0, cy]]
    Z = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 4096]]
    return matmul(matmul(X, Y), Z)


def ship_matrix(s):
    """M = Ry(yaw) * (Rx(pitch) * Rz(roll)) as the 3x3 4.12 matrix."""
    a = rot_matrix(s[11] >> 12, 0, s[12] >> 12)
    b = rot_matrix(0, s[10] >> 12, 0)
    return matmul(b, a)


def chase(s, cfg=CFG0):
    """(eye, target) of the chase camera."""
    f = forward(s)
    eye = [s[0] - ((f[0] * cfg["back_dist"]) >> 12), s[1] - ((f[1] * cfg["back_dist"]) >> 12) - cfg["cam_height"],
           s[2] - ((f[2] * cfg["back_dist"]) >> 12)]
    tgt = [s[i] + ((f[i] * cfg["look_ahead"]) >> 12) for i in range(3)]
    return eye, tgt


# The scripted run, in seconds (ticks = seconds * 60 NTSC, * 50 PAL): the reader's "accelerate, then turn left" plus a brake and a right turn.
SCRIPT = [("CROSS", 0.0, 2.0), ("LEFT", 2.0, 3.0), ("SQUARE", 3.7, 4.6), ("RIGHT", 4.6, 5.2)]
END = 5.6


def pad_at(t_seconds):
    m = 0
    for b, t0, t1 in SCRIPT:
        if t0 <= t_seconds < t1:
            m |= INPUT[b]
    return m


def simulate(start, hz, cfg=CFG0):
    dt = DT_NTSC if hz == 60 else DT_PAL
    s, out = list(start), []
    for k in range(int(END * hz)):
        s = update(s, pad_at(k / hz), dt, cfg)
        out.append(s)
    return out


if __name__ == "__main__":
    start = place((23883, -639, 496), (-1837, -3650, -285), (410, -522, 4042), 120)
    for hz in (60, 50):
        print(f"--- {hz} Hz (dt_scale {DT_NTSC if hz == 60 else DT_PAL})")
        print(f"{'tick':>5} {'t(s)':>5} {'x':>7} {'y':>7} {'z':>7} {'speed':>7} {'yaw':>6} {'roll':>6}")
        for k, s in enumerate(simulate(start, hz), 1):
            if k % 15 == 0:
                print(f"{k:5d} {k / hz:5.2f} {s[0]:7d} {s[1]:7d} {s[2]:7d} {s[9] / 4096:7.2f} {s[10] / 4096:6.0f} {s[12] / 4096:6.0f}")
