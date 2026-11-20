; Chapter 8 -- worked example: jal, jalr, and why a non-leaf routine breaks $ra.
; Set BROKEN to 1 to see the bug: the program then never reaches `done`.

.definelabel BROKEN, 0

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

main:
    la    $s0, results

    ; 1. jal puts the return address in $ra: the address of the instruction
    ;    AFTER the delay slot, i.e. call_site + 8.
call_site:
    jal   where_am_i
    nop
after_call:
    sw    $v0, 0($s0)           ; results[0] = $ra seen by the callee
    la    $t0, after_call
    sw    $t0, 4($s0)           ; results[1] = address of after_call (should match)

    ; 2. A non-leaf routine: double_fact calls factorial.
    jal   double_fact
    li    $a0, 5                ; delay slot: the argument is ready when the callee starts
    sw    $v0, 8($s0)           ; results[2] = 2 * 5! = 240

    ; 3. jalr: call through a register (a function pointer table).
    la    $s1, fn_table         ; $s1 survives calls; $t1 would not
    lw    $t2, 0($s1)           ; &factorial
    li    $a0, 4
    jalr  $t2                   ; jalr rs  ==  jalr $ra, rs
    nop
    sw    $v0, 12($s0)          ; results[3] = 4! = 24
    lw    $t2, 4($s1)           ; &double_fact
    li    $a0, 3
    jalr  $t2
    nop
    sw    $v0, 16($s0)          ; results[4] = 2 * 3! = 12

done:
    j     done
    nop

; leaf: returns the address it was called from (+8) in $v0
where_am_i:
    move  $v0, $ra
    jr    $ra
    nop

; leaf: a0 = n -> v0 = n!
factorial:
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

; non-leaf: a0 = n -> v0 = 2 * n!
.if BROKEN
double_fact:
    jal   factorial             ; overwrites $ra with the address of the next line
    nop
    sll   $v0, $v0, 1
    jr    $ra                   ; returns to the line above: loops forever
    nop
.else
double_fact:
    sw    $ra, saved_ra         ; park our return address in a static slot
    jal   factorial
    nop
    sll   $v0, $v0, 1
    lw    $ra, saved_ra
    nop                         ; load delay: $ra is not ready for the next line
    jr    $ra
    nop
.endif

.align 4
fn_table:  .word factorial, double_fact
saved_ra:  .word 0
results:   .fill 20, 0

.align 0x800
__exe_end:
.close
