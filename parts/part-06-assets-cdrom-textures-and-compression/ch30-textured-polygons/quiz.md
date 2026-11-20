# Chapter 30 quiz

Answers are hidden under each question.

**1.** A texture page is 256 x 256 texels. How many 16-bit VRAM units wide is a page for 4-bpp, 8-bpp and 16-bpp textures, and why do they differ?

<details><summary>Answer</summary>
64, 128 and 256 units. A unit is 16 bits: it holds 4 four-bit palette indices, 2 eight-bit indices or 1 colour, so 256 texels need 64, 128 or 256 units. Pages *start* every 64 units in x (and 256 lines in y), which is what `x/64` and `y/256` in the tpage word count.
</details>

**2.** An 8-bpp texture is at VRAM (704, 0) with its CLUT at (0, 496). Give the tpage word, the CLUT word and the UV origin.

<details><summary>Answer</summary>
tpage = 704/64 + (0/256) * 16 + abr * 32 + tp * 128 = 11 + 0 + 0 + 128 = `0x8B`. CLUT = 0/16 + 496 * 64 = `0x7C00`. UV origin = ((704 mod 64) * 2, 0 mod 256) = (0, 0).
</details>

**3.** A 4-bpp, 128 x 64 texture sits at VRAM x = 964, y = 320. Which page and UV origin, and does it fit?

<details><summary>Answer</summary>
Page column 964/64 = 15 (the page starts at 960), page row 320/256 = 1. Origin `u0 = (964 mod 64) * 4 = 16`, `v0 = 320 mod 256 = 64`. It fits: 16 + 128 = 144 <= 256 and 64 + 64 = 128 <= 256. Its image block is 32 units wide: 964..995, inside the 1024 limit.
</details>

**4.** A 4-bpp image of 64 x 64 pixels. What are `w` and `h` in its TIM image block, and how many bytes of pixel data?

<details><summary>Answer</summary>
`w` = 64 / 4 = 16 (16-bit units, not pixels), `h` = 64, data = 16 * 64 * 2 = 2048 bytes. The block's `bnum` is 12 + 2048 = 2060.
</details>

**5.** Which fields of a polygon say where the texture is and which palette it uses, and which part of a TIM each is derived from?

<details><summary>Answer</summary>
`tpage` (page column, page row, depth) comes from the **image** block's x, y and the TIM's pmode. `clut` comes from the **CLUT** block's x and y. The corner UVs are texel offsets inside the page: the image's `(x mod 64) * m, y mod 256` plus the position inside the texture.
</details>

**6.** Your cube face uses the Z-order corners 0 (top-left), 1 (top-right), 2 (bottom-left), 3 (bottom-right). Write the UVs of a 128 x 64 texture whose origin in the page is (16, 64). Why is the right edge 143, not 144?

<details><summary>Answer</summary>
Corner 0: (16, 64); 1: (143, 64); 2: (16, 127); 3: (143, 127). The last texel column is `u0 + w - 1` = 143; 144 is the first texel of whatever lies to the right of the texture in the page (and 256 would overflow the byte). Using perimeter order `(0,0) (w,0) (w,h) (0,h)` for a Z-order quad swaps corners 2 and 3.
</details>

**7.** The polygon's colour is (128, 128, 128) in one program and (255, 255, 255) in another. What changes on screen? What does command `0x2D` do?

<details><summary>Answer</summary>
Each texel channel is multiplied by `colour / 128`: 128 leaves the texture as it is, 255 brightens it by almost 2x (saturating at 255). Command `0x2D` is "raw texture": the polygon colour is ignored and the texel is drawn as it is.
</details>

**8.** Why does the X on a textured quad that is seen at an angle bend, and why does the texture of a spinning cube swim?

<details><summary>Answer</summary>
The GPU splits the quad into two triangles and interpolates `u, v` linearly in screen space (affine). A perspective view needs `u/z` and `v/z` interpolated and divided per pixel, so straight lines in the texture bend where the triangles meet. The swimming comes from integer vertex coordinates: the corners jump between pixels as the cube turns, and with them the whole mapping. Remedies: smaller or subdivided polygons, keeping polygons away from the camera, textures that tolerate warping.
</details>

**9.** Why does `tim_parse` check that the CLUT's x is a multiple of 16 and that the image lies in one page, when `LoadImage` would happily upload it anyway?

<details><summary>Answer</summary>
Because the polygon's words cannot express otherwise: the CLUT word stores `x/16` (the low bits would be lost, selecting another palette) and the UVs are bytes inside one 256 x 256 page. The upload would succeed and the texture would still be drawn wrong, so a loader should reject the file where the cause is visible.
</details>

**10.** A texture with an opaque black outline disappears at the outline. What is wrong, and what is the fix?

<details><summary>Answer</summary>
The palette entry is `0x0000`, which the GPU treats as transparent. Store opaque black as `0x0421` (the book's `img2tim.py` does) or any non-zero colour.
</details>
