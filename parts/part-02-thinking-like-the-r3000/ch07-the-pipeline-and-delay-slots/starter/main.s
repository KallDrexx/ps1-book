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
    ; YOUR CODE HERE (version 1: out_v1[i] = inputs[i]!, nop in every delay slot)
fact_v1_end:

fact_v2:
    ; YOUR CODE HERE (version 2: same results into out_v2, delay slots filled)
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
