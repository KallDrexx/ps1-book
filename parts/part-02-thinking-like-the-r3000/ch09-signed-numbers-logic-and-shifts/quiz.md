# Chapter 9 Quiz

**1. What is `0xFFFFFFFF` as an unsigned number and as a signed number? What is `-x` in terms of bit operations?**
<details><summary>Answer</summary>
4294967295 unsigned, -1 signed. Negation is invert all bits and add 1: `-x = ~x + 1`, the same as `0 - x`.
</details>

**2. Memory holds the byte `0xC8`. What do `lb` and `lbu` put in the register?**
<details><summary>Answer</summary>
`lb` sign-extends: `0xFFFFFFC8` (-56). `lbu` zero-extends: `0x000000C8` (200).
</details>

**3. What do `ori $t0, $zero, 0xFFFF` and `addiu $t0, $zero, -1` leave in `$t0`? Why do they differ?**
<details><summary>Answer</summary>
`0x0000FFFF` and `0xFFFFFFFF`. `ori` (like `andi` and `xori`) zero-extends its 16-bit immediate, while `addiu` sign-extends it.
</details>

**4. What is `-9 >> 2` with `sra`, and what is `-9 / 4` in C? How do you get the C answer with shifts?**
<details><summary>Answer</summary>
`sra` gives -3 (floor of -2.25); C gives -2 (toward zero). Add `2^2 - 1 = 3` to negative inputs before shifting: `(-9 + 3) >> 2 = -6 >> 2 = -2`. The bias is `(x sra 31) & 3`.
</details>

**5. What does `sllv $t2, $t0, $t1` do when `$t1` is 33?**
<details><summary>Answer</summary>
Only the low 5 bits of the amount are used: 33 & 31 = 1, so it shifts left by 1.
</details>

**6. A 12-bit signed field sits in the low bits of `$a0`. Which two instructions sign-extend it?**
<details><summary>Answer</summary>
`sll $v0, $a0, 20` then `sra $v0, $v0, 20` (20 = 32 - 12). The first moves the field's top bit to bit 31, the second copies it back down.
</details>

**7. Pack the color `0x00FF8040` (R=255, G=128, B=64) into BGR555.**
<details><summary>Answer</summary>
R: 255 >> 3 = 31, G: 128 >> 3 = 16, B: 64 >> 3 = 8. Result: `(8 << 10) | (16 << 5) | 31` = `0x221F`. Bit 15 is 0.
</details>

**8. Why does unpacking with just `c5 << 3` make white slightly gray? What does the replicate formula do instead?**
<details><summary>Answer</summary>
31 << 3 = 248, not 255, because the low three bits are zero. `(c5 << 3) | (c5 >> 2)` copies the top three bits into the bottom, so 31 becomes 255 and 0 stays 0.
</details>

**9. `swap_endian32(0x11223344)`: which shift moves which byte?**
<details><summary>Answer</summary>
Result `0x44332211`. Byte 0 (`0x44`) goes up by 24 (`sll 24`); byte 3 (`0x11`) goes down by 24 (`srl 24`); byte 1 (`0x33`) goes up by 8 and byte 2 (`0x22`) goes down by 8, each followed by a mask for its single byte (`0x00FF0000` and `0x0000FF00`).
</details>

**10. Why is `abs(0x80000000)` equal to `0x80000000`?**
<details><summary>Answer</summary>
The signed range is -2^31 to 2^31 - 1, so +2^31 does not exist. Inverting `0x80000000` and adding 1 wraps back to the same pattern.
</details>
