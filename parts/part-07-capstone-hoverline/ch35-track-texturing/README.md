# Chapter 35: Track Texturing

## 1. Concept

VRAM is a fixed 1024 x 512 picture that holds *everything*: the two framebuffers, every texture and every colour palette. Nothing places textures there for you. This chapter plans that space by hand (a **VRAM layout**), loads the eight track tiles into the places you chose, and draws every track face as a textured quad whose UVs come from the face record, **mirrored** when the face carries `FLIP_H`.

## 2. Why it matters

The track is 560 faces but only eight small tiles: 64 x 64 texels each, reused everywhere. That reuse is the whole point of tiling. It only works when the layout is right: a tile that overlaps a framebuffer is overwritten every frame, a tile that crosses a texture page cannot be addressed, and a wrong page word shows another tile's pixels. Chapters 36 to 41 add more VRAM users (ship textures, a font, subdivided faces that reuse the same tiles). A layout you planned and wrote down is the one you can extend.

## 3. Learning objectives

After this chapter you can:

- draw the VRAM map: which rectangles the framebuffers, the loaded TIMs and your tiles occupy, and how much is free;
- say what a **texture page** and a **CLUT** are, how big a tile is in VRAM at 4, 8 and 16 bpp, and where pages and CLUTs may start;
- turn a tile's VRAM position into its **tpage word**, **CLUT word** and **UV origin**, and back;
- **relocate** a TIM: upload its pixels where your plan says, not where the file says;
- build a `POLY_FT4` from a `.TRK` face: texture index, texture-local UVs, the tile's origin, the two words;
- mirror a face's texture for `FLIP_H` by changing UVs only, and say why the mirror is `u_min + u_max - u`;
- find the contents of VRAM in the PCSX-Redux VRAM viewer and in a dump.

## 4. Prerequisites

[Chapter 30](../../part-06-assets-cdrom-textures-and-compression/ch30-textured-polygons/README.md) (tpage, CLUT, the UV rule), [Chapter 31](../../part-06-assets-cdrom-textures-and-compression/ch31-compression-lzss-texture-packs/README.md) (`.TPK`: given as `tpk_parse` / `tpk_unpack`), [Chapter 32](../../part-06-assets-cdrom-textures-and-compression/ch32-a-real-model-format-shp/README.md) (`POLY_FT4` from a file), [Chapter 34](../ch34-track-geometry/README.md) (the program this chapter extends), and Appendix E: [E.3.4](../../../appendices/E-file-formats.md) (TSB, CBA, UV origin), [E.6](../../../appendices/E-file-formats.md) (`.TPK`), [E.10.3](../../../appendices/E-file-formats.md) (face records).

## 5. Explanation

### 5.1 VRAM is one picture, and you are the allocator

VRAM is 1024 **units** wide and 512 **lines** tall. A unit is one 16-bit word, so VRAM is exactly 1 MiB (524,288 units). The GPU draws into it, scans the display out of it and reads textures from it. All of that shares one address space, and no one stops two uses from overlapping.

```
        x ->  0         320                                           1023
  y=0         +----------+------------------------------------------------+
              | frame-   |                                                |
              | buffer 0 |             columns 320..1023                  |
              | 320x240  |             free for textures and CLUTs        |
  y=240       +----------+              (rows 0..479)                     |
              | frame-   |                                                |
              | buffer 1 |                                                |
              | 320x240  |                                                |
  y=480       +----------+------------------------------------------------+
              |  rows 480..511: 32 lines, free (CLUTs live here)          |
  y=511       +-----------------------------------------------------------+
```

The two buffers are the project's `psxe` display: draw buffer 0 at (0,0) and 1 at (0,240), 320 x 240 each. Everything the GPU draws lands in one of them, so a texture there is gone after the next frame's clear.

### 5.2 What is already in VRAM

`main.c` loads two more things at the places **their own TIMs name** (you may not overlap them). `tools/assets` also names a default place for the track tiles; you will not use it.

| What | Image (x, y, w x h) | CLUT (x, y, w x h) |
|---|---|---|
| framebuffer 0, 1 | (0,0) 320x240 and (0,240) 320x240 | none |
| `LOGO.TIM` (title) | (768, 0) 32x64 | (0, 498) 16x1 |
| `PROPS.TPK` tile 0 (scenery) | (512, 0) 8x64 | (32, 480) 16x1 |
| `PROPS.TPK` tile 1 | (520, 0) 16x64 | (32, 481) 16x1 |

