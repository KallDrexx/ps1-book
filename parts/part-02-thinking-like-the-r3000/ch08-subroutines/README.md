# Chapter 8: Subroutines

## 1. Concept

A **subroutine** is code you jump to, run, and return from. `jal` jumps and records where to come back to (in `$ra`); `jr $ra` comes back. A shared agreement about which registers carry arguments, results, and survive the call turns that into a function.

## 2. Why it matters

Every PS1 game is a tree of calls: `main` calls the frame loop, which calls the renderer, which calls a polygon routine thousands of times. Hand-written assembly (GTE macros, inner loops, BIOS calls) must follow the same register conventions as compiler output, or the two cannot call each other. Everything from Chapter 9 on is written as callable routines.

## 3. Learning objectives

After this chapter you can:

- call a routine with `jal` and return with `jr $ra`, and say exactly what `$ra` holds;
- pass arguments in `$a0` to `$a3` and return results in `$v0` and `$v1`;
- sort the registers into caller-saved and callee-saved, and know which you may use freely;
- explain why a routine that calls another routine destroys its own return address;
- call through a register with `jalr`.

## 4. Prerequisites

[Chapter 3](../../part-01-machine-and-language/ch03-registers-loads-stores-arithmetic/README.md) (registers, loads, stores), [Chapter 4](../../part-01-machine-and-language/ch04-control-flow-branches-and-jumps/README.md) (`j`, branches), and [Chapter 7](../ch07-the-pipeline-and-delay-slots/README.md) (delay slots: every call has one, and you will rebuild the factorial loop from Chapter 7).

## 5. Explanation

### 5.1 Calling and returning

| Instruction | Does |
|---|---|
| `jal target` | `$ra = address of the jal + 8`, then jump to `target` |
| `jr rs` | jump to the address in `rs` |
| `jalr rs` | `$ra = address of the jalr + 8`, jump to the address in `rs` (indirect call) |
| `jalr rd, rs` | same, but the return address goes into `rd` |

`jal` is "jump and link": the **link** is the return address. It is `+ 8`, not `+ 4`, because the delay slot belongs to the call (Chapter 7). The slot runs first, then the callee, and on return execution resumes after the slot.

```
caller                          callee
------                          ------
  jal  callee      ----+
  nop  (delay slot)    |  $ra = here (jal + 8)
  next_instruction <-+ |
                     | +--->   callee:
                     |           ... work ...
                     +------     jr  $ra
                                 nop  (delay slot)
```

`jr $ra` is the standard return. Two more facts:

- `jal` encodes a 26-bit word target, so it reaches only within the same 256 MB region. Everything in this book is in one region.
- `jalr` calls a function whose address is in a register: a function pointer, a table of handlers, a BIOS entry. `jalr $t2` is shorthand for `jalr $ra, $t2`.

### 5.2 The calling convention

The convention is the O32 ABI (the one the PS1 compilers use). Chapter 10 covers the rest of it; this chapter needs the register roles.

| Registers | Names | Role | Preserved across a call? |
|---|---|---|---|
| `$2-$3` | `$v0-$v1` | results (`$v0` first; `$v1` for a second word) | no |
| `$4-$7` | `$a0-$a3` | first four arguments | no |
| `$8-$15`, `$24-$25` | `$t0-$t9` | temporaries | no |
| `$16-$23` | `$s0-$s7` | saved registers | **yes** |
| `$28` | `$gp` | global pointer | **yes** |
| `$29` | `$sp` | stack pointer | **yes** |
| `$30` | `$fp` (`$s8`) | frame pointer / ninth saved register | **yes** |
| `$31` | `$ra` | return address | the callee may change it; see 5.4 |
| `$1` | `$at` | assembler temporary (pseudo-instructions use it) | no |
| `$26-$27` | `$k0-$k1` | reserved for the kernel and exception handlers | never touch |

Two roles for "preserved":

- **Caller-saved** (`$v`, `$a`, `$t`, `$at`): the callee may overwrite them. If the caller needs a value after the call, the caller must keep it somewhere safe first.
- **Callee-saved** (`$s0-$s7`, `$gp`, `$sp`, `$fp`): the callee must hand them back unchanged. If it wants to use one, it saves the old value and restores it before returning.

So a leaf routine that sticks to `$t0-$t9`, `$a0-$a3` and `$v0-$v1` has nothing to save. Chapter 10 shows how to save `$s` registers; until then, **do not touch them in a routine**.

