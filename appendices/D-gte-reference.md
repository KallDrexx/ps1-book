# Appendix D: GTE Reference

Reference for the Geometry Transformation Engine (coprocessor 2) as the book uses it: registers and
their formats, the commands with their cycle counts, the hazards, and every `<inline_c.h>` macro of
PSn00bSDK 0.24 with the GTE register it reads or writes. Teaching text: [Chapter 25](../parts/part-05-three-dimensions-with-the-gte/ch25-the-gte-coprocessor/README.md)
(`RTPS`, `NCLIP`, `AVSZ4`), [Chapter 26](../parts/part-05-three-dimensions-with-the-gte/ch26-multiple-objects-and-simple-motion/README.md)
(a matrix per object), [Chapter 27](../parts/part-05-three-dimensions-with-the-gte/ch27-batching-gte-work-rtpt-and-timing/README.md)
(`RTPT`, timing), [Chapter 28](../parts/part-05-three-dimensions-with-the-gte/ch28-the-camera/README.md) (camera matrices,
`VectorNormalS`).

**Sources and trust.** Register numbers, command words and macro bodies were checked against
`.toolchain/opt/psn00bsdk/include/libpsn00b/inline_c.h` and `psxgte.h`. Cycle counts, the flag-bit map and
the register quirks are psx-spx ("Geometry Transformation Engine"), not measured by the book, except where a
row says "measured". Anything marked *unverified* is from memory of psx-spx and not exercised by a verifier.
Cycle numbers measured in this book are PCSX-Redux's **interpreter** (2 cycles per CPU instruction); real
hardware differs (see D.5).

## D.1 Data registers (`mtc2`/`mfc2`/`lwc2`/`swc2`)

| # | Name | Format | Holds |
|---|---|---|---|
| 0 | `VXY0` | `s16 x` (low), `s16 y` (high) | input vertex 0, x and y |
| 1 | `VZ0` | `s16 z` | vertex 0, z (high half ignored/sign-extended on read) |
| 2, 3 | `VXY1`, `VZ1` | same | vertex 1 |
| 4, 5 | `VXY2`, `VZ2` | same | vertex 2 |
| 6 | `RGBC` | bytes `r, g, b, code` | colour (and GPU command byte) for the lighting commands |
| 7 | `OTZ` | `u16` | average depth, written by `AVSZ3`/`AVSZ4` |
| 8 | `IR0` | `s16`, 4.12 | interpolation / depth-cue factor |
| 9, 10, 11 | `IR1`, `IR2`, `IR3` | `s16` | intermediate vector, saturated; the matrix commands' input and output |
| 12, 13, 14 | `SXY0`, `SXY1`, `SXY2` | `s16 x`, `s16 y` | screen-point FIFO (oldest first) |
| 15 | `SXYP` | | write: push into the FIFO; read: same as `SXY2` |
| 16, 17, 18, 19 | `SZ0` .. `SZ3` | `u16` | depth FIFO (`SZ3` is the newest) |
| 20, 21, 22 | `RGB0`, `RGB1`, `RGB2` | bytes `r, g, b, code` | colour FIFO |
| 23 | `RES1` | | prohibited (psx-spx) |
| 24 | `MAC0` | `s32` | `NCLIP` area; `RTPS`'s depth-cue sum `DQB + DQA * (H / SZ3)`; `AVSZ` sum |
| 25, 26, 27 | `MAC1`, `MAC2`, `MAC3` | `s32` | sums before saturation into `IR1..3` |
| 28 | `IRGB` | 5-5-5 colour | write: expands into `IR1..3` (x 0x80) |
| 29 | `ORGB` | 5-5-5 colour | read: `IR1..3 / 0x80` clamped to 0..31 |
| 30 | `LZCS` | `s32` | write a value ... |
| 31 | `LZCR` | `s32` | ... read the count of its leading sign bits |

A model vertex is an `SVECTOR` (`vx, vy, vz, pad`, 8 bytes): its first word is exactly `VXY`, its second
exactly `VZ`, so a vertex loads with two `lwc2` (`gte_ldv0`). Three vertices at `+0`, `+8`, `+16` load with
`gte_ldv3c`.

