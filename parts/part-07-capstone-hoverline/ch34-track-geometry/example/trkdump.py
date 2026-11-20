#!/usr/bin/env python3
"""trkdump.py -- print a .TRK (Appendix E.10) and, for an eye position, which vertices and faces the Chapter 34 rules keep.

  python trkdump.py build/assets/TRACK.TRK                     # header, flags, a few sections and one ring
  python trkdump.py build/assets/TRACK.TRK --eye 24000 -1500 -2500   # ... and how many vertices are "far" (any |vertex - eye| > 32767)

Standard library only. Vertices are s32 x, y, z (12 bytes); the far rule is the book's: d = vertex - eye in exact integers.
A face is skipped when any of its four vertices is far (the rest of the rules need the GTE: see the verifier's Ref class).
"""
import argparse
import struct
import sys

FAR = 32767
FLAGS = [(1, "FLOOR"), (2, "WALL"), (4, "BOOST"), (8, "START"), (16, "FLIP_H")]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("track")
    ap.add_argument("--eye", nargs=3, type=int, metavar=("X", "Y", "Z"))
    a = ap.parse_args()
    d = open(a.track, "rb").read()
    if d[:4] != b"TRK1":
        sys.exit("not a .TRK (magic is not TRK1)")
    size, = struct.unpack_from("<I", d, 4)
    name = d[8:24].split(b"\0")[0].decode()
    ns, nv, nf, nvis, start, flags, ntex = struct.unpack_from("<HHHHHHH", d, 0x18)
    ov, of, os_, ovis = struct.unpack_from("<IIII", d, 0x28)
    total, = struct.unpack_from("<I", d, 0x38)
    bbox = struct.unpack_from("<6i", d, 0x40)
    print(f"{name}: {size} bytes, {ns} sections, {nv} vertices, {nf} faces, {nvis} visibility entries, start section {start}, lap {total} units")
    print(f"tables at 0x{ov:X} (vertices), 0x{of:X} (faces), 0x{os_:X} (sections), 0x{ovis:X} (visibility)")
    print(f"bbox x {bbox[0]}..{bbox[3]}  y {bbox[1]}..{bbox[4]}  z {bbox[2]}..{bbox[5]}  (x span {bbox[3] - bbox[0]}, z span {bbox[5] - bbox[2]})")
    verts = [struct.unpack_from("<3i", d, ov + 12 * i) for i in range(nv)]
    faces = [(struct.unpack_from("<4H", d, of + 24 * i), struct.unpack_from("<H", d, of + 24 * i + 8)[0]) for i in range(nf)]
    counts = {n: sum(1 for _, f in faces if f & b) for b, n in FLAGS}
    print("faces by flag:", ", ".join(f"{n} {c}" for n, c in counts.items()))
    print("ring 0 (vertices 0..5):", verts[:6])
    for i in (0, ns // 2):
        s = struct.unpack_from("<3iHH", d, os_ + 64 * i)
        first, cnt = struct.unpack_from("<HH", d, os_ + 64 * i + 0x28)
        print(f"section {i}: centre {s[:3]}, length {s[4]}, faces {first}..{first + cnt - 1}")
    if a.eye:
        far = [i for i, v in enumerate(verts) if max(abs(v[k] - a.eye[k]) for k in range(3)) > FAR]
        skipped = sum(1 for v, _ in faces if any(i in set(far) for i in v))
        print(f"eye {tuple(a.eye)}: {len(far)} of {nv} vertices are far (some |vertex - eye| > {FAR}); {skipped} of {nf} faces would be skipped")


if __name__ == "__main__":
    main()
