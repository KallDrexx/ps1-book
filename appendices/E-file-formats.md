# Appendix E: File Formats

Byte-exact specifications of every file format the book reads or writes. The book's own formats
(`MODEL.BIN`, `.SHP`, `.TPK`, `.TRK`, `SCENE.BIN`) are original designs; the generators in
[`tools/assets/`](../tools/assets/README.md) implement this appendix exactly, and
`tools/assets/selftest.py` proves it with independent parsers written from the text below.
If the appendix and a generator ever disagree, that is a bug in one of them: the selftest fails.

| Format | File(s) | Used in |
|---|---|---|
| PSX-EXE | `*.ps-exe`, `HOVER.EXE` | Ch 5, every chapter |
| `SYSTEM.CNF` | `SYSTEM.CNF` | Ch 29, every disc build after it |
| TIM | `*.TIM` | Ch 30, 31, 35 |
| LZSS (the book's variant) | inside `.TPK` | Ch 31 |
| `.TPK` texture pack | `SHIP.TPK`, `TRACK.TPK`, `PROPS.TPK` | Ch 31, 32, 33, 35 |
| `MODEL.BIN` | `MODEL.BIN` | Ch 29 |
| `.SHP` model | `SHIP.SHP`, `PYLON.SHP`, `ARCH.SHP`, `TOWER.SHP` | Ch 32, 33 |
| `SCENE.BIN` | `SCENE.BIN` | Ch 33 |
| `.TRK` track | `TRACK.TRK`, `TRACK2.TRK` | Ch 34 to 38, 40, 41 |
| VAG | `*.VAG` | Ch 39 |

## E.0 Conventions

These apply to every book format unless a field says otherwise.

| Topic | Rule |
|---|---|
| Endianness | **Little-endian**, like the R3000A. Exceptions, stated per field: the `MODEL.BIN` header counts and the VAG header are **big-endian**. |
| Alignment | Every record starts on a 4-byte boundary and every file size is a multiple of 4 (`.VAG` is a multiple of 16 after its 48-byte header). Padding bytes are zero. A conforming reader may ignore them; a writer must write zeros. |
| Offsets | Offsets in headers are **bytes from the start of the file**, never relative to a section. |
| Counts and indices | `u16` unless stated. Indices are zero-based. |
| Magic | Four ASCII bytes at offset 0, ending in a version digit (`SHP1`). A reader rejects an unknown magic instead of guessing. |
| Strings | ASCII, NUL-padded to a fixed width; never assume a trailing NUL when the field is full. |
| Axes | **+X right, +Y down, +Z forward** (into the screen), as in Part V. "Up" is **-Y**: a hill has a negative `y`. |
| Winding | A face is front-facing when its vertices run **clockwise as seen from outside** (`NCLIP` positive, Ch 25). Consequently the cross product `(v1-v0) x (v2-v0)` points **into** the solid. Stored normals point **out**. |
| Quads | **Z order**: the quad is the triangles `(v0,v1,v2)` and `(v1,v3,v2)`; the outline runs `v0, v1, v3, v2`. Same as `POLY_F4`/`POLY_FT4`. |
| Fixed point | **4.12**: `4096 = 1.0`, stored as `s16`. Unit vectors have components in `-4096..4096`. Angles: `4096 = 360 degrees` (`isin`/`icos` units). |
| Colours | Three bytes **R, G, B** (0..255), then one zero byte, exactly the order `setRGB0` expects. In a textured primitive `128` is the neutral modulation colour. VRAM and CLUT colours are 16-bit **BGR555** (`R` in bits 0-4). |
| UV | Bytes `u, v` in **texels**, `0..255`, measured from the top-left of the texture's own image (see E.3.4 for how a loader adds the texture's VRAM offset). The last texel of an `n`-wide texture is `u = n-1`. |
| Checksums | Only `.TPK` has one (CRC-32, the zlib/PNG polynomial). |

