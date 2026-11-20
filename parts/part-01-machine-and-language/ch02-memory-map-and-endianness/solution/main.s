; Chapter 2 -- "Memory Cartographer" (reference solution)
.psx
.create "main.ps-exe", 0x8000F800
.include "common/psxexe.inc"
.org 0x80010000

main:
    lui  $t0, results >> 16         ; t0 = base of the results block
    ori  $t0, $t0, results & 0xFFFF

    ; ---- A. word, halfwords, bytes ------------------------------------------
    lui  $t1, 0x1234
    ori  $t1, $t1, 0x5678
    sw   $t1, 0x00($t0)
    ori  $t1, $zero, 0xBEEF
    sh   $t1, 0x04($t0)
    ori  $t1, $zero, 0xCAFE
    sh   $t1, 0x06($t0)
    ori  $t1, $zero, 0x11
    sb   $t1, 0x08($t0)
    ori  $t1, $zero, 0x22
    sb   $t1, 0x09($t0)
    ori  $t1, $zero, 0x33
    sb   $t1, 0x0A($t0)
    ori  $t1, $zero, 0x44
    sb   $t1, 0x0B($t0)
    lui  $t1, 0xDEAD
    ori  $t1, $t1, 0xBEEF
    sw   $t1, 0x0C($t0)

    ; ---- B. read words back one byte at a time -------------------------------
    lbu  $t1, 0x00($t0)             ; load into four different registers first:
    lbu  $t2, 0x01($t0)             ; the instruction right after a load must not use its result
    lbu  $t3, 0x02($t0)
    lbu  $t4, 0x03($t0)
    sb   $t1, 0x10($t0)
    sb   $t2, 0x11($t0)
    sb   $t3, 0x12($t0)
    sb   $t4, 0x13($t0)
    lbu  $t1, 0x0C($t0)
    lbu  $t2, 0x0D($t0)
    lbu  $t3, 0x0E($t0)
    lbu  $t4, 0x0F($t0)
    sb   $t1, 0x14($t0)
    sb   $t2, 0x15($t0)
    sb   $t3, 0x16($t0)
    sb   $t4, 0x17($t0)

    ; ---- C. one RAM location through three segments --------------------------
    lui  $t2, 0xA001                ; KSEG1 alias of results (0x8001xxxx | 0x20000000)
    ori  $t2, $t2, results & 0xFFFF
    lui  $t1, 0x0BAD
    ori  $t1, $t1, 0xF00D
    sw   $t1, 0x18($t2)
    lui  $t2, 0x0001                ; KUSEG alias of results
    ori  $t2, $t2, results & 0xFFFF
    ori  $t1, $zero, 0x7E57
    sh   $t1, 0x1C($t2)

    ; ---- D. scratchpad -------------------------------------------------------
    lui  $t3, 0x1F80
    lui  $t1, 0x600D
    ori  $t1, $t1, 0xCAFE
    sw   $t1, 0($t3)
    lw   $t1, 0($t3)
    nop                             ; load delay: t1 is not ready yet
    sw   $t1, 0x20($t0)

done:
    j    done
    nop

.align 4
results:
    .fill 64, 0

.align 0x800
__exe_end:
.close
