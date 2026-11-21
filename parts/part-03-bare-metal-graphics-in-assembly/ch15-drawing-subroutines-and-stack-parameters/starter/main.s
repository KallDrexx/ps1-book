; Chapter 15 -- "Low-Poly Landscape" (starter)
;
; You write:
;   draw_flat_tri(color, x0,y0, x1,y1, x2,y2)                      7 arguments: 4 in $a0-$a3, 3 on the stack
;   draw_flat_quad(color, x0,y0, x1,y1, x2,y2, x3,y3)              9 arguments: 4 in $a0-$a3, 5 on the stack
;   draw_gouraud_tri(c0,x0,y0, c1,x1,y1, c2,x2,y2)                 9 arguments: 4 in $a0-$a3, 5 on the stack
;   Colors are 0x00RRGGBB, coordinates signed numbers; vertices go to the GPU in the order given.
;   Each routine waits for the GPU once, then sends ONE packet; $s0-$s7, $gp, $fp and $sp must be preserved.
;   (Stack arguments sit at 16($sp), 20($sp), ... as seen at entry, before you move $sp.)
;   main: draw every entry of `scene` (table at the bottom), in order, with the routine its type names.
;
; Given: gpu_init, gpu_clear (Chapter 13), gpu_wait, pack_color, pack_vertex (Chapter 14), and the scene table.

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

.definelabel GP0, 0x1F801810        ; GPU command / data port (write), GPUREAD (read)
.definelabel GP1, 0x1F801814        ; GPU control port (write), GPUSTAT (read)

.definelabel T_FLAT_TRI,     0      ; scene entry types
.definelabel T_FLAT_QUAD,    1
.definelabel T_GOURAUD_TRI,  2
.definelabel SCENE_MAX,      64     ; the verifier may patch in up to this many entries

.macro vtx,x,y                      ; one packed vertex word: (y << 16) | (x & 0xFFFF)
    .word ((y) << 16) | ((x) & 0xFFFF)
.endmacro

; ---- your routines ------------------------------------------------------------------------------------------
draw_flat_tri:
    ; TODO: wait once, then send 0x20BBGGRR, v0, v1, v2
    jr    $ra
    nop

draw_flat_quad:
    ; TODO: wait once, then send 0x28BBGGRR, v0, v1, v2, v3
    jr    $ra
    nop

draw_gouraud_tri:
    ; TODO: wait once, then send 0x30BBGGRR, v0, 0x00BBGGRR, v1, 0x00BBGGRR, v2
    jr    $ra
    nop

; ---- main ---------------------------------------------------------------------------------------------------
main:
    ; TODO: build a frame; gpu_init; gpu_clear(background color from the table, 0, 0, 320, 240);
    ;       then for each of the `count` entries: unpack its vertices (signed 16-bit halves of the packed words),
    ;       put the arguments in $a0-$a3 and at 16($sp)..., and call the routine its type names.
    jal   gpu_init
    nop

done:
    j     done
    nop

; ---- given routines (Chapters 13 and 14) ------------------------------------
gpu_init:
    lui   $t0, 0x1F80           ; $t0 = 0x1F800000 (GP0 = 0x1810($t0), GP1 = 0x1814($t0))
    sw    $zero, 0x1814($t0)    ; GP1(00h) reset
    li    $t1, 0x03000000
    sw    $t1, 0x1814($t0)      ; GP1(03h) display on
    li    $t1, 0x05000000
    sw    $t1, 0x1814($t0)      ; GP1(05h) display start (0,0)
    li    $t1, 0x06C60260
    sw    $t1, 0x1814($t0)      ; GP1(06h) horizontal range 0x260..0xC60
    li    $t1, 0x07040010
    sw    $t1, 0x1814($t0)      ; GP1(07h) vertical range 16..256
    li    $t1, 0x08000001
    sw    $t1, 0x1814($t0)      ; GP1(08h) 320x240, NTSC, 15-bit, no interlace
