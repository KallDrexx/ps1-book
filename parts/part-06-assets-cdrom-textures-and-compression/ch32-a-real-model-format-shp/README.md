# Chapter 32: A Real Model Format: `.SHP`

## 1. Concept

A production model file holds **many kinds of polygon**: flat or Gouraud-shaded, triangle or quad, textured or not. Each record starts with a **type tag**; the parser reads the tag, knows that type's layout and size, and builds the matching GPU primitive. You write that parser for the book's `.SHP` format and draw the Hoverline ship, first flat-shaded and then textured.

## 2. Why it matters

PS1 hardware has eight polygon commands, and a model uses all of them for a reason. A flat polygon is the cheapest thing the GPU draws (a hull panel); Gouraud shading gives a smooth nose; a texture costs more GPU time and more bytes in the file. A file that stored every face as the biggest type would waste space and GPU time. So real formats store *variable-length records*, and their loaders are a loop that dispatches on a tag and advances a pointer by the record's size. The same habits (dispatch on a tag, advance by a size, check bounds before reading) serve every loader in the rest of the book.

## 3. Learning objectives

After this chapter you can:

- lay out a `.SHP` file (header, vertex list, normal list, primitive list) and say where each part starts;
- walk variable-length records by their size field and dispatch on a type tag;
- validate a file before trusting it: header against file size, record sizes against the end of the file, indices against counts;
- explain why `sizeof(p)` and `sizeof(*p)` differ, and why a *file record* size is not a *GPU packet* size;
- turn a texture-local UV and a texture id into the absolute UVs, `tpage` and `clut` words a textured primitive needs (TSB and CBA arithmetic);
- build all eight primitive types, with a flat-shaded fallback that draws the same geometry untextured.

## 4. Prerequisites

[Chapter 29](../ch29-the-cd-rom-and-loading-files/README.md) (`cd_load_file`, validating a model before use, flat faces), [Chapter 30](../ch30-textured-polygons/README.md) (`POLY_FT4`, UV rule, tpage and CLUT words), [Chapter 31](../ch31-compression-lzss-texture-packs/README.md) (the texture store; **its `tpk_load` is given here**), and the GTE chapters [25](../../part-05-three-dimensions-with-the-gte/ch25-the-gte-coprocessor/README.md) to [28](../../part-05-three-dimensions-with-the-gte/ch28-the-camera/README.md) (`gte_*` macros, `NCLIP`, `AVSZ`, ordering-table slots). [Appendix E.8](../../../appendices/E-file-formats.md) specifies the format; this chapter explains it and you must follow it exactly.

## 5. Explanation

### 5.1 One file, three lists

```
0x00 +--------------------+
     | header   (0x40)    |  "SHP1", file size, name, counts, offsets, bounding box
0x40 +--------------------+  vertices_offset
     | vertices  8 B each |  s16 x, y, z, pad     (an SVECTOR: gte_ldv0 reads it as is)
     +--------------------+  normals_offset
     | normals   8 B each |  s16 x, y, z (4.12), pad   (one per distinct face normal)
     +--------------------+  prims_offset
     | primitives         |  records back to back, prims_size bytes, NOT all the same size
     +--------------------+  file_size
```

The generated ship is 1,492 bytes: 46 vertices, 27 normals, 33 primitives (844 bytes), 3 textures. A primitive never stores coordinates. It stores **indices** into the vertex list, so a vertex shared by six faces is stored once and transformed once.

| Header field | At | Meaning |
|---|---|---|
| `file_size` | 0x04 | whole file, bytes |
| `name` | 0x08 | 16 ASCII bytes, NUL-padded; a 16-character name has no terminating NUL |
| `vertex_count`, `normal_count`, `prim_count`, `texture_count` | 0x18 | four `u16`; `texture_count` = highest texture index used + 1 |
| `vertices_offset`, `normals_offset`, `prims_offset`, `prims_size` | 0x20 | four `u32`, bytes **from the start of the file** |
| `bbox` | 0x30 | six `s16`: min x y z, max x y z |

