# verify-lib: the chapter verification harness

Every chapter's `verify/verify.sh` is a thin wrapper around `harness.py`.
This document is for **chapter authors**: how to write `verify/checks.py` (and
optionally `verify/probe.lua`), plus what we learned about running PCSX-Redux
headless.

```
build  ->  static checks  ->  run PCSX-Redux headless (+ probe)  ->  results.json
       ->  named checks (PASS/FAIL, expected / actual / hint)  ->  CHAPTER NN: PASSED (k/k checks)
```

Exit codes: `0` all checks passed; `1` build failed or a check failed (this
includes the 20 s emulator hard timeout); `2` tooling problem (tool missing,
`checks.py` crashed, probe Lua error). CI (`tools/ci.sh`) expects `0` for `--solution` and
exactly `1` for the untouched starter, which must still **build** (a starter build
error is reported as `NOBUILD`).

## Files

| File | Role |
|---|---|
| `harness.py` | Entry point + the API chapter authors import (`from harness import *`) |
| `redux.lua` | Loaded into PCSX-Redux; runs the job, defines the `verify` Lua API, writes `results.json` |
| `symbols.py` | `Symbols` (armips `.sym`/`.sym2`, ELF via `nm`), `PsxExe` (header, patching, disassembly) |
| `image.py` | `Image` (PPM screenshots), `Vram`, colour-tolerance assertions, perceptual hashes |
| `failure.py` | `CheckFailure`, `HarnessError` |
| `templates/verify.sh`, `checks.py`, `Makefile.armips` | Copy these into a new chapter |

## New-chapter recipe

```
parts/part-01-x/ch03-y/verify/verify.sh     # cp tools/verify-lib/templates/verify.sh ; chmod +x
parts/part-01-x/ch03-y/verify/checks.py     # cp tools/verify-lib/templates/checks.py ; edit
parts/part-01-x/ch03-y/verify/probe.lua     # optional, auto-detected
parts/part-01-x/ch03-y/{starter,solution}/  # starter has main.s (+ Makefile.armips as Makefile)
```

`./verify.sh` checks `starter/` by default (that is where the reader works);
`./verify.sh --solution` checks `solution/`; `./verify.sh path/to/project` checks any directory.
`-v` shows build output and the emulator log; `--keep` keeps the temp dir
(screenshots as `shot_*.ppm`, `vram.bin`, `results.json`, `emulator.log`).

## `checks.py` API

```python
from harness import *

config(title="...", reads={"results": 64}, shots=["end"], ...)   # once, at top

@static_check("name", hint="...")      # runs after the build, before the emulator
def _(ctx): ...

@check("name", hint="...")             # runs after the emulator session(s)
def _(ctx): ...
```

A check **passes by returning**, and **fails by raising** `CheckFailure`
(usually via an `expect_*` helper). Any other exception is reported as a failed
check with a "bug in checks.py" note. The hint printed is the exception's
`hint=` or, if absent, the decorator's.

### `config(...)` options

