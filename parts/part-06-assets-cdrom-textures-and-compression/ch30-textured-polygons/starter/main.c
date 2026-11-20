#include <stdint.h>
#include <stdlib.h>
#include <psxgpu.h>
#include <psxgte.h>
#include <inline_c.h>
#include <psxe/display.h>
#include <psxe/ot.h>
#include "cdrom.h"
#include "tim.h"

#define CX (SCREEN_W / 2)
#define CY (SCREEN_H / 2)
#define OTZ_SHIFT 7                  /* OT slot = OTZ >> 7, as in Chapter 25 */
#define N_TEX 3

/* The three textures, by index: 0 crate (8 bpp), 1 panel (4 bpp), 2 logo (4 bpp). */
static const char *const tex_path[N_TEX] = { "\\DATA\\CRATE.TIM;1", "\\DATA\\PANEL.TIM;1", "\\DATA\\LOGO.TIM;1" };

/* State the verifier reads and patches. Do not change the layout, the order or the initial values. */

/* The 8 corners, +-1.0 (4096). Corner i has x = +1 if bit 0 of i is set, y = +1 if bit 1, z = +1 if bit 2. */
SVECTOR cube[8] = {
	{ -4096, -4096, -4096 }, {  4096, -4096, -4096 }, { -4096,  4096, -4096 }, {  4096,  4096, -4096 },
	{ -4096, -4096,  4096 }, {  4096, -4096,  4096 }, { -4096,  4096,  4096 }, {  4096,  4096,  4096 },
};

/* The 6 faces as corner indices in "Z order": seen from outside, corners 0, 1, 2, 3 are the face's
   top-left, top-right, bottom-left and bottom-right (Chapter 25). Do not reorder. */
uint8_t faces[6][4] = {
	{ 0, 1, 2, 3 },   /* 0: z = -1, the face toward the camera at rest */
	{ 5, 4, 7, 6 },   /* 1: z = +1 */
	{ 4, 0, 6, 2 },   /* 2: x = -1 */
	{ 1, 5, 3, 7 },   /* 3: x = +1 */
	{ 4, 5, 0, 1 },   /* 4: y = -1 (top: y is down) */
	{ 2, 3, 6, 7 },   /* 5: y = +1 */
};

uint8_t face_tex[6] = { 0, 1, 2, 0, 1, 2 };   /* the texture index of each face: crate, panel, logo, crate, panel, logo */

TimInfo tim_info[N_TEX];             /* what tim_parse found in each file */
Tex     tex[N_TEX];                  /* what the polygons need, from tex_from_tim */
int32_t load_status;                 /* 0 = all three loaded; otherwise 1 + the texture that failed (cd_init failure: 100) */

SVECTOR rot      = { 200, 300, 0, 0 };   /* angles about X, Y, Z: 4096 = one turn */
SVECTOR rot_step = {  16,  28, 0, 0 };   /* added to rot every frame */
int32_t cam_z    = 4 * 4096;             /* z of the cube's centre, in the units of cube[] */
int32_t proj_h   = 256;                  /* projection distance h, in pixels */

MATRIX  mtx;                         /* the matrix uploaded to the GTE this frame */
int32_t screen_xy[8];                /* corner i: low half = x, high half = y */
int32_t screen_z[8];                 /* corner i: SZ */
int32_t prims_submitted;             /* quads linked into the table this frame */
int32_t frame_no;                    /* frames completed */

__attribute__((noinline)) void frame_done(void) { __asm__ volatile("" ::: "memory"); }

/* Given: load a MATRIX into the GTE (the SDK macros clobber $t0/$t1; see Chapter 25). */
static __attribute__((noipa)) void load_matrix(const MATRIX *m)
{
	gte_SetRotMatrix(m);
	gte_SetTransMatrix(m);
}

static void update_angles(void)
{
	rot.vx = (rot.vx + rot_step.vx) & 4095;
	rot.vy = (rot.vy + rot_step.vy) & 4095;
	rot.vz = (rot.vz + rot_step.vz) & 4095;
}

static void upload_matrix(void)
{
	VECTOR pos = { 0, 0, cam_z };

	RotMatrix(&rot, &mtx);
	TransMatrix(&mtx, &pos);
	load_matrix(&mtx);
}

static void transform_corners(void)
{
	for (int i = 0; i < 8; i++) {
		gte_ldv0(&cube[i]);
		gte_rtps();
		gte_stsxy(&screen_xy[i]);
		gte_stsz(&screen_z[i]);
	}
}

/* TODO (README 7.3): for each texture i: cd_load_file(tex_path[i], &size); tim_parse into tim_info[i]; tim_upload; tex_from_tim into tex[i];
   free the file image (VRAM has the pixels now). If a step fails: free what you hold, set load_status = 1 + i and return.
   Chapter 29's load_model() is the model. */
static void load_textures(void)
{
	load_status = 1;                 /* placeholder: the screen stays red until your loader works; remove this line */
	if (!cd_init()) {
		load_status = 100;
		return;
	}
}

/* Given: Chapter 25's culling and sorting. TODO (README 7.2): replace the last part with a textured quad: allocate a POLY_FT4,
   neutral colour, corners faces[f][0..3] in that order, the face's texture: UVs, clut and tpage; link it at slot otz >> OTZ_SHIFT. */
static void draw_faces(void)
{
	prims_submitted = 0;
	for (int f = 0; f < 6; f++) {
		int a = faces[f][0], b = faces[f][1], c = faces[f][2], d = faces[f][3];
		const Tex *t = &tex[face_tex[f]];
		int32_t area, otz;

		gte_ldsxy3(screen_xy[a], screen_xy[b], screen_xy[c]);
		gte_nclip();
		gte_stopz(&area);
		if (area <= 0)
			continue;                                  /* facing away */

		gte_ldsz4(screen_z[a], screen_z[b], screen_z[c], screen_z[d]);
		gte_avsz4();
		gte_stotz(&otz);

		(void) t; (void) d;                            /* remove with your code */
		/* TODO: the POLY_FT4 */
	}
}

int main(void)
{
	display_init();
	InitGeom();
	gte_SetGeomOffset(CX, CY);
	gte_SetGeomScreen(proj_h);
	load_textures();
	/* Keeps the state above linked in even where your code does not read it. Leave this line in. */
	__asm__ volatile("" :: "r"(cube), "r"(faces), "r"(face_tex), "r"(tim_info), "r"(tex), "r"(&load_status),
	                 "r"(&rot), "r"(&rot_step), "r"(&cam_z), "r"(&proj_h), "r"(&mtx), "r"(screen_xy),
	                 "r"(screen_z), "r"(&prims_submitted), "r"(tim_parse), "r"(tim_upload), "r"(tex_from_tim));

	for (;;) {
		if (load_status)
			display_clear(96, 0, 0);                   /* red screen: loading failed */
		else
			display_clear(16, 16, 32);
		ot_begin_frame();
		if (!load_status) {
			update_angles();
			upload_matrix();
			transform_corners();
			draw_faces();
		}
		ot_draw();
		display_swap();
		frame_no++;
		frame_done();
	}
	return 0;
}
