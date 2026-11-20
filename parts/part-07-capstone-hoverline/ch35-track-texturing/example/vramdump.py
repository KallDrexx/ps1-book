#!/usr/bin/env python3
"""Look at a VRAM dump from the host (the same picture PCSX-Redux's VRAM viewer shows).

  vramdump.py VRAM.BIN                     ASCII occupancy map: 1 character = 16 units x 16 lines, page boundaries marked
  vramdump.py VRAM.BIN --png out.png       the whole 1024 x 512 VRAM as a 16-bpp picture (needs Pillow, which the book's venv has)
  vramdump.py VRAM.BIN --png out.png --rect 576 256 64 128   only that rectangle (units, lines), enlarged x4

VRAM.BIN is the 1 MiB dump `verify.sh --keep` leaves in <work dir>/run-default/vram.bin (1024 x 512 x 16-bit, row-major).
In the map: '.' empty (all zero), '+' partly drawn, '#' mostly drawn. Texture pages start at every 4th column (64 units) and
at row 0 and row 16 (y = 0 and 256).
"""
import argparse
import struct
import sys

W, H = 1024, 512


def load(path):
    data = open(path, "rb").read()
    if len(data) < W * H * 2:
        sys.exit(f"{path}: {len(data)} bytes, expected {W * H * 2}")
    return data


def pixel(data, x, y):
    return struct.unpack_from("<H", data, (y * W + x) * 2)[0]


def ascii_map(data):
    cell_w, cell_h = 16, 16
    print("     " + "".join(f"{x // 64:<5x}" for x in range(0, W, 64)) + " <- page column (x / 64, hex)")
    for cy in range(0, H, cell_h):
        row = []
        for cx in range(0, W, cell_w):
            n = sum(1 for y in range(cy, cy + cell_h, 4) for x in range(cx, cx + cell_w, 2) if pixel(data, x, y))
            row.append("." if n == 0 else "+" if n < 24 else "#")
        sep = "-" if cy % 256 == 0 else " "
        out = ""
        for i, ch in enumerate(row):
            out += ("|" if i % 4 == 0 and i else "") + ch
        print(f"y{cy:3d}{sep}{out}")
    print("      each character = 16 units x 16 lines; '|' = texture page edge (every 64 units); '-' = page row (y 0, 256)")


def png(data, path, rect):
    from PIL import Image
    x0, y0, w, h = rect or (0, 0, W, H)
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            v = pixel(data, x0 + x, y0 + y)
            px[x, y] = ((v & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, ((v >> 10) & 31) * 255 // 31)
    if rect:
        im = im.resize((w * 4, h * 4), Image.NEAREST)
    im.save(path)
    print(f"wrote {path} ({im.width} x {im.height})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vram")
    ap.add_argument("--png")
    ap.add_argument("--rect", nargs=4, type=int, metavar=("X", "Y", "W", "H"))
    a = ap.parse_args()
    data = load(a.vram)
    if a.png:
        png(data, a.png, a.rect)
    else:
        ascii_map(data)


if __name__ == "__main__":
    main()
