# Chapter 30: Textured Polygons

## 1. Concept

A **textured polygon** takes its color from a picture in VRAM instead of from the vertices. The picture (a **texture**) is a rectangle of **texels** (texture pixels). A TIM file carries it, a **texture page** word tells the GPU where to look, a **CLUT** word tells it which palette to use, and each corner of the polygon carries a **UV** coordinate: the texel that corner shows.

## 2. Why it matters

Every PS1 game dresses its models in textures, and almost every texture bug (mirrored text, garbage in place of a crate, a wrong palette) is a mistake in one of four things: where the texture went in VRAM, the page word, the CLUT word or the UVs. This chapter makes you compute them yourself from the TIM header, so you know where each comes from.

## 3. Learning objectives

After this chapter you can:

- draw the VRAM map and say where framebuffers, texture pages and CLUTs may go;
- compute the **tpage** word and **CLUT** word of a texture and the UV origin inside its page;
- parse a TIM file, validate it, and upload its CLUT and image to the rectangles its header names;
- fill a `POLY_FT4` packet and say what each of its words means;
- choose UVs so that a texture is neither mirrored nor off by one on a cube face;
- explain **affine** texture mapping and **vertex jitter**, and list the ways games reduce the affine error.

## 4. Prerequisites

[Chapter 16](../../part-03-bare-metal-graphics-in-assembly/ch16-copying-data-to-vram/README.md) (VRAM, the 15-bit pixel, uploading an image), [Chapter 20](../../part-04-c-on-the-playstation/ch20-primitives-and-ordering-tables/README.md) (primitives and ordering tables), [Chapters 25](../../part-05-three-dimensions-with-the-gte/ch25-the-gte-coprocessor/README.md) and [26](../../part-05-three-dimensions-with-the-gte/ch26-multiple-objects-and-simple-motion/README.md) (the cube pipeline: `NCLIP`, `AVSZ4`, face table), [Chapter 29](../ch29-the-cd-rom-and-loading-files/README.md) (`cd_load_file`, validating a file before trusting it). [Appendix E.3](../../../appendices/E-file-formats.md) is the formal specification of the TIM format and of the formulas in 5.2 and 5.3.

## 5. Explanation

### 5.1 VRAM and texture pages

VRAM is 1024 x 512 **16-bit units** (2 bytes each, 1 MB). X is counted in units, Y in lines. The book's two 320 x 240 framebuffers sit at (0, 0) and (0, 240), so everything else must go at x >= 320 or y >= 480.

```
 x in 16-bit units:  0       320                  704   736   768   800       1024
                  0  +--------+--------------------+-----+-----+-----+----------+
                     |buffer 0|                    |CRATE|PANEL|LOGO |          |
                 64  |320x240 |   free: textures   +-----+-----+-----+   free   |
                240  +--------+                                                 |
                     |buffer 1|                                                 |
                480  +--------+-------------------------------------------------+
                     | CLUT rows at (0,496) (0,497) (0,498); the rest is free   |
                512  +----------------------------------------------------------+
 CRATE: 8 bpp, 32 x 64 units.  PANEL: 4 bpp, 16 x 64 units (736..751).  LOGO: 4 bpp, 32 x 64 units.
```

A **texture page** is a 256 x 256 *texel* window into VRAM. Its position is given by a column `x/64` (0..15) and a row `y/256` (0 or 1), so a page *starts* on a multiple of 64 units in x and 256 lines in y. How many VRAM units it spans depends on the **color depth**, because shallower pixels are packed tighter:

| Depth | Texels per 16-bit unit | Page size (units x lines) | In a polygon |
|---|---|---|---|
| 4 bpp | 4 (palette index of 4 bits) | 64 x 256 | texel `u` = 4 x (unit offset) |
| 8 bpp | 2 (index of 8 bits) | 128 x 256 | texel `u` = 2 x (unit offset) |
| 16 bpp | 1 (the color itself) | 256 x 256 | texel `u` = unit offset |

