# Appendix A: MIPS R3000A Cheat Sheet

The CPU in the PlayStation is a MIPS R3000A (MIPS I instruction set, little-endian, 33.8688 MHz, no FPU, no MMU/TLB).
This appendix lists every instruction the CPU executes, its encoding, the hazards, what armips accepts and what it expands.
Hardware facts follow psx-spx ("CPU Specifications"); where a fact is not exercised by a chapter of this book it is marked
*(not checked in the book)*. Chapters 2 to 12 teach the material; this is the lookup table.

| Section | Contents |
|---|---|
| A.1 | Registers and the O32 calling convention |
| A.2 | Instruction formats and field extraction |
| A.3 | Instruction tables (by group, with opcode / funct) |
| A.4 | Pseudo-instructions and what armips emits |
| A.5 | Hazards: branch delay, load delay, HI/LO |
| A.6 | Multiply and divide: results, timing, divide by zero |
| A.7 | Coprocessor 0: registers, exceptions, `rfe` |
| A.8 | armips directives and behaviors the book relies on |
| A.9 | Immediates and idioms |

## A.1 Registers

32 general registers, plus `PC`, `HI`, `LO`. `$zero` reads 0 and ignores writes. In armips write `$t0` or `t0`; the book uses the `$` form.

| Number | Name | Role (O32 ABI) | Preserved across a call? |
|---|---|---|---|
| 0 | `$zero` | constant 0 | n/a |
| 1 | `$at` | assembler temporary (pseudo-instruction scratch; never keep a value in it, Ch 6) | no |
| 2-3 | `$v0 $v1` | return values | no |
| 4-7 | `$a0-$a3` | arguments 1 to 4 | no |
| 8-15 | `$t0-$t7` | temporaries | no |
| 16-23 | `$s0-$s7` | saved | **yes** |
| 24-25 | `$t8 $t9` | temporaries | no |
| 26-27 | `$k0 $k1` | reserved for the kernel and exception handler; do not use | n/a |
| 28 | `$gp` | global pointer | yes |
| 29 | `$sp` | stack pointer | yes |
| 30 | `$fp` / `$s8` | frame pointer or ninth saved register | yes |
| 31 | `$ra` | return address (`jal` and `jalr` write it) | no |

**Calling convention (Ch 8, Ch 10).**

| Rule | Value |
|---|---|
| Arguments | first four in `$a0-$a3`; the rest on the stack, in order, from `16($sp)` as the callee sees it on entry |
| Home area | the caller always reserves 16 bytes at `0..15($sp)` at the call, even for fewer than four arguments; the callee may store `$a0-$a3` there |
| `$sp` alignment | multiple of **8** at every call; frame sizes are multiples of 8 (`$ra` alone: 16 + 4 rounded up = **24**) |
| Return value | `$v0` (and `$v1` for 64-bit values) |
| `jal target` | `$ra = address of the jal + 8` (the instruction after the delay slot) |
| `jalr rs` / `jalr rs, rd` | same, return address into `$ra` / `rd`; `jr $ra` returns. armips takes the **target first** (`jalr rs, rd`); GNU `as` and objdump write `jalr rd, rs` |
| Callee-saved | `$s0-$s7`, `$gp`, `$fp`, `$sp` |

## A.2 Instruction formats

```
R-type  31   26 25  21 20  16 15  11 10   6 5     0
        | op=0 |  rs  |  rt  |  rd  |shamt | funct |      register operations
I-type  | op   |  rs  |  rt  |      imm16          |      immediates, loads, stores, branches
J-type  | op   |            target26                |      j, jal
```

