; Chapter 17 -- "Bouncing Gem" (solution)
;
; A Gouraud diamond bounces around a 320x240 screen; a bar graph shows the frame counter.
; Two framebuffers: buffer 0 at VRAM (0,0), buffer 1 at (0,240). Each iteration of the frame loop:
;   update the gem -> draw into the BACK buffer -> wait for VBlank -> show that buffer -> swap.
; VBlank is detected by polling I_STAT (0x1F801070) bit 0 and acknowledging it by writing 0 to that bit.

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

.definelabel GP0,    0x1F801810
.definelabel GP1,    0x1F801814
.definelabel I_STAT, 0x1F801070

.definelabel R,      24             ; gem half-size: the diamond spans (x +- R, y +- R)
.definelabel XMIN,   24             ; allowed range of the gem center: [R, 319-R] x [R, 239-R]
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
frame:                          ; ---- one animation frame ----
    jal   update_gem
    nop
    la    $t0, gem_state
    lw    $t1, 20($t0)          ; buf: the BACK buffer (0 or 1)
    nop
    sll   $t2, $t1, 8
    sll   $t3, $t1, 4
    subu  $s0, $t2, $t3         ; $s0 = buf * 240 = the back buffer's first VRAM line
    jal   set_draw_buffer
    move  $a0, $s0
    li    $a0, 0x101830         ; background
    move  $a1, $zero
    move  $a2, $s0
    li    $a3, 320
    li    $t1, 240
    jal   gpu_clear
    sw    $t1, 16($sp)
    jal   draw_gem
    nop
    jal   draw_bar
    nop
    jal   wait_vblank
    nop
    jal   gpu_wait              ; the GPU must have finished drawing before we show the buffer
    nop
    lui   $t0, 0x1F80
    sll   $t1, $s0, 10
    lui   $t2, 0x0500
    or    $t1, $t1, $t2
    sw    $t1, 0x1814($t0)      ; GP1(05h): display start (0, buf*240)
    la    $t0, gem_state
    lw    $t1, 20($t0)
    lw    $t2, 16($t0)
    xori  $t1, $t1, 1           ; swap: the buffer we just showed is now the front buffer
    addiu $t2, $t2, 1           ; frame counter
    sw    $t1, 20($t0)
    sw    $t2, 16($t0)
    j     frame
    nop
done:                           ; never reached: the animation runs forever
    j     done
    nop

; wait_vblank: poll I_STAT bit 0 until it is set, then acknowledge it (write 0 to bit 0, 1s elsewhere)
wait_vblank:
    lui   $t0, 0x1F80
wv_poll:
    lw    $t1, 0x1070($t0)
    nop
    andi  $t1, $t1, 1
    beqz  $t1, wv_poll
    nop
    li    $t1, -2               ; 0xFFFFFFFE
    jr    $ra
    sw    $t1, 0x1070($t0)

; set_draw_buffer(by): drawing area (0,by)-(319,by+239), drawing offset (0,by)
set_draw_buffer:
    addiu $sp, $sp, -8
    sw    $ra, 4($sp)
    sw    $a0, 0($sp)
    jal   gpu_wait
    nop
    lw    $a0, 0($sp)
    lui   $t0, 0x1F80
    sll   $t1, $a0, 10
    lui   $t2, 0xE300
    or    $t1, $t1, $t2
    sw    $t1, 0x1810($t0)      ; E3: top-left (0, by)
    addiu $t3, $a0, 239
    sll   $t3, $t3, 10
    lui   $t2, 0xE400
    or    $t3, $t3, $t2
    ori   $t3, $t3, 319
    sw    $t3, 0x1810($t0)      ; E4: bottom-right (319, by+239)
    sll   $t1, $a0, 11
    lui   $t2, 0xE500
    or    $t1, $t1, $t2
    sw    $t1, 0x1810($t0)      ; E5: offset (0, by)
    lw    $ra, 4($sp)
    addiu $sp, $sp, 8
    jr    $ra
    nop

