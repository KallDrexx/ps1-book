# Chapter 18: From Assembly to C

## 1. Concept

A C compiler turns your source into the same MIPS instructions you have been writing by hand. An **SDK** (here PSn00bSDK) is a set of ready-made C functions that talk to the hardware. C and assembly work together because both obey the same calling convention, the O32 ABI of Chapter 10.

## 2. Why it matters

Assembly taught you the machine. C gives you speed of development: structures, loops that read well, and an SDK that already knows the GPU, CD drive and pads. Parts IV to VII are written in C. You will still drop to assembly for a few hot spots, and you will read compiler output whenever something is slow or wrong. This chapter makes crossing that boundary routine.

## 3. Learning objectives

After this chapter you can:

- draw the software layers from your C code down to the hardware, and the path from `.c` files to a PSX-EXE;
- build a PSn00bSDK project with CMake;
- say what the startup code (`_start`, the crt0) does around `main`, and what the linker script decides;
- generate and read the compiler's assembly (`-S`, `objdump -d`) at `-O0` and `-O2`;
- port an armips routine to GNU assembler (gas) syntax and call it from C;
- write an assembly routine that calls a C function, with a correct stack frame;
- initialize the display with the SDK and clear it to a chosen color.

## 4. Prerequisites

[Chapter 8](../../part-02-thinking-like-the-r3000/ch08-subroutines/README.md) (`jal`/`jr`), [Chapter 9](../../part-02-thinking-like-the-r3000/ch09-signed-numbers-logic-and-shifts/README.md) (your `rgb888_to_bgr555`), [Chapter 10](../../part-02-thinking-like-the-r3000/ch10-the-stack-and-the-mips-abi/README.md) (the ABI), [Chapter 13](../../part-03-bare-metal-graphics-in-assembly/ch13-the-gpu-vram-and-command-packets/README.md) (display area, fill, GPU color order).

## 5. Explanation

### 5.1 Why games moved to C

Hand-written assembly can be the fastest code, and it is the slowest to write, debug and change. Most of a PS1 game is not a hot loop: menus, game rules, level loading, animation state. C describes that in far fewer lines, and the compiler handles delay slots and register allocation.

Sony's own libraries (`libgpu`, `libgte`, `libcd`, ...) were written to be called from C. Licensed developers got them with **PsyQ**, the development kit built by SN Systems and Psygnosis. Writing a game in C with PsyQ, with assembly only for the hottest routines, became the normal way to work. This book does the same with an open replacement.

### 5.2 PSn00bSDK and PsyQ

**PSn00bSDK** is a free, open-source SDK for the PS1 (started by Lameguy64). It uses a modern GCC and CMake, and it re-implements many PsyQ functions under the same names (`ResetGraph`, `PutDispEnv`, `VSync`, ...), so PsyQ-era code mostly ports with small edits. It is **not** a copy of PsyQ and not binary compatible.

| PsyQ | PSn00bSDK 0.24 header | Covers |
|---|---|---|
| `libgpu.h` | `psxgpu.h` | GPU, display and draw environments, primitives |
| `libgte.h` | `psxgte.h` | The GTE (Part V) |
| `libetc.h` | `psxetc.h` | Interrupt/DMA callbacks, misc |
| `libapi.h` | `psxapi.h` | BIOS calls |
| `libcd.h` | `psxcd.h` | CD-ROM |
| `libspu.h` | `psxspu.h` | Sound |

[Appendix G](../../../appendices/G-psyq-to-psn00bsdk.md) has the full name map. Before you use a function, check the headers under `.toolchain/opt/psn00bsdk/include/libpsn00b/`: only what exists in 0.24 counts.

### 5.3 The software layers

```
  your game        main.c  expand.c  rgb555.s
      |
  SDK libraries    libpsxgpu  libpsxapi  libpsxetc  libc ...
      |            (psxgpu.h, ...)   hide ports, DMA, IRQs
  BIOS (ROM)       kernel, interrupt handling, A0/B0/C0 functions
      |
  hardware         GPU  GTE  DMA  CD  pads  SPU
```

You have been at the bottom: your assembly wrote the GP0/GP1 ports directly. From now on you mostly stay at the top, and each SDK call is code someone wrote the way you did in Part III. `DrawSync(0)` replaces the GPU wait you polled by hand; `VSync(0)` replaces Chapter 17's VBlank loop.

### 5.4 From source to PSX-EXE

