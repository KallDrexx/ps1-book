# Chapter 6: Emulation and Debugging

## 1. Concept

An emulator is a debugger with x-ray vision: because it *is* the machine, it can stop it at any instruction and show you every register and byte of memory.

## 2. Why it matters

From here on, "it doesn't work" is a question you answer with a breakpoint, not with guessing. This chapter also closes Part I: you look closely at the pseudo-instructions the assembler has been expanding since Chapter 1, and at the register (`$at`) it uses to do so.

## 3. Learning objectives

After this chapter you can:

- explain how an interpreter and a dynamic recompiler (dynarec) differ, and what accuracy costs;
- say what PCSX-Redux, DuckStation and Mednafen are each good for;
- use exec, read and write breakpoints, single-step, and the register and memory views to find a bug;
- predict what armips turns `li`, `la`, `move`, `b`, `blt`/`bge` and `lw`/`sw reg, label` into, and read the real instructions in the disassembly;
- explain why `$at` is not yours to keep values in;
- write a Lua script that runs inside PCSX-Redux and prints a register on every breakpoint hit.

## 4. Prerequisites

[Chapter 1](../ch01-workbench/README.md) (running Redux, the debugger menus), [Chapter 3](../ch03-registers-loads-stores-arithmetic/README.md) (registers, `lui`/`addiu`) and [Chapter 4](../ch04-control-flow-branches-and-jumps/README.md) (branches, delay slots). Chapter 5's `exeinfo.py` is useful for reading raw words but not required.

## 5. Explanation

### 5.1 How an emulator runs your code

An emulator keeps the console's state (32 registers, PC, 2 MB of RAM, the GPU's VRAM...) in host memory and advances it. For the CPU there are two designs:

| | Interpreter | Dynamic recompiler (dynarec) |
|---|---|---|
| Method | Fetch one MIPS instruction, decode it, do what it says, repeat. | Translate a *block* of MIPS into host machine code once, cache it, then run the cached code. |
| Speed | Slowest; fine for a 33.8688 MHz CPU on a modern PC. | Several times faster. |
| Hooks | Easy: check for a breakpoint before every instruction. | Hard: a translated block runs as a whole, with no check between its instructions. |
| Timing | Easy to count cycles exactly. | Usually approximated. |

PCSX-Redux has both, and the dynarec is its default. Its debugger needs the interpreter: in the pinned build an exec breakpoint never fires while the dynarec runs. Either start Redux with `-interpreter`, as the verifier and `make run1` do, or untick **Dynarec CPU** in **Configuration > Emulation** and restart the emulator. Redux warns "Debugger and dynarec enabled at the same time" if you forget. The interpreter is fast enough for every program in this book.

**Accuracy** is the other axis. The more of the real hardware an emulator models (instruction timing, DMA and bus timing, how the GPU rasterises), the more programs behave as on a console, and the slower it runs. Programs that only compute (Part I) behave the same everywhere. Programs that depend on hardware timing may not, so test those on more than one emulator.

### 5.2 Three emulators

| | PCSX-Redux | DuckStation | Mednafen |
|---|---|---|---|
| Installed here | Yes (the pinned build) | No | No |
| Needs a PS1 BIOS | No (built-in OpenBIOS) | Yes (your own dump) | Yes (your own dump) |
| Strength | Developer tool: debugger, Lua, GPU logger, headless mode. This is what `verify.sh` drives. | Player-friendly, fast and accurate. Has a debugger too. | Accuracy-first; a common reference for hardware behavior. Its PS1 core is also the libretro core Beetle PSX. |
| Use it for | Everything in this book. | Seeing how your program looks and runs for a typical user (Part III onward). | A strict second opinion. |

Only PCSX-Redux was used to test this book. For the other two, check their own documentation for the BIOS setup and how to boot a bare PSX-EXE.

### 5.3 The PCSX-Redux debugger

Turn it on first: start Redux with `-interpreter -debugger` (`make run1` does), or tick **Enable Debugger** in the Assembly window with the dynarec off (5.1). Names below are from the pinned build (`dd3497b5`).

