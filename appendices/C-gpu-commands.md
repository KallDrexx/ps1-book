# Appendix C: GPU Command Reference

Every GP0 drawing/VRAM command and GP1 display command the book uses, with word-by-word packet layouts, plus the commands it does not use (marked *not used*). Sources: Chapters 13 to 17, 20, 30 and 34, and psx-spx ("GPU Rendering Commands", "GPU Display Control Commands", "GPU Rendering Attributes", "GPU Status Register"). Facts the book verified in PCSX-Redux say so; commands and bits it never sent are marked *(not checked in the book)*. The register addresses and GPUSTAT are in Appendix B.7.

| Section | Contents |
|---|---|
| C.1 | Writing to the GPU: GP0 / GP1, color and vertex words, waiting |
| C.2 | GP0 command map and packet sizes |
| C.3 | Polygons |
| C.4 | Lines and polylines |
| C.5 | Rectangles |
| C.6 | Fill and VRAM copies |
| C.7 | GP0 state commands `E1h`-`E6h` |
| C.8 | Textures: pages, CLUTs, modulation, transparency |
| C.9 | Semi-transparency |
| C.10 | GP1 display commands, display mode, NTSC and PAL |
| C.11 | Limits and clipping summary |
| C.12 | SDK structure names |

## C.1 Writing to the GPU

| Port | Address | Write | Read |
|---|---|---|---|
| GP0 | `0x1F801810` | drawing commands, parameters and VRAM data | GPUREAD (readback) |
| GP1 | `0x1F801814` | display control | GPUSTAT |

Both ports take a **word**: use `sw`. A GP0 word is the first word of a packet (command byte on top, usually a color below) followed by parameter words. A GP1 word is `cc pppppp`: command in bits 31-24, parameter in the low 24 bits.

**Waiting (Ch 13, 15, 16).** Poll GPUSTAT bit 26 until it is 1 **once before the first word of a packet**, and never between the words of a packet or inside a data phase: bit 26 is **clear while the GPU wants parameters or data** (or is busy), so such a wait never ends (verified in PCSX-Redux). The command FIFO holds 16 words. Redux reports ready almost always, so a missing wait appears on hardware, not there. See Appendix B.7.

**Color in a command word** is `BBGGRR` in the low 24 bits: blue in bits 16-23, red in bits 0-7, **the reverse of the usual `0xRRGGBB`**. The first word of a packet is `cc BBGGRR` (command on top). Extra color words in Gouraud packets have `00` on top. Each channel is 8 bits; VRAM keeps only the top 5, so a color read back differs slightly (Ch 1).

**Vertex word** (Ch 14): `word = (y << 16) | (x & 0xFFFF)`; each coordinate is a **signed 11-bit** number, -1024..1023: the GPU uses the low 11 bits and sign-extends. Mask a negative `x` to 16 bits before OR-ing it with `y << 16`, or its upper bits destroy `y`. The **drawing offset** (`E5h`) is added to every vertex of a drawing command afterwards.

**VRAM** is 1024 x 512 units of 16 bits (1 MB), row-major; unit `(x, y)` is at byte offset `(y << 11) + (x << 1)`. Pixel format (BGR555, little-endian): bit 15 mask bit (M), bits 14-10 blue, 9-5 green, 4-0 red. In 15-bit mode a unit is a pixel; in 24-bit mode it is not (C.6.4). The CPU cannot address VRAM; GP0/GPUREAD are the only way in or out.

## C.2 GP0 command map

