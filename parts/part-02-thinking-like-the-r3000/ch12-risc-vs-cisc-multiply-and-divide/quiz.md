# Chapter 12 Quiz

**1. Name two properties of a RISC like MIPS that CISC designs such as x86 or the 68000 usually lack.**
<details><summary>Answer</summary>
Fixed-length instructions (4 bytes) and a load/store architecture (only loads and stores touch memory; arithmetic works on registers). Also many general registers and simple, easily pipelined instructions. The price is lower code density.
</details>

**2. Where does `multu $a0, $a1` put its result? How do you get the low 32 bits and the high 32 bits?**
<details><summary>Answer</summary>
In the special registers HI (upper half) and LO (lower half). `mflo rd` copies the low 32 bits, `mfhi rd` the high 32 bits.
</details>

**3. You write `multu $t0, $t1` followed immediately by `mflo $t2`. Is the value right? What does it cost?**
<details><summary>Answer</summary>
Right: the R3000 interlocks on `mfhi`/`mflo`, stalling until the unit is done. It costs up to 6, 9 or 13 cycles of stall, depending on the size of `rs` (`$t0`). Independent instructions between the two hide that time.
</details>

**4. `divu` or `div`: how long, and what is the cheaper alternative when the divisor is a constant?**
<details><summary>Answer</summary>
36 cycles, fixed. For a constant divisor multiply by its fixed-point reciprocal and shift (for example `x/10 = (x * 0xCCCCCCCD) >> 35` using `multu` and `mfhi`), or for powers of two just `srl`/`sra`.
</details>

**5. What do `divu` and `div` leave in HI and LO when the divisor is zero? Does the CPU trap?**
<details><summary>Answer</summary>
No trap. `divu x/0`: HI = x, LO = `0xFFFFFFFF`. `div x/0`: HI = x, LO = -1 if x >= 0, +1 if x < 0 (psx-spx calls these values garbage). Software must test for zero itself.
</details>

**6. What is the rule about `mfhi`/`mflo` followed by `mult`/`div`, and who enforces it?**
<details><summary>Answer</summary>
MIPS I says that if either of the two instructions after an `mfhi`/`mflo` is a `mult`/`div` (or `mthi`/`mtlo`), the value the move read is undefined; psx-spx only mentions a not-understood "don't touch lo/hi for 2 cycles or so" rule. The safe (conservative) rule is two other instructions in between. Nothing enforces it: there is no exception, armips does not warn and most emulators ignore it, so the assembly programmer (or GCC) has to obey it.
</details>

**7. Write `x * 1000` using shifts and subtracts only. How many shifts?**
<details><summary>Answer</summary>
`1000 = 1024 - 16 - 8`, so `(x << 10) - (x << 4) - (x << 3)`: three shifts and two subtracts.
</details>

**8. Why does `x * 320` with shifts give the same low 32 bits as `mult`, even for negative or overflowing `x`?**
<details><summary>Answer</summary>
Multiplication by a power of two is a left shift, and sums are taken modulo 2^32, exactly like the low word of a product. The low 32 bits of a signed and an unsigned product are the same.
</details>

**9. A word loop copies 1024 bytes. Why can't it simply `lw`/`sw` from the first byte if `dst` is at address 0x80100001?**
<details><summary>Answer</summary>
`lw`/`sw` need a multiple of 4; otherwise an address-error exception. Copy a byte head (3 bytes here) until `dst` is aligned. If `src` is now aligned too (it started with the same `& 3`), run the word loop, then a byte tail. If `src` and `dst` differ mod 4 you need a byte loop or `lwl`/`lwr`.
</details>

**10. Why does `(w - 0x01010101) & ~w & 0x80808080` detect a zero byte in `w`, and why is the `& ~w` needed?**
<details><summary>Answer</summary>
Subtracting 1 from a zero byte borrows and sets its top bit; `& 0x80808080` keeps top bits. But a byte from 0x81 to 0xFF still has its top bit set after subtracting 1, giving a false positive; `& ~w` clears every byte whose top bit was set in `w`.
</details>
