# Chapter 1: The PlayStation and Your Workbench

## 1. Concept

The PlayStation is a small set of cooperating chips built around a 33.8688 MHz MIPS R3000A CPU. You develop for it by **cross-development**: you build programs on your PC, then run them on the console or, in this book, in an emulator.

## 2. Why it matters

Every later chapter assumes you know which chip does what and that your toolchain works. When a sprite fails to appear in Chapter 17, you need to know whether to blame the CPU, the GPU or the DMA controller, and you want to rebuild and see the fix in seconds. This chapter gives you the map and the workbench.

### 2.1 How Sony got here

The PlayStation began as a failed partnership. In 1988 Sony agreed to build a CD-ROM add-on for Nintendo's Super Famicom (the SNES). Sony already made the SNES sound chip, designed by a Sony engineer named Ken Kutaragi. At the Consumer Electronics Show in June 1991, Sony announced the "Play Station". The next day Nintendo announced that it would work with Philips instead. Kutaragi persuaded Sony to turn the project into its own console, and Sony Computer Entertainment was founded in November 1993.

The market it entered was crowded and changing fast:

| Machine | Launch | Medium | Note |
|---|---|---|---|
| 3DO | 1993 | CD-ROM | Licensed to several makers; expensive |
| Atari Jaguar | 1993 | Cartridge | Hard to program; sold poorly |
| Sega Saturn | Nov 1994 (Japan) | CD-ROM | Two CPUs; strong in 2D, awkward in 3D |
| **Sony PlayStation** | **3 Dec 1994 (Japan)** | **CD-ROM** | One CPU, dedicated 3D math and polygon hardware |
| Nintendo 64 | Jun 1996 (Japan) | Cartridge | Faster 3D, but costly cartridges |

The PlayStation launched in Japan at ¥39,800. It reached North America on 9 September 1995 at $299, $100 less than the Saturn, and Europe on 29 September 1995. Sony made three bets that shaped everything you will write in this book:

1. **3D polygons first.** The hardware is designed to transform and draw many textured triangles per frame. Arcade-style 3D games such as *Ridge Racer* (a launch title) and Psygnosis's anti-gravity racer *Wipeout* (1995) showed it off. The capstone of this book, *Hoverline*, is an original game in that tradition.
2. **CD-ROM, not cartridges.** A disc holds about 650 MB and is cheap to press. Cartridges were faster but smaller and far more expensive. The trade-off is loading time, which is why Part VI spends time on files, compression and streaming.
3. **Easy for developers.** Sony shipped C libraries and PC-hosted development kits, so studios could write most of a game in C instead of hand-tuned assembly.

The bet paid off. The PlayStation was the first home console to sell more than 100 million units, and Sony made it until 2006. Its hardware is small and well documented, which makes it an excellent machine to learn on.

### 2.2 How games were made then, and how you will make them now

A 1995 studio wrote code on a PC with Sony's development hardware installed, such as the DTL-H2000 board set. They compiled with a C compiler and linked against Sony's libraries, often using the Psy-Q tools from SN Systems and Psygnosis. Then they downloaded the program to the board and debugged it there. In 1996-97 Sony even sold a hobbyist kit, the Net Yaroze.

You will do the same thing with free tools. The emulator plays the part of the development board: it loads your program, runs it, and lets you stop and inspect it. The workflow is the same; only the hardware has changed.

## 3. Learning objectives

After this chapter you can:

- name the main PS1 chips and say what each one does;
- explain cross-development and how an assembler, an executable file and an emulator fit together;
- install the toolchain and check it with `tools/doctor.sh`;
- build a PSX-EXE, run it in PCSX-Redux, and find the CPU, register and VRAM views;
- change a program, rebuild it, and prove the change with `verify.sh`.

## 4. Prerequisites

None from this book. You should be comfortable at a shell prompt: changing directories, running scripts, and editing a text file.

## 5. Explanation

### 5.1 The hardware at a glance

