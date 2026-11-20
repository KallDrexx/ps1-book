# Chapter 3: Registers, Loads, Stores, and Arithmetic

## 1. Concept

MIPS is a **load/store architecture**. All computation happens between the CPU's 32 registers; memory is touched only by explicit loads and stores. Your job is to move values in, compute, and move them out.

## 2. Why it matters

Every inner loop in a PS1 game, from vertex math to particle updates, is this same pattern: load, compute, store. Knowing exactly what each load flavour does to the upper bits of a register, and what `add` does that `addu` does not, separates code that works from code that works until the numbers get big.

## 3. Learning objectives

After this chapter you can:

- name the 32 registers and say which are hardware facts and which are conventions;
- pick `lb`, `lbu`, `lh`, `lhu` or `lw` and predict the register's full 32 bits;
- explain why `addu` is the safe default and when `add` raises an exception;
- state the range of an immediate and why there is no "subtract immediate";
- write a labelled data table in armips and read it from code.

## 4. Prerequisites

[Chapter 2](../ch02-memory-map-and-endianness/README.md): `lui`/`ori`, `sw`/`sh`/`sb`, `lw`/`lbu`, little-endian layout, and the load-delay rule.

## 5. Explanation

### 5.1 The 32 registers

A register is a 32-bit slot inside the CPU, far faster than RAM. MIPS has 32 general-purpose ones, numbered `$0` to `$31`. Only two have hardware behaviour:

- `$zero` (`$0`) always reads 0; writes are ignored.
- `$ra` (`$31`) receives the return address from `jal` (Chapter 8).

Everything else is **convention**: the assembler and compilers agree on roles so that code can be mixed. Nothing stops you breaking them in your own assembly, but you will meet them again in Chapters 8 and 10.

| Names | Numbers | Convention |
|---|---|---|
| `$zero` | 0 | constant 0 |
| `$at` | 1 | reserved for the assembler (pseudo-instructions use it); avoid |
| `$v0`-`$v1` | 2-3 | function return values |
| `$a0`-`$a3` | 4-7 | function arguments |
| `$t0`-`$t7` | 8-15 | temporaries (a called function may destroy them) |
| `$s0`-`$s7` | 16-23 | saved (a called function must preserve them) |
| `$t8`-`$t9` | 24-25 | more temporaries |
| `$k0`-`$k1` | 26-27 | reserved for the kernel/exception handler; do not use |
| `$gp` | 28 | global pointer |
| `$sp` | 29 | stack pointer |
| `$fp` / `$s8` | 30 | frame pointer or ninth saved register |
| `$ra` | 31 | return address |

Besides these, the CPU has a program counter (`PC`) and the multiply/divide pair `HI`/`LO` (Chapter 12). In armips you can write `$t0` or `t0`; this book uses the `$` form.

For now: use `$t0`-`$t9` and `$s0`-`$s7`, and `$zero` freely.

### 5.2 Loads: how much, and what happens to the upper bits

A register is 32 bits wide, but you can load 8 or 16 bits. The rest of the register must be filled with something. That is the whole difference between the signed and unsigned loads:

| Instruction | Reads | Upper bits |
|---|---|---|
| `lw`  | 4 bytes | (none left) |
| `lhu` | 2 bytes | zeros (**zero-extended**) |
| `lh`  | 2 bytes | copies of bit 15 (**sign-extended**) |
| `lbu` | 1 byte  | zeros |
| `lb`  | 1 byte  | copies of bit 7 |

Example, memory holds the byte `0xFB`:

```
 lbu  ->  0x000000FB   (251)
 lb   ->  0xFFFFFFFB   (-5)
```

Sign extension keeps a small negative number negative when it is widened. This uses **two's complement**, where `0xFFFFFFFF` is -1 and a leading 1 bit means negative (Chapter 9 explains it fully). Choose by meaning: a colour channel or a count is `lbu`; a signed delta is `lb`.

Stores need no such choice: `sb` and `sh` simply write the low 8 or 16 bits.

Alignment as in Chapter 2: `lw`/`sw` at multiples of 4, `lh`/`lhu`/`sh` at even addresses. Bytes have no restriction.

**Load delay (reminder).** The value a load fetches is not usable by the *next* instruction; that instruction still sees the old register. Put something unrelated, or a `nop`, in between. Chapter 7 explains why. armips warns about this and the verifier fails on the warning.

### 5.3 Arithmetic

| Instruction | Does | Traps on overflow? |
|---|---|---|
| `addu rd, rs, rt` | `rd = rs + rt` | no |
| `subu rd, rs, rt` | `rd = rs - rt` | no |
| `addiu rt, rs, imm` | `rt = rs + imm` | no |
| `add`, `sub`, `addi` | same | **yes** |

Operand order matters: `subu $t0, $t1, $t2` is `t1 - t2`.

