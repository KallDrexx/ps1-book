# Appendix F: Troubleshooting

Symptoms first, then causes, ordered by how often they bite. Every entry comes from a chapter's *Pitfalls*
section, from [`tools/verify-lib/README.md`](../tools/verify-lib/README.md), or from what the harness actually
prints; the chapter that teaches it is named so you can read the whole story. Where the book did not verify a
cause, it says *unverified*.

Quick start when something is wrong:

1. `tools/doctor.sh` prints OK / MISSING / WARN per tool and exits non-zero if a required tool is missing.
   Re-run `source tools/env.sh` in any new shell.
2. `verify.sh -v` shows the build output and the emulator log. `verify.sh --keep` keeps the temp directory (screenshots,
   VRAM dumps, logs) and prints its path.
3. Run the program yourself with `make run` and look at it before reading the verifier's hint.

## F.1 The tools do not work

| Symptom | Cause and fix |
|---|---|
| `armips: command not found`, `pcsx-redux: command not found` | New shell. `source tools/env.sh` (puts `.toolchain/bin` on `PATH`). Ch 1 |
| `make` fails in a copy of a starter outside the repository | The Makefile finds `common/` by searching upward for `Summary.md`, or through `PS1BOOK_ROOT`. Source `tools/env.sh` first. Ch 1 |
| `doctor.sh`: `pcsx-redux ... '-version' failed` | The GUI build needs OpenGL 3 libraries. The verifier does not open a window (`-cli`) and may still work. Install your distribution's Mesa/OpenGL packages for `make run` |
| `doctor.sh`: wrong version of armips | Run `tools/setup.sh --force`. The `v0.11.0` tag does not compile with GCC 13+ or CMake 4; `tools/versions.txt` pins a newer commit |
| `doctor.sh` WARN: mkpsxiso differs | The SDK bundles mkpsxiso 2.03; the book pins 2.30. Chapter 42 shows the two behave differently for file dates |
| `xvfb-run` not found | Optional. The harness uses `pcsx-redux -cli` and needs no X server |
| Edits have no effect | You edited `build/` (overwritten every build) or ran an old executable. `make run` rebuilds; the verifier always rebuilds. Ch 1 |

## F.2 What the verifier's result means

| Exit code | Meaning |
|---|---|
| `0` | every check passed (`CHAPTER NN: PASSED (k/k checks)`) |
| `1` | the build failed (`FAILED (build error)`), or a check failed, **including the emulator's 20 s hard timeout** |
| `2` | a tooling problem: a tool is missing, `checks.py` crashed, a probe Lua error, or both `--solution` and a project path were given (`CHAPTER NN: ERROR`) |

`tools/ci.sh` expects `0` for every `--solution` run and exactly `1` for the untouched starter (which must still
build; a starter that does not build is reported `NOBUILD`).

| Message | Usually means |
|---|---|
| `never reached it in N frames` / `emulator did not finish within the 20s hard timeout` | An infinite loop before the chapter's `done:` label, a hang waiting on hardware that never answers (GPU status bit, CD read), or a crash. Add `-v` and look at the exception line |
| `your program lacks symbol X` | The symbol was removed: a missing declaration, or the linker's `-gc-sections` dropped it because nothing references it (F.10) |
| `CPU exception N (...)` with an EPC | See F.4 |
| a probe error, exit `2` | A bug in the chapter's probe or a Lua mistake in a patch; not your program. Report it |

## F.3 Black or wrong screen

Work from the cheapest test: does the program reach `main`, does it draw, is the display on?