```
 +------------------------+     +--------------------------+
 | CPU: R3000A core       |<--->| GTE (coprocessor 2)      |
 | 33.8688 MHz            |     | fixed-point 3D math      |
 | 4 KB I-cache           |     +--------------------------+
 | 1 KB scratchpad        |
 +-----------+------------+
             |  main bus (memory and memory-mapped I/O)
 +------+----+---+-------+-------+-------+--------+---------+
 |      |        |       |       |       |        |         |
 RAM    BIOS     DMA     GPU     MDEC    SPU      CD-ROM    pads,
 2 MB   ROM      7 ch.    |      video    |       2x drive  memory
        512 KB            |      decode   |                 cards
                       VRAM 1 MB       sound RAM 512 KB
                          |
                       TV out
```

Read this table once now; come back to it when a later chapter introduces a chip.

| Chip | What it does | What it does *not* do | You meet it in |
|---|---|---|---|
| **CPU** | An R3000A-compatible MIPS I core (an LSI Logic CW33300) on a Sony chip. Runs your code: 32-bit integer instructions, a 4 KB instruction cache, and a 1 KB **scratchpad** of fast RAM in place of a data cache. | No floating point. No data cache. | Part I onward |
| **GTE** | The Geometry Transformation Engine, coprocessor 2 inside the CPU chip. Rotates, translates and projects 3D points, and computes lighting, in fixed-point arithmetic. | Draws nothing; it only computes. | Part V |
| **GPU** | A 2D rasterizer. Draws flat, Gouraud-shaded and textured triangles and quads, lines, and rectangles into VRAM, then sends part of VRAM to the TV as the picture. | No Z-buffer and no perspective-correct texturing, so the program sorts polygons itself (Chapter 20). | This chapter, Part III |
| **VRAM** | 1 MB of video memory, wired to the GPU only. Think of it as a 1024x512 grid of 16-bit pixels that holds the frame buffers *and* all textures and palettes. | The CPU cannot address it directly. | This chapter, Part III |
| **DMA** | Seven channels that copy blocks between RAM and the GPU, CD-ROM, SPU and MDEC while the CPU does other work. | Does not decide *what* to copy; the CPU sets it up. | Part III |
| **MDEC** | Decompresses JPEG-like image blocks for full-motion video. | Only decodes; the GPU displays the result. | Optional |
| **SPU** | The sound chip: 24 ADPCM voices at up to 44.1 kHz, 512 KB of its own sound RAM, and hardware reverb. It can also mix in CD audio. | Does not read your RAM; samples are copied into sound RAM first. | Part VII |
| **CD-ROM** | A double-speed drive, about 300 KB per second, with its own controller. | Slow to seek; reading a file takes planning. | Part VI |
| **BIOS** | 512 KB of ROM: the boot code, the kernel with its system calls, and the memory card / CD player screen. | Not needed by the emulator; PCSX-Redux has a free replacement, OpenBIOS. | Chapter 22 |
| **Pads and cards** | Controllers and 128 KB memory cards on a serial port. | | Chapter 22 |

Some numbers worth remembering:

- **33.8688 MHz** is exactly 768 x 44,100. The clock was chosen so the CPU and the CD audio sample rate divide evenly.
- **2 MB of main RAM** holds your code, data and stack. The first 64 KB belongs to the BIOS kernel, which is why programs in this book start at address `0x80010000`.
- **1 MB of VRAM** holds the screen. A 320x240 picture at 16 bits per pixel uses 150 KB, so there is room for two frame buffers (Chapter 19) and plenty of textures.

### 5.2 How the CPU talks to the other chips

The CPU has no special instructions for graphics or sound. It talks to every other chip by reading and writing **memory-mapped I/O registers**. These are addresses that look like ordinary memory but are wired to a chip instead of to RAM. All of them sit in one small block starting at `0x1F801000`.

So "sending the GPU a command" means storing a 32-bit word at the GPU's address. There is nothing more to it. The two addresses you need in this chapter are:

| Port | Address | A write sends | A read returns |
|---|---|---|---|
| **GP0** | `0x1F801810` | Drawing commands and VRAM data | Data read back from VRAM |
| **GP1** | `0x1F801814` | Display control and reset commands | `GPUSTAT`, the GPU status |

