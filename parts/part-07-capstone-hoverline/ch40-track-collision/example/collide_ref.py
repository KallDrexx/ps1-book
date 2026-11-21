#!/usr/bin/env python3
"""collide_ref.py -- the reference model of Chapter 40 (collide.h / README 5): exact integer arithmetic, what collide.c does.

  python3 collide_ref.py            a worked example on the generated track 1 (the numbers of README 6)
  from collide_ref import *         what verify/checks.py imports

A track is the dict of tools/assets/formats.parse_trk. A ship is a list of 14 ints in ship_ref.SHIP_FIELDS order
(px py pz fx fy fz vx vy vz speed yaw pitch roll yaw_vel). Everything is a plain function of its arguments; the
state a real program keeps between ticks lives in the State object.
"""
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "ch37-ship-movement-and-physics", "example"))
from ship_ref import isin, icos, fx_mul, heading_angle, pitch_angle, forward, CFG0, MASK, TURN  # noqa: E402,F401

CLAMP = 32767
WALK = 4                      # section moves one search may make (COLL_WALK)
HALF = TURN >> 1
FLOOR, WALL, BOOST = 1, 2, 4  # face flags (E.10.3)
HIT_L, HIT_R, HIT_BOOST, HIT_RESPAWN, HIT_THUD = 1, 2, 4, 8, 16

CFG = dict(radius=90, wall_damp=2048, yaw_fix=2048, boost_impulse=5 * 4096, thud_gap=12, off_limit=1200, reserved0=0, reserved1=0)


def cdiv(a, b):
    """C integer division: truncates toward zero."""
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def clamp(v):
    return max(-CLAMP, min(CLAMP, v))


def wrap32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


def collide_heading(x, z):
    """== ship_ref.heading_angle (the same answer for every input), 129 + 64 evaluations instead of 4096."""
    if x == 0 and z == 0:
        return 0

    def ev(a):
        s, c = isin(a), icos(a)
        return None if s * x + c * z <= 0 else abs(s * z - c * x)
    bb, ba = None, 0
    for a in range(0, 4096, 64):
        e = ev(a)
        if e is not None and (bb is None or e < bb):
            bb, ba = e, a
    best, be = None, None
    for a in range(ba - 64, ba + 65):
        aa = a & 4095
        e = ev(aa)
        if e is not None and (be is None or e < be or (e == be and aa < best)):
            best, be = aa, e
    return best


# ---------------------------------------------------------------- edges
def edges(T, sec):
    """Returns (l0, r0, l1, r1, fallback): XZ points of the section's road edges (E.10.4), or the fallback edges."""
    S = T["sections"][sec]
    V = T["vertices"]
    pts = [(V[e][0], V[e][2]) for e in S["edges"]]
    l0, r0, l1, r1 = pts
    ok = True
    for a, b, ref in ((l0, l1, r0), (r0, r1, l0)):
        ex, ez = b[0] - a[0], b[1] - a[1]
        if ex == 0 and ez == 0:
            ok = False
        elif ex * (clamp(ref[1] - a[1])) - ez * (clamp(ref[0] - a[0])) == 0:
            ok = False
    if ok:
        return l0, r0, l1, r1, 0
    c = S["centre"]
    out = []
    for sgn in (-1, 1):
        a = [c[0] + ((sgn * S["right"][0] * S["half_width"]) >> 12), c[2] + ((sgn * S["right"][2] * S["half_width"]) >> 12)]
        b = [a[0] + ((S["forward"][0] * S["length"]) >> 12), a[1] + ((S["forward"][2] * S["length"]) >> 12)]
        out.append((tuple(a), tuple(b)))
    (l0, l1), (r0, r1) = out
    return l0, r0, l1, r1, 1


def edge_dist(seg, p):
    """seg = (ax, az, bx, bz, rx, rz); p = (x, z). Returns (dist, nx, nz): the signed distance of p from the line a->b, positive on
    the side of the reference point r, and the unit normal pointing to that side (4.12)."""
    ax, az, bx, bz, rx, rz = seg
    ex, ez = bx - ax, bz - az
    ln = math.isqrt(ex * ex + ez * ez)
    if ln == 0:
        return 0, 0, 0
    cref = ex * clamp(rz - az) - ez * clamp(rx - ax)
    s = -1 if cref < 0 else 1
    cr = ex * clamp(p[1] - az) - ez * clamp(p[0] - ax)
    return cdiv(s * cr, ln), cdiv(s * (-ez) * 4096, ln), cdiv(s * ex * 4096, ln)


