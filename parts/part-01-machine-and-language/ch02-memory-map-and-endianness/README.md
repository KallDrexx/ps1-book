# Chapter 2: Memory, the Memory Map, and Endianness

## 1. Concept

The CPU sees one flat 32-bit address space. RAM, scratchpad, the BIOS and the hardware registers all live at fixed addresses in it, and RAM answers at several addresses at once. Multi-byte values are stored **little-endian**: lowest byte first.

## 2. Why it matters

Every PS1 program is loads and stores to the right address. The address decides whether you hit RAM, fast scratchpad or a GPU port, and whether the CPU cache is involved. Byte order decides whether the GPU, the CD controller and your own data tables read the numbers you meant. Almost every "my data is garbage" bug in this book traces back to one of these two things.

## 3. Learning objectives

After this chapter you can:

- read hex and binary, and name bits, bytes, halfwords and words;
- say which address range holds RAM, scratchpad, I/O registers and BIOS;
- explain KUSEG, KSEG0 and KSEG1, and why one RAM byte has three addresses;
- predict the bytes in memory after `sw`, `sh` and `sb`, and the bytes you read back;
- build any 32-bit constant or address with `lui` and `ori`.

## 4. Prerequisites

[Chapter 1](../ch01-workbench/README.md): a working toolchain and the shape of `main.s`.

## 5. Explanation

### 5.1 The vocabulary

An **ISA** (instruction set architecture) is the contract between a CPU and its programs: the instructions, registers and memory rules. The PS1's ISA is **MIPS I**. The CPU is an R3000A-compatible core built by LSI Logic (the CW33300) inside a Sony chip, which is why you see both names.

| Unit | Bits | Hex digits | Range (unsigned) | MIPS instruction suffix |
|---|---|---|---|---|
| bit | 1 | | 0 to 1 | |
| byte | 8 | 2 | 0 to 255 | `b` |
| halfword | 16 | 4 | 0 to 65,535 | `h` |
| word | 32 | 8 | 0 to 4,294,967,295 | `w` |

A word is 32 bits on MIPS (not 16, as in x86 documentation). **Hex** writes four bits per digit, so a byte is exactly two digits: `0xDE` is `1101 1110`. The `0x` prefix marks hex. Addresses and register values are always hex in this book.

### 5.2 One address space, many devices

Every address is a 32-bit number, and the CPU puts it on the bus. The hardware routes it by range. These are the **physical** addresses; section 5.3 explains how you reach them.

| Physical range | Size | What answers |
|---|---|---|
| `0x00000000` - `0x001FFFFF` | 2 MB | Main RAM |
| `0x1F000000` - `0x1F7FFFFF` | 8 MB | Expansion region 1 (parallel I/O port) |
| `0x1F800000` - `0x1F8003FF` | 1 KB | **Scratchpad**: fast on-chip RAM |
| `0x1F801000` - `0x1F801FFF` | 4 KB | **I/O registers** (GPU, DMA, timers, CD-ROM, SPU, pads) |
| `0x1F802000` - `0x1F803FFF` | 8 KB | Expansion region 2 (debug hardware) |
| `0x1FC00000` - `0x1FC7FFFF` | 512 KB | **BIOS** ROM |

Chapter 1 already used the I/O area: GP0 at `0x1F801810`. Writing there does not store a number; it sends a command to a chip. The CPU does not know the difference. The full I/O map is in psx-spx and in [Appendix B](../../../appendices/B-memory-map-and-io.md).

### 5.3 Segments: KUSEG, KSEG0, KSEG1

The CPU's 32-bit addresses are **virtual**. The top bits pick a **segment**, which decides how the address becomes a physical one.

```
 virtual address            segment   cached?   becomes physical
 0x00000000 - 0x7FFFFFFF    KUSEG     yes       the address itself (first 512 MB only)
 0x80000000 - 0x9FFFFFFF    KSEG0     yes       address & 0x1FFFFFFF
 0xA0000000 - 0xBFFFFFFF    KSEG1     no        address & 0x1FFFFFFF
 0xC0000000 - 0xFFFFFFFF    KSEG2     (cache control only; ignore)
```

So RAM offset `0x10000` can be named `0x00010000` (KUSEG), `0x80010000` (KSEG0) or `0xA0010000` (KSEG1). It is one place. Your program is loaded at `0x80010000` because the first 64 KB of RAM belongs to the BIOS kernel. The BIOS itself starts at `0xBFC00000`, which is physical `0x1FC00000`.