The top byte of each word you write is the command number. The psx-spx reference (see Further reading) writes them as `GP1(08h)`, `GP0(02h)`, and so on; this book uses the same notation. Chapter 2 maps the whole address space.

### 5.3 Cross-development: from text to a running program

Your PC has an x86-64 (or ARM) processor. It cannot execute MIPS instructions, and the PlayStation cannot run a text editor. So you work in two places:

- The **host** is your PC. You write and build the program there.
- The **target** is the PlayStation, or an emulator of it. The program runs there.

Here is the pipeline for every assembly chapter in Parts I to III:

```
 host (your PC)                                             target
 +-----------+   make    +--------------+   load + run  +-------------------+
 | main.s    | --------> | build/       | ------------> | PCSX-Redux        |
 | color.txt |  (armips) | main.ps-exe  |               | (an emulated PS1) |
 +-----------+           | main.sym     |               +-------------------+
                         +--------------+                   ^
                                                            | verify.sh drives the
                                                            | same emulator headless
```

There are three pieces, and each has one job.

**armips, the assembler.** You write the program as **assembly language**: text, one CPU instruction per line, such as `sw $t2, 0($t1)` ("store the word in register t2 at the address in t1"). An **assembler** translates that text into machine code, the 32-bit numbers the R3000A executes. armips is a free assembler for MIPS consoles. It also understands **directives**, lines that are instructions to the assembler rather than to the CPU. The starter uses six:

| Directive | Meaning |
|---|---|
| `.psx` | Assemble for the PlayStation's R3000A. |
| `.create "main.ps-exe", 0x8000F800` | Start writing an output file. Byte 0 of the file stands for address `0x8000F800`. |
| `.include "common/psxexe.inc"` | Paste in another source file: the book's 2 KB executable header. |
| `.org 0x80010000` | Put the code that follows at this address. |
| `.align 0x800` | Pad with zeros up to the next multiple of 2,048 bytes. |
| `.close` | Finish the file. |

**The PSX-EXE, the executable file.** An emulator, or a real console booting from a disc, needs more than raw machine code. It needs to know where in RAM to put the code and where to start running it. The **PSX-EXE** format answers that with a 2,048-byte header in front of the code. The header begins with the text `PS-X EXE` and holds, among other things, the start address (the `main` label), the load address (`0x80010000`), the code size, and the initial stack pointer (`0x801FFFF0`, near the top of RAM). That is why `.create` uses `0x8000F800`: it is the load address minus the 2 KB header. armips does not write this header itself; `common/psxexe.inc` does. You will write your own in Chapter 5.

Your first build is exactly 4,096 bytes: 2 KB of header, then your few instructions padded to 2 KB. armips also writes `main.sym`, a list of every label and its address. The verifier uses it to find `done`.

**PCSX-Redux, the emulator.** An **emulator** is a program that imitates the console's hardware in software. When you start Redux with `-exe build/main.ps-exe`, it boots its BIOS (OpenBIOS, unless you supply a real one), waits until the BIOS is ready, then does what a disc boot would do: it copies the code to `0x80010000`, sets the stack pointer from the header, and jumps to `main`. This is called **side-loading**. In Part VI you will boot from a real CD image instead.

Redux is the book's main emulator because it has a debugger, a VRAM viewer and a Lua scripting interface. The verifier uses Lua to run your program with no window, stop at `done`, and take a screenshot.

**The Makefile.** armips looks for `.include` files relative to the directory it runs in. The provided `Makefile` therefore copies your sources and the book's `common/` folder into `build/stage/`, runs armips there, and copies the results to `build/`. You never edit `build/`; it is rebuilt every time.

### 5.4 The toolchain

