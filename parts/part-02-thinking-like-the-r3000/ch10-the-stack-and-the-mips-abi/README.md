# Chapter 10: The Stack and the MIPS ABI

## 1. Concept

The **stack** is a region of RAM that grows downward; `$sp` marks its lowest address in use. Each active function call owns a **frame** on it, holding whatever the function must keep across calls: its return address, saved registers, and the stack arguments of the functions it calls. The **ABI** (application binary interface) is the set of rules that makes every function's frame fit every other function's expectations. This book follows the MIPS **O32** ABI, the one the PS1's C compilers use.

## 2. Why it matters

[Chapter 8](../ch08-subroutines/README.md) left you with a problem: a routine that calls another overwrites `$ra`, and a single static word cannot hold one return address per active call. The stack solves that, and with it recursion, nested calls, and every function with more than a few live values. All the C you write from Part IV on compiles to exactly the frames in this chapter.

## 3. Learning objectives

After this chapter you can:

- reserve and release a frame with a prologue and epilogue, keeping `$sp` aligned;
- save and restore `$ra` and the `$s` registers a routine uses;
- say what the caller's 16-byte home area is for, and where arguments 5 and up live;
- write a recursive routine and trace its frames;
- place the stack, static data and (later) the heap in the PS1 memory map, and estimate how deep recursion can go.

## 4. Prerequisites

[Chapter 5](../../part-01-machine-and-language/ch05-anatomy-of-an-executable/README.md) (the PSX-EXE header fields for the initial stack pointer), [Chapter 7](../ch07-the-pipeline-and-delay-slots/README.md) (delay slots; load delay), and [Chapter 8](../ch08-subroutines/README.md) (`jal`, `jr $ra`, caller-saved vs. callee-saved registers). As in Chapter 9, leaf routines use only the `$t`, `$a` and `$v` registers.

## 5. Explanation

### 5.1 The stack is a convention

The R3000 has no push or pop instruction and no hardware stack. `$sp` (register 29) is an ordinary register that, by convention, points at the **lowest address in use**. The stack **grows down**: to make room you subtract from `$sp`, to give it back you add.

```
 allocate 24 bytes:    addiu $sp, $sp, -24
 free them again:      addiu $sp, $sp,  24
```

Memory **below** `$sp` is free. Anything you store there can be overwritten at any moment by the next call (or by an interrupt handler), so **never read back something you left below `$sp`**. Always move `$sp` first, then store.

### 5.2 Where the stack lives

```
 0x80000000 +--------------------------+  (low addresses at the top here)
            | kernel / BIOS data (64KB)|
 0x80010000 +--------------------------+  <- load address of your PSX-EXE
            | code (.text)             |
            | static data, results[]   |  <- fixed size, fixed address
            +--------------------------+  <- end of your program
            | heap (later)      |      |  <- grows toward higher addresses
            |                   v      |
            | free RAM                 |
            |                   ^      |
            | stack             |      |  <- grows toward lower addresses
 0x801FFFF0 +--------------------------+  <- initial $sp
 0x80200000 +--------------------------+  <- top of the 2 MB of RAM
```

| Kind | Where | Lifetime | Size |
|---|---|---|---|
| **Static** | right after your code, at assemble-time addresses | whole program | fixed |
| **Stack** | top of RAM, growing down | one function call | automatic, LIFO |
| **Heap** | after static data, growing up (`malloc`, from Part IV) | until freed | on demand |

Your PSX-EXE header sets `$sp`. The words at `0x30` and `0x34` are the initial SP base and offset; the loader puts their sum in `$sp` before jumping to `main` (Chapter 5). `common/psxexe.inc` supplies `0x801FFFF0`; Chapter 5's hand-written header used `0x801FFF00`. Either is fine.

There is nothing between the stack and your program but unused RAM: **no guard page, no error**. Recursing too deep walks the stack down into your data and code and corrupts them silently. With nearly 2 MB free and a 24-byte frame the limit is over 80,000 levels, but a real program should stay far below that.

### 5.3 The O32 rules

| Rule | Value |
|---|---|
| Arguments 1 to 4 | `$a0`-`$a3` |
| Arguments 5 and up | on the stack, in order, starting at **16**`($sp)` as the callee sees it on entry |
| Results | `$v0` (plus `$v1` for 64-bit values) |
| `$sp` alignment | multiple of **8** at every call. Frame sizes are multiples of 8 |
| Caller-saved | `$t0-$t9`, `$a0-$a3`, `$v0-$v1`, `$at`: gone after any call |
| Callee-saved | `$s0-$s7`, `$gp`, `$fp`, **`$sp`**: hand them back unchanged |
| `$ra` | overwritten by every `jal`. Save it if you call anything |

