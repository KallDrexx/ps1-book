#!/usr/bin/env python3
"""tpkpack.py -- pack a folder of TIM files into a .TPK texture pack (Appendix E.5 and E.6).

    python tpkpack.py FOLDER -o OUT.TPK

Contract (README 7.2):
  * every *.tim / *.TIM file directly inside FOLDER, in plain string order of the file names (Python's sorted), kept byte for byte;
  * exit status 0 on success; on any error a message on stderr, status 1, and OUT.TPK is NOT written;
  * errors: FOLDER missing or not a folder, no .tim files, more than 255 of them, a file that is not a TIM
    (does not start 10 00 00 00, size not a multiple of 4, or under 20 bytes).
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
    """The TIM files of `folder` as a list of bytes, in file-name order. Raise PackError for the cases in the contract above."""
    raise NotImplementedError("TODO: README 5.6 and 7.2")


def compress(data):
    """The LZSS stream of `data`, the format of Appendix E.5 (README 5.3 and 5.4). Any valid stream will do; a good one is smaller."""
    raise NotImplementedError("TODO: README 5.4")


def build_tpk(tims):
    """The bytes of a .TPK holding `tims` (a list of bytes objects, one per texture): header, size table, stream, padding (README 5.5)."""
    raise NotImplementedError("TODO: README 5.5")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pack a folder of TIM files into a .TPK texture pack.")
    ap.add_argument("folder")
    ap.add_argument("-o", "--output", required=True, metavar="OUT.TPK")
    a = ap.parse_args(argv)
    try:
        tims = read_tims(a.folder)
        blob = build_tpk(tims)
    except NotImplementedError as e:
        # So that the disc still builds while you work: a 4-byte placeholder the game rejects (a red screen). Delete these lines
        # once all three functions exist; a packer that is finished must fail loudly, never write a placeholder.
        print(f"tpkpack: not finished yet ({e}); writing a placeholder", file=sys.stderr)
        Path(a.output).write_bytes(b"TODO")
        return 0
    except (PackError, OSError) as e:
        print(f"tpkpack: {e}", file=sys.stderr)
        return 1
    Path(a.output).write_bytes(blob)
    raw = sum(len(t) for t in tims)
    print(f"{a.output}: {len(tims)} textures, {raw} bytes -> {len(blob)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