**FIFOs.** `SXY0..2` and `SZ0..3` shift on every push: the newest goes into `SXY2`/`SZ3`, the older ones move
down, the oldest falls out. After `RTPS`, `SXY2`/`SZ3` hold the new point; after `RTPT` on `V0, V1, V2`,
`SXY0..2` = the three points in order and `SZ1..3` = their depths (`SZ0` keeps the old `SZ3`; verified in
Chapter 27). `IR1..3`/`MAC1..3` after `RTPT` describe only the **last** vertex.

## D.2 Control registers (`ctc2`/`cfc2`; not reachable with `lwc2`/`swc2`)

| # | Name | Format | Holds |
|---|---|---|---|
| 0 .. 4 | `R11R12`, `R13R21`, `R22R23`, `R31R32`, `R33` | `s16` x 9, 4.12 | rotation matrix `RT`, row-major, two entries per word; `R33` in the low half of word 4 |
| 5, 6, 7 | `TRX`, `TRY`, `TRZ` | `s32` | translation `TR`, in vertex units (not 4.12) |
| 8 .. 12 | `L11L12` .. `L33` | `s16` x 9, 4.12 | light matrix `LLM` |
| 13, 14, 15 | `RBK`, `GBK`, `BBK` | `s32`, 20.12 | background (ambient) colour |
| 16 .. 20 | `LR1LR2` .. `LB3` | `s16` x 9, 4.12 | light colour matrix `LCM` |
| 21, 22, 23 | `RFC`, `GFC`, `BFC` | `s32`, 28.4 | far colour (fog) |
| 24, 25 | `OFX`, `OFY` | `s32`, 16.16 | screen offset; `gte_SetGeomOffset` takes whole pixels |
| 26 | `H` | `u16` | projection distance. psx-spx notes that reading `H` back returns it sign-extended (*unverified here*) |
| 27 | `DQA` | `s16`, 8.8 | depth-cue coefficient |
| 28 | `DQB` | `s32`, 8.24 | depth-cue offset |
| 29, 30 | `ZSF3`, `ZSF4` | `s16`, 4.12 | `AVSZ3` / `AVSZ4` scale factors |
| 31 | `FLAG` | bits | error/saturation bits of the **last command** (D.4) |

`InitGeom()` enables COP2 and sets offsets 0, `H` = 320, `ZSF3` = 341, `ZSF4` = 256 (Chapter 25). It also sets `DQA` = -4194
and `DQB` = `0x1400000` (disassembly of `InitGeom`), values that saturate `IR0`, which is why `FLAG` bit 12 is often set and is harmless.

`MATRIX` (`psxgte.h`) is `int16_t m[3][3]` (offsets 0..16, 4.12) then `int32_t t[3]` (offsets 20, 24, 28; there are
two bytes of padding at 18). `SVECTOR` is `s16 vx, vy, vz, pad`; `VECTOR` is `s32 vx, vy, vz`.

## D.3 Commands

A command is the single instruction `cop2 <25-bit word>`. The word is `0x4A000000 | imm25`; the low six bits are
the command number, bit 19 is `sf` (shift results by 12), bits 17..18 select the matrix, 15..16 the vector, 13..14
the translation vector, bit 10 is `lm` (clamp `IR` to 0..32767). Bits 20..24 (the "fake" command number in Sony's
tools) are ignored by the hardware. Cycle counts are psx-spx's.