```
 main.c     --gcc-->  main.c.obj     --+
 expand.c   --gcc-->  expand.c.obj   --+--> ld  --> game.elf --elf2x--> game.exe
 rgb555.s   --gas-->  rgb555.s.obj   --+     ^
                                              |  exe.ld (layout) + libpsxgpu.a, libc.a ...
```

| Piece | What it is |
|---|---|
| `mipsel-none-elf-gcc` | Cross-compiler: runs on your PC, emits R3000 code. `mipsel` = little-endian MIPS, `none` = no operating system, `elf` = output format |
| gas | GNU assembler, run by `gcc` on `.s` files. Not armips (5.8) |
| `ld` + **linker script** `exe.ld` | Joins object files and library archives. The script says where each section goes: `.text` and `.rodata` from `0x80010000`, then data and `.bss`, with `ENTRY(_start)` |
| `-Wl,-gc-sections` | Throws away functions and data nothing refers to (5.8) |
| `elf2x` | Converts the ELF to a PSX-EXE: the 2 KB header from Chapter 5, then the sections as one image |

The compiler flags the SDK sets (in `lib/libpsn00b/cmake/libpsn00b.cmake`) restate hardware facts you know: `-march=r3000`, `-msoft-float` (no FPU), `-ffreestanding -nostdlib` (no operating system underneath). It also sets `-O2` in a Release build (`-Og` in Debug) and `-G8`, which puts variables of 8 bytes or less in a 64 KB window addressed from `$gp`.

### 5.5 Startup: `crt0` and `main`

Chapter 5's header said "start at this address". Here that address is not `main` but `_start`, the SDK's startup code (traditionally called **crt0**, "C runtime zero"). The loader copies `game.exe` into RAM and jumps to the header's PC:

```
game.exe loaded at 0x80010000, jump to _start
   |
   +- set $gp                (so $gp-relative addressing works)
   +- zero .bss              (C promises globals start as 0)
   +- InitHeap               (memory for malloc)
   +- run static constructors
   +- call main(argc, argv)  <- your code
   +- run destructors, return
```

To read it yourself, run `mipsel-none-elf-objdump -d build/game.elf` and find `<_start>` (it sets `$gp`) and `<_start_inner>` (the rest). In an assembly program you wrote each of those steps, or skipped it. Do not assume `main` sits at `0x80010000` either: in the solution's ELF the function there is `stop_here` (the first one in `main.c`), `main` follows at `0x80010008`, and `_start` lies further up, after the SDK code.

### 5.6 Building with CMake

`CMakeLists.txt` describes the program; CMake generates Ninja build rules from it. The SDK adds one function:

| Piece | Meaning |
|---|---|
| `-DCMAKE_TOOLCHAIN_FILE=.../cmake/sdk.cmake` | Selects the cross-compiler and flags |
| `psn00bsdk_add_executable(game GPREL main.c ...)` | Builds `game.elf`, then `game.exe` and `game.map` |
| `GPREL` | Use the `$gp` window for small variables. `NOGPREL` turns it off |
| `LANGUAGES C ASM` | Lets CMake assemble `.s` files |

`make` in `starter/` runs both CMake steps for you (configure into `build/`, then build) and `make run` starts PCSX-Redux. An assembly file joins the program by being **listed in the executable's sources**; nothing else is needed.

### 5.7 Reading the compiler's assembly

Ask GCC for assembly instead of an object file with `-S`, or disassemble the finished program with `objdump -d`. The chapter's `make asm` compiles `expand.c` twice, at `-O0` and at `-O2`. The function:

```c
uint32_t expand5(uint32_t c5) { return (c5 << 3) | (c5 >> 2); }
```

**`-O0`** (no optimization) is a literal translation: 16 instructions and a stack frame. The first ten:

```
addiu $sp,$sp,-8      # make a frame
sw    $fp,4($sp)      # save the frame pointer
move  $fp,$sp
sw    $4,8($fp)       # store the argument to memory...
lw    $2,8($fp)       # ...and load it straight back
nop                   # load delay slot: GCC wrote the nop
sll   $3,$2,3
lw    $2,8($fp)       # again
nop
srl   $2,$2,2
```

**`-O2`**: four instructions, no memory, no frame.

```
sll   $2,$4,3         # v0 = c5 << 3          (a0 = $4 holds the argument)
srl   $4,$4,2         # reuse a0
jr    $31             # return
or    $2,$2,$4        # delay slot: the final OR, so no nop
```

What to notice:

