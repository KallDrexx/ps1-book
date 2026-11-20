# Part III: Bare-Metal Graphics in Assembly

**Theme.** Driving the PS1 GPU directly by writing command packets to its hardware ports, with no SDK.

**Part outcome.** You can initialize the display, draw shaded polygons, upload images to VRAM, and animate a scene in pure assembly.

## Chapters

| # | Chapter | You build | Status |
|---|---|---|---|
| 13 | [The GPU, VRAM, and Command Packets](ch13-the-gpu-vram-and-command-packets/README.md) | `gpu_init`, `gpu_clear`, `gpu_rect`: a 320x240 display cleared to 8 colour bars | available |
| 14 | [Rendering Polygons](ch14-rendering-polygons/README.md) | "Polygon Gallery": flat and Gouraud triangles and quads | available |
| 15 | [Drawing Subroutines and Stack Parameters](ch15-drawing-subroutines-and-stack-parameters/README.md) | `draw_flat_tri`, `draw_flat_quad`, `draw_gouraud_tri` and a 20-polygon scene from a data table | available |
| 16 | Copying Data to VRAM | `vram_upload`: a 16-bpp image, then a 24-bpp full-screen image | planned |
| 17 | Part III Capstone: Animation in Assembly | "Bouncing Gem": a Gouraud diamond, double-buffered, synchronised to VBlank | planned |

## How the part flows

```
ports & packets -> polygons -> reusable routines -> images -> animation
   (Ch 13)         (Ch 14)       (Ch 15)            (Ch 16)    (Ch 17)
```

Chapter 13 builds the foundation: what the GPU is, how VRAM is laid out, and how a command becomes a few words written to a port. Chapter 14 sends the first real drawing packets (triangles and quads, flat and shaded). Chapter 15 turns them into reusable routines whose many vertex arguments travel on the stack (Chapter 10). Chapter 16 moves pixel data from RAM into VRAM, including the 24-bit display mode. Chapter 17 puts it together: waiting for vertical blank, two framebuffers, and a moving shape.

## Before you start

Finish Part II. You will constantly use:

- the O32 calling convention with a fifth argument on the stack (Chapter 10);
- shifts and masks to pack coordinates and colours into words (Chapter 9);
- aligned data and `lw`/`sw` (Chapter 11).

The workflow is unchanged: `source tools/env.sh`, `make` in `starter/`, `verify.sh`.

## Capstone for the part

Chapter 17 is the capstone: the "Bouncing Gem", written entirely in assembly.
