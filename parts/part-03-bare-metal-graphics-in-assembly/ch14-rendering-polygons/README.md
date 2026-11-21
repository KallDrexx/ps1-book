# Chapter 14: Rendering Polygons

## 1. Concept

The GPU draws **triangles** and **quads** from packets of vertex coordinates and colors. A **flat** polygon has one color. A **Gouraud** polygon has one color per vertex, and the GPU blends them across the surface.

## 2. Why it matters

Every 3D model on the PS1 is a pile of triangles and quads, and every one reaches the screen as a packet like the ones in this chapter. Chapter 15 wraps them in routines; Part V feeds them from the GTE. Learn the packet shapes now and the rest is plumbing.

## 3. Learning objectives

After this chapter you can:

- build the four untextured polygon packets (`20h`, `28h`, `30h`, `38h`) and say how many words each has;
- pack a vertex word, including negative coordinates;
- send the vertices of a quad in Z order and explain how the GPU splits it into two triangles;
- explain Gouraud interpolation and why a quad's shading can show a seam;
- use the drawing offset and the drawing area, and name the limits on polygon size;
- set semi-transparency with the command bit and the draw-mode word.

## 4. Prerequisites

[Chapter 13](../ch13-the-gpu-vram-and-command-packets/README.md) (GP0, the display setup, `BBGGRR` colors, the bit-26 wait), [Chapter 9](../../part-02-thinking-like-the-r3000/ch09-signed-numbers-logic-and-shifts/README.md) (masking signed values), [Chapter 10](../../part-02-thinking-like-the-r3000/ch10-the-stack-and-the-mips-abi/README.md) (calling routines from routines).

## 5. Explanation

### 5.1 The command byte

Every polygon command has `001` in bits 7-5 of the command byte. The low five bits are flags:

| Bit | Value | Meaning when set |
|---|---|---|
| 4 | `+10h` | **Gouraud**: a color per vertex |
| 3 | `+08h` | **Quad** (4 vertices) instead of triangle |
| 2 | `+04h` | Textured (Chapter 30; not used here) |
| 1 | `+02h` | **Semi-transparent** (section 5.7) |
| 0 | `+01h` | Raw texture (textured polygons only) |

The four commands of this chapter:

| Command | Polygon | Words |
|---|---|---|
| `20h` | flat triangle | 4 |
| `28h` | flat quad | 5 |
| `30h` | Gouraud triangle | 6 |
| `38h` | Gouraud quad | 8 |

### 5.2 Packet layouts

The color word is `cc BBGGRR` as in Chapter 13: command on top, blue in the next byte, red lowest.

```
Flat triangle 20h     Flat quad 28h        Gouraud triangle 30h   Gouraud quad 38h
 1  20 BB GG RR        1  28 BB GG RR       1  30 BB GG RR  (c1)    1  38 BB GG RR  (c1)
 2  y1 | x1            2  y1 | x1           2  y1 | x1             2  y1 | x1
 3  y2 | x2            3  y2 | x2           3  00 BB GG RR  (c2)    3  00 BB GG RR  (c2)
 4  y3 | x3            4  y3 | x3           4  y2 | x2             4  y2 | x2
                       5  y4 | x4           5  00 BB GG RR  (c3)    5  00 BB GG RR  (c3)
                                            6  y3 | x3             6  y3 | x3
                                                                    7  00 BB GG RR  (c4)
                                                                    8  y4 | x4
```

Only the **first** color word carries the command byte. The other color words have `00` on top.

### 5.3 The vertex word

```
 31          16 15           0
+--------------+--------------+
|   y (signed) |   x (signed) |      word = (y << 16) | (x & 0xFFFF)
+--------------+--------------+
```

Each coordinate is a **signed 11-bit** number, -1024 to 1023: the GPU uses the low 11 bits and sign-extends them. A negative `x` in a register has its upper bits set, so it must be **masked** to 16 bits before it is OR-ed with `y << 16`, or it destroys `y`.

The **drawing offset** (`E5h`, Chapter 13) is added to every vertex. With an offset of (160, 120), vertex (-90, -100) lands at screen (70, 20). An offset lets a model be built around its own center and moved by changing one word: `0xE5000000 | ((y & 0x7FF) << 11) | (x & 0x7FF)`.

