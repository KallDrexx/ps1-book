# Chapter 42 quiz

**1.** A cue sheet says `TRACK 02 AUDIO`, `INDEX 00 00:15:59`, `INDEX 01 00:17:59`, and the `.bin` has 3,134 sectors. In which sector does the music start, how long is it, and what is the stretch between the two `INDEX` lines?

<details><summary>Answer</summary>

Times are minutes:seconds:frames with 75 frames (sectors) per second. `INDEX 01` is 17 s * 75 + 59 = sector 1334 of the file; the music runs from there to the end: 3,134 - 1,334 = 1,800 sectors = 24 s. `INDEX 00` is sector 15 * 75 + 59 = 1,184, so 150 sectors (2 s) lie between the two: the **pregap**, silence the player counts as part of track 2 but before its start. The data track is sectors 0 to 1,183.
</details>

**2.** Two builds of the same sources, made a minute apart, give images that differ in three sectors. What is almost certainly in those sectors, and why can the image not simply be "fixed" afterwards by patching the bytes?

<details><summary>Answer</summary>

Dates: the volume descriptor (sector 16) holds the volume's creation and modification time, and every directory record (the root directory, `DATA\`) holds its file's date. A sector also ends in error-detection and error-correction bytes computed from its contents, so patching a date means recomputing them; it is easier and safer to give the dates in the project file so the tool writes the right ones in the first place. (And the tool must be one that understands the attributes: the SDK's bundled mkpsxiso ignores the dates of files and directories without a word.)
</details>

**3.** The release folder has `MANIFEST.txt` and `SHA256SUMS`. What does each one describe, and why do you need both?

<details><summary>Answer</summary>

`MANIFEST.txt` describes what is **on the disc** (every file: hash, size, path), which lets anyone who extracts the image check that its contents are the generators' output. `SHA256SUMS` describes what is **in the folder** (the image, the cue sheet, the ELF, the papers), which lets a downloader check the files they got. One cannot replace the other: the image's own hash cannot be inside the image, and the folder's list says nothing about the files inside the `.bin`.
</details>

**4.** A PAL console's BIOS leaves the GPU in PAL mode before it starts the game. Where does the game look, and why is `video_mode = 0` in the source "working" on every emulator you own until someone with a PAL setting runs it?

<details><summary>Answer</summary>

Bit 20 of the GPU status register (`0x1F801814`): 0 = NTSC, 1 = PAL. PSn00bSDK's `ResetGraph(0)` reads it when it first starts and `GetVideoMode()` returns it. A hard-coded 0 is right on every NTSC console and emulator, which is why it survives testing; on PAL it makes `dt_scale` 4096 and `race_hz()` 60, so the world advances a sixth too slowly (each 1/50 s tick moves it by only 1/60 s) and the countdown lasts 3.6 s instead of 3.
</details>

**5.** Your release build removes the debug keys. A colleague suggests also making the ship's `drag` constant a bit friendlier in the release "since nobody will see". What is wrong with that, in general?

<details><summary>Answer</summary>

A release build may remove *tools* (keys, readouts, logging) but not *behavior*: everything you verified, played and measured was done with the development build's rules, so a release with different rules is an untested game. The switch should be the single `HOVERLINE_RELEASE` guard around things the player never uses, and the verifier's play-through of the release disc (the countdown ticks, the ship accelerating) exists to catch accidental differences.
</details>

**6.** Why does `NOTICES.TXT` go on the disc, with the volume's copyright identifier naming it, as well as in the release folder?

<details><summary>Answer</summary>

The folder is separated from the image the first time somebody copies only the `.bin` and `.cue`. The disc is the one thing that always travels with the game, so the statement of what the game is made of and who does not endorse it has to be inside it. The copyright identifier is a *file name*, so it should name a file that exists; an identifier that points nowhere (like the `README.TXT` this chapter's starter inherited) is a small bug a tool will find.
</details>

**7.** What does the verifier's PAL run test about your program, and what does it not?

<details><summary>Answer</summary>

It tests that the program **asks the console** which standard it is on: the verifier sets the GPU to PAL just before `main`, so `video_mode`, `dt_scale` and the countdown length (150 ticks) change only if the program reads the status bit and uses it. It does not test the length of a PAL frame (ticks are counted, not cycles), the picture on a PAL display, or any PAL BIOS: it checks what the program reads, not a PAL machine.
</details>
