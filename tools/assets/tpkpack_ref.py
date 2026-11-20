#!/usr/bin/env python3
"""tpkpack_ref.py -- REFERENCE .TPK packer/unpacker/verifier (Appendix E, ".TPK").

The reader writes their own `tpkpack.py` in Chapter 31; this one is the oracle the
verify scripts compare against.

  tpkpack_ref.py pack   OUT.TPK a.tim b.tim ...      (or a directory: *.tim/*.TIM in name order)
  tpkpack_ref.py unpack IN.TPK OUTDIR                writes 00.tim, 01.tim, ...
  tpkpack_ref.py verify IN.TPK                       parse, decompress, check CRC32 and each TIM
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import formats as F, tim as T


def collect(args):
    files = []
    for a in args:
        p = Path(a)
        files += sorted(f for f in p.iterdir() if f.suffix.lower() == ".tim") if p.is_dir() else [p]
    return files


def pack(files) -> bytes:
    tims = [f.read_bytes() for f in files]
    for f, t in zip(files, tims):
        T.parse(t)                                  # must be valid
    return F.build_tpk(tims)


def verify(data: bytes):
    d = F.parse_tpk(data)
    for t in d["tims"]:
        T.parse(t)
    return d


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("pack", "unpack", "verify")); ap.add_argument("args", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "pack":
        files = collect(a.args[1:])
        data = pack(files); Path(a.args[0]).write_bytes(data)
        print(f"{a.args[0]}: {len(files)} textures, {len(data)} bytes")
    elif a.cmd == "unpack":
        d = verify(Path(a.args[0]).read_bytes()); out = Path(a.args[1]); out.mkdir(parents=True, exist_ok=True)
        for i, t in enumerate(d["tims"]): (out / f"{i:02d}.tim").write_bytes(t)
        print(f"{len(d['tims'])} TIMs -> {out}")
    else:
        d = verify(Path(a.args[0]).read_bytes())
        print(f"OK: {d['count']} textures, raw {d['raw_size']} -> {d['comp_size']} compressed, crc32 {d['crc32']:08X}")


if __name__ == "__main__":
    main()