| Topic | Rule |
|---|---|
| Immediate extension | `addi addiu slti sltiu` and all load/store/branch offsets are **sign-extended**; `andi ori xori` are **zero-extended**. `sltiu` sign-extends its immediate, then compares unsigned. `lui` puts `imm` in the top 16 bits. |
| Branch target | `(address of the delay slot) + (offset16 << 2)`; the base is the branch address + 4, not the branch itself. Reach about +/-128 KiB. (Ch 4: a `bne` at `0x80010008` back to `0x80010000` has offset -3.) |
| Jump target | `j`/`jal`: `(address of the delay slot & 0xF0000000) \| (target26 << 2)`: stays inside the same 256 MB region. Longer jumps use `jr`/`jalr`. |
| Memory address | `base + sign-extended offset16`. `lw`/`sw` need a multiple of 4, `lh`/`lhu`/`sh` an even address, bytes any. A misaligned access raises an address-error exception (A.7), it does not round (Ch 2, 11). |
| Shift amount | `sll srl sra` use `shamt` (5 bits); `sllv srlv srav` use the **low 5 bits** of `rs`. There is no rotate. |
| Endianness | little-endian: `0x12345678` at address A is bytes `78 56 34 12`. |
| `nop` | the word `0x00000000` (`sll $zero,$zero,0`). |

## A.3 Instruction tables

`op` is bits 31-26 (hex). For R-type, `op` = 00 and `funct` is bits 5-0. Operation notation: `rd = rs + rt`, memory `M[...]`.

### A.3.1 Arithmetic and logic (register)

| Instruction | funct | Operation | Traps on overflow? |
|---|---|---|---|
| `add rd,rs,rt` | 20 | `rd = rs + rt` | **yes** (signed) |
| `addu rd,rs,rt` | 21 | `rd = rs + rt` | no |
| `sub rd,rs,rt` | 22 | `rd = rs - rt` | **yes** |
| `subu rd,rs,rt` | 23 | `rd = rs - rt` | no |
| `and rd,rs,rt` | 24 | bitwise AND | |
| `or rd,rs,rt` | 25 | bitwise OR | |
| `xor rd,rs,rt` | 26 | bitwise XOR | |
| `nor rd,rs,rt` | 27 | `rd = ~(rs \| rt)` (`nor rd,rs,$zero` is NOT) | |
| `slt rd,rs,rt` | 2A | `rd = (rs < rt)`, **signed** | |
| `sltu rd,rs,rt` | 2B | `rd = (rs < rt)`, **unsigned** | |

The `u` in `addu` means "never traps", not "unsigned only": the same bits come out for signed and unsigned operands (Ch 3, 9). Compilers emit `addu`/`addiu` essentially always.

### A.3.2 Arithmetic and logic (immediate)

| Instruction | op | Operation | Immediate |
|---|---|---|---|
| `addi rt,rs,imm` | 08 | `rt = rs + imm`, **traps** on signed overflow | sign-ext |
| `addiu rt,rs,imm` | 09 | `rt = rs + imm` | sign-ext (range -32768..32767; also the way to subtract a constant) |
| `slti rt,rs,imm` | 0A | `rt = (rs < imm)` signed | sign-ext |
| `sltiu rt,rs,imm` | 0B | `rt = (rs < imm)` unsigned compare of the sign-extended `imm` | sign-ext |
| `andi rt,rs,imm` | 0C | AND | zero-ext |
| `ori rt,rs,imm` | 0D | OR | zero-ext |
| `xori rt,rs,imm` | 0E | XOR | zero-ext |
| `lui rt,imm` | 0F | `rt = imm << 16` | |

### A.3.3 Shifts

| Instruction | funct | Operation |
|---|---|---|
| `sll rd,rt,sa` | 00 | `rd = rt << sa` (logical) |
| `srl rd,rt,sa` | 02 | `rd = rt >> sa`, zero fill |
| `sra rd,rt,sa` | 03 | `rd = rt >> sa`, copies of bit 31 fill (signed) |
| `sllv rd,rt,rs` | 04 | shift by `rs & 31` |
| `srlv rd,rt,rs` | 06 | |
| `srav rd,rt,rs` | 07 | |

### A.3.4 Multiply and divide (HI/LO)