The least obvious rule is the **home area** (also called the argument spill area): the caller must reserve **16 bytes** at the bottom of its frame, `0..15($sp)` at the call, even if the callee takes fewer than four arguments. The callee may store `$a0`-`$a3` there (to free those registers for its own calls) or use the space for anything else. GCC does so mainly in variadic functions such as `printf`, which spill `$a0`-`$a3` there so that all the arguments form one contiguous array. Two consequences:

- The 16 bytes **your callees** get, `0..15($sp)` after your prologue, are not yours while you call. Put your own saved values at `16($sp)` and up.
- The 16 bytes **your caller** reserved for you, `0..15($sp)` at your entry (`F..F+15($sp)` after your prologue), are yours to overwrite.

### 5.4 A frame

Every non-leaf function builds the same shape. Addresses grow upward in the picture, and the frame size `F` is a multiple of 8:

```
  higher addresses
  +----------------------------------+
  | caller's frame ...               |
  +----------------------------------+
  | outgoing arg 6 (f)               |  <- caller stored it at 20($sp)
  | outgoing arg 5 (e)               |  <- caller stored it at 16($sp)
  | home area for a0..a3 (16 bytes)  |  <- caller's 0($sp)..15($sp); the callee may use it
  +----------------------------------+  <- $sp at the CALLEE's first instruction
  | saved $ra                        |
  | saved $s0, $s1, ...              |
  | (locals, pad to a multiple of 8) |
  | home area for OUR callees  16 B  |  <- 0($sp)..15($sp) after our prologue
  +----------------------------------+  <- $sp = (entry $sp) - F
  lower addresses
```

Reading it from the callee's side: after its prologue (which subtracted `F`), argument 5 is at `F + 16($sp)` and argument 6 at `F + 20($sp)`. A **leaf** function with no frame sees them at `16($sp)` and `20($sp)`.

The prologue and epilogue are mirror images:

| Step | Prologue (entry) | Epilogue (before `jr $ra`) |
|---|---|---|
| 1 | `addiu $sp, $sp, -F` | reload `$ra` |
| 2 | store `$ra` (if you call anything) | reload each `$s` you saved |
| 3 | store each `$s` you will use | `addiu $sp, $sp, F` |

The epilogue must run on **every** return path, base case included. A leaf routine that uses only caller-saved registers needs no frame at all, as in Chapters 8 and 9.

How big is `F`? 16 (home area) + 4 for `$ra` + 4 per saved `$s` register, rounded up to a multiple of 8. `$ra` alone gives 20, rounded to **24**.

Mind the `jal` delay slot. Setting the last argument there with `move` or `addiu` is fine. An `lw` there is a load-delay hazard (Chapter 7): the callee's first instruction would still see the register's old value.

### 5.5 Recursion: a chain of frames

Recursion needs no new idea. Each call gets its own frame, and with it its own saved `$ra` and its own copy of `n`. For `factorial(3)` with a 24-byte frame, starting at `$sp = S`:

```
   main                                    n   saved $ra       $sp
     |  jal factorial(3)                   3   -> main         S - 24
     v
   factorial(3)
     |  jal factorial(2)                   2   -> factorial(3) S - 48
     v
   factorial(2)
     |  jal factorial(1)                   1   -> factorial(2) S - 72
     v
   factorial(1)  base case: v0 = 1, pop frame, return
     ^
   factorial(2)  v0 = 2 * 1 = 2, pop, return
     ^
   factorial(3)  v0 = 3 * 2 = 6, pop, return
     ^
   main  ($sp is back to S)
```

Two values must survive the recursive call: `$ra`, which goes in the frame, and `n`, which goes in `$s0`. But `$s0` belongs to the caller, so the function first saves the old `$s0` in its frame, then uses `$s0` for its own `n`, and restores the old value before it returns. This save, use, restore pattern is why `$s` registers cost the caller nothing: only a callee that needs one pays for it.

`fibonacci` calls itself **twice**, so it must also keep `fib(n-1)` safe while computing `fib(n-2)`. Two `$s` registers (or two frame slots) do it. The calls form a tree, not a chain: the stack is never more than `n` frames deep, but the number of calls grows exponentially with `n`.

### 5.6 What can go wrong

| Symptom | Cause |
|---|---|
| Program loops forever after a return | `$ra` not saved, or not restored |
| Caller's `$s` value changed | used `$s0` without saving and restoring it |
| Stack creeps down each call | an epilogue path that skips `addiu $sp, $sp, F` |
| Right for the base case, wrong once it calls | saved value in the home area (`0..15($sp)`), overwritten by a callee |
| Address errors | `$sp` not a multiple of 4: every `sw`/`lw` through it faults |
| Subtle breakage in C code later | `$sp` a multiple of 4 but not 8: compiled code assumes an 8-byte-aligned `$sp`, for example to find 64-bit (`long long`, `double`) variadic arguments |
| Corrupted data, wild jumps | recursion too deep: the stack met your data |

