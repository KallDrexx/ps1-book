# Chapter 12: RISC vs. CISC, Multiply and Divide

## 1. Concept

The R3000 is a RISC: every instruction is simple, regular and cheap, and anything expensive is left to you. The expensive ones are multiply and divide, so fast PS1 code **replaces them with shifts and adds** and **moves data a word at a time**.

## 2. Why it matters

Every pixel address on the PS1 is `y * 1024 + x` or `y * 320 + x`. Every vertex goes through multiplies; every `memcpy` of a texture or display list moves kilobytes. A 36-cycle divide inside a per-pixel loop, or a byte-at-a-time copy, can cost more than the drawing. Knowing what each instruction costs is how you decide what to write.

## 3. Learning objectives

After this chapter you can:

- explain, fairly, what RISC and CISC trade off, and where MIPS sits;
- use `mult`, `multu`, `div`, `divu`, `mfhi`, `mflo`, `mthi`, `mtlo` and predict HI/LO, including for divide by zero;
- state the R3000A latencies and what a `mfhi`/`mflo` interlock does to your schedule;
- state the `mfhi`/`mflo` to `mult`/`div` spacing rule and write code that respects it;
- turn a constant multiply into shifts and adds (or subtracts), and a divide by a constant into a multiply by a reciprocal;
- write word-at-a-time `memcpy`, `memset` and `strlen` that are correct for any alignment and length.

## 4. Prerequisites

[Chapter 7](../ch07-the-pipeline-and-delay-slots/README.md) (the pipeline, `multu`/`mflo` first seen), [Chapter 8](../ch08-subroutines/README.md) (leaf routines), [Chapter 9](../ch09-signed-numbers-logic-and-shifts/README.md) (shifts and masks), [Chapter 11](../ch11-data-layout-and-memory-alignment/README.md) (alignment).

## 5. Explanation

### 5.1 RISC and CISC

Two design philosophies, both successful.

| | CISC (x86, 68000) | RISC (MIPS, ARM) |
|---|---|---|
| Instructions | Many, variable length (1 to 15 bytes on x86) | Few, fixed length (4 bytes on MIPS I) |
| Memory | Most instructions can read or write memory directly | Only loads and stores touch memory; everything else works on registers (**load/store architecture**) |
| Typical instruction | `add [mem], eax`, `movs`, `rep movsb`: one instruction, several steps | `lw`, `addu`, `sw`: three instructions, one step each |
| Code size | Denser: matters when memory is small and slow | Larger |
| Hardware | Decoding is hard; modern x86 translates to RISC-like micro-ops internally | Simple decode, easy to pipeline (Chapter 7) |
| Registers | Few (8 on 32-bit x86, 8 data + 8 address on 68000) | Many (32 on MIPS) |

Neither is "better". CISC was a good answer when memory was expensive and compilers weak. RISC was a good answer once pipelines and compilers made simple instructions fast. The split has blurred: today's x86 cores are RISC-like inside, and ARM has grown many instructions.

What matters here: on the R3000 **each instruction is one pipeline step, so you can count cost by counting instructions**. The exceptions are the multiplier and divider, which are slow, run beside the pipeline, and live behind their own registers.

### 5.2 The multiplier and divider: HI and LO

`mult`/`multu`/`div`/`divu` do not write a general register. They write the special pair **HI** and **LO**, and you fetch the result later.

| Instruction | Effect |
|---|---|
| `mult rs, rt` | signed 32x32 -> 64 bits: HI:LO = rs * rt |
| `multu rs, rt` | unsigned 32x32 -> 64 bits |
| `div rs, rt` | signed: LO = rs / rt (truncated toward zero), HI = rs % rt (sign of rs) |
| `divu rs, rt` | unsigned: LO = quotient, HI = remainder |
| `mflo rd` / `mfhi rd` | copy LO / HI to a register |
| `mtlo rs` / `mthi rs` | copy a register into LO / HI |

For a 32-bit product you need only `mflo`; it is the same for `mult` and `multu`. `mfhi` gives the upper half (and is what makes the reciprocal trick in 5.6 work). armips has no `mul rd, rs, rt` or `div rd, rs, rt` pseudo-instruction; write the real pair.

