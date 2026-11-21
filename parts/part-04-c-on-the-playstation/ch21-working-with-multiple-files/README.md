# Chapter 21: Working with Multiple Files

## 1. Concept

A C program is built from **translation units** (one `.c` file plus everything it `#include`s). Each is compiled on its own into an object file; the linker joins them. The language gives you three tools to control what the units share: **headers** (declarations), **`extern`** (a name defined elsewhere) and **`static`** (a name private to one file). This chapter uses them to turn Chapters 19 and 20 into a small library, `psxe`, with a thin `main.c` on top.

## 2. Why it matters

A single file gets harder to navigate and to change safely with every feature. A library lets you fix `ot_alloc` once and every program gets the fix. Most later projects link `psxe`, and it grows: Chapter 22 adds an `input` module, Chapter 24 a fixed-point `fixed` module. The habits here (small APIs, hidden state, no circular includes) keep that codebase workable for the rest of the book.

## 3. Learning objectives

After this chapter you can:

- follow a `.c` file through preprocessing, compilation, archiving and linking;
- write a header that is safe to include twice, self-contained, and free of definitions;
- tell a declaration from a definition, and say what `extern` and the one-definition rule mean;
- use `static` to give a function or variable internal linkage, and confirm with `nm` that it is hidden;
- build a static library with CMake and link it with `target_link_libraries`;
- design a module API small enough to remember, and avoid circular dependencies.

## 4. Prerequisites

[Chapter 18](../ch18-from-assembly-to-c/README.md) (the CMake build, `nm`), [Chapter 19](../ch19-double-buffering/README.md) (`display.c`) and [Chapter 20](../ch20-primitives-and-ordering-tables/README.md) (`ot.c`, the scene, the DMA-list probe).

## 5. Explanation

### 5.1 From `.c` files to a program

```
 display.c ---compile---> display.o --+
 ot.c      ---compile---> ot.o -------+--ar--> libpsxe.a ---+
 gfx.c     ---compile---> gfx.o ------+                     +--link--> game.elf --elf2x--> game.exe
 main.c    ---compile---> main.o ---------------------------+
              (each .c is compiled alone,
               seeing only the headers it includes)
```

- The compiler never sees two `.c` files at once. A call to `ot_alloc` in `gfx.c` compiles against a **prototype** from a header; the address is left blank in the object file as an *undefined symbol*.
- An **archive** (`.a`) is a bundle of object files plus an index.
- The **linker** matches each undefined symbol with a definition in some object and patches the address in. With `-gc-sections` (the SDK sets it) it also drops what nothing references.

Two failures you will meet: *undefined reference to `x`* (declared, never defined, or the library is not linked) and *multiple definition of `x`* (defined in two units).

### 5.2 Declaration vs definition

| | Says | Allocates storage / emits code | How many times |
|---|---|---|---|
| Declaration: `void ot_draw(void);` `extern OtFrame ot_frames[2];` | "this name exists, here is its type" | no | as often as you like |
| Definition: `void ot_draw(void) {...}` `OtFrame ot_frames[2] = {...};` | "this is it" | yes | **exactly once** in the whole program |

This is the **one-definition rule** (ODR) in its C form. Functions are easy: a prototype is a declaration. Variables need the keyword **`extern`** in the header, otherwise `OtFrame ot_frames[2];` in a header is a *definition* in every file that includes it.

```
ot.h:   extern OtFrame ot_frames[2];     <- declaration, included everywhere
ot.c:   OtFrame ot_frames[2] = { ... };  <- the one definition
```

### 5.3 Headers

A header holds what other files need to *use* a module: prototypes, `extern` declarations, types, macros. Never function bodies or variable definitions.

**Include guards.** `#include` pastes text. If `main.c` includes `ot.h` and `gfx.h`, and `gfx.h` also includes `ot.h`, the typedef in `ot.h` appears twice and the compiler reports *conflicting types for `OtFrame`*. The guard makes the second paste empty:

```
#ifndef PSXE_OT_H
#define PSXE_OT_H
...
#endif
```

`#pragma once` does the same in one line; it is not in the C standard but GCC supports it. This book uses the classic guard, whose macro name must be unique (prefix it with the library name).

