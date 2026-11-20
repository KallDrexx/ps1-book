; Chapter 3 -- "Register Calculator"
; Read the operands from `inputs`, compute the values listed in the chapter
; (section 7) and store them into `results`. Then fall through to `done`.

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

main:
    ; YOUR CODE HERE

done:
    j    done                       ; the verifier stops here and reads `results`
    nop

.align 4
inputs:
    .word       1000                ; +0x00  a
    .word       2500                ; +0x04  b
    .word       0x7FFFFFF0          ; +0x08  c
    .halfword   0xFF38              ; +0x0C  h
    .byte       0xFB                ; +0x0E  s
    .byte       0                   ; +0x0F  (padding)

.align 4
results:
    .fill 64, 0                     ; 13 words are used

.align 0x800
__exe_end:
.close
