# annotated.s -- expand5() as compiled by mipsel-none-elf-gcc 12.3.0 -O2
#
# C source (expand.c):
#     uint32_t expand5(uint32_t c5) { return (c5 << 3) | (c5 >> 2); }
#
# Generated with:
#     mipsel-none-elf-gcc -O2 -S -ffreestanding -march=r3000 -msoft-float \
#         -fno-pic -mno-abicalls expand.c -o annotated.s
# Registers are numbered, not named: $2 = $v0, $4 = $a0, $31 = $ra.
#
# Directives (not instructions) first.

	.text
	.align	2                   # start on a 4-byte boundary (MIPS needs aligned code)
	.globl	expand5             # export the symbol: other files (and the linker) can see it
	.set	nomips16
	.set	nomicromips
	.ent	expand5
	.type	expand5, @function
expand5:
	# .frame/.mask are debug-info hints. "$sp,0" = this function has a
	# zero-byte stack frame: a leaf function that needs no stack at all.
	.frame	$sp,0,$31
	.mask	0x00000000,0
	.fmask	0x00000000,0
	# GCC tells the assembler: "I have already scheduled the delay slots,
	# do not reorder anything", exactly like our armips code.
	.set	noreorder
	.set	nomacro

	sll	$2,$4,3             # v0 = c5 << 3          (a0 = first argument, O32)
	srl	$4,$4,2             # a0 = c5 >> 2          (reuses a0: the argument is dead now)
	jr	$31                 # return to the caller (ra)
	or	$2,$2,$4            # DELAY SLOT: v0 = (c5<<3) | (c5>>2); runs before the jump lands.
	                            # GCC filled the slot with real work: no nop needed.

	.set	macro
	.set	reorder
	.end	expand5
	.size	expand5, .-expand5  # symbol size = here minus start (lets nm/objdump show it)
	.ident	"GCC: (GNU) 12.3.0"
