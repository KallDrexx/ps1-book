# Chapter 29 Quiz

**1.** A data sector is 2352 bytes on the disc but `CdRead` stores 2048 bytes per sector. Where do the other 304 go, and what changes with `CdlModeSize`?

<details><summary>Answer</summary>

A Mode 2 Form 1 sector is 12 bytes of sync, 4 of header, 8 of subheader, 2048 of data, 4 of error detection (EDC) and 276 of error correction (ECC). The drive checks and strips the framing and delivers the 2048 data bytes. With `CdlModeSize` it delivers 2340 bytes (everything except the 12 sync bytes), which streaming video and audio use.
</details>

**2.** A file is 5000 bytes long. How many sectors does `CdRead` need, how big must the buffer be, and what should `cd_load_file` report as the size?

<details><summary>Answer</summary>

`ceil(5000 / 2048) = 3` sectors, so a 6144-byte buffer. The size reported is 5000, the directory entry's value: the rest of the buffer is padding. A 5000-byte buffer would be overrun by 1144 bytes.
</details>

**3.** What does the BIOS read to boot a disc, and what do `BOOT`, `TCB`, `EVENT` and `STACK` mean?

<details><summary>Answer</summary>

`SYSTEM.CNF` in the root directory (or, if absent, an executable named `PSX.EXE`). `BOOT=cdrom:\HOVER.EXE;1` names the program to load; `TCB` and `EVENT` are the numbers of kernel thread and event slots to allocate (hexadecimal); `STACK` is the initial stack pointer (`801FFFF0`, near the top of the 2 MB).
</details>

**4.** The four bytes `00 00 00 0D` start at `p + 4` in a loaded file. What does `*(uint32_t *)(p + 4)` give on the PS1, and what is the right expression for a big-endian value? Give a second reason the cast is wrong even if `p + 4` is aligned.

<details><summary>Answer</summary>

The CPU is little-endian, so it reads `0x0D000000 = 218,103,808`. The right expression is `((uint32_t) p[4] << 24) | (p[5] << 16) | (p[6] << 8) | p[7]`, which gives 13. The second reason: the file buffer is an array of bytes, and reading it through a `uint32_t *` breaks C's aliasing rules and silently assumes alignment, which fails at the first odd offset (an `lw` from an address not divisible by 4 raises an address error exception on the R3000).
</details>

**5.** `cd_load_file` calls `malloc`, and then `CdRead` reports an error. Which things must it do before returning, and what does it return?

<details><summary>Answer</summary>

Free the buffer (otherwise each failure leaks it), make sure `*size` is 0, and return `NULL`. A timeout is handled the same way, after `CdReadBreak()` stops the drive.
</details>

**6.** Why does `model_parse` test `F > (size - 12 - 8 * V) / 8` rather than `12 + 8 * V + 8 * F > size`?

<details><summary>Answer</summary>

`F` comes from the file, and `8 * F` is computed in 32 bits. For `F = 0x20000002` the product wraps to 16, so the second test passes for a corrupt file that has room for only two faces, and the parser would then read far beyond the buffer. Dividing the space left by 8 cannot overflow, so the check is safe.
</details>

**7.** Why is `memcpy`-ing or casting the *vertices* of `MODEL.BIN` fine when its *counts* are not?

<details><summary>Answer</summary>

The vertices are little-endian `s16`, the CPU's own order, and the format puts them at offsets that are multiples of 4 (`0x08`, 8 bytes each), so with a 4-aligned buffer they can be read in place (the parser still checks the alignment). The counts are big-endian, a different order from the CPU's, so their bytes must be reassembled. (`face_count` is also at an aligned offset; alignment is not what makes it special.)
</details>

**8.** The program works from the disc image but fails when you replace `MODEL.BIN` with a model that has 5 vertices. Name three things that could be built into the program.

<details><summary>Answer</summary>

Any of: the vertex or face count (a loop to 13: the ship has 13 vertices and 13 faces), the file size or sector count (`malloc(2048)`, or a loop that reads one sector), the model itself (compiled in with `xxd -i`), a color or face table, `first_vertex`/`last_vertex` values copied from the ship. Everything about the model must come from the bytes that were read.
</details>

**9.** Where do the heap and the stack live, and what does `malloc` do when the heap is exhausted?

<details><summary>Answer</summary>

Both are in the 2 MB of RAM above the program: the heap starts at the end of `.bss` and grows up (to the top of RAM at most), and the stack starts at `0x801FFFF0` and grows down. `malloc` returns `NULL` when it cannot satisfy a request, so every allocation must be checked. Nothing prevents a large heap from running into the stack.
</details>