| Instruction | funct | Operation |
|---|---|---|
| `mult rs,rt` | 18 | `HI:LO = rs * rt`, signed 32x32 -> 64 |
| `multu rs,rt` | 19 | unsigned |
| `div rs,rt` | 1A | `LO = rs / rt` (toward zero), `HI = rs % rt` (sign of `rs`), signed |
| `divu rs,rt` | 1B | unsigned |
| `mfhi rd` / `mflo rd` | 10 / 12 | `rd = HI` / `LO` |
| `mthi rs` / `mtlo rs` | 11 / 13 | `HI = rs` / `LO = rs` |

No two- or three-operand `mul`/`div` exists: armips rejects `mul $d,$a,$b` (Ch 12); write the real pair. Timing and the hazard rule: A.5 and A.6.

### A.3.5 Loads and stores

| Instruction | op | Operation | Alignment |
|---|---|---|---|
| `lb rt,off(rs)` | 20 | byte, **sign**-extended | none |
| `lbu rt,off(rs)` | 24 | byte, zero-extended | none |
| `lh rt,off(rs)` | 21 | halfword, sign-extended | even |
| `lhu rt,off(rs)` | 25 | halfword, zero-extended | even |
| `lw rt,off(rs)` | 23 | word | multiple of 4 |
| `lwl rt,off(rs)` | 22 | load the bytes from `A` back to the **start** of its aligned word into the **high** end of `rt`, merging with `rt` | none |
| `lwr rt,off(rs)` | 26 | load the bytes from `A` to the **end** of its aligned word into the **low** end of `rt`, merging with `rt` | none |
| `sb rt,off(rs)` | 28 | store low byte | none |
| `sh rt,off(rs)` | 29 | store low halfword | even |
| `sw rt,off(rs)` | 2B | store word | multiple of 4 |
| `swl rt,off(rs)` | 2A | store the high-order bytes of `rt` into the bytes from the start of `A`'s aligned word up to `A` | none |
| `swr rt,off(rs)` | 2E | store the low bytes of `rt` from `A` to its word end | none |
| `lwc2 / swc2` | 32 / 3A | load / store a GTE data register (Appendix D) | multiple of 4 |

Unaligned word at `A` (little-endian): load `lwr rt,0(A)` + `lwl rt,3(A)` (either order); store `swr rt,0(A)` + `swl rt,3(A)`. If `A` is aligned each instruction moves the whole word, so the pair is still correct (Ch 11, 12). Loads obey the load-delay rule (A.5), with one exception for the `lwl`/`lwr` pair.

### A.3.6 Branches and jumps

All have a **delay slot** (A.5). "link" = `$ra = (address of the branch) + 8`.

| Instruction | op / rt / funct | Branches (or jumps) when |
|---|---|---|
| `beq rs,rt,L` | op 04 | `rs == rt` |
| `bne rs,rt,L` | op 05 | `rs != rt` |
| `blez rs,L` | op 06 | `rs <= 0` signed |
| `bgtz rs,L` | op 07 | `rs > 0` signed |
| `bltz rs,L` | op 01, rt 00 | `rs < 0` signed |
| `bgez rs,L` | op 01, rt 01 | `rs >= 0` signed |
| `bltzal rs,L` | op 01, rt 10 | `rs < 0`; **link always written, taken or not** |
| `bgezal rs,L` | op 01, rt 11 | `rs >= 0`; link always written |
| `j target` | op 02 | always |
| `jal target` | op 03 | always, link |
| `jr rs` | funct 08 | always, `PC = rs` |
| `jalr rs` / `jalr rs,rd` (armips order) | funct 09 | always, `PC = rs`, link into `$ra` / `rd` |

The branch condition is evaluated from the register values **before** the delay slot runs (Ch 7). A branch or jump in a delay slot is illegal; armips refuses it (`This instruction can't be in a delay slot`).

### A.3.7 System and coprocessor

