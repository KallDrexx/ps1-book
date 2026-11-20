; Chapter 4 -- "Loop Lab"
; Three small loops over the data below (chapter section 7). Write your code
; between `main:` and `done:`. Fill every branch/jump delay slot with `nop`.

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
    .word       100                 ; +0x00  n       (part a: sum 1..n)
    .word       10                  ; +0x04  count   (part b: values in `values`, 1..16)
    .word       -20                 ; +0x08  seed    (part c: seq[0])
    .word       7                   ; +0x0C  step    (part c: seq[i+1] = seq[i] + step)
    .word       100                 ; +0x10  limit   (part c: compared against each entry)

values:                             ; part b input: 16 words, the first `count` are used
    .word       12, -5, 40, 7, -99, 63, 0, 8, -1, 25
    .word       0, 0, 0, 0, 0, 0

results:                            ; 5 words used
    .fill 32, 0

seq:                                ; part c output: 64 words
    .fill 256, 0

.align 0x800
__exe_end:
.close