| Command byte | Class | Words | Section |
|---|---|---|---|
| `00h` | NOP | 1 | |
| `01h` | clear texture cache | 1 | *(not used)* |
| `02h` | **fill rectangle** in VRAM | 3 | C.6.1 |
| `1Fh` | request GPU interrupt (IRQ1) | 1 | *(not used)* |
| `20h-3Fh` | **polygons** (`001` in bits 7-5) | 4 to 12 | C.3 |
| `40h-5Fh` | **lines** and polylines (`010`) | 3 to open-ended | C.4 |
| `60h-7Fh` | **rectangles** (`011`) | 2 to 4 | C.5 |
| `80h-9Fh` | copy rectangle VRAM to VRAM | 4 | C.6.2 |
| `A0h-BFh` | copy rectangle **CPU to VRAM** | 3 + data | C.6.3 |
| `C0h-DFh` | copy rectangle **VRAM to CPU** | 3, then GPUREAD | C.6.5 |
| `E1h` | draw mode (texture page, blending, dither) | 1 | C.7 |
| `E2h` | texture window | 1 | C.7 |
| `E3h` / `E4h` | drawing area top-left / bottom-right | 1 | C.7 |
| `E5h` | drawing offset | 1 | C.7 |
| `E6h` | mask-bit setting | 1 | C.7 |

The top byte of word 1 selects the command. The fill, polygon, line and rectangle commands take a color in the low 24 bits; the copy commands (`80h`-`DFh`) ignore them.

## C.3 Polygons: `20h`-`3Fh`

### C.3.1 The command byte

`001 g q t s r`: bits 7-5 = `001`.

| Bit | Value | Meaning when set |
|---|---|---|
| 4 | `+10h` | **Gouraud**: a color per vertex |
| 3 | `+08h` | **quad** (4 vertices) instead of triangle |
| 2 | `+04h` | **textured** |
| 1 | `+02h` | **semi-transparent** (blend mode from `E1h` bits 5-6, C.9) |
| 0 | `+01h` | **raw texture**: textured polygons skip the color modulation (C.8.4) |

| Command | Polygon | Words |
|---|---|---|
| `20h` | flat triangle | 4 |
| `28h` | flat quad | 5 |
| `30h` | Gouraud triangle | 6 |
| `38h` | Gouraud quad | 8 |
| `24h` | flat textured triangle | 7 |
| `2Ch` | flat textured quad | 9 |
| `34h` | Gouraud textured triangle | 9 |
| `3Ch` | Gouraud textured quad | 12 |

Add `02h` for semi-transparent (`22h 2Ah 32h 3Ah 26h 2Eh 36h 3Eh`). For textured polygons, `+01h` selects raw texture (`2Dh` skips modulation; the book uses `2Ch` with color 128).

### C.3.2 Untextured packet layouts

```
Flat triangle 20h    Flat quad 28h       Gouraud triangle 30h    Gouraud quad 38h
 1  20 BB GG RR       1  28 BB GG RR      1  30 BB GG RR  (c1)    1  38 BB GG RR  (c1)
 2  y1 | x1           2  y1 | x1          2  y1 | x1             2  y1 | x1
 3  y2 | x2           3  y2 | x2          3  00 BB GG RR  (c2)    3  00 BB GG RR  (c2)
 4  y3 | x3           4  y3 | x3          4  y2 | x2             4  y2 | x2
                      5  y4 | x4          5  00 BB GG RR  (c3)    5  00 BB GG RR  (c3)
                                          6  y3 | x3             6  y3 | x3
                                                                  7  00 BB GG RR  (c4)
                                                                  8  y4 | x4
```

### C.3.3 Textured packet layouts

Each vertex word is followed by a **UV word**. Word 3's upper half carries the **CLUT** word, word 5's upper half the **texture-page** word (C.8). In a UV word: `u` in bits 0-7, `v` in bits 8-15.