| Option | Default | Meaning |
|---|---|---|
| `title` | `""` | Report header |
| `build` | auto | `None` = Makefile -> `make`, CMakeLists -> `cmake`, else `"armips"`; or `"armips"`/`"make"`/`"cmake"`/argv list |
| `main` | `"main.s"` | armips entry file |
| `armips_args` | `()` | e.g. `("-erroronwarning",)` |
| `no_warnings` | `False` | fail the build if tool output contains "warning" |
| `exe` | `"main.ps-exe"` | built PSX-EXE, relative to the build dir (armips: staging dir; make: project dir, or its `build/` as `Makefile.armips` uses; cmake: build dir) |
| `sym` / `elf` | `"main.sym"` / `None` | symbol source. C chapters: `sym="", elf="game.elf"` (uses `mipsel-none-elf-nm`) |
| `iso` | `None` | e.g. `"hoverline.cue"`: boot from disc instead of side-loading `exe` |
| `break_at` | `"done"` | label/address where the run stops and state is captured; `None` = run to `max_frames` |
| `max_frames` | `600` | emulated video frames (60/s) before giving up; CD boots need ~350 frames before `main` |
| `settle_frames` | `2` | frames to keep running after `break_at` before screenshots/VRAM are taken |
| `reads` | `{}` | `{"results": 64}` or `{"tbl": ("symbol_or_addr", 256)}`; snapshotted **at the moment of the break** |
| `shots` | `()` | `"end"` (taken `settle_frames` after break / at the frame limit), an int frame number, or `(name, frame)` |
| `vram` | `False` | dump all of VRAM at the end (`r.vram()`) |
| `inputs` | `()` | `[(frame, "START", hold_frames=6), ...]`; buttons: `UP DOWN LEFT RIGHT CROSS CIRCLE SQUARE TRIANGLE L1 L2 R1 R2 START SELECT L3 R3`. Verified end-to-end in Chapter 22 (see "Pads" below for timing and polarity) |
| `patches` | `{}` | `{"input": 10, "tbl": b"..."}` written into a copy of the `.ps-exe` before the run (int = little-endian u32) |
| `probe` | auto | path to `probe.lua`; default `verify/probe.lua` if present |

### `ctx` (passed to every check)

| Member | |
|---|---|
| `ctx.result` | The default emulator run (a `RunResult`), executed lazily once |
| `ctx.run(name=None, **overrides)` | Another session with any `config` field overridden (`patches=`, `inputs=`, `reads=`, `break_at=`, ...). Cached. ~1-2 s each |
| `ctx.symbols` | `Symbols`: `ctx.symbols["done"]`, `.get`, `.require(...)`, `.size(name)` (sym2/nm only) |
| `ctx.require_symbols("a","b")` | Fails the check listing missing labels |
| `ctx.exe` | `PsxExe`: `.pc .load_addr .text_size .code .problems()` |
| `ctx.disassemble()` | `list[Insn(addr, word, text)]`; `mnemonic(insn)` -> `"addiu"`. Registers appear as `t0`, not `$t0`. Data words show as `.word`/garbage, so restrict with `ctx.disassemble_range("start_label", "end_label")` |
| `ctx.source_text("**/*.s")`, `ctx.source_files()` | Reader's sources (comments stripped by default) for "forbidden construct" checks |
| `ctx.build_log` | Tool output of the build (e.g. check for warnings) |
| `ctx.project`, `ctx.solution` | Paths / mode |

### `RunResult` (`ctx.result`, `ctx.run(...)`)

`r.u32(name, i=0)`, `r.s32`, `r.u16`, `r.u8`, `r.words(name, n=None, signed=False)`, `r.mem(name)` read
the snapshot taken at the break. `r.reg("v0")` / `r.reg("pc")` registers at the break.
`r.record(key)` values the probe stored with `verify.record(key, value)`.
`r.screenshot(name="end")` -> `Image`; `r.vram()` -> `Vram`; `r.frames`, `r.cycles`,
`r.break_hit`, `r.timed_out`, `r.data` (raw JSON).
Every accessor first calls `require_finished()/require_break()`, which fail the check
with a good message ("program never reached `done`", "emulator hit the 20 s timeout",
"probe uses symbol X which your program lacks"). Authors rarely need to handle that.

### Assertions

`expect_eq(actual, expected, what="", hint="", fmt="auto|hex|dec")`, `expect_true(cond, expected, actual, hint)`,
`expect_near(actual, expected, tol)`, `expect_bytes(actual, expected)`, `expect_in(needle, haystack)`.
Helpers: `u32(v)`, `u16(v)`, `words(*vals)` (little-endian bytes).

Images (`image.py`, re-exported by `harness`):

