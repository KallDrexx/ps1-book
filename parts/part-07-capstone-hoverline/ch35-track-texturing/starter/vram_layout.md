# VRAM layout: the Hoverline track tiles

<!-- Fill in every section. Text inside comments does not count for the verifier. Units: x and w in 16-bit VRAM units, y and h in lines.
     The verifier checks: the five headings below (keep the words framebuffer, tile, free, rationale, flip), every tile named,
     and that each tile's VRAM x, y and its CLUT's x, y (the numbers in vram_layout.h) appear in this document. -->

## Framebuffer map

<!-- A 1024 x 512 ASCII sketch of VRAM: the two framebuffers (0,0) and (0,240), what the program already loads
     (README 5.2), and where YOUR tile pages and CLUT rows go. -->

## Tile table

<!-- One row per texture id 0..7 of TRACK.TPK. Name every tile.
| id | tile | VRAM x | VRAM y | w x h | page (x/64, y/256) | u0, v0 | CLUT (x, y) |
|---|---|---|---|---|---|---|---|
-->

## Free space

<!-- How many VRAM units are used (framebuffers, LOGO, PROPS, your tiles and CLUTs) and how many are left, and where the
     biggest free block is. Say what Chapter 36 onwards could still use. -->

## Rationale

<!-- Why these places: pages shared or separate, alignment, CLUT row, how you avoided the framebuffers and the other TIMs,
     whether you left a margin between tiles and why. -->

## Flip flag

<!-- What a face with FLIP_H does to its UVs (formula), where in the pipeline the mirror happens, and what is NOT changed (VRAM, the vertices). -->
