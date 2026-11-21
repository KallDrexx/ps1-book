# Chapter 25: The GTE Coprocessor

## 1. Concept

The **GTE** (Geometry Transformation Engine) is a coprocessor inside the PS1's CPU chip, built to do the arithmetic of Chapter 24 in hardware: multiply a vertex by a rotation matrix, add a translation, divide by depth, and report the screen position, the depth and a few error flags. It can also compute the sign of a triangle's winding (`NCLIP`) and the average of several depths (`AVSZ`). You load numbers into it, start a **command**, and read the results back.

## 2. Why it matters

Chapter 24 spent about 8 multiplies, 2 divides and two function calls per corner. The GTE does a full transform in about 15 cycles, and the book's later 3D chapters (multiple objects, 64 cubes, a camera) would not fit in a frame without it. This chapter also adds two things the wireframe did not need: **back-face culling** (do not draw faces that point away) and **depth sorting** (draw far faces first, through the ordering table of Chapter 20).

## 3. Learning objectives

After this chapter you can:

- describe the GTE's place in the system (coprocessor 2) and name its main registers;
- set up the GTE for a 320x240 screen: offset, projection distance;
- build a rotation matrix and a translation, and upload them;
- transform a vertex with `RTPS` and read its screen position, depth and flags;
- decide whether a face points at the camera with `NCLIP`, and explain why the corner order of a quad matters;
- turn the GTE's average depth (`OTZ`) into an ordering-table slot.

## 4. Prerequisites

[Chapter 24](../ch24-3d-projection-fundamentals/README.md) (the pipeline, Y down / Z in, rotation direction, the cube), [Chapter 23](../ch23-fixed-point-math/README.md) (4.12, angle units), [Chapter 20](../../part-04-c-on-the-playstation/ch20-primitives-and-ordering-tables/README.md) (`POLY_F4`, the ordering table), [Chapter 21](../../part-04-c-on-the-playstation/ch21-working-with-multiple-files/README.md) (`psxe`).

## 5. Explanation

### 5.1 What the GTE is

The GTE is **coprocessor 2** (COP2) of the R3000. It has no program of its own: the CPU moves data in and out, and starts one **command** at a time.

```
        CPU                                   GTE (COP2)
  +--------------+   mtc2 / lwc2   +----------------------------------+
  | registers    | --------------> | data registers   (32 x 32 bit)   |
  | and memory   |   ctc2          | control registers (32 x 32 bit)  |
  |              | --------------> |   matrices, translation, H ...   |
  |              |   cop2 <cmd>    |                                  |
  |              | --------------> |  command unit: RTPS, NCLIP ...   |
  |              |   mfc2 / swc2   |                                  |
  |              | <-------------- |  results in the data registers   |
  +--------------+   cfc2          +----------------------------------+
```

| Instruction | Does |
|---|---|
| `mtc2` / `mfc2` | CPU register to / from a GTE **data** register |
| `ctc2` / `cfc2` | CPU register to / from a GTE **control** register |
| `lwc2` / `swc2` | load / store a GTE data register straight from / to memory |
| `cop2 <cmd>` | start a command: `RTPS` 15 cycles, `RTPT` 23, `NCLIP` 8, `AVSZ3` 5, `AVSZ4` 6 |

The CPU keeps running while a command works. An instruction that reads a GTE register (or starts another command) before the current one has finished simply waits for it, so no padding is needed *after* a command. Two delays do need care: a value read with `mfc2`/`cfc2` reaches the CPU register one instruction late (like `lw`), and a register just written should not be used by a command in the next two instructions. The SDK macros (5.2) contain these `nop`s.

The registers you meet in this chapter ([Appendix D](../../../appendices/D-gte-reference.md) lists all of them with their bit formats):

