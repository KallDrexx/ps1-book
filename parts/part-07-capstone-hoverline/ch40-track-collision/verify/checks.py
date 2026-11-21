"""Chapter 40 checks: Track Collision (the section the ship is over, the road edges, wall response, ground height, boost pads, a track menu).
Build: CMake + PSn00bSDK; the CMake rule runs tools/assets/mkassets.py (TRACK.TRK, TRACK2.TRK ...). The emulator BOOTS THE .cue.

THE MODEL: example/collide_ref.py (and ship_ref.py of Chapter 37): exact integer arithmetic, the same as README 5 and collide.h. Runs:
  unit     the reader's functions called DIRECTLY from the probe (directcall.lua) with crafted arguments: collide_edge_dist, collide_edges, collide_section, collide_ground,
           collide_floor_face and the whole tick collide_ship. The track images are copied into free RAM (the generated track 1, track 2, and a copy of track 1 with three
           irregular sections: a zero-length edge, a corner on an edge line, an `up` vector lying flat). Every result is compared with the model.
  main     the whole game on track 1, driven by poses and pad presses (probe.lua): wall runs, a bend, boost pads, teleports, a respawn. Every game frame is recorded; each one
           is REPLAYED with the model (ship_update, then collide_ship, from the previous frame's state) and must agree, and geometric invariants are checked independently
           (never closer to an edge than the radius, yaw converging, one impulse per pad).
  menu     the title's track menu: twelve LEFT / RIGHT presses, snapshots of `track` after each, then the same runs on track 2.
  bad / missing   discs where TRACK2.TRK is corrupt / absent: the menu must keep track 1 and the game must still work."""

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

ROOT_DIR = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR / "tools" / "assets"))
sys.path.insert(0, str(HERE.parent / "example"))
import mkassets      # noqa: E402
import formats       # noqa: E402
import collide_ref as M  # noqa: E402

SR = M.__dict__["sys"].modules["ship_ref"]
SEED = int(os.environ.get("CH40_SEED") or random.randrange(1, 10 ** 6))
RNG = random.Random(SEED)
print(f"[ch40 unit-test seed {SEED}; CH40_SEED={SEED} repeats it]")

MAX_FRAMES = 1900
config(
    title="Track Collision: the section under the ship, edge distances, walls, ground, boost pads, two tracks",
    build="cmake", exe="game.exe", sym="", elf="game.elf", iso="hoverline.cue",
    break_at=None, max_frames=MAX_FRAMES, timeout=420,
)

_TMP = Path(tempfile.mkdtemp(prefix="ch40ref-"))
atexit.register(shutil.rmtree, _TMP, True)
FILES, MANIFESTS = mkassets.build(_TMP / "assets", seed=1)
IMG1, IMG2 = FILES["TRACK.TRK"], FILES["TRACK2.TRK"]
T1, T2 = formats.parse_trk(IMG1), formats.parse_trk(IMG2)


def patched_image():
    """Track 1 with three irregular sections (README 5.3): section 20's left edge has zero length, section 60's start-ring right vertex lies on the left edge line,
    section 70's `up` vector is flat (|up.y| < 256)."""
    d = bytearray(IMG1)
    off_v, off_f, off_s, off_vis = struct.unpack_from("<IIII", d, 0x28)

    def vx(i):
        return struct.unpack_from("<iii", d, off_v + 12 * i)

    def set_v(i, x, y, z):
        struct.pack_into("<iii", d, off_v + 12 * i, x, y, z)
    x, y, z = vx(6 * 20 + 1)
    set_v(6 * 21 + 1, x, y, z)                         # section 20: left_end := left_start
    x, _, z = vx(6 * 61 + 1)
    _, y, _ = vx(6 * 60 + 4)
    set_v(6 * 60 + 4, x, y, z)                         # section 60: right_start (xz) := left_end (xz): collinear with the left edge
    struct.pack_into("<hhh", d, off_s + 64 * 70 + 0x20, 3000, 100, -2500)   # section 70: up = (3000, 100, -2500) / 4096
    # sections 40 and 41 become 1405 and 605 units long: ring 41 moves 400 units forward (its six vertices, and the two centres that average it), so the bisector
    # between their centres is 200 units from the ring: the nearest centre is NOT the section the ship is over in a band 200 units wide (README 5.4)
    f = struct.unpack_from("<hhh", d, off_s + 64 * 40 + 0x10)
    mv = [(f[k] * 400) >> 12 for k in range(3)]
    for k in range(6):
        x, y, z = vx(6 * 41 + k)
        set_v(6 * 41 + k, x + mv[0], y + mv[1], z + mv[2])
    for sec, sgn in ((40, 1), (41, 1)):
        o = off_s + 64 * sec
        cx, cy, cz = struct.unpack_from("<iii", d, o)
        struct.pack_into("<iii", d, o, cx + (mv[0] >> 1), cy + (mv[1] >> 1), cz + (mv[2] >> 1))
    struct.pack_into("<H", d, off_s + 64 * 40 + 0x0E, struct.unpack_from("<H", d, off_s + 64 * 40 + 0x0E)[0] + 400)
    struct.pack_into("<H", d, off_s + 64 * 41 + 0x0E, struct.unpack_from("<H", d, off_s + 64 * 41 + 0x0E)[0] - 400)
    return bytes(d)


IMG3 = patched_image()
T3 = formats.parse_trk(IMG3)
TR = {1: T1, 2: T2, 3: T3}
IMGS = {1: IMG1, 2: IMG2, 3: IMG3}

# RAM for the direct calls (free in every build: the program ends below 0x80040000, the heap above it stays below 0x80150000, the stack is at 0x801F0000)
IMG_ADDR = {1: 0x80180000, 2: 0x80190000, 3: 0x801A0000}
TRK_ADDR = {1: 0x801B0000, 2: 0x801B0040, 3: 0x801B0080}
SHIP_A, SEG_A, P_A, N_A, EDG_A = 0x801B1000, 0x801B2000, 0x801B2040, 0x801B2060, 0x801B2100


def track_struct(n):
    d, a = IMGS[n], IMG_ADDR[n]
    off_v, off_f, off_s, off_vis = struct.unpack_from("<IIII", d, 0x28)
    t = TR[n]
    return [a + off_v, a + off_f, a + off_s, a + off_vis, len(t["sections"]), len(t["vertices"]), len(t["faces"]), struct.unpack_from("<H", d, 0x1E)[0],
            t["start_section"], t["flags"], t["texture_count"], t["total_length"]]


CFG_NAMES = ["radius", "wall_damp", "yaw_fix", "boost_impulse", "thud_gap", "off_limit"]
CAP = 60 * 4096
SHIPCFG = dict(M.CFG0)
PADS = SR.INPUT


# ---------------------------------------------------------------------------------------------------------------------------------------------
# geometry helpers (positions on a section)
def at(T, sec, u, lat):
    """A point on section `sec`: u in -0.5..0.5 along the centre line (a fraction of the length), lat across it (units, + right); y from the plane."""
    S = T["sections"][sec]
    L = S["length"]
    return [round(S["centre"][k] + (S["forward"][k] * u * L) / 4096 + (S["right"][k] * lat) / 4096) for k in range(3)]


def aligned_yaw(T, sec):
    f = T["sections"][sec]["forward"]
    return M.heading_angle(f[0], f[2]) << 12


def pitch_of(T, sec):
    return M.pitch_angle(T["sections"][sec]["forward"][1]) << 12


def show(v):
    return "(" + ", ".join(str(x) for x in v) + ")"


# ---------------------------------------------------------------------------------------------------------------------------------------------
# the unit calls
UNIT = []          # (case dict) in call order


