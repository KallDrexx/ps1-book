#!/usr/bin/env python3
"""texgen.py -- original procedural textures for the book (PNG, deterministic, Pillow only).

  texgen.py OUTDIR [--seed N]        write every texture as OUTDIR/<name>.png
  texgen.py --list                   print name, size, intended bpp

Every 4-bpp texture uses <= 16 colours and the 8-bpp crate <= 256, so img2tim.py
converts them losslessly (no quantiser involved). No external fonts: the logo
is drawn from a built-in 5x7 pixel font.
"""
import argparse, math, sys
from pathlib import Path
from PIL import Image, ImageDraw


class Lcg:
    def __init__(self, seed): self.s = (seed * 2654435761 + 12345) & 0xFFFFFFFF
    def u32(self):
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFF
        return self.s >> 8
    def below(self, n): return self.u32() % n


def _new(w, h, col):
    im = Image.new("RGB", (w, h), col)
    return im, ImageDraw.Draw(im), im.load()


def _speckle(px, w, h, rng, pal, x0=0, y0=0, x1=None, y1=None):
    x1 = w if x1 is None else x1; y1 = h if y1 is None else y1
    for y in range(y0, y1):
        for x in range(x0, x1):
            px[x, y] = pal[rng.below(len(pal))]


# --- individual textures --------------------------------------------------------

def crate(rng):                                   # 64x64, 8 bpp: wood planks with a frame and X brace
    im, d, px = _new(64, 64, (0, 0, 0))
    for y in range(64):
        for x in range(64):
            plank = x // 16
            g = math.sin((y * 0.35) + plank * 1.7 + math.sin(x * 0.4) * 0.6)
            n = rng.below(5)
            v = 118 + int(22 * g) + n * 3 + (plank % 2) * 10
            px[x, y] = (v, int(v * 0.68), int(v * 0.36))
    dark, light = (60, 36, 18), (176, 120, 66)
    for x in (0, 15, 16, 31, 32, 47, 48, 63):
        d.line([(x, 0), (x, 63)], fill=dark)
    d.rectangle([0, 0, 63, 63], outline=dark)
    d.rectangle([1, 1, 62, 62], outline=light)
    d.rectangle([4, 4, 59, 59], outline=dark)
    d.line([(4, 4), (59, 59)], fill=dark, width=3)
    d.line([(4, 59), (59, 4)], fill=dark, width=3)
    for (x, y) in ((6, 6), (57, 6), (6, 57), (57, 57), (31, 31)):
        d.rectangle([x - 1, y - 1, x + 1, y + 1], fill=(210, 210, 200))
    return im


def panel(rng):                                   # 64x64, 4 bpp: riveted metal plate
    pal = [(70, 76, 86), (82, 90, 102), (96, 104, 118), (58, 62, 70)]
    im, d, px = _new(64, 64, pal[1])
    _speckle(px, 64, 64, rng, pal[:3])
    d.rectangle([0, 0, 63, 63], outline=(30, 32, 38))
    d.line([(1, 1), (62, 1)], fill=(150, 160, 176)); d.line([(1, 1), (1, 62)], fill=(150, 160, 176))
    d.line([(1, 62), (62, 62)], fill=pal[3]); d.line([(62, 1), (62, 62)], fill=pal[3])
    d.rectangle([12, 12, 51, 51], outline=pal[3]); d.line([(13, 52), (52, 52)], fill=(150, 160, 176))
    for (x, y) in ((5, 5), (58, 5), (5, 58), (58, 58)):
        d.rectangle([x - 1, y - 1, x + 1, y + 1], fill=(190, 196, 206)); px[x + 1, y + 1] = (30, 32, 38)
    return im


FONT = {
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "V": ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "I": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"],
    "N": ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"],
}


