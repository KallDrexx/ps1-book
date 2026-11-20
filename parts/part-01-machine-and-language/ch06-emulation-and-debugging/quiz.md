# Chapter 6 Quiz

**1. Why does the book's verifier start PCSX-Redux with `-interpreter`?**
<details><summary>Answer</summary>
Breakpoints need the interpreter, which can check for them before every instruction. A dynarec runs translated blocks of host code with no per-instruction hook point; in the pinned Redux an exec breakpoint never fires under the dynarec, which is Redux's default CPU.
</details>

**2. What do you gain, and what do you pay, for a more accurate emulator?**
<details><summary>Answer</summary>
You gain behaviour closer to a real console (timing, DMA and bus behaviour, GPU details), so programs that race the hardware are tested honestly. You pay in speed, and sometimes in features aimed at players such as upscaling. Programs that only compute behave the same on all of them.
</details>

**3. You want to know which instruction overwrites a variable called `score`. Which breakpoint type do you set, and on what?**
<details><summary>Answer</summary>
A write breakpoint on the address of `score`. It stops at the store that changes it; then look at the instruction and the registers.
</details>

**4. How many real instructions does `li $t0, 0x12345678` assemble to, and which two? What about `li $t0, 100`?**
<details><summary>Answer</summary>
Two: `lui` with the upper half (adjusted by one if the lower half is 0x8000 or more) and `addiu` with the lower half. `li $t0, 100` is one instruction (`ori $t0, $zero, 100`).
</details>

**5. What does `bge $t0, $t1, target` expand to, and which register does it use?**
<details><summary>Answer</summary>
`slt $at, $t0, $t1` then `beq $at, $zero, target`. It uses `$at` as scratch; `$t0` and `$t1` are unchanged.
</details>

**6. Why is `bne $a, $b, loop` followed by `li $t6, 0x5EC0DE77` a bug, even though it assembles?**
<details><summary>Answer</summary>
The `li` is two words. A branch's delay slot holds exactly one instruction that always runs, so the first word (`lui`) runs on every pass and the second (`addiu`) is *after* the slot and runs only when the branch falls through. On a taken branch the register holds only the `lui` result, `0x5EC10000` (the upper half already bumped by one for the `addiu` that never runs).
</details>

**7. A register "changes by itself" between two lines of your source. Where do you look?**
<details><summary>Answer</summary>
In the disassembly (Assembly window), not the source. A pseudo-instruction between those lines may have expanded into instructions that write `$at`, or into a different number of words than you assumed.
</details>

**8. Your Lua script's breakpoint works for a few hits and then stops printing. A likely cause?**
<details><summary>Answer</summary>
The object returned by `PCSX.addBreakpoint` was not stored in a global (or any live variable), so Lua's garbage collector deleted it and the breakpoint was removed.
</details>

**9. You insert a `nop` near the top of a program to test something and your `findings.txt` addresses are suddenly "wrong". Why?**
<details><summary>Answer</summary>
Every instruction after the new one moves up by four bytes, and so do all later labels. Record addresses from an unmodified build, or recompute them from the new `.sym` file.
</details>