def add_call(kind, tag, fn, a0=None, a1=None, a2=None, writes=(), reads=(), limit=None, **extra):
    c = dict(kind=kind, tag=tag, fn=fn, a0=a0, a1=a1, a2=a2, writes=list(writes), reads=list(reads), **extra)
    if limit:
        c["limit"] = limit
    UNIT.append(c)


def w_words(addr, words):
    return dict(addr=addr, words=[v % (1 << 32) for v in words])


def make_unit_calls():
    r = RNG
    # ---- collide_edge_dist
    segs = []
    for _ in range(90):
        ax, az = r.randint(-30000, 30000), r.randint(-30000, 30000)
        ln = r.choice([3, 40, 700, 1100, 3000, 8000])
        ex, ez = r.randint(-ln, ln), r.randint(-ln, ln)
        rx, rz = ax + r.randint(-1500, 1500), az + r.randint(-1500, 1500)
        px, pz = ax + r.choice([r.randint(-1500, 1500), r.randint(-60000, 60000)]), az + r.choice([r.randint(-1500, 1500), r.randint(-60000, 60000)])
        segs.append((ax, az, ax + ex, az + ez, rx, rz, px, pz))
    segs += [(0, 0, 0, 0, 100, 0, 5, 5), (0, 0, 1000, 0, 500, 0, 300, 400), (0, 0, 1000, 0, 500, 0, 300, -400), (0, 0, 1000, 0, 500, 700, 300, 400),
             (0, 0, 0, 1000, 1000, 0, 400, 300), (100, 100, 100, 100, 0, 0, 0, 0), (50, 50, 1050, 1050, 1050, 50, 600, 100), (5, 5, 1005, 505, 505, 255, 700, 250)]
    for i, (ax, az, bx, bz, rx, rz, px, pz) in enumerate(segs):
        add_call("dist", f"edge_dist #{i}", "collide_edge_dist", SEG_A, P_A, N_A, writes=[w_words(SEG_A, [ax, az, bx, bz, rx, rz]), w_words(P_A, [px, pz])],
                 reads=[dict(name="n", addr=N_A, n=2), dict(name="seg", addr=SEG_A, n=6)], seg=(ax, az, bx, bz, rx, rz), p=(px, pz))
    # ---- collide_edges
    for n in (1, 2, 3):
        for sec in range(len(TR[n]["sections"])):
            add_call("edges", f"edges track{n} sec {sec}", "collide_edges", TRK_ADDR[n], sec, EDG_A,
                     writes=[w_words(TRK_ADDR[n], track_struct(n)), w_words(EDG_A, [0x7EADBEEF] * 9)], reads=[dict(name="e", addr=EDG_A, n=9)], n=n, sec=sec)
    for sec in (-1, 112, 99999):
        add_call("edges", f"edges bad section {sec}", "collide_edges", TRK_ADDR[1], sec % (1 << 32), EDG_A,
                 writes=[w_words(TRK_ADDR[1], track_struct(1)), w_words(EDG_A, [0x7EADBEEF] * 9)], reads=[dict(name="e", addr=EDG_A, n=9)], n=1, sec=sec)
    # ---- collide_section
    pts = []
    for n, count in ((1, 90), (2, 90), (3, 40)):
        T = TR[n]
        N = len(T["sections"])
        for _ in range(count):
            sec = r.randrange(N)
            if n == 3 and r.random() < 0.7:
                sec = r.choice([19, 20, 21, 22, 58, 59, 60, 61, 62, 69, 70, 71])
            pos = at(T, sec, r.uniform(-0.5, 0.5), r.choice([r.uniform(-590, 590), r.uniform(-900, 900), r.uniform(-3000, 3000)]))
            pos[1] += r.randint(-300, 300)
            cur = r.choice([sec, sec, (sec + r.choice([-1, 1])) % N, (sec + r.choice([-3, 3, 4, 5, 6])) % N, r.randrange(N)])
            pts.append((n, cur, pos))
    # the trap (README 5.4): in the patched copy the nearest centre is NOT the section the ship is over, in a band 200 units wide
    traps = []
    rr = random.Random(11)
    T = TR[3]
    for _ in range(4000):
        if len(traps) >= 30:
            break
        sec = rr.choice([40, 41])
        pos = at(T, sec, rr.uniform(-0.5, 0.5), rr.uniform(-590, 590))
        if M.nearest_brute(T, pos) != M.section_over(T, sec, pos):
            traps.append((3, rr.choice([sec, M.nearest_brute(T, pos), 39, 42]), pos))
    assert len(traps) >= 25, "verifier self-check: the stretched sections must produce traps"
    pts += traps
    pts += [(1, -1, at(T1, 40, 0, 0)), (1, 5000, at(T1, 40, 0.3, 100)), (1, -1, at(T1, 100, 0.2, -500)), (2, 77777, at(T2, 3, 0.2, 500)), (1, 0, at(T1, 111, 0.45, 20)),
            (1, 111, at(T1, 0, -0.45, 20)), (1, 50, [20000, 0, -20000]), (2, 10, [-30000, 500, 30000]), (1, 7, at(T1, 7, 0, 0))]
    for i, (n, cur, pos) in enumerate(pts):
        add_call("section", f"section #{i} track{n} cur {cur}", "collide_section", TRK_ADDR[n], cur % (1 << 32), P_A,
                 writes=[w_words(TRK_ADDR[n], track_struct(n)), w_words(P_A, pos)], limit=400000, n=n, cur=cur, pos=pos, trap=(n, cur, pos) in traps)
    # ---- collide_ground
    for n, count in ((1, 50), (2, 40), (3, 14)):
        T = TR[n]
        N = len(T["sections"])
        for i in range(count):
            sec = 70 if (n == 3 and i < 8) else r.randrange(N)
            pos = at(T, sec, r.uniform(-0.6, 0.6), r.choice([r.uniform(-700, 700), r.uniform(-4000, 4000), r.uniform(-90000, 90000)]))
            add_call("ground", f"ground track{n} sec {sec}", "collide_ground", TRK_ADDR[n], sec, P_A, writes=[w_words(TRK_ADDR[n], track_struct(n)), w_words(P_A, pos)],
                     n=n, sec=sec, pos=pos)
    # ---- collide_floor_face
    for n, count in ((1, 70), (2, 50)):
        T = TR[n]
        N = len(T["sections"])
        for i in range(count):
            sec = r.randrange(N)
            if i % 7 == 0 and T["sections"][sec]["face_count"]:
                f = T["faces"][T["sections"][sec]["first_face"] + r.randrange(1, 4)]
                v = T["vertices"][f["v"][r.randrange(4)]]
                pos = [v[0], v[1], v[2]]                      # exactly on a corner: inside by the rule
            else:
                pos = at(T, sec, r.uniform(-0.5, 0.5), r.choice([r.uniform(-600, 600), r.uniform(-900, 900)]))
            add_call("face", f"floor_face track{n} sec {sec}", "collide_floor_face", TRK_ADDR[n], sec, P_A, writes=[w_words(TRK_ADDR[n], track_struct(n)), w_words(P_A, pos)],
                     n=n, sec=sec, pos=pos)
    for n in (1, 2):                                         # the middle of every boost pad's centre lane and its neighbours
        T = TR[n]
        for sec in MANIFESTS["TRACK.TRK" if n == 1 else "TRACK2.TRK"]["boost_sections"]:
            for lat in (0, -300, 300, -500):
                pos = at(T, sec, 0.1, lat)
                add_call("face", f"floor_face pad track{n} sec {sec} lat {lat}", "collide_floor_face", TRK_ADDR[n], sec, P_A,
                         writes=[w_words(TRK_ADDR[n], track_struct(n)), w_words(P_A, pos)], n=n, sec=sec, pos=pos)
    # ---- collide_ship
    def ship_case(kind, tag, n, sec, u, lat, yaw_off=0, speed=None, cfg=None, wrong=None, ticks=None, last_hit=None, on_boost=None, hover=120, cap=CAP, aligned=True,
                  state=None, pos=None):
        T = TR[n]
        cfgd = dict(M.CFG)
        cfgd.update(cfg or {})
        if pos is None:
            pos = at(T, sec, u, lat)
        yaw = ((aligned_yaw(T, sec) if aligned else r.randrange(4096) << 12) + (yaw_off << 12) + r.randrange(4096)) & M.MASK
        sp = speed if speed is not None else r.randrange(0, CAP + 1)
        pitch = pitch_of(T, sec)
        f = SR.forward([0] * 10 + [yaw, pitch])
        vel = [SR.fx_mul(f[i], sp) for i in range(3)]
        ship = [pos[0], pos[1], pos[2], r.randrange(4096), r.randrange(1, 4096), r.randrange(4096)] + vel + [sp, yaw, pitch, r.randint(-30000, 30000), r.randint(-40000, 40000)]
        tk = ticks if ticks is not None else r.randrange(50, 100000)
        lh = last_hit if last_hit is not None else r.choice([-1000000, tk - 1, tk - 2, tk - 11, tk - 12, tk - 13, tk - 40, tk])
        cs = [r.randrange(0, 50), r.randrange(0, 20), r.randrange(0, 9), r.randrange(0, 3), r.randrange(2) if on_boost is None else on_boost, lh, 777, -777, 5, 0, 0, 0]
        section = wrong if wrong is not None else (sec if r.random() < 0.8 else (sec + r.choice([-1, 1, 2, -2])) % len(T["sections"]))
        add_call(kind, tag, "collide_ship", TRK_ADDR[n], SHIP_A, None, limit=900000,
                 writes=[w_words(TRK_ADDR[n], track_struct(n)), w_words(SHIP_A, ship), dict(sym="ship_section", words=[section]), dict(sym="ship_ticks", words=[tk]),
                         dict(sym="collide_state", words=cs), dict(sym="collide_cfg", words=[cfgd[k] for k in CFG_NAMES] + [0, 0]),
                         dict(sym="ship_cfg", off=28, words=[hover]), dict(sym="ship_cfg", off=8, words=[cap])],
                 reads=[dict(name="ship", addr=SHIP_A, n=14), dict(name="section", sym="ship_section", n=1), dict(name="cs", sym="collide_state", n=12),
                        dict(name="ev", sym="audio_stats", off=12, n=2)],
                 n=n, ship=ship, section=section, ticks=tk, cs=cs, cfg=cfgd, hover=hover, cap=cap)

    for i in range(70):                                          # nothing near an edge
        n = r.choice([1, 2])
        ship_case("ship_idle", f"idle #{i}", n, r.randrange(len(TR[n]["sections"])), r.uniform(-0.45, 0.45), r.uniform(-330, 330), yaw_off=r.randint(-300, 300),
                  hover=r.choice([120, 120, 40, 300]))
    for side in (-1, 1):                                         # into the wall: the edge's distance below the radius, nose toward it
        for i in range(60):
            n = r.choice([1, 2, 3])
            sec = r.randrange(len(TR[n]["sections"]))
            lat = side * r.choice([r.uniform(480, 600), r.uniform(560, 640), r.uniform(590, 800)])
            ship_case("ship_wall", f"wall {'right' if side > 0 else 'left'} #{i}", n, sec, r.uniform(-0.45, 0.45), lat, yaw_off=side * r.randint(30, 700),
                      speed=r.choice([r.randrange(1, CAP + 1), CAP, 4096, 0]), cfg=r.choice([None, None, dict(radius=60, wall_damp=3500, yaw_fix=1000), dict(radius=130, wall_damp=1024, yaw_fix=4096)]))
    for i in range(30):                                          # at the wall but moving away from it, or along it
        n = r.choice([1, 2])
        sec = r.randrange(len(TR[n]["sections"]))
        side = r.choice([-1, 1])
        ship_case("ship_wall_away", f"wall, nose away #{i}", n, sec, r.uniform(-0.45, 0.45), side * r.uniform(515, 600), yaw_off=-side * r.randint(10, 600), speed=r.randrange(1, CAP + 1))
    for i in range(24):                                          # the thud clock
        n = r.choice([1, 2])
        sec = r.randrange(len(TR[n]["sections"]))
        tk = r.randrange(60, 5000)
        gap = r.choice([12, 12, 5, 30])
        ship_case("ship_thud", f"thud clock #{i} (gap {gap})", n, sec, r.uniform(-0.45, 0.45), r.choice([-1, 1]) * r.uniform(540, 600), yaw_off=r.randint(-300, 300), ticks=tk,
                  last_hit=r.choice([tk - gap, tk - gap + 1, tk - gap - 1, tk - 1, -1000000, tk]), cfg=dict(thud_gap=gap), speed=r.randrange(1000, CAP))
    for n in (1, 2):                                             # boost pads: enter (on_boost 0), stay (1), the side lane, near the cap, other impulse
        T = TR[n]
        pads = MANIFESTS["TRACK.TRK" if n == 1 else "TRACK2.TRK"]["boost_sections"]
        for i in range(14):
            sec = r.choice(pads)
            ship_case("ship_boost", f"boost pad #{i}", n, sec, r.uniform(-0.45, 0.45), r.uniform(-150, 150), yaw_off=r.randint(-100, 100), on_boost=r.choice([0, 0, 1]),
                      speed=r.choice([r.randrange(0, CAP), CAP - 5000, CAP, 3000]), cfg=r.choice([None, dict(boost_impulse=9000), dict(boost_impulse=70000)]), cap=r.choice([CAP, CAP, 150000]))
        for i in range(6):
            sec = r.choice(pads)
            ship_case("ship_boost", f"side lane of a pad section #{i}", n, sec, r.uniform(-0.45, 0.45), r.choice([-1, 1]) * r.uniform(250, 480), on_boost=0, speed=r.randrange(0, CAP))
    for i in range(28):                                          # far outside: respawn
        n = r.choice([1, 2])
        sec = r.randrange(len(TR[n]["sections"]))
        side = r.choice([-1, 1])
        ship_case("ship_respawn", f"respawn #{i}", n, sec, r.uniform(-0.4, 0.4), side * r.choice([r.uniform(1810, 2500), r.uniform(2500, 9000)]), speed=r.randrange(0, CAP),
                  hover=r.choice([120, 200]), cfg=r.choice([None, dict(off_limit=300)]), wrong=r.choice([None, None, sec]))
    for i in range(6):                                           # just outside the respawn limit: pushed back, not respawned
        n = r.choice([1, 2])
        sec = r.randrange(len(TR[n]["sections"]))
        side = r.choice([-1, 1])
        ship_case("ship_wall", f"deep but not respawned #{i}", n, sec, 0.0, side * r.uniform(1700, 1790), yaw_off=side * r.randint(0, 400), speed=r.randrange(1, CAP))
    for i in range(24):                                          # the section pointer is wrong: the neighbour, a few away, nonsense, the first call
        n = r.choice([1, 2])
        N = len(TR[n]["sections"])
        sec = r.randrange(N)
        ship_case("ship_section", f"section pointer off #{i}", n, sec, r.uniform(-0.45, 0.45), r.uniform(-500, 500), wrong=r.choice([(sec + 1) % N, (sec - 1) % N, (sec + 4) % N, (sec + 9) % N, -1, N + 5, 12345]),
                  speed=r.randrange(0, CAP))
    for i in range(10):                                          # the irregular sections of the patched copy
        sec = r.choice([20, 21, 60, 61, 70, 40, 41])
        ship_case("ship_irregular", f"irregular section {sec} #{i}", 3, sec, r.uniform(-0.45, 0.45), r.uniform(-640, 640), yaw_off=r.randint(-300, 300), speed=r.randrange(1, CAP))
    # direct call of the pieces the reader's code might call from collide_ship in other ways: collide_respawn
    for i in range(6):
        n = r.choice([1, 2])
        sec = r.randrange(len(TR[n]["sections"]))
        ship = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
        add_call("respawn", f"respawn direct #{i}", "collide_respawn", TRK_ADDR[n], SHIP_A, sec, limit=900000,
                 writes=[w_words(TRK_ADDR[n], track_struct(n)), w_words(SHIP_A, ship), dict(sym="ship_cfg", off=28, words=[120])],
                 reads=[dict(name="ship", addr=SHIP_A, n=14)], n=n, sec=sec)


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
UNIT_KEYS = ("fn", "a0", "a1", "a2", "limit", "tag", "writes", "reads")
UNIT_PARAMS = {"mode": "unit", "images": UNIT_IMAGES, "calls": [{k: c[k] for k in UNIT_KEYS if k in c and c[k] is not None} for c in UNIT]}


