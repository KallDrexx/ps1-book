; Chapter 15 example -- a six-argument routine: draw_gradient_bar(c0, c1, x, y, w, h)   (not checked by verify.sh)
;
;   $a0 = c0   $a1 = c1   $a2 = x   $a3 = y        4 arguments in registers
;   16($sp) = w   20($sp) = h                      2 arguments on the stack (as seen at entry)
;
; It draws one Gouraud quad (38h): c0 down the left edge, c1 down the right edge.
; The routine spills $a0-$a3 into the caller's home area, so all six arguments form one array:
;     args[i] = (FRAME + 4*i)($sp)        with FRAME = 24:   c0 24, c1 28, x 32, y 36, w 40, h 44
; main draws three bars; each call stores w and h at 16($sp) and 20($sp) first.
; Predict the picture: bar 1 red to blue, bar 2 black to white, bar 3 green to yellow, all 100 wide, stacked.

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

.definelabel GP0, 0x1F801810        ; GPU command / data port (write), GPUREAD (read)
.definelabel GP1, 0x1F801814        ; GPU control port (write), GPUSTAT (read)

.macro send,reg                 ; write a word to GP0
    lui   $t0, 0x1F80
    sw    reg, 0x1810($t0)
.endmacro
.macro send_color,off,cmd
    lw    $a0, off($sp)
    jal   pack_color
    li    $a1, cmd
    send  $v0
.endmacro

draw_gradient_bar:
    addiu $sp, $sp, -24         ; 16 (home area for our callees) + 4 ($ra), rounded up to a multiple of 8
    sw    $ra, 20($sp)
    sw    $a0, 24($sp)          ; the caller's home area: args[0..3]
    sw    $a1, 28($sp)
    sw    $a2, 32($sp)
    sw    $a3, 36($sp)
    jal   gpu_wait
    nop
    send_color 24, 0x38         ; c0 with the command byte
    lw    $a0, 32($sp)          ; v0 = (x, y)
    lw    $a1, 36($sp)
    jal   pack_vertex
    nop
    send  $v0
    send_color 28, 0            ; c1
    lw    $t1, 40($sp)          ; v1 = (x + w, y); args[4] = w, read from the caller's frame
    lw    $a0, 32($sp)
    lw    $a1, 36($sp)
    addu  $a0, $a0, $t1
    jal   pack_vertex
    nop
    send  $v0
    send_color 24, 0            ; c0
    lw    $a1, 36($sp)          ; v2 = (x, y + h); args[5] = h
    lw    $t1, 44($sp)
    lw    $a0, 32($sp)
    addu  $a1, $a1, $t1
    jal   pack_vertex
    nop
    send  $v0
    send_color 28, 0            ; c1
    lw    $t1, 40($sp)          ; v3 = (x + w, y + h)
    lw    $t2, 44($sp)
    lw    $a0, 32($sp)
    lw    $a1, 36($sp)
    addu  $a0, $a0, $t1
    addu  $a1, $a1, $t2
    jal   pack_vertex
    nop
    send  $v0
    lw    $ra, 20($sp)
    addiu $sp, $sp, 24
    jr    $ra
    nop

main:
    addiu $sp, $sp, -32         ; home area 0..15, two stack arguments 16..23, $ra at 24: 28, rounded up to 32
    sw    $ra, 24($sp)          ; (NOT 20: that is where h goes)
    jal   gpu_init
    nop
    li    $a0, 0x202030         ; clear to dark gray
    move  $a1, $zero
    move  $a2, $zero
    li    $a3, 320
    li    $t0, 240
    jal   gpu_clear
    sw    $t0, 16($sp)

    li    $t0, 100
    sw    $t0, 16($sp)          ; w
    li    $t0, 40
    sw    $t0, 20($sp)          ; h
    li    $a0, 0xFF0000
    li    $a1, 0x0000FF
    li    $a2, 110
    jal   draw_gradient_bar
    li    $a3, 20
    li    $a0, 0x000000
    li    $a1, 0xFFFFFF
    li    $a2, 110
    jal   draw_gradient_bar
    li    $a3, 80
    li    $a0, 0x00FF00
    li    $a1, 0xFFFF00
    li    $a2, 110
    jal   draw_gradient_bar
    li    $a3, 140
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

.align 0x800
__exe_end:
.close
