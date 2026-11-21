#!/usr/bin/env python3
"""audio_ref.py -- Chapter 39's reference model and two small tools (stdlib only).

As a library (what verify/checks.py imports):
  pitch_for_speed(speed, rate, idle_mul, span_mul)   the engine pitch of README 5.5, in Python integers
  sfx_pitch(rate)                                    rate * 4096 // 44100
  lateral(section, pos), section_boost(trk, i), nearest(secs, pos), events_for(...)   the event rules of README 5.6
  replay(log)                                        a list of register-store strings -> Replay (every voice register, key-ons, key-offs, CD commands)
  spd_ram(data)                                      the SPU RAM image inside a PCSX-Redux SPU dump (README 5.9)

As a command line:
  audio_ref.py pitch [RATE]            a table of speed -> pitch for the default constants
  audio_ref.py wave FILE.VAG [WIDTH]   decode a .VAG and draw its waveform as ASCII (one column per slice of the sample)
"""
import math
import struct
import sys

SPU_RAM = 0x80000
DEFAULTS = dict(idle_mul=2048, span_mul=6400)
PITCH_MAX = 0x3FFF
FILTERS = [(0, 0), (60, 0), (115, -52), (98, -55), (122, -60)]


# ---------------------------------------------------------------- the model
def sfx_pitch(rate):
    return (rate * 4096) // 44100


def pitch_for_speed(speed, rate, idle_mul=2048, span_mul=6400):
    base = (rate * 4096) // 44100
    speed = max(0, speed)
    mul = idle_mul + (((speed >> 8) * span_mul) >> 10)
    return min((base * mul) >> 12, PITCH_MAX)


def lateral(sec, pos):
    """((dx*rx + dy*ry + dz*rz) >> 12) with each d clamped to +-32767 (Python's >> is arithmetic, like the program's)."""
    s = 0
    for i in range(3):
        d = max(-32767, min(32767, pos[i] - sec["centre"][i]))
        s += d * sec["right"][i]
    return s >> 12


def section_boost(trk, i):
    sec = trk["sections"][i]
    return any(trk["faces"][f]["flags"] & 4 for f in range(sec["first_face"], sec["first_face"] + sec["face_count"]))


def nearest(secs, pos):
    best, bi = None, -1
    for i, s in enumerate(secs):
        d = sum((pos[k] - s["centre"][k]) ** 2 for k in range(3))
        if best is None or d < best:
            best, bi = d, i
    return bi


def events_for(trk, sections, positions, start_section, start_pos):
    """Run the detector of README 5.6 over a lap: per frame a list of events ('boost' / 'thud'). `sections[k]`, `positions[k]` are the
    section and ship position the detector sees in frame k; the state starts from (start_section, start_pos) as audio_events_reset sees it."""
    secs = trk["sections"]

    def off(sec, pos):
        return abs(lateral(secs[sec], pos)) > secs[sec]["half_width"]

    prev, was_off = start_section, off(start_section, start_pos)
    out = []
    for sec, pos in zip(sections, positions):
        ev = []
        if sec < 0:
            out.append(ev)
            continue
        if sec != prev and section_boost(trk, sec):
            ev.append("boost")
        prev = sec
        o = off(sec, pos)
        if o and not was_off:
            ev.append("thud")
        was_off = o
        out.append(ev)
    return out


# ---------------------------------------------------------------- the register log
class Replay:
    """Replays "pose offset width value" stores. Voice registers, key-on / key-off events, CD controller commands."""

    def __init__(self):
        self.regs = {}                  # offset (0x1C00..0x1DFF) -> last halfword
        self.keyons = []                # dicts: pose, voice, addr (the register: byte address / 8), pitch, vol_l, vol_r, adsr1, adsr2, order
        self.keyoffs = []               # (pose, voice, order)
        self.writes = []                # (pose, offset, value) of every halfword store
        self.pitch_writes = {}          # voice -> [(pose, value)]
        self.cd = []                    # (pose, command, [params]) decoded from the CD controller's registers
        self.cd_index = 0
        self.cd_params = []
        self.cd_atv = {}                # index 2/3 writes of the volume matrix: name -> value
        self.n = 0

    def _hw(self, pose, off, v):
        self.regs[off] = v
        self.writes.append((pose, off, v))
        self.n += 1
        if 0x1C00 <= off < 0x1D80:
            vo, reg = (off - 0x1C00) >> 4, (off - 0x1C00) & 15
            if reg == 4:
                self.pitch_writes.setdefault(vo, []).append((pose, v))
        elif off in (0x1D88, 0x1D8A):
            base = 0 if off == 0x1D88 else 16
            for b in range(16):
                if v >> b & 1 and base + b < 24:
                    vo = base + b
                    r = lambda k: self.regs.get(0x1C00 + 16 * vo + k, 0)
                    self.keyons.append(dict(pose=pose, voice=vo, addr=r(6), pitch=r(4), vol_l=r(0), vol_r=r(2), adsr1=r(8), adsr2=r(10), order=self.n))
        elif off in (0x1D8C, 0x1D8E):
            base = 0 if off == 0x1D8C else 16
            for b in range(16):
                if v >> b & 1 and base + b < 24:
                    self.keyoffs.append((pose, base + b, self.n))

    def _cd(self, pose, off, v):
        reg = off - 0x1800
        if reg == 0:
            self.cd_index = v & 3
        elif self.cd_index == 0 and reg == 2:
            self.cd_params.append(v)
        elif self.cd_index == 0 and reg == 1:
            self.cd.append((pose, v, list(self.cd_params)))
            self.cd_params = []
        elif self.cd_index == 2 and reg == 2:
            self.cd_atv["l_to_l"] = v
        elif self.cd_index == 2 and reg == 3:
            self.cd_atv["l_to_r"] = v
        elif self.cd_index == 3 and reg == 1:
            self.cd_atv["r_to_r"] = v
        elif self.cd_index == 3 and reg == 2:
            self.cd_atv["r_to_l"] = v

    def feed(self, line):
        pose, off, w, v = line.split()
        pose, off, w, v = int(pose), int(off, 16), int(w), int(v, 16)
        if 0x1800 <= off < 0x1804:
            self._cd(pose, off, v)
        elif w == 4:
            self._hw(pose, off, v & 0xFFFF)
            self._hw(pose, off + 2, v >> 16)
        else:
            self._hw(pose, off, v)


