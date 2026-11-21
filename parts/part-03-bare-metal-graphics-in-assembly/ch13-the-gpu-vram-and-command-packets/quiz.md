# Chapter 13 Quiz

**1. Which port takes drawing commands and which takes display control? What do you read from the control port's address?**
<details><summary>Answer</summary>
GP0 (`0x1F801810`) takes drawing and VRAM commands; GP1 (`0x1F801814`) takes display control commands. Reading `0x1F801814` returns GPUSTAT, the status word. Reading `0x1F801810` returns GPUREAD (data coming back from the GPU, used for VRAM to CPU transfers).
</details>

**2. How big is VRAM, and can the CPU read or write it with `lw`/`sw`?**
<details><summary>Answer</summary>
1024 x 512 pixels of 16 bits each, 1 MB. It is not mapped into the CPU address space: everything goes through GP0 (and GPUREAD). The framebuffer is just a rectangle of VRAM; textures and palettes live in the rest.
</details>

**3. What is the difference between the display area and the drawing area? Which command sets each?**
<details><summary>Answer</summary>
The display area is the rectangle of VRAM sent to the TV; its top-left corner is set with GP1(05h) and its size by the display mode and ranges (GP1(06h), (07h), (08h)). The drawing area is the rectangle the GPU may draw into; it is set with GP0(E3h) (top-left) and GP0(E4h) (bottom-right, inclusive). They are independent; with double buffering you draw in one while displaying the other.
</details>

**4. You send fill rectangle (02h) with x = 20, w = 20. Which columns are painted? Which command would paint exactly columns 20 to 39?**
<details><summary>Answer</summary>
x is rounded down to a multiple of 16 (16) and the width is rounded up to a multiple of 16 (32), so columns 16 to 47 are painted. The monochrome rectangle GP0(60h) takes any x, y, w, h, and is clipped to the drawing area.
</details>

**5. Does a fill rectangle outside the drawing area do anything? Does a `60h` rectangle there?**
<details><summary>Answer</summary>
The fill ignores the drawing area and paints VRAM wherever you say (in 16-pixel steps). The `60h` rectangle is clipped to the drawing area, so a rectangle entirely outside it draws nothing.
</details>

**6. What byte order does the GPU expect for a color word, and what is in the top byte?**
<details><summary>Answer</summary>
`0xCCBBGGRR`: the command byte `CC` on top, then blue, green, red. If you hold colors as `0x00RRGGBB`, swap red and blue before OR-ing in the command byte. VRAM then keeps only the top 5 bits of each channel, so a screenshot shows a slightly different value (`0x80` comes back as `0x84`).
</details>

**7. Which GPUSTAT bit says "ready to receive command word"? When does it matter?**
<details><summary>Answer</summary>
Bit 26. The GPU buffers commands in a small FIFO and draws while the CPU runs on; if you send packets faster than it draws (for example many large fills), the FIFO fills up. Polling bit 26 before each packet makes the code correct on hardware, even though an emulator is always ready. Bit 27 is "ready to send VRAM to CPU" (Chapter 16) and bit 28 "ready to receive DMA block".
</details>

**8. Your `gpu_clear(color, x, y, w, h)` has five arguments. Where does `h` arrive?**
<details><summary>Answer</summary>
`color`, `x`, `y`, `w` come in `$a0`-`$a3`; the fifth argument `h` is on the caller's stack at `16($sp)` on entry (the first 16 bytes are the home area for `$a0`-`$a3`, Chapter 10). The caller must store it there before `jal`.
</details>

**9. NTSC or PAL: what changes for a 320x240 picture?**
<details><summary>Answer</summary>
NTSC is about 60 Hz with 263 lines of 3413 GPU clocks; PAL is about 50 Hz with 314 lines of 3406 clocks. The horizontal range is the same, but the vertical range sits at different TV lines (NTSC 16 to 256), and GP1(08h) bit 3 selects the video mode. PAL has room for about 288 visible lines, so a 240-line picture is centerd with a different range; VRAM and the commands are identical.
</details>