## 6. Worked example

[`example/main.s`](example/main.s) (`make` in `example/`) shows the stack growing. `trace(4)` calls itself down to `trace(0)`, each call with n > 0 recording its `$sp`, and `args5` reads a fifth argument from the stack.

| `results[i]` | Shows |
|---|---|
| 0 to 3 | `$sp` in `trace(4)`, `trace(3)`, `trace(2)`, `trace(1)`: each 24 bytes lower |
| 4, 5 | `$sp` in `main` before and after the call: identical |
| 6 | `args5(1,2,3,4,5)` = 15, with the fifth argument at `16($sp)` |

Run it, read `results` in the debugger (Chapter 6), and confirm the 24-byte steps. Then step into `trace` and watch `$sp` and the saved `$ra` at `20($sp)` change.

## 7. Project: three ABI-compliant routines

Work in `starter/main.s`. It contains a driver and three stubs that just return.

### 7.1 The routines

| Routine | Input | Result in `$v0` |
|---|---|---|
| `factorial` | `$a0` = n | n! modulo 2^32, with 0! = 1! = 1. **Must call itself.** |
| `fibonacci` | `$a0` = n | fib(n) with fib(0) = 0, fib(1) = 1. **Must call itself, twice** (for n-1 and n-2). |
| `sum6` | `$a0`-`$a3` = a, b, c, d; e at `16($sp)`; f at `20($sp)` | `a + b + c + d + e - f` (the minus keeps e and f distinguishable) |

### 7.2 The driver

The starter's driver already stores `results[0]` to `results[3]`. You add `results[4]`: call `sum6` on the six words at `drv_args`.

| `results[i]` | Value |
|---|---|
| 0, 1 | `factorial(drv_n)`, `factorial(0)` (given) |
| 2, 3 | `fibonacci(drv_k)`, `fibonacci(0)` (given) |
| 4 | `sum6(drv_args)`: `a` to `d` in registers, `e` and `f` on the stack. **You write this.** |

### 7.3 Rules

- Obey O32 completely: `$sp` a multiple of 8, `$s` registers and `$sp` preserved, home area respected.
- The driver is a caller too: it reserves 24 bytes (the 16-byte home area plus two argument words), stores `e` and `f`, calls, and gives the space back. `$sp` at `done` must equal `$sp` at `main`.
- Keep the routines in the starter's order, after `done` and before the data.
- Recursion must be real and plain. `factorial` and `fibonacci` must re-enter **their own label** (`jal` or `jalr`), each call pushing a frame; the verifier counts entries at that label. A loop, a tail call by `j`, or a helper label that recurses is not accepted, and neither is a memoized or pair-returning `fibonacci`: every call with n > 1 must make both recursive calls (the verifier expects at least fib(n) entries).
- Each recursive frame must be 16 to 128 bytes. 24 is the usual minimum; 16 works only if you keep `$ra` in the 16 bytes your caller reserved for you.
- Instruction budget: about 80 instructions per entry of the routine (a frame costs around 10). Plain recursion fits easily.

### 7.4 Hints

- Write the frame diagram first: list what must survive each call, give each a slot at `16($sp)` or above, add the 16-byte home area, round up to a multiple of 8. Use the same `F` in the prologue and in every epilogue.
- `factorial`: only `n` and `$ra` must survive the call; the multiplication needs `n` after the callee returns.
- `fibonacci`: keep `n` (for n-2) and the first result (for the sum) across calls.
- The base case must return **through the epilogue** too.
- `sum6` is a leaf: no frame, no `$ra` to save. Load `e` and `f` straight from `16($sp)` and `20($sp)`. If you ever give it a frame, add its size to both offsets.
- `mflo` stalls until the multiplier finishes (Chapter 7), so the epilogue's loads fit between `multu` and `mflo` for free.

### 7.5 Stretch goals

- `is_even(n)` and `is_odd(n)` as **mutual** recursion.
- A seven-argument `sum7` (three stack arguments) and the matching call.
- Measure the stack: call `factorial(100)` and read the lowest `$sp` in the debugger; compare with 100 frames.
- Provoke an overflow on purpose: remove the base case from a copy of `factorial` and watch what the stack walks into.
- Write an iterative `fibonacci` as well and compare instruction counts for n = 15 with the recursive one.

## 8. Verification

