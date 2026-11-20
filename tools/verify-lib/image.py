"""image.py -- screenshot and VRAM helpers with colour tolerance (stdlib only).

Screenshots arrive as binary PPM (P6, 8-bit RGB) written by redux.lua; VRAM
arrives as the raw 1024x512 16-bit (BGR555, little-endian) dump.

    img = Image.load_ppm(path)               # or ctx/result: r.screenshot("done")
    img.width, img.height
    img.pixel(x, y)                          -> (r, g, b)  0..255
    img.region_mean(x, y, w, h)              -> (r, g, b) floats
    img.fraction_matching(x, y, w, h, rgb, tol)
    colors_close(a, b, tol)                  -> bool (max per-channel diff <= tol)
    expect_pixel(img, x, y, rgb, tol=16)     -> raises CheckFailure on mismatch
    expect_region(img, x, y, w, h, rgb, tol=16, min_fraction=0.98)
    expect_solid(img, rgb, tol=8, min_fraction=0.99)
    ahash(img) / dhash(img)                  -> 64-bit perceptual hash (int)
    hamming(h1, h2)                          -> bit distance (0..64)
    vram = Vram.from_file(path)
    vram.raw(x, y)                           -> 16-bit word at VRAM (x, y)
    vram.pixel(x, y)                         -> (r, g, b) expanded from BGR555
    vram.rect(x, y, w, h)                    -> bytes (row-major, 2 bytes/px)
    bgr555(r, g, b) / rgb_from_bgr555(v)     -> conversions
Colour tolerance: because the PS1 only has 5 bits per channel, an 8-bit colour
that goes through the GPU is quantised to steps of 8. tol >= 8 is therefore the
minimum sensible value for "exact" matches; Gouraud interpolation needs ~16-24.
"""
import struct

from failure import CheckFailure


def bgr555(r, g, b):
    """8-bit RGB -> PS1 15-bit (bit15 = 0)."""
    return ((b >> 3) << 10) | ((g >> 3) << 5) | (r >> 3)


def rgb_from_bgr555(v):
    r, g, b = v & 31, (v >> 5) & 31, (v >> 10) & 31
    return ((r << 3) | (r >> 2), (g << 3) | (g >> 2), (b << 3) | (b >> 2))


def colors_close(a, b, tol=16):
    return all(abs(int(x) - int(y)) <= tol for x, y in zip(a[:3], b[:3]))


def fmt_rgb(c):
    return "(%d,%d,%d)" % tuple(int(round(v)) for v in c[:3])


class Image:
    def __init__(self, width, height, rgb):
        self.width, self.height, self.rgb = width, height, rgb  # rgb: bytes, 3/px

    @classmethod
    def load_ppm(cls, path):
        with open(path, "rb") as f:
            data = f.read()
        # header: P6 <w> <h> <max> whitespace-separated, then one whitespace byte
        pos, toks = 0, []
        while len(toks) < 4:
            while data[pos:pos + 1].isspace():
                pos += 1
            if data[pos:pos + 1] == b"#":
                while data[pos:pos + 1] != b"\n":
                    pos += 1
                continue
            start = pos
            while not data[pos:pos + 1].isspace():
                pos += 1
            toks.append(data[start:pos])
        pos += 1
        if toks[0] != b"P6":
            raise ValueError(f"{path}: not a P6 PPM")
        w, h = int(toks[1]), int(toks[2])
        return cls(w, h, data[pos:pos + w * h * 3])

    def in_bounds(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    def pixel(self, x, y):
        if not self.in_bounds(x, y):
            raise IndexError(f"pixel ({x},{y}) outside {self.width}x{self.height} screenshot")
        i = (y * self.width + x) * 3
        return (self.rgb[i], self.rgb[i + 1], self.rgb[i + 2])

    def region(self, x, y, w, h):
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + w, self.width), min(y + h, self.height)
        for yy in range(y0, y1):
            for xx in range(x0, x1):
                yield self.pixel(xx, yy)

    def region_mean(self, x, y, w, h):
        n = r = g = b = 0
        for p in self.region(x, y, w, h):
            r += p[0]; g += p[1]; b += p[2]; n += 1
        if not n:
            raise IndexError("empty region")
        return (r / n, g / n, b / n)

    def fraction_matching(self, x, y, w, h, rgb, tol=16):
        n = m = 0
        for p in self.region(x, y, w, h):
            n += 1
            m += colors_close(p, rgb, tol)
        return m / n if n else 0.0

    def count_not_matching(self, x, y, w, h, rgb, tol=16):
        return sum(1 for p in self.region(x, y, w, h) if not colors_close(p, rgb, tol))

    def grayscale(self):
        g = bytearray(self.width * self.height)
        for i in range(len(g)):
            r, gg, b = self.rgb[3 * i:3 * i + 3]
            g[i] = (299 * r + 587 * gg + 114 * b) // 1000
        return g

    def save_ppm(self, path):
        with open(path, "wb") as f:
            f.write(b"P6\n%d %d\n255\n" % (self.width, self.height))
            f.write(self.rgb)

    def save_png(self, path):
        """Needs Pillow (installed by setup.sh); handy when debugging a failure."""
        from PIL import Image as PI
        PI.frombytes("RGB", (self.width, self.height), bytes(self.rgb)).save(path)


