#!/usr/bin/env python3
"""Chapter 32 worked example (host only): walk a .SHP exactly as the C parser must, printing the header and every record.
   python shpdump.py [FILE.SHP]      (no argument: the shipped ship, made by tools/assets/shpgen.py)
Only `struct` is used for parsing: no reference library, so every offset below is the one Appendix E.8 gives."""
import os
import struct
import sys
from pathlib import Path

root = os.environ.get("PS1BOOK_ROOT") or str(Path(__file__).resolve().parents[4])
TYPES = ["F3", "F4", "G3", "G4", "FT3", "FT4", "GT3", "GT4"]
SIZES = [16, 20, 24, 32, 24, 32, 32, 44]

if len(sys.argv) > 1:
    data = Path(sys.argv[1]).read_bytes()
else:
    sys.path.insert(0, str(Path(root) / "tools" / "assets"))
    import shpgen
    data = shpgen.make_ship().build()

assert data[:4] == b"SHP1", "not a .SHP"
size, name = struct.unpack_from("<I16s", data, 4)
nv, nn, npr, ntex = struct.unpack_from("<4H", data, 0x18)
voff, noff, poff, psize = struct.unpack_from("<4I", data, 0x20)
print(f"{name.rstrip(bytes(1)).decode()}: {size} bytes, {nv} vertices, {nn} normals, {npr} primitives, {ntex} textures")
print(f"vertices at 0x{voff:X}, normals at 0x{noff:X}, primitives at 0x{poff:X} ({psize} bytes)")
assert noff == voff + 8 * nv and poff == noff + 8 * nn and poff + psize == len(data) == size

pos, counts = poff, dict.fromkeys(TYPES, 0)
for i in range(npr):
    t, flags, rsize = struct.unpack_from("<BBH", data, pos)      # the 4-byte prefix of every record
    assert t < 8 and rsize == SIZES[t], f"record {i}: bad tag {t} or size {rsize}"
    nverts = 3 if TYPES[t].endswith("3") else 4
    v = struct.unpack_from(f"<{nverts}H", data, pos + 4)
    print(f"#{i:<3} +0x{pos:04X}  {TYPES[t]:<3} size {rsize:<2} flags {flags}  vertices {v}")
    counts[TYPES[t]] += 1
    pos += rsize                                                  # THE walk: advance by the record's own size
assert pos == len(data), "bytes left over"
print("counts:", counts)
