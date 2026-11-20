; Chapter 4 -- "Loop Lab" (reference solution)
.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

main:
    la    $s0, inputs
    la    $s1, results
    la    $s2, values
    la    $s3, seq

    ; ---- (a) sum 1..n --------------------------------------------------
    lw    $t0, 0x00($s0)             ; n
    move  $t1, $zero                 ; sum
    blez  $t0, sum_done              ; n <= 0: nothing to add
    nop
sum_loop:
    addu  $t1, $t1, $t0
    addiu $t0, $t0, -1
    bgtz  $t0, sum_loop
    nop
sum_done:
    sw    $t1, 0x00($s1)

    ; ---- (b) max and min of values[0..count-1] (signed) ----------------
    lw    $t0, 0x04($s0)             ; count
    lw    $t2, 0x00($s2)             ; max = values[0]
    addiu $t4, $s2, 4                ; pointer to values[1]
    move  $t3, $t2                   ; min = values[0]
    addiu $t0, $t0, -1               ; elements left
mm_loop:
    blez  $t0, mm_done
    nop
    lw    $t5, 0($t4)
    addiu $t4, $t4, 4                ; (also covers the load delay)
    addiu $t0, $t0, -1
    slt   $t6, $t2, $t5              ; max < x ?
    beq   $t6, $zero, not_max
    nop
    move  $t2, $t5
not_max:
    slt   $t6, $t5, $t3              ; x < min ?
    beq   $t6, $zero, not_min
    nop
    move  $t3, $t5
not_min:
    j     mm_loop
    nop
mm_done:
    sw    $t2, 0x04($s1)
    sw    $t3, 0x08($s1)

    ; ---- (c) fill seq[0..63], count entries below limit -----------------
    lw    $t0, 0x08($s0)             ; value = seed
    lw    $t1, 0x0C($s0)             ; step
    lw    $t2, 0x10($s0)             ; limit
    move  $t4, $s3                   ; pointer
    addiu $t8, $s3, 256              ; end pointer
    move  $t5, $zero                 ; signed count
    move  $t6, $zero                 ; unsigned count
fill_loop:
    sw    $t0, 0($t4)
    slt   $t7, $t0, $t2              ; 1 if value < limit (signed)
    addu  $t5, $t5, $t7
    sltu  $t7, $t0, $t2              ; 1 if value < limit (unsigned)
    addu  $t6, $t6, $t7
    addu  $t0, $t0, $t1
    addiu $t4, $t4, 4
    bne   $t4, $t8, fill_loop
    nop
    sw    $t5, 0x0C($s1)
    sw    $t6, 0x10($s1)

done:
    j    done
    nop

.align 4
inputs:
    .word       100, 10, -20, 7, 100

values:
    .word       12, -5, 40, 7, -99, 63, 0, 8, -1, 25
    .word       0, 0, 0, 0, 0, 0

results:
    .fill 32, 0

seq:
    .fill 256, 0

.align 0x800
__exe_end:
.close
