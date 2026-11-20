# Chapter 5: Anatomy of an Executable: The PSX-EXE Format

## 1. Concept

A PS1 program is a **PSX-EXE**: a 2 KB header telling the BIOS where to load the code, where to start running it and where the stack goes, followed by the raw machine code.

## 2. Why it matters

So far a macro (`common/psxexe.inc`) hid the header from you. Every build tool, emulator, disc image and homebrew loader reads these same few fields. When a program "does nothing" on a console or an emulator, a wrong header is one of the first suspects. This chapter also teaches you to read raw bytes as instructions, which is what a hex dump in a debugger gives you.

## 3. Learning objectives

After this chapter you can:

- name the header fields and say what the loader does with each;
- explain why armips' `.psx` emits no header and how `.create`/`.org` place bytes in the file and in memory;
- decode an R-, I- or J-format instruction word by hand;
- write a host tool that validates a PSX-EXE and disassembles its first instructions;
- build an EXE with a hand-written header that loads at an address of your choice.

## 4. Prerequisites

[Chapter 4](../ch04-control-flow-branches-and-jumps/README.md) (branches, `j`, delay slots). Chapters 2-3 for the memory map, endianness and the `lui`/`addiu` pair that `la` expands to. Part (a) is Python 3.

## 5. Explanation

### 5.1 Two worlds: file and memory

An EXE file is copied into RAM, then the CPU jumps into it. Two address spaces are involved:

```
 file on disk                           RAM (after loading)
 offset 0x000  +----------------+
               |  header 2 KB   |   (read by the loader, never copied)
 offset 0x800  +----------------+       0x80010000 (load address) +----------------+
               |  payload       |  -->                           |  payload       |
               |  code + data   |                                |  code + data   |
               +----------------+                                +----------------+
```

The header says *which* RAM address receives the payload. The default in this book is `0x80010000` (the first 64 KB of RAM belong to the BIOS and kernel), but any address that fits works.

### 5.2 The header

All fields are little-endian 32-bit words unless noted. Offsets are in the **file**.

| Offset | Size | Field | Meaning |
|---|---|---|---|
| `0x00` | 8 | magic | ASCII `PS-X EXE` (with the space). Anything else is "not an executable". |
| `0x08` | 8 | zero | Unused, zero. |
| `0x10` | 4 | initial PC | Address of the first instruction to run. |
| `0x14` | 4 | initial GP | Value loaded into `$gp` (register 28). Zero is common; C toolchains set it for fast access to small globals. |
| `0x18` | 4 | load address | RAM address where the payload is copied. |
| `0x1C` | 4 | size | Payload size in bytes, **not** counting the header. A multiple of `0x800`. |
| `0x20` | 16 | data, BSS | Two address/size pairs (data section, BSS). Usually zero; if the BSS size is non-zero the BIOS zero-fills that range. |
| `0x30` | 4 | SP base | Initial stack pointer. Zero means "keep the loader's stack". |
| `0x34` | 4 | SP offset | The BIOS adds it to the base. PCSX-Redux's side-loader ignores it, so keep it 0. |
| `0x38` | 20 | reserved | Zero. |
| `0x4C` | text | region marker | `Sony Computer Entertainment Inc. for Japan area`, `... for Europe area` or `... for North America area`, zero-terminated. |
| after | | padding | Zeros up to `0x800`. |

```
 0x00  P S - X   E X E 00 00 00 00 00 00 00 00      magic + zeros
 0x10  [  PC  ] [  GP  ] [ load ] [ size ]          the four words you care about most
 0x20  00 .. 00 (16 bytes)
 0x30  [SP base][SP off ] 00 .. 00 (20 bytes)
 0x4C  "Sony Computer Entertainment Inc. for North America area" 00 00 ... 00
 0x7FF
```

Notes:

- **Why 2 KB multiples?** A CD sector holds 2048 bytes. The loader reads whole sectors, so both the header and the payload are sector-sized.
- **The region marker** is informational. Neither the BIOS nor emulators check it, and many homebrew EXEs leave it zero. (Region locking on real hardware is done by the CD-ROM controller reading the disc, not by the EXE.) This book writes a valid one anyway.
- **Stack.** The PS1 stack grows downward from the top of the 2 MB RAM, which ends at `0x80200000`. An initial `$sp` of `0x801FFF00` leaves 256 bytes of slack above it.
- **Memory the BIOS keeps.** The first `0x10000` bytes of RAM are the BIOS and kernel's. Never load below `0x80010000`.

Real header from this chapter's reference solution (`xxd` of the first `0x50` bytes):