def exception_of(r):
    try:
        return r.record("exception")
    except Exception:
        return None


def unit_records(ctx):
    r = ctx.run("unit", probe=probe_gen(ctx, "unit", UNIT_PARAMS), max_frames=700)
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
            expect_true(rec["returned"], f"{case['tag']}: the call returns", "no return within the instruction limit", "An endless loop (a walk with no limit)?")
            expect_true(not rec["clobbered"], f"{case['tag']}: callee-saved registers preserved", str(rec["clobbered"]), "$s0-$s7, $sp, $fp, $gp must survive a call.")
            out.append((case, rec))
    return out


def s32(v):
    return M.wrap32(v)


# ---- the model's answers ----------------------------------------------------------------------------------------------------------------------
def model_ship(case):
    n = case["n"]
    T = TR[n]
    st = M.State.from_words(case["cs"])
    s = list(case["ship"])
    ship_cfg = dict(SHIPCFG, hover=case["hover"], speed_cap=case["cap"])
    sec, flags = M.collide_ship(T, st, s, case["section"], case["ticks"], case["cfg"], ship_cfg)
    return s, sec, st, flags


TOL = dict(pos=1, vel=16, speed=16, yaw=256)


def ship_diff(got, want):
    """First field where the ship words differ beyond the tolerance, or None. Fields: see ship_ref.SHIP_FIELDS."""
    for i, name in enumerate(SR.SHIP_FIELDS):
        a, b = got[i], want[i]
        if name == "yaw":
            d = (a - b + (1 << 23)) % (1 << 24) - (1 << 23)
            if abs(d) > TOL["yaw"]:
                return name, a, b
            continue
        tol = TOL["pos"] if name in ("px", "py", "pz") else TOL["vel"] if name in ("vx", "vy", "vz", "speed") else 0
        if abs(a - b) > tol:
            return name, a, b
    return None


