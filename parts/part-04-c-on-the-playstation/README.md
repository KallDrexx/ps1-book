# Part IV: C on the PlayStation

**Theme.** Moving from hand-written assembly to C with PSn00bSDK, and learning the SDK's rendering model: double buffering, primitives, and ordering tables.

**Part outcome.** You can structure a multi-file C project that renders depth-sorted 2D scenes and responds to controller input: a double-buffered frame loop, primitives sorted through an ordering table, a small static library (`psxe`: `display`, `ot`, `gfx`, `input`), and a pad read through the BIOS with press/release edge detection.

## Chapters

| # | Chapter | You build | Status |
|---|---|---|---|
| 18 | [From Assembly to C](ch18-from-assembly-to-c/README.md) | A C program that clears the screen to a colour computed by your Chapter 9 assembly routine, plus an annotated read of the compiler's output | available |
| 19 | [Double Buffering with Display and Draw Environments](ch19-double-buffering/README.md) | `display_init()`/`display_clear()`/`display_swap()`, a colour-cycling background and a moving rectangle | available |
| 20 | [Primitives and Ordering Tables](ch20-primitives-and-ordering-tables/README.md) | `ot.c`/`ot.h`: 16 overlapping quads sorted by depth | available |
| 21 | [Working with Multiple Files](ch21-working-with-multiple-files/README.md) | The `psxe` engine library (`display`, `ot`, `gfx`) | available |
| 22 | [Controller Input and the BIOS](ch22-controller-input-and-the-bios/README.md) | `input.c`/`input.h` and "Cursor": a square moved by the D-pad, with press/release edge detection | available |

## How the part flows

```
toolchain & ABI -> display envs -> primitives & OT -> modules -> input
    (Ch 18)          (Ch 19)          (Ch 20)          (Ch 21)    (Ch 22)
```

Chapter 18 shows that a C compiler produces the code you already know, and that C and assembly meet at the ABI. Chapter 19 replaces your hand-written display setup with the SDK's display and draw environments and a double-buffered loop. Chapter 20 introduces the GPU's linked-list model: primitives, an ordering table for depth, and DMA. Chapter 21 turns the working code into a reusable library. Chapter 22 explains what the BIOS is, reads the controller through its pad driver, and adds the `input` module with `held`/`pressed`/`released` queries.

## Before you start

Finish Part III. You will constantly use:

- the GPU picture from Chapters 13 to 17: VRAM, display and drawing areas, packets, VBlank;
- the O32 calling convention (Chapter 10) and your Chapter 9 `rgb888_to_bgr555`;
- reading disassembly: a debugging habit from Chapter 6 that now applies to compiler output.

The workflow changes slightly: `source tools/env.sh`, `make` in `starter/` (it runs CMake and Ninja), `verify.sh`. Projects are CMake projects built with PSn00bSDK, and a few programs run on a CD image, not just side-loaded.

## The `psxe` library

From Chapter 21 the engine lives in `common/psxe/` (headers in `include/psxe/`, sources in `src/`, a `CMakeLists.txt` defining the `psxe` target). It grows by one module per chapter that needs it, and `common/psxe/` always holds the latest reference:

| Module | Added in | Exports |
|---|---|---|
| `display` | Ch 21 (from Ch 19) | `display_init`, `display_clear`, `display_swap` |
| `ot` | Ch 21 (from Ch 20) | `ot_begin_frame`, `ot_alloc`, `ot_add`, `ot_draw`, `ot_frames` |
| `gfx` | Ch 21 | `gfx_quad_f4` |
| `input` | Ch 22 | `input_init`, `input_update`, `input_held`, `input_pressed`, `input_released` |

Open the reference only after you pass the chapter that writes the module. Chapter folders stay self-contained: each chapter that uses the library ships its own copy in `starter/psxe/` and `solution/psxe/`, taken from `common/psxe/` as it stands at that chapter (Chapter 21's copy has three modules, Chapter 22's four).

## Capstone for the part

Chapter 22 ("Cursor") joins the pieces: the engine library, double buffering, an ordering table, and the pad. It is the part's capstone: a square that moves, changes colour and resets under your control, checked by a verifier that plays scripted button presses.
