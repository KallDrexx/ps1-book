# Chapter 32 quiz

Answers are hidden under each question.

**1.** Why does the `.SHP` format use variable-length records instead of one size for every primitive? What does the parser use to find the next record?

<details><summary>Answer</summary>
A flat triangle needs 16 bytes, a textured Gouraud quad 44. One size for all (44) would waste up to 28 bytes on every cheap face, and drawing every face as the biggest primitive type would waste GPU time too. With variable records the parser reads the tag, knows the type's layout, and advances the pointer by that record's size (16, 20, 24, 32, 24, 32, 32 or 44). The `size` field stored in the record must agree with the tag's size; a mismatch means a damaged file.
</details>

**2.** A `GT4` record is 44 bytes in the file. How big is the `POLY_GT4` packet you build from it, and why are the two different?

<details><summary>Answer</summary>
52 bytes. The file record stores indices (2 bytes per vertex), a normal index, alignment pads and a color per vertex, in a compact order that suits the disc. The packet is what the GPU reads: the OT tag (4 bytes), then per vertex a color word, an XY word and a UV(+CLUT/tpage) word, in the GPU's order. Only the colors carry over unchanged (even the UVs get the texture's origin added), so you never copy a record into a packet; you build the packet field by field.
</details>

**3.** `POLY_F4 *p = ot_alloc(sizeof(p));` compiles and does not crash. What is wrong?

<details><summary>Answer</summary>
`sizeof(p)` is the size of the *pointer* (4 bytes), not of the packet (24). `ot_alloc` returns a 4-byte block; the next allocation starts 4 bytes later and overwrites the quad's data, so the picture is garbage. Use `sizeof(*p)` (the type `p` points to) or `sizeof(POLY_F4)`. It also differs from the file record size (20 bytes for an `F4`), which is a third, unrelated number.
</details>

**4.** A texture of the pack is 8 bpp, its image is at VRAM (704, 256) and its CLUT at (16, 490). Compute its TSB, CBA and UV origin (opaque).

<details><summary>Answer</summary>
`TSB = (704/64) | ((256/256) << 4) | (0 << 5) | (1 << 7) = 11 | 16 | 128 = 155 = 0x009B`. `CBA = (16/16) | (490 << 6) = 1 | 31360 = 31361 = 0x7A81`. UV origin: `((704 mod 64) * 2, 256 mod 256) = (0, 0)`. A record UV of (10, 20) becomes (10, 20) in this texture's page.
</details>

**5.** Why does the file store texture-*local* UVs and not absolute ones?

<details><summary>Answer</summary>
The model should not depend on where the textures end up in VRAM. A pack's textures may be placed in different pages (the verifier's second disc does exactly that), or moved so that two packs do not overlap. With local UVs the file says "texel (63, 0) of texture 1"; the loader adds the texture's origin `(u0, v0)` that the store learned from the TIM header. The same `.SHP` then works wherever its textures were uploaded.
</details>

**6.** `prims_size` in a header is `0xFFFFFFF0` and `prims_offset` is `0x288`. The check `prims_offset + prims_size <= size` passes. Why, and how should you write it?

<details><summary>Answer</summary>
32-bit unsigned addition wraps: `0x288 + 0xFFFFFFF0 = 0x278` (mod 2^32), which is small. First prove `prims_offset <= size`, then compare `prims_size == size - prims_offset` (the format says they must be exactly equal). The same care applies to any `count * size` product from a file.
</details>

**7.** A wing is flagged double-sided and `NCLIP` gives a negative area. Is it drawn? What if the area is 0?

<details><summary>Answer</summary>
Yes, drawn: a double-sided record is visible from both sides, so either sign is fine. An area of 0 means the projected triangle is degenerate (edge-on): the book's rule never draws it, for any record. A single-sided record is drawn only when `area > 0`.
</details>

**8.** In `render_mode 0` an `FT4` record is drawn as an `F4`, and a `GT3` as a `G3`. Why is that a useful mode while you are writing the loader?

<details><summary>Answer</summary>
It separates two kinds of bug. Flat mode needs only the parser, the transform, the culling and the ordering table: if the ship looks right, the geometry and the walk are right. Textured mode adds the texture store, UV arithmetic, `tpage` and `clut`: if only that mode is wrong, the fault is in those. Without the fallback a missing triangle could be a parser bug or a bad texture, and you would not know which.
</details>

**9.** You advance the record pointer with `rec += sizeof(ShpPrim)`. What happens?

<details><summary>Answer</summary>
`ShpPrim` is 40 bytes, the decoded form. Records are 16 to 44 bytes, so after the first step you are almost never at the start of a record: the "tag" byte you read is part of a vertex index, a UV or a color, and a failed tag/size check (or garbage geometry) follows. Advance by the size of the record you just decoded (`shp_decode` returns it).
</details>
