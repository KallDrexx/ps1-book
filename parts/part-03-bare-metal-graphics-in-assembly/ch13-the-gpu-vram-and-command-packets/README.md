# Chapter 13: The GPU, VRAM, and Command Packets

## 1. Concept

The GPU is a separate chip with its own 1 MB of memory, **VRAM**. You control it through two 32-bit ports: **GP0** for drawing and VRAM commands, **GP1** for display control. Every operation is a **packet**: a command byte plus parameters, written to a port one word at a time.

## 2. Why it matters

Everything you see on a PS1 is VRAM contents sent to the TV, and every pixel in VRAM got there through a packet. Chapters 14 to 17 only change which packets you send. Learn the ports, the VRAM layout and the habit of looking packet formats up in psx-spx once, and the rest of Part III is variations.

## 3. Learning objectives

After this chapter you can:

- draw the 1024x512 VRAM map and place a display area and a drawing area in it;
- initialize a 320x240 NTSC 15-bit display with GP1 commands, and set the drawing area and offset with GP0;
- read GPUSTAT and wait for "ready to receive command word";
- send fill-rectangle and monochrome-rectangle packets, and say why they differ (granularity, clipping);
- write a five-argument routine (fifth on the stack) that builds and sends a packet;
- look up a packet format in psx-spx and implement it.

## 4. Prerequisites

[Chapter 1](../../part-01-machine-and-language/ch01-workbench/README.md) (your first GP0 fill), [Chapter 9](../../part-02-thinking-like-the-r3000/ch09-signed-numbers-logic-and-shifts/README.md) (packing colors with shifts), [Chapter 7](../../part-02-thinking-like-the-r3000/ch07-the-pipeline-and-delay-slots/README.md) (the load delay), [Chapter 10](../../part-02-thinking-like-the-r3000/ch10-the-stack-and-the-mips-abi/README.md) (stack arguments).

## 5. Explanation

### 5.1 Two ports

| Address | Write | Read |
|---|---|---|
| `0x1F801810` | **GP0**: drawing commands and VRAM data | **GPUREAD**: data back from the GPU (Chapter 16) |
| `0x1F801814` | **GP1**: display control commands | **GPUSTAT**: the status word |

Both take a **word**: use `sw`. A GP1 word is `cc pppppp`: command number in the top byte, parameter in the low 24 bits. A GP0 word is the first word of a packet (command byte on top, usually a color below) followed by parameter words.

### 5.2 VRAM

VRAM is a 1024 x 512 grid of 16-bit pixels (1 MB). The CPU cannot address it: it is **not** in the memory map. The only way in or out is GP0/GPUREAD. A pixel is `0bMBBBBBGGGGGRRRRR`: 5 bits per color and a mask bit (Chapter 1 explained the rounding).

```
      x=0                 320                       1024
  y=0 +------------------+- - - - - - - - - - - - - -+
      |  display area    |                           |
      |  320x240         |   free: textures,         |
      |  = draw area     |   palettes, 2nd buffer    |
      |                  |                           |
 240  +------------------+                           |
      |  free (a second 320x240 buffer fits here)    |
      |                                              |
 512  +----------------------------------------------+
```

VRAM does not care what is "the screen". Two rectangles and an offset give it meaning:

| Setting | Set by | Meaning |
|---|---|---|
| **Display area** | GP1(05h) start; GP1(06h) to (08h) size | What goes to the TV |
| **Drawing area** | GP0(E3h) top-left, GP0(E4h) bottom-right | The only region drawing commands may change |
| **Drawing offset** | GP0(E5h) | Added to every vertex of a drawing command |

Display and drawing areas are independent. Double buffering (Chapter 17) draws into one while showing the other. This chapter puts both at (0,0).

### 5.3 GP1: display control

| Command | Word | Meaning |
|---|---|---|
| `00h` | `0x00000000` | **Reset** the GPU: display off, FIFO cleared, GP0 E1h-E6h zeroed |
| `03h` | `0x03000000` | Display enable. Bit 0: **0 = on**, 1 = off |
| `05h` | `0x05000000 \| y<<10 \| x` | Display start: top-left of the display area in VRAM |
| `06h` | `0x06000000 \| x2<<12 \| x1` | Horizontal range on the TV, in GPU clocks |
| `07h` | `0x07000000 \| y2<<10 \| y1` | Vertical range on the TV, in scanlines |
| `08h` | `0x08000000 \| mode` | Display mode (below) |

GP1(00h) is the right first word: the BIOS or an earlier program may have left anything behind. It does not clear VRAM, and because it zeroes E3h-E5h, the drawing area afterwards is the single pixel (0,0) until you set it.

**Display mode, GP1(08h).**