| Command | No. | Cycles | What it does | `gte_*` macro (plain / bare) |
|---|---|---|---|---|
| `RTPS` | 0x01 | 15 | rotate, translate, perspective of `V0` -> `SXY2`, `SZ3`, `IR0..3`, `MAC` | `gte_rtps` / `gte_rtps_b` |
| `RTPT` | 0x30 | 23 | the same for `V0`, `V1`, `V2` | `gte_rtpt` / `gte_rtpt_b` |
| `NCLIP` | 0x06 | 8 | `MAC0 = SX0*SY1 + SX1*SY2 + SX2*SY0 - SX0*SY2 - SX1*SY0 - SX2*SY1` | `gte_nclip` / `gte_nclip_b` |
| `AVSZ3` | 0x2D | 5 | `OTZ = ZSF3 * (SZ1 + SZ2 + SZ3) >> 12` | `gte_avsz3` / `gte_avsz3_b` |
| `AVSZ4` | 0x2E | 6 | `OTZ = ZSF4 * (SZ0 + SZ1 + SZ2 + SZ3) >> 12` | `gte_avsz4` / `gte_avsz4_b` |
| `OP` | 0x0C | 6 | cross product of the `RT` diagonal and `IR` | `gte_op0`, `gte_op12` |
| `SQR` | 0x28 | 5 | square of `IR1..3` | `gte_sqr0`, `gte_sqr12` |
| `GPF` / `GPL` | 0x3D / 0x3E | 5 | general-purpose interpolation (`IR0` times `IR`, `GPL` adds `MAC`) | `gte_gpf0/12`, `gte_gpl0/12` |
| `MVMVA` | 0x12 | 8 | multiply a chosen vector by a chosen matrix, add a chosen translation | `gte_rt*`, `gte_ll*`, `gte_lc*`, `gte_mvmva(sf, mx, v, cv, lm)` |
| `DPCS` / `DPCT` / `DCPL` | 0x10 / 0x2A / 0x29 | 8 / 17 / 8 | depth cueing; the header calls `DCPL` `gte_dpcl` | `gte_dpcs`, `gte_dpct`, `gte_dpcl` |
| `INTPL` | 0x11 | 8 | interpolate a colour toward the far colour | `gte_intpl` |
| `NCS` / `NCT` | 0x1E / 0x20 | 14 / 30 | normal colour (single / triple) | `gte_ncs`, `gte_nct` |
| `NCCS` / `NCCT` | 0x1B / 0x3F | 17 / 39 | normal colour colour | `gte_nccs`, `gte_ncct` |
| `NCDS` / `NCDT` | 0x13 / 0x16 | 19 / 44 | normal colour depth cue | `gte_ncds`, `gte_ncdt` |
| `CC` / `CDP` | 0x1C / 0x14 | 11 / 13 | colour colour / colour depth cue | `gte_cc`, `gte_cdp` |

`gte_rt`, `gte_rtv0..2`, `gte_rtir`, with `tr`/`bk` suffixes, are `MVMVA` presets (matrix `RT`, vector `V0..2`/`IR`,
translation none/`TR`/`BK`); `gte_ll*` use the light matrix, `gte_lc*` the colour matrix. The rows above with only
cycle counts in the book are the ones Chapters 25 and 27 use: `RTPS` 15, `RTPT` 23, `NCLIP` 8, `AVSZ3` 5, `AVSZ4` 6.
The lighting commands are listed for completeness: the book never uses them.

**Equations the book relies on** (`RTPS`; the header comments agree):

```
IR1..3 = MAC1..3 = (TR * 4096 + RT * V0) >> 12         SZ3 = MAC3 (clamped to 0..65535)
SX2 = (OFX + IR1 * (H / SZ3)) >> 16     SY2 = (OFY + IR2 * (H / SZ3)) >> 16     (both saturated to -1024..1023)
```

`H / SZ3` is a 16.16 ratio from a table plus one Newton-Raphson step (psx-spx "GTE Division Inaccuracy"), so it can
be off in the last bit, and it saturates at `0x1FFFF`: where `H >= 2 * SZ3` the **divide overflow** flag (bit 17) is
set and the point is clamped, not garbage. Matching a floating-point model to 1 pixel is right.

