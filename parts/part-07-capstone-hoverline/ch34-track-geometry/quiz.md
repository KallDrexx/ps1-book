# Chapter 34 quiz

**1.** Track 1 has 112 sections. How many vertices and faces does it have, and why are there not 112 x 12 vertices?

<details><summary>Answer</summary>

672 vertices (112 rings x 6) and 560 faces (112 x 5). Neighbouring sections share a ring: ring `r + 1` is the end of section `r` and the start of section `r + 1`, stored once. The last section ends on ring 0.
</details>

**2.** `first_face` and `face_count` are `u16` in a section record. Why does `track_parse` compute `first_face + face_count` in 32 bits before comparing it with the file's face count?

<details><summary>Answer</summary>

In 16 bits `0xFFFF + 2` wraps to 1, which passes the test, and the section would then index faces far outside the table. Widen first (or compare `first_face <= n && face_count <= n - first_face`). The same applies to every offset and size sum.
</details>

**3.** A vertex is at x = 24,000 and the camera at x = -20,000. Both fit `s16`. Is the vertex usable, and what does the program do with its faces?

<details><summary>Answer</summary>

`d.x = 44,000`, which exceeds 32,767 and does not fit `s16`: the vertex is **far**, nothing is loaded, and every face that uses it is skipped (`faces_far`). The inputs fitting is not enough: the *difference* is what the GTE needs.
</details>

**4.** Why must `RT` hold only the rotation of `view_mtx` and `TR` be 0?

<details><summary>Answer</summary>

Because the program has already subtracted the eye in 32-bit C: `d` is camera-relative, and adding `view_mtx.t = -R * eye` again would subtract the eye twice. The other consistent choice, the camera in `TR` with the absolute vertex in `V`, is handled fine by the GTE (`TR` is 32-bit, the sum 44-bit) but only while every absolute coordinate fits `s16`: true of the shipped tracks, false on the verifier's translated track, where the coordinates wrap when narrowed.
</details>

**5.** `|d.x| = 32767` and `|d.x| = 32768`: which is kept?

<details><summary>Answer</summary>

32767 is kept (it fits `s16`), 32768 is far. The rule is "above 32767 is far", symmetric for both signs even though `s16` could hold -32768.
</details>

**6.** Why are all four vertices of a face classified before the first test, and why is each vertex projected once?

<details><summary>Answer</summary>

Classifying all four makes the per-vertex state independent of how a face ends (a far vertex is recorded even if an earlier vertex already failed the near test), so counts are reproducible. Projecting once is the payoff of index sharing: up to four faces use a vertex, and the subtraction and `RTPS` are the expensive part.
</details>

**7.** A face lists its corners `v0 v1 v2 v3`. In which order does the wireframe outline visit them, and why?

<details><summary>Answer</summary>

`v0, v1, v3, v2, v0`. The corners are in Z order (two parallel edges `v0v1` and `v2v3`), so going round the quad skips from `v1` to `v3`, then to `v2`. A `POLY_F4` takes them in file order because the GPU splits the quad into the triangles `v0 v1 v2` and `v1 v2 v3`.
</details>

**8.** In wire mode you link both a `POLY_F4` and a polyline into the same slot. Which do you pass to `ot_add` first?

<details><summary>Answer</summary>

The **outline** first, then the fill. `ot_add` inserts at the front of the slot and the GPU draws a slot front to back, so the fill (linked last) is drawn first and the outline on top.
</details>

**9.** The whole track needs up to 13,440 bytes of fills and the library has a 2,048-byte buffer. What do you do, and what if the buffer is still too small in some frame?

<details><summary>Answer</summary>

Enlarge `PRIM_BUF_SIZE` (this chapter: 32,768). If `ot_alloc` still returns `NULL`, count the face as dropped and make no more allocations this frame, never writing past the block. Chapter 38 avoids the problem by drawing only nearby sections.
</details>
