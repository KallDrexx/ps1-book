; Chapter 13 -- "Colour Bars" (solution)
;
;   gpu_init()                       set up a 320x240 NTSC 15-bit display and the drawing area
;   gpu_clear(color, x, y, w, h)     GP0(02h) fill rectangle      (a0..a3, h at 16($sp))
;   gpu_rect (color, x, y, w, h)     GP0(60h) monochrome rectangle (same arguments)
;   color is 0x00RRGGBB (bits 31-24 ignored). Leaf routines: $t, $a, $v only.

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

.definelabel GP0, 0x1F801810
.definelabel GP1, 0x1F801814

main:
    addiu $sp, $sp, -24
    sw    $ra, 20($sp)

    jal   gpu_init
    nop

    la    $t0, bg_color
    lw    $a0, 0($t0)           ; clear the whole display to the border colour
    move  $a1, $zero
    move  $a2, $zero
    li    $a3, 320
    li    $t0, 240
    jal   gpu_clear
    sw    $t0, 16($sp)          ; 5th argument (delay slot)

    la    $s1, bar_colors
    li    $s2, 0                ; x of the current bar
bar_loop:
    lw    $a0, 0($s1)
    move  $a1, $s2
    li    $a2, 24
    li    $a3, 40
    li    $t0, 192
    jal   gpu_rect
    sw    $t0, 16($sp)
    addiu $s1, $s1, 4
    addiu $s2, $s2, 40
    slti  $t0, $s2, 320
    bnez  $t0, bar_loop
    nop

done:
    j     done
    nop

; ---- routines ---------------------------------------------------------------
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
    sw    $t1, 0x1810($t0)      ; GP0(E1h) draw mode: drawing to the display area allowed
    li    $t1, 0xE3000000
    sw    $t1, 0x1810($t0)      ; GP0(E3h) drawing area top-left (0,0)
    li    $t1, 0xE4000000 | (239 << 10) | 319
    sw    $t1, 0x1810($t0)      ; GP0(E4h) drawing area bottom-right (319,239)
    li    $t1, 0xE5000000
    sw    $t1, 0x1810($t0)      ; GP0(E5h) drawing offset (0,0)
    jr    $ra
    nop

gpu_clear:                      ; fill rectangle: command 02h
    lui   $t4, 0x0200
    j     gpu_cmd
    nop

gpu_rect:                       ; monochrome rectangle, variable size: command 60h
    lui   $t4, 0x6000
gpu_cmd:                        ; shared tail: $t4 = command byte << 24
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
    or    $t1, $t1, $t4         ; command | 0xBBGGRR
    sw    $t1, 0x1810($t0)
    sll   $t2, $a2, 16
    or    $t2, $t2, $a1
    sw    $t2, 0x1810($t0)      ; y << 16 | x
    sll   $t3, $t3, 16
    or    $t3, $t3, $a3
    sw    $t3, 0x1810($t0)      ; h << 16 | w
    jr    $ra
    nop
routines_end:

; ---- data -------------------------------------------------------------------
.align 4
bg_color:   .word 0x202020
bar_colors:
    .word 0xFFFFFF, 0xFFFF00, 0x00FFFF, 0x00FF00
    .word 0xFF00FF, 0xFF0000, 0x0000FF, 0x808080

.align 0x800
__exe_end:
.close