| Bits | Meaning | Value we use |
|---|---|---|
| 0-1 | Horizontal resolution: 0 = 256, 1 = 320, 2 = 512, 3 = 640 | 1 |
| 2 | Vertical resolution: 0 = 240, 1 = 480 (480 needs interlace) | 0 |
| 3 | Video mode: 0 = **NTSC**, 1 = **PAL** | 0 |
| 4 | Color depth: 0 = 15-bit, 1 = 24-bit | 0 |
| 5 | Interlace: 0 = off, 1 = on | 0 |
| 6 | Horizontal resolution 368 (overrides bits 0-1) | 0 |
| 7 | Reverse flag (unused here) | 0 |

So 320x240 NTSC, 15-bit, progressive is `0x08000001`.

**The ranges.** TV timing is counted in GPU clocks horizontally and scanlines vertically. The ranges say where on the TV the picture lands, and their lengths set how much of VRAM is shown, starting at the GP1(05h) corner. In 320-wide mode each pixel takes 8 GPU clocks, so 320 columns need `x2 - x1 = 320 x 8 = 2560`; the usual values are `0x260` to `0xC60`. 240 rows need `y2 - y1 = 240`; psx-spx centers NTSC pictures on line `0x88` (136), so lines 16 to 256. A shorter range shows fewer columns or rows; a longer one shows VRAM beyond your picture.

### 5.4 NTSC and PAL

| | NTSC | PAL |
|---|---|---|
| Refresh | about 60 Hz (59.8) | about 50 Hz (49.8) |
| Scanlines per frame (non-interlaced) | 263 | 314 |
| GPU clocks per scanline | 3413 | 3406 |
| Visible lines | up to 240 (about 224 on most TVs) | up to 288 |
| Vertical center line (psx-spx) | `0x88` = 136 | `0xA3` = 163 |
| 240-line vertical range | 16 to 256 | about 43 to 283 |

Packets and VRAM are identical; only the timing, the video-mode bit and the vertical range change. A PAL console runs at 50 Hz, so PAL releases were often slower or letterboxed: a 240-line picture on a 288-line PAL screen leaves black bars. (Figures from psx-spx "GPU Video Timings" and GP1(07h); the PAL range is not tested in this book.) The verifier checks that you chose **NTSC**.

### 5.5 GPUSTAT

Reading `0x1F801814` returns a 32-bit status word. The bits you need now:

| Bits | Meaning |
|---|---|
| 16, 17-18 | Horizontal resolution (368 flag, then the 2-bit code from GP1(08h)) |
| 19 | Vertical resolution (0 = 240, 1 = 480) |
| 20 | Video mode (0 = NTSC, 1 = PAL) |
| 21 | Color depth (0 = 15-bit, 1 = 24-bit) |
| 22 | Vertical interlace |
| 23 | Display disabled (1 = off) |
| **26** | **Ready to receive command word** |
| 27 | Ready to send VRAM to CPU (Chapter 16) |
| 28 | Ready to receive DMA block (Part IV) |

Bits 16 to 22 echo the GP1(08h) mode you programmed (bit 23 echoes GP1(03h)), which makes GPUSTAT a good way to check a GP1(08h) word. The GPU keeps a small FIFO (16 words) of pending commands and draws while the CPU continues, so a program that sends large fills back to back can outrun it. **Before each packet, wait until bit 26 is 1.** Wait once, before the first word: the bit is clear while the GPU expects the rest of a packet, so a wait between words never ends. Emulators such as PCSX-Redux report ready almost all the time, so a missing wait rarely shows there: it appears on hardware. The wait loop is `lw`, a load-delay `nop`, mask, `beqz` back.

### 5.6 GP0: drawing state

Before drawing, tell the GPU where it may draw. Each is a single word:

| Command | Word | Meaning |
|---|---|---|
| `E1h` | `0xE1000000 \| bits` | **Draw mode**: texture page, blending, dither. Bit 10 = 1 allows drawing into the display area; set it |
| `E3h` | `0xE3000000 \| y<<10 \| x` | Drawing area, **top-left** (inclusive) |
| `E4h` | `0xE4000000 \| y<<10 \| x` | Drawing area, **bottom-right** (inclusive: 319, 239 for a 320x240 area) |
| `E5h` | `0xE5000000 \| y<<11 \| x` | Drawing offset (signed 11-bit x and y) added to vertices |

(`E2h`, the texture window, comes with textures.) The corner in E4h is **inclusive**, which makes "320" and "240" classic off-by-ones.

### 5.7 GP0: two rectangles

**Fill rectangle, `02h`.** Three words:

| Word | Meaning |
|---|---|
| 1 | `0x02BBGGRR`: command, then color |
| 2 | `y << 16 \| x`: top-left, in **VRAM** coordinates |
| 3 | `h << 16 \| w`: size |

