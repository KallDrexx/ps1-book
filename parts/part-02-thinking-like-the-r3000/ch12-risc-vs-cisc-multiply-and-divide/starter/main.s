; Chapter 12 -- Fast Routines (starter)
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
; Leaf routines: use $t, $a, $v only. Keep the labels and their order.
; Rules (section 7 of the chapter):
;   my_memcpy, my_memset, my_strlen, mulK: no mult/multu/div/divu/mfhi/mflo/mthi/mtlo.
;   udiv10: multu + mfhi are allowed (leave 2 instructions between mfhi and any later mult/div); div/divu are not.

my_memcpy:                  ; a0 = dst, a1 = src, a2 = n -> v0 = dst. Any alignment, any n, no overlap.
    ; TODO: byte head, lw/sw words, byte tail
    jr    $ra
    move  $v0, $a0

my_memset:                  ; a0 = dst, a1 = value (low 8 bits), a2 = n -> v0 = dst. Any alignment, any n.
    ; TODO
    jr    $ra
    move  $v0, $a0

my_strlen:                  ; a0 = s -> v0 = length. s at any alignment. May READ (not write) up to 3 bytes past the 0.
    ; TODO
    jr    $ra
    move  $v0, $zero

mul320:                     ; v0 = a0 * 320
    ; TODO
    jr    $ra
    move  $v0, $zero

mul1024:                    ; v0 = a0 * 1024
    ; TODO
    jr    $ra
    move  $v0, $zero

mul10:                      ; v0 = a0 * 10
    ; TODO
    jr    $ra
    move  $v0, $zero

mul100:                     ; v0 = a0 * 100
    ; TODO
    jr    $ra
    move  $v0, $zero

mul_m5:                     ; v0 = a0 * -5
    ; TODO
    jr    $ra
    move  $v0, $zero

mul1000:                    ; v0 = a0 * 1000
    ; TODO
    jr    $ra
    move  $v0, $zero

mul65537:                   ; v0 = a0 * 65537
    ; TODO
    jr    $ra
    move  $v0, $zero

udiv10:                     ; a0 = x (unsigned) -> v0 = x / 10, v1 = x % 10
    ; TODO
    jr    $ra
    move  $v0, $zero

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
