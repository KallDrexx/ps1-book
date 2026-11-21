# Appendix B: Memory Map and I/O Registers

Every address the book uses, grouped by device. Sources: psx-spx ("Memory Map", "Interrupts", "DMA", "Timers", "CDROM", "SPU", "Controllers") and the chapters named in each section. Facts the book measured in PCSX-Redux say so; facts it did not exercise are marked *(not checked in the book)*. Sizes are bytes unless stated. Registers are listed by **physical** address; add `0xA0000000` (KSEG1, uncached) or use the plain `0x1F80....` form as the book does.

| Section | Contents |
|---|---|
| B.1 | Address segments (KUSEG / KSEG0 / KSEG1) and the physical map |
| B.2 | RAM, scratchpad, cache, BIOS and the kernel area |
| B.3 | I/O register overview |
| B.4 | Interrupts (`I_STAT`, `I_MASK`) |
| B.5 | DMA |
| B.6 | Timers (root counters) |
| B.7 | GPU registers and GPUSTAT |
| B.8 | CD-ROM controller |
| B.9 | Controllers (SIO0) and the pad buffer |
| B.10 | SPU |
| B.11 | Frame timing and PCSX-Redux cycle counts |

## B.1 Segments and the physical map

The CPU's 32-bit virtual address picks a segment (Ch 2):

| Virtual range | Segment | Cached? | Becomes physical |
|---|---|---|---|
| `0x00000000-0x7FFFFFFF` | KUSEG | yes | the address itself (first 512 MB used) |
| `0x80000000-0x9FFFFFFF` | KSEG0 | yes | `addr & 0x1FFFFFFF` |
| `0xA0000000-0xBFFFFFFF` | KSEG1 | **no** | `addr & 0x1FFFFFFF` |
| `0xC0000000-0xFFFFFFFF` | KSEG2 | n/a | cache-control register `0xFFFE0130` only; ignore |

Only **instruction fetches** are cached (4 KB instruction cache), and only through KUSEG and KSEG0. The 1 KB "data cache" is wired as the scratchpad. Data loads and stores behave identically through every segment. On real hardware the scratchpad is **not reachable through KSEG1**; PCSX-Redux lets an access to `0xBF800000` through all the same (measured), so use `0x1F800000` (Ch 2). RAM offset `0x10000` is one place named `0x00010000`, `0x80010000` or `0xA0010000`.

| Physical range | Size | What answers |
|---|---|---|
| `0x00000000-0x001FFFFF` | 2 MB | main RAM; mirrored at `0x00200000`, `0x00400000`, `0x00600000` (8 MB window). Never rely on the mirrors. |
| `0x1F000000-0x1F7FFFFF` | up to 8 MB | expansion region 1 (parallel I/O port) |
| `0x1F800000-0x1F8003FF` | 1 KB | **scratchpad** (fast on-chip RAM) |
| `0x1F801000-0x1F801FFF` | 4 KB | **I/O registers** (B.3) |
| `0x1F802000-0x1F803FFF` | 8 KB | expansion region 2 (debug hardware, POST/`DUART`) |
| `0x1FA00000-0x1FBFFFFF` | 2 MB | expansion region 3 (unused) |
| `0x1FC00000-0x1FC7FFFF` | 512 KB | **BIOS ROM** (reset vector `0xBFC00000`) |
| `0xFFFE0130` | 4 | cache control (KSEG2) |

Reading an unmapped address raises a bus error on hardware (exception 6/7, Appendix A.7); an emulator may return garbage instead (Ch 2).

## B.2 RAM, scratchpad, BIOS

