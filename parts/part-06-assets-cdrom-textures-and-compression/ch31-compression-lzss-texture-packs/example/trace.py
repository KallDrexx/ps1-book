#!/usr/bin/env python3
"""Chapter 31 worked example (host only): compress a string with the book's reference LZSS and decode it again, printing every
flag byte and item with the ring cursor.   python trace.py "ABRACADABRA ABRACADABRA"
"""
import os
import sys
from pathlib import Path

root = os.environ.get("PS1BOOK_ROOT") or str(Path(__file__).resolve().parents[4])
sys.path.insert(0, str(Path(root) / "tools" / "assets"))
import lzss  # noqa: E402

text = (sys.argv[1] if len(sys.argv) > 1 else "ABRACADABRA ABRACADABRA").encode()
stream = lzss.compress(text)
print(f"{len(text)} bytes -> {len(stream)} bytes: {stream.hex(' ')}")

ring = bytearray(4096)
r, i, out = 4078, 0, bytearray()
while len(out) < len(text):
    flags = stream[i]
    i += 1
    print(f"flag {flags:02x} = {flags:08b}b (read from the right)")
    for bit in range(8):
        if len(out) >= len(text):
            break
        if flags >> bit & 1:
            c = stream[i]
            i += 1
            print(f"  bit{bit}=1 literal {c:02x} {chr(c)!r:5} -> ring[{r}]")
            out.append(c)
            ring[r] = c
            r = (r + 1) & 4095
        else:
            b0, b1 = stream[i], stream[i + 1]
            i += 2
            pos, length = b0 | (b1 & 0xF0) << 4, (b1 & 15) + 3
            print(f"  bit{bit}=0 ref {b0:02x} {b1:02x}: pos={pos} (0x{pos:03X}) len={length} (cursor {r})")
            for k in range(length):
                c = ring[(pos + k) & 4095]
                out.append(c)
                ring[r] = c
                r = (r + 1) & 4095
            print(f"      -> {bytes(out[-length:])!r}")
print("decoded:", bytes(out) == text)
