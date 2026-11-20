# Part I: The Machine and Its Language

**Theme.** What a PlayStation is, how its R3000A CPU sees memory, and how to write, assemble, run and debug your first MIPS assembly programs.

**Part outcome.** You can write small assembly programs, package them as PSX-EXE files, and inspect their behavior in a debugger.

## Chapters

| # | Chapter | You build |
|---|---|---|
| 1 | The PlayStation and Your Workbench | A working toolchain and a "hello, VRAM" screen fill in your own color |
| 2 | Memory, the Memory Map, and Endianness | "Memory Cartographer": bytes, halfwords and words written to exact addresses |
| 3 | Registers, Loads, Stores, and Arithmetic | "Register Calculator" |
| 4 | Control Flow: Branches and Jumps | "Loop Lab": sums, min/max, array fills |
| 5 | Anatomy of an Executable: The PSX-EXE Format | "Anatomy Lab": `exeinfo.py` and a hand-written EXE header |
| 6 | Emulation and Debugging | "Bug Hunt": locate three bugs with the debugger, fix them, and write a Lua trace script |

## How the part flows

```
tools work  ->  memory  ->  registers  ->  decisions  ->  file format  ->  debugging
  (Ch 1)       (Ch 2)      (Ch 3)         (Ch 4)          (Ch 5)          (Ch 6)
```

Chapter 1 gets every tool running. Chapters 2 to 4 teach the language itself, one idea at a time. Chapter 5 opens the black box you used in Chapter 1 (the PSX-EXE header). Chapter 6 gives you the debugger you will use for the rest of the book.

## Before you start

Follow the setup steps in the [top-level README](../../README.md): run `tools/setup.sh`, then `tools/doctor.sh`. Chapter 1 walks you through the result.

## Capstone for the part

There is no separate capstone. Part I ends with Chapter 6, where you find bugs in programs you could now write yourself.