| Item | Fact |
|---|---|
| Kernel area | the first 64 KB of RAM (`0x80000000-0x8000FFFF`) belongs to the BIOS kernel; programs load at `0x80010000` (Ch 2, 5) |
| Exception vector | the BIOS installs its general-exception handler at `0x80000080` (COP0 debug-breakpoint vector: `0x80000040`) |
| BIOS call tables | `A0h`, `B0h`, `C0h`: put the function number in `$t1` and jump to the table address (the SDK stubs do this, Ch 22). The pad functions used by the book: `B(12h)` `InitPAD`, `B(13h)` `StartPAD`, `B(14h)` `StopPAD`, `B(5Bh)` `ChangeClearPAD` |
| Default stack | `0x801FFFF0` (`EXE_STACK` in `common/psxexe.inc`); PSX-EXE header field at 0x30 (Appendix E.1) |
| Scratchpad use | 1 KB at `0x1F800000-0x1F8003FF` (or `0x9F800000` in KSEG0): hot data for the GTE chapters. **Not executable**: jumping into it crashes (Ch 2). |
| Instruction cache | 4 KB; the book never controls it explicitly |
| Byte order | little-endian (Ch 2) |
| BIOS in the harness | PCSX-Redux runs **OpenBIOS** (a reimplementation) when given no BIOS file: same call tables, but undocumented details may differ. With fast boot it takes about 31 frames to reach `main`, where `SR = 0x40000000` (interrupts off), `I_MASK = 0` and `I_STAT` = 1 (bit 0 already set); measured (Ch 17). |

## B.3 I/O register overview

Registers are 32-bit unless stated. Use `sw`/`lw` for word registers and `sh`/`lhu` for halfword ones (SPU, timers, joypad); a halfword register accessed as a word is *not* guaranteed to work *(not checked in the book)*.

| Address | Device |
|---|---|
| `0x1F801000-0x1F801023` | memory control 1 (expansion bases and delays) |
| `0x1F801040-0x1F80105F` | joypad / memory card (`JOY_*`) and serial port (`SIO_*`) |
| `0x1F801060` | `RAM_SIZE` (memory control 2) |
| `0x1F801070` / `0x1F801074` | `I_STAT` / `I_MASK` |
| `0x1F801080-0x1F8010FF` | DMA channels 0-6, `DPCR`, `DICR` |
| `0x1F801100-0x1F80112F` | timers 0-2 |
| `0x1F801800-0x1F801803` | CD-ROM controller |
| `0x1F801810` / `0x1F801814` | GPU: `GP0`/`GPUREAD`, `GP1`/`GPUSTAT` |
| `0x1F801820` / `0x1F801824` | MDEC: command/data, control/status |
| `0x1F801C00-0x1F801DFF` | SPU |

Memory control 1, for reference *(not checked in the book)*: `0x1F801000` EXP1 base (default `0x1F000000`), `0x1F801004` EXP2 base (`0x1F802000`), `0x1F801008` EXP1 delay/size, `0x1F80100C` EXP3 delay, `0x1F801010` BIOS delay, `0x1F801014` SPU delay, `0x1F801018` CD-ROM delay, `0x1F80101C` EXP2 delay, `0x1F801020` common delay. Leave them as the BIOS set them.

## B.4 Interrupts

`I_STAT` = `0x1F801070` (status), `I_MASK` = `0x1F801074` (enable); bits 0-10 are used. Bit assignments (Ch 17):

| Bit | Source | Bit | Source |
|---|---|---|---|
| 0 | **VBlank** (IRQ0) | 6 | Timer 2 |
| 1 | GPU | 7 | Controller / memory card |
| 2 | CD-ROM | 8 | SIO |
| 3 | DMA | 9 | SPU |
| 4 | Timer 0 | 10 | lightpen / PIO |
| 5 | Timer 1 | | |

| Rule | Detail |
|---|---|
| Acknowledge | write **0** to clear a bit of `I_STAT`, write **1** to leave it alone. `I_STAT = 0xFFFFFFFE` clears only VBlank. Writing 1 to bit 0 does nothing; without a clear the bit stays set and the next wait returns at once. |
| Latching | `I_STAT` latches events whether or not `I_MASK` enables them |
| Delivery | an interrupt reaches the CPU only if its `I_MASK` bit is set **and** COP0 `SR` enables interrupts (IEc = 1, IM bit 10 = 1; Appendix A.7). Then a BIOS handler runs and may acknowledge VBlank itself, so a polling loop would miss it. |
| Polling pattern (Ch 17) | `read I_STAT`; bit 0 clear -> repeat; then write `0xFFFFFFFE`. The book writes `I_MASK = 0` first so polling is safe under a retail BIOS. |
| Other pacing | GPUSTAT bit 31 (odd/even line in interlace) and the root counters also work; the verifiers check only that the program advances once per VBlank |