def replay(log):
    r = Replay()
    for line in log:
        r.feed(line)
    return r


# ---------------------------------------------------------------- SPU RAM from a PCSX-Redux SPU dump
SPD_MAGIC = b"PSXSPUDUMPv1r1"
SPD_RAM_AT_1000 = 0x44        # file offset of SPU RAM address 0x1000 in the dumps of this PCSX-Redux build (README 5.9)
SDK_DUMMY = bytes([0, 5]) + bytes(14)   # the block SpuInit writes at 0x1000


class SpuRam:
    def __init__(self, data):
        if data[:14] != SPD_MAGIC:
            raise ValueError("not an SPU dump")
        if data[SPD_RAM_AT_1000:SPD_RAM_AT_1000 + 16] != SDK_DUMMY:
            raise ValueError("the dump's layout is not the one this verifier knows (the SDK's dummy block is not at file offset 0x44)")
        self.data = data

    def read(self, addr, n):
        """n bytes of SPU RAM at byte address `addr` (>= 0x1000)."""
        if addr < 0x1000 or addr + n > SPU_RAM:
            raise ValueError("address outside the dumped range")
        o = SPD_RAM_AT_1000 + addr - 0x1000
        return self.data[o:o + n]


def spd_ram(data):
    return SpuRam(data)


# ---------------------------------------------------------------- VAG decoding and the ASCII waveform
def decode_blocks(blocks):
    out, h1, h2 = [], 0, 0
    for b in range(len(blocks) // 16):
        blk = blocks[b * 16:b * 16 + 16]
        shift, filt = blk[0] & 15, (blk[0] >> 4) & 7
        shift = 9 if shift > 12 else shift
        f0, f1 = FILTERS[min(filt, 4)]
        for i in range(28):
            n = (blk[2 + i // 2] >> 4) if i & 1 else (blk[2 + i // 2] & 15)
            n -= 16 if n >= 8 else 0
            s = max(-32768, min(32767, ((n << 12) >> shift) + ((h1 * f0 + h2 * f1 + 32) >> 6)))
            out.append(s)
            h2, h1 = h1, s
        if blk[1] & 1:
            break
    return out


def ascii_wave(samples, width=72, height=11):
    if not samples:
        return ""
    step = max(1, len(samples) // width)
    cols = [samples[i:i + step] for i in range(0, len(samples) - step + 1, step)][:width]
    rows = [[" "] * len(cols) for _ in range(height)]
    mid = (height - 1) / 2
    for x, c in enumerate(cols):
        lo, hi = min(c), max(c)
        for v in (lo, hi):
            y = int(round(mid - v / 32768 * mid))
            rows[max(0, min(height - 1, y))][x] = "#"
        for y in range(int(round(mid - hi / 32768 * mid)), int(round(mid - lo / 32768 * mid)) + 1):
            if rows[max(0, min(height - 1, y))][x] == " ":
                rows[max(0, min(height - 1, y))][x] = "|"
    return "\n".join("".join(r) for r in rows)


def main(argv):
    if len(argv) >= 1 and argv[0] == "pitch":
        rate = int(argv[1]) if len(argv) > 1 else 22050
        print(f"rate {rate} Hz, base pitch {sfx_pitch(rate):#06x}")
        for sp in range(0, 60 * 4096 + 1, 5 * 4096):
            p = pitch_for_speed(sp, rate)
            print(f"speed {sp / 4096:5.1f}   pitch {p:#06x} ({p})   plays at {p * 44100 / 4096:8.0f} Hz")
        return 0
    if len(argv) >= 2 and argv[0] == "wave":
        d = open(argv[1], "rb").read()
        if d[:4] != b"VAGp":
            print("not a VAG file")
            return 1
        rate = struct.unpack(">I", d[16:20])[0]
        s = decode_blocks(d[48:])
        print(f"{argv[1]}: {len(s)} samples at {rate} Hz = {len(s) / rate:.3f} s")
        print(ascii_wave(s, int(argv[2]) if len(argv) > 2 else 72))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
