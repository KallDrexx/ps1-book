# Chapter 38 quiz

**1.** A track has 112 sections and the ship is in section 2. With `vis_ahead` 24 and `vis_behind` 4, which sections are drawn and what are `first` and `count`?

<details><summary>Answer</summary>

`first = (2 - 4) mod 112 = 110` (a *non-negative* remainder: C's `%` would give -2), `count = 4 + 24 + 1 = 29`. The sections are **110, 111, 0, 1, 2, ..., 26**: the window wraps over the lap boundary, where `next(111) = 0`.
</details>

**2.** The metric is the squared distance in 3D, computed in 64 bits. Why squared, why 64 bits, and why does a tie go to the lowest index?

<details><summary>Answer</summary>

Squared: the order of distances is the order of their squares, and a square root is slow and not needed. 64 bits: a ship only 65,536 units from a centre already squares past 32 bits (the verifier parks it 150,000 units away, and shifts track 2 by (+60000, 0, +45000)); 64 bits hold three squares for any distance below 2^31. The tie rule makes the answer a *function of the data* so that any implementation, brute force or incremental, and the Python reference agree on every input.
</details>

**3.** The incremental update looks at `prev(cur)`, `cur` and `next(cur)`. A student writes `cur + 1` and `cur - 1` instead. When does it break?

<details><summary>Answer</summary>

At the lap boundary (`cur = 111`: `cur + 1 = 112` is not a section, and `cur = 0`: `cur - 1 = -1`), and on any track whose links are not `i +- 1`. The links in the file are the truth about which section follows which; the format even reserves a `JUNCTION` flag for a section with a second exit.
</details>

**4.** A teleport puts the ship 40 sections away. Why can the hill climb give a wrong answer, and which two rules protect the result?

<details><summary>Answer</summary>

The walk follows the distance downhill from the old section; it can stop in a local valley (a section closer than both neighbours, but not the nearest) or take many moves. Rule 1: after `VIS_MAX_STEPS` = 4 moves it gives up and searches every section. Rule 2: if it stops on a section farther than `vis_lost` (4000 units, compared as `d2 > vis_lost^2`) the answer is not trusted either: brute force. The brute-force search costs about 20,000 cycles, 3-4% of a frame, so the fall-back is cheap enough to be generous.
</details>

**5.** The solution measures the whole track at about 564,000 cycles per frame and the 29-section window at about 245,000 (the same 110 poses), against a vertical blank of 566,120. Why is the section count the right lever, and why is subdivision still off?

<details><summary>Answer</summary>

Work is roughly proportional to the packets built, and the packets are proportional to the faces of the sections drawn: 29 of 112 sections is about a quarter of the faces, and the frame drops to 43% of a blank. Subdividing the window's near faces (Chapter 36) makes 341 packets per frame on average and 592,000 cycles of work: over a blank in 88% of the frames. So `subdiv_enabled` stays 0 by default (R1 toggles it). The numbers are CPU work plus `DrawSync`'s wait, which in the emulator is almost nothing: it does not charge for the GPU's rasterisation, which a console adds to every frame, so they are lower bounds.
</details>

**6.** Why is `prims_this_frame` read before the readout is drawn, and why does the readout use `FntSort` into slot 0 and not `FntFlush`?

<details><summary>Answer</summary>

The readout's characters are sprite packets (one per character) in the same ordering table, so counting after them would mix the text into the number it prints and change it by the length of the line. `FntFlush` draws *immediately*, before the ordering table is sent to the GPU, so the track would be drawn over the text. Sorting the text into the nearest slot (0) puts it after every other slot, on top (only another packet in slot 0, linked earlier, would be drawn after it: a road face right in front of the camera, never at the top-left).
</details>

**7.** The verifier checks the window by looking at `trk_vstate` after the frame instead of reading the ordering table. What does that prove, and what could it miss?

<details><summary>Answer</summary>

`track_vertex_prepare` is only called for the vertices of faces that `track_draw_section` visits, so a vertex that is not `VS_UNSEEN` belongs to a face of a drawn section: the set of such vertices equals the union of the window's faces (the ring vertices shared with neighbouring sections included). It proves the *set of sections visited*, exactly, including wrap and patched sizes. It cannot tell whether a visited face was then culled or drawn; that is the job of Chapter 34's buckets and the packet count check.
</details>