gi_wait:
    lw    $t1, 0x1814($t0)
    nop
    lui   $t2, 0x0400
    and   $t1, $t1, $t2
    beqz  $t1, gi_wait          ; wait for "ready to receive command word"
    nop
    li    $t1, 0xE1000400
    sw    $t1, 0x1810($t0)      ; GP0(E1h) draw mode: drawing to the display area allowed, dither OFF
    li    $t1, 0xE3000000
    sw    $t1, 0x1810($t0)      ; GP0(E3h) drawing area top-left (0,0)
    li    $t1, 0xE4000000 | (239 << 10) | 319
    sw    $t1, 0x1810($t0)      ; GP0(E4h) drawing area bottom-right (319,239)
    li    $t1, 0xE5000000
    sw    $t1, 0x1810($t0)      ; GP0(E5h) drawing offset (0,0)
    jr    $ra
    nop

gpu_clear:                      ; fill rectangle: GP0(02h), the color is 0x00RRGGBB; h is the 5th argument, 16($sp)
    lui   $t0, 0x1F80
    lw    $t3, 16($sp)          ; h
gc_wait:
    lw    $t1, 0x1814($t0)
    nop
    lui   $t2, 0x0400
    and   $t1, $t1, $t2
    beqz  $t1, gc_wait
    nop
    andi  $t1, $a0, 0xFF        ; blue
    sll   $t1, $t1, 16
    andi  $t2, $a0, 0xFF00      ; green
    or    $t1, $t1, $t2
    srl   $t2, $a0, 16
    andi  $t2, $t2, 0xFF        ; red
    or    $t1, $t1, $t2
    lui   $t4, 0x0200
    or    $t1, $t1, $t4         ; 02h | 0xBBGGRR
    sw    $t1, 0x1810($t0)
    sll   $t2, $a2, 16
    or    $t2, $t2, $a1
    sw    $t2, 0x1810($t0)      ; y << 16 | x
    sll   $t3, $t3, 16
    or    $t3, $t3, $a3
    sw    $t3, 0x1810($t0)      ; h << 16 | w
    jr    $ra
    nop

gpu_wait:                       ; returns when the GPU can take a command word (leaf: $t0-$t2 only)
    lui   $t0, 0x1F80
    lui   $t2, 0x0400
gw_loop:
    lw    $t1, 0x1814($t0)
    nop
    and   $t1, $t1, $t2
    beqz  $t1, gw_loop
    nop
    jr    $ra
    nop

pack_color:                     ; (color, cmd) -> (cmd << 24) | 0x00BBGGRR   (leaf)
    andi  $t1, $a0, 0xFF        ; blue
    sll   $t1, $t1, 16
    andi  $t2, $a0, 0xFF00      ; green
    or    $t1, $t1, $t2
    srl   $t2, $a0, 16
    andi  $t2, $t2, 0xFF        ; red
    or    $t1, $t1, $t2
    andi  $t3, $a1, 0xFF
    sll   $t3, $t3, 24
    jr    $ra
    or    $v0, $t1, $t3

pack_vertex:                    ; (x, y) -> (y << 16) | (x & 0xFFFF)   (leaf)
    andi  $t0, $a0, 0xFFFF
    sll   $t1, $a1, 16
    jr    $ra
    or    $v0, $t0, $t1
routines_end:

; ---- data -------------------------------------------------------------------------------------------------
.align 4
; The scene: a low-poly landscape. The verifier replaces this whole table (up to SCENE_MAX entries).
; Layout: count, background color, then `count` entries of 8 words (32 bytes):
;     type, color0, color1, color2, vertex0, vertex1, vertex2, vertex3
; Vertices are packed words (y << 16) | (x & 0xFFFF), absolute screen coordinates (drawing offset 0).
; Unused fields are 0. Polygons are drawn in table order, so later ones paint over earlier ones.
scene:
    .word 23                         ; polygon count
    .word 0x6090D0                      ; background color (sky)
    ; sun
    .word T_FLAT_QUAD, 0xFFE080, 0x000000, 0x000000
    vtx 250,15 :: vtx 275,40 :: vtx 225,40 :: vtx 250,65
    ; cloud
    .word T_FLAT_QUAD, 0xF0F4FF, 0x000000, 0x000000
    vtx 45,30 :: vtx 85,30 :: vtx 30,50 :: vtx 100,50
    ; cloud
    .word T_FLAT_QUAD, 0xE8ECFA, 0x000000, 0x000000
    vtx 150,45 :: vtx 190,45 :: vtx 140,60 :: vtx 200,60
    ; far mountain
    .word T_FLAT_TRI, 0x405080, 0x000000, 0x000000
    vtx 0,150 :: vtx 60,90 :: vtx 130,150 :: .word 0
    ; far mountain
    .word T_FLAT_TRI, 0x4A5C90, 0x000000, 0x000000
    vtx 90,150 :: vtx 170,70 :: vtx 250,150 :: .word 0
    ; far mountain
    .word T_FLAT_TRI, 0x405080, 0x000000, 0x000000
    vtx 200,150 :: vtx 265,95 :: vtx 319,150 :: .word 0
    ; snow cap
    .word T_FLAT_TRI, 0xF0F0FF, 0x000000, 0x000000
    vtx 60,90 :: vtx 50,102 :: vtx 70,102 :: .word 0
    ; snow cap
    .word T_FLAT_TRI, 0xF0F0FF, 0x000000, 0x000000
    vtx 170,70 :: vtx 155,95 :: vtx 185,95 :: .word 0
    ; snow cap
    .word T_FLAT_TRI, 0xF0F0FF, 0x000000, 0x000000
    vtx 265,95 :: vtx 255,107 :: vtx 274,107 :: .word 0
    ; meadow
    .word T_FLAT_QUAD, 0x3A8A3A, 0x000000, 0x000000
    vtx 0,150 :: vtx 319,150 :: vtx 0,239 :: vtx 319,239
    ; hill
    .word T_GOURAUD_TRI, 0x80E070, 0x2A7A2A, 0x2A7A2A
    vtx 70,165 :: vtx 170,239 :: vtx 0,239 :: .word 0
    ; hill
    .word T_GOURAUD_TRI, 0x90E070, 0x2A7A2A, 0x2A7A2A
    vtx 240,175 :: vtx 319,239 :: vtx 150,239 :: .word 0
    ; lake
    .word T_FLAT_QUAD, 0x3070C0, 0x000000, 0x000000
    vtx 110,185 :: vtx 200,185 :: vtx 95,205 :: vtx 215,205
    ; glint
    .word T_FLAT_TRI, 0x80B0F0, 0x000000, 0x000000
    vtx 140,190 :: vtx 160,190 :: vtx 150,200 :: .word 0
    ; road
    .word T_GOURAUD_TRI, 0xC0A070, 0x806040, 0x806040
    vtx 160,210 :: vtx 230,239 :: vtx 110,239 :: .word 0
    ; house wall
    .word T_FLAT_QUAD, 0xD0C090, 0x000000, 0x000000
    vtx 205,190 :: vtx 235,190 :: vtx 205,212 :: vtx 235,212
    ; house roof
    .word T_FLAT_TRI, 0xA03030, 0x000000, 0x000000
    vtx 220,172 :: vtx 243,190 :: vtx 197,190 :: .word 0
    ; tree trunk
    .word T_FLAT_QUAD, 0x704020, 0x000000, 0x000000
    vtx 36,200 :: vtx 42,200 :: vtx 36,225 :: vtx 42,225
    ; tree foliage
    .word T_FLAT_TRI, 0x1A5A1A, 0x000000, 0x000000
    vtx 39,165 :: vtx 52,205 :: vtx 26,205 :: .word 0
    ; tree top
    .word T_GOURAUD_TRI, 0x60C060, 0x1A5A1A, 0x1A5A1A
    vtx 39,150 :: vtx 55,185 :: vtx 23,185 :: .word 0
    ; tree trunk
    .word T_FLAT_QUAD, 0x704020, 0x000000, 0x000000
    vtx 267,200 :: vtx 273,200 :: vtx 267,226 :: vtx 273,226
    ; tree foliage
    .word T_FLAT_TRI, 0x1A5A1A, 0x000000, 0x000000
    vtx 270,168 :: vtx 284,205 :: vtx 256,205 :: .word 0
    ; tree top
    .word T_GOURAUD_TRI, 0x60C060, 0x1A5A1A, 0x1A5A1A
    vtx 270,152 :: vtx 286,188 :: vtx 254,188 :: .word 0
    .fill (scene + 8 + SCENE_MAX * 32) - .      ; room for the verifier's longer scenes

.align 0x800
__exe_end:
.close
