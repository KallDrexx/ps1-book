# Chapter 31: Compression: LZSS Texture Packs

## 1. Concept

**Compression** stores data in fewer bytes and **decompression** rebuilds it exactly. **LZSS** does it by pointing back at bytes already produced: "copy 11 bytes from where `ABRACADABRA` started" costs two bytes instead of eleven. You write the packer on the PC (Python) and the unpacker on the console (C), and ship eight textures as one small file.

## 2. Why it matters

A CD holds about 650 MB, but the drive delivers only **150 KB/s** at single speed and **300 KB/s** at double speed, and every file costs a seek. Loading is slow, and a game that streams track data while you drive has a hard bandwidth budget. Compression attacks both: fewer sectors to read, and (for a game that fills a disc) fewer discs. The price is CPU time: the R3000 at 33.8688 MHz must rebuild every byte. This chapter's pack shrinks from 16,896 to about 5,300 bytes, saving 11.5 KB of disc reads (38 ms at 300 KB/s) for about 16 ms of decoding. Real PS1 games did exactly this with LZ-family schemes, and the book's capstone loads all its textures this way.

## 3. Learning objectives

After this chapter you can:

- explain **RLE**, **LZ77**, **LZSS** and **LZ78** in a sentence each, and say which one the book uses;
- decode an LZSS stream by hand: flag bits, literals, references, the ring buffer and its cursor;
- write a simple greedy LZSS compressor and explain why any valid encoding decodes correctly;
- build and parse the `.TPK` container, including its size table and **CRC-32** check;
- write a decoder in C that never reads or writes outside its buffers, even on a corrupt file;
- keep a global **texture store** that maps a texture id to the tpage, CLUT and UV data a polygon needs.

## 4. Prerequisites

[Chapter 29](../ch29-the-cd-rom-and-loading-files/README.md) (`cd_load_file`, validating before trusting), [Chapter 30](../ch30-textured-polygons/README.md) (`tim_parse`, `tim_upload`, `tex_from_tim`, the `POLY_FT4`), [Chapters 9](../../part-02-thinking-like-the-r3000/ch09-signed-numbers-logic-and-shifts/README.md) and [12](../../part-02-thinking-like-the-r3000/ch12-risc-vs-cisc-multiply-and-divide/README.md) (shifts and masks; a decoder is nothing else), and [Chapter 5](../../part-01-machine-and-language/ch05-anatomy-of-an-executable/README.md) (a host-side Python tool checked by the harness). [Appendix E.5 and E.6](../../../appendices/E-file-formats.md) specify the LZSS variant and the `.TPK` file; this chapter explains them and you must follow them exactly.

## 5. Explanation

### 5.1 The cost model

| | Raw | Packed |
|---|---|---|
| Bytes to read from disc | 16,896 | about 5,300 |
| Time at 300 KB/s | 56 ms | 18 ms |
| CPU time to rebuild | none | about 16 ms (557,000 cycles) |
| RAM while loading | 16,896 | 5,300 (file) + 16,896 (rebuilt), then the file is freed |

On a console where the CPU would otherwise wait for the drive, trading CPU for bandwidth wins. The next chapters load a `.SHP` model and a `.TRK` track through the same machinery.

### 5.2 A family of schemes

| Scheme | Idea | Weakness |
|---|---|---|
| **RLE** (run-length encoding) | Store "byte, count" for runs | Only helps on runs (flat colour) |
| **LZ77** | Slide a window over the output; each token is (distance, length, next byte) | Spends bits on a "next byte" even when no match exists |
| **LZSS** | LZ77, but a flag bit says literal *or* reference, and a reference is used only when it saves bytes | The one the book uses; simple to decode |
| **LZ78 / LZW** | Build an explicit dictionary of phrases as you go | Needs dictionary memory and a growing table (GIF uses LZW) |

RLE is LZ77's special case "distance 1". LZSS is the sweet spot for a 33 MHz CPU: the decoder is a loop with a flag test, a byte copy and a short copy loop.