```python
img = ctx.result.screenshot()                   # Image: .width .height .pixel(x,y)->(r,g,b)
expect_pixel(img, 160, 120, (255,0,0), tol=16)  # raises CheckFailure with expected/actual
expect_region(img, x, y, w, h, rgb, tol=16, min_fraction=0.98)
expect_solid(img, rgb)                          # whole screen
expect_pixel_differs(img, x, y, rgb)            # e.g. "background untouched" checks inverse
img.region_mean(x,y,w,h); img.fraction_matching(x,y,w,h,rgb,tol); img.count_not_matching(...)
expect_similar(img, ref_hash, max_distance=6, algo=dhash)   # perceptual hash; ahash/dhash/hamming exported
vram = ctx.result.vram()                        # needs config(vram=True)
vram.raw(x,y)   vram.pixel(x,y)   vram.rect(x,y,w,h)   vram.expect_rect(x,y,w,h, expected_bytes)
bgr555(r,g,b)   rgb_from_bgr555(v)
```

**Tolerances.** The PS1 stores 5 bits per channel; an 8-bit colour comes back quantised
(`0x80` -> `0x84`). Use `tol >= 8` for flat colours and ~`16-24` near Gouraud/edge pixels.
Never compare whole screenshots byte-for-byte.

## `probe.lua` API (global `verify`, LuaJIT)

Loaded after `redux.lua`. Use it when a chapter needs more than "break at `done`, read `results`".

```lua
verify.sym.done                      -- address table of all symbols; verify.resolve("results+4")
verify.u32("results")  verify.u16(addr)  verify.u8(addr)  verify.s32(addr)   -- RAM/scratchpad reads
verify.write_u32("input", 5)         -- also write_u16/write_u8; verify.read_bytes(addr, n)
verify.regs()                        -- {pc=..., v0=..., sp=..., lo=..., hi=...}
verify.on_exec("frame_end", function(regs) ... end)   -- exec breakpoint; return false to remove
verify.on_access("Write", "gem_state", 4, function(addr, width, pc) ... end)  -- "Read"/"Write"
verify.count_instructions("start_lbl", "end_lbl")     -- returns {n=count}; counts executed instrs in [start,end)
verify.cycles()                      -- CPU cycle counter (33.8688 MHz)
verify.on_vsync(function(frame) ... end)  verify.at_frame(n, fn)      -- frame counter starts at 1
verify.press(frame, "CROSS", hold)   verify.button_down("UP")  verify.button_up("UP")
verify.screenshot("name")  verify.dump_vram()  verify.snapshot("name", addr, size)
verify.record("key", value)          -- value: number/string/bool/table -> r.record("key") in Python
verify.finish("status")              -- end early (normally the `break_at` label or max_frames ends the run)
verify.frame, verify.job, verify.libdir   -- libdir: directory of redux.lua, for dofile of shared helpers
```

**Direct subroutine calls.** `local DC = dofile(verify.libdir .. '/directcall.lua')` gives a ready-made
harness for calling the reader's routines with sentinel-seeded callee-saved registers, garbage temporaries,
a return trampoline, an instruction limit and a printed random seed (`DC.seed`, `DC.rnd`, `DC.rnd32`). See
the header of `directcall.lua`, Chapter 8's `probe.lua` (array arguments via `prepare`/`check`) and Chapter 9's. Chapter 10's adds stack tracking: `DC.SP`, per-call `limit`, `o.on_step(c)`, `d.cur`, `d.main_sp`.
A CPU exception (BIOS vector `0x80000080`; OpenBIOS would otherwise halt until the hard timeout) ends the run at once: the faulting call's record gets `exception = {code, epc, badvaddr}`, and seed/calls/entries/`exception` are recorded (or `o.on_exception(info)` is called). `harness.exception_text(exc)` formats it; `require_break` appends it to its message.

Rules of thumb: wrap nothing in `pcall` yourself (the harness does and reports errors); anything that
resolves an unknown symbol is reported as "your program lacks symbol X" (a normal failed check).
`record` a snapshot in `verify.on_exec("done", ...)` rather than after the run if the value changes.
The hard Python-side timeout (20 s wall, `--timeout`) kills the emulator process group.