def check_ship_cases(ctx, kinds, what):
    n_checked = 0
    for case, rec in kind_cases(ctx, *kinds):
        got_ship = rec["out"]["ship"]
        got_sec = rec["out"]["section"][0]
        got_cs = rec["out"]["cs"]
        s, sec, st, flags = model_ship(case)
        want_cs = st.words() + [0, 0, 0]
        d = ship_diff(got_ship, s)
        ctxt = f"{case['tag']}: input ship {show(case['ship'])}, ship_section {case['section']}, ship_ticks {case['ticks']}, collide_state {show(case['cs'][:9])}"
        expect_true(d is None, f"{what}: ship after = {show(s)}", show(got_ship), f"first difference (field, got, expected): {d}. {ctxt}")
        expect_eq(s32(got_sec), sec, f"{what}: ship_section after ({case['tag']})", hint=ctxt)
        for k, name in enumerate(["hits", "thuds", "boosts", "respawns", "on_boost", "last_hit", "dist_left", "dist_right", "face"]):
            tol = 1 if name in ("dist_left", "dist_right") else 0
            expect_true(abs(got_cs[k] - want_cs[k]) <= tol, f"{what}: collide_state.{name} after ({case['tag']}) = {want_cs[k]}", str(got_cs[k]), ctxt)
        expect_eq(s32(rec["v0"]), flags, f"{what}: the flags collide_ship returns ({case['tag']})", fmt="hex", hint=ctxt)
        n_checked += 1
    return n_checked


# ---- checks: static ----------------------------------------------------------------------------------------------------------------------
@static_check("both_tracks_on_the_disc", hint="iso.xml lists \\DATA\\TRACK2.TRK (assets/TRACK2.TRK, made by mkassets.py), and CMakeLists.txt lists it among the assets.")
def _(ctx):
    xml = next(iter(sorted(ctx.build.build_dir.glob("cd_image_*.xml"))), None)
    expect_true(xml is not None, "the configured disc description", "not found", "Use psn00bsdk_add_cd_image.")
    text = xml.read_text()
    expect_true(re.search(r'name="TRACK2\.TRK"', text, re.I) is not None, 'iso.xml has <file name="TRACK2.TRK" ...>', "missing", "Add it next to TRACK.TRK.")
    expect_true((ctx.build.build_dir / "assets" / "TRACK2.TRK").exists(), "build/assets/TRACK2.TRK exists", "missing", "Add TRACK2.TRK to ASSET_FILES in CMakeLists.txt.")


# ---- checks: the pure functions -------------------------------------------------------------------------------------------------------------
@check("edge_distance", hint="collide_edge_dist: dist = (s * cross(p - a)) / len with s the sign of cross(r - a); n = (s * -ez * 4096 / len, s * ex * 4096 / len); len = isqrt(ex^2 + ez^2); differences clamped.")
def _(ctx):
    for case, rec in kind_cases(ctx, "dist"):
        want = M.edge_dist(case["seg"], case["p"])
        got = (s32(rec["v0"]), rec["out"]["n"][0], rec["out"]["n"][1])
        expect_eq(list(got), list(want), f"{case['tag']}: (dist, nx, nz) for seg {show(case['seg'])}, p {show(case['p'])}",
                  hint="C division truncates toward zero; the sign s comes from the reference point, a zero cross counts as +1; len 0 gives 0 and a zero normal.")
        expect_eq(rec["out"]["seg"], list(case["seg"]), f"{case['tag']}: the input segment is not modified")


@check("edges_recipe_and_fallback", hint="collide_edges: the XZ of vertices[edges[0..3]]; a zero-length edge or a reference point on its line switches BOTH edges to centre -/+ right * half_width, forward * length.")
def _(ctx):
    fallbacks = {1: 0, 2: 0, 3: 0}
    for case, rec in kind_cases(ctx, "edges"):
        n, sec = case["n"], case["sec"]
        e = rec["out"]["e"]
        if sec < 0 or sec >= len(TR[n]["sections"]):
            expect_eq(s32(rec["v0"]), -1, f"{case['tag']}: returns -1")
            expect_eq(e, [s32(0x7EADBEEF)] * 9, f"{case['tag']}: *e is left untouched")
            continue
        l0, r0, l1, r1, fb = M.edges(TR[n], sec)
        want = [l0[0], l0[1], r0[0], r0[1], l1[0], l1[1], r1[0], r1[1], fb]
        expect_eq(e, want, f"{case['tag']}: p[0..3][x, z] and fallback", hint="Order: left_start, right_start, left_end, right_end, each (x, z), then the fallback flag.")
        expect_eq(s32(rec["v0"]), fb, f"{case['tag']}: return value (1 = fallback was used)")
        fallbacks[n] += fb
    expect_eq((fallbacks[1], fallbacks[2]), (0, 0), "sections of the generated tracks that need the fallback")
    expect_true(fallbacks[3] >= 2, "sections of the patched copy that use the fallback (at least 20 and 60)", str(fallbacks[3]), "(verifier self-check)")