UVs are 8-bit **texel** coordinates inside the page: `u, v` in 0..255, with `(0, 0)` the page's top-left corner. Three consequences: a texture is at most 256 x 256 texels, it must not cross the edge of its page, and a polygon can use only **one page**. The panel (4 bpp, x = 736) sits in page column 11 (which starts at x = 704) at texel offset `u0 = (736 mod 64) x 4 = 128`; the crate (8 bpp, x = 704) is in page column 11 too, at `u0 = 0`. Pages of different depths may overlap, as long as the textures' *rectangles* do not.

### 5.2 Palettes: the CLUT

A 4- or 8-bpp texel is not a color but an index into a **CLUT** (color look-up table), a row of 16 or 256 15-bit colors stored in VRAM like any image. A 4-bpp texture therefore takes a quarter of the VRAM of a 16-bpp one (plus its CLUT), and recoloring it means pointing at another CLUT row. The CLUT's x must be a multiple of 16 (the CLUT word keeps `x/16`), and its y is any line.

| Rule | |
|---|---|
| A texel whose color is `0x0000` (the CLUT entry it selects, or the texel itself at 16 bpp) | **transparent**: the pixel is not drawn. The color value counts, not the index |
| Opaque black | store the near-black `0x0421` (the book's `img2tim.py` does); `0x8000` (black with STP set) is also drawn, as true black, on an opaque polygon |
| Bit 15 of a texel color (**STP**, "semi-transparency") | matters only for semi-transparent polygons: texels with STP = 1 are blended, texels with STP = 0 stay opaque |
| Color of the polygon `(r, g, b)` | multiplies the texel: `out = texel x color / 128` per channel (clamped at the maximum), so **128 (`0x80`) is neutral**, 255 brightens almost 2x, 0 gives black |

The `r, g, b` multiply is called **modulation**; command `0x2D` ("raw texture") skips it. This chapter uses `0x2C` with color 128, which shows the texture unchanged.

### 5.3 The two words: tpage and CLUT

```
tpage word (16 bits, in the second UV word of the packet)
 15      9  8 7  6 5  4   3      0
+---------+-----+-----+---+-------+
|  (0)    | tp  | abr | Y | X/64  |      X/64: page column 0..15 (x of the page, in units, divided by 64)
+---------+-----+-----+---+-------+      Y: page row (0: lines 0..255, 1: lines 256..511)
                                         abr: semi-transparency mode 0..3 (0 here)
                                         tp: 0 = 4 bpp, 1 = 8 bpp, 2 = 16 bpp

CLUT word (16 bits, in the first UV word)
 15 14                  6 5          0
+--+---------------------+-----------+
|0 |         Y           |   X / 16  |   Y: the CLUT's line 0..511     X/16: its x, a multiple of 16
+--+---------------------+-----------+
```

The SDK macros do the shifting: `getTPage(tp, abr, x, y)` and `getClut(x, y)` (`psxgpu.h`), with `x, y` the VRAM position of the image or of the CLUT. **Worked example** (the crate, 8 bpp, image at (704, 0), CLUT at (0, 496)): tpage = `704/64 | (0/256) << 4 | 0 << 5 | 1 << 7` = 11 + 128 = `0x8B`; CLUT = `0/16 | 496 << 6` = `0x7C00`; UV origin `(0, 0)`. Appendix E.3.4 has the formulas, and the asset generator writes the same numbers to `build/assets/manifest/CRATE.TIM.json`.

The page word comes from the **image block's** rectangle and the CLUT word from the **CLUT block's**. A TIM does not say "page 11": it says where its pixels are, and you derive the page.

### 5.4 The TIM file

A TIM (Appendix E.3) is an 8-byte header and up to two **blocks**, each a raw VRAM rectangle. All fields are little-endian, and every block starts on a 4-byte boundary.

```
+0   magic    0x00000010
+4   flags    bits 0-2 pmode (0 = 4 bpp, 1 = 8 bpp, 2 = 16 bpp, 3 = 24 bpp); bit 3: a CLUT block follows
+8   CLUT block (if bit 3)          +0 bnum   u32  block size in bytes, including these 12
                                    +4 x      u16  VRAM x, in 16-bit units
                                    +6 y      u16  VRAM y, in lines
                                    +8 w      u16  width in 16-bit units  (NOT pixels)
                                    +10 h     u16  height in lines
                                    +12 data  w x h x 2 bytes, exactly as VRAM holds them
...  image block: the same layout (a 4-bpp image of P pixels has w = P / 4)
```

To put a block in VRAM you hand `LoadImage` its rectangle and its data pointer. **Nothing is converted**: the file already holds VRAM's bytes, and **the header tells you where they belong**. A loader that uploads every TIM to a fixed place ignores them; the verifier moves the textures to catch that.

The SDK has `GetTimInfo(tim, &info)`, and the worked example uses it. It fills a `TIM_IMAGE` with `mode` (the flags word) and pointers into the file: `prect`/`paddr` (image rectangle and pixels) and, only when flags bit 3 is set, `crect`/`caddr`. It checks only the magic (it returns 0 if the magic is right, non-zero if not). A program that loads files from a disc should not trust them (Chapter 29), so the project writes its own parser, with these checks:

| Check | Because |
|---|---|
| the pointer is 4-byte aligned; `size` is at least 20 | the header and the first block header must be readable |
| magic is `0x10`; flags use only bits 0-3; pmode is 0, 1 or 2 | 24-bpp images are display-only; mixed mode is not supported |
| the CLUT flag is set exactly for 4 and 8 bpp | a palette texture without a palette is garbage |
| each block: `w`, `h` at least 1; `x + w <= 1024`; `y + h <= 512`; `bnum == 12 + 2wh`; it fits in the file | the rectangle must exist in VRAM and the data must exist in the file |
| CLUT: `x` a multiple of 16; `w` is 16 (4 bpp) or 256 (8 bpp) | the CLUT word keeps `x/16`; a CLUT row has a fixed length |
| the image block ends exactly at `size` | no trailing data, no truncation |
| the image lies inside one page: `(x mod 64 + w) x m <= 256` and `y mod 256 + h <= 256` (`m` = 4, 2, 1) | UVs are bytes and a polygon has one page |

### 5.5 Uploading

`LoadImage(&rect, data)` copies a rectangle into VRAM by DMA and returns before it finishes: call `DrawSync(0)` before you reuse or free `data`. Upload the CLUT and the image separately, each with its own block's rectangle and the pointer just after its 12-byte header. When both are in VRAM, the copy of the file in RAM is no longer needed: free it.

### 5.6 The `POLY_FT4` packet

`F` = flat (one color), `T` = textured, `4` = quad. After the tag word that links it into the ordering table, the packet is nine 32-bit words:

```
word  byte 3      byte 2   byte 1   byte 0
 0    code 0x2C   b        g        r         command + color (128, 128, 128 = neutral)
 1    y0 (16)              x0 (16)            vertex 0
 2    CLUT (16)            v0       u0        texel of vertex 0; the CLUT word
 3    y1                   x1
 4    tpage (16)           v1       u1        texel of vertex 1; the tpage word
 5    y2                   x2
 6    (0)                  v2       u2
 7    y3                   x3
 8    (0)                  v3       u3
```

The SDK's `setPolyFT4` sets the code `0x2C` and the length 9. Bits of the command byte: bit 0 = raw (no modulation), bit 1 = semi-transparent, bit 2 = textured, bit 3 = quad, bit 4 = Gouraud (`0x3C` = `POLY_GT4`: 12 words, a color per vertex), bit 5 = polygon. The triangle `POLY_FT3` (`0x24`, 7 words) drops vertex 3. In C: `setPolyFT4(p)`, `setRGB0(p, r, g, b)`, `setXY4(p, ...)`, `setUV4(p, u0, v0, u1, v1, u2, v2, u3, v3)`, `p->clut = ...`, `p->tpage = ...`.

### 5.7 UVs on a cube face

The face table from Chapter 25 lists each face's corners in **Z order**: seen from outside, corner 0 is the top-left, 1 the top-right, 2 the bottom-left, 3 the bottom-right. A picture is read in the same order, so a corner's UV depends only on its **index**, not on the face:

```
texture (w x h texels at u0, v0)          face as seen from outside
 (u0,v0)         (u0+w-1, v0)               corner 0 ----- corner 1
    +-----------------+                         |             |
    |   HOVERLINE     |        ->               |   same      |
    +-----------------+                         |   picture   |
 (u0,v0+h-1)     (u0+w-1,v0+h-1)            corner 2 ----- corner 3

corner k:   u = u0 + (k odd ? w-1 : 0)      v = v0 + (k >= 2 ? h-1 : 0)
```

The last texel is `u0 + w - 1`, not `u0 + w`: `u0 + w` is the first texel of whatever sits next to the texture in its page (in the crate's page, `u = 64` is already the panel's data), and a value of 256 does not fit in a byte. So the book's UVs run from the first texel to the last.

The trap: writing the UVs in *perimeter* order `(0,0) (w,0) (w,h) (0,h)` for a quad whose corners are in *Z* order. Corners 2 and 3 swap their texels: the bottom edge is mirrored and the picture folds along the diagonal where the two triangles meet. Rule: **same index, same corner.** If a face still looks mirrored, check its corner order against the face table before you touch the UVs.

### 5.8 Affine mapping and vertex jitter

The GPU does not know a polygon is a perspective view of a rectangle. It splits a quad into **two triangles** (vertices 0-1-2 and 1-2-3) and interpolates `u, v` **linearly in screen space**: this is **affine** mapping. Correct perspective needs a division by depth at each pixel, and the GPU is never told the depth: its vertices are 2D.

```
 a square seen at an angle (the right-hand quad of example/): the far edge 1-3 is shorter

  0 +------____                 Triangles 0-1-2 and 1-2-3 share the edge 1-2.
    |       . '----+ 1          Each maps its half of the texture linearly, but
    |    . '       |            with a different scale, so a straight line in
    | . '      ____+ 3          the texture gets a kink where it crosses 1-2.
  2 +------''''
```

The error grows with the polygon's size on screen and with how much its depth varies across it, and it changes as the polygon turns, so the texture appears to **swim**. The PS1 also has no sub-pixel precision: the GTE gives **integer** screen coordinates, so the vertices of a moving object jump from pixel to pixel and its edges and textures wobble. That is **vertex jitter**; it is part of the PS1 look, and games live with it. They reduce the affine error in these ways:

| Remedy | How |
|---|---|
| Smaller polygons | the error grows with size; the cost is more primitives |
| **Subdivision** | split big polygons into 2 x 2 or 4 x 4 pieces, each with interpolated UVs (Chapter 36 subdivides the polygons near the camera) |
| Keep polygons away from the camera | clip or fade polygons that come close; the error is largest near `z = 0` |
| Design for it | textures that still look fine when bent (noise, grime, decals); no long straight lines on big polygons |

### 5.9 Many textures, few pages

A polygon holds its own `tpage` and `clut`, so changing texture costs nothing extra: faces of one model can use different pages in the same frame. VRAM is the budget. Two framebuffers take 2 x 320 x 240 x 2 = 307,200 bytes, which leaves about 720 KB for textures and CLUTs. Games therefore pack many small textures into one page (an **atlas**: the book's `TRACK.TPK` of Chapter 31 puts 8 tiles in one page, each tile a different `u0, v0`) and reuse one CLUT row for textures that share a palette. The GPU also has a small texture cache; polygons that read nearby texels draw faster than ones that jump around.

## 6. Worked example

[`example/`](example/) loads `CRATE.TIM`, reads its header with `GetTimInfo`, uploads it, prints the mode, the rectangles, the tpage word (`0x008B`) and the CLUT word (`0x7C00`) to the TTY, and draws two quads with the same UVs: a rectangle and a trapezoid. Build and run it with `make run` in `example/` (PCSX-Redux shows the TTY because of `-stdout`). Look at the white dots and the X brace on the trapezoid: they do not lie on straight lines. That is the affine warp of 5.8. Edit it: swap the UVs of corners 2 and 3 and predict the result before you run; change the polygon color to `(64, 64, 64)` and then `(255, 255, 255)`; point `clut` at row 497 (the panel's palette).

## 7. Project: "Crates and Logos"

### 7.1 Behavior

The program boots from `hoverline.cue`, loads three TIMs from the disc, uploads them to VRAM at the places their own headers name, and draws Chapter 25's cube spinning, each face textured. If loading fails, the screen is red.

| Faces (Chapter 25 numbering) | Texture |
|---|---|
| 0 (z = -1), 3 (x = +1) | crate (index 0) |
| 1 (z = +1), 4 (y = -1) | panel (index 1) |
| 2 (x = -1), 5 (y = +1) | logo (index 2) |

This is the table `face_tex[6] = { 0, 1, 2, 0, 1, 2 }`, given in the starter. The camera and pose are given too: `cam_z = 16384` (4 x 4096), `proj_h = 256`, start `rot = (200, 300, 0)`, `rot_step = (16, 28, 0)`.

### 7.2 The contract

`starter/` builds `hoverline.bin` and `hoverline.cue` and boots, but loads nothing and shows a red screen. Given: `CMakeLists.txt`, `iso.xml` (puts `\DATA\CRATE.TIM`, `PANEL.TIM`, `LOGO.TIM` on the disc), `cdrom.c` (Chapter 29's finished `cd_load_file`), `psxe/`, the frame loop, the matrix code, `transform_corners`, and the culling and depth sorting of `draw_faces`. The generated textures:

| File | Depth | Size (texels) | Image at (x, y) | CLUT at (x, y) |
|---|---|---|---|---|
| `CRATE.TIM` | 8 bpp | 64 x 64 | (704, 0) | (0, 496) |
| `PANEL.TIM` | 4 bpp | 64 x 64 | (736, 0) | (0, 497) |
| `LOGO.TIM` | 4 bpp | 128 x 64 | (768, 0) | (0, 498) |

Do not hard-code this table: the verifier boots a second disc whose TIMs are elsewhere. You write, in `tim.c`:

| Function | Contract |
|---|---|
| `int tim_parse(TimInfo *t, const void *data, uint32_t size)` | the checks of 5.4, in that order. On success fills `*t` (`bpp`; the CLUT rectangle, `clut_w = 0` and `clut_data = NULL` if none; the image rectangle; the data pointers into `data`) and returns 1. On any failure returns 0 and **leaves `*t` untouched** |
| `void tim_upload(const TimInfo *t)` | `LoadImage` the CLUT (if any) and the image, each at the rectangle `*t` holds; return only when the GPU is done |
| `void tex_from_tim(Tex *tex, const TimInfo *t)` | `tpage` (abr 0), `clut` (0 if none), `u, v` (the texel origin in its page) and `w, h` (in **texels**) |

and in `main.c`: `load_textures()` (for each of the three: load, parse, upload, `tex_from_tim`, free the file image; on a failure set `load_status = 1 + i`) and the `POLY_FT4` of `draw_faces`.

**The polygon**: one `POLY_FT4` per front face (`NCLIP > 0`), color `(128, 128, 128)`, corners `faces[f][0..3]` in that order, `clut` and `tpage` from `tex[face_tex[f]]`, UVs by the rule of 5.7: corner `k` takes `u = tex.u + (k odd ? tex.w - 1 : 0)` and `v = tex.v + (k >= 2 ? tex.h - 1 : 0)`. Link it at slot `OTZ >> 7`. Read `face_tex` every frame.

**State the verifier reads** (do not change names, types or order; `main()` keeps them linked):

| Symbol | Meaning |
|---|---|
| `tim_info[3]` | `TimInfo` of crate, panel, logo |
| `tex[3]` | `Tex` of the same |
| `face_tex[6]` | `uint8_t`, texture index per face; the verifier overwrites it |
| `load_status` | 0: ok; 1 + i: texture i failed; 100: `cd_init` failed |
| `rot`, `rot_step`, `cam_z`, `proj_h`, `mtx` | as in Chapter 25: angles (4096 = one turn), step, camera distance, projection distance, the matrix in the GTE; the verifier patches `rot` and sets `rot_step` to 0 to freeze a pose |
| `screen_xy[8]`, `screen_z[8]`, `prims_submitted` | per-corner `RTPS` results; polygons linked this frame |
| `frame_no`, `frame_done()` | frames completed; the marker the probe waits at |

### 7.3 Steps

1. `make` in `starter/`, `make run`: a red screen.
2. In `tim.c`, little-endian readers (`rd16`, `rd32`, byte by byte), then `tim_parse`. Check it on paper with the hex dump in Appendix E.3.4 before you run.
3. `tex_from_tim` from 5.3 (check `0x8B` and `0x7C00` for the crate).
4. `tim_upload`, then `load_textures()` in `main.c`. Remove the starter's `load_status = 1` line. Run the verifier now (section 8): its VRAM check rules out a wrong upload before you draw anything.
5. The `POLY_FT4`. Start with one face, then all.

### 7.4 Rules

- Textures come from the disc; the TIM's own header decides where they go.
- Neutral color 128; `0x2C`, not `0x2D`; no semi-transparency.
- Read multi-byte fields byte by byte; never read past `size`.
- Do not change `faces`, `cube`, or the initial values of the state.

### 7.5 Hints

- `RECT r; setRECT(&r, x, y, w, h)` takes the block's own values (units and lines); `LoadImage(&r, ptr)` wants a `const uint32_t *`.
- The first block starts at offset 8; the next at the previous block's offset + its `bnum`.
- 8 bpp: `tp = 1`, `m = 2`; 4 bpp: `tp = 0`, `m = 4`; both are `4 >> tp` (16 bpp: `tp = 2`, `m = 1`).
- `RotMatrix` and the matrix macros are as in Chapter 25 (`load_matrix` is given).
- `ot_alloc` returns `NULL` when the frame's primitive buffer is full: stop drawing.

### 7.6 Stretch goals

- Switch to `POLY_GT4` (`0x3C`) and shade the faces with different vertex colors: what does color 255 do to the logo?
- Load `SKY16.TIM` (16 bpp, no CLUT; `mkassets.py` already generates it, so add it to `iso.xml`) and put it on a face.
- Subdivide each visible face into 2 x 2 quads (UVs interpolated) and compare the warp at `cam_z = 8192`.
- Make part of a texture transparent (color 0) and let the background show through.
- Draw a second cube whose CLUT row you replace with a recolored copy: the same pixels, a different palette.

## 8. Verification

```sh
source tools/env.sh
parts/part-06-assets-cdrom-textures-and-compression/ch30-textured-polygons/verify/verify.sh            # your starter/
parts/part-06-assets-cdrom-textures-and-compression/ch30-textured-polygons/verify/verify.sh --solution # the reference
```

The emulator boots `hoverline.cue`. A second run boots a disc whose three TIMs are generated into other VRAM rectangles (other page columns, the second page row, other CLUT rows) and patches the face-to-texture table, the pose and the spin at run time. A third run calls your `tim_parse` and `tex_from_tim` directly. The checks compute every expected value with `tools/assets` (`tim.py`, `img2tim.py`).

| Check | What it means | If it fails |
|---|---|---|
| `the state symbols exist` | The labels of 7.2 are in the program | A removed declaration or keep-alive line |
| `the disc image has ...`, `the textures are not inside the program` | The disc holds the three TIMs; their pixels and CLUTs are not in `game.exe` | `iso.xml` edited; textures compiled in |
| `boots from the disc, loads the three TIMs; tim_info and tex[] ...` | `load_status` 0; `tim_info` equals the TIM headers; `tex[]` the tpage word, CLUT word, `u, v, w, h` of E.3.4 | Widths read as pixels; byte order; formulas |
| `VRAM holds each TIM's CLUT and image ...` | After the run, VRAM rectangles equal the TIM blocks, byte for byte | Wrong rectangle; image uploaded with `w` in pixels; no `DrawSync` |
| `an alternative disc ...` | The same, with the TIMs elsewhere | Placement hard-coded |
| `the cube spins about its center ...` | `rot` advances by `rot_step`; the matrix is a rotation with translation `(0, 0, cam_z)`; `face_tex` is the given table | The given frame code or initial values were changed |
| `polygons: one POLY_FT4 per front face ...` | Walking the ordering table at every fourth frame: exactly the front faces, command `0x2C`, color 128, corners at the projection (3 px) in the table's order, tpage and CLUT words of the face's texture, UVs per 5.7 exactly, slot `OTZ >> 7` (2 slots) | The message names the face and the field; a hint points out a mirrored texture |
| `picture: every large front face shows its texture ...` | At frames 12, 40, 70: for sample points inside each large face the pixel equals the texel the **affine** mapping gives through the polygon you drew (within one texel) at 90% of the points or more, and the face shows several colors | Wrong palette (right shapes, wrong colors); wrong page (noise); flat color |
| `alt run: ...` | Another table (`2 0 1 1 2 0`), a frozen pose, other placements: the polygons and picture again | `face_tex` copied at start; placement or page bits hard-coded |
| `tim_parse: ...` | 7 valid TIMs (4, 8 and 16 bpp, a 2-row CLUT, a full page, an 8-bpp image that crosses a 64-unit line inside its page) and 20 damaged or misaligned ones | A missing check from 5.4 |
| `tex_from_tim: ...` | 8 crafted placements, including the second page row, the last page column and an 8-bpp image across a 64-unit line | `y/256`, `x mod 64`, depth multiplier |

A pass ends with `CHAPTER 30: PASSED (13/13 checks)` (the thirteenth compares the reference solution's `psxe/` with `common/psxe` and does nothing for your project). The picture check models the affine warp, so the warp does not fail it; wrong colors, mirroring and flat polygons do.

## 9. Common pitfalls

- **Width in pixels.** A TIM's `w` is in 16-bit units: a 4-bpp 64-pixel image has `w = 16`. Uploading it with `w = 64` writes four times too much, and garbage looks plausible.
- **A hard-coded placement.** It passes on your disc, then fails the day a texture moves. Take rectangles from the header.
- **Page word from the CLUT.** The tpage comes from the **image** rectangle; the CLUT word from the CLUT rectangle.
- **Wrong depth bits.** `tp` 0 for 4 bpp, 1 for 8 bpp. A 4-bpp texture read as 8 bpp takes each pair of texels as one palette index: the picture is squeezed and its colors are garbage.
- **`u = w` instead of `w - 1`.** Pixels along the right edge can sample the neighboring texture; at `u0 + w = 256` the value does not even fit in a byte.
- **Perimeter-order UVs on a Z-order quad.** Corners 2 and 3 swap texels: the picture folds along the diagonal.
- **Freeing before `DrawSync`.** The DMA reads memory that is already reused.
- **Texture inside a framebuffer.** x below 320 and y below 480: the next frame overwrites it (or it overwrites the picture).
- **Color `0x0000` as black.** Such texels are not drawn. Use `0x0421`.
- **Crossing a page boundary.** A 128-texel-wide 4-bpp texture (32 units) at `x mod 64 > 32` runs past the page's 256 texels; its UVs would need to exceed 255.
- **Trusting the file.** `GetTimInfo` checks only the magic; a damaged TIM can overwrite any part of VRAM, the framebuffers included.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- psx-spx (nocash PSX specs): "GPU Rendering Attributes" (tpage and CLUT words, texture window), "GPU Render Polygon Commands" (packet layouts), "GPU Memory Transfer Commands", and the TIM section of "CDROM File Formats".
- `.toolchain/opt/psn00bsdk/include/libpsn00b/psxgpu.h` (`POLY_FT4`, `getTPage`, `getClut`, `TIM_IMAGE`, `GetTimInfo`) and PSn00bSDK's `examples/graphics/balls`.
- [Appendix E.3](../../../appendices/E-file-formats.md) and `tools/assets/README.md` for `img2tim.py` (make a TIM from your own PNG: `--bpp 4 --x 640 --y 256 --cx 0 --cy 499`).
- Next: Chapter 31 packs eight textures into one compressed file and shows them as a grid of quads.
