# Chapter 41 quiz

**1.** Each tick the ship gains 0.75 of speed from the thrust and then loses 1/64 of its speed to drag. Where does the speed settle, and why is it not the 60.0 of `speed_cap`?

<details><summary>Answer</summary>

The speed settles where one tick changes nothing: `v = (v + 0.75) * (1 - 1/64)`, so `v / 64 = 0.75 * 63 / 64`, `v = 0.75 * 63 = 47.25`. A force that is proportional to the speed grows until it cancels the constant one, so the speed approaches a limit by itself; the cap is only a safety limit above it (a boost pad pushes the ship over 47.25 for a moment, and the drag then pulls it back). The verifier's ship settles at 47.2 to 47.3 because `fx_mul` floors.
</details>

**2.** The ship moves at `vel = (0, 0, 163840)` (40.0 straight ahead). Its facing now points 30 degrees to the right, so `forward * speed` is `target = (81920, 0, 141876)`. With `grip` = 1024 (1/4) and NTSC `dt`, what is `vel` after one tick, and how far off the facing does the velocity point?

<details><summary>Answer</summary>

`vel[i] += fx_mul(target[i] - vel[i], 1024)`, a quarter of the gap per axis: `x = 0 + 81920 / 4 = 20480`, `z = 163840 + (-21964 * 1024 >> 12) = 163840 - 5491 = 158349`. The velocity points `atan(20480 / 158349)` = 7.4 degrees to the right while the nose points 30: the ship is travelling 22.6 degrees away from where it looks, which is a skid. The gap closes by a quarter each tick, so after four ticks about 68% of it is gone and after ten ticks 94%: the *time constant* of the slide is `1 / grip` ticks (4 ticks, about 67 ms).
</details>

**3.** Why does `handling_skid` clamp the fraction to 4096 *after* multiplying it by `dt`? What would `grip` = 8192 (2.0) do without the clamp?

<details><summary>Answer</summary>

A fraction above 1 does not close the gap, it overshoots it. With `g = 2.0`, `vel += 2 * (target - vel)` gives `vel' = 2 * target - vel`: the velocity jumps to the *far side* of the target by the same distance it was on the near side, and every tick repeats it, so the error never shrinks and the ship vibrates. A milder version happens with a perfectly sensible `grip` when PAL's `dt` (4915 = 1.2) scales it: `grip` 4096 (no skid) would become 1.2, an overshoot of 20% of the gap every tick, so the velocity swings from one side of the facing to the other while it settles, which is exactly what "no skid" must not do. The clamp turns any too-large fraction into "arrive now", which is the physically meaningful limit. The same clamp protects drag and the pitch smoothing.
</details>

**4.** `handling_pitch_target` needs the angle whose sine is `y`. Chapter 37's `pitch_angle` scans 2049 angles. Why does this chapter search -256..256 with a binary search instead, and how many `isin` calls does it need?

<details><summary>Answer</summary>