What the segments change is **caching**. The CPU has a 4 KB instruction cache. Its 1 KB data cache is not used as a cache at all: Sony wired it up as the scratchpad. So on the PS1 only *instruction fetches* are cached, and only in KUSEG and KSEG0; KSEG1 bypasses the cache. Data loads and stores behave the same through every segment. In practice:

| Use | Address style |
|---|---|
| Your code and data | KSEG0 (`0x8001....`) |
| Hardware registers | Any segment; this book uses the KUSEG form `0x1F80....` |
| Scratchpad | `0x1F80....` or KSEG0 (`0x9F80....`); it is **not reachable through KSEG1** |
| Code you just wrote into RAM, or must not be cached | KSEG1 (`0xA001....`) |

### 5.4 Little-endian

When a word occupies four bytes, which byte goes at the lowest address? The R3000A as wired in the PS1 puts the **least significant byte first**. That is little-endian.

```
 word 0x12345678 stored at address A:

   address:   A      A+1    A+2    A+3
   byte:      78     56     34     12
              ^low                 ^high
```

The same holds for halfwords: `0xBEEF` at address A is `EF` then `BE`. Two consequences you will meet daily:

- A hex dump shows words "backwards". The `PS-X EXE` header's start address `0x80010000` appears as `00 00 01 80`.
- Reading a word as bytes (or the reverse) is not a no-op. A `sb` into the lowest byte of a word changes the word's *low* digits.

A **byte** has no order, so `sb` and `lbu` never reorder anything. Only multi-byte accesses do.

### 5.5 The instructions for this chapter

MIPS is a **load/store** architecture: instructions work on registers, and only loads and stores touch memory. A register is a named 32-bit slot in the CPU. There are 32; Chapter 3 covers them. For now:

- `$zero` always reads as 0 and ignores writes.
- `$t0` to `$t9` are free for temporary values.

Memory access takes a base register plus a signed 16-bit **offset**, written `offset($base)`. The address is the base's value plus the offset.

| Instruction | Meaning |
|---|---|
| `sw $rt, off($rs)` | Store **w**ord: the 4 bytes of `rt` to address `rs+off` |
| `sh $rt, off($rs)` | Store **h**alfword: the low 2 bytes of `rt` |
| `sb $rt, off($rs)` | Store **b**yte: the low byte of `rt` |
| `lw $rt, off($rs)` | **L**oad word into `rt` |
| `lbu $rt, off($rs)` | **L**oad **b**yte **u**nsigned: one byte into `rt`, upper bits zero |
| `lui $rt, imm` | **L**oad **u**pper **i**mmediate: `rt = imm << 16`, low half zero |
| `ori $rt, $rs, imm` | `rt = rs OR imm`. The 16-bit `imm` is **zero-extended** |
| `nop` | Do nothing (it is really `sll $zero, $zero, 0`) |

**Alignment.** `sw` and `lw` need an address divisible by 4, and `sh` needs an even address. A misaligned access raises a CPU exception instead of storing anything. Chapter 11 covers alignment in depth; here just keep your offsets consistent.

**Building constants.** Instructions are 32 bits wide, so a 32-bit constant cannot fit in one. You build it in two: `lui` sets the top 16 bits, then `ori` fills the bottom 16. The same recipe makes an address from a label. For a 16-bit-or-smaller constant, `ori $rt, $zero, imm` is enough.

Why `ori` and not `addiu`? Because `addiu` *sign-extends* its immediate: `0xBEEF` has its top bit set, so `addiu` would add `0xFFFFBEEF`, and after a `lui` the upper half would come out one too low. `ori` never does that. armips' `li` and `la` pseudo-instructions hide this: for a value with both halves non-zero they emit `lui` + `addiu` and silently add one to the `lui` when the low half is `0x8000` or more (`li $t0, 0xDEADBEEF` becomes `lui 0xDEAE` + `addiu 0xBEEF`). This chapter has you write the `lui`/`ori` pair yourself so you see the real machine code, and the verifier rejects `addiu`. Chapter 3 returns to `li`.

**Load delay.** This is the one pipeline rule you need before Chapter 7, because this project uses loads. A load's result is not ready for the very next instruction: if you `lbu $t1, ...` and use `$t1` on the following line, you get the *old* `$t1`. armips warns (`register t1 may not be available due to load delay`) but still builds. Rule for now: put one unrelated instruction, or a `nop`, between a load and the first use of its result. (The `nop` after `j done` is a different delay, the branch delay slot; Chapter 7 explains both.)

### 5.6 Reading a memory dump

