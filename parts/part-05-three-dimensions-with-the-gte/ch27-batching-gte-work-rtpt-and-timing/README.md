# Chapter 27: Batching GTE Work: RTPT and Timing

## 1. Concept

The GTE works in parallel with the CPU, and what a transform costs is mostly the loads, stores and waits **around** the command, not the command itself. Transforming three vertices per command (`RTPT`) removes most of them. Knowing when the CPU waits for the GTE lets you put useful work in the gap.

## 2. Why it matters

One cube is 8 transforms; the field in this chapter is 64 cubes, 512 transforms a frame, before any culling or drawing. Games at the PS1's scale (hundreds of polygons at 30 or 60 frames per second) live on this loop. The same chapter also explains the numbers you will quote when you profile: what a "cycle" is here, where the CPU stalls, and how to measure it.

## 3. Learning objectives

After this chapter you can:

- name the GTE's data and control registers, their formats and the SDK macros that move data in and out;
- choose between `lwc2`/`swc2` and `mtc2`/`mfc2`, and say what each costs;
- transform eight corners with three `RTPT` commands, and explain what the repeated corner is for;
- state the two hazards of a GTE command and where the CPU stalls;
- find, with a timer and with the verifier's cycle probe, how many cycles a block of GTE work takes.

## 4. Prerequisites

[Chapter 25](../ch25-the-gte-coprocessor/README.md) (`RTPS`, the SDK macros, `NCLIP`/`AVSZ`), [Chapter 26](../ch26-multiple-objects-and-simple-motion/README.md) (a matrix per object, uploading it), [Chapter 12](../../part-02-thinking-like-the-r3000/ch12-risc-vs-cisc-multiply-and-divide/README.md) (instruction costs).

## 5. Explanation

### 5.1 The register file

The GTE (coprocessor 2) has 32 **data** registers and 32 **control** registers, each 32 bits. psx-spx has the full list; this is the part you will use. "Macro" is the PSn00bSDK `<inline_c.h>` macro that reads or writes it.

**Data registers** (`mtc2`/`mfc2`/`lwc2`/`swc2`):

| # | Name | Format | Holds | Macros |
|---|---|---|---|---|
| 0, 1 | `VXY0`, `VZ0` | s16 x, s16 y; s16 z | input vertex 0 | `gte_ldv0` |
| 2, 3 | `VXY1`, `VZ1` | same | vertex 1 | `gte_ldv1` |
| 4, 5 | `VXY2`, `VZ2` | same | vertex 2 | `gte_ldv2` |
| (0..5) | | | all three | `gte_ldv3`, `gte_ldv3c` |
| 6 | `RGBC` | r, g, b, code bytes | colour for lighting | `gte_ldrgb` |
| 7 | `OTZ` | u16 | average depth (`AVSZ`) | `gte_stotz` |
| 8 | `IR0` | s16 | depth-cue factor | `gte_stdp` |
| 9..11 | `IR1..IR3` | s16 | rotated vector (saturated) | `gte_stsv` |
| 12..14 | `SXY0..SXY2` | s16 x, s16 y | screen-point FIFO | `gte_ldsxy3`, `gte_stsxy`, `gte_stsxy3`, `gte_stsxy3c` |
| 15 | `SXYP` | | write: push into the FIFO; read: `SXY2` | |
| 16..19 | `SZ0..SZ3` | u16 | depth FIFO | `gte_ldsz3/4`, `gte_stsz`, `gte_stsz3/4`, `gte_stsz3c` |
| 20..22 | `RGB0..RGB2` | bytes | colour FIFO | `gte_strgb3` |
| 24 | `MAC0` | s32 | `NCLIP` area, divide product | `gte_stopz` |
| 25..27 | `MAC1..MAC3` | s32 | 32-bit sums before saturation | `gte_stlvnl` |
| 28..31 | `IRGB`, `ORGB`, `LZCS`, `LZCR` | | colour packing, leading-zero count | |

**Control registers** (`ctc2`/`cfc2`; **not** reachable with `lwc2`/`swc2`):