`example/tiledump.py` prints this table from the real files (6). Two more claims on VRAM:

- **The SDK font.** `FntLoad(960, 0)` is what every PSn00bSDK example calls. It uploads a 32 x 32-unit image at (960, 0) and its 16 x 1 CLUT just below, at (960, 32): x 960..991, y 0..32. A program that prints text must keep that rectangle (or call `FntLoad` with another place) free.
- **More textures** in later chapters. Leave room: the free-space section of `vram_layout.md` is where you account for it.

### 5.3 Texture pages

A polygon does not address VRAM freely. It names one **texture page** (**tpage**), and its UVs are coordinates *inside* that page.

| | 4 bpp (16 colours) | 8 bpp (256 colours) | 16 bpp (direct) |
|---|---|---|---|
| a page is | 256 x 256 texels | 256 x 256 texels | 256 x 256 texels |
| in VRAM: width | 64 units | 128 units | 256 units |
| a 64x64 tile: width in units | 16 | 32 | 64 |
| a page starts at | x multiple of 64, y = 0 or 256 | the same | the same |
| needs a CLUT | yes, 16 x 1 units | yes, 256 x 1 units | no |

```
 the pages of VRAM: 16 columns x 2 rows (a page START is every 64 units / 256 lines)

 x:    0    64   128  192  256  320  384  448  512  576  640  704  768  832  896  960
 y=0   [p0 ][p1 ][p2 ][p3 ][p4 ][p5 ][p6 ][p7 ][p8 ][p9 ][p10][p11][p12][p13][p14][p15]
 y=256 [p16][p17][p18][p19][p20][p21][p22][p23][p24][p25][p26][p27][p28][p29][p30][p31]
        '---- framebuffers: pages 0..4 and 16..20 (rows 0..479) ----'
        (4 bpp pages are 64 units wide, as drawn; an 8-bpp page spans 2 columns, a 16-bpp page 4)
```

**Why a tile must lie inside one page.** The UV `u` is one byte (0..255) and the page is 256 texels wide. A tile that starts at texel 240 of its page and is 64 texels wide would need `u` up to 303. There is no such UV: the rule is `u0 + width <= 256` and `v0 + height <= 256`. A 4-bpp tile is 16 units wide, so its `x mod 64` must be at most 48.

```
 a tile at x = 700, y = 300 (4 bpp):     a tile at x = 668, y = 300:
   page x = 640, y = 256  (page 26)        page x = 640, y = 256  (page 26)
   x mod 64 = 60 -> u0 = 60 * 4 = 240      x mod 64 = 28 -> u0 = 112
   240 + 64 = 304 > 256: NOT A LEGAL TILE  v0 = 300 mod 256 = 44; 112 + 64 <= 256: fine
```

Several tiles share a page: eight 64 x 64 tiles at 4 bpp need half of one page (a page holds 16). That is why 4 bpp is the track's choice.

### 5.4 The three numbers per tile

For a tile whose image is at VRAM `(x, y)` (units, lines) and whose CLUT is at `(cx, cy)` (`cx` a multiple of 16):

| | Formula | Meaning |
|---|---|---|
| **tpage word** | `x/64 \| (y/256) << 4 \| (abr << 5) \| (tp << 7)` | page, semi-transparency mode (0 = none), colour depth: `tp` 0 = 4 bpp, 1 = 8, 2 = 16 |
| **CLUT word** | `cx/16 \| cy << 6` | where the palette is |
| **UV origin** | `u0 = (x mod 64) * m`, `v0 = y mod 256` | the tile's top-left texel in the page; `m` = 4, 2, 1 for 4, 8, 16 bpp |

`getTPage(tp, abr, x, y)` and `getClut(x, y)` compute the words (`vram_layout.h` wraps them as `TPAGE_4BPP` and `CLUT_AT`). A face's absolute UV is the tile's `u0, v0` plus the face's texture-local UV (0..63 for these tiles).

