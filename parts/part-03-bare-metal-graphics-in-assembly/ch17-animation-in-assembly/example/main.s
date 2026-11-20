; Chapter 17 -- worked example: one thing per VBlank
;
; A white vertical line, 2 pixels wide, is drawn at x = 2 * (n mod 160) on VBlank number n: it sweeps across the screen
; in 160 frames (about 2.7 s) and leaves a trail. When it wraps, the screen is cleared. There is no double buffering:
; the example only shows VBlank polling and a frame counter. Predict the picture, then run: make run

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

main:
    jal   gpu_init
    move  $s0, $zero            ; $s0 = frame counter
loop:
    lui   $t0, 0x1F80
poll:                           ; wait until I_STAT bit 0 (VBlank) is set
    lw    $t1, 0x1070($t0)
    nop
    andi  $t1, $t1, 1
    beqz  $t1, poll
    nop
    li    $t1, -2
    sw    $t1, 0x1070($t0)      ; acknowledge: write 0 to bit 0, 1 elsewhere (leave other bits alone)
    li    $t2, 160
    divu  $s0, $t2
    mfhi  $s1                   ; n mod 160
    jal   gpu_wait
    nop
    lui   $t0, 0x1F80
    bnez  $s1, draw
    nop
    li    $t1, 0x02000000       ; wrapped: fill the screen black first
    sw    $t1, 0x1810($t0)
    sw    $zero, 0x1810($t0)
    li    $t1, (240 << 16) | 320
    sw    $t1, 0x1810($t0)
    jal   gpu_wait
    nop
    lui   $t0, 0x1F80
draw:
    li    $t1, 0x60FFFFFF       ; rectangle (60h), white
    sw    $t1, 0x1810($t0)
    sll   $t1, $s1, 1           ; x = 2 * (n mod 160)
    sw    $t1, 0x1810($t0)      ; y = 0
    li    $t1, (240 << 16) | 2  ; 2 wide, 240 high
    sw    $t1, 0x1810($t0)
    j     loop
    addiu $s0, $s0, 1

; ---- given routines (Chapters 13-15) ------------------------------------
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
