; Chapter 5 -- "Hand-Made Header"
; Write the PSX-EXE header by hand (chapter section 7, part b). The code below is given.

.psx
.definelabel LOAD, 0x80010000          ; CHANGE ME: where the BIOS copies the code
.create "main.ps-exe", 0x8000F800      ; must equal LOAD - 0x800 (.create needs a literal number)

; ---- the 2048-byte header: YOUR CODE HERE ---------------------------------
; Emit it with .ascii / .word / .fill (see the chapter's field table).
; Do NOT .include "common/psxexe.inc". Required values are in the chapter.
.org LOAD - 0x800
; ...

; ---- the payload ---------------------------------------------------------
.org LOAD

main:
    la    $s0, results
    sw    $gp, 0x00($s0)               ; GP as the BIOS set it
    sw    $sp, 0x04($s0)               ; SP as the BIOS set it
    la    $t0, main
    sw    $t0, 0x08($s0)               ; where this code really is

    la    $t1, table
    addiu $t2, $t1, 32                 ; end pointer
    move  $t3, $zero
sum_loop:
    lw    $t4, 0($t1)
    addiu $t1, $t1, 4
    addu  $t3, $t3, $t4
    bne   $t1, $t2, sum_loop
    nop
    sw    $t3, 0x0C($s0)

done:
    j    done                          ; the verifier stops here and reads `results`
    nop

.align 4
table:
    .word       0x00000010, 0x00000200, 0x00003000, 0x00040000
    .word       0x00500000, 0x06000000, 0x70000000, 0x00000001

results:                               ; 4 words used
    .fill 16, 0

.align 0x800
__exe_end:
.close