All fields are little-endian, like the CPU, so on the console you could read them directly *if* the address is aligned; this chapter reads them byte by byte anyway (5.3).

### 5.2 Eight record types

The type tag names three properties: triangle or quad, flat or Gouraud, textured or not.

| Tag | Type | Vertices | Colors | UVs + texture | Record size | GPU packet |
|---|---|---|---|---|---|---|
| 0 | `F3` | 3 | 1 | no | 16 | `POLY_F3`, 20 B |
| 1 | `F4` | 4 | 1 | no | 20 | `POLY_F4`, 24 B |
| 2 | `G3` | 3 | 3 | no | 24 | `POLY_G3`, 28 B |
| 3 | `G4` | 4 | 4 | no | 32 | `POLY_G4`, 36 B |
| 4 | `FT3` | 3 | 1 (modulation) | yes | 24 | `POLY_FT3`, 32 B |
| 5 | `FT4` | 4 | 1 | yes | 32 | `POLY_FT4`, 40 B |
| 6 | `GT3` | 3 | 3 | yes | 32 | `POLY_GT3`, 40 B |
| 7 | `GT4` | 4 | 4 | yes | 44 | `POLY_GT4`, 52 B |

F = flat (one color), G = Gouraud (one color per vertex, blended across the polygon), T = textured. Quads are in **Z order** (`v0 v1 v2 v3`, the triangles `v0 v1 v2` and `v1 v3 v2`), exactly what `POLY_*4` wants: never reorder them. The color of a textured primitive is a **modulation**: the texel is multiplied by `color / 128`, so `128` leaves it unchanged.

Every record begins with the same 4 bytes, and the body follows in a fixed order:

```
 +0   +1     +2..3          +4 ...
 [type][flags][size  (u16)]  [vertex indices: 3 or 4 x u16]
                             [normal index u16] [pad u16: quads only]
                             [UVs: 3 or 4 x (u,v) bytes]     } textured types only
                             [texture index u16] [pad u16: quads only]  }
                             [colors: 1 or 3 or 4 x (r,g,b,0)]

 GT4 (44 bytes):  type=7 flags size=44 | v0 v1 v2 v3 | normal pad | u0 v0 .. u3 v3 | tex pad | 4 colors
 F3  (16 bytes):  type=0 flags size=16 | v0 v1 v2 | normal | 1 color
```

The pad keeps every field's alignment: a `u16` starts on an even offset, a record on a multiple of 4. `size` is redundant (the tag gives it), which is what lets a validator catch a damaged tag.

**Flags.** Bit 0 **double-sided** (draw from both sides: wings, fins), bit 1 **semi-transparent** (the canopy), bit 2 **unlit** (colors are final; for the lighting stretch goal). Other bits are 0.

### 5.3 Walking the list

Records have different sizes, so there is no `prims[i]`. You keep a pointer and advance it by the record's own size:

```
 rec = file + prims_offset
 repeat prim_count times:
     tag  = rec[0]
     size = table[tag]                 <- also stored at rec[2..3]; they must agree
     ...use the record...
     rec += size                       <- the walk
 after the loop: rec must equal file + file_size
```

Walk by `size`, never by `sizeof` a struct: no single C struct has the layout of all eight record types. You decode each record, one byte at a time, into a convenient struct, `ShpPrim`, so the file layout lives in exactly one function, `shp_decode`. `ShpPrim` is 40 bytes; add that to `rec` instead of the record's size and the second record is already garbage.

### 5.4 Validating before trusting

A `.SHP` comes from a disc, a pack or a modder. Every number in it is an input, and "the file is fine" is a hypothesis. Prove each read is inside the file **before** doing it, in this order:

