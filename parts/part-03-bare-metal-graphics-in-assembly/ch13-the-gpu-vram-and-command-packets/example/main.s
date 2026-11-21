; Chapter 13 example -- fill rectangle vs monochrome rectangle (not checked by verify.sh)
;
; Predict the picture before you run it (make run). All four packets ask for a 20x20 box,
; at x = 8 or x = 290. The drawing area is 0..299 x 0..239: 20 columns narrower than the screen.
;   row 1: GP0(02h) fill rectangle,       x = 8   -> which columns are painted?
;   row 2: GP0(60h) monochrome rectangle, x = 8   -> which columns?
;   row 3: GP0(60h) monochrome rectangle, x = 290 -> what happens at the edge of the drawing area?
;   row 4: GP0(02h) fill rectangle,       x = 290 -> and here?
; (No GPUSTAT wait: four small packets fit in the GPU's 16-word FIFO.)

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

main:
    lui   $t0, 0x1F80               ; GP0 = 0x1810($t0), GP1 = 0x1814($t0)
    sw    $zero, 0x1814($t0)        ; reset
    li    $t1, 0x03000000
    sw    $t1, 0x1814($t0)          ; display on
    li    $t1, 0x06C60260
    sw    $t1, 0x1814($t0)
    li    $t1, 0x07040010
    sw    $t1, 0x1814($t0)
    li    $t1, 0x08000001
    sw    $t1, 0x1814($t0)          ; 320x240 NTSC 15-bit
    li    $t1, 0xE1000400
    sw    $t1, 0x1810($t0)          ; draw mode: drawing to the display area allowed
    li    $t1, 0xE3000000
    sw    $t1, 0x1810($t0)
    li    $t1, 0xE4000000 | (239 << 10) | 299
    sw    $t1, 0x1810($t0)          ; drawing area 0,0 - 299,239
    li    $t1, 0xE5000000
    sw    $t1, 0x1810($t0)

    la    $t2, packets
    la    $t3, packets_end
send:
    lw    $t1, 0($t2)
    addiu $t2, $t2, 4
    sw    $t1, 0x1810($t0)
    bne   $t2, $t3, send
    nop

done:
    j     done
    nop

.align 4
packets:                            ; color (BBGGRR), (y << 16) | x, (h << 16) | w
    .word 0x02FFFF00, (20 << 16) | 8,   (20 << 16) | 20     ; fill, cyan
    .word 0x6000FF00, (60 << 16) | 8,   (20 << 16) | 20     ; rect, green
    .word 0x600000FF, (100 << 16) | 290, (20 << 16) | 20    ; rect, red
    .word 0x0200FFFF, (140 << 16) | 290, (20 << 16) | 20    ; fill, yellow
packets_end:

.align 0x800
__exe_end:
.close