| Group | Registers | Holds |
|---|---|---|
| Input vectors | `VXY0/VZ0`, `VXY1/VZ1`, `VXY2/VZ2` | three vertices, 3 x `int16` each |
| Rotation, translation | `RT` (3x3 `int16`, 4.12), `TR` (3 x `int32`) | the matrix you upload |
| Projection | `H`, `OFX`, `OFY` | projection distance; screen offset (16.16) |
| Screen XY | `SXY0`, `SXY1`, `SXY2` | the last three projected points (`int16` x, `int16` y packed in one word) |
| Depth | `SZ0` to `SZ3`, `OTZ` | the last four depths (`uint16`); the average depth for the ordering table |
| Averaging | `ZSF3`, `ZSF4` | scale factors for `AVSZ3` / `AVSZ4` |
| Results | `MAC0` to `MAC3`, `IR0` to `IR3` | the 32-bit accumulators and 16-bit intermediate values; `NCLIP` leaves its answer in `MAC0` |
| Status | `FLAG` | one bit per kind of overflow |

`SXY` and `SZ` are **FIFOs**: each transform pushes its result in at the end and shifts the older ones down. That is how three vertices can be held for `NCLIP` and four depths for `AVSZ4`.

### 5.2 What the SDK gives you

The classic Sony library had functions such as `RotTransPers`, `RotAverageNclip4` and `NormalClip`. **PSn00bSDK 0.24 does not have them.** It has:

| Where | What |
|---|---|
| `<psxgte.h>` (library) | `InitGeom`, `RotMatrix`, `TransMatrix`, `MulMatrix`, `CompMatrixLV`, `PushMatrix`/`PopMatrix`, `isin`/`icos`, the types `MATRIX`, `SVECTOR`, `VECTOR` |
| `<inline_c.h>` (macros) | one macro per GTE load, store and command: `gte_SetGeomOffset`, `gte_SetGeomScreen`, `gte_SetRotMatrix`, `gte_SetTransMatrix`, `gte_ldv0`, `gte_rtps`, `gte_rtpt`, `gte_ldsxy3`, `gte_nclip`, `gte_ldsz4`, `gte_avsz4`, `gte_stsxy`, `gte_stsz`, `gte_stopz`, `gte_stotz`, `gte_stflg`... |

So the "functions" of the old books are short sequences of macros. The three you will need:

| Classic name | In 0.24 | Outputs |
|---|---|---|
| `RotTransPers(v, &sxy, &p, &flag)` | `gte_ldv0(&v); gte_rtps(); gte_stsxy(&sxy); gte_stsz(&sz); gte_stflg(&flag);` | screen XY, depth `SZ` (the old function returned `SZ / 4`; its `p` was the depth-cue value `IR0`), flags |
| `NormalClip(a, b, c)` | `gte_ldsxy3(a, b, c); gte_nclip(); gte_stopz(&area);` | `MAC0`: twice the signed area |
| `RotAverageNclip4(...)` | four `RTPS`, `gte_nclip`, `gte_avsz4`, `gte_stotz` | screen XY of four corners, area, `OTZ` |

The macros are plain inline assembly: include `<inline_c.h>` after `<psxgte.h>`. They contain the `nop`s of 5.1. Chapter 27 batches three vertices per command with `RTPT` and measures what the GTE costs.

### 5.3 Setting up: `InitGeom`

`InitGeom()` switches COP2 on (a bit of the CPU's status register) and gives every control register a default: offset 0, `H` = 320, and the averaging factors `ZSF3 = 341`, `ZSF4 = 256`. You then set what your program needs:

| Call | Sets | This chapter |
|---|---|---|
| `gte_SetGeomOffset(x, y)` | `OFX`, `OFY`: the screen position of the projection's centre, in whole pixels | `(160, 120)` |
| `gte_SetGeomScreen(h)` | `H`: the projection distance of Chapter 24 | `proj_h` = 256 |

Nothing else is needed for the transform. Call these once, after `InitGeom`.

### 5.4 Types and units

| Type | Layout | Used for |
|---|---|---|
| `SVECTOR` | `int16 vx, vy, vz, pad` (8 bytes) | model vertices; the three angles of a rotation |
| `VECTOR` | `int32 vx, vy, vz` | translations |
| `MATRIX` | `int16 m[3][3]` (4.12) then `int32 t[3]` | rotation and translation together |

The **units** are the part to keep straight. The matrix is 4.12 (4096 = 1.0), but the vertex and the translation are plain integers in whatever unit you choose: with an identity matrix a vertex comes out unchanged. This chapter's cube has corners at +-4096 units (the same numbers as Chapter 24's 4.12 values, now just "units"), and the camera distance is 24576 units. Only the ratios matter: `h * 4096 / 24576` = 43 pixels for a corner's x.