**CLUTs.** A CLUT is a 16-entry (4 bpp) or 256-entry (8 bpp) row of colours: **one line high**, anywhere in VRAM, but its `x` is a multiple of 16. A 4-bpp CLUT is 16 units wide, so eight of them in one row take 128 units. The rows below the framebuffers (y 480..511, x 0..319) are only 32 lines tall and fit CLUTs and nothing else well: the usual home. Each tile has its own CLUT here, because the TIMs carry their own palettes.

### 5.5 Relocating a tile

Every TIM carries *its own* VRAM rectangles (E.3). `tim_upload` copies the pixels to exactly those rectangles. That is convenient for one texture and a trap for a program with a layout: two packs can name the same places, and the TIM does not know where the framebuffers are. The **tile's pixels do not change when it moves**: only the rectangle it is copied to, and the words that point to it.

This chapter's `tim_upload_at(info, img_x, img_y, clut_x, clut_y)` (given) is `tim_upload` with the destination as arguments. Your loader reads each TIM with `tim_parse`, **checks it against its slot**, and uploads it at the slot's place. The verifier's second disc is built so that a loader that trusts the TIM writes onto the framebuffers (7.4).

### 5.6 The faces of the track

Each face (E.10.3) holds a texture index `tex` (the id in `TRACK.TPK`, or `0xFF` = untextured), four texture-local UVs in Z order (one per vertex, 0..63) and a `FLIP_H` flag. The generated track uses the tiles like this (from `tiledump.py`):

| id | tile | looks like | faces | of which `FLIP_H` |
|---|---|---|---|---|
| 0 | `asphalt` | speckled road | 111 | 56 |
| 1 | `asphalt_worn` | patches and cracks | 111 | 0 |
| 2 | `lane_stripe` | dashed centre line | 107 | 0 |
| 3 | `boost` | chevrons | 4 | 0 |
| 4 | `start_line` | chequered flag | 3 | 0 |
| 5 | `wall_a` | wall with a glowing rail | 168 | 56 |
| 6 | `wall_b` | yellow-black hazard stripes | 56 | **56 (all)** |
| 7 | `glow` | cyan gradient | 0 | 0 |

Do not rely on this table in code: the verifier's second disc permutes the ids. The face's `tex` is the only truth.

**The UV rule.** Corner `k` of the quad gets the texel `(u0 + u_k, v0 + v_k)`, and the quad's four corners are in Z order, as in Chapter 30. The face's `u_k`, `v_k` run 0..63, not 0..64: a 64-texel tile spans texels 0 to **63**, and the GPU samples the texel *at* the coordinate, so `u = 64` would read the next tile's first column.

**Flipping.** `FLIP_H` (bit 4) means *mirrored in U*. The tile in VRAM is untouched; the face's UVs are changed:

```
 as stored (lane face):              FLIP_H: u -> u_min + u_max - u   (here 63 - u)

   v0 (0,0)----v1 (63,0)               v0 (63,0)----v1 (0,0)
    |             |                     |             |
   v2 (0,63)---v3 (63,63)              v2 (63,63)---v3 (0,63)

   the picture reads  ->               the picture reads  <-
```

Why `u_min + u_max - u` and not "swap `u0` and `u1`"? On a **lane** quad the U edge is `v0 -> v1`, and both agree. On a **wall** quad the U axis runs along `v0 -> v2`: `u0 = u1`, so swapping them changes nothing. The general rule mirrors the face inside its own U range and works for both (Appendix E.10.3 states it). The mirror comes **before** the tile origin is added: `u = u0 + (u_min + u_max - u_local)`. The hazard-stripe tile (id 6) is only ever used flipped: ignoring `FLIP_H` is visible there, and on the start line (never flipped) a *wrong* mirror is visible too (the chequer swaps colours).

**Edges.** The PS1 has no texture filtering: each pixel takes one texel, and the UVs are interpolated *between* the corners' values. With every corner inside `0..63` (`u0 + w - 1` is the last texel, Chapter 30), a face never reads its neighbour, so tiles may touch in VRAM. A one-texel border around each tile (copies of the edge texels) is the insurance for code whose UVs can reach `w`; it costs a bigger footprint (68 x 66 texels at 4 bpp: 17 units, three tiles across a page). Say in your `vram_layout.md` which you chose.

### 5.7 The packet and the budget

A textured quad is a `POLY_FT4`, **40 bytes** (a flat `POLY_F4` is 24):

