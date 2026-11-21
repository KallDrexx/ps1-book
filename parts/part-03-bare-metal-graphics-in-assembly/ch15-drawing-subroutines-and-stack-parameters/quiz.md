# Chapter 15 Quiz

**1. Where do the seven arguments of `draw_flat_tri(color, x0,y0, x1,y1, x2,y2)` go?**
<details><summary>Answer</summary>
`color`, `x0`, `y0`, `x1` in `$a0`-`$a3`. `y1`, `x2`, `y2` at `16($sp)`, `20($sp)`, `24($sp)` as seen at entry, stored by the caller.
</details>

**2. `draw_gouraud_tri(c0,x0,y0, c1,x1,y1, c2,x2,y2)`: which argument is in `$a3`, and where is `c2`?**
<details><summary>Answer</summary>
`$a3` = `c1` (argument 3). `c2` is argument 6, at `24($sp)` at entry.
</details>

**3. A callee does `addiu $sp, $sp, -24` first. Where is its argument 5 now?**
<details><summary>Answer</summary>
At `24 + 4*5 = 44($sp)`. At entry it was at `20($sp)`; the frame moved `$sp` 24 bytes down.
</details>

**4. What is the home area, and what may the callee do with it?**
<details><summary>Answer</summary>
The 16 bytes at `0..15($sp)` at entry, reserved by the caller for `$a0`-`$a3`. The callee may store the argument registers (or anything else) there. Together with the stack arguments they then form one contiguous array.
</details>

**5. With the array trick of 5.3, why does `draw_flat_tri` need no `$s` register?**
<details><summary>Answer</summary>
Every argument stays in memory (the home area for arguments 0-3, the caller's stack words for the rest) and is reloaded when needed, so nothing has to survive in a register across the calls to `pack_color` and `pack_vertex`. Only `$ra` must be saved.
</details>

**6. Give one advantage and one disadvantage of passing packed vertex words instead of separate x and y.**
<details><summary>Answer</summary>
Advantage: fewer arguments (a triangle takes four, all in registers) and no packing in the callee. Disadvantage: the caller must pack (or already hold packed words), and the code is harder to read and call by hand.
</details>

**7. How many GPUSTAT waits does the verifier accept for a six-word Gouraud packet, and where?**
<details><summary>Answer</summary>
At least one read before the first word, and no reads between the words. A wait before each later word would never end: bit 26 means "ready for a new command", and it stays clear while the GPU still expects parameters of the current one.
</details>

**8. In the scene table, how do you recover x and y (signed) from a packed vertex word in `$t0`?**
<details><summary>Answer</summary>
`sll $t1, $t0, 16` then `sra $t1, $t1, 16` gives x; `sra $t2, $t0, 16` gives y. A logical shift would lose the sign.
</details>

**9. Does a bare-metal program have a heap? Name two places you could keep a scratch buffer.**
<details><summary>Answer</summary>
No. Use space reserved in your data (`.fill`), a fixed region of free RAM between `__exe_end` and the stack, or the 1 KB scratchpad at `0x1F800000`.
</details>
