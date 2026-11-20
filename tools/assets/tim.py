"""TIM reader/writer (Appendix E, section "TIM").

A TIM is: magic 0x10, flags, [CLUT block], image block. All fields little-endian.
Widths in the file are in 16-bit VRAM units ("halfwords"), not pixels.
"""
import struct
from dataclasses import dataclass
from typing import Optional

MAGIC = 0x10
BPP_TO_PMODE = {4: 0, 8: 1, 16: 2, 24: 3}
PMODE_TO_BPP = {v: k for k, v in BPP_TO_PMODE.items()}
FLAG_CLUT = 0x08


class TimError(ValueError):
    pass


@dataclass
class Block:
    x: int          # VRAM x in 16-bit units
    y: int          # VRAM y in lines
    w: int          # width in 16-bit units
    h: int          # height in lines
    data: bytes     # w*h*2 bytes

    def check(self):
        if not (0 <= self.x < 1024 and 0 <= self.y < 512 and 1 <= self.w <= 1024 and 1 <= self.h <= 512):
            raise TimError(f"block rectangle out of VRAM: {self.x},{self.y} {self.w}x{self.h}")
        if len(self.data) != self.w * self.h * 2:
            raise TimError(f"block data is {len(self.data)} bytes, expected {self.w * self.h * 2}")