| Instruction | Encoding | Operation |
|---|---|---|
| `syscall code` | R-type funct 0C | exception 8 (Syscall); the BIOS handler uses it for `EnterCriticalSection`/`ExitCriticalSection` |
| `break code` | R-type funct 0D | exception 9 (Breakpoint) |
| `mfc0 rt,cop0r` | op 10, rs 00 | `rt = COP0 register` (see load-delay note in A.5) |
| `mtc0 rt,cop0r` | op 10, rs 04 | `COP0 register = rt` |
| `rfe` | op 10, CO bit set, funct 10 | restore the status-register mode stack (A.7); **not** a jump |
| `mfc2 / cfc2 / mtc2 / ctc2` | op 12, rs 00 / 02 / 04 / 06 | move GTE data / control registers (Appendix D) |
| GTE command | op 12, bit 25 set | `RTPS`, `RTPT`, `NCLIP`, ... (Appendix D) |
| `cop1`, `cop3`, `lwc0/1/3`, `swc0/1/3` | op 11, 13, 30/31/33, 38/39/3B | no such coprocessor in the console: raise Coprocessor Unusable (A.7) *(not checked in the book)* |

The R3000A in the PlayStation has **no TLB instructions** (`tlbr tlbwi tlbwr tlbp` do not exist) and no `ll`, `sc`, `sync` or branch-likely forms; MIPS II+ instructions (`mul`, `beql`, `movz`, `clz`, ...) are not available.

## A.4 Pseudo-instructions and what armips emits

Observed by disassembling the pinned armips (Ch 6, 3, 4). **One source line is not one instruction**: every 2-word row below affects counts, offsets and delay slots.

| You write | Becomes | Words |
|---|---|---|
| `nop` | `sll $zero,$zero,0` (word `0`) | 1 |
| `move $a,$b` | `addu $a,$b,$zero` | 1 |
| `negu $a,$b` | `subu $a,$zero,$b` | 1 |
| `subiu $a,$b,n` | `addiu $a,$b,-n` | 1 |
| `li $t,v`, `v` in 0..0xFFFF | `ori $t,$zero,v` | 1 |
| `li $t,v`, `v` in -32768..-1 | `addiu $t,$zero,v` | 1 |
| `li $t,v`, low half zero | `lui $t,v>>16` | 1 |
| `li $t,v`, otherwise 32-bit | `lui` of the top half, then `addiu` of the low half | 2 |
| `la $t,label` | expands like `li` of the address: `lui` + `addiu`, or `lui` alone when the low half is zero (`la $t0,0x80020000`) | 1 or 2 |
| `b L` | `beq $zero,$zero,L` | 1 |
| `beqz $a,L` / `bnez $a,L` | `beq` / `bne $a,$zero,L` | 1 |
| `blt $a,$b,L` | `slt $at,$a,$b` ; `bne $at,$zero,L` | 2 |
| `bge $a,$b,L` | `slt $at,$a,$b` ; `beq $at,$zero,L` | 2 |
| `bgt` / `ble` | the same with `$a` and `$b` swapped | 2 |
| `bge $a,10,L` | `slti $at,$a,10` ; `beq $at,$zero,L` | 2 |
| `lw $t,label` | `lui $t,hi` ; `lw $t,lo($t)` | 2 |
| `sw $t,label` | `lui $at,hi` ; `sw $t,lo($at)` | 2 |

**The `li`/`la` trap.** The second instruction is `addiu`, which sign-extends. When the low half is `0x8000` or more, armips adds one to the `lui` half to compensate: `li $t0,0xDEADBEEF` is `lui 0xDEAE` + `addiu 0xBEEF`, not `lui 0xDEAD` + `ori`. Write `lui`/`ori` yourself when you need exactly that pair (Ch 2).

Also: a multi-word pseudo-instruction placed in a delay slot is **split**: the first word lands in the slot and the rest runs after it (only on the fall-through path). The `u` forms (`bltu` ...) exist and use `sltu`. `$at` is clobbered by `blt`/`bge`/`bgt`/`ble` and `sw reg,label`.

## A.5 Hazards

