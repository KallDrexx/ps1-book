# Chapter 19: Double Buffering with Display and Draw Environments

## 1. Concept

The TV shows one area of VRAM while the GPU draws into another. The SDK models this as a **pair of environments**: a `DISPENV` (what is shown) and a `DRAWENV` (where drawing goes). Draw into the hidden buffer, wait for VBlank, then show it and start on the other one. This is double buffering, and you built it by hand in Chapter 17. Now the SDK does the register work.

## 2. Why it matters

Every PS1 game has this loop. With one buffer the viewer sees half-cleared, half-drawn frames. With two, they only ever see finished frames, and the program is paced to 60 (or 50) frames per second by VBlank. Chapter 20 hangs primitives and ordering tables on exactly this frame loop.

## 3. Learning objectives

After this chapter you can:

- explain why drawing into the visible buffer shows flicker and tearing;
- fill and use a `DISPENV`/`DRAWENV` pair and say which GPU commands each produces;
- write the frame order draw, `DrawSync`, `VSync`, `PutDispEnv` and say why each step sits where it does;
- clear the draw area with `isbg`, and animate a color and a position with state that a verifier can read;
- write `display_init()`, `display_clear()` and `display_swap()` in a module of their own.

## 4. Prerequisites

[Chapter 17](../../part-03-bare-metal-graphics-in-assembly/ch17-animation-in-assembly/README.md) (two buffers at VRAM y = 0 and 240, GP1 05h, VBlank pacing), [Chapter 13](../../part-03-bare-metal-graphics-in-assembly/ch13-the-gpu-vram-and-command-packets/README.md) (display and drawing areas), [Chapter 18](../ch18-from-assembly-to-c/README.md) (the SDK calls, CMake, `isbg`).

## 5. Explanation

### 5.1 Why one buffer is not enough

The GPU scans VRAM out to the TV continuously. If it draws into the area being scanned, you see the work in progress:

```
single buffer                              double buffer
  scan-out  ---> shows VRAM (0,0)            scan-out  ---> shows buffer A
  GPU draws ---> into VRAM (0,0)             GPU draws ---> into buffer B (hidden)
  "clear, then draw" is visible              A finished frame is all you ever see
```

### 5.2 The environment pair

PSn00bSDK keeps the two jobs apart:

| Struct | Answers | Becomes |
|---|---|---|
| `DISPENV` | Which VRAM rectangle does the TV show? | GP1 05h (display start) and 06h/07h/08h (range, mode) |
| `DRAWENV` | Where may the GPU draw, and from what origin? | GP0 E1h/E2h (texture page, window), E3h/E4h (drawing area), E5h (offset), optionally a 02h fill |

The fields (names from `psxgpu.h`, PSn00bSDK 0.24):

| `DISPENV` field | Meaning |
|---|---|
| `disp` (`RECT`) | The VRAM rectangle shown: x, y, w, h |
| `screen` (`RECT`) | Where it sits on the TV (defaults are fine) |
| `isinter`, `isrgb24`, `reverse` | Interlace, 24-bit color, flip: all 0 here |

| `DRAWENV` field | Meaning |
|---|---|
| `clip` (`RECT`) | Drawing area: nothing is drawn outside it |
| `ofs[2]` | Extra draw offset, **relative to `clip`'s corner**. `PutDrawEnv` sends E5h = (`clip.x + ofs[0]`, `clip.y + ofs[1]`), and the GPU adds that to every primitive's x, y |
| `isbg` | Non-zero: clear `clip` when the environment is applied |
| `r0`, `g0`, `b0` | The clear color, 0 to 255 each (`setRGB0`) |
| `tw`, `tpage`, `dtd`, `dfe` | Texture window, initial tpage, dither, drawing to the display area. Leave at the defaults |

`RECT` is `{ int16_t x, y, w, h; }`. The SDK uses the fixed-width types of `<stdint.h>` (`int16_t`, `uint8_t`, `uint32_t`). PsyQ's `u_char` and `u_long` still exist in `<sys/types.h>`, but this book uses the `stdint` names.

Two buffers, laid out as in Chapter 17:

```
 VRAM 1024 x 512                x ->  0            320                    1023
 y=0    +---------------------+---------------------------------------------+
        | buffer 0  320x240   |                                             |
        |  disp[0].disp  = (0,0,320,240)                                    |
        |  draw[0].clip  = (0,0,320,240), ofs = (0,0) -> E5h (0,0)          |
 y=240  +---------------------+              free: textures,                |
        | buffer 1  320x240   |              palettes (later)               |
        |  disp[1].disp  = (0,240,320,240)                                  |
        |  draw[1].clip  = (0,240,320,240), ofs = (0,0) -> E5h (0,240)      |
 y=480  +---------------------+  (32 unused lines)                          |
```

