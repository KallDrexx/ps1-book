; Chapter 6 -- Bug 2: "Keyed checksum"
; results[0] should be the sum of (word XOR KEY) over the six words of `words`,
; where KEY = 0x5EC0DE77. The XOR destroys the key register, so the loop reloads
; it on every pass. The result is wrong. Find out why.

.psx
.create "bug2.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

main:
    la    $s1, results
    la    $t1, words
    addiu $t2, $t1, 24                 ; end pointer (6 words)
    move  $t3, $zero                   ; checksum
    li    $t6, 0x5EC0DE77              ; the key
chk_loop:
    lw    $t4, 0($t1)
    addiu $t1, $t1, 4
    xor   $t6, $t6, $t4                ; key ^ word (destroys the key)
    addu  $t3, $t3, $t6
    bne   $t1, $t2, chk_loop
__bug2:
    li    $t6, 0x5EC0DE77              ; reload the key for the next pass
    sw    $t3, 0x00($s1)

done:
    j    done                          ; the verifier stops here and reads `results`
    nop

.align 4
words:
    .word       0x00000001, 0x00000100, 0x00010000, 0x01000000
    .word       0x12345678, 0x0000FFFF
results:                               ; 1 word used
    .fill 16, 0

.align 0x800
__exe_end:
.close
