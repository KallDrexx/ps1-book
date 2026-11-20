; Chapter 16 -- "Picture Show" (starter)
;
; You write:
;   vram_upload(ptr, x, y, w, h)    GP0 A0h: copy a w*h rectangle of 16-bit units from RAM (ptr) to VRAM at (x, y).
;                                   5 arguments: h is at 16($sp). ptr is word-aligned; the data is row-major, 2 bytes per unit,
;                                   w*h units, padded to a whole word. Wait for the GPU ONCE, send the 3 header words, then
;                                   exactly (w*h + 1) / 2 data words, with NO GPUSTAT polling in between (bit 26 reads 0 there).
;                                   Keep x + w <= 1024 and y + h <= 512 (no wrapping). $s0-$s7, $gp, $fp, $sp preserved.
;   bpp24_halfwords(px)             width of a 24-bpp line in VRAM units: px * 3 / 2 (px even). Shifts and adds only.
;   main                            mode 0: gpu_init, fill 320x240 with BG_COLOR, upload img16 at (img16_x, img16_y), size img16_w x img16_h
;                                   mode 1: gpu_init, GP1(08h) = 24-bit mode, upload img24 (320 x 240 pixels) at (0, 0)
;                                   `mode` is a data word: edit it to try part 2; the verifier patches it. Read the sizes from the table.
;
; Given: gpu_init, gpu_clear, gpu_wait (Chapters 13-15) and the data block at the bottom (the images come from img16.bin/img24.bin).

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

.definelabel GP0, 0x1F801810
.definelabel GP1, 0x1F801814
.definelabel BG_COLOR, 0x303038         ; 0x00RRGGBB, mode 0 background

; ---- your routines ------------------------------------------------------------------------------------------
vram_upload:
    ; TODO: wait for bit 26 once; send 0xA0000000, (y << 16) | x, (h << 16) | w; then (w*h + 1) / 2 data words from ptr.
    jr    $ra
    nop

bpp24_halfwords:
    ; TODO: return px + (px >> 1) in $v0
    jr    $ra
    move  $v0, $zero

; ---- main ---------------------------------------------------------------------------------------------------
main:
    addiu $sp, $sp, -32             ; room for the outgoing 5th argument at 16($sp)
    jal   gpu_init
    nop
    ; TODO: lw $t0, mode; part 1 (mode 0): gpu_clear, then vram_upload the 16-bpp picture
    ;                     part 2 (mode 1): GP1(08h) 0x08000011, width in units from bpp24_halfwords, vram_upload the 24-bit picture

done:
    j     done
    nop

; ---- given routines (Chapters 13-15) ------------------------------------------------------------------------
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
