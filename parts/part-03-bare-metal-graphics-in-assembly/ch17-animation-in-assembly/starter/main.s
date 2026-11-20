; Chapter 17 -- "Bouncing Gem" (starter)
;
; See README section 7 for the specification: gem_state layout, the frame loop, the bounce rule, the bar graph.
; Given: gpu_init, gpu_wait, gpu_clear, draw_gouraud_tri (Chapters 13-15) and the data. You write the rest.

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

.definelabel GP0,    0x1F801810
.definelabel GP1,    0x1F801814
.definelabel I_STAT, 0x1F801070

.definelabel R,      24             ; gem half-size: the diamond spans (x +- R, y +- R)
.definelabel XMIN,   24             ; allowed range of the gem centre: [R, 319-R] x [R, 239-R]
.definelabel XMAX,   295
.definelabel YMIN,   24
.definelabel YMAX,   215
.definelabel BAR_N,  60             ; the bar graph cycles through 60 lengths

; unpack/pack helpers and the drawing routine from Chapter 15 (given)
.macro prologue
    addiu $sp, $sp, -24
    sw    $ra, 20($sp)
    sw    $a0, 24($sp)          ; spill a0-a3 into the home area the caller reserved:
    sw    $a1, 28($sp)          ; now the arguments form one array, args[i] = (24 + 4*i)($sp)
    sw    $a2, 32($sp)
    sw    $a3, 36($sp)
    jal   gpu_wait              ; the one wait for this packet
    nop
.endmacro
.macro epilogue
    lw    $ra, 20($sp)
    addiu $sp, $sp, 24
    jr    $ra
    nop
.endmacro
.macro send_color,off,cmd       ; GP0 <- pack_color(args[...], cmd)
    lw    $a0, off($sp)
    jal   pack_color
    li    $a1, cmd
    lui   $t0, 0x1F80
    sw    $v0, 0x1810($t0)
.endmacro
.macro send_vertex,xoff,yoff    ; GP0 <- pack_vertex(x, y)
    lw    $a0, xoff($sp)
    lw    $a1, yoff($sp)
    jal   pack_vertex
    nop
    lui   $t0, 0x1F80
    sw    $v0, 0x1810($t0)
.endmacro


draw_gouraud_tri:               ; args: c0 24, x0 28, y0 32, c1 36, x1 40, y1 44, c2 48, x2 52, y2 56
    prologue
    send_color 24, 0x30
    send_vertex 28, 32
    send_color 36, 0
    send_vertex 40, 44
    send_color 48, 0
    send_vertex 52, 56
    epilogue


; ---- the frame loop -------------------------------------------------------------------------------------
main:
    addiu $sp, $sp, -56         ; 16 outgoing area + stack arguments (16..32) + $ra, $s0
    sw    $ra, 52($sp)
    sw    $s0, 48($sp)
    jal   gpu_init
    nop
    lui   $t0, 0x1F80
    sw    $zero, 0x1074($t0)    ; I_MASK = 0: no IRQ reaches the CPU, so no BIOS handler clears I_STAT before we poll
frame:                          ; ---- one animation frame: keep this label at the top of the loop ----
    ; TODO 1: update_gem        gem_state: x += vx, y += vy; clamp to the edge and negate the velocity when outside
    ; TODO 2: back buffer       by = buf * 240 (shifts, not mul); set the drawing area and offset to (0, by)
    ; TODO 3: clear the back buffer (gpu_clear, 320x240 at (0, by)), draw_gem, draw_bar
    ; TODO 4: wait_vblank       poll I_STAT bit 0, then acknowledge it
    ; TODO 5: wait for the GPU, GP1(05h) display start (0, by); buf ^= 1; frame += 1
    j     frame
    nop
done:                           ; never reached: the animation runs forever
    j     done
    nop

wait_vblank:
    jr    $ra
    nop

set_draw_buffer:                ; (by): drawing area (0,by)-(319,by+239) and drawing offset (0,by)
    jr    $ra
    nop

update_gem:
    jr    $ra
    nop

draw_gem:                       ; two Gouraud triangles, using draw_gouraud_tri
    jr    $ra
    nop

draw_bar:                       ; rectangle (60h) at (10, 4): height 8, width ((frame % 60) + 1) * 5
    jr    $ra
    nop

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
routines_end:

; ---- data -------------------------------------------------------------------------------------------------
.align 4
gem_state:                      ; x, y (centre, pixels), vx, vy (pixels per frame), frame counter, back-buffer index
    .word 60, 80, 3, 2, 0, 1

.align 0x800
__exe_end:
.close