- **GCC writes registers as numbers** (`$2` = `$v0`, `$4` = `$a0`, `$31` = `$ra`). `objdump -d` prints names (`v0`, `a0`, `ra`) and machine words.
- **GCC schedules the delay slots.** It wraps each function body in `.set noreorder`, which tells gas "do not touch my order". At `-O2` the `or` after `jr` is real work; at `-O0` GCC puts a `nop` after `jr` and after each load whose value the next instruction uses. That is what you did by hand in Chapter 7.
- **A leaf function needs no frame at `-O2`.** The `.frame $sp,0,$31` line says so: zero bytes. A function that calls another saves `$ra` and keeps values that must survive the call in `$s` registers (Chapter 10).
- Lines starting with `.` are **directives**, not instructions: `.globl` (export), `.type`, `.size`, `.align`, `.ent`/`.end`, `.frame`/`.mask` (debug hints). Skip them on first read.

### 5.8 Assembly files under gas

A `.s` file in a CMake project is assembled by gas. The instructions are the same; the dialect differs:

| | armips (Parts I to III) | gas (from now on) |
|---|---|---|
| Comments | `;` | `#` |
| File shape | `.psx`, `.create`, `.org`, `.include psxexe.inc`: you build the whole file | None of that: the file is one *piece*. It declares `.text` (code) and the linker places it |
| Symbols | Every label visible | A label is **local** to its file unless you write **`.globl name`**. C can only call exported names |
| Delay slots | You write each `nop` | Same under `.set noreorder`. Under the default, `.set reorder`, gas **manages the slots itself**: it puts a `nop` after every jump or branch and after a load whose value the next instruction uses |
| `$at` | Macros use it quietly | Same by default. After `.set noat`, a macro that needs `$at` is an error; `li` and `la` do not need it and still work |
| `.align n` | `n` bytes | **2^n bytes** (`.align 2` = 4 bytes). Use `.balign 4` to avoid the trap |
| Register names | `$t0`, `$a0`, `$ra` | Same names work; `$8`, `$4`, `$31` are also valid |

This chapter's `.s` files all use `.set noreorder`, so everything you learned about delay slots applies unchanged and ported code behaves exactly like the original. `.type name, @function` and `.size` are optional; they make `nm` and `objdump` output tidy.

**Unused code disappears.** The SDK compiles C with `-ffunction-sections -fdata-sections` (each function and variable in its own section) and links with `-gc-sections`, which removes every section nothing references. A whole `.s` file's `.text` goes the same way if nothing calls into it. If a symbol you expect is missing from `nm`, nothing uses it.

### 5.9 The call boundary

```
     C (main.c)                                 assembly (rgb555.s)
 bgr = rgb888_to_bgr555(rgb);  -- a0 = rgb, jal ------> rgb888_to_bgr555:
                                                          ... uses t0, t1 ...
                               <---- v0 = result ------   jr $ra
                                        (delay slot fills v0)
```

Both sides follow Chapter 10; nothing is new:

| Rule | Consequence here |
|---|---|
| Arguments in `$a0`-`$a3`; more on the stack above the 16-byte home area | `rgb888_to_bgr555(rgb)`: one argument, in `$a0` |
| Return value in `$v0` (`$v1`) | Your routine already returns in `$v0` |
| Caller-saved: `$t0-$t9`, `$a0-$a3`, `$v0-$v1`, `$at` | A leaf routine can use these freely |
| Callee-saved: `$s0-$s7`, `$gp`, `$sp`, `$fp` | If you use them, save and restore them |
| `$ra` | A routine that calls others must save it first |

C declares the contract with a prototype: `extern uint32_t rgb888_to_bgr555(uint32_t rgb);`. That line is the entire interface. The compiler trusts it: nothing checks that the assembly agrees. The reverse direction (assembly calling C) follows the same rules and needs a stack frame: see the worked example.

### 5.10 The SDK display calls

A few calls put a color on screen. This chapter uses a single buffer; Chapter 19 uses two.

| Call | Does |
|---|---|
| `ResetGraph(0)` | Reset the GPU and set up the SDK's interrupt and DMA handling (the SDK's version of your GP1(00h) reset) |
| `SetDefDispEnv(&disp, x, y, w, h)` | Fill a `DISPENV` (what the TV shows): the VRAM rectangle at (x, y), w by h |
| `SetDefDrawEnv(&draw, x, y, w, h)` | Fill a `DRAWENV` (where drawing goes): the same rectangle as drawing area and drawing offset |
| `PutDispEnv(&disp)`, `PutDrawEnv(&draw)` | Send them to the GPU. `PutDrawEnv` queues the drawing settings and, if `isbg` is set, a clear |
| `SetDispMask(1)` | Turn the picture on (it starts off) |