@check("section_under_the_ship", hint="collide_section: de <= 0 -> next, ds < 0 -> prev (by the links), at most 4 moves, then the brute-force search and a second walk. Not the nearest centre.")
def _(ctx):
    traps = 0
    for case, rec in kind_cases(ctx, "section"):
        n = case["n"]
        want = M.section_over(TR[n], case["cur"], case["pos"])
        got = s32(rec["v0"])
        expect_eq(got, want, f"{case['tag']}: the section over {show(case['pos'])}", hint=(
            "The nearest centre is %d here (Chapter 38's answer)." % M.nearest_brute(TR[n], case["pos"]) if case["trap"] else
            "Test the start and end ring lines of the section (and of its neighbours), not distances to centres."))
        traps += case["trap"]
    expect_true(traps >= 25, "the test includes positions where the nearest centre is another section", str(traps), "(verifier self-check)")


@check("ground_height", hint="collide_ground: the plane through the centre with normal up: centre.y + (-(up.x * dx + up.z * dz)) / up.y, differences clamped, |up.y| < 256 gives centre.y.")
def _(ctx):
    for case, rec in kind_cases(ctx, "ground"):
        want = M.ground(TR[case["n"]], case["sec"], case["pos"])
        expect_eq(s32(rec["v0"]), want, f"{case['tag']}: surface y under {show(case['pos'])}", hint="up.y is negative (+y is down): divide by it, do not use its absolute value. C division truncates.")


@check("floor_face_lookup", hint="collide_floor_face: the first FLOOR face of the section (table order) whose quad (corners v0 v1 v3 v2) contains the point; a point on a side is inside.")
def _(ctx):
    inside = 0
    for case, rec in kind_cases(ctx, "face"):
        want = M.floor_face(TR[case["n"]], case["sec"], case["pos"])
        got = s32(rec["v0"])
        inside += want >= 0
        expect_eq(got, want, f"{case['tag']}: the floor face at {show(case['pos'])}", hint="Z order: the perimeter is v0, v1, v3, v2. Inside = the four cross products are not of both signs.")
    expect_true(inside >= 60, "the test includes enough points on the road", str(inside), "(verifier self-check)")


# ---- checks: the tick ----------------------------------------------------------------------------------------------------------------------
@check("tick_without_contact", hint="No edge within the radius: only pos.y (ground - hover) and pos_frac[1] = 0 change; ship_section, face and on_boost follow; nothing else is touched.")
def _(ctx):
    check_ship_cases(ctx, ("ship_idle", "ship_section", "ship_irregular"), "free flight")


@check("wall_push_back_damp_and_yaw", hint="Push along the unit normal by radius - d; if the nose points into the wall: speed -= speed * wall_damp * impact, yaw toward the edge's heading by yaw_fix, yaw_vel = 0, vel refreshed.")
def _(ctx):
    n = check_ship_cases(ctx, ("ship_wall", "ship_wall_away"), "wall")
    expect_true(n >= 90, "wall cases", str(n), "")


@check("thud_event_clock", hint="EV_THUD only when ship_ticks - last_hit >= thud_gap; last_hit = ship_ticks on EVERY hit (sliding along a wall is one thud).")
def _(ctx):
    check_ship_cases(ctx, ("ship_thud",), "thud clock")


@check("boost_pad_impulse", hint="Entering a face with TRK_BOOST (on_boost 0 -> 1) adds boost_impulse, capped at ship_cfg.speed_cap, refreshes vel, counts one EV_BOOST; staying on it does nothing.")
def _(ctx):
    check_ship_cases(ctx, ("ship_boost",), "boost")


@check("off_track_respawn", hint="More than off_limit OUTSIDE an edge: collide_respawn at the section (ship_place's pose), respawns++, on_boost = 0, return COLL_RESPAWN, nothing else.")
def _(ctx):
    check_ship_cases(ctx, ("ship_respawn",), "respawn")
    for case, rec in kind_cases(ctx, "respawn"):
        S = TR[case["n"]]["sections"][case["sec"]]
        want = [S["centre"][i] + ((S["up"][i] * 120) >> 12) for i in range(3)] + [0, 0, 0, 0, 0, 0, 0, M.heading_angle(S["forward"][0], S["forward"][2]) << 12,
                                                                                    M.pitch_angle(S["forward"][1]) << 12, 0, 0]
        expect_eq(rec["out"]["ship"], want, f"{case['tag']}: collide_respawn(section {case['sec']}) writes ship_place's pose", hint="pos_frac, vel, speed, roll, yaw_vel = 0.")


@check("events_reach_the_audio_counters", hint="audio_event(EV_THUD) / audio_event(EV_BOOST): audio_stats.events_thud / events_boost count every event the tick raises (the counters grow over the whole run of direct calls).")
def _(ctx):
    thud = boost = 0
    last = None
    for case, rec in kind_cases(ctx, "ship_idle", "ship_wall", "ship_wall_away", "ship_thud", "ship_boost", "ship_respawn", "ship_section", "ship_irregular"):
        s, sec, st, flags = model_ship(case)
        thud += st.events.count("thud")
        boost += st.events.count("boost")
        ev = rec["out"]["ev"]
        expect_eq(ev, [boost, thud], f"events_boost, events_thud after {case['tag']} (running totals over the direct calls)", hint="Raise EV_BOOST / EV_THUD with audio_event(), once per event.")


@check("calls_are_cheap", hint="A tick of collide_ship must not search the whole track or scan 4096 angles on every call: heading_angle is for rare events, collide_heading is given.")
def _(ctx):
    worst = {}
    for case, rec in kind_cases(ctx, "ship_idle", "ship_wall", "ship_boost", "ship_thud", "ship_wall_away", "ship_section"):
        worst[case["kind"]] = max(worst.get(case["kind"], 0), rec["instrs"])
    for kind, lim in (("ship_idle", 6000), ("ship_wall", 45000), ("ship_boost", 9000), ("ship_thud", 45000), ("ship_wall_away", 6000), ("ship_section", 30000)):
        expect_true(worst.get(kind, 0) <= lim, f"instructions of the slowest {kind} call <= {lim}", str(worst.get(kind)), "A hit scans 4096 angles if it calls heading_angle: use collide_heading. The solution stays below 70% of every limit.")


# ---- the driven runs -------------------------------------------------------------------------------------------------------------------------
def pose(T, sec, u, lat, speed, yaw_off=0, section=None, yaw_vel=0):
    p = at(T, sec, u, lat)
    return [p[0], p[1], p[2], speed, (aligned_yaw(T, sec) + (yaw_off << 12)) & M.MASK, pitch_of(T, sec), 0, yaw_vel, sec if section is None else section]


def segments_for(T, sec_wall_l, sec_wall_r, sec_bend, pad_secs, sec_tele, sec_far):
    """The scripted segments (README 5.10). Returns a list of dicts: name, pose, pads [(buttons, frames)]."""
    pad0 = pad_secs[0]
    return [
        dict(name="left", pose=pose(T, sec_wall_l, 0.0, 0, 20 * 4096), pads=[("CROSS,LEFT", 40), ("CROSS", 80)]),
        dict(name="right", pose=pose(T, sec_wall_r, 0.0, 0, 20 * 4096), pads=[("CROSS,RIGHT", 40), ("CROSS", 80)]),
        dict(name="bend", pose=pose(T, sec_bend, 0.0, 0, 40 * 4096), pads=[("CROSS", 200)]),
        dict(name="pad", pose=pose(T, (pad0 - 2) % len(T["sections"]), 0.0, 0, 30 * 4096), pads=[("", 120)]),
        dict(name="side_lane", pose=pose(T, (pad0 - 2) % len(T["sections"]), 0.0, -400, 30 * 4096), pads=[("", 120)]),
        dict(name="teleport", pose=pose(T, sec_tele, 0.1, 100, 0, section=(sec_tele - 8) % len(T["sections"])), pads=[("", 3)]),
        dict(name="teleport2", pose=pose(T, (sec_tele + 20) % len(T["sections"]), -0.2, -100, 0, section=(sec_tele + 19) % len(T["sections"])), pads=[("", 3)]),
        dict(name="respawn", pose=pose(T, sec_far, 0.0, 2500, 30 * 4096), pads=[("CROSS", 4)]),
        dict(name="rest", pose=pose(T, sec_far, 0.0, 640, 0), pads=[("", 24)]),
        dict(name="rest_left", pose=pose(T, sec_far, 0.0, -650, 0), pads=[("", 12)]),
    ]


