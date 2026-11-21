# Chapter 18: From Assembly to C

## 1. Concept

A C compiler turns your source into the same MIPS instructions you have been writing by hand. An **SDK** (here PSn00bSDK) is a set of ready-made C functions that talk to the hardware. C and assembly work together because both obey the same calling convention, the O32 ABI of Chapter 10.

## 2. Why it matters

Assembly gave you the machine. C gives you speed of development: structures, loops that read well, and an SDK that already knows the GPU, CD drive and pads. Parts IV to VII are written in C. You will still drop to assembly for a few hot spots, and you will read compiler output whenever something is slow or wrong. This chapter makes that boundary routine.

## 3. Learning objectives

After this chapter you can:

- draw the stack from your C code down to the hardware, and the path from `.c` files to a PSX-EXE;
- build a PSn00bSDK project with CMake;
- say what `crt0`/`_start` and the linker script do before and around `main`;
- generate and read the compiler's assembly (`-S`, `objdump -d`) at `-O0` and `-O2`;
- port an armips routine to GNU assembler (gas) syntax and call it from C;
- write an assembly routine that calls a C function, with a correct stack frame;
- initialise the display with the SDK and clear it to a chosen colour.

## 4. Prerequisites

[Chapter 8](../../part-02-thinking-like-the-r3000/ch08-subroutines/README.md) (`jal`/`jr`), [Chapter 9](../../part-02-thinking-like-the-r3000/ch09-signed-numbers-logic-and-shifts/README.md) (your `rgb888_to_bgr555`), [Chapter 10](../../part-02-thinking-like-the-r3000/ch10-the-stack-and-the-mips-abi/README.md) (the ABI), [Chapter 13](../../part-03-bare-metal-graphics-in-assembly/ch13-the-gpu-vram-and-command-packets/README.md) (display area, fill, GPU colour order).

## 5. Explanation

### 5.1 Why games moved to C

Hand-written assembly is the fastest code per instruction and the slowest to write, debug and change. On the PS1 most of a game is not a hot loop: menus, game rules, level loading, animation state. C describes that in a tenth of the lines, and the compiler handles delay slots and register allocation.

Sony's own libraries (`libgpu`, `libgte`, `libcd`, ...) were written to be called from C. The toolchain that carried them to licensed developers was **PsyQ** (built by SN Systems with Psygnosis, supplied by Sony). Writing a game in C with PsyQ, and assembly only for the hottest routines, became the normal way to work. This book does the same, with an open replacement.

### 5.2 PSn00bSDK and PsyQ

**PSn00bSDK** is a free, open-source SDK for the PS1 (started by Lameguy64). It uses a modern GCC and CMake, and it re-implements many PsyQ function names and behaviours, so PsyQ-era tutorials mostly make sense. It is **not** a copy of PsyQ and not binary compatible.

| PsyQ | PSn00bSDK 0.24 header | Covers |
|---|---|---|
| `libgpu.h` | `psxgpu.h` | GPU, display and draw environments, primitives |
| `libgte.h` | `psxgte.h` | The GTE (Part V) |
| `libetc.h` | `psxetc.h` | Interrupt/DMA callbacks, misc |
| `libapi.h` | `psxapi.h` | BIOS calls |
| `libcd.h` | `psxcd.h` | CD-ROM |
| `libspu.h` | `psxspu.h` | Sound |

Function names such as `ResetGraph`, `PutDispEnv` and `VSync` match PsyQ, which is why PsyQ-era code mostly ports with small edits. [Appendix G](../../../appendices/G-psyq-to-psn00bsdk.md) carries the full name map. In this book, check the headers under `.toolchain/opt/psn00bsdk/include/libpsn00b/` before you use a function: only what exists in 0.24 counts.

### 5.3 The stack of software

```
  your game        main.c  expand.c  rgb555.s
      |
  SDK libraries    libpsxgpu  libpsxapi  libpsxetc  libc ...
      |            (psxgpu.h, ...)   hide ports, DMA, IRQs
  BIOS (ROM)       kernel, interrupt handling, A0/B0/C0 functions
      |
  hardware         GPU  GTE  DMA  CD  pads  SPU
```

