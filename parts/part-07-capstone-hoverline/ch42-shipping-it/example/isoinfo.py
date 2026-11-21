#!/usr/bin/env python3
"""isoinfo.py: look inside a PlayStation disc image (README 6). Standard library only.

  python3 isoinfo.py release/hoverline.cue            the tracks, the volume identifiers, every file (LBA, size), SYSTEM.CNF
  python3 isoinfo.py a/hoverline.bin b/hoverline.bin  where two images differ: sector, offset, and what lives in that sector

A data sector of this image is 2352 bytes: 12 sync, 4 header (minutes, seconds, frame, mode), 8 sub-header, 2048 bytes of data (Form 1),
4 EDC, 276 ECC. The ISO 9660 structures are read from the 2048-byte part."""
import struct
import sys
from pathlib import Path

SECT = 2352


def data(img, lba):
    o = lba * SECT + 24
    return img[o:o + 2048]


def read(img, lba, size):
    return b"".join(data(img, lba + i) for i in range((size + 2047) // 2048))[:size]


def records(blob):
    pos = 0
    while pos < len(blob):
        n = blob[pos]
        if n == 0:
            pos = (pos // 2048 + 1) * 2048
            continue
        r = blob[pos:pos + n]
        yield r[33:33 + r[32]], r[25], struct.unpack_from("<I", r, 2)[0], struct.unpack_from("<I", r, 10)[0], r[18:25]
        pos += n


def walk(img, lba, size, prefix=""):
    for name, flags, e_lba, e_size, date in records(read(img, lba, size)):
        if name in (b"\x00", b"\x01"):
            continue
        nm = name.decode("ascii", "replace")
        if flags & 2:
            yield from walk(img, e_lba, e_size, prefix + nm + "/")
        else:
            yield prefix + nm, e_lba, e_size, date


def describe(cue):
    text = cue.read_text()
    print(text.rstrip())
    img = (cue.parent / next(l.split('"')[1] for l in text.splitlines() if l.startswith("FILE"))).read_bytes()
    pvd = data(img, 16)
    print(f"\n{len(img)} bytes = {len(img) // SECT} sectors")
    print("system     ", pvd[8:40].decode().strip())
    print("volume     ", pvd[40:72].decode().strip())
    print("copyright  ", pvd[702:739].decode().strip())
    print("created    ", pvd[813:829].decode("ascii", "replace"), "GMT%+.2f" % (int.from_bytes(pvd[829:830], "little", signed=True) / 4))
    root = struct.unpack_from("<I", pvd, 158)[0], struct.unpack_from("<I", pvd, 166)[0]
    print("\n  LBA     size  date (y m d h m s)  file")
    for nm, lba, size, d in sorted(walk(img, *root), key=lambda t: t[1]):
        print(f"{lba:5} {size:8}  {1900 + d[0]}-{d[1]:02}-{d[2]:02} {d[3]:02}:{d[4]:02}:{d[5]:02}  {nm}")
    for nm, lba, size, _ in walk(img, *root):
        if nm.startswith("SYSTEM.CNF"):
            print("\nSYSTEM.CNF:\n" + read(img, lba, size).decode("ascii", "replace"))


def diff(a, b):
    ia, ib = Path(a).read_bytes(), Path(b).read_bytes()
    print(f"{len(ia)} vs {len(ib)} bytes")
    pvd = data(ia, 16)
    root = struct.unpack_from("<I", pvd, 158)[0], struct.unpack_from("<I", pvd, 166)[0]
    owner = {16: "volume descriptor", root[0]: "root directory"}
    for nm, lba, size, _ in walk(ia, *root):
        for s in range((size + 2047) // 2048):
            owner[lba + s] = nm
    n = 0
    for s in range(min(len(ia), len(ib)) // SECT):
        x, y = ia[s * SECT:(s + 1) * SECT], ib[s * SECT:(s + 1) * SECT]
        if x != y:
            offs = [i for i in range(SECT) if x[i] != y[i]]
            print(f"sector {s:5} ({owner.get(s, 'a directory or free sector')}): {len(offs)} bytes differ, first at offset {offs[0]}")
            n += 1
    print("identical" if n == 0 and len(ia) == len(ib) else f"{n} sectors differ")


if __name__ == "__main__":
    if len(sys.argv) == 2:
        describe(Path(sys.argv[1]))
    elif len(sys.argv) == 3:
        diff(*sys.argv[1:])
    else:
        sys.exit(__doc__)