### 5.5 The matrix

`RotMatrix(&rot, &mtx)` fills `mtx.m` from three angles (`rot.vx`, `vy`, `vz`, **4096 per turn**, like Chapter 23). It multiplies the three rotations as **`Rx * Ry * Rz`**. A vertex `v` becomes `Rx * (Ry * (Rz * v))`: it is turned about **Z first, then Y, then X**. The direction is the one from Chapter 24: positive `vx` moves +Y toward +Z, positive `vy` moves +Z toward +X, positive `vz` moves +X toward +Y (clockwise on screen). Note the order: with `vz = 0` it is Y then X, the reverse of Chapter 24's loop, so the same two angles give a different spin.

`TransMatrix(&mtx, &pos)` copies a `VECTOR` into `mtx.t`. It does not touch the rotation. The GTE computes `R * v + T`, so as in Chapter 24 the cube is rotated first and then moved: `pos = (0, 0, cam_z)`.

`RotMatrix` and `TransMatrix` only fill the C structure. **Uploading** is separate: `gte_SetRotMatrix(&mtx)` and `gte_SetTransMatrix(&mtx)` copy the `m` and `t` parts into the GTE's `RT` and `TR`. Forget them and the GTE keeps the previous matrix. Call them through the starter's `load_matrix(&mtx)`, not directly (section 9 says why).

### 5.6 Transforming: `RTPS`

`RTPS` (**R**otate, **T**ranslate, **P**erspective, **S**ingle) takes the vertex in `V0` and does the whole of Chapter 24's pipeline:

```
 V0 (int16 x3)                                              SXY2  (x, y: int16 each)
    |                                                         ^
    |   IRn = (TR*4096 + RT * V0) >> 12      SZ3 = MAC3      |   SX = OFX + IR1 * (H / SZ3)
    +--> rotate + translate ------------------+--> divide ---+   SY = OFY + IR2 * (H / SZ3)
                                              |
                                              +--> SZ3 (depth, uint16, 0..65535)
```

| Output | Register | Read with | Range and meaning |
|---|---|---|---|
| Screen x, y | `SXY2` | `gte_stsxy(&w)` | one 32-bit word: x in the low half, y in the high half; each saturates to -1024..1023 |
| Depth | `SZ3` | `gte_stsz(&z)` | z after rotation and translation, clamped to 0..65535 |
| Flags | `FLAG` | `gte_stflg(&f)` | error bits, below |

Also left behind: `IR1..IR3` (the view-space x, y, z) and `IR0` (a depth-cueing factor for fog, unused here).

**The divide.** The GTE has no real divider: it computes `H / SZ3` with a table and one Newton-Raphson step, so it can be off by a little in the last bit. The ratio is a 16.16 number saturated at `0x1FFFF` (just under 2.0). Where `H >= 2 * SZ3` it is **divide overflow**: the vertex is closer than `H / 2` (128 units with `h = 256`), or behind the camera, and the flag says so. The result is a saturated number, not garbage, which is why the GTE needs no near-plane clip for crude work.

**Flags.** `FLAG` is cleared by every command. The bits worth knowing:

| Bit | Meaning |
|---|---|
| 31 | summary: at least one error bit (23 to 30, 13 to 18) is set |
| 17 | divide overflow (`H >= 2 * SZ3`) |
| 18 | `SZ3` or `OTZ` saturated |
| 14, 13 | `SX2` / `SY2` saturated (off the +-1024 range) |
| 24 to 22 | `IR1` to `IR3` saturated |
| 12 | `IR0` saturated to 0..4096 (normal here: `InitGeom`'s depth-cue values `DQA`/`DQB` saturate it; not an error and not part of bit 31) |

**Precision.** The GTE rounds in places Chapter 24's code did not (the divide above; one `>> 12` after the sum). A program matching Chapter 24's numbers to 1 pixel is right.

### 5.7 Faces, winding and `NCLIP`

A cube has 6 **faces**, each a quad of 4 corner indices. A face turned away from the camera is hidden by the faces in front of it, so drawing it is wasted work (and with a painter's algorithm it may also be wrong). **Back-face culling** skips it, and the GTE can tell which faces those are from the 2D result alone:

```
  NCLIP(p0, p1, p2) = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)       (twice the signed area)
                      stored in MAC0

        p0 ----> p1                           p0 ----> p2
         \                                     \
          \  clockwise on screen                \  counter-clockwise on screen
           v                                     v
           p2        NCLIP > 0                   p1        NCLIP < 0

  (screen y points down: "clockwise" is as you see it on the TV)
```

**Positive means clockwise.** (The SDK's own comment states the same: a negative `MAC0` means the triangle is back facing.) Zero means edge-on. Seen from outside, a solid object's faces run clockwise if you list their corners one way, and turning the object over reverses the winding on screen: that is the whole trick. It only works if **every face is listed in the same sense**.

**The quad's corner order.** The GPU draws a four-point polygon as two triangles `(v0, v1, v2)` and `(v1, v2, v3)`, so corners go in **Z order**, not around the perimeter:

```
   v0 -------- v1          Z order:       0 1 2 3   (draws a quad)
    |        /  |          perimeter:    0 1 3 2   (draws a bow tie: wrong)
    |      /    |
    |    /      |          NCLIP uses the first three: v0, v1, v2.
   v2 -------- v3
```

The rule that makes every face right: **look at the face from outside the cube; name its corners top-left, top-right, bottom-left, bottom-right as you see them; list them in that order.** Then `v0 -> v1 -> v2` is clockwise exactly when you are looking at the face from outside, which is when it is front-facing. The corner numbering is Chapter 24's (bit 0 is x, bit 1 is y, bit 2 is z, with y down):

```
        4--------5            face 0: z = -1   0 1 2 3     (toward the camera at rest)
       /|       /|            face 1: z = +1   5 4 7 6     (seen from behind: left and right swap)
      6--------7 |            face 2: x = -1   4 0 6 2
      | 0------|-1            face 3: x = +1   1 5 3 7
      |/       |/             face 4: y = -1   4 5 0 1     (the top: y is down, so -1 is up)
      2--------3              face 5: y = +1   2 3 6 7     (the bottom)
```

The starter gives this table. Do not "tidy" it: the tempting mistake is to write each face's corners in some natural order, and then half the faces vanish when they should show.

### 5.8 Depth: `AVSZ4` and `OTZ`

The GPU has no depth buffer, so you sort. For one quad, take the **average depth of its four corners**. `AVSZ4` computes

```
  OTZ = (ZSF4 * (SZ0 + SZ1 + SZ2 + SZ3)) >> 12          (clamped to 0..65535; flag 18 if it clamps)
```

from the four newest `SZ` registers. With `ZSF4 = 256` (InitGeom's value) that is `sum / 16`, the mean depth divided by 4. (`AVSZ3` with `ZSF3 = 341` gives the same for three corners.)

The four `SZ` registers hold the **last four transforms**, so reading them is only right straight after transforming exactly that face's corners. This chapter transforms each corner once and keeps `SZ` in an array; to average a face, load its four values back with `gte_ldsz4(a, b, c, d)`, run `gte_avsz4()` and read `gte_stotz(&otz)`. (`RotAverageNclip4` of the old SDK transforms the four corners of every face again: 24 transforms per cube instead of 8.)

An average is an approximation: long polygons and intersecting ones can still sort wrongly. For a single cube with its hidden faces culled the order does not even matter (the visible faces never overlap); sorting earns its keep once several objects share the screen.

### 5.9 From `OTZ` to an ordering-table slot

Chapter 20's table has 64 slots: slot 0 is nearest (drawn last), 63 is farthest (drawn first). `OTZ` grows with distance, so the conventions already agree. You only scale it:

```
  slot = clamp(OTZ >> 7, 0, 63)         a slot spans 128 OTZ = 512 units of mean depth
```

| Mean depth | `OTZ` | slot |
|---|---|---|
| 16384 | 4096 | 32 |
| 24576 (the cube's centre) | 6144 | 48 |
| 32768 | 8192 | 64: clamped to 63 |

With this chapter's cube a face's centre is 20500 to 28700 units away, so its quad lands in slots 40 to 56. A scene with a bigger range uses a bigger shift; a shallower one a smaller shift, so the 64 slots are spent where the objects are.

## 6. Worked example

`example/` turns one card about the Y axis. It does not cull: it asks `NCLIP` which side faces you, and paints the front green and the back red.

```sh
source tools/env.sh
cd parts/part-05-three-dimensions-with-the-gte/ch25-the-gte-coprocessor/example
make run
```

Try each of these:

1. Swap the colours' test (`area > 0` to `area < 0`). Which side is green now?  (The back: the sign decides which side counts as the front.)
2. Swap the card's corners 1 and 2 in `card[]`. What changes, and why? (Every winding reverses: the front is red at rest.)
3. Change the `12000` distance to `2000`. Watch the card as it turns toward you: when a corner comes closer than `h / 2` the divide overflows (5.6).

## 7. Project: "Solid Cube"

Draw the Chapter 24 cube as six solid quads: transform with the GTE, cull the back faces with `NCLIP`, sort the rest into the ordering table by average depth, and spin it.

### 7.1 Behaviour

A flat-shaded cube, one colour per face, spinning about two axes, in the middle of a dark blue screen (`display_clear(16, 16, 32)`). Never more than three faces are visible at once, and they are never hidden behind each other.

### 7.2 The contract

`starter/main.c` declares this state (do not change names, types or initial values):

| Symbol | Type | Initial | Meaning |
|---|---|---|---|
| `cube[8]` | `SVECTOR` | corners, +-4096 | Corner `i`: x = +4096 if bit 0 of `i` is set, else -4096; y from bit 1, z from bit 2 (`pad` = 0) |
| `faces[6][4]` | `uint8_t` | the table of 5.7 | Corner indices of each face, in Z order |
| `face_colors[6][3]` | `uint8_t` | red, green, blue, yellow, magenta, cyan | `r, g, b` of face `f` |
| `rot` | `SVECTOR` | `{128, 256, 0}` | Current angles about X, Y, Z (4096 = one turn, always kept in 0..4095) |
| `rot_step` | `SVECTOR` | `{24, 40, 0}` | Added to `rot` every frame (may be negative) |
| `cam_z` | `int32_t` | 24576 | The translation's z: the cube's centre is this far away |
| `proj_h` | `int32_t` | 256 | Projection distance `h`, in pixels |
| `mtx` | `MATRIX` | 0 | You fill it: `RotMatrix` plus `TransMatrix`, the matrix you upload |
| `screen_xy[8]` | `int32_t` | 0 | Corner `i` as one `SXY` word: x in the low 16 bits, y in the high 16 |
| `screen_z[8]` | `int32_t` | 0 | Corner `i`'s `SZ` |
| `gte_flags` | `int32_t` | 0 | OR of the `FLAG` register after each of this frame's 8 transforms |
| `prims_submitted` | `int32_t` | 0 | Quads linked into the table **this frame** |
| `faces_drawn` | `int32_t` | 0 | Quads linked since the start |
| `face_mask` | `int32_t` | 0 | Bit `f` set if face `f` was drawn this frame |
| `frame_no` | `int32_t` | 0 | Frames completed (the given loop increments it) |

Frame order (the loop in `main` is given): `display_clear`, `ot_begin_frame`, **`render_begin()`**, `update_angles`, `upload_matrix`, `transform_corners`, `draw_faces`, **`render_end()`**, `ot_draw`, `display_swap`, `frame_no++`, `frame_done()`. The empty functions `render_begin`/`render_end` mark the work whose CPU cycles the verifier counts; `frame_done()` is where it reads the state. So at `frame_done()` with `frame_no == k`, `rot` is `(start + k * rot_step) & 4095` per axis, and everything else belongs to that angle.

What each step must leave behind:

| Step | Result |
|---|---|
| `update_angles` | `rot += rot_step`, each angle `& 4095` |
| `upload_matrix` | `mtx` = `RotMatrix(rot)` with translation `(0, 0, cam_z)`; both parts loaded into the GTE. A matrix built another way must equal `RotMatrix`'s `Rx * Ry * Rz` (5.5) to within 4 per entry |
| `transform_corners` | `screen_xy[i]`, `screen_z[i]` from `RTPS` of `cube[i]`; `gte_flags` |
| `draw_faces` | for each face `f` whose `NCLIP` of corners 0, 1, 2 is **positive**: one `POLY_F4` in `face_colors[f]`, corners `faces[f][0..3]` **in that order**, linked at slot `OTZ >> 7` where `OTZ` is `AVSZ4` of the face's four `screen_z`; the three counters updated |

With the shipped numbers the corners stay 17500 to 31700 units away: no divide overflow, `gte_flags` has no error bit (bit 12 may be set, see 5.6), and every quad is in slot 40 to 56.

### 7.3 Steps

1. `init_gte()`: `InitGeom()`, then the offset `(CX, CY)` and `proj_h`.
2. `update_angles()`.
3. `upload_matrix()`: `RotMatrix`, `TransMatrix` with a `VECTOR`, then `load_matrix(&mtx)` (given; it runs the two `gte_Set...Matrix` macros, 5.5).
4. `transform_corners()`: for each corner `gte_ldv0` / `gte_rtps` / `gte_stsxy` / `gte_stsz` / `gte_stflg` (5.6). OR the flags.
5. `draw_faces()`: for each face `gte_ldsxy3` of its first three corners, `gte_nclip`, `gte_stopz`; skip unless positive; `gte_ldsz4`, `gte_avsz4`, `gte_stotz`; then take a `POLY_F4` from `ot_alloc`, `setPolyF4`, `setRGB0`, the four corners (unpack the low and high halves of `screen_xy`), `ot_add`. Stop if `ot_alloc` returns `NULL`.
6. `make run`: a solid cube whose faces appear and vanish as it turns. Then `verify.sh`.

### 7.4 Rules

- **Use the GTE** for the transform, the culling test and the depth. The verifier looks for `RTPS`/`RTPT`, `NCLIP` and `AVSZ3`/`AVSZ4` in your own objects, and rejects calls from `main.c` to `psxe`'s CPU arithmetic (`fx_mul`, `fx_div`, `fx_rotate`, `fx_lerp`, `fx_sqrt`). No `float`/`double`.
- Read the tables and numbers from the symbols above; the verifier patches them (angles, speeds, colours, cube size, `cam_z`, `proj_h`) and expects the picture to follow.
- Do not write to `cube`, `faces`, `face_colors`, `rot_step`, `cam_z` or `proj_h`. Keep the keep-alive line in `main` and the three marker functions.
- Frame budget: at most 5,700 CPU cycles between `render_begin()` and `render_end()`: twice the reference solution's worst frame (about 2,850). `RotMatrix` is the expensive part: build the matrix once per frame. (Rebuilding it for every face blows the budget; transforming each face's four corners again, 24 transforms instead of 8, still fits.)

### 7.5 Hints

- *Every face is drawn all the time*: you do not test `NCLIP`, or you test `area != 0`.
- *The cube looks inside-out (you see the inside of the far faces)*: the test has the wrong sign. Positive is the front.
- *Some faces never appear*: you reordered the face table, or you use perimeter order.
- *The cube is not centred, or is tiny or huge*: `gte_SetGeomOffset` / `gte_SetGeomScreen`, or the matrix was never uploaded.
- *The cube does not move*: you updated `rot` but not the `mtx` upload, or you call `RotMatrix` on a copy.
- *`gte_ldsxy3` appears to load garbage*: it takes the three 32-bit values, not pointers.
- *Faces fight (the wrong one on top)*: slot too small or too large a shift; print the slots of the three faces and compare them with their depths.
- *The first frame is wrong, the rest right*: `InitGeom` or the offset ran after the first transform.

### 7.6 Stretch goals

- Add the third rotation: `rot_step.vz` (the verifier patches it).
- Light the faces: shade each by how much its normal points at the camera (the corners' cross product, or `NCLIP`'s area as a rough brightness).
- Transform with `gte_rtpt` three corners at a time and compare the cycle count (Chapter 27 does this properly).
- Two cubes, one inside the other, drawn in different sizes: where does average-Z sorting go wrong?
- Draw both sides of every face with different colours, using the sign of `NCLIP` instead of culling (the worked example, on a cube).

## 8. Verification

```sh
source tools/env.sh
parts/part-05-three-dimensions-with-the-gte/ch25-the-gte-coprocessor/verify/verify.sh            # your starter/
parts/part-05-three-dimensions-with-the-gte/ch25-the-gte-coprocessor/verify/verify.sh --solution # the reference
```

The probe records, every time the program calls `frame_done()`, the angles, `mtx`, `screen_xy`, `screen_z`, the flags, the counters, the cycles between the two markers, and the quads it finds by **walking the ordering table** handed to `DrawOTag` (slot, colour, corners). Python recomputes the cube: the same `RotMatrix`, the GTE's divide ported from psx-spx, and `NCLIP` on the reference corners.

| Check | What it means | If it fails |
|---|---|---|
| `the state symbols exist` | The labels of 7.2 and the marker functions are in the program | You removed a declaration or the keep-alive line |
| `the program uses the GTE...` | `objdump` of your objects (not the SDK's libraries) contains the GTE commands `RTPS`/`RTPT`, `NCLIP`, `AVSZ3`/`AVSZ4` | Missing macro; a software loop in its place |
| `the CPU does not redo the GTE's work` | `main.o` references no `fx_mul/fx_div/fx_rotate...` | Chapter 24's maths left in |
| `integers only` | No soft-float helper referenced | A `float` crept in |
| `frame loop...` | `frame_no` 1..120; `rot` equals `start + k * step` (`& 4095`); 0 to 3 quads; `faces_drawn` is the running total; `face_mask` has one bit per quad; the table walk finds exactly `prims_submitted` quads | Angles not wrapped; counters not reset; a primitive not linked, or linked but not counted |
| `matrix...` | `mtx` equals `RotMatrix(rot)` (each entry within 4, in 4.12) and its translation is `(0, 0, cam_z)` | Wrong angles; another rotation order; translation missing |
| `projection...` | `screen_xy` (1 px) and `screen_z` (exactly) equal what `RTPS` gives for your `mtx` | `InitGeom`, offset, `h`, matrix upload; the message tells if the centre is missing |
| `culling...` | In 120 frames, the faces drawn are exactly those the reference says face the camera (faces within an edge-on margin are not judged); never more than 3 | Test missing, wrong sign, wrong corner order |
| `sorting...` | Each quad sits in slot `(mean SZ / 4) >> 7` (+-1), and faces at different depths get different slots | A constant slot; `AVSZ3` with the wrong corners; a different shift |
| `picture (spinning...)` | Screenshots at frames 30 and 95: each visible face's centre has its colour; no pixel of any hidden face's colour; every lit pixel is a face colour | Wrong corners for a face; hidden faces drawn |
| `six frozen poses...` | `rot_step` patched to 0, six orientations showing 1, 2 and 3 faces: matrix, projection, culling, sorting and the picture | A face table with the wrong winding; anything that depends on motion |
| `colours come from face_colors[]` | A pose with the colour table permuted: the picture follows | Colours in code instead of the table |
| `patched lens, cube size, speeds and a third axis` | `h`, `cam_z`, size, steps on all three axes, start angles changed | A constant in place of `proj_h`, `cam_z`, a cube coordinate; `rot.vz` ignored |
| `GTE flags` | No error bit in the shipped run. With `cam_z` = 3000 (cube around the camera) bits 17 and 31 are set | Flags not read after every `RTPS`, or reset in between |
| `frame time` | At most 5,700 cycles between the markers | `RotMatrix` called more than once per frame; other repeated work |

A pass ends with `CHAPTER 25: PASSED (16/16 checks)`. Boot takes about 30 frames; the ten emulator runs take roughly 10 seconds.

## 9. Common pitfalls

- **Perimeter-order quads**: `0 1 3 2` instead of Z order `0 1 2 3` draws a bow tie.
- **Face tables written by feel**: some faces wind the other way, so they vanish when they should show. Use 5.7's rule or the given table.
- **`NCLIP` sign**: positive is front-facing (clockwise on screen) here; do not copy a rule from a Y-up tutorial.
- **Forgetting to upload**: `RotMatrix` and `TransMatrix` fill the C struct only.
- **Calling `gte_SetRotMatrix`/`gte_SetTransMatrix` inline**: PSn00bSDK 0.24's macros overwrite `$t0` and `$t1` but declare only `$t2` as clobbered, so a value the compiler keeps in `$t0`/`$t1` across them is silently destroyed (typically a pointer, and the program crashes later). Whether it happens depends on register allocation, so code that works can break after an unrelated edit. The starter's `load_matrix()` calls them inside a `noipa` function, which the compiler must assume clobbers every temporary register; use it.
- **Mixing units**: the translation is in vertex units, not 4.12; `gte_SetGeomOffset` takes whole pixels (the macro shifts them into 16.16).
- **Rotation order**: `RotMatrix` applies Z, then Y, then X; with Chapter 24's two angles you get a different tumble. Both are valid; the verifier knows this one.
- **Reading `SZ` too late**: the FIFOs hold only the last four results; store what you need straight after each transform.
- **Counting hidden faces**: `prims_submitted` is quads linked, not faces visited.
- **`gte_ldsxy3` takes values, `gte_ldv0` takes a pointer**: the macros are not uniform.
- **Slot out of range**: `ot_add` clamps, but a constant shift that sends every face to slot 63 loses the sorting without any error.
- **`RotAverageNclip4`, `RotTransPers` ...**: they are not in PSn00bSDK 0.24; code copied from Sony-era tutorials needs the macro sequences of 5.2.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- psx-spx (nocash PSX specs): "Geometry Transformation Engine (GTE)": "GTE Registers", "GTE Commands" (RTPS, NCLIP, AVSZ4), "GTE Division Inaccuracy", "GTE Flags".
- `.toolchain/opt/psn00bsdk/include/libpsn00b/psxgte.h` and `inline_c.h` (every macro of 5.2 has a comment with its equation).
- Pikuma, the PS1 course's lectures on the GTE and on back-face culling.
- Next: Chapter 26 gives every object its own transform, so one scene holds several moving cubes; Chapter 27 batches transforms with `RTPT` and measures GTE timing on a field of 64 cubes.
