# Chapter 7 Quiz

**1. Name the five pipeline stages in order and say what each does in one phrase.**
<details><summary>Answer</summary>
IF fetch the instruction, RD decode and read source registers, ALU compute (arithmetic, address, branch condition), MEM access memory for loads and stores, WB write the result to the register.
</details>

**2. What do `$t1` and `$t2` hold, and why? (`$t0` was 5 before; `0($a0)` holds 9.)**
```
lw    $t0, 0($a0)
addu  $t1, $t0, $zero
addu  $t2, $t0, $zero
```
<details><summary>Answer</summary>
`$t1 = 5` (the instruction in the load delay slot sees the old `$t0`), `$t2 = 9`. No error is raised; armips warns about the first `addu`.
</details>

**3. `bne $t0, $zero, loop` is followed by `addiu $t0, $t0, -1`. `$t0` is 1 when the branch executes. Is the branch taken, and what is `$t0` afterwards?**
<details><summary>Answer</summary>
Taken: the branch reads `$t0 = 1` before the slot runs. The slot then runs regardless, so `$t0` is 0 at the loop label.
</details>

**4. Why can `li $t1, 0x12345` not be used safely as a delay-slot filler?**
<details><summary>Answer</summary>
It expands to two instructions. Only the first (`lui`) lands in the slot; the second runs on the fall-through path only. Use single-instruction fillers.
</details>

**5. Give the three common sources of delay-slot filler and one risk of each.**
<details><summary>Answer</summary>
From above (an earlier instruction the branch does not depend on): it must not feed the branch condition. From the target: it must be harmless when the branch is not taken, and the branch must go to the following instruction. Loop bookkeeping (pointer or counter updates): it must be correct on the exit path too.
</details>

**6. armips accepts `.set noreorder`. True or false?**
<details><summary>Answer</summary>
False. armips has no `.set` directive (it reports an invalid opcode) and never reorders, so it always behaves like `noreorder`. GNU `as` and compiler output use `.set noreorder` to turn its reordering off.
</details>

**7. Why is `mflo` safe directly after `multu`, even though the multiply is slow?**
<details><summary>Answer</summary>
The R3000 interlocks on HI/LO: `mflo` stalls until the multiplier has finished. The cost is cycles, not wrong data, so independent work placed between the two is free.
</details>

**8. A `lw` sits in a branch delay slot and the branch is taken. Which instruction is the load's delay slot?**
<details><summary>Answer</summary>
The first instruction executed at the branch target. It sees the old register value; the one after it sees the loaded value.
</details>

**9. Why can the verifier prove a delay slot is "useful" by replacing it with a `nop`?**
<details><summary>Answer</summary>
If the results stay correct with a `nop` there, the instruction was doing no needed work (it was filler). A useful slot instruction changes the outcome when removed. The test cannot tell whether a better instruction exists for that slot.
</details>
