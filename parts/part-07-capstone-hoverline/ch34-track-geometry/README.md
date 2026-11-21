# Chapter 34: Track Geometry

## 1. Concept

A race track is a **ring of sections**. Each section is five quads between two **rings** of six vertices, and neighbouring sections *share* their ring. The track is wider than the 16-bit range of the GTE's vertex input, and the format allows any `s32` world, so every vertex is made **camera-relative in 32-bit C** before the GTE sees it. This chapter loads `TRACK.TRK`, validates it, and draws the whole track as flat-coloured quads (colour by face flag) with a wireframe overlay you can switch on.

## 2. Why it matters

The track is the biggest piece of data in *Hoverline*: 672 vertices, 560 faces, 112 sections. Everything later reads it: textures (Ch 35), subdivision (36), the ship's start line (37), the visibility window (38), collision edges and boost pads (40, 41). Getting the file layout, the checks on untrusted data, and the world-scale arithmetic right here saves every later chapter. It is also where "the world is bigger than the hardware" stops being a footnote.

## 3. Learning objectives

After this chapter you can:

- describe a track as sections, rings and shared vertices, and say how a face finds its four corners through the vertex table;
- parse `.TRK` **in place** with bounds validation: header counts against file size, every index against its table, with distinct error codes in a fixed order;
- say exactly where the GTE's 16-bit limits are (the vertex input and the view-space outputs, not the 32-bit translation), why loading absolute vertices only works for a world that fits `s16` around the origin, and use the recipe: rotation-only `RT`, `TR = 0`, `d = vertex - eye` in 32 bits, skip a vertex when any `|d|` exceeds 32767;
- run each face through the cull rules (far, near plane, back face, size, buffer) and count where it went;
- colour faces from their flags and draw a closed outline with one GPU polyline packet;
- size the primitive buffer for a worst case and say honestly what drawing the whole track costs.

## 4. Prerequisites

