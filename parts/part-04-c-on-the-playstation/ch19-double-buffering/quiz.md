# Chapter 19 Quiz

**1.** Why does drawing into the buffer being displayed look wrong, even if every frame is eventually complete?

<details><summary>Answer</summary>

The GPU scans VRAM out continuously. The viewer sees the clear and each primitive appear partway through a scan: flicker and half-drawn frames. Drawing into a hidden buffer shows only finished frames.
</details>

**2.** Which GPU commands do a `DISPENV` and a `DRAWENV` turn into?

<details><summary>Answer</summary>

`DISPENV`: GP1 05h (display start) plus 06h/07h/08h (horizontal and vertical range, video mode). `DRAWENV`: GP0 E1h/E2h (texture page, texture window), E3h/E4h (drawing area), E5h (draw offset) and, with `isbg`, a 02h fill of the area.
</details>

**3.** Which of `PutDispEnv` and `PutDrawEnv` takes effect immediately, and why does it matter for the frame loop?

<details><summary>Answer</summary>

`PutDispEnv` writes the GP1 registers at once, so it must be placed right after `VSync` and after the frame is finished. `PutDrawEnv` is queued behind earlier work and runs when the GPU is free, so it can be issued early in the frame.
</details>

**4.** Give the order of a frame's five steps after the clear, and say what goes wrong if `VSync(0)` is removed.

<details><summary>Answer</summary>

Draw, `DrawSync(0)`, `VSync(0)`, `PutDispEnv` of the buffer just drawn, swap the back-buffer index. Without `VSync` the display start changes mid-scan (tearing) and the loop runs as fast as it can instead of at the frame rate.
</details>

**5.** Why must the color be set with `setRGB0` before `PutDrawEnv`?

<details><summary>Answer</summary>

`PutDrawEnv` builds and queues the setup/fill packet from the structure's current contents. Changing the color afterwards only affects that environment's next `PutDrawEnv`, which with two buffers is two frames later.
</details>

**6.** Both buffers use the same drawing code to draw a rectangle at y = 104. How does it land in buffer 1 (VRAM y = 240)?

<details><summary>Answer</summary>

`PutDrawEnv` sends the GPU a draw offset (E5h) of `clip`'s corner plus `ofs`. `SetDefDrawEnv` set `clip` to (0, 240, 320, 240) and `ofs` to (0, 0), so the offset is (0, 240). The GPU adds it to every primitive coordinate, so y = 104 becomes VRAM y = 344.
</details>

**7.** `DrawPrim` is called right after `PutDrawEnv`, yet the rectangle is never covered by the clear. Why?

<details><summary>Answer</summary>

`DrawPrim` first waits for the drawing queue to empty and the GPU to go idle (like `DrawSync(0)`), so the queued environment, including the `isbg` clear, completes before the rectangle's packet is sent. It then only starts the DMA and returns, which is why the `TILE` must be `static`.
</details>

**8.** A frame takes 1.5 frame periods to draw. What frame rate results, and where does the time go?

<details><summary>Answer</summary>

30 fps (NTSC). `VSync(0)` waits for the next VBlank after the work is done, so each frame takes two frame periods, with half a period idle inside `VSync`.
</details>

**9.** What does the verifier see if both environments are placed at VRAM y = 0, and which check catches it?

<details><summary>Answer</summary>

The probe sees GP1 05h always with y = 0, so "display start alternates" fails. The screenshot checks usually fail too: right after the swap the program clears and redraws the next frame into the only buffer, so the screen no longer shows the color of the frame that was just "shown".
</details>