| Hazard | Rule | Source |
|---|---|---|
| **Branch delay slot** | The one instruction after any branch or jump **always executes**, taken or not. The branch reads its condition registers before the slot runs. A branch/jump in a slot is illegal. | Ch 4, 7 |
| **Load delay slot** | The instruction right after a load (`lb lbu lh lhu lw lwl lwr`) reads the register's **old** value; the instruction after that sees the loaded one. No stall, no error. ALU results are forwarded: `addiu` then a use on the next line is fine. | Ch 7 |
| Load, then a write to the same register in the slot | the later write wins; the load's value is discarded (checked in Redux) | Ch 7 |
| Load in a branch delay slot | the first instruction executed after the branch (the target, or the fall-through) is that load's delay slot and still sees the old value | Ch 7 |
| `lwl` / `lwr` pair | an `lwl`/`lwr` may sit **directly after** the other on the same register and sees its result; anything else reading `rt` still waits one instruction | Ch 11 (psx-spx) |
| "Old value" is not a guarantee | psx-spx: an interrupt between the load and the next instruction lets the load finish first. Never rely on the stale value; fill the slot with unrelated work. | Ch 7 |
| `mfc0`, `mfc2`, `cfc2` | read like loads: do not use the destination in the next instruction (MIPS I; psx-spx lists the GTE moves as needing a delay). armips prints no warning for these. *(Delay not checked in the book.)* | |
| **HI/LO read side** | `mfhi`/`mflo` **interlock**: they stall until the multiplier or divider is done, so the result is always right | Ch 7, 12 |
| **HI/LO write side** | After `mfhi`/`mflo`, let **two instructions** pass before any `mult multu div divu mthi mtlo`. The MIPS I manuals call a violation undefined; psx-spx says only "do not touch lo/hi in the next 2 cycles or so... not yet understood". Emulators, including PCSX-Redux, do not model it, so a violation passes in the emulator. The book follows the conservative MIPS I rule, and GCC for the R3000 inserts the gap itself. | Ch 7, 12 |

**armips warning.** `register t0 may not be available due to load delay` is printed when the instruction after a load (`lb` to `lwr`) uses the loaded register; an `lwl`/`lwr` pair is exempt. It is a warning: the build still succeeds. The verifiers of Chapters 3, 4 and 7 to 16 fail on any armips warning; those of Chapters 2, 5, 6 and 17 do not look at warnings. armips compares only *consecutive instructions*: it cannot see a use that reaches the load through a branch.

**Filling slots.** Safe sources: an instruction from above the branch that the branch does not test; the first instruction of the target (then branch to the second); loop bookkeeping. A slot you cannot fill is still correct with `nop` (Ch 7).

## A.6 Multiply and divide

### A.6.1 Cycle counts

psx-spx values in CPU cycles; instruction fetch adds equally to every instruction, so treat the table as relative cost (Ch 12).

| Operation | Cycles | Notes |
|---|---|---|
| `addu subu and or xor nor sll srl sra slt` and immediates | 1 | |
| `lw lbu ...` | 1 + load delay slot | |
| `multu rs,rt` | 6 / 9 / 13 | 6 if `rs` in `0..0x7FF`, 9 if `0x800..0xFFFFF`, 13 otherwise (size of **`rs`**; put the smaller operand there) |
| `mult rs,rt` | 6 / 9 / 13 | 6 if `rs` in `-0x800..0x7FF`, 9 if `-0x100000..0xFFFFF`, 13 otherwise |
| `div`, `divu` | **36** | fixed |
| `mfhi`, `mflo` | 1 + stall | stalls until the unit finishes |

The unit runs beside the pipeline, so independent instructions between `mult` and `mflo` hide the wait: about one cycle each on hardware (a cached instruction), two each in PCSX-Redux, which charges every instruction 2 cycles (Ch 7, 12). Measured in Redux (Ch 12): a `multu`/`mflo` pair costs about 6, 9 and 13 cycles more than two plain instructions; `divu`/`mflo` about 36 more. Redux cycle counts mean something only under `-interpreter` (Appendix F).

### A.6.2 Results, including divide by zero

The R3000 **does not trap** on divide by zero or `0x80000000 / -1`. Examples from Ch 12 (`example/main.s`):

