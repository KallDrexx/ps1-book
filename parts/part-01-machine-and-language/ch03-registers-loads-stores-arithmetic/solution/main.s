; Chapter 3 -- "Register Calculator" (reference solution)
.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

main:
    lui   $t0, inputs >> 16          ; t0 = &inputs
    ori   $t0, $t0, inputs & 0xFFFF
    lui   $t1, results >> 16         ; t1 = &results
    ori   $t1, $t1, results & 0xFFFF

    lw    $t2, 0x00($t0)             ; a
    lw    $t3, 0x04($t0)             ; b
    lw    $t4, 0x08($t0)             ; c
    lh    $t5, 0x0C($t0)             ; h, sign-extended
    lhu   $t6, 0x0C($t0)             ; h, zero-extended
    lb    $t7, 0x0E($t0)             ; s, sign-extended
    lbu   $t8, 0x0E($t0)             ; s, zero-extended
    nop                              ; load delay for $t8

    addu  $s0, $t2, $t3              ; a + b
    sw    $s0, 0x00($t1)
    subu  $s0, $t2, $t3              ; a - b
    sw    $s0, 0x04($t1)
    subu  $s0, $t3, $t2              ; b - a
    sw    $s0, 0x08($t1)
    addiu $s0, $t2, 100              ; a + 100
    sw    $s0, 0x0C($t1)
    addiu $s0, $t2, -100             ; a - 100
    sw    $s0, 0x10($t1)
    lui   $s0, 0x1234                ; 0x12345678 + a
    ori   $s0, $s0, 0x5678
    addu  $s0, $s0, $t2
    sw    $s0, 0x14($t1)
    addiu $s0, $t4, 0x20             ; c + 0x20 wraps
    sw    $s0, 0x18($t1)
    sw    $t6, 0x1C($t1)             ; h zero-extended
    sw    $t5, 0x20($t1)             ; h sign-extended
    sw    $t8, 0x24($t1)             ; s zero-extended
    sw    $t7, 0x28($t1)             ; s sign-extended
    addu  $s0, $t5, $t7              ; h + s, both signed
    sw    $s0, 0x2C($t1)
    subu  $s0, $zero, $t2            ; -a
    sw    $s0, 0x30($t1)

    sw    $t3, 0x00($t0)             ; swap a and b in the table
    sw    $t2, 0x04($t0)

done:
    j    done
    nop

.align 4
inputs:
    .word       1000
    .word       2500
    .word       0x7FFFFFF0
    .halfword   0xFF38
    .byte       0xFB
    .byte       0

.align 4
results:
    .fill 64, 0

.align 0x800
__exe_end:
.close
