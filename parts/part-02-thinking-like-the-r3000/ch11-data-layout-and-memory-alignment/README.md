# Chapter 11: Data Layout and Memory Alignment

## 1. Concept

The R3000 can only load and store a value at an address that is a multiple of its size: a halfword at an even address, a word at a multiple of 4. This is **natural alignment**. Break it and the CPU raises an exception instead of guessing. Data layout (where each field sits, how big a struct is, how arrays of structs are indexed) is how you keep every access naturally aligned.

## 2. Why it matters

Everything the PS1 renders is a table of small structs: vertices, faces, colors, GTE input. Part V's `SVECTOR` is exactly the 8-byte struct you build here, and the GTE and DMA both expect word-aligned data. A misaligned access is not slow, it is a crash, and the fix (padding, `.align`) is always the same. For the rare data that cannot be aligned (packed file formats, byte streams) MIPS offers `lwl`/`lwr`.

## 3. Learning objectives

After this chapter you can:

- state the alignment rule and what the CPU does when it is broken (exception code, `BadVAddr`);
- lay out a struct with padding and compute its size;
- compute the address of `table[i].field` as `base + i*size + offset`;
- use `.align`, `.byte`, `.halfword`, `.word` and `.fill` in armips, and know what each does *not* do;
- read and write words at any address with `lwr`/`lwl` and `swr`/`swl`, including their load-delay rule;
- treat 16-bit signed fields correctly: sign-extending loads, wraparound on store.

## 4. Prerequisites

[Chapter 2](../../part-01-machine-and-language/ch02-memory-map-and-endianness/README.md) (little-endian byte order), [Chapter 3](../../part-01-machine-and-language/ch03-registers-loads-stores-arithmetic/README.md) (loads and stores), [Chapter 8](../ch08-subroutines/README.md) (calling leaf routines), and [Chapter 9](../ch09-signed-numbers-logic-and-shifts/README.md) (`lh` vs `lhu`, signed compares).

## 5. Explanation

### 5.1 Natural alignment

| Access | Size | Address must be | Instructions |
|---|---|---|---|
| byte | 1 | anything | `lb` `lbu` `sb` |
| halfword | 2 | a multiple of 2 | `lh` `lhu` `sh` |
| word | 4 | a multiple of 4 | `lw` `sw` |

```
 address (low hex digit)   0 1 2 3 4 5 6 7 8 9 A B
 bytes                     | | | | | | | | | | | |
 halfwords (OK)            [ ][ ][ ][ ][ ][ ]
 words (OK)                [      ][      ][
 word at 2 (NOT OK)            [      ]          <- straddles two aligned words
```

The memory bus fetches whole aligned words. A word at address 2 would need two fetches, and the R3000 has no hardware to do that. It raises an exception instead.

### 5.2 What a misaligned access does

A misaligned `lh`/`lhu`/`lw` raises an **address error on load** (AdEL); a misaligned `sh`/`sw`, an **address error on store** (AdES). The CPU abandons the instruction (the register or memory is not changed), records what happened in Coprocessor 0, and jumps to the exception vector at `0x80000080`.

| Cop0 register | Number | Holds |
|---|---|---|
| `BadVAddr` | 8 | the address that was not aligned |
| `Cause` | 13 | bits 6..2 = exception code: **4** = AdEL, **5** = AdES |
| `EPC` | 14 | the address of the faulting instruction, or of the branch before it if it sat in a delay slot (then `Cause` bit 31, BD, is set) |

Once the BIOS's handler gets control, a program that has not installed its own handler is finished. Treat an address error as a bug in the layout or in the pointer arithmetic. The usual causes: a table that follows a `.byte` without `.align`, an index scaled by the wrong size, or a pointer into a packed byte stream.

### 5.3 Data directives in armips

| Directive | Emits | Notes |
|---|---|---|
| `.byte a, b, ...` | 1 byte each | |
| `.halfword a, ...` | 2 bytes each, little-endian | negative values are fine: `-100` is `0xFF9C` |
| `.word a, ...` | 4 bytes each | |
| `.fill n, v` | `n` **bytes** of value `v` | `.fill 12, 0` is three words |
| `.align n` | zero bytes up to the next multiple of `n` | `n` is a **byte count**, a power of two. `.align 8`, not `.align 3` (an error) |

The trap: **`.halfword` and `.word` do not align themselves.** After a `.byte`, a `.word` is emitted at the very next address, misaligned, and armips says nothing. You must write `.align` yourself. In this chapter's data, `.align 8` in front of the struct table is what keeps every element on an 8-byte boundary.

