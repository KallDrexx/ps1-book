# Chapter 28 Quiz

**1.** The camera stands at `(0, 0, -10000)` and looks along +z with a level `up`. What are the view matrix's rotation and translation? Where does the world point `(500, 0, 0)` land in view space?

<details><summary>Answer</summary>

`forward = (0,0,1)`, `right = forward x up = (0,0,1) x (0,-1,0) = (1,0,0)`, `down = forward x right = (0,1,0)`: the rotation is the identity. `t = -R * eye = (0, 0, 10000)`. The point `(500, 0, 0)` becomes `R * p + t = (500, 0, 10000)`: 500 units right of the line of sight and 10,000 in front of the eye.
</details>

**2.** Why is the second row of the view matrix called `down` here, and what would be wrong with a row that pointed up?

<details><summary>Answer</summary>

View space must match what `RTPS` expects: +x right and +y toward the bottom of the screen (the book's y axis points down). A row pointing up would flip the picture vertically, and the matrix would have determinant -1 (a mirror), so back-face culling would cull the wrong faces.
</details>

**3.** The eye is at `(1000, 0, 0)` and looks at `(1000, 0, 5000)`; then it turns to look at `(-4000, 0, 0)` from the same eye. Without computing, which of `right`, `down`, `forward` change between the two cases, and what is `forward` in the second?

<details><summary>Answer</summary>

`forward` in the second case is `(-1, 0, 0)`. `right = forward x up = (-1,0,0) x (0,-1,0) = (0,0,1)` (the opposite of the look-along-+x case in 5.4) and `down = forward x right = (0,1,0)`. So `forward` and `right` change, while `down` stays `(0, 1, 0)`: turning about the vertical axis leaves it alone.
</details>

**4.** Where in the look-at construction can the cross product become zero, and what does this chapter do then?

<details><summary>Answer</summary>

In `forward x up` when `forward` is parallel to `up` (looking straight up or down): "right" is undefined. The rule: if `|forward x up|` is below 1/32 (or `up` is zero), use `(0,0,1)` as the up vector; if that is parallel too, use `(0,-1,0)`. If `eye == target` there is no `forward`; use `(0,0,1)`. The result is always a valid rotation, though the roll jumps as the camera passes through straight up.
</details>

**5.** `VectorNormalS` on `target - eye` with components of 30,000 stops the program. Why, and what is the fix that keeps the direction?

<details><summary>Answer</summary>

It adds the three squares with MIPS `add`, which traps on signed overflow: `3 * 30000^2 = 2.7e9` is more than 2^31, so the CPU raises an arithmetic-overflow exception and never returns. (Components beyond +-32767 would also wrap in its 16-bit GTE registers.) Shift the vector right first (for example until its largest component is at most 8192), then normalize: the shift changes only the length, not the direction.
</details>

**6.** After `VectorNormalS` a vector has squared length `2^24 * 1.012` (1.2% too long, so about 0.6% in length). What factor does one Newton step multiply it by, and what is the new squared length?

<details><summary>Answer</summary>

Factor `1.5 - 0.5 * 1.012 = 0.994`. The new squared length is `1.012 * 0.994^2 = 0.9999` (times `2^24`): about 0.005% off in length instead of 0.6%. The error went from `e` to about `1.5 e^2`.
</details>

**7.** An object has world matrix `W` and the camera has view matrix `V`. Which call is right, `CompMatrixLV(&V, &W, &out)` or `CompMatrixLV(&W, &V, &out)`? Say what the wrong one computes for the translation.

<details><summary>Answer</summary>

The first: `out.R = V.R * W.R` and `out.t = V.R * W.t + V.t`, so the object is placed in the world first, then the world is moved into view. The second computes `out.t = W.R * V.t + W.t`: it rotates the *camera's* translation by the object's rotation, so the object lands somewhere unrelated to the scene and changes place as it spins.
</details>

**8.** The eye is clamped to `[cam_min, cam_max]` after the pad moves it. Name two ways the picture would break if the eye could go anywhere.

<details><summary>Answer</summary>

(1) Geometry behind or at the eye: a vertex with view z <= 0 has no valid screen position (the GTE's divide overflows), so polygons smear across the screen. (2) Depth range: the ordering table has 64 slots and a face's slot is `SZ / 512`; a face beyond 32,256 units shares slot 63 with the floor and is drawn in the wrong order. A third, the 16-bit limit: `CompMatrixLV` returns `out.T` (the object's view-space position) through 16-bit GTE registers, so an object more than 32,767 from the eye along any view axis is drawn in the wrong place.
</details>