After your program runs, open a memory editor in Redux (**Debug > CPU > Memory Editors**) and go to `results` (find its address in `build/main.sym`). Bytes appear in address order, left to right. `xxd build/main.ps-exe` shows the file; address `results` is at file offset `results - 0x8000F800`.

### 5.7 More facts that bite later

- RAM mirrors: the 2 MB is repeated at `0x00200000`, `0x00400000` and `0x00600000` (physical). Programs should never rely on it.
- The scratchpad is fast on-chip memory, but it is not executable: jumping into it crashes. Chapter 11 and the GTE chapters use it for hot data.
- Reading an unmapped address raises a bus error on real hardware; an emulator may return garbage instead.

## 6. Worked example

Here is the idea at the smallest scale. Store one word, read its first byte, store that byte elsewhere:

```
    lui  $t0, results >> 16          ; t0 = address of results (top half)
    ori  $t0, $t0, results & 0xFFFF  ;                         (bottom half)
    lui  $t1, 0xAABB
    ori  $t1, $t1, 0xCCDD            ; t1 = 0xAABBCCDD
    sw   $t1, 0($t0)                 ; memory: DD CC BB AA
    lbu  $t2, 0($t0)                 ; t2 = 0xDD: the lowest address holds the low byte
    nop                              ; (load delay)
    sb   $t2, 4($t0)                 ; memory +4: DD
```

Predict the bytes before you build it: `DD CC BB AA DD`. If you expected `AA` at `+4`, you assumed big-endian.

## 7. Project: "Memory Cartographer"

Fill the 64-byte `results` block in `starter/main.s` with the layout below, then prove little-endianness by reading words back a byte at a time.

The starter is Chapter 1's program with the GPU code removed (this project draws nothing) and one piece of scaffolding added: the `results` block the verifier reads. The `.create`/`.include`/`.org` lines and the `done` loop are unchanged.

**Layout** (offsets from `results`; the last column is what ends up in memory). The verifier's messages use the part letters.

| Part | Offset | How | Value written | Bytes in memory |
|---|---|---|---|---|
| A | `0x00` | one `sw` | `0x12345678` | `78 56 34 12` |
| A | `0x04` | one `sh` | `0xBEEF` | `EF BE` |
| A | `0x06` | one `sh` | `0xCAFE` | `FE CA` |
| A | `0x08` to `0x0B` | four `sb`, in address order | `0x11, 0x22, 0x33, 0x44` | `11 22 33 44` |
| A | `0x0C` | one `sw` | `0xDEADBEEF` | `EF BE AD DE` |
| B | `0x10` to `0x13` | read bytes 0 to 3 of the word at `0x00` with `lbu`, store each with `sb` | | `78 56 34 12` |
| B | `0x14` to `0x17` | the same for the word at `0x0C` | | `EF BE AD DE` |
| C | `0x18` | one `sw`, addressing `results` through its **KSEG1** alias (`0xA001....`) | `0x0BADF00D` | `0D F0 AD 0B` |
| C | `0x1C` | one `sh`, through its **KUSEG** alias (`0x0001....`) | `0x7E57` | `57 7E` |
| D | `0x20` | `sw` `0x600DCAFE` to the first scratchpad word `0x1F800000`, `lw` it back, `sw` the loaded value here | | `FE CA 0D 60` |

Offsets `0x24` to `0x3F` are unused.

**Constraints**

- Between `main:` and `done:` use only `lui`, `ori`, `sw`, `sh`, `sb`, `lw`, `lbu` and `nop`. No `li`, `la`, `addiu`, loops, branches or jumps. The program is straight-line code. The only loads are `lbu` for the byte-by-byte proof and `lw` for the scratchpad round trip.
- Do not put data in the `results` block of the file; it must start as zeros.
- Keep the labels `main`, `done` and `results` and the `done` loop.
- Respect the load delay (section 5.5).
- Address the scratchpad as `0x1F800000`; the verifier watches that address.

**Hints**

- Load `results` into `$t0` once and use `offset($t0)` for most stores.
- For the aliases, build a second base register with `lui`/`ori`: change only the top bits of the same address.
- `lbu` four times into four different registers, then four `sb`: no store follows the load of its own register.
- The verifier compares memory byte by byte with the last column, lowest address first.

**Stretch goals** (in a copy)

- Store a word at `results+2` and see what the emulator does. Check the log and the CPU registers.
- Write `0x12345678` to RAM through KSEG0, read it through all three aliases, and compare.
- Use `lb` instead of `lbu` on `0xDEADBEEF`'s bytes: `lb` sign-extends. What does a register hold after loading `0xEF`?
- Read the BIOS ROM's first word at `0xBFC00000`. What instruction is it?