Types in tables: `u8 u16 u32` unsigned, `s16 s32` signed (two's complement), `char[n]` ASCII.

## E.1 PSX-EXE

Documented in [Chapter 5](../parts/part-01-machine-and-language/ch05-anatomy-of-an-executable/README.md).
Summary: a 2048-byte header (`"PS-X EXE"` magic at 0x00, initial PC 0x10, initial GP 0x14, load address 0x18,
payload size 0x1C, stack base 0x30, region string at 0x4C, zero padding to 0x800) followed by the payload.
PSn00bSDK's `elf2x` writes the same header for the C chapters. Reference tool: the reader's `exeinfo.py` from Chapter 5.

## E.2 SYSTEM.CNF and the CD layout

The BIOS boots a disc by reading `SYSTEM.CNF` in the root directory. The book's disc builds use exactly the file
PSn00bSDK's template ships (LF line endings are accepted):

```
BOOT=cdrom:\HOVER.EXE;1
TCB=4
EVENT=10
STACK=801FFFF0
```

| Line | Meaning |
|---|---|
| `BOOT` | `cdrom:\` + the executable's root-directory name (8.3, upper case) + `;1`, the ISO9660 version suffix. A subdirectory is written `cdrom:\DIR\NAME.EXE;1`. |
| `TCB` | Number of kernel thread control blocks, **hexadecimal** without a prefix. 4 is the usual default. |
| `EVENT` | Number of kernel event control blocks, also **hexadecimal**: `10` is 16 (psx-spx, *CDROM File Formats*: `EVENT = 10 ;HEX (=16 decimal)`). |
| `STACK` | Initial stack pointer, hexadecimal. `801FFFF0` is the top of the 2 MB RAM minus 16 bytes, the value PSn00bSDK's template uses (psx-spx's example shows `801FFF00`; both work). (`HOVER.EXE`'s own header also carries a stack base; see Chapter 5.) |

psx-spx describes CR LF line ends; the BIOS (and OpenBIOS) also accept the template's LF-only file. An optional argument after `BOOT=...;1` is copied to RAM `0x80000180`; the book does not use it.

mkpsxiso layout used from Chapter 29 on (tested with mkpsxiso 2.30: `mkpsxiso -y -q layout.xml` writes `hoverline.bin`/`.cue`, and the image boots in PCSX-Redux without a side-loaded EXE; `source` paths are relative to the directory mkpsxiso runs in):

```xml
<?xml version="1.0" encoding="utf-8"?>
<iso_project image_name="hoverline.bin" cue_sheet="hoverline.cue">
  <track type="data">
    <identifiers system="PLAYSTATION" application="PLAYSTATION" volume="HOVERLINE"
                 volume_set="HOVERLINE" publisher="PS1BOOK" data_preparer="MKPSXISO"
                 copyright="README.TXT;1"/>
    <directory_tree>
      <file name="SYSTEM.CNF" type="data" source="system.cnf"/>
      <file name="HOVER.EXE"  type="data" source="hover.exe"/>
      <dir name="DATA">
        <file name="MODEL.BIN" type="data" source="build/assets/MODEL.BIN"/>
        <file name="SHIP.SHP"  type="data" source="build/assets/SHIP.SHP"/>
        <!-- ...one <file> per asset... -->
      </dir>
      <dummy sectors="1024"/>
    </directory_tree>
  </track>
  <!-- Chapter 39 adds: <track type="audio" source="music.wav"/> -->
</iso_project>
```

Rules worth remembering: names are 8.3 and case-insensitive (mkpsxiso warns beyond 12 characters); the root directory
holds at most 30 entries and the disc at most 45 directories (PSn00bSDK template comments); `system` and `application`
must read `PLAYSTATION`; `CdSearchFile` takes the path `\DATA\MODEL.BIN;1`. No licence file is needed for emulators
(real Japanese/PAL consoles may demand one; Chapter 42). `<dummy sectors="1024"/>` pads the image end, as the SDK template does.

## E.3 TIM (texture image)

A Sony format the PS1 tool chain has used since 1994, so any TIM tool can read the book's files.
Little-endian, 4-byte aligned. A TIM holds up to two blocks that are **raw VRAM rectangles**: the CLUT and the image.
Uploading a block means `LoadImage` with the rectangle in its header; the pixel data is copied untouched.

```
+--------------------+ 0x00   magic 0x00000010
| header (8 bytes)   |        flags
+--------------------+ 0x08
| CLUT block         |        only if flags bit 3 is set (always for 4/8 bpp)
|  bnum,x,y,w,h,data |
+--------------------+
| image block        |
|  bnum,x,y,w,h,data |
+--------------------+
```

### E.3.1 Header

| Offset | Size | Field | Meaning |
|---|---|---|---|
| 0x00 | u32 | magic | `0x00000010` (bytes `10 00 00 00`). |
| 0x04 | u32 | flags | bits 0-2 **pmode**: 0 = 4 bpp, 1 = 8 bpp, 2 = 16 bpp, 3 = 24 bpp (4 = "mixed" exists in Sony's spec; the book never writes it and its readers may reject it). bit 3: **CLUT present**. All other bits 0. |

### E.3.2 Block (used for both CLUT and image)

| Offset | Size | Field | Meaning |
|---|---|---|---|
| +0x00 | u32 | bnum | Block size in bytes **including this 12-byte header**: `12 + w*h*2`. |
| +0x04 | u16 | x | VRAM X of the rectangle, in **16-bit units** (0..1023). |
| +0x06 | u16 | y | VRAM Y in lines (0..511). |
| +0x08 | u16 | w | Width in **16-bit units** (not pixels). |
| +0x0A | u16 | h | Height in lines. |
| +0x0C | | data | `w*h*2` bytes, row-major, as VRAM holds them. |

### E.3.3 Pixel formats

| bpp | CLUT | Image width `w` (units) for `P` pixels | Pixel packing in each 16-bit unit |
|---|---|---|---|
| 4 | 16 entries: `w=16, h=1` | `P/4` | 4 pixels; **low nibble = leftmost pixel** |
| 8 | 256 entries: `w=256, h=1` | `P/2` | 2 pixels; low byte = leftmost |
| 16 | none | `P` | 1 pixel, BGR555; bit 15 = STP (semi-transparency) |
| 24 | none | `P*3/2` | 3 bytes R,G,B per pixel, packed back to back (`P` even) |

A CLUT entry is a 16-bit BGR555 colour. **Entry value `0x0000` is transparent** when drawn; a real black must be non-zero.
`img2tim.py` writes opaque black as `0x0421` and transparent PNG pixels (alpha < 128) as `0x0000`.
A CLUT block may have `h > 1` rows (several palettes); the book writes one.
`bnum` and the data size must agree, and the book keeps `w*h` even so every TIM is a multiple of 4 bytes.

### E.3.4 Texture pages, TSB, CBA and UV (used by `.SHP` and `.TRK`)

A texture's pixels live where its image block says. The GPU reaches them through a **texture page** (`tpage`, "TSB")
and per-vertex UVs inside it:

| Value | Formula (`x` in 16-bit units, `y` in lines) |
|---|---|
| `TSB` (tpage word) | `(x/64) \| ((y/256) << 4) \| (abr << 5) \| (tp << 7)`, `tp` = 0 (4 bpp), 1 (8 bpp), 2 (16 bpp); `abr` = semi-transparency mode 0..3 (0 for opaque). Same as `getTPage`. |
| `CBA` (CLUT word) | `(clut_x/16) \| (clut_y << 6)`. `clut_x` must be a multiple of 16. Same as `getClut`. |
| UV origin `(u0, v0)` | `((x mod 64) * m, y mod 256)`, with `m` = 4 (4 bpp), 2 (8 bpp), 1 (16 bpp). |
| Absolute UV | `(u + u0, v + v0)`, where `(u, v)` is the texture-local UV stored in the file. |

A page starts on a 64-unit boundary in x (a multiple of 256 lines in y) and spans 256 x 256 **texels**: 64 units of VRAM at 4 bpp, 128 at 8 bpp, 256 at 16 bpp. **A texture must not run past the end of its page**:
`u0 + width_in_texels <= 256` and `v0 + height <= 256`. UVs are also limited to 0..255, so a 4-bpp texture is at most 256 wide.
`img2tim.py --check` warns when a TIM crosses a page. The book's default placements are in `tools/assets/layout.py`
(framebuffers use x 0-319, y 0-479; textures sit to the right, CLUTs below y = 480).

**Worked example** (generated by `tools/assets/examples.py`): a 4-bpp 8x2-pixel image at VRAM (320, 16) with a 16-entry CLUT at (0, 480):

```
00000000: 10 00 00 00 08 00 00 00 2c 00 00 00 00 00 e0 01  ........,.......
00000010: 10 00 01 00 00 00 1f 00 e0 03 00 7c 00 00 00 00  ...........|....
00000020: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00  ................
00000030: 00 00 00 00 14 00 00 00 40 01 10 00 02 00 02 00  ........@.......
00000040: 10 32 23 01 11 22 33 00                          .2#.."3.
```

Reading it: `10 00 00 00` magic; `08 00 00 00` flags (CLUT present, 4 bpp); CLUT block `bnum 0x2C`, x 0, y `0x1E0` = 480, w 16, h 1,
then entries `0000 001F 03E0 7C00` (transparent, red, green, blue) and twelve zero entries; image block `bnum 0x14`, x `0x140` = 320, y 16,
w 2 units (= 8 pixels), h 2; the first byte `10` is pixels 0 (low nibble) and 1 (high nibble), `32` is pixels 2 and 3.

**Pitfalls.** Widths are in 16-bit units, so a 4-bpp 64-pixel texture has `w = 16`. The CLUT is uploaded separately and must not overlap
anything. `LoadImage` is asynchronous (`DrawSync`). Reading a TIM with `h` and `w` swapped uploads garbage that looks plausible.
24-bpp TIMs are display-only (Ch 16); textured polygons cannot use them.

**Reference implementation:** `tools/assets/tim.py` (read/write), `tools/assets/img2tim.py` (PNG to TIM, `--check`, `--to-png`).

## E.4 VAG (SPU-ADPCM sound)

The PS1 SPU plays 4-bit ADPCM. A `.VAG` file is a 48-byte header followed by 16-byte blocks that go to SPU RAM unchanged.
**The header is big-endian**; the block data has no byte order.

### E.4.1 Header (48 bytes)

| Offset | Size | Field | Meaning |
|---|---|---|---|
| 0x00 | 4 | magic | `VAGp` |
| 0x04 | u32 BE | version | `0x00000020` (the book writes 0x20; readers ignore it). |
| 0x08 | u32 | reserved | 0 |
| 0x0C | u32 BE | size | Bytes of block data that follow the header (`file size - 48`), a multiple of 16. |
| 0x10 | u32 BE | rate | Sample rate in Hz (e.g. 22050). SPU pitch = `rate * 4096 / 44100` (`0x1000` = 44100 Hz). |
| 0x14 | 12 | reserved | zeros |
| 0x20 | char[16] | name | NUL-padded |

### E.4.2 Block (16 bytes = 28 samples)

```
byte 0       byte 1      bytes 2..15
+----+----+  +--------+  +-------------------------------------------+
|filt|shft|  | flags  |  | 14 bytes = 28 four-bit samples            |
+----+----+  +--------+  | byte n: low nibble = sample 2n, high = 2n+1|
 hi   lo                  +-------------------------------------------+
```

| Field | Bits | Meaning |
|---|---|---|
| shift | byte 0 bits 0-3 | Range 0..12, 0 = loudest. 13..15 are reserved (reported to act like 9; the book never writes them and its decoder treats them as 9). |
| filter | byte 0 bits 4-6 | 0..4 selects `(f0, f1)` = (0,0), (60,0), (115,-52), (98,-55), (122,-60). |
| flags | byte 1 | bit 0 **loop end**: after this block, set the voice's `ENDX` bit and jump to the repeat address. bit 1 **repeat**: only with bit 0; 0 = also force the envelope to release at level 0 (silence), 1 = keep playing (a loop). bit 2 **loop start**: copy this block's address into the repeat address register. Bits 3-7: 0. |
| samples | bytes 2-15 | Signed 4-bit values, two's complement, **low nibble first**. |

**Decoding** (per sample `n`, with `old`, `older` the two previous output samples, both starting at 0 and *kept across blocks*):

```
s = ((n << 12) >> shift) + ((old * f0 + older * f1 + 32) >> 6)     # arithmetic shifts
s = clamp(s, -32768, 32767);  older = old;  old = s
```

(psx-spx gives the same filter table and the `+32 >> 6` rounding; emulators differ from each other by at most one LSB, so tests compare with a tolerance.)

Flag byte values (psx-spx, *SPU ADPCM Samples*):

| Value | Meaning | The book writes it |
|---|---|---|
| `00` | normal block | every audio block |
| `01` | end + mute: jump to the repeat address, set `ENDX`, envelope to 0 | the end block of a one-shot |
| `02` | ignored (repeat without end) | never |
| `03` | end + repeat: jump to the repeat address, set `ENDX`, keep playing | the last block of a loop |
| `04` | loop start: this block becomes the repeat address | the first block of a loop |
| `06`, `07` | loop start combined with repeat / end + repeat: a block that loops onto itself (other tools end one-shots with a silent `07` block) | never |

The repeat address is a voice register (`1F801C0Eh + 16*voice`). Key-on copies the start address to the current address but does not
reset the repeat address, so a one-shot's `01` end block jumps somewhere arbitrary; that is harmless because its envelope is already at 0.
A voice keeps running after `01` (the SPU cannot stop a voice); `ENDX` tells the program that the sample finished.
(How each emulator handles `01` versus a silent `07` block is for Chapter 39 to confirm in PCSX-Redux, DuckStation and Mednafen.)

### E.4.3 Layout of a file written by `wav2vag.py`

| Block | Contents |
|---|---|
| 0 | 16 zero bytes (silent lead-in, flags 0). Standard practice; the SPU starts from a clean state. |
| 1 .. N | audio, flags 0, padded with zero samples to a multiple of 28. The first block always uses filter 0. |
| last (no loop) | **end block**: `00 01` followed by 14 zero bytes. |
| loop | block `L` (default 1) has flag **4** (loop start); the last audio block has flags **3** (end + repeat); no separate end block. The loop-start block uses filter 0 because the SPU keeps its filter history across the jump. |

The decoded length is always a multiple of 28; the header stores no sample count. Looping is meaningful only if the sample was *designed*
to loop (`ENGINE.WAV` has a whole number of cycles and 28 x 787 samples). SPU RAM addresses are in units of 8 bytes; the 16-byte blocks keep that.

**Worked example**: a 56-sample sine, no loop (`tools/assets/examples.py`): 48-byte header, silent block, two audio blocks, end block.

```
00000000: 56 41 47 70 00 00 00 20 00 00 00 00 00 00 00 40  VAGp... .......@
00000010: 00 00 56 22 00 00 00 00 00 00 00 00 00 00 00 00  ..V"............
00000020: 73 69 6e 65 00 00 00 00 00 00 00 00 00 00 00 00  sine............
00000030: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00  ................
00000040: 01 00 30 65 56 03 bd aa db 30 65 56 03 bd aa db  ..0eV....0eV....
00000050: 34 00 02 66 77 03 bd 89 cb 30 75 77 03 bd 89 cb  4..fw....0uw....
00000060: 00 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00  ................
```

The first 0x30 bytes: `VAGp`, version 0x20, size `0x40` (4 blocks), rate `0x5622` = 22050, name `sine`. At 0x40 the first audio block: shift 1, filter 0, flags 0.
The last block `00 01 00...` is the end block. The real `ENGINE.VAG` begins:

```
00000000: 56 41 47 70 00 00 00 20 00 00 00 00 00 00 31 40  VAGp... ......1@
00000010: 00 00 56 22 00 00 00 00 00 00 00 00 00 00 00 00  ..V"............
00000020: 65 6e 67 69 6e 65 00 00 00 00 00 00 00 00 00 00  engine..........
00000030: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00  ................
00000040: 01 04 66 66 66 66 66 77 77 77 77 77 77 77 77 77  ..fffffwwwwwwwww
```

(size 0x3140; the loop flags are in blocks 1 and N, see the selftest.)

**Pitfalls.** Header fields are big-endian. Upload the whole block data (a multiple of 16 bytes) and keep the SPU RAM address 8-byte aligned. Forgetting the end/repeat flags
makes a sample run on into whatever follows it in SPU RAM (noise). A voice reaching an end block without the repeat bit goes silent.

**Reference implementation:** `tools/assets/vag.py` (encoder and decoder), `wav2vag.py` (WAV to VAG, `--loop`, `--loop-start`), `vag2wav.py`, `sfxgen.py` (the generated effects).

## E.5 The book's LZSS

Used only inside `.TPK`. A classic Okumura-style LZSS with a **4096-byte ring buffer**. It is chosen to be the smallest thing that is
still real: a decoder is about 25 lines of C.

| Parameter | Value |
|---|---|
| Ring size `N` | 4096 (positions 0..4095) |
| Max match `F` | 18 |
| Min match | 3 (a 2-byte reference must save space) |
| Ring initial fill | all **0x00** |
| Ring write cursor `r` at start | **4078** (`N - F`) |
| Flag byte | covers the next **8 items**, consumed **LSB first** |
| Flag bit **1** | literal: copy 1 byte from the input |
| Flag bit **0** | reference: 2 bytes `b0, b1` follow |
| Reference | `pos = b0 \| ((b1 & 0xF0) << 4)` (absolute ring index, 12 bits); `len = (b1 & 0x0F) + 3` (3..18) |
| Every output byte | is also stored at `ring[r]`, then `r = (r + 1) & 4095` |
| End | There is **no end marker**. The decoder stops after exactly `out_size` bytes (known from the container). Unused high bits of the last flag byte are written as 0 and ignored. The input must be fully consumed; a reference that would overrun `out_size` is an error. |

```c
/* reference decoder, C-style: n bytes out; no bounds checks (a valid stream never overruns n) */
uint8_t ring[4096] = {0};  unsigned r = 4078, o = 0;
while (o < n) {
    unsigned flags = *in++;
    for (int bit = 0; bit < 8 && o < n; bit++, flags >>= 1) {
        if (flags & 1) { uint8_t c = *in++; out[o++] = ring[r] = c; r = (r + 1) & 4095; }
        else { unsigned b0 = *in++, b1 = *in++, pos = b0 | ((b1 & 0xF0) << 4), len = (b1 & 15) + 3;
               for (unsigned k = 0; k < len; k++) { uint8_t c = ring[(pos + k) & 4095];
                   out[o++] = ring[r] = c; r = (r + 1) & 4095; } }
    }
}
```

Copying is byte by byte, so a reference may read bytes it has just written (a run `AAAA...` is `A` then a reference to the slot just filled).
The ring starts zeroed, so references into the not-yet-written area yield zeros: a block of zeros compresses without a single literal.
The compressor in this book is greedy (hash chains, longest match, nearest on ties, distance 1..4095); **any valid stream decodes identically**,
so a reader's packer need not produce the same bytes as the reference, only a stream that the reference decoder accepts and that round-trips.

**Worked example.** Input `ABRACADABRA ABRACADABRA` (23 bytes) compresses to 14 bytes:

```
00000000: 7f 41 42 52 41 43 41 44 ee f1 01 20 ee f8        .ABRACAD... ..
```

Bit-by-bit trace (`tools/assets/examples.py` prints it):

```
flag byte 0x7F = 01111111b (read LSB first)
  bit0=1 literal 0x41 'A'
  bit1=1 literal 0x42 'B'
  bit2=1 literal 0x52 'R'
  bit3=1 literal 0x41 'A'
  bit4=1 literal 0x43 'C'
  bit5=1 literal 0x41 'A'
  bit6=1 literal 0x44 'D'
  bit7=0 ref bytes EE F1: pos=4078 (0xFEE), len=4 -> 'ABRA'
flag byte 0x01 = 00000001b (read LSB first)
  bit0=1 literal 0x20 ' '
  bit1=0 ref bytes EE F8: pos=4078 (0xFEE), len=11 -> 'ABRACADABRA'
```

The ring cursor starts at 4078, so the first literal `A` sits at ring position 4078 (`0xFEE`); both references name that position.
Distance is `(r - pos) mod 4096`, but the stored value is the *absolute* position, not the distance: the most common reader bug.

**Reference implementation:** `tools/assets/lzss.py` (`compress(data)`, `decompress(data, out_size=None)`). Import it from verify scripts:
`sys.path.insert(0, ".../tools/assets"); import lzss`.

## E.6 `.TPK` texture pack

One file holding many TIMs, compressed together: a header, a size table, and a single LZSS stream of the concatenated TIM files.
Used for `SHIP.TPK` (3 textures), `TRACK.TPK` (8) and `PROPS.TPK` (2). Texture **id = position in the table**, `0..count-1`.
All fields little-endian; offsets from the start of the file.

```
0x00 +--------------------+
     | "TPK1"             |
0x04 | count    (u32)     |
0x08 | raw_size (u32)     |   sum of sizes[]
0x0C | comp_size(u32)     |   bytes of the LZSS stream
0x10 | crc32    (u32)     |   CRC-32 of the uncompressed blob
0x14 | sizes[count] (u32) |   byte size of each TIM, each a multiple of 4
     +--------------------+ 0x14 + 4*count
     | LZSS stream        |   comp_size bytes, decodes to raw_size bytes
     +--------------------+
     | 0..3 zero bytes    |   pad the file to a multiple of 4
```

| Offset | Size | Field | Meaning |
|---|---|---|---|
| 0x00 | 4 | magic | `TPK1` |
| 0x04 | u32 | count | Number of textures, 1..255. |
| 0x08 | u32 | raw_size | Total bytes after decompression. |
| 0x0C | u32 | comp_size | Compressed bytes. |
| 0x10 | u32 | crc32 | CRC-32 (reflected, polynomial `0xEDB88320`, init and final XOR `0xFFFFFFFF`: zlib's `crc32`) of the uncompressed blob. |
| 0x14 | u32[count] | sizes | Size of texture `i`'s TIM. |
| 0x14 + 4*count | | stream | The compressed blob. |

Decompress once into one buffer (`raw_size` bytes); texture `i` is at `sum(sizes[0..i-1])` and is an ordinary complete TIM
(magic, CLUT block, image block), which still names its own VRAM position. Uploading is `LoadImage` of its CLUT and image blocks.

Real header (first 0x40 bytes of the generated `TRACK.TPK`: 8 textures of 0x840 bytes, raw 0x4200, compressed 0x151F, CRC `C2D7A540`):

```
00000000: 54 50 4b 31 08 00 00 00 00 42 00 00 1f 15 00 00  TPK1.....B......
00000010: 40 a5 d7 c2 40 08 00 00 40 08 00 00 40 08 00 00  @...@...@...@...
00000020: 40 08 00 00 40 08 00 00 40 08 00 00 40 08 00 00  @...@...@...@...
00000030: 40 08 00 00 d5 10 eb f0 08 ef f0 2c eb f2 e0 01  @..........,....
```

and a tiny two-texture pack of the example TIM above (the second copy compresses to a reference):

```
00000000: 54 50 4b 31 02 00 00 00 90 00 00 00 38 00 00 00  TPK1........8...
00000010: 14 f2 52 26 48 00 00 00 48 00 00 00 d5 10 eb f0  ..R&H...H.......
00000020: 08 ef f0 2c e9 f2 e0 01 f7 10 00 01 f9 f0 1f 00  ...,............
00000030: e0 03 53 00 7c dc ff 1b 03 14 1f 00 40 fd f0 fd  ..S.|.......@...
00000040: 02 29 00 10 32 23 01 11 22 21 33 ed ff ff ff 11  .)..2#.."!3.....
00000050: 0f 23 0f 00                                      .#..
```

**Pitfalls.** The size table is the TIM sizes, not the VRAM sizes. Decompress to RAM with enough room (`raw_size`, not `comp_size`).
Textures that are not tpage-aligned still work, but each TIM's header decides the VRAM spot, so two packs can overwrite each other.
Do not CRC the compressed bytes.

**Reference implementation:** `tools/assets/formats.py` (`build_tpk`, `parse_tpk`), CLI `tools/assets/tpkpack_ref.py pack|unpack|verify`.
(Chapter 31's reader writes their own `tpkpack.py`; the reference has a different name so the two never collide.)

## E.7 `MODEL.BIN` (Chapter 29)

The first model format: just enough structure to practise reading bytes and fixing byte order. It holds a ship-like mesh of
flat-coloured triangles and quads. **The two counts are big-endian on purpose** (a classic cross-platform file header), while the
vertex and face data are little-endian (native). Everything is 4-byte aligned.

```
0x00 "MDL1"
0x04 vertex_count  u32 BIG-endian
0x08 vertices      vertex_count x 8 bytes
     face_count    u32 BIG-endian            (at 0x08 + 8*vertex_count)
     faces         face_count x 8 bytes
