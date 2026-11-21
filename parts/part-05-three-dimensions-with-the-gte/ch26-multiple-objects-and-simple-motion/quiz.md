# Chapter 26 Quiz

**1.** Two objects are drawn one after the other, but the second object's matrix is never uploaded. Where does the second object appear, and why?

<details><summary>Answer</summary>

Exactly where the first one is, with its orientation. `RTPS` multiplies by whatever is in the GTE's `RT`/`TR` at that moment; it knows nothing about objects. The second object's vertices are transformed with the first object's rotation and translation.
</details>

**2.** You upload matrix A and call `PushMatrix()`. Then you upload matrix B, call `RotMatrix(&rot, &m)`, and call `PopMatrix()`. Which matrix is in the GTE now, and why?

<details><summary>Answer</summary>

B, not A. The library has a single stack slot, and `RotMatrix` itself calls `PushMatrix` on entry (saving B, the matrix loaded at that moment, over your A) and `PopMatrix` on exit. Your `PopMatrix` then restores B. Keep your own `MATRIX` in a C variable and re-upload it instead.
</details>

**3.** `CompMatrixLV(&cam, &obj, &out)` with `cam` = identity rotation and translation `(0, 0, 14336)`, and `obj.t = (1000, -500, 0)`. What is `out.t`? What is the rotation part, `out.m`?

<details><summary>Answer</summary>

`out.t = cam.m * obj.t + cam.t = (1000, -500, 14336)`. `out.m = cam.m * obj.m = obj.m` (the identity changes nothing). `out` must still be uploaded (`load_matrix`): the call leaves `cam` in the GTE.
</details>

**4.** A cube falls from rest with `gravity = 4` units per frame squared, using `vy += g; y += vy`. How far has it fallen after 10 frames? Compare with `g * t^2 / 2`.

<details><summary>Answer</summary>

`g * (1 + 2 + ... + 10) = 4 * 55 = 220` units. The continuous formula gives `4 * 100 / 2 = 200`. The loop sums ten steps (each with the speed *after* that frame's gravity); the formula is the area under a line. That difference is the integration error.
</details>

**5.** A cube hits the floor with `vy = 163840` (40 units per frame in 20.12) and `bounce = 3277`. What is `vy` right after the bounce? In what direction does the cube move?

<details><summary>Answer</summary>

`fx_mul(163840, 3277) = (163840 * 3277) >> 12 = 131080`, so `vy = -131080` (about -32 units per frame): upward, since y grows downward. The cube keeps 80% of its speed.
</details>

**6.** Why can the floor use one fixed ordering-table slot (the farthest), but the cubes' faces cannot?

<details><summary>Answer</summary>

Floor tiles do not overlap each other, and every cube is above the floor, so the floor is always behind everything: order among the tiles does not matter. Cube faces overlap each other and other cubes, so each needs a slot from its own depth (`AVSZ4 >> 7`).
</details>

**7.** The floor is 8 x 6 tiles. How many corners are transformed, and why not 4 per tile?

<details><summary>Answer</summary>

(8 + 1) * (6 + 1) = 63. Neighbouring tiles share corners, so each grid point is transformed once and reused: 63 `RTPS` instead of 192.
</details>

**8.** `y >> 12` and `y / 4096` give different results for `y = -4097`. Which one matches `fx_mul`'s rounding, and what are the two values?

<details><summary>Answer</summary>

`y >> 12` is an arithmetic shift and rounds toward minus infinity: -2. `y / 4096` truncates toward zero: -1. `fx_mul` uses the shift, so use `>>` for the world position.
</details>
