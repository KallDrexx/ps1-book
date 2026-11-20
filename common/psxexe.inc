; common/psxexe.inc -- PSX-EXE header for armips (Parts I-III).
;
; armips' `.psx` only selects the R3000 instruction set; it does NOT emit a
; PSX-EXE header. This file emits the 2 KB header by hand.
;
; Usage (the header must be the very first thing in the output file). armips
; resolves .include relative to the working directory; verify.sh and the
; chapter Makefile build in a staging dir that has common/ next to main.s.
;
;     .psx
;     .create "out.ps-exe", 0x8000F800      ; file offset 0 == load - 0x800
;     .include "common/psxexe.inc"          ; header; needs label `main`
;     .org 0x80010000                       ; code/data load address
;     main:
;         ...
;     .align 0x800                          ; file size must be a 2048 multiple
;     __exe_end:
;     .close
;
; Optional overrides (define BEFORE the .include with .definelabel):
;     EXE_LOAD   (default 0x80010000)    EXE_STACK (default 0x801FFFF0)

.ifndef EXE_LOAD
.definelabel EXE_LOAD, 0x80010000
.endif
.ifndef EXE_STACK
.definelabel EXE_STACK, 0x801FFFF0
.endif

.org EXE_LOAD - 0x800
.ascii "PS-X EXE"                 ; 0x00 magic
.fill 8, 0                       ; 0x08 pad
.word main                       ; 0x10 initial PC
.word 0                          ; 0x14 initial GP
.word EXE_LOAD                   ; 0x18 load address
.word __exe_end - EXE_LOAD       ; 0x1C size of code/data (2048 multiple)
.fill 16, 0                      ; 0x20 data/bss (unused)
.word EXE_STACK                  ; 0x30 initial SP base
.word 0                          ; 0x34 SP offset
.fill 0x14, 0                    ; 0x38 reserved
.ascii "Sony Computer Entertainment Inc. for North America area"
.fill 0x800 - (0x4C + 55), 0     ; pad header to 2048 bytes