You have been at the bottom: your assembly wrote GP0/GP1 ports directly. From now on you mostly stay at the top, and each SDK call is code someone wrote the way you did in Part III. The SDK's `DrawSync(0)` is the wait you polled by hand; `VSync(0)` is Chapter 17's VBlank loop.

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
| gas | GNU assembler, run by `gcc` on `.s` files. Not armips (5.7) |
| `ld` + **linker script** `exe.ld` | Joins object files and library archives. The script says where each section goes: `.text` and `.rodata` from `0x80010000`, then data and `.bss`, with `ENTRY(_start)` |
| `-Wl,-gc-sections` | Throws away functions and data nothing refers to (5.8) |
| `elf2x` | Converts the ELF to a PSX-EXE: the 2 KB header from Chapter 5 and the sections as one image |

The compiler flags the SDK sets (from `lib/libpsn00b/cmake/libpsn00b.cmake`) are the hardware facts you know: `-march=r3000`, `-msoft-float` (no FPU), `-O2` in a Release build (`-Og` in Debug), `-ffreestanding -nostdlib` (no operating system underneath), and `-G8`, which lets small variables sit in a 64 KB window addressed from `$gp`.

### 5.5 Startup: `crt0` and `main`

Chapter 5's header said "start at this address". Here that is not `main` but `_start`, the SDK's startup code (the traditional name for such code is **crt0**, the C runtime zero). The BIOS loads `game.exe` and jumps to the header's PC:

```
BIOS loads game.exe to 0x80010000, jumps to _start
   |
   +- set $gp                (so $gp-relative addressing works)
   +- zero .bss              (C promises globals start as 0)
   +- InitHeap               (memory for malloc)
   +- run static constructors
   +- call main(argc, argv)  <- your code
   +- run destructors, return
```

(Read it yourself: `mipsel-none-elf-objdump -d build/game.elf`, find `<_start>`.) In an assembly program you wrote every one of those steps, or skipped them. Do not assume `main` sits at `0x80010000` either: in the solution's ELF the first function there is `stop_here` (the first one in `main.c`), `main` follows at `0x80010008`, and `_start` lies further up, after the SDK code.

### 5.6 Building with CMake

`CMakeLists.txt` describes the program; CMake generates Ninja build rules from it. The SDK adds one function:

| Piece | Meaning |
|---|---|
| `-DCMAKE_TOOLCHAIN_FILE=.../cmake/sdk.cmake` | Selects the cross-compiler and flags |
| `psn00bsdk_add_executable(game GPREL main.c ...)` | Builds `game.elf`, then `game.exe` and `game.map` |
| `GPREL` | Use the `$gp` window for small variables. `NOGPREL` turns it off |
| `LANGUAGES C ASM` | Lets CMake assemble `.s` files |

`make` in `starter/` runs both CMake steps for you (configure into `build/`, then build) and `make run` starts PCSX-Redux. An assembly file joins the program by being **listed in the executable's sources**. Nothing else is needed.

### 5.7 Reading the compiler's assembly

Ask GCC for assembly instead of an object with `-S`, or disassemble the finished program with `objdump -d`. The chapter's `make asm` compiles `expand.c` twice. The function:

```c
uint32_t expand5(uint32_t c5) { return (c5 << 3) | (c5 >> 2); }
```

**`-O0`** (no optimisation) is a literal translation: 16 instructions in a stack frame.

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
srl   $2,$2,2 ...
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
- **The delay slots are scheduled by GCC.** It surrounds each function with `.set noreorder`, which tells gas "do not touch my order". At `-O2` the `or` after `jr` is real work; at `-O0` it puts `nop` after loads and jumps. That is what you did by hand in Chapter 7.
- **A leaf function needs no frame at `-O2`.** The `.frame $sp,0,$31` line says so: zero bytes. A function that calls another saves `$ra` and keeps its values in `$s` registers (Chapter 10).
- Lines starting with `.` are **directives**, not instructions: `.globl` (export), `.type`, `.size`, `.align`, `.ent`/`.end`, `.frame`/`.mask` (debug hints). Skip them on first read.