**Self-contained.** A header includes what it uses (`<stdint.h>` for `uint8_t`) so that it compiles when it is the first thing in a file. Include other headers *from the header* only when its own declarations need their types; otherwise leave it to the `.c` file.

### 5.4 `static`: internal linkage

Every name at file scope has a **linkage**. By default it is *external*: the symbol goes into the object file's symbol table and any other unit can refer to it. `static` at file scope makes it *internal*: the symbol is local to that unit.

| Written at file scope | Symbol is | Other files can use it |
|---|---|---|
| `int cur;` | global (`B`) | yes, intended or not |
| `static int cur;` | local (`b`) | no |

Reasons to prefer `static`:

- **Hiding state.** `ot.c`'s `cur` and `used` can only change through the four `ot_*` functions, so an outside file cannot break the invariants.
- **No name clashes.** Two modules may each have a `static int count;`; two *global* ones would be a link error.
- **Room to change.** Whatever is not exported can be renamed or removed freely.

(`static` inside a function means something else: the variable keeps its value between calls. That is not what we use here.)

`nm` shows the difference: an uppercase letter is global, lowercase is local.

### 5.5 Designing the `psxe` APIs

A good module API is small, named with a module prefix (`ot_`, `gfx_`), and hides how it works. Dependencies point one way:

```
        main.c
       /   |   \
      v    v    v
 display   ot <---- gfx          (input: Chapter 22, later)
      \    |    /
       v   v   v
       PSn00bSDK (psxgpu)
```

- `gfx` uses `ot` (to allocate and link packets). `ot` knows nothing about `gfx`.
- `display` and `ot` do not know each other. `main.c` is the only place that orders the calls of the frame.
- No cycles. If `ot.h` included `gfx.h` and `gfx.h` included `ot.h`, the guards would stop the endless paste, but whichever header is entered second would be read before the types it needs from the first exist (*unknown type name*). When two modules seem to need each other, move the shared part into a third module (or a type into its own header).

### 5.6 CMake targets

A **target** is a thing CMake builds (library, executable) together with its properties.

| Command | Meaning |
|---|---|
| `add_library(psxe STATIC a.c b.c)` | build `libpsxe.a` from these units |
| `target_include_directories(psxe PUBLIC include)` | `psxe` and everyone linking it get `-I include` |
| `target_link_libraries(game PRIVATE psxe)` | `game` links `psxe` and inherits its `PUBLIC` include directories |
| `add_subdirectory(psxe)` | process `psxe/CMakeLists.txt`, which defines the target |

`PUBLIC` = needed by me and by my users; `PRIVATE` = only by me.

Link order matters for static libraries. The linker reads its inputs left to right and takes an object out of an archive only if it defines a symbol that is *still undefined at that point*; it never goes back. So a library must come after everything that uses it. `psn00bsdk_add_executable` already puts the SDK libraries on `game`'s link line in a working order (`psxgpu` before `psxetc` and `psxapi`, which it needs), and CMake places `psxe` in front of them. That is why `psxe` links only `PRIVATE psn00bsdk`, the target that carries the SDK's compiler flags and no libraries. Linking `psxgpu` into `psxe` as well looks harmless, but CMake then moves `libpsxgpu` to the end of the line, after `psxapi` and `psxetc`, and the link fails with *undefined reference to `ResetCallback`* (called by `ResetGraph`), among others.

### 5.7 Repository convention

The book keeps a reference copy of the library in `common/psxe/` (next to `psxexe.inc`). It is this chapter's answer, so treat it like `solution/`: open it after you pass. **Chapter folders do not share files**: each later chapter that uses the library ships its own copy in `starter/psxe/` (and `solution/psxe/`), taken from `common/psxe/`, so every project is self-contained and you can copy it anywhere.

## 6. Worked example: look inside an archive

The SDK's own graphics library is a static archive built exactly the way `libpsxe.a` will be. Inspect it:

```sh
source tools/env.sh
cd .toolchain/opt/psn00bsdk/lib/libpsn00b/release
mipsel-none-elf-ar t libpsxgpu_exe_gprel.a           # the objects inside
mipsel-none-elf-nm libpsxgpu_exe_gprel.a | less      # per object: T/t code, D/d data, B/b bss, U undefined
mipsel-none-elf-nm -A *_exe_gprel.a | grep ' T ResetCallback'   # who defines it?
```

Uppercase letters are global, lowercase are local (`static`). Questions:

1. In `common.c.obj`, find two `static` variables and two `static` functions (`b` and `t`).
2. `ResetGraph` is `T` in `common.c.obj`, which also lists `ResetCallback` as `U`. Which archive defines it, and so which must come later on the link line?
3. `_send_linked_list` is `T` in `drawing.c.obj` and `U` in `env.c.obj`. Why can it not be `static`, even though no game is meant to call it?

After the project, run `nm` on your own `libpsxe.a` (in `build/psxe/`): `cur` and `used` are `b`, `ot_frames` is `D` (it has an initializer, the guard bytes), and `clamp_depth` does not appear at all, because the compiler inlined it, and a `static` function that no other file can call needs no symbol. Remove `static` from `cur`, rebuild, and it turns into `B`.

## 7. Project: the `psxe` library

Work in `starter/`. It builds and runs, because it is Chapters 19 and 20 pasted into one `main.c`. Your job is to split it without changing what it does.

### 7.1 Target layout

```
main.c                  scene, draw_scene, advance, the loop
CMakeLists.txt          add_subdirectory(psxe); game links psxe
psxe/
  CMakeLists.txt        target `psxe` (STATIC)
  include/psxe/         display.h  ot.h  gfx.h
  src/                  display.c  ot.c  gfx.c
```

`main.c` includes `<psxe/display.h>` and so on: that works because the `include` directory is `PUBLIC`. The three headers are given in `starter/psxe/include/psxe/`: they hold the API but lack include guards.

### 7.2 The three modules

| Module | Exports (and nothing else) | Notes |
|---|---|---|
| `display` | `display_init`, `display_clear`, `display_swap` | Chapter 19's code. The environments and the back-buffer index are `static` |
| `ot` | `ot_begin_frame`, `ot_alloc`, `ot_add`, `ot_draw`, `ot_frames` | Chapter 20's code. `cur` and `used` are `static`. Move the depth clamp of `ot_add` into a `static` helper `clamp_depth` |
| `gfx` | `gfx_quad_f4` | **New**, below |

`ot_frames` stays a global (the verifier reads it), declared `extern` in `ot.h`, defined in `ot.c`.

**`gfx_quad_f4`**, declared in `gfx.h`:

```
int gfx_quad_f4(int16_t x, int16_t y, int16_t w, int16_t h,
                uint8_t r, uint8_t g, uint8_t b, int depth);
```

Allocates a `POLY_F4` with `ot_alloc`, sets it up as a flat rectangle (`setPolyF4`, `setXYWH`, `setRGB0`), links it with `ot_add` at `depth`, and returns 0. If `ot_alloc` returns `NULL` it returns -1 and draws nothing.

### 7.3 Steps

1. Move the code into `psxe/src/*.c`, one module per file. Each `.c` includes its own header first (it then proves the header is self-contained).
2. Write the guards in the three headers.
3. Write `psxe/CMakeLists.txt` (5.6): a `STATIC` library `psxe` from the three sources, `PUBLIC` include directory, `PRIVATE` link to `psn00bsdk`.
4. Edit the top `CMakeLists.txt`: `add_subdirectory(psxe)`, build `game` from `main.c` only, `target_link_libraries(game PRIVATE psxe)`.
5. Replace the pasted code of `main.c` with calls to the library. `draw_scene` calls `gfx_quad_f4` and stops the frame when it returns a negative value.

### 7.4 Rules

- Keep `scene`, `copies`, `depth_step`, `frame_no` and the `OtFrame` layout as shipped (the verifier patches them). The frame order of Chapter 20 is unchanged.
- `main.c` has at most **70 lines of code** (blank lines and comments do not count), does not include `<psxgpu.h>` and calls no `psxgpu` function itself (not even `ResetGraph` or `VSync`: they belong to `display`).
- `libpsxe.a` exports the names in the table of 7.2 and nothing else, except extra API you add on purpose: a function named with its module's prefix and declared in that module's header (such as `gfx_tile`). Everything else must be `static`.
- Headers declare, never define.
- The only `.c` outside `psxe/` is `main.c`.

