# Chapter 24 Quiz

**1.** Which way do the X, Y and Z axes point in the PS1/GTE convention, and where is the origin on screen once you have projected?

<details><summary>Answer</summary>

X right, Y down, Z into the screen (away from the viewer). The projected coordinates are relative to the center of the view, so you add the center of the picture, `(160, 120)` in a 320x240 mode, to get pixel coordinates (whose own origin is the top-left corner).
</details>

**2.** A point is at `(x, z) = (100, 400)` and the projection distance is `h = 256`. Where does it land horizontally (relative to the center)? Where does `(100, 800)` land, and what does that say about distant objects?

<details><summary>Answer</summary>

`x' = x * h / z`: `100 * 256 / 400 = 64` and `100 * 256 / 800 = 32`. Doubling the distance halves the offset from the center, so distant objects shrink toward the middle of the screen. This is the similar-triangles relation `x'/h = x/z`.
</details>

**3.** What does `h` control? Compute the horizontal field of view (full angle, roughly) for `h = 256` on a 320-pixel-wide screen, and say what a smaller `h` does.

<details><summary>Answer</summary>

`h` is the distance from the eye to the screen plane, in pixels. The half-angle is `atan(160 / 256)`, about 32 degrees, so the full view is about 64 degrees. A smaller `h` is a wider angle: more of the scene fits on screen and everything is drawn smaller. A larger `h` is a zoom-in.
</details>

**4.** Why must a cube be rotated before it is moved along Z, and why does the order of an X rotation and a Y rotation matter?

<details><summary>Answer</summary>

A rotation turns about the origin. Rotating after translating moves the cube along a circle around the camera instead of spinning it in place. X-then-Y and Y-then-X give different orientations because rotations do not commute: the second rotation acts on coordinates the first one already changed.
</details>

**5.** Chapter 23's `fx_rotate(u, v, a, &out)` gives `out.x = u*c - v*s` and `out.y = u*s + v*c`. Which inputs rotate a point about the Y axis, and which output is the new x?

<details><summary>Answer</summary>

`fx_rotate(z, x, a, &out)`: the pairs follow the cycle X, Y, Z, X, so for Y the first coordinate is z and the second is x. `out.x` is the new z and `out.y` is the new x.
</details>

**6.** What happens when a projected point has `z = 0`? And `z < 0`? How does this chapter keep it from happening?

<details><summary>Answer</summary>

`z = 0` divides by zero; `fx_div` saturates, so the coordinates are garbage (and may overflow 16 bits). `z < 0` means the point is behind the camera, but the formula still gives coordinates, mirrored through the screen center, so the point shows up on the wrong side. The chapter pushes the cube by `cam_z = 6.0`; its nearest possible corner is then at about `6 - 1.73 = 4.27`, so `z` is always positive. Real renderers clip against a near plane before the divide.
</details>

**7.** Why does a mesh store vertices once and refer to them by index in its edge and face lists?

<details><summary>Answer</summary>

A cube corner is shared by three edges and three faces. With indices each vertex is rotated and projected once per frame, however many edges or faces use it, and the data is smaller (8 points instead of 24 or 36). It also guarantees that edges sharing a corner always meet.
</details>

**8.** Which primitive draws a one-pixel flat-colored line, which macros fill it in, and what does `ot_alloc` returning `NULL` mean?

<details><summary>Answer</summary>

`LINE_F2`, filled with `setLineF2` (tag length and command code), `setRGB0` (color) and `setXY2` (both end points), then linked with `ot_add`. `NULL` means the frame's primitive buffer is full: nothing was allocated, so the caller must stop drawing rather than write through the pointer.
</details>
