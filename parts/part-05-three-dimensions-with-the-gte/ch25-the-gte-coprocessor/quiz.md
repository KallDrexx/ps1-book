# Chapter 25 Quiz

**1.** What is the GTE, and how does a program use it?

<details><summary>Answer</summary>

Coprocessor 2 of the R3000: a fixed-function unit with its own data and control registers. The CPU loads vertices and matrices with `mtc2`/`ctc2`/`lwc2`, starts a command with `cop2` (`RTPS`, `NCLIP`, `AVSZ4`...), and reads the results back with `mfc2`/`cfc2`/`swc2`. In PSn00bSDK 0.24 the `gte_*` macros of `<inline_c.h>` wrap these instructions.
</details>

**2.** `RotMatrix(&rot, &mtx)` was called, and the cube still draws in the old position. What did the program forget, and what is the translation's unit?

<details><summary>Answer</summary>

`RotMatrix` and `TransMatrix` fill only the C structure; `gte_SetRotMatrix(&mtx)` and `gte_SetTransMatrix(&mtx)` load it into the GTE. The matrix is 4.12, but the translation is in the same plain-integer units as the vertices (the GTE computes `(R * v) >> 12 + T`).
</details>

**3.** With `h = 256`, screen offset `(160, 120)`, a vertex `(4096, 0, 0)` and the translation `(0, 0, 24576)` (no rotation), where does `RTPS` put it? What are `SZ3` and the flags?

<details><summary>Answer</summary>

`SZ3 = 24576`. `SX = 160 + 4096 * 256 / 24576 = 160 + 42.67`, so about 202 (the GTE's divide may differ in the last bit); `SY = 120`. No error flag is set (`H = 256` is far below `2 * SZ3`).
</details>

**4.** A triangle's corners on screen are `(0, 0)`, `(10, 0)`, `(0, 10)`. Is `NCLIP` positive or negative? Is it front- or back-facing?

<details><summary>Answer</summary>

`(x1-x0)*(y2-y0) - (x2-x0)*(y1-y0) = 10*10 - 0*0 = +100`. Going from `(0,0)` to `(10,0)` to `(0,10)` turns clockwise on the screen (y points down), so it is front-facing in this chapter's convention: positive means front.
</details>

**5.** Why must a quad's corners be given in Z order (`0 1 2 3` = top-left, top-right, bottom-left, bottom-right), and what does it have to do with `NCLIP`?

<details><summary>Answer</summary>

The GPU draws a four-point polygon as the triangles `(v0, v1, v2)` and `(v1, v2, v3)`, so going around the perimeter would draw a bow tie. `NCLIP` uses the first three corners, so Z order also makes `v0 -> v1 -> v2` clockwise when the face is seen from outside, which is what makes the sign of `NCLIP` mean "facing the camera" on every face. A face listed in perimeter order, or from the inside, culls when it should show.
</details>

**6.** `InitGeom` sets `ZSF4 = 256`. A quad's four corners have `SZ` 20000, 20400, 21000 and 21400. What are `OTZ` and the ordering-table slot (`OTZ >> 7`)?

<details><summary>Answer</summary>

Sum = 82800; `OTZ = (256 * 82800) >> 12 = 5175` (the mean, 20700, divided by 4). Slot = `5175 >> 7 = 40`. Slot 0 is the nearest and 63 the farthest, so a larger depth means a larger slot and the quad is drawn earlier than nearer ones.
</details>

**7.** A cube is drawn with the back faces culled. Is depth sorting still needed? When would sorting by average Z fail?

<details><summary>Answer</summary>

For one convex object with its back faces culled the visible faces never overlap, so any order is right; sorting matters as soon as several objects or concave shapes share the screen. Average-Z sorting fails for long polygons next to small ones, and for faces that intersect or interleave: the average says which is "farther" while parts of each are nearer.
</details>

**8.** In a frame, `gte_flags` has bit 17 and bit 31 set. What happened, and what does the program see in the screen position?

<details><summary>Answer</summary>

A divide overflow: some vertex has `SZ3 <= H / 2` (it is very close to the camera, at or behind it). The summary bit 31 is set because bit 17 is an error bit. The GTE saturates the divide result, so the screen position is a huge or clamped value (within -1024..1023, with bits 13/14 set if it clamped), not an exception: a program has to check the flags (or clip) if it cares.
</details>