| Level | Question | Typical bug if skipped |
|---|---|---|
| Alignment, magic | Is the image 4-aligned, at least 4 bytes, `SHP1`? | reading a header from a wrong file |
| Header | At least 0x40 bytes? `file_size` equals the size you were given? Offsets consistent with counts (`normals_offset = 0x40 + 8 * vertex_count`, ...)? `prims_offset + prims_size == size`? | counts that run past the file |
| Walk | At least 4 bytes left? tag below 8? `size` field equals the tag's size? the whole record fits? exactly `prim_count` records and **no bytes left over**? | a damaged tag sending the walk into the weeds |
| Indices | every vertex index below `vertex_count`, every normal index below `normal_count` | a wild read through `screen_xy[]` |
| Textures | every textured record's texture index below `texture_count` (and, in `main.c`, `texture_count` not above the TPK's count) | sampling a texture that was never uploaded |

Mind the arithmetic. `prims_offset + prims_size <= size` looks right, but with `prims_size = 0xFFFFFFF0` the sum wraps to a small number and passes. Prove `prims_offset <= size`, then compare `prims_size == size - prims_offset`. A product such as `count * 8` can wrap too: here the counts are `u16`, so 32-bit math is safe, but check that for every format you parse. Also validate against **your own limits**: the program's `screen_xy[]` holds 256 vertices, so a file with 257 is rejected even if it is well formed.

### 5.5 `sizeof`: variable or type?

`sizeof` is computed from a *type* at compile time. Given `POLY_F4 *p`:

| Expression | Value | Meaning |
|---|---|---|
| `sizeof(POLY_F4)` | 24 | the packet |
| `sizeof(*p)` | 24 | the packet (type of the thing `p` points to) |
| `sizeof(p)` | **4** | the pointer itself |
| `sizeof(rec)` for `const uint8_t *rec` | **4** | never the record's size |

`ot_alloc(sizeof(p))` hands you 4 bytes; the next primitive overwrites everything after this one's first word, and the picture is garbage, with no crash. An array *parameter* decays to a pointer too: `void f(int a[8])` has `sizeof(a) == 4`. Prefer `sizeof(*p)` or the type. And remember this chapter's third size, the **file record size** (16 to 44, from the format), which is neither.

### 5.6 From texture id to tpage, CLUT and UV

A textured record says "texture 1, UV (63, 0)". The GPU needs a **texture page** word, a **CLUT** word, and UVs *inside the page*. Chapter 31's store already knows where each TIM was uploaded, so `store.tex[1]` holds all of them as `tpage`, `clut`, `u`, `v` (Appendix E.3.4):

```
 TSB (tpage word)                              CBA (CLUT word)
  bit 8..7  6..5  4      3..0                   bit 14..6      5..0
  +--------+-----+-----+----------+            +-------------+------------+
  |   tp   | abr | y/256|  x/64   |            |   clut_y    | clut_x/16  |
  +--------+-----+-----+----------+            +-------------+------------+
  tp: 0 = 4 bpp, 1 = 8, 2 = 16     abr: blend mode (0 here: opaque)
```

A texture does not start at the corner of its page, so the file's **texture-local** UV (measured from the texture's own top-left) is shifted by the texture's origin: `u = u_local + u0`, `v = v_local + v0`, where `(u0, v0) = ((x mod 64) * m, y mod 256)` and `m` = 4, 2, 1 for 4, 8, 16 bpp.

Worked numbers, `SHIP.TPK`'s `hull_b` (4 bpp, image at VRAM (656, 0), CLUT at (0, 481)):

| Value | Arithmetic | Result |
|---|---|---|
| `TSB` | `656/64 = 10`, `0/256 = 0`, `abr 0`, `tp 0` | `0x000A` |
| `CBA` | `0/16 = 0`, `481 << 6` | `0x7840` |
| `(u0, v0)` | `((656 mod 64) * 4, 0) = (16 * 4, 0)` | `(64, 0)` |
| UV `(63, 0)` | `(63 + 64, 0 + 0)` | `(127, 0)` |

The three ship textures sit side by side in one page (`u0` = 0, 64, 128), so they have the same TSB and three CBAs. The verifier's second disc puts them in different pages and makes one 8 bpp: any constant you hard-code is wrong there. You do **not** recompute these values from VRAM coordinates (the store did); you apply them.

