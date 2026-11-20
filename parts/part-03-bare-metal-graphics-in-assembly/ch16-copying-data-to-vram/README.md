# Chapter 16: Copying Data to VRAM

## 1. Concept

VRAM is not memory-mapped: the CPU cannot store into it. Pixels travel through GP0 in one **CPU to VRAM transfer** (`A0h`): three header words, then the pixels, two per word.

## 2. Why it matters

Every texture, font, sprite sheet and loading screen a PS1 game shows crossed this bridge. In Part VI the CD-ROM will hand you TIM images; the last step of loading one is exactly the `A0h` packet you write here. The 24-bit display mode (used by FMV and some title screens) adds a twist: the *same* VRAM, read as 3 bytes per pixel.

## 3. Learning objectives

After this chapter you can:

- send a CPU to VRAM transfer: header words, size, and the right number of data words;
- pack pixels two per word and say which half is the left pixel;
- explain what happens when `w*h` is odd;
- compute a 24-bpp line width in 16-bit VRAM units with shifts (`px * 3 / 2`);
- embed a binary image with `.incbin` and read its size and position from a table;
- state the GPUSTAT rules for a transfer: wait before the packet, never inside the data.

## 4. Prerequisites

[Chapter 13](../ch13-the-gpu-vram-and-command-packets/README.md) (GP0/GP1, GPUSTAT bit 26, the 1024x512 VRAM), [Chapter 15](../ch15-drawing-subroutines-and-stack-parameters/README.md) (stack arguments, "one wait per packet"), [Chapter 12](../../part-02-thinking-like-the-r3000/ch12-risc-vs-cisc-multiply-and-divide/README.md) (shifts instead of multiplies).

## 5. Explanation

### 5.1 VRAM as 16-bit units

VRAM is 1024 x 512 units of 16 bits, row-major. Unit (x, y) is at byte offset `(y*1024 + x) * 2 = (y << 11) + (x << 1)`: Chapter 12's shifts. Everything in this chapter (x, y, w, h of a transfer) counts **units**, not pixels. In 15-bit mode the two are the same; in 24-bit mode they are not (5.4).

A 15-bit pixel (BGR555, little-endian):

```
 bit  15   14..10   9..5    4..0
      M     Blue    Green   Red          M = mask bit; keep it 0 for plain pictures
```

### 5.2 GP0 `A0h`: copy rectangle, CPU to VRAM

The packet is three words, then data:

```
 word 1   A0 00 00 00         command byte A0h (the rest is ignored)
 word 2   y(31..16) | x(15..0)        destination: top-left unit in VRAM
 word 3   h(31..16) | w(15..0)        size in units
 word 4.. pixel data, two units per word: low half = LEFT unit, high half = right
```

Each word goes to GP0 (`0x1F801810`) with `sw`. The data is the rectangle **row by row** (row-major, no gaps between rows):

```
 RAM (w = 3, h = 2: 6 units = 3 words)           VRAM rectangle at (x, y)
 word 0: [ p1 | p0 ]   <- high half | low half     (x  , y  ) p0  p1  p2
 word 1: [ p3 | p2 ]                               (x  , y+1) p3  p4  p5
 word 2: [ p5 | p4 ]
```

The GPU needs `ceil(w*h / 2)` words. If `w*h` is odd, the last word carries one unit and one pad half the GPU ignores. Send exactly that many words:

| Words sent | Result |
|---|---|
| too few | the GPU keeps waiting for data: your **next packet becomes pixels** |
| too many | the extra words are read as commands |

The source pointer must be word-aligned (you read it with `lw`, Chapter 11). If `w*h` is odd the last `lw` reads 4 bytes of which only 2 count; the buffer must have room for them.

**Limits** (psx-spx):

- `x` and `y` are masked to 10 and 9 bits (`x = 1030` lands at 6; PCSX-Redux agrees). Size 0 means the maximum (1024 or 512). Always send `w, h >= 1`.
- **Stay inside VRAM: `x + w <= 1024`, `y + h <= 512`.** psx-spx says a rectangle past an edge wraps to the opposite edge, but the PCSX-Redux build used here did something else for a rectangle crossing the right edge. Edge-crossing behaviour is not portable, and nothing in this chapter (or its verifier) depends on it.
- The transfer is **not** clipped to the drawing area (`E3h`/`E4h`) and ignores the drawing offset; it does obey the mask-bit setting (`E6h`, off after reset).

### 5.3 Waiting: what GPUSTAT says during a transfer

