# Part III: Bare-Metal Graphics in Assembly

**Theme.** Driving the PS1 GPU directly by writing command packets to its hardware ports, with no SDK.

**Part outcome.** You can initialize the display, draw shaded polygons with reusable stack-parameter routines, upload 16- and 24-bit images to VRAM, and animate a double-buffered scene synchronized to VBlank, in pure assembly.

## Chapters

| # | Chapter | You build |
|---|---|---|
| 13 | [The GPU, VRAM, and Command Packets](ch13-the-gpu-vram-and-command-packets/README.md) | `gpu_init`, `gpu_clear`, `gpu_rect`: a 320x240 display cleared to 8 color bars |
| 14 | [Rendering Polygons](ch14-rendering-polygons/README.md) | "Polygon Gallery": flat and Gouraud triangles and quads |
| 15 | [Drawing Subroutines and Stack Parameters](ch15-drawing-subroutines-and-stack-parameters/README.md) | `draw_flat_tri`, `draw_flat_quad`, `draw_gouraud_tri` and a 20-polygon scene from a data table |
| 16 | [Copying Data to VRAM](ch16-copying-data-to-vram/README.md) | `vram_upload`: a 16-bpp image, then a 24-bpp full-screen image |
| 17 | [Part III Capstone: Animation in Assembly](ch17-animation-in-assembly/README.md) | "Bouncing Gem": a Gouraud diamond bounces between two framebuffers, synchronized to VBlank, with a frame-counter bar graph |

## How the part flows

```
ports & packets -> polygons -> reusable routines -> images -> animation
   (Ch 13)         (Ch 14)       (Ch 15)            (Ch 16)    (Ch 17)
```

Chapter 13 builds the foundation: what the GPU is, how VRAM is laid out, and how a command becomes a few words written to a port. Chapter 14 sends the first real drawing packets (triangles and quads, flat and shaded). Chapter 15 turns them into reusable routines whose many vertex arguments travel on the stack (Chapter 10). Chapter 16 moves pixel data from RAM into VRAM, including the 24-bit display mode. Chapter 17 puts it together: polling for vertical blank, two framebuffers swapped once per frame, and a moving shape with a frame counter.

## Before you start

Finish Part II. You will constantly use:

- the O32 calling convention with a fifth argument on the stack (Chapter 10);
- shifts and masks to pack coordinates and colors into words (Chapter 9);
- aligned data and `lw`/`sw` (Chapter 11).

The workflow is unchanged: `source tools/env.sh`, `make` in `starter/`, `verify.sh`.

## Capstone for the part

Chapter 17 is the capstone: the "Bouncing Gem", written entirely in assembly.