### 5.3 The book's LZSS

The decoder keeps a **ring buffer** (a fixed array that wraps around) of the last 4096 bytes it produced. A reference says "copy `len` bytes starting at ring position `pos`".

| Parameter | Value |
|---|---|
| Ring | 4096 bytes, all **zero** at the start |
| Cursor `r` | the next ring slot to write; starts at **4078** (4096 - 18) |
| Flag byte | covers the next 8 items, read **LSB first**; bit **1** = literal, bit **0** = reference |
| Literal | 1 byte, copied to the output |
| Reference | 2 bytes `b0, b1`: `pos = b0 \| ((b1 & 0xF0) << 4)` (a 12-bit **absolute ring position**), `len = (b1 & 0x0F) + 3` (3..18) |
| Every output byte | is also stored at `ring[r]`, then `r = (r + 1) & 4095` |
| End | no marker: stop after exactly `out_size` bytes (the container knows it) |

```
 reference b0 b1:    b0 = pos bits 7..0        b1 = [ pos bits 11..8 | len - 3 ]
                        7              0           7        4 3        0
                       +----------------+         +----------+---------+
                       |  pos low byte  |         | pos high |  len-3  |
                       +----------------+         +----------+---------+

 ring (4096 slots):  0                                     4078        4095
                     +-------------------------------------+-----------+
                     |  zeros at the start                 |  cursor r |
                     +-------------------------------------+-----------+
                     r starts at 4078, moves up one slot per output byte,
                     and wraps from 4095 to 0; each slot holds the newest
                     byte written there, so the ring is the last 4096 bytes
```

Three things to notice. The position is **absolute** (a slot number), not a distance back from the cursor. The cursor starts at 4078 by Okumura's original convention, so the very first literal sits at slot `0xFEE`. And because the ring starts zeroed, a reference into never-written slots yields zeros: a block of zeros needs no literal at all.

**Worked example.** `ABRACADABRA ABRACADABRA` (23 bytes) becomes 14 bytes:

```
7f 41 42 52 41 43 41 44 ee f1 01 20 ee f8

flag 7F = 01111111b, LSB first:  7 literals then a reference
  41 'A' 42 'B' 52 'R' 41 'A' 43 'C' 41 'A' 44 'D'        ring[4078..4084] = ABRACAD
  ee f1  -> pos = 0xEE | (0xF0 << 4) = 0xFEE = 4078, len = 1 + 3 = 4   -> copies ABRA
flag 01 = 00000001b:  a literal then a reference
  20 ' '
  ee f8  -> pos = 4078, len = 8 + 3 = 11                               -> copies ABRACADABRA
```

The second reference starts at the same slot as the first: the stored value is where the text *is* in the ring, not how far back it is. (Run `python example/trace.py "your text"` to see any string tokenised.)

**A decoder** therefore needs: a zeroed 4096-byte ring; a cursor at 4078; a loop that reads a flag byte and walks 8 bits (stopping the moment `out_size` bytes are out); a literal path; a reference path that copies byte by byte (a reference may read bytes it has just written: that is how `AAAA...` works). Because a file from a disc may be damaged, the book's decoder also **never trusts the stream**: it checks that the input has the bytes it is about to read, that a reference fits in what remains of the output, and that no input is left over at the end. Section 5.7 turns that into requirements.

### 5.4 Writing a compressor

The compressor decides, at each position, between a literal and a reference. The simplest policy is **greedy**: find the longest earlier match (3 to 18 bytes), within the last 4095 bytes; if there is one, emit a reference, else a literal.

```
 position i:   ...  X Y Z . . . .  [ A B R A C A ... ]            data (what you have to encode)
                                       ^ i
 window:       the 4095 bytes before i (and, at the very start, 4096 zeros)
 longest match of data[i:] in the window -> (ring position, length)
```

What the encoder must get right:

- Pretend the 4096 zero bytes come **before** your data. A match found `d` bytes back (1 <= d <= 4095) at data index `i - d` lives at ring slot `(4078 + i - d) & 4095`. That slot number is what goes into the reference.
- The match may overlap the bytes it is creating (a run of one byte): source and destination can touch.
- Flag bits are collected eight at a time into a byte that you emit *before* its eight items; the last flag byte may cover fewer than 8 items (leave the unused high bits 0).
- A match of length 2 is not allowed (it would not save a byte); length 18 is the maximum.

**Speed.** A brute-force search tries every earlier position: 4095 comparisons for every byte. In Python that is minutes for 17 KB. Cheaper: let a C-speed built-in do the search (`bytes.rfind` finds the nearest occurrence of a substring inside a range), or keep a dictionary from every 3-byte string to the positions where it occurred. Take the *longest* match, not the first one you find: extending the nearest 3-byte match loses about 15% and lands right at the verifier's limit. A smarter parse ("lazy matching": check whether waiting one byte gives a longer match) squeezes a few percent more; the reference packer is plain greedy.

**Compression ratio is not part of the format.** Any stream the decoder accepts and that reproduces the data is valid: an all-literal stream (every flag 1) is legal, just 12.5% *bigger* than the input. Your packer need not produce the reference's bytes; the verifier requires only a stream the reference decoder accepts *and* at least 85% of the reference's compression ratio on the shipped textures, so that you really emit references.

### 5.5 The `.TPK` container

A `.TPK` holds many TIMs compressed *together* (concatenated first, then one stream, so a texture can reference bytes of the previous one):

```
0x00 +--------------------+
     | "TPK1"             |  magic
0x04 | count    (u32)     |  textures, 1..255
0x08 | raw_size (u32)     |  bytes after decompression = sum of sizes[]
0x0C | comp_size(u32)     |  bytes of the LZSS stream
0x10 | crc32    (u32)     |  CRC-32 of the UNcompressed blob
0x14 | sizes[count] (u32) |  byte size of each TIM (each a multiple of 4)
     +--------------------+ 0x14 + 4*count
     | LZSS stream        |  comp_size bytes, decodes to raw_size bytes
     +--------------------+
     | 0..3 zero bytes    |  pad the file to a multiple of 4
```

Texture **id** = its position in the size table. After decompression, texture `i` is the complete TIM at byte offset `sizes[0] + ... + sizes[i-1]` of the blob; it still names its own VRAM rectangle in its header (the packer never edits TIM bytes), so uploading it is exactly Chapter 30.

**CRC-32** is a 32-bit checksum that changes if any bit of the data changes. It guards against a bad read or a decoder bug: the decompressed blob must have the header's CRC. It is the zlib/PNG one: process bytes through the reflected polynomial `0xEDB88320`, start with `0xFFFFFFFF`, finish by complementing. Python has `zlib.crc32`; in C you write it, a bit at a time:

```
crc = 0xFFFFFFFF
for each byte b:  crc ^= b;  repeat 8 times:  crc = (crc >> 1) ^ (0xEDB88320 if crc & 1 else 0)
result = ~crc
```

(A 256-entry table makes it 8 times faster: a stretch goal.) The check value: the CRC-32 of the nine ASCII characters `123456789` is `0xCBF43926`. Do not checksum the compressed bytes; the decoder's job is to produce the right *raw* bytes.

### 5.6 Packing a folder

`tpkpack.py FOLDER -o OUT.TPK` reads the folder's `*.tim` files, in the plain string order of their names (so `10.tim` sorts before `9.tim`: zero-pad your names), concatenates them, compresses, and writes the header. That order *is* the texture ids, so it must be deterministic. A packer that edits, reorders or re-aligns TIM bytes would move textures in VRAM; keep them verbatim. A packer must also say no: an empty folder or a file that is not a TIM is an error with a message and exit status 1, and no output file (a half-written pack on disc is worse than none).

### 5.7 Unpacking on the PS1