| Symptom | Likely cause | Chapter |
|---|---|---|
| Black, nothing draws, assembly | Display not enabled (`GP1(03h)`, remember bit 0 = 1 turns it **off**) or no display range commands | 1, 13 |
| Black, C | `SetDispMask(1)` missing; the display starts off | 19 |
| Black, only after you added drawing | The drawing area is unset (after reset it is the single pixel 0,0) | 13 |
| Smeared, old frames show | No clear (`isbg` / `ClearOTagR`) each frame, or the back buffer holds the picture from two frames ago | 17, 19, 20 |
| Draws nothing, `DrawOTag(ot)` | With a reverse table `ot[0]` is the terminator; pass `&ot[N-1]` | 20 |
| Flicker or a frame late | `setRGB0`/edit after `PutDrawEnv` queued the packet; or flipping before the GPU is done (poll bit 26, `DrawSync(0)`) | 17, 19 |
| Red and blue swapped | The GP0 color word is `BBGGRR`; BGR555 has red in the low bits | 1, 9, 13 |
| Half the faces missing, or the cube looks inside-out | Face table written by feel; quad in perimeter order instead of Z order; `NCLIP` sign taken from a Y-up tutorial (positive = front here) | 25 |
| Garbage or wandering geometry | Rotated `cube[]` in place (error accumulates); matrix never uploaded; stale `SVECTOR` read by the GTE (F.8) | 24, 25, 34 |
| Texture in the wrong colors or shows doubled texels | `w` of a TIM is in 16-bit units; wrong depth bits; `tpage` and `clut` swapped; CLUT x not a multiple of 16 | 30, 32, 35 |
| Texture pixels missing | Color 0 is transparent: use `0x0421` for black | 30 |
| Polygon vanishes | Bigger than 1023 x 511; a vertex behind the camera; z <= 0 | 14, 24 |
| One-pixel sparkling slit between two track sections | A T-junction from subdivision: not a texture bug | 36 |
| Text hidden behind the track | `FntFlush` draws before the table; use `FntSort` so the text goes through the ordering table | 38 |
| Everything draws at 30 fps | Two `VSync` calls per frame | 19 |

If the picture is black and you are sure you drew, take a screenshot through the harness (`--keep`, look for the
PPM) before guessing: the verifier reads the same pixels.

## F.4 Emulator crashes, hangs and CPU exceptions

The harness stops a run at the first CPU exception (the BIOS vector `0x80000080`; OpenBIOS would otherwise halt until
the timeout) and prints `CPU exception N` with the faulting address (EPC), the bad address (BadVAddr) and the
decoded cause. Reading `$ExcCode`:

| Code | Name | Typical cause in this book |
|---|---|---|
| 4 | Address error on load/fetch (AdEL) | misaligned `lw`/`lh`; a garbage pointer; a jump to data (F.5) |
| 5 | Address error on store (AdES) | the same, on a store |
| 6, 7 | Bus error (instruction / data) | an address that exists nowhere |
| 8 | `syscall` | **not a fault**: `EnterCriticalSection` and `ExitCriticalSection` (inside `ResetGraph`, `VSync`) use it. The harness ignores it after the direct calls |
| 9 | `break` | GCC's divide-by-zero trap (Ch 23); a deliberate `break` |
| 10 | Reserved instruction | execution ran into data, or a bad return address |
| 11 | Coprocessor unusable | a GTE instruction without `InitGeom()` (COP2 not enabled); from psx-spx, not triggered by any chapter |
| 12 | Arithmetic overflow (`add`, `addi`, `sub`) | `add` instead of `addu` (Ch 3); `VectorNormalS` on a large vector (F.8) |
| 0 | Interrupt | not an error; the harness ignores it |

| Symptom | Cause |
|---|---|
| Hangs in a loop on the GPU | Waiting on the wrong GPUSTAT bit: bit 26 is for commands, 27 for VRAM reads, 28 for DMA. During a `GP0(A0h)` data phase bit 26 reads **0** (measured in PCSX-Redux), so waiting per data word hangs after the header (Ch 15, 16) |
| Hangs after `DrawOTag` | The ordering table was not cleared each frame, so a stale link loops (Ch 20); or primitives on the stack that the DMA reads after the frame is gone (Ch 19, 20) |
| Works for months, then crashes | Register allocation changed (F.7); or an unrelated edit exposed an uninitialised value |
| Crash later than the bug | A wild store (index from a file used before it was checked, Ch 32, 34); the SDK macro clobber (F.7); a stack that grew down into data (unbounded recursion, Ch 10) |
| Emulator window will not open | OpenGL (F.1). The verifier is unaffected |
| Different result from a retail BIOS | The book runs on OpenBIOS. Test on a retail BIOS (set `PS1BOOK_BIOS=/path`) before relying on anything beyond what a poll writes (Ch 22) |

## F.5 Address errors

* **Misaligned access.** `lw`/`sw` need a 4-byte address, `lh`/`sh` 2. On the R3000 a misaligned access is an exception,
  not just slow (Ch 11, 2). The usual causes: a `.word` table after `.byte` data with no `.align` (armips places it at the
  next byte and does not warn; the crash comes at the first `lw`); `.align 3` (armips wants a byte count, `.align 8`);
  a struct cast over a file image (`u16` reads at odd addresses fault, Ch 32); reading a `u32` from an odd address
  in a file, so check alignment first (Ch 34).