## 8. Verification

```sh
parts/part-01-machine-and-language/ch02-memory-map-and-endianness/verify/verify.sh
```

This checks `starter/`. Pass a path for a copy, `-v` for build output and the emulator log, `--solution` for the reference. It assembles your program, scans its machine code, runs it headless to `done`, and watches every store and load to `results` and the scratchpad.

| Check | What it means | If it fails |
|---|---|---|
| `program defines main, done and results` | Required labels exist, `results` is word-aligned. | You deleted or renamed a label. |
| `results block starts out all zero in the executable` | You did not pre-fill the data. | Remove `.byte`/`.word` data from `results`. |
| `main..done uses only lui, ori, sw, ...` | No other instruction appears in your code. The message names the offender. | `addiu` usually means you used `li`, `la` or a sign-extending constant. Use `lui`/`ori`. |
| `instruction mix: at least 12 sb, ...` | You used each store/load type enough times. | The message lists the shortfall, for example `sb: 4 (need 12)`: you skipped the byte copies. |
| `part C builds a KSEG1 ... and a KUSEG ...` | A `lui` makes `0xA001`-style and a `lui` makes `0x0001`-style base. | Build the alias base addresses with their own `lui`. |
| `program reaches done` | No crash or hang. | Likely a misaligned `sw`/`sh`, or a bad address. Use `-v`. |
| `results holds the expected little-endian bytes` | Every byte at every offset. The message shows expected and actual bytes. | Reversed bytes: you wrote them in big-endian order. One wrong pair: a store of the wrong width overwrote a neighbor. |
| `scratchpad word ... holds 0x600DCAFE` | The scratchpad store happened. | You stored to the wrong address. |
| `every layout byte is written by the program` | The verifier refills `results` with `AA` bytes and reruns. | A byte stays `AA`: your program relies on data in the file or on the zero fill. |
| `each value was stored with the required width` | An emulator watchpoint sees each store's size. | The listed `(offset/width)` is missing: you used `sw` where the table says `sh` or `sb`, or the reverse. |
| `the endianness proof reads the words back with byte loads` | There was a byte read of each of the 8 source bytes. | You skipped some `lbu`s. |
| `the copies come from the loads, not from constants` | A third run changes the words at `+0x00`, `+0x0C` and `0x1F800000` just before your first load of each; the copies must follow. | You wrote constants into `0x10`-`0x17` or `0x20` instead of storing the loaded registers, or stored a register on the line right after its load (load delay). |
| `part C writes through the KSEG1 and KUSEG aliases` | The stores at `0x18` and `0x1C` used the right segment addresses. | The base register used for those stores was the KSEG0 one. |
| `scratchpad was written with sw and read back with lw` | Both accesses happened at `0x1F800000`. | Check the `lw`, and spell the address `0x1F800000`, not `0x9F800000` or `0xBF800000`. |

A pass ends with `CHAPTER 02: PASSED (14/14 checks)` and exit status 0.

## 9. Common pitfalls

- **Big-endian thinking.** `0x12345678` at `results` is `78 56 34 12` in memory. Your expected bytes should not read like the constant.
- **`addiu` for constants.** `0xBEEF` and any word whose low half is 0x8000 or more break under `addiu`. Use `ori`.
- **Using the loaded register too soon.** `lbu` then `sb` of the same register on the next line stores the old value. The program still builds; armips only warns.
- **Wrong store width.** `sw` over a halfword overwrites the next two bytes. Do the stores in the order of the table.
- **Misaligned access.** `sw` at an address not divisible by 4 faults. `results` is word-aligned; keep your offsets so.
- **Scratchpad through KSEG1.** `0xBF800000` is not the scratchpad on real hardware, although PCSX-Redux lets the access through. Use `0x1F800000` (or `0x9F800000` outside this project).
- **Forgetting `0x`.** `ori $t1, $zero, 20` is decimal twenty, not `0x20`.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- psx-spx: "Memory Map" (segments and the I/O summary at `0x1F801000`), "Memory Control" and "CPU Specifications" (cache and R3000A notes). <https://psx-spx.consoledev.net/>
- A MIPS I instruction reference (*See MIPS Run* or any MIPS32 manual): `lui`, `ori`, `lbu`, `sb`.
- PCSX-Redux documentation, memory editor and debugger: <https://pcsx-redux.consoledev.net/>
