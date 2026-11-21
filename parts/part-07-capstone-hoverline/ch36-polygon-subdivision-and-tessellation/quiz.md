# Chapter 36 quiz

**1.** A long quad recedes from the camera. Why does its texture look wrong on a PS1, and why does cutting the quad in four help?

<details><summary>Answer</summary>

The GPU interpolates `u` and `v` linearly in screen space, but perspective needs the texture to advance faster on the screen at the far end (the near end covers more pixels per texel). The error grows with the depth range of one polygon. A piece covers a smaller depth range, so its linear interpolation is closer to the true curve; the pieces together follow it. The price is more packets and more projections.
</details>

**2.** A face's `u` values at two corners are 5 and 10. Give the texel of the edge midpoint. Then mirror the face first (`FLIP_H`, `u -> 63 - u`) and give the midpoint of the mirrored corners. Is it the mirror of the first midpoint?

<details><summary>Answer</summary>

`(5 + 10) >> 1 = 7`. Mirrored: 58 and 53, `(58 + 53) >> 1 = 55`. The mirror of 7 would be 56. They differ by one, because `a + b` is odd and `>> 1` rounds down. So the order matters: mirror (and add the tile origin) first, then split. `track_face_uv` returns the face's final UVs, so split those.
</details>

**3.** The primitive buffer has 8,800 bytes left, `subdiv_reserve` is 8192 and the face is textured (`POLY_FT4`, 40 bytes), no outlines. What level may a level-2 face use? And with outlines on (72 bytes per quad)?

<details><summary>Answer</summary>

The rule: lower the level while `left < reserve + (4^level + 1) * leaf_bytes`. Level 2: `8192 + 17 * 40 = 8872 > 8800`, so it is cut. Level 1: `8192 + 5 * 40 = 8392 <= 8800`: level 1. With outlines: level 2 needs `8192 + 17 * 72 = 9416`, level 1 needs `8192 + 5 * 72 = 8552 <= 8800`: also level 1. With outlines and 8,500 bytes left, level 1 would be cut too (8552 > 8500) and the face is drawn whole.
</details>

**4.** Children of one face never crack against each other, but two neighboring faces of different levels can. Why?

<details><summary>Answer</summary>

Two children that share an edge compute its midpoint from the same two end vertices with the same symmetric formula, so they use the identical vertex, and the GPU's rasterizer draws a shared edge between identical points without a gap. A coarse face's edge is one straight segment from A to B; the fine neighbor's edge is A to M to B, where M is the projected 3D midpoint **rounded to a pixel**, which lies a fraction of a pixel off the line AB. The pixels between the line and the two segments are covered by neither face: the background shows (a T-junction crack).
</details>

**5.** The chapter's backing quad is drawn once per subdivided face. Why can no crack remain along the face's edge, and why must it be linked *after* the leaves?

<details><summary>Answer</summary>

The parents (whole faces) of a mesh share their projected vertices exactly, so together they cover the surface with no gap. A sliver left by the leaves lies inside their parent's outline, which is covered by the parent's backing quad; where a leaf overshoots, it merely overlaps the neighbor. The ordering table draws the **newest** packet of a slot **first** (`addPrim` inserts at the head), so linking the backing quad after the leaves, into the slot of the farthest leaf, draws it first, under them. Linked before, it would be drawn on top and hide the children.
</details>

**6.** Why does the criterion give one level to a whole **section** and not to each face from its own vertices?

<details><summary>Answer</summary>

The five faces of a section share their long edges (the lane borders and the wall bottoms). If each face chose its own level from its own vertices, neighbors would often get different levels, and every such edge would be a T-junction. One level per section, taken from the section's road-edge vertices, guarantees that the faces *within* a section agree, so only the rings between sections can differ, and the backing quad covers those.
</details>

**7.** A lane edge is 400 units long. At depth 3,000, how many pixels does it span (projection distance 320), and which level do the book's thresholds give if that is the section's nearest road-edge depth?

<details><summary>Answer</summary>

`400 * 320 / 3000 = 42.7` pixels. The thresholds are 4000 (32 pixels) and 2000 (64 pixels): `2000 <= 3000 < 4000`, so level 1. A screen-size rule "split above 32 px, again above 64 px" gives the same level here, because the depth rule is that rule for a 400-unit edge.
</details>

**8.** How many RTPT instructions does a level-2 face need, and how many vertices are projected? Why is that more than the 21 distinct ones?

<details><summary>Answer</summary>

Each split projects 5 new vertices with 2 RTPTs (3 + 2, the sixth slot repeated). A level-2 face has 1 + 4 = 5 splits: 10 RTPTs and 25 vertices projected. The grid has 5 x 5 = 25 vertices of which 4 are the parent's already projected corners, so 21 are new; the four midpoints shared by two children are computed twice (each child makes its own, 21 + 4 = 25) because that costs less than finding them, and the results are identical.
</details>

**9.** A face has one vertex behind the eye and three in front. In Chapter 34 it vanished. What happens at level 2, roughly, and what still cannot be drawn?

<details><summary>Answer</summary>

The face is split in 3D from the four camera-relative vectors (those are linear, so the midpoints are right even for the vertex behind the eye). Each of the 16 leaves is judged by its own four vertices: leaves whose four corners are at least `TRK_NEAR_Z` deep are drawn; the leaves around the vertex behind the eye (or nearer than 128) are dropped, as a face would be. The hole shrinks from the face to a few small quads next to the camera. Subdivision does not clip: a leaf that crosses the near plane is still dropped whole. The parent's NCLIP is not used here (its projection is meaningless); each leaf has its own.
</details>
