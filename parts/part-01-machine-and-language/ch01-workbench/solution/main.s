; Chapter 1 -- "hello, VRAM"
; Fills the whole screen with one flat colour, then idles forever.
;
; YOUR JOB: change the three colour constants below, rebuild, and write the
; same colour into color.txt (as RRGGBB hex).

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

; ---- colour (0-255 each) -- edit these -------------------------------------
.definelabel RED,   0xE0
.definelabel GREEN, 0x50
.definelabel BLUE,  0x10
; ----------------------------------------------------------------------------

.definelabel GP0, 0x1F801810        ; GPU command / data port
.definelabel GP1, 0x1F801814        ; GPU control port

main:
    li   $t0, GP0
    li   $t1, GP1

    sw   $zero, 0($t1)              ; GP1(00h) reset the GPU
    li   $t2, 0x03000000
    sw   $t2, 0($t1)                ; GP1(03h) display enable
    li   $t2, 0x08000001
    sw   $t2, 0($t1)                ; GP1(08h) display mode: 320x240, NTSC, 15-bit
    li   $t2, 0x05000000
    sw   $t2, 0($t1)                ; GP1(05h) display area starts at VRAM (0,0)
    li   $t2, 0x06C60260
    sw   $t2, 0($t1)                ; GP1(06h) horizontal display range
    li   $t2, 0x07040010
    sw   $t2, 0($t1)                ; GP1(07h) vertical display range

    li   $t2, 0x02000000 | (BLUE << 16) | (GREEN << 8) | RED
    sw   $t2, 0($t0)                ; GP0(02h) fill rectangle: command + colour
    li   $t2, 0x00000000
    sw   $t2, 0($t0)                ;   top-left corner  (y << 16 | x)
    li   $t2, 0x00F00140
    sw   $t2, 0($t0)                ;   size (height << 16 | width) = 320 x 240

done:
    j    done                       ; the verifier stops here
    nop

.align 0x800
__exe_end:
.close
