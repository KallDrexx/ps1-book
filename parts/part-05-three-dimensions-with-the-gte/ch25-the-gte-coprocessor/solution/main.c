#include <stdint.h>
#include <psxgpu.h>
#include <psxgte.h>
#include <inline_c.h>
#include <psxe/display.h>
#include <psxe/ot.h>

#define CX (SCREEN_W / 2)
#define CY (SCREEN_H / 2)
#define OTZ_SHIFT 7                  /* OT slot = OTZ >> 7 (README 5.9) */

/* State the verifier reads and patches. Do not change the layout, the order or the initial values. */

/* The 8 corners, +-1.0 (4096). Corner i has x = +1 if bit 0 of i is set, y = +1 if bit 1, z = +1 if bit 2. */
SVECTOR cube[8] = {
	{ -4096, -4096, -4096 }, {  4096, -4096, -4096 }, { -4096,  4096, -4096 }, {  4096,  4096, -4096 },
	{ -4096, -4096,  4096 }, {  4096, -4096,  4096 }, { -4096,  4096,  4096 }, {  4096,  4096,  4096 },
};

/* The 6 faces as corner indices in "Z order" (README 5.7): when the face is turned toward you,
   corners 0, 1, 2 run clockwise on the screen and NCLIP is positive. */
uint8_t faces[6][4] = {
	{ 0, 1, 2, 3 },   /* 0: z = -1, the face toward the camera at rest */
	{ 5, 4, 7, 6 },   /* 1: z = +1 */
	{ 4, 0, 6, 2 },   /* 2: x = -1 */
	{ 1, 5, 3, 7 },   /* 3: x = +1 */
	{ 4, 5, 0, 1 },   /* 4: y = -1 (top: y is down) */
	{ 2, 3, 6, 7 },   /* 5: y = +1 */
};

uint8_t face_colors[6][3] = {
	{ 224,  48,  48 },   /* red */
	{  48, 200,  64 },   /* green */
	{  64,  96, 240 },   /* blue */
	{ 240, 220,  48 },   /* yellow */
	{ 220,  64, 220 },   /* magenta */
	{  48, 220, 220 },   /* cyan */
};

SVECTOR rot      = { 128, 256, 0, 0 };    /* angles about X, Y, Z: 4096 = one turn, kept in 0..4095 */
SVECTOR rot_step = {  24,  40, 0, 0 };    /* added to rot every frame */
int32_t cam_z    = 6 * 4096;              /* z of the cube's center, in the units of cube[] */
int32_t proj_h   = 256;                   /* projection distance h, in pixels */

MATRIX  mtx;                              /* the matrix uploaded to the GTE this frame */
int32_t screen_xy[8];                     /* corner i: low half = x, high half = y (one SXY word) */
int32_t screen_z[8];                      /* corner i: SZ, its depth, 0..65535 */

int32_t gte_flags;                        /* OR of the GTE flag register after every transform of this frame */
int32_t prims_submitted;                  /* quads linked into the table this frame */
int32_t faces_drawn;                      /* quads linked since start */
int32_t face_mask;                        /* bit f set: face f was drawn this frame */
int32_t frame_no;                         /* frames completed */

__attribute__((noinline)) void render_begin(void) { __asm__ volatile("" ::: "memory"); }   /* the verifier times from here ... */
__attribute__((noinline)) void render_end(void)   { __asm__ volatile("" ::: "memory"); }   /* ... to here */
__attribute__((noinline)) void frame_done(void)   { __asm__ volatile("" ::: "memory"); }

/* Given: load a MATRIX into the GTE (RT and TR). PSn00bSDK 0.24's gte_SetRotMatrix/gte_SetTransMatrix overwrite $t0 and
   $t1 without declaring it, so a value the compiler keeps there across them is lost. Call them only from here: `noipa`
   makes this an opaque call that may clobber every temporary register (README 9). */
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
	int32_t flags = 0;

	for (int i = 0; i < 8; i++) {
		int32_t f;

		gte_ldv0(&cube[i]);
		gte_rtps();
		gte_stsxy(&screen_xy[i]);
		gte_stsz(&screen_z[i]);
		gte_stflg(&f);
		flags |= f;
	}
	gte_flags = flags;
}

static void draw_faces(void)
{
	int32_t mask = 0;

	prims_submitted = 0;
	for (int f = 0; f < 6; f++) {
		int a = faces[f][0], b = faces[f][1], c = faces[f][2], d = faces[f][3];
		int32_t area, otz;
		POLY_F4 *p;

		gte_ldsxy3(screen_xy[a], screen_xy[b], screen_xy[c]);
		gte_nclip();
		gte_stopz(&area);
		if (area <= 0)
			continue;                                  /* facing away */

		gte_ldsz4(screen_z[a], screen_z[b], screen_z[c], screen_z[d]);
		gte_avsz4();
		gte_stotz(&otz);

		p = (POLY_F4 *) ot_alloc(sizeof(POLY_F4));
		if (!p)
			break;
		setPolyF4(p);
		setRGB0(p, face_colors[f][0], face_colors[f][1], face_colors[f][2]);
		setXY4(p, (int16_t) screen_xy[a], screen_xy[a] >> 16, (int16_t) screen_xy[b], screen_xy[b] >> 16,
		          (int16_t) screen_xy[c], screen_xy[c] >> 16, (int16_t) screen_xy[d], screen_xy[d] >> 16);
		ot_add(p, otz >> OTZ_SHIFT);
		mask |= 1 << f;
		prims_submitted++;
		faces_drawn++;
	}
	face_mask = mask;
}

int main(void)
{
	display_init();
	InitGeom();
	gte_SetGeomOffset(CX, CY);
	gte_SetGeomScreen(proj_h);
	/* Keeps the state above linked in even where your code does not read it. Leave this line in. */
	__asm__ volatile("" :: "r"(cube), "r"(faces), "r"(face_colors), "r"(&rot), "r"(&rot_step),
	                 "r"(&cam_z), "r"(&proj_h), "r"(&mtx), "r"(screen_xy), "r"(screen_z),
	                 "r"(&gte_flags), "r"(&prims_submitted), "r"(&faces_drawn), "r"(&face_mask));

	for (;;) {
		display_clear(16, 16, 32);
		ot_begin_frame();
		render_begin();
		update_angles();
		upload_matrix();
		transform_corners();
		draw_faces();
		render_end();
		ot_draw();
		display_swap();
		frame_no++;
		frame_done();
	}
	return 0;
}