def ring_dists(T, sec, pos):
    l0, r0, l1, r1, _ = edges(T, sec)
    ds = edge_dist((l0[0], l0[1], r0[0], r0[1], l1[0], l1[1]), (pos[0], pos[2]))[0]   # the start ring, positive toward the end ring
    de = edge_dist((l1[0], l1[1], r1[0], r1[1], l0[0], l0[1]), (pos[0], pos[2]))[0]   # the end ring, positive toward the start ring
    return ds, de


# ---------------------------------------------------------------- the section the ship is over
def nearest_brute(T, pos):
    best, bi = None, -1
    for i, s in enumerate(T["sections"]):
        d2 = sum((pos[k] - s["centre"][k]) ** 2 for k in range(3))
        if best is None or d2 < best:
            best, bi = d2, i
    return bi


def walk(T, cur, pos):
    """Returns (section, settled): up to WALK moves; settled False if it still wanted to move."""
    moves = 0
    while True:
        ds, de = ring_dists(T, cur, pos)
        if de <= 0:
            nxt = T["sections"][cur]["next"]
        elif ds < 0:
            nxt = T["sections"][cur]["prev"]
        else:
            return cur, True
        if moves == WALK:
            return cur, False
        cur = nxt
        moves += 1


def section_over(T, cur, pos):
    n = len(T["sections"])
    if n == 0:
        return -1
    if cur < 0 or cur >= n:
        cur = nearest_brute(T, pos)
    cur, ok = walk(T, cur, pos)
    if ok:
        return cur
    cur, ok = walk(T, nearest_brute(T, pos), pos)
    return cur


# ---------------------------------------------------------------- the ground and the face
def ground(T, sec, pos):
    S = T["sections"][sec]
    c, up = S["centre"], S["up"]
    if abs(up[1]) < 256:
        return c[1]
    num = up[0] * clamp(pos[0] - c[0]) + up[2] * clamp(pos[2] - c[2])
    return c[1] + cdiv(-num, up[1])


def floor_face(T, sec, pos):
    S = T["sections"][sec]
    V = T["vertices"]
    for i in range(S["first_face"], S["first_face"] + S["face_count"]):
        f = T["faces"][i]
        if not f["flags"] & FLOOR:
            continue
        v = f["v"]
        ring = [(V[v[k]][0], V[v[k]][2]) for k in (0, 1, 3, 2)]
        pos_c = neg_c = 0
        for k in range(4):
            a, b = ring[k], ring[(k + 1) % 4]
            cr = (b[0] - a[0]) * clamp(pos[2] - a[1]) - (b[1] - a[1]) * clamp(pos[0] - a[0])
            pos_c += cr > 0
            neg_c += cr < 0
        if not (pos_c and neg_c):
            return i
    return -1


# ---------------------------------------------------------------- the per-tick step
class State:
    def __init__(self):
        self.hits = self.thuds = self.boosts = self.respawns = 0
        self.on_boost = 0
        self.last_hit = -1000000
        self.dist_left = self.dist_right = 0
        self.face = -1
        self.section = -1
        self.events = []          # ("thud"|"boost") in order

    @classmethod
    def from_words(cls, w):
        st = cls()
        (st.hits, st.thuds, st.boosts, st.respawns, st.on_boost, st.last_hit, st.dist_left, st.dist_right, st.face) = w[:9]
        return st

    def words(self):
        return [self.hits, self.thuds, self.boosts, self.respawns, self.on_boost, self.last_hit, self.dist_left, self.dist_right, self.face]  # + 3 reserved words


def refresh_vel(s):
    f = forward(s)
    for i in range(3):
        s[6 + i] = fx_mul(f[i], s[9])


def respawn(T, s, sec, hover):
    S = T["sections"][sec]
    for i in range(3):
        s[i] = S["centre"][i] + ((S["up"][i] * hover) >> 12)
        s[3 + i] = 0
        s[6 + i] = 0
    s[9] = s[12] = s[13] = 0
    s[10] = heading_angle(S["forward"][0], S["forward"][2]) << 12
    s[11] = pitch_angle(S["forward"][1]) << 12


