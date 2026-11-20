# Part VI: Assets: CD-ROM, Textures, and Compression

**Theme.** Real games stream their data from disc. This part builds a CD image, loads binary files from it, parses them with correct byte order, textures polygons, and decompresses packed data.

**Part outcome.** You run a game from a bootable CD image that loads compressed, textured 3D models designed in the book's own file formats.

## Chapters

| # | Chapter | You build | Status |
|---|---|---|---|
| 29 | [The CD-ROM and Loading Files](ch29-the-cd-rom-and-loading-files/README.md) | "Ship from Disc": `cd_load_file`, a `MODEL.BIN` parser, and a flat-shaded ship read from a bootable `.cue/.bin` | available |
| 30 | [Textured Polygons](ch30-textured-polygons/README.md) | "Crates and Logos": the rotating cube with a different TIM texture on each face, loaded from disc | available |
| 31 | Compression: LZSS Texture Packs | `tpkpack.py` (host) and `tpk.c` (PS1): a pack of 8 textures shown as a grid of quads | planned |
| 32 | A Real Model Format: `.SHP` | a parser for the book's `.SHP` ship, rendered flat-shaded and then textured | planned |

## How the part flows

```
files on disc -> textures -> compressed packs -> full models
   (Ch 29)       (Ch 30)        (Ch 31)           (Ch 32)
```

Chapter 29 gives you the loader every later chapter uses: a program that boots from a disc image, finds a file by name, reads it into RAM and interprets the bytes (including a big-endian header). Chapter 30 turns loaded TIM files into VRAM contents and textured polygons. Chapter 31 shrinks many textures into one LZSS-compressed pack and unpacks it on the console. Chapter 32 reads a production-style model with eight primitive types and draws it with its textures.

## Before you start

Finish Part V. You will use:

- the GTE pipeline of Chapters 25 and 26 (`gte_*`, `NCLIP`, `AVSZ`, ordering-table slots);
- the C project structure and the `psxe` library from Part IV;
- endianness, alignment and the memory map from Chapters 2, 10 and 11.

The generated assets are **not committed**. Each chapter's `CMakeLists.txt` runs the generators in `tools/assets/` into `build/assets/` before it builds the disc image; the file formats are specified in [Appendix E](../../appendices/E-file-formats.md). The workflow is the Part V one: `source tools/env.sh`, `make` in `starter/` (now producing `hoverline.bin` and `hoverline.cue`), `verify.sh`.

## What changes in Part VI

| Before | From Chapter 29 |
|---|---|
| The emulator side-loads `game.exe` | The emulator boots a `.cue` disc image: BIOS, `SYSTEM.CNF`, then `HOVER.EXE` |
| All data is compiled into the program | Data lives in files on the disc and is loaded at run time |
| Verification boots in about 30 frames | Booting a disc takes about 400 emulated frames, so `verify.sh` takes a little longer |