Chapter 15's rule was "wait once, before the first word; bit 26 is a between-packets signal". A transfer makes it vivid. Measured in PCSX-Redux, by reading GPUSTAT at four moments:

| Moment | bit 26 (ready for command word) | bit 28 (ready for DMA block) |
|---|---|---|
| before the packet | 1 | 1 |
| after word 1, after word 3, after 100 data words | **0** | 1 |
| after the last data word | 1 | 1 |

During the data phase bit 26 is **0**, because the GPU wants data, not a command. This is exactly psx-spx's definition (Chapter 15): bit 26 is clear while the GPU "wants to either receive additional parameters/data or it is busy". A routine that polls bit 26 before every data word therefore **hangs after the header**. The rules:

1. Wait for bit 26 **once**, before word 1.
2. Then send the header and all data words back to back, with no polling.

A word on real hardware, which this book cannot test: the emulator accepts every word at once and never pushes back, so it cannot show whether a real GPU keeps up with an unpaced loop (the GP0 FIFO holds 16 words, psx-spx). Small CPU uploads written this way are common in homebrew; large ones, such as textures loaded by games, normally go by **DMA** (Part IV), where the GPU's DMA request paces the transfer. The rule above (no bit-26 polling inside the data) holds either way.

### 5.4 24-bit mode: bytes, not pixels

GP1(`08h`) display mode (Chapter 13) has **bit 4: colour depth** (0 = 15-bit, 1 = 24-bit). In 24-bit mode the display reads VRAM as **3 bytes per pixel**, bytes in the order **R, G, B**:

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

The transfer does not know about colour depth: you send an `A0h` rectangle `w = 480`, `h = 240` of raw bytes. The width in units is `px * 3 / 2` = `px + (px >> 1)`, a shift and an add (Chapter 12); for an odd pixel count it is not a whole number of units, so keep x offsets and widths even.

**Byte order.** psx-spx gives a 24-bit pixel as red in bits 0-7, green 8-15, blue 16-23; little-endian, that puts red at the lowest address. This chapter's verifier confirms it in PCSX-Redux: it uploads random R, G, B bytes and compares the 24-bit screenshot with them pixel by pixel (recorded in `tools/verify-lib/README.md`). Note the 15-bit format is the opposite way round: red is the *low* bits of a unit.

### 5.5 `.incbin`: an image as bytes in your program

`.incbin "img16.bin"` is an armips directive that copies a file's bytes into the output at that point. The path is relative to the build's working directory; the starter's `Makefile` copies every `*.bin` next to `main.s`. Put `.align 4` before it so the label is word-aligned, and give it a label:

```
 img16:  .incbin "img16.bin"     ; 96*64*2 = 12288 bytes of BGR555
```

Both images are made by `tools/assets/ch16_images.py` (original, procedural), with corner markers and an asymmetric "F" so that a flip, a shift or a swapped channel is visible. The generated `.bin` files are checked in; the script reproduces them.

## 6. Worked example

`example/main.s` computes a 16x16 checkerboard in a loop and sends it with `A0h` straight to GP0 (header, then 128 data words), at the middle of the screen. Predict it, then run:

```sh
cd parts/part-03-bare-metal-graphics-in-assembly/ch16-copying-data-to-vram/example
make run
```

You should see a 4x4-cell white and red checkerboard, 16 pixels square, on black. It is not checked by `verify.sh`.

## 7. Project: Picture Show

Work in `starter/main.s`. `gpu_init`, `gpu_clear`, `gpu_wait`, the data table and the two images are given. You write two routines and `main`. One program, two modes: the data word `mode` selects **part 1** (`0`) or **part 2** (`1`). Edit it to see part 2; the verifier patches it.

### 7.1 `vram_upload(ptr, x, y, w, h)`

Arguments `$a0` ptr, `$a1` x, `$a2` y, `$a3` w, **`h` at `16($sp)`** (Chapter 10). Sizes are in 16-bit units, `w, h >= 1`, `x + w <= 1024`, `y + h <= 512`. It must:

1. wait for GPUSTAT bit 26 **once**, then send `0xA0000000`, `(y << 16) | x`, `(h << 16) | w`;
2. send exactly `(w*h + 1) / 2` words read from `ptr` (word-aligned, row-major, two units per word), with **no polling** between them;
3. send nothing to GP1, return with `$sp` and `$s0`-`$s7`, `$gp`, `$fp` unchanged.

You will need `w*h`: `mult`/`mflo` is fine here (Chapter 12).

### 7.2 `bpp24_halfwords(px)`

