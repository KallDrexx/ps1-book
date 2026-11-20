; Chapter 6 -- Bug 3: "Saturating sum"
; Adds the first `count` words of `samples` into a running total. As soon as the
; total reaches `limit`, it stops and reports `limit` instead.
; results[0] = the reported total, results[1] = how many words were added.
; The totals are wrong. Find out why.

.psx
.create "bug3.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

main:
    la    $s0, inputs
    la    $s1, results
    lw    $t5, 0($s0)                  ; limit
    lw    $t0, 4($s0)                  ; count, 1..8
    la    $t1, samples
    move  $t7, $zero                   ; words added
    move  $at, $zero                   ; running total (a spare register!)
add_loop:
    lw    $t4, 0($t1)
    addiu $t1, $t1, 4
    addu  $at, $at, $t4                ; total += sample
    addiu $t7, $t7, 1
__bug3:
    bge   $at, $t5, saturated          ; total >= limit ?
    nop
    addiu $t0, $t0, -1
    bgtz  $t0, add_loop
    nop
    b     finish
    nop
saturated:
    move  $at, $t5                     ; report exactly the limit
finish:
    sw    $at, 0x00($s1)
    sw    $t7, 0x04($s1)

done:
    j    done                          ; the verifier stops here and reads `results`
    nop

.align 4
inputs:
    .word       100                    ; limit
    .word       6                      ; count
samples:
    .word       10, 20, 30, 15, 12, 8, 4, 2
results:                               ; 2 words used
    .fill 16, 0

.align 0x800
__exe_end:
.close
