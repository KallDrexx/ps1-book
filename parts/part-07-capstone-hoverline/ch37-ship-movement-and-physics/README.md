# Chapter 37: Ship Movement and Physics

## 1. Concept

A vehicle is a **rigid body**: a position, a velocity and an orientation, changed a little every **tick** by forces. This chapter puts the Hoverline ship on the track's start line and lets you fly it: **X** accelerates, **Square** brakes, the **D-pad** steers and banks the ship, and a **chase camera** follows from behind and above. The motion is integrated in fixed point, with a fixed time step that does not depend on how long a frame takes, and it covers the same ground per **second** on NTSC (60 Hz) and PAL (50 Hz) consoles. There is no collision yet: the ship flies off the road if you let it.

## 2. Why it matters

Everything after this chapter is built on the ship's state: Chapter 38 asks which track section it is nearest to, 39 pitches the engine hum by its speed, 40 pushes it back from walls, 41 adds drag, skid and laps. The same three ideas, a *state struct*, an *update function with a fixed step* and a *camera derived from the state*, are the skeleton of every game loop. Getting the **conventions** right once (which way is positive yaw, which way is up when +y is down) saves you from every sign error that follows.

## 3. Learning objectives

After this chapter you can:

- describe a rigid body's state and move it with **Euler integration** in 4.12 fixed point (`v += a dt`, `p += v dt`), keeping the sub-unit remainder so slow speeds do not stall;
- define **yaw, pitch and roll** in the book's axes, derive the ship's **forward vector** and say what order of rotations the ship matrix uses (intrinsic vs extrinsic) and why `RotMatrix` alone is the wrong one;
- steer with a **yaw velocity** and **angular damping**, and bank the ship with a smoothed roll;
- apply thrust and brake with an exact **speed cap** and a clamp at zero;
- run the world with a **fixed time step** (several ticks per slow frame) and scale it for **NTSC and PAL** with a fixed-point `dt_scale`;
- place the ship on the start line (hover height above the road, along the section's frame) and build a **chase camera** with Chapter 28's look-at without a +y-down sign error;
- test a physics function directly, with crafted states, against an exact reference.

## 4. Prerequisites

[Chapter 23](../../part-05-three-dimensions-with-the-gte/ch23-fixed-point-math/README.md) (4.12 fixed point, `fx_mul`, `isin` / `icos`), [Chapter 25](../../part-05-three-dimensions-with-the-gte/ch25-the-gte-coprocessor/README.md) (`RotMatrix`, the rotation directions), [Chapter 26](../../part-05-three-dimensions-with-the-gte/ch26-multiple-objects-and-simple-motion/README.md) (motion in fixed point, per-object matrices), [Chapter 28](../../part-05-three-dimensions-with-the-gte/ch28-the-camera/README.md) (`camera_look_at`), [Chapter 22](../../part-04-c-on-the-playstation/ch22-controller-input-and-the-bios/README.md) (held and pressed buttons), [Chapter 32](../../part-06-assets-cdrom-textures-and-compression/ch32-a-real-model-format-shp/README.md) (`.SHP` drawing), Chapters [33](../ch33-game-architecture-objects-scenes-and-input/README.md) to [36](../ch36-polygon-subdivision-and-tessellation/README.md) (the program), and Appendix E.8 (`.SHP`), E.9 (`ry`), E.10 (`.TRK` sections).

## 5. Explanation

### 5.1 The ship as a rigid body

Four things describe the ship at an instant:

| State | Meaning | Changes by |
|---|---|---|
| `pos` | where it is (world units, `s32` x 3) | `vel` |
| `vel` | which way and how fast it moves | `speed` and the heading |
| `yaw`, `pitch`, `roll` | which way it faces (three **Euler angles**) | `yaw_vel`; pitch is fixed this chapter |
| `speed`, `yaw_vel` | scalar rates | thrust, brake, steering, damping |

The book's axes: **+x right, +y DOWN, +z forward**. Every angle is in 4096ths of a turn.

```
            -y (up)
             |
             |   yaw   : about the world's vertical.  + turns +z toward +x (right)
             |   pitch : about the ship's right axis. + raises the nose
             o--- +x     roll  : about the nose.           + puts the RIGHT wing down
            /|
           / |
         +z  +y (down)
        (nose)
```

Yaw is exactly the `ry` of Appendix E.9: the heading `(sin yaw, 0, cos yaw)` of the +z axis, `RotMatrix`'s `vy`, **no sign change**. So **LEFT lowers the yaw** and RIGHT raises it. The `.SHP` ship (530 long) has its nose along +z, wings along x and its top toward -y.

This chapter's ship does not move its velocity independently of its nose: the velocity is always `forward * speed`. That makes it easy to drive; Chapter 41 adds a **skid** by letting `vel` lag behind `forward * speed`, which is why both fields exist.

### 5.2 Units and formats

| Quantity | Format | Notes |
|---|---|---|
| position | whole world units + `pos_frac` 0..4095 | 1/4096 unit remainder per axis |
| `speed`, `vel` | 4.12 world units per **NTSC tick** | `60 * 4096` = 60 units per tick = 3600 per second |
| angles | **12.12**: `angle << 12`, one turn = `1 << 24` | `angle >> 12` is the 4096-per-turn angle that `isin`, `icos` and `RotMatrix` take |
| `yaw_vel` | 12.12 angle per NTSC tick | |
| `thrust`, `brake`, `yaw_accel` | rates per NTSC tick, per tick | |
| `dt` (`dt_scale`) | 4.12 factor | 4096 = 1.0 |

*Why a fraction?* At 60 units per tick the integer position is fine, but a ship creeping at 0.3 units per tick would never move if you truncated each step. The 12-bit remainder carries over (5.5, step 7). *Why 12.12 angles?* A yaw rate of 0.004 units per tick must still do something; with whole-unit angles it would be 0. Both are the same trick: more fraction bits where the quantities are small. The product of two 4.12 numbers is `fx_mul(a, b) = (a * b) >> 12` (Chapter 23, a 64-bit product and an arithmetic shift, so it rounds toward minus infinity).

A **tick** is one video frame of the console: 1/60 s on NTSC, 1/50 s on PAL (5.7).

### 5.3 The start line

`ship_place` puts the ship on the track's **START section** (`track.start_section`, or `ship_cfg.start_section` if that is not negative). With `s` = that section (Appendix E.10.4):

- `pos = s.centre + ((s.up * hover) >> 12)`, per axis, with `hover` = 120. `up` is the road's unit normal in 4.12; **its y is negative** (up is -y), so the ship ends *above* the road and slightly toward the inside of a banked section;
- `yaw = heading_angle(s.forward.x, s.forward.z) << 12`, `pitch = pitch_angle(s.forward.y) << 12` (the nose follows a climbing road at the start); `roll`, `speed`, `yaw_vel`, `vel`, `pos_frac` = 0.

```
  side view, road climbing        top view of the heading
            .  forward               +z
        . '    (y < 0: up)            |   forward = (410, 4042)
   P  o'    ^ up (-y)                 | /   heading_angle = 66
 centre ------- road                  |/
                                      +------ +x          (1024 = a quarter turn toward +x)
```

`heading_angle(x, z)` finds the whole-unit angle 0..4095 that points the same way as `(x, z)` (`isin(a) x + icos(a) z > 0`) and **minimises the cross product** `|isin(a) z - icos(a) x|`; the first one wins a tie. Why not maximise the dot product? Near its peak the dot product is flat: the table's rounding errors (`isin` is off by up to 12 of its 4096, about 0.3%) move the maximum by as much as 14 units. The cross product crosses zero **steeply**, so its minimum stays within 1.5 units of the true heading. `pitch_angle(y)` minimises `|isin(p) + y|` for `p` in -1024..1024 (nose up is positive, and negative y). Both loops run once when the game starts.

The generated road banks and climbs at the start (section 0: `up` = (-1837, -3650, -285), `forward.y` = -522). The ship does **not** tilt to the bank: only its pitch follows the slope, and only at the start. Chapter 41 adds auto-pitch and Chapter 40 the road limits; here the ship flies straight on and soon leaves the road. That is expected.

### 5.4 Orientation: the forward vector and the rotation order

The **forward vector** is where the nose points: `forward = R * (0, 0, 1)`, the third column of the ship matrix. The book's rotations (Chapter 25) are `Rx`, `Ry`, `Rz` with `Ry = [[c,0,s],[0,1,0],[-s,0,c]]`, so `Ry * (0,0,1) = (sin yaw, 0, cos yaw)`. With pitch too (`Rx * (0,0,1) = (0, -sin p, cos p)`, the nose raised means negative y):

```
 forward = ( sin(yaw) cos(pitch),  -sin(pitch),  cos(yaw) cos(pitch) )         (roll does not change it)
```

In code: `fx_mul(isin(a), icos(p))`, `-isin(p)`, `fx_mul(icos(a), icos(p))` with `a = yaw >> 12`, `p = pitch >> 12`.

**Which order of rotations?** A column vector is rotated by the matrix on its **right** first, so a product can be read two ways. *Extrinsic* (about the fixed world axes, right to left) or *intrinsic* (about the axes the body carries, left to right). The SDK's `RotMatrix(rx, ry, rz)` returns `Rx * Ry * Rz`: extrinsically, roll about world z, then yaw about world y, then **pitch last, about world x**; intrinsically, pitch, then yaw about the new y, then roll about the newest z. Same matrix, two stories. Its flaw for a vehicle is the first one: a ship yawed 90 degrees that pitches turns about the world's x axis, which is now its own *nose*, so it rolls; `forward` at yaw 1024 would not depend on the pitch at all.

```
 RotMatrix  Rx*Ry*Rz   yaw 90, pitch up:  nose stays on +x, the ship ROLLS      (wrong for a ship)
 ship       Ry*Rx*Rz   yaw 90, pitch up:  nose on +x raised toward -y            (what a pilot expects)
```

The ship uses **`M = Ry(yaw) * (Rx(pitch) * Rz(roll))`**. Read intrinsically (left to right): yaw about the world's vertical, then pitch about the ship's own right axis, then roll about its nose. Read extrinsically: roll and pitch happen first, while the ship still faces +z, and the yaw turns the whole ship last. Build it from two `RotMatrix` calls, `(pitch, 0, roll)` (= `Rx * Rz`) and `(0, yaw, 0)`, and one `MulMatrix0`. With pitch 0, as here after the start, the order of yaw and roll does not matter; the verifier still tests it with a pitched ship.

### 5.5 One tick: the update order

`ship_update(&ship, pad, dt)` does exactly this, in this order. `pad` is the active-high button mask (`INPUT_*`), `dt` the 4.12 time factor (5.7); the constants live in `ship_cfg` (7.2).

| # | Step | Formula |
|---|---|---|
| 1 | steer | `steer = RIGHT - LEFT` (-1, 0, 1) |
| 2 | yaw velocity | `yaw_vel += fx_mul(steer * yaw_accel, dt)`; then **damping** `yaw_vel -= fx_mul(yaw_vel, fx_mul(yaw_damp, dt))`; `|yaw_vel| < 16` becomes 0 |
| 3 | yaw | `yaw = (yaw + fx_mul(yaw_vel, dt)) & (2^24 - 1)` (the wrap) |
| 4 | roll | `roll += fx_mul(yaw_vel * roll_gain - roll, fx_mul(roll_smooth, dt))` |
| 5 | thrust, brake, cap | CROSS: `speed += fx_mul(thrust, dt)`; SQUARE: `speed -= fx_mul(brake, dt)`; then clamp to `0 .. speed_cap` |
| 6 | velocity | `f = forward(ship)`; `vel[i] = fx_mul(f[i], speed)` |
| 7 | position | `t = pos_frac[i] + fx_mul(vel[i], dt)`; `pos[i] += t >> 12`; `pos_frac[i] = t & 4095` |

Pitch never changes. Notes:

- **Euler integration.** `v += a dt` then `p += v dt`, in this order (*semi-implicit* Euler: the new velocity moves the position). It is first-order accurate; the error shows in 5.7.
- **Angular damping.** The turning rate decays by a fixed *fraction* each tick (`yaw_damp` = 512 = 1/8), so releasing the stick eases the ship straight. With steering held, `yaw_vel` settles where the push and the decay balance: `(yaw_vel + yaw_accel) * (1 - yaw_damp) = yaw_vel`, so `yaw_vel = yaw_accel * (1 - 1/8) / (1/8)` = 14 units per tick, about 74 degrees per second. The **dead zone** `|yaw_vel| < 16` (0.004 units per tick) exists because `fx_mul` rounds toward minus infinity: a small positive rate would never decay to 0.
- **The cap**, defined exactly: the *scalar* `speed` is clamped to `speed_cap` (60.0), and to 0 from below: **braking stops at 0, it never reverses**. `|vel|` equals `speed` up to the sin/cos table's error (under 0.5%); `vel` is derived, not clamped. Holding CROSS and SQUARE together applies both, then clamps. Without either, nothing changes the speed: **no drag** in this chapter.
- **Roll** is signed (a left bank is negative) and not wrapped. 5.6 explains its target.
- All products use the 64-bit `fx_mul`; there is no overflow for the constants in this chapter.

### 5.6 Banking and drawing the ship

A real craft leans into a turn. The roll's **target** is proportional to the turning rate, `yaw_vel * roll_gain` (16: the steady 14 units per tick of yaw give a 224-unit, 20-degree bank), and the roll *eases toward it* by `roll_smooth` (1/4) of the error per tick: a smooth lean in, a smooth recovery. The sign needs no thought: LEFT makes `yaw_vel` negative, the target negative, and **negative roll puts the left wing down**.

To draw it, exactly as Chapter 33 draws an object (camera-relative, view *rotation* only, Chapter 33's recipe):

1. `M = ship_matrix(&ship)`; `d = ship.pos - cam_eye` (`s32`, small) as the translation;
2. `world = CompMatrixLV(view rotation with t = 0, M)`, `load_matrix(&world)` (the noipa wrapper, Chapter 25);
3. `render_shp(&ship_shp, &ship_store)`: the ship has its own `.TPK` (`SHIP.TPK`, three textures), so `render_shp` now takes the texture store as an argument.

The ship is drawn after the track in the same ordering table; both use the OT slot of their depth.

### 5.7 Time: fixed steps, NTSC and PAL

**One tick = one vertical blank** (one video frame). The physics step is always one tick; what varies is how many ticks a *drawn* frame has to catch up.

```
 vertical blanks   |    |    |    |    |    |    |    |    |
 frame A           [ draw ]      ticks run: 1
 frame B           [      draw (slow)      ]    ticks run: 2
 frame C                                   [ draw ]       ticks run: 1
```

`game_update` reads the blank counter (`VSync(-1)`) and runs `frame_ticks` = the blanks since the last frame (clamped to 1..4, so a long stall such as a disc read cannot fire hundreds of steps) calls of `ship_update`, all with the same pad reading. A game with one update per frame would run at half speed whenever a frame takes two blanks.

**Measured on this chapter's program** (the verifier's scripted route, 5.6 s from the start line, subdivision off): one tick per frame, **60 frames per second**, for the first 3.6 s; then the view takes in more of the track, the whole-track pass of Chapter 34 costs a little more than a frame, and nearly every frame takes two blanks: 30 frames per second, with the physics still exact. (PAL's longer frame holds 50 per second for the whole route.) The renderer is not optimised yet: it cannot hold 60 until Chapter 38. With Chapter 36's subdivision on (`subdiv_enabled`, toggled by **R1**) the frame takes two blanks (sometimes three) at every pose: about 30 per second. So this chapter's default is **subdivision off**, keeping the start line at 60; Chapter 38 draws only a window of sections and brings the default back to one blank (with subdivision on, most frames still take two).

**NTSC vs PAL.** A PAL frame lasts 1/50 s: 1.2 times longer. Per-tick rates are written for NTSC; every step multiplies by `dt`:

| Standard | frame | `dt_scale` | one tick of thrust (3072) |
|---|---|---|---|
| NTSC | 1/60 s | 4096 (1.0) | 3072 |
| PAL | 1/50 s | 4915 (1.2 = 60/50, rounded down from 4915.2) | `fx_mul(3072, 4915)` = 3686 |

A tick moves 1.2 times as much, there are 1.2 times fewer of them per second, and the ship covers the same distance per **second**. Not exactly: Euler integration is first order, so a larger step approximates the same curve a little differently. Over the verifier's 5.6 s route the two standards end within about 2% of the distance travelled (their yaw differs by 1 to 2 degrees after the turn); the check allows 2.5% + 20 units.

**The video mode.** `video_mode` (0 NTSC, 1 PAL) is read once at the start of `main`: `display_init_mode(pal)` calls `ResetGraph(0)`, then `SetVideoMode(MODE_PAL)` (**GP1(08h)**, bit 3, the GPU's PAL flag) before it builds the display environments, and `dt_scale = video_mode ? 4915 : 4096`. PCSX-Redux follows the bit: measured, the vertical-blank period is about 566,100 CPU cycles (59.83 Hz) with `video_mode` 0 and 675,900 (50.11 Hz) with 1, and `VSync` follows. Real hardware (psx-spx, "GPU Timings"): NTSC 263 lines of 3413 video clocks at 53.69 MHz, 59.83 Hz, the same 566,100 cycles; PAL 314 lines of 3406 at 53.20 MHz, 49.76 Hz, about 680,600 cycles. The real ratio is 1.202, so 60/50 is within 0.2%. A real console is made for one region; a game either offers both or reads the region from the BIOS; Chapter 42 returns to this. The verifier tests PAL the cheap way: its probe writes 1 to `video_mode` at the entry of `main`, before your code reads it. The display range stays 320 x 240.

### 5.8 The chase camera

Behind and above the ship, looking a little ahead of it, using Chapter 28's `camera_look_at(eye, target, up)` with the ship's `forward` `f` (4.12):

```
   side view, nose to the right (+z), up is -y

                 E  eye                      view ray
                 o  . . . . . . . . . . . . . . . . . .  o T  target
          height |                                 .
                 |           P ship                    .
                 |           o--------> f            . 
                 +-----------+---------------------+
                  <- back ->      <---- look_ahead ---->

   eye    = P - f * back_dist  + (0, -cam_height, 0)     (back 900, height 250)
   target = P + f * look_ahead                           (1200)
   up     = (0, -4096, 0)                                (the world's up, so the horizon stays level)
```

Per axis `(f * back_dist) >> 12`. **Careful with the sign:** +y is down, so **above is `- cam_height`**. The camera does not roll with the ship: you see the ship bank against a level horizon. The verifier checks `dot(eye - pos, forward) < 0` and `eye.y < pos.y` at every frame. Smoothing (a spring so the camera lags a corner) is a stretch goal; this camera is rigid, so the ship stays at the same screen position.

## 6. Worked example

The start line of track 1 (section 0): centre (23883, -639, 496), `up` (-1837, -3650, -285), `forward` (410, -522, 4042).

- **Placement.** `up * 120 >> 12` = (-54, -107, -9), so `pos` = **(23829, -746, 487)**. `heading_angle(410, 4042)` = 66 (`yaw` = 270336) and `pitch_angle(-522)` = 83 (`pitch` = 339968).
- **First tick, CROSS, NTSC.** `speed` = 3072. `forward` = (411, -522, 4044) (isin(66) = 415, isin(83) = 522, icos(83) = 4064), so `vel` = (308, -392, 3033) and `pos_frac` = (308, 3704, 3033) with `pos.y` falling by one, to -747: the ship has moved 0.74 units. **PAL:** `speed` = 3686, `vel` = (369, -470, 3639): 20% more.
- **A left turn.** From rest, LEFT for five ticks gives `yaw_vel` = -7168, -13440, -18928, -23730, -27931 (12.12 angle per tick: -1.75, -3.3, -4.6, -5.8, -6.8 units per tick, still building toward -14): each tick adds -8192 and removes an eighth of what is there.
- **The whole route.** `example/ship_ref.py` is the exact model of this chapter; `python3 ship_ref.py` prints the scripted run (CROSS 2 s, LEFT 1 s, coast, SQUARE, RIGHT) for 60 and 50 ticks per second:

```
 tick  t(s)       x       y       z   speed    yaw   roll
   90  1.50   24133   -1133    3478   60.00     66      0      <- the cap (60.00) reached at tick 80
  120  2.00   24313   -1362    5255   60.00     66      0
  150  2.50   24107   -1591    7009   60.00   3838   -217      <- left turn: yaw falls, roll about -217 units
  210  3.50   21301   -2050    9051   60.00   3324     -7      <- LEFT released: the roll recovers, no drag
  270  4.50   19560   -2291    9756    0.00   3322     -0      <- SQUARE: the speed reaches 0 and stays
```

(Speed in units per tick; yaw and roll in whole angle units, 4096 per turn.)

## 7. Project: the ship on the start line

### 7.1 Behaviour

Chapter 36's program. In the game state the ship stands on the start line, hovering, with the chase camera behind it. **X** accelerates to the cap, **Square** brakes to a stop, **Left / Right** steer and bank, releasing everything lets it coast at constant speed. **Start** returns to the title; entering the game again puts the ship back on the start line. **Select** (wireframe), **Triangle** (subdivision outlines) and **R1** (subdivision on / off) work as before. The picture is the track with the ship in front of it.

### 7.2 The contract

`starter/` is Chapter 36's `solution/` plus the ship's files; it builds, boots and shows the track from the start line with no ship. **Read `ship.h` first: it is the specification of every function.** **Given:** Chapters 33 to 36 (the `psxe` copy gained `display_init_mode` and `input_buttons`), `render_shp` with a texture-store argument, `SHIP.SHP` and `SHIP.TPK` on the disc and loaded in `main.c` (`ship_shp`, `ship_store`), `video_mode` and `dt_scale`, `measure_ticks`, the constants (`ship_cfg`), the R1 toggle, `ship_place` called on entering the game. **You write:**

| File | What |
|---|---|
| `ship.c` | `heading_angle`, `pitch_angle`, `ship_place`, `ship_forward`, `ship_update`, `ship_matrix` |
| `chase.c` | `chase_camera_update` |
| `game.c` | the loop of `frame_ticks` calls to `ship_update` (and `ship_ticks++`) followed by `chase_camera_update`; `draw_ship` |

**State the verifier reads** (names and types fixed):

| Symbol | Meaning |
|---|---|
| `ship` | `Ship`, 14 words: `pos[3]`, `pos_frac[3]`, `vel[3]`, `speed`, `yaw`, `pitch`, `roll`, `yaw_vel` |
| `ship_cfg` | 13 words, patched by the verifier: `thrust` 3072, `brake` 6144, `speed_cap` 245760, `yaw_accel` 8192, `yaw_damp` 512, `roll_gain` 16, `roll_smooth` 1024, `hover` 120, `back_dist` 900, `cam_height` 250, `look_ahead` 1200, `start_section` -1, `reserved` |
| `video_mode`, `dt_scale` | 0 NTSC / 1 PAL, written at the entry of `main`; 4096 or 4915 |
| `frame_ticks`, `ship_ticks` | the ticks run in the last frame; `ship_update` calls since the ship was placed |
| `cam_eye`, `cam_target`, `view_mtx` | the chase camera |
| `subdiv_enabled` | the toggle (default 0) |
| `frame_no`, `game_state`, `track`, `ot_frames` | as in Chapters 33 to 36 |

The probe hooks the entry and the return of `ship_update`, so keep it a real function (the starter's `noinline`), and calls the six functions of `ship.h` / `chase.c` directly.

### 7.3 Steps

1. **Angles and the start** (5.3): `heading_angle`, `pitch_angle`, `ship_place`. Run the verifier: `start_pose` passes once the ship is where the section says (the game also needs steps 2 to 4 before anything moves).
2. **The forward vector and the tick** (5.4, 5.5): `ship_forward`, then `ship_update` one step at a time (thrust, brake and cap; then position with the fraction; then yaw, damping, roll). `unit_ship_update` names the first field that differs.
3. **The loop** (5.7): in `game_update` run `frame_ticks` ticks with `input_buttons()` and `dt_scale`, then the camera.
4. **The camera** (5.8): `chase_camera_update`. The eye is where the track view will now come from.
5. **The picture** (5.4, 5.6): `ship_matrix` (two `RotMatrix`, one `MulMatrix0`), then `draw_ship`. Fly it in the emulator (`make run`), then run the verifier until it passes.

### 7.4 Rules

- `ship_update` follows the order of 5.5 and uses only `ship_cfg` and its arguments; no global state. The verifier calls it with other constants, other time steps and states it never reaches in play.
- Rates are per NTSC tick and every one is multiplied by `dt`; speeds in `Ship` stay per NTSC tick.
- All arithmetic is integer; `fx_mul` for 4.12 products.
- The camera is a function of the ship (`chase_camera_update` reads nothing else); `draw_ship` puts only the camera-relative `d` in the GTE translation.
- `ship_place` is called by `set_state` (given); do not move the ship anywhere else.

### 7.5 Hints

- `isin` and `icos` take **whole-unit** angles: shift the 12.12 angle down by 12 first; `isin` of a negative angle is fine.
- `t >> 12` and `t & 4095` on a negative `t` give the floor and a non-negative remainder together: that is what keeps `pos` and `pos_frac` consistent.
- `RotMatrix` takes an `SVECTOR` of `s16`; cast the shifted angles. Zero the matrix's `t` after `MulMatrix0` (it is not meaningful), then give it `d` with `TransMatrix`.
- If the ship climbs toward the camera, check the sign of `pitch`; if the camera is under the road, check `- cam_height`.

### 7.6 Stretch goals

- **A spring camera**: `eye += (wanted - eye) * k >> 12` per tick (scaled by `dt`), so the camera lags in turns; keep the behind-and-above guarantee by clamping.
- **Analog steering**: use the DualShock stick for a steer value in -1..1 (Chapter 22's pad types).
- **Interpolation**: draw the ship at the fraction of the next tick that the frame time suggests, to remove the judder at 30 frames per second.
- **A speed gauge** with `FntPrint`: speed in units per second for both standards.
- **Ground effect**: raise the hover height with the speed.

## 8. Verification

```sh
source tools/env.sh
parts/part-07-capstone-hoverline/ch37-ship-movement-and-physics/verify/verify.sh            # your starter/
parts/part-07-capstone-hoverline/ch37-ship-movement-and-physics/verify/verify.sh --solution # the reference
```

About one minute: a build and four emulator runs from the disc image. Three are **driven** by a script of pad presses in seconds, timed by the program's own `ship_ticks` (CROSS 2 s, LEFT 1 s, coast, SQUARE 0.9 s, RIGHT 0.6 s): the default NTSC run; the **PAL run** (`video_mode` = 1 written at the entry of `main`, the script in 50 ticks per second); and an **alt run** with every constant of `ship_cfg` patched (and the start section 37, hover 200), where the frames already take two blanks and R1 is pressed once to turn subdivision on as well (two or three). The probe records every `ship_update` call (pad, `dt`, state before and after) and, each frame, the ship and the camera; Python replays the physics from `example/ship_ref.py`, an exact integer model with `isin` ported bit for bit (Chapter 28). The fourth run is **direct calls**: `ship_update` on crafted states with the pad and the time step as arguments, `ship_forward`, `ship_matrix`, `chase_camera_update`, `heading_angle`, `pitch_angle` (about 220 cases; the seed is printed, `CH37_SEED=n` repeats a run).

| Check | What it means | If it fails |
|---|---|---|
| `runs_ok`, `start_pose` | no exception, guard bytes intact; the first state equals `place()` of the model on the START section and on section 37 (hover along `up`, heading from `forward`) | `up` sign, `heading_angle`, hover rule |
| `update_matches_model` | every recorded call equals the model **exactly**, in all three runs, and consecutive calls chain | the first differing field is named |
| `pad_script` | the pad word carries CROSS / LEFT / SQUARE / RIGHT in their windows and not outside them | wrong buttons, a stuck mapping |
| `speed_cap`, `brake_stops_at_zero`, `no_drag` | the top speed is exactly the cap, never above, never negative; braking stops at exactly 0 and the stopped ship does not move; coasting keeps the speed | missing or wrongly ordered clamps; drag |
| `steering_and_banking` | LEFT: yaw and `yaw_vel` fall, roll < 0 (about -220 units); RIGHT mirrors it; the one-second turn is about 75 degrees; yaw rate and roll fade to 0 a second after release | inverted sign, damping |
| `heading_and_velocity` | `vel` follows `forward * speed` against `math.sin` / `math.cos`, not the book's own `isin` | x and z swapped, a yaw sign |
| `time_step`, `pal_runs_at_50hz`, `pal_same_distance_per_second` | `dt` 4096 / 4915 in every call; the emulated frame period is 1/60 and 1/50 s; the PAL ship is within 2.5% + 20 units of the NTSC ship at 1, 2, 3, 4, 5 s (and the speeds agree) | `dt_scale` ignored, `SetVideoMode` missing |
| `fixed_timestep` | `ship_ticks` follows the elapsed vertical blanks within a few ticks, also at two ticks per frame; R1 toggles once | one update per frame |
| `chase_camera_behind_and_above` | at every frame of all three runs: eye and target equal the formula; the eye is behind (`dot < 0`) and above (`y` smaller) | `+ cam_height`, forward sign |
| `start_line_default_frame_rate` | in the first three seconds at most 2% of the frames take more than one blank (measured, not a goal) | subdivision on by default |
| `ship_and_track_drawn` | in three screenshots: the track fills the picture; the ship's orange engine pods are around the projected ship position; the pods are level when straight, the **left** pod lower in the left turn, the right pod lower in the right turn | `draw_ship`, a sign of the roll |
| `unit_*` | the direct calls: caps, brake clamp, dead zone, wraps, PAL step, patched constants; forward vector; the matrix against the model (order Ry * Rx * Rz); the camera; the angle functions | the case, the input and the first wrong field are printed |

A pass ends with `CHAPTER 37: PASSED (20/20 checks)`. The untouched starter fails. So do: ignoring `dt_scale` (the `time_step` and PAL checks), swapping sin and cos in `forward`, putting the camera below the ship (`+ cam_height`), no brake clamp (the ship reverses), no speed cap, and one update per frame (`fixed_timestep`).

## 9. Common pitfalls

- **Above is minus.** `eye.y = ship.y - cam_height`; nose up is negative `forward.y`; `up` of a section has negative y.
- **Yaw direction.** Positive yaw turns +z toward +x. LEFT is negative. A model that looks right and flies mirrored has x and z swapped or a sign flipped.
- **`RotMatrix` for the ship.** It pitches about the world's x axis after the yaw.
- **Truncating the remainder.** `pos += vel * dt >> 12` loses everything below one unit; slow motion stalls.
- **A rounding bias.** `>>` rounds toward minus infinity; a small positive rate never decays. The dead zone is there for that.
- **Braking through zero.** Clamp the speed after the brake, not only when it gets negative one tick later.
- **Per-frame physics.** One update per frame makes the game slower exactly where it is heavy. Ticks come from the vertical blanks.
- **Forgetting PAL.** A fixed `dt` of 4096 is right on an NTSC console only.
- **`dt` applied twice or not at all** to the damping and the smoothing: they are per-tick *fractions* and scale with the step like the accelerations.
- **A 16-bit overflow.** The ship's `d = pos - cam_eye` is small, but `pos` itself is not: keep it `s32` and never put it in the GTE.
- **Rolling the camera with the ship.** The camera's `up` is the world's, not the ship's.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- Appendix E.8 (`.SHP`), E.9 (`ry` and the rotation), E.10.4 and E.10.6 (sections, the start position).
- Glenn Fiedler, "Fix Your Timestep!" (the accumulator pattern behind `frame_ticks`); Chapter 27's frame-time measurement.
- psx-spx, "GPU Display Control Commands" (GP1(08h), the PAL bit) and "Timers" (the vertical blank rate).
- Chapters 28 (the look-at), 38 (nearest section), 40 (collision: the road's edges), 41 (drag, skid and auto-pitch: where `vel` and `forward * speed` part).
