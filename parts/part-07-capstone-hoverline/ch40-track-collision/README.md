# Chapter 40: Track Collision

## 1. Concept

The ship stays on the road because every physics tick the program asks four questions of the track data: **which section am I over, how far am I from each road edge, what is the ground under me, and which face is it**. A signed distance (a dot product with an edge's normal) answers the second; a push along that normal, a damped speed and a corrected heading are the response.

## 2. Why it matters

Until now *Hoverline* has let you fly through the walls. Collision is where the track stops being a picture and becomes a **model**: the same vertices that were drawn now decide where the ship may be. Racing games live on this: the feel of a wall scrape (how much speed it costs, how it turns you along the wall instead of stopping you) is a design decision made in a dozen lines of fixed-point maths, and it has to cost almost nothing on the frames where nothing is touched.

## 3. Learning objectives

After this chapter you can:

- use a **cross product as a signed distance** from a line (a dot product with the perpendicular) and derive the line's unit normal, with no floating point and one integer square root;
- find a section's **road edges** from its vertex indices (E.10.4), and give irregular sections a **fallback**;
- decide which section a point is **over** with the two **ring lines**, walking to the neighbours, and say why that differs from Chapter 38's nearest centre;
- put the ship at a **hover height above a banked, sloping road** (a plane from the section's `up`);
- implement the **response to a wall**: positional push-back, speed damping by impact angle, a heading correction by the **shortest** angle, and a quiet-time rule for the thud;
- use **face flags** (a boost pad's impulse on *entry*), respawn a ship that is far outside, and **swap the track** loaded from the disc without leaking or breaking the one you have.

## 4. Prerequisites

[Chapter 34](../ch34-track-geometry/README.md) (the `.TRK` structures), [37](../ch37-ship-movement-and-physics/README.md) (the ship: `yaw`, `speed`, `ship_update`), [38](../ch38-track-visibility/README.md) (`ship_section`, the nearest section), [39](../ch39-audio/README.md) (`audio_event`, the thud and the chime), and Appendix E.10 (the `.TRK` format, E.10.4 for the collision recipe). This chapter starts from Chapter 39's `solution/`.

## 5. Explanation

### 5.1 What the tick asks

```
 ship_update(...)                 Chapter 37: the ship moves along its heading (it may now be through a wall)
      |
 collide_ship(&track, &ship)      this chapter, once per TICK (a frame may run up to 4)
      |
      +-- 1  section        which section is the ship over?             collide_section   (5.4)
      +-- 2  edges          distance to the left and right edge          collide_edges, collide_edge_dist (5.2, 5.3)
      +-- 3  off the track  more than off_limit outside?  respawn        collide_respawn   (5.7)
      +-- 4  walls          closer than radius?  push, damp, turn, thud  (5.7)
      +-- 5  ground         y = road surface - hover                     collide_ground    (5.5)
      +-- 6  face           on a boost face?  impulse on entry           collide_floor_face (5.6)
```

It runs after **every tick**, not once per frame: the ship moves at most 72 units a tick (60 units at the cap, times PAL's 1.2), less than the 90-unit `radius`, so a ship pushed back to the radius never gets its centre past an edge line before the next test. One call per slow frame (up to four ticks, 288 units) would let it end the frame on the far side of the wall.

World axes as always: +X right, +Y **down**, +Z into the screen. The road is tested in the **XZ plane** (the view from above); Y matters only for the ground height. Distances are whole world units, normals and fractions are 4.12.

### 5.2 A signed distance: the dot product, once more

The dot product of a vector with a **unit** vector `n` is how far it reaches along `n`. So the distance of a point `p` from a line through `a` with unit normal `n` is `dot(p - a, n)`: positive on the side `n` points to, negative on the other, zero on the line. That is the whole of wall collision: the line is a road edge, the side is "the road".

We do not have `n`; we have the edge `a -> b`. Its **perpendicular** is `(-ez, ex)` where `e = b - a`, and the dot product with the perpendicular is the 2D **cross product**:

```
   cross(v) = ex * vz - ez * vx          (= dot(v, (-ez, ex)))
   len      = isqrt(ex*ex + ez*ez)       the edge's length: floor(sqrt), the one square root of the chapter
   dist     = cross(p - a) / len         the signed distance, in units
   n        = (-ez, ex) * 4096 / len     the unit normal, 4.12
```

Which side is positive? The one the **reference point** `r` is on (for the left edge, the right edge's start): `s = -1 if cross(r - a) < 0 else +1`, then `dist = s * cross(p - a) / len` and `n` is multiplied by `s` too. The sign is never derived from the winding or from "which side is left", so it is right on a bend, on a mirrored track, wherever the generator puts the points.

```
   a                                    b          a = (0, 0), b = (1000, 0), r = (500, 700), p = (300, 40)
   +------------------------------------>         e = (1000, 0), len = 1000, cross(r - a) = 700,000 > 0: s = +1
   |   n = (0, 4096)                               cross(p - a) = 1000 * 40 = 40,000   ->   dist = 40
   |   p .  (40 units inside)                      n = (0, +1.0): along +z, toward r   (quiz 1)
   |   r .
```

All `C` divisions here **truncate toward zero** (as `/` does): `-7 / 2 = -3`. Every difference `p - a` is **clamped** to `-32767 .. 32767` per axis before it is multiplied: a ship that was teleported 100,000 units away must not overflow a 32-bit product (`8192 * 32767` fits; the program assumes edges shorter than 8192 units, the generated ones are about 1100).

`collide_isqrt` (floor of the square root, digit by digit) is **given**.

### 5.3 The road edges

Appendix E.10.4: a section's `edges[]` hold four vertex indices, `left_start, right_start, left_end, right_end`: the road's two edges as two segments in the world, and the **ring lines** between sections (`left_start -> right_start` is the start ring, `left_end -> right_end` the end ring). `collide_edges` fetches their XZ coordinates into a `CollideEdges`:

```
        left_start p0 ------------------ left_end p2         p[k] = { x, z } of vertices[edges[k]]
              |   section (the road is between)  |
        right_start p1 ----------------- right_end p3
   forward ->
```

**Irregular sections.** The recipe needs two things: each edge must have a length, and the opposite vertex must not lie on its line (else the reference side is undefined). A section where either fails is *irregular*; the generated tracks have none, but the format promises nothing about other tracks (and the verifier makes some). For it, **both** edges are replaced by the section's frame: left start `centre - right * half_width`, right start `centre + right * half_width`, each end = its start `+ forward * length` (per axis, `(r * w) >> 12`; the *negated* product is shifted for the left, so the shifts round the same way as the model). `collide_edges` returns 1 when it used the fallback.

**Debug print.** `collide_format` writes `L%5d R%5d F%3d` (the distances to the left and right edge as measured at the start of the tick, and the floor face index) into `collide_text`; `game.c` sorts it under the `SEC / PRIMS` line with `FntSort`. Drive along a wall and the right distance sits near 90. (PSn00bSDK's `printf` pads a negative `%5d` *after* the sign: `-38` prints as `-  38`. A libc quirk, not yours; the verifier ignores spaces.)

### 5.4 The section the ship is over

Chapter 38's `ship_section` is the section with the **nearest centre**, and its text warned that this is not always the section the ship is over: the nearest-centre boundary is the *bisector plane* between two centres, while the section boundary is the **ring**, and the two coincide only when the sections on both sides of the ring are the same length and the bend is symmetric. On the generated tracks they nearly do: of 4,000 random points on the road, five were nearest to one section and over another, all within one unit of a ring. Nothing in the format promises it (the verifier stretches section 40 to 1405 units and shrinks section 41 to 605: in a band 200 units wide the nearest centre is the wrong section, and the wrong section has the wrong edges).

A section's **slab** is the part of the plane between its start ring line and its end ring line. With `ds` the distance from the start ring line (positive toward the end ring) and `de` from the end ring line (positive toward the start ring), both from `collide_edge_dist`:

```
   de <= 0  : past the end ring  -> the ship is over `next`
   ds <  0  : before the start ring -> over `prev`           (a point ON the end ring is next's, on the start ring is this section's)
   otherwise: this section
```

`collide_section(t, cur, pos)` starts from last tick's section and **walks** by the links (`next`, `prev`, never `index +- 1`: the lap boundary 111 to 0), at most `COLL_WALK` = 4 moves. A walk that still wants to move gives up, and so does a `cur` that is not a section: then Chapter 38's `track_nearest_brute` picks a start and a second walk runs; whatever it stops on is the answer. A ship that drives normally moves one section at most per tick, so the answer costs one or two looks (median 1,300 instructions; a teleport 12,000).

`ship_section` is now this answer, written by `collide_ship` every tick (the visibility window of Chapter 38 follows it). `track_nearest_update` is no longer called.

### 5.5 Ground height and hover

The road under the ship is the plane through the section's `centre` with normal `up` (E.10.4: 4.12, `-y` is up). A point `d = p - centre` is on the plane when `dot(d, up) = 0`; solving for the y component:

```
   dx = clamp(x - centre.x), dz = clamp(z - centre.z)
   num = up.x * dx + up.z * dz
   y_surface = centre.y + (-num) / up.y          (|up.y| < 256: a plane that is almost vertical: centre.y)
```

`up.y` is negative (about -3,600 to -4,096): divide by it as it is. The tick sets `pos.y = y_surface - hover` (`ship_cfg.hover`, 120; `+y` is down, so *minus* puts the ship above) and `pos_frac[1] = 0`. So the road's slope and bank move the ship up and down, and the ship's own `pitch` (Chapter 37 never changes it) no longer decides the height; Chapter 41 will tilt the nose to the slope.

The plane is an approximation of the quad (a section's ring can twist). Over every road-edge vertex of the generated tracks the plane differs from the real vertex height by at most 30 units (track 1) and 104 (track 2, section 30): the ship dips toward the road at that corner. Interpolating between the two rings is a stretch goal.

### 5.6 Which face is under the ship

Track faces carry flags (E.10.3): `FLOOR`, `WALL`, `BOOST`, `START`. `collide_floor_face(t, sec, pos)` returns the first `FLOOR` face of the section (table order) whose quad contains `(x, z)`, using the same cross product: walk the four sides in perimeter order `v0, v1, v3, v2` (the faces are Z-ordered), and the point is inside when the four values `cross(side) * (p - a)` are **not of both signs** (a point on a side counts as inside, so an orientation never has to be known). The flags of that face are what is under the ship. `WALL` faces are the visible counterpart of the edge lines: the edge vertices *are* the walls' bottom, so the response uses the edges, not the wall quads.

A **boost pad** is a face with `BOOST` (the centre lane of sections 28 and 29 on track 1). The ship **entering** one (the tick's face has `BOOST`, last tick's did not: `collide_state.on_boost`) gets `speed = min(speed + boost_impulse, speed_cap)` once, and `audio_event(EV_BOOST)`. Staying on it adds nothing; two adjoining pad sections are one pad (Chapter 39's chime fired per *section*, and also from a side lane: that detector is removed). At the cap there is nothing to add: the impulse is clamped by `ship_update`'s own cap in Chapter 37 (a stretch goal lets it exceed it).

### 5.7 The response

`collide_ship` in order (collide.h has the exact formulas):

| Step | What |
|---|---|
| 1 | `ship_section = collide_section(...)`; below 0: return 0 |
| 2 | `dl, nl` for the left edge, `dr, nr` for the right; stored in `collide_state` |
| 3 | `dl` or `dr` below `-off_limit` (1200): **respawn** (below), `respawns++`, return |
| 4 | for each edge with `d < radius` (90): a **hit** |
| 5 | `pos.y = ground - hover` |
| 6 | the face, the boost |

**A hit** (`d < radius`, `depth = radius - d`):

1. **Positional correction.** `pos.x += (n.x * depth) >> 12`, `pos.z += (n.z * depth) >> 12`: along the normal, exactly out of the wall. Rounding can leave the distance at `radius - 1` (quiz 3).
2. **Only if the nose points into the wall**, `dot = fx_mul(f.x, n.x) + fx_mul(f.z, n.z) < 0` with `f = ship_forward(...)`:
   - **speed damping**, scaled by how head-on it is: `impact = min(-dot, 4096)`, `speed -= fx_mul(speed, fx_mul(wall_damp, impact))`. A scrape at 10 degrees (`impact` about 0.17) costs about 8% at `wall_damp` 0.5; a head-on hit costs half the speed;
   - **yaw correction** toward the edge's own heading: `target = collide_heading(ex, ez) << 12` (the edge's `b - a`), `err = ((target - yaw + HALF) & ANGLE_MASK) - HALF` with `HALF = ANGLE_TURN / 2`, `yaw = (yaw + fx_mul(err, yaw_fix)) & ANGLE_MASK`. The masked form wraps the error into the **shortest way round** (quiz 4); `fx_mul` keeps the 64-bit product (err reaches 2^23: quiz 5). Each hit removes half the error, so a ship held against a wall straightens out along it;
   - `yaw_vel = 0` (the steering inertia would turn it back in), and `vel` is recomputed as `forward * speed` from the new yaw.
3. **The thud.** `if ship_ticks - last_hit >= thud_gap` (12): `thuds++`, `audio_event(EV_THUD)`. Then `last_hit = ship_ticks` on **every** hit, so sliding along a wall is one thud and the next needs 12 quiet ticks (quiz 7).

Why *damping* and a yaw correction rather than reflecting the velocity? In this model the velocity is not state: Chapter 37 recomputes `vel = forward * speed` every tick, so reflecting `vel` would be undone at once. The honest reflection is of the **heading**: a mirror turn about the wall would send the ship back out at the same angle; the correction toward the edge direction instead *slides* it along the wall, which is the feel most racers want. A real bounce (mirror, then keep the angle) is a stretch goal. One consequence of steering toward the edge's own `b - a`: a ship driving the *wrong way* into a wall is turned toward the track's forward direction (Chapter 41 handles wrong-way driving).

`collide_heading` (**given**) returns exactly what Chapter 37's `heading_angle` returns, in 193 evaluations of `isin`/`icos` instead of 4,096: the coarse minimum every 64 units, then a fine scan around it. About 15,000 instructions instead of about 330,000: a hit on every tick of a scraping ship would otherwise eat the frame.

**Respawn.** More than `off_limit` outside an edge is not a scrape: the ship was teleported, or something is broken. `collide_respawn(t, s, sec)` puts it where `ship_place` puts a ship on the start line, but at section `sec` (`pos = centre + ((up * hover) >> 12)`, `pos_frac`, `vel`, `speed`, `roll`, `yaw_vel` zero, `yaw` and `pitch` from the section's `forward`). With at most 72 units of travel a tick this cannot happen by driving; it is the safety net. It costs about 350,000 instructions (it calls `heading_angle` and `pitch_angle`): once, never per frame.

**The two hooks.** `audio_event(EV_THUD)` and `audio_event(EV_BOOST)` are Chapter 39's. Chapter 39 raised them from the section and the lateral position (`audio_events_update`); that detector is **removed** from `audio.c`, and `collide_ship` raises both.

### 5.8 What the emulator showed

PCSX-Redux, the solution, one pass of the verifier's script (726 frames, two runs):

| Question | Observed |
|---|---|
| Cost of a tick | no contact: median 2,200 instructions (at most 3,800); a hit: median 17,000 (at most 30,500), nearly all of it `collide_heading`; a respawn about 350,000 |
| Do the walls hold? | after every frame of every run the ship's centre is at least 87 units inside both edges (radius 90, 3 for rounding) |
| Hits and thuds while scraping | track 1, the three wall runs: 84 hits, 3 thuds |
| Is the emulated pad immediate? | no: the program's `ship_update` saw a pad change one frame after the script made it, so the verifier replays the pad the program *actually* got (the probe hooks `ship_update`) |
| Frame time | 724 of 726 frames ran exactly one tick (`frame_ticks` = 1); the emulator does not charge GPU time (Chapter 38) |

**Not verified:** how a real console times a hit tick; that a data read stops CD-DA on PCSX-Redux (it does on hardware, one laser: the verifier checks the *program's* restart, not the sound); DuckStation and Mednafen.

### 5.9 Loading another track

The disc now holds `\DATA\TRACK.TRK` (track 1) and `\DATA\TRACK2.TRK` (track 2, 104 sections, a different outline, boost pads at 18, 19, 44, 45, 80, 81). On the **title**, LEFT picks track 1 and RIGHT track 2 (`game.c` calls `track_switch`; `draw_menu` shows `< TRACK n >`); START enters the game on the loaded track.

`track_switch(n)` is yours (trackload.h). The track is parsed **in place** (Chapter 34): `track` points into the file image, which must stay allocated while the track is used. Replacing it is therefore a question of **order**:

```
   n not 1 or 2? return -1                                               nothing changed
   load the file ........ NULL?  return TRK_ERR_READ                     nothing changed
   parse into a SEPARATE Track fresh (track_parse zeroes its output when it fails!)
        error?  free the NEW image, return the code                      nothing changed
   track = fresh;  free(track_image);  track_image = the new file;  track_selected = n;  track_status = 0;  ship_section = -1
```

Parsing straight into `track`, or freeing the old image first, loses the running track when the new file is bad (quiz 8). The boot load in `main.c` stores its image in `track_image`, so the first switch can free it.

And **music**: the drive has one laser. Reading a file seeks away from the audio track and stops it; the end-of-track callback does not fire, so Chapter 39's restart never triggers. Every `track_switch` that read the disc ends with `audio_music_start()`, the failed ones too (quiz 9).

### 5.10 How the verifier checks

1. **Direct calls** (`directcall.lua`, at the entry of `main`): the probe copies the generated `TRACK.TRK` and `TRACK2.TRK`, and a **patched copy of track 1** (an edge of zero length at section 20, a corner on an edge line at 60, a flat `up` at 70, and sections 40/41 stretched), into free RAM and calls every function of `collide.h` about 1,200 times with random and crafted arguments; each result is compared with `example/collide_ref.py`, the model with exactly the formulas of this chapter. Whole ticks are checked field by field.
2. **The game, replayed.** `probe.lua` drives the whole program (title, START, poses written into `ship`, pad presses) through 726 game frames; every frame is recorded. The checker replays each one: from the previous frame's state, `ship_update` then the model's `collide_ship` must give the recorded state. Independent of your code it also checks the ship never nears an edge closer than the radius (edges recomputed in Python), the heading error shrinks, the pad gives one impulse, the teleport finds its section, the far pose respawns, and the readout text is right.
3. **The menu.** Twelve presses with a snapshot of `track` after each (the data is the file's; at most 4 distinct heap blocks: no leak; the music restarted each time), then the same script on track 2. Two other discs, with a corrupt and with no `TRACK2.TRK`, must leave track 1 intact.
4. **Mutants** (`verify/mutants.py`): wrong implementations that the checks must catch (section 8).

## 6. Worked example

Track 1, section 40, the ship 560 units to the right of the centre line (its right edge is at 600, so 40 away: inside the 90-unit radius), 40 units a tick, nose 228 whole units (20 degrees) to the right of the road.

```
right edge: R0 = (-10557, 10053), R1 = (-11492, 9610)       (E.10.4, vertices 244 and 250)
p = (-11007, 9797);  dr = 38, n = (1754, -3703)             the normal points to the left of the road: toward the road's inside
depth = 90 - 38 = 52                                        pos.x += (1754 * 52) >> 12 = 22,  pos.z += (-3703 * 52) >> 12 = -48
f = (-4081, -365) (xz);  dot = -1419  < 0                   the nose points into the wall: impact = 1419 (0.35)
speed 163840 (40.0)  ->  -= fx_mul(163840, fx_mul(2048, 1419)) = 28,360  ->  135,480 (33.1)
edge direction (-935, -443): target heading 2785;  yaw 3014:  err = -229 units;  yaw += -229 / 2  ->  2899.5 units
ground: (-755) - hover 120 -> y = -875
```

`python3 example/collide_ref.py` builds the tracks, prints section 40's edges and runs the model's `collide_ship` on this state (the ship at `centre + right * 560`, yaw = the section's heading + 228 units, pitch the section's, speed 40.0).

## 7. Project: a ship that stays on the road

### 7.1 Behaviour

Chapter 39's game. In the game the ship can no longer leave the road: it scrapes along the walls, losing speed and being turned along them, with one thud per scrape; it hovers over the banked and rising road; a boost pad gives a push and a chime; the readout under `SEC / PRIMS` shows the two edge distances. On the title LEFT / RIGHT choose the track.

### 7.2 The contract

`starter/` is Chapter 39's `solution/` with the wiring done and the work stubbed. **Read `collide.h` and `trackload.h` first: they are the specification.** **Given:** Chapter 39; `game.c` (calls `collide_ship` after every `ship_update`, `collide_reset` on entering the game, the menu, the second readout line), `main.c` (stores `track_image`), the disc (`TRACK2.TRK` in `iso.xml` and `CMakeLists.txt`), `audio.c` without the Chapter 39 event detector; in `collide.c`: the data (`collide_cfg`, `collide_state`), `collide_isqrt`, `collide_heading`, `collide_reset`, `clamp_d`. **You write** the rest:

| Function | What |
|---|---|
| `collide_edge_dist`, `collide_edges` | 5.2, 5.3 |
| `collide_section` | 5.4 |
| `collide_ground`, `collide_floor_face` | 5.5, 5.6 |
| `collide_respawn`, `collide_ship` | 5.7 (the starter's `collide_ship` keeps the Chapter 38 section update as a placeholder) |
| `collide_format` | 5.3 |
| `track_switch` | 5.9 |

**State the verifier reads and patches:** `collide_cfg` (8 words; **patched**), `collide_state` (12 words), `collide_text`, `track`, `track_image`, `track_selected`, `track_status`, `ship`, `ship_section`, `ship_ticks`, `ship_cfg` (hover and speed cap are patched in the direct calls), `audio_stats`.

### 7.3 Steps

1. `collide_edge_dist` and `collide_edges` (`edge_distance`, `edges_recipe_and_fallback`); put `collide_format` on screen to see the numbers (step 6).
2. `collide_section` (`section_under_the_ship`).
3. `collide_ground` and `collide_floor_face` (`ground_height`, `floor_face_lookup`).
4. `collide_ship`: first the section, edges, ground (`tick_without_contact`), then the wall (`wall_push_back_damp_and_yaw`), the thud clock, the boost, the respawn.
5. `collide_respawn`.
6. `collide_format` (`readout_text`).
7. `track_switch` (the `menu_*` checks).

### 7.4 Rules

- Everything derives from the track data and `collide_cfg` / `ship_cfg`: no section numbers, no 600, no 90 in the code.
- Integer arithmetic; use `fx_mul` where a product can pass 32 bits.
- Never index sections by `i +- 1`: use `next` and `prev`.
- A bad track file must not change the running track.

### 7.5 Hints

- Write the pure functions first and print their results with the readout: drive along a wall and watch `R` stay near 90.
- A sign error in `n` pushes the ship *into* the wall; the verifier's first failure names the field.
- `ship_forward` gives the nose direction; the new `vel` is `fx_mul(f[i], speed)`.
- `make run` plays the game: scrape the walls; the thud is Chapter 39's sample.

### 7.6 Stretch goals

- **Reflection**: mirror the heading about the wall, keep `bounce` of the angle, and add a small lateral kick.
- **Ground by interpolation**: the height from the two rings (the plane is off by up to 104 units on track 2).
- **Over-cap boost** that decays back to the cap.
- **Section-keyed heading cache** so even a respawn is cheap.
- **A hit with the wall *face*** (height 250) instead of the edge line, when the ship is above the wall.

## 8. Verification

```sh
source tools/env.sh
parts/part-07-capstone-hoverline/ch40-track-collision/verify/verify.sh            # your starter/
parts/part-07-capstone-hoverline/ch40-track-collision/verify/verify.sh --solution # the reference
```

About two and a half minutes: a build, a direct-call run, the main run (1,200 frames), the menu run (1,900), and two failed-load discs.

| Check | What it means | If it fails |
|---|---|---|
| `both_tracks_on_the_disc` | `TRACK2.TRK` in `iso.xml` and the assets | the wiring |
| `edge_distance`, `edges_recipe_and_fallback` | `collide_edge_dist` and `collide_edges` on random, degenerate and clamped inputs, all of both tracks and the patched copy | sign `s`, truncation, the fallback |
| `section_under_the_ship` | the ring-line walk, with the stretched-section band where the nearest centre is wrong | nearest centre, `ds`/`de` sign, `next`/`prev` |
| `ground_height`, `floor_face_lookup` | the plane and the face lookup | sign of `up.y`, quad order |
| `tick_without_contact`, `wall_push_back_damp_and_yaw`, `thud_event_clock`, `boost_pad_impulse`, `off_track_respawn` | `collide_ship` field by field against the model | each names the field |
| `events_reach_the_audio_counters`, `calls_are_cheap` | events raised once per event; instruction limits (a hit must not scan 4096 angles) | `audio_event`, `heading_angle` |
| `frames_replay_with_the_model` | every game frame equals ship_update + the model | the first differing frame |
| `ship_stays_inside_the_road`, `hover_follows_the_ground`, `yaw_converges_after_impact`, `boost_pad_run`, `events_come_from_collision`, `section_follows_teleports`, `respawn_run`, `readout_text` | the geometric facts, independent of your code | the game wiring |
| `menu_loads_both_tracks`, `menu_game_runs_on_track_2`, `menu_restarts_the_music`, `menu_failed_load_keeps_the_track`, `menu_missing_file_keeps_the_track` | `track_switch` | order of load, parse, free |

A pass ends with `CHAPTER 40: PASSED (27/27 checks)`. The untouched starter builds and fails. Sixteen wrong implementations were tried with `verify/mutants.py` (nearest-centre section, no yaw correction, an unwrapped yaw error, a push by the whole radius, damping that ignores the angle, a boost every tick, the boost taken from the section, the thud clock updated on thuds only, a flipped ground sign, no hover, the slow `heading_angle`, an ignored reference side, no respawn, parsing into the global track, a leaked image, no music restart): all sixteen make `verify.sh` exit 1, each caught by the checks it should be (`python3 verify/mutants.py`, about an hour). Not verified: the feel (that is yours), sound, other emulators.

## 9. Common pitfalls

- **A sign you derived instead of measured.** The reference point decides which side is "inside"; do not decide it from the winding.
- **Overflow.** `8192 * 32767` fits, `err * yaw_fix` does not: `fx_mul`.
- **Division that rounds the wrong way.** C `/` truncates toward zero; `>>` floors. The spec says which is used where.
- **The long way round.** An angle difference must be wrapped.
- **Colliding with the wrong section.** Use the ring lines, and the neighbours.
- **`+y` is down.** `up.y` is negative; hover is *subtracted*.
- **A thud per frame on the wall.** Update `last_hit` on every hit.
- **Parsing in place and freeing the old image.** The order of `track_switch`.
- **Silent music after a disc read.** Restart it.
- **A hit that scans 4,096 angles.** Use `collide_heading`.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- Appendix E.10 (`.TRK`, E.10.4 collision recipe, E.10.6), `tools/assets/README.md` (`trkgen.py`, `--track 2`).
- `example/collide_ref.py`: the model, readable in one sitting.
- Real-Time Collision Detection (Ericson): point-line distance, point in convex polygon.
- psx-spx: *CDROM Control Commands* (Play), *CDROM Audio*.
- Chapter 41 (skid, drag, laps): the handling that makes the wall response feel right.