The **draw offset** is what lets the same drawing code serve both buffers. `SetDefDrawEnv` leaves `ofs` at (0, 0), and `PutDrawEnv` adds `clip`'s corner, so the GPU's offset is the buffer's corner: a rectangle at y = 104 lands at 104 in buffer 0 and at 344 in buffer 1.

### 5.3 The new calls

| Call | Does |
|---|---|
| `SetDefDispEnv(&d, x, y, w, h)` | Fills a `DISPENV` to show the rectangle at (x, y), w by h |
| `SetDefDrawEnv(&d, x, y, w, h)` | Fills a `DRAWENV`: `clip` = the rectangle, `ofs` = (0, 0), `isbg` = 0, dithering on |
| `PutDispEnv(&d)` | Sends the display registers to the GPU **now** (GP1 writes) |
| `PutDrawEnv(&d)` | Builds the environment packet (E1h to E5h, plus the `isbg` fill) inside `d` and adds it to the SDK's drawing queue; it runs when the GPU is free |
| `DrawSync(0)` | Waits until the drawing queue is empty and the GPU is idle |
| `VSync(0)` | Waits for the next VBlank (`VSync(-1)` returns the VBlank counter without waiting) |
| `SetDispMask(1)` | Switches the picture on (it starts off); 0 blanks it |
| `ResetGraph(0)` | Full reset: GP1 00h (which also blanks the picture), the SDK's queue and its interrupt handlers. Modes 1 and 3 are partial resets you will not need |

Two facts drive the loop below (the queue is described in `share/psn00bsdk/doc/drawing_queue.md`):

- `PutDrawEnv` is **queued** behind earlier work. Its settings and clear happen later, in order.
- `PutDispEnv` is **immediate**. Where you place it in the frame decides what the viewer sees.

### 5.4 The frame loop

```
 CPU     |-- display_clear --|-- draw --|-- DrawSync --|-- VSync --|-- PutDispEnv --|  next frame
 GPU     |   clear back      |  rect    |  (idle)                                    |
 screen  | ...... shows front buffer (finished, previous frame) ......| shows new     |
                                                                     ^ VBlank
```

Per frame, in this order:

1. `display_clear`: `PutDrawEnv(back)`. Queues "set area, clear to color" for the **hidden** buffer.
2. Draw. This chapter: one rectangle with `DrawPrim` (5.6).
3. `DrawSync(0)`: the frame is finished before anything is shown.
4. `VSync(0)`: wait for VBlank, the moment the display start can change without tearing.
5. `PutDispEnv(front)`: show the buffer just drawn.
6. Swap which buffer is "back".

Why this order:

| Wrong | Result |
|---|---|
| `PutDispEnv` before `DrawSync` | The finished-looking buffer is shown while the GPU is still drawing: partial frames |
| `PutDispEnv` without `VSync` | The display start changes mid-scan: a tear, and the loop runs far faster than 60 fps |
| `VSync` first, then `DrawSync` | If drawing overruns VBlank, the swap happens whenever the GPU finishes, mid-scan: a tear |
| Draw into the buffer you just showed | You are back to one buffer |

The loop spends its spare time inside `VSync(0)`. If a frame's work takes longer than one frame period, `VSync` waits for the next VBlank and the game drops to 30 fps. The verifier checks this pacing.

### 5.5 Clearing with `isbg`

With `isbg = 1` the `DRAWENV` packet ends with a fill of the draw area in `r0,g0,b0`, so the hidden buffer starts every frame clean. `PutDrawEnv` rebuilds the packet from the struct each time it is called, so to change the color every frame call `setRGB0` first, then `PutDrawEnv`. A color set after `PutDrawEnv` waits for that environment's **next** `PutDrawEnv`, which with two buffers is two frames later.

The framebuffer is 15-bit: the GPU keeps the top 5 bits of each channel, as in Chapter 18.

### 5.6 A stopgap rectangle: `DrawPrim`

The GPU draws from **primitives**: small packets such as "flat rectangle". Chapter 20 teaches them properly, with ordering tables. Until then, the simplest way to draw one thing is:

| Piece | Meaning |
|---|---|
| `TILE` | A primitive struct: a flat, untextured rectangle |
| `setTile(&t)` | Marks the struct as a `TILE` (length and command code) |
| `setXY0(&t, x, y)`, `setWH(&t, w, h)`, `setRGB0(&t, r, g, b)` | Position, size and color (the same `setRGB0` macro as for `DRAWENV`) |
| `DrawPrim((uint32_t *) &t)` | Waits like `DrawSync(0)`, then starts a DMA of the one packet to the GPU and returns |

