; Chapter 2 -- "Memory Cartographer"
; Write the layout described in the chapter (section 7) into `results`,
; using only lui, ori, sw, sh, sb, lbu, lw and nop between `main` and `done`.

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
results:
    .fill 64, 0                     ; 64 bytes of zeros; the layout is in the chapter

.align 0x800
__exe_end:
.close