```

| Item | Size | Layout |
|---|---|---|
| magic | 4 | `MDL1` |
| vertex_count `V` | u32 **BE** | 1..255 |
| vertex | 8 | `s16 x, s16 y, s16 z, s16 pad(0)` little-endian, model units (the `SVECTOR` layout) |
| face_count `F` | u32 **BE** | |
| face | 8 | `u8 i0, i1, i2, i3` vertex indices; **`i3 = 0xFF` means triangle**; then `u8 r, g, b, 0` flat colour |

File size is `12 + 8*V + 8*F`. Quads are Z order and faces are clockwise from outside (E.0), so Chapter 25's `NCLIP` back-face
culling works unchanged. The generated ship is a convex hull (13 vertices, 4 triangles, 9 quads), nose along +Z at z = 300, about 450 units long (z from -150 to 300).

```
00000000: 4d 44 4c 31 00 00 00 0d 00 00 00 00 2c 01 00 00  MDL1........,...
00000010: 00 00 d6 ff 64 00 00 00 ac ff 06 00 64 00 00 00  ....d.......d...
00000020: 00 00 18 00 64 00 00 00 54 00 06 00 64 00 00 00  ....d...T...d...
```

`4D 44 4C 31` is the magic; `00 00 00 0D` is 13 vertices **in big-endian** (read as little-endian it would be 218,103,808, the bug the chapter provokes).
The vertex at 0x08 is `00 00 | 00 00 | 2C 01 | 00 00` = (0, 0, 300), the nose; the next is (0, -42, 100). The face table is at the end of the file; its last three faces:

```
000000c4: 08 07 0c 0b 5a 5e 67 00 05 08 09 0c bb c4 d7 00  ....Z^g.........
000000d4: 0a 09 0b 0c 6a 6f 7a 00                          ....joz.
```

Each line reads `i0 i1 i2 i3 r g b 00`: these three are quads (`i3` = 0x0B, 0x0C, 0x0C); a triangle shows `FF` in the fourth byte.

**Pitfalls.** Swap the two counts (and only them): `vertex_count = (b[4]<<24)|(b[5]<<16)|(b[6]<<8)|b[7]`. Do not byte-swap the vertices. `face_count` is
not at a fixed offset: it follows the vertices. Vertex indices fit a byte, so a model has at most 255 vertices.

**Reference implementation:** `tools/assets/shpgen.py --model-bin OUT.BIN [--manifest m.json]` writes it; `formats.py` (`build_model_bin`, `parse_model_bin`) reads it.
**Manifest schema** (`MODEL.BIN.json`): `file, size, sha256, vertex_count, face_count, triangles, quads, first_vertex[3], last_vertex[3], first_face{indices,color}, last_face{indices,color}, header_hex`.
Chapter 29's probe compares the parsed counts and the first and last vertices with it.

## E.8 `.SHP` object (Chapters 32, 33)

A named mesh with a vertex list, a normal list and a list of **variable-length primitive records**, each tagged with one of eight types.
A parser walks the list by the `size` field in each record and builds the matching GPU primitive. All fields little-endian.

```
0x00 +--------------------+
     | header (0x40)      |
