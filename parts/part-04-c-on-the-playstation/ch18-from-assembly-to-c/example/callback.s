# callback.s -- assembly calling C: sum_expanded(c1, c2) = expand5(c1) + expand5(c2)
# A non-leaf routine, so it needs a stack frame (Chapter 10):
#   0..15($sp)   home area for the callee's a0-a3 (O32: the caller reserves it)
#   20($sp) s0   keeps c2 across the first call (s registers survive calls)
#   24($sp) s1   keeps expand5(c1) across the second call
#   28($sp) ra   our own return address: jal overwrites $ra

        .set    noreorder
        .set    noat

        .section .text
        .globl  sum_expanded
        .type   sum_expanded, @function
sum_expanded:
        addiu   $sp, $sp, -32
        sw      $ra, 28($sp)
        sw      $s1, 24($sp)
        sw      $s0, 20($sp)
        move    $s0, $a1            # c2 must survive the call to expand5
        jal     expand5             # a0 is already c1
        nop                         # delay slot (empty)
        move    $s1, $v0            # expand5(c1)
        jal     expand5
        move    $a0, $s0            # delay slot: argument for the second call
        addu    $v0, $v0, $s1       # expand5(c2) + expand5(c1)
        lw      $ra, 28($sp)
        lw      $s0, 20($sp)        # loads are not instant: something sits between lw $ra and jr $ra
        lw      $s1, 24($sp)
        jr      $ra
        addiu   $sp, $sp, 32        # delay slot: release the frame
        .size   sum_expanded, . - sum_expanded
