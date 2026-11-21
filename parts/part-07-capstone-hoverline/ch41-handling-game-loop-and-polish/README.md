# Chapter 41: Handling, Game Loop, and Polish

## 1. Concept

A simulation becomes a game in two steps. First the ship gets **layered forces** with a time constant you can *feel* (air resistance, a skid, a nose that follows the road), each one a one-line fixed-point blend of "where it is" toward "where it wants to be". Then the program gets a **shape in time**: a state machine (title, countdown, race, results, restart) around a clock that counts in ticks, laps counted from the sections the ship passes, and text that says so.

## 2. Why it matters

Chapters 33 to 40 built a program that *works*; this one makes it something a person plays more than once. The handling is where a racer's identity lives: the same track with a different grip is a different game. The loop around it is what players actually meet: the countdown that holds the car still, the clock that counts only racing time, the warning when you drive the wrong way, the results screen, and the restart that puts everything back. All of it is small integer arithmetic on state you already have, and all of it has to be **exact** (a lap time is a number a player compares), so this chapter is mostly about writing down the *rules* precisely enough that a reference model and your program must agree.

## 3. Learning objectives

After this chapter you can:

- add **drag**, a **skid** and an **auto-pitch** to the ship as three fixed-point blends (`x += (target - x) * k`), say what the constant means as a time constant, and **clamp** a fraction so that no `dt` can overshoot;
- derive the pitch a ship wants from a road's `up` vector and its heading, and make it cheap enough for every tick (a **binary search** on a monotone function instead of a scan);
- count **laps** from net progress along the ring's links, so that reversing over the line cannot score, and detect **wrong-way** driving with the same number;
- write a game **state machine** (title, countdown, race, results) with entry work in one place, edge-triggered input, and a clock that counts ticks, not milliseconds;
- format times (`M:SS.cc`) and a HUD with integer arithmetic, and keep a **best lap** in RAM across restarts;
- verify a *time-dependent* program: replay every frame with a model, and drive the lap logic with a scripted route instead of waiting for a real lap.

## 4. Prerequisites

[Chapter 22](../../part-04-c-on-the-playstation/ch22-controller-input-and-the-bios/README.md) (edge-triggered pad events), [37](../ch37-ship-movement-and-physics/README.md) (`ship_update`, `dt_scale`, ticks), [38](../ch38-track-visibility/README.md) and [40](../ch40-track-collision/README.md) (`ship_section`, the ring links, collision), [39](../ch39-audio/README.md) (`audio_play_sfx`: `BEEP` and `GO` have waited for this chapter). This chapter starts from Chapter 40's `solution/`.

## 5. Explanation

### 5.1 What a tick does now

```
 per tick (RACE, game_update runs it frame_ticks times: 1 to 4)

   ship_update(...)             Chapter 37, with two new lines:
        |                         step 5  speed = handling_drag(speed, dt)        (5.2)
        |                         step 6  handling_skid(vel, forward * speed, dt)  (5.3)
   collide_ship(...)            Chapter 40: walls, ground, boost; ship_section
        |
   handling_auto_pitch(...)     this chapter: the nose follows the road under the ship   (5.4)
        |
   race_tick(...)               this chapter: clock, progress, laps, wrong way, finish   (5.5, 5.6)
```

All the new per-tick quantities follow Chapter 37's rule: a constant is "per NTSC tick" and is multiplied by `dt` (4096 NTSC, 4915 PAL), and every **fraction** is clamped to 4096 (1.0) after that multiplication. The three constants live in `handling_cfg` (`drag` 64, `grip` 1024, `pitch_smooth` 1024) and are patched by the verifier like every `*_cfg` of the part.

World axes as always: +X right, +Y **down**, +Z into the screen; angles are 12.12 (4096 units per turn, `<< 12`), speeds 4.12 per NTSC tick.

### 5.2 Air resistance

Drag is a share of the speed lost every tick. With a constant push `a` (the thrust, 0.75) and a drag fraction `d` (1/64):

```
   v' = (v + a) * (1 - d)        one tick: thrust, then drag
   v  = a * (1 - d) / d          where it stops changing: 0.75 * 63 = 47.25
```

