#!/usr/bin/env python3
"""scenedump.py -- print a SCENE.BIN (Appendix E.9) and, for an eye position, which objects the Chapter 33 cull draws.

  python scenedump.py build/assets/SCENE.BIN                 # header, shape table, object table
  python scenedump.py build/assets/SCENE.BIN --eye 0 -1500 0 # ... and the cull's verdict per object

Standard library only. The cull is the book's rule: any |d| above 32000 -> not drawn; OBJ_ALWAYS_DRAW -> drawn;
else dx^2 + dy^2 + dz^2 <= (cull_radius + radius)^2, where radius = table radius * scale >> 12.
"""
import argparse
import struct
import sys

DRAW_LIMIT = 32000


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scene")
    ap.add_argument("--eye", nargs=3, type=int, metavar=("X", "Y", "Z"))
    a = ap.parse_args()
    d = open(a.scene, "rb").read()
    if d[:4] != b"SCN1":
        sys.exit("not a SCENE.BIN (magic is not SCN1)")
    size, ns, no, off_s, off_o, cull = struct.unpack_from("<IHHIII", d, 4)
    print(f"size {size}  shapes {ns}  objects {no}  shapes at 0x{off_s:X}  objects at 0x{off_o:X}  cull_radius {cull}")
    shapes = []
    for i in range(ns):
        name, radius = struct.unpack_from("<12sI", d, off_s + 16 * i)
        shapes.append((name.split(b"\0")[0].decode(), radius))
        print(f"  shape {i}: {shapes[-1][0]:<12} radius {radius}")
    shown = 0
    for i in range(no):
        sh, fl, x, y, z, rx, ry, rz, sc = struct.unpack_from("<HHiii3hH", d, off_o + 24 * i)
        radius = (shapes[sh][1] * sc) >> 12
        line = f"  object {i:3}: shape {sh} flags {fl} pos ({x}, {y}, {z}) rot ({rx}, {ry}, {rz}) scale {sc} radius {radius}"
        if a.eye:
            dd = [x - a.eye[0], y - a.eye[1], z - a.eye[2]]
            vis = max(abs(v) for v in dd) <= DRAW_LIMIT and (bool(fl & 1) or sum(v * v for v in dd) <= (cull + radius) ** 2)
            shown += vis
            line += f"   d = {tuple(dd)}  {'DRAW' if vis else 'culled'}"
        print(line)
    if a.eye:
        print(f"{shown} of {no} objects drawn from {tuple(a.eye)}")


if __name__ == "__main__":
    main()
