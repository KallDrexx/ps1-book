# PlayStation Programming from the Metal Up

A self-paced textbook that teaches you to write original software for the Sony PlayStation (PS1):
MIPS assembly first, then C with PSn00bSDK, then 3D with the GTE, CD-ROM assets, and a complete original
anti-gravity racer, *Hoverline*. Every chapter ends in a project you implement from a starter, and a
`verify.sh` script that builds your code, runs it headless in an emulator, and tells you whether you got it right.
See [`Summary.md`](Summary.md) for the full curriculum.

## Contents

All 42 chapters and appendices A to G are available.

**[Part I: The Machine and Its Language](parts/part-01-machine-and-language/README.md)**

* [Chapter 1: The PlayStation and Your Workbench](parts/part-01-machine-and-language/ch01-workbench/README.md)
* [Chapter 2: Memory, the Memory Map, and Endianness](parts/part-01-machine-and-language/ch02-memory-map-and-endianness/README.md)
* [Chapter 3: Registers, Loads, Stores, and Arithmetic](parts/part-01-machine-and-language/ch03-registers-loads-stores-arithmetic/README.md)
* [Chapter 4: Control Flow: Branches and Jumps](parts/part-01-machine-and-language/ch04-control-flow-branches-and-jumps/README.md)
* [Chapter 5: Anatomy of an Executable: The PSX-EXE Format](parts/part-01-machine-and-language/ch05-anatomy-of-an-executable/README.md)
* [Chapter 6: Emulation and Debugging](parts/part-01-machine-and-language/ch06-emulation-and-debugging/README.md)

**[Part II: Thinking Like the R3000](parts/part-02-thinking-like-the-r3000/README.md)**

* [Chapter 7: The Pipeline and Delay Slots](parts/part-02-thinking-like-the-r3000/ch07-the-pipeline-and-delay-slots/README.md)
* [Chapter 8: Subroutines](parts/part-02-thinking-like-the-r3000/ch08-subroutines/README.md)
* [Chapter 9: Signed Numbers, Logic, and Bit Shifting](parts/part-02-thinking-like-the-r3000/ch09-signed-numbers-logic-and-shifts/README.md)
* [Chapter 10: The Stack and the MIPS ABI](parts/part-02-thinking-like-the-r3000/ch10-the-stack-and-the-mips-abi/README.md)
* [Chapter 11: Data Layout and Memory Alignment](parts/part-02-thinking-like-the-r3000/ch11-data-layout-and-memory-alignment/README.md)
* [Chapter 12: RISC vs. CISC, Multiply and Divide](parts/part-02-thinking-like-the-r3000/ch12-risc-vs-cisc-multiply-and-divide/README.md)

**[Part III: Bare-Metal Graphics in Assembly](parts/part-03-bare-metal-graphics-in-assembly/README.md)**

* [Chapter 13: The GPU, VRAM, and Command Packets](parts/part-03-bare-metal-graphics-in-assembly/ch13-the-gpu-vram-and-command-packets/README.md)
* [Chapter 14: Rendering Polygons](parts/part-03-bare-metal-graphics-in-assembly/ch14-rendering-polygons/README.md)
* [Chapter 15: Drawing Subroutines and Stack Parameters](parts/part-03-bare-metal-graphics-in-assembly/ch15-drawing-subroutines-and-stack-parameters/README.md)
* [Chapter 16: Copying Data to VRAM](parts/part-03-bare-metal-graphics-in-assembly/ch16-copying-data-to-vram/README.md)
* [Chapter 17: Part III Capstone: Animation in Assembly](parts/part-03-bare-metal-graphics-in-assembly/ch17-animation-in-assembly/README.md)

**[Part IV: C on the PlayStation](parts/part-04-c-on-the-playstation/README.md)**

* [Chapter 18: From Assembly to C](parts/part-04-c-on-the-playstation/ch18-from-assembly-to-c/README.md)
* [Chapter 19: Double Buffering with Display and Draw Environments](parts/part-04-c-on-the-playstation/ch19-double-buffering/README.md)
* [Chapter 20: Primitives and Ordering Tables](parts/part-04-c-on-the-playstation/ch20-primitives-and-ordering-tables/README.md)
* [Chapter 21: Working with Multiple Files](parts/part-04-c-on-the-playstation/ch21-working-with-multiple-files/README.md)
* [Chapter 22: Controller Input and the BIOS](parts/part-04-c-on-the-playstation/ch22-controller-input-and-the-bios/README.md)