The convention is only a promise between pieces of code. The CPU enforces nothing, and nothing warns you when you break it. The verifier checks it for you.

### 5.3 Arguments and results

For `factorial(n)`, the caller puts `n` in `$a0`; the callee leaves `n!` in `$v0`. `sum_array(ptr, len)` takes the address in `$a0` and the count in `$a1`. A routine may freely modify `$a0` and `$a1` (counting `$a1` down and walking `$a0` forward is the normal style).

The delay slot of a `jal` is a natural place to set the last argument, because it runs before the callee's first instruction. One trap: **a `lw` in that slot is too late** (section 9).

### 5.4 Leaf and non-leaf routines

A **leaf** routine calls nobody. A **non-leaf** routine calls another routine. Non-leaf routines have a problem: `jal` overwrites `$ra`.

```
main:    jal outer      $ra = main+8
outer:   jal inner      $ra = outer+8        <- main's return address is gone
         ...
         jr  $ra        goes to outer+8 again: an infinite loop
inner:   ...
         jr  $ra        returns into outer, as it should
```

`outer` must save its incoming `$ra` before calling and restore it before `jr $ra`. The right place for that is the stack, which is Chapter 10. For now there are two stand-ins:

- Copy `$ra` into a callee-saved register. That only moves the problem, because you must not use `$s` registers without saving them yourself.
- Store it in a static word of memory (`sw $ra, saved_ra`). The example below does that. It works only while the routine is never re-entered before it returns: a recursive call (or a call from an interrupt handler) stores its own `$ra` into the same word and the outer return address is lost. One slot per routine cannot hold one return address per active call; a stack can.

Neither is how real code does it. They exist to show the mechanics; Chapter 10 replaces them.

## 6. Worked example

[`example/main.s`](example/main.s) (`make` in `example/`) shows four things:

| `results[i]` | Case | Value |
|---|---|---|
| 0, 1 | `jal where_am_i` returns `$ra`; `after_call` is the address after the delay slot | equal addresses |
| 2 | non-leaf `double_fact(5)` = `2 * factorial(5)`, with `$ra` parked in a static word | `240` |
| 3, 4 | `jalr` through a table of function addresses | `24`, `12` |

Set `BROKEN` to `1` at the top of the file, rebuild, and run it: `double_fact` no longer saves `$ra`, and the program hangs, never reaching `done`. Step it (Chapter 6) and watch `$ra` after the inner `jal`.

## 7. Project: three subroutines and a driver

Turn the Chapter 7 factorial into a real function, add two array routines, and write a driver that calls them. Everything goes in `starter/main.s`.

**Routines** (all leaf, all placed after `done`):

| Routine | Input | Result in `$v0` |
|---|---|---|
| `factorial` | `$a0 = n` (0 to 20) | `n!` modulo 2^32 (`0!` = `1!` = 1) |
| `sum_array` | `$a0` = address of a word array, `$a1` = length | sum of the words, modulo 2^32; `0` when the length is 0 |
| `max_array` | `$a0` = address, `$a1` = length (at least 1) | the largest element, **signed** |

**Rules**

- Return with `jr $ra`. The routines must work from any caller and with any garbage in the temporaries.
- Use only `$v0-$v1`, `$a0-$a3`, `$t0-$t9`. `$s0-$s7`, `$gp`, `$sp` and `$fp` must hold their original values when you return; the simplest way is never to touch them.
- `sum_array` and `max_array` only read the array and must not read past `length` words. Do not read memory when the length is 0.
- No armips warnings.

**Driver.** The starter declares data tables the driver must read (the verifier replaces them):

| Label | Layout |
|---|---|
| `drv_n` | 4 words: factorial inputs |
| `drv_len1`, `drv_arr1` | length (1 to 8) and an 8-word array |
| `drv_len2`, `drv_arr2` | the same for a second array (may be all negative) |
| `results` | 10 words, filled in by the driver |

| `results[i]` | Value |
|---|---|
| 0 to 3 | `factorial(drv_n[0..3])` |
| 4, 5 | `sum_array` and `max_array` of `drv_arr1` with `drv_len1` |
| 6, 7 | the same for `drv_arr2` with `drv_len2` |
| 8 | `sum_array(drv_arr1, 0)` |
| 9 | `max_array(drv_arr1, 1)` |

The driver goes between `main` and `done`. It must call the routines with `jal`, not copy their bodies inline.

**Hints**