| Tool | Role | First used |
|---|---|---|
| **armips** | Assembler for Parts I to III | This chapter |
| **mipsel-none-elf-gcc** | C compiler and binutils for little-endian MIPS | Part IV |
| **PSn00bSDK** | Open-source PS1 SDK: C libraries for the GPU, GTE, CD and SPU, plus CMake files | Part IV |
| **PCSX-Redux** | Emulator and debugger | This chapter |
| **mkpsxiso** | Builds CD images (`.bin`/`.cue`) | Part VI |
| **Python 3.10+** | Asset tools and the verifier | Always |
| **cmake, make, ninja** | Build drivers | `make` now, the others in Part IV |

Exact versions are pinned in `tools/versions.txt`, so your results match the book's.

### 5.5 Installing the workbench

You need a 64-bit x86 Linux machine (macOS and Windows with WSL also work), about 1 GB of free disk, and a few host packages. armips is compiled from source, so you need a C++ compiler. On Debian or Ubuntu:

```sh
sudo apt install build-essential cmake git curl python3 python3-venv
```

Then, from the repository root:

1. **Run `tools/setup.sh`.** It downloads and installs everything into `.toolchain/` inside the repository. It needs no root access and touches nothing outside the repository. It builds armips, unpacks PSn00bSDK (which includes the GCC cross-compiler and `ninja`), mkpsxiso and PCSX-Redux, and creates a Python virtual environment. The first run takes a few minutes, mostly compiling armips. You can run it again at any time; it skips what is already installed (`--force` reinstalls).
2. **Run `source tools/env.sh`** in each new shell. It puts `.toolchain/bin` on your `PATH` and sets `PS1BOOK_ROOT`, which lets a copy of a starter project find the book. If you use fish or another non-POSIX shell, run `bash` first.
3. **Run `tools/doctor.sh`.** It prints one line per tool:

   ```
     OK       armips         armips assembler v0.11.0 ...
     OK       pcsx-redux     build dd3497b5
     WARN     xvfb-run       (optional) not found; ...
   doctor: all required tools OK
   ```

   `OK` is good. `WARN` means an optional tool is missing or a version differs from the pin; the book will still work. `MISSING` means a required tool is absent, and the script exits with status 1. Each `MISSING` line says what to do, usually "run tools/setup.sh".

If you prefer containers, `tools/Dockerfile` builds the same environment; the top-level README has the two commands.

No PlayStation BIOS is needed. A retail BIOS is copyrighted Sony code, and Redux's OpenBIOS runs everything in this book. If you own a console and dump its BIOS, you can point the verifier at it with `PS1BOOK_BIOS=/path/to/bios.bin`.

### 5.6 Putting a color on the screen

The starter program does two things. First it sets up the display with GP1 commands. Then it draws with one GP0 command.

**Display setup (GP1).** After a reset the GPU shows nothing. Six commands make a picture:

| Command | Word | Effect |
|---|---|---|
| `GP1(00h)` | `0x00000000` | Reset the GPU. |
| `GP1(03h)` | `0x03000000` | Turn the display on (bit 0 = 0 means "on"). |
| `GP1(08h)` | `0x08000001` | Display mode: 320 pixels wide, 240 lines, NTSC, 15-bit color. |
| `GP1(05h)` | `0x05000000` | Show VRAM starting at (0, 0). |
| `GP1(06h)` | `0x06C60260` | Horizontal display range: where the picture starts and ends on each TV line. |
| `GP1(07h)` | `0x07040010` | Vertical display range: TV lines 16 to 256, which is 240 lines. |

You do not need every bit yet. The GPU always shows *some rectangle of VRAM*; these commands say which one and how to send it to the TV.

**Drawing (GP0).** The *Fill Rectangle* command, `GP0(02h)`, paints a rectangle of VRAM with one color. It takes three words:

| Word | Value | Meaning |
|---|---|---|
| 1 | `0x02BBGGRR` | Command `02h`, then blue, green and red, one byte each |
| 2 | `y << 16 \| x` | Top-left corner in VRAM |
| 3 | `h << 16 \| w` | Width and height |

Note the byte order: **blue is in the higher byte and red in the lowest.** Many GPU commands pack color this way. The starter builds the word from three constants, so you only edit `RED`, `GREEN` and `BLUE`.