```
 cd_load_file ---> [ TPK file in a malloc'ed buffer ]
                          | tpk_parse: check header, sizes
                          v
                   malloc(raw_size)  <--- lzss_decode: stream -> blob
                          |                tpk_crc32: blob == header's CRC?
                          v
        free(file) ; for each texture: tim_parse -> tim_upload -> tex_from_tim -> store.tex[id]
```

**Layers.** `tpk_parse` validates and copies the header; `lzss_decode` is the decompressor on bare buffers; `tpk_unpack` is parse + decode + CRC into a caller's buffer; `tpk_load` does the whole job. Each is small, and the verifier calls them separately.

**Never trust the file.** A scratched disc or a stray bit must produce an error code, not a crash. The decoder checks (1) before every read that input remains, (2) before a reference that `len <= dst_size - written`, (3) at the end that all input was used. Without (2) a damaged reference writes past the output buffer, and in a C program that corrupts the heap, silently.

**Memory.** The console has 2 MB of RAM; the heap is what the program, its data and the stack leave. This pack needs the compressed file (6,144 bytes: `cd_load_file` rounds up to whole 2,048-byte sectors) plus the raw blob (16,896) at the same time. Free the file as soon as it is decoded. Keep the blob only while you need the TIMs: after upload the pixels are in VRAM and the blob is dead weight. (The book's `main.c` keeps it so the verifier can checksum it; a game would call `tpk_free_raw`.)

**Speed.** The decoder runs about 33 cycles per output byte in the reference (557,000 for this pack). Where it goes: the flag test, the bounds checks and the `ring[r] = c; r = (r + 1) & 4095` for every byte (one load, two stores, two ALU ops). Three habits cost real time: calling a function per byte, wrapping with `%` by a size the compiler cannot see is a power of two (a `div` is 36 cycles, `& 4095` is one), and zeroing the ring item by item. Copying words instead of bytes is possible for literal runs but not for references (they overlap); it is a stretch goal. The verifier allows twice the reference's cycles.

### 5.8 The texture store

A polygon needs four things from a texture: tpage word, CLUT word, and the UV rectangle. `Tex` (Chapter 30) holds them; `TpkTextures` is the book's **texture store**: `tex[id]` for id `0..count-1`, plus the raw blob and its size. Everything above this layer asks for a texture by id and never sees a file or a VRAM coordinate. (Chapter 32 indexes it the same way: a model's primitive says "texture 5".)

## 6. Worked example

[`example/trace.py`](example/trace.py) is a host-only program (no emulator): it compresses a string with the reference compressor and decodes it again, printing every flag byte and item with the ring cursor. `python example/trace.py "ABRACADABRA ABRACADABRA"` reproduces the trace of 5.3. Try `AAAAAAAAAAAAAAAA`, a text of your own, and 32 random letters. Before you run, predict how many bytes each becomes.

## 7. Project: "Eight Textures, One File"

### 7.1 Behaviour