## B.5 DMA

Seven channels, each 16 bytes at `0x1F801080 + 0x10 * n`: `+0` **MADR** (RAM address, 24 bits), `+4` **BCR** (block control), `+8` **CHCR** (control). Global: `DPCR` = `0x1F8010F0`, `DICR` = `0x1F8010F4`.

| Ch | Device | Base | Book use |
|---|---|---|---|
| 0 | MDEC in | `0x1F801080` | no |
| 1 | MDEC out | `0x1F801090` | no |
| 2 | **GPU** | `0x1F8010A0` | ordering table (linked list) via `DrawOTag`, `DrawPrim`, `LoadImage` (Ch 19, 20, 30) |
| 3 | CD-ROM | `0x1F8010B0` | sector data (Ch 29, through the SDK) |
| 4 | **SPU** | `0x1F8010C0` | sample upload, `SpuWrite` (Ch 39) |
| 5 | PIO | `0x1F8010D0` | no |
| 6 | **OTC** (ordering-table clear) | `0x1F8010E0` | `ClearOTagR` (Ch 20) |

**CHCR** (psx-spx):

| Bits | Meaning |
|---|---|
| 0 | direction: 0 = device to RAM, 1 = RAM to device |
| 1 | address step: 0 = +4, 1 = -4 (OTC uses -4) |
| 8 | chopping enable |
| 9-10 | sync mode: 0 = burst (all at once), 1 = slice (request-paced blocks), 2 = **linked list** (GPU ordering tables) |
| 16-18 / 20-22 | chopping DMA window / CPU window sizes (log2) |
| 24 | start / busy (1 = running) |
| 28 | start / trigger (manual-start modes) |

**BCR**: sync mode 0: bits 0-15 = word count; mode 1: bits 0-15 = block size, bits 16-31 = block count; mode 2 (linked list): unused.

**Linked-list packet** (Ch 20): the first word of each packet is `(length << 24) | next address (24 bits)`, followed by `length` words for the GPU; the terminator is an address with all 24 bits set (`0xFFFFFF`). Each SDK primitive begins with this extra `tag` word that the GPU never sees. `ClearOTagR(ot, n)` (channel 6) writes the chain backwards: entry `i` points to `i-1`, entry 0 holds the terminator, so the DMA starts at `&ot[n-1]`, the farthest slot first.

**DPCR** (`0x1F8010F0`): 4 bits per channel; bits `4n .. 4n+2` priority, bit `4n+3` channel enable. Reset value `0x07654321`. **DICR** (`0x1F8010F4`): bit 15 force IRQ, bits 16-22 per-channel IRQ enable, bit 23 master enable, bits 24-30 per-channel flags (write 1 to acknowledge), bit 31 master flag. DMA interrupts appear as `I_STAT` bit 3. *(DICR is not exercised directly in the book.)*

Rules the chapters teach: `DrawPrim` waits like `DrawSync(0)` and then starts a DMA of one packet; `DrawOTag` returns at once, so do not write the table or any packet until `DrawSync(0)` reports done; primitives must not live on the stack (the DMA reads them after the call returns); buffers for `CdRead` must be 4-byte aligned (Ch 19, 20, 29).

## B.6 Timers (root counters)

Three 16-bit counters at `0x1F801100 + 0x10 * n`: `+0` current value, `+4` mode, `+8` target.

| Timer | Registers | Clock sources (mode bits 8-9) | Sync modes use |
|---|---|---|---|
| 0 | `0x1F801100/04/08` | 0 or 2: system clock; 1 or 3: dot clock | horizontal blank |
| 1 | `0x1F801110/14/18` | 0 or 2: system clock; 1 or 3: horizontal blank | vertical blank |
| 2 | `0x1F801120/24/28` | 0 or 1: system clock; 2 or 3: system clock / 8 | stop / free-run |

