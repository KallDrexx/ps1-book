#!/usr/bin/env python3
"""musicgen.py -- an original procedural music loop for Hoverline (stdlib only, deterministic).

  musicgen.py OUT.WAV         writes MUSIC.WAV: 16-bit stereo PCM, 44100 Hz, 24 s (CD-DA format: Red Book audio)

The tune: A minor, 120 BPM, 12 bars of 4/4 (Am F C G, three times). Four layers:
bass (a square-ish note on every eighth), an arpeggio (sixteenth notes, plucked, alternating left/right),
a soft pad (the chord, one note per bar) and drums (kick, snare, hat from a noise source).
The last 1500 sample frames fade to zero, so the CD can start the track again without a click.
The output is the same for the same code: no random module, only an LCG.
"""
import math, struct, sys, wave
from array import array
from pathlib import Path

RATE = 44100
BPM = 120
BAR_SAMPLES = RATE * 4 * 60 // BPM          # 88200 = 2 s
BARS = 12
FRAMES = BAR_SAMPLES * BARS                 # 1,058,400 sample frames = 24 s = 4,233,600 bytes of PCM
BEAT = BAR_SAMPLES // 4                     # 22050
SIXTEENTH = BEAT // 4                       # 5512 (the 4 samples lost per beat are inaudible; the grid is exact per bar)

# chords: (bass root, [arpeggio notes], [pad notes]) as MIDI note numbers
CHORDS = {
    "Am": (33, [57, 60, 64, 69], [57, 60, 64]),
    "F":  (29, [53, 57, 60, 65], [53, 57, 60]),
    "C":  (36, [55, 60, 64, 67], [55, 60, 64]),
    "G":  (31, [55, 59, 62, 67], [55, 59, 62]),
}
PROGRESSION = ["Am", "F", "C", "G"] * 3


class Lcg:
    def __init__(self, seed): self.s = seed & 0xFFFFFFFF
    def next(self):
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFF
        return (self.s >> 8) / (1 << 23) - 1.0


def hz(note): return 440.0 * 2 ** ((note - 69) / 12)


_cache = {}


def _cached(key, make):
    if key not in _cache:
        _cache[key] = make()
    return _cache[key]


def pluck(note, n):
    """A decaying two-partial tone with a short attack."""
    f = hz(note)
    def make():
        out = array("d")
        for i in range(n):
            t = i / RATE
            env = min(1.0, i / 90) * math.exp(-t * 9)
            out.append(env * (math.sin(2 * math.pi * f * t) + 0.35 * math.sin(4 * math.pi * f * t + 0.5)
                              + 0.12 * math.sin(6 * math.pi * f * t)))
        return out
    return _cached(("pluck", note, n), make)


def bass(note, n):
    f = hz(note)
    def make():
        out = array("d")
        for i in range(n):
            t = i / RATE
            env = min(1.0, i / 60) * math.exp(-t * 4.5)
            ph = (f * t) % 1.0
            sq = 1.0 if ph < 0.5 else -1.0
            out.append(env * (0.55 * sq + 0.7 * math.sin(2 * math.pi * f * t)))
        return out
    return _cached(("bass", note, n), make)


def pad(chord):
    def make():
        out = array("d")
        for i in range(BAR_SAMPLES):
            t = i / RATE
            env = min(1.0, t / 0.35) * min(1.0, (BAR_SAMPLES - i) / (RATE * 0.25))
            v = 0.0
            for note in CHORDS[chord][2]:
                f = hz(note)
                v += math.sin(2 * math.pi * f * t) + math.sin(2 * math.pi * f * 1.004 * t)   # a slightly detuned pair
            out.append(env * v / 6.0)
        return out
    return _cached(("pad", chord), make)


def kick(n=9000):
    def make():
        out = array("d")
        ph = 0.0
        for i in range(n):
            t = i / RATE
            ph += 2 * math.pi * (45 + 110 * math.exp(-t * 35)) / RATE
            out.append(math.exp(-t * 11) * math.sin(ph))
        return out
    return _cached(("kick", n), make)


def noise_hit(seed, n, decay, bright):
    def make():
        rng, out, lp = Lcg(seed), array("d"), 0.0
        for i in range(n):
            t = i / RATE
            x = rng.next()
            lp += bright * (x - lp)
            out.append(math.exp(-t * decay) * (x - lp * (1 - bright)))
        return out
    return _cached(("noise", seed, n, decay, bright), make)


def mix(L, R, buf, start, gl, gr):
    n = min(len(buf), len(L) - start)
    for i in range(n):
        v = buf[i]
        L[start + i] += v * gl
        R[start + i] += v * gr


def render():
    L, R = array("d", bytes(8 * FRAMES)), array("d", bytes(8 * FRAMES))
    snare, hat, kk = noise_hit(5, 9000, 18, 0.5), noise_hit(9, 2400, 70, 0.9), kick()
    for bar, name in enumerate(PROGRESSION):
        root, arp, _ = CHORDS[name]
        b0 = bar * BAR_SAMPLES
        mix(L, R, pad(name), b0, 0.20, 0.20)
        for e in range(8):                                     # bass: an eighth-note line (root, root, octave, root ...)
            note = root + (12 if e in (3, 6) else 0)
            mix(L, R, bass(note, BEAT // 2 + 3000), b0 + e * (BEAT // 2), 0.30, 0.30)
        pattern = (0, 1, 2, 3, 2, 1, 2, 3, 0, 1, 2, 3, 2, 1, 3, 2)
        for s in range(16):                                    # the arpeggio, panned left-right
            pan = 0.65 if s % 2 else 0.25
            mix(L, R, pluck(arp[pattern[s]] + (12 if s % 8 >= 4 else 0), 14000), b0 + s * SIXTEENTH, 0.16 * (1 - pan) * 2, 0.16 * pan * 2)
        for beat in range(4):
            if beat in (0, 2) or (bar % 4 == 3 and beat == 3):
                mix(L, R, kk, b0 + beat * BEAT, 0.55, 0.55)
            if beat in (1, 3):
                mix(L, R, snare, b0 + beat * BEAT, 0.20, 0.20)
        for e in range(8):
            mix(L, R, hat, b0 + e * (BEAT // 2), 0.07 if e % 2 == 0 else 0.11, 0.11 if e % 2 == 0 else 0.07)
    for i in range(1500):                                      # the loop seam: a short fade-out, so restarting the track does not click
        g = i / 1500
        L[FRAMES - 1 - i] *= g
        R[FRAMES - 1 - i] *= g
    peak = max(max(L), -min(L), max(R), -min(R)) or 1.0
    g = 0.85 * 32767 / peak
    out = array("h")
    for i in range(FRAMES):
        out.append(max(-32768, min(32767, int(round(L[i] * g)))))
        out.append(max(-32768, min(32767, int(round(R[i] * g)))))
    return out                                                 # interleaved L R


def pcm_bytes(samples):
    if sys.byteorder == "big":
        samples = array("h", samples); samples.byteswap()
    return samples.tobytes()


def write_wav(path, samples):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(pcm_bytes(samples))


def wav_bytes(samples):
    """The complete .WAV file (a 44-byte header and the interleaved little-endian PCM)."""
    data = pcm_bytes(samples)
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 2, RATE, RATE * 4, 4, 16)
            + b"data" + struct.pack("<I", len(data)) + data)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        raise SystemExit(__doc__)
    s = render()
    write_wav(Path(argv[0]), s)
    print(f"{argv[0]}: {len(s) // 2} frames, {len(s) * 2} bytes of PCM")


if __name__ == "__main__":
    main()
