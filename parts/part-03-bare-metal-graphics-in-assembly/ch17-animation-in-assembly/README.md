# Chapter 17: Part III Capstone: Animation in Assembly

## 1. Concept

Animation is redrawing in step with the display: wait for **vertical blank**, draw the next picture in a **hidden** framebuffer, then make that buffer visible.

## 2. Why it matters

Every PS1 game runs this loop: update, draw, wait for VBlank, flip. Draw into the buffer the TV is reading and the player sees half-drawn frames and flicker. Run faster than the display and you waste work; run slower and the game drops to 30 or 20 fps. The SDK's `VSync()` and `DrawSync()` (Part IV) are the routines you write by hand here.

## 3. Learning objectives

After this chapter you can:

- explain what VBlank is and wait for it by polling `I_STAT` bit 0, acknowledging it correctly;
- lay out two 320x240 framebuffers in VRAM and say which is displayed and which is drawn into;
- move the display start (GP1 `05h`) and the drawing area/offset (GP0 `E3h`/`E4h`/`E5h`) together, once per frame;
- keep per-frame state in a fixed memory layout, with a frame counter;
- bounce an object off boundaries with clamp-and-negate;
- assemble a whole animated program from the routines of Chapters 13 to 15.

## 4. Prerequisites

[Chapter 13](../ch13-the-gpu-vram-and-command-packets/README.md) (GP0/GP1, GPUSTAT bit 26, fill `02h`, rectangle `60h`, display start `05h`, drawing area and offset `E3h`-`E5h`), [Chapter 14](../ch14-rendering-polygons/README.md) and [Chapter 15](../ch15-drawing-subroutines-and-stack-parameters/README.md) (Gouraud triangles, stack arguments: `draw_gouraud_tri` is given), [Chapter 12](../../part-02-thinking-like-the-r3000/ch12-risc-vs-cisc-multiply-and-divide/README.md) (shifts, `divu`/`mfhi`).

## 5. Explanation

### 5.1 VBlank and the frame

The display reads VRAM line by line, 60 times a second (NTSC). After the last visible line there is a pause, the **vertical blank**, before the next frame starts. It is the safe moment to change what is displayed. The hardware signals it as interrupt request 0 (**IRQ0**).

### 5.2 `I_STAT`: polling for VBlank

`I_STAT` (`0x1F801070`) has one bit per interrupt source. The GPU sets bit 0 at the start of every VBlank:

| Bit | Source | Bit | Source |
|---|---|---|---|
| **0** | **VBlank** | 6 | Timer 2 |
| 1 | GPU | 7 | Controller / memory card |
| 2 | CD-ROM | 8 | SIO |
| 3 | DMA | 9 | SPU |
| 4-5 | Timers 0, 1 | 10 | lightpen |

A bit stays set until the program **acknowledges** it. The rule is the reverse of what you might expect:

- write a **0** to a bit: that bit is cleared;
- write a **1** to a bit: it is left alone.

So `I_STAT = 0xFFFFFFFE` clears only VBlank. A wait is therefore:

```
 poll:  read I_STAT; bit 0 clear? -> poll again
        write 0xFFFFFFFE          (acknowledge)
```

Without the acknowledge, bit 0 stays set and every later wait returns at once: the loop runs unpaced (the verifier catches this).

**Why polling works here.** `I_STAT` latches events whether or not they are enabled in `I_MASK` (`0x1F801074`). An interrupt reaches the CPU only if its `I_MASK` bit is set *and* the CPU's COP0 status register (`SR`) enables interrupts; only then does a BIOS handler run, and that handler may acknowledge VBlank itself, so your poll would miss it. In this book's PCSX-Redux (OpenBIOS, fast boot), `main` starts with `SR = 0x40000000` (interrupts off), `I_MASK = 0` and `I_STAT = 1`, so nothing else touches the bit. A retail BIOS can start your program with interrupts on, so the given `main` writes `I_MASK = 0` to make polling safe there too (the book verifies the loop only in Redux). Commercial games usually pace with a VBlank interrupt handler or the root counters instead; the verifier checks only that you advance once per VBlank, not which method you use.

**Timing in the emulator.** OpenBIOS takes about 31 frames before your `main` runs, and bit 0 is already set when it does, so your first wait returns at once (the verifier ignores the first few frames). If your drawing takes longer than one frame, bit 0 is already set when you poll, so the wait returns at once and you flip in the middle of a displayed frame; keep the work per frame small.

### 5.3 Two framebuffers

Show buffer A while drawing into buffer B; swap at VBlank. Both fit in VRAM:

```
 VRAM (1024 x 512 pixels)
        0                 320                    1024
      0 +------------------+---------------------+
        | buffer 0         |                     |
        | (0,0)-(319,239)  |       free          |
    240 +------------------+                     |
        | buffer 1         |                     |
        | (0,240)-(319,479)|                     |
    480 +------------------+                     |
    512 +----------------------------------------+
```