- Start from the Chapter 7 loop already in the starter. It reads `$t0` and leaves its answer in `$t1`; two lines connect it to the convention.
- Write `sum_array` first: it is the simplest. Then `max_array`: start with the first element, not 0, or all-negative arrays break.
- For `max`, `slt` is a signed compare; `sltu` is unsigned.
- A loop in the driver may keep its pointer and counter in `$s0-$s2`. They survive the calls only because your routines leave them alone.
- Anything the driver needs after a `jal` must live in a callee-saved register or memory, not in `$t` registers.

**Stretch goals**

- Write a non-leaf `sum_of_factorials(a0 = ptr, a1 = len)` that calls `factorial` for each element. You must keep the pointer, the counter, the running sum and `$ra` alive across calls without the stack. Notice how fast you run out of safe places. That is Chapter 10's motivation.
- Return both the sum and the maximum from one routine, in `$v0` and `$v1`.
- Make the driver call the routines through a table of addresses with `jalr`.

## 8. Verification

```sh
parts/part-02-thinking-like-the-r3000/ch08-subroutines/verify/verify.sh
```

Checks `starter/` by default; pass a path for a copy, `-v` for the log, `--solution` for the reference. The verifier does not trust the driver alone. It **calls your routines directly**: for each call it loads `$a0/$a1`, fills the saved registers with sentinel values and the temporaries with garbage, points `$ra` at a trampoline in unused memory, and jumps to the routine's label. The arguments are random and different each run (the seed is printed on failures). Then it runs the whole program on several patched data sets.

| Check | What it means | If it fails |
|---|---|---|
| `program defines main, done, ...` | Labels exist; routines come after `done`. | A label was deleted, or a routine sits where the driver falls into it. |
| `data tables are as shipped` | `drv_*` unedited, `results` zero. | You edited the tables. |
| `the driver calls the routines with jal/jalr` | `main..done` has a call to each routine. | Inlined code, or a missing call. |
| `armips reports no warnings` | No load-delay warning. | A loaded register used on the next line. |
| `program reaches done` | No hang. | A loop that never ends. |
| `factorial / sum_array / max_array ...` | Many direct calls compared with Python (edge cases and random). | `n < 2`, length 0, negative numbers, wrap-around. The message shows the call and the seed. |
| `every routine returns through $ra` | The trampoline is reached. | A fixed `j` instead of `jr $ra`, or `$ra` overwritten. |
| `callee-saved registers ... unchanged` | Sentinels in `$s0-$s7`, `$gp`, `$sp`, `$fp` survive. | The message names the register you changed. |
| `sum_array and max_array only read their array` | Array and guard words unmodified. | A store into the array, or running past the length. |
| `routines run in linear time` | At most 32 instructions per element (or per `n` for `factorial`) plus 40. | A wrong loop bound or a runaway loop. |
| `driver: results ... shipped data` | `results` has the 10 values. | A wrong index or a missing call. |
| `driver: results follow patched data ...` | Three other data sets; the routines must really be entered (4, 3 and 3 times). | Constants stored instead of computed values. |

A pass ends with `CHAPTER 08: PASSED (14/14 checks)`.

## 9. Common pitfalls

- **A `lw` in the `jal` delay slot.** The callee's first instruction is the load's delay slot and still sees the old register. Checked: with `jal f` / `lw $a0, 0($t5)`, `f` read the previous `$a0`. Load first, call after. `li`, `move` and `addiu` in the slot are fine.
- **Keeping a value in a `$t` register across a call.** The callee may use it. The example's table pointer lives in `$s1` for exactly this reason; with `$t1` it crashed.
- **Using `$s` registers without saving them.** Nothing stops you, and the caller breaks later. The verifier catches it.
- **Forgetting the `nop` after `jr $ra`.** The instruction after it executes before the return, on purpose or not.
- **A non-leaf routine without saving `$ra`.** It returns to itself forever (section 5.4).
- **Assuming `$v0` starts at 0.** Initialise it. The verifier fills it with garbage.
- **Falling into the routines.** If the driver has no `done` loop before them, execution runs straight into `factorial`.
- **`sltu` for `max`.** It treats negative numbers as huge.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- psx-spx, "CPU Specifications" (register names and the `jal`/`jalr` encoding): <https://psx-spx.consoledev.net/>
- *See MIPS Run* (Sweetman), the chapter on the O32 calling convention.
- MIPS O32 ABI summary (register usage and argument passing), the "System V ABI MIPS supplement".
