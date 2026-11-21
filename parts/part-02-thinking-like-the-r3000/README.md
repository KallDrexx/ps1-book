# Part II: Thinking Like the R3000

**Theme.** The quirks and conventions that make MIPS code correct and fast: the pipeline, delay slots, subroutines, signed arithmetic, the stack, alignment, and the RISC philosophy.

**Part outcome.** You write reusable, ABI-compliant assembly routines (leaf and recursive, with stack arguments), lay data out so every access is aligned, and can reason about each instruction's cost: you know when to replace a multiply or divide with shifts and adds, and you copy, fill and scan memory a word at a time.

## Chapters

| # | Chapter | You build |
|---|---|---|
| 7 | [The Pipeline and Delay Slots](ch07-the-pipeline-and-delay-slots/README.md) | "Factorial, Tightly": `n!` plain, then with every delay slot doing work |
| 8 | [Subroutines](ch08-subroutines/README.md) | `factorial`, `sum_array`, `max_array` as callable functions, plus a test driver |
| 9 | [Signed Numbers, Logic, and Bit Shifting](ch09-signed-numbers-logic-and-shifts/README.md) | "Bit Toolkit": `abs`, `sign_extend`, `popcount`, color packing, `swap_endian32` |
| 10 | [The Stack and the MIPS ABI](ch10-the-stack-and-the-mips-abi/README.md) | Recursive `factorial` and `fibonacci`, `sum6` with stack arguments |
| 11 | [Data Layout and Memory Alignment](ch11-data-layout-and-memory-alignment/README.md) | "Vertex Table": aligned `SVECTOR` structs, bounding box, packed copy with `lwl`/`lwr` |
| 12 | [RISC vs. CISC, Multiply and Divide](ch12-risc-vs-cisc-multiply-and-divide/README.md) | Word-at-a-time `memcpy`/`memset`/`strlen`, shift-and-add `mul320` and friends, `udiv10` by reciprocal |

## How the part flows

```
pipeline   ->  functions  ->  bits & signs  ->  the stack  ->  data layout  ->  RISC
 (Ch 7)        (Ch 8)         (Ch 9)            (Ch 10)        (Ch 11)         (Ch 12)
```

Part I taught you to write programs that work. Part II teaches why the machine wants them written a certain way. Chapter 7 explains the quirks you have been working around with `nop`s. Chapter 8 packages code as callable routines, Chapter 9 gives you the tools to manipulate bits and signed values inside them, and Chapter 10 adds the stack, which makes those routines safely nestable. Chapter 11 covers how data must be laid out in memory, and Chapter 12 steps back to the RISC trade-offs behind it all: what each instruction costs, the multiplier and its hazards, and the fast word-at-a-time routines that the rest of the book reuses.

## Before you start

Finish Part I, or at least Chapters 2 to 6: you need loads and stores, branches, and the debugger. Everything runs with the same `source tools/env.sh` and `verify.sh` workflow.

## Capstone for the part

There is no separate capstone. The Part II outcome is the library you accumulate: from Chapter 8 on, your routines are meant to be reused, and later chapters call them (Chapter 12's `my_memcpy`, `my_memset` and the shift-based multiplies are the ones Part III leans on).