**`NCLIP` sign.** Positive `MAC0` = the three points run **clockwise on screen** (y down) = front-facing in this book.
(The SDK's own comment says negative is back-facing.) Zero is edge-on. Quads go in **Z order** `v0 v1 v2 v3`; the
test uses the first three corners.

## D.4 `FLAG` (control register 31)

Cleared at the start of **every** command, so read it (`gte_stflg`) straight after the command whose result you are
judging, and OR the flags yourself across several commands. psx-spx bit map:

| Bit | Meaning | In the summary bit 31? |
|---|---|---|
| 31 | error summary: any of bits 30..23 and 18..13 | (this bit) |
| 30, 29, 28 | `MAC1` / `MAC2` / `MAC3` overflow, positive (44-bit) | yes |
| 27, 26, 25 | `MAC1` / `MAC2` / `MAC3` overflow, negative | yes |
| 24, 23, 22 | `IR1` / `IR2` / `IR3` saturated | 24 and 23 yes; **22 no** |
| 21, 20, 19 | colour FIFO `R` / `G` / `B` saturated | no |
| 18 | `SZ3` or `OTZ` saturated | yes |
| 17 | divide overflow (`H >= 2 * SZ3`, closer than `H/2` or behind the camera) | yes |
| 16, 15 | `MAC0` overflow, positive / negative | yes |
| 14, 13 | `SX2` / `SY2` saturated (off the -1024..1023 range) | yes |
| 12 | `IR0` saturated to 0..4096 | no (normal after `InitGeom`) |

In the shipped Chapter 25 run no error bit is set, and with `cam_z` = 3000 (the cube around the camera) bits 17 and
31 are (the verifier checks both). Saturation is a result, not a trap: the GTE never raises a CPU exception. A
"CPU exception 12" in a GTE program is the **CPU's** `add` overflowing in `VectorNormalS` (Appendix F.8), not a `FLAG`
bit.

## D.5 Hazards and timing

| Rule | Detail |
|---|---|
| The CPU keeps running after a command starts | Independent instructions (ALU on CPU registers, loads/stores to RAM) overlap the GTE's latency for free, up to the command's length |
| Interlock | Reading a GTE register (`swc2`, `mfc2`, `cfc2`) or starting another command **waits** for the running command. A read of *any* GTE register waits, even an unrelated one |
| `mfc2`/`cfc2` result | Arrives in the CPU register **one instruction late**, like `lw`. `gte_stflg` has a `nop` for it |
| Writes before a command | psx-spx documents a two-instruction delay for `lwc2` and nothing certain for `mtc2`/`ctc2`. The book's rule is the safe superset: **two instructions between any `lwc2`/`mtc2`/`ctc2` and a command**. The plain macros contain two `nop`s |
| Emulator | PCSX-Redux models the stall but **not** the write delay: code with the `nop`s dropped passes in the emulator and may use stale inputs on hardware. Verifiers check the instruction stream |

Measured in PCSX-Redux's interpreter (Chapter 27): the 15-cycle `RTPS` hides about 7 ALU instructions (flat cost,
then 2 cycles per extra instruction); an `mfc2` before the filler makes all of it cost. On hardware an ALU instruction
from the instruction cache is about 1 cycle and a RAM load several, so the window holds more ALU work and fewer
loads; the numbers are the emulator's. Cycles count only under `-interpreter`; the dynarec's counts mean nothing for
code this short (Appendix F.10). Measure with root counter 0 (`0x1F801100`, mode `0x1F801104`, mode 0 counts CPU
cycles, wraps at 65536) and take a median of frames: interrupts land in measurements.

## D.6 `<inline_c.h>` macros and the GTE registers they touch

Include `<inline_c.h>` after `<psxgte.h>`. Every macro is `__asm__ volatile`. **Pointer vs. value:** the macros are
not uniform (`gte_ldv0(&v)` takes a pointer; `gte_ldsxy3(a, b, c)` takes three 32-bit values; `gte_ldsxy3c(p)` takes a
pointer). **Memory:** the `gte_ld*` (load) macros declare no `"memory"` input, so the compiler may not have finished
stores to what they read (Appendix F.8); the `gte_st*` (store) macros do declare `"memory"`.

Loads (CPU memory or register -> GTE):

