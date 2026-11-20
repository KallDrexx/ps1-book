# Chapter 3 Quiz

**1. After `lb $t0, 0($a0)` reads the byte `0x80`, what does `$t0` hold? And after `lbu`?**
<details><summary>Answer</summary>
`lb` sign-extends: `0xFFFFFF80` (-128). `lbu` zero-extends: `0x00000080` (128).
</details>

**2. Which registers does the hardware treat specially, and which are only convention?**
<details><summary>Answer</summary>
Hardware: `$zero` (always 0) and `$ra` (written by `jal`). Every other role (`$t`, `$s`, `$a`, `$v`, `$sp`...) is a software convention.
</details>

**3. What is the difference between `add` and `addu`?**
<details><summary>Answer</summary>
Same result bits. `add` raises an Overflow exception when the signed result does not fit in 32 bits; `addu` wraps silently. The "u" does not mean the operands are unsigned.
</details>

**4. How do you subtract 100 from `$t0` with one instruction?**
<details><summary>Answer</summary>
`addiu $t0, $t0, -100`. There is no subtract-immediate; the 16-bit immediate is sign-extended, so a negative one subtracts.
</details>

**5. Why is `addiu $t0, $zero, 0x8000` not 32768?**
<details><summary>Answer</summary>
The immediate is sign-extended: `0x8000` has bit 15 set, so it becomes `0xFFFF8000` (-32768). Use `ori $t0, $zero, 0x8000` for 32768.
</details>

**6. This code stores the wrong value. Why?**
```
lw  $t1, 0($t0)
sw  $t1, 4($t0)
```
<details><summary>Answer</summary>
Load delay: the `sw` runs before `$t1` has the loaded value, so it stores the old `$t1`. Put a `nop` or an unrelated instruction between them.
</details>

**7. `subu $t3, $t1, $t2` with `$t1 = 5` and `$t2 = 8`. What is in `$t3`?**
<details><summary>Answer</summary>
`0xFFFFFFFD` (-3). The order is `rs - rt`, and the result wraps modulo 2^32 without raising an exception.
</details>

**8. A table needs to be read with `lw`. What must you write before it, and where should it not go?**
<details><summary>Answer</summary>
`.align 4` so the address is a multiple of 4 (otherwise `lw` faults). It must not sit inside the instruction path, for example before `done:`, or the CPU would execute the data.
</details>