## What we learned about PCSX-Redux (build `dd3497b5`, Nov 2026)

Exact invocation the harness uses:

```
pcsx-redux -cli -testmode -stdout -lua_stdout -interpreter -debugger -1mbvram \
           -fastboot -run -noupdate -memcard1 <tmp>/mc1.mcd -memcard2 <tmp>/mc2.mcd \
           -exe prog.ps-exe          # or: -iso disc.cue
           -dofile tools/verify-lib/redux.lua          # env PS1BOOK_JOB=<job.lua>
```

* `-cli` = no UI at all; **no X server / xvfb is needed** (xvfb-run also works for the GUI build). Startup ~1 s; a 30-frame run takes ~1 s wall and the emulator is not frame-limited.
* `-testmode` skips loading/saving settings; always pass explicit `-memcard1/2` or it creates files under `~/.config/pcsx-redux`.
* `-interpreter -debugger` are **required** for exec/read/write breakpoints (`PCSX.addBreakpoint`) to fire. Keep the returned object in a global or it is GC'd and removed. Return `false` from the callback for a one-shot.
* No `-bios` needed: Redux falls back to its built-in **OpenBIOS** ("Could not open BIOS ... Retrying with the OpenBIOS"). Set `PS1BOOK_BIOS=/path` to use a retail BIOS.
* `-exe` is side-loaded when the BIOS reaches the shell (`-fastboot` skips the logo). Booting a `.cue` takes ~310 emulated frames before the game's `main`; allow `max_frames >= 600`.
* The AppImage is installed *extracted* (`.toolchain/opt/pcsx-redux/squashfs-root/AppRun`), so FUSE is not needed and startup is fast.
* Lua is **LuaJIT** (Lua 5.1 semantics): no `//`, no integer division, use `bit.band/rshift/...`; `ffi` is a global. Memory: `PCSX.getMemPtr()` (RAM, index by `addr & 0x1FFFFFFF`), `PCSX.getScratchPtr()`, `PCSX.getRegisters().GPR.r[i]` / `.pc`, `PCSX.getCPUCycles()`.
* Events: `PCSX.Events.createEventListener('GPU::Vsync', fn)` fires once per emulated frame (also keep a reference). `PCSX.pauseEmulator()`, `PCSX.quit(code)` (applied after the current Lua block; the exit code propagates).
* Exec breakpoint **width** counts as a range: `PCSX.addBreakpoint(a, 'Exec', b - a, ...)` fires on every instruction in `[a,b)` (this is how `verify.count_instructions` works; verified).
* `PCSX.GPU.takeScreenShot()` -> `{data=Slice, width, height, bpp}`; 16 bpp data is BGR555 (`r = c & 31`, `g = c>>5 & 31`, `b = c>>10 & 31`). Size follows the programmed display range (e.g. 320x240, or 320x239 for the asm default vertical range): do not hard-code it blindly. **24-bpp screenshots (confirmed in Chapter 16):** `data` is `width*height*3` bytes in order **R, G, B** per pixel, row-major, exactly the byte order of the 24-bpp VRAM image (the first byte of VRAM line 0 is the red of pixel 0), so `redux.lua` copies it straight into the PPM and `Image.pixel` returns true (r,g,b). `takeScreenShot().bpp` is non-zero in 24-bpp mode (recorded as `shots[name].bpp`).
* During a GP0 A0h CPU->VRAM transfer GPUSTAT bit 26 reads **0** (bit 28 stays 1) and returns to 1 when the last data word is written (measured in PCSX-Redux): a program that polls bit 26 before each data word hangs. A rectangle that crosses the right edge (x=1020, w=8) is NOT wrapped by Redux: all 8 pixels were written from x=0; x and y are masked to 10/9 bits (x=1030 -> 6).
* `PCSX.GPU.getVRAM()` returns a 2 MB `Slice` laid out with a 1024-pixel row stride (1024 rows). Rows 0-511 are the real VRAM, which is all `Vram` exposes (even with `-1mbvram`).
* **Pads (confirmed in Chapter 22; works headless, `-cli`, no flags, no settings).** `PCSX.SIO0.slots[1].pads[1].setOverride(PCSX.CONSTS.PAD.BUTTON.CROSS)` / `clearOverride(...)` (what `verify.button_down/up/press` and the `inputs=` config use) is seen by a guest reading port 1 through the BIOS driver (`InitPAD`/`StartPAD`, OpenBIOS supports them: its log prints "PS-X Control PAD Driver"). Redux's default pad 1 is a connected **digital pad** (type 4): the BIOS buffer is `[stat=0x00, 0x41, btn_lo, btn_hi]`, all-ones (`FF FF`) when idle. **Active-low on the wire**: a pressed button is a **0** bit, so `UP` gives `btn_lo = 0xEF`, `CROSS` gives `btn_hi = 0xBF`. The bit positions equal PSn00bSDK's `PAD_*` enum (bit 0 SELECT, 1 L3, 2 R3, 3 START, 4 UP, 5 RIGHT, 6 DOWN, 7 LEFT, 8 L2, 9 R2, 10 L1, 11 R1, 12 TRIANGLE, 13 CIRCLE, 14 CROSS, 15 SQUARE), so the harness names map one-to-one (`CROSS` = the X button). **Timing:** `press(f, B, n)` sets the override in the vsync handler of frame `f` and clears it at frame `f+n`; the BIOS driver polls once per VBlank and a program with one `VSync` per loop sees the button for exactly `n` loop iterations, starting at the iteration after frame `f` (a probe sampling guest state in `on_vsync` of frame `f+1` sees the effect; a 1-frame press is seen once). The SDK reaches `main` at ~frame 32 and the first valid pad reading arrives at ~frame 34 (measured), so start scripts at frame >= 50. Before the driver's first poll the buffer keeps its initial contents, **all zero** for a `static` array (both ports; after the first poll port 2, with no pad attached, reads `stat = 0xFF`, rest zero): a reader must check `stat == 0` and the type nibble, because zero bits would read as "every button pressed". Never schedule two presses of the same button so that one ends on the frame the next starts (both actions run in registration order). `inputs=` entries for different buttons may overlap freely.
* **Calling guest functions mid-run** (Chapter 22's probe): at an exec breakpoint on a function that runs every frame (`display_clear`), save `GPR[1..31]`, set `$a0`, `$ra = trampoline`, `$sp -= 256` and `R.pc = fn`; a breakpoint on the trampoline reads `$v0`, then restores the registers and `pc`. Guard the re-entry with the frame number (the restored `pc` re-hits the same breakpoint). Unlike `directcall.lua` this works at any time, so it can ask a running program's state-holding functions (`input_pressed`, ...) what they answer on frame N.
* GPU commands issued by the CPU are processed immediately, so a screenshot taken at the `done` break already shows a fill; `settle_frames` is for programs that finish via DMA/VBlank.
* Other useful flags: `-8mb`, `-pcdrv -pcdrvbase DIR` (host file access from the guest), `-profile/-callgrind`, `-gdb`, `-dynarec`. Docs: https://pcsx-redux.consoledev.net/Lua/introduction/ (note the capital `L`).

## Toolchain facts (armips / PSn00bSDK / nm)

* **armips `.psx` only selects the R3000 instruction set; it emits *no* PSX-EXE header.** The book provides `common/psxexe.inc` (2 KB header; file offset 0 = `0x8000F800`, code at `0x80010000`). Chapter 5 has the reader write that header by hand. Every Part I-III program is: `.psx` / `.create "main.ps-exe", 0x8000F800` / `.include "common/psxexe.inc"` / `.org 0x80010000` / code / `.align 0x800` / `__exe_end:` / `.close`.
* armips resolves `.include` paths relative to the **current working directory**, not the including file. The harness (and `templates/Makefile.armips`) therefore builds in a staging copy of the project with the book's `common/` copied next to it, so chapters write `.include "common/psxexe.inc"`.
* armips `-sym` output contains junk lines (`00000000 0`, `800100AC .dbl:0008`); `Symbols.from_sym` filters them. `-sym2` adds `,size`.
* The armips `v0.11.0` tag does not compile with GCC >= 13 / CMake >= 4; `tools/versions.txt` pins a newer master commit.
* `mipsel-none-elf-nm` prints sign-extended addresses (`ffffffff80010108`); `Symbols.from_elf` masks to 32 bits.
* The PSn00bSDK release zip is self-contained: GCC 12.3.0 (`mipsel-none-elf-*`), `ninja`, `elf2x`, `mkpsxiso 2.03` and `lib/libpsn00b/cmake/sdk.cmake`. The harness's `build="cmake"` configures with `-DCMAKE_TOOLCHAIN_FILE=$PSN00BSDK_LIBS/cmake/sdk.cmake -G Ninja` (Ninja comes from the SDK). The SDK's `template` project builds `template.exe` (PSX-EXE), `template.elf`, and `template.bin/.cue` and runs in Redux (verified, both side-loaded and from the CD image).

## C / PSn00bSDK chapters (learned in Chapter 18, the first to use the `cmake` path)

* Config: `config(build="cmake", exe="game.exe", sym="", elf="game.elf", break_at="stop_here", ...)`. `build` must be explicit: a reader-facing `Makefile` (a thin wrapper around cmake, for `make`/`make run`) would otherwise select the `make` path. The harness configures with `-Wno-dev` (the SDK's `internal_setup.cmake` triggers a harmless GNUInstallDirs warning) and builds out of tree in the temp dir, so a reader's own `build/` is ignored.
* `psn00bsdk_add_executable(game GPREL ...)` produces `game.elf`, `game.exe` (PSX-EXE via `elf2x`, entry = `_start`), `game.map`. Patching symbols (`patches={"clear_rgb888": 0x...}`) works through the ELF symbol table.
* **`break_at` needs a real, out-of-line function.** At `-O2` an empty helper is inlined into its caller and `-gc-sections` then drops the unused out-of-line copy, so its symbol vanishes. Declare it `__attribute__((noinline))` with an `asm volatile("" ::: "memory")` body. The harness reports a missing symbol as "your program lacks symbol X".
* **`-Wl,-gc-sections` removes unreferenced symbols**, including globals nobody reads and `.s` functions nobody calls. A chapter's starter must reference every symbol its checks require (read the variable, even into `(void)`), or the failure message is misleading.
* **SYSCALL is not a fault.** `EnterCriticalSection`/`ExitCriticalSection` (used inside `ResetGraph`, `VSync` ...) execute `syscall`, which enters the BIOS vector `0x80000080` with ExcCode 8. `directcall.lua` ignores code 8 after the direct calls (phase 2; a `syscall` inside a directly called routine is still reported) and code 0 (interrupts) always; before this fix any SDK program that called the SDK after `main` was reported as "CPU exception 8".
* The SDK program reaches `main` after ~30 frames on OpenBIOS (side-loaded); a clear via `DRAWENV.isbg` is visible after `DrawSync(0)`. A 4-run chapter takes ~6 s wall.
* **Overriding a routine's result from the probe** (used to prove C really consumes an assembly return value): set a breakpoint at `$ra` on entry and write `PCSX.getRegisters().GPR.r[2]` there; the breakpoint fires before the instruction at `$ra` executes, so the new `$v0` is what the caller sees. Trigger it by a sentinel in a patched data word.
* Compiling one file to assembly outside CMake: `mipsel-none-elf-gcc -O2 -S -ffreestanding -march=r3000 -msoft-float -fno-pic -mno-abicalls f.c` (`-ffreestanding` is what makes `<stdint.h>` resolve). GCC prints numeric register names (`$2`), `objdump -d` prints names.
