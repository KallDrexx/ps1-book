# Chapter 24: 3D Projection Fundamentals

## 1. Concept

A 3D scene is a list of points in space. To draw it you **transform** the points (rotate, move, scale), then **project** them: divide x and y by the depth z, so far things shrink toward the center of the screen. Do that for every vertex, join the results with lines, and you have a wireframe.

## 2. Why it matters

Every PS1 3D game runs this pipeline for every vertex of every frame, and the GTE exists to do it fast. If you first do it by hand on the CPU, in the fixed-point numbers of Chapter 23, the GTE chapters become "the same steps, in hardware". You also meet the problems every renderer has: rotation order, rotation direction, and what happens when a point gets too close.

## 3. Learning objectives

After this chapter you can:

- describe the PS1's coordinate system (Y down, Z into the screen) and the stages model, world, view, perspective, screen;
- build rotation matrices for X, Y and Z, and say why the order of rotations matters;
- derive `x' = x * h / z` from similar triangles, and say what `h` controls;
- keep a mesh as a vertex array plus index lists (edges, faces);
- draw lines with `LINE_F2` primitives through the ordering table;
- explain what goes wrong when `z <= 0`, and how a design avoids it.

## 4. Prerequisites

[Chapter 23](../ch23-fixed-point-math/README.md) (`fx_mul`, `fx_div`, `fx_rotate`, angle units), [Chapter 20](../../part-04-c-on-the-playstation/ch20-primitives-and-ordering-tables/README.md) (primitives and the ordering table), [Chapter 21](../../part-04-c-on-the-playstation/ch21-working-with-multiple-files/README.md) (the `psxe` library). Part V's README lists the number formats.

## 5. Explanation

### 5.1 Coordinates

The PS1 (and its GTE) uses this system:

```
            Z (into the screen, away from you)
           /
          /
         +------ X (right)
         |
         |
         Y (down)
```

- **X** grows to the right, **Y grows downward** (like screen pixels), **Z grows away from the viewer**.
- The origin `(0,0,0)` is the center of the view. Screen pixels have their origin at the top-left, so the last step adds the center of the picture, `(160, 120)`.
- A point with positive z is in front of you. This chapter keeps every point at `z > 0`.

(Math texts usually draw Y up, with Z toward the viewer. Turn that system half a turn about X and you get this one, so it is still right-handed. You only need to remember: Y down, Z in.)

### 5.2 The pipeline

```
 model space      world space       view space       perspective        screen
 (the object's    (place and spin   (relative to     (divide by z)      (pixels)
  own corners)     it in the scene)  the camera)
 +-----------+    +-----------+    +-----------+    +-----------+    +-----------+
 | cube[i]   | -> | rotate    | -> | translate | -> | x*h/z     | -> | +(160,120)|
 | +-1.0 ... |    | X then Y  |    | z += cam_z|    | y*h/z     |    |           |
 +-----------+    +-----------+    +-----------+    +-----------+    +-----------+
```

| Space | Meaning | Here |
|---|---|---|
| **Model** | Coordinates relative to the object's own center | `cube[]`: corners at +-1.0 |
| **World** | Where the object sits and how it is turned | rotated about its center |
| **View** | Relative to the camera, which sits at the origin and looks along +Z | the cube pushed `cam_z` along Z |
| **Screen** | Pixels | divide by z, scale, add the center |

Real games have one matrix per object (model to world) and one for the camera (world to view). Here the camera never moves, so the two steps merge: spin the cube, push it away. Chapter 28 adds a real camera.

### 5.3 Rotation

Rotating about an axis leaves that axis's coordinate alone and turns the other two. Each is a 2D rotation in a plane, which is Chapter 23's `fx_rotate(u, v, angle, &out)`. With `c = cos(a)` and `s = sin(a)`:

| About | Unchanged | New coordinates | `fx_rotate` inputs |
|---|---|---|---|
| X | x | `y' = y*c - z*s`, `z' = y*s + z*c` | `y, z, a` |
| Y | y | `z' = z*c - x*s`, `x' = z*s + x*c` | `z, x, a` |
| Z | z | `x' = x*c - y*s`, `y' = x*s + y*c` | `x, y, a` |

The pairs follow the cycle X, Y, Z, X: the first coordinate of the pair plays `fx_rotate`'s `x` (and comes back in `out.x`), the second its `y`. Angles are 4096 units per turn. A **positive angle** acts like this:

| Angle | Effect on a point |
|---|---|
| positive `angle_x` | a point on +Y (below the center) moves toward +Z (away from you) |
| positive `angle_y` | a point on +Z (far) moves toward +X (to the right) |
| positive `angle_z` | a point on +X (right) moves toward +Y (down): clockwise on screen |

Check one yourself: angle 1024 (a quarter turn) gives `c = 0`, `s = 4096`, so `(0, 1, 0)` rotated about X becomes `(0, 0, 1)`.

**Order matters.** Rotations do not commute: turn a book a quarter turn about X and then about Y, then try it in the other order, and it ends up lying differently. "X then Y" means: apply the X rotation to the vertex first, then rotate the result about Y, so the Y rotation sees coordinates the X rotation already changed.

**Rotate, then translate.** A rotation always turns about the origin. Rotating after moving the cube away would swing it around the camera. So: rotate in model space, then add the offset.

You can instead multiply the rotation matrices into one 3x3 matrix once per frame and apply that to every vertex: 9 multiplies per vertex against 8 for two `fx_rotate` calls, but still 9 however many rotations you combine. The GTE works that way (Chapter 25). Here, two `fx_rotate` calls per vertex are clearer.

### 5.4 Translation and scaling

**Translation** adds an offset to each coordinate: `z' = z + cam_z`. **Scaling** multiplies each coordinate by a factor, `x' = fx_mul(x, k)`, where 4096 means "unchanged". Scaling is a matrix too (a diagonal one); the vertex table's `+-size` is a scale of the unit cube.

### 5.5 Perspective

Put the viewer's eye at the origin and a screen (a flat window) at distance `h` in front of it. A point `(x, y, z)` is seen where the line from the eye to the point crosses the window.

Side view (the Y axis would look the same):

```
        screen
          |       . P (x, z)
          |     .
    x' -> +---.            two similar triangles, same apex (the eye):
          | .                 x' / h  =  x / z
 eye +----+------------+--->  so   x' = x * h / z
     0    h            z
```

- `h` is the **projection distance**, measured in pixels. It sets the **field of view**: the half-width of the screen is 160 pixels, so the half-angle is `atan(160 / h)`. With `h = 256` that is 32 degrees (a 64-degree view). A smaller `h` is a wider lens: more of the scene fits on screen and everything is drawn smaller.
- Farther points (larger z) get a smaller `x'`: they shrink toward the center. A point at `z = 2h` lands half as far from the center as the same point at `z = h`.
- Y works the same way: `y' = y * h / z`. Y is already "down", so no sign change is needed.
- Finally the center: `screen_x = 160 + x'`, `screen_y = 120 + y'`.