* **A garbage pointer.** `badvaddr` looks like a sentinel (`0xC0DD....`, the verifier's callee-saved fill) when you used a
  register you did not save (Ch 8, 10, 15), or when an SDK macro destroyed `$t0`/`$t1` (F.7).
* **Scratchpad through KSEG1.** On real hardware `0xBF800000` is not the scratchpad (PCSX-Redux lets it through, so a program can work there and fail on a console); use `0x1F800000` or `0x9F800000` (Ch 2).
* **Reading a header word as a full pointer.** An OT/primitive header holds a 24-bit address; `nextPrim(p)` puts the
  `0x80000000` back (Ch 20).
* **Unsigned where signed was meant.** `lhu` for coordinates turns -100 into 65436 (Ch 11).

## F.6 Delay-slot and load-delay bugs

| Bug | Symptom | Fix | Chapter |
|---|---|---|---|
| Using a loaded register in the very next instruction | the **old** value, no error; armips only warns | put an instruction between, or heed the warning | 2, 3, 7 |
| Forgot the branch delay slot | the instruction after a branch runs always | a `nop`, or a harmless useful instruction | 4, 7 |
| A multi-instruction pseudo-op (`li`/`la` with 32 bits, `blt`) in a slot | only the first half lands in the slot | write the expansion by hand | 5, 6, 7 |
| `lw $a0, ...` in the `jal` slot | the callee's first instruction sees the old `$a0` (checked) | load before the `jal` | 8, 14 |
| Copied the target's first instruction into the slot | it runs twice | branch to the second instruction | 7 |
| Value kept in a `$t` register across a call | the callee reused it | use `$s` registers, saved | 8 |
| `blt` and friends | they use `$at`; so does your own code | do not use `$at` yourself | 4, 6 |
| `gas` reordering in a C project's `.s` file | extra `nop`s, moved instructions | `.set noreorder` | 18 |
| `lw $ra` then `jr $ra` | returns to the old address | one instruction between | 18 |
| `mult`/`div` (or `mthi`/`mtlo`) within two instructions after `mfhi`/`mflo` | undefined on hardware; passes in the emulator | two instructions of gap | 7, 12 |

armips does not see a load delay that reaches the use through a branch (Ch 7). The emulator does not model the GTE
write delay, so missing `nop`s before a GTE command pass in the emulator and may fail on hardware (F.8).

## F.7 The PSn00bSDK 0.24 clobber defect (`$t0` / `$t1`)

**What is wrong.** `gte_SetRotMatrix`, `gte_SetTransMatrix`, `gte_SetLightMatrix` and `gte_SetColorMatrix` load their
words through `$t0` and `$t1` (and `$t2`) but declare only `$t2` as clobbered. You can read it in
`.toolchain/opt/psn00bsdk/include/libpsn00b/inline_c.h`: the asm bodies start `lw $t0, 0(%0); lw $t1, 4(%0)` and the
clobber list is `: "$t2"`. A value the compiler keeps in `$t0` or `$t1` across the macro is silently destroyed.

**Symptom.** Typically a crash through a garbage pointer (an address error, F.5) far from the cause, or a loop counter
or pointer that changes. Whether it happens depends on register allocation, so code that works can break after an
unrelated edit, or between `-O1` and `-O2`.

**Remedy.** Call the four macros only from a function marked `noipa`, as the book's `load_matrix()` does (given in
Chapters 25 and 26, used in 27 to 41):

```c
static __attribute__((noipa, unused)) void load_matrix(const MATRIX *m)
{
    gte_SetRotMatrix(m);
    gte_SetTransMatrix(m);
}
```

Plain `noinline` is **not** enough. With GCC's `-fipa-ra` (on at `-O2`) the caller inspects which registers the
compiled callee uses, does not see the undeclared ones, and keeps its own values in `$t0`/`$t1` across the call.
`noipa` forbids that analysis, so the caller must assume every temporary register is lost.

The other setters are safe: `gte_SetGeomOffset` declares `$t0`/`$t1`, `gte_SetBackColor` declares `$t0..$t2`,
`gte_SetFarColor` and `gte_SetTransVector` declare the registers they use.

## F.8 GTE problems

