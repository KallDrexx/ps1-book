# Chapter 17 Quiz

**1. What does it mean to acknowledge the VBlank bit in `I_STAT`, and what value do you write?**
<details><summary>Answer</summary>
Clear it, so the next poll waits for the next VBlank. Write a 0 to bit 0; bits written as 1 are left alone. `0xFFFFFFFE` clears only VBlank.
</details>

**2. You poll `I_STAT` bit 0 but never acknowledge. What happens?**
<details><summary>Answer</summary>
Bit 0 stays set, so every later wait returns immediately. The loop runs as fast as it can instead of once per VBlank: the animation is too fast and may flicker.
</details>

**3. Why does polling work here without a BIOS interrupt handler getting in the way?**
<details><summary>Answer</summary>
`I_STAT` latches the event regardless of `I_MASK`. The CPU takes an interrupt (and a BIOS handler, which might acknowledge VBlank itself, runs) only if the `I_MASK` bit is set and the COP0 status register enables interrupts. In the book's Redux setup interrupts are off, and the given `main` also writes `I_MASK = 0`, so nothing else clears the bit.
</details>

**4. Which two GPU settings choose the buffer, and what does each do?**
<details><summary>Answer</summary>
GP1 `05h` (display start) selects what is shown. GP0 `E3h`/`E4h`/`E5h` (drawing area and offset) select where drawing goes. A fill ignores area and offset and uses absolute coordinates.
</details>

**5. With buffers at (0,0) and (0,240), what are the GP1 `05h` words for each?**
<details><summary>Answer</summary>
`0x05000000` for buffer 0, `0x05000000 | (240 << 10) = 0x0503C000` for buffer 1.
</details>

**6. Why wait for GPUSTAT bit 26 before the flip?**
<details><summary>Answer</summary>
Drawing commands run asynchronously. Flipping while the GPU is still drawing shows a half-finished frame.
</details>

**7. The gem is at x = 293 with vx = 5, and the maximum is 295. What are x and vx after one frame?**
<details><summary>Answer</summary>
298 is past the maximum, so x is clamped to 295 and vx becomes -5.
</details>

**8. Why does the back buffer need clearing every frame?**
<details><summary>Answer</summary>
It still holds the picture from two frames ago. Without a clear the old gem positions would stay, leaving a trail.
</details>

**9. How do you compute `buf * 240` without `mult`?**
<details><summary>Answer</summary>
`(buf << 8) - (buf << 4)`, since 240 = 256 - 16.
</details>
