; Chapter 16 -- "Picture Show" (solution)
;
; vram_upload(ptr, x, y, w, h)       copy a w*h rectangle of 16-bit units from RAM to VRAM at (x, y)  [GP0 A0h]
; bpp24_halfwords(px)                width of a 24-bpp line in VRAM units: px * 3 / 2 (px even), shifts only
; main                               mode 0: 15-bit display, background fill, the 96x64 image in the middle
;                                    mode 1: 24-bit display, the 320x240 image full screen
;
; Given: gpu_init, gpu_clear, gpu_wait (Chapters 13-15) and the data block at the bottom.

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

.definelabel GP0, 0x1F801810
.definelabel GP1, 0x1F801814
.definelabel BG_COLOR, 0x303038         ; 0x00RRGGBB, mode 0 background

; ---- vram_upload(ptr, x, y, w, h): h is the 5th argument, 16($sp) ----------------------------------------
vram_upload:
    lw    $t3, 16($sp)              ; h
    lui   $t0, 0x1F80               ; I/O base
    lui   $t5, 0x0400               ; GPUSTAT bit 26 mask
    mult  $a3, $t3
    mflo  $t4                       ; w * h units
    addiu $t4, $t4, 1
    srl   $t4, $t4, 1               ; words = (units + 1) / 2
vu_w0:
    lw    $t1, 0x1814($t0)
    nop
    and   $t1, $t1, $t5
    beqz  $t1, vu_w0                ; wait: ready for a command word
    nop
    lui   $t1, 0xA000
    sw    $t1, 0x1810($t0)          ; A0h: copy rectangle CPU -> VRAM
    sll   $t2, $a2, 16
    or    $t2, $t2, $a1
    sw    $t2, 0x1810($t0)          ; destination: y << 16 | x
    sll   $t2, $t3, 16
    or    $t2, $t2, $a3
    sw    $t2, 0x1810($t0)          ; size: h << 16 | w
vu_loop:
    lw    $t1, 0($a0)
    addiu $a0, $a0, 4
    sw    $t1, 0x1810($t0)          ; two pixels
    addiu $t4, $t4, -1
    bnez  $t4, vu_loop
    nop
    jr    $ra
    nop

bpp24_halfwords:                    ; px even -> px * 3 / 2 = px + (px >> 1)
    srl   $t0, $a0, 1
    jr    $ra
    addu  $v0, $a0, $t0

; ---- main ---------------------------------------------------------------------------------------------------
main:
    addiu $sp, $sp, -32
    jal   gpu_init
    nop
    lw    $t0, mode
    nop
    bnez  $t0, part2
    nop

part1:                              ; 15-bit display: background, then the image
    li    $a0, BG_COLOR
    move  $a1, $zero
    move  $a2, $zero
    li    $a3, 320
    li    $t0, 240
    sw    $t0, 16($sp)
    jal   gpu_clear
    nop
    la    $a0, img16
    lw    $a1, img16_x
    lw    $a2, img16_y
    lw    $a3, img16_w
    lw    $t0, img16_h
    nop
    sw    $t0, 16($sp)
    jal   vram_upload
    nop
    j     finish
    nop

part2:                              ; 24-bit display: switch mode, then the whole screen
    lui   $t0, 0x1F80
    li    $t1, 0x08000011           ; GP1(08h): 320 wide, 240 high, NTSC, bit 4 = 24-bit colour
    sw    $t1, 0x1814($t0)
    lw    $a0, img24_w
    jal   bpp24_halfwords
    nop
    move  $a3, $v0                  ; width in 16-bit units: 480
    lw    $t0, img24_h
    la    $a0, img24
    move  $a1, $zero
    move  $a2, $zero
    sw    $t0, 16($sp)
    jal   vram_upload
    nop

finish:
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

routines_end:

; ---- data -----------------------------------------------------------------------------------------------------
.align 4
mode:       .word 0                 ; 0 = part 1 (16-bit), 1 = part 2 (24-bit); the verifier patches this
img16_x:    .word 112               ; where the 96x64 image goes in VRAM (centred on the 320x240 screen)
img16_y:    .word 88
img16_w:    .word 96                ; in pixels = 16-bit units
img16_h:    .word 64
img24_w:    .word 320               ; in pixels (a line is 480 units of VRAM)
img24_h:    .word 240
.align 4
img16:      .incbin "img16.bin"     ; 96*64*2 bytes, BGR555
.align 4
img24:      .incbin "img24.bin"     ; 320*240*3 bytes, R,G,B
.align 4
img_end:

.align 0x800
__exe_end:
.close
