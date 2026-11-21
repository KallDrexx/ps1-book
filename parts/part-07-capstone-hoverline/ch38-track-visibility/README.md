# Chapter 38: Track Visibility

## 1. Concept

So far the game draws **every section of the track, every frame**, although the player sees a tenth of it. This chapter finds out **which section the ship is nearest to** and draws only a **window** of sections around it: some ahead, a few behind. Finding the section is a small search problem with a fast path (the ship is almost always in the same section as last frame, or in a neighbour) and a slow path (the first frame, or a teleport). The picture gets a **debug readout** (`SEC 098  PRIMS  124`) so you can watch it work.

## 2. Why it matters

Chapter 36's subdivision and Chapter 37's ship push the frame past one vertical blank, so the game runs at 30 frames per second. The cheapest primitive is the one you never build: culling by *section* is the first and biggest saving, long before any per-face test. The **nearest section** is also the game's main spatial index. Chapter 40 asks which road edges are near the ship and Chapter 41 how far along the lap it is. Both start from `ship_section`.

## 3. Learning objectives

After this chapter you can:

- explain why a loop of sections is treated as a **ring** and take `next` / `prev` links across the lap boundary;
- define a **distance metric** exactly (squared, 3D, 64-bit, ties to the lowest index) so that two implementations agree on every input;
- find the nearest section by **brute force** and then **incrementally** through the links;
- decide **when the fast path cannot be trusted** (teleports, fast flight, leaving the road) and fall back;
- render a **window** of `N` sections ahead and `M` behind with wrap-around, and compare it with a precomputed **visibility list**;
- show a live **debug readout** with the SDK font and count the primitives of a frame;
- **measure** a frame against the vertical-blank budget.

## 4. Prerequisites

[Chapter 23](../../part-05-three-dimensions-with-the-gte/ch23-fixed-point-math/README.md) (fixed point, squared distances and their overflow), [Chapter 22](../../part-04-c-on-the-playstation/ch22-controller-input-and-the-bios/README.md) (edge-triggered input), Chapters [34](../ch34-track-geometry/README.md) (sections, the face buckets, `track_stats`), [35](../ch35-track-texturing/README.md) (the VRAM plan), [36](../ch36-polygon-subdivision-and-tessellation/README.md) (the primitive budget), [37](../ch37-ship-movement-and-physics/README.md) (the ship, the fixed time step) and Appendix E.10 (`.TRK` sections, E.10.5 the visibility block).

## 5. Explanation

### 5.1 Why a window: the numbers

Measured on this chapter's solution with the emulator's cycle counter: **work** is everything from the start of a frame to the call of `VSync(0)`: input, physics, the section update, drawing the track, the ship and the readout, and `DrawSync`'s wait for the GPU. One NTSC vertical blank is **566,120** CPU cycles. All rows use the same 110 poses (the first 110 of the verifier's lap, 5.9).

| Frame (110 posed frames) | Sections | Packets (mean / max) | Work, cycles (mean / max) | Share of a blank | Frames over one blank |
|---|---|---|---|---|---|
| Whole track (Chapter 37) | 112 | 179 / 294 | 563,758 / 716,016 | 100% / 126% | 47% |
| Window 24 ahead, 4 behind | 29 | 117 / 128 | 244,551 / 270,565 | 43% / 48% | 0% |
| Window 9 ahead, 2 behind | 12 | 63 / 68 | 133,061 / 154,461 | 24% / 27% | 0% |
| Window 24 + 4 **with** Chapter 36 subdivision | 29 | 341 / 382 | 592,499 / 675,301 | 105% / 119% | 88% |

Three lessons. The window gives back more than half the frame. Work is roughly proportional to the **packets**, so the section count is the lever. And subdivision **still does not fit**, even with the window: it stays **off by default** (the R1 toggle remains).

**What these numbers leave out.** The emulator does not charge for the GPU's *rasterisation*: its `DrawSync` returns almost at once. On a console the program sends the table and then waits in `DrawSync` until the GPU has filled every pixel, so a real frame is this work **plus** the fill time, which depends on the screen area covered and the overdraw rather than on the packet count. 43% is therefore a CPU figure and a lower bound: the 57% left is the room the GPU has. This book does not measure the fill time.