Because `DrawPrim` waits first, the queued clear is guaranteed to finish before the rectangle is drawn. It does **not** wait for the rectangle: the DMA may still be reading the struct after `DrawPrim` returns, so keep the `TILE` `static`. The `DrawSync(0)` in `display_swap` waits for the rectangle. With many primitives, waiting before every packet wastes time; ordering tables fix that and add depth sorting. Coordinates are relative to the draw offset (5.2), so the rectangle's code never mentions which buffer it is in.

### 5.7 The hue and the state

The animation uses four global variables. The verifier reads them (so their names and meanings are fixed) and patches their initial values.

| Variable | Type | Meaning | Initial |
|---|---|---|---|
| `frame_no` | `uint32_t` | Frames drawn so far | 0 |
| `hue` | `uint32_t` | Background hue, 0 to 1535 | 256 |
| `hue_step` | `uint32_t` | Added to `hue` after every frame | 12 |
| `rect_x` | `int32_t` | Left edge of the rectangle | 16 |

All are `volatile`. **Hue to color** (six segments of 256, `seg = hue >> 8`, `f = hue & 255`):

| seg | R | G | B |
|---|---|---|---|
| 0 | 255 | f | 0 |
| 1 | 255 - f | 255 | 0 |
| 2 | 0 | 255 | f |
| 3 | 0 | 255 - f | 255 |
| 4 | f | 0 | 255 |
| 5 | 255 | 0 | 255 - f |

**Per frame:** the frame is drawn with the current values; then `frame_no += 1`, `hue = (hue + hue_step) % 1536`, and `rect_x` goes up by 1, back to 0 after reaching 288 (screen width minus the 32-pixel rectangle).

## 6. Worked example

`example/` is the **single-buffer** version of the module: one `DISPENV`, one `DRAWENV`, both at VRAM (0, 0), with the same three functions. It clears to blue-gray and moves a white square. Run it:

```sh
cd parts/part-04-c-on-the-playstation/ch19-double-buffering/example
make run
```

It looks fine: the clear and one square finish within VBlank, before the TV scans anything. Now set `LONG_FRAME` to `1` in `main.c`. An extra `VSync(0)` between the clear and the square stands in for a frame with too much drawing to fit in VBlank. Predict, then run. The square flickers: every other frame the TV shows the buffer cleared but not yet drawn. Your project removes that limit by drawing where the TV is not looking. Not checked by `verify.sh`.

## 7. Project: Color Cycle

Work in `starter/`. `make` builds it; `make run` shows a black screen because `display.c` and the helpers in `main.c` are stubs.

### 7.1 Files

| File | Yours |
|---|---|
| `display.h` | Given: the three prototypes and `SCREEN_W`/`SCREEN_H` |
| `display.c` | **Write** all three functions (7.2) |
| `main.c` | Given: state variables, the frame loop. **Write** `hue_to_rgb`, `draw_rect`, `advance` (7.3 to 7.5) |

### 7.2 `display.c`

The API (prototypes in `display.h`): `void display_init(void)`, `void display_clear(uint8_t r, uint8_t g, uint8_t b)`, `void display_swap(void)`. Keep two `DISPENV`s, two `DRAWENV`s and an index of the hidden ("back") buffer as `static` variables.

- `display_init()`: `ResetGraph(0)`. Buffer 0 at VRAM (0, 0), buffer 1 at (0, 240), each 320 by 240, for both env types. Turn `isbg` on in both draw environments (required: it is the clear the checks expect). Start with buffer 0 as the back buffer. Show buffer 1 with `PutDispEnv` (the viewer must never see the buffer being drawn into), then `SetDispMask(1)`.
- `display_clear(r, g, b)`: put the color into the **back** draw environment and `PutDrawEnv` it.
- `display_swap()`: `DrawSync(0)`, `VSync(0)`, `PutDispEnv` for the buffer just drawn, then switch the back buffer.

### 7.3 `hue_to_rgb`

Implement the table in 5.7. Out-parameters are the three bytes.

### 7.4 `draw_rect`

A white 32 by 32 `TILE` at (x, 104), sent with `DrawPrim` (5.6). Make the `TILE` `static`: `DrawPrim` returns before its DMA has finished reading it.

### 7.5 `advance`

Update the state as in 5.7. Use `hue_step`; do not write its value as a constant.

### 7.6 Rules