**[Part V: Three Dimensions with the GTE](parts/part-05-three-dimensions-with-the-gte/README.md)**

* [Chapter 23: Fixed-Point Math](parts/part-05-three-dimensions-with-the-gte/ch23-fixed-point-math/README.md)
* [Chapter 24: 3D Projection Fundamentals](parts/part-05-three-dimensions-with-the-gte/ch24-3d-projection-fundamentals/README.md)
* [Chapter 25: The GTE Coprocessor](parts/part-05-three-dimensions-with-the-gte/ch25-the-gte-coprocessor/README.md)
* [Chapter 26: Multiple Objects and Simple Motion](parts/part-05-three-dimensions-with-the-gte/ch26-multiple-objects-and-simple-motion/README.md)
* [Chapter 27: Batching GTE Work: RTPT and Timing](parts/part-05-three-dimensions-with-the-gte/ch27-batching-gte-work-rtpt-and-timing/README.md)
* [Chapter 28: The Camera](parts/part-05-three-dimensions-with-the-gte/ch28-the-camera/README.md)

**[Part VI: Assets: CD-ROM, Textures, and Compression](parts/part-06-assets-cdrom-textures-and-compression/README.md)**

* [Chapter 29: The CD-ROM and Loading Files](parts/part-06-assets-cdrom-textures-and-compression/ch29-the-cd-rom-and-loading-files/README.md)
* [Chapter 30: Textured Polygons](parts/part-06-assets-cdrom-textures-and-compression/ch30-textured-polygons/README.md)
* [Chapter 31: Compression: LZSS Texture Packs](parts/part-06-assets-cdrom-textures-and-compression/ch31-compression-lzss-texture-packs/README.md)
* [Chapter 32: A Real Model Format: `.SHP`](parts/part-06-assets-cdrom-textures-and-compression/ch32-a-real-model-format-shp/README.md)

**[Part VII: Capstone: *Hoverline*, an Original Anti-Gravity Racer](parts/part-07-capstone-hoverline/README.md)**

* [Chapter 33: Game Architecture: Objects, Scenes, and Input Events](parts/part-07-capstone-hoverline/ch33-game-architecture-objects-scenes-and-input/README.md)
* [Chapter 34: Track Geometry](parts/part-07-capstone-hoverline/ch34-track-geometry/README.md)
* [Chapter 35: Track Texturing](parts/part-07-capstone-hoverline/ch35-track-texturing/README.md)
* [Chapter 36: Polygon Subdivision and Tessellation](parts/part-07-capstone-hoverline/ch36-polygon-subdivision-and-tessellation/README.md)
* [Chapter 37: Ship Movement and Physics](parts/part-07-capstone-hoverline/ch37-ship-movement-and-physics/README.md)
* [Chapter 38: Track Visibility](parts/part-07-capstone-hoverline/ch38-track-visibility/README.md)
* [Chapter 39: Audio](parts/part-07-capstone-hoverline/ch39-audio/README.md)
* [Chapter 40: Track Collision](parts/part-07-capstone-hoverline/ch40-track-collision/README.md)
* [Chapter 41: Handling, Game Loop, and Polish](parts/part-07-capstone-hoverline/ch41-handling-game-loop-and-polish/README.md)
* [Chapter 42: Shipping It](parts/part-07-capstone-hoverline/ch42-shipping-it/README.md)

**Appendices**

* [Appendix A: MIPS R3000A Cheat Sheet](appendices/A-mips-cheat-sheet.md)
* [Appendix B: Memory Map and I/O Registers](appendices/B-memory-map-and-io.md)
* [Appendix C: GPU Command Reference](appendices/C-gpu-commands.md)
* [Appendix D: GTE Reference](appendices/D-gte-reference.md)
* [Appendix E: File Formats](appendices/E-file-formats.md)
* [Appendix F: Troubleshooting](appendices/F-troubleshooting.md)
* [Appendix G: PsyQ to PSn00bSDK Name Map](appendices/G-psyq-to-psn00bsdk.md)

## Prerequisites

