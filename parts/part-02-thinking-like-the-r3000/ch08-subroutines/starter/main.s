; Chapter 8 -- Subroutines (starter)
; Write three leaf routines and a test driver. See the chapter text, section 7.
;   factorial(a0 = n)               -> v0 = n! mod 2^32
;   sum_array(a0 = ptr, a1 = len)   -> v0 = sum of len words (0 if len = 0)
;   max_array(a0 = ptr, a1 = len)   -> v0 = largest signed word (len >= 1)
; Keep every label below: the verifier calls the routines by name and patches the data tables.

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

; ---- test driver ----------------------------------------------------------
main:
    ; TODO: results[0..3]  = factorial(drv_n[0..3])
    ; TODO: results[4]     = sum_array(drv_arr1, drv_len1)
    ; TODO: results[5]     = max_array(drv_arr1, drv_len1)
    ; TODO: results[6]     = sum_array(drv_arr2, drv_len2)
    ; TODO: results[7]     = max_array(drv_arr2, drv_len2)
    ; TODO: results[8]     = sum_array(drv_arr1, 0)
    ; TODO: results[9]     = max_array(drv_arr1, 1)

done:
    j     done                  ; the verifier stops here
    nop

; ---- routines (placed after `done`, so the driver can never fall into them) ----
factorial:                      ; a0 = n -> v0 = n!
    ; The Chapter 7 loop, still working on $t0 / $t1 instead of the calling convention.
    ; TODO: take n from $a0, leave the result in $v0.
    li    $t1, 1
fact_loop:
    slti  $t2, $t0, 2
    bne   $t2, $zero, fact_ret
    nop
    multu $t1, $t0
    mflo  $t1
    addiu $t0, $t0, -1
    j     fact_loop
    nop
fact_ret:
    jr    $ra
    nop

sum_array:                      ; a0 = ptr, a1 = len -> v0 = sum
    ; TODO
    jr    $ra
    nop

max_array:                      ; a0 = ptr, a1 = len (>= 1) -> v0 = signed maximum
    ; TODO
    jr    $ra
    nop

; ---- data (do not edit; the verifier replaces it) ----------------------------
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
