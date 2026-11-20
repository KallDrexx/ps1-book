# Chapter 29: The CD-ROM and Loading Files

## 1. Concept

A PS1 program and its data live on an **ISO9660** disc (the standard CD file system). The BIOS boots the program from the disc's `SYSTEM.CNF`; the program then finds each file by name, reads it into RAM in whole **2048-byte sectors**, and interprets the bytes as structured data, taking care of byte order and alignment.

## 2. Why it matters

Every PS1 game is a loader. The console has 2 MB of RAM and a disc of about 650 MB, so models, textures, tracks and sounds are read in when they are needed. The same few steps (find, read whole sectors, wait, check for errors, parse) carry the rest of this book: textures in Chapter 30, packs in Chapter 31, models in Chapter 32, the whole racer in Part VII. File formats also meet the machine's byte order here for the first time: a header written big-endian by one tool and read by a little-endian CPU is a classic bug, and this chapter provokes it on purpose.

## 3. Learning objectives

After this chapter you can:

- describe a CD-ROM data sector, the drive's two speeds, and how a position is written (minutes, seconds, frames);
- explain how the BIOS boots from `SYSTEM.CNF` and build a bootable `.bin/.cue` image with mkpsxiso and CMake;
- load a file with `CdSearchFile`, `CdControl(CdlSetloc)`, `CdRead` and `CdReadSync`, with the right buffer size and with error handling;
- say where the program, the heap and the stack live in the 2 MB, and what `malloc` can and cannot do there;
- read big-endian and little-endian integers byte by byte, and explain why casting an unaligned pointer is wrong;
- parse and validate a binary model file, and draw it flat-shaded with the GTE.

## 4. Prerequisites

[Chapter 2](../../part-01-machine-and-language/ch02-memory-map-and-endianness/README.md) (memory map, little-endian), [Chapter 5](../../part-01-machine-and-language/ch05-anatomy-of-an-executable/README.md) (the PSX-EXE header), [Chapter 11](../../part-02-thinking-like-the-r3000/ch11-data-layout-and-memory-alignment/README.md) (alignment), [Chapter 18](../../part-04-c-on-the-playstation/ch18-from-assembly-to-c/README.md) (startup code, CMake), [Chapter 21](../../part-04-c-on-the-playstation/ch21-working-with-multiple-files/README.md) (`psxe`), [Chapter 25](../../part-05-three-dimensions-with-the-gte/ch25-the-gte-coprocessor/README.md) (the GTE pipeline you reuse). [Appendix E](../../../appendices/E-file-formats.md) sections E.2 and E.7 are the formal specification of this chapter's files.

## 5. Explanation

### 5.1 The drive and its sectors

A CD is read as a numbered series of **sectors**. The drive delivers each one as 2352 raw bytes; for a data disc (Mode 2 Form 1, the PS1 format) the part you want is 2048 of them.

```
one raw sector: 2352 bytes
+------+--------+-----------+-----------------+------+---------+
| sync | header | subheader |      data       | EDC  |   ECC   |
|  12  |   4    |     8     |      2048       |  4   |   276   |
+------+--------+-----------+-----------------+------+---------+
                             ^ what CdRead delivers (default mode)
```

| Fact | Value |
|---|---|
| Data per sector (default) | 2048 bytes. Mode bit `CdlModeSize` asks for 2340 instead (everything but the sync), used by video and audio streaming |
| Single speed | 75 sectors per second, about 150 KB/s |
| Double speed | 150 sectors per second, about 300 KB/s. Set with `CdlModeSpeed`; nearly all games use it |
| A position | **MSF**: minutes, seconds, frames (a frame is a sector, 75 per second), each a **BCD** byte (`0x32` means 32) |
| Sector 0 | `00:02:00`: the first two seconds (150 sectors) of the track are its pregap, so `CdPosToInt`/`CdIntToPos` subtract and add 150 |

Reading is slow compared with RAM, and **seeking** is slower still: moving the laser takes from tens to several hundred milliseconds depending on the distance, and spinning up a stopped disc takes about a second. Games put files that load together next to each other on the disc, and stream while playing. One sector is about 7 ms at double speed; our 220-byte model costs one sector plus a seek.

### 5.2 The disc layout