Fill Rectangle is the simplest drawing command. It ignores the drawing-area clip, and it works in steps of 16 pixels horizontally (psx-spx gives the exact rounding). 320 is a multiple of 16, so a full-screen fill is exact.

**Why the color comes back slightly different.** VRAM stores each pixel as 16 bits: 5 bits each for red, green and blue, plus one mask bit. Your 8-bit value loses its lowest 3 bits when it is stored, and the screenshot expands it back to 8 bits. So `0x80` comes back as `0x84`, and `0x20` as `0x21`. That is why the verifier allows a small tolerance.

## 6. Worked example

Open `starter/main.s` in an editor. It is the complete "hello, VRAM" program, about 30 instructions, and every line is commented. Do not worry about `li`, `sw` or `j` yet; Chapters 3 and 4 explain them. For now, read it for its shape:

```
header include  ->  main: GP1 setup x6  ->  GP0 fill x3  ->  done: loop forever
```

The `done:` label is a loop that jumps to itself forever. A PS1 program has no operating system to return to, so real games loop forever too. The verifier uses `done` as the place to stop the emulator and look at the screen.

Build and run it:

```sh
source tools/env.sh
cd parts/part-01-machine-and-language/ch01-workbench/starter
make           # assemble: produces build/main.ps-exe and build/main.sym
make run       # starts PCSX-Redux with -exe build/main.ps-exe -run -fastboot
```

`-run` starts emulation immediately, and `-fastboot` skips the BIOS start-up animation. A window opens with a solid dark-blue screen (`#204080`).

Now take a short tour of Redux. The menu names below are from the pinned build (`dd3497b5`):

1. **Emulation > Pause emulation.** The CPU stops; **Emulation > Start emulation** resumes it.
2. **Debug > CPU > Show Registers.** The 32 general-purpose registers. After `main` has run, `t0` holds `1F801810` and `t1` holds `1F801814`, the two GPU ports.
3. **Debug > CPU > Show Assembly.** The machine code in memory, disassembled. Scroll to `80010000` to find your program; the current instruction is the jump at `done`. Note that `li` has become a `lui` + `addiu` pair: some assembly "instructions" are shorthand that armips expands (Chapter 3). Stepping and breakpoints need the debugger, which you turn on with the **Enable Debugger** box in this window or under **Configuration > Emulation**; they also need the dynarec turned off (Chapter 6 explains). You will use them in Chapter 6.
4. **Debug > GPU > VRAM viewers > Show main VRAM viewer.** All of VRAM, 1024x512. Your fill is the 320x240 rectangle in the top-left corner. Everything else is VRAM you have not touched yet.
5. **Debug > Show Logs.** Messages from the emulator and the BIOS. Look here first when something goes wrong.

Close Redux when you are done. You can also check the file you built:

```sh
xxd build/main.ps-exe | head -2
```

The first line starts with `PS-X EXE`. At offset `0x10` you will see `0000 0180`: that is `0x80010000`, the address of `main`, stored with the low byte first. Chapter 2 explains this byte order.

## 7. Project

Make the screen your own color, and record which color you chose.

**Requirements**

1. Run `tools/doctor.sh` and fix anything it marks `MISSING`.
2. In `starter/main.s`, change the `RED`, `GREEN` and `BLUE` constants to a color of your choice. It must be clearly different from the default `204080`: at least one channel must change by `0x18` (24) or more.
3. Rebuild, run it, and confirm that the window shows your color.
4. Write the same color into `starter/color.txt` as six hex digits, `RRGGBB` (for example `E05010`), with nothing else in the file.

**Constraints**

- Keep the GP1 setup, the `main:` and `done:` labels, and the `.include` of `common/psxexe.inc`.
- The fill must still cover the whole 320x240 screen.

**Hints**

- A color picker gives you `#RRGGBB`. Split it into three bytes and write each as `0x..`.
- `main.s` lists the constants as red, green, blue. The GPU word packs them as blue, green, red; the expression in the `li` line does that for you.
- After editing, run `make` before `make run`, or just `make run`, which rebuilds first.

