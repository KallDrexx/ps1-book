#!/usr/bin/env python3
"""tpkpack.py -- pack a folder of TIM files into a .TPK texture pack (Appendix E.5 and E.6).

    python tpkpack.py FOLDER -o OUT.TPK

Reads every *.tim / *.TIM file in FOLDER (not its subfolders) in plain string order of the file names, keeps each file
byte for byte, compresses their concatenation with the book's LZSS and writes OUT.TPK. Exit status 0 on success; on any
error a message goes to stderr, the status is 1 and OUT.TPK is not written.
"""
import argparse
import struct
import sys
import zlib
from pathlib import Path

N = 4096              # ring size
F = 18                # longest match
MIN_MATCH = 3
R0 = N - F            # the ring cursor at the start: 4078
MAX_TEXTURES = 255


class PackError(Exception):
    pass


def read_tims(folder):
    """The TIM files of `folder` as a list of bytes, in file-name order. Raises PackError."""
    p = Path(folder)
    if not p.is_dir():
        raise PackError(f"{folder}: not a folder")
    names = sorted(f.name for f in p.iterdir() if f.is_file() and f.suffix.lower() == ".tim")
    if not names:
        raise PackError(f"{folder}: no .tim files")
    if len(names) > MAX_TEXTURES:
        raise PackError(f"{folder}: {len(names)} textures, at most {MAX_TEXTURES}")
    tims = []
    for name in names:
        data = (p / name).read_bytes()
        if len(data) < 20 or len(data) % 4 or data[:4] != b"\x10\x00\x00\x00":
            raise PackError(f"{name}: not a TIM file (magic 10 00 00 00, a multiple of 4 bytes, at least 20)")
        tims.append(data)
    return tims


def compress(data):
    """The LZSS stream of `data` (Appendix E.5). Greedy: the longest match, the nearest one on ties."""
    n = len(data)
    hist = bytes(N) + data            # the 4096 zero bytes the ring starts with, then the data: hist[N + i] is data[i]
    out = bytearray()
    flag_at, bit = 0, 8               # where the current flag byte is, and the next free bit in it
    i = 0
    while i < n:
        cur = N + i
        lo = cur - (N - 1)            # a match may start at most 4095 bytes back
        best, src = 0, 0
        limit = min(F, n - i)
        if limit >= MIN_MATCH:
            q = hist.rfind(hist[cur:cur + MIN_MATCH], lo, cur + MIN_MATCH - 1)
            if q >= 0:
                best, src = MIN_MATCH, q
                for length in range(limit, MIN_MATCH, -1):       # longest first; the match may run into the bytes it creates
                    q = hist.rfind(hist[cur:cur + length], lo, cur + length - 1)
                    if q >= 0:
                        best, src = length, q
                        break
        if bit == 8:
            flag_at = len(out)
            out.append(0)
            bit = 0
        if best:
            pos = (src - F) & (N - 1)                            # absolute ring position of hist[src]
            out += bytes((pos & 0xFF, ((pos >> 4) & 0xF0) | (best - MIN_MATCH)))
            i += best
        else:
            out[flag_at] |= 1 << bit
            out.append(data[i])
            i += 1
        bit += 1
    return bytes(out)


def build_tpk(tims):
    """The bytes of a .TPK holding `tims` (a list of bytes objects, one per texture)."""
    raw = b"".join(tims)
    stream = compress(raw)
    head = b"TPK1" + struct.pack("<IIII", len(tims), len(raw), len(stream), zlib.crc32(raw) & 0xFFFFFFFF)
    head += struct.pack("<%dI" % len(tims), *[len(t) for t in tims])
    blob = head + stream
    return blob + bytes(-len(blob) % 4)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pack a folder of TIM files into a .TPK texture pack.")
    ap.add_argument("folder")
    ap.add_argument("-o", "--output", required=True, metavar="OUT.TPK")
    a = ap.parse_args(argv)
    try:
        tims = read_tims(a.folder)
        blob = build_tpk(tims)
    except (PackError, OSError) as e:
        print(f"tpkpack: {e}", file=sys.stderr)
        return 1
    Path(a.output).write_bytes(blob)
    raw = sum(len(t) for t in tims)
    print(f"{a.output}: {len(tims)} textures, {raw} bytes -> {len(blob)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