### 5.3 What things cost

psx-spx timings, in CPU cycles. (Instruction fetch from RAM and the cache add to every instruction alike; treat the table as relative cost.)

| Operation | Cycles | Notes |
|---|---|---|
| `addu`, `subu`, `and`, `or`, `sll`, `srl`, `sra`, `slt` | 1 | one pipeline step |
| `lw`, `lbu`, ... | 1 + a delay slot | Chapter 7 |
| `multu` | 6, 9 or 13 | depends on the size of `rs` (below) |
| `mult` | 6, 9 or 13 | same, with `rs` read as signed |
| `div`, `divu` | **36** | fixed |
| `mfhi`, `mflo` | 1 + **stall** | waits for the multiplier or divider to finish |

`multu` by `rs`: 6 cycles for `rs` in `0..0x7FF`, 9 for `0x800..0xFFFFF`, 13 for bigger. `mult` is the same on the magnitude: 6 cycles when `rs` is in `-0x800..0x7FF`, 9 when in `-0x100000..0xFFFFF`, 13 otherwise. Put the smaller operand in `rs`.

The unit runs **in parallel**. `mult` issues and the next instructions keep executing. If you reach `mfhi`/`mflo` too early the CPU **interlocks** (stops) until the result is ready, so the answer is always right; you only lose cycles. Useful work placed between the two is free:

```
   multu a0, a1        <- starts, takes 13 cycles
   ...6 independent instructions...   <- run meanwhile
   mflo  v0            <- almost no stall
```

