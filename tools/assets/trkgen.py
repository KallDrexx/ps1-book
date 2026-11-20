#!/usr/bin/env python3
"""trkgen.py -- procedurally generate an original looping anti-gravity track (.TRK) and a JSON manifest.

  trkgen.py OUT.TRK [--track 1|2] [--sections N] [--manifest OUT.json]

Track 1: 112 sections (about 1000 units each), banked bends and rolling hills, a lap of about 112000 units.
Track 2: 104 sections, a three-lobed circuit. Geometry follows Appendix E (".TRK"):
+Y is down, so a hill has NEGATIVE y; vertices are int32 world units and the track spans more than
+-32767, so renderers must work camera-relative (Chapter 34).
Cross-section (6 vertices per ring):  0 LT  1 L  2 CL  3 CR  4 R  5 RT
     LT                        RT        (walls are 250 high, road half-width 600,
     |  L___CL___CR___R  |              three 400-unit lanes; the road is the three
     +--wall--lane-lane-lane--wall-+    quads 1-2, 2-3, 3-4)
"""
import argparse, hashlib, json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import formats as F
from shpgen import newell, flip_order

HALF_WIDTH = 600
WALL_H = 250
RING_U = [-HALF_WIDTH, -HALF_WIDTH, -HALF_WIDTH // 3, HALF_WIDTH // 3, HALF_WIDTH, HALF_WIDTH]
RING_H = [WALL_H, 0, 0, 0, 0, WALL_H]
VIS_AHEAD, VIS_BEHIND = 24, 4
VIS_NEAR_FACTOR = 6.0            # also visible: sections whose centre is within 6 average section lengths
BANK_GAIN = 6000                 # bank angle (radians) = BANK_GAIN * heading change per unit length, clamped
BANK_MAX = 0.45                  # ~26 degrees
BANK_SMOOTH = 4                  # triangular smoothing over +-4 rings

# ---------------------------------------------------------------- small vector helpers
def add(a, b): return tuple(x + y for x, y in zip(a, b))
def sub(a, b): return tuple(x - y for x, y in zip(a, b))
def mul(a, k): return tuple(x * k for x in a)
def dot(a, b): return sum(x * y for x, y in zip(a, b))
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def norm(a):
    l = math.sqrt(dot(a, a)); return tuple(x / l for x in a)
def length(a): return math.sqrt(dot(a, a))

# ---------------------------------------------------------------- centre line
def control_points(track):
    pts = []
    if track == 1:
        n = 14
        for k in range(n):
            t = 2 * math.pi * k / n
            m = 1 + 0.18 * math.sin(2 * t + 0.7) + 0.08 * math.sin(3 * t + 1.9)
            pts.append((20000 * math.cos(t) * m, -1200 * math.sin(t + 0.5) - 350 * math.sin(3 * t), 13000 * math.sin(t) * m))
    else:
        n = 12
        for k in range(n):
            t = 2 * math.pi * k / n
            r = 15000 * (1 + 0.32 * math.sin(3 * t + 0.4) + 0.12 * math.cos(2 * t))
            pts.append((r * math.cos(t), -900 * math.sin(2 * t) - 350 * math.cos(t), r * math.sin(t)))
    return pts

def catmull_rom(pts, per=48):
    n, out = len(pts), []
    for i in range(n):
        p0, p1, p2, p3 = pts[(i - 1) % n], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        for s in range(per):
            t = s / per
            out.append(tuple(0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t * t
                                    + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t ** 3) for k in range(3)))
    return out

def resample(poly, n):
    """n points equally spaced by arc length along the closed polyline."""
    m = len(poly)
    cum = [0.0]
    for i in range(m):
        cum.append(cum[-1] + length(sub(poly[(i + 1) % m], poly[i])))
    total, out, j = cum[-1], [], 0
    for k in range(n):
        s = total * k / n
        while cum[j + 1] < s: j += 1
        f = (s - cum[j]) / (cum[j + 1] - cum[j])
        out.append(add(poly[j], mul(sub(poly[(j + 1) % m], poly[j]), f)))
    return out

