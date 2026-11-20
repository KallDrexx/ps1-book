# Chapter 1 Quiz

**1. Name the CPU in the PS1 and its clock speed.**
<details><summary>Answer</summary>
A MIPS R3000A (an LSI CW33300 core) at 33.8688 MHz.
</details>

**2. Which chip draws triangles and rectangles into VRAM: the CPU, the GTE or the GPU? What does the GTE do instead?**
<details><summary>Answer</summary>
The GPU. The GTE is a coprocessor attached to the CPU that does fast fixed-point vector and matrix math (3D transforms); it draws nothing.
</details>

**3. Why can't you run a program you assemble on your PC directly?**
<details><summary>Answer</summary>
The host (x86-64 or ARM) and the PS1 (MIPS) use different instruction sets. You cross-assemble or cross-compile on the host and run the result on the target, here an emulator.
</details>

**4. In `GP1(08h)`-style notation, what do GP0 and GP1 refer to?**
<details><summary>Answer</summary>
Two GPU ports in the I/O area: GP0 (0x1F801810) takes drawing commands and VRAM data; GP1 (0x1F801814) takes display and control commands. The top byte of each word is the command number.
</details>

**5. The fill command is `0x02BBGGRR`. How is pure green written?**
<details><summary>Answer</summary>
`0x0200FF00`. The byte order in the word is blue, green, red, so green sits in the middle byte.
</details>

**6. A GPU fill that you send to GP0 appears on the screen. Which two things must be true besides the fill itself?**
<details><summary>Answer</summary>
The display must be enabled (GP1(03h)) and the display area/range/mode must point at the part of VRAM you filled (GP1(05h), (06h), (07h), (08h)).
</details>

**7. What does `verify.sh` do that `doctor.sh` does not?**
<details><summary>Answer</summary>
`doctor.sh` only checks that the tools are installed at the right versions. `verify.sh` builds your code, runs it in a headless emulator, and checks the result.
</details>

**8. Why does the verifier compare colors with a tolerance?**
<details><summary>Answer</summary>
VRAM stores 5 bits per channel, so an 8-bit value is quantized (for example 0x20 comes back as 0x21). An exact match would fail on correct programs.
</details>

**9. The PSX-EXE header says the code loads at `0x80010000`. What does the header add that raw machine code lacks, and why does the book's `.create` line use `0x8000F800`?**
<details><summary>Answer</summary>
The header (starting with `PS-X EXE`) tells the loader where to copy the code, how big it is, where to start executing (`main`) and where the stack starts. It is 2 KB (0x800 bytes) long and sits in front of the code, so the file's byte 0 corresponds to 0x80010000 - 0x800 = 0x8000F800.
</details>

**10. Name two design bets Sony made with the PlayStation and one consequence of each for programmers.**
<details><summary>Answer</summary>
Any two of: 3D polygons first (hardware GTE + GPU, so you will spend much of the book on triangles, fixed-point math and polygon sorting); CD-ROM instead of cartridges (cheap and large, but slow, so you plan loading, compression and streaming); developer-friendly C libraries (most games were written in C, which is why Part IV moves from assembly to C).
</details>