- Keep the names `display_init`, `display_clear`, `display_swap`, `main` and the four state variables; the verifier finds your program through them.
- Do not change the initial values. The verifier patches `hue`, `hue_step` and `rect_x` in the executable and expects the screen to follow. That is why their shipped values are non-zero: a global initialized to 0 goes in `.bss`, which is not stored in the file (`crt0` zeroes it, Chapter 18), so there is nothing to patch. `frame_no` is in `.bss` and always starts at 0.
- Frame order is fixed: values drawn, then `display_swap()`, then `advance()`.
- One `VSync` per frame, inside `display_swap()`. No busy loops to waste time.

### 7.7 Hints

- A black screen: `SetDispMask(1)` missing, or `PutDispEnv` never called.
- Black first frames, then colors that lag behind `hue`: `setRGB0` after `PutDrawEnv`.
- The rectangle at the wrong height or in only one buffer: `PutDrawEnv` already sets the GPU offset to the buffer's corner; do not add 240 yourself, and leave `ofs` at 0.
- Flicker or half-drawn rectangle: look at the order in 5.4.

### 7.8 Stretch goals

Do these in a copy (`cp -r starter stretch`).

- Move `VSync(0)` before `DrawSync(0)`. Even with a hundred `DrawPrim` calls nothing tears: why? (`DrawPrim` waits for everything before its own packet, so at most one rectangle is still in flight. Chapter 20's queued drawing is where this order matters.)
- Watch `VSync(-1)` (the VBlank counter) next to `frame_no` in the debugger; do they stay in step?
- Make the rectangle bounce, as in Chapter 17.
- Add a third buffer pair and rotate through three: what changes in `display_swap()`?

## 8. Verification

```sh
parts/part-04-c-on-the-playstation/ch19-double-buffering/verify/verify.sh
```

The harness builds with CMake, then runs your program three times for 130 frames: on the shipped state and on two states it **patches into** `hue`, `hue_step` and `rect_x`. The probe records the state variables at every GP1 05h write (display start) made inside `display_swap()`; the one in `display_init` is ignored.

| Check | What it means | If it fails |
|---|---|---|
| `symbols`, `state variables start as shipped` | The ELF has the functions and variables; initial values unedited | A symbol was optimized away, or you edited an initial value |
| `display.c uses the environment API` | The eight calls of 5.3 and `isbg` appear in `display.c` | A step is missing from `display_init`/`display_swap` |
| `state follows the update rules` | First frame uses the initial values; each next frame obeys 5.7 | Constant `hue_step`, wrong wrap, state changed before drawing |
| `display start alternates ...` | GP1 05h alternates (0,0), (0,240); frame n is shown from buffer `n % 2` | One buffer, or `PutDispEnv` on the wrong env |
| `one iteration per VBlank` | One write per VBlank (two irregular gaps tolerated) | No `VSync` (too fast) or a doubled one (too slow) |
| `screenshots ...` | At frames 70 and 100: about 1200 grid points outside the rectangle equal the hue color exactly, at the GPU's 5 bits per channel (no tearing, no leftover rectangle); the white rectangle is at `rect_x`; 30 frames later it moved 30 px and the color changed | Wrong hue table, `isbg` missing, swap before drawing |

Each screenshot is compared with the state recorded at the last display-start write before it. A pass ends with `CHAPTER 19: PASSED (7/7 checks)`.

## 9. Common pitfalls

- **`setRGB0` after `PutDrawEnv`.** The queued packet already has the old color; the new one waits for that environment's next turn, two frames later.
- **`PutDrawEnv` on the front buffer.** You clear the picture the TV is showing.
- **Forgetting `isbg` or the clear.** The previous frame's rectangles stay; the screen smears.
- **Adding the buffer's y yourself.** `PutDrawEnv` already offsets drawing by `clip`'s corner.
- **`SetDispMask(1)` missing.** The display starts off; you get a black screen though everything draws.
- **Two `VSync` calls per frame.** The game runs at 30 fps and the verifier's pacing check fails.
- **Reading the numbers as "this frame".** `display_swap()` shows the frame you just drew; once `advance()` has run, the variables describe the next one.
- **A `TILE` on the stack.** `DrawPrim` returns while its DMA may still be reading the packet; the next call's stack frame can overwrite it.
- **A header declaring a function the `.c` never defines.** It links until you call it.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- `.toolchain/opt/psn00bsdk/include/libpsn00b/psxgpu.h`: `DISPENV`, `DRAWENV`, `TILE`, every call above.
- `share/psn00bsdk/doc/drawing_queue.md`: the queue behind `PutDrawEnv`, `DrawSync` and `DrawPrim`.
- `share/psn00bsdk/examples/beginner/hello/main.c`: the same pattern with an ordering table (Chapter 20).
- Chapter 17: the same loop in assembly, with GP1 05h written by hand.