### 5.4 Quads and the Z order

A quad is two triangles. The vertices are sent in **Z order**, not around the outline:

```
   v1 ----------- v2          triangle A = v1 v2 v3
    |          .  |           triangle B = v2 v3 v4
    |       .     |
    |    .        |           The shared edge is the diagonal v2-v3.
    | .           |
   v3 ----------- v4
```

If you send the corners in outline order (top-left, top-right, bottom-right, bottom-left), the two triangles overlap and a quarter of the rectangle stays empty: a notch instead of a rectangle.

**Winding does not matter.** Whether a triangle's vertices run clockwise or counterclockwise, the GPU draws it (verified in PCSX-Redux; the example shows it). There is no back-face culling in hardware; the engine does that in software (Chapter 25).

### 5.5 Gouraud shading

Each vertex has a color. For a pixel inside the triangle, the GPU takes a weighted mix of the three colors, with the weights set by how close the pixel is to each vertex (barycentric weights, which add up to 1):

```
            c1 = red
              /\            pixel color = w1*c1 + w2*c2 + w3*c3
             /  \                          (w1 + w2 + w3 = 1)
            / .  \          near v1: w1 ~ 1  -> almost pure red
           /  p   \         center:  w = 1/3 each -> the average
     c3   /________\  c2    on an edge: the opposite vertex has weight 0
```

The mix is linear along every line through the triangle. In a **quad** each of the two triangles interpolates **its own three** colors, so a Gouraud quad can show a faint seam along the diagonal v2-v3, where the two triangles' gradients meet. The colors at the four corners are exact.

A flat polygon skips all of this: one color word, a shorter packet and a faster fill.

**Dither.** Bit 9 of the draw-mode word (`E1h`) turns on ordered dithering: a small pattern added to each color before it is cut to 5 bits, which hides banding in Gouraud gradients. The book keeps it **off**: `E1h = 0x400`, only bit 10 set ("drawing to the display area allowed", Chapter 13). With dither on, Gouraud pixels change by a few levels.

### 5.6 Clipping and limits

| Rule | Effect |
|---|---|
| **Drawing area** (E3h/E4h) | Pixels outside it are not touched; a polygon partly outside is clipped |
| **Vertex range** | Each coordinate is signed 11 bits, -1024 to 1023; the drawing offset is added afterward |
| **Size limit** | The distance between any two vertices may be at most **1023 horizontally and 511 vertically**. A larger polygon is **dropped entirely**, not clipped |

Tested in PCSX-Redux: a triangle 1200 wide and one 520 tall are not drawn at all; one 1000 wide is. The size limit is why engines split big polygons that stick far out of the screen (Chapter 36).

### 5.7 Semi-transparency

Two things are needed: set bit 1 of the command byte (`22h`, `2Ah`, `32h`, `3Ah`), and choose the blend in the draw-mode word `E1h`, bits 5-6. *B* is what is already in VRAM, *F* is the polygon's color:

| `E1h` bits 5-6 | Result | Meaning |
|---|---|---|
| 0 | `B/2 + F/2` | average: a 50% blend |
| 1 | `B + F` | additive (glows), clamped at 255 |
| 2 | `B - F` | subtractive (shadows), clamped at 0 |
| 3 | `B + F/4` | a faint additive |

The mode is part of the GPU's **state**: it stays until the next `E1h` and applies to every later polygon that has the semi-transparency bit. Opaque commands (`20h`...`38h`) ignore it, so they need no reset. Keep bit 10 set whenever you write `E1h`.

## 6. Worked example

`example/main.s` sends one long word stream to GP0: two flat triangles of the same shape with opposite vertex order, a Gouraud triangle, a flat quad, and four semi-transparent quads of one color, one per mode, each partly over the flat quad. Predict the picture, then run:

```sh
cd parts/part-03-bare-metal-graphics-in-assembly/ch14-rendering-polygons/example
make run
```

Check: both triangles appear; the Gouraud triangle is a smooth RGB blend; the four quads differ only because of the mode. The example is not checked by `verify.sh`.

## 7. Project: Polygon Gallery

Work in `starter/main.s`. `gpu_init`, `gpu_clear` and `gpu_wait` are given (Chapter 13). You write two small routines and `main`.

