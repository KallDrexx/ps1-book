; Chapter 7 -- "Factorial, Tightly"
; Two independent versions of the same job (chapter section 7):
;   fact_v1 .. fact_v1_end   plain version: a `nop` in every delay slot
;   fact_v2 .. fact_v2_end   tight version: no `nop` in any delay slot
; Each version sets up its own registers, reads `inputs`, and writes its own
; output block. They run one after the other (v1 falls through into v2).

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

main:

fact_v1:
    la    $s0, inputs
    la    $s1, out_v1
    lw    $s2, 0($s0)           ; count
    addiu $s0, $s0, 4           ; (also covers the load delay)
v1_next:
    lw    $t0, 0($s0)           ; n
    nop                         ; load delay
    li    $t1, 1                ; acc = 1
v1_loop:
    slti  $t2, $t0, 2           ; n < 2 ?
    bne   $t2, $zero, v1_store
    nop
    multu $t1, $t0
    mflo  $t1                   ; acc *= n
    addiu $t0, $t0, -1
    j     v1_loop
    nop
v1_store:
    sw    $t1, 0($s1)
    addiu $s0, $s0, 4
    addiu $s1, $s1, 4
    addiu $s2, $s2, -1
    bgtz  $s2, v1_next
    nop
fact_v1_end:

fact_v2:
    la    $s0, inputs
    la    $s1, out_v2
    lw    $s2, 0($s0)           ; count
    addiu $s0, $s0, 4           ; load-delay filler
    li    $t4, 1
v2_next:
    lw    $t0, 0($s0)           ; n
    addiu $s0, $s0, 4           ; load-delay filler: advance input pointer
    slti  $t2, $t0, 2           ; n < 2 ?
    bne   $t2, $zero, v2_store
    li    $t1, 1                ; delay slot: acc = 1 on both paths
v2_loop:
    multu $t1, $t0
    addiu $t0, $t0, -1          ; runs while the multiply is in flight
    bne   $t0, $t4, v2_loop
    mflo  $t1                   ; delay slot: collect the product
v2_store:
    sw    $t1, 0($s1)
    addiu $s2, $s2, -1
    bgtz  $s2, v2_next
    addiu $s1, $s1, 4           ; delay slot: advance output pointer
fact_v2_end:

done:
    j    done                       ; the verifier stops here and reads the outputs
    nop

.align 4
inputs:
    .word       8                   ; +0x00  count (1..8)
    .word       5, 0, 1, 12, 7, 13, 2, 10   ; +0x04  n values (0..20); first `count` are used

out_v1:                             ; version 1 results: 8 words
    .fill 32, 0
out_v2:                             ; version 2 results: 8 words
    .fill 32, 0

.align 0x800
__exe_end:
.close
