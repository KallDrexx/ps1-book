# Chapter 4 Quiz

**1. What does "branch delay slot" mean, and what do you put there in this chapter?**
<details><summary>Answer</summary>
The instruction after a branch or jump always executes, taken or not. Put a `nop` there; Chapter 7 shows how to use it productively.
</details>

**2. A `bne` sits at `0x80010020` and its target is `0x80010010`. What is the stored offset?**
<details><summary>Answer</summary>
Offsets count words from the delay slot (`0x80010024`): `(0x80010010 - 0x80010024) / 4 = -5`.
</details>

**3. There is no `blt $t0, $t1, label` instruction. How do you branch if `$t0 < $t1` (signed)?**
<details><summary>Answer</summary>
`slt $t2, $t0, $t1` then `bne $t2, $zero, label` (and a `nop`). `slt` writes 1 if the test is true.
</details>

**4. `$t0 = 0xFFFFFFF0`. What do `slti $t1, $t0, 100` and `sltiu $t1, $t0, 100` produce?**
<details><summary>Answer</summary>
`slti` gives 1 (-16 < 100). `sltiu` gives 0 (4,294,967,280 is not below 100).
</details>

**5. Which single instruction branches only when `$t0` is zero?**
<details><summary>Answer</summary>
`beq $t0, $zero, label` (`beqz` is the pseudo form). `blez` and `bgez` also branch on zero, but on negative or positive values too.
</details>

**6. Why does `j` reach any address in RAM but a branch only about +/-128 KiB?**
<details><summary>Answer</summary>
`j` stores the low 26 bits of the word address and takes the top 4 bits from the delay slot's address, covering a 256 MB region. A branch stores only a 16-bit signed word offset relative to the delay slot.
</details>

**7. The loop below ends with `bgtz`. What happens for a starting `n` of -1, and what if `bgtz` were `bne $t0, $zero, loop`?**
```
loop:  ...
       addiu $t0, $t0, -1
       bgtz  $t0, loop
       nop
```
<details><summary>Answer</summary>
With `bgtz` the body runs once and exits (-2 is not greater than 0). With `bne` against zero, a negative start never reaches 0, so the loop runs about 4 billion times. Choose the exit test to match the values you can receive.
</details>

**8. How can you count how many times `a < b` held without any branch?**
<details><summary>Answer</summary>
`slt t, a, b` then `addu count, count, t`, because `slt` produces exactly 0 or 1.
</details>