### 5.4 Structs and padding

Sony's `libgte` and PSn00bSDK's `psxgte.h` both define the vertex the GTE likes best:

```
 SVECTOR  (8 bytes)                    typedef struct { short vx, vy, vz, pad; } SVECTOR;

   offset:   +0       +2       +4       +6
           +--------+--------+--------+--------+
           |   vx   |   vy   |   vz   |  pad   |
           +--------+--------+--------+--------+
            16-bit signed each; pad is unused
```

Three shorts need only 6 bytes. The `pad` makes the size **8**, so that an array of them keeps *every* element on an 8-byte boundary (and the GTE can load a whole vertex as two words). The same rule applies in C: a struct's alignment is that of its most strictly aligned member, and the compiler pads between and after fields to maintain it.

```
 struct { char a; int b; short c; }       a = +0, pad +1..+3, b = +4, c = +8, pad +10..+11  -> size 12
 reordered { int b; short c; char a; }    b = +0, c = +4, a = +6, pad +7                    -> size 8
```

Ordering fields largest first usually wastes the least space.

### 5.5 Arrays of structs

```
 address of table[i].field  =  base + i * size + offset(field)

 vertices (8-aligned):    +0       +8       +16      ...
                       [SVECTOR0][SVECTOR1][SVECTOR2] ...
                        x y z p   x y z p   x y z p

 vertex 3, vz:   base + 3*8 + 4 = base + 28
```

In a loop you rarely compute that product: step a pointer by the struct size (`addiu $a0, $a0, 8`) and keep the field offsets in the load and store instructions (`lh $t0, 4($a0)`). Because the base is 8-aligned and the size is 8, every element and every field stays naturally aligned.

### 5.6 16-bit fields: signed loads, wrapping stores

- `lh` sign-extends the halfword, so `-100` arrives in the register as `0xFFFFFF9C`. Compare these with `slt`.
- `sh` stores only the low 16 bits. Adding to a field in a register and storing it back therefore **wraps modulo 2^16**: `32767 + 1` is stored as `0x8000`, which reads back as `-32768`. No overflow is signaled. The project's `vt_translate` contract specifies exactly this wraparound.

### 5.7 Unaligned access on purpose: `lwl`/`lwr`, `swl`/`swr`

Sometimes the data is simply not aligned: a packed array of 6-byte records, a byte stream from a file. MIPS provides four instructions that handle one word at *any* address, in two halves. They never raise an address error.

```
 memory (little-endian):  addr:  0   1   2   3 | 4   5   6   7
                                11  22  33  44 | 55  66  77  88       want the word at 1: 22 33 44 55

 lwr $t0, 1(base)     takes bytes from addr 1 to the END of its aligned word  (22 33 44)
                      -> into the LOW bytes of $t0; the top byte of $t0 is left alone
 lwl $t0, 4(base)     takes bytes from the START of its aligned word up to addr 4  (55)
                      -> into the HIGH bytes of $t0; the low bytes are left alone

 $t0 after both:  0x55443322
```

The recipe on this little-endian CPU, for a word at address `A`:

| Want | Instructions |
|---|---|
| load unaligned word | `lwr rt, 0(A)` and `lwl rt, 3(A)` (either order) |
| store unaligned word | `swr rt, 0(A)` and `swl rt, 3(A)` |

If `A` happens to be aligned, each of the two loads the whole word (redundantly), so the pair is still correct; `swr`/`swl` behave the same way. The second instruction is the price of not knowing the alignment.

**Load delay.** Each instruction merges its bytes into the existing value of `rt`, so the second must see the result of the first. The R3000 makes its one exception to the load-delay rule here (psx-spx: "no delay required between lwl and lwr"): the pair may be adjacent on the same register, in either order. Any other instruction reading `rt` still has to wait one instruction.

There is no such pair for halfwords: load an unaligned halfword with two `lbu`, a shift and an `or`; store one with two `sb`.

## 6. Worked example

[`example/main.s`](example/main.s) (`make` in `example/`) reads the word at `bytes+1` with `lwr`/`lwl` and stores it in `results[0]` (`0x55443322`), then executes a plain `lw` from `bytes+2`. That one is meant to crash.

