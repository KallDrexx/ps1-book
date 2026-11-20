#!/usr/bin/env python3
"""tiledump.py -- what the track tiles ask for and which faces use them: the input of your VRAM plan.

  python tiledump.py build/assets/TRACK.TPK build/assets/TRACK.TRK        # from starter/, after make

Per texture id: bits per pixel, the rectangle and CLUT the TIM itself names (its DEFAULT place, which your plan may ignore),
the size in texels, the footprint in a texture page, how many faces use the tile and how many of those carry FLIP_H.
Also prints what is already in VRAM from the program's other files when you pass --disc-dir (LOGO.TIM, PROPS.TPK).
Needs the book's tools (PS1BOOK_ROOT, set by tools/env.sh).
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("PS1BOOK_ROOT", Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(ROOT / "tools" / "assets"))
import formats   # noqa: E402
import tim as T  # noqa: E402

FLIP_H = 16


def rect_of(b):
    return f"({b.x},{b.y}) {b.w}x{b.h}"



def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tpk")
    ap.add_argument("trk")
    ap.add_argument("--disc-dir", help="directory with LOGO.TIM and PROPS.TPK (build/assets) to list what is already in VRAM")
    a = ap.parse_args()
    tpk = formats.parse_tpk(Path(a.tpk).read_bytes())
    trk = formats.parse_trk(Path(a.trk).read_bytes())
    uses, flips = {}, {}
    for f in trk["faces"]:
        uses[f["tex"]] = uses.get(f["tex"], 0) + 1
        flips[f["tex"]] = flips.get(f["tex"], 0) + bool(f["flags"] & FLIP_H)
    print(f"{a.tpk}: {tpk['count']} tiles;  {a.trk}: {len(trk['faces'])} faces, texture_count {trk['texture_count']}\n")
    print("id  bpp  texels  image rect (as in the TIM)   CLUT rect (as in the TIM)   faces  flipped  units of VRAM (image + CLUT)")
    for i, data in enumerate(tpk["tims"]):
        t = T.parse(data)
        mult = {4: 4, 8: 2, 16: 1}[t.bpp]
        units = t.image.w * t.image.h + (t.clut.w * t.clut.h if t.clut else 0)
        print(f"{i:<3} {t.bpp:<4} {t.image.w * mult}x{t.image.h:<4} {rect_of(t.image):<28} {rect_of(t.clut) if t.clut else '-':<27} {uses.get(i, 0):<6} {flips.get(i, 0):<8} {units}")
    print(f"untextured faces (tex = 0xFF): {uses.get(255, 0)}")
    print("\nPage footprint of one 256-texel-wide texture: 4 bpp = 64 units, 8 bpp = 128 units, 16 bpp = 256 units; a page is 256 lines tall.")
    if a.disc_dir:
        d = Path(a.disc_dir)
        print("\nAlready in VRAM (loaded by main.c at the places the TIMs name):")
        lg = T.parse((d / "LOGO.TIM").read_bytes())
        print(f"  LOGO.TIM   image {rect_of(lg.image)}  CLUT {rect_of(lg.clut)}")
        for i, data in enumerate(formats.parse_tpk((d / "PROPS.TPK").read_bytes())["tims"]):
            t = T.parse(data)
            print(f"  PROPS.TPK {i} image {rect_of(t.image)}  CLUT {rect_of(t.clut)}")
        print("  framebuffers  (0,0) 320x240 and (0,240) 320x240")


if __name__ == "__main__":
    main()
