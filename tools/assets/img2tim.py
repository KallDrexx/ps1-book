#!/usr/bin/env python3
"""img2tim.py -- PNG -> TIM (4/8/16/24 bpp), plus a TIM validator.

  img2tim.py in.png out.tim --bpp 4|8|16|24 [--x X] [--y Y] [--cx CX] [--cy CY]
  img2tim.py --check file.tim [file2.tim ...]      validate and describe TIMs (exit 1 on error)
  img2tim.py --to-png file.tim out.png             decode a TIM for a quick look

X/Y: where the image goes in VRAM (X in 16-bit units, default 320,0).
CX/CY: where the CLUT goes (CX multiple of 16, default 0,480). 4/8 bpp only.
4/8 bpp: if the PNG has <= 16/256 colours the palette is exact (first-appearance
order); otherwise Pillow's median-cut quantiser is used (no dithering).
Pixels with alpha < 128 become the transparent colour 0x0000 at palette index 0.
Opaque black is stored as 0x0421 so it is not mistaken for transparent.
"""
import argparse, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tim as T
from PIL import Image


def _palette_and_indices(im: Image.Image, ncol: int):
    """im is RGBA. Return (palette as list of 16-bit colours padded to ncol, indices row-major)."""
    w, h = im.size
    px = list(im.get_flattened_data()) if hasattr(im, "get_flattened_data") else list(im.getdata())
    has_t = any(p[3] < 128 for p in px)
    keyed = [(p[0] >> 3, p[1] >> 3, p[2] >> 3) for p in px]
    uniq = []
    seen = {}
    for p, k in zip(px, keyed):
        if p[3] < 128 or k in seen:
            continue
        seen[k] = len(uniq) + (1 if has_t else 0)
        uniq.append(k)
    room = ncol - (1 if has_t else 0)
    if len(uniq) <= room:
        pal = ([0] if has_t else []) + [T.bgr555(r << 3, g << 3, b << 3) for r, g, b in uniq]
        idx = [0 if p[3] < 128 else seen[k] for p, k in zip(px, keyed)]
    else:
        rgb = Image.new("RGB", (w, h))
        rgb.putdata([(p[0], p[1], p[2]) if p[3] >= 128 else (0, 0, 0) for p in px])
        q = rgb.quantize(colors=room, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        qp = q.getpalette()[:room * 3]
        off = 1 if has_t else 0
        pal = ([0] if has_t else []) + [T.bgr555(qp[i * 3], qp[i * 3 + 1], qp[i * 3 + 2]) for i in range(len(qp) // 3)]
        qi = list(q.get_flattened_data()) if hasattr(q, "get_flattened_data") else list(q.getdata())
        idx = [0 if p[3] < 128 else qi[i] + off for i, p in enumerate(px)]
    pal += [0] * (ncol - len(pal))
    return pal, idx


def convert(png_path, bpp, x=320, y=0, cx=0, cy=480) -> bytes:
    im = Image.open(png_path).convert("RGBA")
    w, h = im.size
    units = T.units_for_pixels(w, bpp)
    if (units * h) % 2:
        raise SystemExit("image data would not be a multiple of 4 bytes: make width*height even (and 4-bpp width % 4 == 0)")
    if bpp in (4, 8):
        pal, idx = _palette_and_indices(im, 16 if bpp == 4 else 256)
        data = T.pack_indices(idx, bpp)
        clut = T.Block(cx, cy, len(pal), 1, struct.pack("<%dH" % len(pal), *pal))
    else:
        px = list(im.get_flattened_data()) if hasattr(im, "get_flattened_data") else list(im.getdata())
        if bpp == 16:
            data = struct.pack("<%dH" % len(px), *[T.bgr555(*p) for p in px])
        else:
            data = b"".join(bytes(p[:3]) for p in px)
        clut = None
    return T.build(T.Tim(bpp, T.Block(x, y, units, h, data), clut))


def describe(path) -> str:
    t = T.parse(Path(path).read_bytes())
    s = f"{path}: {t.bpp}-bpp {t.pixel_width}x{t.height} px, image at ({t.image.x},{t.image.y}) {t.image.w}x{t.image.h} units"
    if t.clut:
        c = t.clut
        s += f", CLUT at ({c.x},{c.y}) {c.w}x{c.h}"
        if c.x % 16:
            raise T.TimError("CLUT x not a multiple of 16")
    if t.bpp <= 16 and not T.fits_in_page(t.image.x, t.image.y, t.image.w, t.image.h, t.bpp):
        s += "  [WARNING: crosses a texture-page boundary]"
    T.decode_rgba(t)       # must decode
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--bpp", type=int, choices=(4, 8, 16, 24))
    ap.add_argument("--x", type=int, default=320); ap.add_argument("--y", type=int, default=0)
    ap.add_argument("--cx", type=int, default=0); ap.add_argument("--cy", type=int, default=480)
    ap.add_argument("--check", action="store_true"); ap.add_argument("--to-png", action="store_true")
    a = ap.parse_args(argv)
    if a.check:
        bad = 0
        for f in a.files:
            try:
                print(describe(f))
            except (T.TimError, OSError, struct.error) as e:
                print(f"{f}: INVALID: {e}"); bad += 1
        sys.exit(1 if bad else 0)
    if a.to_png:
        t = T.parse(Path(a.files[0]).read_bytes())
        w, h, px = T.decode_rgba(t)
        im = Image.new("RGBA", (w, h)); im.putdata(px); im.save(a.files[1]); return
    if len(a.files) != 2 or not a.bpp:
        ap.error("usage: img2tim.py in.png out.tim --bpp N")
    data = convert(a.files[0], a.bpp, a.x, a.y, a.cx, a.cy)
    Path(a.files[1]).write_bytes(data)
    print(f"{a.files[1]}: {len(data)} bytes")


if __name__ == "__main__":
    main()
