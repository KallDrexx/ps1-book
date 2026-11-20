# PlayStation Programming from the Metal Up
### A guided curriculum in MIPS assembly and C for the Sony PlayStation (PS1)

---

## 1. Project Overview

This repository will hold a self-paced textbook that teaches one reader to write original software for the Sony PlayStation and run it on PS1 emulators (and, optionally, real hardware). The reader can already program (if/else, loops, functions) but has no experience with assembly language, console hardware, or 3D graphics.

The curriculum follows the scope and order of Pikuma's *PS1 Programming with MIPS Assembly & C* (https://pikuma.com/courses/ps1-programming-mips-assembly-language). It starts with bare-metal MIPS assembly that writes directly to hardware registers. It then moves to C with a PS1 SDK, covers 3D rendering with the Geometry Transformation Engine (GTE), loads assets from CD-ROM, and ends with a complete 3D anti-gravity racing game.

**Design principles**

1. **One concept per chapter.** Every chapter states one central concept and teaches only what is needed to understand and use it.
2. **Learning by building.** Every chapter ends in a project the reader implements themselves, starting from a provided starter skeleton.
3. **Machine-checked mastery.** Every chapter ships a `verify` script. The script builds the reader's code, runs it headless in an emulator, and objectively checks that the concept was implemented correctly. Passing `verify` is the definition of "done" for a chapter.
4. **Cumulative.** Later chapters build on earlier code. Parts end in small capstones, and the book ends in one large capstone.
5. **Original work only.** The reference course builds its final project with assets and file formats from a commercial game. **This book does not.** The capstone, *Hoverline*, is an original anti-gravity racer. Its ship models, textures, track, and binary file formats (`.SHP`, `.TPK`, `.TRK`) are designed by this book, and its assets come from book-provided generator scripts. The engineering lessons (LZSS-compressed texture packs, sectioned track geometry, subdivision, ship physics, track collision) are preserved one-for-one.
6. **Linux-first, cross-platform toolchain.** All tools are free and open source and run on Linux (the reader's platform). macOS and Windows work too. No emulated Windows XP and no proprietary Sony SDK are needed.

---

## 2. Toolchain (canonical choices)

Authoring agents must use these tools consistently across all chapters. Pin exact versions in `tools/versions.txt`, and check current install instructions and CLI flags against each project's upstream docs at authoring time.

| Role | Tool | Notes |
|---|---|---|
| Assembler (Parts I–III) | **armips** | `.psx` (selects the R3000 instruction set only; it emits **no** PSX-EXE header) / `.create` / `.org` / `.include` directives. The 2 KB header comes from the book's `common/psxexe.inc`. `-sym` emits symbol files that the verification harness uses. |
| C compiler (Parts IV–VII) | **GCC cross-compiler `mipsel-none-elf`** (binutils + gcc) | Built by the PSn00bSDK toolchain instructions or installed from a distro or prebuilt package. |
| SDK (Parts IV–VII) | **PSn00bSDK** | Open source. Its APIs mirror Sony's `libgpu`/`libgte`/`libetc`/`libcd`/`libspu` names (`ClearOTagR`, `PutDrawEnv`, `RotMatrix`, …), so the concepts carry over to the original SDK. Exception: 0.24's `libpsxgte` has only the matrix/vector routines (`InitGeom`, `RotMatrix`, `TransMatrix`, `MulMatrix`, `CompMatrixLV`, `PushMatrix`, `VectorNormalS`, `isin`, …); the old per-vertex wrappers (`RotTransPers`, `RotTransPers3`, `RotAverageNclip4`, `NormalClip`, `SetGeomOffset`, `SetRotMatrix`, …) do not exist, and their work is done with the `gte_*` macros of `<inline_c.h>` (Ch 25, Appendix G). Uses CMake. |
| Primary emulator & debugger | **PCSX-Redux** | Integrated debugger, VRAM viewer, GPU logger, and a Lua scripting API. Its headless/test mode drives every `verify` script. |
| Secondary emulators | **DuckStation**, **Mednafen (Beetle PSX)** | Cross-checked in Chapter 6 and in the final chapter. |
| CD image builder | **mkpsxiso** | Builds `.bin/.cue` images from an XML layout. |
| Texture tools | **book-provided Python `img2tim.py`** (and optionally `img2tim`/TIMedit) | Converts PNG to TIM (4/8/16 bpp with CLUT). |
| Audio tools | **book-provided `wav2vag.py`** (or PSn00bSDK/`psxavenc`) | WAV to VAG (SPU ADPCM). Optionally XA/CD-DA for music. |
| Host scripting | **Python 3.10+** | Asset generators, file-format packers, verification logic. |
| Headless display | **xvfb-run** (Linux) | Lets PCSX-Redux run inside `verify` without a visible window when needed. |

`tools/setup.sh` installs or locates all of the above and runs `tools/doctor.sh`, a self-check. A `Dockerfile` gives a fully reproducible environment.

---

## 3. Repository & Chapter Layout (convention for authoring agents)

```
ps1-book/
├── Summary.md                  # this file
├── README.md                   # how to use the book
├── tools/
│   ├── setup.sh, doctor.sh, versions.txt, Dockerfile
│   ├── verify-lib/             # shared verification harness (see §4)
│   │   ├── harness.py          # build → run emulator → collect results → report
│   │   ├── redux.lua           # Lua helpers loaded into PCSX-Redux
│   │   ├── symbols.py          # parse armips .sym / ELF symbols (nm)
│   │   └── image.py            # screenshot / VRAM comparisons with tolerances
│   └── assets/                 # generators + selftest (see its README): img2tim.py, tim.py, lzss.py, tpkpack_ref.py, shpgen.py, trkgen.py, scenegen.py, texgen.py, wav2vag.py, vag2wav.py, vag.py, sfxgen.py, formats.py, layout.py, examples.py, mkassets.py, selftest.py
├── common/                     # shared code: psxexe.inc (Parts I–III); psxe/ (C engine library, the Ch 21 reference, copied into later chapters)
├── appendices/
│   ├── A-mips-cheatsheet.md
│   ├── B-memory-map-and-io-registers.md
│   ├── C-gpu-command-reference.md
│   ├── D-gte-reference.md
│   ├── E-file-formats.md       # PSX-EXE, SYSTEM.CNF, TIM, VAG, LZSS, MODEL.BIN, .SHP, .TPK, .TRK, SCENE.BIN (written; the generators are tested against it)
│   └── F-troubleshooting.md
└── parts/
    └── part-NN-slug/
        ├── README.md           # part intro: theme, goals, what you'll build
        └── chNN-slug/
            ├── README.md       # the chapter text
            ├── starter/        # what the reader begins with (compiles, but incomplete)
            ├── solution/       # reference solution (kept spoiler-hidden; used to test verify)
            ├── verify/
            │   ├── verify.sh   # entry point: ./verify.sh [path-to-reader-project]
            │   ├── checks.py   # chapter-specific assertions
            │   └── probe.lua   # chapter-specific emulator probe (optional)
            ├── example/        # the runnable worked example (optional; not checked by verify/CI)
            └── quiz.md         # 5–10 self-check questions with answers in <details>
```

**Every chapter `README.md` follows this template:**

1. **Concept** – one or two sentences naming the single big idea.
2. **Why it matters** – motivation tied to real PS1 games and hardware.
3. **Learning objectives** – 3–6 measurable bullets.
4. **Prerequisites** – the earlier chapters it builds on.
5. **Explanation** – prose, diagrams (ASCII or SVG), annotated code, and hardware register tables.
6. **Worked example** – a small, complete, runnable program that shows the concept.
7. **Project** – the specification the reader implements: requirements, constraints, hints, and stretch goals.
8. **Verification** – how to run `verify.sh`, what each check means, and what typical failure messages indicate.
9. **Common pitfalls** – especially delay slots, alignment, endianness, and fixed-point overflow.
10. **Quiz** – a link to `quiz.md`.
11. **Further reading** – psx-spx (nocash PSX specs), PSn00bSDK docs, PCSX-Redux docs.

---

## 4. Verification Harness Specification

All `verify.sh` scripts are thin wrappers around `tools/verify-lib/harness.py`. Its contract:

1. **Build.** Run the reader's build (`make`, `armips`, or `cmake --build`). A build failure produces a clear message, and the script exits with code 1.
2. **Static checks (optional, per chapter).** Examples: required symbols exist (from armips `-sym` output or `mipsel-none-elf-nm`), a forbidden construct is absent (e.g. "no `mul` pseudo-instruction" in Ch 12), the PSX-EXE header is valid, an ISO contains the required files.
3. **Run.** Launch PCSX-Redux headless with the built `.ps-exe` (or `.cue`), loading `redux.lua` plus the chapter's `probe.lua`. The probe can:
   - set a breakpoint on a symbol (e.g. `done`, `frame_end`) and read registers/RAM when it is hit;
   - let N frames elapse and then capture a screenshot / framebuffer;
   - inject controller input on given frames (to test pad handling);
   - read RAM structures at symbol addresses (e.g. a `results` block the starter declares);
   - count executed instructions or cycles between two symbols (for performance chapters).
   The probe writes a JSON result file and quits the emulator with an exit code. There is a hard timeout (default 20 s) so an infinite loop counts as a failed check, not a hang.
4. **Assert.** `checks.py` loads the JSON and runs named checks. Each check prints `PASS`/`FAIL` with a human-readable explanation (expected vs. actual, and a hint).
5. **Report.** The final line is `CHAPTER NN: PASSED (k/k checks)` or `FAILED`. The exit code is 0 only if every check passed.

**Robustness rules:**
- Image checks sample specific pixels or regions with color tolerance, or use perceptual hashes. They never require byte-identical screenshots, because emulator versions differ.
- For parts with no rendered output (I–II), the starter code provides a labelled `results:` data block and a `done:` label (an infinite loop). The harness breaks at `done` and inspects `results`.
- `verify.sh --solution` runs the harness against `solution/`. CI uses this to prove every verify script passes on the reference solution and fails on the untouched starter.

---

## 5. Parts and Chapters

The book has **8 parts, 42 chapters**. Course-section mapping is shown as *(Pikuma §N)*.

---

### Part I — The Machine and Its Language
**Theme:** What a PlayStation is, how its R3000A CPU sees memory, and how to write, assemble, run, and debug a first MIPS assembly program.
**Part outcome:** The reader can write small assembly programs, package them as PSX-EXE files, and inspect their behavior in a debugger.

#### Chapter 1 — The PlayStation and Your Workbench *(Pikuma §1–2)*
- **Concept:** The PS1 is a small set of cooperating chips (CPU, GTE, GPU, SPU, MDEC, CD-ROM, DMA) built around a 33.8688 MHz MIPS R3000A. Development means cross-compiling on a PC and running the result in an emulator.
- **Covers:** Console history and the 1994 market context. Hardware block diagram. The cross-development workflow. Installing armips, the MIPS GCC toolchain, PSn00bSDK, PCSX-Redux, mkpsxiso, and Python. Running `tools/doctor.sh`.
- **Project:** Set up the workbench. Assemble the provided "hello, VRAM" program, which fills the screen with one color, and run it in PCSX-Redux. Then change the color constant.
- **Verification:** `doctor.sh` confirms every tool is installed and the right version. The harness runs the reader's modified program and checks that the screen color matches the value the reader chose (recorded in `color.txt`).

#### Chapter 2 — Memory, the Memory Map, and Endianness *(Pikuma §3)*
- **Concept:** The CPU sees one 32-bit address space. RAM, BIOS, scratchpad, and hardware I/O registers live at fixed addresses, mirrored through KUSEG/KSEG0/KSEG1. Multi-byte values are stored little-endian.
- **Covers:** What an ISA is. Bits, bytes, halfwords, words. Hex notation. The PS1 memory map (2 MB RAM at `0x80000000`, 1 KB scratchpad at `0x1F800000`, I/O at `0x1F801000`, BIOS at `0xBFC00000`). Cached vs. uncached segments. Little-endian storage. The MIPS–LSI relationship (the CPU is an LSI CW33300 core).
- **Project:** "Memory Cartographer." Use only `lui`/`ori`/`sw`/`sb`/`sh` (plus `lbu`/`lw`, the minimum loads for reading back, and `nop` for the load delay, which this chapter introduces ahead of Chapter 7) to write a given set of byte, halfword, and word values to specified addresses in a `results` block, including through KSEG1/KUSEG aliases and the scratchpad, then read the same words back byte-by-byte to prove little-endianness.
- **Verification:** The harness breaks at `done` and checks every byte of `results` against the expected little-endian layout. Watchpoints check each store's width and segment, and a perturbation run (source words changed just before they are read) proves the byte-extraction copies come from real loads.

#### Chapter 3 — Registers, Loads, Stores, and Arithmetic *(Pikuma §4)*
- **Concept:** MIPS is a load/store architecture. All computation happens in 32 general-purpose registers, and memory is touched only by explicit load and store instructions.
- **Covers:** Register names and conventions (`$zero`, `$at`, `$v0–1`, `$a0–3`, `$t0–9`, `$s0–7`, `$sp`, `$ra`). `lb/lbu/lh/lhu/lw`, `sb/sh/sw`, `add/addu/addi/addiu/sub/subu`. Immediates and their 16-bit limit. Overflow trapping (`add`) vs. wrapping (`addu`). armips syntax rules (labels, directives, comments, `.org`, `.word`, `.byte`).
- **Project:** "Register Calculator." Load operands from a data table, compute a list of required expressions (sums, differences, a 32-bit constant built from two halves), and store each result into `results`.
- **Verification:** Every result word is checked. A static check confirms the program assembles without warnings and uses only Chapter 2–3 instructions.

#### Chapter 4 — Control Flow: Branches and Jumps *(Pikuma §4)*
- **Concept:** Programs make decisions and loop by comparing registers and changing the program counter with branches (relative, conditional) and jumps (absolute).
- **Covers:** `beq/bne/blez/bgtz/bltz/bgez`, `slt/slti/sltu`, `j`. Building `if/else`, `while`, and `for` from these primitives. Loop counters and sentinels. An intro to the branch delay slot (fill it with `nop` for now; it is explained fully in Ch 7).
- **Project:** "Loop Lab." (a) Sum 1..N for N given in data. (b) Find the max and min of a word array. (c) Fill a 64-entry array with a sequence and count how many entries satisfy a condition.
- **Verification:** The results block is checked for several N/array values. The harness patches the input data in RAM before running, so hard-coded answers fail.

#### Chapter 5 — Anatomy of an Executable: The PSX-EXE Format *(Pikuma §4)*
- **Concept:** A PS1 program is a PSX-EXE: a 2 KB header that tells the BIOS where to load the code, where execution starts, and where the stack is, followed by the raw machine code.
- **Covers:** The header fields (magic `"PS-X EXE"`, initial PC, initial GP, load address, file size, stack base/size, region marker). Why armips' `.psx` emits no header, and how the book's `common/psxexe.inc` builds one from `.ascii`/`.word` directives (`.create "main.ps-exe",0x8000F800`, `.include "common/psxexe.inc"`, `.org 0x80010000`). How emulators side-load EXEs vs. how the BIOS boots from CD. Instruction encoding (R/I/J formats), and reading a hex dump as instructions.
- **Project:** (a) Write `exeinfo.py`, a host tool that parses and validates any PSX-EXE header and disassembles the first 16 instructions. (b) Build an EXE with a **hand-written header** (raw `.ascii`/`.word` directives written by the reader, without `common/psxexe.inc`) that loads at a non-default address and still runs.
- **Verification:** `exeinfo.py` is run against several provided EXEs, including malformed ones, and its output is compared with expected values. The reader's hand-built EXE must pass header validation and reach `done` with the correct results.

#### Chapter 6 — Emulation and Debugging *(Pikuma §5)*
- **Concept:** An emulator is a debugger with x-ray vision. Stepping, breakpoints, and memory/register watches turn invisible machine state into something you can inspect.
- **Covers:** How emulators work (interpreter vs. dynarec, accuracy tradeoffs). Comparing PCSX-Redux, DuckStation, and Mednafen. The PCSX-Redux debugger: step into/over, breakpoints (exec/read/write), memory editor, register view, disassembly. Pseudo-instructions (`li`, `la`, `move`, `nop`, `b`, `bge`…) and what armips expands them into. Using `$at`. A first PCSX-Redux Lua script.
- **Project:** "Bug Hunt." The starter has three buggy programs: an off-by-one loop, a wrong pseudo-instruction expansion assumption, and a clobbered `$at`. Find and fix each bug, record the faulting address in `findings.txt`, and write a short Lua script that prints a register every time a breakpoint hits.
- **Verification:** All three fixed programs produce correct results. `findings.txt` names the correct instruction addresses. The reader's Lua script is run and its output must contain the expected register trace.

---

### Part II — Thinking Like the R3000
**Theme:** The quirks and conventions that make MIPS code correct and fast: the pipeline, delay slots, subroutines, signed arithmetic, the stack, alignment, and the RISC philosophy.
**Part outcome:** The reader writes reusable, ABI-compliant assembly routines and can reason about each instruction's cost.

#### Chapter 7 — The Pipeline and Delay Slots *(Pikuma §6)*
- **Concept:** The R3000A overlaps five pipeline stages. As a result, the instruction after a branch always executes (branch delay slot), and a loaded value is not ready for the very next instruction (load delay slot).
- **Covers:** The IF/RD/ALU/MEM/WB stages. Hazards. Branch delay slot semantics. The R3000 load delay slot and why the next instruction sees the *old* value. Filling delay slots with useful work. armips never reorders and has no `.set` directive (it behaves like GNU `as` under `.set noreorder`, which appears in compiler output); its load-delay warning only compares consecutive lines. `multu`/`mflo` (the HI/LO interlock).
- **Project:** "Factorial, Tightly." Compute `n!` iteratively for several inputs. Then make a second version with every delay slot filled by a useful instruction (no `nop` in delay slots).
- **Verification:** The results are correct for all inputs (patched at runtime). A static check on the disassembly confirms that the optimized routine has zero `nop`s in delay slots. An instruction-count probe confirms it runs in fewer instructions than the first version.

#### Chapter 8 — Subroutines *(Pikuma §7)*
- **Concept:** `jal` saves a return address in `$ra` and `jr $ra` returns to it. Together with an agreement on which registers carry arguments and results, this lets code be reused as functions.
- **Covers:** `jal`, `jalr`, `jr`. Arguments in `$a0–$a3`, results in `$v0–$v1`. Caller-saved vs. callee-saved registers. Leaf vs. non-leaf routines. Why calling a function from a function breaks `$ra`.
- **Project:** Turn factorial into a `factorial(a0) -> v0` subroutine, plus `sum_array(a0=ptr, a1=len)` and `max_array`. Write a test-driver `main` that calls each one several times and stores the results.
- **Verification:** The harness calls the reader's subroutines directly. It sets `$a0/$a1` and the PC to the routine symbol with a breakpoint on a return trampoline, then checks `$v0` and that callee-saved registers (`$s0–$s7`, `$sp`) are unchanged.

#### Chapter 9 — Signed Numbers, Logic, and Bit Shifting *(Pikuma §7)*
- **Concept:** The same 32 bits mean different numbers depending on interpretation. Two's complement, sign extension, masking, and shifts are how low-level code packs, unpacks, and transforms data.
- **Covers:** Two's complement. `lb` vs `lbu`, `lh` vs `lhu`. Sign extension of immediates. `and/or/xor/nor/andi/ori/xori`. `sll/srl/sra/sllv/srlv/srav`. Masks and bitfields. Multiply and divide by powers of two (and the arithmetic-shift rounding trap for negative numbers).
- **Project:** "Bit Toolkit." Implement `abs`, `sign_extend(value, bits)`, `popcount`, `rgb888_to_bgr555` (the PS1 15-bit color format), `bgr555_unpack`, and `swap_endian32` as subroutines.
- **Verification:** Each routine is called with a battery of edge cases (0, -1, `0x80000000`, max values, random values) and compared against Python reference implementations.

#### Chapter 10 — The Stack and the MIPS ABI *(Pikuma §10)*
- **Concept:** The stack is a region of memory that grows downward from `$sp`. Functions reserve frames on it to save `$ra` and callee-saved registers, to spill locals, and to receive arguments beyond the first four, all following the O32 ABI.
- **Covers:** Stack frames, prologue/epilogue. Saving `$ra` for nested calls. The O32 rule that the caller reserves 16 bytes of argument home space. Passing a 5th+ argument on the stack. Stack vs. heap vs. static data in the PS1 memory map. Recursion.
- **Project:** Write recursive `factorial`, recursive `fibonacci`, and `sum6(a,b,c,d,e,f)` (two arguments on the stack). Each must be fully ABI-compliant.
- **Verification:** The results are correct. `$sp` is identical before and after each call. A probe tracks the minimum `$sp` reached and checks that the stack depth matches a valid frame size. Callee-saved registers are preserved. Calls are made from a harness-written C-ABI trampoline.

#### Chapter 11 — Data Layout and Memory Alignment *(Pikuma §11)*
- **Concept:** MIPS requires naturally aligned memory accesses (halfwords on 2-byte and words on 4-byte boundaries). Data layout decisions (variables, arrays, structs of vectors) must respect this.
- **Covers:** `.align`, `.word/.halfword/.byte` in data sections. Address-error exceptions on misaligned loads. Struct layout and padding (e.g. `SVECTOR {short vx, vy, vz, pad}`). Arrays of structs and computing element addresses. `lwl/lwr` for intentionally unaligned access.
- **Project:** "Vertex Table." Define an aligned array of 8 `SVECTOR`-style structs (a cube's corners), then write routines that translate all vertices by an offset, compute the bounding box, and copy the table to a packed 6-byte-per-vertex format using `lwl/lwr`/byte ops.
- **Verification:** The output tables are checked byte-for-byte. A symbol check confirms the struct table is 8-byte aligned. A negative test confirms the reader can explain (in `answers.md`, matched by keyword) why a provided misaligned load crashes.

#### Chapter 12 — RISC vs. CISC, Multiply and Divide *(Pikuma §8, §12)*
- **Concept:** RISC trades complex instructions for simple, regular, pipelinable ones. Understanding the cost of each instruction (especially `mult`/`div` and the HI/LO registers) shapes how PS1 code is written.
- **Covers:** CISC examples (x86, 68000) vs. RISC (MIPS, ARM). Instruction density vs. regularity. `mult/multu/div/divu`, `mfhi/mflo` and their timing hazards. Strength reduction: multiplying by constants with shifts and adds (e.g. ×320, ×1024 for VRAM addressing).
- **Project:** Implement `memcpy`, `memset`, and `strlen` as fast word-at-a-time routines with byte tails. Implement `mul320(x)` and `mul_by_const` variants with no `mult` instruction, plus `udiv10`.
- **Verification:** Correctness is checked against reference results on random buffers, including unaligned lengths. A static check bans `mult/div` in the shift-based routines. Instruction-count budgets are enforced (e.g. word-wise memcpy must use fewer than ⅓ of the instructions of a byte-wise loop on a 1 KB copy).

---

### Part III — Bare-Metal Graphics in Assembly
**Theme:** Driving the PS1 GPU directly by writing command packets to its hardware ports, with no SDK.
**Part outcome:** The reader can initialize the display, draw shaded polygons, upload images to VRAM, and animate a scene in pure assembly.

#### Chapter 13 — The GPU, VRAM, and Command Packets *(Pikuma §9)*
- **Concept:** The GPU is controlled through two 32-bit ports: GP0 (drawing and VRAM commands) and GP1 (display control). Every drawing operation is a packet of words, a command byte plus parameters, written to these ports.
- **Covers:** The 1 MB VRAM as a 1024×512 16-bit framebuffer. Display area vs. drawing area. GP1 commands (reset, display enable, display mode, display start, horizontal/vertical range). GP0 commands (draw mode, drawing area, offset, fill rectangle). GPUSTAT bits and waiting for "ready to receive command". How to look up packet formats in psx-spx. NTSC vs. PAL timings.
- **Project:** "Colour Bars." Write `gpu_init`, `gpu_clear(color, x, y, w, h)` (GP0 `02h` fill rectangle) and `gpu_rect(color, x, y, w, h)` (GP0 `60h` monochrome rectangle), with `h` as a fifth argument on the stack. Initialize a 320×240 NTSC 15-bit display, clear it with one fill, and draw 8 vertical 40-pixel bars from a colour table with `gpu_rect`. (Fill rectangle works in 16-pixel steps, so it cannot draw 40-pixel bars; the chapter teaches both commands and why they differ.)
- **Verification:** The routines are called directly with random arguments: the harness records every GP0/GP1 word (reset first, display mode, ranges, E1h/E3h–E5h, exact packet words, a GPUSTAT read before the first GP0 word) and diffs VRAM (fill rounded to 16 pixels and not clipped; `60h` pixel-exact and clipped to the drawing area). The real program then runs on the shipped and two patched colour tables; the screenshot must be 320×240 and every pixel of each bar and the border must match within tolerance.

#### Chapter 14 — Rendering Polygons *(Pikuma §10)*
- **Concept:** The GPU rasterizes triangles and quads from packets of vertex coordinates and colors. Flat shading uses one color per polygon, and Gouraud shading interpolates a color per vertex.
- **Covers:** GP0 `0x20` (flat triangle), `0x28` (flat quad), `0x30`/`0x38` (Gouraud). Vertex ordering for quads (Z-pattern). Semi-transparency bits. Drawing offset and clipping.
- **Project:** "Polygon Gallery." Draw a fixed composition: a flat triangle, a flat quad, a Gouraud triangle, and a Gouraud quad, at specified screen positions and colors.
- **Verification:** The screenshot is sampled at each polygon's centroid (flat color match), at each Gouraud triangle's vertices (color match), and at midpoints (interpolated color within tolerance). Background pixels must be untouched.

#### Chapter 15 — Drawing Subroutines and Stack Parameters *(Pikuma §10)*
- **Concept:** Reusable drawing routines need more than four arguments. This chapter puts the ABI from Ch 10 to work: the extra polygon parameters travel on the stack.
- **Covers:** Designing `draw_flat_tri(color, x0,y0, x1,y1, x2,y2)` (seven arguments, three of them on the stack). Packing x/y into one word (`(y<<16)|x`). Stack and heap usage within the PS1 memory map. Avoiding redundant GPU-ready waits.
- **Project:** Implement `draw_flat_tri`, `draw_flat_quad`, and `draw_gouraud_tri` as ABI-compliant routines. Use them to draw a scene of at least 20 polygons from a data table (a "low-poly landscape").
- **Verification:** The harness calls each routine with harness-chosen parameters (via the Ch 10 trampoline) and samples the screenshot. ABI checks confirm `$sp`/`$s*` are preserved. The scene from the data table is verified by sampled pixels.

#### Chapter 16 — Copying Data to VRAM *(Pikuma §12)*
- **Concept:** VRAM is not memory-mapped to the CPU. Image data is moved into it with a GP0 "CPU→VRAM" transfer command followed by a stream of pixel words, at 16 or 24 bits per pixel.
- **Covers:** GP0 `0xA0` (copy rectangle CPU→VRAM). Pixel packing (two 16-bit pixels per word). Computing pixel addresses with shifts (Ch 12). 24-bpp display mode and its 3-bytes-per-pixel layout. `.incbin` for embedding raw images.
- **Project:** "Picture Show": write `vram_upload(ptr, x, y, w, h)` (fifth argument on the stack) and `bpp24_halfwords(px)` (`px*3/2` with shifts). One program with a `mode` data word: mode 0 embeds a provided 16-bpp image (`.incbin`) and displays it on a cleared background; mode 1 switches to 24-bpp mode and displays a provided 24-bit image full-screen (a 480x240-unit upload).
- **Verification:** The probe calls `vram_upload` directly with harness-chosen buffers and rectangles (odd widths and pixel counts, VRAM right/bottom edges, never crossing them) and reads VRAM back through the PCSX-Redux API: the rectangle must match exactly (uploads are lossless) and nothing outside may change. The real program runs in both modes on the shipped and on patched images (random pixels, other size/place); the 24-bpp run must write GP1(08h) with bit 4 set and its screenshot must show the image.

#### Chapter 17 — Part III Capstone: Animation in Assembly *(extension)*
- **Concept:** Animation means redrawing in sync with the display. Waiting for vertical blank and double-buffering the drawing area prevent tearing.
- **Covers:** VBlank via the interrupt status register `I_STAT` (polling, no handler yet). Two framebuffers in VRAM and swapping the display start each frame. Frame counters. Simple velocity/position updates.
- **Project:** "Bouncing Gem." A Gouraud-shaded diamond bounces around the screen, reflecting off the edges, with a frame counter displayed as a bar graph. Written entirely in assembly.
- **Verification:** Three 150-frame runs (the shipped `gem_state` and two patched starting states). The probe records `gem_state` at every loop iteration and every VBlank, and every GP0 `E3h` / GP1 `05h` write. Each step must follow the exact clamp-and-negate rule, with bounces on both axes; the loop must advance once per VBlank (a few missed VBlanks tolerated); each iteration must set the drawing area to the back buffer and write the display start exactly once, to the buffer just drawn, alternating 0/240. Screenshots at two frames show the shaded gem at the recorded position, a cleared background, and a bar matching the frame counter.

---

### Part IV — C on the PlayStation
**Theme:** Moving from hand-written assembly to C with PSn00bSDK, and learning the SDK's rendering model: double buffering, primitives, and ordering tables.
**Part outcome:** The reader structures a multi-file C project that renders depth-sorted 2D scenes and responds to controller input.

#### Chapter 18 — From Assembly to C *(Pikuma §13)*
- **Concept:** A C compiler generates the same MIPS code the reader has been writing. An SDK wraps the hardware, and the two worlds interoperate through the ABI.
- **Covers:** Why games moved to C. History of Sony's PsyQ SDK and its open replacement PSn00bSDK (and how names map). The cross-compiler, linker scripts, startup code (`crt0`), and CMake. Reading the compiler's generated assembly (`-S`, `objdump -d`). Calling an assembly routine from C and back.
- **Project:** Build a C program that initializes the display with the SDK, clears the screen, and calls the reader's `rgb888_to_bgr555` from Ch 9 (linked as an `.s` file) to compute the clear color. Inspect the compiler's output for a small function and annotate it in `annotated.s`.
- **Verification:** The project builds with CMake. The ELF exports `main` and links the reader's assembly symbol. The screenshot is the expected color. A check confirms `annotated.s` exists and references the correct function.

#### Chapter 19 — Double Buffering with Display and Draw Environments *(Pikuma §14)*
- **Concept:** The SDK models the screen as a pair of display/draw environments. The program draws into one buffer while the other is shown, then swaps them at VBlank.
- **Covers:** `DISPENV`/`DRAWENV`, `SetDefDispEnv`, `SetDefDrawEnv`, `PutDispEnv`, `PutDrawEnv`, `VSync`, `DrawSync`, `SetDispMask`. Background clear via `isbg`. PSn00bSDK integer types (`int16_t`, `u_long` legacy names).
- **Project:** Write `display.c`/`display.h` with `display_init()`, `display_clear(r, g, b)` (set the back buffer's `isbg` colour and `PutDrawEnv` it) and `display_swap()` (`DrawSync`, `VSync`, `PutDispEnv` of the buffer just drawn, flip). Animate a background color that cycles through hues (`hue`/`hue_step` state, a stated six-segment table), and draw a `TILE` (via `DrawPrim`, a stopgap until Ch 20) that moves 1 pixel per frame.
- **Verification:** Three runs (shipped state and two patched `hue`/`hue_step`/`rect_x` states). A probe records the state at every display-start write from `display_swap()`: the state must follow the stated update rules, the display start must alternate 0/240 (frame n from buffer n mod 2), once per VBlank. Screenshots at frames N and N+30 show the exact hue colour on a grid of background points (no tearing) and the rectangle at the recorded position, 30 px apart.

#### Chapter 20 — Primitives and Ordering Tables *(Pikuma §14)*
- **Concept:** The GPU draws in painter's order. The SDK gets depth ordering from an *ordering table*, an array of linked lists indexed by depth, through which primitives in a primitive buffer are DMA-chained to the GPU.
- **Covers:** Primitive structs (`POLY_F4` in the project; `POLY_F3`, `POLY_G3`/`G4`, `TILE`, `SPRT` tabulated), `setPolyF4`/`setRGB0`/`setXY4`/`setXYWH`, `addPrim`/`termPrim`/`setaddr`. A primitive buffer with a bump-pointer allocator (`ot_alloc`, NULL on overflow). `ClearOTagR` (DMA channel 6), `DrawOTag`. Reverse OTs and why index 0 is drawn last. DMA linked-list format (24-bit next pointer + 8-bit length byte, terminator `0x00FFFFFF`). Why one table + buffer per display buffer.
- **Project:** Given `ot.h` (`OT_LENGTH` 64, `PRIM_BUF_SIZE` 2048, `OtFrame ot_frames[2]` with 16 guard bytes each), write `ot.c` (`ot_begin_frame`, `ot_alloc`, `ot_add`, `ot_draw`) and `main.c`'s `draw_scene`/`advance`: render a shipped `scene` of 16 overlapping coloured quads (4×4 grid, distinct depths) as `POLY_F4`s through the OT, and animate every depth by `(depth + depth_step) % 64` per frame.
- **Verification:** Four runs (shipped scene, two patched scenes with new depths, permuted colours and `depth_step`, and `copies` = 20 for overflow). The probe breaks on `ClearOTagR`/`DrawOTag` and walks the DMA list from `DrawOTag`'s argument: the head is `&ot[63]` of a freshly cleared table, the two tables alternate, the 16 packets appear farthest-first each in slot `depth`, and they are consecutive 24-byte blocks from the frame's buffer. Overflow: no crash, guard bytes intact, at most 85 packets drawn. Screenshots: ~1,500 points (every overlapping pair included) show the nearest quad's colour.

#### Chapter 21 — Working with Multiple Files *(Pikuma §20)*
- **Concept:** Scaling a codebase means separating interface from implementation: header files declare, `.c` files define, and the build system compiles each one separately and links them together.
- **Covers:** Header guards, `extern` globals, `static` linkage, translation units, CMake targets, a reusable `common/` engine library. Designing small module APIs (display, ot, gfx, input).
- **Project:** The starter is Ch 19 + Ch 20 pasted into one `main.c`, plus the three `psxe` headers (API given, guards missing). Refactor it into a static library `psxe` (`display`, `ot`, new `gfx_quad_f4`) in `starter/psxe/{include/psxe,src}` with its own `CMakeLists.txt` (`PRIVATE psn00bsdk` only: linking `psxgpu` into it breaks the SDK's link order), plus a thin `main.c`. Worked example: `ar`/`nm` on the SDK's `libpsxgpu` (no `example/`). The reference library is kept in `common/psxe/` (`solution/psxe` must equal it); each later chapter ships its own copy in `starter/psxe` and `solution/psxe`.
- **Verification:** `libpsxe.a` exists; `nm` per archive member shows each module exports its API and otherwise only `module_*` names declared in its header (so non-`static` helpers/state fail). Headers have unique guards, compile alone/twice/together, define nothing. `main.c` ≤ 70 code lines, no `psxgpu` use, the only `.c` outside `psxe/`. Ch 20's dynamic checks (DMA-list walk, bump allocation, overflow guards, pacing, ~1,500 sampled screenshot points on two scenes) plus 16 `gfx_quad_f4` calls per frame.

#### Chapter 22 — Controller Input and the BIOS *(Pikuma §19)*
- **Concept:** The digital pad is read over a serial interface. The BIOS and SDK expose its state as a bitmask of pressed buttons, and edge detection turns that state into "pressed this frame" events.
- **Covers:** The BIOS (what it provides: boot, kernel calls via the `A0/B0/C0` tables, the interrupt handler, pad and memory-card services; OpenBIOS vs. Sony's). The SIO0 poll at byte level. The BIOS pad driver (`InitPAD`/`StartPAD`/`ChangeClearPAD`; PSn00bSDK 0.24 has no `PadInit`/`PadRead`, only the driver and `PADTYPE`/`PAD_*` definitions in `psxpad.h`), and the zeroed buffer before the first poll (check `stat` and `type`). Button bitmasks and active-low logic. Writing the `psxe` module `input.c/h` with `input_init()`, `input_update()` and pure queries `input_held()`, `input_pressed()`, `input_released()`. Worked example: a raw 16-bit pad viewer.
- **Project:** "Cursor." Move a 16 px square with the D-pad (`speed` px per frame, `fast` while holding Square; diagonals, opposites cancel), change its colour with X (on press, not hold), reset its position to `home` when Start is *released* (exercising `input_released`), and clamp it to the screen every frame. All numbers live in a starter-declared `cursor_state`.
- **Verification:** Static: `libpsxe.a` exports only the four modules' APIs, `input.o` references `InitPAD`/`StartPAD`, headers guarded, thin `main.c`. Four scripted runs through PCSX-Redux pad overrides (shipped numbers; patched speeds/home/colour; 40 px steps with a 32 px square against all four edges; a query run): `cursor_state` sampled every frame shows per-frame steps, one colour change per 30-frame X hold, home only after Start's release, clamping, no change before the first press; screenshots match the state. The probe also calls `input_held/pressed/released` directly every frame: pure, one-frame edges, "any" for multi-bit masks, 0 for an empty mask.

---

### Part V — Three Dimensions with the GTE
**Theme:** The math of 3D graphics in fixed-point, and the Geometry Transformation Engine coprocessor that does it in hardware.
**Part outcome:** The reader renders multiple transformed, back-face-culled 3D objects viewed through a controllable camera.

#### Chapter 23 — Fixed-Point Math *(Pikuma §17)*
- **Concept:** The PS1 has no floating-point unit. Fractional values are represented as scaled integers (the GTE uses 4.12 fixed point, where 4096 = 1.0), and every multiply needs a matching shift.
- **Covers:** A review of IEEE floats and why they are slow (soft-float) on PS1. Q-format notation. Fixed-point add/mul/div and overflow and precision tradeoffs. Rounding. Sine/cosine via the SDK (`isin`/`icos`, 4096 = 360°) and lookup tables. Can you use floats? (Yes, slowly; measure it.)
- **Project:** Write `fixed.h/.c` with `fx_mul`, `fx_div`, `fx_from_int`, `fx_lerp`, `fx_sqrt` (integer Newton's method), and a 2D rotation `fx_rotate(x,y,angle)`. Benchmark a float vs. fixed loop.
- **Verification:** The harness runs a test table (inputs generated by Python, results written to a `results` array) and compares with tolerance against Python references. It confirms the benchmark shows fixed-point running at least 5× faster than float.

#### Chapter 24 — 3D Projection Fundamentals *(Pikuma §15)*
- **Concept:** 3D rendering is a pipeline: model vertices → world (transform) → view → perspective divide by depth → screen. Meshes are vertex arrays plus face index lists.
- **Covers:** Coordinate systems (the PS1's Y-down convention). Rotation matrices around X/Y/Z, translation, scaling. Perspective projection `x' = x·h/z`. Vertex and face-index representation. Wireframe rendering with `LINE_F2`.
- **Project:** "Software Cube." On the CPU only (using Ch 23 fixed-point, no GTE), rotate and project a wireframe cube and draw its 12 edges with line primitives, spinning on two axes.
- **Verification:** The probe reads the projected 2D vertex array at fixed frames and compares it with Python-computed projections (±1 px). A static check confirms there are no GTE calls. A screenshot check confirms lines are drawn at the projected positions.

#### Chapter 25 — The GTE Coprocessor *(Pikuma §15–16)*
- **Concept:** The GTE (coprocessor 2) performs matrix × vector transforms, perspective division, and polygon normal tests in hardware, many times faster than the CPU.
- **Covers:** GTE architecture overview (COP2, data/control registers, the SXY/SZ FIFOs, `mtc2`/`cfc2`/`cop2`, command cycle counts and the CPU interlock). What PSn00bSDK 0.24 provides: `InitGeom`, `RotMatrix` (Rx·Ry·Rz), `TransMatrix`, `MATRIX`/`SVECTOR`/`VECTOR`, and the `<inline_c.h>` macros `gte_SetGeomOffset`, `gte_SetGeomScreen`, `gte_SetRotMatrix`, `gte_SetTransMatrix`, `gte_ldv0`, `gte_rtps`, `gte_stsxy`, `gte_stsz`, `gte_stflg`, `gte_ldsxy3`, `gte_nclip`, `gte_stopz`, `gte_ldsz4`, `gte_avsz4`, `gte_stotz`. The macro sequences that replace the classic `RotTransPers`/`NormalClip`/`RotAverageNclip4`. The matrix-upload macros are called only through the starter's `noipa` `load_matrix()` (they clobber `$t0`/`$t1` undeclared; Appendix F). `RTPS` outputs (screen XY, SZ, flags; the GTE divider and divide overflow). `NCLIP` sign vs. winding (positive = clockwise on screen = front-facing) and Z-order quad corners. `AVSZ4` (`ZSF4` = 256 from `InitGeom`, OTZ = ΣSZ/16) and OTZ → OT slot.
- **Project:** "Solid Cube." Rewrite the cube with the GTE as 6 flat-shaded quads (one color per face): one `RTPS` per corner, cull back faces with `NCLIP`, sort into the OT by `AVSZ4` (slot = OTZ >> 7), and spin it continuously.
- **Verification:** Static: the reader's own objects contain RTPS/RTPT, NCLIP and AVSZ3/4 commands and `main` calls no `fx_*` maths. The matrix must equal a Python port of `RotMatrix`; corners must equal a Python RTPS (psx-spx divider) of the reader's own matrix (±1 px, SZ exact). The ordering table is walked: 0–3 quads, exactly the faces with positive reference NCLIP (edge-on faces not judged), each in slot OTZ >> 7 (±1). Screenshots sample face centres and scan for hidden-face colours, over a spinning run, six frozen poses, a recoloured pose and patched lens/size/speeds. GTE flags show divide overflow for a cube around the camera. Frame time ≤ 2× the reference's worst frame.

#### Chapter 26 — Multiple Objects and Simple Motion *(Pikuma §17)*
- **Concept:** Each object has its own transform. Composing per-object rotation and translation with the GTE's matrix state lets one scene contain independently moving objects.
- **Covers:** Per-object `MATRIX` build (`RotMatrix`, `TransMatrix`) and upload (`gte_SetRotMatrix`/`gte_SetTransMatrix`). Saving and restoring GTE state (`PushMatrix`/`PopMatrix` or explicit). Fixed-point velocity and gravity. Collision with a ground plane. A floor made of a grid of quads.
- **Project:** "Bouncing Cubes." Three cubes of different sizes bounce under fixed-point gravity on a checkerboard floor, each spinning on a different axis.
- **Verification:** The probe samples cube positions (from an `objects` array) over 300 frames. Y must follow a parabolic bounce, never dropping below the floor, and each cube's rotation angles must change independently. The floor is verified by sampling alternating checker colors.

#### Chapter 27 — Batching GTE Work: RTPT and Timing *(Pikuma §18)*
- **Concept:** The GTE runs in parallel with the CPU, and its cost is mostly the loads, stores and waits around each command. Transforming three vertices per command (`RTPT`) and scheduling CPU work while a command runs makes a many-object scene fit in a frame.
- **Covers:** The GTE register map and formats (`VXY0..2`, `SXY0..2`/`SXYP`, `SZ0..3`, `MAC`, `IR`, `RT`, `TR`, `OFX/OFY/H`, `FLAG`). `lwc2/swc2` vs. `mtc2/mfc2`/`ctc2/cfc2`. Command timing (psx-spx: RTPS 15, RTPT 23, NCLIP 8, AVSZ4 6 cycles) and hazards: the interlock on reading a busy GTE or issuing a command, the one-instruction `mfc2`/`cfc2` delay, and the book's rule of two instructions between any `lwc2`/`mtc2`/`ctc2` and a command (psx-spx documents it for `lwc2`; the SDK macros' two `nop`s). Independent CPU work in the latency window, measured in PCSX-Redux's interpreter (2 cycles per instruction; hardware differs). Batched macros (`gte_ldv3c`, `gte_rtpt`, `gte_stsxy3c`, `gte_stsz3c`); plain `gte_rtpt()` is `nop; nop; cop2`, while the bare `gte_rtpt_b()` (65 `_b` macros in 0.24's `inline_c.h`) is only the command, so the reader schedules independent instructions into the two slots (a raw `cop2 0x0280030` is equivalent). Measuring with root counter 0 and with the verifier's cycle probe. The SDK's matrix-upload macros clobber `$t0`/`$t1` undeclared (see Appendix F).
- **Project:** "The 64-Cube Field": 64 cubes, each with its own matrix (built by given code), transformed by two paths selected by `path`: `RTPS` per corner (given, the Ch 25 code) and the reader's batched `RTPT` (reference: corners 0–2, 3–5, 5–7; alternatives 6, 7 + a pad vertex storing two words, or 2×`RTPT` + 2×`RTPS`). `field_cycles[]` reports each path's cycles.
- **Verification:** Static: `RTPT` in the reader's own objects, no command within two instructions of an `lwc2`/`mtc2`/`ctc2`, no floats. Both paths (patched into one build) must equal a Python RTPS (psx-spx divider) bit for bit for every cube, corner and frame, and each other, also for patched poses/camera/lens with saturation and divide overflow. Commands are counted at run time (path 1: ≥ 2 `RTPT` and ≤ 2 `RTPS` per cube). Path 1 must take at least 15 % fewer transform cycles than path 0 (reference 31 %, a looped variant 20 %); the program's root-counter timer must agree with the probe within 3 %; the frame must stay under 232,600 cycles (2× the reference); a screenshot finds all 64 tiles.

#### Chapter 28 — The Camera *(Pikuma §21)*
- **Concept:** A camera is the inverse of an object transform. The look-at construction builds a view matrix from an eye position, a target, and an up vector, and every object's world matrix is then composed with it.
- **Covers:** View space (camera at the origin looking +z, +y toward the screen's bottom). The view matrix as the transpose of the camera's axes: rows `right`, `down`, `forward` (Y-down, right-handed: `right = normalize(forward x up)`, `down = forward x right`, `up = (0,-1,0)` for a level camera), `t = -R·eye`. Degenerate rule: `|forward x up| < 1/32` (or `up = 0`) falls back to up = +z, then -y; `eye == target` looks along +z. Normalising in fixed point with `VectorNormalS` and its 0.24 limits (components through 16-bit `IR` registers; the sum of squares uses a trapping `add`, so ≥ 2^31 raises an arithmetic-overflow exception; table error up to ~0.8%): pre-shift to ≤ 8192 and one Newton step (`1.5 − 0.5|v|²`). The cross product on the CPU at full 2^24 scale (why not `OP`). `CompMatrixLV(&view, &world, &out)` (view first; `out.T` saturates at 16 bits). A pad-driven world-relative free-fly camera with a clamp box; crude near-plane rejection of floor tiles (`SZ < 256`). `MulMatrix0` is mentioned only for stretch goals; the project does not use it.
- **Project:** Implement `camera_look_at(eye, target, up)` (reads only its parameters, writes only `view_mtx`) and a flyable camera that always looks at the centre bouncing cube of the Ch 26 scene: RIGHT/LEFT move the eye ±x, UP/DOWN ±z, R1 lowers (+y), L1 raises (−y), `cam_speed` per frame, then clamped to `[cam_min, cam_max]`.
- **Verification:** The probe calls `camera_look_at` directly (~36 triples from a scratch buffer, so reading the globals fails; CPU exceptions are reported): each entry within 10/4096 of a float reference (8 + 2/sin near parallel), `t` within 3 of `-R·eye` of the reader's own rows, rows orthonormal (|row|² ±48/4096), det +1, degenerate fallbacks, callee-saved registers and arguments intact. Shipped and patched runs (300/230 frames, scripted pad): every frame `view_mtx` is the look-at of the recorded eye/target/up, the eye follows the movement rule exactly (clamps included), every cube face and floor tile is where the reference puts it through the reader's matrix (±3 px), the centre cube's pixel centroid is within 16 px of the screen centre in 14 screenshots, the physics is Ch 26's, and the frame takes ≤ 68,600 cycles (2× the reference).

---

### Part VI — Assets: CD-ROM, Textures, and Compression
**Theme:** Real games stream their data from disc. This part builds a CD image, loads binary files from it, parses them with correct endianness, textures polygons, and decompresses packed data.
**Part outcome:** The reader runs a game from a bootable CD image that loads compressed, textured 3D models designed in the book's own formats.

#### Chapter 29 — The CD-ROM and Loading Files *(Pikuma §22)*
- **Concept:** On real hardware, programs and data come from an ISO9660 disc. The program finds files by name, reads whole 2048-byte sectors into RAM buffers, and interprets those bytes as structured data.
- **Covers:** CD-ROM drive overview (sectors, modes, speeds). The `SYSTEM.CNF` boot file. Building a bootable image with mkpsxiso. `CdInit`, `CdSearchFile`, `CdRead`, `CdReadSync` (and the BIOS file API as an alternative). Heap initialization and `malloc` (`InitHeap`). Reading big- vs. little-endian integers byte by byte. The book's simple `MODEL.BIN` format (Appendix E.7: `MDL1` magic, big-endian counts, little-endian `s16` vertices, 8-byte face records with `i3 = 0xFF` for a triangle; at most 255 vertices). `SYSTEM.CNF` and the mkpsxiso XML are in Appendix E.2 (executable name `HOVER.EXE`, assets in `\DATA\`).
- **Project:** Write `cdrom.c/h` with `cd_load_file(name, &size) -> void*`. Write `model.c` that parses `MODEL.BIN`, which contains a ship-like low-poly mesh generated by `tools/assets/shpgen.py --model-bin` (manifest: `MODEL.BIN.json`) with deliberately big-endian header fields. Render it flat-shaded from the disc image.
- **Verification:** The build must produce a `.cue/.bin` that boots in PCSX-Redux with no side-loaded EXE. A probe confirms the parsed vertex and face counts and the first and last vertices match the generator's manifest. The screenshot shows the model at the expected screen location.

#### Chapter 30 — Textured Polygons *(Pikuma §23)*
- **Concept:** Textured polygons sample a rectangular texture page in VRAM using per-vertex UV coordinates. Paletted (4/8-bpp) textures look colors up in a CLUT, and the PS1's affine mapping produces its signature wobble.
- **Covers:** TPAGE (64×256 area, bit depth, semi-transparency) and CLUT addressing. `getTPage`/`getClut`. The TIM file format (header, CLUT block, pixel block). Converting PNG→TIM with `img2tim.py`. `POLY_FT4`/`POLY_GT4`. Affine texture warping, polygon jitter from integer vertex coordinates, and mitigations (subdividing, keeping polygons small). TPAGE size limits and atlas techniques.
- **Project:** Load a 4-bpp and an 8-bpp TIM from the CD into VRAM, and render the rotating cube with a different texture on each face: crate, panel, and a book-provided "Hoverline" logo.
- **Verification:** A VRAM probe confirms the TIM pixel and CLUT data were uploaded to the coordinates the TIM header specifies. Screenshot sampling at face centers matches expected texel colors (tolerant). A primitive check confirms `POLY_FT4`/`GT4` usage with valid tpage/clut fields.

#### Chapter 31 — Compression: LZSS Texture Packs *(Pikuma §25)*
- **Concept:** Disc space and load time are precious. Games pack many assets into one compressed archive, and a decompressor rebuilds them in RAM using a sliding window of previously decoded bytes.
- **Covers:** The LZSS algorithm (flag bits, literal bytes, back-reference offset/length, ring buffer). The book's **`.TPK` texture pack** format (Appendix E.6): `TPK1` header with texture count, raw/compressed sizes and CRC-32, a per-texture size table, then one LZSS-compressed blob of concatenated TIMs. The LZSS variant is fixed in Appendix E.5 (4096-byte zeroed ring, cursor 4078, LSB-first flag bytes, 12-bit absolute position + 4-bit length-3). The reference packer is `tools/assets/tpkpack_ref.py`; the reader's own is `tpkpack.py`. Writing the packer in Python and the unpacker in C. Building a global texture store and uploading each texture.
- **Project:** Write `tpkpack.py` (host, compresses a folder of TIMs) and `tpk.c` (PS1, `tpk_load(file) -> texture_id[]`). Load a pack of 8 textures and display them as a grid of textured quads.
- **Verification:** Host tests round-trip random and real data through the reader's Python compressor and a reference decompressor, and the reverse. On the PS1, the decompressed buffer's CRC32 (computed by a probe from RAM) must match the original TIMs, and all 8 textures must appear at the correct VRAM locations.

#### Chapter 32 — A Real Model Format: `.SHP` *(Pikuma §24–25)*
- **Concept:** Production model formats hold many primitive *types* (flat and Gouraud tris and quads, textured variants) with per-type layouts. A parser dispatches on a type tag and builds the matching GPU primitive for each one.
- **Covers:** The book's **`.SHP` object format**: object name, vertex list, normals list, a primitive list where each entry has a type tag, flags, indices, UVs, a texture index, and colors (fully specified in Appendix E.8: eight types `F3 F4 G3 G4 FT3 FT4 GT3 GT4`, texture-local UVs plus the TSB/CBA arithmetic of E.3.4). `sizeof` on variables vs. types. Mapping texture indices to the TPK store (TSB/CBA: texture-page and CLUT attribute words). Pointer-walking variable-length records. Flat-shaded fallback rendering.
- **Project:** Parse and render a `.SHP` ship model (generated by `shpgen.py`, which mixes all primitive types) with its matching `.TPK`. First render it flat-shaded to validate geometry, then fully textured.
- **Verification:** The probe compares parsed counts per primitive type against the generator manifest. Every primitive's tpage/clut words must match the expected TSB/CBA values. Screenshots of the ship at three fixed angles are compared by perceptual hash to the reference render.

---

### Part VII — Capstone: *Hoverline*, an Original Anti-Gravity Racer
**Theme:** Everything comes together in a complete 3D racing game: a ship hovering along a twisting textured track, with physics, collision, visibility culling, and sound. All assets and formats are original to this book.
**Part outcome:** A bootable CD image of a playable time-trial racer that runs at a stable frame rate on PCSX-Redux, DuckStation, and Mednafen.

#### Chapter 33 — Game Architecture: Objects, Scenes, and Input Events *(Pikuma §24, §26–27)*
- **Concept:** A game is a loop over a world of objects. A linked list of scene objects, loaded from disc and culled by camera distance, gives an extensible and efficient structure.
- **Covers:** The Hoverline project overview and asset pipeline (`make assets` runs all generators). Loading multiple `.SHP`/`.TPK` pairs. A singly linked list of `Object` nodes (insert, iterate, remove). Scene files listing landscape objects (pylons, arches, towers) with positions: `SCENE.BIN` (Appendix E.9: shape table of `.SHP` names + 24-byte object entries; generator `scenegen.py`; asset set from `mkassets.py`). Camera–object distance checks with squared distances in fixed point (avoiding overflow). Edge-triggered pad events from Ch 22 reused for menus.
- **Project:** Build the Hoverline skeleton: title screen (press Start), then a scene of 20+ landscape objects loaded from `SCENE.BIN` into a linked list, explored with the Ch 28 fly camera, with distant objects culled.
- **Verification:** The probe walks the linked list in RAM through the head symbol and checks node count and positions against `SCENE.BIN`. With the camera placed by injected input, the submitted-object count must equal the Python-computed count within cull range. Start transitions the title→game state.

#### Chapter 34 — Track Geometry *(Pikuma §28)*
- **Concept:** A race track is a sequence of connected *sections*, each a ring of quad faces between shared vertices. Rendering it at world scale requires managing the GTE's 16-bit input limits.
- **Covers:** The book's **`.TRK` format** (Appendix E.10): `s32` vertex table, 24-byte face table (4 Z-order indices, flags `FLOOR/WALL/BOOST/START/FLIP_H`, texture index, UVs, colour), 64-byte section table (centre, half width, length, forward/right/up 4.12 frame, face range, next/prev, flags incl. `JUNCTION` (unused), visibility slice, four road-edge vertex indices) and the visibility list. The track is generated from a spline by `trkgen.py`. Structs for sections and faces. Rendering sections. Shrinking/scaling world vertices. Face flags (track surface, wall, boost pad, start line). Debug rendering with quad outlines. Bypassing the 16-bit GTE limit by making vertices camera-relative, and clamping overflow values.
- **Project:** Load `TRACK.TRK` and render the whole track as flat-shaded faces colored by flag type, with a wireframe overlay toggle. Fly along it with the camera.
- **Verification:** Parsed section/face/vertex counts match the `trkgen` manifest. A probe confirms camera-relative coordinates stay within ±32767 after transform setup, at three harness-chosen camera positions far from the origin. Screenshots show boost-pad-colored faces at a known section.

#### Chapter 35 — Track Texturing *(Pikuma §29)*
- **Concept:** Large surfaces are textured with small reusable tiles placed manually in VRAM, with per-face UVs and flip flags giving variety without more memory.
- **Covers:** Loading the track tile set (`TRACK.TPK`). Manual VRAM layout planning (framebuffers, tile pages, CLUT rows). Per-face UV coordinates and texture index from `.TRK`. Horizontal flip flags for mirrored tiles. Visualizing VRAM in the PCSX-Redux VRAM viewer.
- **Project:** Texture the full track. Write a `vram_layout.md` plan explaining the reader's placement, then implement it with flipped tiles on the marked faces.
- **Verification:** A VRAM probe checks that tiles sit at the addresses declared in the reader's `vram_layout.h` and do not overlap the framebuffers. Every track primitive must have valid tpage/clut/UV values (no out-of-page UVs). Sampled screenshot texels match at a known flipped and a known unflipped face.

#### Chapter 36 — Polygon Subdivision and Tessellation *(Pikuma §30)*
- **Concept:** Large polygons near the camera exaggerate affine texture warping and get clipped badly. Recursively subdividing them, UVs included, keeps textures stable. Mismatched subdivision creates T-junction cracks.
- **Covers:** Distance- and screen-size-based subdivision criteria. Recursive quad splitting (midpoints in 3D and in UV). Primitive-buffer budget control. T-junctions, why they produce sparkling gaps, and mitigation strategies (consistent levels across edges, slight overlap, max-depth rules).
- **Project:** Add recursive subdivision (up to 2 levels) to near track faces, with a debug toggle that shows subdivided faces in wireframe colors per level.
- **Verification:** At a harness-placed camera, the probe counts the primitives per subdivision level, checking that near faces are subdivided and far ones are not. Subdivided UVs are checked for exact midpoints. A gap detector samples a row of pixels across a section boundary and checks for no background-colored pixels (cracks).

#### Chapter 37 — Ship Movement and Physics *(Pikuma §31)*
- **Concept:** A vehicle is a rigid body with position, velocity, and orientation (yaw, pitch, roll). Thrust along the ship's forward vector, integrated each frame in fixed point and independent of video standard, produces convincing motion.
- **Covers:** `Ship` struct and `ship.h` API. Euler integration of position and velocity. Thrust magnitude and speed caps. NTSC (60 Hz) vs. PAL (50 Hz) and time-step scaling. Yaw, pitch, roll, and deriving the combined rotation matrix. Intrinsic vs. extrinsic rotation order. Yaw velocity with angular damping. Banking (roll) into turns. A chase camera positioned behind and above the ship using Ch 28's look-at.
- **Project:** Put the player ship on the track start line. Accelerate with X, brake with Square, steer with the D-pad (with visual roll), and follow with the chase camera. No collision yet.
- **Verification:** With scripted input (accelerate for 120 frames, then turn left for 60), the ship state (from a symbol) must match a Python reference simulation of the same specified physics within tolerance. The PAL-mode run (a harness flag) must travel the same distance per second as the NTSC run. The camera must stay behind the ship (dot product check).

#### Chapter 38 — Track Visibility *(Pikuma §32)*
- **Concept:** Drawing the whole track every frame wastes the GPU. Tracking which section the ship is nearest to, and rendering only a window of sections ahead and behind, keeps the frame rate stable.
- **Covers:** Initializing the ship's nearest section (brute-force search). Updating it incrementally each frame by checking neighbors through section links. Rendering N sections ahead and M behind. Clamping vertex coordinates near the camera. Precomputed visibility lists (the optional `.VIS` table is the visibility block inside the `.TRK`, Appendix E.10.5) as an alternative.
- **Project:** Replace whole-track rendering with nearest-section windowed rendering, and add an on-screen debug readout of the current section index and primitive count.
- **Verification:** On a scripted lap, the probe compares the reader's nearest-section index each frame with a Python brute-force reference (it must match ≥99% of frames). Primitives per frame must stay under budget, and the frame time must stay under one VBlank throughout the lap.

#### Chapter 39 — Audio *(Pikuma §33)*
- **Concept:** The SPU is a 24-voice ADPCM sampler with its own 512 KB RAM. Sound effects are uploaded as VAG samples and triggered on voices with a pitch and volume, while music streams from the disc.
- **Covers:** SPU architecture (voices, ADSR envelopes, reverb, SPU RAM). Converting WAV→VAG with `wav2vag.py` (format: Appendix E.4; effects from `sfxgen.py`; `ENGINE.VAG` is looped, flags 4/3). Uploading samples (`SpuWrite` / DMA), setting voice address, pitch, volume, and key-on. Pitch as a function of sample rate (`pitch = rate × 4096 / 44100`). Engine sound pitched by ship speed. Background music via CD-DA or XA audio tracks added to the mkpsxiso layout. Original book-provided (or generated) sounds and music only.
- **Project:** Add an engine hum whose pitch follows speed, a collision thud, a boost chime, and a looping background music track from the CD.
- **Verification:** A probe reads SPU registers (voice key-on, pitch, start address) through PCSX-Redux. Key-on must fire on the expected events during a scripted run, and engine-voice pitch must rise monotonically with speed. SPU RAM must contain the VAG data (CRC match). The disc image must list an audio track.

#### Chapter 40 — Track Collision *(Pikuma §34)*
- **Concept:** The ship stays on the track by testing its position against the current section's left and right edges with dot products, then pushing it back and correcting its heading when it crosses one.
- **Covers:** Loading different tracks. Dot product review (signed distance to a plane or edge). Finding a section's left/right edge vertices (recipe plus fallback values for irregular sections). Debug-printing edge values with `FntPrint`. The collision response: positional correction, velocity reflection or damping, and yaw correction toward the track direction. Using face flags (boost pads → speed impulse, walls).
- **Project:** Implement wall collision with a damped bounce and yaw correction, plus boost pads that give a speed impulse. Support loading either of two generated tracks from a menu.
- **Verification:** Scripted runs that steer hard into each wall must keep the ship inside the edge bounds (checked every frame against the Python edge computation). Yaw must converge toward the track direction after impact. A boost-pad run must show the specified speed increase. Both tracks must load.

#### Chapter 41 — Handling, Game Loop, and Polish *(Pikuma §35)*
- **Concept:** "Feel" comes from tuned, layered forces: skid (lateral slip), air resistance, and auto-pitch to follow the track's slope. These, wrapped in a proper game-state machine, turn a simulation into a game.
- **Covers:** Skid factor (blending the velocity direction toward the facing direction). Resistance (speed-proportional drag). Auto-pitch from section normals. Preventing the ship from turning back (wrong-way detection through section progression). A game-state machine (title → countdown → race → results). Lap counting via the start-line flag. A lap timer HUD with `FntPrint` or sprite digits. A best lap saved in RAM (memory card optional/stretch).
- **Project:** Finish Hoverline: a 3-lap time trial with countdown, lap times, wrong-way warning, a results screen, and tuned handling.
- **Verification:** A scripted "ideal lap" input file (provided) must complete 3 laps within a time window, and lap counts and timer must match. Wrong-way input must trigger the warning flag. The state machine must pass through all states in order. Skid and resistance must match the reference physics on a test straight.

#### Chapter 42 — Shipping It: Conclusion and Next Steps *(Pikuma §36)*
- **Concept:** Shipping means a reproducible build, testing across emulators (and, if possible, real hardware), and knowing what to learn next.
- **Covers:** A release build (optimization flags, stripping debug output). Region and licence-string considerations for booting (homebrew-safe, no Sony logo assets). Testing on PCSX-Redux, DuckStation, and Mednafen, and the accuracy differences found. Running on real hardware: unirom/serial loaders, burned CD-R with modchip, or ODE (optional). Profiling. Next steps: MDEC video, memory cards, interrupt handlers, link cable, a Net Yaroze retrospective, contributing to PSn00bSDK and emulators.
- **Project:** Produce the final `hoverline.cue/.bin` with a single `make release`, and write `RELEASE.md` with the reader's cross-emulator test notes.
- **Verification:** A clean-checkout build in the Docker image produces the image deterministically (hash-stable across two builds). The image boots and completes the scripted ideal lap in PCSX-Redux, and boots and reaches the title screen in DuckStation (and Mednafen, if installed) through their headless/scripted modes. `RELEASE.md` must exist with a section per emulator.

---

### Part VIII — Appendices (reference material, no projects)
- **A. MIPS R3000A cheat sheet:** every instruction, its encoding, delay-slot behavior, and pseudo-instruction expansions.
- **B. Memory map & I/O registers:** RAM, scratchpad, BIOS, GPU, SPU, CD, DMA, timers, interrupts.
- **C. GPU command reference:** every GP0/GP1 command with packet layouts.
- **D. GTE reference:** registers and their formats, commands, cycle counts, hazards, and the `<inline_c.h>` macros with the register each one reads or writes.
- **E. File formats:** PSX-EXE, TIM, VAG, `SYSTEM.CNF`, and the book's own `MODEL.BIN`, `.SHP`, `.TPK`, `.TRK`, `SCENE.BIN` (byte-exact specifications that authoring agents must keep consistent with the generator scripts).
- **F. Troubleshooting:** black screens, emulator crashes, address errors, delay-slot bugs, GTE overflow, CD-loading failures. Must include the PSn00bSDK 0.24 defect: `gte_SetRotMatrix`, `gte_SetTransMatrix`, `gte_SetLightMatrix` and `gte_SetColorMatrix` write `$t0`/`$t1` but declare only `$t2` clobbered, so a value GCC keeps there is silently destroyed (typically a crash through a garbage pointer, depending on register allocation). Call them only from a `noipa` function (Ch 25–27's `load_matrix`); `noinline` is not enough because `-fipa-ra` lets the caller keep values in `$t0`/`$t1` across the call. Also: cycle counts in Redux mean something only under `-interpreter`.
- **G. PsyQ ↔ PSn00bSDK name map:** helps the reader follow older tutorials and the reference course. It must record that PSn00bSDK 0.24 has no `RotTransPers`, `RotTransPers3`, `RotTransPers4`, `RotAverage3/4`, `RotAverageNclip3/4`, `RotNclip3/4`, `NormalClip`, `AverageZ3/4`, `SetGeomOffset`, `SetGeomScreen`, `SetRotMatrix`, `SetTransMatrix` functions, and give each one's `gte_*` macro sequence (e.g. `RotTransPers` = `gte_ldv0`, `gte_rtps`, `gte_stsxy`, `gte_stsz`, `gte_stflg`; `NormalClip` = `gte_ldsxy3`, `gte_nclip`, `gte_stopz`; `SetGeomOffset` = `gte_SetGeomOffset`). The matrix routines (`RotMatrix`, `TransMatrix`, `MulMatrix0`, `CompMatrixLV`, `PushMatrix`, …) keep their PsyQ names. Note that the `SetRotMatrix`/`SetTransMatrix` replacements (`gte_SetRotMatrix`/`gte_SetTransMatrix`) have the clobber defect of Appendix F, and that `inline_c.h` (Nugget's `inline_n.h` equivalent) has a bare `gte_*_b()` variant of most commands without the two `nop`s (e.g. `gte_rtpt_b()`).

---

## 6. Guidance for Authoring Agents

1. **Write in order.** Each chapter's `starter/` must be derivable from the previous chapter's `solution/`, plus new scaffolding.
2. **Specify formats before generators.** Write Appendix E (book formats) before Chapters 29–41, and have `tools/assets/*.py` implement it exactly. All capstone assets are procedurally generated or original. Never include or reference commercial game assets.
3. **Prove every verify script both ways.** It must pass on `solution/` and fail on `starter/`. Add a CI job (`tools/ci.sh`) that does this for every chapter.
4. **Keep checks behavioral.** Never require a specific variable name unless the starter declares it. Expose the needed state through starter-declared symbols such as `results`, `scene`, `ship`, and `done`.
5. **Tone and length.** Conversational and precise, as long as the concept needs and no longer (up to roughly 9,000 words; shorter is fine when the content is adequately explained). Use diagrams for memory layouts, pipelines, packets, VRAM maps, and transform pipelines. Explain every new instruction or API the first time it appears.
6. **Cite hardware facts** against psx-spx and the PSn00bSDK documentation, and note emulator-specific behavior wherever it differs.
