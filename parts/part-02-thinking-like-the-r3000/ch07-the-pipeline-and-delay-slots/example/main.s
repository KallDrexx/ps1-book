; Chapter 7 worked example: watch the two delay slots at work.
; Build with `make`, run with `make run`, or step through it in the PCSX-Redux debugger.
; results[0..4] after the run: 111 222 1 111 222   (explained in the chapter, section 6)

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

main:
    la    $s0, results
    la    $a0, value            ; value holds 222

    ; A. load delay: the instruction right after a load still sees the OLD register
    li    $t0, 111
    lw    $t0, 0($a0)
    addu  $t1, $t0, $zero       ; load delay slot: reads the old t0 (111)
    addu  $t2, $t0, $zero       ; one instruction later: reads the loaded 222
    sw    $t1, 0($s0)
    sw    $t2, 4($s0)

    ; B. branch delay slot: the instruction after a taken branch still runs
    li    $t3, 0
    beq   $zero, $zero, skip
    addiu $t3, $t3, 1           ; delay slot: executes
    addiu $t3, $t3, 100         ; skipped
skip:
    sw    $t3, 8($s0)

    ; C. both at once: a load in a branch delay slot; its load delay slot is the target
    li    $t4, 111
    beq   $zero, $zero, target
    lw    $t4, 0($a0)           ; delay slot: the load
target:
    addu  $t5, $t4, $zero       ; first instruction at the target: old t4 (111)
    addu  $t6, $t4, $zero       ; next: 222
    sw    $t5, 12($s0)
    sw    $t6, 16($s0)

done:
    j     done
    nop

.align 4
value:   .word 222
results: .fill 32, 0

.align 0x800
__exe_end:
.close
