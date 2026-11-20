; Chapter 5 -- "Hand-Made Header" (reference solution)
; A PSX-EXE whose header is written by hand: no `.include "common/psxexe.inc"`.

.psx
.definelabel LOAD, 0x80040000          ; where the BIOS copies the code (2 KB aligned, not the default)
.create "main.ps-exe", 0x8003F800          ; = LOAD - 0x800: file offset 0

; ---- the 2048-byte header ------------------------------------------------
.org LOAD - 0x800
.ascii "PS-X EXE"                      ; 0x00 magic
.fill 8, 0                             ; 0x08 zero
.word main                             ; 0x10 initial PC
.word LOAD + 0x8000                    ; 0x14 initial GP
.word LOAD                             ; 0x18 load address
.word __exe_end - LOAD                 ; 0x1C size of the payload
.fill 16, 0                            ; 0x20 unused / memfill
.word 0x801FFF00                       ; 0x30 initial SP base
.word 0                                ; 0x34 initial SP offset
.fill 0x14, 0                          ; 0x38 reserved
.ascii "Sony Computer Entertainment Inc. for North America area"   ; 0x4C
.fill 0x800 - 0x4C - 55, 0             ; pad the header to 2048 bytes

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
