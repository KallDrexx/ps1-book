; Chapter 11 -- Vertex Table (starter)
; SVECTOR { short vx, vy, vz, pad } = 8 bytes: vx at +0, vy at +2, vz at +4, pad at +6. All values are signed 16-bit.
;
;   vt_translate(a0 = table, a1 = count, a2 = &offset)
;       add the SVECTOR at a2 (dx, dy, dz) to x, y, z of each vertex IN PLACE. Sums wrap to 16 bits. pad untouched.
;   vt_bbox(a0 = table, a1 = count >= 1, a2 = out)
;       out = six halfwords: min x, min y, min z, max x, max y, max z (SIGNED comparisons).
;   vt_pack(a0 = table, a1 = count, a2 = dst)
;       6 bytes per vertex: x, y, z, each little-endian, no pad. dst may have ANY alignment.
;       Returns v0 = bytes written (6 * count). Writes nothing else.
;   vt_unpack(a0 = packed, a1 = count, a2 = table)
;       the reverse. a0 may have ANY alignment; a2 is word-aligned. Rebuilt pad = 0.
; All four are leaf routines: use $t, $a, $v registers only.

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
vt_translate:               ; a0 = table, a1 = count, a2 = &offset
    ; TODO
    jr    $ra
    nop

vt_bbox:               ; a0 = table, a1 = count (>= 1), a2 = out
    ; TODO
    jr    $ra
    nop

vt_pack:                ; a0 = table, a1 = count, a2 = dst (any alignment) -> v0 = bytes written
    ; TODO
    jr    $ra
    move  $v0, $zero

vt_unpack:               ; a0 = packed (any alignment), a1 = count, a2 = table
    ; TODO
    jr    $ra
    nop

routines_end:

; ---- data -------------------------------------------------------------------
; TODO (section 7.2): align the table to its element size, then write the eight corners.
;   .align n takes a BYTE count (a power of two), not an exponent.
;   Corner i = (x, y, z, 0): x = +100 if bit 0 of i is set, else -100; y from bit 1; z from bit 2.
vertices:
    .fill 64, 0                 ; replace with 8 lines of `.halfword x, y, z, 0`

vt_offset:  .halfword 10, -20, 30, 0    ; dx, dy, dz, pad  (do not edit)
bbox:       .fill 12, 0                 ; 6 halfwords
            .align 4
pk_pre:     .byte 0xA5                  ; guard byte; also puts `packed` at an ODD address on purpose
packed:     .fill 48, 0                 ; 8 vertices x 6 bytes
pk_post:    .byte 0xA5                  ; guard byte
            .align 8
roundtrip:  .fill 64, 0

.align 0x800
__exe_end:
.close