**Mode register** (psx-spx): bit 0 sync enable; bits 1-2 sync mode; bit 3 reset counter at target (0 = wrap after `0xFFFF`); bit 4 IRQ at target; bit 5 IRQ at `0xFFFF`; bit 6 IRQ repeat; bit 7 IRQ toggle; bits 8-9 clock source; bit 10 IRQ flag (0 = requested); bit 11 reached target; bit 12 reached `0xFFFF`. Writing the mode resets the counter to 0.

The book uses only **timer 0 in mode 0**: it counts CPU cycles (33.8688 MHz) and wraps at 65536. Read it before and after and subtract as `uint16_t` (Ch 27). It measures cycles on hardware as well as the emulator. Dot-clock and hblank sources are *not checked in the book*.

## B.7 GPU

| Address | Write | Read |
|---|---|---|
| `0x1F801810` | **GP0**: drawing commands and VRAM data (command list: Appendix C) | **GPUREAD**: data back from the GPU (`C0h` readback, GP1 info commands) |
| `0x1F801814` | **GP1**: display control (Appendix C) | **GPUSTAT** |

Both take a **word**: use `sw`. A GP1 word is `cc pppppp` (command in the top byte, parameter in the low 24 bits). VRAM is 1024 x 512 units of 16 bits (1 MB) and is **not** in the CPU memory map; GP0 and GPUREAD are the only way in or out (Ch 13).

### GPUSTAT (`0x1F801814`)

| Bits | Meaning |
|---|---|
| 0-3 | texture page X base (N * 64 units), as in `E1h` bits 0-3 |
| 4 | texture page Y base (0 = line 0, 1 = line 256) |
| 5-6 | semi-transparency mode (`E1h`) |
| 7-8 | texture color depth: 0 = 4 bpp, 1 = 8 bpp, 2 = 15 bpp |
| 9 | dither enable |
| 10 | drawing to the display area allowed |
| 11 | set mask bit when drawing (`E6h` bit 0) |
| 12 | do not draw over pixels with the mask bit set (`E6h` bit 1) |
| 13 | interlace field |
| 14 | "reverse" flag |
| 15 | texture disable |
| 16 | horizontal resolution 2 (1 = 368 wide) |
| 17-18 | horizontal resolution 1: 0 = 256, 1 = 320, 2 = 512, 3 = 640 |
| 19 | vertical resolution: 0 = 240, 1 = 480 |
| 20 | video mode: 0 = NTSC, 1 = PAL |
| 21 | color depth: 0 = 15-bit, 1 = 24-bit |
| 22 | vertical interlace |
| 23 | display disabled (1 = off) |
| 24 | GPU interrupt request |
| 25 | DMA / data request (meaning depends on the GP1(04h) direction) |
| **26** | **ready to receive a command word.** Set when the GPU wants a new command; **clear** while it wants parameters or data of the current packet, or is busy executing |
| 27 | ready to send VRAM to the CPU (`C0h` readback) |
| **28** | ready to receive a DMA block |
| 29-30 | DMA direction (GP1(04h)): 0 off, 1 FIFO, 2 CPU to GP0, 3 GPUREAD to CPU |
| 31 | even/odd line in interlace modes (0 during vertical blank) |

Bits 16-22 reflect the GP1(08h) word you wrote (its bits 0-5 appear in 17-22, bit 6 in 16) and bit 23 reflects GP1(03h), so GPUSTAT checks a mode word (Ch 13).

**The bit-26 rules (Ch 13, 15, 16).**

| Rule | Why |
|---|---|
| Wait for bit 26 = 1 **once, before the first word of a packet** | the GPU's FIFO holds 16 words, so a 6-word packet fits; a large fill sent back to back can outrun the GPU on real hardware |
| **Never** poll bit 26 between the words of a packet or inside an `A0h` data phase | the bit is 0 while the GPU wants parameters or data; the loop never ends (verified in PCSX-Redux: a routine that waits before every word hangs after word 1) |
| Measured during an `A0h` upload (Redux) | bit 26 is 1 before the packet, **0** after word 1, after word 3 and after 100 data words, 1 again after the last data word. Bit 28 stays 1 throughout. |
| Emulators report ready almost always | a missing wait rarely shows in Redux; it appears on hardware. The verifiers require one read before each packet and none inside it |
| Before flipping buffers | wait for bit 26 so the GPU has finished drawing, then one `GP1(05h)` write per frame (Ch 17) |