Return `px * 3 / 2` in `$v0` for even `px`, using shifts and adds only (a static check bans `mult` and `div`). `bpp24_halfwords(320)` is 480.

### 7.3 `main`, part 1 (`mode = 0`)

`gpu_init`; `gpu_clear` the whole 320x240 area with `BG_COLOR` (`0x303038`); upload the 16-bpp picture `img16` to `(img16_x, img16_y)` with size `img16_w` x `img16_h`. Read all four from the data table: the verifier patches them, and also the pixels.

### 7.4 `main`, part 2 (`mode = 1`)

`gpu_init`; write GP1 `08h` with `0x08000011` (320 wide, 240 high, NTSC, **24-bit**); compute the line width in units with `bpp24_halfwords(img24_w)`; upload `img24` (`img24_h` rows) at `(0, 0)` with one `vram_upload`. No background fill is needed: the picture covers the screen.

### 7.5 Hints

- Put the three header words and the data loop in the same routine; the loop is `lw`, `addiu` pointer, `sw`, count down.
- Odd `w*h`: round the word count **up**.
- `main` needs a frame of at least 32 bytes: `h` goes to `16($sp)` before every `jal vram_upload`.
- A garbled picture that stops short in part 2 means `w = 320` units instead of 480.

### 7.6 Stretch goals

- **Readback.** `GP0 C0h` (copy rectangle VRAM to CPU) takes the same three words, then you read the pixels from GPUREAD (the same address as GP0, reading) while GPUSTAT bit 27 is set. Write `vram_download` and compare with what you sent. (Not checked; see psx-spx.)
- Upload the 24-bit picture 100 pixels to the right (what is `x` in units?) and move the display start (GP1 `05h`).
- Draw a polygon (Chapter 14) on top of the 16-bit picture.

## 8. Verification

```sh
parts/part-03-bare-metal-graphics-in-assembly/ch16-copying-data-to-vram/verify/verify.sh        # your starter/
parts/part-03-bare-metal-graphics-in-assembly/ch16-copying-data-to-vram/verify/verify.sh -v     # + build output and emulator log
```

The verifier calls your routines directly with harness-chosen arguments (random pixel buffers; odd widths and pixel counts; the right and bottom edges, e.g. a 64x8 rectangle at `(960, 504)`; a 1023x3 rectangle) and compares VRAM with the buffer. Then it runs the real program in both modes, on the shipped images and on patched ones (other size and place, random pixels).

| Check | Failing means |
|---|---|
| ONE packet: `A0h`, destination, size, `ceil(w*h/2)` data words | wrong header word, or too few / too many data words (odd counts!) |
| rectangle equals the buffer | pixels swapped within a word, wrong row order, or a half-word lost |
| nothing outside changes | wrong destination, extra words |
| waits before the first word | no GPUSTAT read before the packet |
| "did not return" | a bit-26 poll inside the data phase, or a loop whose counter is wrong |
| ABI | `$s` registers or `$sp` changed; `h` read from the wrong offset |
| `bpp24_halfwords` | wrong formula; `mult` used |
| part 1 VRAM and screen | position or size hard-coded instead of read from the table; picture flipped |
| part 2 GP1 `08h` | bit 4 not set, or other bits changed |
| part 2 packet and VRAM | width 320 instead of 480 units; `bpp24_halfwords` not called (480 hard-coded) |
| part 2 screenshot | wrong colour order, or the display is not in 24-bit mode |

## 9. Common pitfalls

- **Waiting per data word.** Bit 26 is 0 in the data phase: the program hangs after the header.
- **Width in pixels in 24-bit mode.** A 320-unit upload fills two thirds of the picture.
- **Rounding the word count down.** An odd `w*h` loses its last pixel; the next packet then completes it.
- **`h` read after moving `$sp`.** The fifth argument is at `16($sp)` *at entry* (Chapter 15).
- **Load delay.** `lw` then `sw` of the same register back to back: put an instruction between them.
- **Crossing a VRAM edge.** Not portable (5.2); stay inside VRAM.

## 10. Quiz

[`quiz.md`](quiz.md)

## 11. Further reading

- psx-spx (nocash PSX specs), *GPU Rendering Commands*: GP0 `A0h`, `C0h`, and the mask bit; *GPU Display Control Commands*: GP1 `08h`; *GPU Status Register*: bits 26 to 28.
- PCSX-Redux documentation (https://pcsx-redux.consoledev.net/): the VRAM viewer shows 24-bit mode.
- PSn00bSDK `LoadImage`: the same transfer, done with DMA.
