; Chapter 10 -- The Stack and the MIPS ABI (reference solution)
;   factorial(a0 = n)                    -> v0 = n! mod 2^32   (recursive)
;   fibonacci(a0 = n)                    -> v0 = fib(n), fib(0) = 0, fib(1) = 1   (tree recursion)
;   sum6(a0..a3 = a,b,c,d; 16($sp) = e; 20($sp) = f) -> v0 = a + b + c + d + e - f

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

; ---- test driver ----------------------------------------------------------
main:
    la    $s0, drv_n
    la    $s1, results

    lw    $a0, 0($s0)           ; results[0] = factorial(drv_n)
    jal   factorial
    nop
    sw    $v0, 0($s1)

    jal   factorial             ; results[1] = factorial(0)
    move  $a0, $zero
    sw    $v0, 4($s1)

    lw    $a0, 4($s0)           ; results[2] = fibonacci(drv_k)
    jal   fibonacci
    nop
    sw    $v0, 8($s1)

    jal   fibonacci             ; results[3] = fibonacci(0)
    move  $a0, $zero
    sw    $v0, 12($s1)

    addiu $sp, $sp, -24         ; results[4] = sum6(...): 16 bytes home area + 2 stack arguments
    lw    $a0, 8($s0)
    lw    $a1, 12($s0)
    lw    $a2, 16($s0)
    lw    $a3, 20($s0)
    lw    $t0, 24($s0)
    lw    $t1, 28($s0)
    sw    $t0, 16($sp)          ; 5th argument
    sw    $t1, 20($sp)          ; 6th argument
    jal   sum6
    nop
    addiu $sp, $sp, 24
    sw    $v0, 16($s1)

done:
    j     done                  ; the verifier stops here
    nop

; ---- routines -------------------------------------------------------------
; Frame (24 bytes):  20 saved $ra | 16 saved $s0 | 0..15 home area for OUR callees
factorial:                      ; a0 = n -> v0 = n!
    addiu $sp, $sp, -24
    sw    $ra, 20($sp)
    sw    $s0, 16($sp)
    slti  $t0, $a0, 2
    beq   $t0, $zero, fact_rec
    move  $s0, $a0              ; delay slot: keep n across the call
    li    $v0, 1                ; n < 2
    lw    $ra, 20($sp)
    lw    $s0, 16($sp)
    addiu $sp, $sp, 24
    jr    $ra
    nop
fact_rec:
    jal   factorial
    addiu $a0, $a0, -1
    multu $v0, $s0              ; n * factorial(n - 1)
    lw    $ra, 20($sp)          ; useful work between multu and mflo
    lw    $s0, 16($sp)
    mflo  $v0
    addiu $sp, $sp, 24
    jr    $ra
    nop

; Frame (32 bytes):  24 saved $ra | 20 saved $s1 | 16 saved $s0 | 0..15 home area | 28 padding
fibonacci:                      ; a0 = n -> v0 = fib(n)
    addiu $sp, $sp, -32
    sw    $ra, 24($sp)
    sw    $s0, 16($sp)
    sw    $s1, 20($sp)
    slti  $t0, $a0, 2
    bne   $t0, $zero, fib_base
    move  $s0, $a0              ; delay slot: keep n
    jal   fibonacci
    addiu $a0, $a0, -1          ; fib(n - 1)
    move  $s1, $v0
    jal   fibonacci
    addiu $a0, $s0, -2          ; fib(n - 2)
    addu  $v0, $v0, $s1
    j     fib_end
    nop
fib_base:
    move  $v0, $a0              ; fib(0) = 0, fib(1) = 1
fib_end:
    lw    $ra, 24($sp)
    lw    $s0, 16($sp)
    lw    $s1, 20($sp)
    addiu $sp, $sp, 32
    jr    $ra
    nop

; Leaf: no frame needed. The 5th and 6th arguments are above our $sp.
sum6:                           ; a0..a3, 16($sp) = e, 20($sp) = f
    lw    $t0, 16($sp)
    lw    $t1, 20($sp)
    addu  $v0, $a0, $a1
    addu  $v0, $v0, $a2
    addu  $v0, $v0, $a3
    addu  $v0, $v0, $t0
    subu  $v0, $v0, $t1
    jr    $ra
    nop

; ---- data -----------------------------------------------------------------
.align 4
drv_n:    .word 6               ; factorial input
drv_k:    .word 12              ; fibonacci input
drv_args: .word 10, 20, 30, 40, 50, 60      ; a, b, c, d, e, f for sum6
results:  .fill 20, 0           ; 5 words

.align 0x800
__exe_end:
.close