### 5.8 Assembly files under gas

A `.s` file in a CMake project is assembled by gas through `gcc`. The same instructions, a different dialect:

| | armips (Parts I to III) | gas (from now on) |
|---|---|---|
| Comments | `;` | `#` |
| File shape | `.psx`, `.create`, `.org`, `.include psxexe.inc`: you build the whole file | None of that: the file is one *piece*. It declares `.text` (code) and the linker places it |
| Symbols | Every label visible | A label is **local** to its file unless you write **`.globl name`**. C can only call exported names |
| Delay slots | You write each `nop` | Same if `.set noreorder`. Without it (the default `.set reorder`) gas **inserts the nops for you** and may fill slots itself (verified: it adds a `nop` after `lw` and after `jr`) |
| `$at` | Macros use it quietly | `.set noat` forbids macros from using `$at`; a `la`/`li` into a register still works |
| `.align n` | `n` bytes | **2^n bytes** (`.align 2` = 4 bytes). Use `.balign 4` to avoid the trap |
| Register names | `$t0`, `$a0`, `$ra` | Same names work; `$8`, `$4`, `$31` are also valid |

The project uses `.set noreorder` in every `.s` file, so everything you learned about delay slots applies unchanged and the code you ported behaves exactly like the original. `.type name, @function` and `.size` are optional hints that make `nm` and `objdump` tidy.

**One more habit.** The linker removes sections nothing references (`-gc-sections`). A function in a `.s` file that no C code calls is simply not in the program, and a global variable nobody reads disappears from the ELF. If a symbol you expect is missing from `nm`, nobody uses it.

### 5.9 The call boundary

```
     C (main.c)                                 assembly (rgb555.s)
 bgr = rgb888_to_bgr555(rgb);  -- a0 = rgb, jal ------> rgb888_to_bgr555:
                                                          ... uses t0, t1 ...
                               <---- v0 = result ------   jr $ra
                                        (delay slot fills v0)
```

Both sides follow Chapter 10, nothing new:

| Rule | Consequence here |
|---|---|
| Arguments in `$a0`-`$a3`; more on the stack above the 16-byte home area | `rgb888_to_bgr555(rgb)`: one argument, in `$a0` |
| Return value in `$v0` (`$v1`) | Your routine already returns in `$v0` |
| Caller-saved: `$t0-$t9`, `$a0-$a3`, `$v0-$v1`, `$at` | A leaf routine can use these freely |
| Callee-saved: `$s0-$s7`, `$gp`, `$sp`, `$fp` | If you use them, save and restore them |
| `$ra` | A routine that calls others must save it first |

C declares the contract with a prototype: `extern uint32_t rgb888_to_bgr555(uint32_t rgb);`. That line is the entire "foreign function interface". Types matter: `uint32_t` is one 32-bit register; the compiler will not warn you if the assembly disagrees. The reverse direction (assembly calling C) is the same rules with a frame: see the example.

### 5.10 The SDK display calls

You need only five calls to show a colour. Single buffer; Chapter 19 does it properly with two.

| Call | Does |
|---|---|
| `ResetGraph(0)` | Initialise the GPU and the SDK's interrupt/DMA machinery (the SDK's version of your `gpu_init` start) |
| `SetDefDispEnv(&disp, x, y, w, h)` | Fill a `DISPENV` (what the TV shows): the VRAM rectangle at (x, y), w by h |
| `SetDefDrawEnv(&draw, x, y, w, h)` | Fill a `DRAWENV` (where drawing goes): the same rectangle as clip area, offset and so on |
| `PutDispEnv(&disp)`, `PutDrawEnv(&draw)` | Send them to the GPU. `PutDrawEnv` queues the draw settings and, with `isbg`, the clear |
| `SetDispMask(1)` | Turn the picture on (it starts off) |