| Symptom | Cause | Chapter |
|---|---|---|
| **CPU exception 12 (arithmetic overflow)** in `camera_look_at` or any `VectorNormalS` call | `VectorNormalS` loads each component into a 16-bit `IR` register (wraps outside +-32767) and sums the squares with MIPS `add`, which **traps** at 2^31 (all three components near 26,800). `target - eye` can be 32,000 per component. Shift the input right until the largest component is at most 8192 (a direction survives a shift). An all-zero vector returns garbage. Accuracy is about 0.8%: add a Newton step | 28 |
| Geometry flickers or explodes near the camera | Divide overflow: `H >= 2 * SZ3`, so the vertex is closer than `H/2` or behind the camera. `FLAG` bit 17 (and bit 31). The result is saturated, not garbage; skip vertices with a small `SZ` | 25, 34 |
| `FLAG` shows bit 12 | `IR0` saturated by `InitGeom`'s `DQA`/`DQB`. Normal; not part of bit 31 | 25 |
| `FLAG` bits 13/14 | `SX2`/`SY2` saturated to -1024..1023: the point is far off screen | 25 |
| `FLAG` bits 18, 31 on `AVSZ` | `OTZ` clamped; the depth is out of range | 25 |
| Flags always zero | `FLAG` is cleared by **every** command: read it right after the command (`gte_stflg`), OR across commands yourself | 25 |
| All objects use the first object's matrix | One upload for everything. Upload per object with `load_matrix` | 26 |
| `RotMatrix` appears to ignore your `PopMatrix` | `RotMatrix` pushes and pops the library's single slot itself | 26 |
| Garbage projections that change with optimization level | `gte_ld*` has no `"memory"` clobber, so the compiler may not have finished the stores to the vertex (a local `SVECTOR`, or a global you just wrote). Put `__asm__ volatile("" ::: "memory");` before any `gte_ld*` that reads something you just wrote | 34, 35, 36 |
| Wrong results after `RTPT` | `SZ0` is the *old* depth; the new ones are `SZ1..SZ3`. `IR`/`MAC` hold the last vertex only | 27 |
| Corrupts the next cube's slot | `gte_stsxy3c(&xy[6])` writes `[8]` too. Store two words in the last batch, or overlap the batches | 27 |
| `gte_ldsxy3` loads garbage | It takes three values, not pointers; `gte_ldv0` takes a pointer | 25 |
| Right in the emulator, wrong on hardware | Dropped `nop`s: the emulator does not model the write delay. Keep two instructions between the last write and a command (use the macros, or the `_b` form with two instructions of your own) | 27 |
| Right on the shipped track, wrong on another | Camera in `TR` with absolute vertices wider than `s16`; subtract in `int32_t`, then narrow; a vertex with any `|d|` > 32767 is far and must be skipped, not truncated | 34, 33 |
| Back-face culling culls the wrong side after changing the camera | A mirrored matrix (determinant -1: two rows or two operands swapped) | 28 |
| Wrong result from a hand-made `OP` | `OP` needs a vector in the `RT` diagonal and overwrites the matrix you loaded; its `IR` results saturate at 16 bits | 28 |

## F.9 CD loading failures

| Symptom | Cause | Chapter |
|---|---|---|
| `CdSearchFile` returns `NULL` | Path form: `\DATA\MODEL.BIN;1`, leading backslash, backslashes (doubled in C), upper case. 0.24's `CdSearchFile` rejects lower case and `/` despite its header | 29 |
| Nothing found though the file exists | `source` paths in `iso.xml` are relative to the **build directory**, not the XML file; or the file is not on the disc image the run booted | 29 |
| Read returns but the data is wrong or the heap is trashed | The drive writes whole sectors: allocate `ceil(size / 2048) * 2048`; `*size` is the directory's byte count | 29 |
| Freeze | A blocking `CdReadSync(0, 0)` waits as long as the drive struggles. 0.24 has a watchdog (about 180 vblanks, 3 s; it acts only while you call `CdReadSync`), but poll, count frames and give up. `CdReadRetry` retries | 29 |
| Fails right after start-up | `CdInit` before `ResetGraph`: the CD library needs the interrupt system `ResetGraph` sets up | 29 |
| Passes on your disc, fails the verifier's | Model compiled in, or a hard-coded placement; the verifier swaps the file | 29, 30 |
| Texture upload garbage | `LoadImage` is asynchronous: `DrawSync(0)` before freeing the file or blob | 30, 31, 35 |
| Texture lands in the framebuffer | Placement inside x < 320, y < 480; take the rectangle from the layout, not the TIM's own defaults | 30, 35 |
| Music silent after a disc read | A read resets the drive: restart the track (`CdlPlay`), and set `CdMix` again | 39, 40 |
| Music silent from the start | Any of three at zero: the drive's matrix (`CdMix`), the SPU's CD volume (`SpuSetCommonCDVolume`), `SPU_CTRL` bit 0. No error is raised | 39 |
| Freeze or crash in a CD callback | Calling the CD library from the callback: set a flag and act in the main loop | 39 |
| `CdlModeRept` does not loop | It only reports positions; restart from the auto-pause callback | 39 |
| Booting a `.cue` is slow in a probe | About 310 emulated frames before `main`; allow `max_frames >= 600` | verify-lib |
| Wrong region/disc behavior | The disc region lock (SCEx string) is read by the drive controller and no CD-R carries it; emulators ignore it. Not a software bug | 42 |