```
sector  what
------  ------------------------------------------------------------
0-15    system area (licence data on retail discs; zeros in our image)
16      ISO9660 primary volume descriptor: "CD001", volume name HOVERLINE
17      volume descriptor terminator
18-21   path tables (a little-endian and a big-endian copy, each twice)
22      root directory
23      SYSTEM.CNF      54 bytes   -> 1 sector (the rest of it is padding)
24-35   HOVER.EXE       24576 bytes = 12 sectors
36      DATA directory
37      DATA\MODEL.BIN  220 bytes  -> 1 sector
...     <dummy sectors="1024"/> pads the end of the image
```

(Sector numbers are from the reference solution's image; yours may differ by a few.) The **directory entries** hold, for each file, its name, its first sector and its size in bytes. A file is stored in consecutive sectors, and its last sector is padded: the disc knows the file's size only through the directory entry. (ISO9660 sidesteps byte order by storing every number in its directory records twice, little-endian then big-endian, and every path table in both orders.)

The `.bin` file mkpsxiso writes holds the raw 2352-byte sectors; the `.cue` file tells an emulator (or a burner) how to read it:

```
FILE "hoverline.bin" BINARY
  TRACK 01 MODE2/2352
    INDEX 01 00:00:00
```

### 5.3 Booting: `SYSTEM.CNF` and `HOVER.EXE`

When the console starts a disc, the BIOS does this:

```
 BIOS starts the drive, reads the volume descriptor (sector 16)
   |
   +- finds SYSTEM.CNF in the root directory and reads it
   |     BOOT=cdrom:\HOVER.EXE;1    <- the program (root dir, 8.3 name, ;1 = version)
   |     TCB=4  EVENT=10            <- kernel thread and event slots (hexadecimal)
   |     STACK=801FFFF0             <- initial $sp
   +- allocates those kernel structures
   +- loads HOVER.EXE (a PSX-EXE: Chapter 5's header + code) to the address in its header
   +- jumps to its start address with $sp = STACK   ->  _start  ->  main
```

The executable on the disc is **the same file format** you have built since Chapter 5; only its name and place changed. An unmodified real console also refuses a burned disc: its drive checks a region marking that a CD burner cannot write (Chapter 42). Emulators do not check it.

`SYSTEM.CNF` is a plain text file ([Appendix E.2](../../../appendices/E-file-formats.md)). If it is missing, the BIOS looks for an executable called `PSX.EXE` instead.

### 5.4 Building the image: mkpsxiso and CMake

**mkpsxiso** builds the `.bin/.cue` pair from an XML description. The starter's `iso.xml` is the book's layout:

```xml
<iso_project>
  <track type="data">
    <identifiers system="PLAYSTATION" application="PLAYSTATION" volume="HOVERLINE" ... />
    <directory_tree>
      <file name="SYSTEM.CNF" type="data" source="${PROJECT_SOURCE_DIR}/system.cnf" />
      <file name="HOVER.EXE"  type="data" source="game.exe" />
      <dir name="DATA">
        <file name="MODEL.BIN" type="data" source="assets/MODEL.BIN" />
      </dir>
      <dummy sectors="1024"/>
    </directory_tree>
  </track>
</iso_project>
```

| Rule | Why |
|---|---|
| `system` and `application` are `PLAYSTATION` | otherwise the disc is not recognised |
| Names are 8.3, upper case, directories have no extension | ISO9660 level 1 |
| `source` paths are relative to the **build** directory | CMake runs mkpsxiso there; a file in the source tree needs `${PROJECT_SOURCE_DIR}` |
| At most 30 entries in the root, 45 directories on the disc | limits of the BIOS's file functions (PSn00bSDK template); stay inside them |

CMake wires it up in two lines: `psn00bsdk_add_executable(game ...)` makes `game.exe`, and `psn00bsdk_add_cd_image(iso hoverline iso.xml DEPENDS game assets system.cnf)` runs mkpsxiso after it. `iso.xml` goes through CMake's `configure_file` first, which is why `${PROJECT_SOURCE_DIR}` works in it. The `assets` target runs `tools/assets/shpgen.py --model-bin` and writes `build/assets/MODEL.BIN` (generated assets are never committed). `make` in `starter/` builds everything; `make run` boots `build/hoverline.cue` in PCSX-Redux.

### 5.5 Reading a file

Reading a file from the SDK is five calls. Each one has a reason:

```
 CdInit()                      once, after ResetGraph(): hook the CD interrupt, reset the drive
    |
 CdSearchFile(&file, path)     "\DATA\MODEL.BIN;1"  ->  file.pos (MSF), file.size (bytes)
    |                          NULL if the name is not on the disc
 malloc(sectors * 2048)        sectors = ceil(file.size / 2048)
    |
 CdControlB(CdlSetloc, &file.pos, 0)    where to start (does not move the laser yet)
    |
 CdRead(sectors, buf, CdlModeSpeed)     start: seek, then deliver sectors into buf (returns at once)
    |
 CdReadSync(0, 0)  or  poll CdReadSync(1, 0)    wait: 0 = done, > 0 = sectors left, < 0 = error
```

| Call | Returns | Notes |
|---|---|---|
| `CdInit()` | 1 ok, 0 error | call after `ResetGraph`/`ResetCallback`, once |
| `CdSearchFile(&file, path)` | `&file` or `NULL` | fills a `CdlFILE`: `pos` (a `CdlLOC` in BCD), `size` (bytes), `name`. Blocks while it reads. It keeps the path table and the last directory it searched in heap memory, so a second file in the same directory costs no disc read |
| `CdControlB(cmd, param, result)` | 1 ok | send a command and wait until it has completed. `CdControl` returns as soon as the drive acknowledges it (the difference matters for slow commands such as seeks) |
| `CdRead(n, buf, mode)` | 1 started, 0 failed | `buf` must be 4-byte aligned; `n` sectors of 2048 bytes are stored back to back |
| `CdReadSync(mode, &status)` | sectors left, `-1` error, `-2` aborted | mode 0 blocks until done; mode 1 returns at once |
| `CdReadBreak()` | | abort a read (give up) |
| `CdIsoError()` | `CdlIso*` code | a file-system failure (no disc, lid open, not ISO9660). A name that is simply not there leaves it at `CdlIsoOkay` (0) |

The path is the disc path with a version suffix, `\DATA\MODEL.BIN;1`; in C each backslash is written twice (`"\\DATA\\MODEL.BIN;1"`). Write it exactly that way. `psxcd.h` says names are case-insensitive and the leading backslash optional, but 0.24 is stricter: in tests `\data\model.bin;1`, `/DATA/MODEL.BIN;1` and `DATA\MODEL.BIN;1` all return `NULL`, and so does `\system.cnf;1` (only a root-directory name may drop the leading backslash or use `/`). The `;1` is optional. Search results use the BCD position that `CdlSetloc` wants, so no conversion is needed.

**Sector rounding.** The drive writes whole sectors. Reading a 220-byte file means reading one sector: 2048 bytes arrive in your buffer. A buffer of `file.size` bytes is overrun by up to 2047 bytes, which silently corrupts whatever the allocator placed next. So allocate `ceil(size / 2048) * 2048`, and remember that `size` (from the directory entry) is the file's real length, not the buffer's.

```
file.size = 5000      sectors = ceil(5000 / 2048) = 3      buffer = 6144 bytes
 [ sector 0 : 2048 ][ sector 1 : 2048 ][ sector 2 : 904 file bytes + 1144 padding ]
```

**Errors and time.** A read can fail (a scratched disc, an open lid) or stall. PSn00bSDK 0.24 has a watchdog: when no sector arrives for 180 vblanks (about 3 s), `CdReadSync` restarts a read begun with `CdReadRetry`, or ends a plain `CdRead` with `-1`. It notices only while you are calling `CdReadSync`. `cd_load_file` still sets its own limit: it polls (`CdReadSync(1, 0)` and `VSync(0)`), so the frame loop stays in your hands (a loading screen could be drawn between polls), and gives up after a fixed number of frames whatever the library does. Every failure path must release what it took: `free` the buffer, set the outputs to "nothing".

The BIOS has its own file API (`open("cdrom:\\DATA\\MODEL.BIN;1", ...)`, `read`, `close`, in `psxapi.h`) for the same job. This book uses the SDK's `Cd*` functions: they read asynchronously, expose the drive's modes and are what later chapters build on. The BIOS route is a stretch goal (7.6); the verifier expects the `Cd*` calls.

### 5.6 The heap and `malloc`

A file's size is only known at run time, so its buffer comes from the **heap**, the pool of memory `malloc` hands out and `free` takes back. You saw in Chapter 18 that `_start` calls `InitHeap` before `main`; in PSn00bSDK 0.24 it gives the heap everything from the end of `.bss` to `0x801FFFF8`. You need no `InitHeap` call of your own (it exists to place a heap elsewhere).

```
0x80000000 +--------------------+
           | BIOS kernel, 64 KB |
0x80010000 +--------------------+
           | .text .data .bss   |   game.exe (about 24 KB here)
_end       +--------------------+
           | heap  (grows up)   |   malloc / free
           |         |          |
           |         v   ^      |
           |             |      |
           | stack (grows down) |   starts at 0x801FFFF0 (SYSTEM.CNF STACK=)
0x80200000 +--------------------+
```

What this means for a loader:

- **2 MB is all there is.** Program, heap, stack, and the ordering tables and primitive buffers of `psxe` share it. `malloc` returns `NULL` when it cannot satisfy a request: always check.
- **`malloc` returns 8-byte-aligned blocks**, so a file buffer can be read with word loads (5.7) and given to `CdRead`.
- **The CD library uses the heap too.** `CdSearchFile` keeps its path table and a 2048-byte directory in `malloc`ed memory.
- **Fragmentation.** Freeing blocks in a different order than they were taken leaves holes that a big request cannot use. Load big, long-lived assets first; free in reverse order.
- **No guard.** The heap's limit is the top of RAM, not the stack pointer. A runaway heap can run into the stack, and nothing says so.

### 5.7 Bytes and byte order

The R3000 is little-endian (Chapter 2), but file formats are often not. `MODEL.BIN`'s two counts are **big-endian**, the most significant byte first. Take 13, as it appears in the file:

```
file bytes      00 00 00 0D
                |  |  |  |
big-endian      00 00 00 0D   -> 0x0000000D = 13       <- what the format means
little-endian   0D 00 00 00   -> 0x0D000000 = 218,103,808   <- what an lw would give you
```

So build the number yourself, one byte at a time: `(p[0] << 24) | (p[1] << 16) | (p[2] << 8) | p[3]`. That also settles **alignment**. `lw` needs an address divisible by 4 (Chapter 11), and a pointer into the middle of a file buffer is not guaranteed to be. `*(uint32_t *)(p + 5)` can raise an address error exception on the PS1 and is wrong in C regardless (it breaks the aliasing and alignment rules). Reading bytes is always safe, and the compiler turns it into the right instructions.

The *little-endian* fields of `MODEL.BIN` (the `s16` vertex coordinates) are the CPU's own order, so they can be read in place, but only because the format puts them at offsets that are multiples of 4 and the buffer is aligned. That is a property the file's designer arranged, and your parser checks the alignment instead of assuming it.

### 5.8 `MODEL.BIN`

The first model format: a mesh of flat-coloured triangles and quads ([Appendix E.7](../../../appendices/E-file-formats.md) is the specification).

```
0x00  "MDL1"                        magic
0x04  vertex_count V   u32 BIG-endian, 1..255
0x08  vertices         V x 8 bytes: s16 x, s16 y, s16 z, s16 0       little-endian
      face_count F     u32 BIG-endian         at 0x08 + 8*V
      faces            F x 8 bytes: u8 i0 i1 i2 i3, u8 r g b 0        i3 = 0xFF: a triangle
file size = 12 + 8*V + 8*F
```

The generated ship has 13 vertices, 4 triangles and 9 quads: 220 bytes, with the nose at `(0, 0, 300)`. Faces are clockwise as seen from outside, quads are in Z order, so Chapter 25's `NCLIP` culling works unchanged. A reader that trusts a file is a reader that crashes on a damaged one, so a parser **validates before it trusts**:

| Check | Because |
|---|---|
| address is 4-aligned; size is at least 12 | the header must be readable |
| magic is `MDL1` | it is the right kind of file |
| `1 <= V <= 255`, and size is at least `12 + 8V` | indices are bytes, and `0xFF` means "triangle"; the vertex table and `face_count` must be inside the image |
| `face_count` fits in the bytes left, and size is exactly `12 + 8V + 8F` | do the test as `F > (size - 12 - 8V) / 8`: `8 * F` overflows for a corrupt `F` |
| every face index is below `V` | an index is an array subscript |

### 5.9 Drawing it

This is Chapter 25's pipeline with a model in place of the cube: transform every vertex once with `RTPS` into `screen_xy[]` and `screen_z[]` (up to 255 of them), then for every face run `NCLIP` on corners 0, 1, 2 (positive means front-facing), average the depths with `AVSZ3` or `AVSZ4`, build a `POLY_F3` or `POLY_F4` in the colour the file stores, and link it into the ordering table at slot `OTZ >> 3`. (Chapter 25 used a shift of 7; the ship is only 800 units from the camera, so its depths are small and a smaller shift keeps its faces in distinct slots. The model is convex, so wrong sorting would not show, but the habit is worth keeping.) Rotation about Y at a few units per frame turns the ship slowly.

## 6. Worked example

[`example/`](example/) is the call sequence of 5.5 written out in one function, run on three files, with the results printed to the TTY. Build and run it with `make run` in `example/`: PCSX-Redux prints (because of `-stdout`) the position and sector count of `SYSTEM.CNF` and `MODEL.BIN`, the text of `SYSTEM.CNF`, the first 12 bytes of `MODEL.BIN`, the two readings of its vertex count (13 and 218,103,808), and what a missing file gives. Edit it: ask for `\DATA\MODEL.BIN` without `;1` (found), then for `\data\model.bin;1` (not found, 5.5).

## 7. Project: "Ship from Disc"

### 7.1 Behaviour

The program boots from `hoverline.cue`, loads `\DATA\MODEL.BIN;1` from the disc, parses it, and draws the ship flat-shaded, turning slowly about its vertical axis, on a dark background. If anything fails, the screen is red.

### 7.2 The contract

`starter/` builds into `hoverline.bin/.cue` and runs, but loads nothing. It gives you `CMakeLists.txt`, `iso.xml`, `system.cnf`, `Makefile`, `psxe/`, the frame loop and matrix code in `main.c`, and `cd_init()`. You write:

| In | What |
|---|---|
| `cdrom.c` | `cd_load_file` |
| `model.c` | `read_be32`, `model_parse` |
| `main.c` | filling `model_info`; `transform_vertices`; `draw_faces` |

**`void *cd_load_file(const char *path, uint32_t *size)`** (declared in `cdrom.h`):

- `path` is a full disc path as `CdSearchFile` takes it: `"\\DATA\\MODEL.BIN;1"`.
- It reads through the SDK: `CdSearchFile`, then `CdRead` (or `CdReadRetry`), then `CdReadSync`. The verifier counts these calls, so the BIOS `open`/`read` route does not pass.
- Returns a `malloc`ed buffer that the caller `free`s. It holds the whole file, is a whole number of sectors long (`ceil(size / 2048) * 2048` bytes) and is 4-byte aligned.
- `*size` is set to the file's size from the directory entry, in bytes. It may be `NULL`.
- Returns `NULL`, with `*size = 0`, when the file is not found (and then reads nothing), is empty, `malloc` fails, the read reports an error, or the read has not finished after 600 video frames (polled once per frame, then `CdReadBreak`). Nothing is leaked on any path.

**`int model_parse(Model *m, const void *data, uint32_t size)`** (declared in `model.h`): the checks of 5.8, in that order. On success it fills `*m` (`verts = data + 8`, `faces = data + 12 + 8 * V`; both point into `data`, nothing is copied) and returns 1. On any failure it returns 0 **and leaves `*m` untouched** (there are no separate error codes).

**`draw_faces`** links exactly one polygon per front face (`NCLIP > 0`): a `POLY_F3` for a triangle, a `POLY_F4` for a quad, in the face's file colour, unlit. Keep the given camera (`rot`, `cam_z`, `proj_h`, the screen centre): the verifier projects the vertices itself and compares the picture.

**State the verifier reads** (do not change names, types or order; `main()` keeps them linked):

| Symbol | Meaning |
|---|---|
| `model_info` | `{int32 vertex_count, face_count; int16 first_vertex[3], last_vertex[3]}`, from the parsed `model` |
| `model`, `model_buf`, `model_size` | the parsed model; what `cd_load_file` returned and its size |
| `load_status` | 0 ok; 1 `CdInit` failed; 2 load failed; 3 parse failed (given) |
| `rot`, `rot_step`, `cam_z`, `proj_h`, `mtx` | angles (4096 = one turn), their per-frame step, camera distance, projection distance, the matrix loaded into the GTE |
| `screen_xy[256]`, `screen_z[256]` | per-vertex results of `RTPS` |
| `prims_submitted` | polygons linked this frame |
| `frame_no`, `frame_done()` | frames completed; the marker the probe waits at |

### 7.3 Steps

1. `make` in `starter/` and boot the disc (`make run`): a red screen, because `cd_load_file` returns `NULL`.
2. Write `cd_load_file` following 5.5: `*size = 0`, search, round, allocate, set location, read, wait with a timeout, free on every failure.
3. Write `read_be32`, then `model_parse`. Test it on paper with the bytes in 5.7 and Appendix E.7's dump before you run it.
4. Fill `model_info` after a successful parse: the counts, vertex 0 and the **last** vertex.
5. Transform the vertices and draw the faces (5.9). Start with `vertex_count` points on screen, then add culling, then colours.

### 7.4 Rules

- **The model comes from the disc.** The verifier checks that the vertex and face tables are not in `game.exe`, and rebuilds the disc with a different model (a pyramid: 5 vertices, 4 triangles, 1 quad) that your program must show.
- Read the counts byte by byte. Do not cast a `uint8_t *` into the file to `uint32_t *`.
- Never read beyond `size`.
- Free what you allocate on every failure path.

### 7.5 Hints

- `CdlFILE` is a struct: `file.pos` is what `CdlSetloc` takes (by address), `file.size` is an `int`.
- `CdReadSync(1, 0)` returns the sectors still pending; loop while it is positive, calling `VSync(0)` between polls so you can count frames.
- Triangles have `i[3] == 0xFF`: use `POLY_F3`, with three corners. Quads are `POLY_F4`, corners `a b c d` in Z order (`setXY4`).
- `gte_ldsz3` / `gte_avsz3` for triangles, `gte_ldsz4` / `gte_avsz4` for quads. `gte_stotz(&otz)` reads the result.
- `load_matrix` is given for the reason in Chapter 25 (SDK macros clobber `$t0`/`$t1`). Call the matrix macros only through it.
- `ot_alloc` returns `NULL` when the frame's primitive buffer is full: stop drawing, do not write.

### 7.6 Stretch goals

- Use `CdReadRetry` so a failed read tries again before `cd_load_file` gives up.
- Print the heap use with `GetHeapUsage` before and after the load and after `free`.
- Load `\SYSTEM.CNF;1` with `cd_load_file` and parse its `BOOT=` line.
- Add a second `MODEL.BIN` to the disc and switch models with a pad button (Chapter 22).
- Read a file with `open`/`read`/`close` (the BIOS API) and compare the time with `CdRead`.

## 8. Verification

```sh
source tools/env.sh
parts/part-06-assets-cdrom-textures-and-compression/ch29-the-cd-rom-and-loading-files/verify/verify.sh            # your starter/
parts/part-06-assets-cdrom-textures-and-compression/ch29-the-cd-rom-and-loading-files/verify/verify.sh --solution # the reference
```

The emulator **boots `hoverline.cue`**: no EXE is side-loaded, so a wrong `SYSTEM.CNF`, name or layout shows up as a boot failure. The probe records, every frame, the angles, the matrix and the polygons it finds by walking the ordering table; it counts calls to the CD library and writes to the controller's registers; in a second run it boots a disc with a different model, and in a third it calls your functions directly. Python compares everything with `tools/assets` (`shpgen.model_bin_manifest`, `formats.parse_model_bin`), not with numbers typed into the checks.

| Check | What it means | If it fails |
|---|---|---|
| `the state symbols exist` | The labels of 7.2 are in the program | You removed a declaration or the keep-alive line |
| `the disc image has SYSTEM.CNF, HOVER.EXE and DATA\MODEL.BIN` | The image, read with a small ISO9660 parser, holds the three files; `BOOT=cdrom:\HOVER.EXE;1`; `HOVER.EXE` is `game.exe`; `MODEL.BIN` is the generator's | `iso.xml` edited wrongly |
| `the model is not inside the program` | The model's vertex and face tables are not in `game.exe` | The model was compiled in (`xxd -i`) |
| `the reference solution's psxe mirrors common/psxe` | Solution only | |
| `boots from the disc, loads and parses the model` | `load_status` is 0 | The hint names the step that failed; the screen is red |
| `the file is read through the CD library` | `CdSearchFile`, `CdRead` (or `CdReadRetry`), `CdReadSync` entered; the controller's registers written; `model_size` is the directory's; the bytes at `model_buf` are the disc file's | Another buffer; a partial read; a rounded size |
| `model_info matches the generator's manifest` | Counts, first and last vertex equal `MODEL.BIN.json` | Byte order of the counts; last vertex index off by one |
| `the model spins slowly about its origin` | `rot` advances by `rot_step` (non-zero, at most 64); the matrix is a rotation, translation `(0, 0, cam_z)`, and changes | `rot_step` ignored; matrix not rebuilt |
| `picture: the ship's silhouette, front faces and flat colours` | At frames 12 and 70 the outline is the hull of the projected vertices (+-5 px); each large front face shows its file colour at its centre; the polygons in the table are exactly the front faces, triangles as `POLY_F3` and quads as `POLY_F4` | Culling missing or reversed; wrong corners; colours from the wrong face |
| `a different MODEL.BIN on the disc (a pyramid)...` | The same checks on a rebuilt disc with another model | Anything about the ship built into the program |
| `cd_load_file: finds files, returns whole-sector buffers...` | Called directly on `SYSTEM.CNF`, `HOVER.EXE`, `MODEL.BIN` (also with a NULL size) and on missing names: size, bytes, last bytes, aligned buffer, a request of at least the rounded size, `NULL`/0/no read for missing | Buffer of `size` bytes; wrong size; a read after a failed search |
| `model_parse: big-endian counts, limits, ...` | 14 crafted images: valid ones (3 vertices, 255 vertices, no faces) give the right `Model`; bad magic, little-endian counts, 0 or 256 vertices, short or long images, an enormous `face_count`, a bad index, a misaligned pointer are rejected with `*m` untouched | A missing validation step; `8 * F` overflow |

A pass ends with `CHAPTER 29: PASSED (12/12 checks)`. Booting the disc takes about 400 emulated frames, so the three emulator runs take about 25 seconds.

## 9. Common pitfalls

- **Little-endian counts.** `*(uint32_t *)(p + 4)` gives 218,103,808 vertices. Read the four bytes.
- **Buffer of `size` bytes.** The drive writes whole sectors; allocate `ceil(size / 2048) * 2048`. It "works" until the neighbouring block is something you care about.
- **Rounded size reported.** `*size` is the directory's byte count, not the sector count times 2048.
- **Waiting without a limit.** A blocking `CdReadSync(0, 0)` freezes the game for as long as the drive struggles, and the library's own watchdog is a detail of one SDK version. Poll, count frames, give up.
- **`CdInit` before `ResetGraph`.** The CD library needs the interrupt system `ResetGraph` sets up.
- **Forgetting `free` on failure paths.** Each early `return NULL` after `malloc` leaks a buffer.
- **Freeing the buffer while the model is in use.** `model.verts` and `model.faces` point into it.
- **Wrong path form.** Write `\DATA\MODEL.BIN;1`: leading backslash, backslashes (doubled in C), upper case as on the disc. 0.24's `CdSearchFile` rejects lower case, and `/` or a missing leading backslash in subdirectory paths, despite what its header says.
- **Trusting `face_count`.** It is not at a fixed offset (it follows the vertices), and `8 * F` overflows 32 bits for a corrupt file.
- **`source` paths in `iso.xml`.** They are relative to the build directory, not to the XML file.
- **Compiling the model in.** It passes on your machine and fails the moment the disc changes; the verifier swaps the model.
- **Matrix macros inline.** `gte_SetRotMatrix`/`gte_SetTransMatrix` clobber `$t0`/`$t1` (Chapter 25): call them only through `load_matrix`.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- psx-spx (nocash PSX specs): "CDROM Drive" (sector formats, modes, commands), "CDROM File Formats" (ISO9660 and `SYSTEM.CNF`), "CDROM Disk Images" (`.cue` and 2352-byte images), "BIOS File Functions".
- `.toolchain/opt/psn00bsdk/include/libpsn00b/psxcd.h` (every function above is documented in its header) and `stdlib.h` (`InitHeap`, `malloc`, `GetHeapUsage`).
- PSn00bSDK's `examples/cdrom/cdbrowse` (directory listing) and the template's `iso.xml`; mkpsxiso's documentation for the XML format.
- Pikuma, the PS1 course's lectures on the CD-ROM and on loading files.
- Next: Chapter 30 loads TIM textures from the same disc and puts them on polygons.