The fill is a VRAM operation, not a drawing operation. It ignores the drawing area and the drawing offset (the verifier tests the first; PCSX-Redux shows the second). It works in blocks of 16 pixels horizontally: **x is rounded down to a multiple of 16 and w is rounded up to one**. So x = 20, w = 20 paints columns 16 to 47. Heights are exact. It is the fast way to clear a big area, but it cannot draw 40-pixel bars.

**Monochrome rectangle, `60h`.** Also three words, with the same layout:

| Word | Meaning |
|---|---|
| 1 | `0x60BBGGRR` |
| 2 | `y << 16 \| x` (signed 11-bit each, -1024 to 1023; the drawing offset is added) |
| 3 | `h << 16 \| w` |

This is an ordinary drawing command: pixel exact, **clipped to the drawing area**, shifted by the offset. A rectangle completely outside the area draws nothing.

**Which to use?** `320 / 8 = 40`, and 40 is not a multiple of 16, so a fill cannot make 8 equal bars: a fill at x = 40, w = 40 paints columns 32 to 79. You could use unequal bars that fit the granularity (for example four of 48 and four of 32), but the project uses the right tool for each job: one fill clears the screen (320 x 240 is exact), and eight `60h` rectangles draw the bars. Chapter 14 uses the same drawing path for polygons.

**Color order.** In both packets the color is `BBGGRR`: blue in bits 16-23, red in bits 0-7. That is the reverse of the usual `0xRRGGBB`. The routines you write take `0x00RRGGBB`, so you must swap.

### 5.8 Looking packets up

You will not memorize the packets. psx-spx (the community hardware reference, "GPU Rendering Commands" and "GPU Display Control Commands") lists each one as a table of words and bit fields. The routine: find the command byte, list the words, then for each word note the bit fields and what is *rounded or clipped*. Write the packet as a comment above your code first.

## 6. Worked example

`example/main.s` draws four 20x20 boxes with raw packets, using both commands, one pair at x = 8 and one pair at x = 290. It narrows the drawing area to 0..299 so that clipping is visible on screen:

```sh
cd parts/part-03-bare-metal-graphics-in-assembly/ch13-the-gpu-vram-and-command-packets/example
make run
```

Predict which columns each box covers before you run it. The answers: the first fill covers x = 0 to 31 (rounded out), the first `60h` exactly 8 to 27, the second `60h` 290 to 299 (clipped at the drawing area), and the second fill 288 to 319 (rounded out, and not clipped, because the fill ignores the drawing area). It is not checked by `verify.sh`.

## 7. Project: Color Bars

Work in `starter/main.s`. You write three routines and `main`.

### 7.1 The routines

| Routine | Arguments | Does |
|---|---|---|
| `gpu_init` | none | Reset, then a 320x240 NTSC 15-bit non-interlaced display starting at (0,0), ranges as in 5.3; draw mode with bit 10 set; drawing area (0,0)-(319,239); drawing offset (0,0) |
| `gpu_clear` | `$a0` color, `$a1` x, `$a2` y, `$a3` w, **`16($sp)` h** | One fill-rectangle packet |
| `gpu_rect` | same | One `60h` monochrome rectangle packet |

`color` is `0x00RRGGBB`; the top byte is ignored. The routines are leaf routines (only `$t`, `$a`, `$v`), and each waits for GPUSTAT bit 26 before its first GP0 word. Five arguments do not fit in registers: the fifth is on the stack at `16($sp)`, above the 16-byte home area (Chapter 10). The caller stores it there before the `jal`.

### 7.2 `main`

1. `gpu_init`.
2. `gpu_clear` the whole display (0, 0, 320, 240) with the color in `bg_color`.
3. Eight `gpu_rect` calls, one per bar: bar *i* is at x = 40 *i*, y = 24, 40 wide, 192 high, colored by word *i* of `bar_colors`. The border (24 rows above and below) keeps the background color.
4. Fall into `done`.

### 7.3 Your steps

1. Write `gpu_init`. Run the verifier: the transcript checks tell you which word is wrong.
2. Write `gpu_rect`. Hand it one rectangle from `main` and look at the screen.
3. Write `gpu_clear` by reusing the code: the two packets differ only in the command byte.
4. Write `main`'s bar loop. Remember to store the fifth argument before each `jal`: the callee may overwrite it.

### 7.4 Rules

- Keep the starter's labels. Read the colors **from `bar_colors` and `bg_color` in memory**: the verifier patches both tables.
- Do not round `x` or `w` yourself in `gpu_clear`; the hardware does that.
- Only `$t`, `$a`, `$v` in the routines; do not touch `$sp`.

### 7.5 Hints

- Keep the port base in a register: `lui $t0, 0x1F80`, then `0x1810($t0)` is GP0 and `0x1814($t0)` is GP1.
- A load has a delay slot (Chapter 7): a `nop` after reading GPUSTAT.
- Bit 26 is `0x04000000`; `lui` builds that mask in one instruction.
- Color: three `andi`/shift pairs and two `or`s turn `0x00RRGGBB` into `0x00BBGGRR`.
- The two packets differ only in the command byte: a shared tail saves code.