A `DRAWENV` can clear its area: set `draw.isbg = 1` and the colour with `setRGB0(&draw, r, g, b)`, each **0 to 255**. `DrawSync(0)` waits until the GPU finishes. Those are the same GP1(08h)/GP0 `E3h`-`E5h` words and the fill packet of Chapter 13, built by library code.

**Colours again.** `rgb888_to_bgr555` gives a 15-bit value; the GPU's fill takes 8 bits per channel and keeps only the top 5. So the project widens each 5-bit field back to 8 bits (`expand5`). The picture is the original colour, rounded to what 15 bits can show. (`c5 << 3` alone would store the same VRAM pixel, since the fill drops the low 3 bits; `expand5` makes the 8-bit values you pass the true ones, 31 to 255, as in Chapter 9.)

## 6. Worked example

`example/` is assembly calling C: `sum_expanded(c1, c2)` in `callback.s` calls the C function `expand5` twice and adds the results. Study the stack frame (`$ra`, `$s0`, `$s1` saved; 16 bytes of home area) and the delay-slot use. `main.c` uses it to colour the screen.

```sh
cd parts/part-04-c-on-the-playstation/ch18-from-assembly-to-c/example
make run
```

Predict the colour first: `sum_expanded(0, 31)` is 255, `(0, 0)` is 0, `(8, 8)` is 66 + 66. (A purple screen, 255, 0, 132.) Then find `lw $ra` in the epilogue and say why another `lw` sits before `jr $ra`. It is not checked by `verify.sh`.

## 7. Project: Clear with the Assembly

Work in `starter/`. First `make` and `make run`: it builds and shows a black screen. `rgb555.s` is your Chapter 9 `rgb888_to_bgr555`, ported to gas for you. You may replace it with your own port of your solution (the verifier calls it directly).

### 7.1 What you write

| Where | Task |
|---|---|
| `CMakeLists.txt` | Add `rgb555.s` to the executable's sources |
| `expand.c` | `expand5(c5)`: 5-bit channel (0..31) to 8-bit: `c5 << 3 \| c5 >> 2` |
| `main.c` | Compute the clear colour from `clear_rgb888` **through `rgb888_to_bgr555`**, widen each field with `expand5`, set `draw.isbg` and `setRGB0` |
| `annotated.s` | `expand5`'s `-O2` assembly with your comments (below) |

### 7.2 The clear contract

1. `rgb = clear_rgb888` (a `0x00RRGGBB` word, read at run time).
2. `bgr = rgb888_to_bgr555(rgb)`.
3. `r = bgr & 31`, `g = (bgr >> 5) & 31`, `b = (bgr >> 10) & 31`: bit 15 and above are 0.
4. `setRGB0(&draw, expand5(r), expand5(g), expand5(b))`, `draw.isbg = 1`, then the display calls from 5.10, then `DrawSync(0)`, then `stop_here()`.

### 7.3 `annotated.s`

Run `make asm`; it writes `expand.O0.s` and `expand.O2.s`. Copy `expand.O2.s` to `annotated.s`, then annotate:

- one `#` comment per instruction saying what it does in terms of the C source;
- say which register holds the argument and the result, and what the delay slot does;
- one comment per directive you were unsure about (`.globl`, `.frame`, `.set noreorder`, ...);
- a short note comparing it with `expand.O0.s`.

It must keep the compiler's instructions and the `expand5:` label.

### 7.4 Rules

- Keep `main`, `stop_here` (and its `noinline`), `clear_rgb888` and the names `expand5`, `rgb888_to_bgr555`. The verifier finds your program through them.
- Do not change the initial value of `clear_rgb888`. The verifier patches the variable in the executable: a colour written as a constant in C fails.
- Do not re-implement `rgb888_to_bgr555` in C. Use the return value.
- `expand5` takes values 0..31 and no `static` or `inline`.

### 7.5 Hints