* You can program (loops, functions, conditionals). No assembly, console, or 3D experience needed.
* Linux on x86-64 (Windows: WSL 2). `tools/setup.sh` installs Linux x86-64 binaries only, so on macOS, or on any
  non-x86 machine, use the Docker image described under Setup.
* Installed on the host: `git`, `curl`, `python3` (3.10+, with `venv`), `cmake` (3.21+), `make`, and a C++ compiler
  (`build-essential`) because armips is built from source.
  On Debian/Ubuntu: `sudo apt install build-essential cmake git curl python3 python3-venv`.
* About 1 GB of disk for the toolchain. No sudo is needed for the toolchain itself, and **no PlayStation BIOS is
  needed** (PCSX-Redux's built-in OpenBIOS is used).

## Setup

```sh
tools/setup.sh      # installs into ./.toolchain (armips, MIPS GCC, PSn00bSDK, PCSX-Redux, mkpsxiso, Python deps)
tools/doctor.sh     # re-run any time: prints OK / MISSING per tool, exits non-zero if anything is missing
```

`setup.sh` is idempotent (`--force` reinstalls). Versions are pinned in [`tools/versions.txt`](tools/versions.txt).
To put the tools on your `PATH` in a shell: `source tools/env.sh`.

Prefer a container, or not on x86-64 Linux? `docker build -f tools/Dockerfile -t ps1-book .` then
`docker run --rm -it --user "$(id -u):$(id -g)" -v "$PWD":/book ps1-book bash`.
The image holds the same Linux x86-64 toolchain, so on an ARM host (Apple silicon) add `--platform linux/amd64`
to both commands; the tools then run under emulation, so expect them to be slower. The verifier needs no display.

## Working through a chapter

1. Read the chapter text, `parts/part-NN-*/chNN-*/README.md`.
2. Work in that chapter's `starter/` directory (or a copy of it elsewhere; run `source tools/env.sh` first so the
   copy's `Makefile` can find the book through `PS1BOOK_ROOT`).
   Build with `make` (or the command the chapter gives) and run it in PCSX-Redux to watch it work.
3. Check yourself:
   ```sh
   parts/part-01-*/ch01-*/verify/verify.sh            # verifies ./starter, i.e. your work
   parts/part-01-*/ch01-*/verify/verify.sh path/to/your/copy
   parts/part-01-*/ch01-*/verify/verify.sh -v         # also show the build output and emulator log
   ```
   Each check prints `PASS`/`FAIL` with *expected*, *actual* and a *hint*. The last line is
   `CHAPTER NN: PASSED (k/k checks)` when you are done (exit code 0).
4. Take the `quiz.md`. Stuck? Peek at `solution/` only after you have tried (`verify.sh --solution` proves it passes).

A program that hangs before the chapter's end point (the `done:` label in the assembly chapters) fails the check
after a 20-second timeout. Exit codes: `0` passed, `1` build or check failed, `2` tooling problem.
Something not working? [Appendix F: Troubleshooting](appendices/F-troubleshooting.md) lists symptoms and fixes.

## Repository layout

```
Summary.md              curriculum and authoring conventions
README.md               this file
common/                 shared code: psxexe.inc (the PSX-EXE header for Parts I-III) and psxe/ (the C engine
                        library from Chapter 21, copied into each later chapter that uses it)
tools/
  setup.sh doctor.sh env.sh versions.txt requirements.txt Dockerfile
  ci.sh                 proves every chapter: solution passes, untouched starter fails
  verify-lib/           the verification harness (see its README.md for the chapter-author API)
  assets/               asset generators and their selftest (see its README.md)
appendices/             reference material A-G (MIPS, memory map, GPU, GTE, file formats, troubleshooting, PsyQ name map)
parts/part-NN-slug/README.md                part intro
parts/part-NN-slug/chNN-slug/{README.md, starter/, solution/, verify/, quiz.md}   README.md = chapter text
.toolchain/             downloaded tools (git-ignored)
```

## For chapter authors

Read [`tools/verify-lib/README.md`](tools/verify-lib/README.md). Start from the files in
`tools/verify-lib/templates/` (`verify.sh`, `checks.py`, `Makefile.armips`). Before committing a chapter, run
`tools/ci.sh` (or `tools/ci.sh ch07` for one chapter): the `--solution` run must pass and the starter run must fail.
