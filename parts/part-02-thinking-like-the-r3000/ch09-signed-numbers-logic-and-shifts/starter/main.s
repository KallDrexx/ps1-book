; Chapter 9 -- Bit Toolkit (starter)
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

    ; TODO (section 7.2): results[7..12], written by the driver itself.
    ;   7..10  lb, lbu, lh, lhu of drv_val
    ;   11     drv_val >> 3, arithmetic
    ;   12     drv_val / 8 rounded toward zero (no div)

done:
    j     done                  ; the verifier stops here
    nop

; ---- routines -------------------------------------------------------------
abs:                     ; a0 -> v0
    ; TODO
    jr    $ra
    nop

sign_extend:             ; a0 = value, a1 = bits -> v0
    ; TODO
    jr    $ra
    nop

popcount:                ; a0 -> v0
    ; TODO
    jr    $ra
    nop

rgb888_to_bgr555:        ; a0 = 0x??RRGGBB -> v0
    ; TODO
    jr    $ra
    nop

bgr555_unpack:           ; a0 -> v0 = 0x00RRGGBB, v1 = bit 15
    ; TODO
    jr    $ra
    nop

swap_endian32:           ; a0 -> v0
    ; TODO
    jr    $ra
    nop

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
