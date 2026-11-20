# Chapter 9: Signed Numbers, Logic, and Bit Shifting

## 1. Concept

A register is just 32 bits. Whether they mean `-1` or `4294967295`, a colour or a mask, depends on which instruction reads them. Two's complement, sign extension, masks and shifts are how low-level code packs, unpacks and reinterprets bits.

## 2. Why it matters

The PS1 is made of packed bit fields. Pixels are 15-bit colours. GPU commands carry a colour in the low 24 bits and a command number in the top 8. Vertices are signed 16-bit halves. Pad state is one bit per button. The GTE works in signed fixed-point numbers. Every one of these is a mask, a shift, or a sign extension.

## 3. Learning objectives

After this chapter you can:

- negate a number and read a bit pattern as signed or unsigned;
- choose between `lb`/`lbu` and `lh`/`lhu`, and say what each puts in the upper bits;
- build and test bit fields with `and`, `or`, `xor`, `nor` and their immediate forms;
- pick the right shift (`sll`, `srl`, `sra`) and explain why `sra` is not a division;
- pack an RGB888 colour into the PS1's BGR555 format and unpack it again;
- reverse the bytes of a word.

## 4. Prerequisites

[Chapter 2](../../part-01-machine-and-language/ch02-memory-map-and-endianness/README.md) (bytes, endianness), [Chapter 3](../../part-01-machine-and-language/ch03-registers-loads-stores-arithmetic/README.md) (loads and stores), and [Chapter 8](../ch08-subroutines/README.md) (you write six subroutines under the same rules: arguments in `$a0`-`$a1`, results in `$v0`-`$v1`, leave the `$s` registers alone).

## 5. Explanation

### 5.1 Two's complement

An n-bit register has 2^n patterns. Two's complement reads the top bit as worth **-2^(n-1)** instead of +2^(n-1). In 32 bits:

```
 unsigned:   0 ............................................. 4294967295
 pattern:    0x00000000 ........ 0x7FFFFFFF | 0x80000000 ........ 0xFFFFFFFF
 signed:     0 ........ +2147483647         | -2147483648 ........ -1

              0x00000000  (0)
            .-'          `-.
   0xC0000000              0x40000000
     (-2^30)  |            |  (+2^30)
            `-.          .-'
      0x80000000  <-->  0x7FFFFFFF
   (-2^31, most negative)  (+2^31-1, most positive)

 Adding 1 at 0x7FFFFFFF steps across the seam to 0x80000000.
```

Facts to keep:

- **Negate = invert all bits, add 1.** `-x = ~x + 1`. `0 - x` gives the same answer, which is why the CPU needs no separate negate instruction (write `subu rd, $zero, rs`).
- **`addu`/`subu` do not know about signs.** The same instruction adds signed and unsigned numbers. Signedness only matters where an instruction must choose: comparisons (`slt` vs `sltu`), right shifts (`sra` vs `srl`) and narrow loads (`lb` vs `lbu`).
- **The range is lopsided.** 32 bits hold -2147483648 to +2147483647. The most negative value has no positive twin: negating `0x80000000` gives `0x80000000` again. Remember this for `abs`.

### 5.2 Sign extension

Moving a narrow signed value into a wider register means copying its top bit upward, so the value stays the same:

```
 8-bit  0xF0 = -16:             1111 0000
 widened, copy bit 7 upward:    1111 1111 1111 1111 1111 1111 1111 0000   = 0xFFFFFFF0 = -16
 widened, zeros (zero-extend):  0000 0000 0000 0000 0000 0000 1111 0000   = 0x000000F0 = 240
```

Loads choose for you:

| Instruction | Reads | Upper bits |
|---|---|---|
| `lb` | 1 byte | **sign**-extended |
| `lbu` | 1 byte | zero |
| `lh` | 2 bytes (aligned) | **sign**-extended |
| `lhu` | 2 bytes (aligned) | zero |
| `lw` | 4 bytes (aligned) | none needed |

There is no `lwu` on the 32-bit R3000. Stores (`sb`, `sh`) simply write the low bits; there is nothing to extend. Use `lbu`/`lhu` for pixels, flags and unsigned counters; `lb`/`lh` for signed vertex and fixed-point values.

Immediates matter too:

| Instruction | 16-bit immediate becomes |
|---|---|
| `addiu`, `slti`, `sltiu`, and the load/store offsets | **sign**-extended (`addiu $t, $zero, -1` gives `0xFFFFFFFF`) |
| `andi`, `ori`, `xori` | **zero**-extended (`ori $t, $zero, 0xFFFF` gives `0x0000FFFF`, not `-1`) |

The logic instructions treat their immediate as a bit mask, so it must not grow a sign. This is why `li $t, 0xFFFF` and `li $t, -1` assemble to different instructions.

