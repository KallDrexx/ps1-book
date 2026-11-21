/* Chapter 27 worked example: how long does the CPU wait for a GTE command?
 *
 * Each bar times   RTPS ; some other instructions ; read SXY2   with root counter 0 (it counts CPU cycles). Top to bottom:
 *   1  no command at all (just the timer reads and the store): subtract it from the others to get the cost of RTPS
 *   2  RTPS, nothing in the gap: the read has to wait for the command
 *   3-6  RTPS, then k = 4, 8, 12, 16 independent ALU instructions: free while k is small (the CPU would be waiting anyway),
 *        then the bar grows by 2 cycles per instruction
 *   7  RTPS, then four loads from RAM: free as well
 *   8  RTPS, then a read of an unrelated GTE register, then four ALU instructions: the read waits for the command, so the
 *      ALU instructions that follow it are no longer hidden
 * The numbers are also printed (run with the emulator's -stdout, which `make run` passes). */
#include <stdint.h>
#include <stdio.h>
#include <psxgpu.h>
#include <psxgte.h>
#include <inline_c.h>
#include <psxe/display.h>
#include <psxe/ot.h>
#include <psxe/gfx.h>

#define RC0_COUNT (*(volatile uint16_t *) 0x1F801100)
#define RC0_MODE  (*(volatile uint16_t *) 0x1F801104)

static SVECTOR v = { 1000, -500, 300, 0 };
static int32_t out;

#define ALU "addu $t1, $t1, $t2\n"                   /* one independent instruction */
#define ALU2 ALU ALU
#define ALU4 ALU2 ALU2
#define ALU8 ALU4 ALU4

/* name, the command (empty string = no command), the k instructions */
#define ROW(name, cmd, ops)                                                                     \
	static uint32_t name(void)                                                                  \
	{                                                                                           \
		uint16_t t0, t1;                                                                        \
		gte_ldv0(&v);                                                                           \
		t0 = RC0_COUNT;                                                                         \
		__asm__ volatile(cmd ops ::: "$9", "$10");                                              \
		gte_stsxy(&out);                                                                        \
		t1 = RC0_COUNT;                                                                         \
		return (uint16_t) (t1 - t0);                                                            \
	}

#define RTPS "nop\n nop\n cop2 0x0180001\n"          /* the command, with the two nops the macro would add */
#define LW   "lw $9, 0($29)\n"                      /* a load from RAM: needs no GTE */
#define LW4  LW LW LW LW
#define MFC2 "mfc2 $9, $6\n"                        /* a read of a GTE register (RGBC): the command does not touch it, but the read waits */
ROW(row_none,   "",   "")
ROW(row_k0,     RTPS, "")
ROW(row_k4,     RTPS, ALU4)
ROW(row_k8,     RTPS, ALU8)
ROW(row_k12,    RTPS, ALU8 ALU4)
ROW(row_k16,    RTPS, ALU8 ALU8)
ROW(row_lw4,    RTPS, LW4)
ROW(row_mfc2,   RTPS, MFC2 ALU4)

static uint32_t (*const rows[])(void) = { row_none, row_k0, row_k4, row_k8, row_k12, row_k16, row_lw4, row_mfc2 };
#define N_ROWS (sizeof rows / sizeof rows[0])

/* gte_SetRotMatrix/gte_SetTransMatrix overwrite $t0/$t1 without declaring it: call them only from a `noipa` function
   (README 5.7). */
static __attribute__((noipa)) void load_matrix(const MATRIX *m)
{
	gte_SetRotMatrix(m);
	gte_SetTransMatrix(m);
}

int main(void)
{
	uint32_t cycles[N_ROWS];
	int frame = 0;

	display_init();
	InitGeom();
	gte_SetGeomOffset(160, 120);
	gte_SetGeomScreen(256);
	RC0_MODE = 0;
	{
		MATRIX m = { { { 4096, 0, 0 }, { 0, 4096, 0 }, { 0, 0, 4096 } }, { 0, 0, 8000 } };
		load_matrix(&m);
	}

	for (;;) {
		display_clear(16, 16, 32);
		ot_begin_frame();
		for (unsigned i = 0; i < N_ROWS; i++)
			cycles[i] = rows[i]();
		for (unsigned i = 0; i < N_ROWS; i++)
			gfx_quad_f4(20, 20 + 24 * i, cycles[i] * 3, 16, i == 0 ? 120 : 64, i == 0 ? 120 : 200, 64, 0);
		ot_draw();
		display_swap();
		if (++frame == 60) {
			for (unsigned i = 0; i < N_ROWS; i++)
				printf("row %u: %u cycles\n", i + 1, (unsigned) cycles[i]);
		}
	}
	return 0;
}