### 5.2 The ring and the window

The sections form a **loop**. Section `i` links to `next` (forward) and `prev` (back); the last section's `next` is 0.

```
 the ring (112 sections), drawn as a strip that wraps; s = ship_section = 2:

   ... 108 109 | 110 111   0   1  [2]   3   4  ...  26 | 27  28 ...
               |<--- 4 behind --->| s |<-- 24 ahead -->|
                        ^ next(111) = 0: the lap boundary

 drawn: 110, 111, 0, 1, 2, ..., 26  (29 sections)
```

The window drawn for section `s` is

| Quantity | Rule |
|---|---|
| sections | `s - vis_behind .. s + vis_ahead`, indices **modulo** `section_count` |
| `first` | `(s - vis_behind) mod n` (a non-negative remainder) |
| `count` | `vis_behind + vis_ahead + 1` |
| too wide | if `count >= n`: `first = 0`, `count = n` (everything, each section once) |
| negative inputs | `vis_ahead` or `vis_behind` below 0 counts as 0 |

Defaults `VIS_AHEAD` 24 and `VIS_BEHIND` 4 are the manifest's `vis_rule` (E.10.5). Both are variables (`vis_ahead`, `vis_behind`) so the verifier can patch them. The sections drawn **ahead** matter most: the camera looks forward and the road recedes. The few behind keep the road under and just behind the camera.

### 5.3 The nearest section: one exact metric

"Nearest" must mean the same thing in every implementation, or the verifier cannot compare. This chapter's metric:

```
d2(i) = dx*dx + dy*dy + dz*dz     with  d = pos - centre(i)   per axis
```

- **3D**, not the XZ plane: the ship hovers above the road and the track climbs; the heights agree between neighbours.
- **Squared**: no square root; the order of distances is the order of their squares.
- **64-bit**: compute each `d` and each square in a 64-bit integer. A ship only 65,536 units from a centre already squares past `u32`, and a ship that has left the track is exactly the case that happens (the verifier flies it 150,000 units away). 64 bits hold the sum of three squares while every `|d|` is below 2^31, far beyond any world the format allows. On the R3000 a 32 x 32 to 64 multiply is one instruction; `int64_t` costs a few more cycles, nothing else.
- **Ties** go to the **lowest index**.

The **brute-force search** is a loop over every section with a strict `<` (so the first, lowest index, keeps a tie). For 104 to 112 sections it costs about **17,600 to 21,300 cycles** in the solution (3 to 4% of a blank): cheap, but not free, and it grows with the track.

**What "nearest" is not.** The nearest *centre* is not always the section the ship is *over*. The boundary between two sections' "nearest" zones is the plane halfway between their centres, while the road's boundary is the ring between them; on a bend, a bank or a change of section length the two differ, so near a ring the answer can be the neighbour. For choosing what to draw that does not matter (the window is 29 sections wide). It matters for Chapter 40's collision, which needs the section whose edges are beside the ship: it starts from `ship_section` and has to test the neighbour too when the ship is past a ring.

### 5.4 The incremental update

Between two frames the ship moves at most 60 units per tick; a section is about 1000 long. So the nearest section is almost always **the one it was**, or a neighbour. Test those three and follow the links:

```
 cur = last frame's section
 repeat:
     candidates = { prev(cur), cur, next(cur) }
     best = the smallest (d2, index) among them          <- index breaks ties
     if best == cur: stop
     if this would be move 5 (VIS_MAX_STEPS = 4 moves allowed): give up (5.5)
     cur = best                                           <- one move
```

Rules that matter:

- **Use the links**, `sections[cur].next` and `.prev`, never `cur + 1`: the lap boundary is `111 -> 0` and, in another track, the link could do something else (the format has a reserved `JUNCTION` flag).
- Comparing the pair **(d2, index)**, not only `d2`, makes a tie deterministic and makes the walk **terminate**: the pair strictly decreases at every move.
- A fast ship (several sections per frame) simply needs more moves. After `VIS_MAX_STEPS` moves, give up and search everything (5.5).
- A normal frame costs three to five distances, about **650 to 2,400 cycles** here (median 1,100) against 17,600+ for a full search. The verifier measures it.