A `DRAWENV` can clear its area: set `draw.isbg = 1` and the color with `setRGB0(&draw, r, g, b)`, each channel **0 to 255**. `DrawSync(0)` waits until the GPU has finished the queued work. Underneath are the GP1(08h) word, the GP0 `E3h`-`E5h` words and the fill packet of Chapter 13, built by library code.

**Colors again.** `rgb888_to_bgr555` returns a 15-bit value, but the GPU's fill takes 8 bits per channel (and keeps only the top 5). So the project widens each 5-bit field back to 8 bits with `expand5`. The picture is the original color, rounded down to what 15 bits can show. (`c5 << 3` alone would store the same VRAM pixel, since the fill drops the low 3 bits; `expand5` passes the true 8-bit values, 31 becoming 255, as in Chapter 9.)

## 6. Worked example

`example/` is assembly calling C: `sum_expanded(c1, c2)` in `callback.s` calls the C function `expand5` twice and adds the results. Study the stack frame (`$ra`, `$s0`, `$s1` saved; 16 bytes of home area) and the use of the delay slots. `main.c` calls it to compute the clear color.

```sh
cd parts/part-04-c-on-the-playstation/ch18-from-assembly-to-c/example
make run
```

Predict the color before you run it. The answer: `sum_expanded(0, 31)` is 255, `(0, 0)` is 0 and `(8, 8)` is 66 + 66, so the screen is pink (255, 0, 132). Then find `lw $ra` in the epilogue and say why another `lw` sits between it and `jr $ra`. The example is not checked by `verify.sh`.

## 7. Project: Clear with the Assembly

Work in `starter/`. First run `make` and `make run`: the starter builds and shows a black screen. `rgb555.s` is Chapter 9's `rgb888_to_bgr555`, ported to gas for you. You may replace it with a port of your own Chapter 9 solution (the verifier calls it directly).

### 7.1 What you write

| Where | Task |
|---|---|
| `CMakeLists.txt` | Add `rgb555.s` to the executable's sources |
| `expand.c` | `expand5(c5)`: widen a 5-bit channel (0..31) to 8 bits: `c5 << 3 \| c5 >> 2` |
| `main.c` | Compute the clear color from `clear_rgb888` **through `rgb888_to_bgr555`**, widen each field with `expand5`, set `draw.isbg` and `setRGB0` |
| `annotated.s` | `expand5`'s `-O2` assembly with your comments (below) |

### 7.2 The clear contract

1. `rgb = clear_rgb888` (a `0x00RRGGBB` word, read at run time).
2. `bgr = rgb888_to_bgr555(rgb)`.
3. `r = bgr & 31`, `g = (bgr >> 5) & 31`, `b = (bgr >> 10) & 31`.
4. `setRGB0(&draw, expand5(r), expand5(g), expand5(b))`, `draw.isbg = 1`, then the display calls from 5.10, then `DrawSync(0)`, then `stop_here()`.

### 7.3 `annotated.s`

Run `make asm`; it writes `expand.O0.s` and `expand.O2.s`. Copy `expand.O2.s` to `annotated.s`, then annotate:

- one `#` comment per instruction saying what it does in terms of the C source;
- say which register holds the argument and the result, and what the delay slot does;
- a comment on each directive you had to look up (`.globl`, `.frame`, `.set noreorder`, ...);
- a short note comparing it with `expand.O0.s`.

Keep the compiler's instructions and the `expand5:` label.

### 7.4 Rules

- Keep `main`, `stop_here` (and its `noinline`), `clear_rgb888` and the names `expand5`, `rgb888_to_bgr555`. The verifier finds your program through them.
- Do not change the initial value of `clear_rgb888`. The verifier patches the variable in the executable: a color written as a constant in C fails.
- Do not re-implement `rgb888_to_bgr555` in C. Use the return value.
- `expand5` only has to handle 0..31. Do not mark it `static` or `inline`: the verifier calls it by name.

### 7.5 Hints

- The linker error `undefined reference to rgb888_to_bgr555` means the first row of 7.1 is not done.
- `setRGB0` is a macro that assigns the three fields `r0`, `g0`, `b0`; its arguments are plain numbers.
- Still a black screen? `isbg` and the color must be set before `PutDrawEnv`.
- To see the call boundary, run `mipsel-none-elf-objdump -d build/game.elf | less` and look for `<expand5>` and for the `jal` to `rgb888_to_bgr555` in `main`.

