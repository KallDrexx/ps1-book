# Chapter 39 quiz

**1.** A sample was recorded at 11,025 Hz. What pitch value plays it at its natural speed, and what does the value `0x1000` do to it?

<details><summary>Answer</summary>

`pitch = rate * 4096 / 44100 = 11025 * 4096 / 44100 = 1024 = 0x0400`. The SPU always outputs 44,100 samples per second and steps through a voice's sample by `pitch / 4096` per output, so `0x1000` is the step 1.0: the 11,025 Hz recording would be played four times too fast (two octaves up).
</details>

**2.** `SPU_CH_ADDR(v)` must be given the address of a sample at byte `0x4150` of SPU RAM. What value is written, and why is a sample's address a multiple of 8?

<details><summary>Answer</summary>

`0x4150 / 8 = 0x082A`: the register counts **8-byte units**. The SPU's RAM is addressed in units of 8 bytes, and ADPCM blocks are 16 bytes, so every block starts on an 8-byte boundary; the book keeps samples on 64-byte boundaries because the DMA transfer works in 64-byte blocks.
</details>

**3.** Why does `ENGINE.VAG` end with flags 4 and 3, while `THUD.VAG` ends with a flag-1 block? What would happen to the engine if it ended like the thud?

<details><summary>Answer</summary>

Flag 4 on a block records its address as the loop point; flag 3 (end + repeat) on the last block makes the SPU jump back to that point and keep playing, so the hum never ends. Flag 1 (end, no repeat) makes the SPU set the voice's ENDX bit and **mute it**: right for a one-shot. An engine ending in flag 1 would play once (1 s at its native rate, 2 s at the idle pitch) and go silent; the verifier sees it as an envelope level of 0.
</details>

**4.** The engine's pitch is `min((base * mul) >> 12, 0x3FFF)` with `mul = idle_mul + (((speed >> 8) * span_mul) >> 10)`. Why is the speed shifted by 8 *before* the multiplication, and why is the mapping guaranteed to be non-decreasing?

<details><summary>Answer</summary>

`speed` is 4.12 fixed point and reaches 245,760; times a `span_mul` of thousands it would pass 2^31. Shifting first keeps every product within 32 bits (at the price of a resolution of 1/16 unit per tick, still 960 distinct steps over the speed range). Non-decreasing: every operation (shift, multiply by a non-negative constant, add, multiply by `base`, shift, `min`) preserves order, and negative speeds are clamped to 0 first.
</details>

**5.** Two consecutive sections both have boost faces (28 and 29). The ship drives through both. How many chimes, and why? And when does a thud fire for a ship that stays off the road for 100 frames?

<details><summary>Answer</summary>

Two: the boost event fires when the nearest section **changes** into a section with a boost face, and 27 to 28 and 28 to 29 are two changes (staying inside one section raises nothing). The thud fires once, when the ship **first** goes off the road (`|lateral| > half_width` is true now and was false the frame before); the 99 frames after it are "was already off" and stay quiet. Coming back on and going out again is a new thud.
</details>

**6.** `audio_play_sfx` keys the voice off before the key-on, and writes all the registers before it. Why those orders?

<details><summary>Answer</summary>

A key-on **starts** the voice with whatever the registers contain at that moment: pitch, address and volume must be final first, or the first samples play with the previous sound's settings (a click or a wrong pitch). The key-off first guarantees a voice that is still playing an earlier sound restarts from its envelope's beginning instead of continuing; with the 23-voice round robin it rarely matters, but it makes the call correct for any pool size.
</details>

**7.** The music does not play and no error is reported. Name three independent things that can silence a CD-DA track that is being played.

<details><summary>Answer</summary>

(1) The SPU side: its CD input volume `SPU_CD_VOL_L/R` is 0, or the CD-audio-enable bit (bit 0) of `SPU_CTRL` is clear; (2) the drive side: the CD volume matrix (`CdMix`) routes the channels nowhere (values 0); (3) the source: the track number is wrong (track 1 is the data track) or the disc image has no audio track. (The book also sets `CdlModeDA`, as the SDK's examples do; psx-spx describes that bit as allowing the drive to *read* audio sectors.) The verifier checks the commands and registers (`music_plays_from_the_cd`) because it cannot hear the result.
</details>

**8.** How can a verifier prove that a sample is in SPU RAM when Lua cannot read the SPU, and which parts of the evidence come from the emulator rather than from the program?

<details><summary>Answer</summary>

The emulator writes an **SPU dump** that contains the RAM image; the verifier compares the five VAG bodies with it byte for byte at the addresses the program says it used (and checks that the start-address register of each key-on holds the same address / 8). The register values themselves come from a write breakpoint that decodes the store instruction and reads the stored register. Neither depends on how the program uploaded the data (DMA or FIFO), but both depend on this emulator build's features, and neither tells whether it *sounds* right.
</details>
