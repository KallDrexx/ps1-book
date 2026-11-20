# Chapter 7: The Pipeline and Delay Slots

## 1. Concept

The R3000A works on several instructions at once, like an assembly line. Two visible consequences: the instruction after a branch always runs (the **branch delay slot**), and a loaded value is not ready for the very next instruction (the **load delay slot**).

## 2. Why it matters

Chapters 2 to 4 gave you rules of thumb: "`nop` after every branch", "`nop` after every load". They are always safe and they waste cycles. In an inner loop that runs thousands of times per frame, every `nop` is pure loss. Game programmers filled these slots by hand, and compilers still do it. You also cannot read compiler output (Part IV) without knowing that the instruction after a `bne` belongs to the branch.

## 3. Learning objectives

After this chapter you can:

- name the five pipeline stages and draw two instructions overlapping;
- explain why a branch has a delay slot and a load has a load delay slot;
- predict what a short sequence computes when it contains a load or branch hazard;
- fill delay slots with useful work and say which instructions are safe to put there;
- read the armips load-delay warning and know what it can and cannot see.

## 4. Prerequisites

[Chapter 4](../../part-01-machine-and-language/ch04-control-flow-branches-and-jumps/README.md) (branches, `nop` in the slot), [Chapter 3](../../part-01-machine-and-language/ch03-registers-loads-stores-arithmetic/README.md) (loads, stores, `addiu`), [Chapter 6](../../part-01-machine-and-language/ch06-emulation-and-debugging/README.md) (stepping in the debugger; the pseudo-instruction expansions matter here).

## 5. Explanation

### 5.1 The five-stage pipeline

Doing one instruction start to finish before the next would leave most of the chip idle. The R3000 splits every instruction into five **stages**, each handled by different hardware, and starts a new instruction every cycle:

| Stage | Name | Work |
|---|---|---|
| IF | Instruction Fetch | read the instruction from memory (or the instruction cache) |
| RD | Register Read | decode, read the source registers |
| ALU | Arithmetic | add, compare, compute an address or a branch condition |
| MEM | Memory | loads and stores access memory |
| WB | Write Back | write the result into the destination register |

```
cycle        1    2    3    4    5    6    7
instr 1      IF   RD   ALU  MEM  WB
instr 2           IF   RD   ALU  MEM  WB
instr 3                IF   RD   ALU  MEM  WB
instr 4                     IF   RD   ALU  MEM  WB
```

Once the line is full, one instruction finishes per cycle even though each takes five. (This is the textbook model. Real timing also depends on the instruction cache, memory speed and the multiplier; the rules below do not.)

Overlap creates **hazards**: an instruction needs something an earlier one has not produced yet. A CPU can handle a hazard by **interlocking** (stalling the line until the value is ready) or by exposing it to the programmer. MIPS originally stood for "Microprocessor without Interlocked Pipeline Stages": the R3000 exposes two hazards, and you must code around both. It does interlock on one thing, the multiplier (5.4).

### 5.2 The branch delay slot

A branch decides where the next instruction comes from, but by then the instruction behind it has already been fetched:

```
cycle            1    2    3    4    5
beq  ...         IF   RD   ALU  MEM  WB
delay slot            IF   RD   ALU  MEM  WB     already fetched: it runs
target / next              IF   RD   ALU  ...    fetched from the branch's decision
```

MIPS I made that fetched instruction part of the architecture rather than throwing it away. **The instruction after any branch or jump always executes, taken or not.** Chapter 4 told you this; now the rules in full:

- The branch **condition is evaluated from the register values before the slot runs.** If the slot changes a register the branch tests, the branch does not see the change. (Checked in the emulator: `beq $t0,$zero,x` with `li $t0,1` in the slot is still taken when `$t0` was 0.)
- A branch or jump in a delay slot is illegal. armips refuses it (`This instruction can't be in a delay slot`).
- Only the **one** instruction after the branch is in the slot. armips never moves instructions around: what you write is the order that runs. (Contrast GNU `as`, which reorders unless told `.set noreorder`. armips has no `.set` at all and always behaves like `noreorder`. You will see `.set noreorder` in compiler output in Part IV.)
- A **pseudo-instruction** that expands to two real ones is split by this rule. `li $t2, 0x12345` after a branch puts only the `lui` in the slot; the `ori`/`addiu` lands on the fall-through path only (checked with armips). Use single-instruction ops in slots.
- The pseudo-branches `blt`/`bgt`/`bge`/`ble` expand to `slt` + `bne`/`beq`. The `slt` comes *before* the branch and your next line fills the real slot.

