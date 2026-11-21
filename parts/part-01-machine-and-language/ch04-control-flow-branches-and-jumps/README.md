# Chapter 4: Control Flow: Branches and Jumps

## 1. Concept

A program decides and repeats by changing the **program counter** (PC). MIPS has no `if` or `while`: you compare registers, then either fall through to the next instruction or **branch** elsewhere.

## 2. Why it matters

Every game loop, vertex loop and collision test is built from the few instructions in this chapter. The R3000A has no flags register, so a comparison like `a < b` is an ordinary instruction that writes 0 or 1 to a register. Once you see that, `if`, `while` and `for` in C stop being magic.

## 3. Learning objectives

After this chapter you can:

- choose between `beq`, `bne`, `blez`, `bgtz`, `bltz` and `bgez` for a given test;
- build a comparison with `slt`, `slti`, `sltu` or `sltiu`, and say when signed and unsigned results differ;
- translate `if/else`, `while` and `for` into labels and branches;
- explain how a branch offset is computed and how it differs from a `j` target;
- say what the branch delay slot is, and fill it with `nop`.

## 4. Prerequisites

[Chapter 3](../ch03-registers-loads-stores-arithmetic/README.md): registers, `lw`/`sw`, `addu`/`addiu`, data tables, pseudo-instructions. Chapter 2's load-delay rule still applies.

## 5. Explanation

### 5.1 The program counter

The PC holds the address of the instruction being fetched. Normally it advances by 4 each time. A branch or jump replaces that with a different address. You have already used one: `j done` at the end of every program jumps to itself forever.

### 5.2 The branch delay slot (first look)

On MIPS, **the instruction after a branch or jump always executes**, whether or not the branch is taken. That slot is the **branch delay slot**. It exists because the CPU has already fetched the next instruction by the time the branch resolves.

```
    bne   $t0, $zero, loop     ; decide
    nop                        ; delay slot: runs either way
    ...                        ; fall-through, only if not taken
```

Rule for this chapter: **put a `nop` after every branch and jump.** It is always correct. Chapter 7 shows how to put useful work there and what goes wrong with a stray instruction. The verifier enforces the `nop`.

### 5.3 Conditional branches

Six instructions. Two compare a pair of registers; four compare one register with zero:

| Instruction | Branches if | Compares |
|---|---|---|
| `beq rs, rt, label` | `rs == rt` | two registers |
| `bne rs, rt, label` | `rs != rt` | two registers |
| `blez rs, label` | `rs <= 0` (signed) | register vs. zero |
| `bgtz rs, label` | `rs > 0` (signed) | register vs. zero |
| `bltz rs, label` | `rs < 0` (signed) | register vs. zero |
| `bgez rs, label` | `rs >= 0` (signed) | register vs. zero |

Equality against zero uses `$zero` as one operand: `beq $t0, $zero, label`.

**How the target is encoded.** The instruction stores a signed 16-bit **word** offset. The CPU computes

```
target = (address of the delay slot) + offset * 4        ; delay slot = branch address + 4
```

The base is the delay slot, not the branch itself. Reach is about +/-128 KiB, enough for any loop in this book. You never compute the offset; the assembler does, from the label. Checked with armips: a `bne` at `0x80010008` back to `0x80010000` stores offset -3, since `(0x80010000 - 0x8001000C) / 4 = -3`.

**The pseudo-branches.** armips accepts `b label` (`beq $zero, $zero`), `beqz`/`bnez` (`beq`/`bne` against `$zero`), and `blt`/`bgt`/`bge`/`ble` (plus `u` forms), which expand to `slt`/`sltu` into `$at` followed by `bne`/`beq $at, $zero` (Chapter 6 covers `$at`). The `nop` you write after one lands in the real branch's delay slot. The verifier accepts them, but write the `slt` yourself in this chapter so you see what each test costs.

### 5.4 Comparisons: the `slt` family

There is no "branch if less than" between two registers. Instead, a **set on less than** instruction writes 1 to its destination if the test is true and 0 otherwise:

| Instruction | Destination is 1 if |
|---|---|
| `slt rd, rs, rt` | `rs < rt`, **signed** |
| `sltu rd, rs, rt` | `rs < rt`, **unsigned** |
| `slti rt, rs, imm` | `rs < imm`, signed |
| `sltiu rt, rs, imm` | `rs < imm`, unsigned |

Then branch on that 0/1 with `beq`/`bne` against `$zero`.

Signed and unsigned disagree when exactly one operand has bit 31 set. The pattern `0xFFFFFFF0` is -16 signed and 4,294,967,280 unsigned:

```
 slt  : 0xFFFFFFF0 < 100   -> 1      (-16 < 100)
 sltu : 0xFFFFFFF0 < 100   -> 0      (huge < 100 is false)
```

