; Chapter 10 -- The Stack and the MIPS ABI (starter)
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

    ; TODO (section 7.2): results[4] = sum6(a, b, c, d, e, f) from drv_args.
    ;   a..d go in $a0-$a3; e and f go on the stack at 16($sp) and 20($sp).

done:
    j     done                  ; the verifier stops here
    nop

; ---- routines -------------------------------------------------------------
; Each stub just returns. Replace them (keep the order: factorial, fibonacci, sum6).
factorial:                      ; a0 = n -> v0 = n!   (must call itself)
    ; TODO
    jr    $ra
    nop

fibonacci:                      ; a0 = n -> v0 = fib(n)   (must call itself, twice)
    ; TODO
    jr    $ra
    nop

sum6:                           ; a0..a3 = a,b,c,d; 16($sp) = e; 20($sp) = f -> v0 = a+b+c+d+e-f
    ; TODO
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
