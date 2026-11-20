# Chapter 26: Multiple Objects and Simple Motion

## 1. Concept

The GTE holds **one** rotation matrix and **one** translation at a time. To draw several objects you give each its own transform: build it, load it into the GTE, transform that object's vertices, then move on to the next object. Add a little physics (gravity, a floor) and the objects move on their own.

## 2. Why it matters

Chapter 25 drew one cube. Every real scene has many things, each with its own position, orientation and size. The pattern of this chapter, *per object: build matrix, upload, transform, draw*, is the inner loop of every PS1 3D game. Chapter 27 makes it fast; Chapter 28 puts a camera in front of it.

## 3. Learning objectives

After this chapter you can:

- explain why the GTE's matrix must be uploaded again for every object;
- build an object's matrix from angles, size and position, and compose it with a camera (world) matrix;
- say what `PushMatrix`/`PopMatrix` really do, and when explicit re-uploading is the better tool;
- integrate velocity and gravity in fixed point, in a stated order, and bounce off a plane;
- draw a floor as a grid of quads behind everything else;
- give objects and floor the ordering-table slots that make the picture right.

## 4. Prerequisites

[Chapter 25](../ch25-the-gte-coprocessor/README.md) (the `gte_*` macros, `RotMatrix`, NCLIP, AVSZ4, OT slots), [Chapter 23](../ch23-fixed-point-math/README.md) (`fx_mul`, 20.12, angle units), [Chapter 20](../../part-04-c-on-the-playstation/ch20-primitives-and-ordering-tables/README.md) (ordering tables), [Chapter 21](../../part-04-c-on-the-playstation/ch21-working-with-multiple-files/README.md) (`psxe`).

## 5. Explanation

### 5.1 One matrix at a time

`RTPS` always multiplies by whatever is in the GTE's `RT` and `TR` registers *right now*. It has no idea which object a vertex belongs to.

```
 object A's matrix                          object B's matrix
        |                                          |
        v                                          v
  upload to RT/TR --> 8 x RTPS --> quads    upload to RT/TR --> 8 x RTPS --> quads
        (A's corners, A's place)                  (B's corners, B's place)
```

Forget the second upload and B's corners are transformed with A's matrix: B lands exactly on A (the worked example in section 6 shows it). So the loop is always:

| Step | Per object |
|---|---|
| 1 | build a `MATRIX` from this object's angles, size, position |
| 2 | compose it with the camera |
| 3 | upload it: `gte_SetRotMatrix`, `gte_SetTransMatrix` (the starter's `load_matrix` does both) |
| 4 | transform its vertices, cull, sort, emit quads |

The vertices (the unit cube) are shared by all objects. Only the matrix differs.

### 5.2 Building the object matrix

| Call | Effect | Note |
|---|---|---|
| `RotMatrix(&rot, &m)` | `m` = rotation from three angles (4096 per turn), `Rx * Ry * Rz` | Chapter 25 |
| `ScaleMatrix(&m, &s)` | multiplies **column** `j` of `m` by `s.v[j] / 4096` | a `VECTOR`; `4096` leaves it unchanged |
| `TransMatrix(&m, &pos)` | sets `m.t` | plain integer units, not 4.12 |

Scaling the columns scales the *model* before it is rotated, so a unit cube with corners at +-4096 becomes a cube with corners at +-`size` when `s = (size, size, size)`. Matrix entries are `int16`, so `size` must stay below 32768. One shared model, three sizes: no vertex data is copied.

### 5.3 Composing with the world: `CompMatrixLV`

Objects live in the **world**; the camera sits somewhere in it. The GTE needs *object to view* in one step. `CompMatrixLV(&a, &b, &out)` multiplies two matrices:

```
  out.R = a.R * b.R
  out.T = a.R * b.T + a.T                 a = camera (world to view), b = object (model to world)
```

(It does this on the GTE, so it leaves `a` loaded in `RT`/`TR` as a side effect: upload `out` yourself afterwards. `b.T` passes through 16-bit GTE registers, so each component must stay within +-32767.)

This chapter's camera is a **fixed translation**: `cam_mtx` has an identity rotation (4096 on the diagonal) and `T = cam`, so `out.T` is the object's world position plus `cam`. The call looks like overkill now. In Chapter 28 `cam_mtx` gets a real rotation and the same call does all the work.

```
  model (+-4096) --ScaleMatrix/RotMatrix--> object axes --TransMatrix--> world --cam_mtx--> view --RTPS--> screen
                        (per object)             (per object)                   (shared)       (shared)
```

### 5.4 Saving and restoring GTE state

What if the GTE holds a matrix you want back later? Two tools:

| Tool | What it is | Limits |
|---|---|---|
| `PushMatrix()` / `PopMatrix()` | copy the GTE's `RT` and `TR` (8 control registers) to / from one static buffer in the library | **one level**: no nesting; a second push overwrites the first |
| Re-upload | keep the `MATRIX` in a C variable, upload it again (`load_matrix`) | costs one upload (8 control-register writes) |

There is a trap: `RotMatrix` uses the same slot. It calls `PushMatrix` on entry and `PopMatrix` on exit (it borrows the GTE's `RT` to multiply the three axis matrices with `MulMatrix0`, then puts back whatever was loaded). So after any `RotMatrix` call the slot holds what the GTE held *when `RotMatrix` started*, not what you pushed: push A, upload B, call `RotMatrix`, pop, and you get B back. In 0.24 only `RotMatrix` and `HiRotMatrix` touch the slot; `MulMatrix0` and `CompMatrixLV` leave it alone but overwrite the GTE's matrix registers themselves.

This chapter re-uploads: every object's matrix is built into its own local `MATRIX`, which is also the copy you would restore from. You never need the old state, because each object loads its own.

### 5.5 Motion in fixed point

All motion is along **y**, which points **down** (Chapter 24). Positions and velocities use Chapter 23's **20.12** format: 4096 means one world unit (per frame, for velocity).

| Quantity | Format | Meaning |
|---|---|---|
| `y` | 20.12 | the cube's centre; `y >> 12` is the world unit used for drawing |
| `vy` | 20.12 | units per frame, positive = falling |
| `gravity` | 20.12 | units per frame per frame (4 units = 16384) |
| `bounce` | 4.12 | restitution: the fraction of speed kept (3277 = 0.80) |

**The update order is part of the contract.** Per object, per frame:

```
  vy += gravity
  y  += vy
  limit = (floor_y - radius) << 12          the lowest centre allowed
  if y > limit:
      y  = limit                              sit exactly on the floor
      vy = -fx_mul(vy, bounce)                reverse, lose some speed
      bounces += 1
  angles: a = (a + step) & 4095, each axis on its own
```

This is **semi-implicit (symplectic) Euler**: velocity first, then position with the *new* velocity. Update position first and the numbers differ, and the verifier compares every frame **exactly**.

The result is a parabola for each hop, and each hop is lower than the last by the factor `bounce` (the speed at the top is 0; the speed at the bottom is what is kept):

```
  y (up)
   ^   .-.                          each arc: v = g * t,  y = g * t^2 / 2
   |  /   \     .-.                 speed after the bounce = bounce * speed before
   | /     \   /   \    .-.
   |/       \ /     \  /   \  .-.
 --+---------V-------V-/-----V/---V----> frame
   0       floor     contacts
```

**Integration error.** Real physics is continuous; the loop is not. A cube falling from rest for `n` frames drops `g * n * (n + 1) / 2`, not `g * n^2 / 2`: the sum of `n` steps, not the area under a line. And when it lands, the part of the last step that went *below* the floor is thrown away, so each bounce loses a little more energy than `bounce` says. Both effects are small at this size and speed. The only requirement is that every run of the same numbers gives the same frames, which exact integer arithmetic guarantees.

**At rest.** With a low `bounce` the hops shrink until the speed kept is less than one frame of gravity. From then on the test fires *every* frame: `y` stays clamped at `limit`, `vy` settles near `gravity * 4096 / (4096 + bounce)` going in and minus that times `bounce / 4096` going out, and `bounces` grows by one per frame. That is part of the model; the verifier's patched run contains a cube that does it. (The "rest" stretch goal changes this, so keep it out of the build you verify.)

`vy * bounce` exceeds 32 bits at these speeds (900,000 x 3,500 > 2^31). `fx_mul` multiplies in 64 bits and then shifts; the C expression `vy * bounce >> 12` on `int32_t` overflows.

**Collision with a plane** is one comparison, as above. A cube is not a sphere, so `radius` is a **bounding radius** (centre to floor at rest): this chapter uses `5/4` of the half-edge. A flat cube then hovers a little above the floor, and a tilted one sinks a corner into it. Exact contact would transform the corners first (stretch goal).

### 5.6 The floor: a grid of quads

A **checkerboard** of 8 x 6 tiles, each 2048 units wide, in the plane `y = floor_y`, centred on x = 0, z = 0. Corner `(c, r)` of the grid, with `0 <= c <= 8` and `0 <= r <= 6`:

```
  x = (c - 4) * 2048        y = floor_y        z = (r - 3) * 2048

      far (large z)
   r=6  +---+---+---+---+---+---+---+---+
        |   |   |   |   |   |   |   |   |
   r=5  +---+---+---+---+---+---+---+---+          tile (c, r) has corners
        |   ...                         |             (c, r+1) (c+1, r+1)   far-left, far-right
   r=0  +---+---+---+---+---+---+---+---+             (c, r)   (c+1, r)     near-left, near-right
      near     c=0                  c=8                (Z order, seen from above)
```

Transform the 9 x 7 = 63 grid corners **once**, not 4 per tile: neighbouring tiles share them. Tile `(c, r)` gets colour `(c + r) & 1` of the two floor colours. Seen from above in Z order the corners run clockwise, so `NCLIP` is positive (Chapter 25's rule: look at the face from outside).

The floor's matrix is the camera's own: an identity rotation and `T = cam`. The floor is "object zero" of the scene.

### 5.7 Depth: where do the floor and the cubes go?

Chapter 25 sorted by the average depth of each face. Do that for the cube faces. The floor does **not** need it:

- floor tiles never overlap each other, so their order among themselves does not matter;
- every cube is above the floor, so the floor is always the farthest thing.

Put every floor quad in the **farthest slot** (`OT_LENGTH - 1`, 63). A cube face's slot is `OTZ >> 7` with the camera at 14336 units: about 23 to 31, always nearer. Cubes then draw over the floor, with no per-tile sorting. Per-face sorting still decides which of the three cubes is in front where they overlap on screen. It is a painter's-algorithm approximation (Chapter 25): good for objects that do not interpenetrate.

**Budget.** The primitive buffer holds 2048 bytes: 85 `POLY_F4`s (24 bytes each). The scene needs at most 48 floor quads + 9 cube faces (3 per cube) = 57.

## 6. Worked example

`example/` draws two cards, each spinning at its own speed, one on each side. As shipped, the second card's matrix is **never uploaded**.

```sh
source tools/env.sh
cd parts/part-05-three-dimensions-with-the-gte/ch26-multiple-objects-and-simple-motion/example
make run
```

Try each of these:

1. Run it as shipped (`FORGET_UPLOAD 1`). Where is the green card? (Exactly where the red one is, with the same spin: it was transformed with the red card's matrix. You see only red, because in one OT slot the quad added last is drawn first.)
2. Set `FORGET_UPLOAD` to 0. Both cards turn independently. Which line made the difference?
3. Swap the order: draw the green card first. Which card is "wrong" now?

## 7. Project: "Bouncing Cubes"

Three cubes of different sizes bounce on a checkerboard floor, each spinning about a different axis.

### 7.1 Behaviour

Dark-blue background (`display_clear(24, 24, 48)`), an 8 x 6 floor of two greys, a red, a green and a blue cube falling, bouncing with decreasing height, and turning. Cubes are always drawn over the floor and the visible faces are shaded.

### 7.2 The contract

`starter/main.c` declares this state. Do not change names, types, order or initial values: the verifier reads **and patches** it.

**`objects[3]`**, an array of `Object`, 15 `int32_t` fields each, in this order:

| # | Field | Meaning |
|---|---|---|
| 0 | `x` | world x of the centre (units) |
| 1 | `y` | world y of the centre, **20.12**; grows downward |
| 2 | `z` | world z of the centre (units) |
| 3 | `vy` | vertical velocity, 20.12 units per frame |
| 4-6 | `ax`, `ay`, `az` | angles about X, Y, Z, kept in 0..4095 |
| 7-9 | `sx`, `sy`, `sz` | added to the angles every frame (may be negative) |
| 10 | `size` | half the cube's edge (units) |
| 11 | `radius` | collision radius (units) |
| 12 | `bounce` | restitution, 4.12 |
| 13 | `colour` | `r | g << 8 | b << 16` |
| 14 | `bounces` | floor contacts so far (you maintain it) |

Initial values:

| | red | green | blue |
|---|---|---|---|
| `x`, `z` | -4400, -1200 | 0, 1800 | 4400, 0 |
| `y` (units) / `vy` (units per frame) | -3000 / 0 | -4000 / -60 | -2500 / 30 |
| `ax, ay, az` | 300, 0, 120 | 0, 500, 200 | 700, 150, 0 |
| `sx, sy, sz` | 0, 56, 0 | 40, 0, 0 | 0, 0, -48 |
| `size` / `radius` | 1200 / 1500 | 1700 / 2125 | 2200 / 2750 |
| `bounce` | 3277 (0.80) | 2867 (0.70) | 3482 (0.85) |
| `colour` | (224, 48, 48) | (48, 200, 64) | (64, 96, 240) |

Other state:

| Symbol | Type | Initial | Meaning |
|---|---|---|---|
| `gravity` | `int32_t` | 16384 | 20.12 units per frame squared (4.0) |
| `floor_y` | `int32_t` | 4096 | the floor's world y (units); the eye is at y = 0 |
| `cam` | `VECTOR` | (0, 0, 14336) | the fixed camera translation |
| `proj_h` | `int32_t` | 256 | projection distance; offset (160, 120) |
| `cube[8]`, `faces[6][4]` | | Chapter 25's tables, +-4096 | the shared model |
| `face_shade[6]` | `uint16_t` | 256, 208, 176, 232, 192, 160 | face `f` colour = channel `* shade >> 8` |
| `floor_colors[2][3]` | `uint8_t` | (72, 72, 96), (168, 168, 190) | tile colour `(c + r) & 1` |
| `cam_mtx` | `MATRIX` | you build it | identity rotation, translation `cam` |
| `frame_no` | `int32_t` | 0 | frames completed (the given loop increments it) |

Frame order (the loop in `main` is given): `display_clear`, `ot_begin_frame`, **`render_begin()`**, `update_objects`, `draw_floor`, `draw_object` for each cube, **`render_end()`**, `ot_draw`, `display_swap`, `frame_no++`, `frame_done()`. At `frame_done()` with `frame_no == k`, `objects` has had `k` updates.

What each step must leave behind:

| Step | Result |
|---|---|
| `init_world` | `cam_mtx` built once |
| `update_objects` | the update of 5.5 for each of the three objects |
| `draw_floor` | 48 `POLY_F4` in slot 63: corners from the 9 x 7 grid, colour `(c + r) & 1`, culled by `NCLIP` |
| `draw_object` | its own matrix uploaded; one `POLY_F4` per face with positive `NCLIP`, colour from `colour` and `face_shade`, slot `AVSZ4 >> 7` |

The object's matrix: `RotMatrix` of its angles, `ScaleMatrix` by `(size, size, size)`, `TransMatrix` to `(x, y >> 12, z)`, `CompMatrixLV` with `cam_mtx`.

### 7.3 Steps

1. `init_world()`: identity on the diagonal of `cam_mtx.m`, then `TransMatrix` with `cam`.
2. `update_objects()` (5.5). Use `fx_mul` from `psxe/fixed.h`.
3. `draw_floor()`: upload `cam_mtx` with `load_matrix`; loop over the 63 corners with `gte_ldv0` / `gte_rtps` / `gte_stsxy` into a 7 x 9 array; loop over the tiles with `gte_ldsxy3` / `gte_nclip` / `gte_stopz`; `put_quad` (given).
4. `draw_object()`: build, compose, upload (5.2, 5.3); eight corners with `gte_rtps` keeping `SXY` and `SZ`; per face `gte_nclip`, `gte_ldsz4`, `gte_avsz4`, `gte_stotz`, `put_quad`.
5. `make run`: three cubes bouncing, each with its own spin. Then `verify.sh`.

### 7.4 Rules

- **Use the GTE** for transforms, culling and depth; the verifier looks for `RTPS`/`RTPT`, `NCLIP` and `AVSZ3`/`AVSZ4` in your own objects.
- **No `float`/`double`**: the physics is integer.
- Read every number from the symbols above; the verifier patches positions, velocities, gravity, restitution, floor height, sizes, spins, colours, the camera and the lens, and expects the same exact physics and a matching picture.
- Keep the keep-alive line in `main` and the three marker functions. Do not write to `cam`, `gravity`, `floor_y`, `proj_h`, or the model tables.
- Frame budget: at most 59,500 CPU cycles between `render_begin()` and `render_end()`: twice the reference solution's frame (about 29,750). Transform each vertex once and build each matrix once.

### 7.5 Hints

- *All cubes look the same, or sit in one spot*: one matrix for all (5.1). Build and upload inside the per-object function.
- *Cubes spin together*: they share one angle. Each object has its own `ax`, `ay`, `az`.
- *The bounce is slightly off*: update order (5.5); `fx_mul` on the *new* `vy`; the clamp on `y`.
- *A cube is drawn under the floor*: floor slot is not the farthest.
- *Cubes jump to the wrong place when the camera is patched*: the world position is added through `cam_mtx`, not by hand.
- *The floor's tiles are all missing*: `NCLIP` sign, or the corners in perimeter order (Chapter 25).
- *Nothing appears at all*: an empty `init_world` leaves `cam_mtx` zero, so every vertex lands in one point.

### 7.6 Stretch goals

- Rest: stop a cube when its bounce speed falls below a threshold. What number works? (The verifier expects the plain model of 5.5, so verify without it.)
- Exact contact: transform the corners first and use the lowest one.
- A shadow: a dark quad on the floor under each cube, scaled by height.
- Per-object `vx` and walls.
- `PushMatrix`/`PopMatrix` around the floor: why does the single level work here, and how does `RotMatrix` break it?

## 8. Verification

```sh
source tools/env.sh
parts/part-05-three-dimensions-with-the-gte/ch26-multiple-objects-and-simple-motion/verify/verify.sh            # your starter/
parts/part-05-three-dimensions-with-the-gte/ch26-multiple-objects-and-simple-motion/verify/verify.sh --solution # the reference
```

Each time the program calls `frame_done()`, the probe records `objects[]` and walks the ordering table handed to `DrawOTag` (slot, colour, corners of every quad). Python replays the integer model and the projection, and compares **exactly** for physics and within 2 px for geometry.

| Check | What it means | If it fails |
|---|---|---|
| `the state symbols exist` | The labels of 7.2 are in the program | Keep-alive line removed |
| `the program uses the GTE` | `RTPS`/`RTPT`, `NCLIP`, `AVSZ3`/`AVSZ4` in your own objects | A software loop |
| `integers only` | No soft-float helper referenced | A `float` crept in |
| `physics: y, velocity ...` | Every frame of 300, all three cubes: `y`, `vy`, `bounces` equal the integer model | Update order, rounding, a missing clamp |
| `floor: no cube ... below floor_y` | `y + radius` never exceeds the floor | Contact test missing or late |
| `spin ...` | Each axis' angle advances by its own step, wraps at 4096, in shipped and patched runs | Shared angle, no `& 4095` |
| `patched start state, gravity ...` | A run with every number changed matches the model | A hard-coded trajectory |
| `each cube has its own matrix` | Visible faces' quads have the reference corners, colours and slots; hidden faces are absent | No per-object upload; wrong composition |
| `... camera and lens patched ... frozen scene` | Same, with a different camera, lens and a still scene | Constants in place of `cam`, `proj_h` |
| `floor: 8 x 6 quads` | 48 quads at slot 63, corners and colours match | Wrong grid, wrong slot, no checker |
| `picture` | Tile centres show the checker colours, face centres the cube colours; cubes over the floor | Floor drawn in front |
| `frame time` | At most 59,500 cycles between the markers | Rebuilding matrices per face |

A pass ends with `CHAPTER 26: PASSED (13/13 checks)`. The shipped run is 300 frames (about 8 s of wall time); this chapter sets `timeout=40` in `checks.py` (a harness option, default 20 s) so that a slow machine does not fail it.

## 9. Common pitfalls

- **One upload for everything**: the second object inherits the first's matrix.
- **Calling `gte_SetRotMatrix`/`gte_SetTransMatrix` directly**: in PSn00bSDK 0.24 they overwrite `$t0`/`$t1` without telling the compiler, so a pointer or counter it keeps there is silently destroyed (it depends on register allocation, so an unrelated edit can expose it). Use the given `load_matrix()`, which is `noipa` so the compiler must assume the call clobbers every temporary register (Chapter 27, 5.7, explains why `noinline` is not enough).
- **Pushing across `RotMatrix`**: it pushes and pops the library's single slot itself, so your `PopMatrix` returns whatever the GTE held when `RotMatrix` was called.
- **`y` is 20.12, positions in the matrix are not**: use `y >> 12` for the translation.
- **`>>` and negatives**: `y >> 12` rounds toward minus infinity, as the verifier's model does; `y / 4096` does not.
- **32-bit products**: `vy * bounce` overflows `int32_t`; use `fx_mul` (64-bit).
- **Update order**: velocity first, then position (5.5).
- **Scaling the wrong thing**: `ScaleMatrix` takes 4.12 factors: `size` as given means a cube of half-edge `size`, not `size * 4096`.
- **Forgetting `& 4095`** on a negative step: the angle goes negative and `isin` misbehaves.
- **Floor in the middle of the table**: cubes below it are hidden by tiles that are nearer in depth.
- **Counting the buffer**: 2048 bytes is 85 `POLY_F4`s; a bigger floor needs a different plan.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- `.toolchain/opt/psn00bsdk/include/libpsn00b/psxgte.h` (`CompMatrixLV`, `ScaleMatrix`, `PushMatrix` notes).
- Pikuma, the PS1 course's lecture on multiple objects and motion.
- Glenn Fiedler, "Integration Basics" (symplectic vs explicit Euler).
- Next: Chapter 27 transforms three corners per command (`RTPT`) on a field of 64 cubes and counts cycles; Chapter 28 replaces `cam` with a real camera matrix.
