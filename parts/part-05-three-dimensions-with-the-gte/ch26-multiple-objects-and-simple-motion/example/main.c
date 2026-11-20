/* Chapter 26 worked example: two cards, each spinning at its own speed, one left of centre and one right.
 * The GTE holds ONE rotation and ONE translation. A card is drawn with whatever matrix is loaded when its corners
 * are transformed. With FORGET_UPLOAD 1 the second card is transformed before its own matrix is uploaded, so it is
 * drawn with the first card's matrix: same spin, same place. Set it to 0 to see two independent cards. */
#include <stdint.h>
#include <psxgpu.h>
#include <psxgte.h>
#include <inline_c.h>
#include <psxe/display.h>
#include <psxe/ot.h>

#define FORGET_UPLOAD 1

static SVECTOR card[4] = {                     /* Z order: top-left, top-right, bottom-left, bottom-right */
	{ -1800, -1800, 0 }, { 1800, -1800, 0 }, { -1800, 1800, 0 }, { 1800, 1800, 0 },
};

/* gte_SetRotMatrix/gte_SetTransMatrix overwrite $t0/$t1 without declaring it: call them only from a `noipa` function
   (README 9). */
static __attribute__((noipa)) void load_matrix(const MATRIX *m)
{
	gte_SetRotMatrix(m);
	gte_SetTransMatrix(m);
}

static void upload(int angle, int x)
{
	SVECTOR rot = { 0, angle, 0, 0 };
	VECTOR  pos = { x, 0, 12000 };
	MATRIX  mtx;

	RotMatrix(&rot, &mtx);
	TransMatrix(&mtx, &pos);
	load_matrix(&mtx);
}

static void draw_card(int r, int g, int b)
{
	int32_t sxy[4];
	POLY_F4 *p;

	for (int i = 0; i < 4; i++) {
		gte_ldv0(&card[i]);
		gte_rtps();
		gte_stsxy(&sxy[i]);
	}
	p = (POLY_F4 *) ot_alloc(sizeof(POLY_F4));
	if (!p)
		return;
	setPolyF4(p);
	setRGB0(p, r, g, b);
	setXY4(p, (int16_t) sxy[0], sxy[0] >> 16, (int16_t) sxy[1], sxy[1] >> 16,
	          (int16_t) sxy[2], sxy[2] >> 16, (int16_t) sxy[3], sxy[3] >> 16);
	ot_add(p, 0);
}

int main(void)
{
	int a0 = 0, a1 = 0;

	display_init();
	InitGeom();
	gte_SetGeomOffset(SCREEN_W / 2, SCREEN_H / 2);
	gte_SetGeomScreen(256);

	for (;;) {
		display_clear(16, 16, 32);
		ot_begin_frame();
		a0 = (a0 + 20) & 4095;
		a1 = (a1 + 55) & 4095;

		upload(a0, -4000);                     /* card 0: slow, on the left */
		draw_card(224, 48, 48);
#if !FORGET_UPLOAD
		upload(a1, 4000);                      /* card 1: fast, on the right */
#endif
		draw_card(48, 200, 64);
		ot_draw();
		display_swap();
	}
	return 0;
}