; step_axis(p, min, max): *p += *(p+8); if outside [min, max]: clamp to the edge and negate the velocity
step_axis:
    lw    $t1, 0($a0)
    lw    $t2, 8($a0)
    nop
    addu  $t1, $t1, $t2
    slt   $t3, $t1, $a1
    beqz  $t3, sa_hi
    nop
    move  $t1, $a1
    subu  $t2, $zero, $t2
sa_hi:
    slt   $t3, $a2, $t1         ; max < pos ?
    beqz  $t3, sa_store
    nop
    move  $t1, $a2
    subu  $t2, $zero, $t2
sa_store:
    sw    $t1, 0($a0)
    jr    $ra
    sw    $t2, 8($a0)

update_gem:
    addiu $sp, $sp, -24
    sw    $ra, 20($sp)
    la    $a0, gem_state
    li    $a1, XMIN
    jal   step_axis
    li    $a2, XMAX
    la    $a0, gem_state + 4
    li    $a1, YMIN
    jal   step_axis
    li    $a2, YMAX
    lw    $ra, 20($sp)
    addiu $sp, $sp, 24
    jr    $ra
    nop

; draw_gem: two Gouraud triangles sharing the horizontal diagonal
.definelabel C_TOP, 0xA0F0FF
.definelabel C_SIDE, 0x20B0F0
.definelabel C_BOT, 0x1040A0
draw_gem:
    addiu $sp, $sp, -56
    sw    $ra, 52($sp)
    sw    $s1, 48($sp)
    sw    $s2, 44($sp)
    la    $t0, gem_state
    lw    $s1, 0($t0)           ; x
    lw    $s2, 4($t0)           ; y
    ; triangle 1: top, right, left
    li    $a0, C_TOP
    move  $a1, $s1
    addiu $a2, $s2, -R
    li    $a3, C_SIDE
    addiu $t1, $s1, R
    sw    $t1, 16($sp)          ; x1
    sw    $s2, 20($sp)          ; y1
    li    $t1, C_SIDE
    sw    $t1, 24($sp)          ; c2
    addiu $t1, $s1, -R
    sw    $t1, 28($sp)          ; x2
    jal   draw_gouraud_tri
    sw    $s2, 32($sp)          ; y2
    ; triangle 2: left, right, bottom
    li    $a0, C_SIDE
    addiu $a1, $s1, -R
    move  $a2, $s2
    li    $a3, C_SIDE
    addiu $t1, $s1, R
    sw    $t1, 16($sp)
    sw    $s2, 20($sp)
    li    $t1, C_BOT
    sw    $t1, 24($sp)
    sw    $s1, 28($sp)
    addiu $t1, $s2, R
    jal   draw_gouraud_tri
    sw    $t1, 32($sp)
    lw    $ra, 52($sp)
    lw    $s1, 48($sp)
    lw    $s2, 44($sp)
    addiu $sp, $sp, 56
    jr    $ra
    nop

; draw_bar: rectangle at (10, 4), height 8, width ((frame % 60) + 1) * 5
draw_bar:
    addiu $sp, $sp, -8
    sw    $ra, 4($sp)
    la    $t0, gem_state
    lw    $t1, 16($t0)
    li    $t2, BAR_N
    divu  $t1, $t2
    mfhi  $t3
    nop
    addiu $t3, $t3, 1
    sll   $t4, $t3, 2
    addu  $t3, $t3, $t4         ; *5
    sw    $t3, 0($sp)
    jal   gpu_wait
    nop
    lw    $t3, 0($sp)
    lui   $t0, 0x1F80
    li    $t1, 0x6020D0F0       ; rectangle (60h), color 0xF0D020
    sw    $t1, 0x1810($t0)
    li    $t1, (4 << 16) | 10
    sw    $t1, 0x1810($t0)
    lui   $t1, 8
    or    $t1, $t1, $t3
    sw    $t1, 0x1810($t0)      ; height 8, width
    lw    $ra, 4($sp)
    addiu $sp, $sp, 8
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
routines_end:

; ---- data -------------------------------------------------------------------------------------------------
.align 4
gem_state:                      ; x, y (center, pixels), vx, vy (pixels per frame), frame counter, back-buffer index
    .word 60, 80, 3, 2, 0, 1

.align 0x800
__exe_end:
.close
