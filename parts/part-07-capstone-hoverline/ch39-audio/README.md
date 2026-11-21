# Chapter 39: Audio

## 1. Concept

*Hoverline* has been silent. This chapter gives it an **engine hum whose pitch follows the ship's speed**, a **boost chime**, a **collision thud** and a **music track from the disc**. The first three are *samples*: small recordings kept in the **SPU's** own RAM and played by writing a few registers. The music is *CD audio*: the disc carries a second track of audio, and the drive plays it into the SPU's mixer without the CPU touching the data.

The SPU (sound processing unit) is a 24-voice sampler. You upload sample data once; after that each sound is a handful of register writes: *where* the sample is, *how fast* to play it (the pitch), *how loud*, and *go* (key-on).

## 2. Why it matters

Sound is half of what a racer feels like: the pitch of the hum is the speedometer you do not look at. It is also the first hardware in the book whose result **cannot be read back**: you write registers and trust the chip, so exact register values, addresses in 8-byte units and ADPCM block flags matter, and the verifier has to watch the *writes* instead of the output.

## 3. Learning objectives

After this chapter you can:

- describe the SPU: **24 voices**, ADPCM decoding, **ADSR** envelopes, the mixer with its CD input, **reverb**, and its **512 KB** RAM with the first 4 KB reserved;
- convert a WAV to a **VAG** with `wav2vag.py`, and explain the **loop flags** (4 and 3) of the engine sample and the **end block** of a one-shot;
- **upload** a sample into SPU RAM (DMA in 64-byte blocks) and keep an allocator for it;
- play a voice: start address (8-byte units), **pitch** (`rate * 4096 / 44100`), volume, envelope, **key-on** and key-off;
- allocate voices (a fixed engine voice, round-robin one-shots) and drive a pitch from a game value with a **monotone, exact** mapping;
- add a **CD-DA track** to the disc layout and play it with `CdlPlay`, mixing it through the CD volume matrix and the SPU's CD input;
- verify hardware you cannot read: **log the register writes** and read SPU RAM from an emulator dump.

## 4. Prerequisites

[Chapter 29](../../part-06-assets-cdrom-textures-and-compression/ch29-the-cd-rom-and-loading-files/README.md) (`cd_load_file`), [Chapter 33](../ch33-game-architecture-objects-scenes-and-input/README.md) (the state machine), Chapters [37](../ch37-ship-movement-and-physics/README.md) (the ship, `speed`) and [38](../ch38-track-visibility/README.md) (`ship_section`), and Appendix E.2 (the disc layout) and **E.4** (the VAG format). This chapter starts from Chapter 38's `solution/`.

## 5. Explanation

### 5.1 The SPU

```
 SPU RAM (512 KB)                                   +------------------------------+
 +-------------+   ADPCM    +----------+  +-----+  |  CD audio (from the drive)---+--> volume
 | samples     |--> decode ->| ADSR     |->| vol |--+  external input              |
 +-------------+   x 24     | envelope |  | L/R |  |                              |
   voice v: start address,  +----------+  +-----+  |   MIXER --> (reverb) --> master volume --> out
   pitch, repeat address                           |    sum of 24 voices + CD + ext         44.1 kHz stereo
                                                   +------------------------------+
```

Each of the **24 voices** reads 4-bit ADPCM blocks from SPU RAM, decodes them (Appendix E.4), shapes the level with an **ADSR envelope**, scales it by its left and right volume and adds it to the mix. The CD drive's audio enters the same mix through its own volume. **Reverb** (an echo effect with a work area at the top of SPU RAM) and **FM / noise** modes exist; this chapter uses none of them.

The output runs at 44,100 Hz whatever the samples are: a voice **steps through its sample** by `pitch / 4096` samples per output tick, so the pitch is a playback-speed ratio (5.3).

**SPU RAM** is separate from main RAM (the CPU cannot address it; data goes in through DMA or a FIFO). The map used here:

```
 0x00000 +------------------------------+
         | 4 capture buffers (4 x 0x400)|  the SPU writes CD audio and voices 1, 3 here
 0x01000 +------------------------------+
         | dummy block (16 bytes)       |  SpuInit puts one here and keys every voice onto it
 0x01010 +------------------------------+  <- SPU_RAM_FIRST: the first byte of a sample
         | ENGINE  12608 B  (0x01010)   |
         | BOOST    7616 B  (0x04150)   |  every size rounded up to 64 bytes (5.2)
         | THUD     4480 B  (0x05F10)   |
         | BEEP     3200 B  (0x07090)   |
         | GO       7616 B  (0x07D10)   |  ends at 0x09AD0: 39 KB of 512 KB
 0x09AD0 +------------------------------+
         | free ...                     |
         | (reverb work area, top, unused)
 0x80000 +------------------------------+
```

The SDK has no `SpuMalloc`: keep your own `next_addr`. The registers sit at physical `0x1F801C00` to `0x1F801DFF`; PSn00bSDK names them in `hwregs_c.h` (`SPU_CH_FREQ(v)`, `SPU_KEY_ON1`, ...) and `psxspu.h` wraps them in macros (`SpuSetVoicePitch`, `SpuSetKey`).

### 5.2 Samples: from WAV to SPU RAM

`sfxgen.py` writes five 22,050 Hz mono WAVs; `wav2vag.py` encodes them as `.VAG` (Appendix E.4): a 48-byte **big-endian** header, then 16-byte ADPCM blocks of 28 samples that go to SPU RAM unchanged. `mkassets.py` produces `ENGINE BOOST THUD BEEP GO` `.VAG` and puts them in `\DATA\` on the disc (`iso.xml`).

| File | Blocks | Ends with | Why |
|---|---|---|---|
| `ENGINE.VAG` | 788 | block 1 has flag **4** (loop start), the last block flag **3** (end + repeat) | a hum has no end: at the last block the SPU jumps back to the loop start |
| `BOOST.VAG`, `THUD.VAG`, `BEEP.VAG`, `GO.VAG` | 475, 278, 199, 475 | an **end block**, flag **1** (end, no repeat) | a one-shot: at the end the SPU mutes the voice by itself |

(`example/audio_ref.py wave FILE.VAG` draws a VAG's waveform as ASCII.)

To upload a file: load it with `cd_load_file`, check `VAGp` and that the header's size field equals the file size minus 48, read the **rate** (big-endian) and send the blocks that follow the header:

1. `SpuSetTransferMode(SPU_TRANSFER_BY_DMA)` and `SpuSetTransferStartAddr(addr)` choose how and where;
2. `SpuWrite(data, size)` starts the transfer on **DMA channel 4**, and `SpuIsTransferCompleted(SPU_TRANSFER_WAIT)` waits for it;
3. the transfer works in **64-byte blocks**, so `size` is rounded up to a multiple of 64: the file buffer may end before that, so copy the blocks into a zero-filled buffer of the rounded size first;
4. `addr` is the allocator's next free byte, **8-byte aligned** (the sizes above keep it a multiple of 64); record `addr`, `size`, `rate` and whether the last block's flags have bit 1 (repeat) set in `audio_samples[id]`.

The other way in is the **manual FIFO**: set the transfer address register and write halfwords to `SPU_DATA`; `SPU_TRANSFER_BY_IO` selects it. It is slower and needs no DMA.

### 5.3 A voice: registers, pitch and key-on

Voice `v` owns 16 bytes at `0x1F801C00 + 16 v`:

| Offset | Register | Value |
|---|---|---|
| +0, +2 | volume left, right | 15 bits, `0x3FFF` = full (bit 15 clear = fixed volume) |
| +4 | **pitch** | `0x1000` = native 44,100 Hz; `0x4000` (4 x, two octaves up) is the fastest (psx-spx); the book clamps to `0x3FFF` |
| +6 | **start address** | in **8-byte units**: `addr / 8` |
| +8, +10 | ADSR | see below |
| +12 | envelope level | the current level, updated by the SPU: read it, do not write it |
| +14 | repeat address | where an end block jumps to; set by a flag-4 block as it plays, and (per psx-spx, not measured here) loaded with the start address at key-on |

Global registers: `SPU_KEY_ON1/2` (`0x1F801D88/8A`, one bit per voice, voices 0-15 and 16-23), `SPU_KEY_OFF1/2` (`0x1F801D8C/8E`), `SPU_CHAN_STATUS1/2` (`0x1F801D9C/9E`, the **ENDX** bits: voice `v` has played a block with the end flag), `SPU_CD_VOL_L/R` (`0x1F801DB0/B2`), `SPU_CTRL` (`0x1F801DAA`). A key-on write *starts* the voices whose bits are set: it copies the start address into the current address and starts the envelope. **Set every register of the voice before the key-on.**

**Pitch.** A sample recorded at `rate` Hz plays correctly when the SPU steps through it at `rate` samples per second. The SPU produces 44,100 outputs per second and `pitch / 4096` is the step per output, so

```
   pitch = rate * 4096 / 44100        (integer division)

   rate 22050 Hz  -> 0x0800        half a sample per output: native speed for this sample
   rate 44100 Hz  -> 0x1000
   pitch 0x0400   -> plays at 11025 Hz: one octave below native
   pitch 0x0FB8   -> plays at 43325 Hz: almost one octave above native
   (each doubling of the pitch is one octave)
