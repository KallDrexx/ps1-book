; Chapter 6 -- Bug 1: "Sum of N"
; Should store the sum of the first `count` words of `samples` in results[0],
; and the number of words it read in results[1]. It does not. Find out why.
; (Do not rename the data labels; the verifier patches them.)

.psx
.create "bug1.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

main:
    la    $s0, inputs
    la    $s1, results
    lw    $t0, 0($s0)                  ; count, 1..8
    la    $t1, samples                 ; read pointer
    move  $t3, $zero                   ; sum
    move  $t5, $zero                   ; words read
sum_loop:
    lw    $t4, 0($t1)
    addiu $t1, $t1, 4
    addu  $t3, $t3, $t4
    addiu $t5, $t5, 1
    addiu $t0, $t0, -1                 ; one fewer left
    bgez  $t0, sum_loop
    nop
    sw    $t3, 0x00($s1)
    sw    $t5, 0x04($s1)

done:
    j    done                          ; the verifier stops here and reads `results`
    nop

.align 4
inputs:
    .word       8                      ; count
samples:
    .word       0x00000011, 0x00000022, 0x00000033, 0x00000044
    .word       0x00000055, 0x00000066, 0x00000077, 0x00000088
guard:
    .word       0x0BAD0000             ; belongs to nobody
results:                               ; 2 words used
    .fill 16, 0

.align 0x800
__exe_end:
.close