**Immediates are 16 bits and sign-extended.** `addiu` takes -32768 to 32767. To subtract a constant, add its negative (`addiu $t0, $t0, -100`); the CPU has no subtract-immediate instruction. Anything bigger than 16 bits needs `lui`/`ori` as in Chapter 2.

**Overflow.** Registers wrap: `0x7FFFFFFF + 1` is `0x80000000`. The "u" in `addu` does not mean unsigned-only. The same bits come out for signed and unsigned operands. It only means "never raise an exception". The non-`u` forms raise an **Overflow exception** when the result does not fit in a *signed* 32-bit number. On the PS1 that means your program is thrown into the BIOS exception handler and, in this book's tests, never reaches `done`. Compilers emit `addu`/`addiu` essentially always, and so should you.

**Pseudo-instructions.** armips accepts a few conveniences that expand to real instructions:

| Written | Becomes |
|---|---|
| `li $t0, value` | one `ori` (0 to `0xFFFF`), one `addiu` (-32768 to -1), one `lui` (low half zero), otherwise `lui` + `addiu` |
| `la $t0, label` | the same, with the label's address |
| `move $t0, $t1` | `addu $t0, $t1, $zero` |
| `subiu $t0, $t1, n` | `addiu $t0, $t1, -n` |
| `negu $t0, $t1` | `subu $t0, $zero, $t1` |

Chapter 2 asked you to write the `lui`/`ori` pair by hand to see the real encoding. From here on these pseudo-instructions are fine, and the verifier accepts them. The caution from Chapter 2 still holds: the two-instruction `li` is `lui` + `addiu`, not `lui` + `ori`, so its `lui` is one higher than the value's top half whenever bit 15 is set (`li $t0, 0xDEADBEEF` is `lui 0xDEAE` + `addiu 0xBEEF`).

### 5.4 armips syntax in one page

| Element | Form |
|---|---|
| Label | `name:` at the start of a line. Its value is the address of what follows. |
| Comment | `;` to end of line (`//` also works). |
| `.org addr` | Set the current address. Chapter 1's `.org 0x80010000` is the code start. |
| `.word v, ...` | Emit 32-bit values (little-endian, as on the PS1). |
| `.halfword v` | Emit a 16-bit value. |
| `.byte v` | Emit an 8-bit value. |
| `.fill n, v` | Emit `n` bytes of value `v`. |
| `.align n` | Pad with zeros to a multiple of `n`. |
| Expressions | `label >> 16`, `label & 0xFFFF`, `1+2`; usable wherever a number is. |

Data is not special: it is bytes in the file. A label before `.word` names a table, and the CPU reads it with a load. Put `.align 4` before word tables so `lw` works. A table placed after `done:` is never executed because the program loops at `done`. Never put data inside the code you run.

## 6. Worked example

Compute `x - y` for two words in a table and store the result:

```
    la    $t0, pair        ; t0 = &pair
    lw    $t1, 0($t0)      ; x
    lw    $t2, 4($t0)      ; y
    nop                    ; load delay: $t2 is not ready yet
    subu  $t3, $t1, $t2
    sw    $t3, 8($t0)
done:
    j     done
    nop

.align 4
pair:  .word 50, 8, 0
```

Whenever you write a load, ask: what is the first instruction that reads this register? If it is the next line, add a `nop` or reorder.

## 7. Project: "Register Calculator"

Load operands from the `inputs` table in `starter/main.s`, compute the values below, and store them in `results`. The starter is Chapter 2's program with its body removed and one piece of scaffolding added, the `inputs` table.

**The table** (read-only data; do not edit it, the verifier replaces it with other values):

| Offset | Size | Name | Starter value |
|---|---|---|---|
| `+0x00` | word | `a` | 1000 |
| `+0x04` | word | `b` | 2500 |
| `+0x08` | word | `c` | `0x7FFFFFF0` |
| `+0x0C` | halfword | `h` | `0xFF38` |
| `+0x0E` | byte | `s` | `0xFB` |

**Results** (one word each, at `results + 4*index`):

