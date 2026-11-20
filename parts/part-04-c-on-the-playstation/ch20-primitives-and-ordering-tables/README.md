# Chapter 20: Primitives and Ordering Tables

## 1. Concept

The GPU has no depth buffer: it draws primitives in the order it receives them, and later ones cover earlier ones (the painter's algorithm). The SDK sorts by depth with an **ordering table** (OT): an array of linked-list heads, one per depth level, which the DMA walks to feed the GPU. You add primitives to the table at their depth and let one DMA transfer send them far to near.

## 2. Why it matters

Every PS1 3D game sorts polygons this way, thousands per frame, with no CPU time spent moving data to the GPU. In Chapter 19 you sent one rectangle with `DrawPrim`, which waits for the GPU each time. An ordering table sends the whole frame in one DMA and sorts it for free: inserting a packet is two pointer writes. Chapters 21 to 41 build on this exact structure.

## 3. Learning objectives

After this chapter you can:

- lay out a primitive packet and its header word (24-bit next pointer, 8-bit length) and say how the DMA walks the list;
- explain why `ClearOTagR` builds a reverse table, which index is drawn first, and how depth maps to index;
- fill `POLY_F4` primitives with the SDK macros and insert them with `addPrim`;
- write a bump-pointer primitive allocator with an overflow guard, and say why it exists once per frame buffer;
- render and animate a depth-sorted scene and explain every pointer involved.

## 4. Prerequisites

[Chapter 13](../../part-03-bare-metal-graphics-in-assembly/ch13-the-gpu-vram-and-command-packets/README.md) and [Chapter 14](../../part-03-bare-metal-graphics-in-assembly/ch14-rendering-polygons/README.md) (GP0 packets, quads in Z order), [Chapter 19](../ch19-double-buffering/README.md) (the display/draw environments and the frame loop; `display.c` is reused unchanged).

## 5. Explanation

### 5.1 Painter's order

```
 draw far first                  near last covers it
   +------+                        +------+
   | blue |                        | blue |
   |   +--+--+                     |   +--+--+
   +---+--+  |   then green  -->   +---+gr|een|
       | green                         |  +---+
       +-----+                         +-----+
```

If you submit in the wrong order the picture is wrong, and there is no second chance: the GPU has already overwritten the pixels. So you need the packets **sorted by depth before they are sent**. Sorting 1000 packets with `qsort` costs too much; the ordering table sorts by *bucketing*.

### 5.2 A primitive is a packet with a header word

The SDK structs begin with one extra word, `tag`, which the DMA reads and the GPU never sees. `POLY_F4` (a flat quad, GP0 28h from Chapter 14):

```
 offset  bits 31..24 | 23..16 | 15..8 | 7..0
   +0    len         |      addr (next packet, low 24 bits)     <- tag
   +4    code=28h    |  b     |  g    |  r                       <- first GP0 word
   +8    y0                   |  x0
   +12   y1                   |  x1
   +16   y2                   |  x2
   +20   y3                   |  x3
 sizeof(POLY_F4) = 24; len = 5 (words after the tag)
```

| Field | Meaning |
|---|---|
| `addr` (bits 0 to 23) | Address of the next header word, without the `0x80000000` KSEG0 bits. `0x00FFFFFF` ends the list |
| `len` (bits 24 to 31) | How many words after the tag go to GP0 (0 to 255). 0 means "pointer only" |

The first DMA word is the header of the *current* packet, so each packet is "my length, where the next one is, then my data".

New names, all from `psxgpu.h`:

| Name | What it is |
|---|---|
| `POLY_F4` | Flat-shaded quad: `r0,g0,b0`, `code`, `x0,y0 ... x3,y3` (`int16_t`), after `tag` |
| `setPolyF4(p)` | Sets `len` = 5 and `code` = 0x28 |
| `setRGB0(p, r, g, b)`, `setXY4(p, ...)` | Colour; the four corners in Z order |
| `setXYWH(p, x, y, w, h)` | Same as `setXY4` for an upright rectangle: top-left, top-right, bottom-left, bottom-right |
| `setaddr/getaddr`, `setlen/getlen`, `setcode/getcode` | Read and write the header and code bytes |
| `termPrim(p)` | `setaddr(p, 0xFFFFFF)`: makes `p` the end of a list |
| `addPrim(ot, p)` | Insert `p` at the head of the list that starts at `ot`: `p->addr = ot->addr; ot->addr = p` |

Other primitives follow the same pattern. Names, `len` and codes:

| Struct | `setX` macro | `len` | `code` | Size |
|---|---|---|---|---|
| `POLY_F3` | `setPolyF3` | 4 | 20h | 20 |
| `POLY_F4` | `setPolyF4` | 5 | 28h | 24 |
| `POLY_G3` | `setPolyG3` | 6 | 30h | 28 |
| `POLY_G4` | `setPolyG4` | 8 | 38h | 36 |
| `TILE` | `setTile` | 3 | 60h | 16 |
| `SPRT` | `setSprt` | 4 | 64h | 20 |

`G` primitives carry a colour per corner (`setRGB0` to `setRGB3`), which the GPU interpolates (Gouraud shading). `TILE` and `SPRT` are rectangles; `SPRT` is textured (Part VI).

### 5.3 The ordering table

An OT is an array of `uint32_t`. The SDK takes `uint32_t *` (PsyQ called the type `u_long`). Each element is itself a header word with `len` = 0: an *empty list head*. Adding a packet to slot z splices it in right behind that head:

```
before addPrim(&ot[2], A)           after
  ot[2] --> ot[1] --> ot[0] --> END   ot[2] --> A --> ot[1] --> ot[0] --> END
```

Walking the whole list visits every slot in order, and every packet added to a slot is visited right after that slot's head. So **the order of the slots is the order of drawing**. Two details:

- `addPrim` inserts at the *head*: of two packets in the same slot, the one added **last** is drawn **first** (behind). Give overlapping primitives different slots, or accept this.
- The packets themselves can live anywhere in RAM, in any order. Only the links matter.

### 5.4 ClearOTagR and the reverse table

`ClearOTagR(ot, n)` prepares the table for `n` slots using DMA channel 6 (OTC, "ordering table clear"), which does nothing except write a chain of header words backwards through memory. Observed in the emulator (`ClearOTagR` on 64 entries):

```
 index:    63 -> 62 -> 61 -> ...  -> 2 -> 1 -> 0 -> END (0x00FFFFFF)
 address:  ot+252  ot+248                 ot+8  ot+4  ot+0
 each entry's addr field = the address of the entry below it
```

Entry `i` points to entry `i - 1`, and entry 0 holds the terminator. To draw, start the DMA at the **last** entry, `&ot[n - 1]`: slot 63 is drawn first, slot 0 last. (`ClearOTag` is the forward version: entry `i` points to `i + 1`.) Passing `&ot[0]` is a classic bug: the list is just the terminator and nothing is drawn.

```
 far                                                    near
 slot 63 ... slot 12 ... slot 3 ... slot 0
 drawn FIRST ----------------------> drawn LAST (on top)
```

So **depth 0 is nearest and the largest index is farthest**. With a reverse table, a depth value you compute from a 3D transform (bigger z = farther) can index the table directly. The reverse table exists because the OTC hardware can only write addresses downward.

`ClearOTagR` must run **every frame**: `addPrim` modified the links last frame, and the table is rebuilt from scratch. The primitives are not touched; their memory is simply reused.

### 5.5 Sending it: DrawOTag

`DrawOTag(ot)` queues a DMA channel 2 transfer in **linked-list mode** starting at `ot`. Unlike `DrawPrim`, it does not wait for earlier drawing first: it returns at once, and the DMA reads each packet from RAM while the GPU draws. Rule: **do not write the table or any packet until `DrawSync(0)` says the GPU is done**. The SDK's drawing queue (Chapter 19) runs it after the queued `PutDrawEnv`, so the clear still comes first.

### 5.6 The primitive buffer: a bump allocator

Primitives need memory that outlives the function that built them (not the stack, not a `static` per primitive: you have hundreds, with a count that changes). Standard solution: one array and a **bump pointer**.

```
 prim[ 0 ........................... PRIM_BUF_SIZE-1 ][guard]
       |A  |B  |C  |   free space ...
                   ^ used    alloc(n): return &prim[used]; used += n
 start of frame: used = 0  (everything is "freed" at once)
```

Allocation is one compare and one add, there is no `free`, and the whole frame is released by resetting `used`. Rules:

- round sizes up to a multiple of 4: every packet must start on a word boundary, because a word store to an address that is not a multiple of 4 raises an address error and the 24-bit links address whole words;
- **check the size first**: return `NULL` if `n > PRIM_BUF_SIZE - used`;
- callers must handle `NULL` (skip the primitive).

The PS1 has no memory protection. An allocator that runs off the end silently overwrites whatever comes next: here the next frame's table, which can send the DMA anywhere in RAM and hang the console. So the guard is not optional.

### 5.7 Two copies

Each frame owns a table and a primitive buffer: `OtFrame`, `ot_frames[2]`, one per display buffer. The rule from 5.5 is why. While the GPU is still reading frame *n*'s packets, the CPU is free to start frame *n+1*, but only if it writes somewhere else. In this chapter's loop `display_swap()` calls `DrawSync(0)` before the next frame starts, so one copy would happen to work. Real engines keep the CPU working while the GPU draws and move the wait later, so the second copy is what makes that safe; it costs 2,320 bytes. Your `ot.c` keeps the current index and flips it in `ot_draw()`, in step with `display_swap()`.

```
 frame n   : ot_frames[0]  built by CPU -> DrawOTag -> read by DMA/GPU
 frame n+1 : ot_frames[1]  built by CPU            (frame n may still be drawing)
 frame n+2 : ot_frames[0]  rebuilt: ClearOTagR, used = 0
```

## 6. Worked example

`example/` draws three overlapping squares with a bare 8-slot table in `main.c`: no allocator, three `static` `POLY_F4`s. Run it:

```sh
cd parts/part-04-c-on-the-playstation/ch20-primitives-and-ordering-tables/example
make run
```

`Z_RED`, `Z_GREEN` and `Z_BLUE` give the depths 5, 3, 1. Before running, predict the picture: red is farthest, so the blue square is on top and the red one at the bottom. Now change the values (try 1, 3, 5; then give two squares the same depth and say who wins and why), and change `DrawOTag(&ot[OT_LEN - 1])` to `&ot[0]` to see nothing at all. Not checked by `verify.sh`.

## 7. Project: Sixteen Quads

Work in `starter/`. `make` builds it; `make run` shows an empty screen until `ot.c` and the two marked functions of `main.c` are written.

### 7.1 Files

| File | Yours |
|---|---|
| `display.c`, `display.h` | Given: Chapter 19's solution, unchanged |
| `ot.h` | Given: `OT_LENGTH` (64), `PRIM_BUF_SIZE` (2048), `OtFrame`, `ot_frames`, the four prototypes |
| `ot.c` | **Write** the four functions (7.2). `ot_frames` and its guard bytes are given |
| `main.c` | Given: `scene`, state variables, frame loop. **Write** `draw_scene` and `advance` (7.3, 7.4) |

The `(void)` lines and the `linked[]` array in the starter only keep symbols linked until your code uses them; delete them as you go.

### 7.2 The `ot` API

| Function | Behaviour |
|---|---|
| `void ot_begin_frame(void)` | Call `ClearOTagR` on the current frame's table (all `OT_LENGTH` slots) and reset the bump pointer to 0 |
| `void *ot_alloc(size_t size)` | Round `size` up to a multiple of 4. If it does not fit in the current frame's `prim` array, return `NULL` and change nothing. Otherwise return the next block and advance the pointer |
| `void ot_add(void *prim, int depth)` | Clamp `depth` to 0 to `OT_LENGTH - 1`, then `addPrim` into that slot of the current table |
| `void ot_draw(void)` | `DrawOTag` starting at the **last** slot of the current table, then switch to the other `OtFrame` |

Keep the current index and the bump pointer as `static` variables. `ot_frames[2]` is the storage: each has `ot[]`, `prim[]` and `guard[]` (16 bytes of `0xA5` that must never change).

### 7.3 `draw_scene`

For each of the 16 quads in `scene` (7.5), in table order, and repeating the whole pass `copies` times (7.6): allocate a `POLY_F4`, set it up (`setPolyF4`, `setXYWH`, `setRGB0`) and `ot_add` it at the quad's `depth`. When `ot_alloc` returns `NULL`, stop submitting for this frame. Read `copies` once at the start of the call.

### 7.4 `advance`

After the frame is drawn and shown: `frame_no` += 1 and every quad's `depth` becomes `(depth + depth_step) % OT_LENGTH`. Quads cycle through the table: one reaching 63 jumps from the farthest to the nearest. Do not write `depth_step` as a constant.

### 7.5 The `scene` table

`Quad scene[16]`, 16 bytes per element, 256 in all:

| Offset | Size | Field |
|---|---|---|
| 0 | `int16_t` | `x`: left edge |
| 2 | `int16_t` | `y`: top edge |
| 4 | `int16_t` | `w`: width |
| 6 | `int16_t` | `h`: height |
| 8 | `uint8_t` | `r` |
| 9 | `uint8_t` | `g` |
| 10 | `uint8_t` | `b` |
| 11 | `uint8_t` | padding (0) |
| 12 | `int32_t` | `depth`: 0 = nearest, 63 = farthest |

The shipped table lays the quads on a 4 by 4 grid, 90 by 70 pixels each, so that neighbours overlap (42 pairs of quads overlap, some three or four deep), each with its own colour and a different depth. The background is `display_clear(24, 24, 32)`.

### 7.6 The other state variables

All `volatile uint32_t`, with non-zero shipped values so that they can be patched (a global initialised to 0 sits in `.bss` and is not stored in the file; Chapter 19):

| Variable | Shipped | Meaning |
|---|---|---|
| `frame_no` | 0 | Frames drawn so far |
| `copies` | 1 | How many times `draw_scene` submits the whole scene |
| `depth_step` | 1 | Added to every depth after each frame |

`copies` exists for the verifier: it patches it to 20, so that a frame needs 320 quads against room for 85. A correct program shows the first 85 and skips the rest.

### 7.7 Rules

- Keep the names `ot_begin_frame`, `ot_alloc`, `ot_add`, `ot_draw`, `ot_frames`, `scene`, `copies`, `depth_step`, `frame_no`. Do not change `ot.h`'s constants or the shipped data.
- Frame order is fixed: `display_clear`, `ot_begin_frame`, `draw_scene`, `ot_draw`, `display_swap`, `advance`.
- Use `ClearOTagR` and `DrawOTag`. Do not draw with `DrawPrim` or sort in your own code: the depth sorting must be the table's.
- All primitives are allocated from `ot_frames`; no locals, no new buffers.

### 7.8 Hints

- Nothing on screen: `DrawOTag(&ot[0])` instead of the last slot, or `ot_alloc` always returns `NULL`.
- Quads in submission order, not depth order: `ot_add` ignores `depth`, or the depth is reversed (index `OT_LENGTH - 1 - depth`).
- The screen shows an old frame mixed in, or the program hangs: `ClearOTagR` is missing, or runs on the wrong frame's table.
- Garbage after a while: the bump pointer is not reset in `ot_begin_frame`.

### 7.9 Stretch goals

Do these in a copy (`cp -r starter stretch`).

- Swap `POLY_F4` for `POLY_G4` and colour each corner differently.
- Add a `TILE` shadow behind each quad, one slot farther.
- Make `OT_LENGTH` 1024: what do 64 versus 1024 slots change in memory and in sort resolution?
- Move `DrawSync` out of `display_swap()` so the CPU builds frame *n+1* while the GPU draws *n*. What breaks if you use a single `OtFrame`?

## 8. Verification

```sh
parts/part-04-c-on-the-playstation/ch20-primitives-and-ordering-tables/verify/verify.sh
```

Four runs, up to 130 frames: the shipped scene, two scenes the harness **patches into `scene`** (new depths and a permutation of the colours, with `depth_step` 7 and 3), and the overflow run (`copies` = 20). The probe stops on every call of `ClearOTagR` and `DrawOTag`, and **walks the DMA list** from the argument of `DrawOTag`, the way the hardware would, recording each packet's header, code and colour.

| Check | What it means | If it fails |
|---|---|---|
| `symbols`, `ClearOTagR and DrawOTag are linked in`, `data layout as shipped` | The names exist and the data is unedited | Edited `ot.h` or the table, or the SDK calls are missing |
| `ClearOTagR builds a 64-entry table ...` | A `ClearOTagR(OT_LENGTH)` of one of the two tables every frame (extra clears are fine), consecutive frames use different tables, `DrawOTag` starts at `&ot[63]` of the table just cleared | Wrong head, one table only, or the length is not `OT_LENGTH` |
| `the DMA list holds the 16 quads farthest-first` | The list ends with the terminator; 64 heads and 16 `POLY_F4` packets (len 5, code 28h); the colours appear largest depth first; each packet hangs off slot `depth`; depths follow the animation | Depth reversed, ignored, or hard-coded, or you sorted in your own code |
| `packets are bump-allocated` | The 16 packets are consecutive 24-byte blocks from the start of the frame's `prim` | Pointer not reset, or padding |
| `overflow` | With 320 quads: no hang, guard bytes intact at every frame and at the end, 48 to 85 packets drawn | No size check in `ot_alloc`, or `draw_scene` ignores `NULL` |
| `pacing` | One frame per VBlank | Extra `VSync`, or a frame too long |
| `screenshots` | At frames 70 and 100 about 1500 sample points, at least 3 px from any quad edge, show the colour of the nearest quad; 480 of them are in overlaps (every overlapping pair has its own point) | Wrong order on screen: table, depth direction or missing clear |

A pass ends with `CHAPTER 20: PASSED (9/9 checks)`. The patched scenes defeat a hard-coded order; the failure message shows the colour found and the quad it looks like.

## 9. Common pitfalls

- **`DrawOTag(ot)` instead of `&ot[N-1]`.** With a reverse table `ot[0]` is the terminator: you draw nothing.
- **Reading "depth" the wrong way.** Index 0 is last drawn, so nearest. A table that looks right with one depth direction and wrong with the other is the commonest bug.
- **No `ClearOTagR` each frame.** Old links stay: packets repeat, or a list loops until the DMA hangs.
- **Not resetting the bump pointer.** The buffer fills after a few frames.
- **Primitives on the stack.** `DrawOTag` returns before the DMA reads them; the stack frame is gone.
- **Same slot, wrong expectation.** `addPrim` inserts at the head: the last added is drawn first.
- **Allocating after the overflow check fails.** `ot_alloc` must change nothing when it returns `NULL`.
- **Forgetting the 24-bit pointer.** Header addresses drop `0x80000000`; `nextPrim(p)` puts it back. Reading `addr` as a full pointer crashes.
- **Flipping the frame index twice** (in `ot_draw` and again elsewhere), so `ot_frames[cur]` and the display buffer drift apart.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- `.toolchain/opt/psn00bsdk/include/libpsn00b/psxgpu.h`: `POLY_F4`, the `set*`/`addPrim` macros, `ClearOTagR`, `DrawOTag`.
- `share/psn00bsdk/doc/drawing_queue.md`: how `DrawOTag` and `PutDrawEnv` share one queue.
- `share/psn00bsdk/examples/beginner/hello/main.c`: the same pattern in a single file (a 16-slot table and an 8 KB buffer).
- psx-spx, "DMA Channels" (the linked-list mode, the OTC channel) and "GPU Render Polygon Commands".
- Chapter 13 and 14: the GP0 words that the packets carry.