`make` in `starter/` builds a disc whose `\DATA\TEXTURES.TPK` is made by **your** `tpkpack.py` from a folder of eight TIM files (the book's track tiles, `00.tim` to `07.tim`). The game loads it with `tpk_load`, uploads the eight textures, and draws them as a 4 x 2 grid of quads. If anything fails the screen is red.

### 7.2 The contract

`starter/` builds and boots, but the packer writes a placeholder and the loader fails. Given: `CMakeLists.txt` (which runs your packer: `python tpkpack.py build/tiles -o build/assets/TEXTURES.TPK`), `iso.xml`, `cdrom.c` and `tim.c` (Chapters 29 and 30, finished), `psxe/`, `tpk.h`, `main.c` (the frame loop and the grid drawing), `tpkpack.py`'s `main()` and `tpk.c`'s `tpk_free_raw`. You write `read_tims`, `compress` and `build_tpk` in `tpkpack.py`, the other five functions of `tpk.c` (the decoder included), and one line of `main.c`.

**`tpkpack.py FOLDER -o OUT.TPK`** (the starter's `main()` is given; you fill three functions):

| Rule | |
|---|---|
| Input | every file directly inside `FOLDER` whose name ends in `.tim` or `.TIM` (any case), **in plain string order of the names** (`sorted`). Other files and subfolders are ignored |
| Output | the `.TPK` of Appendix E.6: your LZSS stream, the CRC-32 of the raw blob, the size table of the TIM sizes, zero padding to a multiple of 4. TIM bytes are copied verbatim |
| Success | exit status 0, one line on stdout |
| Errors | status **1**, a message on stderr, **no output file**: `FOLDER` missing or not a folder; no `.tim` files; more than 255; a file that is not a TIM (does not start `10 00 00 00`, size not a multiple of 4, or under 20 bytes) |
| Compression | at least 85% of the reference packer's compression ratio on the shipped textures (see 5.4) |
| Time | the verifier allows 90 s per run; a sensible compressor takes under a second |

**`tpk.h`** is the contract for the C side: read it, it is short and carries the exact behaviour, error codes and check order of `tpk_crc32`, `lzss_decode`, `tpk_parse`, `tpk_unpack`, `tpk_load` and `tpk_free_raw`. In brief:

| Function | Contract |
|---|---|
| `uint32_t tpk_crc32(const uint8_t *p, size_t n)` | zlib's CRC-32; any alignment; 0 for `n = 0` |
| `int lzss_decode(src, src_size, dst, dst_size)` | exactly `dst_size` bytes out; `TPK_OK` or `TPK_ERR_DATA` on truncation, overrun, or leftover input; never writes outside `dst[0..dst_size)`, never reads outside `src[0..src_size)`; keep `noinline` |
| `int tpk_parse(file, size, TpkHeader *h)` | `TPK_ERR_MAGIC` / `TPK_ERR_HEADER` by the list in `tpk.h`; copies the sizes into `h` |
| `int tpk_unpack(file, size, dst, dst_size)` | parse; `TPK_ERR_SPACE` if `dst_size < raw_size` (nothing written); decode; `TPK_ERR_CRC` on mismatch |
| `int tpk_load(path, TpkTextures *out)` | read, parse, `malloc(raw_size)`, unpack, free the file, then `tim_parse` / `tim_upload` / `tex_from_tim` for each texture into `out->tex[id]`. Any failure: its negative code, `out->count = 0`, `out->raw = NULL`, `out->raw_size = 0`, nothing leaked |

**The grid.** Given in `main.c`: texture id `i` is drawn in cell `(i % 4, i / 4)`, stretched over a 64 x 64 square whose top-left corner is `(col * 80 + 8, row * 120 + 28)`, corners in Z order, UVs at the texture's first and last texels, colour `(128, 128, 128)`.

**State the verifier reads** (names, types and order are fixed; `main()` keeps them linked):

| Symbol | Meaning |
|---|---|
| `store` | the `TpkTextures` the loader fills |
| `load_status` | 0 = loaded; 100 = `CdInit` failed; otherwise the negative code `tpk_load` returned |
| `tpk_raw`, `tpk_raw_size` | the decompressed blob and its size, copied from `store` after loading; the verifier computes the CRC-32 of these bytes from RAM |
| `prims_submitted`, `frame_no`, `frame_done()` | quads linked this frame; frames completed; the marker the probe waits at |

### 7.3 Steps

1. Run `make` in `starter/` (`make run` boots it): a red screen.
2. In `tpkpack.py`, `build_tpk` with an **all-literal** `compress` first (valid!). Check your output with `python tools/assets/tpkpack_ref.py verify OUT.TPK`.
3. `read_tims`: order, filtering and the error cases of 7.2. Try them by hand.
4. The real `compress`. Compare your size with the reference's: `tpkpack_ref.py pack` on the same folder.
5. In `tpk.c`: `tpk_crc32` (check `123456789`), `tpk_parse`, then `lzss_decode`, `tpk_unpack`, finally `tpk_load`.
6. In `main.c`, replace the placeholder in `load_textures()` by the call to `tpk_load`. Run `verify.sh`.

### 7.4 Rules

- The textures come from the disc as a compressed pack; the packer, not a script of yours, decides the bytes.
- Never edit TIM bytes. Read multi-byte header fields byte by byte.
- `lzss_decode` and `tpk_parse` never read or write outside their buffers, whatever the input.
- Do not hard-code texture counts, sizes or VRAM positions: the verifier boots a second disc with another pack.

### 7.5 Hints

- Host: build the history as `bytes(4096) + data`; for each position try the longest candidate first with `hist.rfind(hist[cur:cur+length], cur - 4095, cur + length - 1)`; the position you store is `(index_in_hist - 18) & 4095`.
- Host: `struct.pack("<IIII", ...)` and `zlib.crc32(raw) & 0xFFFFFFFF`.
- Host: write the output only after packing succeeded.
- C: make the ring `static` (4 KB) and `memset` it at the start of every call; a second call must start from zeros again.
- C: `if (len > dst_size - o)` rather than `o + len > dst_size` (no overflow).
- C: compare your decoder against the worked example of 5.3 (`7f 41 42 ...`) on paper before you run.
- `tpk_unpack` may parse the header again; the cost is negligible.

### 7.6 Stretch goals

- Lazy matching in the compressor: compare ratios.
- A table-driven CRC-32 (build the 256-entry table on first use) and see what it saves in `tpk_unpack`.
- Copy literal runs a word at a time in the decoder.
- Pack `SHIP.TPK`'s textures (tools/assets) and show them in the same grid with 3 cells.
- A `tpkpack.py --list OUT.TPK` mode that prints each texture's size and VRAM rectangle.

## 8. Verification

```sh
source tools/env.sh
parts/part-06-assets-cdrom-textures-and-compression/ch31-compression-lzss-texture-packs/verify/verify.sh            # your starter/
parts/part-06-assets-cdrom-textures-and-compression/ch31-compression-lzss-texture-packs/verify/verify.sh --solution # the reference
```

It takes about 30 seconds. The build runs **your** packer (so a broken packer is a build or a check failure). Host checks use no emulator: they decode your pack with the book's reference decompressor (`tools/assets/lzss.py`) and compare it with the reference packer; they run your packer on crafted folders. Then the emulator boots the disc, a second disc whose pack the **reference packer** made (different textures, depths and VRAM places), and a third run that calls your functions directly with guard bytes around the output buffers. Python compares everything with `tools/assets`, not with numbers typed into the checks.

| Check | What it means | If it fails |
|---|---|---|
| `the state symbols exist` | The labels of 7.2 are in the program | A removed declaration or keep-alive line |
| `the disc image has ...`, `the textures are not inside the program` | `TEXTURES.TPK` is on the disc; the pixels are not in `game.exe` | `iso.xml` edited; textures compiled in |
| `host: your tpkpack.py's TEXTURES.TPK decodes with the REFERENCE decompressor ...` | Magic, count, size table, stream, CRC-32, zero padding and every TIM byte for byte | The message names the field; "CRC32 mismatch" often means a compressor bug (see 9) |
| `host: ... within 85% of the reference packer's compression ratio` | You emit real references | All-literal packer; matches limited to a tiny window |
| `host: edge cases ...` | 1 texture, 5 KB of random data (past the ring size), a 16 KB run of zeros (at most 20%), a pattern repeated at distance 3000 (at most 50%), odd sizes | Ring position as a distance; wrong cursor start; the last flag byte |
| `host: texture ids ...`, `255 textures ...`, `errors ...` | String order; `.TIM` and `.tim`; ignored files; 255 ok, 256 an error; every error case: status 1, message, no file | Sorting by number; a placeholder fallback left in `main()` |
| `boots from the disc; the pack unpacks ...` | `load_status` 0; the CRC-32 and bytes of the blob at `tpk_raw` equal the TIMs' concatenation; `store.tex[i]` has the tpage, CLUT, `u, v, w, h` of E.3.4 | The message gives the first differing byte or the error code of `tpk_load` |
| `VRAM holds each texture's CLUT and image ...` | VRAM rectangles equal the TIM blocks, byte for byte | A texture not uploaded, or in the wrong order of offsets |
| `an alternative disc ...`, `alt run ...` | The same for a reference-packed pack of 4, 8 and 16-bpp textures elsewhere in VRAM; polygons and picture | An unpacker that only works on your packer's output; hard-coded textures |
| `polygons ...`, `picture ...` | Eight `POLY_FT4`, one per cell, with the right words and UVs; each cell shows its texture (90% of sample points within a texel and a colour tolerance) | Wrong ids or `tex[]` entries |
| `performance ...` | `lzss_decode` cycles at most 2x the reference | A call per byte, `%`, a per-item `memset` |
| `lzss_decode: valid streams ...` / `damaged streams ...` | The worked example, all literals, zeros, 5000 random bytes, a pattern past the wrap, runs, the real textures; then truncated, truncated inside a reference, an extra byte, an overrun, too-short and too-long outputs, each with guard bytes | An out-of-bounds write; "reads the byte after `src_size`" |
| `tpk_crc32`, `tpk_parse`, `tpk_unpack`, `tpk_load` | The cases of `tpk.h`: padding 0..3, 13 damaged headers, a buffer one byte short, a bad CRC, a missing file, a second load | A missing check, or an error code that differs from `tpk.h` |

A pass ends with `CHAPTER 31: PASSED (23/23 checks)`. The untouched starter fails. An all-literal packer, a wrong ring start, MSB-first flags, a distance instead of an absolute position and a missing overrun check each fail at least one check, even when packer and unpacker make the same mistake (the reference-packed disc and the reference decoder catch that).

## 9. Common pitfalls

- **Position vs distance.** The reference stores the absolute ring slot, `(4078 + i - d) & 4095`; storing the distance `d` is the most common bug, and the data looks almost right.
- **Cursor at 0, or 4077.** The ring starts at slot 4078 so the first literal is at `0xFEE`.
- **Flag bits MSB first.** The book reads them LSB first.
- **A dirty ring.** The ring must be zeros at every call; a `static` array zeroed once breaks the second load.
- **A reference past the end.** Check `len` against what remains of the output *before* the copy loop.
- **Reading past the stream.** A truncated file must not be completed by whatever bytes follow it in memory.
- **CRC of the compressed bytes.** The header's CRC is of the *raw* blob.
- **Sorting numerically.** `10.tim` comes before `9.tim` in string order. Zero-pad (`00.tim`..`07.tim`).
- **Size table of the VRAM sizes.** It lists TIM *file* sizes.
- **Forgetting padding.** The file is a multiple of 4; the padding is zeros and is not part of `comp_size`.
- **Writing the pack before success.** A failed run must leave no file.
- **`u = w` instead of `w - 1`** (from Chapter 30) when you reuse `tex_from_tim`'s output for the quad UVs.
- **Freeing the blob before the upload is done.** The TIMs live in the decompressed blob, not the file: free the file as soon as it is decoded, but free the blob only after `DrawSync` (`LoadImage` reads it asynchronously).

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- Haruhiko Okumura's original `LZSS.C` (1989): the 4096-byte ring, `F = 18`, `N - F` start, and the flag-byte layout this chapter inherits.
- psx-spx (nocash PSX specs): "CDROM Drive" (speeds and sector timing), "File Formats: TIM".
- RFC 1950 / 1952 (zlib, gzip) and the PNG specification for CRC-32; Python's `zlib` and `binascii` modules.
- [Appendix E.5 and E.6](../../../appendices/E-file-formats.md); `tools/assets/lzss.py` and `tpkpack_ref.py` for the reference compressor and packer; `tools/assets/README.md`.
- Next: Chapter 32 reads a `.SHP` model whose primitives name their textures by the ids you built here.
