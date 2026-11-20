; Chapter 11 -- Vertex Table (solution)
;   vt_translate(a0 = table, a1 = count, a2 = &offset)   add the SVECTOR at a2 to every vertex (x, y, z; pad untouched)
;   vt_bbox(a0 = table, a1 = count >= 1, a2 = out)       out = 6 halfwords: min x,y,z then max x,y,z (signed)
;   vt_pack(a0 = table, a1 = count, a2 = dst)            6 bytes per vertex (x, y, z, little-endian); dst: ANY alignment;
;                                                        v0 = bytes written (6 * count)
;   vt_unpack(a0 = packed, a1 = count, a2 = table)       the reverse; a0: ANY alignment, a2 word-aligned; pad = 0

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

; ---- test driver (given) --------------------------------------------------
main:
    la    $a0, vertices         ; 1. translate in place
    li    $a1, 8
    la    $a2, vt_offset
    jal   vt_translate
    nop

    la    $a0, vertices         ; 2. bounding box
    li    $a1, 8
    la    $a2, bbox
    jal   vt_bbox
    nop

    la    $a0, vertices         ; 3. pack into the odd-addressed buffer
    li    $a1, 8
    la    $a2, packed
    jal   vt_pack
    nop

    la    $a0, packed           ; 4. unpack from it into `roundtrip`
    li    $a1, 8
    la    $a2, roundtrip
    jal   vt_unpack
    nop

done:
    j     done                  ; the verifier stops here
    nop

; ---- routines ---------------------------------------------------------------
vt_translate:
    lh    $t0, 0($a2)           ; dx, dy, dz
    lh    $t1, 2($a2)
    lh    $t2, 4($a2)
@@loop:
    beqz  $a1, @@end
    nop
    lh    $t3, 0($a0)
    lh    $t4, 2($a0)
    lh    $t5, 4($a0)
    addu  $t3, $t3, $t0
    addu  $t4, $t4, $t1
    addu  $t5, $t5, $t2
    sh    $t3, 0($a0)           ; sh keeps the low 16 bits: wraparound
    sh    $t4, 2($a0)
    sh    $t5, 4($a0)
    addiu $a0, $a0, 8
    b     @@loop
    addiu $a1, $a1, -1
@@end:
    jr    $ra
    nop

vt_bbox:
    lh    $t0, 0($a0)           ; min = max = first vertex
    lh    $t1, 2($a0)
    lh    $t2, 4($a0)
    move  $t3, $t0
    move  $t4, $t1
    move  $t5, $t2
@@loop:
    addiu $a1, $a1, -1
    beqz  $a1, @@done
    addiu $a0, $a0, 8
    lh    $t6, 0($a0)
    lh    $t7, 2($a0)
    lh    $t8, 4($a0)
    slt   $t9, $t6, $t0         ; x < min ?
    beqz  $t9, @@xmax
    nop
    move  $t0, $t6
@@xmax:
    slt   $t9, $t3, $t6         ; max < x ?
    beqz  $t9, @@ymin
    nop
    move  $t3, $t6
@@ymin:
    slt   $t9, $t7, $t1
    beqz  $t9, @@ymax
    nop
    move  $t1, $t7
@@ymax:
    slt   $t9, $t4, $t7
    beqz  $t9, @@zmin
    nop
    move  $t4, $t7
@@zmin:
    slt   $t9, $t8, $t2
    beqz  $t9, @@zmax
    nop
    move  $t2, $t8
@@zmax:
    slt   $t9, $t5, $t8
    beqz  $t9, @@loop
    nop
    b     @@loop
    move  $t5, $t8
@@done:
    sh    $t0, 0($a2)
    sh    $t1, 2($a2)
    sh    $t2, 4($a2)
    sh    $t3, 6($a2)
    sh    $t4, 8($a2)
    sh    $t5, 10($a2)
    jr    $ra
    nop

vt_pack:
    move  $v0, $zero
@@loop:
    beqz  $a1, @@end
    nop
    lw    $t0, 0($a0)           ; x and y together (the table is aligned)
    lhu   $t1, 4($a0)           ; z
    swr   $t0, 0($a2)           ; a word store to ANY address: swr + swl
    swl   $t0, 3($a2)
    sb    $t1, 4($a2)           ; z, a byte at a time
    srl   $t1, $t1, 8
    sb    $t1, 5($a2)
    addiu $a0, $a0, 8
    addiu $a2, $a2, 6
    addiu $v0, $v0, 6
    b     @@loop
    addiu $a1, $a1, -1
@@end:
    jr    $ra
    nop

vt_unpack:
@@loop:
    beqz  $a1, @@end
    nop
    lwr   $t0, 0($a0)           ; x and y: a word load from ANY address: lwr + lwl
    lwl   $t0, 3($a0)           ; the pair may sit back to back (see the chapter)
    lbu   $t1, 4($a0)           ; z, low byte
    lbu   $t2, 5($a0)           ; z, high byte
    sw    $t0, 0($a2)
    sll   $t2, $t2, 8
    or    $t1, $t1, $t2         ; z, with pad = 0 in the top half
    sw    $t1, 4($a2)
    addiu $a0, $a0, 6
    addiu $a2, $a2, 8
    b     @@loop
    addiu $a1, $a1, -1
@@end:
    jr    $ra
    nop
routines_end:

; ---- data -------------------------------------------------------------------
; SVECTOR { short vx, vy, vz, pad }  (8 bytes)
.align 8
vertices:                       ; cube corners: bit 0 of the index picks x, bit 1 y, bit 2 z; 0 = -100, 1 = +100
    .halfword -100, -100, -100, 0
    .halfword  100, -100, -100, 0
    .halfword -100,  100, -100, 0
    .halfword  100,  100, -100, 0
    .halfword -100, -100,  100, 0
    .halfword  100, -100,  100, 0
    .halfword -100,  100,  100, 0
    .halfword  100,  100,  100, 0
vt_offset:  .halfword 10, -20, 30, 0    ; dx, dy, dz, pad
bbox:       .fill 12, 0                 ; 6 halfwords
            .align 4
pk_pre:     .byte 0xA5                  ; guard byte; also puts `packed` at an ODD address
packed:     .fill 48, 0                 ; 8 vertices x 6 bytes
pk_post:    .byte 0xA5                  ; guard byte
            .align 8
roundtrip:  .fill 64, 0

.align 0x800
__exe_end:
.close
