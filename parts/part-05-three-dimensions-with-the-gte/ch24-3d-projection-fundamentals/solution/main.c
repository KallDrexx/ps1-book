#include <stdint.h>
#include <psxgpu.h>
#include <psxe/display.h>
#include <psxe/ot.h>
#include <psxe/fixed.h>

#define CX (SCREEN_W / 2)
#define CY (SCREEN_H / 2)

/* State the verifier reads and patches. Do not change the layout, the order or the initial values. */

/* The 8 corners, x y z in 4.12, +-1.0. Corner i has x = +1 if bit 0 of i is set, y = +1 if bit 1, z = +1 if bit 2. */
int16_t cube[8][3] = {
	{ -4096, -4096, -4096 }, {  4096, -4096, -4096 }, { -4096,  4096, -4096 }, {  4096,  4096, -4096 },
	{ -4096, -4096,  4096 }, {  4096, -4096,  4096 }, { -4096,  4096,  4096 }, {  4096,  4096,  4096 },
};

/* The 12 edges as pairs of corner indices: four along x, four along y, four along z. */
uint8_t edges[12][2] = {
	{ 0, 1 }, { 2, 3 }, { 4, 5 }, { 6, 7 },
	{ 0, 2 }, { 1, 3 }, { 4, 6 }, { 5, 7 },
	{ 0, 4 }, { 1, 5 }, { 2, 6 }, { 3, 7 },
};

int16_t projected[8][2];            /* screen x, y of each corner, written every frame */

int32_t angle_x = 128, angle_y = 256;   /* current angles, 4096 = one turn, kept in 0..4095 */
int32_t step_x = 24, step_y = 40;       /* added every frame */
int32_t cam_z = 6 * 4096;               /* distance from the camera to the cube's centre, 20.12 */
int32_t proj_h = 256;                   /* projection distance h, in pixels */
int32_t frame_no;                       /* frames completed */

__attribute__((noinline)) void frame_done(void)
{
	__asm__ volatile("" ::: "memory");   /* the verifier looks at the state here, once per frame */
}

static void update_angles(void)
{
	angle_x = (angle_x + step_x) & 4095;
	angle_y = (angle_y + step_y) & 4095;
}

static void project_cube(void)
{
	for (int i = 0; i < 8; i++) {
		fx x = cube[i][0], y = cube[i][1], z = cube[i][2];
		fx_vec2 r;

		fx_rotate(y, z, angle_x, &r);      /* about X: y and z change */
		y = r.x;
		z = r.y;
		fx_rotate(z, x, angle_y, &r);      /* about Y: z and x change */
		z = r.x;
		x = r.y;
		z += cam_z;                        /* move the cube away from the camera */

		projected[i][0] = CX + ((fx_div(x, z) * proj_h) >> FX_SHIFT);
		projected[i][1] = CY + ((fx_div(y, z) * proj_h) >> FX_SHIFT);
	}
}

static void draw_edges(void)
{
	for (int e = 0; e < 12; e++) {
		LINE_F2 *l = (LINE_F2 *) ot_alloc(sizeof(LINE_F2));
		int a = edges[e][0], b = edges[e][1];

		if (!l)
			return;
		setLineF2(l);
		setRGB0(l, 255, 255, 255);
		setXY2(l, projected[a][0], projected[a][1], projected[b][0], projected[b][1]);
		ot_add(l, 0);
	}
}

int main(void)
{
	display_init();
	/* Keeps the state above linked in even where your code does not read it (the linker drops unused
	   data, and the verifier needs every symbol to patch and read). Leave this line in. */
	__asm__ volatile("" :: "r"(cube), "r"(edges), "r"(projected), "r"(&angle_x), "r"(&angle_y),
	                 "r"(&step_x), "r"(&step_y), "r"(&cam_z), "r"(&proj_h));

	for (;;) {
		display_clear(16, 16, 32);
		ot_begin_frame();
		update_angles();
		project_cube();
		draw_edges();
		ot_draw();
		display_swap();
		frame_no++;
		frame_done();
	}
	return 0;
}