The speed *finds its own limit*. `speed_cap` (60.0) stops being the top speed and becomes a safety limit above it, which a boost pad (+5.0) can reach for a moment before the drag pulls the ship back. Two things make drag different from "a smaller thrust": it acts on a coasting ship (let go of CROSS and the speed decays by 1/64 per tick, a half-life of 44 ticks, three-quarters of a second), and a faster ship loses more.

```
   handling_drag(speed, dt) = speed - fx_mul(speed, min(fx_mul(drag, dt), 4096))
```

It is applied in `ship_update` **between** the thrust and the clamp, so the order of the Chapter 37 steps is the rule (`ship.h`). `fx_mul` floors a negative product (arithmetic shift), as everywhere in the book.

### 5.3 Skid

Until now `vel = forward * speed` every tick: the ship went exactly where it pointed. A skid is the smallest change that stops that: let the velocity *follow* the facing instead of equalling it.

```
   target = forward * speed                         where the nose says the ship should be going
   vel   += (target - vel) * g        g = min(fx_mul(grip, dt), 4096)       per axis, in place
```

```
   seen from above, +z up the page, the nose has just turned 30 degrees right

        vel   new vel   target = forward * speed
         ^      ^      ^
         |     /     /          one tick later vel has closed a quarter of the gap to target:
         |   /    /             the ship still travels mostly straight ahead and slides round the corner
         | /  /
         +
```

`grip` 4096 is Chapter 37's ship (`vel` = `target` at once); 1024 closes a quarter of the gap per tick, a *time constant* of `1 / grip` = 4 ticks (67 ms): the slide is visible but short. A lower grip is an ice rink, a higher one rails. **Why clamp?** A fraction above 1 does not close the gap, it jumps over it: the velocity lands on the far side of the target (with `g` = 2.0 exactly as far off as it started, every tick, forever; above 2.0 further each tick), and PAL's `dt` (1.2) pushes any grip above 3414 past 1.0 (quiz 3).

The position is moved by `vel`, not by `forward * speed`: the one change in step 7. `speed` stays the *scalar the pilot controls* (thrust, brake, drag, cap, the engine pitch); `vel` is where the ship actually goes. Chapter 40's wall response recomputes `vel = forward * speed` after a hit: a hit **ends the skid**, which is the "slides along the wall" feel the chapter wanted.

### 5.4 Auto-pitch

The ship's pitch has been fixed since Chapter 37. The road under it is a plane through the section's centre with normal `up` (Chapter 40, 5.5), and the nose should lie along that plane *in the direction the ship heads*. With the heading `(hx, hz) = (isin(a), icos(a))`, `a = yaw >> 12` (4.12 each):

```
   num = up.x * hx + up.z * hz                 8.24: how far the road's normal leans along the heading
   g   = (-num) / up.y                         the slope along the heading, 4.12 (C division); negative = climbing
   y   = g * 4096 / isqrt(4096^2 + g^2)        the y component of the unit vector along that slope
   p   = the smallest p in -256..256 minimising |isin(p) + y|
   target pitch = p << 12                      12.12; nose up = positive; a climb (y < 0) gives p > 0
```

Bank and slope are different numbers: the banked, climbing start of track 1 (`up` = (-1837, -3650, -285)) heading +z has `g` = -319 (a slope of 0.078, `p` = 50 units = 4.4 degrees up), because only `up.z` leans along the heading; heading +x, the same road is a 27-degree wall (`up.x`), which the **22.5-degree limit** (`PITCH_LIMIT` 256) clamps (quiz 5). A flat or upside-down plane (`up.y > -256`) gives 0.

The pitch then **eases** toward the target: `pitch += fx_mul(target - pitch, min(fx_mul(pitch_smooth, dt), 4096))`, a quarter of the way per tick. Never snap an angle to its target: a ship that jumps 5 degrees at a section boundary looks broken.

**Cost.** This runs on every tick, and Chapter 37's `pitch_angle` scans 2049 angles (about 170,000 instructions). Scanning only -256..256 is still about 40,000. But `isin` **rises strictly** over this range (every step is at least 5 units), so `isin(p) + y` crosses zero once and a binary search finds the crossing in 10 evaluations; the answer is the first `p` with `isin(p) + y >= 0` or the one before it, whichever is closer (the smaller on a tie). Measured: 564 instructions (`calls_are_cheap` allows 2,500). The range was *chosen* so that the algorithm is valid: over the whole range `isin` is flat near the peak and the search would need a scan back (quiz 4).

