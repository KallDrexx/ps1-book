# Chapter 21 Quiz

**1.** What is a translation unit, and what does the linker do that the compiler cannot?

<details><summary>Answer</summary>

A translation unit is one `.c` file after the preprocessor has pasted in its includes. The compiler turns each into an object file on its own, leaving calls to names defined elsewhere as undefined symbols. The linker matches those with definitions in other objects or archives and fills in the addresses.
</details>

**2.** Which of these is a definition: `extern int frame_no;`, `int frame_no;`, `void ot_draw(void);`, `void ot_draw(void) { }`?

<details><summary>Answer</summary>

`int frame_no;` (at file scope it allocates storage) and `void ot_draw(void) { }`. The other two only declare. Only definitions are limited to one per program.
</details>

**3.** `ot.h` contains `OtFrame ot_frames[2];` (no `extern`) and is included by `ot.c` and `main.c`. What happens, and what is the fix?

<details><summary>Answer</summary>

Each file has its own definition: the linker reports *multiple definition of `ot_frames`*. Write `extern OtFrame ot_frames[2];` in the header and define it once in `ot.c`.
</details>

**4.** What does an include guard prevent? Why does a missing one often show up only after you add a second header?

<details><summary>Answer</summary>

It prevents a header's contents from being pasted twice into one translation unit, which would repeat typedefs and struct definitions (errors such as *conflicting types*). With one header there is one include; a second header that includes the first creates the duplicate.
</details>

**5.** In `nm` output, `cur` appears as `b` and `ot_alloc` as `T`. What does each letter case tell you, and which keyword produced the lowercase one?

<details><summary>Answer</summary>

Uppercase means a global symbol visible to other files; lowercase means local. `static` at file scope gave `cur` internal linkage. `T` is code, `b` is zero-initialised data (`.bss`).
</details>

**6.** Give two benefits of making a module's state variables `static`.

<details><summary>Answer</summary>

Other files cannot change them except through the module's functions, so invariants hold; names cannot clash between modules; and the implementation can change without touching users.
</details>

**7.** In `target_include_directories(psxe PUBLIC include)`, what would change with `PRIVATE`?

<details><summary>Answer</summary>

`psxe`'s own sources would still find the headers, but `game` (which links `psxe`) would not inherit the include path, so `#include <psxe/ot.h>` in `main.c` would fail.
</details>

**8.** `gfx.c` calls `ot_alloc`. Should `ot.h` include `gfx.h` too? Why or why not?

<details><summary>Answer</summary>

No. `gfx` depends on `ot`, never the reverse. A cycle would make each header need the other first. If two modules need each other, move the shared part into a third.
</details>

**9.** The linker reports *undefined reference to `gfx_quad_f4`* although `gfx.c` exists. List two causes.

<details><summary>Answer</summary>

`gfx.c` is not listed in `add_library`, or the executable is not linked with `psxe` (or the function was made `static`, or the prototype and definition names differ).
</details>
