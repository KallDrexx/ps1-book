; Chapter 12 example -- what do mult/div leave in HI and LO?
; Run it, then read `table` (16 words) in the debugger or the memory viewer. Each row is HI, LO.
;   row 0: divu  7 / 0         row 1: div   7 / 0
;   row 2: div  -7 / 0         row 3: div   0x80000000 / -1
;   row 4: div  -7 / 2         row 5: multu 0xFFFFFFFF * 0xFFFFFFFF
;   row 6: mult -1 * -1        row 7: multu 0x10000 * 0x10000
; Predict every row before you look (the zero-divide rows are psx-spx material, not obvious).
.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

main:
    la    $t9, table
    li    $t0, 7
    li    $t1, -7
    move  $t2, $zero
    li    $t3, -1
    li    $t4, 0x80000000
    li    $t5, 2

    divu  $t0, $t2              ; 7 / 0 (unsigned)
    mfhi  $t6
    mflo  $t7
    sw    $t6, 0($t9)
    sw    $t7, 4($t9)

    div   $t0, $t2              ; 7 / 0 (signed)
    mfhi  $t6
    mflo  $t7
    sw    $t6, 8($t9)
    sw    $t7, 12($t9)

    div   $t1, $t2              ; -7 / 0
    mfhi  $t6
    mflo  $t7
    sw    $t6, 16($t9)
    sw    $t7, 20($t9)

    div   $t4, $t3              ; 0x80000000 / -1
    mfhi  $t6
    mflo  $t7
    sw    $t6, 24($t9)
    sw    $t7, 28($t9)

    div   $t1, $t5              ; -7 / 2
    mfhi  $t6
    mflo  $t7
    sw    $t6, 32($t9)
    sw    $t7, 36($t9)

    multu $t3, $t3              ; 0xFFFFFFFF * 0xFFFFFFFF
    mfhi  $t6
    mflo  $t7
    sw    $t6, 40($t9)
    sw    $t7, 44($t9)

    mult  $t3, $t3              ; -1 * -1
    mfhi  $t6
    mflo  $t7
    sw    $t6, 48($t9)
    sw    $t7, 52($t9)

    lui   $t0, 1
    multu $t0, $t0              ; 0x10000 * 0x10000
    mfhi  $t6
    mflo  $t7
    sw    $t6, 56($t9)
    sw    $t7, 60($t9)

done:
    j     done
    nop

.align 4
table:  .fill 64, 0

.align 0x800
__exe_end:
.close