```
Flat textured triangle 24h        Flat textured quad 2Ch
 1  24 BB GG RR  (modulation)      1  2C BB GG RR
 2  y1 | x1                        2  y1 | x1
 3  clut<<16 | v1<<8 | u1          3  clut<<16 | v1<<8 | u1
 4  y2 | x2                        4  y2 | x2
 5  tpage<<16 | v2<<8 | u2         5  tpage<<16 | v2<<8 | u2
 6  y3 | x3                        6  y3 | x3
 7  v3<<8 | u3                     7  v3<<8 | u3
                                   8  y4 | x4
                                   9  v4<<8 | u4

Gouraud textured triangle 34h     Gouraud textured quad 3Ch
 1  34 BB GG RR (c1)               1  3C BB GG RR (c1)
 2  y1 | x1                        2  y1 | x1
 3  clut<<16 | v1<<8 | u1          3  clut<<16 | v1<<8 | u1
 4  00 BB GG RR (c2)               4  00 BB GG RR (c2)
 5  y2 | x2                        5  y2 | x2
 6  tpage<<16 | v2<<8 | u2         6  tpage<<16 | v2<<8 | u2
 7  00 BB GG RR (c3)               7  00 BB GG RR (c3)
 8  y3 | x3                        8  y3 | x3
 9  v3<<8 | u3                     9  v3<<8 | u3
                                  10  00 BB GG RR (c4)
                                  11  y4 | x4
                                  12  v4<<8 | u4
```

`POLY_FT4` (`2Ch`) is 9 words after the SDK tag (`setPolyFT4` sets code `0x2C`, length 9); `POLY_GT4` (`3Ch`) is 12.

### C.3.4 Quads, winding and shading

| Topic | Rule (Ch 14) |
|---|---|
| **Z order** | vertices are sent `v1 v2 v3 v4` and the quad is the triangles `v1 v2 v3` and `v2 v3 v4`, sharing the diagonal `v2-v3`. Sending the outline order (`v1 v2 v4 v3`) makes a bow tie. (Appendix E numbers the same vertices `v0..v3`: triangles `(v0,v1,v2)` and `(v1,v3,v2)`.) |
| Winding | does **not** matter: the GPU draws clockwise and counterclockwise triangles alike (verified in PCSX-Redux). There is no hardware back-face culling; engines cull in software with `NCLIP` (Ch 25). |
| Gouraud | each pixel is a barycentric mix of the three vertex colors, linear along every line. In a quad each of the two triangles interpolates **its own three** colors, so a Gouraud quad can show a faint seam along the diagonal; the four corner colors are exact. |
| Dither | `E1h` bit 9 adds an ordered dither pattern before colors are cut to 5 bits; the book keeps it **off** (`E1h = 0x400`). With dither on, Gouraud pixels shift by a few levels. |
| Affine texturing | UVs are interpolated linearly in screen space, with no perspective correction: large textured polygons warp (Ch 30, 36) |

## C.4 Lines and polylines: `40h`-`5Fh`

`010 g p . s .`: bit 4 Gouraud, bit 3 polyline, bit 1 semi-transparent. The book sends only the flat, opaque polyline `48h` (Ch 34).

| Command | Meaning | Packet |
|---|---|---|
| `40h` | flat line | `cc BBGGRR`, `y1 x1`, `y2 x2` (3 words) |
| `42h` | flat line, semi-transparent | same |
| `48h` | flat polyline | `48 BB GG RR`, then one vertex word per point, then the terminator |
| `4Ah` | flat polyline, semi-transparent | same |
| `50h` | Gouraud line | `50 BBGGRR (c1)`, `v1`, `00 BBGGRR (c2)`, `v2` (4 words) |
| `58h` | Gouraud polyline | `c1`, `v1`, `c2`, `v2`, `c3`, `v3` ..., then the terminator |