Run it with `make run`, or load `build/main.ps-exe` in PCSX-Redux with the debugger (Chapter 6). The program never reaches `done`; the emulator ends up in the BIOS exception handler. Look at the Cop0 registers (the debugger's Registers window lists them) and at `results`. You report what you find in `answers.md` (step 4 of 7.2).

## 7. Project: Vertex Table

Work in `starter/main.s`. The driver is given. You write the data table and four routines. The `SVECTOR` coordinates are **signed 16-bit**.

### 7.1 The routines

All four are leaf routines: use `$t`, `$a`, `$v` registers only.

| Routine | Arguments | Behavior |
|---|---|---|
| `vt_translate` | `$a0` = table, `$a1` = count, `$a2` = pointer to an offset SVECTOR | add the offset's x, y, z to every vertex **in place**. Each sum wraps to 16 bits. `pad` is not touched. |
| `vt_bbox` | `$a0` = table, `$a1` = count (at least 1), `$a2` = output | write six halfwords: min x, min y, min z, max x, max y, max z. **Signed** compares. |
| `vt_pack` | `$a0` = table, `$a1` = count, `$a2` = dst | write x, y, z of each vertex as 6 little-endian bytes, no pad. `dst` may have **any alignment**. `$v0` = bytes written (`6 * count`). Touch nothing else. |
| `vt_unpack` | `$a0` = packed data, `$a1` = count, `$a2` = table | the reverse. `$a0` may have **any alignment**; `$a2` is a word-aligned table. Rebuilt `pad` = 0. |

```
 packed format (per vertex, 6 bytes):
   +0     +1     +2     +3     +4     +5
 [x lo ][x hi ][y lo ][y hi ][z lo ][z hi ]      vertex i starts at packed + 6*i
```

### 7.2 Your steps

1. **The table.** Replace the placeholder after `vertices:` with `.align` and eight `.halfword x, y, z, 0` lines for a cube's corners. Corner `i`: x is +100 if bit 0 of `i` is set, else -100; y from bit 1; z from bit 2.
2. **`vt_translate`**, then **`vt_bbox`**. Stride is 8; fields are at +0, +2, +4.
3. **`vt_pack`** and **`vt_unpack`**. The driver's `packed` buffer starts at an **odd** address (the starter puts a guard byte in front of it), so `sh`/`sw` there will crash. Use `swr`/`swl` + `sb`, or byte stores throughout; read with `lwr`/`lwl` + `lbu`, or byte loads.
4. **`answers.md`.** Run `example/` and fill in the file (four lines):

| Line | Value |
|---|---|
| `exception_code:` | the number in Cause bits 6..2 |
| `bad_address:` | the address in `BadVAddr`, as `0x...` |
| `faulting_instruction:` | the mnemonic at `EPC` (for example `lw`) |
| `explanation:` | one or two sentences: why the CPU refuses, and what you would use if the data could not be aligned |

The explanation is only checked for being a real sentence, not for particular words.

### 7.3 Rules

- Keep the starter's labels and their order: routines in the starter's order, then `routines_end`, then the data. Do not edit `vt_offset`, the guard bytes, or the sizes of the buffers.
- Routines preserve `$s0-$s7`, `$gp`, `$sp`, `$fp` (they are leaves).
- `vt_pack` and `vt_unpack` must contain at least one unaligned or byte instruction (`lwl`/`lwr`/`swl`/`swr` or `lb`/`lbu`/`sb`). Which ones is your choice, as long as the routine works at every alignment.
- Write exactly the bytes the contract names; the verifier surrounds every buffer with guard bytes.
- At most 60 instructions per vertex (plus 100 per call).

### 7.4 Hints

- `lh` sign-extends, so a plain `slt` on the loaded registers is already a signed comparison.
- Initialize min and max from vertex 0, then loop over the rest. A count of 1 must work.
- In `vt_translate` load dx, dy, dz once, before the loop.
- `swr rt, 0(A)` followed by `swl rt, 3(A)` writes a whole word at `A`. Then `sb` the two bytes of z, shifting between them.
- In `vt_unpack` build `z` from two `lbu`s (`lo | (hi << 8)`); the high half of that word is the zero pad, so one `sw` writes z and pad together.
- Only an instruction directly after a *normal* load must not use its result; `lwr`/`lwl` on one register are the exception (5.7).

### 7.5 Stretch goals

- Rewrite `vt_pack` with only byte stores, and `vt_unpack` with only byte loads. Count the instructions against the `lwl`/`lwr` version.
- `vt_translate` by the offset using one 32-bit add for x and y together: when is that wrong? (Think about carries between the halves.)
- Lay out `struct { char tag; short x; char flag; int id; short y; }`, then reorder it for the smallest size. Compute both sizes.
- Add `vt_centroid`: sum each axis, then divide by the count. For a power-of-two count `sra` is enough; Chapter 12 covers `div`.

## 8. Verification

```sh
parts/part-02-thinking-like-the-r3000/ch11-data-layout-and-memory-alignment/verify/verify.sh
```

Checks `starter/` by default; pass a path for a copy, `-v` for the log, `--solution` for the reference. Like Chapters 8 to 10, the verifier **calls each routine directly** on scratch buffers with guard bytes, sentinels in the `$s` registers, random data (the seed is printed on failure), and every buffer alignment 0 to 3 for the packed data. The first CPU exception ends the run and is reported with its code, pc and bad address.

| Check | What it means | If it fails |
|---|---|---|
| `program defines main, done, ...` | Labels and order. | A label was deleted or moved. |
| `the struct table ... is 8-byte aligned` | `vertices`, `vt_offset`, `roundtrip` at multiples of 8 (read from the armips symbols). | Missing `.align 8`. |
| `vertices holds the cube` | The 64 bytes you wrote. | Wrong corner order, wrong sign, missing pad. |
| `the other data is as shipped` | Offset, guard bytes, odd `packed`. | Edited a buffer. |
| `the packing routines use unaligned-capable instructions` | `swl`/`swr`/`sb` in `vt_pack`; `lwl`/`lwr`/`lb`/`lbu` in `vt_unpack`. | Only `sw`/`sh`/`lw`/`lh` there. |
| `the driver calls each routine` | `jal` to all four. | A call removed. |
| `armips reports no warnings` | No load-delay slips. | Using a loaded register in the next instruction. |
| `answers.md: ...` (two checks) | Your three values equal the ones the verifier gets by running `example/` and reading Cop0; plus a 10-word explanation. | Message names the field. |
| `program reaches done`, `no CPU exception ...` | The driver finishes; no address error anywhere. | A loop never ends, or the message shows the code (4 load, 5 store), pc and bad address. |
| `vt_translate ...`, `vt_bbox ...`, `vt_pack ...`, `vt_unpack ...` | Byte-for-byte equal to the Python reference on random and edge data (extreme coordinates, negatives, wraparound, counts 0 to 16, all alignments). | The message shows the input and expected/actual values per vertex. |
| `routines write only where they should` | Guard bytes untouched; inputs not modified. | Eight bytes per vertex in `vt_pack`, or an off-by-one count. |
| `every routine returns`, `callee-saved registers`, `instruction budget` | Leaf-routine hygiene. | See Chapter 8. |
| `driver: ...` | The real program, run on the shipped cube and on four patched tables: `vertices`, `bbox`, `packed` (with guards) and `roundtrip` all match. | A routine works alone but the driver or the labels are wrong. |

A pass ends with `CHAPTER 11: PASSED (22/22 checks)`.

## 9. Common pitfalls

- **A `.word`/`.halfword` table after a `.byte` with no `.align`.** armips places it at the next byte and does not warn. The crash comes later, at the first `lw`.
- **`.align 3`.** armips wants a byte count: `.align 8`. (The error message is "Invalid alignment".)
- **Forgetting the pad.** Three shorts make 6 bytes; strides of 6 misalign every other element for word loads.
- **Using `lhu` for coordinates.** `-100` becomes 65436, and every comparison after it is wrong.
- **`sw` into the packed buffer.** It works when the buffer happens to be word-aligned and crashes when it is not. The verifier tries all four alignments.
- **`swl`/`swr` with the wrong offsets.** The pair is `0(A)` and `3(A)`, never `0` and `4`.
- **Overrunning the packed buffer.** Storing the pad too (8 bytes per vertex) corrupts the guard byte after the buffer.
- **Reading a loaded register in the next instruction** (except the `lwr`/`lwl` pair).

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- psx-spx, "CPU Specifications": the exception table, `Cause`, `BadVAddr`, `EPC`, and the `LWL`/`LWR`/`SWL`/`SWR` description: <https://psx-spx.consoledev.net/>
- psx-spx, "Geometry Transformation Engine (GTE)": the vector registers (`VXY0`, `VZ0`) that an `SVECTOR` is loaded into as two words (Part V).
- *See MIPS Run* (Sweetman), the chapters on memory alignment and unaligned access.
- armips documentation: `.align`, `.fill`, `.byte`, `.halfword`, `.word`: <https://github.com/Kingcom/armips>
