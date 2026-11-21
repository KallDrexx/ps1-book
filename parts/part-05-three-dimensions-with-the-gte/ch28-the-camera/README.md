# Chapter 28: The Camera

## 1. Concept

The GTE has no camera: it has one matrix, and it always transforms *toward the screen*. To get a **camera**, place an eye in the world and load the *inverse* of that placement, the **view matrix**. Build it from an eye, a target and an up direction (**look-at**), compose it with every object's matrix, and you can fly.

## 2. Why it matters

Every 3D game moves a viewpoint: the racer of Part VII chases a ship, a flight sim banks, a shooter turns its head. Until now the camera was a constant (Chapter 26's `cam`). Look-at is the standard way to point that viewpoint at something, and it is the first place in this book where fixed-point error *accumulates* across several steps: normalizing, cross products, and a translation that depends on both.

## 3. Learning objectives

After this chapter you can:

- explain why the view matrix is the inverse of the camera's placement, and why a transpose is enough;
- name the camera's three axes in this book's Y-down system and build them from `eye`, `target` and `up` with two cross products;
- normalize a vector in 4.12 with `VectorNormalS`, say what its input limit and accuracy are, and repair the accuracy;
- state a rule for the case where `up` is parallel to the view direction;
- compose the view with each object's world matrix in the right order, with `CompMatrixLV`;
- move a camera from the pad with a stated rule, and keep it where the scene stays drawable.

## 4. Prerequisites

[Chapter 26](../ch26-multiple-objects-and-simple-motion/README.md) (this is its scene, with the camera replaced; `CompMatrixLV`, `load_matrix`), [Chapter 25](../ch25-the-gte-coprocessor/README.md) (`gte_*`, NCLIP, OT slots), [Chapter 24](../ch24-3d-projection-fundamentals/README.md) (axes: +X right, +Y **down**, +Z into the screen), [Chapter 23](../ch23-fixed-point-math/README.md) (4.12 vs 20.12), [Chapter 22](../../part-04-c-on-the-playstation/ch22-controller-input-and-the-bios/README.md) (`input_update`/`input_held`).

## 5. Explanation

### 5.1 View space: the world as the camera sees it

Three coordinate systems, one per stage (Chapter 24 introduced them):

```
  object space --(object matrix)--> world space --(VIEW matrix)--> view space --(RTPS)--> screen
   the model's own    place, spin,      one shared       the camera is the           perspective
   coordinates        scale each        scene            origin, looking +z          divide
```

In **view space** the camera sits at the origin, looks along **+z**, with +x to its right and +y toward the bottom of the picture. `RTPS` assumes exactly that: it divides by z and adds the screen center. So "moving the camera" never touches `RTPS`. You change what the world looks like *in view space*:

| You want | Equivalent in view space |
|---|---|
| camera moves right | the whole world moves left |
| camera turns left | the whole world turns right |
| camera moves up (y gets smaller) | the world moves down |

The view matrix applies that **inverse** transform to every point.

### 5.2 The camera's axes

A camera has a position (`eye`) and three perpendicular unit vectors, its own axes written in world coordinates:

```
        world -y (up)
           ^
           |    down  (camera +y)
           |   /
           |  /          forward (camera +z): where it looks
           | /          /
   eye *---------------->  right (camera +x)
```

| Axis | Camera's meaning | Row of the view matrix |
|---|---|---|
| `right` | to the camera's right (view +x) | row 0 |
| `down` | toward the bottom of the picture (view +y) | row 1 |
| `forward` | where it looks (view +z) | row 2 |

The middle one is **down**, not "up": the book's y axis points down, and view +y must stay "toward the screen's bottom" for `RTPS`. The usual graphics-textbook "up" row is `-down`. A camera that is level has `down = (0, 1, 0)`.

### 5.3 The view matrix is the inverse, and for a rotation that is the transpose

If the camera's axes (as columns) form a rotation matrix `C`, then `C` takes view-space vectors to world space. The view matrix needs the other direction. A rotation's inverse is its **transpose** (`C` has orthonormal columns: unit length, mutually perpendicular), and transposing turns columns into rows:

```
              | right.x  right.y  right.z |          view = R * (world - eye)
   R = C^T =  | down.x   down.y   down.z  |        = R * world  -  R * eye
              | fwd.x    fwd.y    fwd.z   |
```

Each row dotted with a world vector asks "how far along this camera axis?": that is the definition of right, down and forward distances. The GTE computes `RT * v + TR`, so:

- `RT` = `R`, the matrix above (4.12);
- `TR` = `-R * eye` (plain integer units; the **eye is rotated like any point, then negated**).

Check with Chapter 26's fixed camera: eye `(0, 0, -14336)` looking along +z has `R` = identity, so `t = (0, 0, +14336)`: that was `cam`.

### 5.4 Look-at: from eye, target, up to the matrix

| Step | Compute | Notes |
|---|---|---|
| 1 | `forward = normalize(target - eye)` | eye == target has no direction: use `(0, 0, 1)` |
| 2 | `right = normalize(forward x up)` | `up` is the *wish* ("sky is -y"), not an axis |
| 3 | `down = forward x right` | already perpendicular and unit |
| 4 | rows = `right`, `down`, `forward` | |
| 5 | `t = -R * eye` | |

`x` is the **cross product**: `a x b = (ay*bz - az*by, az*bx - ax*bz, ax*by - ay*bx)`, a vector perpendicular to both, with length `|a||b| sin(angle)`. Its direction follows the right-hand rule, and this book's axes (x right, y down, z in) are a right-handed system. That is why step 2 is `forward x up`, with `up = (0, -1, 0)` for "the sky is -y". Check: `forward = (0, 0, 1)` gives `(0,0,1) x (0,-1,0) = (1, 0, 0)`, +x as it must be. Step 3 checks too: `(0,0,1) x (1,0,0) = (0, 1, 0)`, down.

A second check by hand: eye at the origin, target `(5000, 0, 0)`. Then `forward = (1,0,0)`, `right = (0,0,-1)`, `down = (0,1,0)`: the view matrix's rows are those three, and the world point `(5000, 0, 0)` becomes `(0, 0, 5000)`: straight ahead.

**Degenerate: `up` parallel to `forward`.** Looking straight up or down, `forward x up` is zero and "right" is undefined. This chapter's rule, which the verifier tests:

| Condition | Behavior |
|---|---|
| `\|forward x up\|` < 1/32 (sin of the angle under about 1.8 degrees; `forward` and `up` both normalized), or `up` is the zero vector | replace `up` by `(0, 0, 1)` (world +z) |
| still parallel (forward is along z too) | replace `up` by `(0, -1, 0)` |
| `eye == target` | `forward = (0, 0, 1)` |

The result is always a valid rotation. It is not *continuous*: pass through straight-up and the camera's roll jumps. Games that need smoothness track the camera's own orientation instead; this is a stretch goal.

### 5.5 Normalizing in fixed point

`VectorNormalS(VECTOR *in, SVECTOR *out)` writes `in / |in|` as a **4.12** vector (4096 = 1.0). It loads the three components into the GTE's 16-bit `IR` registers, squares them (`SQR`), adds the squares on the CPU, and looks up `1 / sqrt` in a 192-entry table. Its disassembly (`libpsxgte`, `vector.s`) shows three things:

| Fact | Consequence |
|---|---|
| Each component goes through a **16-bit** register: outside +-32767 it wraps. The squares are summed with MIPS `add`, which **traps on overflow**: if `x*x + y*y + z*z` reaches 2^31 (all three components near 26,800) the CPU raises an arithmetic-overflow exception and the program never comes back | Shift the input right first until the largest component is at most 8192. A direction survives a shift; only the length changes |
| The table is coarse: errors up to about **32/4096 (0.8%)** per component | A unit vector that is 0.8% too long or short skews the matrix. Orthonormality is the whole point |
| It handles tiny vectors (components of 1..3) fine | An all-zero vector reads an entry before the table and comes back as `(0, 0, 0)`, which is no direction: test for it yourself |

**Repairing the accuracy.** If a vector `v` has length `1 + e` (`e` of a few tenths of a percent), multiplying it by `1.5 - 0.5 * |v|^2` makes the length `1 + O(e^2)`. That is one **Newton step** for `1/sqrt`. In 4.12: `|v|^2` is the sum of squares (`2^24` means 1.0); the factor is `(3 * 2^24 - |v|^2) >> 13` (4096 means 1.0); each component becomes `(c * factor) >> 12`. After this step the reference solution's components are within about 3 (in 1/4096 units) of exact, against 32 without.

**The cross product needs headroom, not a shift.** `forward` and `up` are 4.12, so each product is up to 2^24 and the difference up to 2^25. Do *not* shift that down to 4.12 before normalizing: when the vectors are nearly parallel the cross product is small (sin 0.1 gives about 400 in 4.12) and the shift would throw away most of its precision. Keep the full 32-bit value and shift it right only as far as `VectorNormalS` needs (the same largest-component-at-most-8192 rule: 11 bits at most), then normalize. `down = forward x right` is different: both inputs are unit, so one `>> 12` gives a 4.12 result at full accuracy.

**Error budget.** `forward` and `up` each carry a unit or two of 4.12 error per component. The direction of `right` inherits that error *divided by `sin(angle)`*: ordinary for a level camera (sin near 1), ten times larger at sin 0.1. That is why a nearly parallel `up` is fragile, and why the verifier's tolerance grows as sin shrinks.

(The GTE also has a cross product, `OP` (`gte_op0()`/`gte_op12()`). It wants one vector in the diagonal of `RT` and the other in the `IR` registers, which overwrites the matrix you may have loaded, and its `IR` results saturate at 16 bits. The CPU's 32-bit multiply is simpler and exact here.)

### 5.6 Composing the view with every object

Every object already has a world matrix `W` (rotate, scale, translate: Chapter 26). The GTE needs *object to view* in one step:

```
   object  --W-->  world  --V-->  view          R = Rv * Rw
                                                T = Rv * Tw + Tv
```

`CompMatrixLV(&V, &W, &out)` does exactly this (Chapter 26): `out.R = V.R * W.R`, `out.T = V.R * W.T + V.T`. **The camera goes first (left), the object second.** Swap them and you apply the *object's* rotation to the *camera's* translation: the cube flies off (the worked example shows it).

| Thing | Matrix uploaded |
|---|---|
| each cube | `CompMatrixLV(&view_mtx, &its_world_matrix, &out)`, then `load_matrix(&out)` |
| the floor | `view_mtx` itself (its world matrix is the identity) |

Two limits to respect: `W.T` goes *into* the GTE through 16-bit registers, and `out.T` comes back out through the same registers (saturated), so each component of the object's world position *and* of its view-space position must stay within +-32767. `view_mtx.t` itself is a full 32-bit value. The clamp box of 7.2 keeps every cube within about 28,000 of the eye. Build the view **once per frame** and reuse it for every object; building it per object repeats the work for no change.

`MulMatrix0(&a, &b, &out)` multiplies two rotation matrices without any translation. You do not need it for the basic project; it is the tool for combining *rotations* of the camera itself (stretch goals).

### 5.7 A free-fly camera

Flying means: change `eye` each frame, call `camera_look_at`, draw. Because the camera always looks at a target, the pad moves the *eye*, never the angles.

The rule this chapter uses (**world-relative**; every number is in 7.2):

| Held | Change to `eye`, per frame |
|---|---|
| RIGHT / LEFT | x += / -= `cam_speed` (from the start view: sideways; the scene slides the other way) |
| UP / DOWN | z += / -= `cam_speed` (from the start view: toward / away from the cubes) |
| R1 | y += `cam_speed` (**lower**: y points down) |
| L1 | y -= `cam_speed` (**raise**) |

Opposite buttons cancel. After the move each component is clamped to `[cam_min, cam_max]`. World axes make the rule simple and exactly checkable. (A view-relative rule would need the current `forward`, and with the camera locked on the cube it would turn into "approach" and "orbit"; see the stretch goals.)

**Why a clamp box.** Two things go wrong when the eye reaches the geometry:

- **Behind the eye.** A point whose view z is zero or negative has no sensible screen position: the GTE divides by z and the result overflows into a smear across the screen. Cubes never get behind the eye here: the box keeps the eye at z <= -5000, every cube corner stays beyond z = -3300, and the camera always faces the cubes. The floor is large and can reach the eye's side, so `draw_floor` also stores each corner's `SZ` (`gte_stsz`) and **skips a tile with any corner nearer than `NEAR_Z` (256)**. That is crude near-plane rejection; real engines clip the polygon against the plane instead.
- **Too far.** The ordering table has 64 slots, and a face's slot is its average `SZ / 512`. The floor owns the last slot, so a cube must stay nearer than 63 slots (32,256 units). The box's farthest corner is about 27,000 units from the center cube, and no cube face seen from inside the box lies beyond slot 57.

## 6. Worked example

`example/` flies a camera in a circle around a spinning cube on a ground grid. `camera_look_at` is the one you will write (read it after your own attempt). Two switches break the camera on purpose.

```sh
source tools/env.sh
cd parts/part-05-three-dimensions-with-the-gte/ch28-the-camera/example
make run
```

1. Run it as shipped. The ground stays put while the camera circles; the cube turns in place.
2. Set `WRONG_ORDER` to 1 (`CompMatrixLV(&m, &view_mtx, ...)`). The cube leaves the picture. Which of its three parts (rotation, size, position) is being applied to the camera's translation? (Rotation and size: `out.T = m.R * view.T + m.T`, so the eye's 9,500-unit offset is spun with the cube and shrunk to a quarter.)
3. Set `WRONG_ORDER` back to 0 and `SKIP_TRANSLATION` to 1 (rows only, `t = 0`). The ground tilts and swings but the cube is gone. Where is the eye now, in the view matrix's mind? (At the world origin. The cube is at the origin: it is *on* the eye.)
4. Change `cam_up` to `(1500, -4096, 0)`: the horizon tilts. Then to `(0, 4096, 0)`: the world turns upside down.

## 7. Project: "Flyable Camera"

Replace Chapter 26's fixed camera with a look-at camera that always looks at the **center cube** (the green one, `objects[1]`), and fly it with the pad.

### 7.1 Behavior

The same scene as Chapter 26, seen from a camera that starts in the old place. D-pad moves it, L1/R1 raise and lower it, and whatever you do, the green cube stays in the middle of the screen while it bounces. The floor and the other cubes swing around it with correct perspective.

### 7.2 The contract

`starter/main.c` declares this state. Do not change names, types or initial values: the verifier reads **and patches** it.

| Symbol | Type | Initial | Meaning |
|---|---|---|---|
| `cam_eye` | `VECTOR` | (0, 0, -14336) | where the camera is (world units); you move it |
| `cam_target` | `VECTOR` | (0, -4000, 1800) | what it looks at; **you set it every frame** to the center cube |
| `cam_up` | `VECTOR` | (0, -4096, 0) | which way is "up" (the sky is -y); only its direction matters; input, never written |
| `cam_speed` | `int32_t` | 100 | units per frame |
| `cam_min`, `cam_max` | `VECTOR` | (-12000, -9000, -20000), (12000, 3000, -5000) | the eye's clamp box |
| `view_mtx` | `MATRIX` | (you fill it) | the view matrix, see below |

**`view_mtx`** is what `camera_look_at` writes:

| Field | Contents |
|---|---|
| `m[0][0..2]` | `right`, 4.12 |
| `m[1][0..2]` | `down`, 4.12 |
| `m[2][0..2]` | `forward`, 4.12 |
| `t[0..2]` | `-R * eye`, integer units (rows dotted with the eye, `>> 12`, negated) |

**`void camera_look_at(const VECTOR *eye, const VECTOR *target, const VECTOR *up)`** is a global, non-inline function (keep `__attribute__((noinline))`). It reads **only its parameters**, writes **only `view_mtx`**, applies 5.4 including the degenerate rules, and is correct for every eye and target component within +-16000 and `up` components within +-32767.

**Movement** (`update_camera`), per frame, after `input_update()` (7.3):

```
  dx = RIGHT - LEFT      dy = R1 - L1      dz = UP - DOWN        (each held button counts 1)
  cam_eye += cam_speed * (dx, dy, dz)       then each component clamped to [cam_min, cam_max]
```

Diagonals are not slowed down (both axes move at full speed). Nothing else writes `cam_eye`. **Frame order** (the loop in `main` is given up to the marked place): `display_clear`, `ot_begin_frame`, `render_begin()`, `input_update`, `update_objects`, **`update_camera`, set `cam_target`, `camera_look_at`**, `draw_floor`, `draw_object` x3, `render_end()`, `ot_draw`, `display_swap`, `frame_no++`, `frame_done()`. At `frame_done()` with `frame_no == k` the objects have had `k` updates and the eye `k` moves. `cam_target` is `(objects[1].x, objects[1].y >> 12, objects[1].z)`: the cube's position **after** this frame's update (`y` is 20.12).

**Tolerances** (all in 1/4096 unless stated). Each matrix entry within **10** of the reference (the verifier widens this to 8 + 2 / sin when `up` is nearly parallel to `forward`); `t` within **3** of `-(your own row . eye) / 4096`; each row's `|row|^2 / 4096` within 48 of 4096 (length within about 0.6%: `VectorNormalS` alone is not enough), each pair's dot product within 48, determinant 1 +- 0.03.

### 7.3 Steps

1. `camera_look_at` (5.4, 5.5): a helper that normalizes a `VECTOR` into an `SVECTOR` with the shift, `VectorNormalS` and the Newton step; a helper for the cross product; then the five steps and the degenerate rule. (`DEGENERATE` in the starter is the threshold for the full-scale cross product's length. Its squared length overflows 32 bits, so compare after `>> 10`: `x*x + y*y + z*z < (DEGENERATE >> 10)^2`.)
2. `update_camera`: the rule of 7.2, with the clamp.
3. In `main`'s loop: call `update_camera`, set `cam_target`, call `camera_look_at`.
4. Replace `cam_mtx` with `view_mtx` in `draw_floor` and `draw_object`, then delete `cam`, `cam_mtx` and `init_world` (and their two entries in the keep-alive line).
5. `make run`: fly around. Then `verify.sh`.

### 7.4 Rules

- Use the GTE for transforms as in Chapter 26; no `float`/`double`.
- Read every number from the symbols above: the verifier patches the start eye, up, speed, clamp box and the center cube's position.
- Use `load_matrix()` to upload matrices (Chapter 26, section 9).
- Keep the keep-alive line and the three marker functions. Do not write `cam_up`, `cam_speed`, `cam_min`, `cam_max`.
- Frame budget: at most 68,600 CPU cycles between `render_begin()` and `render_end()` (twice the reference solution). Build the view once per frame, not per object.

### 7.5 Hints

- *Everything is mirrored or upside down*: the rows are in the wrong order or `down` is really `up`. Check with the hand example in 5.4.
- *The scene swings the wrong way when the eye moves*: `t` has the wrong sign or you stored `-eye`. It is `-R * eye`.
- *The picture is black or smeared, or the program stops*: `VectorNormalS` input too large (shift first), or `t` not stored.
- *Right and down are only almost perpendicular*: you skipped the Newton step.
- *Cubes jump to strange places only when the camera turns*: `CompMatrixLV` arguments swapped.
- *It works with `up = (0, -4096, 0)` but not a tilted one*: you hard-coded the `up` row, or ignored the argument.
- *Wrong values only in the verifier's direct calls*: you read `cam_eye` instead of `eye`. The verifier passes pointers to a different buffer.

### 7.6 Stretch goals

- Camera-relative movement: UP moves toward the target on the ground (forward projected onto the xz plane), LEFT/RIGHT strafe, making the camera orbit the cube. (The verifier tests the world-relative rule, so verify without it.)
- Smooth the target: ease `cam_target` toward the cube with `fx_lerp`.
- Yaw/pitch camera: keep two angles, build the view with `RotMatrix` and `MulMatrix0` of the transposed rotation, and compare with look-at.
- Reject cube faces behind the eye as the floor does.

## 8. Verification

```sh
source tools/env.sh
parts/part-05-three-dimensions-with-the-gte/ch28-the-camera/verify/verify.sh            # your starter/
parts/part-05-three-dimensions-with-the-gte/ch28-the-camera/verify/verify.sh --solution # the reference
```

Three kinds of run. **Direct calls:** the probe calls `camera_look_at` itself, up to 36 times, with arguments it keeps in a scratch buffer (axes, rolled and upside-down `up`, tiny and huge `up`, 32000-unit differences, `eye == target`, the degenerate cases, and a seeded random set). **Shipped run:** 300 frames, with scripted pad presses. **Patched run:** another start eye, `up`, speed, clamp box and position of the center cube, with presses that hit every clamp.

| Check | What it means | If it fails |
|---|---|---|
| `the state symbols exist` | The labels of 7.2 are in the program | Keep-alive line removed, `camera_look_at` missing or `static` |
| `the program uses the GTE` | `RTPS`/`RTPT`, `NCLIP`, `AVSZ3`/`AVSZ4` in your objects | A software loop |
| `integers only` | No soft-float helper referenced | A `float` crept in |
| `camera_look_at is a well-behaved C function` | Returns; keeps `$s0`-`$s7`, `$fp`, `$sp`; arguments unchanged | Writing through `eye`/`target`/`up`; assembly that forgets to save; "CPU exception 12": `VectorNormalS` overflowed (5.5) |
| `the view matrix: rows ... match the float reference` | Every entry within tolerance, `t` equal to `-R * eye` of your own rows | Transposed, negated, wrong cross order, ignoring `up`, global instead of parameter |
| `degenerate cases` | Fallbacks of 5.4 | Zero vector fed to the normalizer |
| `every result is orthonormal and right-handed` | Unit, perpendicular rows, determinant +1 | Missing Newton step, mirrored matrix |
| `every frame: view_mtx is camera_look_at's answer` | The program really uses the function on its own eye, target, up each frame | Called before the eye moved, or not at all |
| `the camera looks at the center cube` | `cam_target` equals the cube's position that frame | Old position, `y` not shifted |
| `the pad moves the eye exactly` | The eye follows the rule of 7.2 frame by frame, clamps included | Axis or sign, missing clamp, speed hard-coded |
| `the view reaches every object` | Each cube face and floor tile is where the reference puts it through *your* matrix | Composition order, a missing view on the floor |
| `picture` | The center cube's pixels are centered (within 16 px) in 14 screenshots across both runs | Camera not following, wrong translation |
| `the scene is still Chapter 26's` | Physics unchanged | Disturbed `update_objects` |
| `frame time` | At most 68,600 cycles between the markers | The view built per object |

A pass ends with `CHAPTER 28: PASSED (15/15 checks)`; the fifteenth, not in the table, compares `solution/psxe` with `common/psxe` and only applies to `--solution`.

## 9. Common pitfalls

- **Shifting before normalizing the cross product**: for nearly parallel vectors this throws away most of the precision (5.5).
- **`VectorNormalS` on large vectors**: its components wrap at 16 bits and its sum of squares traps at 2^31 (the verifier reports "CPU exception 12 (arithmetic overflow)"). `target - eye` can be 32,000 per component.
- **A mirrored matrix**: swap two rows or two cross-product operands and the determinant becomes -1: the world is a mirror image, and back-face culling culls the wrong sides.
- **`up` is not an axis**: `right = forward x up`, and `down` comes from `forward x right`. Using `up` as a row skews the matrix as soon as the camera pitches.
- **Rotating without translating**: the camera then sits at the world origin. `t = -R * eye`.
- **`-eye` instead of `-R * eye`**: right only while the camera has no rotation.
- **Composition order**: `CompMatrixLV(&view, &object, ...)`, view first.
- **The eye reaching the geometry**: behind-the-eye vertices give garbage. Clamp, or reject (5.7).
- **Calling `gte_SetRotMatrix` directly**: use `load_matrix()` (Chapter 26, section 9).
- **Mixing formats**: a cube's `y` is 20.12 but `cam_target` and `cam_eye` are plain units: `cam_target.vy = objects[1].y >> 12`.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- `.toolchain/opt/psn00bsdk/include/libpsn00b/psxgte.h` (`VectorNormalS`, `CompMatrixLV`, `ApplyMatrixLV`, `MulMatrix0`).
- psx-spx, "GTE" chapters: `OP`, `MVMVA`, and the register saturation rules.
- Pikuma, the PS1 course's lecture on the camera and look-at.
- Fabien Sanglard or Scratchapixel, "Lookat" derivations in the usual right-handed, y-up convention (flip y to compare).
- Next: Part VI loads assets from a CD image; the camera of this chapter flies the models you load there.
