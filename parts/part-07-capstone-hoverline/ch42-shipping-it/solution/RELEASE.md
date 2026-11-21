# Hoverline 1.0: release notes

An original anti-gravity time trial for the PlayStation. Boot `hoverline.cue` (data track, then one CD-DA music track). The disc is unlicensed homebrew and carries no Sony license data; burned to a CD-R it has no SCEx region string, so a retail console boots it only with a modchip or a disc-swap trick (or runs the image from an optical drive emulator); emulators and loaders need nothing.

## How it was built

`make release` from a clean checkout, with PSn00bSDK 0.24, GCC 12.3.0 (`mipsel-none-elf`) and mkpsxiso 2.30 as pinned in `tools/versions.txt`. The result is in `release/`: `hoverline.bin`, `hoverline.cue`, `hoverline.elf` (symbols, not on the disc), `MANIFEST.txt` (the files on the disc), `SHA256SUMS`, `NOTICES.TXT`, this file. Two builds in different directories give byte-identical `hoverline.bin` and `hoverline.cue`: every timestamp in `iso.xml` is fixed.

## PCSX-Redux

Status: tested

PCSX-Redux build dd3497b5 (rolling dev build 582), interpreter core, OpenBIOS, headless. NTSC, and PAL (OpenBIOS does not set the GPU's PAL bit, so the verifier sets it with GP1(08h) just before `main`, as a PAL BIOS would) both boot to the title, run the countdown and reach the race; the PAL run counts 150 ticks of countdown, the NTSC run 180. Timings: this is an interpreter, so cycle counts are exact for the emulated CPU, not for hardware. Not compared with a retail BIOS.

## DuckStation

Status: not tested

DuckStation could not be run in the environment the book was written in (no headless mode, no display). Expected differences to look for when you try it: the sound of the looping engine voice and the end of one-shots (SPU details), the exact frame pacing in PAL, and how the CD-DA track is found from the cue sheet.

## Mednafen

Status: not tested

Mednafen was not installed in the authoring environment. Its accuracy-first core is the one most likely to show timing problems in the GPU command lists and the CD loading; run the disc from the title to the results screen and compare.

## Real hardware

Status: not tested

No console, modchip or optical drive emulator was available. Before calling the game working on hardware, check: the disc boots (license data aside), both video standards, the music (CD-DA through the CD mixer), and that the frame rate holds on the slow part of the track with a real CD drive.

## Known issues

Lap 1 is about half a section shorter than the others (the ship starts at the middle of its section). The best lap is kept in RAM only; there is no memory card support.