### 7.5 Hints

- *conflicting types for `OtFrame`*: a missing include guard.
- *unknown type name `uint8_t`*: the header lacks `#include <stdint.h>`.
- *multiple definition of `ot_frames`*: it is defined (without `extern`) in a header.
- *undefined reference*: a `.c` is missing from `add_library`, `game` does not link `psxe`, or `psxe` links an SDK library (5.6).
- `nm` shows an unexpected `T` or `B`: a `static` is missing.

### 7.6 Stretch goals

- Add `gfx_quad_g4` (Gouraud: a color per corner) and `gfx_tile` (a `TILE` rectangle).
- Build the library as `OBJECT` instead of `STATIC` and compare the link with `-gc-sections`.
- Add `psxe/psxe.h`, a single header that includes the three. What does that do to compile times and to your dependency diagram?

## 8. Verification

```sh
parts/part-04-c-on-the-playstation/ch21-working-with-multiple-files/verify/verify.sh
```

| Check | What it means | If it fails |
|---|---|---|
| `symbols`, `data layout as shipped` | Program and library symbols exist; data unedited | A module is missing from the link, or the data was edited |
| `libpsxe.a exports only the module API` | `nm` on the archive: objects are `display`, `ot`, `gfx`; each defines its API and no other global except `module_*` names declared in its header | A helper or state variable is not `static`, or the archive is missing |
| `headers` | Each header compiles alone and twice, the three compile together, and they define no variable or function | Missing guard, missing `#include`, definition in a header |
| `main.c is thin` | At most 70 code lines, no SDK drawing calls or `psxgpu.h`, no stray `.c` | Code left in `main.c` |
| `the reference solution mirrors common/psxe` | Book maintenance: checked only for `solution/` | (passes for your project) |
| `ClearOTagR ...`, `the DMA list ...`, `packets are bump-allocated`, `overflow`, `pacing` | Chapter 20's checks on the running program: the probe walks the DMA list; the guard bytes stay intact with 320 quads | The split changed behavior |
| `gfx_quad_f4 is called once per quad` | 16 calls between consecutive `DrawOTag` | `draw_scene` bypasses `gfx` |
| `screenshots` | About 1500 sampled points on two scenes show the nearest quad's color: the picture is the Chapter 20 picture | Wrong order or colors |

A pass ends with `CHAPTER 21: PASSED (13/13 checks)`.

## 9. Common pitfalls

- **Definitions in headers, or a shared variable without `extern`.** Fine with one `.c`, a *multiple definition* link error with two. (GCC 10 and later default to `-fno-common`; older compilers silently merged uninitialized copies, so old code may "work".)
- **Include guard macro copied between headers.** Two headers with `#define PSXE_OT_H` and the second silently vanishes.
- **A header that only compiles after something else.** If `gfx.h` works only because `main.c` included `<stdint.h>` first, it is not self-contained.
- **Everything global "just in case".** Any global is API; once someone uses it you cannot change it.
- **Circular includes.** Fix the design, not the include order.
- **Library listed before the objects that need it** on a link line. Nothing is taken from it, and the link reports *undefined reference*. `target_link_libraries` orders this for you, as long as you do not also link SDK libraries into `psxe` (5.6).
- **Using `static` on something the program needs from another file.** The link error is *undefined reference*.

## 10. Quiz

[quiz.md](quiz.md)

## 11. Further reading

- `.toolchain/opt/psn00bsdk/lib/libpsn00b/cmake/internal_setup.cmake`: `psn00bsdk_add_executable` and `psn00bsdk_add_library`.
- The CMake manual: `target_link_libraries` and "PUBLIC, PRIVATE and INTERFACE".
- `man nm`: the symbol type letters.
- [Chapter 22](../ch22-controller-input-and-the-bios/README.md) adds the `input` module to `psxe`.
