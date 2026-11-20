# rgb555.s -- Chapter 9's rgb888_to_bgr555, ported from armips to GNU as.
#   a0 = 0x??RRGGBB   ->   v0 = 0x00000BBBBBGGGGGRRRRR   (low 3 bits of each channel dropped)

        .set    noreorder           # we place delay-slot instructions ourselves
        .set    noat                # $at is ours, the assembler must not use it

        .section .text
        .globl  rgb888_to_bgr555
        .type   rgb888_to_bgr555, @function
rgb888_to_bgr555:
        srl     $t0, $a0, 19        # R: bits 23..19 -> 4..0
        andi    $t0, $t0, 0x1F
        srl     $t1, $a0, 6         # G: bits 15..11 -> 9..5
        andi    $t1, $t1, 0x03E0
        or      $t0, $t0, $t1
        sll     $t1, $a0, 7         # B: bits 7..3 -> 14..10
        andi    $t1, $t1, 0x7C00
        jr      $ra
        or      $v0, $t0, $t1       # delay slot: runs before the jump lands
        .size   rgb888_to_bgr555, . - rgb888_to_bgr555
