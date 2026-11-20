; Chapter 10 worked example -- watching the stack grow.
; results[] (7 words):
;  0..3  $sp seen at depth 4, 3, 2, 1 of trace()   (each level 24 bytes lower than the last)
;  4     $sp in main              5  $sp in main after the calls (same as 4)
;  6     args5(1, 2, 3, 4, 5) = 15, the 5th argument read from 16($sp) by the callee

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

main:
    la    $s1, results
    sw    $sp, 16($s1)          ; results[4]

    la    $t0, cursor
    sw    $s1, 0($t0)           ; cursor = &results[0]
    jal   trace
    li    $a0, 4                ; delay slot: depth 4
    sw    $sp, 20($s1)          ; results[5]

    addiu $sp, $sp, -24         ; 16 bytes home area + the 5th argument (+ 4 padding)
    li    $t0, 5
    sw    $t0, 16($sp)
    li    $a0, 1
    li    $a1, 2
    li    $a2, 3
    jal   args5
    li    $a3, 4                ; delay slot
    addiu $sp, $sp, 24
    sw    $v0, 24($s1)

done:
    j     done
    nop

; trace(n): store $sp at *cursor, cursor += 4, then trace(n - 1) until n == 0.
; Frame of 24 bytes: 20 = saved $ra, 16 = spare, 0..15 = home area for the callee.
trace:
    addiu $sp, $sp, -24         ; prologue
    sw    $ra, 20($sp)
    la    $t0, cursor
    beq   $a0, $zero, trace_ret
    nop
    lw    $t1, 0($t0)
    nop
    sw    $sp, 0($t1)
    addiu $t1, $t1, 4
    sw    $t1, 0($t0)
    jal   trace
    addiu $a0, $a0, -1          ; delay slot
trace_ret:
    lw    $ra, 20($sp)          ; epilogue
    addiu $sp, $sp, 24
    jr    $ra
    nop

; Leaf: a + b + c + d + e. The fifth argument is at 16($sp), just above our (empty) frame.
args5:
    addu  $v0, $a0, $a1
    lw    $t0, 16($sp)
    addu  $v0, $v0, $a2
    addu  $v0, $v0, $a3
    addu  $v0, $v0, $t0
    jr    $ra
    nop

.align 4
cursor:   .word 0
results:  .fill 28, 0

.align 0x800
__exe_end:
.close
