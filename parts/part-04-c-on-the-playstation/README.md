# Part IV: C on the PlayStation

**Theme.** Moving from hand-written assembly to C with PSn00bSDK, and learning the SDK's rendering model: double buffering, primitives, and ordering tables.

**Part outcome.** You can structure a multi-file C project that renders depth-sorted 2D scenes and responds to controller input.

## Chapters

| # | Chapter | You build | Status |
|---|---|---|---|
| 18 | [From Assembly to C](ch18-from-assembly-to-c/README.md) | A C program that clears the screen to a colour computed by your Chapter 9 assembly routine, plus an annotated read of the compiler's output | available |
| 19 | Double Buffering with Display and Draw Environments | `display_init()`/`display_swap()`, a colour-cycling background and a moving rectangle | planned |
| 20 | Primitives and Ordering Tables | `ot.c`/`ot.h`: 16 overlapping quads sorted by depth | planned |
| 21 | Working with Multiple Files | The `psxe` engine library (`display`, `ot`, `gfx`) | planned |
| 22 | Controller Input and the BIOS | "Cursor": a sprite moved by the D-pad, with press/release edge detection | planned |

## How the part flows

```
toolchain & ABI -> display envs -> primitives & OT -> modules -> input
    (Ch 18)          (Ch 19)          (Ch 20)          (Ch 21)    (Ch 22)
```

Chapter 18 shows that a C compiler produces the code you already know, and that C and assembly meet at the ABI. Chapter 19 replaces your hand-written display setup with the SDK's display and draw environments and a double-buffered loop. Chapter 20 introduces the GPU's linked-list model: primitives, an ordering table for depth, and DMA. Chapter 21 turns the working code into a reusable library. Chapter 22 reads the controller through the BIOS and SDK.

## Before you start

Finish Part III. You will constantly use:

- the GPU picture from Chapters 13 to 17: VRAM, display and drawing areas, packets, VBlank;
- the O32 calling convention (Chapter 10) and your Chapter 9 `rgb888_to_bgr555`;
- reading disassembly: a debugging habit from Chapter 6 that now applies to compiler output.

The workflow changes slightly: `source tools/env.sh`, `make` in `starter/` (it runs CMake and Ninja), `verify.sh`. Projects are CMake projects built with PSn00bSDK, and a few programs run on a CD image, not just side-loaded.

## Capstone for the part

Chapter 22 ("Cursor") joins the pieces: the engine library, double buffering, an ordering table, and the pad.
