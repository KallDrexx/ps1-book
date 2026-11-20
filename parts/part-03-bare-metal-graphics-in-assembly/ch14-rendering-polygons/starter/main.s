; Chapter 14 -- "Polygon Gallery" (starter)
;
;   gpu_init()                      given (Chapter 13): 320x240 NTSC 15-bit display, drawing area, offset 0
;   gpu_clear(color, x, y, w, h)    given (Chapter 13): GP0(02h) fill; h at 16($sp)
;   gpu_wait()                      given: loop until GPUSTAT bit 26 is set
;   pack_color(color, cmd)  -> v0   0x00RRGGBB and a command byte -> (cmd << 24) | 0x00BBGGRR
;   pack_vertex(x, y)       -> v0   two signed numbers -> (y << 16) | (x & 0xFFFF)
;   The two pack_ routines are leaf routines: $t, $a, $v only.
;
; main (section 7): gpu_init; gpu_clear the whole screen with bg_color; set the drawing offset to `origin`;
; then draw the four polygons of the gallery from the tables below, in this order:
;   flat triangle (20h), flat quad (28h), Gouraud triangle (30h), Gouraud quad (38h).
; Vertex coordinates in the tables are relative to `origin` (the GPU adds the drawing offset).

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

.definelabel GP0, 0x1F801810        ; GPU command / data port (write), GPUREAD (read)
.definelabel GP1, 0x1F801814        ; GPU control port (write), GPUSTAT (read)

main:
    addiu $sp, $sp, -32
    sw    $ra, 28($sp)
    ; TODO: gpu_init; gpu_clear the whole screen with bg_color (as in Chapter 13);
    ;   send GP0(E5h) with the drawing offset taken from `origin`;
    ;   then one packet each: flat triangle, flat quad, Gouraud triangle, Gouraud quad,
    ;   with the words read from the tables at the bottom (wait for GPUSTAT bit 26 before each packet).

done:
    j     done                      ; the verifier stops here
    nop

; ---- your routines ----------------------------------------------------------
pack_color:                     ; (color = $a0, cmd = $a1) -> $v0 = (cmd << 24) | 0x00BBGGRR
    ; TODO
    jr    $ra
    nop

pack_vertex:                    ; (x = $a0, y = $a1) -> $v0 = (y << 16) | (x & 0xFFFF)
    ; TODO
    jr    $ra
    nop

; ---- given routines (from Chapter 13) ---------------------------------------
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

gpu_clear:                      ; fill rectangle: GP0(02h), the colour is 0x00RRGGBB
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

gpu_wait:                       ; returns when the GPU can take a command word
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

; ---- data: the gallery (the verifier patches every table below) --------------
; Colours are 0x00RRGGBB words, coordinates are signed 32-bit words, relative to `origin`.
.align 4
origin:     .word 160, 120                  ; drawing offset: x, y
bg_color:   .word 0x181830
flat_tri:                                   ; colour, then x0 y0, x1 y1, x2 y2
    .word 0xFFA000
    .word -90, -100,  -30, -20,  -150, -20
flat_quad:                                  ; colour, then v1 v2 / v3 v4 (Z order)
    .word 0x20C0A0
    .word 30, -100,  140, -90,  20, -20,  130, -15
gouraud_tri:                                ; colour0, x0 y0, colour1, x1 y1, colour2, x2 y2
    .word 0xFF0000, -90, 10
    .word 0x00FF00, -30, 95
    .word 0x0000FF, -150, 95
gouraud_quad:                               ; colour, x y   for v1, v2, v3, v4
    .word 0xFF0000, 30, 10
    .word 0xFFFF00, 140, 10
    .word 0x0000FF, 30, 95
    .word 0xFFFFFF, 140, 95

.align 0x800
__exe_end:
.close