| Index | Value |
|---|---|
| 0 | `a + b` |
| 1 | `a - b` |
| 2 | `b - a` |
| 3 | `a + 100` |
| 4 | `a - 100` |
| 5 | `0x12345678 + a` (build the constant from its two halves) |
| 6 | `c + 0x20` (wraps; with the starter's `c` it overflows a signed number) |
| 7 | `h`, zero-extended |
| 8 | `h`, sign-extended |
| 9 | `s`, zero-extended |
| 10 | `s`, sign-extended |
| 11 | `h + s`, both treated as signed |
| 12 | `-a` (use `$zero`) |

**Then** swap `a` and `b` in the `inputs` table itself, in memory.

**Constraints**

- Between `main:` and `done:` use only: `lui ori lw lh lhu lb lbu sw sh sb add addu addi addiu sub subu nop` (and the pseudo-instructions of section 5.3, which expand to those). No branches, loops, shifts or logic.
- Use immediate-form adds for indexes 3 and 4.
- Do not pre-fill `results`; do not edit the table; keep the labels `main`, `done`, `inputs`, `results`.
- Respect the load delay. The program has no stack and needs none.

**Hints**

- Load every operand once into its own register at the top, then compute from registers.
- Indexes 7-10 are two loads from the same address with different instructions.
- Registers are cheap: you have more than 20 free ones.
- The swap needs both values in registers before either store.

**Stretch goals** (in a copy)

- Put an `add` where the starter's `c` overflows and watch what the emulator does. Look at the CPU registers in Redux; `Cause` and `EPC` show the exception.
- Write `h + s` using `lhu` and `lbu` instead and compare with index 11.
- Remove all `nop`s and read what armips warns.

## 8. Verification

```sh
parts/part-01-machine-and-language/ch03-registers-loads-stores-arithmetic/verify/verify.sh
```

Checks `starter/` by default. Pass a path for a copy, `-v` for build output and the emulator log, `--solution` for the reference. The verifier assembles your program, scans its machine code, then runs it **four times**: with the starter's table, with two other input tables, and with `results` pre-filled with `0xAA`. The results must follow the inputs each time, so a program that stores precomputed numbers cannot pass.

| Check | What it means | If it fails |
|---|---|---|
| `program defines main, done, inputs and results` | Labels exist and tables are word-aligned. | A label was deleted or renamed. |
| `results block starts out all zero in the executable` | `results` is not pre-filled. | Remove data from `results`. |
| `main..done uses only Chapter 2-3 instructions` | No other opcode appears. The message names the offender. | A shift, branch, `and` or `mul` slipped in. Chapter 4 and later cover them. |
| `instruction mix: ...` | Each load width, `sw`, adds, subtracts, an immediate add twice, and `lui` appear at least the needed number of times. The message lists the shortfall. | You replaced a load flavour with another, or computed something with a constant. |
| `armips reports no warnings` | The build log has no warning. | Usually a load-delay warning: insert a `nop` or an unrelated instruction after the load it names. |
| `program reaches done` | No hang or crash. | An overflowing `add`/`addi`/`sub` (use the `u` forms), a misaligned access or a wild address. A 20-second timeout usually means an exception. |
| `results hold the right values for the starter's inputs` | Each expression is compared. The message names the first wrong index. | Wrong operand order, signed/unsigned load mixed up, or a load used too early (you see the previous register contents). |
| `results follow the inputs (ordinary values)` | The table is replaced; every result must change accordingly. | Results are hard-coded or read from the wrong offset. |
| `results follow the inputs (extreme values)` | Wraparound and sign-bit cases. | Typically `lh` vs `lhu`, or a trapping add. |
| `results stay inside the 13 words` | The verifier fills `results` with `0xAA`; all 13 words must be written and the tail untouched. | A result is not stored, or a store used the wrong offset. |
| `a and b are swapped in the inputs table` | `inputs` ends with a and b exchanged and `c`, `h`, `s` unchanged. | Storing `a` to both slots (stored after overwriting), or the wrong offsets. |

A pass ends with `CHAPTER 03: PASSED (11/11 checks)` and exit status 0.

## 9. Common pitfalls

- **Using a loaded register too soon.** The result is the old value, not an error. Only armips' warning tells you.
- **Operand order in `subu`.** `subu rd, rs, rt` is `rs - rt`.
- **`lb` where you meant `lbu`** (or the reverse). Values below 0x80 hide it; test with big ones.
- **`add` instead of `addu`.** Works for months, then traps on one big input.
- **Immediates beyond 16 bits.** armips rejects `addiu $t0, $t0, 0x12345`, but it silently truncates a negative one: `addiu $t0, $t0, -40000` assembles as `+25536`. Build such constants with `lui`/`ori` (or `li`) and use `addu`.
- **Hex immediates in `addiu`.** armips accepts `0x8000` to `0xFFFF` as bit patterns, and the CPU sign-extends them: `addiu $t0, $t0, 0xFFFF` adds -1, not 65535.
- **Data inside code.** A `.word` placed before `done:` would be executed as an instruction.
- **Swap overwrite.** Storing `a` over `b` before `b` is in a register loses `b`.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- psx-spx, "CPU Specifications" (register table, exceptions, and the full opcode list): <https://psx-spx.consoledev.net/>
- MIPS I instruction reference (any "MIPS Run" or MIPS32 manual): `addu`, `lb`, `lh`.
- armips documentation, directives and pseudo-instructions: <https://github.com/Kingcom/armips>