In fixed point, divide first, then scale by the integer `h` (Chapter 23's `fx_div` returns a 20.12 ratio, so its product with `h` carries 12 fraction bits):

```
screen_x = 160 + ((fx_div(x, z) * h) >> 12)
```

The ratio keeps 12 fraction bits, and for points in view it is small, so the product stays far from 32-bit overflow. A `div` costs 36 cycles on the R3000 (Chapter 12). Two per vertex, 16 per frame, is cheap here; for thousands of vertices it is not, which is one reason the GTE has its own divider.

**The camera offset.** The cube's corners are +-1.0 around the origin. Left alone, half of them have `z < 0`, so you push the cube `cam_z` away. The cube's corners reach `size * sqrt(3)` from the center (about 1.73 for size 1), and after rotation any of them can be nearest, so `z_min = cam_z - 1.73 * size`. Pick `cam_z` large enough that this stays positive with room to spare, and small enough for the cube to fill a decent part of the screen. This chapter: `cam_z = 6.0`, `h = 256`.

### 5.6 What happens at z <= 0

The projection divides by z. Three cases:

| z | Result |
|---|---|
| tiny positive | the point shoots far off screen (x/z becomes huge); big coordinates also overflow `int16_t` in the primitive |
| `0` | division by zero. `fx_div` saturates (`INT32_MAX` or `INT32_MIN`): garbage coordinates |
| negative | the point is **behind** the camera, but the formula still gives an answer: the point is mirrored through the center (x/z flips sign), so a line from it to a point in front of you is drawn across the screen in the wrong direction |

Renderers fix this by **clipping against a near plane**: choosing a minimum `z = near` and cutting off everything closer, before the divide. This chapter avoids the problem by design (`z_min` above). Chapter 28 comes back to it.

### 5.7 Meshes

A **mesh** is geometry stored as numbers. The cube is a **vertex array** of 8 points, plus **index lists** that name vertices by number:

```
        4--------5            vertex i:  bit 0 = x (+),  bit 1 = y (+),  bit 2 = z (+)
       /|       /|            0 = (-,-,-)   1 = (+,-,-)   2 = (-,+,-)   3 = (+,+,-)
      0--------1 |            4 = (-,-,+)   5 = (+,-,+)   6 = (-,+,+)   7 = (+,+,+)
      | 6------|-7
      |/       |/             (as on screen: x right, y down; the near face is 0-1-3-2,
      2--------3               the far face 4-5-7-6)
```

- An **edge list** (12 pairs) is enough for a wireframe: this chapter.
- A **face list** holds four (quad) or three (triangle) indices per face; the cube has 6 quad faces. Chapter 25 draws faces.

Why indices? A corner belongs to three edges and three faces. Storing it once and referring to it by number means each vertex is **transformed once** per frame, however often it is used, and the edges that share it always meet. The projected positions go into an array parallel to the vertex array (`projected[i]` belongs to `cube[i]`), and the lists are looked up in it.

### 5.8 Drawing lines: `LINE_F2`

The GPU draws one-pixel-wide lines with a **line primitive**. In `LINE_F2`, `F` means flat color and `2` two points. From PSn00bSDK's `<psxgpu.h>`:

| Item | |
|---|---|
| `LINE_F2` | fields `r0 g0 b0` (color), `x0 y0`, `x1 y1` (`int16_t`), plus the tag and command byte |
| `setLineF2(p)` | sets the tag length (3 words) and the command code |
| `setRGB0(p, r, g, b)` | color |
| `setXY2(p, x0, y0, x1, y1)` | both end points |

It goes into the ordering table like the polygons of Chapter 20: take a packet with `ot_alloc(sizeof(LINE_F2))` (it returns `NULL` when the frame's buffer is full), fill it, and link it with `ot_add(p, depth)`. The coordinate fields are 16-bit, but a line may not span more than 1023 pixels across or 511 down: the GPU silently drops longer ones.

**Where is `gfx_line`?** There is none: `psxe`'s `gfx` module stays as Chapter 21 left it (`gfx_quad_f4` only). Filling a line takes about ten lines of code, and you write them in `main.c` from the table above.

## 6. Worked example

`example/` is a tunnel: eight squares one unit apart in depth, drifting toward the camera. There is no rotation, only the perspective divide, so you see its effect alone.

```sh
source tools/env.sh
cd parts/part-05-three-dimensions-with-the-gte/ch24-3d-projection-fundamentals/example
make run
```

Try each of these:

1. Change `H` from 200 to 100, then to 400. What changes: the size of the squares, or the way they bunch toward the center? (Only the size: `H` multiplies every coordinate alike, so the ratio between a near and a far square, which depends on their depths alone, stays the same.)
2. In `sx` and `sy`, divide by a constant (say `3 * FX_ONE`) instead of `z`. The eight squares become identical and coincide: without the divide by z there is no depth.
3. Delete the wrap (the `if (z0 < NEAR)` line and its body). What happens as the nearest square's `z` approaches 0 and then goes negative (5.6)?

## 7. Project: "Software Cube"

Rotate and project a wireframe cube on the CPU and draw its twelve edges. **No GTE:** only `psxe/fixed.h` and integer code.

### 7.1 Behavior

A white wireframe cube, spinning about two axes, in the middle of a dark blue screen (`display_clear(16, 16, 32)`). Every frame the angles grow by fixed steps, the eight corners are rotated and projected, and the twelve edges are drawn as white `LINE_F2` lines between the projected corners.

### 7.2 The contract

`starter/main.c` declares this state (do not change names, types or initial values):

| Symbol | Type | Initial | Meaning |
|---|---|---|---|
| `cube[8][3]` | `int16_t` | corners, +-4096 | Corner `i`: x = +4096 if bit 0 of `i` is set, else -4096; y from bit 1, z from bit 2. 4.12, so +-1.0 |
| `edges[12][2]` | `uint8_t` | pairs of corner indices | Given: `{0,1} {2,3} {4,5} {6,7}` (along x), `{0,2} {1,3} {4,6} {5,7}` (along y), `{0,4} {1,5} {2,6} {3,7}` (along z) |
| `projected[8][2]` | `int16_t` | 0 | You fill it: screen `x, y` of corner `i` in `projected[i][0]`, `projected[i][1]`. 32 bytes, row-major |
| `angle_x`, `angle_y` | `int32_t` | 128, 256 | Current angles, 4096 = one turn, always kept in `0..4095` |
| `step_x`, `step_y` | `int32_t` | 24, 40 | Added to the angles every frame (may be negative) |
| `cam_z` | `int32_t` | 24576 | Distance 6.0 (20.12): added to every z after rotating |
| `proj_h` | `int32_t` | 256 | Projection distance `h`, in pixels |
| `frame_no` | `int32_t` | 0 | Frames completed (the given loop increments it) |

Per frame, for each corner `i` (work in `fx`; the `int16_t` table entries are used as they are):

| Step | Computation |
|---|---|
| 1 | `x, y, z = cube[i]` |
| 2 | rotate about X: `fx_rotate(y, z, angle_x, &r)`; `r.x` is the new `y`, `r.y` the new `z` |
| 3 | rotate about Y: `fx_rotate(z, x, angle_y, &r)`; `r.x` is the new `z`, `r.y` the new `x` |
| 4 | `z += cam_z` |
| 5 | `projected[i][0] = 160 + ((fx_div(x, z) * proj_h) >> 12)` |
| 6 | `projected[i][1] = 120 + ((fx_div(y, z) * proj_h) >> 12)` |

Frame order (the loop in `main` is given): `update_angles` (add the steps, `& 4095`), `project_cube`, `draw_edges`, draw and swap, `frame_no++`, `frame_done()`. So when `frame_done()` is called with `frame_no == k`, `angle_x == (128 + 24 * k) & 4095` and `projected` belongs to those angles.

The verifier computes the same thing in Python (the SDK's `isin`/`icos` ported exactly, `fx_rotate`'s single shift, `fx_div`'s truncation toward zero, and `>> 12` as an arithmetic shift, which rounds toward minus infinity). Follow the table and you match it exactly. It accepts 1 pixel of difference, enough for computing `x * proj_h / z` directly or for multiplying the two rotations into one matrix first. Use `fx_rotate` from `psxe`, not a sine table of your own: the SDK's `isin`/`icos` differ from the true sine by up to 12/4096 (Chapter 23), which can cost a second pixel.

With the shipped numbers the corners stay within x = 82..237 and y = 47..192, always on screen, and z never drops below about 4.26.

### 7.3 Steps

1. `update_angles()`: add the steps and wrap with `& 4095` (so negative steps work too).
2. `project_cube()`: the table of 7.2, as a loop over the eight corners.
3. `draw_edges()`: for each edge, take a `LINE_F2` from the ordering table (5.8), color `255, 255, 255`, end points from `projected[a]` and `projected[b]`, `ot_add(..., 0)`. If `ot_alloc` returns `NULL`, stop drawing.
4. `make run`: the cube should spin, its far corners visibly closer together than its near ones. Then run `verify.sh` (section 8).

### 7.4 Rules

- Integers only. No `float`/`double`.
- **No GTE**: no `gte_*` macros, no SDK GTE routines (`RotTransPers`, `RotMatrix`, `InitGeom`, ...) and no COP2 instruction anywhere in your objects. (`isin`/`icos` are ordinary integer routines and are fine.)
- Read the tables and numbers from the symbols above; the verifier patches them (a different cube size and edge table, steps, start angles, `cam_z`, `proj_h`) and expects the picture to follow.
- Do not write to `cube`, `edges`, the steps, `cam_z` or `proj_h`, and keep the starter's `__asm__ volatile` line at the top of `main` (it keeps the state linked in).

### 7.5 Hints

- *Cube looks flat or its edges do not meet*: you project `x` without dividing by z, or divide by the unrotated z.
- *The cube is mirrored or spins the "wrong" way*: check which `fx_rotate` output is which coordinate (7.2, steps 2 and 3).
- *It wobbles instead of tumbling*: the X and Y rotations act on the same original `x, y, z` instead of on each other's output.
- *The cube sits in the top-left corner*: you did not add the screen center, `(160, 120)`.
- *A rotation seems to do nothing*: `fx_rotate`'s `out` is a struct; copy both fields back before the next step.
- *Lines on the wrong side of the screen*: Y is down; do not negate it.
- *Build error `undefined reference to fx_...`*: `fixed.c` is part of `libpsxe.a`; link `psxe` (the starter's CMake does).

### 7.6 Stretch goals

- Add a Z rotation (`angle_z`, third `fx_rotate`) and a third step.
- Draw the six faces' edges from a **face list** (4 indices per face) instead of the edge list; every edge gets drawn twice, which tells you why edge lists exist.
- Scale: make the cube pulse with `fx_mul(x, k)`, `k` varying between 0.5 and 1.0.
- Make `cam_z` smaller until the cube reaches the camera and watch the cases of 5.6 happen. Then skip every edge that has an endpoint with `z < near`.
- Shade each edge by the average `z` of its endpoints (still `LINE_F2`, one color per line), and sort the edges through the ordering table: depth = average z, scaled to 0..63.
- Add a second cube with a different size and speed.

## 8. Verification

```sh
parts/part-05-three-dimensions-with-the-gte/ch24-3d-projection-fundamentals/verify/verify.sh
```

The probe watches `frame_done()` for 120 frames in three runs and records `frame_no`, the angles and `projected[]`. Python recomputes the cube from the recorded angles; screenshots at frames 30 and 95 check the drawing.

| Check | What it means | If it fails |
|---|---|---|
| `the state symbols exist` | The symbols of 7.2 are in the program | You removed a declaration, or the starter's keep-alive line at the top of `main` |
| `no GTE in the sources` | No `gte_*`, `RotTransPers`, `inline_c.h`... in your `.c`/`.h` | Use `fixed.h` |
| `no GTE instruction or SDK GTE routine in the program's own objects` | `objdump` of your objects (not the SDK's libraries) has no `mtc2/mfc2/ctc2/cfc2/lwc2/swc2/cop2`, and they reference no libpsxgte routine except `isin`/`icos` | A GTE macro or SDK call; remove it |
| `integers only` | No soft-float helper referenced | A `float` crept in |
| `frame loop ...` | `frame_no` is 1, 2, 3...; the angles equal `(start + k * step) & 4095` | Missing `& 4095`; steps added twice; angle updated at the wrong place |
| `projected[] matches the reference` | 120 frames, every corner within 1 px | Rotation order, direction, no divide, no center. The message tells you which of these fits your numbers |
| `patched ... the program follows its data` | Smaller cube, other edge table, negative step, other start angles | Constants instead of the symbols |
| `patched projection distance...` | `proj_h = 200`, `cam_z = 5.5`, bigger cube | Constants instead of `proj_h`/`cam_z` |
| `picture ...` (two checks) | Five samples along each of the 12 edges are white; every lit pixel is within 2 px of an edge; the screen's corners are background | Lines missing or drawn from the wrong array; leftover primitives; not cleared |

A pass ends with `CHAPTER 24: PASSED (11/11 checks)` (the eleventh check only concerns the book's own solution). Boot takes about 30 frames; the three runs take roughly 10 seconds.

## 9. Common pitfalls

- **Rotating the table in place**: rotate local copies of each vertex. If you write the result back into `cube[]`, the error accumulates and the cube drifts and shrinks.
- **Translating before rotating**: the cube orbits the camera instead of spinning in place.
- **Dividing without widening**: `(x << 12) / z` overflows 32 bits once `|x|` reaches 128.0. `fx_div` switches to 64 bits when it must; the multiply by `h` is safe because the ratio is small.
- **`>>` on negative numbers**: an arithmetic shift rounds toward minus infinity, so with `(a * h) >> 12` a negative offset can land one pixel farther from the center than its positive twin. The contract fixes the rule.
- **Angle wrap**: `angle % 4096` is negative for a negative angle in C; use `& 4095`.
- **Y up**: a textbook projection for Y up negates y on the way to the screen; copied here it flips the picture. On the PS1 Y is already down.
- **`z <= 0`**: mirrored or exploding geometry; design `cam_z` so it cannot happen (5.6).
- **Unreferenced state**: the linker removes data nothing refers to. The `__asm__ volatile` line at the top of `main` keeps the state alive; leave it in.
- **Line length**: a `LINE_F2` wider than 1023 or taller than 511 pixels is dropped.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- psx-spx (nocash PSX specs): "GPU Render Line Commands", and under "Geometry Transformation Engine (GTE)" the section "GTE Coordinate Calculation Commands" (`RTPS`) for the same pipeline in hardware.
- `.toolchain/opt/psn00bsdk/include/libpsn00b/psxgpu.h` (`LINE_F2`, `setLineF2`, `setXY2`).
- Pikuma, "Perspective Projection" and "3D Rotation and Matrices" lectures in the PS1 course; any computer-graphics text on the pinhole camera.
- Next: Chapter 25 hands the rotate-translate-project steps to the GTE.
