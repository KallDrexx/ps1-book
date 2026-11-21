# Chapter 16 Quiz

**1. What are the three header words of a CPU to VRAM transfer of a 40x30 rectangle to (10, 20)?**
<details><summary>Answer</summary>
`0xA0000000`, `(20 << 16) | 10 = 0x0014000A`, `(30 << 16) | 40 = 0x001E0028`. Then 600 data words.
</details>

**2. In a data word, which pixel is in the low half?**
<details><summary>Answer</summary>
The left one (the lower x). The right pixel is in the high half. Pixels are sent row by row.
</details>

**3. A 7x5 rectangle is uploaded. How many data words, and what is in the last one?**
<details><summary>Answer</summary>
35 units are 18 words (rounded up). The last word holds one real pixel in its low half; the high half is padding the GPU ignores.
</details>

**4. You send one data word too few. What happens to your next packet?**
<details><summary>Answer</summary>
The GPU still expects data, so it takes the first word of the next packet as pixels and writes it to VRAM. That packet has lost its command word: its remaining words are read as commands, and everything after may go wrong.
</details>

**5. Why does a routine that waits for GPUSTAT bit 26 before each data word hang?**
<details><summary>Answer</summary>
From the first header word on, bit 26 ("ready for a command word") is 0: the GPU wants parameters or data, not a command. It becomes 1 again only after the last data word. Wait once, before the first header word.
</details>

**6. How wide, in 16-bit units, is a 320-pixel line in 24-bit mode? How many units are 2 pixels?**
<details><summary>Answer</summary>
480 units (320 * 3 / 2). Two pixels are 6 bytes = 3 units.
</details>

**7. What byte order does a 24-bit pixel have in VRAM, and what are its 16-bit units for pixel 0?**
<details><summary>Answer</summary>
R, G, B (red at the lowest address). As little-endian 16-bit units, unit 0 is `G0:R0` (green in the high byte, red in the low byte), and unit 1 starts with `B0` in its low byte.
</details>

**8. Write `px * 3 / 2` without `mult` or `div`.**
<details><summary>Answer</summary>
`px + (px >> 1)` (valid when `px` is even, so the result is whole): `srl t, a0, 1` then `addu v0, a0, t`.
</details>

**9. Which command selects the 24-bit display, and what are its bits for a 320x240 NTSC screen?**
<details><summary>Answer</summary>
GP1 `08h`: `0x08000011`. Bits 0-1 = 1 (320 wide), bit 2 = 0 (240 high), bit 3 = 0 (NTSC), bit 4 = 1 (24-bit color).
</details>