| Macro | Reads from | Writes (GTE) |
|---|---|---|
| `gte_ldv0(&sv)`, `ldv1`, `ldv2` | `SVECTOR` (8 bytes) | `VXY0/VZ0` (data 0, 1), `VXY1/VZ1` (2, 3), `VXY2/VZ2` (4, 5) |
| `gte_ldv3(&a, &b, &c)` | three `SVECTOR` pointers | `V0`, `V1`, `V2` |
| `gte_ldv3c(p)` | six consecutive words (three `SVECTOR`s, 8-byte stride) | `V0..V2` |
| `gte_ldv3c_vertc(p)` | words at 0, 4, 12, 16, 24, 28 (12-byte stride) | `V0..V2` |
| `gte_ldv01(&a, &b)`, `gte_ldv01c(p)` | two vertices | `V0`, `V1` |
| `gte_ldrgb(&cv)`, `ldrgb3`, `ldrgb3c` | `CVECTOR`(s) | `RGBC` (6), colour FIFO |
| `gte_ldsxy0/1/2(v)`, `gte_ldsxy3(a, b, c)` | **CPU values** (packed x, y words) | `SXY0..2` (12..14) via `mtc2` |
| `gte_ldsxy3c(p)` | three consecutive words (pointer) | `SXY0..2` via `lwc2` |
| `gte_ldsz3(a, b, c)` | values | `SZ1..SZ3` (17..19) |
| `gte_ldsz4(a, b, c, d)` | values | `SZ0..SZ3` (16..19) |
| `gte_ldlv0`, `ldsv`, `ldbv`, `ldcv`, `ldclmv`, `ldopv1/2`, `lddp`, `ldlzc`, `ld_intpol_*` | various | `IR`, `IR0`, `LZCS` ... (see the header comments) |

Control-register setters:

| Macro | Argument | Writes | Notes |
|---|---|---|---|
| `gte_SetGeomOffset(x, y)` | whole pixels | `OFX`, `OFY` (24, 25) = value << 16 | declares `$t0`, `$t1` correctly |
| `gte_SetGeomScreen(h)` | integer | `H` (26) | |
| `gte_SetRotMatrix(&m)` | `MATRIX` | `RT` (0..4) from offsets 0..16 | **clobber defect** (Appendix F.7) |
| `gte_SetTransMatrix(&m)` | `MATRIX` | `TR` (5..7) from offsets 20..28 | **clobber defect** |
| `gte_SetLightMatrix(&m)` | `MATRIX` | `LLM` (8..12) | **clobber defect** |
| `gte_SetColorMatrix(&m)` | `MATRIX` | `LCM` (16..20) | **clobber defect** |
| `gte_SetBackColor(r, g, b)` | 8-bit | `RBK..BBK` (13..15) = value << 4 | declares `$t0..$t2` |
| `gte_SetFarColor(r, g, b)` | 8-bit | `RFC..BFC` (21..23) = value << 4 | declares `$12..$14` |
| `gte_ldtr(x, y, z)` | values | `TR` (5..7) | no temporaries |
| `gte_SetTransVector(&v)` | `VECTOR` | `TR` | declares `$12..$14` |
| `gte_ldbkdir`, `ldfcdir`, `gte_SetRGBcd` | values | `BK`, `FC`, `RGBC` | |
| `gte_ldsvrtrow0`, `ldsvllrow0`, `ldsvlcrow0` | row of a matrix | first row of `RT` / `LLM` / `LCM` | for building a matrix a row at a time |

Stores (GTE -> memory):