# ---------------------------------------------------------------- frames
def frames(centres):
    """Per ring: (right', up') with banking."""
    n = len(centres)
    fwd = [norm(sub(centres[(i + 1) % n], centres[(i - 1) % n])) for i in range(n)]
    right0 = [norm(cross(f, (0, -1, 0))) for f in fwd]
    turn = []
    for i in range(n):
        a = norm(sub(centres[i], centres[(i - 1) % n])); b = norm(sub(centres[(i + 1) % n], centres[i]))
        # signed horizontal heading change; right of heading (ax,az) is (az,-ax)
        turn.append(math.atan2(b[0] * a[2] - b[2] * a[0], b[0] * a[0] + b[2] * a[2]))
    seg = [length(sub(centres[(i + 1) % n], centres[(i - 1) % n])) / 2 for i in range(n)]
    raw = [BANK_GAIN * t / l for t, l in zip(turn, seg)]
    k = BANK_SMOOTH; wsum = sum(k + 1 - abs(j) for j in range(-k, k + 1))
    bank = [max(-BANK_MAX, min(BANK_MAX, sum((k + 1 - abs(j)) * raw[(i + j) % n] for j in range(-k, k + 1)) / wsum)) for i in range(n)]
    out = []
    for i in range(n):
        down0 = cross(fwd[i], right0[i])
        c, s = math.cos(bank[i]), math.sin(bank[i])
        right = add(mul(right0[i], c), mul(down0, s))
        down = add(mul(right0[i], -s), mul(down0, c))
        out.append((right, mul(down, -1), bank[i]))
    return out

def q412(v): return tuple(max(-4096, min(4096, round(c * 4096))) for c in v)

# ---------------------------------------------------------------- build
def generate(track=1, nsec=None):
    nsec = nsec or (112 if track == 1 else 104)
    dense = catmull_rom(control_points(track))
    centres = resample(dense, nsec)
    fr = frames(centres)
    verts = []
    for i in range(nsec):
        right, up, _ = fr[i]
        for u, h in zip(RING_U, RING_H):
            verts.append(tuple(round(centres[i][k] + u * right[k] + h * up[k]) for k in range(3)))
    boost_secs = [28, 29, 76, 77] if track == 1 else [18, 19, 44, 45, 80, 81]
    faces, sections = [], []
    ring = lambda r, k: (r % nsec) * 6 + k
    ring_c = [tuple((verts[ring(i, 1)][k] + verts[ring(i, 4)][k]) / 2 for k in range(3)) for i in range(nsec)]
    for i in range(nsec):
        a, b = i, (i + 1) % nsec
        ca, cb = ring_c[a], ring_c[b]
        centre = tuple(round((ca[k] + cb[k]) / 2) for k in range(3))
        fwd = norm(sub(cb, ca))
        up = norm(add(fr[a][1], fr[b][1]))
        right = norm(add(fr[a][0], fr[b][0]))
        right = norm(sub(right, mul(fwd, dot(right, fwd))))
        up = norm(sub(sub(up, mul(fwd, dot(up, fwd))), mul(right, dot(up, right))))
        first = len(faces)
        for k in range(5):
            pts_i = [ring(a, k), ring(a, k + 1), ring(b, k), ring(b, k + 1)]
            pts = [verts[x] for x in pts_i]
            if k == 0:   uv = [(0, 0), (0, 63), (63, 0), (63, 63)]; outward = right
            elif k == 4: uv = [(0, 63), (0, 0), (63, 63), (63, 0)]; outward = mul(right, -1)
            else:        uv = [(0, 0), (63, 0), (0, 63), (63, 63)]; outward = up
            if dot(newell(pts), outward) > 0:        # area vector must point into the solid
                order = flip_order(4)
                pts_i = [pts_i[o] for o in order]; uv = [uv[o] for o in order]
            flags, tex = 0, 0
            if k in (0, 4):
                flags = F.FACE_WALL; tex = 5 if i % 4 != 3 else 6
                if i % 2: flags |= F.FACE_FLIP_H
                color = (40, 60, 120)
            else:
                flags = F.FACE_FLOOR
                if k == 1: tex = 0 if i % 2 == 0 else 1
                elif k == 2: tex = 2
                else:
                    tex = 1 if i % 2 == 0 else 0
                    if i % 2: flags |= F.FACE_FLIP_H
                color = (70, 72, 80)
                if k == 2 and i in boost_secs: flags |= F.FACE_BOOST; tex = 3; color = (0, 200, 255)
                if i == 0: flags |= F.FACE_START; tex = 4; color = (240, 240, 240)
            faces.append(dict(v=pts_i, flags=flags, tex=tex, uv=uv, color=color))
        sections.append(dict(centre=centre, half_width=HALF_WIDTH, length=round(length(sub(cb, ca))),
                             forward=q412(fwd), right=q412(right), up=q412(up), first_face=first, face_count=5,
                             next=b, prev=(i - 1) % nsec, flags=F.SEC_START if i == 0 else 0,
                             edges=(ring(a, 1), ring(a, 4), ring(b, 1), ring(b, 4))))
    avg = sum(s["length"] for s in sections) / nsec
    vis = []
    for i in range(nsec):
        lst = []
        for off in range(nsec):
            j = (i + off) % nsec
            near = length(sub(sections[i]["centre"], sections[j]["centre"])) <= VIS_NEAR_FACTOR * avg
            if off <= VIS_AHEAD or off >= nsec - VIS_BEHIND or near:
                lst.append(j)
        vis.append(lst)
    total = sum(s["length"] for s in sections)
    data = F.build_trk("TRACK%d" % track, verts, faces, sections, vis, 0, total, 8)
    meta = dict(boost_sections=boost_secs, banks_deg=[round(math.degrees(f[2]), 2) for f in fr])
    return data, meta