Pick by meaning. Counters and deltas are signed; addresses and bit patterns are unsigned.

**Immediates.** `slti` and `sltiu` both **sign-extend** the 16-bit immediate. `sltiu` then compares it as unsigned, so `sltiu $t0, $t1, -1` means `$t1 < 0xFFFFFFFF`.

**Building the other comparisons.** Swap operands or invert the branch:

| Want | Write |
|---|---|
| `a < b` | `slt t, a, b` |
| `a > b` | `slt t, b, a` |
| `a >= b` | `slt t, a, b` then branch if `t == 0` |
| `a <= b` | `slt t, b, a` then branch if `t == 0` |

A comparison result is also just a number, so `addu count, count, t` counts how many times the test was true, with no branch at all.

### 5.5 Jumps

`j label` loads the PC with an absolute address. Its 26-bit field holds the low 26 bits of `target >> 2`; the upper 4 address bits come from the delay slot's address. A jump therefore reaches anywhere in the same 256 MB region, which covers all of RAM. Checked with armips: `j` to `0x80010000` stores the field `0x0004000`.

`jr rs` (jump to the address in a register) and `jal` (jump and link) arrive with functions in Chapter 8 and are not allowed in this project.

### 5.6 Control structures

All of C's structures are the same two moves: a test that skips code, and a jump that goes back.

```
 if (c) { A }         while (c) { B }            for (i = 0; i < n; i++) { B }

   test c             top:  test c               i = 0
   skip A if false          exit if false        top:  test i < n
   A                        B                          exit if false
 skip:                      j top                      B
                      exit:                            i++
                                                       j top
                                                 exit:
```

if/else adds a `j` over the else block at the end of the then block.

Two idioms:

- **Count down to zero.** A loop that counts `n` down can test the counter directly (`bgtz n, loop` to continue, or `blez n, exit` to leave) with no separate compare.
- **End pointer.** Walk a pointer until it equals an address one past the last element (`bne ptr, end, loop`) instead of keeping an index and a bound.

Test at the top when zero iterations must be possible (`n = 0`).

## 6. Worked example

Count down from `n` and add each value (sum of `1..n`), for the case where `n` is at least 1:

```
    la    $s0, n_word      ; a .word holding n
    lw    $t0, 0($s0)      ; n
    move  $t1, $zero       ; sum = 0 (also covers the load delay)
loop:
    addu  $t1, $t1, $t0    ; sum += n
    addiu $t0, $t0, -1     ; n--
    bgtz  $t0, loop        ; while n > 0
    nop                    ; delay slot
```

If `n` were 0 this would add 0, decrement to -1, see `-1 > 0` is false and exit with sum 0. That happens to be right here, but the body still ran once, which is wrong for most other bodies. Decide on purpose whether a loop must handle zero iterations.

## 7. Project: "Loop Lab"

Three loops over data in `starter/main.s`. The starter is Chapter 3's skeleton with different tables.

**Input tables** (the verifier replaces these; do not edit them):

| Label | Layout |
|---|---|
| `inputs` | `+0x00 n`, `+0x04 count`, `+0x08 seed`, `+0x0C step`, `+0x10 limit` (words) |
| `values` | 16 words; only the first `count` (1 to 16) are used |

**Outputs**

| Where | Value |
|---|---|
| `results+0x00` | (a) sum of `1..n` (`n >= 0`; `n = 0` gives 0) |
| `results+0x04` | (b) maximum of `values[0..count-1]`, **signed** |
| `results+0x08` | (b) minimum, signed |
| `seq[0..63]` | (c) `seq[0] = seed`, `seq[i+1] = seq[i] + step` (wrapping) |
| `results+0x0C` | (c) how many of the 64 entries are `< limit`, **signed** compare |
| `results+0x10` | (c) how many are `< limit`, **unsigned** compare |

`seq` is a 256-byte block the starter provides.

**Constraints**

- Between `main:` and `done:` use only Chapter 3's instructions plus `beq bne blez bgtz bltz bgez slt slti sltu sltiu j nop` (pseudo-instructions that expand to these, such as `li la move b beqz bnez`, are fine).
- A `nop` in every branch/jump delay slot. Branch only to labels between `main` and `done`.
- Three real loops. No shifts, multiplies, `jal`, `jr` or closed-form shortcuts.
- Do not pre-fill `results` or `seq`; do not modify `inputs` or `values`.
- Keep the labels `main`, `done`, `inputs`, `values`, `results`, `seq`.

**Hints**

