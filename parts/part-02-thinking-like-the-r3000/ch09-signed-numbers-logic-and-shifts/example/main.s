; Chapter 9 worked example -- the same bits, different meanings.
; results[] (13 words):
;  0 lb   of 0xF0       -16          1 lbu  of 0xF0       240
;  2 lh   of 0x8001     -32767       3 lhu  of 0x8001     32769
;  4 ori  0xFFFF        65535        5 addiu -1           0xFFFFFFFF
;  6 andi 0xFFFFFFFF,0xFFFF 0xFFFF   7 nor (not) 0x0F0F0F0F  0xF0F0F0F0
;  8 sra  -7,1          -4           9 srl  -7,1          0x7FFFFFFC
; 10 -7/2 toward zero   -3          11 sllv 1 << 33       2 (amount masked to 5 bits)
; 12 sign-extend 5 bits 0x1D        0xFFFFFFFD

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

main:
    la    $s0, bytes
    la    $s1, results

    lb    $t0, 0($s0)           ; 0xF0 as a signed byte
    lbu   $t1, 0($s0)           ; 0xF0 as an unsigned byte
    lh    $t2, 4($s0)           ; 0x8001 as a signed halfword
    lhu   $t3, 4($s0)
    sw    $t0, 0($s1)
    sw    $t1, 4($s1)
    sw    $t2, 8($s1)
    sw    $t3, 12($s1)

    ori   $t0, $zero, 0xFFFF    ; the immediate is ZERO-extended
    addiu $t1, $zero, -1        ; addiu sign-extends its immediate
    sw    $t0, 16($s1)
    sw    $t1, 20($s1)
    andi  $t2, $t1, 0xFFFF      ; mask the low half
    sw    $t2, 24($s1)

    lui   $t0, 0x0F0F
    ori   $t0, $t0, 0x0F0F
    nor   $t3, $t0, $zero       ; nor with zero is NOT
    sw    $t3, 28($s1)

    li    $t0, -7
    sra   $t1, $t0, 1           ; floor(-3.5) = -4
    srl   $t2, $t0, 1           ; logical: a zero enters the top
    srl   $t3, $t0, 31          ; the sign bit as 0 or 1 ...
    addu  $t3, $t0, $t3         ; ... added first: now rounds toward zero
    sra   $t3, $t3, 1
    sw    $t1, 32($s1)
    sw    $t2, 36($s1)
    sw    $t3, 40($s1)

    li    $t0, 1
    li    $t1, 33
    sllv  $t2, $t0, $t1         ; only the low 5 bits of $t1 count: 33 & 31 = 1
    sw    $t2, 44($s1)

    li    $t0, 0x1D             ; 5-bit field 11101
    sll   $t0, $t0, 27          ; move its top bit to bit 31
    sra   $t0, $t0, 27          ; and copy it back down
    sw    $t0, 48($s1)

done:
    j     done
    nop

.align 4
bytes:   .word 0x000000F0
         .word 0x00008001
results: .fill 52, 0

.align 0x800
__exe_end:
.close
