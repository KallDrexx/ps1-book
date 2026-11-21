# VRAM layout: the Hoverline track tiles

Units: x and w in 16-bit VRAM units, y and h in lines. Texture page = 64 units x 256 lines at 4 bpp (256 x 256 texels).

## Framebuffer map

```
x:   0    64   128  192  256  320  ...                 512 520 576      640     768  800  1024
y=0   +-----------------------+                        PR  PR |tile page|        LOGO
      |  framebuffer 0        |                                | 576..639|
      |  320 x 240            |  free                          |  y 256..|
y=240 +-----------------------+
      |  framebuffer 1        |                                           (page (9, 0) above the tiles: free)
      |  320 x 240            |
y=480 +-----------------------+---------------------------------------------------------------+
      | CLUT strip: logo (0,498), props (32,480..481), tiles (64..191, 488)  free elsewhere   |
y=512 +--------------------------------------------------------------------------------------+
```

Already taken by the program before the tiles: framebuffer 0 at (0,0) 320x240, framebuffer 1 at (0,240) 320x240,
LOGO.TIM image (768,0) 32x64 with its CLUT (0,498), PROPS.TPK images (512,0) 8x64 and (520,0) 16x64 with CLUTs (32,480) and (32,481).

## Tile table

All tiles are 4 bpp, 64 x 64 texels = 16 units x 64 lines. Page word = `TPAGE_4BPP(x, y)`; CLUT word = `CLUT_AT(cx, cy)`.

| id | tile | VRAM x | VRAM y | w x h | page (x/64, y/256) | u0, v0 | CLUT (x, y) |
|---|---|---|---|---|---|---|---|
| 0 | asphalt | 576 | 256 | 16 x 64 | 9, 1 | 0, 0 | (64, 488) |
| 1 | asphalt_worn | 592 | 256 | 16 x 64 | 9, 1 | 64, 0 | (80, 488) |
| 2 | lane_stripe | 608 | 256 | 16 x 64 | 9, 1 | 128, 0 | (96, 488) |
| 3 | boost | 624 | 256 | 16 x 64 | 9, 1 | 192, 0 | (112, 488) |
| 4 | start_line | 576 | 320 | 16 x 64 | 9, 1 | 0, 64 | (128, 488) |
| 5 | wall_a | 592 | 320 | 16 x 64 | 9, 1 | 64, 64 | (144, 488) |
| 6 | wall_b | 608 | 320 | 16 x 64 | 9, 1 | 128, 64 | (160, 488) |
| 7 | glow | 624 | 320 | 16 x 64 | 9, 1 | 192, 64 | (176, 488) |

All eight tiles share one page word (page (9, 1), p25 in README 5.3's map), so the GPU never switches pages between track faces.

## Free space

| Region | Units | Share of 524,288 |
|---|---|---|
| Framebuffers (2 x 320 x 240) | 153,600 | 29.3 % |
| LOGO image + CLUT | 2,048 + 16 | 0.4 % |
| PROPS images + CLUTs | 1,536 + 32 | 0.3 % |
| Track tiles (8 x 16 x 64) + CLUTs (8 x 16) | 8,192 + 128 | 1.6 % |
| **Used** | **165,552** | **31.6 %** |
| **Free** | **358,736** | **68.4 %** |

Left over for later chapters: the other eight tile slots of page (9, 1) (x 576..639, y 384..511: two more rows of four);
whole free pages at x 320..511, 576..767 and 832..959 in the first page row and x 320..575 and 640..1023 in the second; the rest of
pages (8, 0), (12, 0) and (15, 0) around PROPS, LOGO and the SDK font's place (960..991 x 0..32, if `FntLoad(960, 0)` is called);
and CLUT room in rows 480..511 left of x 320 wherever the table above leaves it (x 192..319 of row 488, for example).

## Rationale

- One page for all the track tiles: one tpage word, no page switches, easy to check.
- Page 9 sits beside PROPS (512..527) and LOGO (768..799) without touching them; the tile page is not the TIMs' own place (384..447), so the program really relocates.
- Tiles are packed in a 4 x 2 grid with no margin: the face UVs are 0..63, the last texel of a 64-texel tile, so a polygon never samples the neighbor.
  Vertical neighbors are the rows y 256..319 and 320..383; there is no horizontal gap either.
- The CLUTs share one row at y = 488, 16 units apart (CLUT x must be a multiple of 16), under the framebuffers where nothing else but the other CLUTs lives.
- The framebuffers are never overlapped: everything the GPU draws there is overwritten every frame.

## Flip flag

Faces with `FLIP_H` (bit 4 of the flags) use the same tile mirrored in U: each corner's u becomes `u_min + u_max - u` of the face's own four u values,
which for these 0..63 faces is `63 - u`; v is unchanged. Nothing in VRAM is changed, and the tile's origin is added after the mirror.
In track 1 the odd sections have mirrored walls (and a mirrored right lane); the hazard-stripe wall (tile 6) makes the mirror visible.