**Stretch goals** (do these in a copy, because the verifier expects the full-screen version)

- Make the fill cover only the top half of the screen. What color is the rest, and why? Compare with the VRAM viewer.
- Fill the left and right halves with two different colors using two fill commands.
- Display a different part of VRAM: fill a rectangle at x = 320 and change `GP1(05h)` to show it.
- Switch to 640x480. Look up `GP1(08h)` in psx-spx ("GPU Display Control Commands"): you need the 640 width, the 480-line and interlace bits, and a bigger fill.

## 8. Verification

From the repository root:

```sh
parts/part-01-machine-and-language/ch01-workbench/verify/verify.sh
```

This checks `starter/`, where you work. Pass a path to check a copy elsewhere. Add `-v` to see the build output and the emulator log, and `--keep` to keep the screenshots. The script builds your project, runs it in PCSX-Redux with no window, stops at `done`, takes a screenshot, and runs these checks:

| Check | What it means | If it fails |
|---|---|---|
| `toolchain passes tools/doctor.sh` | Every required tool is installed. | The message lists the `MISSING` tools. Run `tools/setup.sh`. |
| `program is a valid PSX-EXE with main and done` | The header is sound and your labels exist. | "program lacks symbol `done`": you deleted or renamed a label. Restore it. |
| `color.txt holds a colour that is not the starter default` | You recorded a color that is clearly not `204080`. | "expected six hex digits, actual 'TODO'": edit `color.txt`. "some channel at least 24 away": pick a more different color. |
| `program reaches done without hanging` | The CPU got to the end. | A timeout means a crash or an endless loop before `done`. Run with `-v`. |
| `screen is one flat colour covering the whole display` | The fill covers the whole picture. | A small screen means the display setup changed; a partly filled one means the fill size changed. |
| `screen colour matches color.txt` | The GPU shows your color, not the default, and it matches `color.txt`. | The failure prints the pixel it saw. "NOT ~ (32,64,128)" means `main.s` still has the default. Otherwise you edited one file and not the other. |

A failed build prints `FAILED (build error)` with armips' message and line number. Typical causes are a typo in a constant or a broken `.include` path; build with the provided `Makefile`.

A passing run ends with `CHAPTER 01: PASSED (6/6 checks)` and exit status 0.

## 9. Common pitfalls

- **`armips: command not found` or `pcsx-redux: command not found`.** You opened a new shell. Run `source tools/env.sh` again.
- **`make` fails in a copied project.** The `Makefile` finds the book's `common/` folder by searching upward for `Summary.md`, or through `PS1BOOK_ROOT`. Outside the repository, source `tools/env.sh` first.
- **Black screen.** The display enable `GP1(03h)` or the display range commands are missing. Without them the GPU sends no picture.
- **Red and blue swapped.** The GP0 word is `BBGGRR`, not `RRGGBB`. This only happens if you build the word by hand.
- **`color.txt` rejected.** Write exactly six hex digits, such as `3CB371`. `0x3CB371`, three-digit shorthand, and color names are not accepted.
- **Color changed in one place only.** Update both `main.s` and `color.txt`.
- **Running an old build.** You edited `main.s` but ran an old executable. `make run` rebuilds; the verifier always rebuilds.
- **Edited files under `build/`.** They are overwritten on every build. Edit only the sources.
- **The Redux window does not open, or is blank.** The GUI needs OpenGL 3 graphics drivers; `doctor.sh` reports a failed `-version` as a hint. The verifier does not need a window and still works.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- psx-spx (nocash PlayStation specifications): "Memory Map", "GPU Display Control Commands (GP1)" and "GPU Rendering Commands" (Fill Rectangle). <https://psx-spx.consoledev.net/>
- PCSX-Redux documentation, including the debugger and the Lua API: <https://pcsx-redux.consoledev.net/>
- armips readme (directives such as `.create`, `.org` and `.definelabel`): <https://github.com/Kingcom/armips>
- PSn00bSDK, which you will use from Part IV: <https://github.com/Lameguy64/PSn00bSDK>
