# Chapter 37 quiz

**1.** The ship's yaw is 1024 (a quarter turn, 4096 per turn) and its pitch is 0. What is `forward`, and which way does the nose point in the book's axes? What changes at yaw 3072?

<details><summary>Answer</summary>

`forward = (sin yaw, 0, cos yaw) = (4096, 0, 0)` in 4.12: the nose points along **+x**, the right side of the world. Positive yaw turns +z toward +x (the `vy` of `RotMatrix`, no sign change). At yaw 3072 (three quarters) it is `(-4096, 0, 0)`: along -x. LEFT therefore **lowers** the yaw.
</details>

**2.** The camera must be "behind and above" the ship. A student writes `eye.y = ship.y + cam_height`. What does the player see, and what is the right line?

<details><summary>Answer</summary>

+y is **down** in the book's axes, so the eye is `cam_height` units *below* the ship: the camera looks up at the belly and, over a road, from under the floor. The right line is `eye.y = ship.y - cam_height` (and the same sign care for `forward.y`: nose up is negative y). The verifier's check is the sign of `eye.y - ship.y` and the dot product `(eye - pos) . forward < 0`.
</details>

**3.** The speed is 245,000 (4.12), `speed_cap` is 245,760 and CROSS is held with `thrust = 3072`. Give the speed after one tick. With SQUARE held instead, `brake = 6144` and speed 5000, what is it?

<details><summary>Answer</summary>

`245000 + 3072 = 248072`, clamped to **245760**. Brake: `5000 - 6144 = -1144`, clamped to **0**: the ship stops and never reverses (`speed >= 0`). The clamp comes after both adjustments, so holding both buttons applies `thrust - brake` and then clamps.
</details>

**4.** One tick at NTSC adds `thrust = 3072` to the speed. What does a PAL tick add, with `dt_scale = 4915`? Why is the PAL step bigger?

<details><summary>Answer</summary>

`fx_mul(3072, 4915) = (3072 * 4915) >> 12 = 3686`. A PAL frame lasts 1/50 s, 1.2 times an NTSC frame (1/60 s), so everything that happens per tick is multiplied by 60/50 = 1.2 (4915 / 4096 = 1.19995). The ship then gains the same speed and covers the same distance per **second** in both standards, up to the integration error: the steps are coarser in PAL, and first-order Euler integration makes the two routes differ by about 2%.
</details>

**5.** The game takes 2 vertical blanks to draw a frame. What should the physics do, and what happens to a game that calls `ship_update` once per frame?

<details><summary>Answer</summary>

Run **two** ticks that frame (`frame_ticks` = the vertical blanks since the last frame, clamped to 1..4): the world moves one fixed step per blank whatever the drawing costs. A game with one update per frame runs at half speed whenever a frame takes two blanks: the ship is slower exactly where the scene is heavy.
</details>

**6.** Why does the book build the ship matrix as `Ry * (Rx * Rz)` and not use `RotMatrix(&{pitch, yaw, roll})` directly?

<details><summary>Answer</summary>

`RotMatrix` multiplies `Rx * Ry * Rz`: the pitch is applied **last**, about the world's x axis. With the ship turned 90 degrees, that axis is the nose direction, so pitching would roll the ship instead of raising its nose (and `forward` at yaw 1024 would not depend on the pitch at all). `Ry * Rx * Rz` turns the ship about the world's vertical first, then pitches about the ship's own right axis, then rolls about the nose: the order a pilot expects.
</details>

**7.** `yaw_vel` is -200,000 (12.12 angle per tick), LEFT is no longer held, `yaw_damp = 512` (1/8). What is `yaw_vel` after one tick, and why is there a dead zone around zero?

<details><summary>Answer</summary>

`yaw_vel -= fx_mul(yaw_vel, 512)`: `fx_mul(-200000, 512) = -25000`, so `yaw_vel = -175000`: each tick removes an eighth. The rate decays geometrically and never quite reaches 0 with integer arithmetic (`fx_mul` rounds toward minus infinity, so a positive rate of a few units would stay forever). A value below 16 in magnitude (0.004 angle units per tick) is therefore set to 0 so that the ship stops turning, and the roll target (`yaw_vel * roll_gain`) goes to 0 with it.
</details>

**8.** Turning left, which way must the roll go, and how does the sign convention (right wing down is positive) tell you the roll target's sign?

<details><summary>Answer</summary>

Banking into a turn: the **left** wing goes down. With positive roll = right wing down, that is a **negative** roll. LEFT gives a negative `yaw_vel`, so `roll_target = yaw_vel * roll_gain` is negative too: the same sign, no extra minus. The roll then follows the target smoothly (`roll += (target - roll) * roll_smooth`), and returns to 0 after the turn.
</details>