@dataclass
class Tim:
    bpp: int
    image: Block
    clut: Optional[Block] = None

    @property
    def pixel_width(self) -> int:
        w = self.image.w
        return {4: w * 4, 8: w * 2, 16: w, 24: w * 2 // 3}[self.bpp]

    @property
    def height(self) -> int:
        return self.image.h


def units_for_pixels(w_pixels: int, bpp: int) -> int:
    """Width in 16-bit units needed for w_pixels pixels."""
    if bpp == 4:
        if w_pixels % 4: raise TimError("4-bpp width must be a multiple of 4 pixels")
        return w_pixels // 4
    if bpp == 8:
        if w_pixels % 2: raise TimError("8-bpp width must be a multiple of 2 pixels")
        return w_pixels // 2
    if bpp == 16:
        return w_pixels
    if bpp == 24:
        if w_pixels % 2: raise TimError("24-bpp width must be even")
        return w_pixels * 3 // 2
    raise TimError(f"bad bpp {bpp}")


def build(t: Tim) -> bytes:
    if t.bpp not in BPP_TO_PMODE:
        raise TimError(f"bad bpp {t.bpp}")
    t.image.check()
    flags = BPP_TO_PMODE[t.bpp] | (FLAG_CLUT if t.clut else 0)
    if t.clut and t.bpp > 8:
        raise TimError("CLUT only valid for 4/8 bpp")
    if t.bpp <= 8 and not t.clut:
        raise TimError("4/8 bpp TIM needs a CLUT")
    out = struct.pack("<II", MAGIC, flags)
    for blk in ([t.clut] if t.clut else []) + [t.image]:
        blk.check()
        out += struct.pack("<IHHHH", 12 + len(blk.data), blk.x, blk.y, blk.w, blk.h) + blk.data
    return out


def parse(data: bytes, allow_trailing: bool = False) -> Tim:
    if len(data) < 20:
        raise TimError("file too short")
    magic, flags = struct.unpack_from("<II", data, 0)
    if magic != MAGIC:
        raise TimError(f"bad magic 0x{magic:08X}")
    if flags & ~0x0B:
        raise TimError(f"reserved flag bits set: 0x{flags:X}")
    pmode = flags & 3
    bpp = PMODE_TO_BPP[pmode]
    has_clut = bool(flags & FLAG_CLUT)
    if has_clut != (bpp <= 8):
        raise TimError("CLUT flag does not match bpp")
    pos = 8
    blocks = []
    for _ in range(2 if has_clut else 1):
        if pos + 12 > len(data):
            raise TimError("truncated block header")
        bnum, x, y, w, h = struct.unpack_from("<IHHHH", data, pos)
        if bnum != 12 + w * h * 2:
            raise TimError(f"bnum {bnum} != 12 + w*h*2 ({12 + w * h * 2})")
        if pos + bnum > len(data):
            raise TimError("truncated block data")
        blk = Block(x, y, w, h, bytes(data[pos + 12:pos + bnum]))
        blk.check()
        blocks.append(blk)
        pos += bnum
    if pos != len(data) and not allow_trailing:
        raise TimError(f"{len(data) - pos} trailing bytes")
    clut = blocks[0] if has_clut else None
    if clut and clut.w != (16 if bpp == 4 else 256):
        raise TimError(f"CLUT width {clut.w} (expected {16 if bpp == 4 else 256})")
    return Tim(bpp, blocks[-1], clut)


# --- colour and pixel helpers -------------------------------------------------

def bgr555(r: int, g: int, b: int, a: int = 255) -> int:
    """RGB888 -> 16-bit PS1 colour. Transparent -> 0x0000; opaque black -> 0x0421 (so it stays opaque)."""
    if a < 128:
        return 0
    v = (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)
    return v if v else 0x0421


def rgb_from_bgr555(v: int):
    r, g, b = v & 31, (v >> 5) & 31, (v >> 10) & 31
    return (r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2)


def pack_indices(idx, bpp: int) -> bytes:
    """Pack palette indices (row-major, width already padded) into TIM data. 4-bpp: low nibble = left pixel."""
    if bpp == 8:
        return bytes(idx)
    if bpp == 4:
        out = bytearray()
        for i in range(0, len(idx), 2):
            out.append(idx[i] | (idx[i + 1] << 4))
        return bytes(out)
    raise TimError("pack_indices: 4 or 8 only")


def unpack_indices(data: bytes, bpp: int):
    if bpp == 8:
        return list(data)
    out = []
    for b in data:
        out += [b & 15, b >> 4]
    return out


def clut_entries(t: Tim):
    return [struct.unpack_from("<H", t.clut.data, i * 2)[0] for i in range(t.clut.w * t.clut.h)]


def decode_rgba(t: Tim, clut_row: int = 0):
    """Return (width, height, [(r,g,b,a), ...]) -- for tests/previews."""
    w, h = t.pixel_width, t.height
    d = t.image.data
    px = []
    if t.bpp in (4, 8):
        pal = clut_entries(t)[clut_row * t.clut.w:(clut_row + 1) * t.clut.w]
        idx = unpack_indices(d, t.bpp)
        for i in idx[:w * h]:
            v = pal[i]
            px.append((*rgb_from_bgr555(v), 0 if v == 0 else 255))
    elif t.bpp == 16:
        for i in range(w * h):
            v = struct.unpack_from("<H", d, i * 2)[0]
            px.append((*rgb_from_bgr555(v), 0 if v == 0 else 255))
    else:
        for i in range(w * h):
            px.append((d[i * 3], d[i * 3 + 1], d[i * 3 + 2], 255))
    return w, h, px


# --- texture-page arithmetic (used by SHP/TRK loaders; see Appendix E) ---------

def tsb(x: int, y: int, bpp: int, abr: int = 0) -> int:
    """GPU texture-page word ("TSB"/tpage) for an image at VRAM (x in 16-bit units, y in lines)."""
    tp = {4: 0, 8: 1, 16: 2, 24: 2}[bpp]
    return (x // 64) | ((y // 256) << 4) | (abr << 5) | (tp << 7)


def cba(cx: int, cy: int) -> int:
    """CLUT attribute word: x/16 in bits 0-5, y in bits 6-14."""
    if cx % 16:
        raise TimError("CLUT x must be a multiple of 16")
    return (cx // 16) | (cy << 6)


def uv_origin(x: int, y: int, bpp: int):
    """(u0, v0): texel offset of the image's top-left corner inside its texture page."""
    mult = {4: 4, 8: 2, 16: 1}[bpp]
    return ((x % 64) * mult, y % 256)


def fits_in_page(x: int, y: int, w_units: int, h: int, bpp: int) -> bool:
    mult = {4: 4, 8: 2, 16: 1}[bpp]
    return (x % 64) * mult + w_units * mult <= 256 and (y % 256) + h <= 256