| Where | What |
|---|---|
| **Debug > CPU > Show Registers** | The 32 registers, `hi`/`lo` and `pc`. |
| **Debug > CPU > Show Assembly** | Disassembly around the PC. Right-click an instruction for *Run to Cursor* and *Toggle Breakpoint*. Buttons or keys for *Resume*, *Step In*, *Step Over*, *Step Out*. |
| **Debug > CPU > Show Breakpoints** | List, add, enable and delete breakpoints. |
| **Debug > CPU > Memory Editors > Memory Editor #1** | Hex view of RAM with a go-to-address box. The same submenu has editors for the scratchpad, hardware registers and SPU RAM. |
| **Debug > Show Lua Console** | Lua output, and a prompt to type Lua into. It sits next to **Show Logs**. |
| **Emulation > Pause emulation** / **Start emulation** | Stop and resume the whole machine. |

There are three kinds of breakpoint:

| Kind | Stops when... | Use it to answer |
|---|---|---|
| **Exec** | the CPU is about to run that address | "Does this code run? How often? With which register values?" |
| **Read** | a load touches that address | "Who reads this variable?" |
| **Write** | a store touches that address | "Who corrupts this variable?" |

Add them from the Breakpoints window, or *Toggle Breakpoint* in the Assembly window for exec. A **single step** executes one instruction and stops, so you can watch registers change.

A workflow:

1. **Observe** the wrong result (Registers at `done`, `results` in a memory editor).
2. **Narrow**: the result is a chain of steps; find the *first* one that is wrong. A breakpoint halfway splits the chain.
3. **Look at the real instructions**, not your source. In the Assembly window, switch off the display option *Combined pseudo-instructions* if you want to see exactly what was assembled.
4. **Change one thing** and re-test.

A breakpoint on `done` hits again on every pass of the `j done` loop. In a script, make it a one-shot or pause at the first hit (section 5.6).

### 5.4 Pseudo-instructions: what armips really emits

The R3000 has no `li`, `la`, `move` or `blt`. They are **pseudo-instructions**: assembler conveniences that expand into one or two real instructions. This is what the pinned armips emits (checked by disassembling its output):

| You write | Becomes | Words |
|---|---|---|
| `nop` | `sll $zero, $zero, 0` (the word `0`) | 1 |
| `move $a, $b` | `addu $a, $b, $zero` | 1 |
| `li $t, 100` (0 to 0xFFFF) | `ori $t, $zero, 100` | 1 |
| `li $t, -1` (-32768 to -1) | `addiu $t, $zero, -1` | 1 |
| `li $t, 0x12340000` (bottom half zero) | `lui $t, 0x1234` | 1 |
| `li $t, 0x12345678` (anything else) | `lui` of the top half, then `addiu` of the bottom half | 2 |
| `la $t, label` | the same as `li` with the label's address: normally `lui` + `addiu` | 2 |
| `b label` | `beq $zero, $zero, label` | 1 |
| `beqz $a, label` / `bnez $a, label` | `beq` / `bne $a, $zero, label` | 1 |
| `blt $a, $b, L` | `slt $at, $a, $b` then `bne $at, $zero, L` | 2 |
| `bge $a, $b, L` | `slt $at, $a, $b` then `beq $at, $zero, L` | 2 |
| `bgt` / `ble` | the same with `$a` and `$b` swapped | 2 |
| `bge $a, 10, L` | `slti $at, $a, 10` then `beq $at, $zero, L` | 2 |
| `lw $t, label` | `lui $t, hi` then `lw $t, lo($t)` | 2 |
| `sw $t, label` | `lui $at, hi` then `sw $t, lo($at)` | 2 |

Two things to notice:

- A 32-bit `li` or `la` uses `addiu`, which **sign-extends** its 16-bit immediate. When the bottom half is 0x8000 or more, the `addiu` subtracts, so the assembler adds one to the `lui` half to compensate. The `lui` in the disassembly is therefore not always the top half you wrote.
- Several rows are **two** instructions. Anything that assumes "one line of source = one instruction" is wrong: instruction counts, hand-computed offsets, and *the delay slot*. A branch is followed by exactly one instruction that always executes. If you write a two-word pseudo-instruction there, the first word lands in the slot and the second comes *after* it, so it runs only when the branch is not taken.

armips accepts `bne` followed by `li $t6, 0x12345678` without complaint. It does not accept every pseudo-instruction you may know from other assemblers: `mul $d, $a, $b` is rejected (Chapter 12).

### 5.5 `$at`, the assembler temporary

Register 1 is `$at` ("assembler temporary"). The assembler uses it as scratch when one source line needs two real instructions and a middle value, as in `blt` and `sw reg, label` above. By convention **you do not keep values in it**. armips does not stop or warn you: the program assembles cleanly, and the register is overwritten by the next pseudo-instruction that needs it.

