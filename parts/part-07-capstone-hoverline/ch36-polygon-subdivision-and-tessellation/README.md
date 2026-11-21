# Chapter 36: Polygon Subdivision and Tessellation

## 1. Concept

A big polygon near the camera is drawn badly by the PS1: its texture **swims** (the GPU maps textures affinely, Chapter 30), and a polygon that reaches the camera cannot be projected at all. The cure is to **subdivide**: cut the near polygons into 4 or 16 smaller ones, texture coordinates included, and draw those. This chapter splits the track's near faces recursively, keeps the number of packets inside the primitive buffer, and closes the **cracks** (T-junctions) that splitting some faces and not their neighbours leaves behind.

## 2. Why it matters

Chapter 35's track looks right from far away and wrong from close by: a 400 x 1000-unit lane fills the screen, the chequered start line bends, and a face with one vertex nearer than 128 units vanishes whole (Chapter 34), leaving a hole under the camera. Every later chapter drives a ship low over this surface. Subdivision is also the first place where **a rule about shared edges** decides whether the picture has holes: the same thinking comes back with collision (Chapter 40).

## 3. Learning objectives

After this chapter you can:

- explain **affine texture mapping** and why subdividing reduces its error;
- say what the GPU cannot do (z-clip, polygons over 1023 x 511) and how smaller polygons keep a near surface drawable;
- choose a **subdivision criterion** from depth or from projected size, and write it as an exact integer rule;
- split a quad into 4 children with **edge midpoints and a centre** in 3D and in UV, recursively, and say why the integer arithmetic must be exact;
- project the new vertices with **RTPT** batches and cull, order and emit each child;
- keep the packet count inside the buffer with a **deterministic budget rule**;
- explain a **T-junction**, why it leaves background-coloured pixels, and compare the ways to avoid it;
- read the debug view: which faces were split, how often.

## 4. Prerequisites