### 5.7 Normals and lighting

Each record names a **face normal** (4.12, pointing out of the solid). The normals are precomputed so that lighting never needs a cross product at run time. The project draws the record colors as stored; lighting is a stretch goal (7.6): rotate the normal with the object matrix (`gte_rtv0`), dot it with a light direction, scale the color. The `unlit` flag marks colors that must not be scaled. Back-face culling does **not** use the normal: it uses `NCLIP` on the projected vertices, which is exact for the view actually drawn, as in Chapter 29.

### 5.8 The flat fallback

Textures need a working loader, a CLUT, correct UVs and the right page. When a model looks wrong, you first want to know whether the *geometry* is wrong. So `render_mode 0` draws every record **without** its texture: flat and Gouraud records as themselves, textured records as the untextured type of the same shape.

| Record | `render_mode 0` | `render_mode 1` |
|---|---|---|
| `F3 F4 G3 G4` | itself | itself |
| `FT3`, `FT4` | `F3`, `F4`, color = the record's color (the neutral 128: mid-gray) | itself, textured |
| `GT3`, `GT4` | `G3`, `G4`, the record's colors | itself, textured |

A textured packet differs from its fallback only in size, command byte and the UV, `tpage` and `clut` fields.

## 6. Worked example

[`example/shpdump.py`](example/shpdump.py) is a host-only program that walks `SHIP.SHP` with `struct` only: it prints the header, then one line per record with its offset, type, size and vertex indices, and asserts the invariants of 5.4. `python example/shpdump.py` dumps the ship; pass any `.SHP` path to dump another. Read the offsets column: `+0x0288` (a 32-byte `GT3`), `+0x02A8` (a 24-byte `G3`), `+0x02C0`. Each is the previous offset plus the previous size, nothing else. Records 2 and 3 are a `G3` and a `GT3`: predict the offset of record 4 before you run it.

## 7. Project: "The Ship, Textured"

### 7.1 Behavior

