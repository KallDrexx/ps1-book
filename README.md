# PlayStation Programming from the Metal Up

A self-paced textbook that teaches you to write original software for the Sony PlayStation (PS1):
MIPS assembly first, then C with PSn00bSDK, then 3D with the GTE, CD-ROM assets, and a complete original
anti-gravity racer, *Hoverline*. Every chapter ends in a project you implement from a starter, and a
`verify.sh` script that builds your code, runs it headless in an emulator, and tells you whether you got it right.
See [`Summary.md`](Summary.md) for the full curriculum.

## Prerequisites

* You can program (loops, functions, conditionals). No assembly, console, or 3D experience needed.
* Linux (primary), macOS or Windows (WSL recommended). x86-64 for the prebuilt tools; other CPUs can use Docker.
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

Prefer a container? `docker build -f tools/Dockerfile -t ps1-book .` then
`docker run --rm -it --user "$(id -u):$(id -g)" -v "$PWD":/book ps1-book bash`.

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

A hung program or infinite loop before the chapter's `done:` label simply fails the check after a 20-second timeout.

## Repository layout

```
Summary.md              curriculum and authoring conventions
README.md               this file
common/                 shared starter code handed to the reader (psxexe.inc, the PSX-EXE header macro; psxe/, the C engine library from Chapter 21, copied into each chapter that uses it)
tools/
  setup.sh doctor.sh env.sh versions.txt requirements.txt Dockerfile
  ci.sh                 proves every chapter: solution passes, untouched starter fails
  verify-lib/           the verification harness (see its README.md for the chapter-author API)
  assets/               asset generators (img2tim.py, wav2vag.py, ...)
appendices/             reference material (MIPS, memory map, GPU, GTE, file formats, troubleshooting)
parts/part-NN-slug/README.md                part intro
parts/part-NN-slug/chNN-slug/{README.md, starter/, solution/, verify/, quiz.md}   README.md = chapter text
.toolchain/             downloaded tools (git-ignored)
```

## For chapter authors

Read [`tools/verify-lib/README.md`](tools/verify-lib/README.md). Start from the files in
`tools/verify-lib/templates/` (`verify.sh`, `checks.py`, `Makefile.armips`). Before committing a chapter, run
`tools/ci.sh` (or `tools/ci.sh ch07` for one chapter): the `--solution` run must pass and the starter run must fail.