### 5.3 The load delay slot

A load gets its data at the end of MEM, but the next instruction needs its operands in ALU, one stage too early:

```
cycle            1    2    3    4    5    6
lw   $t0,0($a0)  IF   RD   ALU  MEM  WB
next                  IF   RD   ALU  MEM  WB      ALU at cycle 4: loaded data not there yet
one later                  IF   RD   ALU  MEM      ALU at cycle 5: data forwarded, OK
```

So the instruction in the **load delay slot** (immediately after the load) reads the register's **old** value; the one after it sees the loaded one. There is no stall and no error, just stale data:

```
    li    $t0, 111
    lw    $t0, 0($a0)       ; memory holds 222
    addu  $t1, $t0, $zero   ; t1 = 111 (old t0)
    addu  $t2, $t0, $zero   ; t2 = 222
```

Rules:

- Results of ordinary ALU instructions *are* forwarded: `addiu` then a use on the next line is fine.
- You can put something useful (not using the loaded register) in the load delay slot, just as in a branch slot.
- armips warns `register t0 may not be available due to load delay` when the line after a load reads the loaded register. The verifier treats warnings as failures in this book. armips only compares *consecutive lines*: it cannot see a use that reaches the load through a branch (below).
- A load in a **branch** delay slot has the instruction at the branch target (or fall-through) as its load delay slot. The first instruction executed after the branch still sees the old value.
- If the instruction in the load delay slot **writes** the loaded register (`lw $t0,...` then `addiu $t0,$zero,5`, or a second `lw $t0`), the later write wins: the first load's value is discarded and never seen (checked in Redux).
- "Old value" is what you *usually* get, not a guarantee: psx-spx notes that an interrupt between the load and the next instruction lets the load finish first. Never write code that relies on the stale value; the slot is for unrelated work.

### 5.4 One new instruction pair: `multu` and `mflo`

The project multiplies. `multu rs, rt` multiplies two registers and puts the 64-bit product in two special registers, **HI** and **LO**. `mflo rd` copies LO into a normal register (the low 32 bits of the product; for factorial you only ever need that, and it wraps modulo 2^32 for free). Chapter 12 covers the family properly.

The multiplier runs in parallel with the pipeline: `multu` starts and the next instructions keep going. `mflo` is the one place the R3000 does interlock: if the result is not ready it stalls until it is. So you can schedule independent work between a `multu` and its `mflo`. (psx-spx: `multu` takes 6 to 13 cycles depending on the size of `rs`; with small operands, up to six instructions in between cost nothing extra.)

One caution for later: the MIPS I architecture says a `mult`/`div` started within two instructions after an `mfhi`/`mflo` gives undefined results, and psx-spx reports a not-yet-understood "don't touch HI/LO for about two cycles" rule on the PS1. Emulators do not model it, and this chapter's verifier does not require the gap (the reference solution's tight loop has none); GCC targeting the R3000 inserts it for you. Chapter 12 returns to it.

### 5.5 Filling delay slots

Rule of thumb: ask, "what instruction must run on **both** paths and does not change what the branch tests?" Three standard sources:

| Source | Idea |
|---|---|
| From above | An instruction before the branch that the branch does not depend on moves down into the slot. |
| From the target | The first instruction of the destination, if executing it on the fall-through path is harmless. Then branch to the instruction after it. |
| Loop bookkeeping | Pointer bumps and counter updates that every iteration needs, whichever way the loop goes. |

A slot you cannot fill is still correct with a `nop`. Never trade correctness for a filled slot.

## 6. Worked example

[`example/main.s`](example/main.s) runs all three cases above and writes five results. Build it (`make` in `example/`; armips prints two load-delay warnings on purpose) and check `results` in the debugger:

