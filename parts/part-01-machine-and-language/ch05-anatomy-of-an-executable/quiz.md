# Chapter 5 Quiz

**1. Which header field says where execution starts, and where does the loader copy the payload?**
<details><summary>Answer</summary>
Initial PC (file offset `0x10`) is where execution starts. The load address (offset `0x18`) is where the payload from file offset `0x800` is copied.
</details>

**2. A PSX-EXE file is 6144 bytes long. What should its size field be?**
<details><summary>Answer</summary>
The size field excludes the 2048-byte header: 6144 - 2048 = 4096 = `0x1000`. It must be a multiple of `0x800`.
</details>

**3. In a hex dump the bytes at file offset `0x10` read `00 10 01 80`. What is the initial PC?**
<details><summary>Answer</summary>
Little-endian: reverse the bytes to `80 01 10 00`, so `0x80011000`.
</details>

**4. Why does armips' `.psx` not produce a runnable EXE by itself, and what do you add?**
<details><summary>Answer</summary>
`.psx` only selects the R3000 instruction set; it writes no header. You add the 2 KB header with `.ascii`/`.word`/`.fill` (or `common/psxexe.inc`), starting the file at `LOAD - 0x800` with `.create`, then `.org LOAD` for the code.
</details>

**5. Decode `0xAE1D0004`.**
<details><summary>Answer</summary>
`op = 0x2B` is `sw`; `rs = 16` (`$s0`), `rt = 29` (`$sp`), `imm = 4`. So `sw $sp, 4($s0)`.
</details>

**6. A `bne` at `0x80010020` has `imm16 = 0xFFFB`. Where does it branch?**
<details><summary>Answer</summary>
`0xFFFB` is -5. Target = `0x80010024 + 4 * (-5) = 0x80010010`.
</details>

**7. Why are the header and payload sizes multiples of 2048 bytes?**
<details><summary>Answer</summary>
A CD-ROM sector holds 2048 bytes of data, and the loader reads whole sectors.
</details>

**8. You change the load word in your header to `0x80050000` but leave `.org 0x80040000` for the code. The file passes header validation. What happens when it runs?**
<details><summary>Answer</summary>
The loader copies the payload to `0x80050000`, but the code was assembled for `0x80040000`: absolute addresses (`la`, `j`) point at the wrong place, so it jumps into memory that does not hold your code and never reaches `done`.
</details>

**9. What does the `$sp` register contain when your program starts?**
<details><summary>Answer</summary>
The header's SP base plus SP offset, set by the loader (PCSX-Redux's side-loader uses the base alone, which is why the offset is kept 0). Nothing else sets it, so a header with the wrong stack leaves any function-calling code (Chapter 8 onward) with a bad stack.
</details>
