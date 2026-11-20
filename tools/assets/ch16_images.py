#!/usr/bin/env python3
"""Generate the two original test images for Chapter 16 (procedural, no external assets).

  img16.bin   96x64 pixels, 16 bpp (PS1 BGR555, little-endian, bit 15 = 0): 12288 bytes
  img24.bin  320x240 pixels, 24 bpp (bytes R,G,B per pixel, row-major, no padding): 230400 bytes

Both are asymmetric on purpose: a flip, a shift or a swapped colour channel is visible.
  * corner markers: top-left RED, top-right GREEN, bottom-left BLUE, bottom-right WHITE
  * a letter "F" (not mirror-symmetric) near the top-left
  * a gradient background

Usage:  ch16_images.py OUTDIR [OUTDIR...]     (writes img16.bin and img24.bin into each directory)
        ch16_images.py --png OUTDIR           (also writes img16.ppm / img24.ppm previews)
"""
import sys
from pathlib import Path

F_GLYPH = ["#####",
           "#....",
           "#....",
           "####.",
           "#....",
           "#....",
           "#...."]


def make(w, h, cell):
    """Return rows of (r,g,b) tuples. `cell` = pixel size of one glyph cell; marker square is 4*cell."""
    img = [[(0, 0, 0)] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            r = 40 + (150 * x) // (w - 1) // 2
            g = 60 + (120 * y) // (h - 1)
            b = 200 - (120 * (x + y)) // (w + h - 2)
            img[y][x] = (r, g, b)
    m = 4 * cell
    marks = [(0, 0, (255, 0, 0)), (w - m, 0, (0, 255, 0)), (0, h - m, (0, 0, 255)), (w - m, h - m, (255, 255, 255))]
    for ox, oy, c in marks:
        for y in range(m):
            for x in range(m):
                img[oy + y][ox + x] = c
    gx, gy = m + 2 * cell, m // 2
    for gyi, row in enumerate(F_GLYPH):
        for gxi, ch in enumerate(row):
            if ch == "#":
                for y in range(cell):
                    for x in range(cell):
                        img[gy + gyi * cell + y][gx + gxi * cell + x] = (255, 240, 60)
    for x in range(w):                      # a black line across the middle row
        img[h // 2][x] = (0, 0, 0)
    return img


def to_bgr555(img):
    out = bytearray()
    for row in img:
        for r, g, b in row:
            v = (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)
            out += v.to_bytes(2, "little")
    return bytes(out)


def to_rgb24(img):
    return bytes(c for row in img for px in row for c in px)


def ppm(img):
    h, w = len(img), len(img[0])
    return b"P6\n%d %d\n255\n" % (w, h) + to_rgb24(img)


def main(argv):
    png = "--png" in argv
    dirs = [Path(a) for a in argv if not a.startswith("--")]
    if not dirs:
        print(__doc__)
        return 2
    i16, i24 = make(96, 64, 3), make(320, 240, 8)
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        (d / "img16.bin").write_bytes(to_bgr555(i16))
        (d / "img24.bin").write_bytes(to_rgb24(i24))
        if png:
            (d / "img16.ppm").write_bytes(ppm(i16))
            (d / "img24.ppm").write_bytes(ppm(i24))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
