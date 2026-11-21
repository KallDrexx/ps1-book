# Chapter 2 Quiz

**1. Write the bytes in memory, lowest address first, after `sw` of `0xCAFEBABE`.**
<details><summary>Answer</summary>
`BE BA FE CA`. The PS1 is little-endian: the least significant byte goes at the lowest address.
</details>

**2. Three virtual addresses, `0x00010000`, `0x80010000` and `0xA0010000`, name how many different RAM bytes? What differs?**
<details><summary>Answer</summary>
One. KUSEG, KSEG0 and KSEG1 all map to physical `0x00010000`. KSEG1 bypasses the cache; the other two go through it. On the PS1 that cache holds only instructions, so for data loads and stores all three behave the same.
</details>

**3. Where are main RAM, the scratchpad, the I/O registers and the BIOS (physical addresses)?**
<details><summary>Answer</summary>
RAM: `0x00000000` (2 MB). Scratchpad: `0x1F800000` (1 KB). I/O registers: `0x1F801000` (4 KB). BIOS: `0x1FC00000` (512 KB; seen at `0xBFC00000` through KSEG1).
</details>

**4. Why does `addiu $t1, $zero, 0xBEEF` not load `0x0000BEEF`?**
<details><summary>Answer</summary>
`addiu` sign-extends its 16-bit immediate. `0xBEEF` has bit 15 set, so it becomes `0xFFFFBEEF`. `ori` zero-extends, so `ori $t1, $zero, 0xBEEF` gives `0x0000BEEF`.
</details>

**5. Give a two-instruction sequence that puts `0x1F801810` in `$t0`.**
<details><summary>Answer</summary>
`lui $t0, 0x1F80` then `ori $t0, $t0, 0x1810`. `lui` sets the upper 16 bits and clears the lower ones; `ori` fills them in.
</details>

**6. A word holds `0x00000041`. After `sb` of a register with value `0x7F` to the address of that word, what is the word?**
<details><summary>Answer</summary>
`0x0000007F`. The address of a word is the address of its lowest byte, which holds the low digits. `sb` replaces only that byte.
</details>

**7. What is the difference between `lbu` and `lw`, and which of them cares about byte order?**
<details><summary>Answer</summary>
`lbu` reads one byte (zero-extended); `lw` reads four bytes and assembles them with the lowest address as the least significant byte. Only `lw` (and `lh`/`sh`/`sw`) depends on byte order; a single byte has none.
</details>

**8. You write `lbu $t1, 0($t0)` and the next line is `sb $t1, 4($t0)`. What goes wrong?**
<details><summary>Answer</summary>
The load's result is not available to the next instruction (the load delay), so `sb` stores the old value of `$t1`. Put an unrelated instruction or a `nop` between them.
</details>

**9. Why can't you reach the scratchpad at `0xBF800000`?**
<details><summary>Answer</summary>
On real hardware the scratchpad is not mapped in the uncached KSEG1 segment (PCSX-Redux does not enforce this). Use `0x1F800000` or the KSEG0 address `0x9F800000`.
</details>

**10. What happens on `sw` to an address that is not a multiple of 4?**
<details><summary>Answer</summary>
The CPU raises an address-error exception and the store does not happen. `sh` needs an even address.
</details>
