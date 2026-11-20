#!/usr/bin/env python3
"""vag2wav.py -- decode a VAG to a 16-bit mono WAV (verification helper).

  vag2wav.py in.vag out.wav
"""
import argparse, sys, wave, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vag


def convert(data: bytes):
    v = vag.parse(data)
    return vag.decode(v["blocks"]), v["rate"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("vag"); ap.add_argument("wav")
    a = ap.parse_args(argv)
    s, rate = convert(Path(a.vag).read_bytes())
    with wave.open(a.wav, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % len(s), *s))
    print(f"{a.wav}: {len(s)} samples @ {rate} Hz")


if __name__ == "__main__":
    main()