### 5.3 Logic

| Instruction | Does |
|---|---|
| `and rd, rs, rt` / `andi rt, rs, imm` | bit is 1 only if both are 1 |
| `or` / `ori` | 1 if either is 1 |
| `xor` / `xori` | 1 if they differ |
| `nor rd, rs, rt` | `~(rs \| rt)`; `nor rd, rs, $zero` is NOT |

The four jobs of a mask `m`:

| Goal | Operation |
|---|---|
| keep some bits (extract) | `x & m` |
| force bits to 1 (set) | `x \| m` |
| force bits to 0 (clear) | `x & ~m` |
| flip bits (toggle) | `x ^ m` |

There is no NOT instruction and no `andn`; `nor` with `$zero` supplies NOT.

### 5.4 Shifts

| Instruction | Shifts | Fills with | Amount |
|---|---|---|---|
| `sll rd, rt, n` | left | zeros | constant 0 to 31 |
| `srl rd, rt, n` | right, **logical** | zeros | constant |
| `sra rd, rt, n` | right, **arithmetic** | copies of the sign bit | constant |
| `sllv`, `srlv`, `srav rd, rt, rs` | same | same | register `rs`, **low 5 bits only** |

Note the operand order of the variable forms: value in `rt`, amount in `rs`. Only the low 5 bits of the amount count: a variable shift by 33 shifts by 1, and one by 32 does nothing (it does **not** clear the register).

```
 sra by 3 of 0xFFFFFC85:     1111 1111 1111 1111 1111 1100 1000 0101
                          -> 1111 1111 1111 1111 1111 1111 1001 0000   (sign copied in at the top)
 srl by 3 of the same:       0001 1111 1111 1111 1111 1111 1001 0000   (zeros in: now a big positive number)
```

