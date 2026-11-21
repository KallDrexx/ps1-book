# Chapter 8 Quiz

**1. After `jal foo` at address `0x80010100`, what is `$ra`, and why that value?**
<details><summary>Answer</summary>
`0x80010108`, the jal's address plus 8. The instruction at `+4` is the delay slot and has already run by the time the callee returns, so execution resumes after it.
</details>

**2. Name the caller-saved and callee-saved register groups.**
<details><summary>Answer</summary>
Caller-saved (callee may overwrite): `$v0-$v1`, `$a0-$a3`, `$t0-$t9`, `$at`. Callee-saved (callee must restore): `$s0-$s7`, `$gp`, `$sp`, `$fp`.
</details>

**3. A routine needs one extra scratch register. May it use `$s0` if it puts the old value back before returning? What if it does not have a place to put it?**
<details><summary>Answer</summary>
Yes, if it saves and restores it (on the stack, Chapter 10). With nowhere to save it, it must use a `$t` register instead.
</details>

**4. Why does this routine never return correctly? Which fix needs the stack?**
```
outer:  jal  inner
        nop
        jr   $ra
        nop
```
<details><summary>Answer</summary>
`jal inner` overwrites `$ra` with the address of the `jr`, so `outer` "returns" to its own `jr` forever. `outer` has to save its incoming `$ra` before the call and restore it after. A stack frame is the general solution; a static word works only for non-recursive code.
</details>

**5. What does the first instruction of `f` see in `$a0` here, if `$a0` held 111 and `0($t5)` holds 222?**
```
jal  f
lw   $a0, 0($t5)
```
<details><summary>Answer</summary>
111. The `lw` is in the delay slot, so `f`'s first instruction is the load's delay slot and still sees the old value; only from the second instruction on does `$a0` hold 222. Load before the `jal`, or use a non-load instruction in the slot.
</details>

**6. When is `jalr` used instead of `jal`?**
<details><summary>Answer</summary>
When the target address is in a register at run time: function pointers, handler tables, callbacks. `jal` has a fixed target encoded in the instruction.
</details>

**7. In which register does a function return its result? What about a second 32-bit value?**
<details><summary>Answer</summary>
`$v0`; the second goes in `$v1`.
</details>

**8. A `max_array` starts with `$v0 = 0` and keeps the larger value. What input breaks it?**
<details><summary>Answer</summary>
An all-negative array: the answer stays 0. Start from the first element.
</details>