```
00000000: 5053 2d58 2045 5845 0000 0000 0000 0000  PS-X EXE........
00000010: 0000 0480 0080 0480 0000 0480 0008 0000  ................   pc gp load size
00000030: 00ff 1f80 0000 0000 ...                                     sp base, sp offset
```

Read `0000 0480` as bytes `00 00 04 80`; reversed that is `0x80040000`.

### 5.3 How armips produces it

`.psx` only selects the R3000 instruction set. It writes **no header**. You place the header yourself, because `.create` starts a file at a chosen *address*, and the bytes you emit first land at the start of the file:

| Directive | Effect |
|---|---|
| `.create "file", ADDR` | Open an output file. `ADDR` is the address of file offset 0. It must be a plain number (a label will not work here). |
| `.org ADDR` | Move the output position to `ADDR`; bytes after it are assembled for that address. The file offset follows. |
| `.ascii "text"`, `.word`, `.fill n, v` | Emit raw bytes. `.fill 8, 0` is eight zero bytes. |
| `.align 0x800` | Pad with zeros to the next multiple of `0x800`. |
| `.close` | Finish the file. |

So the book's layout is: create at `LOAD - 0x800` (the header sits there), emit 2048 bytes, then `.org LOAD` for the code. File offset 0x800 and RAM address `LOAD` coincide. `common/psxexe.inc` is exactly this header; open it and match each line to the table above. Label references such as `.word main` work even though `main` comes later.

### 5.4 Side-loading versus booting from disc