```
 word 0  tag
 word 1  code 0x2C | r g b          (128, 128, 128: the texel unchanged)
 word 2  x0 y0
 word 3  u0 v0 | CLUT word  << 16   <- the CLUT rides with the FIRST UV pair
 word 4  x1 y1
 word 5  u1 v1 | TPAGE word << 16   <- the tpage rides with the SECOND
 word 6  x2 y2
 word 7  u2 v2 | (padding)
 word 8  x3 y3
 word 9  u3 v3 | (padding)
```

Colour 128 is the neutral value: the GPU multiplies the texel by `colour / 128`. The ordering-table slot, the culling and the counters are Chapter 34's, unchanged. Only the packet differs: 560 faces take up to 22,400 bytes (`PRIM_BUF_SIZE` is 32,768 in this chapter's `psxe`), 40,320 with every outline, and a full buffer drops faces exactly as before. A face with `tex = 0xFF` (or an id the program did not load) is drawn as in Chapter 34: a flat quad in the flag colour.

### 5.8 Looking at VRAM

In PCSX-Redux: **Debug > GPU > VRAM viewers > Show main VRAM viewer** shows all 1024 x 512 pixels of VRAM. Pause, and find your tiles, the CLUT row and the framebuffers. A 4-bpp tile looks like garbled colours in this view, because VRAM holds *indices* packed four to a unit, not colours: the viewer shows them as 16-bit pixels. A **CLUT row** looks like 16 distinct colours in a line. Wrong places show up at once: a tile inside the framebuffer is overdrawn, a missing CLUT is a row of black.

The host-side equivalent is `example/vramdump.py` (6): an ASCII occupancy map and a PNG of a dump, which is what the verifier compares against.

## 6. Worked example