The function runs on every tick, and a scan costs tens of thousands of instructions (the verifier's limit is 2,500 for the whole call). On -256..256 (the limit is 22.5 degrees, far more than any road climbs) `isin` rises strictly: every step is at least 5 units, so `isin(p) + y` crosses zero exactly once and a binary search finds the crossing. 513 candidates need `ceil(log2(513))` = 10 evaluations, plus two to compare the neighbours (the answer is the first angle with a non-negative value, or the one before it if that is closer; on a tie the smaller angle). Over the whole -1024..1024 range this would not work: `isin` is flat near the peak, several angles share a value, and "the first of them" would need a scan back. Choosing the domain so that an algorithm is valid is part of the design.
</details>

**5.** Section 0 of track 1 has `up = (-1837, -3650, -285)`: the road is banked (`up.x`) and climbs (`up.z`). The ship heads along +z (`yaw` 0). Then it heads along +x. Which components of `up` decide the pitch target in each case?

<details><summary>Answer</summary>

`g = (-(up.x * hx + up.z * hz)) / up.y` with `(hx, hz) = (isin(yaw), icos(yaw))`. Heading +z, `(hx, hz) = (0, 4096)`: only `up.z` counts, `g = -(-285 * 4096) / -3650 = -319` (a climb of 0.078, pitch target 50 whole units = 4.4 degrees nose up). The bank (`up.x`) tilts the road *across* the heading and does not change the slope *along* it. Heading +x, `(hx, hz) = (4096, 0)`: only `up.x` counts, and the slope is steep (`g = -2061`, about 27 degrees up the side of the bank), which the 22.5 degree limit clamps. The same road has different slopes in different directions; the target must be recomputed from the *heading* every tick.
</details>

**6.** A track has 112 sections and the ship starts on section 0. Its progress goes 0 ... 111, 112 (a lap), then 111, 110, then 111, 112, 113. How many laps are counted? What goes wrong in an implementation that counts "entered section 0 from section 111"?

<details><summary>Answer</summary>

One. The lap is counted when `progress` reaches 112; the back-and-forth around the line moves it 112, 111, 110, 111, 112, 113, and the next lap needs 224. The simpler rule "a lap is counted whenever the ship enters the start section from the previous one" counts the second crossing of the line (110 -> 111 -> 112 enters section 0 forward again) as a lap, so a player could drive back and forth over the line to collect laps. Net progress with links (+1 along `next`, -1 along `prev`) cannot be cheated that way, and it also gives the wrong-way test for free.
</details>

**7.** `wrong_way` = `furthest - progress >= 2`. The ship's `furthest` is 50. What are `progress` and the flag if it goes back to 49, to 48, then forward again to 49 and 50? Why compare with `furthest` rather than with the previous tick?

<details><summary>Answer</summary>

49: gap 1, no warning. 48: gap 2, **warning**. Forward to 49: gap 1, the warning clears; 50: gap 0. Comparing with the previous tick would flicker the warning on for one tick whenever a section is crossed backwards (a ship that slides 10 units over a ring while it rotates, or the wall response turning it) and off at the next tick; comparing with the *furthest point* means that the player has to go a real distance backwards before they are told, and has to come back by the same distance before the warning goes, a hysteresis of two sections.
</details>

**8.** 3725 ticks have passed in the race. What does the timer show at 60 Hz and at 50 Hz? Why does the program count ticks and convert only when it prints?

<details><summary>Answer</summary>

`3725 * 100 / 60 = 6208` hundredths (integer division, 6208.33 rounded down): `1:02.08`. At 50 Hz `3725 * 100 / 50 = 7450`: `1:14.50`. The game's clock is the tick (one per video frame), exactly the unit in which the physics advances, so lap times add up exactly (a total is the sum of its laps with no rounding drift) and two laps can be compared with `<` as integers. Converting to hundredths at every tick would accumulate rounding, and a PAL machine would have to know its own rate in a dozen places instead of one (`race_hz`).
</details>

**9.** At the results screen the player may be holding CROSS (they were accelerating when they crossed the line). Why does the restart use `input_pressed(INPUT_CROSS)` rather than `input_held`?

<details><summary>Answer</summary>

`input_pressed` is true only on the frame the button *goes down* (Chapter 22). With `input_held`, the results screen would be left on the very frame the race ended, because the throttle button is still down, and the player would never see their time. The edge-triggered test needs a fresh press, so the player has to let go and press again, which also means that START and CROSS on the results act once, not once per frame. (Holding the button for a *minimum time* before accepting input is the other half of the polish: stretch goal.)
</details>

**10.** The countdown starts when `set_state(STATE_COUNTDOWN)` runs; `race_countdown_tick` beeps when `cd_ticks % hz == 0` before incrementing and answers GO when `cd_ticks >= count_from * hz` after it. At 60 Hz with `count_from` 3, on which countdown ticks do the beeps and GO sound, and at which times?

<details><summary>Answer</summary>

Beeps on ticks 0, 60 and 120 (the first at once, then one per second); GO on tick 179, the 180th tick (`cd_ticks` has just become 180). The three beeps are at 0 s, 1 s and 2 s and GO is three seconds after the countdown began, so the player hears "3, 2, 1, GO" at equal intervals; the first beep belongs to tick 0, not to tick 1, because the test happens before the increment. The race clock starts at zero on the *next* tick: the time the countdown took is never part of a lap.
</details>
