; Chapter 16 -- worked example: a checkerboard made on the fly and sent to VRAM with GP0 A0h.
;
; 16x16 pixels = 256 units = 128 words, computed in a loop (no image file needed) and written straight to GP0.
; Cells are 4x4 pixels, alternating white and red. Destination: (152, 112), the middle of the 320x240 screen.
; Not checked by verify.sh.

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

main:
    jal   gpu_init
    nop
    lui   $t0, 0x1F80               ; I/O base: GP0 = 0x1810($t0), GPUSTAT = 0x1814($t0)
    lui   $t5, 0x0400               ; GPUSTAT bit 26: ready to receive a command word
ex_wait:
    lw    $t1, 0x1814($t0)
    nop
    and   $t1, $t1, $t5
    beqz  $t1, ex_wait
    nop
    lui   $t1, 0xA000
    sw    $t1, 0x1810($t0)          ; word 1: A0h, copy rectangle CPU -> VRAM
    li    $t1, (112 << 16) | 152
    sw    $t1, 0x1810($t0)          ; word 2: destination, y << 16 | x
    li    $t1, (16 << 16) | 16
    sw    $t1, 0x1810($t0)          ; word 3: size, h << 16 | w
    li    $t6, 0x7FFF7FFF           ; two white pixels (BGR555 0x7FFF, bit 15 clear)
    li    $t7, 0x001F001F           ; two red pixels
    move  $t2, $zero                ; pixel row 0..15
ex_row:
    move  $t3, $zero                ; cell 0..3 in this row
ex_cell:
    srl   $t4, $t2, 2               ; cell row = row / 4
    addu  $t4, $t4, $t3
    andi  $t4, $t4, 1               ; checker colour
    beqz  $t4, ex_white
    move  $t1, $t6
    move  $t1, $t7
ex_white:
    sw    $t1, 0x1810($t0)          ; one cell = 4 pixels = 2 words: no waiting inside the data
    sw    $t1, 0x1810($t0)
    addiu $t3, $t3, 1
    slti  $t4, $t3, 4
    bnez  $t4, ex_cell
    nop
    addiu $t2, $t2, 1
    slti  $t4, $t2, 16
    bnez  $t4, ex_row
    nop

done:
    j     done
    nop

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


.align 0x800
__exe_end:
.close