| # | Name | Format | Holds | Macros |
|---|---|---|---|---|
| 0..4 | `R11R12 .. R33` | s16 x 9, 4.12 | rotation matrix `RT` | `gte_SetRotMatrix` |
| 5..7 | `TRX, TRY, TRZ` | s32 | translation `TR` | `gte_SetTransMatrix` |
| 8..20 | light, colour matrices, `BK` | | lighting (Part VII) | |
| 21..23 | `RFC, GFC, BFC` | s32 | far colour (fog) | |
| 24, 25 | `OFX`, `OFY` | s32, 16.16 | screen offset | `gte_SetGeomOffset` (takes whole pixels) |
| 26 | `H` | u16 | projection distance | `gte_SetGeomScreen` |
| 27, 28 | `DQA`, `DQB` | s16, s32 | depth cueing | |
| 29, 30 | `ZSF3`, `ZSF4` | s16, 4.12 | `AVSZ3` / `AVSZ4` scale | |
| 31 | `FLAG` | bits | errors of the last command | `gte_stflg` |

A vertex is an `SVECTOR` (`vx, vy, vz, pad`, 8 bytes). Its first word is exactly `VXY`, its second exactly `VZ` (the pad is ignored), so one vertex loads with **two `lwc2`**, no unpacking.

### 5.2 Moving data in and out

| Instruction | Does | Cost in instructions |
|---|---|---|
| `lwc2 $n, off(rs)` | memory word straight into data register `n` | 1 (no CPU register used) |
| `swc2 $n, off(rs)` | data register `n` straight to memory | 1 |
| `mtc2 rt, $n` | CPU register to data register `n` | 1 (after a `lw`: 2) |
| `mfc2 rt, $n` | data register `n` to a CPU register | 1, **result one instruction late** |
| `ctc2` / `cfc2` | the same for control registers | |

So `lwc2`/`swc2` are the cheap way when the data is already in memory in GTE format, as `SVECTOR`s and `SXY` words are. `mtc2`/`mfc2` are for values the CPU computes or tests (`gte_ldsxy3` uses `mtc2` because the point is already in a CPU register). Matrices live in control registers, which only `ctc2` can write: five words of rotation and three of translation, one load and one `ctc2` each, so `gte_SetRotMatrix` plus `gte_SetTransMatrix` cost 16 instructions.

### 5.3 `RTPT`: three vertices, one command

`RTPT` runs `RTPS` on `V0`, `V1` and `V2`. Afterwards (verified by this chapter's probe):

```
before:  SXY0 SXY1 SXY2          SZ0 SZ1 SZ2 SZ3
          a    b    c             p   q   r   s

RTPT(V0, V1, V2) pushes three results:
after:   SXY0 SXY1 SXY2          SZ0 SZ1 SZ2 SZ3
          v0'  v1'  v2'           s   v0' v1' v2'     (SZ0 keeps the old SZ3)
```

All three screen points are in the FIFO in order, and `gte_stsxy3c(p)` writes `SXY0..SXY2` to three consecutive words; `gte_stsz3c(p)` writes `SZ1..SZ3`. `IR1..IR3` and `MAC1..MAC3` describe only the **last** vertex. `FLAG` is the OR over the three.

The result of each vertex is bit-identical to what `RTPS` gives: the verifier compares both paths word for word.

### 5.4 Eight corners, three at a time

Eight is not a multiple of three. Ways out:

| Scheme | Commands per cube | Notes |
|---|---|---|
| 8 x `RTPS` | 8 | Chapter 25's code |
| 3 x `RTPT`, third batch = corners 5, 6, 7 | 3 | corner 5 is computed twice; every store goes to a real slot |
| 3 x `RTPT`, third batch = 6, 7 + a **pad** vertex | 3 | the pad result must be discarded, never stored in a slot that does not exist |
| 2 x `RTPT` + 2 x `RTPS` | 4 | no repeated work |

A pad corner is any valid vertex (use a copy of corner 7). The trap is the **stores**: `gte_stsxy3c(&screen_xy[i][6])` writes three words, `[6]`, `[7]` and `[8]`, and `[8]` is the next cube's corner 0 (for the last cube it is past the array). Store two words, or overlap the batches as in row 2.

### 5.5 Timing, stalls and hazards

Command latencies (psx-spx): `RTPS` 15 cycles, `RTPT` 23, `NCLIP` 8, `AVSZ3` 5, `AVSZ4` 6. Three `RTPS` are 45; one `RTPT` is 23, and it needs one load group, one `nop` pair and one store group instead of three.

Three rules decide what the CPU can do while the GTE works:

1. **Starting a command** does not stop the CPU: it goes on with the next instruction.
2. **Reading a result** (`swc2`, `mfc2`, `cfc2`) or starting another command **waits** until the GTE is done. This is the interlock, and it is the only place a GTE program stalls.
3. **Setting up and collecting** are not interlocked. A value read by `mfc2`/`cfc2` reaches the CPU register **one instruction** later (psx-spx), like a `lw`; `gte_stflg` has a `nop` for it. For writes, psx-spx gives `lwc2` a delay of **two instructions** (and itself doubts the details) and gives no figure for `mtc2`/`ctc2`; the SDK's (and Sony's) command macros start with two `nop`s after whatever wrote last. This book's rule is the safe superset: **two instructions between any `lwc2`/`mtc2`/`ctc2` and a command**.