SEGS = {
    1: segments_for(T1, 10, 18, 36, MANIFESTS["TRACK.TRK"]["boost_sections"], 60, 40),
    2: segments_for(T2, 8, 14, 30, MANIFESTS["TRACK2.TRK"]["boost_sections"], 55, 25),
}


def probe_segments(segs):
    return [dict(pose=s["pose"], pads=[list(p) for p in s["pads"]]) for s in segs]


MENU_PRESSES = [2, 1, 2, 2, 1, 1, 2, 1, 2, 1, 2, 2]
MENU_START = 8 + 6 * len(MENU_PRESSES) + 8


def params_main():
    return {"segments": probe_segments(SEGS[1]), "start_frame": 6}


def params_menu(segs):
    title = [dict(frame=8 + 6 * i, button="RIGHT" if t == 2 else "LEFT", hold=3) for i, t in enumerate(MENU_PRESSES)]
    snaps = [12 + 6 * i for i in range(len(MENU_PRESSES))]
    return {"title": title, "snaps": snaps, "segments": probe_segments(segs), "start_frame": MENU_START}


_def = _TMP / "params_main.lua"
_def.write_text("PARAMS = " + lua_val(params_main()) + "\n")
os.environ["CH40_PARAMS"] = str(_def)


def alt_disc(ctx, name, mode):
    """A copy of the disc where TRACK2.TRK is corrupt ('bad': the magic) or not on it ('missing')."""
    bdir = ctx.build.build_dir
    if (bdir / f"{name}.cue").exists():
        return
    xml = next(iter(sorted(bdir.glob("cd_image_*.xml"))), None)
    if xml is None:
        raise CheckFailure(expected="CMake's configured iso xml", actual="not found", hint="Use psn00bsdk_add_cd_image.")
    text = xml.read_text()
    if mode == "bad":
        (bdir / name).mkdir(exist_ok=True)
        bad = bytearray(IMG2)
        bad[0:4] = b"XRK1"
        (bdir / name / "TRACK2.TRK").write_bytes(bytes(bad))
        text, k = re.subn(r'(<file\s+name="TRACK2\.TRK"[^>]*?source=")[^"]*(")', lambda m: m.group(1) + str(bdir / name / "TRACK2.TRK") + m.group(2), text, flags=re.I)
    else:
        text, k = re.subn(r'<file\s+name="TRACK2\.TRK"[^>]*/>', "", text, flags=re.I)
    expect_eq(k, 1, 'iso.xml has one <file name="TRACK2.TRK" source=.../> entry', hint="Appendix E.2.")
    (bdir / f"{name}.xml").write_text(text)
    p = subprocess.run(["mkpsxiso", "-y", "-q", "-o", f"{name}.bin", "-c", f"{name}.cue", f"{name}.xml"], cwd=bdir, capture_output=True, text=True, timeout=60, env=tool_env())
    expect_eq(p.returncode, 0, "mkpsxiso builds the alternative disc", hint=(p.stdout + p.stderr)[-400:])


class Run:
    pass


_runs = {}


def run_of(ctx, name):
    if name in _runs:
        return _runs[name]
    if name == "main":
        r = ctx.result
    elif name == "menu":
        r = ctx.run(name, probe=probe_gen(ctx, name, params_menu(SEGS[2])), max_frames=2600)
    else:
        alt_disc(ctx, name, name)
        press = [dict(frame=8, button="RIGHT", hold=3), dict(frame=14, button="LEFT", hold=3), dict(frame=20, button="RIGHT", hold=3)]
        p = {"title": press, "snaps": [12, 18, 24], "segments": probe_segments(SEGS[1][:1]), "start_frame": 30}
        r = ctx.run(name, probe=probe_gen(ctx, name, p), iso=f"{name}.cue", max_frames=1500)
    r.require_finished()
    exc = exception_of(r)
    if exc:
        raise CheckFailure(expected="no CPU exception", actual=f"CPU exception {exc['code']} at pc 0x{exc['epc']:08X}, address 0x{exc['badvaddr']:08X}",
                           hint="A NULL track, a section index out of range, a store through a bad pointer.")
    o = Run()
    o.r, o.name = r, name
    o.info = r.record("info") or {}
    o.rows = r.record("rows") or []
    o.snaps = r.record("snaps") or []
    expect_true(o.info.get("load_status") == 0, "the program loads everything and enters the game", f"info {o.info}", "Booting + loading takes about 400 emulated frames.")
    o.track = 2 if name == "menu" else 1
    o.segs = SEGS[o.track] if name in ("main", "menu") else SEGS[1][:1]
    _runs[name] = o
    return o


def by_seg(o):
    out = {}
    for row in o.rows:
        out.setdefault(row["seg"], []).append(row)
    return out


def pad_mask(names):
    m = 0
    for b in re.findall(r"[A-Z0-9]+", names or ""):
        m |= PADS[b]
    return m


def replay(o, T, tolerance=True):
    """Replays every game frame with the model. Returns (checked, skipped, first_problem or None, problems)."""
    prev_ship = prev_section = prev_cs = None
    entry = o.info["entry"]
    prev_cs = entry["cs"]
    prev_section = entry["section"]
    checked = skipped = 0
    problems = []
    segs = o.segs
    seen_seg = 0
    for row in o.rows:
        seg = segs[row["seg"] - 1]
        if row["seg"] != seen_seg:
            seen_seg = row["seg"]
            p = seg["pose"]
            prev_ship = [p[0], p[1], p[2], 0, 0, 0, 0, 0, 0, p[3], p[4], p[5], p[6], p[7]]
            if p[8] is not None:
                prev_section = p[8]
        if row["ticks"] != 1 or len(row["pads"]) != 1:
            skipped += 1
        else:
            s = SR.update(prev_ship, row["pads"][0], 4096)
            st = M.State.from_words(prev_cs)
            sec, flags = M.collide_ship(T, st, s, prev_section, row["sticks"] - 1)
            d = ship_diff(row["ship"], s)
            checked += 1
            bad = None
            if d:
                bad = f"ship {d[0]}: got {d[1]}, expected {d[2]}"
            elif row["section"] != sec:
                bad = f"ship_section: got {row['section']}, expected {sec}"
            else:
                for k, name in enumerate(["hits", "thuds", "boosts", "respawns", "on_boost", "last_hit", "dist_left", "dist_right", "face"]):
                    if abs(row["cs"][k] - st.words()[k]) > (1 if name.startswith("dist") else 0):
                        bad = f"collide_state.{name}: got {row['cs'][k]}, expected {st.words()[k]}"
                        break
            if bad:
                problems.append(f"segment {seg['name']} frame {row['k']}: {bad}")
        prev_ship, prev_section, prev_cs = row["ship"], row["section"], row["cs"]
    return checked, skipped, problems


