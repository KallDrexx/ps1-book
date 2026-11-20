; Chapter 14 example -- polygon packets by hand (not checked by verify.sh)
;
; Predict the picture before you run it (make run).
;   top row:    two flat triangles (20h) with the SAME vertices in opposite order. Does the GPU cull one?
;   top right:  a Gouraud triangle (30h): red, green, blue corners.
;   middle:     an opaque orange band (28h), then four semi-transparent quads (2Ah) with the SAME colour,
;               one per semi-transparency mode (E1h bits 5-6 = 0, 1, 2, 3), each half over the band.
; The packets are one long word stream; the loop at the bottom sends it to GP0.
; (No GPUSTAT wait, to keep it short. Fine in PCSX-Redux, which runs each command at once; on real hardware a
;  stream this long can overflow the GPU's 16-word FIFO, which is why the project waits before every packet.)

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

.macro vtx,x,y                      ; one vertex word: (y << 16) | (x & 0xFFFF)
    .word ((y) << 16) | ((x) & 0xFFFF)
.endmacro

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
    sw    $t1, 0x1810($t0)          ; draw mode: drawing to the display area allowed, no dither
    li    $t1, 0xE3000000
    sw    $t1, 0x1810($t0)
    li    $t1, 0xE4000000 | (239 << 10) | 319
    sw    $t1, 0x1810($t0)
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
packets:
    .word 0x02404040                ; fill: grey background
    vtx 0, 0
    .word (240 << 16) | 320

    .word 0x200000FF                ; flat triangle, red; vertices left, right, bottom
    vtx 10, 10
    vtx 90, 10
    vtx 50, 70
    .word 0x200000FF                ; the same triangle, other order: left, bottom, right
    vtx 110, 10
    vtx 150, 70
    vtx 190, 10

    .word 0x30FF0000                ; Gouraud triangle: blue top-left ...
    vtx 210, 10
    .word 0x0000FF00                ; ... green top-right ...
    vtx 310, 10
    .word 0x000000FF                ; ... red bottom
    vtx 260, 70

    .word 0x28 << 24 | 0x2080C0     ; flat quad, orange (0xC08020 as RGB): Z order TL, TR, BL, BR
    vtx 0, 120
    vtx 320, 120
    vtx 0, 150
    vtx 320, 150

    .word 0xE1000400 | (0 << 5)     ; draw mode: semi-transparency mode 0: (B + F) / 2
    .word 0x2A << 24 | 0xA04060     ; semi-transparent flat quad (bit 1 of the command), 0x6040A0 as RGB
    vtx 10, 100
    vtx 70, 100
    vtx 10, 180
    vtx 70, 180
    .word 0xE1000400 | (1 << 5)     ; mode 1: B + F
    .word 0x2A << 24 | 0xA04060
    vtx 90, 100
    vtx 150, 100
    vtx 90, 180
    vtx 150, 180
    .word 0xE1000400 | (2 << 5)     ; mode 2: B - F
    .word 0x2A << 24 | 0xA04060
    vtx 170, 100
    vtx 230, 100
    vtx 170, 180
    vtx 230, 180
    .word 0xE1000400 | (3 << 5)     ; mode 3: B + F / 4
    .word 0x2A << 24 | 0xA04060
    vtx 250, 100
    vtx 310, 100
    vtx 250, 180
    vtx 310, 180
packets_end:

.align 0x800
__exe_end:
.close