A timeline of one `RTPS` in a loop (C = CPU instruction, g = the GTE busy; nominal cycles):

```
CPU:  ldv0 ldv0 nop nop RTPS  swc2 ........ (stalled, waiting for the result) swc2 ...
GTE:                       |gggggggggggggggg|   (15 cycles)
                                              ^ the read returns here
```

and eight of them in a row, against three `RTPT`:

```
8 x RTPS    [ld ld nop nop R wait st st] x 8      the waits are 8 x ~13 cycles, the setup 8 times
3 x RTPT    [ld ld ld ld ld ld nop nop T wait st st st st st st] x 3
```

**Independent work in the gap.** Instructions that touch no GTE register (ALU on CPU registers, `lw`/`sw` to RAM, loop control) run while the command works, so they are free up to the length of the wait:

```
CPU:  RTPS  addu addu addu addu addu  swc2        <- the read finds the result ready: no stall
GTE:        |gggggggggggggggg|
```

The worked example (section 6) measures it. Past the window, every extra instruction costs its full price, and a **read** of any GTE register (even an unrelated one) also waits, so the instructions after it are no longer hidden. How many instructions fit is a property of the machine that runs them. PCSX-Redux's interpreter charges a flat **2 cycles per instruction** (measured: each ALU instruction past the window adds 2), so the 15-cycle `RTPS` hides about 7. On hardware an ALU instruction from the instruction cache costs about 1 cycle and a load from main RAM several, so the window holds more ALU work and fewer loads. The shape (flat, then rising) is the same; the numbers in this chapter are the emulator's.

What is worth scheduling: loop control and address arithmetic of the next batch, the CPU test that decides whether the next object is drawn at all, loading the next object's matrix words into CPU registers (the `ctc2`s must wait, the `lw`s need not).

PCSX-Redux models the stall but **not** rule 3: code that drops the `nop`s computes the right numbers in the emulator (tested: the reference with bare `cop2` words passes every run-time check), and on hardware may start the command on stale inputs. The verifier therefore checks the instruction stream (section 8).

### 5.6 Measuring cycles

Two tools:

- **A root counter.** Root counter 0 (`0x1F801100`, mode register `0x1F801104`) with mode 0 counts CPU cycles and wraps at 65536. Read it before and after (`uint16_t` subtraction handles the wrap), as the starter's main loop does. It costs a couple of instructions and measures hardware as well as the emulator.
- **The cycle probe.** The verifier counts the emulator's cycles between two marker functions (`transform_begin()` / `transform_end()`). It is exact and costs nothing in the program. The chapter checks that your timer and the probe agree to 3 %.

Both count the emulator's cycles only under its **interpreter** (`-interpreter`, which the verifier and this chapter's `make run` pass). Redux's default CPU, the dynarec, counts cycles per translated block, and its numbers for code this short mean nothing.

Always measure the same work twice and compare, never trust one number: interrupts (the vertical blank) can land inside a measurement, so the verifier uses the median of the frames.

### 5.7 The SDK's macros

PSn00bSDK 0.24's `<inline_c.h>` is "basically identical to Nugget's `inline_n.h`" and, like it, has two flavours of each command. The plain macro is `nop; nop; cop2 <word>`: `gte_rtpt()` is two `nop`s and the command. The `_b` ("bare") macro is only the command: `gte_rtpt_b()` expands to `cop2 0x0280030`, with no `nop` before or after (65 of them, e.g. `gte_rtps_b`, `gte_rtpt_b`, `gte_nclip_b`, `gte_avsz3_b`, `gte_avsz4_b`, `gte_mvmva_b`; both flavours are plain `asm volatile` with no clobbers). With `_b` you fill the two slots yourself:

```
gte_ldv3c(&cube[0]);                    /* the last lwc2 */
next = base + 3;  count--;              /* two independent instructions: the slots the nops would fill */
gte_rtpt_b();                           /* bare RTPT, the same word gte_rtpt() issues after its nops */
```