| `results[i]` | Case | Value | Why |
|---|---|---|---|
| 0, 1 | load then two uses | 111, 222 | the first user sees the old register |
| 2 | branch slot | 1 | the `addiu` after `beq` ran |
| 3, 4 | load in a branch slot | 111, 222 | the first instruction at the target is its load delay slot |

Step through it in Redux (Chapter 6) and watch `$t1` and `$t2` change.

## 7. Project: "Factorial, Tightly"

Compute `n!` for a list of inputs, twice, in one program: first plainly, then with every delay slot doing real work. Both versions go in `starter/main.s`, between labels the starter declares.

**Data** (the verifier replaces `inputs`; do not edit it):

| Label | Layout |
|---|---|
| `inputs` | `+0x00 count` (1 to 8), then 8 words `n` (0 to 20); the first `count` are used |
| `out_v1` | 8 words: version 1 writes `out_v1[i] = inputs[i]!` for `i < count` |
| `out_v2` | 8 words: version 2 does the same into `out_v2` |

**Overflow.** `12! = 479001600` is the largest factorial that fits in 32 bits. Larger `n` just keeps multiplying and wraps: the result is `n!` modulo 2^32 (for example `13!` gives `1932053504`). `0!` and `1!` are 1. The verifier tests all of these, so the loop must not assume `n >= 2`.

**Structure**

```
main:
fact_v1:  ... fact_v1_end:     version 1
fact_v2:  ... fact_v2_end:     version 2
done:
```

Version 1 falls through into version 2, and `done` follows. Each version sets up its own registers (it must work even if the other never ran), reads `count`, loops over the inputs, and leaves `inputs` unchanged. Leave `out_*[i]` for `i >= count` untouched.

**Version 1: plain.** Correct, straightforward, `nop` in every branch and jump delay slot (and wherever you need a load delay).

**Version 2: tight.** Same results, but **no delay slot holds a `nop`**. Every branch and jump slot holds an instruction that does real work. Fill load delay slots too, where you can.

**What counts as "useful".** A delay-slot instruction is useful if the program would be wrong, or at least different, with a `nop` there. It must be correct on both paths of the branch. These do **not** count: `nop`; a disguised no-op (`move $t0,$t0`, `addiu $t0,$t0,0`, `addu $t0,$t0,$zero`); anything that only writes `$zero`; a dummy instruction on a scratch register nobody reads. The verifier checks this by actually replacing each slot instruction with a `nop` and requiring the results to break (section 8). It cannot judge whether you found the *best* instruction for a slot, only that the slot is working.

**Constraints**

- Each block uses only: `lui ori lw sw addiu addu subu slt sltu slti sltiu mult multu mflo beq bne blez bgtz bltz bgez j nop` (pseudo-instructions that expand to these, like `li la move b bnez`, are fine). No shifts, logic ops or `jal`/`jr`. No lookup tables: the work is real multiplication.
- Branch only inside your own block (its end label is a valid target). A branch may not be the last instruction of a block.
- No armips warnings.
- Keep the labels `main fact_v1 fact_v1_end fact_v2 fact_v2_end done inputs out_v1 out_v2`, in that order.

**Hints**

- Get version 1 right first; version 2 is a transformation of it.
- Count down (`n`, `n-1`, ... 2) so the loop test is cheap, and test `n < 2` once before the loop (`slti`).
- A pointer bump at the end of the outer loop, the `acc = 1` initialisation, and the `mflo` that collects the product are all candidates for delay slots. Check each one is legal on both paths.
- The instruction after a `lw` is also a free slot. Put the input pointer advance there.
- Remember the multiplier runs in parallel: independent loop bookkeeping can sit between `multu` and `mflo`.

**Stretch goals** (in a copy)

- Unroll the multiply loop by two and count again.
- Move `mflo` out of the delay slot and watch your instruction count rise. Where is the best place for it?
- Put a real instruction in a slot that is *wrong* on the other path, and predict the wrong result before running it.

## 8. Verification

```sh
parts/part-02-thinking-like-the-r3000/ch07-the-pipeline-and-delay-slots/verify/verify.sh
```