A left shift by n multiplies by 2^n (modulo 2^32), signed or unsigned. A right shift divides by 2^n only with the right flavour: `srl` for unsigned, `sra` for signed. **The rounding trap:** `sra` rounds toward negative infinity, but C-style division (and most people's expectation) rounds toward zero.

| x | x >> 1 (`sra`) | x / 2 (toward zero) |
|---|---|---|
| 7 | 3 | 3 |
| -7 | **-4** | **-3** |

To divide a signed number by 2^n toward zero, add `2^n - 1` first when it is negative, then shift. You can build that bias from the sign: `sra x, 31` is all ones for a negative x, and masking it with `2^n - 1` gives the bias.

### 5.5 Fields: the shift-and-mask idiom

Extract a field `width` bits wide at bit `pos`: shift right by `pos`, then `and` with `(1 << width) - 1`. Insert: clear the field, `or` the shifted value. Sign-extend a field: shift it to the **top** of the register, then arithmetic-shift it back down. The second shift does the copying:

```
 5-bit field 11101 in the low bits of a word, with junk above:      ....1 1101
 sll by 27 (= 32 - 5): the field now owns bits 31..27               1110 1000 0000 ... 0000
 sra by 27:            sign copied down                              1111 1111 ... 1111 1101  = -3
```

### 5.6 The PS1's 15-bit colour

VRAM pixels and many GPU colour fields use BGR555. Per psx-spx, a 16-bit pixel is

```
 bit  15  14 13 12 11 10   9  8  7  6  5   4  3  2  1  0
     [ M ][  B  B  B  B  B ][ G  G  G  G  G ][ R  R  R  R  R ]
```

`M` (bit 15) is the mask / semi-transparency flag. 5 bits per channel, **red in the lowest bits**: the opposite order to the 0x00RRGGBB you usually write colours in.

Converting from 8 bits per channel throws away the low 3 bits of each channel:

```
 0x00RRGGBB    bits 23..16   15..8    7..0
                  RRRRRrrr   GGGGGggg BBBBBbbb        (lowercase = discarded)
 BGR555        bit  14..10      9..5      4..0
                  BBBBB        GGGGG      RRRRR
```

Going back, the low 5 bits need filling. Shifting left by 3 leaves the low 3 bits zero, so full white (31) becomes 248, not 255. This book's `bgr555_unpack` **replicates the top bits**: `c8 = (c5 << 3) | (c5 >> 2)`, which maps 0 to 0 and 31 to 255 exactly.

### 5.7 Endianness swap

The R3000 in the PS1 is little-endian (Chapter 2). Data from big-endian formats or tools arrives with its bytes reversed. `swap_endian32` reverses the four bytes of a word: `0x11223344` becomes `0x44332211`. Each byte moves by a shift; masks keep only the byte you want from each shifted copy.

## 6. Worked example

[`example/main.s`](example/main.s) (`make` in `example/`) stores thirteen results; its header lists them. Run it, then read `results` in the debugger (Chapter 6).

| `results[i]` | Shows | Value |
|---|---|---|
| 0, 1 | `lb` vs `lbu` of byte `0xF0` | `-16`, `240` |
| 2, 3 | `lh` vs `lhu` of halfword `0x8001` | `-32767`, `32769` |
| 4, 5 | `ori` zero-extends, `addiu` sign-extends | `0x0000FFFF`, `0xFFFFFFFF` |
| 6, 7 | `andi` as a mask, `nor` as NOT | `0x0000FFFF`, `0xF0F0F0F0` |
| 8, 9 | `sra` vs `srl` of `-7` by 1 | `-4`, `0x7FFFFFFC` |
| 10 | `-7 / 2` toward zero, via the bias trick | `-3` |
| 11 | `sllv` by 33 | `2` (shift amount masked to 1) |
| 12 | 5-bit field sign-extended | `-3` |

## 7. Project: Bit Toolkit

Six leaf subroutines plus finishing the driver. Everything goes in `starter/main.s`, which declares the routines as stubs that just return.

### 7.1 The routines

All take their argument in `$a0` (and `$a1`), return in `$v0` (and `$v1`), use only `$t0-$t9`, `$a0-$a3`, `$v0-$v1`, and return with `jr $ra`. The verifier fills every register it does not set with garbage.

| Routine | Input | Result |
|---|---|---|
| `abs` | `$a0` signed | `$v0` = absolute value. `abs(0x80000000)` = `0x80000000` (no positive twin) |
| `sign_extend` | `$a0` = value, `$a1` = bits (1 to 32) | `$v0` = low `bits` bits of `$a0` read as a signed field, extended to 32 bits. Bits of `$a0` above the field are ignored. `bits` = 32 returns the value; `bits` = 1 returns 0 or -1 |
| `popcount` | `$a0` | `$v0` = number of 1 bits, 0 to 32 |
| `rgb888_to_bgr555` | `$a0` = `0x??RRGGBB` (top byte is ignored) | `$v0` = BGR555 in bits 0-14: `(B>>3)<<10 \| (G>>3)<<5 \| (R>>3)`. Bit 15 and bits 16-31 are 0 |
| `bgr555_unpack` | `$a0` = BGR555 in the low 16 bits (bits 16-31 ignored) | `$v0` = `0x00RRGGBB` with each channel `c8 = (c5<<3) \| (c5>>2)`; `$v1` = bit 15 of the input (0 or 1) |
| `swap_endian32` | `$a0` | `$v0` = bytes reversed |

### 7.2 Rules

- **Shifts, masks and adds only.** `mult`, `multu`, `div`, `divu`, `mfhi`, `mflo`, `mthi` and `mtlo` are banned in the whole program (Chapter 12 covers them).
- **Routines touch no memory.** No loads or stores between `done` and `drv_val`, so no lookup tables: the point is to compute with shifts and masks. (The driver may load and store.)
- At most 400 instructions per call. That is generous (a loop over the 32 bits fits); the straight-line versions take about 5 to 25.
- No armips warnings; place routines after `done` and before the data.

### 7.3 The driver

The starter's driver already calls the six routines on four input words and stores `results[0]` to `results[6]`. You write the rest, directly in the driver:

| Label | Content |
|---|---|
| `drv_val` | signed input for `abs`, `sign_extend`, `popcount`, `swap_endian32` and the rows below |
| `drv_bits` | width for `sign_extend` |
| `drv_rgb`, `drv_bgr` | inputs for the two colour routines |
| `results` | 13 words |

| `results[i]` | Value |
|---|---|
| 0 to 3 | `abs(val)`, `sign_extend(val, bits)`, `popcount(val)`, `rgb888_to_bgr555(rgb)` (given) |
| 4, 5 | `bgr555_unpack(bgr)`: `$v0`, then `$v1` (given) |
| 6 | `swap_endian32(val)` (given) |
| 7 to 10 | `lb`, `lbu`, `lh`, `lhu` of `drv_val` (low byte / low halfword) |
| 11 | `drv_val` shifted right by 3, arithmetic |
| 12 | `drv_val / 8` **rounded toward zero**, without `div` |

### 7.4 Hints

- `abs`: build a mask from the sign (`sra` by 31). XOR with it, then subtract it. Work it out for 5, -5 and 0.
- `sign_extend`: the shift-to-top-and-back idiom needs the amount `32 - bits`. Use the variable shifts.
- `popcount`: test the low bit, add it, shift right logically, repeat until zero. Use `srl`, not `sra`, or negative inputs never reach zero.
- `rgb888_to_bgr555`: shift each channel's top 5 bits into place and mask. Three shift-and-mask pairs, two `or`s.
- `bgr555_unpack`: extract a 5-bit field, then `(c << 3) | (c >> 2)`. Same steps for each channel; place the result with a final shift.
- `swap_endian32`: handle the outer bytes with plain shifts and the two inner bytes with a shift and a mask. A mask like `0x00FF0000` needs `lui`.
- Fill delay slots only when it is obviously safe; a `nop` is fine here. The load-delay rule from Chapter 7 still applies in the driver.

### 7.5 Stretch goals

- Reimplement `popcount` in about a dozen instructions with the SWAR trick (add bit pairs, then nibbles, then bytes with masks `0x55555555`, `0x33333333`, `0x0F0F0F0F`); the last step needs a multiply or more shifts. Stay under the ban.
- Write `bgr555_pack_flag(a0, a1)` that sets or clears bit 15.
- Write `reverse_bits32` (bit-reversal) with the same swap-and-mask idea at 1, 2, 4, 8 and 16 bits.

## 8. Verification

```sh
parts/part-02-thinking-like-the-r3000/ch09-signed-numbers-logic-and-shifts/verify/verify.sh
```

Checks `starter/` by default; pass a path for a copy, `-v` for the log, `--solution` for the reference. Like Chapter 8, the verifier **calls each routine directly**, with sentinel values in the `$s` registers, garbage in the temporaries, and `$ra` aimed at a return trampoline. It prints the random seed on a failure, so you can see exactly which call failed.

| Check | What it means | If it fails |
|---|---|---|
| `program defines main, done, ...` | Labels and ordering. | A label was deleted, or a routine moved. |
| `data tables are as shipped` | `drv_*` unedited. | You edited the tables. |
| `no mult/div/HI/LO instructions` | None in the program. | A banned instruction; the message names it. |
| `the routines use registers only` | No load/store in the routines. | A table lookup or stack use. |
| `the driver calls each routine` | `jal` to all six from `main..done`. | A routine was inlined or skipped. |
| `abs ...`, `sign_extend ...`, `popcount ...`, `rgb888_to_bgr555 ...`, `bgr555_unpack ...`, `swap_endian32 ...` | Edge values (0, -1, `0x80000000`, `0x7FFFFFFF`, masks), every width 1 to 32, and random values with garbage in the unused bits, against Python reference functions. | The message shows the call, expected and actual values. Typical: `abs(0x80000000)`, `bits` = 1 or 32, a `srl` where `sra` was needed. |
| `every routine returns through $ra` | The trampoline is reached. | A fixed `j`, or `$ra` overwritten. |
| `callee-saved registers unchanged` | `$s0-$s7`, `$gp`, `$sp`, `$fp` intact. | The message names the register. |
| `armips reports no warnings` | Clean build. | Usually a load-delay hazard in the driver. |
| `instruction budget` | At most 400 per call. | A loop that runs far too often. |
| `driver: results ...` | All 13 results, on the shipped data and on four other data sets. | Wrong index; `sra` where round-toward-zero was required; `lbu` where `lb` was meant. |

A pass ends with `CHAPTER 09: PASSED (18/18 checks)`.

## 9. Common pitfalls

- **`sra` for division of negatives.** `-7 >> 1` is `-4`, not `-3`. Add the bias first (section 5.4).
- **`srl` where `sra` is needed** (and the reverse). `sign_extend` with `srlv` returns the field zero-extended, which looks right for positive test values.
- **`andi`/`ori` with a "negative" immediate.** The immediate is zero-extended, so there is no way to write `ori $t, $t, -1`. Use `li` or `nor`.
- **Loading a byte with `lb` when you want an unsigned value.** A pixel channel of 200 comes back as -56.
- **Shift amounts of 32 or more.** The variable forms use the low 5 bits only; `sllv` by 32 does nothing rather than clearing the register. (For `sign_extend`, `bits` = 32 means a shift by 0, which is fine.)
- **Colour channel order.** BGR555 puts red in the **low** bits, the reverse of `0x00RRGGBB`.
- **Truncating 8 to 5 bits.** The reference drops the low 3 bits; it does not round.
- **`abs(0x80000000)`.** There is no positive 2^31. The routine returns `0x80000000` unchanged; callers must know.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- psx-spx, the GPU section on 15-bit colour (texture and VRAM pixel formats) for the BGR555 layout and the mask bit: <https://psx-spx.consoledev.net/>
- psx-spx, "CPU Specifications" for the instruction encodings (`sll`, `sllv`, `andi`).
- *Hacker's Delight* (Warren), chapters 2 and 5, for bit tricks (`abs`, `popcount`, byte swaps).
- *See MIPS Run* (Sweetman), the chapter on the instruction set (shifts, sign extension).