[Chapter 33](../ch33-game-architecture-objects-scenes-and-input/README.md) (the program this chapter extends: states, camera, `cam_eye`, camera-relative placement), [Chapters 25 to 27](../../part-05-three-dimensions-with-the-gte/README.md) (GTE macros, `NCLIP`, `AVSZ4`, ordering-table slots), [Chapter 28](../../part-05-three-dimensions-with-the-gte/ch28-the-camera/README.md) (the camera, **given**), [Chapter 29](../../part-06-assets-cdrom-textures-and-compression/ch29-the-cd-rom-and-loading-files/README.md) and [Chapter 32](../../part-06-assets-cdrom-textures-and-compression/ch32-a-real-model-format-shp/README.md) (loading a file, validating a parser's input), and [Appendix E.10](../../../appendices/E-file-formats.md) (`.TRK`).

## 5. Explanation

### 5.1 Sections, rings, shared vertices

A **ring** is one cross-section of the road: six vertices. A **section** is the road between two rings: five quads. The next section starts at the ring the last one ended on, so each ring's vertices are stored **once** and used by two sections (that is *index sharing*).

```
 ring cross-section, looking along the direction of travel (E.10.2)

   0 LT                                      5 RT          LT/RT: top of the walls (250 up)
    |                                         |            L, CL, CR, R: the road, three 400-wide lanes
    | wall      CL----lane----CR       wall   |
    1 L ----lane---- 2 ------ 3 ----lane---- 4 R
          face 1       face 2     face 3
    face 0 = left wall (ring vertices 0,1)       face 4 = right wall (4,5)
```

```
   ring r            ring r+1          Section r has 5 quads between ring r and ring r+1:
  6r .. 6r+5       6r+6 .. 6r+11       faces 5r .. 5r+4
     0 ---------------- 0'
     1 ---[ face 1 ]--- 1'             Section r+1 reuses ring r+1 as ITS start.
     2 ---[ face 2 ]--- 2'             The last section ends on ring 0 (the track is a loop).
     3 ---[ face 3 ]--- 3'
     4 ---------------- 4'
```

Track 1 has 112 sections, so 112 rings x 6 = **672 vertices** and 112 x 5 = **560 faces**. The ring is banked (rolled) in bends, up to about 26 degrees, so a ring is not always horizontal. That ring layout belongs to the *generated* tracks; the **format** only promises what its tables say, so the program must go through the tables, not through `6 * r + k` arithmetic.

### 5.2 Three tables that point at each other

```
 header (0x60 bytes): counts, offsets
   |
   +--> vertex table  (12 bytes each)  s32 x, y, z       <----------+
   +--> face table    (24 bytes each)  v[4] indices ------------------+   Z order (see 5.6)
   |                                   flags, tex, uv[8], color[4]
   +--> section table (64 bytes each)  first_face, face_count ----> the faces of this section
   |                                   next, prev, edges[4] -------> vertex indices (road edges)
   +--> visibility list (u16 each)     section indices (Chapter 38)
```

Everything is little-endian, which is also how the R3000 stores `int`. Face `v[]` indices and section `edges[]` index the **vertex** table; section `first_face` and `face_count` index the **face** table; `next`/`prev` index the **section** table. Every one of these is a number read from a file, so every one is checked before it is used (5.4).

| Flag | Bit | Meaning |
|---|---|---|
| `FLOOR` | 0 | a drivable lane quad |
| `WALL` | 1 | a side wall facing the road |
| `BOOST` | 2 | the centre lane of a boost section (always with `FLOOR`) |
| `START` | 3 | the start line, three lane quads of the start section (with `FLOOR`) |
| `FLIP_H` | 4 | mirrored texture: Chapter 35, ignored here |

### 5.3 Reading it in place

The file is read into one buffer with `cd_load_file` (Chapter 29: a `malloc`ed, 4-byte aligned buffer). Instead of copying 560 faces into new structs, the parser fills a small `Track` with **pointers into that buffer**: `vertices = image + 0x60`, `faces = vertices + 12 * vertex_count`, and so on. The buffer then has to stay allocated for as long as the track is used (`main.c` does not free it). `TrkVertex`, `TrkFace` and `TrkSection` in `track.h` are laid out exactly like the file's records (a `_Static_assert` checks the sizes 12, 24, 64), so `&track.faces[i]` *is* face `i`.

Two consequences. The image must be 4-byte aligned (a `u32` read from an odd address raises a CPU exception on the R3000), which is the first thing `track_parse` checks. And a **header field is read with byte-wise helpers** (`rd16`, `rd32`), which is safe at any address, while the tables are read through the struct pointers after the alignment is proven.

### 5.4 Validating: nothing is trusted until it is checked

A damaged file must give an error code, never a crash or a wild pointer. `track_parse` checks in a **fixed order** and returns at the first failure:

| Code | Name | What is wrong |
|---|---|---|
| -2 | `TRK_ERR_ALIGN` | the image address is not a multiple of 4 |
| -3 | `TRK_ERR_MAGIC` | fewer than 4 bytes, or not `TRK1` |
| -4 | `TRK_ERR_HEADER` | shorter than 0x60; `file_size != size`; a section, vertex or face count of 0, or any count (visibility included) above the program's limit; `start_section >= section_count`; an offset not equal to `0x60`, `+12*vertices`, `+24*faces`, `+64*sections`; or the total size not equal to `vis_offset` + the visibility list padded to 4 |
| -5 | `TRK_ERR_VERTEX` | a coordinate outside +-1,000,000 |
| -6 | `TRK_ERR_FACE` | a vertex index >= `vertex_count`; a flag bit outside the five; neither `FLOOR` nor `WALL`; `BOOST` or `START` without `FLOOR`; `tex` >= `texture_count` and not `0xFF` |
| -7 | `TRK_ERR_SECTION` | `next` or `prev` >= `section_count`; `first_face + face_count` past the face table; an `edges[]` entry >= `vertex_count`; an unknown section flag; `vis_first + vis_count` past the visibility list |
| -8 | `TRK_ERR_VIS` | a visibility entry >= `section_count` |

`-1` (`TRK_ERR_READ`) is not a parser code: `main.c` stores it in `track_status` when `cd_load_file` fails, as Chapter 33 does for the scene. Within each table the records are walked in order and each record's fields are checked in the order listed (`track.h` spells it out).

Three habits. **Counts first, then the sums**: the offsets and sizes are computed from counts that are already bounded, in 32 bits, so they cannot wrap. **Widen before adding**: `first_face + face_count` of two `u16` values must be done in 32 bits (`0xFFFF + 2` wraps to 1 in 16 bits and would pass). **Fail clean**: on any failure `*out` is all zero and the input is untouched. The limits (160 sections, 1024 vertices, 1024 faces, 8192 visibility entries, coordinates +-1,000,000) are the *program's*, not the format's; they size the arrays of 5.7 and keep `vertex - eye` inside `s32`.

### 5.5 World scale and the GTE's 16 bits

`RTPS` computes, per axis, `MAC = TR * 4096 + RT * V` in 44 bits and shifts it right by 12; then it saturates the view-space result to 16 bits (`IR1..IR3` to -32768..32767, the depth `SZ` to 0..65535). So the 16-bit places are the **input** vertex `V` (`VXY0`, `VZ0` are `s16`) and the view-space **outputs**. The translation `TR` is 32-bit. The track's vertices are `s32` because the format must allow worlds of any size. How big are the tracks really?

| | track 1 | track 2 | the verifier's second disc (track 2 + (60000, 0, 45000)) |
|---|---|---|---|
| x | -22,416 .. 24,474 | -18,416 .. 19,986 | 41,584 .. 79,986 |
| z | -13,353 .. 12,448 | -18,230 .. 14,377 | 26,770 .. 59,377 |
| every coordinate fits `s16` | yes | yes | no (every x and z is above 32,767) |
| widest extent | 46,890 (x) | 38,402 (x) | 38,402 (x) |

The shipped tracks fit 16 bits coordinate by coordinate, but the *distance between* two points does not (46,890 > 32,767), and the format promises neither (the book's limit is +-1,000,000 per axis). What the GTE needs is a **small input**: the vertex relative to the camera.

```
   vertex v (s32)      eye E (s32)
          \             /
           d = v - E             32-bit C, any size
                |
                v     any |d.x|, |d.y|, |d.z| > 32767 ?   yes -> the vertex is FAR: do not load it
        SVECTOR rel = (s16) d
                |
                v
   RT = rotation part of view_mtx      <- t is NOT used
   TR = 0
                |
              RTPS -> screen x, y (SXY) and view depth (SZ)
```

Per frame, for the whole track: load the **rotation** of `view_mtx` into `RT` with the translation set to 0 (copy `view_mtx`, zero its `t`), and then for each vertex subtract, test, load, `RTPS`.

**Why not put the camera in `TR`?** It is the obvious alternative: load all of `view_mtx` (so `TR = view_mtx.t = -R * eye`) and the absolute vertex. The GTE then forms `R * v + t = R * (v - eye)` itself, in 44 bits, so the large translation is not the problem. The input is: the absolute vertex must be narrowed to `s16` for `VXY0`/`VZ0`. On the shipped tracks every coordinate fits, so the shortcut draws a correct picture, give or take one unit of depth from the rounding of `t` (it even draws some faces the recipe skips as far); the verifier's bit-exact projection check still tells the two apart. Move the same track by (+60000, 0, +45000), as the verifier's second disc does, and every x and z wraps when it is narrowed (41,584 becomes -23,952): the picture is garbage however close the camera is. The recipe's input is `d`, which is small wherever the world is; its only cost is that `d` itself must fit, and that is what "far" means.

**What "far" means.** A vertex whose `d` has a component above 32767 in magnitude cannot be loaded. The rule (Appendix E.10.2) is to **skip every face that uses it**; the alternative is to clamp `d` and accept distorted far faces. Clamping draws wrong shapes, skipping draws nothing; the book skips. A far face is more than 32,767 units (about 32 sections) away; a 1,000-unit quad that far is about 10 pixels wide at `proj_h` = 320, so little is lost.

**Precision.** The view rotation is 4.12: each product is exact, and `RTPS` shifts the sum right by 12. The view-space saturation of `IR1..IR3` (-32768..32767) can bite even with a valid `d`: with `|d|` up to 32767 on each axis a vertex can have `|x_view|` above that. Such a vertex is never on the screen, though: with `proj_h` = 320 and a half-screen of 160, `sx` is within the screen only if `z >= 2 |x|`, so `z` would have to exceed 65,534 while `|d|` is at most 56,755. The GTE also saturates the *screen* position to -1024..1023. Neither saturation moves a vertex that is on the screen; both can bend a face that reaches far past the edge (Chapter 36 subdivides such faces). The verifier models both exactly.

### 5.6 What happens to a face

For each face of the drawn sections (`faces_seen`), the tests run in this order and the face ends in **exactly one** of the six buckets, so they sum to `faces_seen`; `wire_prims` counts outlines, not faces:

```
 classify all 4 vertices (each vertex: once per frame)
   any vertex FAR ?                       -> faces_far
   any view z (SZ) < 128 ?                -> faces_near     behind the eye, or too close to project
   NCLIP area of v0 v1 v2 <= 0 ?          -> faces_back     facing away (or edge-on)
   box wider than 1023 or taller than 511 -> faces_big      the GPU would drop it (Chapter 36 fixes this)
   buffer full ?                          -> faces_dropped
   else                                   -> faces_drawn    POLY_F4 (+ outline in wire mode)
```

All four vertices are classified **before** the first test, so the per-vertex state is the same however the face ends. Vertices are shared, so a vertex is subtracted and projected **once per frame** and its result is reused by the (up to four) faces around it: this is what the shared ring buys you. `trk_vstate[i]` records `VS_UNSEEN`, `VS_OK` or `VS_FAR`. The verifier checks the stored results (`trk_rel`, `trk_sxy`, `trk_sz`, `trk_vstate`), not how often you ran `RTPS`: projecting a vertex again for each face, or three at a time with `RTPT`, gives the same numbers.

**Vertex order.** Faces list their corners in **Z order**: `v0 v1` is one edge, `v2 v3` the opposite edge, so the outline of the quad is `v0 -> v1 -> v3 -> v2`. A `POLY_F4` takes the corners in exactly this order. `NCLIP` on `v0 v1 v2` is positive when the face is turned towards you (the generator already ordered each face to face the road).

**Colour legend** (a GPU word is `r | g << 8 | b << 16`; `track_colour(flags)`):

| Face | Test (in this order) | RGB | |
|---|---|---|---|
| start line | `START` | (240, 240, 240) | white |
| boost pad | `BOOST` | (0, 200, 255) | cyan |
| wall | `WALL` | (40, 60, 120) | blue |
| lane | `FLOOR` | (70, 72, 80) | grey |
| none of the four | | (255, 0, 255) | magenta |
| wireframe | | (255, 255, 0) | yellow |

The generated tracks store the same values in each face's `color[]` field, and Appendix E.10.3 mentions it. This chapter takes the colour from the **flags** anyway: flags are the face's meaning, the colour field is a convenience a tool may fill wrongly (the verifier's second disc zeroes it).

### 5.7 Packets and the budget

A flat quad is a `POLY_F4`, **24 bytes**: tag, colour + command `0x28`, four `xy` words (Chapter 14). Its ordering-table slot is `AVSZ4` of the four `SZ` values `>> 7` (`OTZ_SHIFT`, as in Chapter 33), clamped to 0..63 by `ot_add`.

| Worst case | Bytes |
|---|---|
| 560 faces x `POLY_F4` | 13,440 |
| + 560 outlines x 32 (5.8) | 31,360 |
| `psxe` before this chapter | **2,048** |

The Chapter 21 library gives each frame 2,048 bytes of primitives: 85 quads. This chapter's copy of `psxe/include/psxe/ot.h` sets `PRIM_BUF_SIZE` to **32,768** (two frames = 64 KB of the 2 MB RAM). When the buffer is full anyway, `ot_alloc` returns `NULL`: count the face in `faces_dropped` and `prims_dropped` and allocate nothing more this frame; never write past it (guard bytes behind each buffer must stay `0xA5`).

**What the whole track costs.** The harness counted the R3000 cycles inside `track_draw` for the 20 main-disc poses on the reference solution: **174,000 to 454,000, mean 325,000**, against the 566,120 cycles between two NTSC vertical blanks: **about 57 percent** of one frame for the drawing alone, 64 percent in the two poses with the outline. In PCSX-Redux the loop still holds one frame (the GPU is not timed); a real console also spends time filling pixels. What matters is what the time buys: at the start line **187** of 560 faces are far, **173** behind the eye, **39** back-facing, **2** too big, **159** drawn. About **72 percent of the faces are rejected**, and there will still be a ship, physics and collision to fit. Chapter 38 draws only a window of sections around the ship; this chapter deliberately draws all of them, so that you see why.

### 5.8 The wireframe overlay

One closed outline per face is one GPU **polyline**: command `0x48` (flat, no transparency), then a vertex word per point, ended by the **terminator word `0x55555555`**. Five points close a quad:

```
 word 0   tag (link, length = 7 words)           the next 7 words after the tag:
 word 1   0x48 | b g r                           command and yellow
 word 2   xy  v0
 word 3   xy  v1
 word 4   xy  v3          v0 -> v1 -> v3 -> v2 -> v0  (Z order, back to the first corner)
 word 5   xy  v2
 word 6   xy  v0
 word 7   0x55555555      terminator
```

The SDK has `LINE_F4` (four points, three edges); a closed quad needs five, so the project defines its own 32-byte `LINE_P5` (given).

**Drawing order.** The outline must come after its fill or the fill hides it. `ot_add` puts the *newest* packet at the *front* of its slot, and the GPU walks a slot front to back, so **link the outline first, then the fill**. Both go in the same slot. In wire mode one `ot_alloc(24 + 32)` gives both packets, so a face is either drawn with its outline or dropped as a whole.

## 6. Worked example

[`example/trkdump.py`](example/trkdump.py) is a host-only dump of a `.TRK` with the far rule applied to an eye you choose:

```sh
python ../example/trkdump.py build/assets/TRACK.TRK --eye 24000 -1500 -2500    # from starter/, after make
```

It prints the header, the flag counts (336 floor, 224 wall, 4 boost, 3 start), the bounding box, and for that eye the number of far vertices (224 of 672) and of faces skipped (192 of 560). Move the eye to the other end of the track and watch the counts change.

## 7. Project: the whole track, outlined

### 7.1 Behaviour

The program boots from the disc: the title, then **Start** goes to the game as in Chapter 33. The game now shows **only the track** (the Chapter 33 scenery is still loaded, but not drawn: the track uses the frame's whole primitive budget). It is seen from the Chapter 33 start position, behind the start line, in a dark blue sky. The **fly camera** is unchanged: D-pad moves in world axes, R1/L1 down/up, R2/L2 turn. **Select** toggles the wireframe overlay (edge-triggered). **Start** returns to the title.

### 7.2 The contract

`starter/` is Chapter 33's `solution/` plus the new modules; it builds and boots, but `track_parse` rejects every file, so the game state shows a red screen (`load_status` 4). **Given:** everything of Chapter 33 including `main.c` (it loads `\DATA\TRACK.TRK;1` and calls your `track_parse`), `psxe/` with the larger buffer, the `LINE_P5` packet and `load_matrix`. **Read `track.h` and `track_render.h` first: they are the contract.** **You write:**

| File | Functions |
|---|---|
| `track.c` | `track_parse`, `track_vertex`, `track_face`, `track_section` |
| `track_render.c` | `track_colour`, `vertex_prepare`, `draw_face`, `track_draw` |
| `game.c` | the Select toggle in `game_update` |

**State the verifier reads** (names and types fixed; `main()` keeps them linked):

| Symbol | Meaning |
|---|---|
| `track` | the `Track` struct, 12 words: 4 table pointers, `section_count`, `vertex_count`, `face_count`, `vis_count`, `start_section`, `flags`, `texture_count`, `total_length` |
| `track_status`, `load_status` | what `track_parse` returned; 4 = the track failed |
| `wire_mode` | 0 or 1 |
| `track_stats` | 8 words: `faces_seen, far, near, back, big, dropped, drawn, wire_prims` of the last `track_draw` |
| `trk_rel[]`, `trk_vstate[]`, `trk_sxy[]`, `trk_sz[]` | per vertex: the camera-relative `SVECTOR`, `VS_UNSEEN/OK/FAR`, the projected xy (low 16 bits x, high 16 y), the view depth |
| `prims_submitted`, `prims_dropped` | packets linked (fills and outlines), faces dropped for lack of buffer |
| `cam_eye`, `cam_yaw`, `cam_min`, `cam_max`, `view_mtx` | the camera: **patchable** |
| `frame_no`, `frame_done()` | frames completed; the probe's marker |

### 7.3 Steps

1. `make` in `starter/` and boot it: red screen. Run `trkdump.py`.
2. `track_parse` in `track.c`, in the order of `track.h`, then the three accessors. `load_status` becomes 0 and the red screen is replaced by the dark blue sky.
3. `track_colour`.
4. `vertex_prepare`: subtract, test, load, `RTPS`, store. Look at `trk_rel` and `trk_sxy` of one vertex in the PCSX-Redux memory view to see the camera-relative numbers.
5. `draw_face`: the rules in order, with `POLY_F4`. The packet is the same as in Chapter 14, with corners `v0..v3` as stored.
6. `track_draw`: wrap and cut the window, load the **rotation** of `view_mtx` with `t = 0`, loop over the sections' faces.
7. Select toggles `wire_mode`; add the outline in `draw_face` (link it **before** the fill).
8. `verify.sh`.

### 7.4 Rules

- `d = vertex - eye` in `s32`, then to `s16`. Never `view_mtx.t`, never the absolute vertex.
- Skip a face when **any** of its four vertices is far; classify all four first.
- Nothing may depend on this track: no counts, no section numbers. The verifier boots a second disc with track 2 translated far from the origin, with zeroed colour fields.
- Colour comes from the flags, not from `color[]`.
- Never write past `ot_alloc`'s block.
- `input_pressed`, not `input_held`, for Select.

### 7.5 Hints

- Test `first_face + face_count` in 32 bits; compare indices with `<` against the *count*, as `int`.
- `vertex_prepare`: `trk_vstate[i] != VS_UNSEEN` means done; return the stored state.
- Load the GTE from `trk_rel[i]` itself. `gte_ldv0` reads memory through a pointer without telling the compiler (its `asm` has no `"memory"` clobber), so a local `SVECTOR` filled just before it may not have been stored yet; if you do use a local, put `__asm__ volatile("" ::: "memory");` between the stores and the load.
- `NCLIP`: `gte_ldsxy3`, `gte_nclip`, `gte_stopz` (Chapter 26/32 `render_shp` does the same).
- `gte_ldsz4`, `gte_avsz4`, `gte_stotz`, then `>> OTZ_SHIFT`.
- Set a `POLY_F4`'s corners by writing `trk_sxy[v]` straight into its `x0..` words.

### 7.6 Stretch goals

- Project three vertices at a time with `RTPT` (Chapter 27) and count the cycles saved.
- Clamp instead of skip: compare the picture from a far pose, and say what looks wrong.
- Colour the faces by section number to see the sections.
- Draw the section window `[s - 2, s + 8]` for a section `s` you choose: `track_draw(first, count)` already supports it.

## 8. Verification

```sh
source tools/env.sh
parts/part-07-capstone-hoverline/ch34-track-geometry/verify/verify.sh            # your starter/
parts/part-07-capstone-hoverline/ch34-track-geometry/verify/verify.sh --solution # the reference
```

About 35 seconds: a build, three emulator runs (the disc, a second disc, direct calls). The probe is driven by `frame_no`: it reads `track`, taps Start, holds Select, flies, then **poses the camera** (writing `cam_eye` and `cam_yaw`) at 20 (main disc) or 24 (second disc) places and records `track_stats`, the per-vertex arrays, the packets of the ordering table and a screenshot. Python derives everything from the generated `.TRK` in exact integers, **including the GTE's projection bit for bit**.

| Check | What it means | If it fails |
|---|---|---|
| `main disc: track_parse ...`, `alt disc: track 2 ...` | `Track` counts equal the manifest; tables point into the image; the alt disc has 104 sections | constants instead of header fields |
| `wireframe toggle`, `the fly camera` | one change in a 20-frame hold; back with a short press; the eye still moves | `held` instead of `pressed` |
| `... track_stats ...` (main and alt) | the 8 counters equal the rules at every pose | wrong order of the tests; vertices of a far face unclassified |
| `... camera-relative ...` (main and alt) | every `trk_rel` equals `vertex - eye`, within +-32767; `VS_FAR` exactly when some `|d| > 32767`; `trk_sxy`, `trk_sz` equal the exact RTPS | absolute vertices, `TR` used, `t` not zeroed |
| `boundaries` | a vertex at `|d| = 32767` is kept and at 32768 is far, on every axis, both signs | `>=` for `>`; clamping |
| `... packets ...` | the ordering table holds exactly the expected `POLY_F4` / polyline packets: colour, corners, slot; an outline after its fill | wrong corner order; outline linked after fill |
| `... pictures ...` | the colour at the centre of drawn faces equals the legend under painter's order (cyan boost pads of sections 28, 76); yellow at outline edges | wrong colour or draw order |
| `the primitive buffers ...` | guard bytes intact | writing past a block |
| `track_parse accepts ... rejects ...` | 81 crafted files: every code, the check order, limits and exact boundaries; `*out` zero; input untouched | order of checks; 16-bit sums |
| `track_vertex / track_face / track_section` | pointer or `NULL` for -1, 0, last, count, 65535, ... | unsigned compare |
| `track_colour` | 67 flag values | priority |
| `track_draw(t, first, count)` | wrap, count cut, `count <= 0`, negative `first`; vertices seen; `view_mtx.t` set non-zero in the test | modulo of a negative; not zeroing `t` |
| `the primitive budget` | six draws on one frame; the drops start where the model says | one drop must stop all later allocations |

A pass ends with `CHAPTER 34: PASSED (23/23 checks)`. The untouched starter fails; so do absolute vertices, the camera in `TR`, clamping instead of skipping, hard-coded counts, and a swapped colour priority.

## 9. Common pitfalls

- **Putting the camera in `TR`.** The GTE handles the large `t` fine; the absolute vertex is what gets narrowed to 16 bits. It looks right on the shipped tracks (their coordinates fit `s16`) and breaks as soon as one does not, as on the second disc.
- **Subtracting in 16 bits.** `(s16) v.x - (s16) eye.x` wraps; subtract in `int32_t`, then narrow.
- **A local `SVECTOR` for `gte_ldv0`.** The macro does not tell the compiler it reads memory, so the GTE can load stale stack bytes: garbage projections that change with the optimisation level (7.5).
- **Forgetting that `d` can still be too big.** A vertex 40,000 units away has no `s16`; it must be skipped, not truncated.
- **Testing only the first vertex.** A face is skipped when *any* corner is far; and classify all four, or `trk_vstate` differs.
- **`>=` for the far limit.** 32767 fits in `s16` and is kept; 32768 is far.
- **Adding two `u16` and comparing.** `first_face + face_count` wraps in 16 bits.
- **Reading a `u32` from an odd address.** An address error exception: check alignment first.
- **Linking the outline after the fill.** The fill covers it.
- **Writing past the packet.** A full buffer returns `NULL`; stop allocating for the frame.
- **Trusting the file.** Every index in it is a number to be checked.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- Appendix E.10 (`.TRK`), `tools/assets/trkgen.py` (the generator and manifest), `formats.py` (`parse_trk`).
- psx-spx, "GTE Division Inaccuracy" and "GTE Coordinate Calculation" (the saturations of 5.5).
- Chapter 14 and Appendix C (`POLY_F4`, polyline `0x48`).
- Next: Chapter 35 textures the same faces from `TRACK.TPK`.
