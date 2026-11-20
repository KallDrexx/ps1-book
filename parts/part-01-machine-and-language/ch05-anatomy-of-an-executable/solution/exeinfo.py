#!/usr/bin/env python3
"""exeinfo.py -- inspect a PSX-EXE (chapter 5, reference solution).

usage: python3 exeinfo.py FILE
"""
import struct
import sys

REGIONS = {"Sony Computer Entertainment Inc. for Japan area",
           "Sony Computer Entertainment Inc. for Europe area",
           "Sony Computer Entertainment Inc. for North America area"}
REGS = ("zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 "
        "t8 t9 k0 k1 gp sp fp ra").split()
R_SH = {0x00: "sll", 0x02: "srl", 0x03: "sra"}
R_3 = {0x21: "addu", 0x23: "subu", 0x24: "and", 0x25: "or", 0x26: "xor", 0x27: "nor",
       0x2A: "slt", 0x2B: "sltu"}
I_ARITH = {0x09: "addiu", 0x0A: "slti", 0x0B: "sltiu", 0x0C: "andi", 0x0D: "ori", 0x0E: "xori"}
I_MEM = {0x20: "lb", 0x21: "lh", 0x23: "lw", 0x24: "lbu", 0x25: "lhu", 0x28: "sb", 0x29: "sh", 0x2B: "sw"}


def sx16(v):
    return v - 0x10000 if v & 0x8000 else v


def disasm(w, addr):
    if w == 0:
        return "nop"
    op, rs, rt, rd = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
    sa, fn, imm = (w >> 6) & 31, w & 63, w & 0xFFFF
    br = (addr + 4 + 4 * sx16(imm)) & 0xFFFFFFFF
    if op == 0:
        if fn in R_SH: return f"{R_SH[fn]} {REGS[rd]}, {REGS[rt]}, {sa}"
        if fn in R_3: return f"{R_3[fn]} {REGS[rd]}, {REGS[rs]}, {REGS[rt]}"
        if fn == 0x08: return f"jr {REGS[rs]}"
    elif op == 1 and rt in (0, 1):
        return f"{('bltz', 'bgez')[rt]} {REGS[rs]}, 0x{br:08X}"
    elif op in (2, 3):
        t = ((addr + 4) & 0xF0000000) | ((w & 0x3FFFFFF) << 2)
        return f"{('j', 'jal')[op - 2]} 0x{t:08X}"
    elif op in (4, 5):
        return f"{('beq', 'bne')[op - 4]} {REGS[rs]}, {REGS[rt]}, 0x{br:08X}"
    elif op in (6, 7):
        return f"{('blez', 'bgtz')[op - 6]} {REGS[rs]}, 0x{br:08X}"
    elif op in I_ARITH:
        v = sx16(imm) if op in (0x09, 0x0A, 0x0B) else f"0x{imm:X}"
        return f"{I_ARITH[op]} {REGS[rt]}, {REGS[rs]}, {v}"
    elif op == 0x0F:
        return f"lui {REGS[rt]}, 0x{imm:X}"
    elif op in I_MEM:
        return f"{I_MEM[op]} {REGS[rt]}, {sx16(imm)}({REGS[rs]})"
    return f".word 0x{w:08X}"


def invalid(cat, why):
    print(f"INVALID: {cat}")
    print(f"  {why}")
    return 1


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    data = open(argv[1], "rb").read()
    if len(data) < 0x800:
        return invalid("short", f"{len(data)} bytes; the header alone is 2048")
    if data[:8] != b"PS-X EXE":
        return invalid("magic", f"starts with {data[:8]!r}")
    pc, gp, load, size, _a, _b, _c, _d, spb, spo = struct.unpack_from("<10I", data, 0x10)
    if size % 0x800 or 0x800 + size > len(data):
        return invalid("size", f"size 0x{size:X} is not a multiple of 0x800 or exceeds the file")
    if not (0x80000000 <= load and load + size <= 0x80200000):
        return invalid("load", f"image 0x{load:08X}+0x{size:X} is outside RAM")
    if pc % 4 or not (load <= pc < load + size):
        return invalid("pc", f"pc 0x{pc:08X} is misaligned or outside the image")
    region = data[0x4C:0x800].split(b"\0")[0].decode("ascii", "replace")
    if region not in REGIONS:
        return invalid("region", f"unknown marker {region!r}")
    print("magic:  PS-X EXE")
    print(f"pc:     0x{pc:08X}")
    print(f"gp:     0x{gp:08X}")
    print(f"load:   0x{load:08X}")
    print(f"size:   0x{size:X}")
    print(f"sp:     0x{(spb + spo) & 0xFFFFFFFF:08X}")
    print(f"region: {region}")
    for i in range(16):
        w = struct.unpack_from("<I", data, 0x800 + 4 * i)[0] if 0x800 + 4 * i + 4 <= len(data) else 0
        print(f"{load + 4 * i:08X}: {w:08X}  {disasm(w, load + 4 * i)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
