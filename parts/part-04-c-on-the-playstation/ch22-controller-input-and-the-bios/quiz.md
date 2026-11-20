# Chapter 22 Quiz

**1.** What is the BIOS, and how does a program call one of its functions?

<details><summary>Answer</summary>

It is the firmware in ROM that boots the console and provides kernel services (memory and string helpers, file and memory-card access, the pad driver, events, threads) and the interrupt handler. A program calls a function through one of the kernel tables: it puts the function number in `$t1` and jumps to `0xA0`, `0xB0` or `0xC0`. The SDK wraps this in small stubs such as `InitPAD`.
</details>

**2.** A digital pad's button word is `0xFEFF` (Left bit = bit 7). Which buttons are down? What would the active-high mask be?

<details><summary>Answer</summary>

`0xFEFF` = `1111 1110 1111 1111`: the only 0 bit is bit 8, so only **L2** is down (active-low). The active-high mask is `~0xFEFF & 0xFFFF = 0x0100`. (Bit 7, Left, is a 1, so Left is up.)
</details>

**3.** An idle pad reads `0xFFFF`. A program keeps `if (raw & PAD_UP) y--;`. What happens?

<details><summary>Answer</summary>

The pad is active-low, so Up being *up* gives a 1 bit: the cursor moves up whenever Up is **not** pressed, and stops while it is held. Invert first (`~raw`) or test `!(raw & PAD_UP)`.
</details>

**4.** Fill in the table for a button that is down in frames 3 to 5 only (frames 1 to 7). In which frames are `held`, `pressed` and `released` true?

<details><summary>Answer</summary>

`held`: 3, 4, 5. `pressed`: 3 (down now, up before). `released`: 6 (up now, down before). Press and release are one-frame events; held lasts as long as the button is down.
</details>

**5.** Why must a pad buffer be `static` (or global), not a local array in `input_init`?

<details><summary>Answer</summary>

The driver keeps writing into it from the VBlank interrupt after `input_init` has returned. A local array lives on the stack and is reused by other calls, so the driver would corrupt them.
</details>

**6.** Why does `input_update` check `stat` and `type` before using `btn`?

<details><summary>Answer</summary>

Not every buffer holds a pad answer. Before the first poll it still holds its initial zeros (a `static` array): `stat` 0 looks valid, and zero bits read as active-low mean every button is down. An empty port reports `stat = FFh`. Only `stat == 0` together with a known `type` (4, 5 or 7) says the buffer holds a real answer.
</details>

**7.** A colour should change once per press. Your code calls `input_held(INPUT_CROSS)` instead of `input_pressed`. What does a 30-frame hold do, and why?

<details><summary>Answer</summary>

The colour advances 30 times: `held` is true on every frame the button is down, and the rule runs every frame. `pressed` is true on the first frame only.
</details>

**8.** What goes wrong if `input_update` runs twice in one frame?

<details><summary>Answer</summary>

The second call copies the new reading into `before` too, so `now == before` and `pressed` and `released` are false for that frame: every edge is lost (and an edge seen by code between the two calls disappears). Call it once per frame.
</details>

**9.** Why does the book's `input_pressed` not clear a flag after it returns 1?

<details><summary>Answer</summary>

Then only the first caller in a frame would see the press; a second system asking (a menu and the player, say) would miss it. The queries are pure functions of `now` and `before`, so any number of callers get the same answer.
</details>

**10.** The harness runs OpenBIOS, not Sony's BIOS. Name one thing you should not depend on for that reason.

<details><summary>Answer</summary>

The exact timing of the first poll, or anything else the BIOS writes that the SDK does not document (what the rest of a 34-byte buffer holds, say). Stick to what a poll writes: `stat`, `type` and `btn`, checked before use.
</details>