0x40 +--------------------+  vertices_offset
     | vertices  8 B each |
     +--------------------+  normals_offset
     | normals   8 B each |
     +--------------------+  prims_offset
     | primitives         |  prims_size bytes, records back to back
     +--------------------+  file_size
```

### E.8.1 Header (0x40 bytes)

| Offset | Size | Field | Meaning |
|---|---|---|---|
| 0x00 | 4 | magic | `SHP1` |
| 0x04 | u32 | file_size | Whole file. |
| 0x08 | char[16] | name | Object name, e.g. `SHIP`. |
| 0x18 | u16 | vertex_count | |
| 0x1A | u16 | normal_count | |
| 0x1C | u16 | prim_count | |
| 0x1E | u16 | texture_count | Highest `texture index + 1` used by any textured primitive (0 if none). The matching `.TPK` must hold at least this many textures. |
| 0x20 | u32 | vertices_offset | Always 0x40. |
| 0x24 | u32 | normals_offset | `0x40 + 8*vertex_count` |
| 0x28 | u32 | prims_offset | `normals_offset + 8*normal_count` |
| 0x2C | u32 | prims_size | Bytes of primitive data; `prims_offset + prims_size = file_size`. |
| 0x30 | s16[6] | bbox | `min x,y,z, max x,y,z` over all vertices. |
| 0x3C | u32 | reserved | 0 |

Vertex: `s16 x, y, z, pad` (8 bytes, the `SVECTOR` layout, ready for `gte_ldv0`). Normal: `s16 x, y, z` in **4.12**, pad (8 bytes).
The list holds one entry per distinct face normal; primitives name theirs by index, so several faces share an entry.
A normal points **out** of the solid and equals `-normalize((v1-v0) x (v2-v0))` for a clockwise-from-outside face (for a quad, the area vector of the outline `v0,v1,v3,v2`).

### E.8.2 Primitive records

Every record starts with a 4-byte prefix and its size is a multiple of 4:

| Offset | Size | Field | Meaning |
|---|---|---|---|
| +0 | u8 | type | 0 `F3`, 1 `F4`, 2 `G3`, 3 `G4`, 4 `FT3`, 5 `FT4`, 6 `GT3`, 7 `GT4` (F flat, G Gouraud, T textured, 3 triangle, 4 quad) |
| +1 | u8 | flags | bit 0 **double sided** (skip back-face culling), bit 1 **semi-transparent** (set the primitive's semi-transparency bit with `setSemiTrans`; the blend mode is bits 5-6 of the TSB for a textured primitive, and of the current draw mode (a `DR_TPAGE` primitive or `DRAWENV.tpage`) for an untextured one; the book uses mode 0, 50%+50%), bit 2 **unlit** (colours are final, skip lighting). Other bits 0. |
| +2 | u16 | size | Total bytes of this record, from the table below. A parser may use it to skip unknown types. |

The body follows in this order; items that do not apply are absent:

| Order | Item | Size | Present for |
|---|---|---|---|
| 1 | vertex indices | 3 x u16 (tri) or 4 x u16 (quad), Z order | all |
| 2 | face normal index | u16 | all |
| 3 | zero pad | u16 | quads only (keeps 4-byte alignment) |
| 4 | UVs | 3 or 4 x (`u8 u, u8 v`) | `FT*`, `GT*` |
| 5 | texture index | u16 | `FT*`, `GT*`: index into the `.TPK` |
| 6 | zero pad | u16 | textured quads only |
| 7 | colours | 1 x (`r,g,b,0`) for flat types, 3 or 4 for Gouraud types | all |

| Type | Tag | Size (bytes) | Maps to |
|---|---|---|---|
| `F3` | 0 | 16 | `POLY_F3` |
| `F4` | 1 | 20 | `POLY_F4` |
| `G3` | 2 | 24 | `POLY_G3` |
| `G4` | 3 | 32 | `POLY_G4` |
| `FT3` | 4 | 24 | `POLY_FT3` (one modulation colour) |
| `FT4` | 5 | 32 | `POLY_FT4` |
| `GT3` | 6 | 32 | `POLY_GT3` |
| `GT4` | 7 | 44 | `POLY_GT4` |

These are **file** record sizes. The GPU primitives a loader builds from them are different structures (for example `POLY_F3` is 20 bytes in RAM with its OT tag, `POLY_GT4` 52); never copy a record into a primitive.

Layout of the biggest one, `GT4` (44 bytes):

```
+0  type=7 flags size=44        +4  v0 v1 v2 v3 (4 x u16)      +12 normal u16, pad u16
+16 u0 v0 u1 v1 u2 v2 u3 v3     +24 tex u16, pad u16           +28 colour0..colour3 (4 x r,g,b,0)
```

Texture handling: UVs are texture-local (E.0). A loader looks up texture `tex` in the TPK store, adds `(u0, v0)` from E.3.4 to every UV, and
fills `tpage = TSB` and `clut = CBA` from where that texture's TIM was uploaded. Expect `TSB`/`CBA` to differ per texture and UVs to be non-zero-based
whenever two textures share a page. The colour of a textured primitive modulates the texel (128 = unchanged).

Real file (first 0x40 bytes of the generated `SHIP.SHP`: 46 vertices, 27 normals, 33 primitives, 3 textures, bbox -330..330 x -190..40 x -230..300):

```
00000000: 53 48 50 31 d4 05 00 00 53 48 49 50 00 00 00 00  SHP1....SHIP....
00000010: 00 00 00 00 00 00 00 00 2e 00 1b 00 21 00 03 00  ............!...
00000020: 40 00 00 00 b0 01 00 00 88 02 00 00 4c 03 00 00  @...........L...
00000030: b6 fe 42 ff 1a ff 4a 01 28 00 2c 01 00 00 00 00  ..B...J.(.,.....
```

and the first two primitives (a `GT3`, 32 bytes, then a `G3`, 24 bytes):

```
00000288: 06 00 20 00 00 00 01 00 02 00 00 00 00 3f 3f 3f  .. ..........???
00000298: 20 00 00 00 c8 c8 d2 00 96 96 aa 00 96 96 aa 00   ...............
000002a8: 02 00 18 00 00 00 02 00 03 00 01 00 78 82 96 00  ............x...
000002b8: 46 4b 5a 00 46 4b 5a 00                          FKZ.FKZ.
```

`06 00 20 00`: type 6 (`GT3`), flags 0, size 32; vertices 0, 1, 2; normal 0; UVs (0,63) (63,63) (32,0); texture 0; three colours `C8 C8 D2`, `96 96 AA`, `96 96 AA`.
`02 00 18 00`: type 2 (`G3`), size 24; vertices 0, 2, 3 (the nose and the next edge of the first ring); normal 1; then three colours.

**Pitfalls.** Records are variable-length: advance by `size`, never by `sizeof` a struct. Quads are Z order, so a GPU `POLY_*4` takes `v0 v1 v2 v3` as stored (do not
"fix" it to a loop order). Double-sided faces need either sign of the `NCLIP` result. A texture never straddles two texture pages: the generator keeps each one inside a page.
Modulation colours above 128 brighten the texel (up to 2x), saturating at full intensity per channel.

**Reference implementation:** `tools/assets/shpgen.py ship|pylon|arch|tower OUT.SHP --manifest m.json` writes; `formats.py` (`build_shp`, `parse_shp`) reads.
The ship mixes all eight types (every entry of the manifest's `prim_counts` is non-zero). **Manifest schema** (`SHIP.SHP.json`): `file, name, size, sha256, vertex_count, normal_count,
prim_count, prim_counts{F3..GT4}, texture_count, bbox[6], first_vertex, last_vertex, texture_set, textures[{index,name,bpp,x,y,clut_x,clut_y,uv_origin,cba,tsb_abr0}],
textured_prims[{index,type,tex,tsb,cba,uv_abs[[u,v]...]}]`. Chapter 32's probe compares parsed counts with `prim_counts`, and each textured primitive's tpage and clut
with `tsb`/`cba` (the generated textured primitives are opaque, so `abr` is 0; the semi-transparent canopy is untextured).

## E.9 `SCENE.BIN` (Chapter 33)

A list of landscape objects for a scene: which `.SHP` files to load and where to put copies of them. Little-endian, offsets from the file start.

```
0x00 +--------------------+
     | header (0x20)      |
0x20 +--------------------+  shapes_offset
     | shapes  16 B each  |
     +--------------------+  objects_offset
     | objects 24 B each  |
     +--------------------+
```

| Offset | Size | Field | Meaning |
|---|---|---|---|
| 0x00 | 4 | magic | `SCN1` |
| 0x04 | u32 | file_size | |
| 0x08 | u16 | shape_count | Distinct models. |
| 0x0A | u16 | object_count | Placed objects (the generated scene has 35). |
| 0x0C | u32 | shapes_offset | 0x20 |
| 0x10 | u32 | objects_offset | `0x20 + 16*shape_count` |
| 0x14 | u32 | cull_radius | Suggested draw distance in world units (20000). An object farther than `cull_radius + shape.radius` from the camera is skipped unless `ALWAYS_DRAW`. Compare **squared** distances: coordinate differences of tens of thousands square to hundreds of millions per axis, so the sum of three axes can overflow `s32` (Chapter 33's lesson). |
| 0x18 | u32[2] | reserved | 0 |

Shape entry (16 bytes):

| Offset | Size | Field | Meaning |
|---|---|---|---|
| +0x00 | char[12] | name | 8.3 file name of the `.SHP` in the disc's `DATA` directory (`PYLON.SHP`), NUL-padded. |
| +0x0C | u32 | radius | Bounding radius of the model about its origin, world units. |

Object entry (24 bytes):

| Offset | Size | Field | Meaning |
|---|---|---|---|
| +0x00 | u16 | shape | Index into the shape table. |
| +0x02 | u16 | flags | bit 0 `ALWAYS_DRAW`: never distance-culled (a renderer may still skip an object it cannot transform; Chapter 33's skips any more than 32000 units from the eye on an axis). Others 0. |
| +0x04 | s32[3] | position | World position `x, y, z` of the model origin (units as `.TRK`). Models stand on their origin: the body extends toward -Y. |
| +0x10 | s16[3] | rotation | `rx, ry, rz` in 4096ths of a turn. The generator only rotates about Y. |
| +0x16 | u16 | scale | 4.12 uniform scale; 4096 = 1.0. |

`ry` is defined as the heading of the model's +Z axis: `(sin ry, 0, cos ry)` (generator: `ry = atan2(hx, hz)`). This is exactly PSn00bSDK's
convention, so the rotation is `RotMatrix` with `vx = rx, vy = ry, vz = rz`, no sign change: its `Ry` block is `[[c,0,s],[0,1,0],[-s,0,c]]`
(Chapter 25: positive `vy` turns +Z toward +X), which maps `(0,0,1)` to `(sin ry, 0, cos ry)`. With `rx = rz = 0` the `Rx*Ry*Rz` order does not matter.

```
00000000: 53 43 4e 31 98 03 00 00 03 00 23 00 20 00 00 00  SCN1......#. ...
00000010: 50 00 00 00 20 4e 00 00 00 00 00 00 00 00 00 00  P... N..........
00000020: 50 59 4c 4f 4e 2e 53 48 50 00 00 00 91 01 00 00  PYLON.SHP.......
00000030: 41 52 43 48 2e 53 48 50 00 00 00 00 c2 03 00 00  ARCH.SHP........
00000040: 54 4f 57 45 52 2e 53 48 50 00 00 00 dc 05 00 00  TOWER.SHP.......
```

`53 43 4E 31` magic; `98 03 00 00` size 920; 3 shapes; `0x23` = 35 objects; shapes at 0x20, objects at 0x50; cull radius `0x4E20` = 20000;
then the shape table: `PYLON.SHP` radius `0x191` = 401, `ARCH.SHP` 962, `TOWER.SHP` 1500.

The generated scene (from `TRACK.TRK`): 1 arch over the start line (`ALWAYS_DRAW`), 28 pylons (a pair at every section `i` with `i mod 8 = 4`, 1000 units either side of the centre line), 6 towers on an outer ring.

**Pitfalls.** Objects are not sorted; do not assume a pylon follows another. Position fields are 32-bit while the GTE wants 16-bit camera-relative values
(subtract the camera first). The model radius is measured about the model origin, not the bounding-box centre.

**Reference implementation:** `tools/assets/scenegen.py TRACK.TRK OUT.BIN --manifest m.json`; `formats.py` (`build_scene`, `parse_scene`).
**Manifest** (`SCENE.BIN.json`): `file, size, sha256, object_count, shape_count, shapes[{name,radius,count}], cull_radius, pos_bbox[6], objects[{index,shape,flags,pos,rot,scale}]`.
Chapter 33's squared-distance cull count is recomputed from `objects`.

## E.10 `.TRK` track (Chapters 34 to 41)

A looping track as a ring of **sections**. The generator makes about 100 sections of 5 quads each (each section about 1000 units long, close to the 1200-unit road width, so a 64x64 tile is stretched at most about 2.5:1), between **rings** of 6 shared vertices.
It carries everything Chapters 34-40 need: geometry and texturing (34, 35, 36), a start position (37), per-section visibility lists (38),
and collision edges, face flags and section frames (40, 41). All little-endian, offsets from the file start. The generated `TRACK.TRK` has 672 vertices, 560 faces, 112 sections and is 35708 bytes.

```
0x00 +----------------------+
     | header (0x60)        |
0x60 +----------------------+  vertices_offset
     | vertices  12 B each  |
     +----------------------+  faces_offset
     | faces     24 B each  |
     +----------------------+  sections_offset
     | sections  64 B each  |
     +----------------------+  vis_offset
     | visibility u16 list  |  (padded with a u16 zero to a multiple of 4)
     +----------------------+
```

### E.10.1 Header (0x60 bytes)

| Offset | Size | Field | Meaning |
|---|---|---|---|
| 0x00 | 4 | magic | `TRK1` |
| 0x04 | u32 | file_size | |
| 0x08 | char[16] | name | `TRACK1`, `TRACK2` |
| 0x18 | u16 | section_count | `N`: 112 (track 1) or 104 (track 2). |
| 0x1A | u16 | vertex_count | |
| 0x1C | u16 | face_count | |
| 0x1E | u16 | vis_count | Entries in the visibility list. |
| 0x20 | u16 | start_section | Section where the ship starts and the start line is. |
| 0x22 | u16 | flags | bit 0 `LOOP`: the last section's `next` is section 0. |
| 0x24 | u16 | texture_count | Textures a face may reference (the track pack holds 8). |
| 0x26 | u16 | reserved | 0 |
| 0x28 | u32 | vertices_offset | 0x60 |
| 0x2C | u32 | faces_offset | `0x60 + 12*vertex_count` |
| 0x30 | u32 | sections_offset | `faces_offset + 24*face_count` |
| 0x34 | u32 | vis_offset | `sections_offset + 64*section_count` |
| 0x38 | u32 | total_length | Sum of all section `length`s: one lap along the centre line, world units. |
| 0x3C | u32 | reserved | 0 |
| 0x40 | s32[6] | bbox | `min x,y,z, max x,y,z` of all vertices. |
| 0x58 | 8 | reserved | 0 |

### E.10.2 Vertices

`s32 x, y, z` (12 bytes), world units, **+Y down**. The generated tracks span about 47000 x 26000 units, **more than the 16-bit range**
(`s16` is +-32767), while the GTE's vertex registers `VXY/VZ` take `s16`. The format keeps absolute `s32` coordinates on purpose (one shared vertex
table, no per-section origins); the renderer makes them small (Chapter 34):

1. Load only the camera's **rotation** into `RT` and set `TR = 0`.
2. Per vertex, in 32-bit C: `d = v - camera_pos` (each axis an `int32_t`).
3. If any `|d|` exceeds 32767, the vertex is farther than the GTE can take: skip the whole face (or clamp `d` and accept the
   distortion on far faces; Chapter 34 compares both). Otherwise store `d` as an `SVECTOR` and `gte_ldv0` it.

With the generated visibility lists (24 sections, about 24000 units ahead) every vertex the renderer draws passes step 3.
The same applies to `SCENE.BIN` positions and to the ship. Do not put the camera translation into `TR` and load the absolute
vertex: the vertex itself would already be truncated to 16 bits.
Vertices are shared: ring `r` (the start of section `r`) is vertices `6r .. 6r+5`, and section `N-1` ends at ring 0.

Ring cross-section (looking along the direction of travel; the generated tracks have half width 600, wall height 250, three 400-wide lanes):

```
   0 LT                                      5 RT
    |                                         |
    |  wall        road (3 lanes)       wall  |
    1 L ---- 2 CL ---- 3 CR ---- 4 R
         left      centre     right
```

| Ring vertex | Lateral (units, + = right) | Height (+ = up = -Y) |
|---|---|---|
| 0 LT | -600 | +250 |
| 1 L | -600 | 0 |
| 2 CL | -200 | 0 |
| 3 CR | +200 | 0 |
| 4 R | +600 | 0 |
| 5 RT | +600 | +250 |

Lateral and height are measured in the ring's frame, which **banks** (rolls about the direction of travel) by up to ~26 degrees in bends: in a right-hand turn the
right edge is lower (larger `y`). The ring layout is a property of the generated tracks; the format itself only promises what the section `edges` below say.

### E.10.3 Faces (24 bytes)

| Offset | Size | Field | Meaning |
|---|---|---|---|
| +0x00 | u16[4] | v | Vertex indices `v0..v3`, **Z order**, clockwise from the front (the side facing up for lanes, facing the road for walls). |
| +0x08 | u16 | flags | see below |
| +0x0A | u8 | tex | Texture index into the track `.TPK`, or `0xFF` = untextured. |
| +0x0B | u8 | pad | 0 |
| +0x0C | u8[8] | uv | `u0,v0,u1,v1,u2,v2,u3,v3`, texture-local (E.0; 0..63 for the 64x64 tiles). Stored for the **unflipped** face. |
| +0x14 | u8[4] | color | `r,g,b,0`: the face's untextured colour (the Chapter 34 flat render uses it; textured renders use neutral 128). |

Face flags:

| Bit | Name | Meaning |
|---|---|---|
| 0 | `FLOOR` | Drivable surface (the three lane quads). |
| 1 | `WALL` | A side wall, facing the road. |
| 2 | `BOOST` | Boost pad (centre lane of the sections in the manifest's `boost_sections`). Always with `FLOOR`. |
| 3 | `START` | Start/finish line (the three lane quads of the start section). With `FLOOR`. |
| 4 | `FLIP_H` | Render **mirrored in U**: use the UVs `(u1,u0,u3,u2)` for the vertices `(v0,v1,v2,v3)` (swap the two vertices of each U edge; V unchanged). The texture itself is not modified. |
| 5-15 | | 0 |

Per section the 5 faces are, in order: left wall (ring vertices 0,1), left lane (1,2), centre lane (2,3), right lane (3,4), right wall (4,5).
Each face joins a pair of ring vertices of the section's start ring with the same pair of its end ring; the generator reverses the quad's winding where needed
so it is front-facing from the road side, and the UVs follow the vertices through that reversal. Faces of a section are consecutive: `first_face .. first_face + face_count - 1`.

### E.10.4 Sections (64 bytes)

| Offset | Size | Field | Meaning |
|---|---|---|---|
| +0x00 | s32[3] | centre | Midpoint of the section's centre line: the average of the start and end ring centres, where a ring centre is the average of its `L` and `R` vertices. |
| +0x0C | u16 | half_width | Distance from the centre line to `L`/`R` (600). |
| +0x0E | u16 | length | Distance between the start and end ring centres, world units. |
| +0x10 | s16[3] + pad | forward | Unit vector (4.12) from the start ring centre toward the end ring centre. |
| +0x18 | s16[3] + pad | right | Unit vector (4.12), the normalised mean of the two rings' `L->R` directions made orthogonal to `forward`. `normalize(forward x (0,-1,0))` on level road; banked sections tilt it. |
| +0x20 | s16[3] + pad | up | Unit vector (4.12) out of the road surface (negative `y` on level road), orthogonal to both. Right-handed in the book's Y-down axes: `down = forward x right`. |
| +0x28 | u16 | first_face | |
| +0x2A | u16 | face_count | 5 |
| +0x2C | u16 | next | Section driven into when moving forward. |
| +0x2E | u16 | prev | |
| +0x30 | u16 | flags | bit 0 `JUNCTION` (the section has a second exit: reserved; the book's tracks never set it, follow `next` only), bit 1 `START`. |
| +0x32 | u16 | vis_first | Index of this section's first entry in the visibility list. |
| +0x34 | u16 | vis_count | |
| +0x36 | u16[4] | edges | Vertex indices of the **road edges**: `left_start, right_start, left_end, right_end` (ring vertices 1 and 4 of the start ring, then of the end ring). |
| +0x3E | u16 | pad | 0 |

Invariants (the selftest checks them): `next = (i+1) mod N`, `prev = (i-1) mod N`, `edges[2..3]` of section `i` equal `edges[0..1]` of section `i+1`, faces and sections tile the face
table without gaps, `|half_width - |R-L|/2| <= 1`.

**Collision recipe** (Chapter 40). Let `L0 = vertices[edges[0]]`, `R0 = vertices[edges[1]]`, `L1 = vertices[edges[2]]`, `R1 = vertices[edges[3]]`. In the XZ plane a position `p` is inside the road
when it is on the same side of the left edge `L0->L1` as `R0`, and on the same side of the right edge `R0->R1` as `L0` (sign of the 2D cross product `(L1-L0) x (p-L0)`). A cheaper approximation: `|dot(p - centre, right)| <= half_width`.
The edge direction `L1-L0` also gives the heading to steer toward after an impact; `up` gives the surface normal for auto-pitch.

### E.10.5 Visibility lists (Chapter 38)

`vis_count` `u16` section indices; section `i` owns the slice `vis[vis_first .. vis_first + vis_count - 1]`. For the generated tracks the slice for section `i` holds every
section `j` with `(j - i) mod N <= 24` (ahead, including `i` itself), **or** `(j - i) mod N >= N - 4` (the 4 behind), **or** whose centre is within `6 x` the average section length of
section `i`'s centre (spatially close, e.g. across a bend). Entries are in order of `(j - i) mod N`, so the first entry is always `i`. The parameters are in the manifest (`vis_rule`).
A renderer may use these lists instead of computing its own window; this is the book's optional `.VIS` table, carried inside the `.TRK`.

### E.10.6 Start position and units

The ship starts at `sections[start_section].centre` (on the road surface), heading `forward`, raised along `up` by the hover height (Chapter 37). World units are arbitrary: the road is 1200 wide,
a section about 1000 long, a lap about 112000, the ships 450 (`MODEL.BIN`) and 530 (`SHIP.SHP`) long. `TRACK2.TRK` (104 sections, a different outline) exists for Chapter 40's menu.

```
00000000: 54 52 4b 31 7c 8b 00 00 54 52 41 43 4b 31 00 00  TRK1|...TRACK1..
00000010: 00 00 00 00 00 00 00 00 70 00 a0 02 30 02 8e 0d  ........p...0...
00000020: 00 00 01 00 08 00 00 00 60 00 00 00 e0 1f 00 00  ........`.......
00000030: 60 54 00 00 60 70 00 00 82 b8 01 00 00 00 00 00  `T..`p..........
00000040: 70 a8 ff ff b8 f8 ff ff d7 cb ff ff 9a 5f 00 00  p............_..
00000050: 7d 06 00 00 a0 30 00 00 00 00 00 00 00 00 00 00  }....0..........
```

`54 52 4B 31` magic; size `0x8B7C` = 35708; name `TRACK1`; `70 00` = 112 sections, `A0 02` = 672 vertices, `30 02` = 560 faces, `8E 0D` = 3470 visibility entries;
start section 0; flags 1 (`LOOP`); 8 textures; offsets `0x60`, `0x1FE0`, `0x5460`, `0x7060`; total length `0x1B882` = 112770; then the bounding box
(`x` from -22416 to 24474, ...).

One face (the first, a left wall, offset `0x1FE0`): vertices 1, 0, 7, 6; flags `02` (`WALL`); texture 5; UVs `(0,63) (0,0) (63,63) (63,0)`; colour (40,60,120):

```
00001fe0: 01 00 00 00 07 00 06 00 02 00 05 00 00 3f 00 00  .............?..
00001ff0: 3f 3f 3f 00 28 3c 78 00                          ???.(<x.
```

and the first section (offset `0x5460`): centre `(23883, -639, 496)`, half width 600 (`58 02`), length `0x03ED` = 1005, then `forward`, `right`, `up`, faces 0..4, next 1, prev 111,
flags 2 (`START`), visibility entries 0..30, edges 1, 4, 7, 10:

```
00005460: 4b 5d 00 00 81 fd ff ff f0 01 00 00 58 02 ed 03  K]..........X...
00005470: 9a 01 f6 fd ca 0f 00 00 36 0e 07 f9 a9 fd 00 00  ........6.......
00005480: d3 f8 be f1 e3 fe 00 00 00 00 05 00 01 00 6f 00  ..............o.
00005490: 02 00 00 00 1f 00 01 00 04 00 07 00 0a 00 00 00  ................
```

**Pitfalls.** Vertices are `s32`: reading them as `s16` makes every coordinate garbage. Camera-relative subtraction first, GTE load second. Faces are Z-ordered quads that already
include the winding fix: render them as stored. `FLIP_H` changes the UVs, not the vertices. Ring vertices are shared between neighbouring sections, so edges
and walls meet exactly; subdivision (Ch 36) must split shared edges identically or T-junction cracks appear. `up` has negative `y`: do not add it to a height as if `+y` were up.

**Reference implementation:** `tools/assets/trkgen.py OUT.TRK [--track 1|2] [--sections N] --manifest m.json`; `formats.py` (`build_trk`, `parse_trk`).
**Manifest** (`TRACK.TRK.json`): `file, name, size, sha256, section_count, vertex_count, face_count, vis_entries, texture_count, start_section, total_length, bbox[6],
face_counts{floor,wall,boost,start,flip_h}, boost_sections[], start_faces[], centre_line[[x,y,z] per section], section_lengths[], half_width, edges[[L0,R0,L1,R1 coordinates] per section],
vis[[...] per section], vis_rule{ahead,behind,near_factor}, max_slope, max_bank_deg, exceeds_int16`. Chapter 34 compares counts, 38 the nearest section against `centre_line`, 40 the collision against `edges`.

## E.11 Generating and checking everything

```
source tools/env.sh
$PS1BOOK_PYTHON tools/assets/mkassets.py build/assets      # every file above, plus manifest/*.json
$PS1BOOK_PYTHON tools/assets/selftest.py                   # proves generators == this appendix (also run by tools/ci.sh)
```

| Tool | Purpose |
|---|---|
| `texgen.py` | original PNG textures (crate, panel, Hoverline logo, hull, track tiles, props) |
| `img2tim.py`, `tim.py` | PNG to TIM; `--check` validates |
| `lzss.py`, `tpkpack_ref.py` | reference LZSS and `.TPK` packer/unpacker/verifier |
| `shpgen.py` | ship, scenery and `MODEL.BIN` generator |
| `trkgen.py`, `scenegen.py` | track and scene generators |
| `sfxgen.py`, `wav2vag.py`, `vag2wav.py`, `vag.py` | sound effects, VAG encoder/decoder |
| `formats.py` | reference readers/writers for the book's formats |
| `mkassets.py` | the whole pipeline in one call |

[`tools/assets/README.md`](../tools/assets/README.md) lists every command line and how chapter `verify` scripts use the manifests.