### 5.5 Laps from progress

Where is the start line? The ship begins on section `S0` (the START section). **Progress** is the number of net steps the ship has made along the ring since the race began:

```
   race_section_step(prev, cur) = +1 if cur is prev's `next`,  -1 if cur is prev's `prev`,  else 0
   each tick:  progress += step         furthest = max(furthest, progress)
   a lap is complete when  progress >= (lap + 1) * section_count
```

```
        ring of N sections (N = 112 on track 1)
             S0-1   S0   S0+1                   progress 0 at the start, N when the ship has gone all the way
        ----+------+-----+---->                  round and enters S0 again from S0-1: that is the start line
              ^ start line                      back over it (N -> N-1 -> N) does not make it 2N
```

Three rules make it honest:

- **Links, not indices.** Follow `next` / `prev` (Chapter 40's rule). The verifier swaps the links of some sections, so `cur == prev + 1` fails.
- **Net progress, not crossings.** A ship that goes back over the line and forward again returns to the same progress: no second lap, and none lost (quiz 6).
- **Jumps count for nothing.** A step between sections that are not neighbours (a respawn, a teleport, a wild frame) is 0: you cannot gain a lap by being thrown forward.

`section_count` is the *track's* (`t->section_count`: 112 on track 1, 104 on track 2), `laps` is `race_cfg.laps` (3; used as `clamp(laps, 1, 8)`). The lap's time is `ticks - (the earlier laps)`; the lap line is the ring at the *start* of `S0` while the ship begins at `S0`'s *centre*, so lap 1 is about half a section (0.2 s) shorter than the others: the book says so rather than hiding it (a stretch goal places the ship a section back).

### 5.6 Wrong way

```
   wrong_way = (furthest - progress >= race_cfg.wrong_way)        (2; used as max(wrong_way, 1))
```

Driving back two sections from the furthest point raises the flag; driving forward by one clears it. Comparing with the furthest point, not with the last tick, is a **hysteresis**: a ship that wobbles over a ring does not flicker the warning (quiz 7). The same number protects the laps: the flag is set after going backward over the line, and the lap count never decreases.

### 5.7 The state machine

```
                START                  GO (the countdown has run out)            last lap done
      TITLE ------------> COUNTDOWN ----------------------------------> RACE ----------------> RESULTS
        ^  ^                  |                                           |                       |  |
        |  +---- START -------+                                           |                       |  |
        |  +---- START ----------------------------------------------------+                       |  |
        |  +---- START ---------------------------------------------------------------------------+  |
        |                                                                                             |
        +-- (LEFT / RIGHT: the track menu, as in Chapter 40)          CROSS: restart: COUNTDOWN <-----+
```

`game.h` has the exact contract per state; in brief:

| State | Per tick | Leaves by |
|---|---|---|
| `TITLE` | nothing moves; LEFT / RIGHT pick the track | START |
| `COUNTDOWN` | `race_countdown_tick`: BEEP, GO; the ship does not move | GO -> RACE; START -> TITLE |
| `RACE` | `ship_update`, `collide_ship`, `handling_auto_pitch`, `race_tick` | last lap -> RESULTS; START -> TITLE |
| `RESULTS` | nothing moves | CROSS -> COUNTDOWN (restart); START -> TITLE |

**Entry work belongs to the entry, not to the state's per-frame code.** `set_state` is given: entering `COUNTDOWN` places the ship on the start line, zeroes the collision counters, `race_reset`s the clock and starts the engine hum; entering `TITLE` or `RESULTS` silences the engine. `game_update` only *decides* when to change state. The restart is therefore the same code path as the first start, which is why it cannot drift from it.

**The countdown** runs in ticks like everything else: a beep on countdown ticks 0, `hz` and 2 `hz` (`SMP_BEEP`), GO on the tick that completes `count_from * hz` ticks (`SMP_GO`, 3 s at 60 Hz). `race_countdown_tick`'s order is the contract: test *before* incrementing for the beep, *after* for GO. When GO or the finish changes the state in the middle of a frame that has several ticks (`frame_ticks` up to 4), the rest of that frame's ticks are dropped: the race clock starts at the first tick after GO, and the lap that ends the race is the last tick it counts. Edge-triggered input everywhere: a held CROSS cannot skip the results screen (quiz 9).

### 5.8 Time and text

One tick is one video frame. The program keeps **ticks** and converts when it prints: `cs = ticks * 100 / hz` (integer division, `hz` = `race_hz()`: 60 NTSC, 50 PAL), `M:SS.cc`. Lap times add up exactly; two lap times compare with `<`. 3,725 ticks print `1:02.08` at 60 Hz and `1:14.50` at 50 Hz (quiz 8).

`race_format_text(race, state, hz)` writes the whole HUD into `race_text[12][32]`; `game.c` draws every non-empty line with `FntSort` (the SDK font, Chapter 34's debug lines sit above at y = 8 and 20). The exact text, so a verifier (and you) can compare it:

| State | Lines |
|---|---|
| TITLE | 0: `BEST LAP m:ss.cc` (only if `race_best > 0`) |
| COUNTDOWN | 0: `GET READY n` (n = `count_from - cd_ticks / hz`, at least 1) |
| RACE | 0: `LAP a/L`; 1: `TIME m:ss.cc`; 2: `LAST m:ss.cc  BEST m:ss.cc` (`-:--.--` where there is none); 3: `WRONG WAY` |
| RESULTS | 0: `RESULTS`; 1..L: `LAP k  m:ss.cc`; L+1: `TOTAL m:ss.cc`; L+2: `BEST m:ss.cc`; L+3: `NEW BEST LAP` |

`snprintf` is not cheap on the R3000: one `race_format_time` costs about 4,700 instructions, so the RACE HUD costs 9,000 to 18,000 instructions a frame (the whole physics tick is about 3,000 without a wall hit: Chapter 40's 2,200 plus this chapter's 700), more than everything else the frame does (see 5.10). It is drawn once per frame, not per tick, which is why it is affordable; a sprite-digit HUD is the stretch goal that removes it.

### 5.9 The best lap

`race_best` is a global in RAM: the fastest lap since power-on, in ticks, 0 for none. At the finish `race_tick` sets `best_lap` (this race's fastest) and, **only if it is strictly better** than `race_best` (or `race_best` is 0), updates `race_best` and sets `new_best`; the results screen says `NEW BEST LAP`, and the title shows `BEST LAP` from then on. A tie is not a new best (the verifier flies one). `race_reset` clears the `Race` but not `race_best`; a restart keeps it. Saving it to a memory card is the stretch goal (the format and the BIOS calls are for another book, or Chapter 42's "next steps").

### 5.10 What the emulator showed

PCSX-Redux, the solution, the verifier's runs:

| Question | Observed |
|---|---|
| Cost of the new calls | `handling_drag` 32 instructions, `handling_skid` 83, `handling_pitch_target` 564 (binary search), `handling_auto_pitch` about 650, `race_tick` 91 to 161, `race_section_step` 48, `race_countdown_tick` 21 |
| Cost of the text | `race_format_time` 4,661; `race_format_text`: 90 (the title, no best lap yet) to 5,200 (the title with one), 1,800 (countdown), 9,000 to 18,000 (race), 12,000 to 62,000 (results, 3 to 8 laps) |
| The pilot's lap (a bot in `probe.lua` that steers at the centre of the section 3 ahead, holds CROSS, brakes in sharp corners) | 2,394 ticks, 39.90 s; 4 wall hits (2 thuds), 2 boost pads (a boost raises the speed to 52.3 for a moment); the 75th percentile of the speed 47.3 (the drag limit is 47.25) |
| Do frames run more than one tick? | 2,810 of 2,812 frames ran exactly one tick (the emulator does not charge GPU time, Chapter 38) |

**Not verified:** how a real console times the frames (the countdown and the clock are in *ticks*, correct at 60 or 50 Hz by construction, not measured on hardware); PAL (the `dt_scale` and `hz` paths are checked by direct calls with the PAL values, not by a PAL run); DuckStation and Mednafen; the *feel* (that is yours: the constants are the knobs).

### 5.11 How the verifier checks

1. **Direct calls** (`directcall.lua`, at the entry of `main`; about 3,200 calls, seed printed): every function of `handling.h` and `race.h` with random and crafted arguments (all sections of both tracks, a patched copy of track 1 with swapped links and a flat `up`), compared with `example/handling_ref.py`: the drag and the skid with PAL's `dt` and out-of-range constants, 287 pitch targets, the auto-pitch of whole ships, 2,000 section steps, 420 `race_tick` calls from crafted states (laps, reversals, jumps, wrong-way limits, ties of the best lap), the countdown, 47 times at both rates, 110 texts in every state.
2. **One lap, driven** (`probe.lua`'s pilot, `laps` patched to 1): every game frame is **replayed** from the previous frame's state, with the pad `ship_update` really received: `ship_update`, `collide_ship`, `handling_auto_pitch`, `race_tick` of the model must give the recorded ship (all 14 words), `ship_section`, `collide_state`, the 19 words of `race`, `race_best` and the sounds raised that frame. Independently of your code: the laps by index arithmetic, the clock, the window for the lap, the top speed, a real skid (the velocity direction leaves the facing by more than 1.7 degrees), the pitch error, the text on screen against the text the model makes of the recorded state; then CROSS restarts and START aborts to the title.
3. **Ghost races** (`ghost`, `track2`): a lap needs 112 section steps, not 112 seconds of driving, so the probe **moves the ship** onto section after section (written into `ship` after every frame) along a scripted route: a backward excursion over the line, a lap flown backward and forward over the line, laps at different paces, **two races in a row** (the first sets the best lap, the second ties it), three laps; then track 2 with two laps (`race_cfg.laps` patched to 2: the program must not hard-code 3 or 112). Those frames cannot be replayed from the previous ship, so the *race* part is replayed from the section the program itself computed.
4. **Mutants** (`verify/mutants.py`): wrong implementations that the checks must catch (section 8).

## 6. Worked example

The numbers of the chapter, from the functions of `example/handling_ref.py` (running it prints the drag, terminal-speed, pitch and time lines):

```
drag     speed 40.0 (163840), NTSC: 163840 - (163840 * 64 >> 12) = 161280 (39.375); PAL (dt 4915): 160800
terminal speed under thrust 0.75: 47.17 after 400 ticks, exactly 47.25 (193536) after 2000
skid     vel (0, 0, 163840), target (81920, 0, 141876) (the nose 30 degrees right, speed 40.0), grip 1024:
         NTSC: vel = (20480, 0, 158349) (7.4 degrees off the straight, 22.6 off the nose); PAL (g = 1228): (24560, 0, 157255)
pitch    section 0, up (-1837, -3650, -285), yaw 0:  num = -285 * 4096 = -1,167,360;  g = 1,167,360 / -3650 = -319;
         y = -319 * 4096 / isqrt(4096^2 + 319^2) = -318;  isin(50) = 315, isin(51) = 321: a tie, the smaller wins:
         p = 50 whole units;  target 204800 (12.12)
         eased from 0: 51200 (12.5 units), 89600, 118400, 140000, ... a quarter of the way each tick
time     3725 ticks: 372,500 / 60 = 6208 hundredths: 1:02.08 (50 Hz: 7450: 1:14.50)
progress ring of 112: ... 111, 112 (lap 1), 111, 110, 111, 112, 113: still one lap; the second needs 224
```

## 7. Project: finish Hoverline

### 7.1 Behaviour

Chapter 40's game, finished. START on the title begins a **countdown** (the ship waits on the start line, "GET READY 3, 2, 1" and three beeps, then GO); the **race** is three laps against a clock, with the lap and time at the top left; the ship has **drag**, a **skid** and **auto-pitch**; driving backward shows WRONG WAY; the third lap ends the race on the **results** screen (the laps, the total, the best lap, NEW BEST LAP if it is one); CROSS restarts, START goes to the title, where the best lap stays.

### 7.2 The contract

`starter/` is Chapter 40's `solution/` with the wiring done and the work stubbed. **Read `handling.h`, `race.h` and `game.h` first: they are the specification.** **Given:** Chapter 40; `ship.c` (calls `handling_drag` and `handling_skid`), `game.c` (`set_state`, the HUD drawing, `debug_toggles`, the readouts), `race_reset`, `race_hz`, the data (`handling_cfg`, `race_cfg`, `race`, `race_best`, `race_text`), `main.c`'s keep-alive list, the disc (nothing new). **You write:**

| Where | Function | What |
|---|---|---|
| `handling.c` | `handling_drag` | 5.2 |
| | `handling_skid` | 5.3 |
| | `handling_pitch_target` | 5.4 (the binary search) |
| | `handling_auto_pitch` | 5.4 |
| `race.c` | `race_section_step` | 5.5 |
| | `race_tick` | 5.5, 5.6, 5.9 |
| | `race_countdown_tick` | 5.7 |
| | `race_format_time` | 5.8 |
| | `race_format_text` | 5.8 |
| `game.c` | `game_update` | 5.7 (the starter handles the title only; its other states do nothing, so the countdown never ends) |

**State the verifier reads and patches:** `handling_cfg` (4 words, **patched**), `race_cfg` (4 words, **patched**: laps, wrong-way limit, countdown seconds), `race` (19 words), `race_best`, `race_text` (12 lines of 32), `game_state`, `state_changes`, `ship`, `ship_section`, `ship_ticks`, `frame_ticks`, `collide_state`, `track_selected`, `audio_stats`, and the calls of `audio_play_sfx` (the sample ids: `BEEP` at the countdown and at a lap, `GO` at the start).

### 7.3 Steps

1. `handling_drag` and `handling_skid` (`air_resistance`, `skid_blend`): the ship now behaves differently at once; `make run` and drive.
2. `handling_pitch_target`, `handling_auto_pitch` (`pitch_target_from_the_road`, `auto_pitch_follows_the_section`, `calls_are_cheap`).
3. `race_countdown_tick`, `race_format_time` and `race_format_text` (`countdown_ticks`, `time_text`, `hud_and_results_text`): put the text on the screen first.
4. `race_section_step`, `race_tick` (`section_step_follows_links`, `lap_counting`, `wrong_way_warning`, `finish_and_best_lap`).
5. `game_update` (`state_machine_in_order`, `countdown_freezes_and_beeps`), then the whole-game checks (`frames_replay_with_the_model` and the rest).

### 7.4 Rules

- Integer arithmetic only; `fx_mul` where a product can pass 32 bits.
- Every constant from `handling_cfg` / `race_cfg` / `ship_cfg`: no 64, no 1024, no 3 laps, no 112 in the code.
- Follow the ring by `next` / `prev`, never `index +- 1`.
- Entry work stays in `set_state`; `game_update` only decides.
- `race_tick` and the auto-pitch run on **every tick**; keep them cheap (a scan of the angles fails `calls_are_cheap`).

### 7.5 Hints

- Write the pure functions first and print their results on the HUD; the contract gives every formula.
- `handling_skid` is Chapter 37's `vel = forward * speed` with `+=` and a fraction: set `grip` to 4096 to see Chapter 37 again.
- The race text is the easiest to get wrong by a space: two spaces in `LAST ...  BEST ...` and `LAP k  ...`.
- A frame can run several ticks: the loop in `game_update` stops when the state changes.
- Holding START on the title enters the countdown once (edge-triggered); do not read START again in the same frame.

### 7.6 Stretch goals

- **Tune it**: change `grip` and `drag` (the verifier pins them to the README's values, so tuning does not break it); find the pair you like for the pad you have.
- **Sprite digits** instead of `FntSort` (the HUD costs up to 18,000 instructions a frame now).
- **A minimum results time** (ignore CROSS for the first 60 ticks).
- **Place the ship one section back** so that lap 1 is as long as the others.
- **Best lap on the memory card** (BIOS `McdXXX` calls; another book's chapter).
- **A ghost**: record `pos` per tick in the first lap and draw it in the second.
- **Pitch from the real quad**: interpolate the height between the section's two rings.

## 8. Verification

```sh
source tools/env.sh
parts/part-07-capstone-hoverline/ch41-handling-game-loop-and-polish/verify/verify.sh            # your starter/
parts/part-07-capstone-hoverline/ch41-handling-game-loop-and-polish/verify/verify.sh --solution # the reference
```

About two and a half minutes: a build, a direct-call run, the driven lap (3,800 frames), two ghost runs.

| Check | What it means | If it fails |
|---|---|---|
| `air_resistance`, `skid_blend` | the two blends against the model, PAL `dt`, constants patched out of range | the clamp to 4096, the order of operations, a constant in the code |
| `pitch_target_from_the_road`, `auto_pitch_follows_the_section` | the slope along the heading, the 513-angle minimum, the easing | sign of `g`, the tie rule, `up.y > -256`, an invalid section |
| `calls_are_cheap` | instruction limits per call: pitch 2,500, auto-pitch 3,000, `race_tick` 1,500, `race_section_step` 400, drag 200, skid 400 | a scan instead of the binary search; a loop over the whole track |
| `section_step_follows_links` | +1 / -1 / 0 by the links (some swapped by the verifier) | `index +- 1` |
| `lap_counting`, `wrong_way_warning`, `finish_and_best_lap` | `race_tick` field by field over 420 crafted ticks | the threshold, the tie, `new_best`, laps clamped to 1..8 |
| `countdown_ticks`, `time_text`, `hud_and_results_text` | the countdown's order, the time format and its limits, all 12 lines in every state | beep before / after the increment, a missing space |
| `state_machine_in_order` | the states 1 2 3 1 2 0 and one `state_changes` per change | `set_state` call sites |
| `countdown_freezes_and_beeps` | the ship still, beeps on ticks 0 / 60 / 120, GO once | the sounds, the ticks that run after GO |
| `frames_replay_with_the_model` | every frame of three runs against the model | the first differing field |
| `laps_cross_the_start_line`, `race_clock_counts_ticks` | laps by index arithmetic, the clock, the lap times add up | progress, the reset |
| `one_lap_in_a_window`, `top_speed_is_drag_limited`, `ship_slides_in_turns`, `pitch_follows_the_road` | facts independent of the model: 1,879..4,500 ticks for the lap, the speed settles near 47, the velocity leaves the facing, the pitch follows | drag, grip, auto-pitch not called |
| `text_matches_the_race`, `results_screen`, `restart_and_abort`, `wrong_way_warning_in_the_game`, `second_track` | what the screen shows; the best lap across races; the restart; two laps on track 2 | the text, `race_reset`, `section_count` |

A pass ends with `CHAPTER 41: PASSED (26/26 checks)`. The untouched starter builds and fails. Nineteen wrong implementations were tried with `verify/mutants.py` (no drag, drag without `dt`, an unclamped fraction, no skid, a skid on two axes, a linear scan for the pitch, the pitch with the wrong sign, auto-pitch never called, ring steps by index, 112 sections hard-coded, backward steps not subtracted, a wrong-way flag that never clears, a tie as a new best, a best lap not kept, a countdown one tick long, no lap chime, a restart that keeps the old race, unpadded seconds, START restarting from the results): all nineteen make `verify.sh` exit 1, each caught by the checks it should be (`python3 verify/mutants.py`, about 2.5 minutes each on an idle machine, about 45 minutes in all; not part of CI). **Not verified:** the feel, the sound itself (the calls are logged, not heard), dropping the rest of a frame's ticks after GO or the finish (the emulator almost never runs a frame of more than one tick, 5.10, so a loop that runs on passes), PAL as a run, other emulators, and a *three-lap* race flown by real driving (the pilot flies one lap; three laps are flown by the ghost: the laps are counted by the same code, the physics of laps 2 and 3 is the physics of lap 1).

## 9. Common pitfalls

- **A fraction above 1.** `fx_mul(grip, dt)` can pass 4096 on PAL; clamp it.
- **Rounding that floors the wrong way.** `fx_mul` floors; `/` truncates. The contract says which is used where (`g` truncates, `fx_mul` floors).
- **Laps by crossings.** Net progress, not "entered the start section".
- **Counting by `index + 1`.** The ring is a linked list.
- **A scan on every tick.** The pitch target is asked 60 times a second.
- **Entry work in the per-frame code.** It runs every frame, or only once by luck of the edge; put it in `set_state`.
- **Level-triggered restart.** A held button restarts the race the frame it ends.
- **`snprintf` in a loop.** Every format is thousands of instructions; once a frame is fine.
- **Forgetting the rest of the frame's ticks.** A frame can run 4 ticks; stop when the state changes.
- **The clock in milliseconds.** Ticks add up exactly; convert when printing.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- `example/handling_ref.py`: the model, readable in one sitting (`python3 example/handling_ref.py` prints the numbers of section 6).
- Appendix E.10 (`.TRK`: section links, `up`, the START faces).
- psx-spx: *GPU Timings* (the frame rate that a tick counts), *Controller and Memory Card* (for the stretch goal).
- Game Programming Patterns (Nystrom): *State*, *Game Loop*.
- Chapter 42 (shipping: a release build and the cross-emulator tests of this game).
