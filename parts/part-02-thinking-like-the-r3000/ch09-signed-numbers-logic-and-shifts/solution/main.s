; Chapter 9 -- Bit Toolkit
; Six leaf routines (pure register code) and a test driver.
;   abs(a0)                    -> v0 = |a0| as a signed 32-bit value (abs(0x80000000) = 0x80000000)
;   sign_extend(a0=value, a1=bits 1..32) -> v0 = low `bits` bits of value, sign-extended to 32 bits
;   popcount(a0)               -> v0 = number of 1 bits in a0 (0..32)
;   rgb888_to_bgr555(a0=0x??RRGGBB) -> v0 = 0x0000_0BBB_BBGG_GGGR_RRRR (low 3 bits of each channel dropped)
;   bgr555_unpack(a0=0x????xBBBBBGGGGGRRRRR) -> v0 = 0x00RRGGBB (c8 = c5<<3 | c5>>2), v1 = bit 15 (0/1)
;   swap_endian32(a0)          -> v0 = the four bytes of a0 in reverse order

.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

; ---- test driver ----------------------------------------------------------
main:
    la    $s0, drv_val          ; callee-saved: keeps its value across the calls
    la    $s1, results

    lw    $a0, 0($s0)           ; results[0] = abs(val)
    jal   abs
    nop
    sw    $v0, 0($s1)

    lw    $a0, 0($s0)           ; results[1] = sign_extend(val, bits)
    lw    $a1, 4($s0)
    jal   sign_extend
    nop
    sw    $v0, 4($s1)

    lw    $a0, 0($s0)           ; results[2] = popcount(val)
    jal   popcount
    nop
    sw    $v0, 8($s1)

    lw    $a0, 8($s0)           ; results[3] = rgb888_to_bgr555(rgb)
    jal   rgb888_to_bgr555
    nop
    sw    $v0, 12($s1)

    lw    $a0, 12($s0)          ; results[4], [5] = bgr555_unpack(bgr)
    jal   bgr555_unpack
    nop
    sw    $v0, 16($s1)
    sw    $v1, 20($s1)

    lw    $a0, 0($s0)           ; results[6] = swap_endian32(val)
    jal   swap_endian32
    nop
    sw    $v0, 24($s1)

    lb    $t0, 0($s0)           ; results[7..10]: the four load flavours at drv_val
    lbu   $t1, 0($s0)
    lh    $t2, 0($s0)
    lhu   $t3, 0($s0)
    sw    $t0, 28($s1)
    sw    $t1, 32($s1)
    sw    $t2, 36($s1)
    sw    $t3, 40($s1)

    lw    $t0, 0($s0)           ; results[11] = val >> 3 (arithmetic: rounds toward -infinity)
    nop
    sra   $t1, $t0, 3
    sw    $t1, 44($s1)

    sra   $t2, $t0, 31          ; results[12] = val / 8 rounded toward zero:
    andi  $t2, $t2, 7           ;   add 7 first when val is negative, then shift
    addu  $t2, $t0, $t2
    sra   $t2, $t2, 3
    sw    $t2, 48($s1)

done:
    j     done                  ; the verifier stops here
    nop

; ---- routines -------------------------------------------------------------
abs:                            ; a0 -> v0
    sra   $t0, $a0, 31          ; t0 = 0 or -1 (all ones)
    xor   $v0, $a0, $t0         ; flips the bits when negative
    jr    $ra
    subu  $v0, $v0, $t0         ; delay slot: ...and adds 1 (subtracting -1)

sign_extend:                    ; a0 = value, a1 = bits -> v0
    li    $t0, 32
    subu  $t0, $t0, $a1         ; t0 = 32 - bits (0 for bits = 32)
    sllv  $v0, $a0, $t0         ; field to the top
    jr    $ra
    srav  $v0, $v0, $t0         ; delay slot: back down, copying the sign bit

popcount:                       ; a0 -> v0
    move  $v0, $zero
pop_loop:
    beq   $a0, $zero, pop_ret
    andi  $t0, $a0, 1           ; delay slot (harmless when leaving)
    addu  $v0, $v0, $t0
    j     pop_loop
    srl   $a0, $a0, 1           ; delay slot
pop_ret:
    jr    $ra
    nop

rgb888_to_bgr555:               ; a0 = 0x??RRGGBB -> v0
    srl   $t0, $a0, 19          ; R: bits 23..19 -> 4..0
    andi  $t0, $t0, 0x1F
    srl   $t1, $a0, 6           ; G: bits 15..11 -> 9..5
    andi  $t1, $t1, 0x03E0
    or    $t0, $t0, $t1
    sll   $t1, $a0, 7           ; B: bits 7..3 -> 14..10
    andi  $t1, $t1, 0x7C00
    jr    $ra
    or    $v0, $t0, $t1

bgr555_unpack:                  ; a0 -> v0 = 0x00RRGGBB, v1 = bit 15
    andi  $t0, $a0, 0x1F        ; red
    sll   $t1, $t0, 3
    srl   $t0, $t0, 2
    or    $t0, $t0, $t1
    sll   $v0, $t0, 16
    srl   $t0, $a0, 5           ; green
    andi  $t0, $t0, 0x1F
    sll   $t1, $t0, 3
    srl   $t0, $t0, 2
    or    $t0, $t0, $t1
    sll   $t0, $t0, 8
    or    $v0, $v0, $t0
    srl   $t0, $a0, 10          ; blue
    andi  $t0, $t0, 0x1F
    sll   $t1, $t0, 3
    srl   $t0, $t0, 2
    or    $t0, $t0, $t1
    or    $v0, $v0, $t0
    srl   $t1, $a0, 15          ; mask bit
    jr    $ra
    andi  $v1, $t1, 1

swap_endian32:                  ; a0 -> v0
    sll   $t0, $a0, 24          ; byte 0 -> top
    srl   $t1, $a0, 24          ; byte 3 -> bottom
    or    $t0, $t0, $t1
    srl   $t1, $a0, 8           ; byte 2 -> byte 1
    andi  $t1, $t1, 0xFF00
    or    $t0, $t0, $t1
    sll   $t1, $a0, 8           ; byte 1 -> byte 2
    lui   $t2, 0x00FF
    and   $t1, $t1, $t2
    jr    $ra
    or    $v0, $t0, $t1

; ---- data -----------------------------------------------------------------
.align 4
drv_val:  .word 0xFFFFFC85      ; signed input for abs, sign_extend, popcount, swap, loads, shifts
drv_bits: .word 8               ; field width for sign_extend (1..32)
drv_rgb:  .word 0x00FF8040      ; 0x00RRGGBB
drv_bgr:  .word 0x0000C3A5      ; BGR555 halfword (bit 15 set)
results:  .fill 52, 0           ; 13 words

.align 0x800
__exe_end:
.close