def logo(rng):                                    # 128x64, 4 bpp: "HOVERLINE" in block letters
    bg, bar1, bar2, white = (8, 12, 40), (0, 200, 220), (230, 40, 170), (255, 255, 255)
    ramp = [(0, 255, 255), (60, 200, 255), (120, 140, 255), (200, 90, 255)]
    im, d, px = _new(128, 64, bg)
    d.rectangle([0, 0, 127, 63], outline=bar1)
    d.rectangle([2, 2, 125, 61], outline=bar2)
    scale, word = 2, "HOVERLINE"
    x0 = (128 - len(word) * 6 * scale + scale) // 2
    y0 = 20
    for i, ch in enumerate(word):
        for gy, row in enumerate(FONT[ch]):
            for gx, c in enumerate(row):
                if c == "#":
                    col = ramp[min(3, gy * 4 // 7)]
                    X, Y = x0 + (i * 6 + gx) * scale, y0 + gy * scale
                    d.rectangle([X, Y, X + scale - 1, Y + scale - 1], fill=col)
    d.polygon([(8, 44), (120, 44), (112, 50), (16, 50)], fill=bar2)
    d.line([(16, 12), (112, 12)], fill=white)
    d.line([(24, 14), (104, 14)], fill=bar1)
    return im


def hull_a(rng):                                  # 64x64, 4 bpp: grey hull plating, grid of panels
    pal = [(104, 112, 124), (116, 124, 136), (128, 136, 148), (84, 90, 100)]
    im, d, px = _new(64, 64, pal[1])
    for cy in range(0, 64, 32):
        for cx in range(0, 64, 32):
            tone = pal[rng.below(3)]
            d.rectangle([cx, cy, cx + 31, cy + 31], fill=tone)
            d.rectangle([cx, cy, cx + 31, cy + 31], outline=pal[3])
            d.line([(cx + 2, cy + 2), (cx + 29, cy + 2)], fill=(168, 176, 190))
    for y in range(64):
        for x in range(64):
            if rng.below(23) == 0: px[x, y] = pal[3]
    return im


def hull_b(rng):                                  # 64x64, 4 bpp: livery with diagonal stripes
    white, red, navy, grey = (232, 236, 240), (214, 40, 48), (24, 40, 96), (170, 176, 188)
    im, d, px = _new(64, 64, white)
    for k in range(-64, 64, 32):
        d.polygon([(k, 0), (k + 12, 0), (k + 76, 64), (k + 64, 64)], fill=red)
        d.polygon([(k + 14, 0), (k + 18, 0), (k + 82, 64), (k + 78, 64)], fill=navy)
    d.rectangle([0, 0, 63, 63], outline=grey)
    return im


def wing(rng):                                    # 64x32, 4 bpp
    a, b, c = (40, 48, 70), (70, 84, 120), (0, 220, 240)
    im, d, px = _new(64, 32, a)
    for y in range(32):
        d.line([(0, y), (63, y)], fill=(a, b)[(y // 4) % 2])
    d.rectangle([0, 14, 63, 17], fill=c)
    d.rectangle([0, 0, 63, 31], outline=(20, 24, 36))
    return im


def asphalt(rng):                                 # 64x64, 4 bpp
    pal = [(58, 60, 66), (66, 68, 74), (74, 76, 82), (50, 52, 58)]
    im, d, px = _new(64, 64, pal[1])
    _speckle(px, 64, 64, rng, pal)
    return im


def asphalt_worn(rng):                            # 64x64, 4 bpp: patches and cracks
    pal = [(62, 64, 70), (72, 74, 80), (84, 86, 92), (46, 48, 54)]
    im, d, px = _new(64, 64, pal[1])
    _speckle(px, 64, 64, rng, pal[:3])
    for _ in range(3):
        x, y = rng.below(64), rng.below(64)
        for _ in range(14):
            px[x % 64, y % 64] = pal[3]
            x += rng.below(3) - 1; y += 1 + rng.below(2)
    d.rectangle([20, 22, 43, 41], outline=pal[0])
    return im


def lane_stripe(rng):                             # 64x64, 4 bpp: dashed centre line (runs along v)
    pal = [(58, 60, 66), (66, 68, 74), (74, 76, 82), (50, 52, 58)]
    im, d, px = _new(64, 64, pal[1])
    _speckle(px, 64, 64, rng, pal)
    d.rectangle([30, 4, 33, 27], fill=(236, 236, 224))
    d.rectangle([30, 36, 33, 59], fill=(236, 236, 224))
    return im


def boost(rng):                                   # 64x64, 4 bpp: chevrons pointing toward +v (forward)
    bg, edge, hi, lo = (10, 20, 50), (0, 90, 160), (0, 230, 255), (0, 140, 200)
    im, d, px = _new(64, 64, bg)
    d.rectangle([0, 0, 63, 63], outline=edge); d.rectangle([2, 2, 61, 61], outline=edge)
    for k, col in ((6, lo), (24, hi), (42, lo)):
        d.polygon([(10, k), (32, k + 12), (54, k), (54, k + 8), (32, k + 20), (10, k + 8)], fill=col)
    return im


def start_line(rng):                              # 64x64, 4 bpp: chequered flag
    im, d, px = _new(64, 64, (0, 0, 0))
    for y in range(64):
        for x in range(64):
            px[x, y] = (240, 240, 240) if ((x // 8) + (y // 8)) % 2 else (16, 16, 20)
    return im


def wall_a(rng):                                  # 64x64, 4 bpp: dark wall with glowing rail
    pal = [(30, 34, 46), (38, 44, 58), (46, 52, 68)]
    im, d, px = _new(64, 64, pal[1])
    _speckle(px, 64, 64, rng, pal)
    d.rectangle([0, 26, 63, 29], fill=(0, 200, 230)); d.line([(0, 25), (63, 25)], fill=(0, 100, 130)); d.line([(0, 30), (63, 30)], fill=(0, 100, 130))
    return im


def wall_b(rng):                                  # 64x64, 4 bpp: hazard stripes
    yel, blk = (240, 200, 0), (24, 24, 24)
    im, d, px = _new(64, 64, yel)
    for k in range(-64, 128, 32):
        d.polygon([(k, 0), (k + 16, 0), (k + 16 - 64, 64), (k - 64, 64)], fill=blk)
    d.rectangle([0, 0, 63, 63], outline=blk)
    return im


def glow(rng):                                    # 64x64, 4 bpp: vertical cyan gradient
    im, d, px = _new(64, 64, (0, 0, 0))
    for y in range(64):
        t = 15 - min(15, y // 4)
        d.line([(0, y), (63, y)], fill=(0, 16 * t, 17 * t))
    return im


def pylon(rng):                                   # 32x64, 4 bpp
    a, b = (230, 230, 236), (230, 60, 30)
    im, d, px = _new(32, 64, a)
    for y in range(0, 64, 16):
        d.rectangle([0, y + 4, 31, y + 11], fill=b)
    d.rectangle([0, 0, 31, 63], outline=(90, 94, 104))
    return im


def tower(rng):                                   # 64x64, 4 bpp: windows
    wall, win, lit = (52, 58, 78), (20, 24, 36), (255, 220, 120)
    im, d, px = _new(64, 64, wall)
    for gy in range(4, 60, 12):
        for gx in range(6, 58, 14):
            d.rectangle([gx, gy, gx + 7, gy + 7], fill=lit if rng.below(3) == 0 else win)
    return im


def sky16(rng):                                   # 64x64, 16 bpp: smooth gradient (exercises the 16-bpp path)
    im, d, px = _new(64, 64, (0, 0, 0))
    for y in range(64):
        for x in range(64):
            px[x, y] = (20 + y * 2, 40 + y * 2 + x // 4, 120 + y + x // 2)
    return im


# name -> (function, intended bpp)
TEXTURES = {
    "crate": (crate, 8), "panel": (panel, 4), "logo": (logo, 4),
    "hull_a": (hull_a, 4), "hull_b": (hull_b, 4), "wing": (wing, 4),
    "asphalt": (asphalt, 4), "asphalt_worn": (asphalt_worn, 4), "lane_stripe": (lane_stripe, 4),
    "boost": (boost, 4), "start_line": (start_line, 4), "wall_a": (wall_a, 4), "wall_b": (wall_b, 4),
    "glow": (glow, 4), "pylon": (pylon, 4), "tower": (tower, 4), "sky16": (sky16, 16),
}


def generate(seed=1):
    """Return {name: (PIL.Image RGB, bpp)}. Each texture gets its own RNG stream so adding one never changes another."""
    out = {}
    for i, (name, (fn, bpp)) in enumerate(TEXTURES.items()):
        out[name] = (fn(Lcg(seed * 1000 + i)), bpp)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir", nargs="?"); ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    texs = generate(a.seed)
    if a.list or not a.outdir:
        for n, (im, bpp) in texs.items():
            print(f"{n:14s} {im.width}x{im.height} {bpp} bpp")
        return
    out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
    for n, (im, bpp) in texs.items():
        im.save(out / f"{n}.png")
    print(f"wrote {len(texs)} PNGs to {out}")


if __name__ == "__main__":
    main()