Measured in PCSX-Redux (this chapter's scratch test): a `multu`/`mflo` pair costs about 6, 9 and 13 cycles more than two plain instructions for small, medium and large `rs`, and `divu`/`mflo` about 36 more. Putting six `nop`s between them hides all but one cycle of the 13.

### 5.4 The hazard on the other side

Chapter 7 mentioned it; here is exactly what is known.

- **MIPS I architecture (R2000/R3000 manuals):** if either of the two instructions after an `mfhi`/`mflo` writes the register it read (`mult`, `multu`, `div`, `divu`, or `mthi`/`mtlo`), the value the `mfhi`/`mflo` read is *undefined*.
- **psx-spx** says only: "After accessing the lo/hi registers, there seems to be a strange rule that one should not touch the lo/hi registers in the next 2 cycles or so... not yet understood if/when/how that rule applies...?" It names no instructions and reports no observed corruption.
- **Emulators:** most, including PCSX-Redux, do not model it. Code that breaks the rule still passes in the emulator.

So nobody has pinned down what the PS1 actually needs. This chapter's rule is the **conservative** one, the MIPS I rule: after `mfhi`/`mflo`, let two instructions pass before any `mult`/`div` (or `mthi`/`mtlo`). It costs nothing, and GCC for the R3000 inserts the same gap itself; in assembly it is your job. `verify.sh` checks it on the instructions `udiv10` actually executes, and the reference solution to Chapter 7 follows it too.

### 5.5 Divide by zero and overflow

The R3000 does **not trap** on divide by zero (or on `0x80000000 / -1`). It leaves a defined, odd result. `example/` prints them:

| Operation | HI | LO |
|---|---|---|
| `divu 7 / 0` | 7 (the dividend) | `0xFFFFFFFF` |
| `div 7 / 0` (dividend >= 0) | the dividend | -1 |
| `div -7 / 0` (dividend < 0) | the dividend | +1 |
| `div 0x80000000 / -1` | 0 | `0x80000000` |
| `div -7 / 2` | -1 | -3 (truncates toward zero) |

psx-spx calls the signed divide-by-zero LO "total garbage" and notes that real software must check for zero itself. So must you: there is no exception to catch.

### 5.6 Strength reduction

**Strength reduction** replaces an expensive operation with cheaper ones that give the same result. A shift left by `k` is a multiply by `2^k`; a constant is a sum of powers of two.

```
  x * 320   320 = 256 + 64 = 2^8 + 2^6

  x << 8   =  x * 256
  x << 6   =  x *  64
  ------- addu
            =  x * 320            2 shifts + 1 add: 3 cycles, no HI/LO

  x * 1000  1000 = 1024 - 16 - 8   (3 terms, subtracting is allowed)
  x * -5    = -((x << 2) + x)
```

Rules of thumb:

- Write the constant in binary. Count the 1 bits; a run of ones (`0b0111_1000`) is cheaper as `2^7 - 2^3`.
- Shift-and-add is exact modulo 2^32 for signed and unsigned `x` alike. Overflow behaves exactly like `mult`.
- For a negative constant, build the positive product and negate with `subu rd, $zero, rt`.
- It is only worth it while the shift/add count stays small. With 2 to 4 terms you beat the multiplier (6 to 13 cycles plus a stall) comfortably; at 6 or more, use `multu`.

### 5.7 Dividing by a constant: multiply by the reciprocal

A divide costs 36 cycles. Dividing by a **constant** can use one multiply instead: `x / 10` is `x * (1/10)`, and 1/10 as a fixed-point fraction is a magic number.

```
  x / 10  =  (x * 0xCCCCCCCD) >> 35        unsigned, 32-bit x
             \_____ multu ____/  \ HI >> 3
```

`0xCCCCCCCD` is `ceil(2^35 / 10)`. `multu` leaves the 64-bit product in HI:LO; HI is already the product `>> 32`, so one more `srl` by 3 finishes. The remainder is `x - q * 10`, and `q * 10 = (q << 3) + (q << 1)`. This is exact for **every** 32-bit `x` (checked here on millions of values, including both ends of the range). The compiler does the same transformation for you in C.

**Who may use what in this chapter's project:** `my_memcpy`, `my_memset`, `my_strlen` and the `mulK` routines use no multiplier or divider instructions at all. `udiv10` may use `multu` and `mfhi` (that is the point), but not `div`/`divu`. A shifts-and-adds approximation is also accepted if it stays within the instruction budget.

### 5.8 Word-at-a-time

A byte loop does one byte per iteration, with a pointer bump, a counter and a branch around every byte. A word loop does four bytes with the same overhead. For `memcpy` the byte loop is about 6 instructions per byte, the word loop about 5 per four bytes.

The catch is alignment (Chapter 11): `lw`/`sw` need a multiple of 4. The standard shape:

```
  head:   bytes until the destination is word-aligned   (0 to 3 bytes)
  body:   whole words
  tail:   the remaining 0 to 3 bytes
```

For `memcpy` there are two pointers and only one can be fixed by a byte head. If `src` and `dst` have the same `& 3` (the common case), aligning one aligns both. If they differ, the word path is not possible with plain `lw`/`sw`; this chapter's contract allows a **byte loop for that case** (the `lwl`/`lwr` version is a stretch goal).

Zero-byte test for `strlen`: a 32-bit word `w` contains a zero byte exactly when

```
  (w - 0x01010101) & ~w & 0x80808080   != 0
```

It is exact for every byte value, `0x80` to `0xFF` included (that is what the `& ~w` is for; section 9). An aligned word that contains the terminator lies inside one 4-byte block, so it cannot run past the end of RAM or into another memory region; that is why the contract lets `my_strlen` **read** (never write) up to 3 bytes past the 0.

## 6. Worked example

`example/main.s` runs the multiplier and divider on the cases from 5.5 and writes HI and LO into `table`. Predict each of the eight rows, run it and compare:

```sh
cd parts/part-02-thinking-like-the-r3000/ch12-risc-vs-cisc-multiply-and-divide/example
make run       # then look at `table` in the debugger's memory view (Chapter 6)
```

Rows: `divu 7/0`, `div 7/0`, `div -7/0`, `div 0x80000000/-1`, `div -7/2`, `multu 0xFFFFFFFF * 0xFFFFFFFF`, `mult -1 * -1`, `multu 0x10000 * 0x10000`. It is not checked by `verify.sh`.

## 7. Project

Work in `starter/main.s`. The driver is given. You write eleven routines. All are leaf routines (`$t`, `$a`, `$v` only) and may assume nothing about alignment.

### 7.1 The routines

| Routine | Arguments | Returns |
|---|---|---|
| `my_memcpy` | `$a0` dst, `$a1` src, `$a2` n | `$v0` = dst. Any alignment, any n (0 included). Buffers do not overlap. |
| `my_memset` | `$a0` dst, `$a1` value, `$a2` n | `$v0` = dst. Only the **low 8 bits** of `$a1` count. |
| `my_strlen` | `$a0` s | `$v0` = bytes before the first 0. May **read** up to 3 bytes past the 0. |
| `mul320`, `mul1024`, `mul10`, `mul100`, `mul_m5`, `mul1000`, `mul65537` | `$a0` x | `$v0` = x * K (mod 2^32), K = 320, 1024, 10, 100, -5, 1000, 65537 |
| `udiv10` | `$a0` x (unsigned) | `$v0` = x / 10, `$v1` = x % 10 |

The starter also ships `bytes_memcpy`, `bytes_memset`, `bytes_strlen`: the plain byte loops with the same contracts. They are your yardstick (about 6, 4 and 4 instructions per byte). Do not edit them.

### 7.2 Your steps

1. **The multiplies.** Decompose each constant on paper first (5.6). `mul_m5` and `mul65537` are the odd ones.
2. **`udiv10`** by the reciprocal (5.7). Put `mfhi` at least two instructions before any later `mult`/`div`.
3. **`my_memset`**: build the 32-bit pattern from one byte with two shift-OR steps, then head, words, tail.
4. **`my_memcpy`**: head, words, tail when `src` and `dst` agree mod 4; bytes otherwise.
5. **`my_strlen`**: byte head, the zero-byte test per word, then find the zero in the last word.
6. Run `example/` and compare with 5.5.

### 7.3 Rules

- Keep the starter's labels and their order. Do not edit the driver, the baselines or the data.
- **`my_memcpy`, `my_memset`, `my_strlen` and every `mulK`: none of `mult multu div divu mfhi mflo mthi mtlo`.**
- **`udiv10`: no `div`/`divu`/`mthi`/`mtlo`.** `multu` and `mfhi` are allowed, with a two-instruction gap after `mfhi`/`mflo`.
- Callee-saved registers untouched; write only the bytes the contract names (the verifier puts guard bytes around every buffer).
- Instruction budgets are in section 8.

### 7.4 Hints

- `addu`/`subu` after shifts on different temporaries: you never need to move `$a0`.
- In the word loop put the pointer bump in the branch delay slot (Chapter 7). Test against an *end pointer* so you need no counter.
- Compute the end pointer as `dst + (n & ~3) - 4` and compare before the bump, so the bump can live in the delay slot.
- A head only runs when `n >= 8` (otherwise just do bytes): then it can never use up all of `n`.
- For `strlen`, after the zero-test fires, step the pointer back one word and finish with a byte loop.

### 7.5 Stretch goals

- Unroll the word loop of `my_memcpy` by 4 and count again.
- Make `my_memcpy` use `lwr`/`lwl` for mismatched alignment (Chapter 11). Count against the byte loop.
- `mul_by_const(x, k)` for a runtime `k`: shift-and-add over the bits of `k`.
- Rewrite `udiv10` with no multiplier at all (shift-and-add reciprocal: `q = (x>>1) + (x>>2)`, `q += q>>4`, ...) and add a correction step for the remainder.
- Write `udiv100` or `udiv7` the same way (the magic number for 7 needs a 33-bit trick: look it up).

## 8. Verification

```sh
parts/part-02-thinking-like-the-r3000/ch12-risc-vs-cisc-multiply-and-divide/verify/verify.sh
```

Checks `starter/` by default; pass a path for a copy, `-v` for the log, `--solution` for the reference. Like Chapters 8 to 11, the verifier **calls each routine directly** with sentinels in the `$s` registers, random data (the seed is printed on failure), guard bytes around every buffer, and counts executed instructions.

| Check | What it means | If it fails |
|---|---|---|
| `program defines main, done, every routine ...` | Labels and order. | A label was deleted or moved. |
| `no mult/.../mtlo in the shift-based routines` | Scans the machine code from `my_memcpy` up to `udiv10`. | Message names the instruction and address. |
| `udiv10 does not use div/divu` | The 36-cycle divider is out. | `div`/`divu`/`mthi`/`mtlo` in `udiv10`. |
| `the data is as shipped`, `the driver calls the routines`, `armips reports no warnings` | As in earlier chapters. | |
| `my_memcpy copies ...`, `my_memset fills ...`, `my_strlen measures ...` | Byte-for-byte vs. Python: all 16 source/destination alignment pairs, lengths 0 to 257, bytes `0x01 0x7F 0x80 0xFF`, high garbage in the `memset` value. | The message shows the first wrong byte and the call's alignments. |
| `memcpy/memset write only inside the destination` | Guard bytes and source untouched. | Word loop overrun, head or tail miscount. |
| `the multiply routines equal x * K` | Seven routines, 19 inputs each (0, -1, `0x80000000`, random...). | Wrong decomposition; the message gives x and the values. |
| `udiv10 gives x/10 ...` | 0, 9, 10, `0xFFFFFFFF`, `0xCCCCCCCD`, ... plus 60 random. | The message gives x, expected and actual. |
| `the multiply/divide unit runs only in udiv10 ...` | The same rules on the instructions each call *executes*, so a `multu` reached by a jump counts. | The message names the routine and the instruction. |
| `udiv10 leaves 2 instructions between mfhi/mflo and a following mult/div` | The 5.4 rule on the executed path (branches followed). | A `mult`/`div` within 2 executed instructions after `mfhi`/`mflo`. |
| `every routine returns`, `callee-saved registers ...` | Leaf-routine hygiene. | See Chapter 8. |
| `my_memcpy on 1 KB ... 1/3` | **Fewer than 2 instructions per byte** (the baseline is about 6), for 1024 aligned, 1023 co-aligned at offset 1, 1000 at offset 3. | A byte loop, a `nop` in the loop, or work per word that could be hoisted. |
| `my_memset on 1 KB ... 1/3` | Fewer than 4/3 per byte (baseline 4), same three cases. | As above. |
| `my_strlen on 1000 bytes ... 60%` | Fewer than 2.4 per byte (baseline 4), at offsets 0 and 2. | Too much per-word overhead. |
| `each mulK routine takes at most 8 instructions, udiv10 at most 24` | No loops. | A loop in a multiply. |
| `driver: the results ...`, `the routines are actually entered` | The real program ran and wrote the right values. | Labels or driver edited. |

The budgets only count for correct code, and are fixed numbers (the baselines are checked still to cost what they cost). Mismatched `src`/`dst` alignment is judged on correctness only. Alternative designs are welcome: any structure that is correct and within budget passes. The mul budget rules out a shift-and-add *loop*, and the contract's "read up to 3 bytes past the 0" is not policed (reading further is harmless here, but stay within it).

A pass ends with `CHAPTER 12: PASSED (24/24 checks)`.

## 9. Common pitfalls

- **`mult` where a shift will do.** It works, it is just slower, and in this chapter it is rejected.
- **`mfhi` straight after `mult` in a tight loop, then `mult` again.** Two instructions of gap, always.
- **Forgetting the divide-by-zero case.** There is no exception; you get garbage and keep running.
- **Wrong operand in `rs`.** The multiplier's time depends on `rs`. Put the small value there.
- **`lw` on an unaligned address.** The loop must see an aligned pointer: byte-head first, and decide the case from `(src ^ dst) & 3`.
- **`srl` vs `sra` on a signed value.** Fine for `udiv10`; do not use `srl` to halve a negative number.
- **Counting a `memset` value as 32 bits.** Only the low byte counts; mask it before replicating.
- **A zero-byte test that fails on `0x80`.** Using `(w - 0x01010101) & 0x80808080` alone gives false positives; you need `& ~w` as well.
- **Using `bne` on the pointer *after* the bump** and running one word too far: compare before bumping, or use an end pointer.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- psx-spx, "CPU Specifications": multiply/divide timing, divide by zero, the HI/LO note: <https://psx-spx.consoledev.net/>
- *See MIPS Run* (Sweetman): the chapters on the integer multiply/divide unit and on hazards.
- Hacker's Delight (Warren): chapter 10, integer division by constants (where `0xCCCCCCCD` comes from).
- Patterson and Hennessy, *Computer Organization and Design*: the RISC design principles.
