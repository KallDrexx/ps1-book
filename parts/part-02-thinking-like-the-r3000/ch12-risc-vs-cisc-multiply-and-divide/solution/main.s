; Chapter 12 -- Fast Routines (reference solution)
;
;   my_memcpy(a0 = dst, a1 = src, a2 = n)   -> v0 = dst   (buffers must not overlap)
;   my_memset(a0 = dst, a1 = value, a2 = n) -> v0 = dst   (only the low 8 bits of a1 are used)
;   my_strlen(a0 = s)                       -> v0 = length (bytes before the first 0)
;   mul320 mul1024 mul10 mul100 mul_m5 mul1000 mul65537 (a0 = x) -> v0 = x * K (mod 2^32), shifts and adds only
;   udiv10(a0 = x unsigned)                 -> v0 = x / 10, v1 = x % 10
; Any alignment, any length. Leaf routines: $t, $a, $v only.

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

; ---- test driver (given) --------------------------------------------------
main:
    la    $a0, copy_dst         ; 1. copy the message to an odd address
    la    $a1, msg
    li    $a2, msg_end - msg
    jal   my_memcpy
    nop

    la    $a0, copy_dst         ; 2. its length
    jal   my_strlen
    nop
    la    $t0, results
    sw    $v0, 0($t0)

    la    $a0, fill_dst         ; 3. fill 13 bytes at an odd address
    li    $a1, 0x5A
    li    $a2, 13
    jal   my_memset
    nop

    li    $a0, 77               ; 4. 77 * 320
    jal   mul320
    nop
    la    $t0, results
    sw    $v0, 4($t0)

    li    $a0, -3               ; 5. -3 * 1000
    jal   mul1000
    nop
    la    $t0, results
    sw    $v0, 8($t0)

    li    $a0, 1234567          ; 6. 1234567 / 10
    jal   udiv10
    nop
    la    $t0, results
    sw    $v0, 12($t0)
    sw    $v1, 16($t0)

done:
    j     done
    nop

; ---- your routines ----------------------------------------------------------
my_memcpy:
    move  $v0, $a0
    xor   $t0, $a0, $a1
    andi  $t0, $t0, 3
    bne   $t0, $zero, mc_tail   ; relative misalignment: bytes only
    sltiu $t1, $a2, 8           ; (slot) harmless on both paths
    bne   $t1, $zero, mc_tail   ; short: bytes only
    nop
mc_head:                        ; n >= 8, so the head never uses up n
    andi  $t0, $a0, 3
    beq   $t0, $zero, mc_words
    nop
    lbu   $t1, 0($a1)
    addiu $a1, $a1, 1
    sb    $t1, 0($a0)
    addiu $a2, $a2, -1
    j     mc_head
    addiu $a0, $a0, 1
mc_words:
    srl   $t2, $a2, 2
    sll   $t2, $t2, 2           ; bytes in whole words
    subu  $a2, $a2, $t2         ; tail count
    addu  $t2, $t2, $a0
    addiu $t2, $t2, -4          ; address of the last word
mc_wloop:
    lw    $t0, 0($a1)
    addiu $a1, $a1, 4
    sw    $t0, 0($a0)
    bne   $a0, $t2, mc_wloop
    addiu $a0, $a0, 4
mc_tail:
    beq   $a2, $zero, mc_done
    nop
mc_tloop:
    lbu   $t1, 0($a1)
    addiu $a1, $a1, 1
    sb    $t1, 0($a0)
    addiu $a2, $a2, -1
    bne   $a2, $zero, mc_tloop
    addiu $a0, $a0, 1
mc_done:
    jr    $ra
    nop

my_memset:
    move  $v0, $a0
    andi  $t1, $a1, 0xFF
    sltiu $t0, $a2, 8
    bne   $t0, $zero, ms_tail
    nop
ms_head:
    andi  $t0, $a0, 3
    beq   $t0, $zero, ms_words
    nop
    sb    $t1, 0($a0)
    addiu $a2, $a2, -1
    j     ms_head
    addiu $a0, $a0, 1
ms_words:
    sll   $t3, $t1, 8
    or    $t3, $t3, $t1
    sll   $t4, $t3, 16
    or    $t3, $t3, $t4         ; the byte in all four lanes
    srl   $t2, $a2, 2
    sll   $t2, $t2, 2
    subu  $a2, $a2, $t2
    addu  $t2, $t2, $a0
    addiu $t2, $t2, -4
ms_wloop:
    sw    $t3, 0($a0)
    bne   $a0, $t2, ms_wloop
    addiu $a0, $a0, 4
ms_tail:
    beq   $a2, $zero, ms_done
    nop
ms_tloop:
    sb    $t1, 0($a0)
    addiu $a2, $a2, -1
    bne   $a2, $zero, ms_tloop
    addiu $a0, $a0, 1