```sh
parts/part-02-thinking-like-the-r3000/ch10-the-stack-and-the-mips-abi/verify/verify.sh
```

Checks `starter/` by default; pass a path for a copy, `-v` for the log, `--solution` for the reference. Like Chapters 8 and 9, the verifier **calls each routine directly**, with an `$sp` of its own, sentinel values in the `$s` registers, garbage in the temporaries, and `$ra` aimed at a return trampoline; the random seed is printed on failure. It also watches the stack: every time `factorial` or `fibonacci` is **re-entered** it records `$sp` and overwrites that call's home area (the bottom 16 bytes of the caller's frame) and the 64 bytes below `$sp`, as a real callee may. Your own incoming home area is yours to use; anything you keep in your callees' home area or below `$sp` is destroyed. The first CPU exception (for example an address error) ends the run and is reported with its code and address.

| Check | What it means | If it fails |
|---|---|---|
| `program defines main, done, ...` | Labels and order. | A label was deleted or moved. |
| `data tables are as shipped` | `drv_*` unedited. | You edited the tables. |
| `... contain a call to themselves` | A `jal` to its own label (or a `jalr`) inside each routine; two in `fibonacci`. | A loop or a helper label was used. |
| `the driver calls all three routines` | `jal` to each from `main`. | `sum6` call missing. |
| `armips reports no warnings` | A clean build. | Usually a loaded register used by the very next instruction. |
| `program reaches done` | The run ends at `done`. | A loop that never ends, or recursion without a base case. |
| `no CPU exception ...` | No address error or wild jump. | Message gives the code, `pc` and bad address: misaligned `$sp`, or a jump through a clobbered `$ra`. |
| `factorial(n) ...`, `fibonacci(n) ...`, `sum6 ...` | Correct results on edge and random inputs (n up to 100; fib(15)). | Message shows the call, expected and actual. Right only for n = 0 and 1 usually means a saved value in the home area. |
| `really recurse` | Re-entries below the caller's `$sp`: about n for factorial, at least fib(n) for fibonacci. | An iterative version. |
| `every call returns through $ra` | The trampoline is reached. | `$ra` not restored. |
| `$sp is identical after every call` | Epilogue undoes prologue. | A return path without the `addiu`. |
| `callee-saved registers unchanged` | `$s0-$s7`, `$gp`, `$fp` intact. | An `$s` register used but not restored. |
| `$sp stays 8-byte aligned` | Every re-entry, and the lowest `$sp` reached. | Frame size 20 or 28 instead of 24 or 32. |
| `frame sizes are sane` | Each recursive frame 16 to 128 bytes. `sum6` uses at most 64. | A frame too small to hold the home area, or far larger than needed. |
| `instruction budget` | At most 80 instructions per entry. | A loop running far too often. |
| `driver: results ...` | All five results, on shipped and three patched data sets. | Wrong index, or `sum6` args misplaced. |
| `driver: sum6 is called with e at 16($sp) ...` | `e`, `f` found at the right stack slots; `$sp` unchanged at `done`. | Wrong offset; frame not released. |
| `driver run: the stack stays inside RAM ...` | Under 4 KB used. | Stack leak. |

A pass ends with `CHAPTER 10: PASSED (21/21 checks)`.

## 9. Common pitfalls

- **Forgetting to save `$ra`** in a routine that calls. It returns to itself forever (Chapter 8).
- **Epilogue only on one path.** The base case returns early and leaves `$sp` one frame lower every time.
- **Storing into the home area.** Offsets `0..15($sp)` belong to your callees. Your saves start at `16($sp)`.
- **Frame size not a multiple of 8.** 20 and 28 look right and misalign `$sp`.
- **Using `$s0` without saving it.** The caller keeps live values there; the verifier fills them with sentinels on purpose.
- **Reading the stack arguments at the wrong offset.** Offsets 16 and 20 are valid at entry. After your own prologue they move up by your frame size.
- **An `lw` in a `jal` delay slot.** The callee's first instruction still sees the register's old value (load delay, Chapter 7).
- **Reading memory below `$sp` after a call.** It no longer holds what you wrote.
- **Unbounded recursion.** No error: the stack silently eats your data and code.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- psx-spx, "CPU Specifications", register names and conventions; "BIOS Memory Map" for the kernel area; "CDROM File Playstation EXE and SYSTEM.CNF" for the initial SP fields: <https://psx-spx.consoledev.net/>
- *See MIPS Run* (Sweetman), the chapter on subroutine linkage and the stack.
- The MIPS O32 ABI document (*System V ABI, MIPS Processor Supplement*), the calling-convention and stack-frame sections.
- PCSX-Redux debugger documentation (stepping and watching `$sp`): <https://pcsx-redux.consoledev.net/>
