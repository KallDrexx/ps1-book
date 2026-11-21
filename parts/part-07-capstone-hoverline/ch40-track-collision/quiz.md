# Chapter 40 quiz

**1.** The road edge runs from `a = (0, 0)` to `b = (1000, 0)` and the road lies on the side of `r = (500, 700)`. A ship is at `p = (300, 40)`. What are `dist` and the normal `n` of `collide_edge_dist`?

<details><summary>Answer</summary>

`e = (1000, 0)`, `len = 1000`. `cross(v) = ex * vz - ez * vx = 1000 * vz`. For the reference point `cross(r - a) = 700,000 > 0`, so `s = +1`. For the ship `cross(p - a) = 40,000`, so `dist = 40,000 / 1000 = 40`: the ship is 40 units inside the edge, on the road's side. The normal is `(s * -ez * 4096 / len, s * ex * 4096 / len) = (0, 4096)`: a unit vector pointing along +z, toward the reference point. A dot product with the unit normal gives the same number: `(p - a) . n = 40 * 4096 / 4096`. The cross product with the edge *is* the dot product with the edge's perpendicular, just not yet divided by the length.
</details>

**2.** Chapter 38's `ship_section` is the nearest center. Why is that not enough for collision, and what does `collide_section` test instead?

<details><summary>Answer</summary>

The nearest center is decided by the *bisector plane* between two centers, which passes through the midpoint of the line joining them. The sections meet at a *ring*, a line across the road that is not that plane when the road bends or when the two sections differ in length (a point near the ring can be closer to one center while lying inside the other section's quad). Colliding with the wrong section's edges pushes the ship the wrong way. `collide_section` tests the two ring lines of the section: ahead of the end ring means the next section, behind the start ring the previous one, and it walks until the ring tests agree. The edges used for the push are then those of the section the ship is actually over.
</details>

**3.** A hit pushes the ship by `(n.x * depth) >> 12`. The ship is 30 units inside the edge and `radius` is 90. What is `depth`, and what happens to the edge distance after the push? Why can it end up at 89 instead of 90?

<details><summary>Answer</summary>

`depth = radius - d = 60`. The push moves the ship 60 units along the unit normal, so the new distance is `d + 60 = 90`. The normal is a 4.12 vector rounded toward zero (its length is slightly below 4096), and the shift floors the product, so the displacement can fall short by one unit: 89. The verifier accepts `radius - 3` for exactly that reason; it checks that the ship is *inside the road*, not that it sits at an exact distance.
</details>

**4.** The yaw correction computes `err = ((target - yaw + HALF) & ANGLE_MASK) - HALF`. What does it do, and what goes wrong with `err = target - yaw`?

<details><summary>Answer</summary>

Angles live on a circle of `ANGLE_TURN = 2^24` units. `target - yaw` can be anywhere in `(-2^24, 2^24)`, and a ship at yaw 10 whose target is `ANGLE_TURN - 10` should turn by 20 units to the left, not by nearly a whole turn to the right. Adding `HALF`, masking and subtracting `HALF` wraps the difference into `[-HALF, HALF)`, the *shortest* way round. Without it the ship would sometimes spin the long way every time it touches a wall.
</details>

**5.** Why must the correction be `fx_mul(err, yaw_fix)` and not `(err * yaw_fix) >> 12` in plain 32-bit `int` arithmetic?

<details><summary>Answer</summary>

`err` can be as large as `2^23` (half a turn in 12.12 angle units) and `yaw_fix` is up to `4096 = 2^12`: the product reaches `2^35` and overflows 32 bits. At the default `yaw_fix` of 2048 (`2^11`) it already overflows for any error above `2^20`, a sixteenth of a turn (22.5 degrees), an ordinary hit. `fx_mul` of the `psxe` library keeps the full 64-bit product and shifts afterwards. A 32-bit multiply would give a wrapped, meaningless correction, often in the wrong direction.
</details>

**6.** Sections 28 and 29 of track 1 are both boost-pad sections, but the ship gets one speed impulse for driving through both. Why, and how is that different from Chapter 39's chime?

<details><summary>Answer</summary>

Chapter 40 decides it from the **face under the ship**: `on_boost` is 1 while the ship is over a face with `TRK_BOOST`, and the impulse comes on the *entry* (0 to 1). Driving from section 28's center lane into section 29's keeps `on_boost` at 1, so there is no new entry. Chapter 39 looked at the *section* (a change into a section that has a boost face), so two sections gave two chimes, and a ship in a side lane of a pad section also got one. Using the face is more accurate and is why the chime now comes from `collide_ship`.
</details>

**7.** A hit raises `EV_THUD` only if `ship_ticks - last_hit >= thud_gap`, yet `last_hit` is set on *every* hit. Why not set it only when a thud is raised?

<details><summary>Answer</summary>

Because a ship sliding along a wall hits on almost every tick. If `last_hit` changed only on thuds, a thud would repeat every `thud_gap` ticks for as long as the ship scraped the wall (five per second at 12 ticks). Updating it on every hit makes the gap a *quiet time*: the next thud needs 12 ticks without any contact, so one scrape is one thud. Leaving the wall for a moment and returning is a new impact.
</details>

**8.** `track_switch(2)` fails because `TRACK2.TRK` has a bad magic. Name two ways an implementation can damage the running game, and what it does instead.

<details><summary>Answer</summary>

(1) Parsing straight into the global `track`: `track_parse` zeroes its output on failure, so the old track is gone and the game has no track. (2) Freeing the old image *before* the new one is known to be good: `track` then points into freed memory. The correct order is to load the file, parse into a *separate* `Track`, and only when that succeeded copy it over `track`, free the old image and keep the new one; on any failure free the **new** image and leave everything else alone.
</details>

**9.** After a `track_switch`, why is the music restarted?

<details><summary>Answer</summary>

The drive has one laser. Reading a file means seeking to the file's sectors, which stops the CD-DA track that was playing from the audio track. Nothing tells the program: the auto-pause callback does not fire, so Chapter 39's restart never triggers. The program must send `CdlPlay` again after it has used the drive, and the same would be true of any later load while music plays.
</details>
