# Chapter 20 Quiz

**1.** The GPU has no depth buffer. What decides which of two overlapping primitives ends up on top?

<details><summary>Answer</summary>

The order in which the GPU receives them: the later one overwrites the earlier one (painter's algorithm). Depth sorting means sending the packets far to near.
</details>

**2.** Describe the header word of a primitive. What does `0x050116D4` mean?

<details><summary>Answer</summary>

Bits 0 to 23 are the address of the next header word (without the `0x80000000` bits), bits 24 to 31 are the number of words after the header that go to GP0. `0x050116D4` is: 5 data words follow (a `POLY_F4`), and the next header is at `0x800116D4`. `0x00FFFFFF` in the address field ends the list.
</details>

**3.** After `ClearOTagR(ot, 64)`, which entry does `ot[10]` point to, what does `ot[0]` hold, and where must `DrawOTag` start?

<details><summary>Answer</summary>

`ot[10]` points to `ot[9]`; `ot[0]` holds the terminator `0x00FFFFFF`; `DrawOTag` starts at `&ot[63]`. Starting at `&ot[0]` draws nothing.
</details>

**4.** Which of depth 3 and depth 40 is drawn first with a reverse table, and which is in front?

<details><summary>Answer</summary>

Depth 40 is drawn first (behind); depth 3 is drawn later and covers it. Smaller index = nearer.
</details>

**5.** Two primitives are added to the same slot, A then B. Which is drawn first?

<details><summary>Answer</summary>

B. `addPrim` inserts at the head of the slot's list, so the last added is first in the list and drawn first (behind).
</details>

**6.** What does `addPrim(&ot[z], p)` do, in pointer terms, and what does it cost compared with sorting an array of packets?

<details><summary>Answer</summary>

`p->addr = ot[z].addr; ot[z].addr = p`: two stores, no search, no copying. The cost is independent of how many packets are already in the table.
</details>

**7.** Why is the primitive buffer a bump allocator, and why does `ot_begin_frame` reset it instead of freeing each primitive?

<details><summary>Answer</summary>

A frame's primitives all die together at the next frame, so allocation is a compare and an add and "free" is `used = 0`. There is no per-primitive bookkeeping, which matters with thousands of packets per frame.
</details>

**8.** Why must `ot_alloc` check for space, when it only hands out pointers?

<details><summary>Answer</summary>

The caller writes the primitive through the pointer. The PS1 has no memory protection, so an allocation past the end silently overwrites the next data, here a table or packet header, and the DMA may then follow a corrupt link and hang. Returning `NULL` and skipping the primitive is the safe failure.
</details>

**9.** Why are there two ordering tables and two primitive buffers when the program has only one CPU thread?

<details><summary>Answer</summary>

`DrawOTag` returns at once while the DMA is still reading the packets. While the GPU draws frame *n*, the CPU may build frame *n+1*, but must not write anything the DMA can still read. Two sets (one per display buffer) make that safe; with `DrawSync` before building, one would happen to work.
</details>

**10.** A program draws with `DrawOTag(&ot[N-1])` but calls `ClearOTagR` only once, at start-up. What goes wrong?

<details><summary>Answer</summary>

`addPrim` rewrote the links during the first frame and nothing resets them. From the second frame on, new packets are inserted on top of old ones: the same primitives are drawn repeatedly and, once their memory is reused, links can form a loop or point at garbage.
</details>