- Load the table addresses once into `$s` registers; keep loop state in `$t` registers.
- For (b), start with `values[0]` as both max and min and scan the rest. An "is it bigger" test is a `slt` and a branch that skips the update.
- For (c), you can fill and count in one pass. For the end of the loop compare a pointer to `seq + 256`.
- Part (c) with the starter data gives different signed and unsigned counts; make sure you understand why.

**Stretch goals** (in a copy)

- Rewrite (c)'s counts with a branch instead of `addu` of the `slt` result.
- Put a non-`nop` instruction in a delay slot and predict what changes, then check in the Redux debugger.
- Use `sltiu rt, rs, 1` as "is `rs` zero?" and find where that idiom helps.

## 8. Verification

```sh
parts/part-01-machine-and-language/ch04-control-flow-branches-and-jumps/verify/verify.sh
```

Checks `starter/` by default; pass a path for a copy, `-v` for build output and emulator log, `--solution` for the reference. The verifier scans your machine code, then runs the program several times: with the starter's data, with five other data sets patched into the executable (zero and single-element cases, large `n`, extreme values, ties, negative step), and once with `results` and `seq` pre-filled with `0xAA`. The largest `n` is 3000, so a simple loop finishes well within the time limit.

| Check | What it means | If it fails |
|---|---|---|
| `program defines main, done, inputs, values, results and seq` | Labels exist; tables word-aligned. | A label was deleted or renamed. |
| `data tables are as shipped` | `results` and `seq` start zero; inputs unedited. | You pre-filled an output or edited an input. |
| `main..done uses only Chapter 2-4 instructions` | No other opcode. The message names the offender. | A shift, `and`, `mult`, `jal` or `jr`. |
| `every branch and jump has a nop in its delay slot` | The word after each is `0x00000000` (`nop`). | A missing `nop`, or a useful instruction placed in the slot (save that for Chapter 7). |
| `branch targets stay inside main..done and the code has at least 3 loops` | Backward branches/jumps counted. | Fewer than three loops, or a branch past `done` or into data. |
| `instruction mix` | At least two `slt`/`slti`, one `sltu`/`sltiu` and three conditional branches. | You counted with something other than `slt`/`sltu`. |
| `armips reports no warnings` | No warnings in the build log. | A load used by the very next instruction. |
| `program reaches done` | No hang within the timeout. | An infinite loop: counter never changes, exit test inverted, or branch to the wrong label. |
| `results and seq are right for the starter's data` | Every value compared; message names the first wrong one. | Off-by-one bound, swapped `slt` operands, `slt` vs `sltu`. |
| `loops handle the degenerate cases` | `n = 0`; `count = 1`; zero limit; sign-boundary seed. | Loop body runs once before the first test. |
| `results follow the data` | Values like `0x80000000`, `limit = 0x80000000`. | Wrong signedness in a compare. |
| `ties and a long sum` | Equal values; `n = 3000`; negative step. | Strict vs. non-strict compare mix-up or a loop that scales badly. |
| `every word of results and seq is written by your code` | Pre-filled `0xAA` blocks must be fully overwritten. | A missing store, or a store past the fifth result. |
| `input tables are left unchanged` | `inputs` and `values` same after the run. | You counted down in memory instead of in a register. |

A pass ends with `CHAPTER 04: PASSED (14/14 checks)` and exit status 0.

## 9. Common pitfalls

- **Forgetting the delay slot.** The instruction after a branch runs regardless. A `nop` makes it harmless.
- **Off-by-one in loop bounds.** Testing before or after the decrement changes the count by one. Trace the first and last pass by hand.
- **Signed vs. unsigned compare.** `slt` on addresses or bit patterns, or `sltu` on signed counters, works until a value has bit 31 set. Test with `0x80000000`.
- **A load in the compare.** `lw $t0, ...` then `slt $t1, $t0, ...` on the next line reads the old `$t0` (Chapter 2's load delay).
- **Loop that tests at the bottom.** It always runs once; zero-iteration cases need a test first.
- **Branching to data or past `done`.** Labels are just addresses; the assembler will not stop you.
- **`slti` with a large constant.** The immediate is 16 bits, sign-extended. For a bigger limit, load it into a register and use `slt`.
- **Using pseudo-branches blindly.** `blt` hides a `slt` and overwrites `$at` (Chapter 6).

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- [Appendix A](../../../appendices/A-mips-cheat-sheet.md): branch and jump encodings, pseudo-instruction expansions, delay-slot hazards.
- psx-spx, "CPU Specifications": the opcode table and branch delay behavior: <https://psx-spx.consoledev.net/>
- MIPS I instruction reference (any "MIPS Run" or MIPS32 manual): `beq`, `bne`, `slt`, `sltu`, `j`.
- armips documentation, MIPS section: <https://github.com/Kingcom/armips>