- `make` prints the compiler's errors; the linker error `undefined reference to rgb888_to_bgr555` means step one of 7.1.
- `setRGB0` is a macro that assigns three fields; the arguments are plain numbers.
- A black screen after all of this: have you `PutDrawEnv`ed after setting `isbg`?
- `mipsel-none-elf-objdump -d build/game.elf | less`, then look for `<expand5>` and for the `jal` to `rgb888_to_bgr555` in `main`.

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

The harness builds with CMake and the SDK, **calls `expand5` and `rgb888_to_bgr555` directly** (every 5-bit value; edge and random colours; saved registers checked), then runs your program four times: on the shipped colour, on two other values it **patches into `clear_rgb888`**, and once with a trick: when `rgb888_to_bgr555` returns, the verifier overwrites `$v0` with a different colour. Your screen must follow *that*.

| Check | What it means | If it fails |
|---|---|---|
| `the ELF exports main, expand5, ...` | `nm` finds the symbols | `rgb555.s` is not in `CMakeLists.txt`, or the symbol was garbage-collected as unused |
| `rgb888_to_bgr555 comes from an assembly (.s) file ...` | `.globl` and the label are in a `.s` file, not defined in C | Missing `.globl`, or the routine was rewritten in C |
| `clear_rgb888 is as shipped` | The initial value is unedited | You changed it |
| `annotated.s exists, defines expand5, ...` | The label, at least 8 annotation lines, at least 3 instruction lines | File missing, or the compiler's output was replaced by prose |
| `program reaches stop_here() ...` | No crash or hang | Run with `-v` |
| `direct calls return ...` | Leaf routines keep `$s` registers | The routine used an `$s` register |
| `expand5(c) = c<<3 \| c>>2 ...` | All 32 values | Wrong shifts; `expand5` is still the stub |
| `rgb888_to_bgr555 meets the Chapter 9 contract` | The routine's output for 24 inputs | A porting slip in your own `.s` |
| `shipped / patched colour 1 / 2` | The routine was called with the variable's value, and the whole screen is that colour | Hard-coded colour, wrong channel split, `isbg` or `PutDrawEnv` missing |
| `the screen uses the assembly routine's RESULT` | The picture is the colour the *overwritten* `$v0` encodes | You recomputed the colour in C and ignored the return value |

Colours are compared with a tolerance of 10 (15-bit quantisation). A pass ends with `CHAPTER 18: PASSED (12/12 checks)`.

## 9. Common pitfalls

- **`rgb555.s` not in `CMakeLists.txt`.** Then it is never assembled: link error, or the symbol is missing.
- **No `.globl`.** The label is local to the `.s` file; the linker reports `undefined reference`.
- **`.align 4` in gas** means 16 bytes. Use `.balign 4` or `.align 2`.
- **A `.s` file with reordering on** (no `.set noreorder`): gas inserts nops (and may move instructions), so your hand-placed delay slot is wrong.
- **Forgetting the load delay** before `jr $ra` after `lw $ra`.
- **Assuming a symbol survives.** Unreferenced functions and variables are removed by `-gc-sections`; `stop_here` is `noinline` so `-O2` keeps the call.
- **Blue and red swapped.** `rgb888_to_bgr555` puts red in the lowest 5 bits: `bgr & 31` is red.
- **Reading `clear_rgb888` once at compile time.** Declared `volatile` on purpose: read it when `main` runs.
- **Compiling at `-O0` by accident** and wondering why the assembly is long: the SDK's Release build uses `-O2`.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- `.toolchain/opt/psn00bsdk/share/psn00bsdk/template/` and `examples/beginner/hello/`: the SDK's own starting projects.
- `.toolchain/opt/psn00bsdk/include/libpsn00b/psxgpu.h`: every function used here, with its struct definitions.
- GNU as manual, "MIPS-Dependent Features" (`.set`, `.align`); GCC manual, "MIPS Options".
- Chapter 10 (the ABI, again). Chapter 19 next: two buffers and the real draw loop.