def edge_dists(T, sec, pos):
    l0, r0, l1, r1, _ = M.edges(T, sec)
    dl = M.edge_dist((l0[0], l0[1], l1[0], l1[1], r0[0], r0[1]), (pos[0], pos[2]))[0]
    dr = M.edge_dist((r0[0], r0[1], r1[0], r1[1], l0[0], l0[1]), (pos[0], pos[2]))[0]
    return dl, dr


def edge_heading(T, sec, side):
    l0, r0, l1, r1, _ = M.edges(T, sec)
    a, b = (l0, l1) if side == "left" else (r0, r1)
    return M.heading_angle(b[0] - a[0], b[1] - a[1]) << 12


def yaw_err(yaw, target):
    return (target - yaw + (1 << 23)) % (1 << 24) - (1 << 23)


def track_checks(name, o, T, boost_secs):
    segs = by_seg(o)
    names = [s["name"] for s in o.segs]
    for i, nm in enumerate(names):
        expect_true(len(segs.get(i + 1, [])) >= 3, f"{name}: the '{nm}' segment ran", f"{len(segs.get(i + 1, []))} frames", "The probe records one row per game frame.")


# ---- checks: the whole game --------------------------------------------------------------------------------------------------------------------
@check("frames_replay_with_the_model", hint="Every game frame (one tick) starts from the previous frame's state: ship_update, then your collide_ship; the model must agree on the ship, ship_section and collide_state.")
def _(ctx):
    for name in ("main", "menu"):
        o = run_of(ctx, name)
        T = T1 if name == "main" else T2
        checked, skipped, problems = replay(o, T)
        expect_true(checked >= 0.9 * len(o.rows), f"{name}: frames that ran exactly one tick (the others cannot be replayed)", f"{checked} of {len(o.rows)}",
                    "The frame took more than one vertical blank: is collide_ship slow? (frame_ticks > 1)")
        expect_true(not problems, f"{name}: every frame equals the model ({checked} replayed)", f"{len(problems)} differ; first: {problems[:1]}",
                    "Look at the first one: it names the segment, the frame and the field. Rows come from the real program; the model replays one tick from the previous state.")


@check("ship_stays_inside_the_road", hint="After every frame the ship's centre is at least `radius` (minus 3 for rounding) inside both edges of ship_section, in the XZ plane. Checked against collide_ref's edges, not against your code.")
def _(ctx):
    for name in ("main", "menu"):
        o = run_of(ctx, name)
        T = T1 if name == "main" else T2
        worst = 10 ** 9
        where = None
        for row in o.rows:
            sec = row["section"]
            expect_true(0 <= sec < len(T["sections"]), f"{name}: ship_section is a section", str(sec), "ship_section is set by collide_ship every tick.")
            dl, dr = edge_dists(T, sec, row["ship"])
            m = min(dl, dr)
            if m < worst:
                worst, where = m, (o.segs[row["seg"] - 1]["name"], row["k"], dl, dr)
        expect_true(worst >= 90 - 3, f"{name}: the smallest distance to an edge over every frame is at least 87", f"{worst} (segment {where[0]}, frame {where[1]}: left {where[2]}, right {where[3]})",
                    "Push back along the normal by radius - d, on the edge that was crossed, using the section the ship is over.")
        sw = by_seg(o)
        for i, seg in enumerate(o.segs):
            if seg["name"] in ("left", "right", "bend"):
                rows = sw.get(i + 1, [])
                expect_true(rows and rows[-1]["cs"][0] >= 10, f"{name}: the '{seg['name']}' run hits the wall (collide_state.hits)", str(rows[-1]["cs"][0] if rows else None),
                            "Is collide_ship called every tick from game_update?")


@check("hover_follows_the_ground", hint="After every tick pos.y = collide_ground(...) - hover (hover = ship_cfg.hover): the ship follows the slope and the bank of the road.")
def _(ctx):
    o = run_of(ctx, "main")
    bad = []
    for row in o.rows:
        if row["cs"][3] and row["ship"][9] == 0:
            continue
        sec = row["section"]
        want = M.ground(T1, sec, row["ship"]) - 120
        if abs(row["ship"][1] - want) > 2:
            bad.append((row["seg"], row["k"], row["ship"][1], want))
    expect_true(not bad, "pos.y == ground - 120 (+-2) at the end of every frame", f"{len(bad)} frames differ; first (segment, frame, y, expected): {bad[:1]}",
                "Hover is vertical: y of the plane under (x, z) minus hover; +y is down.")


@check("yaw_converges_after_impact", hint="Each hit moves the heading yaw_fix of the way toward the edge's own heading; after a few hits against the wall the ship points along it.")
def _(ctx):
    o = run_of(ctx, "main")
    sw = by_seg(o)
    for i, seg in enumerate(o.segs):
        if seg["name"] not in ("left", "right"):
            continue
        rows = sw[i + 1]
        side = seg["name"]
        hit_rows = [k for k, rw in enumerate(rows) if k and rw["cs"][0] > rows[k - 1]["cs"][0]]
        expect_true(hit_rows, f"'{side}' run: at least one hit", "none", "")
        first = hit_rows[0]
        before = abs(yaw_err(rows[first - 1]["ship"][10], edge_heading(T1, rows[first - 1]["section"], side)))
        tail = rows[-20:]
        after = max(abs(yaw_err(rw["ship"][10], edge_heading(T1, rw["section"], side))) for rw in tail)
        expect_true(before > 40 << 12, f"'{side}' run: the ship was pointing into the wall when it first hit (heading error before: {before >> 12} units)", str(before >> 12),
                    "(verifier self-check: the run steers hard into the wall)")
        expect_true(after < before / 3 and after < 60 << 12, f"'{side}' run: after the impact the heading error shrinks (before {before >> 12} units, last 20 frames at most {after >> 12})",
                    f"{after >> 12} units", "yaw += fx_mul(err, yaw_fix) with err wrapped to (-half turn, half turn]; yaw_vel = 0.")


@check("boost_pad_run", hint="Driving over a pad's centre lane adds boost_impulse once (two adjoining pad sections are ONE pad); the side lane gives nothing.")
def _(ctx):
    for name in ("main", "menu"):
        o = run_of(ctx, name)
        sw = by_seg(o)
        names = [s["name"] for s in o.segs]
        rows = sw[names.index("pad") + 1]
        boosts = rows[-1]["cs"][2]
        expect_eq(boosts, 1, f"{name}: boost entries over the pad run (a two-section pad is one pad)")
        k = next(i for i, r in enumerate(rows) if i and r["cs"][2] > rows[i - 1]["cs"][2])
        jump = rows[k]["ship"][9] - rows[k - 1]["ship"][9]
        expect_true(abs(jump - 5 * 4096) <= 64, f"{name}: the speed jumps by boost_impulse (5.0 units/tick = 20480) at the entry", f"{jump}", "speed = min(speed + boost_impulse, speed_cap).")
        expect_eq(rows[-1]["boost"] - rows[0]["boost"], rows[-1]["cs"][2] - rows[0]["cs"][2], f"{name}: audio_stats.events_boost grows with the entries")
        side = sw[names.index("side_lane") + 1]
        expect_eq(side[-1]["cs"][2], boosts, f"{name}: the side lane run adds no boost (collide_state.boosts stays {boosts})")


@check("events_come_from_collision", hint="One EV_THUD per impact (not per frame spent on the wall) and one EV_BOOST per pad: audio_stats.events_thud / events_boost match collide_state.")
def _(ctx):
    o = run_of(ctx, "main")
    last = o.rows[-1]
    expect_eq(last["thud"], last["cs"][1], "audio_stats.events_thud equals collide_state.thuds at the end of the run")
    expect_eq(last["boost"], last["cs"][2], "audio_stats.events_boost equals collide_state.boosts at the end of the run")
    expect_true(last["cs"][1] >= 4, "the run raised several thuds", str(last["cs"][1]), "")
    expect_true(last["cs"][0] > 4 * last["cs"][1], "far more hits than thuds (sliding along a wall is one thud)", f"hits {last['cs'][0]}, thuds {last['cs'][1]}", "last_hit is updated on every hit.")