### 7.1 The composition

```
 (0,0)                                      x ->                     (319,0)
   +------------------------------+---------------------------------+
   |        v1                    |   v1 --------------- v2         |
   |       /  \     flat          |    |     flat quad     |        |
   |      /    \    triangle      |   v3 --------------- v4         |
   |    v3------v2                |                                 |
   |------------------------------+---------------------------------|
   |        v1  red               |  v1 red ---------- v2 yellow    |
   |       /  \     Gouraud       |   |    Gouraud quad    |        |
   |      /    \    triangle      |  v3 blue --------- v4 white     |
   | v3 blue---v2 green           |                                 |
   +------------------------------+---------------------------------+
                                                              (319,239)
```

The `origin` table holds the drawing offset, (160, 120). All vertices below are **relative to the origin** (they go into the packet unchanged; the GPU adds the offset). Colors are `0x00RRGGBB`.

| Polygon | Command | Color(s) | Vertices (x, y) relative to origin |
|---|---|---|---|
| Background | fill `02h` | `0x181830` | whole 320x240 screen |
| Flat triangle | `20h` | `0xFFA000` | (-90,-100), (-30,-20), (-150,-20) |
| Flat quad | `28h` | `0x20C0A0` | (30,-100), (140,-90), (20,-20), (130,-15) |
| Gouraud triangle | `30h` | v1 `0xFF0000`, v2 `0x00FF00`, v3 `0x0000FF` | (-90,10), (-30,95), (-150,95) |
| Gouraud quad | `38h` | v1 `0xFF0000`, v2 `0xFFFF00`, v3 `0x0000FF`, v4 `0xFFFFFF` | (30,10), (140,10), (30,95), (140,95) |

The starter already has these as data tables; **your code reads them**. The verifier patches all of them (colors, vertices, origin) before running, so the numbers above are only the shipped values. Table layouts (all words, coordinates signed):

| Label | Words |
|---|---|
| `origin` | x, y |
| `bg_color` | color |
| `flat_tri` | color, x1, y1, x2, y2, x3, y3 |
| `flat_quad` | color, x1, y1, ..., x4, y4 |
| `gouraud_tri` | (color, x, y) for v1, v2, v3 |
| `gouraud_quad` | (color, x, y) for v1, v2, v3, v4 |

### 7.2 The routines