[Chapter 30](../../part-06-assets-cdrom-textures-and-compression/ch30-textured-polygons/README.md) (affine warp, the UV rule), [Chapters 25 to 27](../../part-05-three-dimensions-with-the-gte/) (the GTE, `RTPS`/`RTPT`/`NCLIP`/`AVSZ4`), [Chapter 34](../ch34-track-geometry/README.md) (camera-relative `d = v - eye`, the far / near / back / big rules, `track_stats`), [Chapter 35](../ch35-track-texturing/README.md) (the textured packet, `FLIP_H`) and Appendix E.10 (`.TRK`: the section's `edges`).

## 5. Explanation

### 5.1 Why big polygons swim

The GPU interpolates `u` and `v` **linearly across the screen**. Perspective says the texture should advance *non-linearly*: the near end of a receding quad covers more screen than its far end, so an even texture step per pixel is wrong. The error grows with the depth range of the polygon.

```
 one big quad, seen from above          the same quad as four
 (stripes are even texture steps)

   far    |  |  |  |  |  |             far   |   |   |   |
         /  |  |  |  |  \                   /|   |   |   |\
        /   |  |  |  |   \                 /-+---+---+---+-\
       /    |  |  |  |    \               /  |   |   |   |  \
 near /_____|__|__|__|_____\        near  /___|___|___|___|___\
   affine: stripes even on screen   each piece is affine, the pieces together
   (true texture: crowded far away) follow the perspective curve
```

Split the quad at its depth midpoint and each half has half the depth range, so about half the error; four pieces, a quarter. The cost is packets and projections, which is why only the **near** faces are split.

### 5.2 What the GPU cannot do for you

- **No z-clipping.** The GPU takes screen coordinates. A vertex behind the eye (or very near) has none: `RTPS` clamps its depth and divides by almost nothing. Chapter 34's rule drops any face with a vertex nearer than `TRK_NEAR_Z` (128): near the camera whole faces, the whole section under the eye, disappear.
- **Size limit.** A polygon wider than 1023 or taller than 511 pixels is not drawn (Chapter 34: `faces_big`).
- **Coordinates.** Screen coordinates are 11-bit signed after the GTE (about -1024..1023) and the camera-relative `d` is 16-bit (Chapter 34).

Subdividing helps with the first two. A child is judged **by its own** four vertices: of a face with one vertex behind the eye, the children away from it are projectable and drawn, so the hole shrinks from a face to a few small quads; a face too big for the GPU becomes children that are not. Subdivision does **not** clip: a child that still touches the near plane is dropped whole, like a face. The third limit stays: a child with a corner projected beyond about ±1024 is still drawn from the saturated coordinate, as in Chapter 34.

### 5.3 Splitting a quad

A quad's corners are in **Z order** (`v0 v1` on top, `v2 v3` below; Chapter 30). The split makes **five new vertices** and four children, each in the same Z order, so each child keeps its parent's winding:

```
 q0 ------ m01 ------ q1            child 0: q0   m01  m02  c
  |         |          |            child 1: m01  q1   c    m13
  |   0     |    1     |            child 2: m02  c    q2   m23
 m02 ------ c  ------ m13           child 3: c    m13  m23  q3
  |         |          |
  |   2     |    3     |            m01 = mid(q0, q1)   m02 = mid(q0, q2)
 q2 ------ m23 ------ q3            m13 = mid(q1, q3)   m23 = mid(q2, q3)
                                    c   = mid(m01, m23)
```

`mid(a, b)` is `(a + b) >> 1` (arithmetic shift: it rounds toward minus infinity) on **each** of: the camera-relative position `p` (x, y, z), the texel `u`, the texel `v`. Three rules:

- **Midpoints are taken in 3D**, on the camera-relative `d` vectors (`s16` in the GTE, computed in `int`), **not** on the screen. The midpoint of a receding edge is not the screen midpoint of its ends (5.1); projecting the 3D midpoint puts the vertex where the surface really is.
- **UVs use the face's final texels**: after `FLIP_H` and with the tile origin already added (what `track_face_uv` returns). Both operands are integers inside the tile, so `(a + b) >> 1` is exact and stays inside it. Mirroring *before* the split matters: `63 - ((a + b) >> 1)` and `(63 - a + 63 - b) >> 1` differ by one when `a + b` is odd. Rounding up, `(a + b + 1) >> 1`, is a bug the verifier names.
- `(a + b) >> 1` is **symmetric**: two children that share an edge compute the same midpoint from the same two ends. Inside one face, children are watertight by construction.

A level-2 face repeats the split in each child: 16 leaf quads, 5 splits, 25 vertices projected (21 distinct; the shared ones are computed twice, which is cheaper than finding them).

### 5.4 When to split: the criterion

| Criterion | Rule | Good | Bad |
|---|---|---|---|
| **Distance** | split when the depth `sz` is below a threshold | cheap: the depth is already computed for the vertices | ignores how big the face is |
| **Screen size** | split when a projected edge is longer than N pixels | splits what looks wrong | needs the projection first; a face edge-on has a long edge and no area |

They are the same rule for faces of one size: a 400-unit lane edge spans `400 * 320 / z` pixels, **32 px at z = 4000** and **64 px at z = 2000**. This chapter uses distance with those two thresholds; a screen-size rule is a stretch goal (7.6).

**The rule.** Per **section** (not per face):

1. Take the four vertices of `edges[0..3]` of the section (the road edges of its two rings).
2. Prepare each (Chapter 34) and keep those that are `VS_OK` **and** have `sz >= TRK_NEAR_Z` (128). If none: level 0.
3. `z` is the smallest `sz` of the kept ones. **Level 2** if `z < SUBDIV_Z2` (2000), **level 1** if `z < SUBDIV_Z1` (4000), else **level 0**.
4. All five faces of the section get that level.

```
 camera                         one lap seen from a section's start (levels from the camera)
   ^        z (depth)       0         2000        4000                       far
   |        level            |   2     |    1      |           0 ......
  [o]--+----+----+----+----+----+----+----+----+----+----+----+----+---
       | s0 | s1 | s2 | s3 | s4 | s5 | ...                  (sections ~1000 long)
         2    2    1    1    0    0   ...
```

*Why per section.* The five faces of a section share their long edges, so one level for all five means **no T-junction inside a section** (5.8). Faces with any `VS_FAR` vertex are far (Chapter 34): no level. A section whose four edge vertices are all nearer than 128 gets level 0 and its faces are dropped by the whole-face rule.

`example/levels.py` (6) prints this table for a camera.

### 5.5 The recursion and the GTE

The track already holds, per face vertex, `d` (`trk_rel`), `sxy` and `sz` (Chapter 34). The split path starts from those four and calls `subdiv_face`:

1. `subdiv_mid` for the five new vertices (m01, m02, m13, m23, then `c` from m01 and m23);
2. `subdiv_project`: **two RTPT calls** (m01, m02, m13, then m23, c). RTPT projects three vertices in one instruction; the sixth slot repeats a vertex. Load with `gte_ldv3`, store with `gte_stsxy3` and `gte_stsz3`. The rotation is the view matrix with `TR = 0` (Chapter 34), already loaded;
3. recurse into the four children, until `depth == level`: that quad is a **leaf**.

**The memory barrier.** Write the `SVECTOR`s, then `__asm__ volatile("" ::: "memory");`, then `gte_ldv3`: its asm has no memory clobber (Chapter 34's pitfall).

### 5.6 Leaves, counting and the order of the rules

A leaf goes through Chapter 34's rules, on its **own** four vertices, in this order:

| # | Test | Counter | If it fires |
|---|---|---|---|
| 1 | any `sz < TRK_NEAR_Z` | `leaves_near` | skipped |
| 2 | NCLIP of the first three screen points `<= 0` | `leaves_back` | skipped |
| 3 | bounding box wider than `TRK_MAX_W` or taller than `TRK_MAX_H` | `leaves_big` | skipped |
| 4 | otherwise: slot = AVSZ4 of the four `sz`, `>> OTZ_SHIFT` | `leaves_drawn0..2` (by depth) | `track_emit` links it; `leaves_dropped` if the buffer is full |

The given `draw_face` (`track_render.c`) does the **parent** part, in this order: far test; the section's level; if it is above 0 and the face has no near vertex, NCLIP of the parent (a back-facing parent has only back-facing children: `faces_back`, no split); the **budget rule** (5.7); then `subdiv_face`. A face that ends at level 0 takes Chapter 35's path unchanged.

A subdivided face is counted **once** in `track_stats`, by the first of these that applies: `drawn` (any leaf linked), `dropped`, `near`, `big`, `back`. Every face still lands in exactly one counter (`faces_seen` is their sum). `subdiv_stats` counts the leaves; the table is in 7.2.

*Measured on the reference* (the verifier's "start line, very close" and "on the road" poses, 250 and 120 units up): 345 and 391 packets against 138 and 151 with nothing split, and 805,000 and 938,000 cycles in `track_draw` against 485,000 and 568,000: about +65%. An NTSC frame (one vertical blank to the next) is 566,120 CPU cycles. Unsplit, the whole-track pass already takes 0.86 to 1.00 frames; with subdivision, every verifier pose with the normal reserve takes **1.3 to 2.2 frames** (worst about 1.22 million cycles, at a wall). So this chapter's program does **not** fit in 1/60 s: the frame rate drops to 30 or 20 Hz. That is a known cost here, not a goal: Chapter 38 draws only a window of sections around the ship, which brings the unsplit pass well inside the budget; subdivision inside that window still takes more than one frame on most poses (Chapter 38 measures it). The verifier's cost check (8) only catches an implementation that is much slower than this one.

### 5.7 The primitive budget

Each level multiplies the packets by 4. One textured face, 40 bytes (`POLY_FT4`):

| Level | Quads | Bytes | with outlines (+32 each) |
|---|---|---|---|
| 0 | 1 | 40 | 72 |
| 1 | 4 | 160 | 288 |
| 2 | 16 | 640 | 1152 |

The buffer is 32,768 bytes (`PRIM_BUF_SIZE`). Splitting every one of 560 faces at level 2 needs 358,400 bytes: ten times too much, and Chapter 34's rule would drop faces from the first full buffer on. The budget rule stops that **before** the buffer is full:

> while `level > 0` and `ot_bytes_left() < subdiv_reserve + (4^level + 1) * leaf_bytes`: `level--`

`leaf_bytes` is 40 textured, 24 flat, +32 with outlines (`wire_mode` or `subdiv_debug`); the `+ 1` is the backing quad (5.8), counted at leaf size although it never has an outline (a little too much, never too little). `subdiv_reserve` is **8192** bytes: room for about 200 more plain faces after the face being split. A cut is counted in `budget_cuts`. `ot_bytes_left()` is new in this chapter's `psxe`. The reserve is a variable so the verifier can patch it: with 40000 nothing is ever split.

The rule is **deterministic**: it depends only on the bytes used so far, which depend only on the sections drawn before. At the poses of the verifier no face is dropped, and the normal poses never need a cut; with outlines on, the budget does cut (a few faces: the outline is 32 more bytes per quad).

### 5.8 T-junctions and cracks

Two neighbours that share an edge, one split and one not (or split to different levels), draw that edge differently:

```
  the coarse face's edge is one straight segment A---B;
  the fine face's edge is two segments A--M--B, M = the projected 3D midpoint, rounded to a pixel

    A ____________________ B        A _________ M _________ B
      \_ coarse ___________/          \_  fine  ___/ \___ fine _/
                                          M is a few tenths of a pixel off the line A-B

  the pixels between the line and the polyline belong to neither face:
  background shows: a one-pixel slit that sparkles as the camera moves
```

The **T** is the vertex `M` of one face lying in the middle of the other face's edge. Projection keeps straight lines straight, so `M` would be on the line A-B exactly; it is off only because every vertex is rounded to a whole pixel. Inside one face, children share their vertices and cannot crack. Cracks appear where two **parents** that share an edge have different levels.

With per-section levels (5.4) that happens at the ring between two sections of different level, and a distance rule *must* change level somewhere. The usual mitigations:

| Method | How | Verdict |
|---|---|---|
| **Consistent levels across edges** | make both faces of every shared edge agree: per section (this chapter) only covers the edges *inside* a section; covering the rings needs a level per vertex or per edge, and a face whose edges differ then needs a **conforming** pattern (the coarse side gets the vertex `M` too: triangles or extra vertices) | exact; every face needs its neighbours' levels and one pattern per combination of edge levels |
| **Max-depth / level-difference rules** | cap the depth, and keep neighbours within one level of each other | limits how many T-vertices an edge can have (one), so the conforming patterns stay few; on its own it does not remove the crack |
| **Slight overlap** | move the fine face's outline about 1 pixel outward | cheap, but the push is per axis, not along the edge's normal, so on thin faces seen at a grazing angle it misses the slit |
| **Backing quad** | draw the whole face once **behind** its children | crack-free by construction; one extra quad per split face |

**How the reference got here.** It first used per-section levels with a 1-pixel outward expansion of the leaves. The gap detector still found background pixels at the level rings, on faces seen at grazing angles. The expansion was then replaced by the backing quad.

**What the project does: per-section levels plus a backing quad.** Each split face also emits **one quad for the whole face**, with the face's own four corners, UVs and tile. It is linked into the slot of its **farthest leaf**, *after* the leaves: the ordering table draws the newest packet of a slot first (Chapter 34), so it is drawn under them. Why this cannot leave a crack:

- the union of all parents is exactly the unsplit track: neighbouring parents use the same projected vertices, so they tile with no gap (Chapter 35's picture);
- a leaf that leaves a sliver along the parent's edge leaves it **inside** the parent, where the backing quad is; a leaf that overshoots the edge only overlaps the neighbour;
- the backing quad shows in the sliver as the parent's own texture, affinely warped: one pixel wide, invisible.

The backing quad is drawn only when the face as a whole could be drawn (no vertex nearer than 128, not too big), so a split face that touches the near plane gets none. It has no outline in the debug view.

**What the verifier demands.** The backing quad is part of the contract, not one option among several. The packet check (8) compares the ordering table with a model that has exactly one backing quad per split, drawable face, in its slot and drawn before its leaves, and `subdiv_stats.backings` must match. A different fix that also leaves no gap (overlap, conforming triangles) therefore fails the packet and count checks, even though the gap detector would pass it. The reason is that the verifier checks every packet exactly; a stretch goal (7.6) lets you try the others. The **gap detector** looks for the background colour along every edge shared by two completely drawn faces (both at least 6 pixels across), on the seam and one pixel to each side. With the backing quad it finds none; without it, it finds background pixels, mostly along the seams between levels.

### 5.9 The debug view

`subdiv_debug` (toggled by **Triangle**, edge-triggered like Select) puts an outline on every quad **drawn**, in the colour of the depth it was produced at:

| Depth | Meaning | Outline | RGB | GPU word |
|---|---|---|---|---|
| 0 | a whole face (not split) | yellow | 255, 255, 0 | `0x0000FFFF` (`COL_LEVEL0`, the Chapter 34 wire colour) |
| 1 | one split (a quarter of a face) | cyan | 0, 255, 255 | `0x00FFFF00` (`COL_LEVEL1`) |
| 2 | two splits (a sixteenth) | magenta | 255, 0, 255 | `0x00FF00FF` (`COL_LEVEL2`) |

Select's wire mode is separate: it outlines every quad in yellow. With both on, the level colours win. Both add 32 bytes per quad, so the budget cuts sooner.

## 6. Worked example

```sh
python ../example/levels.py build/assets/TRACK.TRK --section 0 --back 1300 --height 450     # from starter/, after make
```

The camera is placed like the verifier's poses. The script prints each section in front of the camera with the depth of its nearest road-edge vertex, its level and how many quads a face of it becomes, then an upper bound on the quads (before culling, without backing quads). Try other `--back` and `--height` values: the three thresholds move along the road, and the bound shows where the budget starts to matter. It uses floating point; the verifier's model is the GTE's integer arithmetic.

Then run the reference in PCSX-Redux (`make run` in `solution/`), press **Start** and **Triangle**: the outlines are yellow far away, cyan and magenta near the camera, and the transitions are rings across the road.

## 7. Project: subdividing the track

### 7.1 Behaviour

Chapter 35's program. Near sections are drawn as 4 or 16 quads per face, from the criterion (5.4). **Select** toggles the yellow wireframe (Chapter 34), **Triangle** toggles the per-depth outlines (5.9). The picture without outlines looks like Chapter 35's, with steadier textures and no holes under the camera.

### 7.2 The contract

`starter/` is Chapter 35's `solution/` plus `subdiv.c/h` and the hook in `track_render.c`. It builds and boots and shows Chapter 35's picture, because every stub returns level 0. **Read `subdiv.h` and `track_render.h` first.** **Given:** everything of Chapter 35, `track_render.c` (the parent rules, the split path calling your functions, `track_emit`: the packet and outline code), `ot_bytes_left()`, the constants and `SubdivStats` in `subdiv.h`, `main.c`. **You write:** the files below.

| File | What |
|---|---|
| `game.c` | **Triangle** toggles `subdiv_debug` (edge-triggered) |
| `subdiv.c` | `subdiv_level`, `subdiv_section_level`, `subdiv_budget_level`, `subdiv_mid`, `subdiv_project`, `subdiv_face` |

**State the verifier reads** (names and types fixed):

| Symbol | Meaning |
|---|---|
| `subdiv_stats` | 13 words: `faces_level0..2` (faces that were not far, by the **criterion's** level), `leaves_drawn0..2` (quads linked, by depth), `leaves_near`, `leaves_back`, `leaves_big`, `leaves_dropped`, `budget_cuts`, `outlines`, `backings` |
| `subdiv_debug`, `subdiv_reserve` | the toggle; the budget's reserve in bytes (starts at `SUBDIV_RESERVE`; the verifier patches both) |
| `track_stats`, `prims_submitted`, `prims_dropped` | Chapter 34's counters; with this chapter's counting rule (5.6) |
| the Chapter 33 to 35 state | `cam_eye`, `cam_yaw`, `view_mtx`, `frame_no`, `game_state`, `wire_mode`, the ordering table |

### 7.3 Steps

1. **The toggle**: in `game_update`, **Triangle** (`INPUT_TRIANGLE`) flips `subdiv_debug`, once per press.
2. **The criterion**: `subdiv_level(z)` and `subdiv_section_level`. Build and run `verify.sh`: the first three words of `subdiv_stats` start to match (the near sections now vanish, because `subdiv_face` still draws nothing).
3. **`subdiv_mid` and `subdiv_project`** (5.3, 5.5). Test them on paper with one face.
4. **`subdiv_face`: the recursion and the leaves** (5.5, 5.6): split to `level`, cull each leaf, `track_emit`, count. The near sections reappear, textured.
5. **The backing quad and the return code** (5.8, 5.6): after the leaves, once. Run `verify.sh`: the gap detector passes.
6. **The budget** (5.7): `subdiv_budget_level`.
7. **Look at it**: **Triangle** in the emulator, then `verify.sh` until it passes. Write down the packets at the close pose and compare with the worked example's bound.

### 7.4 Rules

- The level is **per section**, from the **camera-relative depth** of the four road-edge vertices; never from absolute coordinates, never per face.
- Midpoints are `(a + b) >> 1` on the camera-relative position and on the **final** UVs; children in the order of 5.3; **5 new vertices per split, projected with RTPT**.
- A leaf is judged on its own four vertices, in the order of 5.6. A leaf is never clipped, only dropped.
- The backing quad is drawn after the leaves of its face, in the slot of the farthest leaf, never with an outline.
- No `malloc` in the frame. The recursion needs at most 4 children x 4 vertices on the stack per level.
- Flat faces (`tex = 0xFF`) are subdivided too: leaves are `POLY_F4`, `u` and `v` are ignored.

### 7.5 Hints

- Keep `SdVert` as given: `SVECTOR p` is what `gte_ldv3` reads, so write `p` before projecting and add the barrier (5.5).
- `(a + b) >> 1` on `int` values: do the sum in `int`, not in the `s16` fields.
- `track_emit` takes the four packed screen points, the eight texels, the depth for the slot (`AVSZ4` result) and the depth for the colour; read its comment.
- Counters: `(&subdiv_stats.leaves_drawn0)[depth]` is a quick way to index them.
- If a pose fails, the verifier names the face, its depth and the packet it expected: compare with a hand calculation of one split.

### 7.6 Stretch goals

- **A screen-size criterion**: split when the longest projected edge of the *parent* exceeds 32 / 64 pixels; compare the packet counts with the depth rule.
- **Per-vertex levels and conforming edges**: give each ring vertex a level from its own depth, split each edge by the level of its two ends, and fill a face whose edges differ with triangles (the coarse side gets the vertex its neighbour has). With neighbours kept within one level, count the patterns you need. Remove the backing quad and run `verify.sh`: the gap detector still applies, while the packet and count checks fail by design (they model the backing quad).
- **Level 3** with the budget rule, and see where the reserve has to grow.
- **Perspective-correct texture** by hand: for a face at level 2, compare the UV of a leaf's centre with the true perspective-correct value.

## 8. Verification

```sh
source tools/env.sh
parts/part-07-capstone-hoverline/ch36-polygon-subdivision-and-tessellation/verify/verify.sh            # your starter/
parts/part-07-capstone-hoverline/ch36-polygon-subdivision-and-tessellation/verify/verify.sh --solution # the reference
```

About 25 seconds: a build and two emulator runs (the disc and a second disc). The probe taps **Triangle** twice and holds it once, then writes camera poses (and `wire_mode`, `subdiv_debug`, `subdiv_reserve`) and records, for each, the view matrix, both counters, the packets of the ordering table, the CPU cycles of `track_draw` and a screenshot. Python computes everything else from the generated files: Chapter 34's GTE model with this chapter's rules, then every packet.

| Check | What it means | If it fails |
|---|---|---|
| the toggle | Triangle flips `subdiv_debug` once per press, a held button once | `input_held` instead of `input_pressed` |
| `faces are split by distance` (main, alt) | `subdiv_stats` and `track_stats` equal the model's at every pose: the levels, the leaves by depth, near / back / big, cuts, outlines, backings; faces nearer than 128 are recovered through their children | the criterion (which vertices, which threshold), the counting order, the budget |
| `... packets` (main, alt) | every packet equals the model's, pose by pose: leaf quads, backing quads, positions, tpage and CLUT words, outlines; each backing quad drawn before its face's leaves in its slot | child order, the RTPT inputs, the slot (AVSZ4 of the leaf), the backing's slot; the backing linked before the leaves (drawn over them); a crack fix other than the backing quad |
| `the UVs of every quad are exact` (main, alt) | the four texels of every quad (backing included) are the exact midpoints; reported alone so that a rounding or a dropped UV is named | `+ 1` in the rounding; flipping after the split; the parent's UVs copied to the children |
| `the gap detector` | with debug and wire off, no pixel along any seam between two completely drawn faces, or beside it, has the background colour; includes seams between **different levels** | no backing quad |
| `the primitive budget` | nothing dropped in any pose; patched reserves cut levels as the rule says | wrong bytes in the rule (outline, backing) |
| `debug outlines` | counts per colour equal the model's; the picture contains each colour | wrong depth for the colour |
| `cost` | `track_draw` under 1.6 million cycles (2.8 NTSC frames) in every pose; at the two paired poses, subdividing costs less than twice the unsplit pose (the reference: 1.3 to 2.2 frames, +65%) | 4 RTPS per leaf, a division in the recursion |
| `the primitive buffers` | the guard bytes stayed `0xA5` | writing past the block |

The second disc has track 2 moved far from the origin, the texture ids permuted and two sections untextured (Chapter 35): the criterion must use camera-relative depth, and flat faces must split too. A pass ends with `CHAPTER 36: PASSED (15/15 checks)`. The untouched starter fails; so do subdividing everything (the budget and the packets), `(a + b + 1) >> 1`, copying UVs to the children, and omitting the backing quad (the gap detector and the packets).

## 9. Common pitfalls

- **Midpoints on the screen.** Use the 3D midpoint and project it; the screen midpoint is the wrong point of a receding edge.
- **Rounding up.** `(a + b + 1) >> 1`, or `/ 2` on negative numbers (which rounds toward zero), gives other vertices than the verifier's.
- **Flipping after the split.** Mirror the face first.
- **A 16-bit sum.** Add in `int`: two `s16` values can add to more than `s16`.
- **No memory barrier before `gte_ldv3`.** The GTE reads stale vertices (Chapter 34).
- **Splitting by face.** Faces of a section then differ in level and the edges between them crack.
- **Using the nearest vertex of a section behind the camera.** A vertex with `sz < 128` is not a distance; skip it (5.4).
- **Counting a subdivided face once per leaf.** `track_stats` counts faces.
- **The backing quad over its children.** The ordering table draws the last linked packet of a slot first: link the backing quad after the leaves, in the slot of the farthest leaf.
- **An outline on the backing quad.** It would draw lines across the leaves.
- **Forgetting flat faces.** `tex = 0xFF` splits too.
- **Reading the crack as a texture bug.** A one-pixel sparkling slit between two sections is a T-junction.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- Appendix E.10 (the track, section `edges`), E.3.4 (UV origin).
- psx-spx, "GPU Render Polygon Commands" (the 1023 x 511 limit and the vertex coordinate range).
- Chapters 30 (affine warp), 34 (the near rule, the buffer), 35 (the packet), 38 (which sections to draw at all), 40 (edges shared between things, again).