### 7.6 Stretch goals

Do these in a copy (`cp -r starter stretch`).

- Compile `expand.c` at `-O0`, `-O1`, `-O2`, `-Os` and compare instruction counts.
- Write `expand5` in assembly in a second `.s` file and let `main.c` call it. Does the verifier still pass?
- Use `mipsel-none-elf-objdump -dS` (with `-g`) to interleave C and assembly in `main`.
- Look at `build/game.map` and find where `expand5` and `clear_rgb888` landed.

## 8. Verification

```sh
parts/part-04-c-on-the-playstation/ch18-from-assembly-to-c/verify/verify.sh
```

The harness builds with CMake and the SDK and **calls `expand5` and `rgb888_to_bgr555` directly** (every 5-bit value; edge and random colors; saved registers checked). It then runs your program four times: with the shipped color, with two other values it **patches into `clear_rgb888`**, and once with a trick: when `rgb888_to_bgr555` returns, the verifier overwrites `$v0` with a different color, and your screen must show *that* color.

| Check | What it means | If it fails |
|---|---|---|
| `the ELF exports main, expand5, ...` | `nm` finds the symbols | `rgb555.s` is not in `CMakeLists.txt`, or the symbol was garbage-collected as unused |
| `rgb888_to_bgr555 comes from an assembly (.s) file ...` | `.globl` and the label are in a `.s` file, and no C file defines the function | Missing `.globl`, or the routine was rewritten in C |
| `clear_rgb888 is as shipped` | The initial value is unedited | You changed it |
| `annotated.s exists, defines expand5, ...` | The label, at least 8 annotation lines, at least 3 instruction lines | File missing, or the compiler's output was replaced by prose |
| `program reaches stop_here() ...` | No crash or hang | `stop_here()` removed, or a crash before it. Run with `-v` |
| `direct calls return ...` | Both routines return and preserve the callee-saved registers | The routine used an `$s` register without saving it |
| `expand5(c) = c<<3 \| c>>2 ...` | All 32 values | Wrong shifts; `expand5` is still the stub |
| `rgb888_to_bgr555 meets the Chapter 9 contract` | The routine's result for 24 inputs | A porting slip in your own `.s` |
| `shipped / patched color 1 / 2` | The routine was called with the variable's value, and the whole screen is that color | Hard-coded color, wrong channel split, `isbg` or `PutDrawEnv` missing |
| `the screen uses the assembly routine's RESULT` | The picture is the color the *overwritten* `$v0` encodes | You recomputed the color in C and ignored the return value |

Colors are compared with a tolerance of 10 per channel. A pass ends with `CHAPTER 18: PASSED (12/12 checks)`.

## 9. Common pitfalls

- **`rgb555.s` not in `CMakeLists.txt`.** It is never assembled: a link error if `main` calls the routine, a missing symbol if not.
- **No `.globl`.** The label is local to the `.s` file; the linker reports `undefined reference`.
- **`.align 4` in gas** means 16 bytes. Use `.balign 4` or `.align 2`.
- **A `.s` file without `.set noreorder`.** gas adds its own `nop` after each jump, so your hand-placed delay-slot instruction runs too late or never.
- **`jr $ra` directly after `lw $ra`.** The load delay: `jr` still sees the old `$ra`. Put another instruction between them.
- **Assuming a symbol survives.** `-gc-sections` removes unreferenced functions and variables. Separately, `stop_here` is `noinline` so that `-O2` keeps it as a real call.
- **Blue and red swapped.** `rgb888_to_bgr555` puts red in the lowest 5 bits: `bgr & 31` is red.
- **Writing the color as a constant.** `clear_rgb888` is `volatile` so that `main` reads it at run time, after the verifier has patched it.
- **Annotating the `-O0` file.** `annotated.s` starts from `expand.O2.s`; the SDK's Release build uses `-O2`.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- `.toolchain/opt/psn00bsdk/share/psn00bsdk/template/` and `examples/beginner/hello/`: the SDK's own starting projects.
- `.toolchain/opt/psn00bsdk/include/libpsn00b/psxgpu.h`: every function used here, with its struct definitions.
- GNU as manual, "MIPS-Dependent Features" (`.set`, `.align`); GCC manual, "MIPS Options".
- Next, Chapter 19: two buffers and a real frame loop.