## B.8 CD-ROM controller

Four byte-wide registers at `0x1F801800-0x1F801803`; the meaning of 1801-1803 depends on the **index** in bits 0-1 of 1800 (psx-spx). The SDK's `Cd*` functions drive all of this in the book (Ch 29, 39); it is listed here so the probe logs in Ch 39 are readable. *(Register-level use is not checked beyond the logs.)*

| Address | Index 0 | Index 1 |
|---|---|---|
| `0x1F801800` | read: status; write: index select (bits 0-1). Status bits: 2 ADPBUSY, 3 parameter FIFO empty, 4 parameter FIFO not full, 5 response FIFO not empty, 6 data FIFO not empty, 7 busy | same |
| `0x1F801801` | write: command; read: response FIFO | read: response FIFO |
| `0x1F801802` | write: parameter FIFO; read: data FIFO | write: interrupt enable |
| `0x1F801803` | write: request (want data); read: interrupt enable | read: interrupt flags; write: acknowledge (1 clears) |

Indexes 2 and 3 hold the audio volume matrix and are not used directly by the book.

| Command | Name | Used for |
|---|---|---|
| `01h` | Getstat | status byte |
| `02h` | Setloc | MSF (BCD) of the next seek/read; does not move the laser (Ch 29) |
| `03h` | Play | CD-DA play from a track (BCD track number as parameter; track 2 = `0x02`) (Ch 39) |
| `06h` | ReadN | data read |
| `08h` | Stop | |
| `09h` | Pause | |
| `0Ah` | Init | |
| `0Bh` / `0Ch` | Mute / Demute | |
| `0Eh` | Setmode | see below |
| `15h` / `16h` | SeekL / SeekP | |
| `1Ah` | GetID | disc check |

Interrupt codes: INT1 data ready, INT2 command complete, INT3 command acknowledge, INT4 data end (CD-DA auto-pause, Ch 39), INT5 error.

**Setmode bits**: 0 CD-DA allowed (`CdlModeDA`), 1 auto-pause (`CdlModeAP`), 2 report (`CdlModeRept`, position reports during play, **not** a repeat), 3 XA filter, 4 ignore bit, 5 sector size (0 = 2048 data bytes, 1 = 2340: `CdlModeSize`), 6 XA-ADPCM, 7 speed (0 single = 75 sectors/s, about 150 KB/s; 1 double = 150 sectors/s, about 300 KB/s: `CdlModeSpeed`).

Disc facts the book uses (Ch 29): a raw sector is 2352 bytes of which 2048 are data (Mode 2 Form 1); a position is MSF in **BCD**, 75 frames per second; sector 0 is `00:02:00` (the first 150 sectors are the pregap; `CdPosToInt`/`CdIntToPos` subtract and add 150); the volume descriptor is sector 16. The CD-DA music reaches the speakers through two volumes, both non-zero: the drive matrix (`CdMix`, `{128,0,128,0}` = 100% L to L and R to R) and the SPU CD input volume (`SPU_CD_VOL_L/R`, B.10).

## B.9 Controllers and the pad buffer

Pads and memory cards share the serial port **SIO0**, a master/slave link: the console sends a byte and the pad answers with a byte at the same time. The book uses the BIOS driver and never touches these registers directly (Ch 22); they are listed for reference *(not checked in the book)*.

| Address | Register |
|---|---|
| `0x1F801040` | `JOY_DATA` (TX/RX) |
| `0x1F801044` | `JOY_STAT` |
| `0x1F801048` | `JOY_MODE` (halfword) |
| `0x1F80104A` | `JOY_CTRL` (halfword) |
| `0x1F80104E` | `JOY_BAUD` (halfword) |
| `0x1F801050-0x1F80105E` | `SIO_DATA/STAT/MODE/CTRL/MISC/BAUD` (second serial port) |

**Digital-pad poll (Ch 22).** Sent bytes `01h` (controller; `81h` selects a memory card), `42h` (read), `00h`...; the pad answers `--`, `41h` (type 4, one halfword of button data), `5Ah`, `btn_lo`, `btn_hi`.