| Path | What happens |
|---|---|
| **Side-load** (emulator `-exe`, the book's `make run`) | The emulator (or a cartridge/serial loader) parses the header itself, copies the payload to the load address, sets PC, GP and SP, and starts. No disc, no region check. |
| **CD boot** | The BIOS reads `SYSTEM.CNF`, finds `BOOT = cdrom:\FILE.EXE;1`, loads that file's header and payload the same way, and runs it. Part VI builds a disc. |

Either way the header is the contract. In this chapter's reference run, PCSX-Redux put the header's GP and SP base in the registers exactly as written: you will prove that with your own program. One difference: the BIOS sets `$sp` to base + offset, while PCSX-Redux's side-loader uses the base alone. With offset 0, as the usual tools write it, both agree.

### 5.5 Reading instruction words

An instruction is one 32-bit word in one of three layouts. The top 6 bits are the **opcode** (`op`).

```
 31      26 25   21 20   16 15   11 10    6 5      0
R: | op=0   |  rs   |  rt   |  rd   |  sa   | funct  |   registers; funct picks the operation
I: |  op    |  rs   |  rt   |       imm16            |   immediate, offset or branch distance
J: |  op    |            target26                    |   jump
```

`rs`, `rt`, `rd` are register numbers 0-31 (`$t0` is 8, `$s0` is 16, `$sp` is 29, `$ra` is 31). `sa` is a shift amount.

Worked decode. The first word of the reference payload, bytes `04 80 10 3C` in the file, is `0x3C108004`:

```
 0x3C108004 = 0011 11|00 000|1 0000| 1000 0000 0000 0100
              op=0x0F  rs=0  rt=16   imm16=0x8004
```

`op 0x0F` is `lui`, `rt 16` is `$s0`: `lui $s0, 0x8004`. That is the first half of `la $s0, results`.

Rules you need for the project:

- **Branches:** the target is `address_of_next_instruction + 4 * signed imm16` (Chapter 4). A disassembler prints the absolute address.
- **`j`/`jal`:** target = (upper 4 bits of next instruction's address) `|` (`target26` shifted left 2).
- **Loads/stores** print as `lw rt, imm(rs)` with a signed `imm`.
- **`lui`, `andi`, `ori`, `xori`** treat `imm` as unsigned; **`addiu`, `slti`, `sltiu`** and memory offsets as signed.
- The word `0` is `sll $zero, $zero, 0`, which everyone writes as `nop`.

The instruction set for your disassembler (Chapters 3-4 plus a few friends):

| Format | Instructions | Operand order |
|---|---|---|
| R, shift (`funct`) | `sll`=00 `srl`=02 `sra`=03 | `rd, rt, sa` |
| R, 3-register | `addu`=21 `subu`=23 `and`=24 `or`=25 `xor`=26 `nor`=27 `slt`=2A `sltu`=2B | `rd, rs, rt` |
| R | `jr`=08 | `rs` |
| I, arithmetic (`op`) | `addiu`=09 `slti`=0A `sltiu`=0B `andi`=0C `ori`=0D `xori`=0E | `rt, rs, imm` |
| I | `lui`=0F | `rt, imm` |
| I, memory | `lb`=20 `lh`=21 `lw`=23 `lbu`=24 `lhu`=25 `sb`=28 `sh`=29 `sw`=2B | `rt, imm(rs)` |
| I, branch | `beq`=04 `bne`=05 | `rs, rt, target` |
| I, branch | `blez`=06 `bgtz`=07 | `rs, target` |
| I, regimm (`op`=01) | `bltz` (`rt`=0), `bgez` (`rt`=1) | `rs, target` |
| J | `j`=02 `jal`=03 | `target` |

Everything else prints as `.word 0x........`.

## 6. Worked example

Take the solution's header and ask the three questions a loader asks:

1. *Is it an EXE?* Bytes 0-7 are `PS-X EXE`. Yes.
2. *Where does the payload go, and how big is it?* Load `0x80040000`, size `0x800`. The file is `0x800 + 0x800 = 4096` bytes (check with `ls -l`).
3. *Where do I start and what are the registers?* PC `0x80040000` (the `main` label, the first payload instruction), GP `0x80048000`, SP `0x801FFF00 + 0`.

The reference program then does what you can now predict: right after `la $s0, results`, the instructions `sw $gp, 0($s0)` and `sw $sp, 4($s0)` copy the loader's `$gp` and `$sp` into `results`. If your header is right, `results[0]` is the GP word of your header and `results[1]` its SP.

## 7. Project: "Anatomy Lab"

Two parts in this chapter's `starter/` directory.

### Part (a): `exeinfo.py`

A host tool, run as `python3 exeinfo.py FILE`. It must validate the file and report on it. Only the standard library is needed.

**Validation** (check in this order; the first failure decides the category):

| Category | The file is rejected when... |
|---|---|
| `short` | it is smaller than 2048 bytes |
| `magic` | bytes 0-7 are not `PS-X EXE` |
| `size` | the size field is not a multiple of `0x800`, or `0x800 + size` is more than the file length |
| `load` | the load address is below `0x80000000`, or `load + size` is above `0x80200000` |
| `pc` | the PC is not 4-byte aligned, or not in `[load, load + size)` |
| `region` | the zero-terminated string at `0x4C` is not one of the three standard markers |

Extra bytes after the payload are allowed. The `load` and `region` rules are stricter than the BIOS, which would boot a KUSEG load address or a blank marker; your tool flags them anyway.

**Output for a bad file:** exit status 1 and a first line `INVALID: <category>` (the category word alone, lower-case). You may add more lines after it.

**Output for a good file:** exit status 0 and these lines, in this order:

```
magic:  PS-X EXE
pc:     0x80010000
gp:     0x00000000
load:   0x80010000
size:   0x800
sp:     0x801FFFF0
region: Sony Computer Entertainment Inc. for North America area
80010000: 3C08A001  lui t0, 0xA001
...
```

- Numbers are hex with `0x`. `sp` is the SP base plus the SP offset.
- Then **16 instruction lines** `ADDR: WORD  text` for the first 16 words of the payload (file offset `0x800`, addresses starting at the load address). `WORD` is the 32-bit word in 8 hex digits (mind the byte order). Use ABI register names without `$` (`t0`, `sp`, `ra`). Branch and jump targets are absolute addresses. Hex or decimal immediates are both accepted, but the value must follow the signedness rules in 5.5: `addiu sp, sp, -24` (or `-0x18`), never `0xFFE8`; `ori t0, t0, 0xFFFF`, never `-1`.

Test it on your own build (`build/main.ps-exe`) and on any EXE from earlier chapters. To make bad files, copy one and damage it, for example `printf 'X' | dd of=copy.ps-exe bs=1 seek=0 conv=notrunc`, or `truncate -s 1000 copy.ps-exe`.

### Part (b): a hand-written header

`starter/main.s` has a complete, working program. The header is missing. Write it with `.ascii`, `.word` and `.fill` (no `.include`, no `.incbin`).

Requirements:

- Load address: any multiple of `0x800` from `0x80011000` to `0x801E0000`, **not** `0x80010000`. Change `.definelabel LOAD`, the literal in `.create` (which must equal `LOAD - 0x800`) and your header together.
- Initial PC: `main`.
- Initial GP: `LOAD + 0x8000`.
- Initial SP: base `0x801FFF00`, offset 0.
- Size field: payload size from the `__exe_end` label; the file must be exactly `0x800 +` size bytes.
- Region marker: one of the three standard strings, then zeros to `0x800`. All unused fields zero.

When it works, the program stores `$gp`, `$sp`, the address of `main` and the sum of the 8-word `table` into `results`. You do not edit the code.

**Hints**

- `xxd build/main.ps-exe | head -8` is your friend. Compare with section 5.2.
- Count the region string: the filler after it is `0x800 - 0x4C - length`.
- If the program hangs, check that `.org LOAD`, the load word and `.create` agree.

**Stretch goals**

- Make `exeinfo.py` add a warning for an SP base of 0 or an unusual GP.
- Print the instruction text with `jal`'s target as a symbol from `main.sym` if available.
- Change the region to Japan and confirm nothing else changes.

## 8. Verification

```sh
parts/part-01-machine-and-language/ch05-anatomy-of-an-executable/verify/verify.sh
```

Checks `starter/` by default; pass a path for a copy, `-v` for build output and emulator log, `--solution` for the reference. The emulator part takes up to 20 seconds if the program never starts. The exeinfo checks create their own EXEs (varied load addresses, instruction mixes and exactly-one-defect bad files), so nothing can be hard-coded.

| Check | What it means | If it fails |
|---|---|---|
| `exeinfo.py exists and runs` | The file exists and does not crash. | Missing file, or a Python exception (shown). |
| `exeinfo.py prints the header fields of valid EXEs` | Seven `key: value` lines with correct values for four different headers. | Wrong byte order or offset, `size` including the header, `sp` not base plus offset. |
| `...disassembles the first 16 instructions...` | Address, word and decoded text for all supported forms. | Message names the first wrong instruction: a wrong bit field, signed vs. unsigned immediate, branch target computed from the wrong address. |
| `...rejects malformed EXEs with the right category` | 14 broken files, each must give its own category. | A crash on short input, wrong order of tests, wrong boundary (for example `load + size` exactly at `0x80200000` is allowed). |
| `exeinfo.py agrees with your hand-built EXE` | Your tool and your header agree. | Part (a) or (b) is off. |
| `program defines main, done, table and results` | Labels exist. | You deleted one. |
| `the header is written by hand...` | No `.include`, `.incbin` or `.import`. | You used `psxexe.inc`. |
| `header starts with the magic...` | `PS-X EXE` plus 8 zeros. | Missing space in the magic, or the header is empty. |
| `file is a 2048-byte header plus a payload...` | Exact size, multiple of `0x800`. | Size computed from the wrong label; missing `.align 0x800`. |
| `load address is non-default...` | Aligned, in the allowed range, fits in RAM. | Still `0x80010000`, or unaligned. |
| `initial PC is the address of main` | Word at `0x10`. | `.word main` missing or wrong place. |
| `initial GP is load + 0x8000; SP base is 0x801FFF00 with offset 0` | Words at `0x14`, `0x30`, `0x34`. | Fields swapped or offset by 4. |
| `region marker...` | Standard string at `0x4C`, zeros elsewhere. | Typo in the string, wrong `.fill` count. |
| `program starts at the header's entry point and reaches done` | The emulator loaded and ran it. | Header, `.org` and `.create` disagree. |
| `GP, SP and the program's own address...` | The registers the program saw equal the header. | Header word at the wrong offset. |
| `the code and data landed at the load address` | A checksum over `table`, recomputed with new data. | Code assembled for one address, loaded at another. |

A pass ends with `CHAPTER 05: PASSED (16/16 checks)` and exit status 0.

## 9. Common pitfalls

- **Endianness when reading a dump.** `0000 0480` is `0x80040000`. Reverse bytes within each word.
- **Header size in the size field.** The field counts the payload only; the file is `0x800` larger.
- **Header and `.org` disagree.** Changing the load word but not `.org LOAD` (or the `.create` literal) gives a file that looks right and crashes.
- **`.create` takes a number.** `.create "x", LOAD - 0x800` fails; write the literal and keep a comment.
- **Missing `.align 0x800`.** The size is no longer a multiple of 2 KB and the file ends mid-sector.
- **Wrong sign extension in the disassembler.** `addiu t0, t0, 0xFFFF` is `-1`. `ori` with `0xFFFF` is not.
- **Branch targets from the wrong base.** The offset is relative to the instruction *after* the branch.
- **Region string off by one.** Count it: 55 characters for North America.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- psx-spx, "CPU Specifications" and "BIOS: PSX Executables" (the EXE header table): <https://psx-spx.consoledev.net/>
- psx-spx, "CDROM File Formats" for how `SYSTEM.CNF` points at the EXE.
- armips documentation: `.create`, `.org`, `.fill`, `.align`: <https://github.com/Kingcom/armips>
- `common/psxexe.inc` in this repository: the same header as a macro file.
