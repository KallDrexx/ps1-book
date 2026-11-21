# Chapter 10 Quiz

**1. Which direction does the stack grow, and how do you allocate and free 32 bytes?**
<details><summary>Answer</summary>
Down, toward lower addresses. Allocate with `addiu $sp, $sp, -32`, free with `addiu $sp, $sp, 32`. There is no push or pop instruction.
</details>

**2. A function stores a value at `-4($sp)`, calls another function, then reads it back. What is wrong?**
<details><summary>Answer</summary>
Memory below `$sp` is free: the callee's frame (or an interrupt) overwrites it. Move `$sp` down first, then store inside the frame.
</details>

**3. Why must a function that calls another save `$ra`? Where does it go?**
<details><summary>Answer</summary>
`jal` overwrites `$ra` with the return address of the new call, so the function's own return address would be lost. It is stored in the function's frame and reloaded before `jr $ra`. A static word fails for recursion because each active call needs its own copy.
</details>

**4. The caller passes `a`, `b`, `c`, `d`, `e`, `f`. In which registers or addresses does a leaf callee find each one?**
<details><summary>Answer</summary>
`a`-`d` in `$a0`-`$a3`; `e` at `16($sp)` and `f` at `20($sp)`. If the callee has built a frame of `F` bytes, they are at `F + 16($sp)` and `F + 20($sp)`.
</details>

**5. What is the 16-byte home area, and who may use it?**
<details><summary>Answer</summary>
Space the caller reserves at the bottom of its frame (`0..15($sp)` at the call), even when the callee has fewer than four arguments. The callee may store `$a0`-`$a3` there or use it as scratch. The caller must keep nothing of its own there across a call.
</details>

**6. What is the smallest legal frame for a non-leaf function that saves only `$ra`, and why?**
<details><summary>Answer</summary>
24 bytes: 16 for the home area of its own callees, 4 for `$ra`, and 4 padding to keep `$sp` a multiple of 8. (Hand-written code may squeeze to 16 by keeping `$ra` in the 16 bytes its own caller reserved for it; compilers do not do this.)
</details>

**7. A recursive routine uses `$s0`. What must it do, and why is this safe for the caller?**
<details><summary>Answer</summary>
Save the old `$s0` in its frame in the prologue and restore it in the epilogue on every return path. The caller sees `$s0` unchanged across the call, so it can keep live values there.
</details>

**8. Under the verifier, `factorial` is right for n = 0 and 1 and fails from n = 2 up. A likely cause?**
<details><summary>Answer</summary>
A saved value in `0..15($sp)`: the callee's home area, which any callee may overwrite. The verifier overwrites it on every re-entry, so the bug shows as soon as the routine recurses. Without that it could stay hidden until a callee that really uses its home area comes along.
</details>

**9. Roughly how deep can a 24-byte-frame recursion go on the PS1, and what happens at the limit?**
<details><summary>Answer</summary>
About 2 MB / 24 bytes: over 80,000 frames, a little less than the full quotient because of the kernel area, program and data. There is no check: the stack runs into your data and code and corrupts them silently (and eventually into the kernel area at `0x80000000`).
</details>