## F.10 Debugging, breakpoints and cycle counts

* **Breakpoints that never fire** need `-interpreter -debugger`. With the dynarec running, or without `-debugger` (or the
  GUI checkbox), breakpoints silently do nothing (Ch 6; `tools/verify-lib/README.md`). The harness always passes both.
* Keep the object `PCSX.addBreakpoint` returns in a **global**: otherwise it is garbage-collected and the breakpoint
  vanishes after a while. Return `false` from the callback for a one-shot.
* An exec breakpoint stops **before** the instruction runs: registers show the state before it. Do not break on
  `done:`; it loops forever.
* **Cycle counts mean something only under `-interpreter`** (2 cycles per instruction, flat). The default dynarec
  counts per translated block and its numbers for short code are meaningless (Ch 27). Your numbers are the
  emulator's, not hardware's.
* `break_at` needs a real out-of-line function. At `-O2` an empty helper is inlined and `-gc-sections` drops its symbol;
  declare it `__attribute__((noinline))` with `asm volatile("" ::: "memory")`. `-gc-sections` also removes globals
  nobody reads: reference every symbol a check requires (`(void)x`) (Ch 18, 24).
* One source line may be two instructions: trust the disassembly (`mipsel-none-elf-objdump -d -z`). Inserting one
  instruction moves every later address: record addresses after your last edit (Ch 6).
* Compile one file to assembly: `mipsel-none-elf-gcc -O2 -S -ffreestanding -march=r3000 -msoft-float -fno-pic -mno-abicalls f.c`.

## F.11 Disk, temp files and headless runs

* Each verify run makes a temp directory `ps1book-chNN-XXXXXXXX` under `$TMPDIR` (default `/tmp`), holding the build,
  the program, screenshots and logs. It is deleted on exit unless you pass `--keep` (or set `PS1BOOK_KEEP`), so
  repeated `--keep` runs fill the disk. If `/tmp` is small or under a quota, point `TMPDIR` at a larger directory.
  (A full disk was not tested, so no message is quoted here.)
* `tools/ci.sh` writes its logs to a `mktemp -d` that it removes on exit, and runs every chapter twice (solution, then
  starter), each run using the temp space described above.
* Headless: the harness passes `-cli -testmode`. No X server or `xvfb-run` is needed, a 30-frame run takes about a
  second, and `-testmode` plus explicit `-memcard1/2` keeps it from creating files under `~/.config/pcsx-redux`.
* The toolchain is about 1 GB under `.toolchain/`; `tools/setup.sh --force` reinstalls.
* Wrap anything you script around the tools in `timeout`: a program that waits on hardware the emulator never
  answers is stopped by the harness at 20 s, but a command you run yourself is not.
* A hung program before `done:` fails after the 20 s timeout; a long probe can raise it with `config(timeout=...)`.

## F.12 Build errors in the C chapters

| Error | Cause |
|---|---|
| `undefined reference` to your asm routine | `rgb555.s` not listed in `CMakeLists.txt`, or no `.globl` (Ch 18) |
| `undefined reference` to a function in a header | Declared, never defined; it links until you call it (Ch 19). Or a `static`, or a library listed before the objects that need it (Ch 21) |
| Multiple definition | A definition in a header, or a shared variable without `extern` (Ch 21) |
| A header vanishes | A copied include-guard macro (Ch 21) |
| `.align 4` is 16 bytes in gas | Use `.balign 4` or `.align 2` (Ch 18) |
| `RotTransPers`, `SetGeomOffset`, `NormalClip` undeclared | They do not exist in PSn00bSDK 0.24. See Appendix G |
| `<stdint.h>` not found compiling by hand | add `-ffreestanding` |

Related: [Appendix D](D-gte-reference.md) (the GTE), [Appendix G](G-psyq-to-psn00bsdk.md) (names).
