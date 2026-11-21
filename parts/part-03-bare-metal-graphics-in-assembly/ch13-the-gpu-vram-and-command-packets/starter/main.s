; Chapter 13 -- "Color Bars" (starter)
;
;   gpu_init()                       set up a 320x240 NTSC 15-bit display and the drawing area
;   gpu_clear(color, x, y, w, h)     GP0(02h) fill rectangle       color=$a0 x=$a1 y=$a2 w=$a3, h at 16($sp)
;   gpu_rect (color, x, y, w, h)     GP0(60h) monochrome rectangle (same arguments)
;   color is 0x00RRGGBB (bits 31-24 ignored; the GPU wants 0xBBGGRR). Leaf routines: $t, $a, $v only.
;
; main (section 7): gpu_init; gpu_clear the whole 320x240 display with bg_color;
; then 8 bars, one gpu_rect each, from bar_colors: bar i at x = 40*i, y = 24, 40 wide, 192 high.

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

.definelabel GP0, 0x1F801810        ; GPU command / data port (write), GPUREAD (read)
.definelabel GP1, 0x1F801814        ; GPU control port (write), GPUSTAT (read)

main:
    ; TODO: make room on the stack (arguments for the callee + saved $ra), then
    ;   gpu_init, gpu_clear(bg_color, 0, 0, 320, 240), and a loop of 8 gpu_rect calls
    ;   reading the colors from bar_colors.

done:
    j     done                      ; the verifier stops here
    nop

; ---- your routines ----------------------------------------------------------
gpu_init:
    lui   $t0, 0x1F80               ; $t0 = 0x1F800000: GP0 = 0x1810($t0), GP1 = 0x1814($t0)
    sw    $zero, 0x1814($t0)        ; GP1(00h) reset
    ; TODO: display on, display start, horizontal/vertical range, display mode (GP1);
    ;       wait for GPUSTAT bit 26; then draw mode, drawing area, drawing offset (GP0 E1h-E5h)
    jr    $ra
    nop

gpu_clear:                          ; fill rectangle (command 02h)
    ; TODO
    jr    $ra
    nop

gpu_rect:                           ; monochrome rectangle, variable size (command 60h)
    ; TODO
    jr    $ra
    nop
routines_end:

; ---- data (the verifier patches these two tables, so read them from memory) --
.align 4
bg_color:   .word 0x202020
bar_colors:
    .word 0xFFFFFF, 0xFFFF00, 0x00FFFF, 0x00FF00
    .word 0xFF00FF, 0xFF0000, 0x0000FF, 0x808080

.align 0x800
__exe_end:
.close
