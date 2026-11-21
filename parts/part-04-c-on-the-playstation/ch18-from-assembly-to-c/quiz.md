# Chapter 18 Quiz

**1.** What does `mipsel-none-elf-gcc` mean, part by part?

<details><summary>Answer</summary>

It is a cross-compiler (it runs on your PC but emits code for another machine). `mipsel`: little-endian MIPS, the R3000's byte order. `none`: no operating system on the target. `elf`: the output format (`elf2x` later converts it to a PSX-EXE).
</details>

**2.** The PSX-EXE header's start address is not `main`. What runs first? Name two things it does before `main`.

<details><summary>Answer</summary>

`_start`, the SDK's startup code (the "crt0"). It sets `$gp`, zeroes `.bss`, initializes the heap and runs static constructors, then calls `main`.
</details>

**3.** What does a linker script decide? Name one fact from `exe.ld`.

<details><summary>Answer</summary>

Where each section of the program goes in memory and what the entry point is. `exe.ld` starts `.text` and `.rodata` at `0x80010000` (`APP_RAM`) and sets `ENTRY(_start)`.
</details>

**4.** In your `.s` file you wrote the label `rgb888_to_bgr555:` but the linker says `undefined reference to rgb888_to_bgr555`. Give two likely causes.

<details><summary>Answer</summary>

There is no `.globl rgb888_to_bgr555`, so the label is local to the file; or the `.s` file is not listed in `psn00bsdk_add_executable(...)`, so it was never assembled.
</details>

**5.** The `-O0` output for `expand5` has a `nop` after each `lw` that reloads the argument; the `-O2` output has no `nop` and puts an `or` after `jr`. What is each, and who put it there?

<details><summary>Answer</summary>

The `nop` after `lw` fills the load delay slot, because the next instruction uses the loaded register. The `or` after `jr` is useful work in the branch delay slot, which executes before the jump lands. GCC schedules both itself and tells gas not to reorder with `.set noreorder`.
</details>

**6.** In gas for MIPS, what does `.align 4` do? How would you ask for 4-byte alignment?

<details><summary>Answer</summary>

It aligns to 2^4 = 16 bytes (the argument is a power of two, not a byte count). `.align 2` or `.balign 4` gives 4-byte alignment. armips' `.align 4` means 4 bytes, so porting needs care.
</details>

**7.** A C function calls `int f(int a, int b)` implemented in assembly. Which registers carry `a`, `b` and the result, and which registers may the assembly use without saving them?

<details><summary>Answer</summary>

`a` in `$a0`, `b` in `$a1`, the result in `$v0`. The caller-saved registers `$t0-$t9`, `$a0-$a3`, `$v0-$v1`, `$at` can be used freely. `$s0-$s7`, `$gp`, `$sp`, `$fp` must be preserved.
</details>

**8.** An assembly routine calls a C function. Why must it save `$ra`, and why does it need a frame even if it uses no local variables?

<details><summary>Answer</summary>

`jal` overwrites `$ra` with the address after the call, so the routine's own return address would be lost. It also needs somewhere to save `$ra` (and any `$s` registers) and must reserve the callee's 16-byte argument home area on the stack.
</details>

**9.** Your program contains a global variable that nothing reads, and it is missing from `nm`. Why?

<details><summary>Answer</summary>

The SDK links with `-ffunction-sections -fdata-sections` and `-Wl,-gc-sections`, so the linker discards sections nothing refers to.
</details>

**10.** `rgb888_to_bgr555(0x00FF8040)` returns a 15-bit color. Why does the project widen it again with `expand5` before calling `setRGB0`?

<details><summary>Answer</summary>

`setRGB0` and the GPU fill take 8 bits per channel; the 15-bit value holds 5 bits per channel. `expand5` brings each channel back to 0..255 (the GPU then keeps the top 5 bits again), so the on-screen color is the original rounded down to 15-bit precision.
</details>