Checks `starter/` by default; pass a path for a copy, `-v` for build output and emulator log, `--solution` for the reference. The verifier scans your machine code, runs the program with several input sets patched into the executable, then runs variants (version 1 skipped, delay-slot instructions removed one at a time) and reads an instruction counter the probe keeps.

| Check | What it means | If it fails |
|---|---|---|
| `program defines main, both blocks, done, ...` | Labels exist, in order; tables word-aligned. | A label was deleted or moved. |
| `data tables are as shipped` | Outputs start zero, `inputs` unedited. | You pre-filled an output or edited `inputs`. |
| `both blocks use only the allowed instructions` | The message names the offender. | A shift, `jal`/`jr`, logic op or data inside a block. |
| `branches stay inside their own block, and each block has a loop` | Targets, slot inside block, no branch in a slot, a backward branch. | Branch to the other version, or a branch as the block's last instruction. |
| `version 1: a nop in every delay slot` | The baseline is the plain version. | A non-`nop` in a slot of version 1. |
| `version 2: no nop in any delay slot, and no filler that does nothing` | Rejects `nop` and disguised no-ops. | A `nop` or `move $t,$t` in a slot. |
| `version 2 really multiplies` | `mult`/`multu` and `mflo` present. | Table lookup or repeated addition. |
| `armips reports no warnings` | No load-delay warning. | A loaded register used by the next line. |
| `program reaches done` | No hang. | Loop never exits, or a slot instruction broke the counter. |
| `both versions are right for the starter's inputs` | Every word is compared; the message names the first wrong one. | Wrong `0!`/`1!`, off-by-one loop, stale value after a load. |
| `edge cases: 0!, 1!, 2!, 12!, 13!..20!` | The largest exact value and wraparound. | Assuming `n >= 2`, or a loop that overflows differently. |
| `different counts and orders follow the patched data` | `count` 1 to 8, outputs beyond `count` untouched (they start as `0xAAAAAAAA`). | Hard-coded count or writing past it. |
| `version 2 does not depend on version 1` | Version 1 is jumped over and version 2 must still work. | Reusing a register or pointer version 1 set up. |
| `every delay-slot instruction in version 2 is load-bearing` | With version 1 skipped, each slot is replaced with a `nop` in turn; results must break. | The slot holds filler that does nothing. |
| `version 2 executes fewer instructions than version 1` | Probe counts on three input sets. | A slot filled but loop bookkeeping not tightened. |
| `version 2 is genuinely tight` | At most 14 instructions per input plus 6 per multiplication, and enough real multiplies. | A bloated loop or no real multiplication. |
| `input table is left unchanged` | `inputs` same after the run. | Counting down in memory. |

A pass ends with `CHAPTER 07: PASSED (17/17 checks)`. For reference, with the starter's inputs a natural version 1 executes about 450 instructions and a tight version 2 about 250.

## 9. Common pitfalls

- **Using a loaded register on the next line.** You get the old value. armips warns; heed it.
- **A slot instruction that is wrong on the other path.** Hoisting the first instruction of the target into the slot is only safe if it is harmless when the branch is not taken.
- **Changing a register the branch tests, and expecting the branch to notice.** The branch already read it.
- **Multi-instruction pseudo-ops in a slot.** `li`/`la` with a 32-bit value is two instructions; only the first lands in the slot.
- **Assuming armips reorders for you.** It never does. Your order is the execution order.
- **Branching to the original target after copying its first instruction.** When you copy the target's first instruction into the slot, branch to the *second*, or that instruction runs twice.
- **Counting on the load warning for everything.** armips does not see a use that reaches a load through a branch.
- **Forgetting `n < 2`.** `0!` and `1!` must be 1; a loop that starts with `acc * n` gives 0 for `0!`.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- psx-spx, "CPU Specifications" (pipeline, load delay, branch delay, multiply/divide timing): <https://psx-spx.consoledev.net/>
- Hennessy and Patterson, *Computer Organization and Design: MIPS Edition*, the pipeline chapter (hazards and forwarding).
- armips documentation, MIPS section: <https://github.com/Kingcom/armips>
