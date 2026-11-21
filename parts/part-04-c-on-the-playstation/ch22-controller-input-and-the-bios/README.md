# Chapter 22: Controller Input and the BIOS

## 1. Concept

The digital pad is read over a serial link. The **BIOS** (the firmware built into the console) polls it once per frame and leaves the result in a buffer you hand it. The buffer holds a **bitmask**: one bit per button, where a `0` means pressed. **Edge detection** compares this frame's mask with the last one to turn "is down" into "went down this frame".

## 2. Why it matters

Every game reads the pad every frame. The raw data answers only "which buttons are down right now". Gameplay needs more: fire once per press, not 60 times a second; open a menu on release; jump higher the longer you hold. The `input` module you write here is the layer between the hardware and those rules, and the `psxe` library keeps it for the rest of the book.

## 3. Learning objectives

After this chapter you can:

- state what the BIOS provides and how a program calls it (`A0`/`B0`/`C0` tables);
- describe, at a high level, how the console and the pad talk;
- start the BIOS pad driver (`InitPAD`, `StartPAD`) and read its buffer;
- explain **active-low** logic and convert a raw button word into a usable mask;
- implement `held`, `pressed` and `released` by comparing two readings;
- test input code with scripted button presses in the emulator.

## 4. Prerequisites

[Chapter 21](../ch21-working-with-multiple-files/README.md) (the `psxe` library, `static`, headers), [Chapter 19](../ch19-double-buffering/README.md) (the frame loop and `VSync`), and the bit operations (`&`, `|`, `~`, shifts) from Part I.

## 5. Explanation

### 5.1 What the BIOS is

The BIOS is a 512 KB program in ROM, mapped at `0xBFC00000`. The CPU starts executing there on reset. It does three jobs:

| Job | What happens |
|---|---|
| Boot | Initializes the hardware and its own data structures (the *kernel*, which lives in the first 64 KB of RAM, below where programs load), then loads and starts your executable from the disc (or, in an emulator, the file you side-load) |
| Services | Functions any program can call: memory and string helpers, file access to the disc and memory cards, the pad driver, events and threads |
| Interrupts | Its exception handler at `0x80000080` receives every interrupt and every `syscall`; this is how `EnterCriticalSection` works |

You call a BIOS function through one of three **kernel call tables**, `A0`, `B0` and `C0`. The convention: put the function number in `$t1` and jump to address `0xA0`, `0xB0` or `0xC0`. The SDK hides that in three-instruction stubs. This is `InitPAD` in `libpsxapi`:

```
li  t2, 0xB0        ; table B
jr  t2
li  t1, 0x12        ; function 0x12 of table B (delay slot)
```