Two GPU settings select a buffer. Both are needed:

| Setting | Command | Meaning |
|---|---|---|
| what is **shown** | GP1 `05h`: `(y << 10) | x` | display start: top-left pixel of the visible 320x240 area |
| where drawing **goes** | GP0 `E3h`/`E4h`: `(y << 10) | x` of top-left / bottom-right; `E5h`: `(y << 11) | x` | drawing area, and an offset added to every vertex |

The display mode is 320x240 **non-interlaced**: each frame is one complete picture, so a 240-line buffer is a whole frame. (A 480-line interlaced mode shows alternating fields and needs a different layout; it is not used here.)

With the offset set to `(0, by)`, where `by` is the buffer's first VRAM line (0 or 240), your coordinates stay `0..319` x `0..239` for either buffer. A **fill** (GP0 `02h`, Chapter 13) ignores the drawing area and offset: give it absolute VRAM coordinates, here `(0, by)`, 320x240.

### 5.4 The swap timeline

```
 time ->        frame k                    frame k+1                  frame k+2
 VBlank            |                          |                          |
 shown:    [ buffer 0 ........................ ][ buffer 1 ............... ][ buffer 0 ...
 drawing:          [ draw buf 1 ][ wait ] flip [ draw buf 0 ][ wait ] flip [ draw buf 1 ...
                                    ^                            ^
                       GP1(05h) = (0,240)            GP1(05h) = (0,0)
```

Draw, then wait for VBlank, then flip. The flip must come **after** the GPU has finished drawing, so wait for GPUSTAT bit 26 (Chapter 13) before writing GP1 `05h`. Write `05h` exactly **once** per frame: an extra flip can show a buffer that is still being drawn.

### 5.5 The frame loop

```
        +---------------------------------------------+
        |                                             |
        v                                             |
   frame: update gem state (move, bounce)             |
        |                                             |
        v                                             |
   select back buffer: E3/E4/E5 = (0, by)             |
        |                                             |
        v                                             |
   clear back buffer; draw gem; draw bar              |
        |                                             |
        v                                             |
   wait for VBlank (poll + acknowledge)               |
        |                                             |
        v                                             |
   wait for GPU idle; GP1(05h) = (0, by)              |
        |                                             |
        v                                             |
   buf ^= 1;  frame += 1  -------------------------->+
```

`by = buf * 240`. Compute it with shifts: `(buf << 8) - (buf << 4)`.

### 5.6 State, motion and bounce

All per-frame state lives in one block, so you can change the starting point by editing data and the verifier can read it:

| Offset | Field | Meaning |
|---|---|---|
| 0 | `x` | gem center, pixels (signed word) |
| 4 | `y` | gem center, pixels |
| 8 | `vx` | pixels per frame |
| 12 | `vy` | pixels per frame |
| 16 | `frame` | counts displayed frames, starts at 0 |
| 20 | `buf` | the **back** buffer: the one being drawn into (0 or 1) |

Each velocity is 8 bytes after its position, so one routine can serve both axes.

Motion per axis, once per frame: `p += v`. If `p < min`, set `p = min` and `v = -v`. If `p > max`, set `p = max` and `v = -v`. Clamping keeps the gem inside however fast it goes.

## 6. Worked example

`example/main.s` waits for VBlank and draws one 2-pixel-wide white line per frame at `x = 2 * (n mod 160)`: a sweep that fills the screen in 160 frames, then clears it. No double buffering, only the poll-and-acknowledge loop and a counter. Predict it, then run:

```sh
cd parts/part-03-bare-metal-graphics-in-assembly/ch17-animation-in-assembly/example
make run
```

Not checked by `verify.sh`.

## 7. Project: Bouncing Gem

Work in `starter/main.s`. Given: `gpu_init`, `gpu_wait`, `gpu_clear`, `draw_gouraud_tri` (your Chapter 15 routine, with its helpers), the `I_MASK = 0` write in `main`, the data and all constants. The stubs and the frame loop with five numbered TODOs are yours to complete.

### 7.1 What must be on screen

- A diamond centered at `(x, y)` with half-size `R = 24`: vertices top `(x, y-R)`, right `(x+R, y)`, left `(x-R, y)`, bottom `(x, y+R)`, drawn as **two Gouraud triangles**. Colors (`0x00RRGGBB`): top `0xA0F0FF`, left and right `0x20B0F0`, bottom `0x1040A0`.
- A background `0x101830`, cleared over the whole back buffer every frame.
- A **bar graph**: a rectangle (GP0 `60h`, Chapter 13) at `(10, 4)`, 8 high, color `0xF0D020`, width `((frame % 60) + 1) * 5` pixels. Drawn after the gem. (`divu` and `mfhi`, Chapter 12.)

### 7.2 The frame loop

Keep the starter's labels: `gem_state`, `frame` (the first instruction of the loop body, run once per frame), `main`, `done`. In order, once per iteration:

1. update `gem_state` (5.6) with bounds `x` in `[24, 295]`, `y` in `[24, 215]`;
2. back buffer: `by = buf * 240`; set the drawing area to `(0, by)`-`(319, by + 239)` and the offset to `(0, by)`;
3. clear the back buffer, draw the gem, draw the bar;
4. wait for VBlank: poll `I_STAT` bit 0, then acknowledge it;
5. wait for the GPU, then GP1 `05h` with `x = 0`, `y = by`; then `buf ^= 1` and `frame += 1`.

The initial `gem_state` is `x=60, y=80, vx=3, vy=2, frame=0, buf=1` (buffer 0 is shown first). Do not overwrite it in `main`: the verifier patches different values. It compares `gem_state` at every iteration with the rule of 5.6 exactly, and expects each picture to show the state *after* that iteration's update.

### 7.3 Hints

- Write `wait_vblank` first and test it with only a fill in the loop, alternating between two colors: the screen should flicker at 60 Hz.
- Spill live values (`by`, the gem position) to the stack or `$s` registers across `jal`: the given routines clobber `$t` registers.
- `draw_gouraud_tri` takes nine arguments: five on the stack at `16($sp)`..`32($sp)` of *your* frame (Chapter 15). Reserve 16 bytes of outgoing area plus those 20.
- Draw triangle 1 as top, right, left and triangle 2 as left, right, bottom: the shared edge is the horizontal diagonal.
- A gem that smears means the back buffer is not cleared; flicker means you flip before the GPU has finished, or flip twice.

### 7.4 Stretch goals

- Add a second gem with its own state block, and a routine that takes the block's address.
- Make the diamond spin or pulse using a lookup table (fixed-point math comes later in the book).
- Read the controller (a later chapter) to steer the gem.
- Measure how many CPU cycles one iteration's drawing takes (in the Redux Lua console, read `PCSX.getCPUCycles()` at two breakpoints) and compare with the roughly 566,000 cycles of an NTSC frame.

## 8. Verification

```sh
parts/part-03-bare-metal-graphics-in-assembly/ch17-animation-in-assembly/verify/verify.sh       # your starter/
parts/part-03-bare-metal-graphics-in-assembly/ch17-animation-in-assembly/verify/verify.sh -v    # + build output and emulator log
```

The verifier runs your program three times for 150 frames each: once as shipped and twice with `gem_state` patched to other starting positions and velocities. A probe records `gem_state` at the top of every loop iteration (label `frame`), at every VBlank, and every `E3h` and GP1 `05h` write.

| Check | Failing means |
|---|---|
| motion rules | not the clamp-and-negate rule; initial state overwritten; `frame` not +1 or `buf` not toggled per iteration |
| the gem bounces off every edge | a boundary missing on one axis; the gem is outside the bounds; it did not move in some frame |
| one update per VBlank | no VBlank wait, or no acknowledge (loop runs unpaced); or the loop regularly takes two VBlanks (a few missed VBlanks, up to 5%, are tolerated) |
| two framebuffers, swapped once per frame | not exactly one `05h` per iteration, or no `E3h`; the drawing area is not at `buf*240`; the display start is not the buffer just drawn; buffers do not alternate |
| screenshots show the gem where `gem_state` says | the gem is not at `(x, y)`; wrong shading; background not cleared (ghosts); the bar length is wrong for the frame counter |

A runaway (thousands of iterations per frame) is stopped early and reported as a missing VBlank wait.

## 9. Common pitfalls

- **Clearing `I_MASK` is not acknowledging.** `I_MASK` only decides what interrupts the CPU; the event bit is in `I_STAT`.
- **Acknowledging with 1.** Writing `1` to `I_STAT` bit 0 leaves it set. Write `0xFFFFFFFE`.
- **Flipping before the GPU is done.** Drawing is asynchronous; poll GPUSTAT bit 26 first.
- **Flipping twice per frame**, or moving only the display start and not the drawing area: you then draw into the buffer you show.
- **Not clearing the back buffer.** It holds the picture from *two* frames ago.
- **Filling with offset coordinates.** Fills ignore the offset: the second buffer needs `y = 240`.
- **Load delay.** `lw` then use of the same register in the next instruction (Chapter 7).
- **Losing registers across `jal`.** `$t` registers do not survive a call (Chapter 10).
- **Overwriting `gem_state` in `main`.** Hard-coded starting values defeat the verifier's patches.

## 10. Quiz

[`quiz.md`](quiz.md)

## 11. Further reading

- psx-spx (nocash PSX specs), *Interrupts* (I_STAT, I_MASK); *GPU Display Control Commands*: GP1 `05h`; *GPU Rendering Commands*: drawing area and offset.
- PCSX-Redux documentation (https://pcsx-redux.consoledev.net/): the VRAM viewer shows both buffers.
- PSn00bSDK `VSync`, `DrawSync`, `PutDispEnv`, `PutDrawEnv`: what these routines do for you in Part IV.