| Routine | Does |
|---|---|
| `pack_color(color, cmd)` | `$v0 = (cmd << 24) \| 0x00BBGGRR` from `0x00RRGGBB` (ignore the color's top byte) |
| `pack_vertex(x, y)` | `$v0 = (y << 16) \| (x & 0xFFFF)`, correct for negative inputs |

Both are leaf routines: `$t`, `$a`, `$v` only, no `$sp`.

### 7.3 `main`

1. `gpu_init`, then `gpu_clear` the whole screen with `bg_color`.
2. Send `GP0(E5h)` with the drawing offset from `origin`.
3. Draw the four polygons, in this order: flat triangle, flat quad, Gouraud triangle, Gouraud quad. Wait for GPUSTAT bit 26 (`gpu_wait`) before each packet.
4. Fall into `done`.

### 7.4 Your steps

1. Write `pack_color` and `pack_vertex`. Run the verifier: it calls both with random inputs.
2. In `main`, set the offset and send the flat triangle by hand, word by word. Check the screen.
3. Add the flat quad. Check that the table's vertices are in Z order.
4. Add the Gouraud triangle, then the Gouraud quad: each needs a color word before *every* vertex, with the command byte in the first one only.
5. Now that you have four copies of nearly the same code, write a routine that sends a polygon from a table pointer, a command byte and a vertex count. (Chapter 15 does this properly.)

### 7.5 Rules

- Keep the starter's labels. Read every color, vertex and the origin **from the tables in memory**.
- Keep the draw mode `0x400` from `gpu_init` (dither off) and use the opaque commands `20h`/`28h`/`30h`/`38h`.
- Send each GPU word with `sw` to `0x1F801810`.

### 7.6 Hints

- A table word is a 32-bit value: `lw` a coordinate and it is already sign-extended, ready for `pack_vertex`.
- `andi` with `0xFFFF` masks x; `0x7FF` masks the offset coordinates.
- After a `lw`, leave one instruction before you use the loaded register (Chapter 7). A load in a `jal` delay slot is *not* ready for the callee's first instruction.
- Save `$ra` and any `$s` register you use when a routine calls another (Chapter 10).

### 7.7 Stretch goals

Do these in a copy of your project (`cp -r starter stretch`).

- Draw the same Gouraud quad twice: once as one `38h`, once as two `30h` triangles, and compare the seam.
- Overlay a semi-transparent (`2Ah`) quad over the gallery in each of the four modes, side by side.
- Change the origin in the table and watch the whole gallery move without touching any vertex.
- Turn dither on (`E1h = 0x600`) and look at the Gouraud triangle in an emulator zoomed in.

## 8. Verification

```sh
parts/part-03-bare-metal-graphics-in-assembly/ch14-rendering-polygons/verify/verify.sh
```

The verifier calls `pack_color` and `pack_vertex` directly with random arguments, then runs your program on **three galleries** (the shipped tables and two patched ones with different origin, colors, vertices and triangle winding). The probe logs every GP0 word.

| Check | What it means | If it fails |
|---|---|---|
| `program defines main, done, ...` | Labels exist. | A label was deleted. |
| `armips reports no warnings` | Clean build. | Usually a load delay. |
| `program reaches done ...` | No hang, no exception. | Infinite loop or bad address. |
| `pack_color ...`, `pack_vertex ...` | Exact result in `$v0`, `$s` registers untouched. | Top byte leaking; negative `x` overwriting `y`. |
| `the drawing offset: GP0(E5h) ...` | An E5h word with the table's origin before the first polygon. | Offset not set, or x and y swapped. |
| `flat triangle`, `flat quad`, `Gouraud triangle`, `Gouraud quad` | A packet with that command byte, the right length and the right colors and vertices. Any vertex order that draws the same shape is accepted (a triangle in any order; a quad with the same v2-v3 diagonal), and so is a vertex masked to 11 bits instead of 16. Other harmless commands (extra E1h words, fills) are ignored. | Wrong command byte, color order, vertex order, or a command byte on every color word. |
| `each polygon packet is preceded by a read of GPUSTAT` | A status read between packets. | No wait routine. |
| `flat triangle and flat quad ...` | The centroid of each triangle of each flat polygon is its color (tolerance 10). | Polygon missing or in the wrong place. |
| `Gouraud triangle ...`, `Gouraud quad ...` | Seven samples per triangle: near each vertex, the center and between vertices, each compared with the interpolated color (tolerance 20). | A flat color, or colors paired with the wrong vertices. |
| `background untouched ...` | A grid of pixels away from the polygons equals `bg_color`. | Wrong offset, or a stray packet. |

Colors get a tolerance because VRAM keeps 5 bits per channel and the hardware interpolates in fixed point; the tolerances are wide enough for dithered output too. A pass ends with `CHAPTER 14: PASSED (15/15 checks)`.

## 9. Common pitfalls

- **Command byte on every color word.** Only the first color word of a Gouraud packet has it.
- **Outline order for quads.** The order is Z: v1 v2 / v3 v4.
- **Unmasked negative x.** Without `andi x, 0xFFFF` the sign bits wipe out y.
- **Red and blue swapped.** The word is `BBGGRR`.
- **Absolute coordinates with an offset set** (or the reverse): the polygon lands in the wrong place. Pick one.
- **Offset word with the wrong shifts.** E5h is `y << 11 | x`; E3h/E4h are `y << 10 | x`.
- **Wrong count of words.** A packet of the wrong length makes the GPU read your next command as a vertex.
- **Polygons bigger than 1023 x 511** vanish.
- **Load delay in a `jal` slot.** The callee's first instruction does not see the loaded value.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- psx-spx, "GPU Render Polygon Commands" and "GPU Rendering Attributes" (draw mode `E1h`, drawing area `E3h`/`E4h`, drawing offset `E5h`).
- [Appendix C](../../../appendices/C-gpu-commands.md): every GPU command in one place.
- [Chapter 13](../ch13-the-gpu-vram-and-command-packets/README.md) for the ports, state and color order.
- Chapter 15 next: the same packets as reusable routines with arguments on the stack.