def manifest(data, meta):
    d = F.parse_trk(data)
    secs, faces = d["sections"], d["faces"]
    def cnt(mask): return sum(1 for f in faces if f["flags"] & mask)
    slopes = []
    for s in secs:
        e = s["edges"]; v = d["vertices"]
        a = [(v[e[0]][k] + v[e[1]][k]) / 2 for k in range(3)]; b = [(v[e[2]][k] + v[e[3]][k]) / 2 for k in range(3)]
        h = math.hypot(b[0] - a[0], b[2] - a[2]); slopes.append(abs(b[1] - a[1]) / h)
    return dict(
        file=d["name"] + ".TRK", name=d["name"], size=len(data), sha256=hashlib.sha256(data).hexdigest(),
        section_count=len(secs), vertex_count=len(d["vertices"]), face_count=len(faces), vis_entries=sum(len(s["vis"]) for s in secs),
        texture_count=d["texture_count"], start_section=d["start_section"], total_length=d["total_length"],
        bbox=list(d["bbox"]), face_counts=dict(floor=cnt(F.FACE_FLOOR), wall=cnt(F.FACE_WALL), boost=cnt(F.FACE_BOOST),
                                               start=cnt(F.FACE_START), flip_h=cnt(F.FACE_FLIP_H)),
        boost_sections=meta["boost_sections"], start_faces=[i for i, f in enumerate(faces) if f["flags"] & F.FACE_START],
        centre_line=[list(s["centre"]) for s in secs], section_lengths=[s["length"] for s in secs],
        half_width=HALF_WIDTH, edges=[[list(d["vertices"][i]) for i in s["edges"]] for s in secs],
        vis=[s["vis"] for s in secs], vis_rule=dict(ahead=VIS_AHEAD, behind=VIS_BEHIND, near_factor=VIS_NEAR_FACTOR),
        max_slope=round(max(slopes), 4), max_bank_deg=max(abs(b) for b in meta["banks_deg"]),
        exceeds_int16=any(abs(c) > 32767 for v in d["vertices"] for c in v) or (d["bbox"][3] - d["bbox"][0]) > 32767)

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out"); ap.add_argument("--track", type=int, choices=(1, 2), default=1)
    ap.add_argument("--sections", type=int); ap.add_argument("--manifest")
    a = ap.parse_args(argv)
    data, meta = generate(a.track, a.sections)
    Path(a.out).write_bytes(data)
    if a.manifest:
        Path(a.manifest).write_text(json.dumps(manifest(data, meta), indent=1, sort_keys=True) + "\n")
    print(f"{a.out}: {len(data)} bytes")

if __name__ == "__main__":
    main()
