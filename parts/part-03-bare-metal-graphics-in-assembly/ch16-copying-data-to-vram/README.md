# Chapter 16: Copying Data to VRAM

## 1. Concept

VRAM is not memory-mapped: the CPU cannot store into it. Pixels reach it through GP0, in a **CPU to VRAM transfer** (`A0h`): three header words, then the pixels, two per word.

## 2. Why it matters

Every texture, font, sprite sheet and loading screen a PS1 game shows got into VRAM this way. In Part VI you will load TIM images from the CD-ROM; the last step of loading one is the `A0h` packet you write here. The 24-bit display mode (used by FMV and some title screens) reads the *same* VRAM as 3 bytes per pixel.

## 3. Learning objectives

After this chapter you can:

- send a CPU to VRAM transfer: the three header words and the right number of data words;
- pack pixels two per word and say which half is the left pixel;
- explain what happens when `w*h` is odd;
- compute a 24-bpp line width in 16-bit VRAM units with shifts (`px * 3 / 2`);
- embed a binary image with `.incbin` and read its size and position from a table;
- state the GPUSTAT rules for a transfer: wait before the packet, never inside the data.

## 4. Prerequisites

[Chapter 13](../ch13-the-gpu-vram-and-command-packets/README.md) (GP0/GP1, GPUSTAT bit 26, the 1024x512 VRAM, GP1 `08h`), [Chapter 10](../../part-02-thinking-like-the-r3000/ch10-the-stack-and-the-mips-abi/README.md) and [Chapter 15](../ch15-drawing-subroutines-and-stack-parameters/README.md) (stack arguments, "one wait per packet"), [Chapter 11](../../part-02-thinking-like-the-r3000/ch11-data-layout-and-memory-alignment/README.md) (word alignment), [Chapter 12](../../part-02-thinking-like-the-r3000/ch12-risc-vs-cisc-multiply-and-divide/README.md) (shifts instead of multiplies).

## 5. Explanation

### 5.1 VRAM as 16-bit units

VRAM is 1024 x 512 units of 16 bits, row-major. Unit (x, y) is at byte offset `(y*1024 + x) * 2 = (y << 11) + (x << 1)`. The x, y, w and h of a transfer count **units**, not pixels. In 15-bit mode the two are the same; in 24-bit mode they are not (5.4).

A 15-bit pixel (BGR555) fills one unit:

```
 bit  15   14..10   9..5    4..0
      M     Blue    Green   Red          M = mask bit; keep it 0 for plain pictures
```

### 5.2 GP0 `A0h`: copy rectangle, CPU to VRAM

The packet is three words, then data:

```
 word 1   0xA0000000                  command byte A0h in bits 31..24 (the rest is ignored)
 word 2   y(31..16) | x(15..0)        destination: top-left unit in VRAM
 word 3   h(31..16) | w(15..0)        size in units
 word 4.. pixel data, two units per word: low half = LEFT unit, high half = right
```

Each word goes to GP0 (`0x1F801810`) with `sw`. The data is the rectangle **row by row**, with no gaps between rows; a word may hold the last unit of one row and the first of the next:

```
 RAM (w = 3, h = 2: 6 units = 3 words)           VRAM rectangle at (x, y)
 word 0: [ p1 | p0 ]   <- high half | low half     (x  , y  ) p0  p1  p2
 word 1: [ p3 | p2 ]                               (x  , y+1) p3  p4  p5
 word 2: [ p5 | p4 ]
```

The GPU expects `ceil(w*h / 2)` words. If `w*h` is odd, the last word carries one unit in its low half; the GPU ignores the high half. Send exactly that many words:

| Words sent | Result |
|---|---|
| too few | the GPU keeps waiting for data: your **next packet becomes pixels** |
| too many | the extra words are read as commands |

The source pointer must be word-aligned, because you read it with `lw` (Chapter 11). If `w*h` is odd, the last `lw` reads 4 bytes of which only 2 count; the buffer must have room for them.

**Limits** (psx-spx):

- `x` and `y` are masked to 10 and 9 bits (`x = 1030` lands at 6; PCSX-Redux agrees). A size of 0 means the maximum (1024 or 512); always send `w, h >= 1`.
- **Stay inside VRAM: `x + w <= 1024`, `y + h <= 512`.** psx-spx says a rectangle past an edge wraps to the opposite edge, but the PCSX-Redux build used here did not: a rectangle crossing the right edge was written from x = 0 instead. Edge-crossing behavior is not portable, and nothing in this chapter or its verifier depends on it.
- The transfer is **not** clipped to the drawing area (`E3h`/`E4h`) and ignores the drawing offset; it does obey the mask-bit setting (`E6h`, off after reset).

### 5.3 Waiting: what GPUSTAT says during a transfer

Chapter 15's rule was one wait per packet, before its first word. A transfer shows why. GPUSTAT read in PCSX-Redux at five moments:

| Moment | bit 26 (ready for command word) | bit 28 (ready for DMA block) |
|---|---|---|
| before the packet | 1 | 1 |
| after word 1; after word 3; after 100 data words | **0** | 1 |
| after the last data word | 1 | 1 |

From the first header word to the last data word bit 26 is **0**: the GPU wants parameters or data, not a new command (psx-spx's definition of the bit, Chapter 15). A routine that waits for bit 26 before every data word therefore **hangs after the header**. The rules:

1. Wait for bit 26 **once**, before word 1.
2. Then send the header and all data words back to back, with no polling.

This book cannot test real hardware. The emulator accepts every word at once, so it cannot show whether a real GPU keeps up with an unpaced loop (psx-spx: the GP0 FIFO holds 16 words). Small CPU uploads written this way are common in homebrew; large ones, such as the textures a game loads, normally go by **DMA**, where the GPU's DMA request paces the transfer (the SDK does this for you from Part IV on). Either way, do not poll bit 26 inside the data.

### 5.4 24-bit mode: bytes, not pixels

Bit 4 of the GP1 `08h` display mode word (Chapter 13) selects the **color depth**: 0 = 15-bit, 1 = 24-bit. In 24-bit mode the display reads VRAM as **3 bytes per pixel**, bytes in the order **R, G, B**:

```
 24-bit pixels in VRAM, as bytes (low address first):
   R0 G0 B0 | R1 G1 B1 | R2 G2 B2 | R3 G3 B3 | ...
 the same bytes seen as 16-bit units (little-endian):
   unit 0 = G0:R0    unit 1 = R1:B0    unit 2 = B1:G1    unit 3 = G2:R2 ...
        <-- 3 units hold 2 pixels -->
```

So a pixel is 1.5 units wide. A 320-pixel line takes **480 units**, and the whole 320x240 picture is a 480 x 240 rectangle of VRAM:

```
 VRAM (units)    0                       480                    1024
               0 +-----------------------+---------------------+
                 | 320x240 pixels shown  |                     |
                 | in 24-bit mode        |  free               |
                 | (480 x 240 units)     |                     |
             240 +-----------------------+                     |
                 |                                             |
             512 +---------------------------------------------+
```

The transfer knows nothing about color depth: you send an `A0h` rectangle with `w = 480`, `h = 240` of raw bytes. The width in units is `px * 3 / 2 = px + (px >> 1)`, a shift and an add (Chapter 12). An odd pixel count is not a whole number of units, so keep pixel x offsets and widths even.

**Byte order.** psx-spx gives a 24-bit pixel as red in bits 0-7, green 8-15, blue 16-23; little-endian, that puts red at the lowest address. This chapter's verifier confirms it in PCSX-Redux: it uploads random R, G, B bytes and compares the 24-bit screenshot with them pixel by pixel. The 15-bit format also has red lowest (bits 4..0 of a unit), so both formats are R, G, B from the low end.

### 5.5 `.incbin`: an image as bytes in your program

The armips directive `.incbin "img16.bin"` copies a file's bytes into the output at that point. The starter's `Makefile` stages every `*.bin` next to `main.s` before it runs armips, so the bare file name is enough. Give the data a label, and put `.align 4` before it so that the label is word-aligned:

```
 .align 4
 img16:  .incbin "img16.bin"     ; 96*64*2 = 12288 bytes of BGR555
```

Both images are generated by `tools/assets/ch16_images.py` and checked in. Each has four different corner markers and a letter "F", so that a flip, a shift or a swapped channel is visible.

## 6. Worked example

`example/main.s` computes a 16x16 checkerboard in a loop and sends it straight to GP0 as one `A0h` packet (header, then 128 data words) to the middle of the screen. Read the loop and predict the picture, then run:

```sh
cd parts/part-03-bare-metal-graphics-in-assembly/ch16-copying-data-to-vram/example
make run
```

You should see a white and red checkerboard of 4 x 4 cells, each 4 x 4 pixels, on black. It is not checked by `verify.sh`.

## 7. Project: Picture Show

Work in `starter/main.s`. `gpu_init`, `gpu_clear`, `gpu_wait`, the data table and the two images are given. You write two routines and `main`. The program has two modes: the data word `mode` selects **part 1** (`0`) or **part 2** (`1`). Edit it to see part 2; the verifier patches it.

### 7.1 `vram_upload(ptr, x, y, w, h)`

Arguments: `$a0` ptr, `$a1` x, `$a2` y, `$a3` w, **`h` at `16($sp)`** (Chapters 10 and 15). Positions and sizes are in 16-bit units, `w, h >= 1`, `x + w <= 1024`, `y + h <= 512`. It must:

1. wait for GPUSTAT bit 26 **once**, then send `0xA0000000`, `(y << 16) | x`, `(h << 16) | w`;
2. send exactly `(w*h + 1) / 2` words read from `ptr` (word-aligned, row-major, two units per word), with **no polling** between them;
3. write nothing to GP1, and return with `$sp`, `$s0`-`$s7`, `$gp` and `$fp` unchanged.

For `w*h`, `mult`/`mflo` is fine (Chapter 12).

### 7.2 `bpp24_halfwords(px)`

Return `px * 3 / 2` in `$v0` for even `px`, using shifts and adds only (a static check bans `mult` and `div`). `bpp24_halfwords(320)` is 480.

### 7.3 `main`, part 1 (`mode = 0`)

Call `gpu_init`; `gpu_clear` the whole 320x240 area with `BG_COLOR` (`0x303038`); upload the 15-bit picture `img16` to `(img16_x, img16_y)` with size `img16_w` x `img16_h`. Read all four from the data table: the verifier patches them, and the pixels too.

### 7.4 `main`, part 2 (`mode = 1`)

Call `gpu_init`; write `0x08000011` to GP1 (display mode: 320 wide, 240 high, NTSC, **24-bit**); compute the line width in units with `bpp24_halfwords(img24_w)`; upload `img24` (`img24_h` rows) to `(0, 0)` with one `vram_upload`. No background fill is needed: the picture covers the screen.

### 7.5 Hints

- Put the three header words and the data loop in the same routine; the loop is `lw`, `addiu` pointer, `sw`, count down.
- Odd `w*h`: round the word count **up**.
- `main` needs a frame of at least 32 bytes: `h` goes to `16($sp)` before every `jal vram_upload`.
- A garbled picture that covers only the left two thirds of the screen in part 2 means `w = 320` units instead of 480.

### 7.6 Stretch goals

- **Readback.** `GP0 C0h` (copy rectangle VRAM to CPU) takes the same three words; then you read the pixels from GPUREAD (a read of the GP0 address) while GPUSTAT bit 27 is set. Write `vram_download` and compare with what you sent. (Not checked; see psx-spx.)
- Upload the 24-bit picture 100 pixels to the right (what is `x` in units?) and move the display start (GP1 `05h`) to match.
- Draw a polygon (Chapter 14) on top of the 15-bit picture.

## 8. Verification

```sh
parts/part-03-bare-metal-graphics-in-assembly/ch16-copying-data-to-vram/verify/verify.sh        # your starter/
parts/part-03-bare-metal-graphics-in-assembly/ch16-copying-data-to-vram/verify/verify.sh -v     # + build output and emulator log
```

The verifier calls your routines directly with its own arguments (random pixel buffers; odd widths and pixel counts; rectangles that touch the right and bottom edges, such as 64x8 at `(960, 504)`; a 1023x3 rectangle) and compares VRAM with the buffer. Then it runs the whole program in both modes, on the shipped images and on patched ones (random pixels; in part 1 another size and position).

| Check | Failing means |
|---|---|
| one packet: `A0h`, destination, size, `ceil(w*h/2)` data words | wrong header word (`h` read from the wrong offset?), or too few or too many data words (odd counts) |
| rectangle equals the buffer | data not read from `ptr` in order, or words skipped |
| nothing outside changes | wrong destination, extra words |
| waits before the first word | no GPUSTAT read before the packet |
| "did not return" | a bit-26 poll inside the data phase, or a loop whose counter is wrong |
| ABI | `$s` registers, `$gp`, `$fp` or `$sp` changed |
| `bpp24_halfwords` | wrong formula; `mult` used |
| part 1 VRAM and screen | position or size hard-coded instead of read from the table; picture flipped |
| part 2 GP1 `08h` | bit 4 not set, or other bits changed |
| part 2 packet and VRAM | width 320 instead of 480 units; `bpp24_halfwords` not called (480 hard-coded); more than one upload |
| part 2 screenshot | wrong width in units, or the display is not in 24-bit mode |

## 9. Common pitfalls

- **Waiting per data word.** Bit 26 is 0 until the last data word is sent: the program hangs.
- **Width in pixels in 24-bit mode.** A 320-unit upload covers two thirds of each line and garbles the picture.
- **Rounding the word count down.** With an odd `w*h` the GPU still waits for the last pixel, and takes the first word of your next packet for it.
- **`h` read after moving `$sp`.** The fifth argument is at `16($sp)` *at entry*; after a prologue it is at `16 + frame size` (Chapter 15).
- **Load delay.** An `sw` right after the `lw` of the same register stores the old value: put an instruction between them.
- **Crossing a VRAM edge.** Not portable (5.2); stay inside VRAM.

## 10. Quiz

[`quiz.md`](quiz.md)

## 11. Further reading

- psx-spx (nocash PSX specs), *GPU Rendering Commands*: GP0 `A0h`, `C0h`, and the mask bit; *GPU Display Control Commands*: GP1 `08h`; *GPU Status Register*: bits 26 to 28.
- PCSX-Redux documentation (https://pcsx-redux.consoledev.net/): the VRAM viewer shows 24-bit mode.
- PSn00bSDK `LoadImage`: the same transfer, done with DMA.