### 5.5 Teleports and being lost

The walk is a **hill climb**: it follows the distance downhill. That finds the nearest section when the distance has one valley around the ship. It fails when the ship jumps (a respawn, a debug warp), and a **local minimum** can trap it: a section closer than both its neighbours but not the nearest, for example where the loop passes close to itself. Two rules limit the damage:

| Situation | Rule |
|---|---|
| `cur` is not a section (`-1` at boot, or out of range) | brute force |
| the walk wants a **5th move** | brute force |
| the walk stops, but the section is **farther than `vis_lost`** (4000 units, `d2 > vis_lost^2`) | brute force |
| otherwise | the walk's answer |

The third rule is the safety net: a ship **on the road** is within a few hundred units of its section, so a result 4000 units away is not trustworthy and flight far off the road gets the exact answer, at the price of a full search each frame (only 3% of a blank). The rules are not a proof: a local minimum *within* 4000 units would be kept. On the book's two tracks no part of the loop comes back within that distance, and on every pose of the verifier's laps the rule's answer equals the brute-force one; a track that doubles back closely would need a smaller `vis_lost` or a periodic full search. `vis_lost` is a variable the verifier can patch.

Brute force is also the **initial value**: `set_state` calls it right after `ship_place`.

### 5.6 What the window reuses from Chapter 34

Vertices near (and far from) the camera need nothing new; the window sits in front of Chapter 34's rules:

- A vertex more than 32,767 units from the eye in any axis is **far** and its faces are skipped (not clamped). With 24 sections ahead (about 24,000 units) the far rule rarely fires, but it is still the safety net.
- A face with a vertex nearer than `TRK_NEAR_Z` = 128 is skipped (**near**), faces facing away (`NCLIP`) and oversized faces (1023 x 511) likewise: Chapter 34's buckets, unchanged.
- `track_draw` is cut into `track_draw_begin` (reset the statistics, load the rotation into the GTE) and `track_draw_section` (the five faces of one section). `track_draw(first, count)` is those two in a loop, so a **window** and a **list** are two ways to call the same code.

The ring vertices are shared, so a window touches the vertices of rings `first .. first + count` (one more ring than sections). The verifier uses that: after the frame, the vertices that `trk_vstate` marks as *seen* are exactly those of the faces of the window.

### 5.7 The readout and the primitive count

`prims_this_frame` is the number of **GPU packets linked for the track and the ship**: `prims_submitted` right after `draw_ship`, before the text. The readout is one line, **`SEC nnn  PRIMS nnnn`**:

```
SEC  98  PRIMS  124        ("SEC %3d  PRIMS %4d": the section in 3 columns, the packets in 4)
```

It is written into `vis_text` (31 characters at most), from `ship_section` and `prims_this_frame` of the **same** frame.

