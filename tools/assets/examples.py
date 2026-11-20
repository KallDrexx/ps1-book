"""Worked examples for Appendix E: tiny hand-sized files plus slices of the real generated assets.

`slices(files)` returns {name: (file, offset, length)}; `xxd(data, base)` renders the dump text
that appears verbatim in the appendix (the selftest checks that it does).
"""
import struct
import formats as F, tim, vag, lzss

LZSS_TEXT = b"ABRACADABRA ABRACADABRA"

def xxd(data: bytes, base: int = 0) -> str:
    lines = []
    for i in range(0, len(data), 16):
        c = data[i:i + 16]
        lines.append("%08x: %-47s  %s" % (base + i, " ".join("%02x" % b for b in c), "".join(chr(b) if 32 <= b < 127 else "." for b in c)))
    return "\n".join(lines)

def tiny_tim() -> bytes:
    """4-bpp, 8x2 pixels, 16-entry CLUT: black(transparent), red, green, blue + zeros; image at VRAM (320,16), CLUT at (0,480)."""
    pal = [0x0000, 0x001F, 0x03E0, 0x7C00] + [0] * 12
    clut = tim.Block(0, 480, 16, 1, struct.pack("<16H", *pal))
    idx = [0, 1, 2, 3, 3, 2, 1, 0, 1, 1, 2, 2, 3, 3, 0, 0]
    return tim.build(tim.Tim(4, tim.Block(320, 16, 2, 2, tim.pack_indices(idx, 4)), clut))

def tiny_vag() -> bytes:
    import math
    s = [round(12000 * math.sin(2 * math.pi * i / 14)) for i in range(56)]
    return vag.build(vag.encode(s), 22050, "sine")

def tiny_tpk() -> bytes:
    return F.build_tpk([tiny_tim(), tiny_tim()])

def lzss_example():
    return LZSS_TEXT, lzss.compress(LZSS_TEXT)

def lzss_trace(comp: bytes, n: int) -> str:
    """Human-readable item list for the worked example."""
    out, i, r, ring, rows = [], 0, lzss.R0, bytearray(lzss.N), []
    while len(out) < n:
        flags = comp[i]; rows.append(f"flag byte 0x{flags:02X} = {flags:08b}b (read LSB first)"); i += 1
        for b in range(8):
            if len(out) >= n: break
            if flags >> b & 1:
                c = comp[i]; i += 1; out.append(c); ring[r] = c; r = (r + 1) & 4095
                rows.append(f"  bit{b}=1 literal 0x{c:02X} '{chr(c)}'")
            else:
                b0, b1 = comp[i], comp[i + 1]; i += 2
                p, l = b0 | (b1 & 0xF0) << 4, (b1 & 15) + 3
                got = bytearray()
                for k in range(l):
                    c = ring[(p + k) & 4095]; got.append(c); out.append(c); ring[r] = c; r = (r + 1) & 4095
                rows.append(f"  bit{b}=0 ref bytes {b0:02X} {b1:02X}: pos={p} (0x{p:03X}), len={l} -> {got.decode()!r}")
    return "\n".join(rows)

def slices(files):
    """Named slices of the real generated assets: name -> (filename, offset, length)."""
    return {
        "model_head": ("MODEL.BIN", 0, 0x30),
        "model_tail": ("MODEL.BIN", len(files["MODEL.BIN"]) - 24, 24),
        "shp_head": ("SHIP.SHP", 0, 0x40),
        "shp_prims": ("SHIP.SHP", struct.unpack_from("<I", files["SHIP.SHP"], 0x28)[0], 0x20 + 0x14 + 4),
        "tpk_head": ("TRACK.TPK", 0, 0x40),
        "trk_head": ("TRACK.TRK", 0, 0x60),
        "trk_face": ("TRACK.TRK", struct.unpack_from("<I", files["TRACK.TRK"], 0x2C)[0], 24),
        "trk_section": ("TRACK.TRK", struct.unpack_from("<I", files["TRACK.TRK"], 0x30)[0], 64),
        "scene_head": ("SCENE.BIN", 0, 0x50),
        "vag_head": ("ENGINE.VAG", 0, 0x50),
    }


if __name__ == "__main__":
    # prints every dump used by the appendix:  python3 tools/assets/examples.py --print
    import tempfile, mkassets
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        files, _ = mkassets.build(Path(tmp), 1)
    print("== tiny TIM\n" + xxd(tiny_tim())); print("== tiny VAG\n" + xxd(tiny_vag())); print("== tiny TPK\n" + xxd(tiny_tpk()))
    txt, comp = lzss_example(); print("== LZSS example\n" + xxd(comp)); print("== LZSS trace\n" + lzss_trace(comp, len(txt)))
    for nm, (f, off, ln) in slices(files).items():
        print(f"== {nm} ({f} @ 0x{off:X})\n" + xxd(files[f][off:off + ln], off))