and keep two non-GTE instructions between the last register write and it. Writing `__asm__ volatile("cop2 0x0280030")` yourself is equivalent. Neither the macro nor the asm statement pins the neighbouring C code in place, so check the disassembly (`mipsel-none-elf-objdump -d -z`) to see what the compiler really put there; the verifier does the same. (The command word is `0x4A000000 | imm25`: bit 19 is `sf`, the command number is the low six bits, `0x30` for `RTPT`, `0x01` for `RTPS`; bits 20-24, the "fake" command number Sony's tools show (2 for `RTPT`), are ignored by the hardware.)

**A defect to know about.** In this SDK, `gte_SetRotMatrix` and `gte_SetTransMatrix` (and `gte_SetLightMatrix`, `gte_SetColorMatrix`) load through `$t0` and `$t1` but declare only `$t2` as clobbered. A value the compiler keeps in `$t0`/`$t1` across them is silently destroyed; the symptom is usually a store through a garbage pointer, far from the cause, and whether it happens depends on register allocation. The book's `load_matrix()` (given here and in Chapters 25 and 26) calls them inside a function marked `noipa`. Plain `noinline` is not enough: with GCC's `-fipa-ra` (on at `-O2`) the caller looks at which registers the compiled callee uses, does not see the undeclared ones, and keeps its own values in `$t0`/`$t1` across the call. `noipa` forbids that, so the caller assumes every temporary register is lost.

## 6. Worked example

`example/` times `RTPS`, then *k* other instructions, then the read, for several *k*, with root counter 0, and draws one bar per row (and prints the numbers once, about a second after start).

```sh
source tools/env.sh
cd parts/part-05-three-dimensions-with-the-gte/ch27-batching-gte-work-rtpt-and-timing/example
make run
```

Measured in PCSX-Redux's interpreter (cycles; row 1 is the cost of the timer reads and the store alone):

| Row | Gap between command and read | Cycles |
|---|---|---|
| 1 | no command | 12 |
| 2 | nothing | 31 |
| 3 | 4 ALU instructions | 31 |
| 4 | 8 | 34 |
| 5 | 12 | 42 |
| 6 | 16 | 50 |
| 7 | 4 loads from RAM | 31 |
| 8 | a `mfc2`, then 4 ALU instructions | 45 |

Look at the shape: flat while the CPU would be waiting anyway (rows 2, 3, 7), then 2 cycles per instruction (rows 4 to 6). Row 8: the read waits for the command, so the four ALU instructions after it are charged in full.

Try: change the command to `RTPT` (`0x0280030`) and find how many ALU instructions fit in its longer window; the first row that grows is where the window ends.

## 7. Project: "The 64-Cube Field"

Transform a field of 64 spinning cubes two ways and compare the cost: one `RTPS` per corner (given) and batched `RTPT` (yours).

### 7.1 Behaviour

An 8 x 8 grid of cubes, each with its own pose, speed and matrix, seen through one fixed camera. Each frame the given code spins the cubes and builds their matrices; your path transforms all 64 x 8 corners; the given code marks the middle of every cube with a coloured 8 x 8 tile (the tiles are the visible result: they sit where the transformed corners say). `path` selects which transform runs: 0 for `RTPS`, 1 for `RTPT`. The program times the transform of the field with root counter 0 and keeps the result of the last frame in `field_cycles[path]` (and prints it every 120 frames when run with `-stdout`, which `make run` passes).

### 7.2 The contract

`starter/main.c` declares this state (do not change names, types or initial values):

| Symbol | Type | Initial | Meaning |
|---|---|---|---|
| `cubes[64]` | `Cube` (10 x `int32`) | the grid | Cube `i` is in column `i & 7`, row `i >> 3`. Fields: `x y z` (centre), `ax ay az` (angles, 4096 per turn), `sx sy sz` (added to the angles each frame), `size` (half edge) |
| `cube[8]` | `SVECTOR` | corners, +-4096 | Corner `c`: x from bit 0, y from bit 1, z from bit 2 (as in Chapter 25) |
| `path` | `int32_t` | 0 | 0 = `RTPS` per corner, 1 = `RTPT` batches |
| `cam` | `VECTOR` | `{0, 0, 8192}` | The common camera: added to every cube's position (no rotation) |
| `proj_h` | `int32_t` | 256 | Projection distance |
| `cube_mtx[64]` | `MATRIX` | 0 | Cube `i`'s matrix, **built for you** each frame: `RotMatrix` of its angles, scaled by `size`, translation `(x, y, z) + cam` |
| `screen_xy[64][8]` | `int32_t` | 0 | **Yours.** Cube `i`, corner `c`: one `SXY` word, x in the low 16 bits, y in the high 16 |
| `screen_z[64][8]` | `int32_t` | 0 | **Yours.** Cube `i`, corner `c`: `SZ` |
| `field_cycles[2]` | `int32_t` | 0 | Cycles of the transform, last frame, per path (the given loop writes it) |
| `frame_no` | `int32_t` | 0 | Frames completed |

Per frame (given): `update_cubes`, `build_matrices`, `transform_begin()`, the selected `transform_field_*`, `transform_end()`, `draw_tiles`. `render_begin()`/`render_end()` surround all of the frame's work. The five marker functions are what the verifier times and observes.

**Both paths must leave in `screen_xy`/`screen_z` exactly what `RTPS` gives for that cube's `cube_mtx[i]`, for every cube and corner, every frame.** `load_matrix(i)` (given) loads the matrix into the GTE.

### 7.3 Steps

1. `make run` in `starter/`: path 0 shows the grid of tiles and prints its cycles. Read `transform_field_rtps()`: it is Chapter 25's loop.
2. Write `transform_field_rtpt()`: per cube, `load_matrix(i)`, then batches. Use `gte_ldv3c(&cube[c])` (three consecutive `SVECTOR`s), `gte_rtpt()`, `gte_stsxy3c(&screen_xy[i][c])` and `gte_stsz3c(&screen_z[i][c])`. Decide how to cover corners 6 and 7 (5.4).
3. Set `path = 1`, `make run`, compare the two printed cycle counts.
4. `verify.sh`.

### 7.4 Rules

- Transform with `RTPT` (the verifier looks for it in your own objects and counts how often it runs). At most two `RTPS` per cube.
- Do not change path 0, `update_cubes`, `build_matrices`, `load_matrix`, the timer code, the markers or the keep-alive line.
- No `float`/`double`. No GTE command within two instructions of a GTE register write.
- Do not write outside `screen_xy[i][0..7]` and `screen_z[i][0..7]`.

### 7.5 What the reference achieves

Measured by the verifier in PCSX-Redux (cycles of the transform section for all 64 cubes):

| Path | Cycles | Per cube | vs path 0 |
|---|---|---|---|
| 0: `RTPS` per corner | 25,640 | 401 | |
| 1: 3 x `RTPT` (0-2, 3-5, 5-7) | 17,640 | 276 | 31 % fewer (1.45x) |
| 1: 2 x `RTPT` + 2 x `RTPS` | 18,160 | 284 | 29 % fewer |
| 1: the same 3 x `RTPT` in a `for` loop with a conditional | 20,460 | 320 | 20 % fewer |

**Your path 1 must save at least 15 %** (about half the reference's saving). The whole frame (matrices, transform, tiles) costs about 124,000 cycles in path 0 and 116,000 in path 1; the budget is twice that, 232,600. A 60 Hz frame is 564,480 cycles: the transform is 3 % of it with `RTPT`, 4.5 % with `RTPS`. Most of the rest of the frame's work is the 64 matrices (`RotMatrix` and friends, over a thousand cycles each): the next thing to avoid, for example by not rebuilding the matrix of a cube that does not move.

### 7.6 Hints

- *Corners 6 and 7 are wrong, or the first cube is*: a three-word store ran past a row (5.4).
- *Every cube looks like cube 0*: `load_matrix(i)` is missing or outside the loop.
- *The result is right but not faster*: you wrote a loop around `RTPS`, or called path 0's function.
- *`gte_ldv3c` loads the wrong vertices*: it takes a pointer to the first of three **consecutive** `SVECTOR`s.
- *Which store for SZ?* After `RTPT`, `SZ1..SZ3` hold the three depths (5.3); `SZ0` holds an older value.

### 7.7 Stretch goals

- Use `gte_rtpt_b()` instead of `gte_rtpt()` and put the next batch's address arithmetic there (5.7). Does it get faster, and why must two instructions stay?
- During the last `RTPT` of a cube, load the next cube's matrix words into CPU registers; after the stores, `ctc2` them (the `lw`s overlap with the command). Measure with `field_cycles`.
- Turn the three batches into a loop the compiler unrolls; compare with the table in 7.5.
- Add `NCLIP` and `AVSZ4` per face and count what the whole Chapter 25 pipeline costs for 64 cubes.

## 8. Verification

```sh
source tools/env.sh
parts/part-05-three-dimensions-with-the-gte/ch27-batching-gte-work-rtpt-and-timing/verify/verify.sh            # your starter/
parts/part-05-three-dimensions-with-the-gte/ch27-batching-gte-work-rtpt-and-timing/verify/verify.sh --solution # the reference
```

The probe records, every frame, the 64 matrices, `screen_xy`, `screen_z`, the cycles between the markers, the program's own `field_cycles`, and how many `RTPS` and `RTPT` commands actually ran in the transform section (an execution breakpoint on every one found in the loaded program). Each path runs separately by patching `path` in the same build; Python recomputes every corner of every cube with the GTE's divider ported from psx-spx.

| Check | What it means | If it fails |
|---|---|---|
| `the state symbols exist` | The labels of 7.2 and the markers are in the program | A declaration or the keep-alive line was removed |
| `the program uses RTPT` | `objdump` of your objects (not the SDK's) contains `RTPT` | Path 1 is still empty, or uses only `RTPS` |
| `every GTE command comes at least two instructions after ...` | No `cop2` command within two instructions of an `lwc2`/`mtc2`/`ctc2` (the rule of 5.5; a write three or more instructions earlier is fine) | `_b` macros or hand-written commands without the nops (works in the emulator, not reliably on hardware) |
| `integers only` | No soft-float helper | A `float` crept in |
| `poses: cube_mtx[] follows cubes[]` | The given code is intact | `update_cubes`/`build_matrices` changed |
| `path 0 ... bit for bit` | The baseline is right (all 64 x 8 x 24 results) | Path 0 changed |
| `path 1 ... bit for bit` | Your batching gives `RTPS`'s answers exactly | Wrong corner, pad corner stored, store past a row, matrix not loaded per cube |
| `the two paths agree word for word` | The paths agree with each other | as above |
| `patched poses, camera and lens` | Different poses, `cam`, `proj_h`, with cubes straddling and behind the camera plane: saturation and divide overflow must also agree | A constant in place of data; a skipped cube |
| `path 1 really batches` | At run time: >= 2 `RTPT`/cube, <= 2 `RTPS`/cube, enough commands for 8 corners; path 0 runs 512 `RTPS` | Path 1 calls path 0, or reuses results |
| `cycles` | Path 1 saves >= 15 % of path 0's cycles in the same build (prints both numbers) | A loop around `RTPS` in disguise; extra work in the transform |
| `the program's own timer agrees` | `field_cycles[path]` is within 3 % of the probe | Timer code changed |
| `frame budget` | The frame stays under 232,600 cycles | Work added to the loop |
| `picture` | A tile in the right colour at the middle of each of the 64 cubes, both paths | Bad `screen_xy` for corners 0 and 7 |

A pass ends with `CHAPTER 27: PASSED (15/15 checks)`; the runs take about 20 seconds.

## 9. Common pitfalls

- **Three-word stores in the last batch**: `stsxy3c(&xy[6])` writes `[8]` too (5.4).
- **Forgetting `load_matrix(i)` per cube**: every cube then uses the previous cube's matrix.
- **Reading `SZ0`**: after `RTPT` the depths are in `SZ1..SZ3`.
- **`IR`/`MAC` after `RTPT`**: they hold the last vertex only.
- **Dropping the `nop`s**: the emulator forgives it, the hardware does not.
- **Measuring one frame once**: interrupts land in measurements; take a median.
- **Trusting a timer without a baseline**: row 1 of the worked example; subtract the cost of the timer itself.
- **Calling `gte_SetRotMatrix`/`gte_SetTransMatrix` inline**: they clobber `$t0`/`$t1` undeclared; call them through a `noipa` function such as `load_matrix()` (5.7).
- **Comparing paths with different work**: the shared parts (matrix upload, loop) are in both; the saving is on the corners only.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- psx-spx (nocash PSX specs): "GTE Registers", "GTE Commands" (`RTPS`, `RTPT`), "GTE Instruction Timing" / "GTE Opcode Summary", "GTE Division Inaccuracy", "GTE Flags".
- `.toolchain/opt/psn00bsdk/include/libpsn00b/inline_c.h` and `gtereg.inc`.
- PCSX-Redux docs: Lua API (`PCSX.getCPUCycles`) and the root counter notes in psx-spx ("Timers").
- Pikuma, the PS1 course's lecture on batching GTE operations.
- Next: Chapter 28 turns the camera into a matrix and puts it under your control.