**Terminator.** `0x55555555` (the value the book writes). psx-spx states the test as `(word & 0xF000F000) == 0x50005000`; the book only sends `0x55555555`. A closed outline of a quad is five points (back to the first) plus the terminator, e.g. the Ch 34 packet: `48 BBGGRR`, `v0`, `v1`, `v3`, `v2`, `v0`, `0x55555555` (the tag's length is 7 words). Lines are 1 pixel wide, are clipped to the drawing area and shifted by the drawing offset; the polygon size limit (C.11) applies to the distance between consecutive points *(limit not checked for lines in the book)*.

## C.5 Rectangles (sprites): `60h`-`7Fh`

`011 ss t . s r` : bits 4-3 = size, bit 2 textured, bit 1 semi-transparent, bit 0 raw texture.

| Size bits | Size | Untextured | Textured |
|---|---|---|---|
| 0 | variable | `60h` | `64h` |
| 1 | 1 x 1 | `68h` | `6Ch` |
| 2 | 8 x 8 | `70h` | `74h` |
| 3 | 16 x 16 | `78h` | `7Ch` |

Add `02h` for semi-transparent, `01h` for raw texture (textured only).

```
Monochrome rectangle 60h          Textured rectangle 64h
 1  60 BB GG RR                    1  64 BB GG RR        (modulation color)
 2  y | x    (top-left)            2  y | x
 3  h<<16 | w                      3  clut<<16 | v<<8 | u
                                   4  h<<16 | w
```

The fixed-size forms (`68h 70h 78h`, `6Ch 74h 7Ch`) omit the size word. Rectangles use the **texture page from `E1h`** (a textured rectangle has no tpage word of its own) and the CLUT in word 3.

A rectangle is an ordinary drawing command: **pixel-exact, clipped to the drawing area, shifted by the drawing offset**; one completely outside the area draws nothing. Position is signed 11-bit per axis (-1024..1023). Maximum variable size 1023 x 511 *(psx-spx; not checked in the book)*. `E1h` bits 12-13 flip a textured rectangle in X/Y on GPUs that support it *(not checked in the book)*. The SDK names: `TILE`/`TILE_1/8/16` (`60h 68h 70h 78h`), `SPRT`/`SPRT_8/16` (`64h 74h 7Ch`).

## C.6 Fill and copy commands (VRAM operations)

### C.6.1 Fill rectangle, `02h`

| Word | Meaning |
|---|---|
| 1 | `0x02BBGGRR` |
| 2 | `y << 16 \| x` : top-left in **VRAM** coordinates |
| 3 | `h << 16 \| w` : size |

This is a VRAM operation, not a drawing operation:

| Property | Value (Ch 13, 17) |
|---|---|
| Granularity | blocks of 16 pixels horizontally: **`x` is rounded down to a multiple of 16 and `w` is rounded up to a multiple of 16**. `x = 20, w = 20` paints columns 16 to 47. Heights are exact. psx-spx: `x & 0x3F0`, `w = ((w & 0x3FF) + 0xF) & ~0xF`. |
| Clipping | **ignores the drawing area** (`E3h/E4h`; the verifier tests it) |
| Drawing offset | **ignores `E5h`** (PCSX-Redux shows it): give absolute VRAM coordinates, e.g. `(0, 240)` for the second buffer |
| Color | 8 bits per channel in the packet; the fill keeps the top 5 and drops the low 3 (Ch 18) |
| Use | fast clear of a large area; a full 320 x 240 clear is exact. It cannot draw 40-pixel bars: use `60h` |

### C.6.2 VRAM to VRAM, `80h`

Four words: `0x80000000`, source `y<<16 | x`, destination `y<<16 | x`, size `h<<16 | w` *(not used in the book)*.

### C.6.3 CPU to VRAM, `A0h` (Ch 16)

```
 word 1   0xA0000000                  command A0h in bits 31-24 (the low 24 bits are ignored)
 word 2   y(31..16) | x(15..0)        destination: top-left unit in VRAM
 word 3   h(31..16) | w(15..0)        size in units
 word 4.. pixel data, two units per word: low half = LEFT unit, high half = right
```

Data is the rectangle row by row, no gaps between rows. The GPU needs `ceil(w*h / 2)` words; if `w*h` is odd, the last word carries one unit and one pad half the GPU ignores (the source buffer needs room for the whole last word).

| Rule | Detail |
|---|---|
| Too few words | the GPU keeps waiting for data: **your next packet becomes pixels** |
| Too many words | the extras are read as commands |
| Coordinates | `x` is masked to 10 bits, `y` to 9 (`x = 1030` lands at 6, PCSX-Redux agrees); a size of 0 means the maximum (1024 / 512). Always send `w, h >= 1`. |
| Edge | stay inside VRAM: `x + w <= 1024`, `y + h <= 512`. psx-spx says a rectangle past an edge wraps; the PCSX-Redux build used did something else for the right edge. **Not portable; the book never depends on it.** |
| Clipping | **not** clipped to the drawing area and ignores the drawing offset; it obeys the mask-bit setting (`E6h`, off after reset) |
| Waiting | wait for bit 26 once before word 1; send header and data back to back (C.1). Small CPU uploads are common; large ones go by DMA channel 2 (Appendix B.5), paced by the GPU's DMA request |
| Alignment | the source pointer is read with `lw`: word-aligned |

### C.6.4 24-bit color

GP1 `08h` bit 4 selects 24 bits per displayed pixel. VRAM is then read as **3 bytes per pixel in the order R, G, B** (low address first). psx-spx gives red in bits 0-7, green 8-15, blue 16-23 of the 24-bit value; little-endian that puts red at the lowest address. Verified in PCSX-Redux (Ch 16): random R, G, B bytes uploaded and compared with a 24-bit screenshot pixel by pixel. The 15-bit format has the same order: red is the *low* 5 bits of a unit. Both are the reverse of the usual `0xRRGGBB`.

```
 bytes:      R0 G0 B0 | R1 G1 B1 | R2 G2 B2 | R3 G3 B3
 as units:   unit0 = G0:R0   unit1 = R1:B0   unit2 = B1:G1   unit3 = G2:R2 ...      (3 units hold 2 pixels)
```

A pixel is 1.5 units wide: line width in units `= px * 3 / 2 = px + (px >> 1)`; a 320-pixel line takes **480 units** and the 320 x 240 picture is a 480 x 240 rectangle. The transfer knows nothing about color depth: you send an `A0h` rectangle with `w` in **units**. Keep pixel x offsets and widths even. Only the **display** reads this way; drawing commands still work in 15-bit.

### C.6.5 VRAM to CPU, `C0h`

Same three words as `A0h` (source rectangle); then read the pixels from GPUREAD (`0x1F801810`) while GPUSTAT bit 27 is set *(not checked in the book)*.

## C.7 GP0 state commands

### `E1h` Draw mode (texture page, blending, dither)

| Bits | Meaning |
|---|---|
| 0-3 | texture page X base, in units of 64 (`x = N * 64`, N = 0..15) |
| 4 | texture page Y base: 0 = line 0, 1 = line 256 |
| 5-6 | semi-transparency mode (C.9) |
| 7-8 | texture color depth: 0 = 4 bpp, 1 = 8 bpp, 2 = 15 bpp |
| 9 | dither 24 to 15 bit (1 = on) |
| 10 | **drawing to the display area allowed** (the book always sets it: `0x400`) |
| 11 | texture disable (needs GP1 `09h`) *(not used)* |
| 12-13 | textured-rectangle X / Y flip *(not used)* |

The mode stays until the next `E1h` and applies to later semi-transparent commands. Opaque polygon commands ignore the blend mode. Keep bit 10 set whenever you write `E1h`. For textured polygons the texture-page word in the packet replaces bits 0-8; for rectangles the last `E1h` is used.

### `E2h` Texture window *(not used in the book)*

Bits 0-4 mask X, 5-9 mask Y (in 8-pixel units), 10-14 offset X, 15-19 offset Y. The texel coordinate becomes `(coord & ~(mask*8)) | ((offset & mask) * 8)`, repeating a small texture inside the page.

### `E3h` / `E4h` Drawing area

| Command | Word | Meaning |
|---|---|---|
| `E3h` | `0xE3000000 \| y<<10 \| x` | top-left corner, **inclusive** |
| `E4h` | `0xE4000000 \| y<<10 \| x` | bottom-right corner, **inclusive** (319, 239 for a 320 x 240 area) |

Drawing commands may change only this rectangle; polygons partly outside are clipped. After `GP1(00h)` the area is the single pixel (0,0) until you set it. The inclusive corner is the classic 320/240 off-by-one.

### `E5h` Drawing offset

`0xE5000000 | ((y & 0x7FF) << 11) | (x & 0x7FF)`: a signed 11-bit offset added to every vertex of a drawing command. With offset (160, 120), vertex (-90, -100) lands at (70, 20). It is not applied to fills or CPU/VRAM copies.

### `E6h` Mask-bit setting

Bit 0: set the mask bit (VRAM bit 15) on every pixel drawn. Bit 1: do not draw over pixels whose mask bit is already set. Both are 0 after reset *(not used in the book)*.

`GP1(00h)` zeroes the state commands `E1h-E6h`.

## C.8 Textures

### C.8.1 Pages and units (Ch 30)

A **texture page** is a 256 x 256 *texel* window into VRAM. It starts on a multiple of 64 units in x and on line 0 or 256. Texels per VRAM unit depend on the depth:

| Depth | Texels per 16-bit unit | A page is wide (units x lines) | Texel `u` for a unit offset |
|---|---|---|---|
| 4 bpp | 4 (a 4-bit palette index) | 64 x 256 | `4 x offset` |
| 8 bpp | 2 (an 8-bit index) | 128 x 256 | `2 x offset` |
| 15/16 bpp | 1 (a color) | 256 x 256 | `offset` |

UVs are **8-bit texel coordinates inside the page**, `0..255`, `(0,0)` its top-left. So a texture is at most 256 x 256, must not cross the edge of its page, and a polygon can use only one page. The crate (8 bpp, image at x = 704) is in page column 11 at `u0 = 0`; the panel (4 bpp, x = 736) is in column 11 at `u0 = (736 mod 64) x 4 = 128`. A texture is placed by its **image block** (the page word comes from the image rectangle, the CLUT word from the CLUT rectangle).

### C.8.2 The tpage word and the CLUT word

```
tpage word (16 bits, upper half of the SECOND UV word)
 15      9  8 7  6 5  4   3      0
+---------+-----+-----+---+-------+
|  (0)    | tp  | abr | Y | X/64  |      X/64: page column 0..15
+---------+-----+-----+---+-------+      Y: 0 = lines 0..255, 1 = lines 256..511
                                         abr: semi-transparency mode 0..3
                                         tp: 0 = 4 bpp, 1 = 8 bpp, 2 = 16 bpp

CLUT word (16 bits, upper half of the FIRST UV word)
 15 14                  6 5          0
+--+---------------------+-----------+
|0 |         Y           |   X / 16  |   Y: line 0..511     X/16: x, a multiple of 16
+--+---------------------+-----------+
```

Worked example (Ch 30): crate, 8 bpp, image at (704, 0), CLUT at (0, 496): tpage = `704/64 | (1 << 7)` = `0x8B`; CLUT = `496 << 6` = `0x7C00`. SDK macros: `getTPage(tp, abr, x, y)`, `getClut(x, y)`. Bits above 8 of the tpage word stay 0. A CLUT row is 16 colors (4 bpp) or 256 (8 bpp) of 15-bit colors stored in VRAM like any image; its `x` is a multiple of 16.

### C.8.3 Transparency and the mask bit

| Rule | Detail |
|---|---|
| A texel of color `0x0000` | **transparent** (not drawn). The color value counts, not the index: the CLUT entry the index selects, or the texel itself at 16 bpp |
| Opaque black | store `0x0421` (the book's `img2tim.py` does); `0x8000` (STP set) is also opaque black on an opaque polygon |
| Bit 15 of a texel (STP) | matters only for semi-transparent polygons: STP = 1 texels are blended, STP = 0 texels stay opaque |

### C.8.4 Modulation

The polygon color `(r, g, b)` multiplies the texel: `out = texel x color / 128` per channel, so **128 (`0x80`) is neutral**, 255 brightens up to almost 2x and 0 gives black. Command bit 0 (raw texture, e.g. `2Dh`) skips it. The book uses `2Ch` with color 128, which is the texture as stored.

## C.9 Semi-transparency

Two things are needed: the **command bit 1** (`22h 2Ah 32h 3Ah`, textured `+02h`), and the mode in `E1h` bits 5-6 (or the tpage word's `abr` for textured polygons). *B* is the pixel already in VRAM, *F* the polygon's color (Ch 14):

| `E1h` bits 5-6 | Result | Meaning |
|---|---|---|
| 0 | `B/2 + F/2` | average, 50% blend |
| 1 | `B + F` | additive (glows), clamped at 255 |
| 2 | `B - F` | subtractive (shadows), clamped at 0 |
| 3 | `B + F/4` | faint additive |

The mode is state: it persists until the next `E1h` and applies to every later command that has the semi-transparency bit.

## C.10 GP1 display commands

| Command | Word | Meaning |
|---|---|---|
| `00h` | `0x00000000` | **reset** the GPU: display off, command FIFO cleared, `E1h-E6h` zeroed. Does **not** clear VRAM. The right first word: the BIOS or an earlier program may have left anything behind. |
| `01h` | `0x01000000` | reset the command buffer *(not used)* |
| `02h` | `0x02000000` | acknowledge the GPU interrupt *(not used)* |
| `03h` | `0x03000000 \| off` | display enable; bit 0: **0 = on**, 1 = off |
| `04h` | `0x04000000 \| dir` | DMA direction (0 off, 1 FIFO, 2 CPU to GP0, 3 GPUREAD to CPU); echoed in GPUSTAT 29-30 *(set by the SDK)* |
| `05h` | `0x05000000 \| y<<10 \| x` | **display start**: top-left of the display area in VRAM (x 0-9, y 10-18) |
| `06h` | `0x06000000 \| x2<<12 \| x1` | horizontal display range on the TV, in GPU clocks (x1 0-11, x2 12-23) |
| `07h` | `0x07000000 \| y2<<10 \| y1` | vertical display range, in scanlines (y1 0-9, y2 10-19) |
| `08h` | `0x08000000 \| mode` | **display mode** (below) |
| `09h` | `0x09000000 \| allow` | allow texture-disable *(not used)* |
| `10h-1Fh` | `0x10000000 \| n` | request GPU info into GPUREAD (`n` = 2 texture window, 3 drawing area top-left, 4 bottom-right, 5 drawing offset, 7 GPU type) *(not used)* |

### GP1(08h) display mode

| Bits | Meaning | Book's value |
|---|---|---|
| 0-1 | horizontal resolution: 0 = 256, 1 = 320, 2 = 512, 3 = 640 | 1 |
| 2 | vertical resolution: 0 = 240, 1 = 480 (480 needs interlace) | 0 |
| 3 | video mode: 0 = **NTSC**, 1 = **PAL** | 0 |
| 4 | color depth: 0 = 15-bit, 1 = 24-bit | 0 (1 in Ch 16 part 2) |
| 5 | interlace: 0 = off, 1 = on | 0 |
| 6 | horizontal resolution 368 (overrides bits 0-1) | 0 |
| 7 | reverse flag | 0 |

| Mode word | Meaning |
|---|---|
| `0x08000001` | 320 x 240, NTSC, 15-bit, progressive (the book's default) |
| `0x08000011` | 320 x 240, NTSC, **24-bit** (Ch 16) |
| `0x08000009` | 320 x 240, **PAL**, 15-bit (`0x08000008` is the PAL bit alone, which a PAL BIOS leaves set; Ch 37, 42) |

GPUSTAT bits 16-22 echo the mode word and bit 23 echoes GP1(03h). In the SDK, `SetVideoMode(MODE_PAL)` writes GP1(08h) bit 3, and `ResetGraph(0)` reads the GPU's video-mode bit when it first starts (Ch 42).

### Display start, ranges

* `05h` sets where in VRAM the display **starts**. The **display ranges** (`06h`/`07h`) set where on the TV it lands *and* how much is shown: `y2 - y1` lines and `(x2 - x1) / clocks-per-pixel` pixels (psx-spx rounds the pixel count to a multiple of 4). The horizontal resolution in `08h` sets only the pixel width: 10, 8, 7, 5 or 4 GPU clocks for 256, 320, 368, 512 or 640.
* A shorter range shows less of the picture; a longer one shows **more of VRAM** (whatever lies right of or below your buffer), not a black border (Ch 13, from psx-spx).
* 320 pixels at 8 clocks need `x2 - x1 = 2560`; the usual values are `0x260` to `0xC60`. A 240-line picture needs `y2 - y1 = 240`.
* Double buffering (Ch 17): two 320 x 240 buffers at `(0,0)` and `(0,240)`; draw into one while `05h` shows the other; **one `05h` write per frame**, after waiting for the GPU (GPUSTAT bit 26); a fill into a buffer needs absolute coordinates because it ignores the offset.

### NTSC and PAL (Ch 13)

| | NTSC | PAL |
|---|---|---|
| Refresh | about 60 Hz (59.83) | about 50 Hz (49.76 on hardware) |
| Scanlines per frame (non-interlaced) | 263 | 314 |
| GPU clocks per scanline | 3413 | 3406 |
| Visible lines | up to 240 (about 224 on most TVs) | up to 288 |
| Vertical center line (psx-spx) | `0x88` = 136 | `0xA3` = 163 |
| 240-line vertical range | 16 to 256 | about 43 to 283 |
| CPU cycles per vertical blank | 566,120 (Redux, measured) | about 675,900 (Redux); about 680,600 on hardware |

Packets and VRAM are identical; only timing, the video-mode bit and the vertical range change. The PAL range is not tested in the book. The cycle counts are reconciled in Appendix B.11.

## C.11 Limits and clipping summary

| Rule | Effect | Source |
|---|---|---|
| Vertex coordinates | signed 11 bits, -1024..1023, before the drawing offset is added | Ch 14 |
| **Polygon size limit** | the distance between any two vertices may be at most **1023 horizontally and 511 vertically**; a larger polygon is **dropped entirely**, not clipped (PCSX-Redux: 1200 wide and 520 tall not drawn, 1000 wide drawn). Engines split big polygons; screen coordinates saturate near +/-1024 (Ch 36) | Ch 14, 36 |
| Drawing area | pixels outside `E3h`/`E4h` are never touched | Ch 13, 14 |
| Fill `02h` | ignores area and offset; 16-pixel horizontal granularity | Ch 13 |
| `A0h` | ignores area and offset; `x`/`y` masked to 10/9 bits; never cross the VRAM edge | Ch 16 |
| FIFO | 16 words; wait for bit 26 once per packet | Ch 15 |
| Winding | irrelevant to the GPU | Ch 14 |
| Texture | 8-bit UVs, one page per polygon, affine interpolation | Ch 30 |

## C.12 SDK structure names

PSn00bSDK structs mirror the PsyQ names: each begins with one extra `tag` word (24-bit next pointer, 8-bit length) that the DMA reads and the GPU never sees (Appendix B.5, Ch 20). Length is the number of words after the tag.

| Struct | Code | Length | Packet |
|---|---|---|---|
| `POLY_F3` | `20h` | 4 | flat triangle |
| `POLY_F4` | `28h` | 5 | flat quad (Ch 20: length 5, code `28h`) |
| `POLY_G3` / `POLY_G4` | `30h` / `38h` | 6 / 8 | Gouraud triangle / quad |
| `POLY_FT3` / `POLY_FT4` | `24h` / `2Ch` | 7 / 9 | flat textured triangle / quad |
| `POLY_GT3` / `POLY_GT4` | `34h` / `3Ch` | 9 / 12 | Gouraud textured triangle / quad |
| `TILE` | `60h` | 3 | variable monochrome rectangle |
| `SPRT` | `64h` | 4 | variable textured rectangle |

Helpers: `setPolyF4(p)`, `setRGB0(p,r,g,b)` (R, G, B arguments in the natural order; the macro puts them in `BBGGRR`), `setXY4`, `setUV4`, `addPrim(ot_slot, p)`. `DrawPrim` waits like `DrawSync(0)` and then DMAs one packet; `DrawOTag` returns immediately (Appendix B.5). A `DRAWENV` can clear its area (`isbg = 1`), which the SDK implements with the fill command (Ch 18).