# ---- assertions (raise CheckFailure so the harness prints expected/actual/hint)

def expect_pixel(img, x, y, rgb, tol=16, hint="", what=None):
    what = what or f"pixel ({x},{y})"
    try:
        got = img.pixel(x, y)
    except IndexError as e:
        raise CheckFailure(expected=f"{what} ~ {fmt_rgb(rgb)}", actual=str(e), hint=hint)
    if not colors_close(got, rgb, tol):
        raise CheckFailure(expected=f"{what} ~ {fmt_rgb(rgb)} (+/-{tol})", actual=fmt_rgb(got), hint=hint)


def expect_region(img, x, y, w, h, rgb, tol=16, min_fraction=0.98, hint="", what=None):
    what = what or f"region ({x},{y}) {w}x{h}"
    frac = img.fraction_matching(x, y, w, h, rgb, tol)
    if frac < min_fraction:
        mean = img.region_mean(x, y, w, h)
        raise CheckFailure(
            expected=f"{what}: >= {min_fraction:.0%} of pixels ~ {fmt_rgb(rgb)} (+/-{tol})",
            actual=f"{frac:.0%} match; mean colour {fmt_rgb(mean)}", hint=hint)


def expect_solid(img, rgb, tol=8, min_fraction=0.99, hint=""):
    expect_region(img, 0, 0, img.width, img.height, rgb, tol, min_fraction, hint, what="whole screen")


def expect_pixel_differs(img, x, y, rgb, tol=16, hint="", what=None):
    what = what or f"pixel ({x},{y})"
    got = img.pixel(x, y)
    if colors_close(got, rgb, tol):
        raise CheckFailure(expected=f"{what} NOT ~ {fmt_rgb(rgb)}", actual=fmt_rgb(got), hint=hint)


# ---- perceptual hashes (no dependencies)

def _resize_gray(gray, w, h, nw, nh):
    out = []
    for j in range(nh):
        y0, y1 = j * h // nh, max((j + 1) * h // nh, j * h // nh + 1)
        for i in range(nw):
            x0, x1 = i * w // nw, max((i + 1) * w // nw, i * w // nw + 1)
            s = n = 0
            for y in range(y0, y1):
                row = y * w
                for x in range(x0, x1):
                    s += gray[row + x]; n += 1
            out.append(s / n)
    return out


def ahash(img):
    """Average hash: 8x8 box-downsample, bit = pixel above mean."""
    px = _resize_gray(img.grayscale(), img.width, img.height, 8, 8)
    mean = sum(px) / 64
    return sum(1 << i for i, v in enumerate(px) if v > mean)


def dhash(img):
    """Difference hash: 9x8 box-downsample, bit = left pixel brighter than right."""
    px = _resize_gray(img.grayscale(), img.width, img.height, 9, 8)
    h = 0
    for j in range(8):
        for i in range(8):
            if px[j * 9 + i] > px[j * 9 + i + 1]:
                h |= 1 << (j * 8 + i)
    return h


def hamming(a, b):
    return bin(a ^ b).count("1")


def expect_similar(img, ref_hash, max_distance=6, algo=dhash, hint=""):
    d = hamming(algo(img), ref_hash)
    if d > max_distance:
        raise CheckFailure(expected=f"perceptual hash distance <= {max_distance}",
                           actual=f"distance {d}", hint=hint)


# ---- VRAM

class Vram:
    WIDTH, HEIGHT = 1024, 512

    def __init__(self, data):
        if len(data) < self.WIDTH * self.HEIGHT * 2:
            raise ValueError(f"VRAM dump is {len(data)} bytes, expected {self.WIDTH * self.HEIGHT * 2}")
        self.data = data

    @classmethod
    def from_file(cls, path):
        with open(path, "rb") as f:
            return cls(f.read())

    def raw(self, x, y):
        return struct.unpack_from("<H", self.data, (y * self.WIDTH + x) * 2)[0]

    def pixel(self, x, y):
        return rgb_from_bgr555(self.raw(x, y))

    def rect(self, x, y, w, h):
        return b"".join(self.data[((y + j) * self.WIDTH + x) * 2:((y + j) * self.WIDTH + x + w) * 2]
                        for j in range(h))

    def expect_rect(self, x, y, w, h, expected, hint=""):
        got = self.rect(x, y, w, h)
        if got != expected:
            n = next((i for i in range(min(len(got), len(expected))) if got[i] != expected[i]), None)
            where = ""
            if n is not None:
                px = n // 2
                where = f"; first difference at VRAM ({x + px % w},{y + px // w}): " \
                        f"got 0x{got[n & ~1] | got[n | 1] << 8:04X}, want 0x{expected[n & ~1] | expected[n | 1] << 8:04X}"
            raise CheckFailure(expected=f"VRAM rect ({x},{y}) {w}x{h} equals {len(expected)} expected bytes",
                               actual="differs" + where, hint=hint)