def collide_ship(T, st, s, section, ticks, cfg=CFG, ship_cfg=CFG0):
    """One tick after ship_update. s is modified in place; returns (section, flags)."""
    sec = section_over(T, section, (s[0], s[1], s[2]))
    st.section = sec
    if sec < 0:
        return sec, 0
    l0, r0, l1, r1, _ = edges(T, sec)
    p = (s[0], s[2])
    dl, nlx, nlz = edge_dist((l0[0], l0[1], l1[0], l1[1], r0[0], r0[1]), p)
    dr, nrx, nrz = edge_dist((r0[0], r0[1], r1[0], r1[1], l0[0], l0[1]), p)
    st.dist_left, st.dist_right = dl, dr
    flags = 0
    if dl < -cfg["off_limit"] or dr < -cfg["off_limit"]:
        respawn(T, s, sec, ship_cfg["hover"])
        st.respawns += 1
        st.on_boost = 0
        return sec, HIT_RESPAWN
    for d, nx, nz, e, bit in ((dl, nlx, nlz, (l1[0] - l0[0], l1[1] - l0[1]), HIT_L), (dr, nrx, nrz, (r1[0] - r0[0], r1[1] - r0[1]), HIT_R)):
        if d >= cfg["radius"]:
            continue
        flags |= bit
        st.hits += 1
        depth = cfg["radius"] - d
        s[0] += (nx * depth) >> 12
        s[2] += (nz * depth) >> 12
        f = forward(s)
        dot = fx_mul(f[0], nx) + fx_mul(f[2], nz)
        if dot < 0:
            impact = min(-dot, 4096)
            s[9] -= fx_mul(s[9], fx_mul(cfg["wall_damp"], impact))
            target = collide_heading(e[0], e[1]) << 12
            err = ((target - s[10] + HALF) & MASK) - HALF
            s[10] = (s[10] + ((err * cfg["yaw_fix"]) >> 12)) & MASK
            s[13] = 0
            refresh_vel(s)
        if ticks - st.last_hit >= cfg["thud_gap"]:
            st.thuds += 1
            st.events.append("thud")
            flags |= HIT_THUD
        st.last_hit = ticks
    s[1] = ground(T, sec, (s[0], s[1], s[2])) - ship_cfg["hover"]
    s[4] = 0
    face = floor_face(T, sec, (s[0], s[1], s[2]))
    st.face = face
    on = 1 if face >= 0 and T["faces"][face]["flags"] & BOOST else 0
    if on and not st.on_boost:
        s[9] = min(s[9] + cfg["boost_impulse"], ship_cfg["speed_cap"])
        refresh_vel(s)
        st.boosts += 1
        st.events.append("boost")
        flags |= HIT_BOOST
    st.on_boost = on
    return sec, flags


def readout(st):
    return "L%5d R%5d F%3d" % (st.dist_left, st.dist_right, st.face)


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(_HERE, "..", "..", "..", "..", "tools", "assets"))
    import tempfile
    import pathlib
    import mkassets
    import formats
    tmp = tempfile.TemporaryDirectory()
    files, _ = mkassets.build(pathlib.Path(tmp.name) / "a", seed=1)
    T = formats.parse_trk(files["TRACK.TRK"])
    S = T["sections"][40]
    print("section 40: centre", S["centre"], "edges", [T["vertices"][e] for e in S["edges"]])
    # README 6: the ship 560 units right of the centre, nose 228 units right of the road, 40 units a tick
    s = [round(S["centre"][k] + S["right"][k] * 560 / 4096) for k in range(3)] + [0] * 6 + [40 * 4096,
         ((heading_angle(S["forward"][0], S["forward"][2]) + 228) << 12) & MASK, pitch_angle(S["forward"][1]) << 12, 0, 0]
    refresh_vel(s)
    print("before: pos", s[0:3], "speed", s[9], "yaw", s[10] / 4096, "units")
    st = State()
    sec, flags = collide_ship(T, st, s, 40, 100)
    print("after:  pos", s[0:3], "speed", s[9], "yaw", s[10] / 4096, "units; section", sec, "flags", hex(flags), "dist_right", st.dist_right)