Rule: if you see `$at` in your own source, something is wrong. Use `$t0`-`$t9` and `$s0`-`$s7` (Chapter 3). If a register "changes by itself", look at the *disassembly*, not the source: the culprit may be a pseudo-instruction that wrote `$at`.

### 5.6 A first Lua script

PCSX-Redux embeds LuaJIT (Lua 5.1 semantics). A script can place breakpoints and run a function of yours whenever one hits. The pieces you need:

| Call | Meaning |
|---|---|
| `PCSX.addBreakpoint(addr, 'Exec', 4, 'name', fn)` | Exec breakpoint on one instruction (width 4). `'Read'` / `'Write'` also exist (width = bytes watched). `fn` runs at each hit, *before* the instruction executes. |
| return `false` from `fn` | Remove the breakpoint after this hit (a one-shot). |
| `PCSX.getRegisters().GPR.n.t0` | Register `t0` as a number; also `.at`, `.v0`, `.sp`... `.pc` is on `getRegisters()` itself. |
| `PCSX.pauseEmulator()` | Pause, like the menu item. |
| `print(...)`, `string.format(...)` | Output goes to the Lua console (and to stdout in headless mode). |

**Keep the value `addBreakpoint` returns in a global**, otherwise Lua's garbage collector eventually deletes the breakpoint. Print registers with `%08x`.

Run a script by starting Redux with `-dofile script.lua`, or paste it into the Lua console. Every script in this chapter sets breakpoints, so always add `-interpreter -debugger`.

## 6. Worked example

Save this script as `starter/symptom.lua`. It reports the result of `bug1` when it reaches `done`. `0x80010048` is the address of `done` in `build/bug1.sym`, as built from the unedited starter.

```lua
local DONE = 0x80010048

doneBP = PCSX.addBreakpoint(DONE, 'Exec', 4, 'bug1 finished', function()
    local gpr = PCSX.getRegisters().GPR.n
    print(string.format('sum=0x%08x words=%d', gpr.t3, gpr.t5))
    PCSX.pauseEmulator()
    return false
end)
```

Build, then run it from `starter/`:

```sh
make
pcsx-redux -exe build/bug1.ps-exe -run -fastboot -interpreter -debugger -dofile symptom.lua
```

The Lua console prints `sum=0x0bad0264 words=9` and the emulator pauses. The program is supposed to add 8 words; it read 9. That is a *symptom*; finding the instruction responsible is your job. The script uses everything from section 5.6: an address from the `.sym` file, a breakpoint callback, register access and the one-shot `return false`.

## 7. Project: "Bug Hunt"

`starter/` holds three small programs that each assemble and run to `done` but compute the wrong answer, plus `Makefile` (`make` builds all three; `make run1`, `run2`, `run3` open one in Redux), `findings.txt` and an empty `trace.lua`. Each program's header comment says what it should do.

| Program | Should compute | Kind of bug |
|---|---|---|
| `bug1.s` | sum of `count` words | a loop that is off by one |
| `bug2.s` | sum of `word XOR key` | a wrong assumption about a pseudo-instruction |
| `bug3.s` | saturating sum of `count` words | a register that was not yours |

**Do not edit anything until you have done steps 1 to 3 for all three**; the addresses you record are those of the original build. (Copy `starter/` aside, or use `git` to get it back.)

1. **Reproduce.** Run each program in Redux and look at the result at `done`. Compare with what the comment promises.
2. **Locate.** Use only the debugger (breakpoints, steps, registers, disassembly) to find the one faulty instruction in each program. Definitions:
   - `bug1`: the branch whose decision makes the loop run once too often.
   - `bug2`: the first word of the pseudo-instruction that does not do what its author assumed.
   - `bug3`: the first word of the pseudo-instruction that destroys a value the program still needs.
3. **Record.** Fill in `findings.txt`, one line each, 8-digit hex, in the form `bug1: 0x8001ABCD`. Anything after the address on a line is ignored, so you can add a note to yourself.
4. **Trace.** Write `trace.lua`, to be run against the **original** `bug3`:
   - Put an exec breakpoint on your `bug3` address.
   - At every hit print one line `at=0x........` with the current value of `$at` (8 hex digits).
   - Keep the breakpoint in a global, and print no other lines of the form `at=...`.
   - Read the live register: the verifier patches different data into the program.

   Run it with the original program (`build/bug3.ps-exe` before you fix anything) as in section 6, with `-dofile trace.lua`. Notice what the sequence of `$at` values tells you.
