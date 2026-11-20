# Chapter 11 Quiz

**1. For each of `lb`, `lhu`, `lw`, `sh`: what must the address satisfy, and what happens if it does not?**
<details><summary>Answer</summary>
`lb` needs nothing. `lhu` and `sh` need a multiple of 2, `lw` a multiple of 4. A violation raises an address-error exception: code 4 (AdEL) for loads, 5 (AdES) for stores. The instruction does not complete, the address goes to Cop0 `BadVAddr`, the faulting instruction's address to `EPC`, and the CPU jumps to `0x80000080`.
</details>

**2. `SVECTOR` has three 16-bit fields. Why is it 8 bytes and not 6?**
<details><summary>Answer</summary>
The `pad` field rounds it up to 8, so that in an array every element starts at a multiple of 8. With 6-byte elements the halfword fields would still be even, but every other element would start at an address that is 2 mod 4, so loading `vx,vy` as one word (as the GTE's `lwc2` does) would raise an address error.
</details>

**3. A table starts at `vertices`, which is 8-aligned. What is the address of `vz` of vertex 5?**
<details><summary>Answer</summary>
`vertices + 5*8 + 4 = vertices + 44`. (base + index * size + field offset.)
</details>

**4. In armips, what does `.align 4` do, and why is `.align 2` after a `.byte` not enough in front of a `.word`?**
<details><summary>Answer</summary>
`.align n` pads with zero bytes up to the next multiple of `n` bytes (a power of two, not an exponent). `.align 2` only guarantees an even address; a `.word` needs a multiple of 4. `.word` and `.halfword` never align themselves, and armips does not warn.
</details>

**5. Memory at addresses 0 to 7 holds `11 22 33 44 55 66 77 88`. Which two instructions load the word at address 1 into `$t0`, and what does `$t0` hold?**
<details><summary>Answer</summary>
`lwr $t0, 1($base)` and `lwl $t0, 4($base)` (offsets A and A+3). `lwr` fills the low bytes with `22 33 44`, `lwl` the top byte with `55`. `$t0` = `0x55443322`.
</details>

**6. When may an instruction use the register just written by `lwr`? By `lw`?**
<details><summary>Answer</summary>
After `lw` it may not in the very next instruction (load delay slot). After `lwr`, the next instruction may be the matching `lwl` on the same register, which sees the merged value. Any other reader must still wait one instruction.
</details>

**7. `$t0` = 32767 (a `vx`), you add 1 and `sh` it. What does a later `lh` return? Why?**
<details><summary>Answer</summary>
-32768. `sh` stores the low 16 bits (`0x8000`), and `lh` sign-extends them. There is no overflow check; 16-bit fields wrap.
</details>

**8. `vt_pack` is passed a buffer at an odd address. Name one correct and one crashing way to store the 32-bit x,y pair.**
<details><summary>Answer</summary>
Correct: `swr rt, 0(A)` plus `swl rt, 3(A)`, or four `sb`. Crashing: `sw` (and `sh` for z): misaligned stores raise AdES.
</details>
