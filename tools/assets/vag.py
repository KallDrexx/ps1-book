"""VAG (SPU-ADPCM) encoder/decoder and file wrapper (Appendix E, section "VAG")."""
import struct

FILTERS = [(0, 0), (60, 0), (115, -52), (98, -55), (122, -60)]   # (f0, f1) in 1/64 units
SAMPLES_PER_BLOCK = 28
HEADER_SIZE = 48
FLAG_END, FLAG_REPEAT, FLAG_START = 1, 2, 4


class VagError(ValueError):
    pass


def _clamp16(v):
    return -32768 if v < -32768 else 32767 if v > 32767 else v


def decode_block(block: bytes, h1: int, h2: int):
    """Decode one 16-byte block -> (28 samples, h1, h2)."""
    shift, filt = block[0] & 15, block[0] >> 4
    if filt > 4:
        raise VagError(f"filter {filt} not valid")
    if shift > 12:
        shift = 9                      # what the hardware does
    f0, f1 = FILTERS[filt]
    out = []
    for i in range(SAMPLES_PER_BLOCK):
        b = block[2 + i // 2]
        n = (b >> 4) if (i & 1) else (b & 15)
        if n >= 8:
            n -= 16
        s = _clamp16(((n << 12) >> shift) + ((h1 * f0 + h2 * f1 + 32) >> 6))
        out.append(s)
        h2, h1 = h1, s
    return out, h1, h2


def _encode_block(chunk, h1, h2, force_filter0=False):
    best = None
    for filt in ([0] if force_filter0 else range(5)):
        f0, f1 = FILTERS[filt]
        for shift in range(13):
            a, b, err, nibs = h1, h2, 0, []
            for s in chunk:
                pred = (a * f0 + b * f1 + 32) >> 6
                n = round((s - pred) * (1 << shift) / 4096)
                n = -8 if n < -8 else 7 if n > 7 else n
                rec = _clamp16(((n << 12) >> shift) + pred)
                err += (s - rec) ** 2
                nibs.append(n & 15)
                b, a = a, rec
            if best is None or err < best[0]:
                best = (err, filt, shift, nibs, a, b)
    _, filt, shift, nibs, a, b = best
    body = bytes(nibs[i] | (nibs[i + 1] << 4) for i in range(0, 28, 2))
    return bytes((shift | (filt << 4), 0)) + body, a, b


def encode(samples, loop_start_block: int | None = None) -> bytes:
    """Encode 16-bit mono samples to SPU-ADPCM blocks (no file header).

    Layout: one silent block, the audio blocks (zero-padded to a multiple of 28
    samples), then either an end block (no loop) or loop flags on the last block.
    loop_start_block counts audio blocks (0 = loop the whole sample).
    """
    samples = list(samples)
    if not samples:
        raise VagError("no samples")
    while len(samples) % SAMPLES_PER_BLOCK:
        samples.append(0)
    nblocks = len(samples) // SAMPLES_PER_BLOCK
    out = bytearray(16)                                  # leading silent block, flags 0
    h1 = h2 = 0
    for bi in range(nblocks):
        chunk = samples[bi * 28:bi * 28 + 28]
        blk, h1, h2 = _encode_block(chunk, h1, h2, force_filter0=(bi == 0 or bi == loop_start_block))
        flags = 0
        if loop_start_block is not None:
            if bi == loop_start_block:
                flags |= FLAG_START
            if bi == nblocks - 1:
                flags |= FLAG_END | FLAG_REPEAT
        b = bytearray(blk); b[1] = flags
        out += b
    if loop_start_block is None:
        out += bytes((0, FLAG_END)) + bytes(14)          # end block
    return bytes(out)


def decode(blocks: bytes):
    """Decode a block stream -> list of samples, dropping the leading silent block and an end block."""
    if len(blocks) % 16:
        raise VagError("data size not a multiple of 16")
    out, h1, h2 = [], 0, 0
    nb = len(blocks) // 16
    for bi in range(nb):
        blk = blocks[bi * 16:bi * 16 + 16]
        flags = blk[1]
        if bi == 0 and not any(blk):
            continue
        if bi == nb - 1 and flags == FLAG_END and not any(blk[2:]) and blk[0] == 0:
            break
        s, h1, h2 = decode_block(blk, h1, h2)
        out += s
        if flags & FLAG_END:
            break
    return out


def build(blocks: bytes, rate: int, name: str = "") -> bytes:
    nm = name.encode("ascii", "replace")[:15]
    hdr = b"VAGp" + struct.pack(">IIII", 0x20, 0, len(blocks), rate) + bytes(12) + nm.ljust(16, b"\0")
    assert len(hdr) == HEADER_SIZE
    return hdr + blocks


def parse(data: bytes):
    """Return dict(version, size, rate, name, blocks, loop (bool), loop_start_block or None)."""
    if len(data) < HEADER_SIZE or data[:4] != b"VAGp":
        raise VagError("bad magic")
    version, _res, size, rate = struct.unpack_from(">IIII", data, 4)
    name = data[32:48].split(b"\0")[0].decode("ascii", "replace")
    blocks = data[HEADER_SIZE:]
    if size != len(blocks):
        raise VagError(f"size field {size} != {len(blocks)} data bytes")
    if size % 16 or size < 32:
        raise VagError("bad data size")
    loop_start = None
    for bi in range(size // 16):
        if blocks[bi * 16 + 1] & FLAG_START:
            loop_start = bi - 1               # relative to first audio block
            break
    last = blocks[-15]
    return dict(version=version, size=size, rate=rate, name=name, blocks=blocks,
                loop=bool(last & FLAG_REPEAT), loop_start_block=loop_start)