| Macro | Reads (GTE) | Writes |
|---|---|---|
| `gte_stsxy(&w)` | `SXY2` (14) | one word: x low, y high |
| `gte_stsxy3(&a, &b, &c)` | `SXY0..SXY2` | three pointers |
| `gte_stsxy3c(p)` | `SXY0..SXY2` | three consecutive words (writes `p[0..2]`; mind the third word) |
| `gte_stsxy0/1/2`, `stsxy01`, `stsxy01c` | single / pairs of FIFO entries | |
| `gte_stsxy3_f3/g3/ft3/gt3/f4/g4/ft4/gt4(prim)` | `SXY0..SXY2` | straight into the first three vertex fields (`xy0`, `xy1`, `xy2`) of the primitive pointed to; the 4-vertex variants store the same three, the fourth is set separately |
| `gte_stsz(&z)` | `SZ3` (19) | one word |
| `gte_stsz3(&a, &b, &c)`, `gte_stsz3c(p)` | `SZ1..SZ3` | |
| `gte_stsz4(...)`, `gte_stsz4c(p)` | `SZ0..SZ3` | |
| `gte_stszotz(&v)` | `SZ3` | `SZ3 >> 2` (the "otz" Sony's `RotTransPers` returned) |
| `gte_stotz(&v)` | `OTZ` (7) | |
| `gte_stopz(&v)` | `MAC0` (24) | `NCLIP`'s result |
| `gte_stdp(&v)` | `IR0` (8) | |
| `gte_stflg(&v)` | `FLAG` (ctrl 31) via `cfc2`, `nop` | declares `$12` |
| `gte_stflg_4(&v)` | `FLAG` & 0x40000 (bit 18) | |
| `gte_stlvl`, `stlvnl`, `stlvnl0/1/2`, `stsv`, `stbv`, `stcv`, `stclmv`, `strgb`, `strgb3*`, `stlzc`, `stfc` | `IR`, `MAC`, `RGB` FIFO, `LZCR`, `FC` | see the header comments |
| `gte_sttr(&v)`, `gte_ReadRotMatrix(&m)`, `ReadLightMatrix`, `ReadColorMatrix`, `ReadGeomOffset(&x, &y)`, `ReadGeomScreen(&h)` | `TR`, `RT`, `LLM`, `LCM`, `OFX/OFY`, `H` | read-backs |
| `gte_mvlvtr()`, `gte_FlipRotMatrixX()`, `gte_FlipTRX()`, `gte_subdvl/subdvd/adddvl/adddvd` | | helpers; see the header |

Commands (each: `nop; nop; cop2 <word>`): see D.3. **Bare variants:** 67 `gte_*_b()` macros (`gte_rtps_b`,
`gte_rtpt_b`, `gte_nclip_b`, `gte_avsz3_b`, `gte_avsz4_b`, `gte_mvmva_b(sf, mx, v, cv, lm)`, the `rt*`, `ll*`, `lc*`
families, the lighting and `op`/`gpf`/`gpl`/`sqr` commands) expand to the `cop2` word alone, with no `nop`s. The
caller must place two non-GTE instructions between the last register write and the command; the macro does not pin
the neighbouring C code, so check the disassembly (`mipsel-none-elf-objdump -d -z`). Writing
`__asm__ volatile("cop2 0x0280030")` is equivalent to `gte_rtpt_b()`. (`gte_avsz4`'s header comment numbers the
registers `SZ1..SZ4`; the macros load and store data registers 16..19, which are `SZ0..SZ3`.)

**Batching** (Chapter 27): `gte_ldv3c(&cube[i]); gte_rtpt(); gte_stsxy3c(&xy[i]); gte_stsz3c(&sz[i]);` transforms three
vertices for 23 GTE cycles instead of 45. Eight corners do not divide by three: pad the last batch with a duplicate
vertex and never store the padded result into a slot that does not exist.

**Library functions** (`psxgte.h`, linked from `libpsxgte`): `InitGeom`, `RotMatrix(&sv, &m)` (rotates about Z, then Y,
then X: `Rx * Ry * Rz`; angles 4096 per turn as used throughout the book), `HiRotMatrix`, `TransMatrix(&m, &v)`,
`ScaleMatrix`, `ScaleMatrixL`, `MulMatrix`, `MulMatrix0`, `CompMatrixLV`, `ApplyMatrixLV`, `PushMatrix`/`PopMatrix`
(a single slot), `VectorNormalS`, `Square0`, `SquareRoot0`, `SquareRoot12`, `isin`/`icos`, `hisin`/`hicos`. **Angle units:** `isin`/`icos`
take **4096 per turn** (`isin(1024)` = 4096, `isin(2048)` = 0; only the low 12 bits count) and `hisin`/`hicos` take
**131072** per turn. The `psxgte.h` comments say 131072 and 4194304: they are wrong, as the disassembly of
`isin.c.obj` in `libpsxgte` shows (the sign comes from bit 11 of the angle; [Chapter 23](../parts/part-05-three-dimensions-with-the-gte/ch23-fixed-point-math/README.md) and its verifier). All the names above were found in `libpsxgte_exe_gprel.a` with `nm`. The old
per-vertex wrappers are not there: see Appendix G.