### 7.6 Stretch goals

Do these in a copy of your project (`cp -r starter stretch`): the verifier checks the project exactly as specified above.

- Write `gpu_clear_exact`: a fill for the 16-aligned middle and `60h` rectangles for the edges.
- Make the bars a gradient: 8 shades from `bar_colors[0]` to `bar_colors[7]`, interpolated in code.
- Draw the bars with `02h` only, using widths 48 and 32.
- Switch `gpu_init` to PAL (bit 3, and a vertical range from 5.4) and look at what the picture does.

## 8. Verification

```sh
parts/part-03-bare-metal-graphics-in-assembly/ch13-the-gpu-vram-and-command-packets/verify/verify.sh
```

The verifier **calls `gpu_init`, `gpu_clear` and `gpu_rect` directly** with random arguments and the fifth on the stack (the seed is printed on failure), recording every word that reaches GP0 or GP1 and every VRAM pixel that changes. It then runs the real program on three different color tables and samples the screenshot.

| Check | What it means | If it fails |
|---|---|---|
| `program defines main, done, gpu_init, ...` | Labels exist. | A label was deleted. |
| `armips reports no warnings` | Clean build. | Usually a load delay. |
| `program reaches done ...`, `every direct call returns ...` | No hang, no exception; `$s0-$s7`, `$gp`, `$sp`, `$fp` untouched. | A wait loop that never ends, or a stray `$s` register. |
| `gpu_init: GP1(00h) reset first ...` | Order and parameters of the GP1 words: reset first, display on, start (0,0), range lengths 2560 and 240, mode `0x08000001`. | The message names the word. |
| `gpu_init: draw mode E1h ... E3h/E4h/E5h` | Draw mode bit 10, area (0,0)-(319,239), offset (0,0). | E4h holds 319, 239, not 320, 240. |
| `the display is 320x240, 15 bits per pixel` | The real picture has the right size. | The GP1 range or mode words. |
| `gpu_clear sends one GP0(02h) ...`, `gpu_rect sends ... GP0(60h)` | Exactly three GP0 words (each stored with one `sw`) and nothing else, for random arguments. | Red and blue not swapped; `h` read from the wrong place. |
| `... wait for GPUSTAT bit 26 ...` | At least one read of `0x1F801814` before the first GP0 word. The emulator is always ready, so it cannot tell whether you test the right bit: that part is on you. | No wait loop. |
| `gpu_clear paints the 16-pixel-granular rectangle ...` | VRAM pixels changed = the rounded rectangle, with the right 15-bit color, even outside the drawing area. | The color, or the size. |
| `gpu_rect paints exactly its rectangle, clipped ...` | Exact rectangle, clipped at the drawing area (partly or fully outside). | `gpu_init`'s E3h/E4h. |
| `the program calls gpu_init once, gpu_clear, and gpu_rect exactly 8 times` | `main` does what 7.2 says. | A missing or repeated call in `main`. |
| `shipped colors ...`, `patched color table 1/2` | 8 bars of 40x192 in table order, the border, in each table. | Bars drawn from constants, wrong order, wrong geometry. |
| `the real run sends rectangles through GP0 only` | At least 8 `60h` packets in the real run. | Bars drawn without `gpu_rect`. |

Colors are compared with a tolerance of 10, because VRAM keeps 5 bits per channel. A pass ends with `CHAPTER 13: PASSED (17/17 checks)`.

## 9. Common pitfalls

- **Red and blue swapped.** The GPU word is `BBGGRR`.
- **`h` in the wrong place.** Fifth argument: `16($sp)` at entry, not `$t0`.
- **Forgetting the delay slot** after `lw` of GPUSTAT: you test the old register.
- **A fill wider than you asked.** A fill of width 40 paints 48 pixels. That is the hardware, not a bug in your code: do not round in `gpu_clear`.
- **E4h with 320, 240.** The corner is inclusive: 319, 239.
- **Drawing area unset.** After a reset the area is the single pixel (0,0); `60h` clips to it and draws almost nothing.
- **Display on bit.** GP1(03h) bit 0 = 1 turns the display *off*.
- **Reading the tables as constants.** The verifier patches `bar_colors`.
- **Waiting on the wrong bit.** Bit 26 is for commands; 27 is for VRAM reads; 28 is for DMA.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- psx-spx, "GPU" chapters: Rendering Commands, Display Control Commands, GPUSTAT, VRAM Overview, Video Timings.
- [Chapter 1](../../part-01-machine-and-language/ch01-workbench/README.md), section 5.6, for your first fill.
- Chapter 14 next: the same GP0 port, with vertex packets.