| Operation | HI | LO |
|---|---|---|
| `divu 7 / 0` | 7 (the dividend) | `0xFFFFFFFF` |
| `div 7 / 0` (dividend >= 0) | the dividend | -1 |
| `div -7 / 0` (dividend < 0) | the dividend | +1 |
| `div 0x80000000 / -1` | 0 | `0x80000000` |
| `div -7 / 2` | -1 | -3 (truncates toward zero) |
| `multu 0xFFFFFFFF * 0xFFFFFFFF` | `0xFFFFFFFE` | `0x00000001` |
| `mult -1 * -1` | 0 | 1 |

None of the divide-by-zero results is a usable quotient: test for zero yourself. For a 32-bit product `mflo` is the same for `mult` and `multu`.

Strength-reduction identities used in the book: `x*320 = (x<<8)+(x<<6)`, `x*-5 = -((x<<2)+x)`, `x/10 = (x * 0xCCCCCCCD) >> 35` (`multu`, then `mfhi`, then `srl` by 3), exact for every unsigned 32-bit `x`.

## A.7 Coprocessor 0 and exceptions

There is no MMU. COP0 holds only the exception and debug registers.

| COP0 reg | Name | Meaning |
|---|---|---|
| 3 | BPC | execution breakpoint address |
| 5 | BDA | data breakpoint address |
| 6 | JUMPDEST | last branch/jump target (read-only) |
| 7 | DCIC | breakpoint control |
| 8 | BadVaddr | faulting address after an address error |
| 9 | BDAM | data breakpoint mask |
| 11 | BPCM | execution breakpoint mask |
| 12 | **SR** | status register |
| 13 | **CAUSE** | exception cause |
| 14 | **EPC** | address to resume at |
| 15 | PRID | processor ID |

**SR** (psx-spx): bit 0 IEc (interrupt enable, current), 1 KUc (user mode, current), 2-3 IEp/KUp (previous), 4-5 IEo/KUo (old); bits 8-15 IM (interrupt mask; bits 8-9 software, bit 10 = the hardware interrupt line fed by `I_STAT`/`I_MASK`, Appendix B); 16 IsC (isolate cache), 17 SwC (swap caches), 22 BEV (boot exception vectors), 28-31 CU0-CU3 (coprocessor usable; CU2 = GTE). At `main` in the book's PCSX-Redux (OpenBIOS, fast boot) `SR = 0x40000000`: only CU2 set, interrupts off (measured; Ch 17).

**CAUSE**: bits 2-6 ExcCode; bits 8-15 IP (pending interrupts; bit 10 = hardware IRQ); bits 28-29 CE (coprocessor number); bit 31 BD (the exception happened in a branch delay slot: `EPC` then points at the **branch**).

| ExcCode | Name | Typical cause in this book |
|---|---|---|
| 0 | Int | hardware interrupt (VBlank, DMA, timer, ...) |
| 4 | AdEL | misaligned or illegal-address **load** / instruction fetch |
| 5 | AdES | misaligned or illegal-address **store** |
| 6 | IBE | bus error on instruction fetch |
| 7 | DBE | bus error on data access |
| 8 | Syscall | `syscall` |
| 9 | Bp | `break` |
| 10 | RI | reserved (undefined) instruction |
| 11 | CpU | coprocessor unusable (e.g. a GTE instruction with CU2 clear) |
| 12 | Ovf | `add`/`addi`/`sub` overflow |

**Vectors.** Reset `0xBFC00000`. General exception `0x80000080` (BEV = 0) or `0xBFC00180` (BEV = 1), which the `break` instruction also uses; COP0 debug breakpoints (BPC/BDA) use `0x80000040` *(not checked in the book)*. The BIOS installs its handler at `0x80000080`; once it runs, a homebrew program has no recovery from an address error or overflow (Ch 3, 11). BIOS function tables: call `A0h`/`B0h`/`C0h` with the function number in `$t1` (Appendix B).

**`rfe`** pops the mode stack: `SR[3:0] = SR[5:2]` (the old/previous bits shift down; the old bits stay). It is normally the instruction in the delay slot of the `jr` that leaves the handler.

## A.8 armips: directives and behavior

The book assembles Parts I to III with armips (`.psx` selects the R3000 instruction set). `-sym` writes the symbol file the harness reads.