The SDK has a bitmap font. `FntLoad(x, y)` uploads it once; the book puts it at **`FntLoad(960, 0)`**: VRAM x 960..991, y 0..31 plus its palette just below, in the free area Chapter 35's `vram_layout.md` left for it. To draw the line **on top of the track**, sort its characters into the *nearest* slot of the ordering table (the table is drawn from slot 63 down, so slot 0 is drawn last): `FntSort(ot, buffer, x, y, text)`, with the table entry from the new `ot_slot(0)` of this chapter's `psxe` copy, and a buffer from `ot_alloc`. Within one slot the packet linked last is drawn first, so a road face that also lands in slot 0 (just in front of the camera, at the bottom of the screen) would cover the text; at the top-left corner there is none. Each character is one 8 x 8 sprite packet (about 16 bytes); the readout line is therefore *not* in `prims_this_frame` (the verifier's walk of the table finds `prims_this_frame` packets plus the characters).

`FntPrint` / `FntFlush` draw immediately, **before** the table is drawn, so the track would cover them: that is why this chapter sorts the text itself.

### 5.8 The alternative: a precomputed visibility list

The `.TRK` carries a **visibility list** (E.10.5): for every section `i`, a slice `vis[vis_first .. vis_first + vis_count - 1]` of the sections to draw. On the generated tracks it holds the same 24 ahead and 4 behind, **plus** any section whose centre is within six average lengths (the manifest's `vis_rule`: meant for a road that passes close to itself across a bend). On the book's two tracks no other part of the loop is that close, so the only extras are the 5th and 6th sections behind: track 1's lists have 30 or 31 entries, and list mode draws almost the window.

| | Window | List |
|---|---|---|
| Needs the loop order | yes | no |
| Handles a track that doubles back | no: a nearby parallel road is outside | yes, if the generator put it there |
| Data | two numbers | `vis` table in the file |
| Cost to build | none | done offline, by the tools |

`vis_mode` 0 is the window (the main path), 1 is the list (**stretch**, 7.6). Either way the *section* is what selects the set.

### 5.9 How the verifier drives a lap

Nothing collides yet: the ship flies straight and leaves the road, so a lap cannot be flown with the pad. The probe **poses the ship**:

1. At the end of every frame (the program's `frame_done`), the probe writes the next pose into `ship`: `pos` (on the centre line, with a lateral sway and the hover height), `yaw` along the road, `speed` 0.
2. The pad is idle and the speed 0, so `ship_update` leaves the pose alone. The game then runs the chase camera, **your update**, the draw, the readout.
3. At the next `frame_done` the probe records the row: `ship_section`, the counters, the vertices the frame touched, the packets of the ordering table, the frame's work in cycles, and which vertical blanks passed. The verifier also checks that `ship.pos` is still the pose it wrote.

The script, generated from the `.TRK`: smooth running over the **lap boundary** (111 to 0); a fast stretch (2.2 sections per frame, then 6.5, beyond the walk); **teleports**; a run **backwards**; a trip **off the road** (up to 6000 units to the side) and one **far away** (150,000 units); and a whole lap. The second run is track 2, translated by (+60000, 0, +45000) with a different script.

## 6. Worked example

Track 1, ship at the start pose (23829, -746, 487). Section centres: 111 is (23649, -512, -463), 0 is (23883, -639, 496), 1 is (23874, -765, 1487).

| Section | d2 |
|---|---|
| 111 | 989,656 |
| 0 | **14,446** |
| 1 | 1,002,386 |

Brute force gives **0**. Move the ship 700 units along the road, to (23953, -728, 1186): `d2` is 2,858,273 (111), 488,921 (0), **98,211 (1)**, 1,729,796 (2). From `cur` = 0 the walk looks at 111, 0, 1: section 1 wins, one move. The next step looks at 0, 1, 2: section 1 stays. Stopped, 98,211 is below 4000^2: the answer is 1.

The window for `s` = 2, 24 ahead and 4 behind: `first = (2 - 4) mod 112 = 110`, `count = 29`: sections **110, 111, 0, 1, 2, ..., 26**. `example/vis_ref.py` is this chapter's reference model: `nearest`, `update`, `window` in Python integers; the verifier uses it, and `"$PS1BOOK_PYTHON" example/vis_ref.py` prints this example.

## 7. Project: windowed track rendering

### 7.1 Behaviour

Chapter 37's game. The picture is now the track **window** around the ship, the ship, and the readout at the top-left. Fly with X and the arrows as before: the section number counts up, the packet count stays near 100 to 130, and the frame rate stays at 60. **Select**, **Triangle** and **R1** work as before.

### 7.2 The contract

`starter/` is Chapter 37's `solution/` with the new wiring done and the work stubbed. **Read `track_vis.h` first: it is the specification.** **Given:** everything of Chapter 37; `track_draw_begin` / `track_draw_section`; `game_update` (the update and the brute-force first value on entering the game), `draw_track` (window, ship, counter, readout); `FntLoad(960, 0)` in `main`; `ot_slot` in the `psxe` copy; the state variables. **You write**, in `track_vis.c`:

| Function | What |
|---|---|
| `track_nearest_brute` | the exact metric over every section; counts `vis_brute_runs` |
| `track_nearest_update` | the walk of 5.4 and the fall-backs of 5.5 |
| `track_window` | `first` / `count` of 5.2; sets `vis_first` / `vis_count` |
| `vis_readout_format` | the line of 5.7 into `vis_text` |
| `track_draw_list` | *stretch*: the list of 5.8; set `vis_list_done = 1` |

**State the verifier reads and patches** (names and types fixed):

| Symbol | Meaning |
|---|---|
| `ship_section` | `int32_t`, the nearest section; -1 before the game starts |
| `prims_this_frame` | `int32_t`, packets of the track and the ship in the last frame |
| `vis_ahead`, `vis_behind` | `int32_t`, default 24 and 4; **patched** |
| `vis_mode`, `vis_lost` | 0 / 1; 4000; **patched** |
| `vis_first`, `vis_count` | the window (or list) drawn in the last frame |
| `vis_brute_runs` | full searches since boot |
| `vis_text` | `char[32]`, the readout line |
| `vis_list_done` | 1 if the stretch goal is implemented |
| `ship` | the posed state (14 words, as Chapter 37) |

The probe hooks the entry and return of `track_nearest_update` to count its cycles: keep it a function of its own, in its own file.

### 7.3 Steps

1. **The metric and the brute-force search** (5.3). With only this, `starts_in_the_game` passes; temporarily call it every frame to see the section number follow the ship.
2. **The window** (5.2). The readout shows the packets fall by more than half.
3. **The update** (5.4, 5.5): the walk, then the two fall-backs. `nearest_section_main_lap` and `teleports_recover` are the tests.
4. **The readout text** (5.7). `readout_text` and `readout_on_screen`.
5. **Measure**: `frame_budget_main` and `window_is_cheaper_than_the_whole_track`.

### 7.4 Rules

- The metric is **exactly** 5.3: 3D, 64-bit, ties to the lowest index.
- The update uses the **links**, not `+ 1`, and makes a normal frame cost a few distances. **A full search every frame gives the right answers but fails the verifier**: `update_uses_the_links_not_the_whole_track` allows only the full searches the rule of 5.5 needs (+3) and 8,000 cycles for an update without one. This is a rule of the exercise, not of the frame rate (a full search is 3 to 4% of a blank on these tracks): the incremental walk is what the chapter teaches, and its cost does not grow with the track.
- Draw the window of `vis_ahead` and `vis_behind` as they are **now**: they are read each frame.
- `prims_this_frame` is read *before* the readout is added.
- No new global limits: nothing is hard-coded to track 1 (112 sections) or to its position.

### 7.5 Hints

- `(int64_t) a - b` widens **before** it subtracts. `(int64_t) (a * b)` widens after the product has already overflowed.
- `((x % n) + n) % n` is the non-negative remainder in C.
- Keep `best` and its distance in two variables, and compare the distance first, the index second.
- A section's links are `uint16_t`; compare them as `int`.
- Print the numbers with `snprintf(vis_text, sizeof vis_text, "...")`; `%3d` and `%4d` need `int`, not `int32_t` on every compiler (cast).

### 7.6 Stretch goals

- **The visibility list** (5.8): `track_draw_list`, `vis_list_done = 1`. The verifier then runs with `vis_mode = 1` and compares the vertices touched with the section's slice.
- **A two-step update** that looks at `next(next(cur))` and `prev(prev(cur))` before moving: fewer iterations on fast flight.
- **Draw order of the window**: far to near is automatic (the table sorts it); but you can *stop* the window at the first section beyond `TRK_FAR_LIMIT`.
- **A dynamic window**: grow `vis_ahead` while the frame has spare cycles, shrink it when `frame_ticks` exceeds 1.
- **Subdivision inside the window**: the near level only: how many frames does that fit?

## 8. Verification

```sh
source tools/env.sh
parts/part-07-capstone-hoverline/ch38-track-visibility/verify/verify.sh            # your starter/
parts/part-07-capstone-hoverline/ch38-track-visibility/verify/verify.sh --solution # the reference
```

About one minute: a build and up to five emulator runs from the disc image, all driven by the probe's poses (5.9): **main** (track 1, the whole script, 335 frames), **whole** (the first 110 poses with the window wider than the track), **narrow** (`vis_ahead` 9, `vis_behind` 2, patched at the entry of `main`), **alt** (track 2 translated by (+60000, 0, +45000), a different script) and **list** (`vis_mode` 1; skipped unless `vis_list_done` is 1).

| Check | What it means | If it fails |
|---|---|---|
| `starts_in_the_game` | the first `ship_section` is the brute-force answer for the start pose; the probe's poses are seen (`ship.pos`) | the metric, a missing first search |
| `nearest_section_main_lap` | on every frame of the lap `ship_section` equals the reference (first gate: 99% of frames and every miss fixed the next frame; then all of them) | the first wrong pose, its kind, got and wanted |
| `teleports_recover` | right on the teleport frame **and** the next | no fall-back |
| `update_uses_the_links_not_the_whole_track` | full searches are at most the frames that need one (+3); an update without a full search is under 8,000 cycles (measured at most 2,000) | searching every frame |
| `window_rule_main`, `window_rule_patched` | on every frame: `first` and `count` follow the rule; `track_stats` sees 5 faces per section; the vertices `track_draw` touched are **exactly** those of the window (also 9 / 2 and "wider than the track"); windows that wrap occur | off-by-one, no wrap, ignoring the patched variables |
| `prim_counts` | `prims_this_frame` equals the packets in the frame's ordering table (readout characters excluded), the ship's share is plausible, at most 170 in any frame, guard bytes intact | counting after the readout, whole-track drawing |
| `frame_budget_main` | between every two frames of the lap **exactly one** vertical blank; the busiest frame's work is under 540,000 cycles | window too wide |
| `window_is_cheaper_than_the_whole_track` | mean work of the window under 85% of the whole-track run on the same poses | a window of 100+ sections |
| `alt_disc_track_2_translated` | the lap of the other track matches the reference, the window rule holds, every frame under the cycle limit | 32-bit squares (far poses), hard-coded 112 |
| `readout_text` | `vis_text` is `SEC %3d  PRIMS %4d` of that frame | format, wrong frame |
| `readout_on_screen` | the font is in VRAM at (960, 0); in two screenshots every character cell at (8 + 8 i, 8) holds white pixels | font not loaded, drawn under the track |
| `stretch_visibility_list` | only when `vis_list_done` = 1: the vertices touched equal those of the section's slice | wrong slice |

A pass ends with `CHAPTER 38: PASSED (13/13 checks)`. The untouched starter fails. So do: a stale section (the update returns `cur`), no wrap in the window (`first` clamped to 0), an off-by-one count (`ahead + behind`), 32-bit squared distances (the stretch 150,000 units away), and a window of 40 ahead. Searching **every** frame passes the correctness checks but fails the update-cost check (7.4).

## 9. Common pitfalls

- **`cur + 1` for the next section.** It works until the lap boundary (and fails on any track that is not a simple loop).
- **A negative remainder.** In C `-2 % 112` is `-2`. Add `n` and take the remainder again.
- **32-bit squares.** Fine on the first track near the origin, wrong as soon as the world is shifted; the verifier shifts it.
- **A tie broken by the scan order of the walk.** Compare `(d2, index)`, or two equal answers differ by one section.
- **Trusting the hill climb after a jump.** It stops on a local valley. The 5-move limit and `vis_lost` are there for it.
- **Counting the readout.** `prims_this_frame` is read before `FntSort`.
- **`FntFlush` for the text.** It draws before the table: the track covers it.
- **Window too small ahead.** The road pops in at the horizon; 24 is the book's choice, not a law.
- **Forgetting the whole-track case.** A window wider than the track must not draw a section twice.
- **Believing subdivision fits now.** Measured: it does not. R1 is off by default.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- Appendix E.10.4 (section links), E.10.5 (the visibility list and `vis_rule`), E.10.2 (camera-relative vertices).
- Chapter 40 (the road's edges of the nearest section), Chapter 41 (laps: the same index drives the lap counter).
- Ericson, *Real-Time Collision Detection* (spatial partitioning); the "portal" and "potentially visible set" ideas behind precomputed lists.
- psx-spx, "GPU Display Control Commands" and "Timers": the frame period the budget is measured against.