You can confirm it with `mipsel-none-elf-objdump -d` on the library (Chapter 21's worked example shows how to open it). The pad functions are `B(12h)` `InitPAD`, `B(13h)` `StartPAD`, `B(14h)` `StopPAD` and `B(5Bh)` `ChangeClearPAD`.

The BIOS also keeps an **event and handler system**: a program or driver registers a function to run when something happens (a VBlank, a finished read). The pad driver uses it: it hooks the VBlank interrupt and polls the pad inside it, with no work from your loop.

> **Which BIOS?** Real consoles have Sony's BIOS, in several revisions. Our harness runs **OpenBIOS**, PCSX-Redux's open-source replacement. It implements the same call tables, including the pad driver, but it is a reimplementation, so undocumented details may differ. This chapter relies only on what a poll writes (`stat`, type, buttons), and says so where it describes something observed under OpenBIOS.

### 5.2 How the console talks to the pad

Pads and memory cards share one serial port, **SIO0**. The console is the master: it sends a byte and the pad answers with a byte at the same time. A select line picks the port (slot 1 or 2), the first byte picks the device (`01h` a controller, `81h` a memory card), and the device confirms each byte except its last with an acknowledge line.

A poll of a digital pad, at the level you need:

```
console sends:   01h    42h    00h      00h       00h
                 (ctrl) (poll) (idle)   (idle)    (idle)
pad answers:     --     41h    5Ah      btn_lo    btn_hi
                        |      |        '- 16 button bits (5.4)
                        |      '- "data follows" marker
                        '- type 4, 1 word of data: a digital pad
```

You never write this. The BIOS driver does it once per VBlank (60 times a second on NTSC) and stores the answer in your buffer, without the `5Ah` marker:

```
buffer:  [0] status     00h = a pad answered; FFh = no answer (no pad)
         [1] 41h        type (high nibble) and length (low nibble)
         [2] btn_lo     bits 0..7  of the button word
         [3] btn_hi     bits 8..15 of the button word
         (an analog pad adds stick bytes after these)
```

The SDK gives this layout a name, `PADTYPE` in `<psxpad.h>`: `stat`, `len`, `type`, `btn`.

### 5.3 Starting the driver

Three calls, as in the SDK's own examples:

| Call | Meaning |
|---|---|
| `InitPAD(buf1, len1, buf2, len2)` | Register one buffer per port. The SDK examples use 34 bytes each (room for a multitap's worth of data) |
| `StartPAD()` | Start polling from the VBlank handler |
| `ChangeClearPAD(0)` | Tell the driver not to acknowledge the VBlank interrupt itself: the SDK's `VSync` already does. The SDK examples recommend it |

Wrap them in `EnterCriticalSection()` / `ExitCriticalSection()` (interrupts off), as the SDK's `cdrom/cdbrowse` example does, so no VBlank arrives half-way through the setup. Call them **after** `display_init()`: `ResetGraph` sets up the SDK's interrupt handling, and the SDK examples start the pad after it. The buffers must live as long as the program (a `static` array in `input.c`), because the driver writes into them from an interrupt long after `input_init` has returned.

Two facts to design around:

- The buffer is written **behind your back**. Read it once per frame into your own variable and use that copy.
- Until the first poll arrives, the buffer holds what it held before: for a `static` array, **all zero** (observed under OpenBIOS: the first reading lands about two frames after `main` starts). A zero `stat` then looks valid, and zero bits mean "every button pressed" (5.4). Check `stat == 0` **and** a known `type` before trusting `btn`; an empty port reports `stat = FFh` once polled.

PSn00bSDK 0.24 has no higher-level pad library (Sony's SDK has `PadInit`/`PadRead`): `<psxpad.h>` holds definitions only. Its `examples/io/pads` shows the alternative: driving SIO0 yourself from a timer interrupt, which is how you poll more often than once per frame or switch a pad to analog mode.

### 5.4 Bitmasks and active-low logic

A **bitmask** packs many yes/no values into one integer, one per bit. To test a bit, AND with a mask that has only that bit set; to set several at once, OR their masks.

The pad's button word has 16 bits:

| Bit | Button | Bit | Button |
|---|---|---|---|
| 0 | Select | 8 | L2 |
| 1 | L3 | 9 | R2 |
| 2 | R3 | 10 | L1 |
| 3 | Start | 11 | R1 |
| 4 | Up | 12 | Triangle |
| 5 | Right | 13 | Circle |
| 6 | Down | 14 | Cross (X) |
| 7 | Left | 15 | Square |

(Bits 0 to 7 travel in `btn_lo`, 8 to 15 in `btn_hi`; `<psxpad.h>` names these positions `PAD_SELECT` ... `PAD_SQUARE`.)

The pad is **active-low**: the electrical idle level is high, so a button that is *down* sends a **0** and an *up* button sends a **1**. An idle pad reads `0xFFFF`. Holding Up gives `0xFFEF`.

Most people find "1 = down" (**active-high**) easier. Invert once, where the data enters your code:

```
raw  = 1111 1111 1110 1111      (Up held)
~raw = 0000 0000 0001 0000      bit 4 set: Up
```

Every caller of the module then uses active-high masks and never sees the raw form. Mixing the two is the classic bug here: `if (raw & PAD_UP)` is true when Up is *not* pressed.

### 5.5 Edge detection

`held` says what is down. Game rules often want the *change*: an **edge** is a frame where a button's state differs from the frame before.

```
frame:      1  2  3  4  5  6  7  8
X down:     0  0  1  1  1  1  0  0
held(X):    0  0  1  1  1  1  0  0
pressed(X): 0  0  1  0  0  0  0  0     down now, up before
released(X):0  0  0  0  0  0  1  0     up now, down before
```

To compute edges you keep **two** words: the latest reading and the one before. With active-high words `now` and `before`:

| Query | Bits that qualify |
|---|---|
| held | `now` |
| pressed | `now` AND NOT `before` |
| released | `before` AND NOT `now` |

`input_update()` shifts `now` into `before` and reads a new `now`, once per frame. The queries are pure: asking twice gives the same answer. (A design that clears a flag when you read it breaks as soon as two pieces of code ask.)

### 5.6 The `input` module

The module joins `psxe` as `include/psxe/input.h` and `src/input.c`. The header is given in `starter/`:

| Item | Contract |
|---|---|
| `INPUT_UP`, `INPUT_CROSS`, ... | 16 active-high masks, bit positions as in 5.4 |
| `void input_init(void)` | Starts the BIOS driver for port 1. Afterwards no button is reported down (until a real reading says so) |
| `void input_update(void)` | Takes one reading of port 1 and does the shift of 5.5. Call it **once per frame** before any query |
| `int input_held(uint16_t mask)` | 1 if any button of `mask` is down, else 0 |
| `int input_pressed(uint16_t mask)` | 1 if any button of `mask` went down at the last update |
| `int input_released(uint16_t mask)` | 1 if any button of `mask` came up at the last update |

An empty mask always gives 0. If there is no valid pad answer (5.3), every button counts as up. The raw buffer, the two words and any helper are `static`: the library exports exactly the five functions.

## 6. Worked example

`example/` is a pad viewer: sixteen squares in bit order, lit when the bit says "down". It uses the raw driver with no library, so you can see the active-low data directly.

```sh
source tools/env.sh
cd parts/part-04-c-on-the-playstation/ch22-controller-input-and-the-bios/example
make run
```

Press keys in the emulator window (PCSX-Redux maps the keyboard to pad 1: **Configuration > Controls** shows the mapping). Check:

1. Which squares light for Up, Cross and Start? Do they match the table in 5.4?
2. In `main.c`, remove the `!` in front of `(raw & (1 << bit))`. What do you see at rest, and why?
3. Comment out the `stat == 0 && type` test. What changes in the first frame or two?

## 7. Project: "Cursor"

A 16-pixel square on a dark screen that you steer.

### 7.1 Behavior

| Input | Effect (applied once per frame) |
|---|---|
| D-pad | Moves the square by `speed` pixels per frame along each held direction. Two directions at once (diagonal) move on both axes. Opposite directions cancel |
| Square (held) | The step is `fast` instead of `speed` |
| X (Cross), on **press** | `color = (color + 1) % 6`. Holding the button does nothing more |
| Start, on **release** | `x = home_x; y = home_y`. The color stays |

After all of that, every frame, the position is **clamped**: `0 <= x <= SCREEN_W - size` and `0 <= y <= SCREEN_H - size`. The square stops at the edge; it does not wrap and is never partly off screen.

Start acts on **release**: nothing happens while it is down, and the square jumps home on the frame it comes up. Each query thus has a job: `held` drives the D-pad and Square, `pressed` X, `released` Start.

### 7.2 State the verifier reads

`starter/main.c` declares it. Keep the layout and the initial values:

| Field (`cursor_state`, eight `int32_t`) | Offset | Initial | Meaning |
|---|---|---|---|
| `x`, `y` | 0, 4 | 152, 112 | Top-left corner of the square |
| `color` | 8 | 0 | Index into `cursor_colors` |
| `speed` | 12 | 2 | Pixels per frame |
| `fast` | 16 | 4 | Pixels per frame while Square is held |
| `home_x`, `home_y` | 20, 24 | 152, 112 | Where Start sends the cursor |
| `size` | 28 | 16 | Side of the square |

`cursor_colors[6][3]` (r, g, b): red `230,40,40`, green `40,200,60`, blue `60,110,255`, yellow `240,220,40`, magenta `220,60,220`, cyan `40,220,220`. The background is `(24, 24, 32)`.

**Your rules must read all of these from the struct.** The verifier patches `speed`, `fast`, `home_*`, `size`, `x`, `y` and `color` before some runs.

### 7.3 Steps

1. In `psxe/src/input.c`, implement the five functions of 5.6. Start the driver as in 5.3. Include `<psxapi.h>` and `<psxpad.h>`.
2. Check the module before writing the full rules: does `input_held(INPUT_UP)` follow the real button?
3. In `main.c`, write `cursor_update()` (the table and the clamp of 7.1). The loop, the drawing and `main` are given: the loop calls `input_update()`, then `cursor_update()`, then draws.
4. Build and run (`make run`), then `verify.sh`.

### 7.4 Rules

- `libpsxe.a` exports the five `input_*` functions of the `input` module and nothing else from `input.c`.
- `input.c` reaches the pad through the BIOS driver (`InitPAD`, `StartPAD`); `main.c` includes only `psxe` headers (no `<psxapi.h>`, `<psxpad.h>`, `<psxgpu.h>`), calls no SDK pad or graphics function, and has at most 70 lines of code.
- `input_update` is called once per frame, `input_init` once.
- The rules of 7.1 use all three queries. The verifier also calls `input_held`, `input_pressed` and `input_released` directly, so they must be in the program: the SDK build drops functions nobody calls.

### 7.5 Hints

- *The cursor never moves*: does `input_init` hand the driver the buffer `input_update` reads? Is that buffer `static`, not on the stack?
- *Everything is "pressed" at start-up*: you trusted the zeroed buffer (5.3).
- *The square drifts the wrong way*: `~` is missing, or applied twice.
- *The color spins while X is down*: that is `held`, not `pressed`.
- *`pressed` never fires*: you updated `before` after computing the answer, or in `input_pressed` itself.
- Compare against what the viewer showed you if the bit positions confuse you.

### 7.6 Stretch goals

- Read port 2 as well (`input_*` with a port argument; the second `InitPAD` buffer).
- Add **repeat**: `input_held_frames(mask)` counting how long a button has been down, and make Start need a 30-frame hold.
- Plug in a real pad (or map keys in Redux) and print `stat`, `type` and `btn` with `FntPrint`.
- Read the DualShock analog sticks from `PADTYPE` for movement with a dead zone.

## 8. Verification

```sh
parts/part-04-c-on-the-playstation/ch22-controller-input-and-the-bios/verify/verify.sh
```

The harness presses buttons on PCSX-Redux's emulated pad (**pad overrides**, applied on scripted frames) and the probe records `cursor_state` every frame. It also calls your `input_held`, `input_pressed` and `input_released` directly, every frame, while buttons change. Four scripted runs of 135 to 330 frames each: the shipped numbers, patched numbers, big steps against all four edges, and a query test.

| Check | What it means | If it fails |
|---|---|---|
| `symbols`, `data layout as shipped` | Your program has the parts; state and color table unedited | Removed or edited data; a function nobody calls was dropped by the linker |
| `libpsxe.a exports only the module API` | `nm`: four modules, each exporting only its API | A `static` is missing in `input.c` |
| `input.c goes through the BIOS pad driver` | `input.o` references `InitPAD` and `StartPAD` | Reading the pad some other way |
| `headers` | Four guarded, self-contained headers that define nothing | As Chapter 21 |
| `main.c is thin` | At most 70 lines, only `psxe` headers | Pad code in `main.c` |
| `the BIOS pad driver is started once` | One `InitPAD` with two RAM buffers, one `StartPAD` | `input_init` not called, or called twice |
| `input_update is called once per frame` | The probe counts calls per VBlank | Called twice or not every frame |
| `D-pad`, `Square` | Moves by `speed`/`fast` per frame, diagonals, opposites cancel; each frame's step is exactly 0 or the speed | No `~`, wrong axis, `else if` chains |
| `X changes the color once per PRESS` | A 30-frame hold: exactly one change; three 3-frame taps: three; wraps at 6 | `held` instead of `pressed` |
| `Start ... RELEASED` | Nothing while it is down, home (from the struct) after release; color kept | Hard-coded home, wrong edge |
| `speeds, size and color come from cursor_state` | Patched run: speed 3, fast 7, color 3 | Constants in your rules |
| `clamped ... on all four edges` | Every frame inside `0..SCREEN-size` with a 32 px square and 40 px steps | Clamp missing or uses a constant size |
| `screenshots` | One square at the reported position, in the reported color, nothing else | Drawing not driven by the state |
| `input_held / pressed / released, called directly` | Over a 30-frame press, an overlapping press and a 1-frame tap: pressed fires for exactly one frame, released too; reading twice changes nothing; masks of several bits mean "any"; empty mask is 0 | Query with side effects; wrong edge |
| `raw pad polarity and start-up` | An idle pad reports nothing down; nothing changed before the first scripted press | Forgot to invert, or no `stat`/`type` test (the zeroed buffer read as "all pressed") |

A pass ends with `CHAPTER 22: PASSED (18/18 checks)`. Timing: the script starts at frame 60, well after the first poll. A button pressed on frame *f* for *n* frames is seen by `input_update` on *n* consecutive loop iterations from the next one on; the movement checks allow one frame of slack either way.

## 9. Common pitfalls

- **Active-low confusion.** Test `!(raw & mask)`, or invert once on entry. Never mix.
- **Trusting the buffer before the first poll.** Zero bits read as every button down, and a zero `stat` looks valid. Check `stat` and `type`.
- **A pad buffer on the stack.** The driver keeps writing to it after your function returns. Make it `static`.
- **Calling `input_update` more than once per frame.** The second call makes `before == now`, and every edge disappears.
- **Detecting edges with `held` and a flag in game code.** Fine for one button; with ten, it is ten flags. Keep it in the module.
- **Level vs. edge.** Movement wants `held`; toggles, menu choices and "fire once" want `pressed`; "confirm on release" wants `released`.
- **Starting the pad before `display_init`.** Follow the order of 5.3: graphics first.
- **Assuming a digital pad.** Analog pads report `type` 5 or 7 with the same first four bytes; accept all three if you want them to work.
- **Different BIOS, different details.** Test on real hardware or a retail BIOS before relying on anything beyond what a poll writes.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- psx-spx (nocash PSX specs): "Controllers and Memory Cards", especially "Controller Communication Protocol" and "Digital Pad", and "BIOS Function Summary" for the `A0`/`B0`/`C0` tables.
- `.toolchain/opt/psn00bsdk/include/libpsn00b/psxpad.h` and `psxapi.h`.
- `.toolchain/opt/psn00bsdk/share/psn00bsdk/examples/io/pads/` (manual SIO0 polling) and `graphics/fpscam/main.c` (the BIOS driver as used in this chapter).
- PCSX-Redux Lua documentation, `PCSX.SIO0` pad overrides (https://pcsx-redux.consoledev.net/Lua/introduction/).
- Part V starts with fixed-point math (Chapter 23); the `input` module returns when the camera needs steering.
