# Chapter 35 quiz

**1.** VRAM is 1024 x 512. How many bytes is that? The two 320 x 240 framebuffers are at (0,0) and (0,240): which columns and lines are left free for textures and CLUTs?

<details><summary>Answer</summary>

1024 x 512 x 2 bytes = 1 MiB (524,288 16-bit units). The buffers take x 0..319, y 0..479 (two blocks of 320 x 240). Free: every column from x = 320 to 1023 (all 512 lines), and lines 480..511 for x 0..319 (32 lines: room for CLUTs, not for tiles).
</details>

**2.** A 4-bpp texture is 64 x 64 texels. What size is it in VRAM, in units and lines? And at 8 bpp and 16 bpp?

<details><summary>Answer</summary>

4 bpp: 4 texels per unit, so 16 units x 64 lines. 8 bpp: 2 texels per unit, 32 x 64. 16 bpp: one texel per unit, 64 x 64.
</details>

**3.** A 4-bpp 64 x 64 tile is uploaded to VRAM (x = 700, y = 300). Is it a legal tile? If not, give the nearest legal x at or below 700 that keeps the same page. If yes, give its tpage word and `u0, v0`.

<details><summary>Answer</summary>

Not legal. Its page starts at x = 640, y = 256, and `700 mod 64 = 60`, so `u0 = 240` and `240 + 64 = 304` texels would cross the page's 256-texel width. The tile is 16 units wide, so `x mod 64` must be at most 48: the largest legal x in that page at or below 700 is 640 + 48 = 688. (There it would have `u0 = 192`, `v0 = 300 mod 256 = 44`, tpage word `10 | (1 << 4)` = 0x1A.)
</details>

**4.** A CLUT of a 4-bpp tile is placed at x = 70. What goes wrong, and what is the rule?

<details><summary>Answer</summary>

The CLUT word stores `x / 16` in 6 bits, so the x of a CLUT must be a multiple of 16. At x = 70 the word can only say 64 (4 x 16): the GPU would read the palette from (64, y), the wrong colors. The rule: `clut_x mod 16 = 0`; the y is free (0..511).
</details>

**5.** `tim_upload` and `tim_upload_at` both call `LoadImage`. What is different, and why does Chapter 35's second disc make the difference visible?

<details><summary>Answer</summary>

`tim_upload` copies the pixels to the rectangles the TIM names; `tim_upload_at` copies them to a destination you pass. The pixels are identical, only the target changes. The second disc's TIMs name rectangles on the framebuffers, so a loader that uses the TIM's own place destroys the picture and leaves the declared place empty.
</details>

**6.** A face has u values `(10, 40, 10, 40)` and `FLIP_H`. What are the mirrored u values? Why is "swap `u0` and `u1`" not a correct general rule?

<details><summary>Answer</summary>

`u_min + u_max - u` = 50 - u: `(40, 10, 40, 10)`. Swapping `u0` and `u1` gives the same result here (the U edge is `v0 -> v1`), but on a wall quad `u0 = u1` and the U edge runs `v0 -> v2`; swapping `u0` and `u1` changes nothing. The mirror inside the face's own U range works for both.
</details>

**7.** Why must the mirror be applied to the face's texture-local `u` *before* the tile's `u0` is added?

<details><summary>Answer</summary>

The mirror axis is the middle of the tile, not the middle of the page. `63 - (u0 + u)` points outside the tile (for `u0 = 128` it gives negative numbers); `u0 + (63 - u)` stays inside the tile.
</details>

**8.** The packets of two faces have the same tpage word but different CLUT words. What does that tell you about the tiles?

<details><summary>Answer</summary>

Their images are in the same texture page (possibly side by side, at different `u0, v0`), but each has its own palette: they are different tiles (or the same pixels with another palette). The tpage word says where the pixels are, the CLUT word what the pixel values mean.
</details>

**9.** The plan has a one-texel border around each tile. A face has UVs 0..63. Which UV does the face use for its leftmost column now, and what is the page cost?

<details><summary>Answer</summary>

The border is outside the tile's 64 texels, so the face's UVs do not change; the tile's origin `u0, v0` moves one texel inside the allocated rectangle. The cost: a 66 x 66 footprint per tile (at 4 bpp the width is rounded up to whole units: 68 texels = 17 units), so three tiles across a 64-unit page instead of four, and the origin `u0` is no longer a multiple of 64 texels.
</details>
