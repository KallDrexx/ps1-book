#!/usr/bin/env python3
"""sfxgen.py -- original procedural sound effects for Hoverline (stdlib only, deterministic).

  sfxgen.py OUTDIR            writes ENGINE.WAV BOOST.WAV THUD.WAV BEEP.WAV GO.WAV (16-bit mono, 22050 Hz)

ENGINE.WAV is a seamless loop (see engine()) (its length is a multiple of 28 samples and every
component has a whole number of cycles), so wav2vag.py --loop gives a click-free hum.
"""
import math, struct, sys, wave
from pathlib import Path

RATE = 22050


class Lcg:
    """Deterministic noise: no dependency on the random module's version."""
    def __init__(self, seed): self.s = seed & 0xFFFFFFFF
    def next(self):
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFF
        return (self.s >> 8) / (1 << 23) - 1.0          # [-1, 1)


def _pcm(xs, gain=0.8):
    return [max(-32768, min(32767, int(round(x * gain * 32767)))) for x in xs]


def engine():
    n = 28 * 787                                          # 22036 samples, ~1 s
    comps = [(1, 1.0), (2, 0.6), (3, 0.35), (5, 0.2), (8, 0.1)]
    base = 10                                             # fundamental = 40 cycles per loop (~40 Hz); harmonics above
    out = []
    for i in range(n):
        t = i / n
        x = sum(a * math.sin(2 * math.pi * base * 4 * k * t + 0.3 * k) for k, a in comps)
        x += 0.25 * math.sin(2 * math.pi * 3 * t)         # slow throb (3 cycles per loop)
        out.append(x / 2.3)
    return _pcm(out, 0.7)


def boost():
    rng, n = Lcg(1), int(RATE * 0.6)
    out, lp = [], 0.0
    for i in range(n):
        t = i / n
        env = math.sin(math.pi * min(1.0, t * 1.0)) ** 2 * (1 - t) ** 0.5
        a = 0.05 + 0.6 * t                                # low-pass opens as it sweeps up
        lp += a * (rng.next() - lp)
        out.append(lp * env * 2.0 + 0.2 * env * math.sin(2 * math.pi * (300 + 1500 * t * t) * (i / RATE)))
    return _pcm(out, 0.8)


def thud():
    rng, n = Lcg(7), int(RATE * 0.35)
    out = []
    for i in range(n):
        t = i / RATE
        env = math.exp(-t * 14)
        f = 90 * math.exp(-t * 6) + 40
        ph = 2 * math.pi * (f * t)
        out.append(env * (math.sin(ph) + 0.4 * rng.next() * math.exp(-t * 60)))
    return _pcm(out, 0.9)


def _tone(freq, dur, vol=0.8):
    n = int(RATE * dur)
    out = []
    for i in range(n):
        env = min(1.0, i / 120) * min(1.0, (n - i) / 400)
        out.append(env * (math.sin(2 * math.pi * freq * i / RATE) + 0.25 * math.sin(4 * math.pi * freq * i / RATE)) / 1.25)
    return _pcm(out, vol)


def beep(): return _tone(880.0, 0.25)
def go(): return _tone(1760.0, 0.6)


SOUNDS = {"ENGINE": engine, "BOOST": boost, "THUD": thud, "BEEP": beep, "GO": go}


def write_wav(path, samples, rate=RATE):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % len(samples), *samples))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        raise SystemExit(__doc__)
    out = Path(argv[0]); out.mkdir(parents=True, exist_ok=True)
    for name, fn in SOUNDS.items():
        s = fn()
        write_wav(out / f"{name}.WAV", s)
        print(f"{name}.WAV: {len(s)} samples")


if __name__ == "__main__":
    main()
