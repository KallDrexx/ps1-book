# Chapter 15: Drawing Subroutines and Stack Parameters

## 1. Concept

A reusable drawing routine takes more arguments than the four registers `$a0`-`$a3` can carry. Under the O32 ABI (Chapter 10) the rest travel **on the stack**, and the routine must find them after it has moved `$sp`.

## 2. Why it matters

Chapter 14 sent polygons word by word, copy by copy. Real code calls `draw_flat_tri(...)` hundreds of times per frame, with seven or more values each. Later, the GTE (Part V) hands you projected vertices and your code turns each one into a call like these. Getting the argument layout, the frame and the register-preservation rules right once means every later chapter can simply call your routines.

## 3. Learning objectives

After this chapter you can:

- say which arguments of a call travel in registers and which on the stack, and at which offsets;
- compute where argument *i* lives inside a callee's own frame;
- spill `$a0`-`$a3` into the caller's home area so all arguments form one array;
- choose between separate `x, y` arguments and packed vertex words, and name the trade-off;
- explain "one GPU wait per packet" and where a routine should put it;
- drive a scene from a data table of typed records.

## 4. Prerequisites

[Chapter 10](../../part-02-thinking-like-the-r3000/ch10-the-stack-and-the-mips-abi/README.md) (frames, `16($sp)` arguments, home area, `$s` registers), [Chapter 13](../ch13-the-gpu-vram-and-command-packets/README.md) (`gpu_clear`'s fifth argument, the bit-26 wait), [Chapter 14](../ch14-rendering-polygons/README.md) (the packets, `pack_color`, `pack_vertex`).

## 5. Explanation

### 5.1 Seven arguments, two homes

`draw_flat_tri(color, x0, y0, x1, y1, x2, y2)` has seven arguments. O32 gives the first four to registers and the rest to the stack, in order:

```
argument:    0      1    2    3    |   4         5         6
name:      color   x0   y0   x1    |   y1        x2        y2
             |      |    |    |    |    |         |         |
           $a0    $a1  $a2  $a3    |  16($sp)   20($sp)   24($sp)     <- $sp as seen AT ENTRY
          (registers)              |  (the caller stored these before `jal`)
```

The rule never changes: argument *i* below 4 is in `$a`*i*; argument *i* from 4 up is at `4*i($sp)` **at entry**, before the callee touches `$sp`. For `gpu_clear` in Chapter 13 that was `h`, argument 4, at `16($sp)`.

All three routines (the two longer ones have nine arguments):

| Routine | Registers (args 0-3) | Stack at entry (args 4-8) |
|---|---|---|
| `draw_flat_tri(color, x0,y0, x1,y1, x2,y2)` | `$a0`=color `$a1`=x0 `$a2`=y0 `$a3`=x1 | `16`=y1 `20`=x2 `24`=y2 |
| `draw_flat_quad(color, x0,y0, x1,y1, x2,y2, x3,y3)` | `$a0`=color `$a1`=x0 `$a2`=y0 `$a3`=x1 | `16`=y1 `20`=x2 `24`=y2 `28`=x3 `32`=y3 |
| `draw_gouraud_tri(c0,x0,y0, c1,x1,y1, c2,x2,y2)` | `$a0`=c0 `$a1`=x0 `$a2`=y0 `$a3`=c1 | `16`=x1 `20`=y1 `24`=c2 `28`=x2 `32`=y2 |

Colours are `0x00RRGGBB`, coordinates are signed numbers, and vertices go into the packet in the order given (a quad's in Z order, Chapter 14). A Gouraud triangle's colour *k* belongs to vertex *k*.

### 5.2 The caller's side

Before `jal`, the **caller** must have stored the stack arguments at the bottom of its own frame, just above the 16-byte home area. So the caller's frame needs room for them: `16 + 4*(number of stack arguments)`, rounded to a multiple of 8, plus whatever else it keeps. `main` in this chapter calls the quad routine with five stack arguments, so its outgoing area is `16..32`.

```
 caller's frame                             higher addresses
 +--------------------------------+
 |  ... saved registers, locals   |
 |  arg 8  y3         (32)        |
 |  arg 7  x3         (28)        |  <- the caller wrote these five words
 |  arg 6  y2         (24)        |     BEFORE the jal (a delay-slot store is fine)
 |  arg 5  x2         (20)        |
 |  arg 4  y1         (16)        |
 |  home area: a3 a2 a1 a0 (12..0)|  <- reserved by the caller, free for the callee
 +--------------------------------+ <- $sp at entry
```

### 5.3 The callee's side: finding the arguments after the prologue

The callee's first act is `addiu $sp, $sp, -F`. From then on `16($sp)` is **its own** area. The caller's words are now `F` bytes higher:

```
 argument i (i >= 4):   at entry  4*i($sp)      after the prologue  (F + 4*i)($sp)
```

Reading `16($sp)` after the prologue gets junk: your own home area for the routines *you* call. This is the commonest bug in this chapter.

**A tidy trick.** The caller's home area, `0..15` at entry, is the callee's to use. Store `$a0`-`$a3` there straight after the prologue:

```
 after the prologue and four stores (F = 24):

   (F + 28)($sp)  arg 7          +-- stack arguments, written by the caller
   (F + 16)($sp)  arg 4          |
   (F + 12)($sp)  arg 3  <-- sw $a3   \
   (F +  8)($sp)  arg 2  <-- sw $a2    |  the home area, filled by YOU
   (F +  4)($sp)  arg 1  <-- sw $a1    |  (the callee is allowed to)
   (F +  0)($sp)  arg 0  <-- sw $a0   /
   ----------------------------------- the caller's $sp at entry
   (F - 4)($sp)   saved $ra   (your frame; locals / saved $s registers below)
```

Now **all** the arguments sit in one array: argument *i* is at `(F + 4*i)($sp)`, whatever *i* is. They survive the calls you make (to `pack_color`, `pack_vertex`, `gpu_wait`), which clobber `$a0`-`$a3` and the `$t` registers; you reload each one just before you need it. No `$s` registers are needed at all, so there is nothing to save and restore except `$ra`.

The alternative is to copy the arguments into `$s0`-`$s7` and save those. It is fine for a few arguments; for nine you run out of registers.

**Frame size.** Your routine calls other routines, so it needs the 16-byte area for them and a slot for `$ra`: 16 + 4, rounded up to a multiple of 8, is `F = 24`.

### 5.4 Separate coordinates or packed words?

The GPU wants `(y << 16) | (x & 0xFFFF)`. A routine could take that word directly:

| | `draw_flat_tri(color, x0,y0, x1,y1, x2,y2)` | `draw_flat_tri_p(color, v0, v1, v2)` |
|---|---|---|
| Arguments | 7: three on the stack | 4: all in registers |
| Caller | stores three values to the stack | has already packed (or kept the table's packed words) |
| Callee | packs each vertex | sends words as they are |
| Cost | more stores, loads and `pack_vertex` calls | fewer instructions, no stack arguments |
| Readability | `x` and `y` are visible | the packing is the caller's job |

Real engines choose packed (the GTE's output is packed already). This chapter uses the **separate** form because stack arguments are the point; the scene table stores **packed** words (compact, 4 bytes per vertex) and `main` unpacks them to call the routines. That is wasteful on purpose: in a stretch goal you write the packed variants and compare.

### 5.5 One wait per packet

Chapter 13 introduced the wait: poll GPUSTAT (`0x1F801814`) until bit 26 is set. psx-spx describes the bit precisely: it is set when the GPU **wants a new command**; when it is clear, the GPU "wants to either receive additional parameters/data or it is busy with command execution". The command FIFO (psx-spx: 64 bytes, 16 words) is what lets you write the parameters at full speed.

So bit 26 is a *between-commands* signal, and that gives the rule:

- **One wait per packet**, before its first word. The biggest packet here has 6 words, inside the FIFO.
- **None between the words of a packet.** Once the command word is in, bit 26 stays clear until the last parameter arrives, so a wait before word 2 never ends. This is not just slow: PCSX-Redux behaves the same way, and a routine that waits before every word hangs after its first word.
- **Inside the routine**, so callers cannot forget it and `main` needs no waits of its own.

Between packets the emulator usually reports ready at once (it draws instantly), so a *missing* wait does not show there; the verifier checks for it anyway. It requires a GPUSTAT read before the first word of each packet and none between its words. Sending through a helper is fine as long as it follows the same pattern.

### 5.6 Where things live: stack, tables, scratch memory

```
 0x00000000  +-----------------------------+   (also seen as 0x80000000 cached, 0xA0000000 uncached)
             | BIOS / kernel data (64 KB)  |   don't touch
 0x00010000  +-----------------------------+   <- your program is loaded here (0x80010000)
             | code, then data (scene...)  |
             | __exe_end                   |
             |   free RAM: your scratch    |   <- no malloc exists; reserve what you need yourself:
             |   buffers, if you need any  |      a .fill in the data, or a fixed address you choose
             |            ...              |
             |   stack (grows DOWN)        |   <- starts at 0x801FFFF0 (common/psxexe.inc)
 0x00200000  +-----------------------------+   end of the 2 MB of RAM
 0x1F800000   scratchpad: 1 KB of fast CPU memory, no cache, usable for hot data
```

There is no operating-system heap on a bare-metal PS1. **Static data** (the scene table) is part of your program. **Stack** memory belongs to running routines and vanishes when they return. **Scratch memory** is a region you pick yourself (for example, a buffer after `__exe_end`, or the 1 KB scratchpad at `0x1F800000`) and manage by hand. Never leave data below `$sp`: a callee, or an interrupt, may overwrite it.

### 5.7 The scene table

A scene is a table in memory that the program walks; the picture is *data*. The verifier replaces the whole table with other landscapes, so nothing about the picture may live in your code.

```
 scene +  0:  count                     number of entries (20..64)
 scene +  4:  background colour         0x00RRGGBB, the clear colour
 scene +  8:  entry 0   (32 bytes)
 scene + 40:  entry 1
   ...

 entry:   +0  type          0 flat triangle, 1 flat quad, 2 Gouraud triangle
          +4  colour0       0x00RRGGBB      (the only colour of a flat polygon)
          +8  colour1       Gouraud only    (0 otherwise)
          +12 colour2       Gouraud only    (0 otherwise)
          +16 vertex0       packed: (y << 16) | (x & 0xFFFF), absolute screen coordinates
          +20 vertex1
          +24 vertex2
          +28 vertex3       quads only      (0 otherwise)
```

Polygons are drawn **in table order**, so later entries cover earlier ones (the painter's algorithm: sky first, mountains, meadow, trees last). The drawing offset stays at (0,0). To unpack a vertex word `v`: `x = (v << 16) >>arith 16` (`sll` then `sra`), `y = v >>arith 16` (`sra`).

The table is declared in `starter/main.s` with a `vtx x,y` macro that builds the packed word. Room is reserved for 64 entries after it.

## 6. Worked example

`example/main.s` is a six-argument routine: `draw_gradient_bar(c0, c1, x, y, w, h)`, which draws a Gouraud quad (`38h`, c0 down the left edge, c1 down the right). It uses the array trick from 5.3: `w` and `h` are read from `(24 + 16)($sp)` and `(24 + 20)($sp)`. `main` stores `w` and `h` at `16($sp)` and `20($sp)` before each call and draws three bars. Predict the picture, then run:

```sh
cd parts/part-03-bare-metal-graphics-in-assembly/ch15-drawing-subroutines-and-stack-parameters/example
make run
```

You should see three 100x40 bars: red to blue, black to white, green to yellow. It is not checked by `verify.sh`.

## 7. Project: Low-Poly Landscape

Work in `starter/main.s`. `gpu_init`, `gpu_clear`, `gpu_wait`, `pack_color`, `pack_vertex` and the scene table are given. You write three routines and `main`.

### 7.1 The routines

Signatures and registers are in 5.1. Each routine must:

1. keep the frame 8-byte aligned and restore `$ra`, `$sp` and every `$s` register it touched (also `$gp` and `$fp`, which you simply do not touch);
2. wait for the GPU **once**, before the first word;
3. send exactly one packet to `0x1F801810`: `20h` (4 words), `28h` (5 words) or `30h` (6 words), with the colour words built by `pack_color` and the vertex words by `pack_vertex` (a colour's top byte is ignored);
4. send nothing to GP1.

### 7.2 `main`

1. `gpu_init`, then `gpu_clear` the whole 320x240 screen with the table's background colour.
2. For each of the `count` entries, in order: unpack the vertices, put the arguments in `$a0`-`$a3` and on the stack, and call the routine for the entry's type.
3. Fall into `done`.

`main`'s frame must be big enough for the largest call (five stack arguments: `16..32`).

### 7.3 Your steps

1. Draw the diagram of 5.3 for `draw_flat_tri` and write down `F` and every argument's offset.
2. Write `draw_flat_tri` and test it from `main` with fixed numbers. Run the verifier: it calls the routine directly.
3. Write `draw_flat_quad` and `draw_gouraud_tri` (the Gouraud one alternates colour word and vertex word).
4. In `main`, walk the table. Start by drawing only type-0 entries, then add the other two.
5. Run the verifier. It replaces the table with two different landscapes, so a hard-coded count or shape fails.

### 7.4 Rules

- Keep the starter's labels and the table format. Everything you draw comes from the table.
- Draw through the three routines, with the arguments as specified. The verifier calls them with its own values.
- Keep `E1h = 0x400` from `gpu_init` (dither off) and use opaque commands.

### 7.5 Hints

- The macros in the example (`send_color`, `send`) save repetition; armips macros take arguments, such as `.macro name,a,b`.
- After `lw`, leave one instruction before using the register (Chapter 7); armips warns about it, and the verifier treats a warning as a failure.
- A store in a `jal` delay slot is a good place for the last stack argument, but a load there is not ready for the callee.
- `main` must keep its own pointer and counter across the calls: use `$s0` and `$s1` and save them in its frame.

### 7.6 Stretch goals

Work in a copy (`cp -r starter stretch`).

- Design your own landscape: replace the entries (at least 20), keeping the format. Keep quads convex and in Z order: the picture checks assume it.
- Write `draw_flat_tri_p(color, v0, v1, v2)` taking packed words and compare the instruction counts with `draw_flat_tri`.
- Add a fourth type, a Gouraud quad (`38h`), as twelve arguments, then as two Gouraud triangles.
- Add `draw_scene(table)`: move the loop out of `main`, so any table can be drawn.
- Put a copy of the table in the scratchpad (`0x1F800000`) and draw from there.

## 8. Verification

```sh
parts/part-03-bare-metal-graphics-in-assembly/ch15-drawing-subroutines-and-stack-parameters/verify/verify.sh
```

The verifier calls each routine **directly**: arguments 0-3 in `$a0`-`$a3`, the others stored at `16($sp)` and up, junk in the home area and above the arguments, sentinels in `$s0`-`$s7`/`$gp`/`$fp`, `$ra` aimed at a return trampoline. It logs every GP0/GP1 write. Then it runs the real program on **three scenes**: your table (read back from memory) and two landscapes it writes over `scene` (26 and 20 polygons, other shapes, colours, vertex orders). The random seed is printed on failure. A run that writes thousands of GPU words or polls GPUSTAT tens of thousands of times without reaching `done` is stopped at once and reported as a `runaway`.

| Check | What it means | If it fails |
|---|---|---|
| `program defines main, done, ...` | Labels exist. | A label was deleted. |
| `armips reports no warnings` | Clean build. | Usually a load delay. |
| `draw_flat_tri ...`, `draw_flat_quad ...`, `draw_gouraud_tri ...` | Exactly one packet with the right command and words (any equivalent vertex order, 11-bit masking accepted). | Wrong stack offset, command byte on every Gouraud colour word, missing colour, bad Z order. |
| `ABI: ... unchanged` | The routine returns and `$sp`, `$s0`-`$s7`, `$gp`, `$fp` are as at entry. | An `$s` register used but not restored; `$sp` not restored. |
| `one GPU wait per packet ...` | GPUSTAT read before the first word, none between the words. | No wait. (A wait between words hangs instead: see the `done` row.) |
| `program reaches done ...` | No hang or CPU exception. | Wrong frame size or lost `$ra` (`runaway: ... GPU words`), a wait between the words of a packet (`runaway: ... GPUSTAT reads`). |
| `the scene table has at least 20 polygons ...` | Your shipped table is valid. | Count word below 20 or an unknown type. |
| `the program sends the table's polygons ...` | The polygon packets, in order, match the table, in all three scenes. | Count hard-coded, type dispatch wrong, vertices unpacked wrongly (unsigned!). |
| `every routine is called ...` | `main` calls each routine for its type. | Drawing inline instead of calling. |
| `the picture ...` | Sample points inside polygons (3 px from any edge) have the colour of the topmost polygon there (interpolated for Gouraud; tolerance 10 flat, 20 Gouraud). | Wrong draw order, colours, or position. |
| `background untouched ...` | Points away from all polygons equal the table's background colour. | Screen not cleared with the table colour, or a stray packet. |

Colours have a tolerance because VRAM keeps 5 bits per channel. A pass ends with `CHAPTER 15: PASSED (13/13 checks)`.

## 9. Common pitfalls

- **Reading `16($sp)` after the prologue.** After `addiu $sp, $sp, -F` the caller's arguments are at `F + 4*i`.
- **Forgetting the stack arguments in the caller.** `main` must store them before each `jal`: a stale `16($sp)` from the previous call is used otherwise.
- **Too small an outgoing area.** Five stack arguments occupy the words at `16..32`, so saved registers go at `36` or above; otherwise the arguments overwrite them.
- **Using `$a0`-`$a3` after a `jal`.** They are caller-saved: reload them from your array.
- **Clobbering `$s` registers.** `main`'s pointer and counter live in `$s0`/`$s1`; a callee that uses them without saving breaks the loop.
- **Unsigned unpacking.** `srl` instead of `sra` turns a negative coordinate into a huge number.
- **One wait per word.** Bit 26 stays clear until the packet is complete, so the second wait never ends.
- **A frame that is not a multiple of 8.** Keeps `$sp` aligned, as Chapter 10 requires.
- **Load delay in a `jal` slot** (Chapter 14): the callee's first instruction does not see the loaded value.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- Chapter 10's ABI section (home area, frame layout) and Chapter 13's `gpu_clear`.
- psx-spx, "GPU Rendering Commands: Polygons", "GPUSTAT (1F801814h)", "Memory Map", "Scratchpad".
- Any MIPS O32 ABI summary ("See MIPS Run", the System V MIPS ABI): the argument-passing rules used here.
- Chapter 16 next: moving image data into VRAM.
