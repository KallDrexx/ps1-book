#!/usr/bin/env python3
"""wav2vag.py -- 16-bit PCM WAV -> VAG (SPU-ADPCM).

  wav2vag.py in.wav out.vag [--name NAME] [--loop] [--loop-start SAMPLE]

Mono 16-bit PCM only (stereo is mixed down). The WAV's sample rate goes in the
header; Ch 39 computes the SPU pitch from it. --loop marks the whole sample as a loop;
--loop-start SAMPLE starts the loop at that sample (rounded down to a 28-sample block).
Output is deterministic.
"""
import argparse, sys, wave, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vag


def read_wav(path):
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2 or w.getcomptype() != "NONE":
            raise SystemExit(f"{path}: need 16-bit PCM")
        ch, rate, n = w.getnchannels(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    s = struct.unpack("<%dh" % (n * ch), raw)
    if ch > 1:
        s = [sum(s[i * ch:(i + 1) * ch]) // ch for i in range(n)]
    return list(s), rate


def convert(samples, rate, name="", loop=False, loop_start=0):
    ls = (loop_start // 28) if loop else None
    return vag.build(vag.encode(samples, ls), rate, name)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wav"); ap.add_argument("vag")
    ap.add_argument("--name", default=None)
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--loop-start", type=int, default=0)
    a = ap.parse_args(argv)
    s, rate = read_wav(a.wav)
    name = a.name if a.name is not None else Path(a.wav).stem[:15]
    data = convert(s, rate, name, a.loop or a.loop_start > 0, a.loop_start)
    Path(a.vag).write_bytes(data)
    print(f"{a.vag}: {len(s)} samples @ {rate} Hz -> {len(data)} bytes" + (" (looped)" if a.loop else ""))


if __name__ == "__main__":
    main()
