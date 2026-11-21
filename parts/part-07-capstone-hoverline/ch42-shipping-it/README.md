# Chapter 42: Shipping It

## 1. Concept

A program is finished when someone else can run it. **Shipping** is the work between "it runs on my machine" and that sentence: one command that makes the release from sources and nothing else, an image whose bytes depend on the inputs and on nothing else (not the clock, not the directory, not the time zone), a game that knows which kind of console it is on, a disc that carries no debug tools and no stolen property, and a few honest pages that say what it is, what it is made of and where it has been tested.

## 2. Why it matters

Everything so far was checked by a script that builds the game, boots it and looks at memory. A release is a different kind of promise: *this exact file*. If a bug report says "the disc crashes on the third lap", you must be able to rebuild the disc that was reported, byte for byte, a year later. If you cannot say what is in the image, you cannot say who owns it. If the game thinks every console is NTSC, every player with a PAL console (and every emulator set to PAL) gets a game that runs a sixth too slow. None of this is code in the usual sense; all of it is a few lines of build rules, one `if`, and some writing, and each one is easy to get *almost* right.

## 3. Learning objectives

After this chapter you can:

- read a PlayStation disc image by hand: the 2352-byte sector, the system area, the ISO 9660 volume descriptor, directories, `SYSTEM.CNF`, and the cue sheet with its tracks and pregap;
- build an image **reproducibly**: find every place a timestamp hides, fix it, pin the tool that makes the image, and prove it by building twice in different places;
- separate a **release** build from a development build with one compile-time switch, and say what belongs in each;
- tell the three things called "region" apart (the video standard, the disc licence check, the executable's header string), detect NTSC or PAL at run time, and say what each does on an emulator and on a console;
- assemble a release folder with a manifest and checksums that anyone can verify, and write the notices that say where every file came from;
- plan a test across emulators and real hardware, record what you saw (and what you did not see), and know where to go next.

## 4. Prerequisites

[Chapter 29](../../part-06-assets-cdrom-textures-and-compression/ch29-the-cd-rom-and-loading-files/README.md) (`SYSTEM.CNF`, mkpsxiso), [37](../ch37-ship-movement-and-physics/README.md) (`dt_scale`, ticks), [39](../ch39-audio/README.md) (the CD-DA track), [41](../ch41-handling-game-loop-and-polish/README.md) (the finished game); Appendix E. This chapter starts from Chapter 41's `solution/`.

## 5. Explanation

### 5.1 What is shipped

```
   sources (C, CMake, iso.xml, system.cnf, NOTICES.TXT, RELEASE.md)
        |                                            tools/assets/*.py   (the generators)
        |  cmake -DHOVERLINE_RELEASE=ON                       |
        v                                                     v
     game.exe  ----------------------------->  mkpsxiso (the PINNED one) <----  assets/*.TIM .TPK .SHP .TRK .VAG  MUSIC.WAV
        |                                            |
        |                                            v
   game.elf (symbols)              hoverline.bin + hoverline.cue
        |                                            |
        +-------------------+------------------------+
                            v
   release/   hoverline.bin   hoverline.cue   hoverline.elf   MANIFEST.txt   SHA256SUMS   NOTICES.TXT   RELEASE.md
```

The **disc** (`.bin` + `.cue`) is the product. The **ELF** is not on the disc; it is the key to a crash address (`mipsel-none-elf-addr2line`) in a bug report about *this* build, so it travels with the release. `MANIFEST.txt` lists what is **on the disc** (hash, size, path); `SHA256SUMS` lists what is **in the folder**, in the format `sha256sum -c` reads, so a downloader can check the pair. `NOTICES.TXT` is also on the disc (5.6) and `RELEASE.md` is the human page (5.7).

### 5.2 The disc image, by hand

A `.bin` is a list of raw sectors, 2352 bytes each. A data sector of this game is **MODE 2 Form 1**:

```
 0        12   16        24                      2072   2076                 2352
 +---------+----+---------+-----------------------+------+--------------------+
 |  sync   | hdr| subhdr  |   2048 bytes of data  | EDC  |        ECC         |
 +---------+----+---------+-----------------------+------+--------------------+
   00 FF*10 00   mm ss ff 02  (file/channel/submode/coding, twice)        error detection / correction
```

Everything the file system says lives in the 2048-byte part. The layout of this image, from `example/isoinfo.py release/hoverline.cue`:

| Sectors | What |
|---|---|
| 0 to 15 | the **system area**. On a retail disc, sector 4 holds Sony's licence text and 5 to 11 its logo data. Here: all zero. |
| 16 | the **primary volume descriptor** (`CD001`): system and application identifier (`PLAYSTATION`), volume name, the creation and modification dates, the copyright file identifier, the root directory |
| 17 to 22 | the terminator, the path tables, the root directory (a list of records: name, first sector, size, date, flags) |
| 23 and on | `SYSTEM.CNF`, the notices, `HOVER.EXE`, then `DATA\` with its files, each starting on a sector boundary |
| the rest | the **audio track**: raw CD-DA samples, 44.1 kHz 16-bit stereo, 75 sectors per second |

The **cue sheet** tells an emulator or a burning tool how to cut that file into tracks:

```
FILE "hoverline.bin" BINARY
  TRACK 01 MODE2/2352
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    INDEX 00 00:15:59        <- the pregap (2 s) starts here
    INDEX 01 00:17:59        <- the music starts here: 17 s * 75 + 59 = sector 1334
```

Times are minutes, seconds and frames (75 per second): the music begins at sector 1334 of the file, 1,800 sectors (24 s) before the end. The `FILE` name is **relative** so the pair can be moved.

`SYSTEM.CNF` is the whole boot protocol: `BOOT = cdrom:\HOVER.EXE;1` names the executable (`;1` is the ISO 9660 version number), and `TCB`, `EVENT` and `STACK` tell the kernel how many threads and events to allow and where the stack starts. The BIOS reads this file with its own tiny file system code, finds the executable and runs it. The **copyright identifier** in the volume descriptor is a *file name* in the root; it must point to a file that exists (a disc whose identifier names a missing file is a small lie that tools notice).

**Reproducibility.** Build the starter twice, a few seconds apart, and compare the images (`cmp`, or `example/isoinfo.py a.bin b.bin`). Three sectors differ, a few dozen bytes each (how many depends on how many digits of the clock changed), and nothing else:

| Where | What changed |
|---|---|
| sector 16 | the volume's creation and modification time, and the date in the root record |
| the root directory | the date of `.` and `..` and of every record |
| the `DATA\` directory | the date of every record (each file's modification time) |

Dates are the usual culprit, and there is no way to fix them *after* the image is made without recomputing the error-correction bytes, so they must be fixed in the **project file**. The mkpsxiso that the book pins (2.30, `tools/versions.txt`) can: its `share/doc/mkpsxiso/example.xml` documents a `date` attribute (`YYYYMMDDHHMMSS`) for `directory_tree`, `dir` and `file`, and the `identifiers` element takes `creation_date` and `modification_date` (16 digits: the same plus hundredths; not in `example.xml`). The SDK ships an **older** mkpsxiso (2.03) and its CMake macro finds that one first. It honours the two volume dates but silently ignores `date` on files and directories (it uses the files' modification times), so the XML builds fine and the root and `DATA\` directories still differ. The macro looks the tool up in a cache variable (`MKPSXISO`, in the SDK's `internal_setup.cmake`), so a build can be told which one to use.

Two more sources of difference are not in the image. The generators are deterministic by design (the same seed gives the same bytes); lists in your own scripts must be **sorted**, because directory order is the file system's choice. And `game.elf` contains the build directory in its debug information, so it differs between two checkouts even when `game.exe` does not; that is why reproducibility is judged on the image, the cue sheet and the manifest, and the ELF is "the symbols of this build", not a promise of identical bytes. (A compiler flag, `-ffile-prefix-map`, would fix that too.)

### 5.3 Release and development builds

The development disc has things the player must not have: the debug keys (Select: wireframe, Triangle: subdivision outlines, R1: subdivision), and the two text lines at the top left (`SEC / PRIMS`, the edge distances) that cost a `snprintf` each frame. The cleanest way to keep both is **one switch**: the CMake option `HOVERLINE_RELEASE` (given in the starter) defines the macro of the same name, and the source tests it.

```c
#ifndef HOVERLINE_RELEASE
    /* development only */
#endif
```

Rules for such a switch: it removes *tools*, never *behaviour* (the physics, the sounds and the timing are the same in both builds, or the release is a game nobody tested); it is set in **one** place (the build rule, not scattered `#define`s); and the development build stays the default so that `make` is what you use every day. Optimisation is the same in both: the SDK's flags use `-O2`, and the book's Makefile builds both discs in the Release configuration. What a release removes beyond debug *features* is debug *output*: a `printf` to the TTY costs time and reveals your internals.

### 5.4 Region, three ways

"Region" means three different things on a PlayStation, and a release must treat each on purpose.

| What | Where it lives | What it does |
|---|---|---|
| **Video standard** (NTSC 60 Hz / PAL 50 Hz) | a bit in the GPU's status register (`0x1F801814`, bit 20); the BIOS sets it from its own region at start-up | decides the frame period (about 566,100 CPU cycles in NTSC, 680,600 in PAL: Chapter 37) and the picture's height. **The game must adapt.** |
| **Disc region lock** | the **SCEx string** (`SCEA`, `SCEE` or `SCEI`) that a pressing plant puts in the wobble of the disc's groove, outside every sector; Sony's licence text and logo in sectors 4 to 11 also name a region | the CD controller reads the string and a console boots only a disc of its own region; a CD-R cannot carry it, whatever its sectors hold. Modchips inject the string, optical drive emulators and loaders bypass the drive, emulators do not check it. |
| **The executable's header string** | the 60-odd bytes at `0x4C` of the PS-X EXE header ("Sony Computer Entertainment Inc. for Europe area") | historically the region marker of a licensed executable; the disc boot path of an emulator ignores it, and SDK tools such as `elf2x` leave it empty. |

For the first one the game does what Chapter 37 prepared: `dt_scale` (4096 NTSC, 4915 PAL) and `race_hz()` (60 / 50) already exist; until now `video_mode` was a variable the verifier set. A shipped game must **ask**. PSn00bSDK's `ResetGraph(0)` reads the GPU's video-mode bit when it first starts up (from the disassembly of the 0.24 library: it reads the status register at its first start-up, before it sends the GPU its reset command) and keeps it for `GetVideoMode()`; so the game calls `ResetGraph(0)` first thing in `main` and then asks. Ask **once**, early, before anything that depends on it (`dt_scale`, the display set-up), and let the display code set the matching mode.

A caution about the emulator. A real PAL console's BIOS leaves the GPU in PAL mode when it hands over to the game. **OpenBIOS**, which PCSX-Redux runs when you give it no BIOS file, does not; so the verifier's PAL run does what a PAL BIOS would have done: three instructions that write the GPU command `0x08000008` just before `main`. That is a faithful test of *your* code (it must read the console, not a constant) and an unfaithful test of everything else: **the picture on a PAL screen is not checked** (the game draws a 240-line picture; a PAL display has 288 lines, so on a real PAL set the image sits in a taller frame; positioning it is a stretch goal) and neither is the timing of a PAL frame.

### 5.5 The release folder

`make release` does, in order: configure a **separate** build directory (`build-release`, so the development build is not disturbed) with the release option and the pinned tool, build, then gather. The gathering is a script you write (any language the book's environment has; Python is already there): copy the five files, write `MANIFEST.txt` from the same project file mkpsxiso was given (never from a hand-kept list), and write `SHA256SUMS` last, over everything else. Sort every list. The make target must work in a **clean checkout**: no file of an earlier build may be needed, and no prebuilt image may sit in the source tree (a release assembled from a stale file is the classic way to ship the wrong build).

The checksum format is fixed by the tool that reads it: 64 hex digits, two spaces (or a space and `*`), the file name, one per line.

### 5.6 Licensing and notices

A game you give to others carries a duty to say what it is made of.

- **Your content.** The book's rule is that everything is original or generated: the notice names the generators (`tools/assets/*.py`) and says so. A commercial game's tracks, textures or samples, however altered, are not yours to ship; the rule exists so that nobody has to ask.
- **Software you link.** The SDK's own `LICENSE.md` (in the install, `share/psn00bsdk/doc/LICENSE.md`) says what applies: the PSn00bSDK core (the libraries in `HOVER.EXE`, the CMake scripts, some tools) is under the **Mozilla Public License 2.0**, which allows a closed or differently licensed game but requires you to share changes you make to the SDK's own files; the same file says that using the SDK as is, you need not publish anything. MPL 2.0 also asks whoever distributes the covered code in executable form to tell recipients where its source is (section 3.2), so the notice names the SDK, its version, its licence and its address: one sentence that costs nothing. mkpsxiso is GPL version 2 or later and the bundled GCC is GPL version 3; they *make* the disc and none of their code is on it (this `HOVER.EXE` links no `libgcc` routine; if yours does, 64-bit division for example, GCC's Runtime Library Exception lets you ship it under your own terms).
- **Trademarks and Sony's property.** "PlayStation" names the console; say so and say that the disc is **not licensed, endorsed or published by** Sony. Do not put Sony's licence text, logo data or boot-screen data in an image (the system area of this image is empty on purpose, and the verifier looks for Sony's text outside `NOTICES.TXT`).
- **Where.** `NOTICES.TXT` is a file **on the disc** (so it travels with every copy of the image) and the volume's copyright identifier names it. This is not legal advice; it is the checklist a hobbyist release should pass.

### 5.7 Testing across emulators and hardware

The same disc behaves differently on different emulators because they trade accuracy for speed differently. What to look at in *this* game:

| Area | Why it can differ |
|---|---|
| CD: the data track and the CD-DA music | how the cue sheet is read, how fast the drive is emulated, whether the audio loop restarts cleanly |
| SPU | looping samples and the end of one-shots, ADSR, the CD mixer volume |
| GPU | the 24-bit rounding of Gouraud shading, dithering, the texture window, the drawing of `LINE` primitives; a hardware renderer shows polygon seams that the software renderer hides |
| GTE | the precision and overflow flags (the track is built to fit its 16-bit limits, but the edge is where emulators disagree) |
| Timing | how many CPU cycles a frame takes (the game counts ticks by `VSync`, so a slow emulator makes a slow game, never a different one) |

Test the same script on each: boot, title, left / right to pick the track, start, the countdown, a lap, the results, restart, a quit to the title; then the same in the other video standard (every emulator has a setting for it). Write down the version of the emulator and its settings with what you saw, and write **"not tested"** where you did not test: a note that says "works on DuckStation" without a version is worth less than a note that says "not tested". On the verification machine only PCSX-Redux can be driven headless; `RELEASE.md` is where DuckStation, Mednafen and the hardware are recorded, with a `Status:` line each.

On real hardware, in rough order of effort (check each project's documentation for the current state): a **serial or parallel loader** (Unirom on the console, with a PC-side uploader such as PCSX-Redux's `nops`) runs an executable without a disc; an **optical drive emulator** (an SD card in the CD drive's place) runs an image without the drive's region check; a **burned CD-R** needs a modchip or the disc-swap trick because it cannot carry the SCEx string (5.4); a memory-card boot exploit runs code from a card. The game's disc is plain data plus an executable, so it is ready for all of them; the audio track and the loading speed of a real drive are the first things to test.

### 5.8 Where to go from here

You have written a complete game from the CPU registers up. Doors to open next, none needed to finish this book: **MDEC video** (the decompression engine that played the FMV; `libpress` in PSn00bSDK); **memory cards** (save the best lap: the BIOS card calls, the card's file system); **interrupts and your own event handlers** (everything `VSync` and the pad hide); the **link cable** (serial); **profiling** with the hardware timers (Chapter 38's methods, on a real console); the **Net Yaroze**, Sony's 1996 hobbyist console (a retrospective: C, a small SDK, a 2 MB limit, and the cultural root of everything in this book); and **contributing**: PSn00bSDK, PCSX-Redux, psx-spx and the emulators all take bug reports with a reproducible disc, and now you can make one.

### 5.9 What the emulator showed

PCSX-Redux (`tools/versions.txt`), the solution, the verifier's runs:

| Question | Observed |
|---|---|
| Image | 3,134 sectors, 7,371,168 bytes: a 1,184-sector data track, a 150-sector pregap, 1,800 sectors of music; 19 files plus the audio track in `MANIFEST.txt` |
| Build time | about 5 s for a clean `make release` including the generators (the music takes 2.7 s of it) |
| The starter's `iso.xml` (no dates), two builds, either mkpsxiso | 3 sectors differ (the volume descriptor, the root directory, `DATA\`), 132 bytes in one pair of builds |
| All dates fixed, the SDK's mkpsxiso 2.03 | 2 sectors differ (the root directory and `DATA\`: file and directory dates); the volume descriptor is now the same |
| mkpsxiso 2.30, the file dates fixed but not the volume dates | the same three sectors still differ (the volume's own time, the root's `.` and `..`) |
| mkpsxiso 2.30, all dates fixed | identical, in another directory and another time zone |
| `game.elf` | differs between two directories (paths in the debug information); `game.exe` does not |
| The release disc, NTSC | countdown 180 ticks; with the debug readout, 323 white pixels in the readout area; without it, none |
| The release disc, PAL (the GPU bit set before `main`) | `video_mode` 1, `dt_scale` 4915, countdown 150 ticks |
| `GetVideoMode()` on OpenBIOS, nothing done | always NTSC |

**Not verified:** DuckStation, Mednafen, any real hardware; the look of the picture on a PAL display; the timing of a PAL frame (the verifier's PAL run is a console *report*, not a 50 Hz clock); how a retail BIOS treats the image (the licence check); that the notices are legally sufficient.

### 5.10 How the verifier checks

1. **Build.** `make release` in your project.
2. **Static checks**, on the files in `release/`: the file list and `SHA256SUMS`; the cue sheet; the image parsed by a small ISO 9660 reader in `checks.py` (identifiers, `SYSTEM.CNF`, the executable, the copyright file); **every asset byte for byte** against what the generators make, and the audio track against `MUSIC.WAV`; an all-zero system area and no Sony licence text anywhere outside `NOTICES.TXT`; `MANIFEST.txt` against the image; `NOTICES.TXT` and `RELEASE.md` for content.
3. **Reproducibility**: the project is copied without any build output to a fresh directory, `make release` runs again there with `TZ` changed, and the `.bin`, `.cue` and `MANIFEST.txt` must be identical to yours.
4. **Two runs of the release disc** in PCSX-Redux: an NTSC console and a PAL one. START, the countdown, CROSS held in the race; Select, Triangle and R1 pressed in the countdown and in the race. Recorded per frame: the state, ticks, `video_mode`, `dt_scale`, the three debug variables, the ship's speed, the HUD text; screenshots.
5. A **note** that DuckStation and Mednafen were not run.

## 6. Worked example

`example/isoinfo.py` is the small reader the verifier is built on. Run it on an image you built:

```
python3 example/isoinfo.py release/hoverline.cue            what 5.2 describes: the tracks, the identifiers, every file with its sector
python3 example/isoinfo.py a/hoverline.bin b/hoverline.bin  which sectors differ between two builds, and which file lives in them
```

The numbers to check by hand: `HOVER.EXE` starts at sector 26, so at byte `26 * 2352 + 24 = 61,176` of the `.bin` you find `PS-X EXE`; its 133,120 bytes take 65 sectors. The file `DATA/LOGO.TIM` is 4,160 bytes at sector 92: 3 sectors, the last one mostly empty. The manifest line for it is its SHA-256, the size, and the path:

```
<64 hex digits>       4160  DATA/LOGO.TIM
```

and `sha256sum -c SHA256SUMS` in `release/` checks the folder. A release is trusted when someone else can reproduce those lines.

## 7. Project: ship Hoverline

### 7.1 Behaviour

`make release` in a clean checkout produces `release/` with the seven files of 5.1. The disc inside boots on a console of either video standard and runs the game of Chapter 41 without its development tools, and it carries a `NOTICES.TXT`. Building it twice anywhere gives the same image. `RELEASE.md` says what was and was not tested.

### 7.2 The contract

`starter/` is Chapter 41's `solution/` plus scaffolding. **Given:** the game; the `HOVERLINE_RELEASE` option in `CMakeLists.txt`; a `make release` that builds with it and copies the image (so you can see what is missing); skeletons for `NOTICES.TXT` and `RELEASE.md`. **You write:**

| Where | What |
|---|---|
| `main.c` | the video standard, asked of the console once, before `dt_scale` and the display are set (5.4) |
| `game.c` | the debug keys and the debug readout compiled out of the release (5.3) |
| `iso.xml` | every timestamp fixed; the copyright identifier naming a file that exists; `NOTICES.TXT` on the disc (5.2, 5.6) |
| `Makefile` / `CMakeLists.txt` | `make release` using the pinned mkpsxiso (5.2) |
| a script of your own | the gathering: `MANIFEST.txt`, `SHA256SUMS`, copies (5.5) |
| `NOTICES.TXT`, `RELEASE.md` | the papers (5.6, 5.7) |

**State the verifier reads:** `video_mode`, `dt_scale`, `game_state`, `frame_no`, `frame_ticks`, `wire_mode`, `subdiv_debug`, `subdiv_enabled`, `ship`, `race_text`, `load_status` (all declared by the starter), and `release/hoverline.elf` for the symbols.

### 7.3 Steps

1. Run `make release` on the starter; open the result with `isoinfo.py` and see what is missing (`dates`, `NOTICES.TXT`).
2. Build twice and compare with `isoinfo.py a.bin b.bin`; make them equal.
3. The release switch (`game.c`), then the video standard (`main.c`); `make run` still plays.
4. The gathering script, the notices, `RELEASE.md`.
5. `verify.sh`, then a clean clone and `make release` again.

### 7.4 Rules

- The release is made from sources and the generators only; no image, executable or archive in the source tree.
- The development build (`make`) still has the debug keys and readout.
- `MANIFEST.txt` is computed from the build, not typed.
- `RELEASE.md` says `Status: not tested` for anything you did not run. A false `tested` is worse than none.
- All content is original or generated; never add a file from a commercial game.

### 7.5 Hints

- If two images differ, `isoinfo.py a.bin b.bin` names the sector and the file; start with sector 16.
- The SDK's CMake macro caches the path of the tool it finds; the cache is set before the first configure.
- The release switch changes *what is drawn and what the pad does*, not what the ship does.
- If the countdown is 20% too long on PAL, `video_mode` is still 0.
- A notice is a sentence per file group, not a licence text.

### 7.6 Stretch goals

- **A PAL picture**: use the 288 lines (centre the 240-line frame, or draw a taller one).
- **`-ffile-prefix-map`** so that `game.elf` is reproducible too.
- **A version string** in the title, taken from the build (`git describe`) and recorded in `RELEASE.md`.
- **A bug-report helper** that runs `addr2line` on an address with the shipped ELF.
- **Test a second emulator** (DuckStation, Mednafen) and write what you saw in `RELEASE.md`.
- **Save the best lap** on a memory card.

## 8. Verification

```sh
source tools/env.sh
parts/part-07-capstone-hoverline/ch42-shipping-it/verify/verify.sh            # your starter/
parts/part-07-capstone-hoverline/ch42-shipping-it/verify/verify.sh --solution # the reference
```

About a minute and a half: three builds (yours, the clean copy, and the harness's), two short emulator runs.

| Check | What it means | If it fails |
|---|---|---|
| release folder | the seven files, `SHA256SUMS` correct | the gathering script |
| cue sheet | tracks, modes, `INDEX` in the file, the audio track equals `MUSIC.WAV` | the cue sheet is mkpsxiso's; did the XML lose the audio track? |
| disc image | identifiers, `SYSTEM.CNF`, the executable's size, the copyright file exists | `iso.xml` |
| every asset | byte for byte the generators' output | a stale or edited asset |
| no Sony data | sectors 0 to 15 all zero; no Sony licence text outside `NOTICES.TXT` | a licence file in the XML |
| `MANIFEST.txt` | every file on the disc, right hash and size | computed from the wrong list |
| `NOTICES.TXT` | on the disc and in `release/`, every file named, "not licensed by Sony", origin, SDK | missing sentences |
| `RELEASE.md` | four sections, a `Status:` each, no TODO | the skeleton |
| reproducible | a clean copy in another place and zone gives the same image | dates; the SDK's tool; a prebuilt file |
| play NTSC / PAL | boots, countdown 180 / 150 ticks, `video_mode`, `dt_scale`, the ship moves, the HUD is drawn | the console is asked; the constants |
| debug keys, readout | the three variables stay 0 under key presses; no text at the top left | `HOVERLINE_RELEASE` |

A pass ends with `CHAPTER 42: PASSED (13/13 checks)`. The untouched starter builds and fails (exit 1). `verify/mutants.py` makes plausible wrong solutions (a missing volume date, the SDK's mkpsxiso, a constant video mode, an inverted test, a release that keeps the readout, a copyright identifier that points nowhere) and checks that `verify.sh` rejects each (about 1.5 minutes each; not part of CI).

**Not verified**, as 5.9 says: DuckStation, Mednafen, hardware, the PAL picture, and whether the text of `NOTICES.TXT` is *sufficient*; the verifier checks that it exists and says the right kinds of things. The note about the emulators that could not be run is printed at the top of every run.

## 9. Common pitfalls

- **A release that is not the build you tested.** Run the verifier on `release/`, not on `build/`.
- **Timestamps.** The clock is an input. Fix every date or the image changes each build.
- **The wrong mkpsxiso.** The one the SDK finds first ignores the attributes of the one you read about.
- **A hand-kept manifest.** It is wrong the day after you write it.
- **Different behaviour in the two builds.** Strip tools, never rules.
- **A constant for the console.** `video_mode = 0` works on every machine you own.
- **Asking late.** The SDK reads the bit at its first start-up only; ask before anything depends on the answer (5.4).
- **Copying Sony's licence sectors** "so it boots". They are not yours, and they would not make a CD-R boot anyway: the lock is the SCEx string, which no sector holds (5.4).
- **"Tested" without a version.** Say which emulator, which build, which settings, or say "not tested".

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- `example/isoinfo.py`: the disc reader, a page long.
- `tools/versions.txt` and `share/doc/mkpsxiso/example.xml` in the mkpsxiso install: the attributes of the project file.
- psx-spx: *CDROM File Formats* (sectors, ISO 9660 in MODE 2), *CDROM Disk Format*, *GPU Status Register* (bit 20), *BIOS Boot*.
- The PSn00bSDK documentation and `LICENSE.md` of the version you ship (`.toolchain/opt/psn00bsdk/share/psn00bsdk/doc/LICENSE.md` here); the Mozilla Public License 2.0 FAQ.
- psx-spx: *CDROM Protection - SCEx Strings* (the region lock).
- The documentation of PCSX-Redux, DuckStation and Mednafen for their video-standard and BIOS settings.
- Reproducible Builds (reproducible-builds.org): the general version of 5.2.