**BIOS buffer** (`InitPAD(buf1,len1,buf2,len2)`, 34 bytes each in the SDK examples; `StartPAD()`; `ChangeClearPAD(0)` so the SDK's `VSync` acknowledges VBlank): `[0]` status (`00h` a pad answered, `FFh` no pad), `[1]` length/type byte, then `btn_lo`, `btn_hi`; PSn00bSDK names this `PADTYPE` (`stat len type btn`) in `<psxpad.h>`.

**Button word** is **active-low** (0 = pressed; an idle pad reads `0xFFFF`; holding Up gives `0xFFEF`):

| Bit | Button | Bit | Button |
|---|---|---|---|
| 0 | Select | 8 | L2 |
| 1 | L3 | 9 | R2 |
| 2 | R3 | 10 | L1 |
| 3 | Start | 11 | R1 |
| 4 | Up | 12 | Triangle |
| 5 | Right | 13 | Circle |
| 6 | Down | 14 | Cross |
| 7 | Left | 15 | Square |

## B.10 SPU

24 voices, ADPCM decoding, ADSR envelopes, a mixer with CD and external inputs, reverb, 44,100 Hz stereo output. **512 KB of SPU RAM, separate from main RAM** (the CPU cannot address it): data goes in by DMA channel 4 or by writing halfwords to the transfer FIFO. All SPU registers are 16-bit: access with `sh`/`lhu`.

### Voice registers: 16 bytes at `0x1F801C00 + 16 * v` (v = 0..23), Ch 39

| Offset | Register | Value |
|---|---|---|
| +0 / +2 | volume left / right | 15 bits, `0x3FFF` = full (bit 15 clear = fixed volume mode) |
| +4 | **pitch** (sample rate) | `0x1000` = native 44,100 Hz; `pitch = rate * 4096 / 44100`; the book never writes above `0x3FFF` (psx-spx gives `0x4000` as the useful maximum) |
| +6 | **start address** | in **8-byte units** (`addr / 8`; `getSPUAddr` rounds up) |
| +8 | ADSR1 | bits 15-8 attack (bit 15 mode, 14-10 shift, 9-8 step), 7-4 decay shift, 3-0 sustain level (0-15; 15 = full) |
| +10 | ADSR2 | bits 15-6 sustain (mode, direction, shift, step), bit 5 release mode, bits 4-0 release shift |
| +12 | envelope level | current level (the book only reads it) |
| +14 | repeat address | set by a flag-4 block as it plays |

The book writes `ADSR1 = 0x00FF` (fastest attack, sustain level 15: no shaping) and `ADSR2 = 0x000A` (release shift 10, a fade of about 50 ms). After `SpuInit` the ADSR registers hold nothing useful, so every voice needs them. Set every register of the voice **before** the key-on. Pitch examples: 22,050 Hz sample at `0x0800`; `0x0400` plays at 11,025 Hz, one octave down.

### Global registers

| Address | Name | Meaning |
|---|---|---|
| `0x1F801D80 / 82` | main volume L / R | |
| `0x1F801D84 / 86` | reverb output volume L / R | |
| `0x1F801D88 / 8A` | `SPU_KEY_ON1/2` | key-on, one bit per voice (voices 0-15, 16-23); starts the voices whose bits are set: copies start address to current address and starts the envelope |
| `0x1F801D8C / 8E` | `SPU_KEY_OFF1/2` | key-off (release) |
| `0x1F801D90-0x1F801D9A` | FM mod, noise, reverb-on enables | *(not used in the book)* |
| `0x1F801D9C / 9E` | `SPU_CHAN_STATUS1/2` | **ENDX**: voice `v` has played a block with the end flag |
| `0x1F801DA2` | reverb work-area start | *(not used)* |
| `0x1F801DA4` | IRQ address | *(not used)* |
| `0x1F801DA6` | transfer address | in 8-byte units |
| `0x1F801DA8` | transfer FIFO | halfword writes (manual transfer, `SPU_TRANSFER_BY_IO`) |
| `0x1F801DAA` | `SPU_CTRL` (SPUCNT) | bit 15 SPU enable, 14 unmute, 5-4 transfer mode (0 stop, 1 manual write, 2 DMA write, 3 DMA read), 2 CD reverb, 1 external audio enable, **0 CD audio enable** (stays set in the book) |
| `0x1F801DAC` | transfer control | normally `0x0004` *(not used directly)* |
| `0x1F801DAE` | SPU status (SPUSTAT) | |
| `0x1F801DB0 / B2` | `SPU_CD_VOL_L/R` | CD audio input volume; `SpuInit` sets `0x7FFF`, the book writes `0x6000` |
| `0x1F801DB4 / B6` | external input volume L / R | |
| `0x1F801DB8 / BA` | current main volume L / R | |
| `0x1F801DC0-0x1F801DFF` | reverb registers | *(not used)* |

### SPU RAM and sample data (Ch 39, Appendix E.4)

| Item | Fact |
|---|---|
| Size / address unit | 512 KB; addresses in the registers are bytes / 8 |
| Reserved | the first `0x1000` bytes hold capture buffers (CD audio, voices 1 and 3); the SDK puts a 16-byte dummy block next and keys every voice onto it; the first byte of a sample is `0x1010` (`SPU_RAM_FIRST`). The SDK has no `SpuMalloc`; the book keeps its own allocator |
| ADPCM block | 16 bytes = 28 samples (header byte, flags byte, 14 data bytes) |
| Flags | bit 0 end, bit 1 repeat, bit 2 loop start; the book's one-shots end with flag **1** (mutes the voice and sets ENDX), loops use flag 4 on block 1 and flag 3 on the last block |
| Upload | DMA channel 4 in 64-byte blocks (`SpuWrite`, `SpuIsTransferCompleted`) |
| Output | 44,100 Hz stereo; a voice advances `pitch / 4096` samples per output tick |
| Observing it in Redux | the registers cannot be read from Lua; the probe logs stores to `0x1F801C00-0x1F801DFF` and `0x1F801800-0x1F801803` by decoding the store instruction at the PC. `PCSX.SPU.Logger.exportSPD` writes an SPU dump; RAM address `0x1000` is at file offset `0x44` in the build used (Ch 39) |

## B.11 Frame timing and PCSX-Redux cycle counts

The CPU clock is **33.8688 MHz** (768 x 44,100). Vertical-blank periods in CPU cycles, as the chapters state them:

| Standard | Value | Source |
|---|---|---|
| NTSC, PCSX-Redux, measured | **566,120** cycles per vertical blank to the next (59.83 Hz; equal to the psx-spx hardware figure); chapters round it to "about 566,100" | Ch 34, 36, 37, 38 (cycle counter), Ch 42 |
| PAL, PCSX-Redux, measured | about **675,900** cycles (50.11 Hz) with the GPU PAL bit set | Ch 37 |
| PAL, real hardware (psx-spx) | about **680,600** cycles (49.76 Hz) | Ch 37, 42 |

These do not contradict each other. psx-spx ("GPU Timings") gives the non-interlaced refresh as **59.826 Hz** (NTSC) and **49.761 Hz** (PAL) on the nominal video clocks (NTSC 53.693175 MHz, PAL 53.203425 MHz; 263 / 314 lines of about 3413 / 3406 video clocks). Dividing the CPU clock by them gives **566,120** (NTSC, exactly what Redux counts) and about **680,600** (PAL). Redux's PAL figure is about 0.7% lower than that. It equals 314 lines at Redux's NTSC line length (566,120 / 263 = about 2,152.5 cycles), which suggests Redux keeps one line length for both standards; the book reports the figure as measured and does not investigate. A "frame" for a cycle budget in Chapters 34 to 38 is the 566,120 of Redux. Cycle counts in Redux are meaningful only under `-interpreter` (Appendix F). Scanlines per frame (non-interlaced) 263 / 314 and the display-range centers are in Appendix C (GP1 `06h`/`07h`).

Other timings the book quotes: 150 KB/s (single) and 300 KB/s (double) disc speed; one sector about 7 ms at double speed; spinning up a stopped disc about a second (Ch 29).