| Directive | Effect | Book note |
|---|---|---|
| `.psx` | select the PlayStation R3000A instruction set. It emits **no PSX-EXE header**. | Ch 1, 5 |
| `.create "f", addr` | start an output file; `addr` is the address of **file offset 0** | the book uses `LOAD - 0x800` |
| `.close` | finish the file | |
| `.org addr` | set the current address (virtual and file position move together) | code starts at `0x80010000` |
| `.include "f"` | include a source file, resolved relative to the working directory | `common/psxexe.inc` emits the 2 KB header |
| `.definelabel name, v` | define a constant label | `.ifndef` / `.endif` also exist |
| `.word v,...` | 32-bit values, little-endian | **does not align itself** |
| `.halfword v,...` | 16-bit values | negative values fine (`-100` = `0xFF9C`); does not align itself |
| `.byte v,...` | 8-bit values | |
| `.ascii "text"` | the bytes of the string, no terminator | |
| `.fill n, v` | `n` **bytes** of value `v` (`.fill 12,0` is three words) | |
| `.align n` | zero-pad up to the next multiple of `n`; **`n` is a byte count**, a power of two | `.align 8`, not `.align 3` (error "Invalid alignment") |
| `.incbin "f"` | copy a file's bytes in; path relative to the build's working directory | Ch 16 |
| Comments | `;` to end of line (`//` also works) | |
| Expressions | `label >> 16`, `label & 0xFFFF`, `1+2`, usable wherever a number is | |

**Behavior the book depends on.**

| Fact | Consequence |
|---|---|
| armips has no `.set noreorder`/`.set reorder` and **never reorders** | Your source order is the execution order; every delay slot is filled by you. Compiler output in Part IV shows `.set noreorder`; that is GNU `as`, which reorders unless told. |
| `.psx` writes no header | The PSX-EXE header (Appendix E.1, Ch 5) is emitted by `common/psxexe.inc`; the file must be a multiple of 0x800 bytes, so end with `.align 0x800`. |
| `.word`, `.halfword` after a `.byte` | emitted at the very next address, misaligned, **without a warning**; the crash comes at the first `lw` (Ch 11). Put `.align` yourself. |
| Pseudo-instructions expand silently | see A.4; `bne` followed by `li $t6,0x12345678` assembles without complaint. |
| Load-delay warning is a warning, not an error | The build still succeeds; most assembly-chapter verifiers fail on any warning (A.5). |
| Mnemonics not accepted | `mul` (`Invalid MIPS opcode`) and three-operand `div` (Ch 12). |
| Data is just bytes | Never place data in the run path; the program loops at `done:` so a table after it is never executed (Ch 3). |

## A.9 Immediates and idioms

| Goal | Code |
|---|---|
| Load a constant | `li $t0, 0x12345678` (2 words), or `lui $t0,0x1234` ; `ori $t0,$t0,0x5678` |
| Address of a label | `la $t0, label`; or `lui $t0, label>>16` ; `ori $t0,$t0,label & 0xFFFF` |
| Register copy | `move $a,$b` |
| Negate / NOT | `subu $a,$zero,$b` / `nor $a,$b,$zero` |
| Subtract a constant | `addiu $t0,$t0,-100` (no subtract-immediate exists) |
| Compare, branch if `a < b` | `slt $at,$a,$b` ; `bne $at,$zero,L` (or `blt`) |
| Test a bit, branch if clear | `andi $t1,$t0,mask` ; `beq $t1,$zero,L` |
| Multiply by 320 | `sll $t1,$t0,8` ; `sll $t2,$t0,6` ; `addu $t1,$t1,$t2` |
| Wait for GPUSTAT bit 26 | `lui $t1,0x0400` ; `wait: lw $t0,0($s0)` (`$s0` = `0x1F801814`) ; `nop` (load delay) ; `and $t0,$t0,$t1` ; `beqz $t0,wait` ; `nop` |
| Return | `jr $ra` ; `nop` |
| Idle loop (`done:`) | `done: j done` ; `nop` |
