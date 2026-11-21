/* Chapter 25 worked example: a card that turns around. One flat quad, spinning about the Y axis, drawn through the GTE.
 * Its front is green, its back red. The program does NOT cull: it asks NCLIP which side faces you and picks the color.
 * Watch the color change at the moment the card is edge-on, which is where NCLIP crosses zero. */
#include <stdint.h>
#include <psxgpu.h>
#include <psxgte.h>
#include <inline_c.h>
#include <psxe/display.h>
#include <psxe/ot.h>

/* Corners in "Z order": top-left, top-right, bottom-left, bottom-right, as seen from the front (y is down). */
static SVECTOR card[4] = {
	{ -3000, -2000, 0 }, { 3000, -2000, 0 }, { -3000, 2000, 0 }, { 3000, 2000, 0 },
};

/* gte_SetRotMatrix/gte_SetTransMatrix overwrite $t0/$t1 without declaring it: call them only from a `noipa` function
   (README 9). */
static __attribute__((noipa)) void load_matrix(const MATRIX *m)
{
	gte_SetRotMatrix(m);
	gte_SetTransMatrix(m);
}

int main(void)
{
	SVECTOR rot = { 0, 0, 0, 0 };
	VECTOR  pos = { 0, 0, 12000 };
	MATRIX  mtx;

	display_init();
	InitGeom();
	gte_SetGeomOffset(SCREEN_W / 2, SCREEN_H / 2);
	gte_SetGeomScreen(256);

	for (;;) {
		int32_t sxy[4], area;
		POLY_F4 *p;

		display_clear(16, 16, 32);
		ot_begin_frame();

		rot.vy = (rot.vy + 20) & 4095;
		RotMatrix(&rot, &mtx);
		TransMatrix(&mtx, &pos);
		load_matrix(&mtx);

		for (int i = 0; i < 4; i++) {
			gte_ldv0(&card[i]);
			gte_rtps();
			gte_stsxy(&sxy[i]);
		}
		gte_ldsxy3(sxy[0], sxy[1], sxy[2]);
		gte_nclip();
		gte_stopz(&area);                  /* > 0: corners 0, 1, 2 run clockwise on the screen: the front */

		p = (POLY_F4 *) ot_alloc(sizeof(POLY_F4));
		if (p) {
			setPolyF4(p);
			if (area > 0)
				setRGB0(p, 48, 200, 64);
			else
				setRGB0(p, 224, 48, 48);
			setXY4(p, (int16_t) sxy[0], sxy[0] >> 16, (int16_t) sxy[1], sxy[1] >> 16,
			          (int16_t) sxy[2], sxy[2] >> 16, (int16_t) sxy[3], sxy[3] >> 16);
			ot_add(p, 0);
		}
		ot_draw();
		display_swap();
	}
	return 0;
}
