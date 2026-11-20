; Chapter 8 -- Subroutines
; Three leaf routines (factorial, sum_array, max_array) and a test driver.
;   factorial(a0 = n)               -> v0 = n! mod 2^32
;   sum_array(a0 = ptr, a1 = len)   -> v0 = sum of len words (0 if len = 0)
;   max_array(a0 = ptr, a1 = len)   -> v0 = largest signed word (len >= 1)

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

; ---- test driver ----------------------------------------------------------
main:
    la    $s0, drv_n            ; callee-saved registers keep the driver's
    la    $s1, results          ; state alive across every call
    li    $s2, 4
drv_fact:
    lw    $a0, 0($s0)           ; n
    jal   factorial
    addiu $s0, $s0, 4           ; delay slot: runs before the callee starts
    sw    $v0, 0($s1)
    addiu $s2, $s2, -1
    bgtz  $s2, drv_fact
    addiu $s1, $s1, 4           ; delay slot: advance the results pointer

    la    $a0, drv_arr1         ; results[4] = sum(arr1)
    lw    $a1, drv_len1
    jal   sum_array
    nop
    sw    $v0, 0($s1)

    la    $a0, drv_arr1         ; results[5] = max(arr1)
    lw    $a1, drv_len1
    jal   max_array
    nop
    sw    $v0, 4($s1)

    la    $a0, drv_arr2         ; results[6] = sum(arr2)
    lw    $a1, drv_len2
    jal   sum_array
    nop
    sw    $v0, 8($s1)

    la    $a0, drv_arr2         ; results[7] = max(arr2)
    lw    $a1, drv_len2
    jal   max_array
    nop
    sw    $v0, 12($s1)

    la    $a0, drv_arr1         ; results[8] = sum of zero elements
    jal   sum_array
    move  $a1, $zero            ; delay slot: argument set in the slot
    sw    $v0, 16($s1)

    la    $a0, drv_arr1         ; results[9] = max of the first element only
    jal   max_array
    li    $a1, 1
    sw    $v0, 20($s1)

done:
    j     done                  ; the verifier stops here
    nop

; ---- routines -------------------------------------------------------------
factorial:                      ; a0 = n -> v0 = n! (wraps mod 2^32)
    move  $t0, $a0
    li    $v0, 1
fact_loop:
    slti  $t1, $t0, 2
    bne   $t1, $zero, fact_ret
    nop
    multu $v0, $t0
    mflo  $v0
    addiu $t0, $t0, -1
    j     fact_loop
    nop
fact_ret:
    jr    $ra
    nop

sum_array:                      ; a0 = ptr, a1 = len -> v0 = sum
    move  $v0, $zero
sum_loop:
    blez  $a1, sum_ret
    nop
    lw    $t0, 0($a0)
    addiu $a0, $a0, 4           ; fills the load delay slot
    addu  $v0, $v0, $t0
    addiu $a1, $a1, -1
    j     sum_loop
    nop
sum_ret:
    jr    $ra
    nop

max_array:                      ; a0 = ptr, a1 = len (>= 1) -> v0 = signed max
    lw    $v0, 0($a0)
    addiu $a0, $a0, 4
    addiu $a1, $a1, -1
max_loop:
    blez  $a1, max_ret
    nop
    lw    $t0, 0($a0)
    addiu $a0, $a0, 4
    slt   $t1, $v0, $t0         ; v0 < t0 ?  (signed)
    beq   $t1, $zero, max_skip
    addiu $a1, $a1, -1          ; delay slot: runs on both paths
    move  $v0, $t0
max_skip:
    j     max_loop
    nop
max_ret:
    jr    $ra
    nop

; ---- data -----------------------------------------------------------------
.align 4
drv_n:    .word 5, 0, 12, 7             ; four factorial inputs (0..20)
drv_len1: .word 6                       ; 1..8
drv_arr1: .word 3, 9, -4, 12, 7, 1, 0, 0
drv_len2: .word 4                       ; 1..8
drv_arr2: .word -5, -9, -2, -7, 0, 0, 0, 0
results:  .fill 40, 0                   ; 10 words

.align 0x800
__exe_end:
.close