ms_done:
    jr    $ra
    nop

my_strlen:
    move  $t0, $a0
sl_head:
    andi  $t1, $t0, 3
    beq   $t1, $zero, sl_words
    nop
    lbu   $t2, 0($t0)
    nop
    beq   $t2, $zero, sl_done
    nop
    j     sl_head
    addiu $t0, $t0, 1
sl_words:
    lui   $t3, 0x0101
    ori   $t3, $t3, 0x0101
    lui   $t4, 0x8080
    ori   $t4, $t4, 0x8080
sl_wloop:                       ; a word has a zero byte iff (w - 0x01010101) & ~w & 0x80808080 != 0
    lw    $t1, 0($t0)
    addiu $t0, $t0, 4
    subu  $t2, $t1, $t3
    nor   $t1, $t1, $zero
    and   $t2, $t2, $t1
    and   $t2, $t2, $t4
    beq   $t2, $zero, sl_wloop
    nop
    addiu $t0, $t0, -4
sl_tail:
    lbu   $t2, 0($t0)
    nop
    beq   $t2, $zero, sl_done
    nop
    j     sl_tail
    addiu $t0, $t0, 1
sl_done:
    jr    $ra
    subu  $v0, $t0, $a0

mul320:                         ; x*256 + x*64
    sll   $t0, $a0, 8
    sll   $t1, $a0, 6
    jr    $ra
    addu  $v0, $t0, $t1

mul1024:
    jr    $ra
    sll   $v0, $a0, 10

mul10:                          ; x*8 + x*2
    sll   $t0, $a0, 3
    sll   $t1, $a0, 1
    jr    $ra
    addu  $v0, $t0, $t1

mul100:                         ; x*64 + x*32 + x*4
    sll   $t0, $a0, 6
    sll   $t1, $a0, 5
    addu  $t0, $t0, $t1
    sll   $t1, $a0, 2
    jr    $ra
    addu  $v0, $t0, $t1

mul_m5:                         ; -(x*4 + x)
    sll   $t0, $a0, 2
    addu  $t0, $t0, $a0
    jr    $ra
    subu  $v0, $zero, $t0

mul1000:                        ; x*1024 - x*16 - x*8
    sll   $t0, $a0, 10
    sll   $t1, $a0, 4
    subu  $t0, $t0, $t1
    sll   $t1, $a0, 3
    jr    $ra
    subu  $v0, $t0, $t1

mul65537:                       ; x + x*65536
    sll   $t0, $a0, 16
    jr    $ra
    addu  $v0, $t0, $a0

udiv10:                         ; x/10 = (x * 0xCCCCCCCD) >> 35
    lui   $t0, 0xCCCC
    ori   $t0, $t0, 0xCCCD
    multu $a0, $t0
    mfhi  $t1                   ; interlocks until the product is ready
    srl   $v0, $t1, 3           ; quotient
    sll   $t2, $v0, 3
    sll   $t3, $v0, 1
    addu  $t2, $t2, $t3         ; q * 10
    jr    $ra
    subu  $v1, $a0, $t2         ; remainder

; ---- byte-wise baselines (given; same contracts, for instruction-count comparison) ----
bytes_memcpy:
    move  $v0, $a0
    beq   $a2, $zero, bc_done
    nop
bc_loop:
    lbu   $t0, 0($a1)
    addiu $a1, $a1, 1
    sb    $t0, 0($a0)
    addiu $a2, $a2, -1
    bne   $a2, $zero, bc_loop
    addiu $a0, $a0, 1
bc_done:
    jr    $ra
    nop

bytes_memset:
    move  $v0, $a0
    beq   $a2, $zero, bs_done
    nop
bs_loop:
    sb    $a1, 0($a0)
    addiu $a2, $a2, -1
    bne   $a2, $zero, bs_loop
    addiu $a0, $a0, 1
bs_done:
    jr    $ra
    nop

bytes_strlen:
    move  $v0, $a0
bl_loop:
    lbu   $t0, 0($v0)
    nop
    bne   $t0, $zero, bl_loop
    addiu $v0, $v0, 1
    addiu $v0, $v0, -1
    jr    $ra
    subu  $v0, $v0, $a0

routines_end:

; ---- data (given) -----------------------------------------------------------
.align 4
results:  .fill 20, 0           ; strlen, mul320, mul1000, udiv10 q, r

msg:      .ascii "Strength reduction beats the divider."
msg_end:  .byte 0

            .align 4
copy_pre:  .byte 0xA5
copy_dst:  .fill 48, 0          ; odd address on purpose
copy_post: .byte 0xA5

            .align 4
fill_pre:  .byte 0xA5
fill_dst:  .fill 16, 0
fill_post: .byte 0xA5

.align 0x800
__exe_end:
.close