Two host scripts, both standard Python (the book's venv has Pillow for the PNG).

```sh
python ../example/tiledump.py build/assets/TRACK.TPK build/assets/TRACK.TRK --disc-dir build/assets   # from starter/, after make
```

prints, per tile: bpp, the rectangle and CLUT the TIM itself names (its default place: your plan may ignore it), the size, how many faces use it and how many are flipped, and the rectangles that are already taken. It is the input of your plan.

```sh
verify.sh --solution --keep         # leaves .../run-default/vram.bin (and the screenshots)
python ../example/vramdump.py <work dir>/run-default/vram.bin             # ASCII occupancy map, 1 char = 16 units x 16 lines
python ../example/vramdump.py vram.bin --png vram.png                     # the whole VRAM
python ../example/vramdump.py vram.bin --png tiles.png --rect X Y W H     # only a rectangle, enlarged 4x
```

Run it on a dump of the reference solution and compare the map with the one you drew: the framebuffers are the blocks of `#` at the left, everything else is thin.

## 7. Project: the textured track

### 7.1 Behaviour

The program is Chapter 34's: the title, **Start** into the game, the track from behind the start line, the fly camera, **Select** toggles the wireframe. Now the lanes and walls are textured: asphalt with a dashed centre line, glowing-rail and hazard-stripe walls, cyan-chevron boost pads and a chequered start line, with the mirrored faces mirrored. A face that cannot be textured is flat as before.

### 7.2 The contract

`starter/` is Chapter 34's `solution/` plus the new pieces. It builds and boots, and draws the **flat** track, because `track_tex_load` does nothing and `track_face_uv` says "untextured". **Read `track_tex.h`, `vram_layout.h` and `tim.h` first.** **Given:** everything of Chapter 34 (with the `gte_ldv0` pitfall of 9 fixed), `tim_upload_at`, `main.c` (it calls your `track_tex_load` on `\DATA\TRACK.TPK;1`; a failure is not fatal), `iso.xml` and `CMakeLists.txt` with the new file, `TileSlot` and the two helper macros. **You write:**

| File | What |
|---|---|
| `vram_layout.md` | the plan: five sections (template given) |
| `vram_layout.h` | `LAYOUT_INIT`: one `TileSlot { x, y, w, h, tpage, clut }` per texture id |
| `track_tex.c` | `track_tex_load`, `track_face_uv` |
| `track_render.c` | `fill_textured` (the `POLY_FT4`); `draw_face` already chooses between it and `fill_flat` |

**State the verifier reads** (names and types fixed):

| Symbol | Meaning |
|---|---|
| `vram_layout[]` | your `TileSlot` table, 12 bytes per id (`x y w h tpage clut`, `u16` each), at least 8 entries |
| `track_tex[]`, `track_tex_count`, `tex_status` | per id the `Tex` the loader derived (`tpage clut u v w h`); tiles loaded; 0 or `TT_ERR_*` |
| the Chapter 34 state | `track_stats`, `cam_eye`, `cam_yaw`, `view_mtx`, `prims_submitted`, `frame_no`, the ordering table |

### 7.3 Steps

1. `make` in `starter/`, boot it: the flat track. Run `tiledump.py`. Run the program in PCSX-Redux and open the VRAM viewer: find what is there.
2. **Plan on paper**: for each tile pick `(x, y)` inside one page, away from the framebuffers, `LOGO` and `PROPS`; for each CLUT a place `(cx, cy)` with `cx` a multiple of 16. Write the plan in `vram_layout.md` first (tile table, ASCII map, free space).
3. `vram_layout.h`: the numbers, with `TPAGE_4BPP` and `CLUT_AT`.
4. `track_tex_load`: file, pack, then for **every** tile `tim_parse`, check it against its slot, and only then upload with `tim_upload_at`; fill `track_tex[id]`. Look at the VRAM viewer: your tiles are where you planned.
5. `track_face_uv`: tile origin + the face's UV, mirrored when flagged.
6. `fill_textured`: the `POLY_FT4`. The track is textured.
7. `vram_layout.md`: the flip section, free-space numbers, the rationale. Run `verify.sh`.

### 7.4 Rules

- The plan is data: ids index `vram_layout`; code does not know that id 6 is a wall.
- **Relocate**: the tile goes where the slot says, never where its TIM says. The verifier's second disc has TIMs that name places on the framebuffers.
- The texture index is the face's own `tex`. `0xFF`, or an index the program did not load, means a flat quad in the flag colour (Chapter 34).
- UVs are absolute inside the page: tile origin + face UV. `FLIP_H` mirrors with `u_min + u_max - u`, before the origin is added.
- Check the slot before the upload: rectangles inside VRAM, the CLUT word consistent, bpp and size equal to the TIM's (`TT_ERR_*` in `track_tex.h`, in that order).
- No tile, CLUT or image overlaps a framebuffer, `LOGO.TIM`, `PROPS.TPK` or another tile.
- Free every buffer `track_tex_load` allocates, on every path.

### 7.5 Hints

- A tile is 16 units x 64 lines. `w` in the slot is in units.
- `tpk_parse`, `tpk_unpack` and `cd_load_file` are Chapter 29 and 31's; `tim_parse` already refuses a TIM that crosses a page.
- `tim_upload_at` waits for the GPU (`DrawSync`) after each rectangle.
- The `POLY_FT4` fields are `x0..y3`, `u0..v3`, `clut`, `tpage` (Chapter 30, 32). Write the four `trk_sxy` words as `fill_flat` does.
- Do not trust one view: the VRAM viewer shows the pixels, the verifier compares them byte for byte, the screenshot shows what a polygon makes of them.

### 7.6 Stretch goals

- Make `asphalt_worn` an 8-bpp tile (`img2tim.py --bpp 8`), change your plan and the loader's slot check, and see the footprint grow.
- Draw the track with a second CLUT (a night palette) by changing **only the `clut` word** of the packets: same pixels, other colours.
- Add a one-texel border to the tiles (5.6) and compare the seams (a bordered TIM no longer matches the verifier's tiles).
- Make the boost pads semi-transparent: `abr` in the tpage word and code `0x2E`.

## 8. Verification

```sh
source tools/env.sh
parts/part-07-capstone-hoverline/ch35-track-texturing/verify/verify.sh            # your starter/
parts/part-07-capstone-hoverline/ch35-track-texturing/verify/verify.sh --solution # the reference
```

About 20 seconds: a build and two emulator runs (the disc, and a second disc). The probe reads `vram_layout` and `track_tex` from RAM, taps Start, then writes 18 (main) or 22 (second disc) camera poses and records the packets of the ordering table, `view_mtx`, `track_stats` and a screenshot for each; at the end it dumps the whole VRAM. Python computes everything else from the generated files: Chapter 34's exact GTE model, then the `POLY_FT4` of every face.

| Check | What it means | If it fails |
|---|---|---|
| `vram_layout.md ...` (two checks) | the five headings, every tile named, at least 1400 characters of text outside comments, and every tile's x, y, CLUT x, y as numbers in the document | the template left empty; a plan the header does not match |
| `the plan` | read from RAM: slot size = the TIM's; inside VRAM; one page per tile; tpage and CLUT words consistent; no overlap with the framebuffers, `LOGO`, `PROPS`, or each other | page crossing (`x mod 64 + w > 64`); words from other coordinates; a CLUT inside a tile |
| `the loader's table` | `track_tex[id]` = (tpage, clut, `u0`, `v0`, 64, 64) from the declared slot | origin in units instead of texels |
| `VRAM holds every tile ...` (main, alt) | each tile's image and CLUT, byte for byte, at the declared place; `LOGO` and `PROPS` intact | upload at the TIM's place (the second disc catches it); `DrawSync` missing |
| `... packets ...` (main, alt) | every packet of every pose equals the model: `POLY_FT4`, UV = origin + face UV (mirrored for `FLIP_H`), tpage and CLUT words; `0xFF` faces as `POLY_F4`; UVs inside the tile | `FLIP_H` ignored or the wrong formula; tpage in the wrong word; hard-coded ids |
| `... pictures ...` (main, alt) | sampled pixels of top-most faces equal the texel their UVs select (looked up in the TIM); flipped faces show the mirrored tile, unflipped faces do not | VRAM and packets disagree |
| `the primitive buffers` | the guard bytes behind the buffers stayed `0xA5` | writing past `ot_alloc`'s block |

The second disc has track 2 moved far from the origin (Chapter 34), **all texture indices permuted**, two sections with `tex = 0xFF`, and a `TRACK.TPK` whose eight tiles are in reversed order and whose TIMs name places on the framebuffers. The `TT_ERR_*` paths are not exercised: test them yourself with a broken slot. A pass ends with `CHAPTER 35: PASSED (15/15 checks)`. The untouched starter fails; so do a tile on a framebuffer, a tile across a page, `FLIP_H` ignored, and an upload at the TIM's own place.

## 9. Common pitfalls

- **Units versus texels.** `w` in a `TileSlot` is in 16-bit units: 16 for a 64-texel 4-bpp tile. `u0` is in texels: `(x mod 64) * 4`. Mixing them gives a plausible wrong picture.
- **A tile across a page.** `x mod 64 + 16 > 64` means the UVs would have to exceed 255.
- **The tpage word of the wrong place.** It names the *page* the tile is in, not the tile: `x/64`, `y/256`, not `x`, `y`.
- **CLUT and tpage in the wrong UV word.** CLUT with the first pair, tpage with the second.
- **A CLUT with `x` not a multiple of 16.** The word has no bits for it; the palette is read from the wrong place.
- **Trusting the TIM's own rectangles.** They are defaults for a loose file. The second disc shows what happens on top of a framebuffer.
- **Flip by swapping `u0` and `u1`.** Right on a lane quad, a no-op on a wall quad.
- **Flipping after adding the origin.** `63 - (u0 + u)` is not the mirror in the page.
- **UV 64.** The last texel of a 64-texel tile is 63.
- **Uploading while the GPU is busy.** `LoadImage` is asynchronous: `DrawSync(0)` before freeing the file image (`tim_upload_at` does it).
- **A local `SVECTOR` for `gte_ldv0`.** Chapter 34's code stored the vertex into the global `trk_rel` and then ran the `gte_ldv0` macro, whose `asm` has no `"memory"` clobber, so nothing told the compiler to finish the stores first. It happened to work. This chapter's copy has `__asm__ volatile("" ::: "memory");` before the macro: put the same barrier before any `gte_ld*` that reads something you have just written.
- **Hard-coding which id is which.** The second disc permutes the ids.
- **Forgetting the fallback.** `tex = 0xFF` is legal in a `.TRK`.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- Appendix E.3.4 (TSB, CBA, UV origin), E.6 (`.TPK`), E.10.3 (faces, `FLIP_H`); `tools/assets/layout.py` (the book's default places, which are not a plan to copy).
- psx-spx, "GPU Texture Caching", "GPU Render Polygon Commands" and "GPU Memory Transfers".
- Chapters 30 and 32 (the same packets), Chapter 36 (the tiles stretched over subdivided faces).