```

`psxspu.h` has the macro `getSPUSampleRate(rate)` for this and `getSPUAddr(addr)` for the 8-byte units (it rounds **up**).

**The envelope.** The SPU multiplies the voice by an **ADSR** envelope: **A**ttack (rise to full), **D**ecay (fall to the sustain level), **S**ustain (hold, rising or falling at a rate), **R**elease (fall to 0 after the key-off). `ADSR1` (`+8`): bits 15-8 attack (mode, shift, step), bits 7-4 decay shift, bits 3-0 **sustain level** (0-15; 15 = full). `ADSR2` (`+10`): bits 15-6 sustain (mode, direction, shift, step), bit 5 release mode, bits 4-0 release shift. After `SpuInit` the registers hold nothing useful, so every voice needs them. The book wants *no shaping*: the fastest attack and sustain level 15 give `ADSR1` = `0x00FF`; a release with shift 10 (a fade of about 50 ms after key-off) gives `ADSR2` = `0x000A`.

**Stopping.** A one-shot needs no key-off: its last block (flag 1) makes the SPU **mute the voice and set its ENDX bit** (5.8). The looped engine runs until the program keys it off (`SPU_KEY_OFF1` bit 0).

### 5.4 One-shots and voice allocation

There are 24 voices; the engine owns **voice 0** for as long as the game runs. Everything else is a one-shot on **voices 1 to 23, round robin**: the first sound gets voice 1, the next voice 2, ... voice 23, then voice 1 again.

| Policy | Idea | Here |
|---|---|---|
| fixed voice per sound | simple, but two thuds in a row cut each other | the engine only |
| **round robin** | a cursor over a pool; the oldest voice is reused | one-shots: a thud lasts 0.35 s and the pool has 23 voices, so it is never reused while it plays |
| priority / steal | give a voice to the important sound | the stretch goal |

`audio_play_sfx(id)` takes the next voice, keys it off (a precaution: key-on restarts the sample and the envelope anyway), writes volume, pitch (`rate * 4096 / 44100` of *that* sample), start address and the envelope, then keys it on. `audio_voice_alloc()` is the cursor alone, so it can be tested without sound. `audio_init` resets it to 1.

### 5.5 The engine hum

The hum is the looped `ENGINE` sample on voice 0, **started once when the game state is entered** and keyed off on the title. Every game frame, after the physics, the program writes a new **pitch** from `ship.speed` (Chapter 37: 4.12 units per NTSC tick, 0 to `speed_cap` = 245,760):

```
   base  = rate * 4096 / 44100                          (the ENGINE sample's rate, from its header)
   mul   = idle_mul + (((speed >> 8) * span_mul) >> 10)       speed below 0 counts as 0
   pitch = min((base * mul) >> 12, 0x3FFF)
```

`idle_mul` (default 2048 = 0.5) and `span_mul` (6400) are in `audio_cfg` and **patchable**; `speed >> 8` first keeps every product inside 32 bits (`speed` is tested up to `1 << 24`).

| Speed (units/tick) | `mul` | Pitch (rate 22050) | Plays at |
|---|---|---|---|
| 0 | 2048 | `0x0400` | 11,025 Hz (an octave low: idle) |
| 20 | 4048 | `0x07E8` | 21,792 Hz |
| 40 | 6048 | `0x0BD0` | 32,558 Hz |
| 60 (cap) | 8048 | `0x0FB8` | 43,325 Hz (3.9 x the idle rate: almost two octaves up) |

The mapping is **monotone** (a faster ship never sounds lower) because every step preserves order, and **linear in speed**. The ear hears frequency ratios, so a more musical map would be exponential (a stretch goal). Because `base` comes from the file's rate, an engine re-recorded at another rate sounds the same.

### 5.6 Game events

Two events trigger one-shots now; Chapter 40 will replace the second with real collision. Both are evaluated once per frame, **after** `ship_section` is updated, with the ship's position after the physics:

| Event | Rule | Sound |
|---|---|---|
| **boost** (`EV_BOOST`) | `ship_section` is **different** from the previous frame's **and** that section has a face with `TRK_BOOST` | `BOOST` (the chime) |
| **thud** (`EV_THUD`) | the ship is **off the road** and was not last frame | `THUD` |

*Off the road*: `|lateral| > half_width` of `ship_section`, where `lateral = (dx*right.x + dy*right.y + dz*right.z) >> 12` with `d = pos - section.centre` (each component of `d` clamped to +-32767 first: a ship far away must not overflow). `right` is the section's 4.12 unit vector (E.10.4), `half_width` 600 on the book's tracks.

The verifier tests these details: an event fires **on the change**, not on every frame the condition holds (stay on a pad or outside the road and nothing repeats); two consecutive boost sections (28, 29 on track 1) are two sections, so **two chimes**; a teleport *onto* a pad is a change of section (a chime), a teleport while already outside stays outside (no second thud); entering the game raises nothing (`audio_events_reset` stores the start state).

```
        boost pad sections 28, 29                    |lateral| > 600
 section: 27 | 28 | 29 | 30                road:  |<----------->|
 events :     chime chime                    ship:  .  . ## ## ## .      -> one thud, when it first goes out
```

### 5.7 Music from the disc

The music is **not** a sample: 24 seconds of 44.1 kHz stereo PCM is 4.2 MB, eight times the whole SPU RAM (and still more than twice it as ADPCM). It is a **CD-DA** (Red Book audio) track: raw 44,100 Hz, 16-bit, stereo PCM on a second track that the drive plays itself.

**On the disc.** `tools/assets/musicgen.py` writes an original 24 s loop (A minor, 120 BPM, 12 bars: bass, arpeggio, pad and drums, all synthesized; `mkassets.py --music` makes `MUSIC.WAV`, 4.2 MB). `iso.xml` adds it after the data track:

```
   <track type="audio" source="assets/MUSIC.WAV" />     ->  hoverline.cue:  TRACK 02 AUDIO
                                                                            INDEX 00 00:15:36    (the 2 s pregap)
                                                                            INDEX 01 00:17:36    (the music starts)
```

Track 1 is the data track (the program, the assets); track 2 is the music. mkpsxiso inserts a 2-second **pregap** (150 silent sectors in the `.bin`) before an audio track.

**In the program.** Audio from the drive reaches the output through two volumes, and both must be non-zero:

| Step | Call | Why |
|---|---|---|
| the drive's matrix | `CdMix(&mix)` with `{128, 0, 128, 0}` | 128 = 100%; left to left, right to right. This is the usual power-on matrix, but nothing guarantees what the BIOS or a previous program left there, so set it |
| the SPU's CD input | `SpuSetCommonCDVolume(l, r)` (`SPU_CD_VOL_*`) | `SpuInit` sets `0x7FFF`; the book sets `music_vol` (`0x6000`); `SPU_CTRL` bit 0 (CD audio enable) stays set |
| the mode | `CdControl(CdlSetmode, &mode, 0)`, mode = `CdlModeDA \| CdlModeAP` | `DA` (bit 0): CD-DA allowed (psx-spx: it lets the drive *read* audio sectors; the SDK's examples set it for play too); `AP` (bit 1): **auto-pause** at the end of the track and raise an interrupt (INT4) |
| start | `CdControl(CdlPlay, &track, 0)`, `track` = 2 | command `0x03` with the track number as its parameter (BCD on the wire: 2 is `0x02`, track 10 would be `0x10`) |

**Looping.** The drive does not loop. With `CdlModeAP` it pauses at the end of the track and signals `CdlDataEnd`: `CdAutoPauseCallback` registers a function that sets a flag (a callback must be short), and `audio_update` (once per frame) sees the flag and sends `CdlPlay` again. (`CdlModeRept` is the **report** mode, position reports during play, not a repeat.) The music starts when the program has loaded, on the **title**, and plays on through the game.

**Why not XA?** XA audio is ADPCM in Mode 2 Form 2 sectors of the data track, interleaved with other sectors; the drive decodes it during a read and feeds the same CD input (the SDK's `cdxa` example shows it). It is 4 to 8 times smaller than CD-DA at similar quality, but it needs an XA-encoded, interleaved file and more code. CD-DA is a few calls and costs disc space; the book's disc has plenty.

### 5.8 What the emulator showed

PCSX-Redux, with the probe of 5.9 (`audio_stats.endx`, `env_engine` and `env_last` are the program's own readings of `ENDX` and the envelope level):

| Question | Observed |
|---|---|
| Does the loop (flag 4 at block 1, flag 3 at the last) keep the engine running? | yes: the envelope level stays `0x7FFF` for the whole run (a flag-1 end would drop it to 0), and the ENDX bit of voice 0 is set at the loop ends |
| What does a **flag-1 end block** do to a one-shot? | the envelope level goes to **0** with no key-off and the voice's ENDX bit is set |
| A one-shot ending in a silent **flag-7** block instead (a one-off run)? | the same: envelope 0 and ENDX set. By the flag table of E.4 a `07` block repeats itself silently and should leave the envelope up, so Redux does not follow the table here. This is one emulator's behavior, not a hardware fact; the book writes `01`, which mutes the voice under either reading |
| Does `CdlPlay` with a track number play track 2, and does `CdlModeAP` end it? | the command is accepted, and the auto-pause callback fires after the 24 s track (24 s of emulated time later): `music_restarts` counts it |

**Not verified** (the toolchain has one emulator, and the verifier cannot hear): how other emulators and real hardware treat a flag-1 and a silent flag-7 ending (other tools end one-shots with the latter); what a block with shift 13 to 15 sounds like (psx-spx says like 9; the book never writes one); whether every emulator honors `CdlPlay`'s track parameter (the SDK warns that some ignore it).

### 5.9 How the verifier hears

It cannot record sound, so it **watches the writes**. Section 8 lists the checks; this is how they get their evidence.

1. **Registers.** The emulator's Lua cannot read the SPU's registers, but PCSX-Redux fires a **write breakpoint** on stores to I/O addresses. The callback gets the address and not the value, so the probe decodes the **store instruction** at the PC and reads the value from its source register (`verify.on_hwwrite` in `tools/verify-lib/redux.lua`). Every store to `0x1F801C00`-`0x1F801DFF` (SPU) and `0x1F801800`-`0x1F801803` (CD controller) is logged with the frame it belongs to. `checks.py` replays the log, so it knows every voice register at every key-on, every key-off, the CD commands and the CD volume matrix.
2. **SPU RAM.** `PCSX.SPU.Logger.exportSPD` writes an SPU dump that holds the **RAM image** (in this build, RAM address `0x1000` is at file offset `0x44`; the SDK's dummy block is the anchor the verifier checks for). The five `.VAG` bodies must be there byte for byte.
3. **The run.** The pad is idle except for START. At the end of every frame the probe writes a **pose** (a position on or beside the track, and a speed) into `ship`; `ship_update` leaves a speed-0 pose where it is, so the events see exactly the posed position. The script teleports and drives across the boost pads, leaves the road on both sides, drives along the verge, teleports while outside, raises a thud on alternate frames (more than 23 one-shots, so the voices wrap), sweeps the speed from 0 to the cap and back, and holds still after a last thud.
4. **Direct calls and a second disc.** At the entry of `main` the probe calls `audio_pitch_for_speed` 90 times and `audio_voice_alloc` 50 times. A second image, with other sample rates in the headers of `ENGINE`, `BOOST` and `THUD` and other `audio_cfg` values patched in, makes a hard-coded pitch or volume fail.

## 6. Worked example

The engine at speed 30 units per tick, on the book's disc. `speed = 30 * 4096 = 122,880`.

```
base  = 22050 * 4096 / 44100          = 2048
speed >> 8                            = 480
(480 * 6400) >> 10                    = 3000
mul   = 2048 + 3000                   = 5048
pitch = (2048 * 5048) >> 12           = 2524 = 0x09DC     (plays at 27,175 Hz)
```

A chime: the ship moves from section 27 to 28, which has a boost face. The frame's `audio_events_update` sees `28 != 27` and `audio_section_boost` is 1, so `audio_event(EV_BOOST)` runs `audio_play_sfx(SMP_BOOST)`: voice 5 (say), volume `0x3000` both sides, pitch `0x0800`, start address `0x4150 / 8 = 0x082A`, key-on `1 << 5` written to `SPU_KEY_ON1`. `python3 example/audio_ref.py pitch` prints the table of 5.5.

## 7. Project: sound for Hoverline

### 7.1 Behavior

Chapter 38's game, with sound. The CD music plays from the title on. Entering the game starts the hum; it rises as you accelerate (X) and falls when you brake (Square). Driving into a **boost** section (28, 29, 76, 77) plays the chime; driving off the edge of the road (there is no wall yet) plays the thud, once per excursion. START returns to the title and silences the hum; the music goes on.

### 7.2 The contract

`starter/` is Chapter 38's `solution/` with the wiring done and the work stubbed. **Read `audio.h` first: it is the specification.** **Given:** Chapter 38; the hooks in `game.c` (`set_state` starts and stops the engine and resets the detector; `game_update` calls `audio_events_update` and `audio_engine_update(ship.speed)` each frame) and in `main.c` (`audio_init`, `audio_music_start`, `audio_update` once per frame, the symbols kept linked); the disc (`iso.xml` lists the `.VAG` files and the audio track, `CMakeLists.txt` runs `mkassets.py --music`); in `audio.c`: the globals, `paths[]`, `be32`, the auto-pause callback. **You write** the rest of `audio.c`:

| Function | What |
|---|---|
| `audio_upload_sample`, `audio_init` | 5.2 (and `audio_status`) |
| `audio_pitch_for_speed` | 5.5, exactly |
| `audio_voice_alloc`, `audio_play_sfx` | 5.4, 5.3 |
| `audio_engine_start`, `_stop`, `_update` | 5.5 |
| `audio_event`, `audio_lateral`, `audio_section_boost`, `audio_events_reset`, `audio_events_update` | 5.6 |
| `audio_music_start`, `audio_update` | 5.7, and the diagnostics `audio_stats.endx / env_engine / env_last` |

**State the verifier reads and patches:** `audio_samples[5]` (4 words each), `audio_cfg` (8 words; **patched**), `audio_stats` (12 words), `audio_status`, `ship` and `ship_section` (Chapters 37 and 38).

### 7.3 Steps

1. **Upload** (5.2). With `audio_init` and the allocator, `samples_in_table` and `spu_ram_holds_the_vag_data` pass.
2. **One voice** (5.3, 5.4): `audio_play_sfx(SMP_THUD)` from a button press, to hear it in an emulator window (`make run`).
3. **The pitch** (5.5): `audio_pitch_for_speed` first (`pitch_function_direct_calls`), then the engine voice.
4. **Events** (5.6): `audio_lateral`, `audio_section_boost`, then the detector.
5. **Music** (5.7): `music_plays_from_the_cd`; then the restart.

### 7.4 Rules

- Everything derives from the files and `audio_cfg`: the pitch from the VAG's **rate field**, the start address from where **you** uploaded the sample. Nothing is hard-coded to 22,050 Hz.
- The engine key-on happens **once** per game entry, one-shots one key-on per event. A key-on every frame fails `no_stray_key_ons`.
- Write all of a voice's registers **before** its key-on.
- Do not clear `SPU_CTRL`'s CD-audio bit or write the CD volume before `CdMix`.

### 7.5 Hints

- `SpuWrite` takes a `const uint32_t *` and a **byte** count; `calloc` the padded buffer so the tail is zero.
- `getSPUAddr` rounds up: pass an aligned byte address.
- A callback runs in an interrupt: set a flag and return. Do not call `CdControl` from it.
- `CdControl(CdlPlay, &track, 0)` wants a pointer to a `uint8_t`.
- `make run` plays sound in the emulator window: `-run -fastboot` boots the disc; the CD-DA track plays too.

### 7.6 Stretch goals

- **Exponential pitch**: pitch proportional to `2^(speed / k)` through a small table, so equal speed steps give equal musical intervals.
- **Engine volume with speed**, and a short **crossfade** at key-on.
- **Voice stealing**: when all 23 voices are busy, reuse the one with the lowest envelope level (`SPU_CH_ADSR_VOL`).
- **Countdown beeps**: `BEEP` and `GO` are already uploaded; Chapter 41 will play them.
- **Reverb**: the SPU's reverb on the thud (`SpuSetCommonCDReverb` is the CD's; study psx-spx's reverb registers).
- **XA music**: the SDK's `cdxa` example.

## 8. Verification

```sh
source tools/env.sh
parts/part-07-capstone-hoverline/ch39-audio/verify/verify.sh            # your starter/
parts/part-07-capstone-hoverline/ch39-audio/verify/verify.sh --solution # the reference
```

About a minute: a build, the **main** run (about 800 frames), the **alt** disc (about 600 frames) and the **loop** run (about 2,000 frames, long enough for the music track to end).

| Check | What it means | If it fails |
|---|---|---|
| `disc_has_audio_track` | the `.cue` has `TRACK 02 AUDIO`; the `.bin` holds the generated WAV's sectors after it | `iso.xml` lacks the track |
| `samples_in_table` | five entries: aligned, at or above `0x1010`, size and rate from the header, loop flag, no overlap | upload, parsing |
| `spu_ram_holds_the_vag_data` | each body is in the SPU dump at the table's address, byte for byte | wrong address, a short transfer, the header uploaded |
| `engine_starts_on_voice_0` | one key-on of voice 0 when the game starts, with the right address, volume, idle pitch; the envelope stays up (the loop works); ENDX shows loop ends | restarting each frame, wrong register |
| `engine_pitch_follows_speed` | the pitch written in every game frame equals the formula (all poses); monotone through the sweep up and down; 40+ distinct values; both ends exact | the formula, writing only at key-on |
| `pitch_function_direct_calls` | 90 calls (speeds from negative to `1 << 24`, five sample rates, other constants) equal the model; callee-saved registers kept | overflow, no clamp, hard-coded rate |
| `voice_allocation_round_robin` | `1..23, 1..23, 1..4` | cursor, voice 0 handed out |
| `boost_chime_events`, `collision_thud_events` | one key-on per event in the right frame, round-robin voice, pitch from the sample's rate, volume, start address | edge detection, the lateral rule |
| `no_stray_key_ons` | nothing else keys on; counters agree; all of voices 1-23 used and never 0 | key-on every frame |
| `one_shot_ends_by_itself` | the thud's envelope is up after its key-on and 0 eighty frames later, ENDX set, no key-off by the program | a cut-off upload |
| `engine_stops_on_the_title` | a key-off of voice 0 on returning to the title | the hook |
| `music_plays_from_the_cd` | `CdlSetmode` with DA and AP, then `CdlPlay` with 2; CD volume registers; `SPU_CTRL` bits; the volume matrix | missing `CdMix` |
| `music_restarts_when_the_track_ends` | a second `CdlPlay` after the 24 s track (at least 1,300 vertical blanks after the first); `music_restarts` counts it | callback, the flag, a timer instead of the callback |
| `nothing_hard_coded_alt_disc` | on the second disc (5.9): pitches, key-ons, RAM and the CD volume follow the other rates and constants | constants in the code |

A pass ends with `CHAPTER 39: PASSED (15/15 checks)`. The untouched starter fails; so do (all tried): a pitch that ignores the speed, a key-on of the engine every frame, a start address off by 16 bytes, a sample uploaded 64 bytes away from the address in the table, no `CdlPlay`, and hard-coded `0x800` / 22,050. Not verified: the sound itself (5.8).

## 9. Common pitfalls

- **Pitch from the wrong rate.** `0x1000` is 44.1 kHz, not the sample's rate: a 22,050 Hz sample at `0x1000` plays an octave high.
- **Addresses in bytes.** The start-address register is in 8-byte units.
- **The header in SPU RAM.** Upload the blocks, not the 48 header bytes; and the **size** field is big-endian.
- **No end flag on a one-shot.** The voice runs on into whatever follows in SPU RAM (noise).
- **A short or unaligned transfer.** The SPU's DMA moves 64-byte blocks.
- **Key-on before the registers.** The voice starts with the pitch and address of its previous sound.
- **Key-on every frame.** The sound restarts 60 times a second: a buzz, and a "stuck" voice.
- **Everything on voice 0.** Two sounds cut each other; use a pool.
- **CD volume zero.** `SpuInit` gives the SPU's CD input `0x7FFF`, but the drive's matrix (`CdMix`) and `SPU_CTRL` bit 0 matter too; with any of them at zero the music is silent without an error.
- **Calling the CD library from the callback.** Set a flag and act in the main loop.
- **Assuming `CdlModeRept` loops.** It reports positions.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- Appendix E.4 (VAG), E.2 (the disc layout; the audio track), [Appendix B](../../../appendices/B-memory-map-and-io.md) (SPU registers), `tools/assets/README.md` (`musicgen.py`, `--music`).
- psx-spx: *SPU Overview*, *SPU Voice Registers*, *SPU ADPCM Samples*, *SPU ADSR Envelope*, *SPU Reverb*, *CDROM Control Commands* (Setmode), *CDROM - CD Audio Commands* (Play).
- The SDK's examples `sound/vagsample`, `sound/spustream` (streaming from main RAM), `sound/cdstream`, `cdrom/cdxa`.
- Chapter 40 (collision events replace the thud), Chapter 41 (countdown beeps, the lap chime).
