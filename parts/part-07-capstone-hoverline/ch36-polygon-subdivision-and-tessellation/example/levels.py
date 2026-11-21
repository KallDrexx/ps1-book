#!/usr/bin/env python3
"""levels.py -- which subdivision level every section gets from a camera, and what that costs. A planning tool, not the verifier.

  python levels.py build/assets/TRACK.TRK --section 0 --back 1300 --height 450        # from starter/, after make

The camera stands `back` units behind the center of --section along its forward vector and `height` units above the road, looking along the section's
heading (the harness' poses; pitch 0 as in the fly camera). Depth is the view-space z of a vertex: for a camera at yaw `a` it is dx * sin(a) + dz * cos(a)
with d = vertex - eye (floating point here; the verifier's model is the GTE's integer arithmetic, so a section within a unit or two of a threshold can
differ). The rule is README 5.4: the smallest depth among the section's four road-edge vertices that are in front of the near limit; 2 below Z2, 1 below Z1.
Prints one line per section in front of the camera, nearest first, and the quads a face of each level adds.
"""
import argparse
import math
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("PS1BOOK_ROOT", Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(ROOT / "tools" / "assets"))
import formats   # noqa: E402

NEAR_Z, Z1, Z2, FAR = 128, 4000, 2000, 32767


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trk")
    ap.add_argument("--section", type=int, default=0)
    ap.add_argument("--back", type=int, default=1300)
    ap.add_argument("--height", type=int, default=450)
    ap.add_argument("--count", type=int, default=14, help="how many sections to print (default 14)")
    a = ap.parse_args()
    t = formats.parse_trk(Path(a.trk).read_bytes())
    s = t["sections"][a.section]
    f, u = s["forward"], s["up"]
    eye = [s["centre"][k] - f[k] * a.back / 4096 + u[k] * a.height / 4096 for k in range(3)]
    yaw = math.atan2(f[0], f[2])
    sy, cy = math.sin(yaw), math.cos(yaw)
    n = len(t["sections"])
    rows = []
    for i, sec in enumerate(t["sections"]):
        zs = []
        for vi in sec["edges"]:
            d = [t["vertices"][vi][k] - eye[k] for k in range(3)]
            if max(abs(c) for c in d) > FAR:
                continue
            z = d[0] * sy + d[2] * cy
            if z >= NEAR_Z:
                zs.append(z)
        if zs:
            z = min(zs)
            rows.append((z, i, 2 if z < Z2 else 1 if z < Z1 else 0))
    rows.sort()
    print(f"eye = ({eye[0]:.0f}, {eye[1]:.0f}, {eye[2]:.0f}), yaw {math.degrees(yaw):.1f} deg; Z1 = {Z1}, Z2 = {Z2}\n")
    print("section  nearest road-edge z   level  quads per face   bar (one # per 250 units of depth)")
    quads = 0
    for z, i, lv in rows[:a.count]:
        print(f"{i:7d}  {z:19.0f}   {lv:5d}  {4 ** lv:14d}   {'#' * int(z // 250)}")
    for z, i, lv in rows:
        quads += 5 * 4 ** lv
    by = [sum(1 for r in rows if r[2] == k) for k in range(3)]
    print(f"\nsections with a usable edge vertex: {len(rows)} of {n}; at level 0 / 1 / 2: {by[0]} / {by[1]} / {by[2]}")
    print(f"upper bound on the quads: {quads} (5 faces per section, 4^level each); at 40 bytes that is {quads * 40} of the 32768-byte buffer, before culling")


if __name__ == "__main__":
    main()