@check("section_follows_teleports", hint="collide_section walks the ring lines from last tick's section, and falls back to the brute-force search when the walk gives up.")
def _(ctx):
    for name in ("main", "menu"):
        o = run_of(ctx, name)
        T = T1 if name == "main" else T2
        sw = by_seg(o)
        names = [s["name"] for s in o.segs]
        for nm in ("teleport", "teleport2"):
            seg = o.segs[names.index(nm)]
            row = sw[names.index(nm) + 1][0]
            p = seg["pose"]
            want = M.section_over(T, p[8], [p[0], p[1], p[2]])
            expect_eq(row["section"], want, f"{name}: {nm}: ship_section on the first frame after the teleport (it was {p[8]})")


@check("respawn_run", hint="Far outside an edge the ship is put back at the section's centre: speed 0, heading along the road.")
def _(ctx):
    for name in ("main", "menu"):
        o = run_of(ctx, name)
        sw = by_seg(o)
        names = [s["name"] for s in o.segs]
        rows = sw[names.index("respawn") + 1]
        expect_eq(rows[0]["cs"][3], 1, f"{name}: respawns after the first frame of the far-outside pose")
        expect_true(rows[0]["ship"][9] == 0 or rows[0]["ship"][9] < 4 * 4096, f"{name}: speed after the respawn (CROSS may add one tick of thrust)", str(rows[0]["ship"][9]), "")


@check("readout_text", hint="collide_format: \"L%5d R%5d F%3d\" from collide_state.dist_left, dist_right, face; drawn under the SEC / PRIMS line.")
def _(ctx):
    o = run_of(ctx, "main")
    for row in o.rows:
        want = "L%5d R%5d F%3d" % (row["cs"][6], row["cs"][7], row["cs"][8])
        strip = lambda t: re.sub(r"\s+", "", t)       # PSn00bSDK's printf pads a negative %5d AFTER the sign ("-  38"): only the characters count
        expect_eq(strip(row["text"]), strip(want), f"collide_text of segment {o.segs[row['seg'] - 1]['name']} frame {row['k']}, ignoring spaces")
        expect_true(row["text"].startswith("L") and len(row["text"]) == len(want), "the text has the layout of \"L%5d R%5d F%3d\" (length and first character)", row["text"], "")


# ---- the track menu ----------------------------------------------------------------------------------------------------------------------------
@check("menu_loads_both_tracks", hint="track_switch(n): load TRACK.TRK / TRACK2.TRK, parse into a separate Track, replace `track`, free the old image, set track_selected and ship_section = -1.")
def _(ctx):
    o = run_of(ctx, "menu")
    expect_eq(len(o.snaps), len(MENU_PRESSES), "snapshots on the title (one after each press)")
    ptrs = set()
    for i, (sn, want) in enumerate(zip(o.snaps, MENU_PRESSES)):
        T = TR[want]
        expect_eq(sn["sel"], want, f"track_selected after press {i + 1} ({'RIGHT' if want == 2 else 'LEFT'})")
        expect_eq(sn["track"][4], len(T["sections"]), f"track.section_count after press {i + 1}")
        expect_eq(sn["track"][5], len(T["vertices"]), f"track.vertex_count after press {i + 1}")
        expect_eq(sn["track"][8], T["start_section"], f"track.start_section after press {i + 1}")
        expect_eq(sn["name"], ("TRACK%d" % want).ljust(8, "\0")[:8], f"the loaded image's name after press {i + 1}")
        sec0 = T["sections"][0]
        expect_eq(sn["sec0"][:3], list(sec0["centre"]), f"track.sections[0].centre after press {i + 1} (the data is the file's)")
        expect_eq(sn["status"], 0, f"track_status after press {i + 1}")
        ptrs.add(sn["track"][0])
    expect_true(len(ptrs) <= 4, "the track images use at most 4 distinct heap blocks over 12 loads (the old image is freed)", f"{len(ptrs)} different vertex tables",
                "free(track_image) after a successful load; a failed parse frees the NEW image.")


@check("menu_game_runs_on_track_2", hint="Entering the game after choosing track 2 places the ship on track 2's start section; the whole collision script runs there (frames_replay..., ship_stays... above).")
def _(ctx):
    o = run_of(ctx, "menu")
    e = o.info["entry"]
    S = T2["sections"][T2["start_section"]]
    want = [S["centre"][i] + ((S["up"][i] * 120) >> 12) for i in range(3)]
    expect_eq(e["ship"][:3], want, "the ship's position at entry (track 2's start section, hover 120 along up)")
    expect_eq(e["section"], T2["start_section"], "ship_section at entry")
    expect_eq(e["track"]["sel"], 2, "track_selected when the game is entered")


@check("menu_restarts_the_music", hint="Reading the disc interrupts CD-DA: every track_switch ends with audio_music_start() (a CdlPlay), so audio_stats.music_cmds grows by one per press.")
def _(ctx):
    o = run_of(ctx, "menu")
    base = o.info["start"]["music"]
    after = [sn["music"] for sn in o.snaps]
    expect_eq(after, [base + i + 1 for i in range(len(after))], "audio_stats.music_cmds after each press (start value + presses so far)")


def failed_menu(ctx, name):
    o = run_of(ctx, name)
    base = o.info["start"]
    expect_eq(base["sel"], 1, "track_selected at boot")
    expect_eq(len(o.snaps), 3, "snapshots")
    s1, s2, s3 = o.snaps[0], o.snaps[1], o.snaps[2]
    expect_eq(s1["sel"], 1, f"{name} disc: track_selected after RIGHT (track 2 cannot be loaded: nothing changes)")
    expect_eq(s1["track"], base["track"], f"{name} disc: the Track struct is unchanged after the failed load", hint="Parse into a separate Track: track_parse zeroes its output when it fails.")
    expect_eq(s1["image"], base["image"], f"{name} disc: track_image is unchanged after the failed load")
    expect_eq(s1["sec0"], base["sec0"], f"{name} disc: the old track's data is still there (the failed load must not free it)")
    expect_eq(s1["status"], 0, f"{name} disc: track_status stays 0 (the old track is fine)")
    expect_eq(s1["music"], base["music"] + 1, f"{name} disc: the music is restarted after a failed read too")
    expect_eq(s2["sel"], 1, f"{name} disc: LEFT loads track 1 again")
    expect_eq(s2["track"][4], len(T1["sections"]), f"{name} disc: section_count after LEFT")
    expect_eq(s3["sel"], 1, f"{name} disc: RIGHT fails again")
    expect_eq(s3["track"][4], len(T1["sections"]), f"{name} disc: still track 1")
    e = o.info["entry"]
    S = T1["sections"][T1["start_section"]]
    expect_eq(e["ship"][:3], [S["centre"][i] + ((S["up"][i] * 120) >> 12) for i in range(3)], f"{name} disc: the game starts on track 1")
    rows = by_seg(o).get(1, [])
    expect_true(len(rows) >= 100 and rows[-1]["cs"][0] >= 10, f"{name} disc: the game plays (the wall run hits the wall)", f"{len(rows)} rows", "")


@check("menu_failed_load_keeps_the_track", hint="A corrupt TRACK2.TRK (bad magic) must leave `track`, track_image, track_selected and track_status as they were.")
def _(ctx):
    failed_menu(ctx, "bad")


@check("menu_missing_file_keeps_the_track", hint="A TRACK2.TRK that is not on the disc: cd_load_file returns NULL; return TRK_ERR_READ and change nothing.")
def _(ctx):
    failed_menu(ctx, "missing")
