# Chapter 27 Quiz

**1.** After `gte_ldv3c(&cube[0]); gte_rtpt();`, which registers hold the three screen points and which the three depths? Which store macros read them?

<details><summary>Answer</summary>

The points are in `SXY0`, `SXY1`, `SXY2` (vertex 0 first), read with `gte_stsxy3c(p)` or `gte_stsxy3(a, b, c)`. The depths are in `SZ1`, `SZ2`, `SZ3` (`SZ0` still holds an older value), read with `gte_stsz3c(p)` or `gte_stsz3(a, b, c)`.
</details>

**2.** Why is `lwc2 $0, 0(a0)` cheaper than `lw t0, 0(a0)` followed by `mtc2 t0, $0`? When would you use `mtc2` anyway?

<details><summary>Answer</summary>

`lwc2` moves the word from memory straight into the GTE register: one instruction, no CPU register, no load delay to cover. Use `mtc2` when the value is computed on the CPU (`gte_ldsxy3` loads screen points that are already in CPU registers). Control registers cannot be loaded with `lwc2` at all: they need `lw` + `ctc2`.
</details>

**3.** A cube has 8 corners and `RTPT` takes 3. A reader writes three batches (0-2, 3-5, 6-8) with `gte_stsxy3c(&screen_xy[i][c])` after each. What goes wrong, and name two ways to fix it.

<details><summary>Answer</summary>

The last batch transforms whatever follows `cube[7]` and its three-word store writes `screen_xy[i][6]`, `[7]` and `[8]`; `[8]` is cube `i + 1`'s corner 0 (and past the array for the last cube). Fixes: make the last batch corners 5, 6, 7 (corner 5 is transformed twice, harmlessly); or pad with a valid vertex and store only two words; or do corners 6 and 7 with `RTPS`.
</details>

**4.** `RTPS` takes 15 cycles. In the worked example, 4 ALU instructions between the command and the read cost nothing, 16 cost 19 cycles more. Explain both, and what changes on real hardware.

<details><summary>Answer</summary>

The read waits for the command to finish, so the CPU is idle for the rest of its 15 cycles. Instructions that need no GTE register fill that idle time for free. When there are more than the window holds, the extra ones run after the command is done and cost their full price. PCSX-Redux's interpreter charges 2 cycles per instruction, so the window holds about 7. That is the emulator's model: on hardware an ALU instruction from the cache costs about 1 cycle (more fit) and a load from RAM several (fewer fit).
</details>

**5.** Which of these can run while an `RTPT` is in progress without stalling: `addiu` on a CPU register, `lw` from RAM, `swc2` of `SXY0`, `mfc2` of an unrelated register, a second `cop2` command?

<details><summary>Answer</summary>

`addiu` and `lw` run freely. The `swc2`, the `mfc2` (any register) and a second command all wait for the first command to finish (the interlock); the worked example shows it for a read of an unrelated register.
</details>

**6.** A path 1 reports 52 % fewer cycles than path 0, where the reference manages 31 %. Why is that a warning sign rather than a triumph, and how does the verifier catch the usual cause?

<details><summary>Answer</summary>

Faster than the batching can explain means work was skipped: for example one cube is transformed and its results copied to the others. Speed only counts when the output is identical. The verifier compares every corner of every cube with the reference, and counts the `RTPT` commands that actually run (at least two per cube).
</details>

**7.** You replace `gte_rtpt()` with a bare `gte_rtpt_b()` (or `cop2 0x0280030`) right after the `lwc2`s. The emulator still shows correct numbers. Why is that not a pass, and how does the verifier catch it?

<details><summary>Answer</summary>

psx-spx gives GTE register loads a two-instruction delay, and the SDK macro puts two `nop`s before every command for it (the book's rule: two instructions after any `lwc2`/`mtc2`/`ctc2`). The emulator does not model that hazard, so it computes the right numbers anyway, but real hardware may start the command on stale inputs. The verifier scans the disassembly of your objects and fails any command that follows an `lwc2`/`mtc2`/`ctc2` within two instructions.
</details>
