; Chapter 11 worked example -- alignment, and what happens when you ignore it.
;
; Memory at `bytes` (little-endian):   11 22 33 44 55 66 77 88
;
;  results[0]  the word at bytes+1, read the SAFE way (lwr + lwl)   0x55443322
;  results[1]  the halfword at bytes+2, aligned lhu                 0x00004433
;
; Then the program does a plain `lw` from bytes+2. That address is not a multiple of 4,
; so the CPU raises an address-error exception and the program never reaches `done`.
; (Under the BIOS the machine just stops there.) Find out what happened: see section 6
; of the chapter README and Project step 7.2.

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

main:
    la    $s0, bytes
    la    $s1, results

    lwr   $t0, 1($s0)           ; low three bytes of the result come from bytes+1 .. bytes+3
    lwl   $t0, 4($s0)           ; the top byte comes from bytes+4 (right after lwr: legal for this pair)
    lhu   $t1, 2($s0)           ; aligned halfword: fine
    sw    $t0, 0($s1)           ; one instruction after lwl: t0 has arrived
    sw    $t1, 4($s1)

    addiu $s2, $s0, 2           ; bytes + 2: NOT a multiple of 4
    lw    $t2, 0($s2)           ; <- address error on load
    nop
    sw    $t2, 8($s1)           ; never reached

done:
    j     done
    nop

.align 4
bytes:   .word 0x44332211
         .word 0x88776655
results: .fill 12, 0

.align 0x800
__exe_end:
.close