5. **Fix** each program with the smallest change that makes it right for *all* inputs. Keep every label the starter declares and do not change the data. For `bug3`, the fix is about where the running total lives.

Requirements and constraints:

- The programs must work for any `count` from 1 to 8 (`bug1`, `bug3`) and any six words (`bug2`).
- No hard-coded answers; the verifier patches the inputs.
- `findings.txt` and `trace.lua` describe the *original* programs, so never "update" them to match your fixes.

**Hints** (read one at a time)

- *bug1.* Put a read breakpoint on `guard`. Where is the pointer in `$t1`, and what is `$t0`, when the loop finally stops? Check the branch against the case `$t0 == 0`.
- *bug2.* Set a breakpoint on the `bne`'s target and look at `$t6` on the second pass. Then read the words of the `li` in the Assembly window, and ask which of them ran.
- *bug3.* Single-step the `bge` and watch `at`. Turn *Combined pseudo-instructions* off to see why.

**Stretch goals**

- Make `trace.lua` also print the loop counter `$t0`, and the sample being added (`$t4`).
- Add a Write breakpoint on `results` in Lua and print the PC of whoever stores there.
- Run your fixed `.ps-exe` files in another emulator if you have one, and compare `results`.

## 8. Verification

```sh
parts/part-01-machine-and-language/ch06-emulation-and-debugging/verify/verify.sh
```

Checks `starter/` by default; pass a path for a copy, `-v` for logs, `--solution` for the reference. Expect about 15 seconds.

| Check | What it means | If it fails |
|---|---|---|
| `the three programs, findings.txt and trace.lua exist` | Files present. | Missing file. |
| `each program keeps the labels...` | `main`, `done`, `results` and data labels exist. | Renamed or deleted. |
| `bug1 adds exactly count words` | Three runs with random data and counts; sum and word count must match. | Words read is not `count`, or the sum includes `guard`. |
| `bug2 sums (word XOR key)...` | Three runs with random words (including 0 and `0xFFFFFFFF`). | Some words were combined with a wrong key. |
| `bug3 reports the right total...` | Never saturating, saturating mid-way, saturating on word 1. | The running total is being destroyed. |
| `findings.txt: bugN names the faulty instruction` | The address is compared with the one in the *original* program, assembled by the verifier. Your edits cannot move it. The verifier never prints the right address. | Wrong instruction, wrong definition (section 7 step 2), or an address from your already-edited build. |
| `trace.lua loads and runs...` | Redux loads it without a Lua error. | Syntax error or a bad API call; run it yourself and read the Lua console. |
| `trace.lua prints at=0x........` | The verifier runs your script against the original `bug3` with fresh random inputs and compares your lines with `$at` as recorded independently at every hit. | Wrong address, missing hits (breakpoint garbage-collected?), wrong register, constant output. |

A pass ends with `CHAPTER 06: PASSED (10/10 checks)`.

## 9. Common pitfalls

- **Debugger off, or dynarec on.** Without `-debugger` (or the checkbox), or with the dynarec running, breakpoints silently do nothing. Use `-interpreter -debugger`.
- **Breakpoint timing.** An exec breakpoint stops *before* the instruction runs, so registers show the state *before* it. A read breakpoint's Lua callback likewise sees the PC of the load and the destination register still holding its old value. In the GUI, check where the PC marker sits before you decide which instruction is the culprit.
- **Breakpoint object collected.** A script that does not store `addBreakpoint`'s result in a global may work for a while and then stop printing.
- **Debugging the source, not the program.** One line of source can be two instructions. Trust the disassembly.
- **Instruction in a delay slot.** A multi-word pseudo-instruction after a branch is split by it (section 5.4).
- **`$at` in your own code.** Assembles cleanly, fails sometimes (section 5.5).
- **A plain breakpoint on `done`.** It loops forever, so the breakpoint hits again each time you resume.
- **Fixing before recording.** Insert one instruction and every later address moves.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- PCSX-Redux documentation: debugger and Lua API: <https://pcsx-redux.consoledev.net/>
- psx-spx, "CPU Specifications" (register names, `$at`): <https://psx-spx.consoledev.net/>
- armips documentation, the "MIPS" section on pseudo-instructions: <https://github.com/Kingcom/armips>
- The DuckStation and Mednafen documentation pages for their debugging features and BIOS setup.
