; Chapter 15 -- "Low-Poly Landscape" (solution)
;
;   draw_flat_tri(color, x0,y0, x1,y1, x2,y2)                      7 arguments: 4 in $a0-$a3, 3 on the stack
;   draw_flat_quad(color, x0,y0, x1,y1, x2,y2, x3,y3)              9 arguments: 4 in $a0-$a3, 5 on the stack
;   draw_gouraud_tri(c0,x0,y0, c1,x1,y1, c2,x2,y2)                 9 arguments: 4 in $a0-$a3, 5 on the stack
;   Colours are 0x00RRGGBB, coordinates signed numbers; vertices go to the GPU in the order given.
;   Each routine waits for the GPU once, then sends ONE packet; $s0-$s7, $gp, $fp and $sp are preserved.
;
; main: gpu_init, clear the screen with the scene's background colour, then draw every entry of `scene`
; (see the table at the bottom) in order, calling the routine its type names.

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

; Incoming argument i is at 4*i($sp) of the CALLER's frame. After our prologue (frame F = 24)
; and spilling $a0-$a3 into the caller's home area, argument i is at (24 + 4*i)($sp), for every i.
.macro prologue
    addiu $sp, $sp, -24
    sw    $ra, 20($sp)
    sw    $a0, 24($sp)          ; spill a0-a3 into the home area the caller reserved:
    sw    $a1, 28($sp)          ; now the arguments form one array, args[i] = (24 + 4*i)($sp)
    sw    $a2, 32($sp)
    sw    $a3, 36($sp)
    jal   gpu_wait              ; the one wait for this packet
    nop
.endmacro
.macro epilogue
    lw    $ra, 20($sp)
    addiu $sp, $sp, 24
    jr    $ra
    nop
.endmacro
.macro send_color,off,cmd       ; GP0 <- pack_color(args[...], cmd)
    lw    $a0, off($sp)
    jal   pack_color
    li    $a1, cmd
    lui   $t0, 0x1F80
    sw    $v0, 0x1810($t0)
.endmacro
.macro send_vertex,xoff,yoff    ; GP0 <- pack_vertex(x, y)
    lw    $a0, xoff($sp)
    lw    $a1, yoff($sp)
    jal   pack_vertex
    nop
    lui   $t0, 0x1F80
    sw    $v0, 0x1810($t0)
.endmacro

draw_flat_tri:                  ; args: color 24, x0 28, y0 32, x1 36, y1 40, x2 44, y2 48
    prologue
    send_color 24, 0x20
    send_vertex 28, 32
    send_vertex 36, 40
    send_vertex 44, 48
    epilogue

draw_flat_quad:                 ; args: color 24, x0 28, y0 32, x1 36, y1 40, x2 44, y2 48, x3 52, y3 56
    prologue
    send_color 24, 0x28
    send_vertex 28, 32
    send_vertex 36, 40
    send_vertex 44, 48
    send_vertex 52, 56
    epilogue

draw_gouraud_tri:               ; args: c0 24, x0 28, y0 32, c1 36, x1 40, y1 44, c2 48, x2 52, y2 56
    prologue
    send_color 24, 0x30
    send_vertex 28, 32
    send_color 36, 0
    send_vertex 40, 44
    send_color 48, 0
    send_vertex 52, 56
    epilogue

; ---- main: draw the scene -------------------------------------------------------------------------------
; unpack a vertex word into signed x and y registers
.macro unpack_x,dst,src
    sll   dst, src, 16
    sra   dst, dst, 16
.endmacro
.macro unpack_y,dst,src
    sra   dst, src, 16
.endmacro

main:
    addiu $sp, $sp, -48         ; 16 outgoing home area + up to 5 stack arguments (16..32) + $ra, $s0, $s1
    sw    $ra, 44($sp)
    sw    $s0, 40($sp)
    sw    $s1, 36($sp)
    jal   gpu_init
    nop
    la    $t0, scene
    lw    $a0, 4($t0)           ; background colour
    move  $a1, $zero
    move  $a2, $zero
    li    $a3, 320
    li    $t1, 240
    jal   gpu_clear
    sw    $t1, 16($sp)          ; 5th argument (delay slot)
    la    $s0, scene
    lw    $s1, 0($s0)           ; polygon count
    addiu $s0, $s0, 8           ; first entry
next_entry:
    beqz  $s1, done
    nop
    lw    $t0, 0($s0)           ; type
    lw    $t1, 16($s0)          ; packed vertices v0..v3
    lw    $t2, 20($s0)
    lw    $t3, 24($s0)
    lw    $t4, 28($s0)
    beqz  $t0, do_flat_tri
    li    $t5, T_FLAT_QUAD
    beq   $t0, $t5, do_flat_quad
    nop

do_gouraud_tri:                 ; (c0, x0,y0, c1, x1,y1, c2, x2,y2)
    lw    $a0, 4($s0)
    unpack_x $a1, $t1
    unpack_y $a2, $t1
    lw    $a3, 8($s0)
    unpack_x $t5, $t2
    sw    $t5, 16($sp)          ; x1
    unpack_y $t5, $t2
    sw    $t5, 20($sp)          ; y1
    lw    $t5, 12($s0)
    nop
    sw    $t5, 24($sp)          ; c2
    unpack_x $t5, $t3
    sw    $t5, 28($sp)          ; x2
    unpack_y $t5, $t3
    sw    $t5, 32($sp)          ; y2
    jal   draw_gouraud_tri
    nop
    j     entry_done
    nop

do_flat_tri:                    ; (color, x0,y0, x1,y1, x2,y2)
    lw    $a0, 4($s0)
    unpack_x $a1, $t1
    unpack_y $a2, $t1
    unpack_x $a3, $t2
    unpack_y $t5, $t2
    sw    $t5, 16($sp)          ; y1
    unpack_x $t5, $t3
    sw    $t5, 20($sp)          ; x2
    unpack_y $t5, $t3
    sw    $t5, 24($sp)          ; y2
    jal   draw_flat_tri
    nop
    j     entry_done
    nop

do_flat_quad:                   ; (color, x0,y0, x1,y1, x2,y2, x3,y3)
    lw    $a0, 4($s0)
    unpack_x $a1, $t1
    unpack_y $a2, $t1
    unpack_x $a3, $t2
    unpack_y $t5, $t2
    sw    $t5, 16($sp)          ; y1
    unpack_x $t5, $t3
    sw    $t5, 20($sp)          ; x2
    unpack_y $t5, $t3
    sw    $t5, 24($sp)          ; y2
    unpack_x $t5, $t4
    sw    $t5, 28($sp)          ; x3
    unpack_y $t5, $t4
    sw    $t5, 32($sp)          ; y3
    jal   draw_flat_quad
    nop

entry_done:
    addiu $s0, $s0, 32
    j     next_entry
    addiu $s1, $s1, -1

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

gpu_clear:                      ; fill rectangle: GP0(02h), the colour is 0x00RRGGBB; h is the 5th argument, 16($sp)
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
; Layout: count, background colour, then `count` entries of 8 words (32 bytes):
;     type, colour0, colour1, colour2, vertex0, vertex1, vertex2, vertex3
; Vertices are packed words (y << 16) | (x & 0xFFFF), absolute screen coordinates (drawing offset 0).
; Unused fields are 0. Polygons are drawn in table order, so later ones paint over earlier ones.
scene:
    .word 23                         ; polygon count
    .word 0x6090D0                      ; background colour (sky)
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
