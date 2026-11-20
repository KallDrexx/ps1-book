"""LZSS, the book's variant (Appendix E, section ".TPK"). Reference compressor + decompressor.

Okumura-style: 4096-byte ring buffer zero-filled, write cursor starts at 4078 (N-F),
flag byte per 8 items read LSB first (1 = literal byte, 0 = 2-byte reference),
reference = 12-bit absolute ring position + 4-bit (length-3), length 3..18.
There is no end marker: the decoder stops after `out_size` bytes (or at end of input
if out_size is None).
"""
N = 4096
F = 18
MIN_MATCH = 3
R0 = N - F          # 4078: initial ring write position
MAX_CHAIN = 64


class LzssError(ValueError):
    pass


def decompress(data: bytes, out_size: int | None = None) -> bytes:
    ring = bytearray(N)
    r = R0
    out = bytearray()
    i, n = 0, len(data)
    while out_size is None or len(out) < out_size:
        if i >= n:
            break
        flags = data[i]; i += 1
        for _ in range(8):
            if out_size is not None and len(out) >= out_size:
                break
            if i >= n:
                break
            if flags & 1:
                c = data[i]; i += 1
                out.append(c); ring[r] = c; r = (r + 1) & (N - 1)
            else:
                if i + 1 >= n:
                    raise LzssError("truncated reference")
                b0, b1 = data[i], data[i + 1]; i += 2
                pos = b0 | ((b1 & 0xF0) << 4)
                length = (b1 & 0x0F) + MIN_MATCH
                for k in range(length):
                    c = ring[(pos + k) & (N - 1)]
                    out.append(c); ring[r] = c; r = (r + 1) & (N - 1)
            flags >>= 1
    if out_size is not None:
        if len(out) < out_size:
            raise LzssError(f"input ended after {len(out)} of {out_size} bytes")
        if len(out) > out_size:
            raise LzssError("last match overruns out_size")
        if i != n:
            raise LzssError(f"{n - i} unused input bytes")
    return bytes(out)


def compress(data: bytes) -> bytes:
    n = len(data)
    hist = bytes(N) + bytes(data)        # virtual history: 4096 zero bytes before the data
    chains: dict[bytes, list[int]] = {}
    ins = 0                              # next hist index to insert into the chains
    out = bytearray()
    flag_pos = -1
    flag_bit = 8
    i = 0
    while i < n:
        cur = N + i
        while ins < cur:                 # insert every source position q < cur
            if ins + 3 <= len(hist):
                chains.setdefault(hist[ins:ins + 3], []).append(ins)
            ins += 1
        best_len, best_d = 0, 0
        maxlen = min(F, n - i)
        if maxlen >= MIN_MATCH:
            cand = chains.get(hist[cur:cur + 3])
            if cand:
                tried = 0
                for q in reversed(cand):
                    d = cur - q
                    if d > N - 1 or tried >= MAX_CHAIN:
                        break
                    tried += 1
                    l = 3
                    while l < maxlen and hist[q + l] == hist[cur + l]:
                        l += 1
                    if l > best_len:
                        best_len, best_d = l, d
                        if l == maxlen:
                            break
        if flag_bit == 8:
            flag_pos = len(out); out.append(0); flag_bit = 0
        if best_len >= MIN_MATCH:
            s = (R0 + i - best_d) & (N - 1)
            out += bytes((s & 0xFF, ((s >> 4) & 0xF0) | (best_len - MIN_MATCH)))
            i += best_len
        else:
            out[flag_pos] |= 1 << flag_bit
            out.append(data[i])
            i += 1
        flag_bit += 1
    return bytes(out)