`make` in `starter/` builds a disc with `\DATA\SHIP.SHP;1` (the model) and `\DATA\SHIP.TPK;1` (its three textures), generated by `tools/assets/mkassets.py` into `build/assets/`. The program loads the pack (Chapter 31's loader, **given**), loads and parses the model with **your** parser, and draws the ship turning slowly about Y. If loading fails, the screen is red.

### 7.2 The contract

`starter/` builds and boots, but the parser is a stub (red screen) and the drawing is empty. **Given:** `CMakeLists.txt`, `iso.xml`, `cdrom.c`, `tim.c`, `tpk.c` (Chapters 29 to 31, finished), `psxe/`, `shp.h` (**the contract: read it first**: types, codes, check order), and `main.c`'s loading, matrix, transform and frame loop. **You write:** the five functions of `shp.c` and `draw_shp()` in `main.c`.

| Function | Contract (details in `shp.h`) |
|---|---|
| `shp_record_size(type)` | 16 20 24 32 24 32 32 44; 0 for a tag above 7 |
| `shp_decode(rec, ShpPrim *)` | fill the struct from the record, one byte at a time; return the record's size |
| `shp_parse(data, size, Shp *)` | validate in the order of 5.4, fill `Shp` (pointers **into** `data`, `counts[8]` by tag) |
| `shp_packet_size(type, textured)` | `sizeof(POLY_xx)` of the packet `shp_fill` builds (without a texture a textured type becomes its flat/Gouraud twin) |
| `shp_fill(pkt, ShpPrim *, sxy, Tex *)` | the per-type builder: command byte and length, colors, XY from `sxy`, and for a texture the UV + origin, `tpage`, `clut`; semi-transparency bit; **not linked** |

**Error codes of `shp_parse`**, in check order (the first failing check wins):

| Code | Name | Condition |
|---|---|---|
| -2 | `ALIGN` | `data` not a multiple of 4 |
| -3 | `MAGIC` | `size < 4` or no `SHP1` |
| -4 | `HEADER` | `size < 0x40`; `file_size != size`; `vertex_count` 0 or above 256; `prim_count` 0; `texture_count` above 255; the three offsets and `prims_size` not exactly as 5.1 gives |
| -5 | `PRIM` | during the walk: fewer than 4 bytes left; tag above 7; `size` field not the tag's size; record does not fit; after `prim_count` records, bytes left over |
| -6 | `INDEX` | vertex index `>= vertex_count` or normal index `>= normal_count` |
| -7 | `TEXTURE` | textured record with texture index `>= texture_count` |

(`-1` read failure and `-8` "model needs more textures than the pack holds" come from `main.c`.)

**The scene** (the program owns it; the verifier freezes it by writing these `int32` symbols):

| Item | Rule |
|---|---|
| Pose | `RotMatrix` of `{angle_x, angle_y, angle_z}` (4096 = one turn), `TransMatrix` by `(0, 0, cam_z)`; `cam_z = 1000`, `proj_h = 360`, offset `(160, 120)` |
| Motion | defaults `angle_x = 160`, `angle_y = 0`, `spin_step = 8`; after each frame `angle_y = (angle_y + spin_step) & 4095`. The verifier sets `spin_step = 0` |
| Vertices | every vertex through `RTPS` into `screen_xy[i]` (x low 16 bits, y high) and `screen_z[i]` |
| Culling | `area` = `NCLIP` of vertices 0, 1, 2 as stored. Draw when `area > 0`; a **double-sided** record is also drawn when `area < 0`; `area == 0` never |
| OT slot | `OTZ` from `AVSZ3` (triangles) or `AVSZ4` (quads) of the vertices' `screen_z`; slot = `OTZ >> 3`, Chapter 29's shift (`ot_add` clamps) |
| Mode | `render_mode` 0 = flat fallback, 1 = textured (table in 5.8) |
| Colors | as stored; no lighting |
| Semi-transparency | flag bit 1 sets the primitive's semi-transparency bit (any kind) |
| Count | `prims_submitted` = packets linked this frame; if `ot_alloc` returns NULL stop drawing |

**State the verifier reads** (names, types, order are fixed; `main()` keeps them linked):

| Symbol | Meaning |
|---|---|
| `shp_info` | `{ int32 prim_counts[8] (F3 F4 G3 G4 FT3 FT4 GT3 GT4); vertex_count; normal_count; prim_count; texture_count; char name[16] }`, from the parsed file (given code copies `Shp` into it) |
| `shp`, `store` | the parsed model and Chapter 31's texture store |
| `load_status`, `tpk_status`, `shp_status` | 0 = loaded; 100 = `CdInit` failed; 1 = pack failed (code in `tpk_status`); 2 = model failed (code in `shp_status`) |
| `render_mode`, `angle_x/y/z`, `spin_step`, `cam_z`, `proj_h` | the scene above |
| `mtx`, `screen_xy`, `screen_z` | what the GTE was given and returned |
| `prims_submitted`, `frame_no`, `frame_done()` | packets linked; frames completed; the marker the probe waits at |

### 7.3 Steps

1. Run `make` in `starter/`, then `python ../example/shpdump.py` to see what the parser must find.
2. `shp_record_size` and `shp_decode`. Check `shp_decode` against the dump by hand for one `F3` and one `GT4`.
3. `shp_parse`, level by level (5.4). When it accepts the ship, `load_status` becomes 0 and the red screen goes away.
4. `shp_packet_size` and `shp_fill`, **untextured kinds first** (`F3 F4 G3 G4`).
5. `draw_shp()`: decode, cull, slot, allocate, fill, link. Set `render_mode = 0` as its initial value and run: the ship appears flat-shaded. Textured records are drawn as their flat twins (the table in 5.8).
6. Textured kinds in `shp_fill`: UV + origin, `tpage`, `clut`. Pass `&store.tex[p.tex]` in `draw_shp()` for `render_mode 1`. Set `render_mode` back to 1. Run `verify.sh`.

### 7.4 Rules

- Never read a byte of the file before the checks so far prove it is inside the file. Read multi-byte fields byte by byte.
- Advance by the record's size, never by `sizeof` anything.
- Do not hard-code counts, texture ids, TSB or CBA values, or the ship's name: the verifier boots a second disc with another ship and other texture places.
- Textured primitives come from `store.tex[]`; do not recompute VRAM positions.

### 7.5 Hints

- `ShpPrim` has room for four of everything; for a triangle the fourth entry is unused. Compute `nverts`, `textured`, `gouraud` from the tag once.
- Field offsets: indices at +4; normal at `+4 + 2 * nverts`; add 2 for the quad pad; UVs follow; then the texture index (+2 pad for a textured quad); then colors.
- Fixed-size record tables beat `switch` ladders for the *size*; a `switch` is natural for the *packet*.
- `setUV3/4` store bytes: add the texture's origin to the local UV first. The sum fits in 0..255 for the shipped files.
- `sxy[i] >> 16` is the signed y; `(int16_t) sxy[i]` is the signed x. Off-screen vertices are negative.

### 7.6 Stretch goals

- Light the ship: one directional light in view space; rotate each record's normal, dot it with the light, scale `F`/`G` colors (skip `unlit` records). Gouraud records would need per-vertex normals: what would you add to the format?
- A second model: `shpgen.py pylon` with `PROPS.TPK`, drawn beside the ship.
- Sort the packets better: a separate pass for double-sided records, or the farthest vertex's `z` for the slot.
- Count what the walk costs in cycles and see where it goes.

## 8. Verification

```sh
source tools/env.sh
parts/part-06-assets-cdrom-textures-and-compression/ch32-a-real-model-format-shp/verify/verify.sh            # your starter/
parts/part-06-assets-cdrom-textures-and-compression/ch32-a-real-model-format-shp/verify/verify.sh --solution # the reference
```

It takes about 30 seconds: a build, three emulator boots from disc (the real disc, a second disc, and a run that calls your functions directly) at about 400 frames each. The probe poses the ship by writing the symbols of 7.2 and records three poses in both render modes: the packets found by walking the ordering table, `screen_xy`, `screen_z`, `mtx`, and a screenshot. Python derives what **should** be there from the `.SHP` itself (and the generator's manifest) and compares.

| Check | What it means | If it fails |
|---|---|---|
| `the state symbols ...`, `the disc image ...`, `the model is not inside the program` | The labels exist; both files are on the disc; the model is read at run time | Removed declaration; edited `iso.xml` |
| `boots from the disc; shp_info ...` | `load_status` 0; `shp_info` counts per type, vertices, normals, name equal the manifest; the store holds the TPK's textures (tpage, clut, u, v, w, h) | The message shows the first different count: tag dispatch or the walk's stride is wrong |
| `alt disc ...` | The same on another ship (other counts, 49 vertices, no canopy, two more `GT4`) with the textures elsewhere in VRAM (one 8 bpp) | Hard-coded counts, ids or page numbers |
| `pose and projection` | `mtx` is `RotMatrix` of the angles plus `(0, 0, cam_z)`; `screen_xy/z` follow a float projection of the file's vertices | A wrong vertex list pointer or stride |
| `the packets ...` | For every record: the packet kind, colors, absolute UVs, `tpage`, `clut`, semi-transparency bit, the culling rule and the OT slot, as a multiset equal to the expected one, both modes, three poses | Culling sign; missing double-sided; flat colors; UV origin; slot rule |
| `textured primitives carry the manifest's TSB and CBA` | Each textured packet's `(tpage, clut)` is one the manifest lists | Swapped words; the wrong texture's data |
| `pictures ...` (main, alt) | The picture's silhouette equals the projected polygons'; at the top-most polygons' centroids the picture has the packet's color or the TIM's texel; textures really show | Packets right but VRAM or CLUT wrong |
| `perceptual hash ...` | dHash (16 x 16 cells, 256 bits) of each of the six screenshots within 14 bits of a reference render of the book's solution (`verify/ref/*.png`) | A wrong pose, a missing class of polygons |
| `shp_parse: the shipped files ...` | five good files (ship, alternate, pylon, arch, tower): every `Shp` field | Pointers must point into the image |
| `shp_parse: every damaged file ...` | 44 crafted files: bad magic, short, misaligned, lying header, `prims_size` overflow, 257 vertices, no primitives, wrong `prim_count`, bad tag, wrong record size, cut-off record, indices and texture index out of range, error priority | A missing check or a code that differs from 7.2 |
| `shp_decode`, `shp_record_size`, `shp_packet_size`, `shp_fill` | Every record of both ships decoded; all eight builders with and without a texture, with negative coordinates and guard bytes around the packet | A field in the wrong place; a write past the packet |

A pass ends with `CHAPTER 32: PASSED (17/17 checks)`. The untouched starter fails. Ignoring the type tags, a 40-byte `GT4` stride, swapped TSB and CBA, hard-coded counts, drawing textured records untextured in render mode 1, and forgetting the UV origin each fail at least one check.

**The hash tolerance.** The tolerance (14 of 256 bits) was measured on the solution: other valid draw orders (an OT shift of 2, 4 or 5) move the hash by 0 to 2 bits and a 3-pixel shift of the picture by up to 12, while a different pose is at least 32 bits away. A hash cannot tell flat from textured (they differ by 1 to 6 bits), which is why the structural checks above exist. If a future PCSX-Redux renders the ship differently, regenerate the PNGs with `SHP_UPDATE_REFS=1 verify.sh --solution` (only ever on the reference solution).

## 9. Common pitfalls

- **`sizeof(p)` for a pointer** (5.5): a 4-byte allocation, garbage on screen, no crash.
- **Walking by a struct or packet size.** `ShpPrim` is 40 bytes and a `POLY_GT4` 52; a record is 16 to 44. With the wrong stride the walk drifts and every later record is garbage.
- **Casting the file to a struct.** The file's layout (with its pads) is not a C struct's, and `u16` reads at odd addresses fault on the R3000.
- **`prims_offset + prims_size <= size`** wraps in 32 bits (5.4).
- **Checking indices after using them.** `screen_xy[v]` with `v` from the file is a wild read.
- **Reordering quads.** `v0 v1 v2 v3` goes to the GPU as stored.
- **Absolute vs local UV.** Forgetting to add the texture's `(u0, v0)` samples from the corner of the page, so every polygon shows the texture stored there; adding it twice samples the wrong place too.
- **Swapping `tpage` and `clut`.** Both are 16-bit words and compile in either place; the picture has a wrong palette or is garbage.
- **Culling a double-sided wing from behind.** It disappears when you turn the ship over.
- **Treating `FT` colors as colors.** In a textured record `128` means "unchanged", not gray. In the flat fallback it becomes gray on purpose.
- **Forgetting `setSemiTrans`** for the canopy: it renders opaque.
- **Packet budget.** The per-frame packet buffer (`PRIM_BUF_SIZE`, 2,048 bytes) must hold the worst frame: the whole ship, every record visible, needs 1,016 bytes. Stop drawing when `ot_alloc` returns NULL.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- psx-spx (nocash PSX specs): "GPU Render Polygon Commands" (polygon packets and their command bytes), "GPU Rendering Attributes" (the texpage and CLUT words).
- PSn00bSDK `psxgpu.h`: `POLY_F3` ... `POLY_GT4`, `setPolyXX`, `setUV3/4`, `getTPage`, `getClut`.
- [Appendix E.3.4 and E.8](../../../appendices/E-file-formats.md); `tools/assets/shpgen.py` (the generator and its manifest) and `formats.py` (`parse_shp`, the reference parser).
- Next: Part VII. Chapter 33 loads many `.SHP`/`.TPK` pairs into a scene of linked objects, with the parser you wrote here.
