#include <stdint.h>
#include <psxgpu.h>
#include <psxgte.h>
#include <inline_c.h>
#include <psxe/display.h>
#include <psxe/ot.h>
#include <psxe/fixed.h>
#include <psxe/input.h>

#define CX (SCREEN_W / 2)
#define CY (SCREEN_H / 2)
#define OTZ_SHIFT 7                  /* OT slot = OTZ >> 7 (Chapter 25) */
#define FLOOR_SLOT (OT_LENGTH - 1)   /* the floor is always the farthest thing */

#define FLOOR_COLS 8                 /* tiles along x */
#define FLOOR_ROWS 6                 /* tiles along z */
#define TILE       2048              /* tile edge, world units */
#define NEAR_Z     256               /* a floor tile with a corner nearer than this (view z) is skipped: README 5.7 */
#define N_OBJECTS  3
#define DEGENERATE 524288            /* given: |forward x up| (products of two 4.12 vectors, 2^24 = 1.0) below 2^24 / 32 means "parallel" */
#define CENTRE     1                 /* the cube the camera looks at: the green one */

/* One bouncing cube. Every field is an int32, in this order: the verifier reads and patches the array. */
typedef struct {
	int32_t x, y, z;          /* centre, world units; y is 20.12 fixed point (y >> 12 = units), y grows DOWN */
	int32_t vy;               /* vertical velocity, 20.12 units per frame (positive = falling) */
	int32_t ax, ay, az;       /* angles about X, Y, Z, 0..4095 */
	int32_t sx, sy, sz;       /* added to the angles every frame */
	int32_t size;             /* half the cube's edge, units */
	int32_t radius;           /* collision radius, units (centre to floor at rest) */
	int32_t bounce;           /* restitution, 4.12 (4096 = loses no speed) */
	int32_t colour;           /* r | g << 8 | b << 16 */
	int32_t bounces;          /* floor contacts so far */
} Object;

/* State the verifier reads and patches. Do not change the layout, the order or the initial values. */
Object objects[N_OBJECTS] = {
	{ -4400, -3000 * 4096, -1200,        0,  300,   0, 120,   0, 56,   0, 1200, 1500, 3277, 0x3030E0, 0 },   /* red   */
	{     0, -4000 * 4096,  1800, -60 * 4096,   0, 500, 200,  40,  0,   0, 1700, 2125, 2867, 0x40C830, 0 },   /* green */
	{  4400, -2500 * 4096,     0,  30 * 4096, 700, 150,   0,   0,  0, -48, 2200, 2750, 3482, 0xF06040, 0 },   /* blue  */
};

int32_t gravity = 4 * 4096;               /* added to every vy each frame (20.12 units per frame squared) */
int32_t floor_y = 4096;                   /* the floor's world y (the eye is at y = 0) */
int32_t proj_h  = 256;                    /* projection distance h, in pixels */

SVECTOR cube[8] = {                       /* the unit cube, +-1.0 (4096); corner i: x from bit 0, y from bit 1, z from bit 2 */
	{ -4096, -4096, -4096 }, {  4096, -4096, -4096 }, { -4096,  4096, -4096 }, {  4096,  4096, -4096 },
	{ -4096, -4096,  4096 }, {  4096, -4096,  4096 }, { -4096,  4096,  4096 }, {  4096,  4096,  4096 },
};
uint8_t faces[6][4] = {                   /* Chapter 25's table */
	{ 0, 1, 2, 3 }, { 5, 4, 7, 6 }, { 4, 0, 6, 2 }, { 1, 5, 3, 7 }, { 4, 5, 0, 1 }, { 2, 3, 6, 7 },
};
uint16_t face_shade[6] = { 256, 208, 176, 232, 192, 160 };   /* face f colour = channel * shade >> 8 */
uint8_t floor_colors[2][3] = { { 72, 72, 96 }, { 168, 168, 190 } };   /* tile (col + row) even / odd */

/* Chapter 26's fixed camera. TODO 4 replaces it with view_mtx everywhere and then deletes it. */
VECTOR  cam     = { 0, 0, 14336 };
MATRIX  cam_mtx;

/* The camera (README 7.2). Positions are world units; +x right, +y DOWN, +z into the screen. */
VECTOR  cam_eye    = { 0, 0, -14336 };    /* where the camera is: the old fixed camera's place, seen from the world */
VECTOR  cam_target = { 0, -4000, 1800 };  /* what it looks at: main sets it to the centre cube every frame */
VECTOR  cam_up     = { 0, -4096, 0 };     /* which way is up: -y. Only its direction matters. */
int32_t cam_speed  = 100;                 /* units per frame while a direction is held */
VECTOR  cam_min    = { -12000, -9000, -20000 };   /* the eye stays inside this box */
VECTOR  cam_max    = {  12000,  3000,  -5000 };
MATRIX  view_mtx;                         /* world -> view: rows right, down, forward; t = -R * eye */
int32_t frame_no;                         /* frames completed */

__attribute__((noinline)) void render_begin(void) { __asm__ volatile("" ::: "memory"); }
__attribute__((noinline)) void render_end(void)   { __asm__ volatile("" ::: "memory"); }
__attribute__((noinline)) void frame_done(void)   { __asm__ volatile("" ::: "memory"); }

/* Given: load a MATRIX into the GTE (RT and TR). PSn00bSDK 0.24's gte_SetRotMatrix/gte_SetTransMatrix overwrite $t0 and
   $t1 without declaring it, so a value the compiler keeps there across them is lost. Call them only from here: `noipa`
   makes this an opaque call that may clobber every temporary register (README 9). */
static __attribute__((noipa)) void load_matrix(const MATRIX *m)
{
	gte_SetRotMatrix(m);
	gte_SetTransMatrix(m);
}

/* TODO 1 (README 7.3): the look-at matrix. Fill view_mtx from the three arguments: rows right, down, forward in .m, t = -R * eye.
   The arguments are inputs: do not write through them. Keep the prototype and keep the function out of line. */
__attribute__((noinline)) void camera_look_at(const VECTOR *eye, const VECTOR *target, const VECTOR *up)
{
	(void) eye;
	(void) target;
	(void) up;
}

/* TODO 2: read the pad (input_held) and move cam_eye by cam_speed per frame, then clamp it to [cam_min, cam_max] (README 7.2). */
__attribute__((unused)) static void update_camera(void)
{
}

static void init_world(void)
{
	cam_mtx.m[0][0] = cam_mtx.m[1][1] = cam_mtx.m[2][2] = 4096;
	TransMatrix(&cam_mtx, &cam);
}

static void update_objects(void)
{
	for (int i = 0; i < N_OBJECTS; i++) {
		Object *o = &objects[i];
		int32_t limit = (floor_y - o->radius) << 12;

		o->vy += gravity;
		o->y  += o->vy;
		if (o->y > limit) {
			o->y  = limit;
			o->vy = -fx_mul(o->vy, o->bounce);
			o->bounces++;
		}
		o->ax = (o->ax + o->sx) & 4095;
		o->ay = (o->ay + o->sy) & 4095;
		o->az = (o->az + o->sz) & 4095;
	}
}

static void put_quad(int32_t a, int32_t b, int32_t c, int32_t d, int r, int g, int bl, int slot)
{
	POLY_F4 *p = (POLY_F4 *) ot_alloc(sizeof(POLY_F4));

	if (!p)
		return;
	setPolyF4(p);
	setRGB0(p, r, g, bl);
	setXY4(p, (int16_t) a, a >> 16, (int16_t) b, b >> 16, (int16_t) c, c >> 16, (int16_t) d, d >> 16);
	ot_add(p, slot);
}

static void draw_floor(void)
{
	int32_t sxy[FLOOR_ROWS + 1][FLOOR_COLS + 1], sz[FLOOR_ROWS + 1][FLOOR_COLS + 1];

	load_matrix(&cam_mtx);                  /* TODO 4: view_mtx */
	for (int r = 0; r <= FLOOR_ROWS; r++) {
		for (int c = 0; c <= FLOOR_COLS; c++) {
			SVECTOR v = { (c - FLOOR_COLS / 2) * TILE, floor_y, (r - FLOOR_ROWS / 2) * TILE, 0 };

			gte_ldv0(&v);
			gte_rtps();
			gte_stsxy(&sxy[r][c]);
			gte_stsz(&sz[r][c]);
		}
	}
	for (int r = 0; r < FLOOR_ROWS; r++) {
		for (int c = 0; c < FLOOR_COLS; c++) {
			int32_t area;
			const uint8_t *col = floor_colors[(r + c) & 1];

			/* a corner at or behind the eye has no meaningful screen position (the GTE's divide overflows): skip the tile */
			if (sz[r][c] < NEAR_Z || sz[r][c + 1] < NEAR_Z || sz[r + 1][c] < NEAR_Z || sz[r + 1][c + 1] < NEAR_Z)
				continue;

			/* seen from above: far-left, far-right, near-left, near-right (Z order) */
			gte_ldsxy3(sxy[r + 1][c], sxy[r + 1][c + 1], sxy[r][c]);
			gte_nclip();
			gte_stopz(&area);
			if (area <= 0)
				continue;
			put_quad(sxy[r + 1][c], sxy[r + 1][c + 1], sxy[r][c], sxy[r][c + 1], col[0], col[1], col[2], FLOOR_SLOT);
		}
	}
}

static void draw_object(const Object *o)
{
	SVECTOR rot = { o->ax, o->ay, o->az, 0 };
	VECTOR  scl = { o->size, o->size, o->size };
	VECTOR  pos = { o->x, o->y >> 12, o->z };
	MATRIX  m, world;
	int32_t sxy[8], sz[8];

	RotMatrix(&rot, &m);                 /* this object's rotation ... */
	ScaleMatrix(&m, &scl);               /* ... and size, */
	TransMatrix(&m, &pos);               /* ... and position in the world, */
	CompMatrixLV(&cam_mtx, &m, &world);   /* then through the fixed camera. TODO 4: view_mtx */
	load_matrix(&world);

	for (int i = 0; i < 8; i++) {
		gte_ldv0(&cube[i]);
		gte_rtps();
		gte_stsxy(&sxy[i]);
		gte_stsz(&sz[i]);
	}
	for (int f = 0; f < 6; f++) {
		int a = faces[f][0], b = faces[f][1], c = faces[f][2], d = faces[f][3];
		int32_t area, otz;

		gte_ldsxy3(sxy[a], sxy[b], sxy[c]);
		gte_nclip();
		gte_stopz(&area);
		if (area <= 0)
			continue;
		gte_ldsz4(sz[a], sz[b], sz[c], sz[d]);
		gte_avsz4();
		gte_stotz(&otz);
		put_quad(sxy[a], sxy[b], sxy[c], sxy[d],
		         ((o->colour & 255) * face_shade[f]) >> 8,
		         (((o->colour >> 8) & 255) * face_shade[f]) >> 8,
		         (((o->colour >> 16) & 255) * face_shade[f]) >> 8, otz >> OTZ_SHIFT);
	}
}

int main(void)
{
	display_init();
	input_init();
	InitGeom();
	gte_SetGeomOffset(CX, CY);
	gte_SetGeomScreen(proj_h);
	init_world();
	/* Keeps the state above linked in even where your code does not read it. Leave this line in. */
	__asm__ volatile("" :: "r"(objects), "r"(&gravity), "r"(&floor_y), "r"(&cam), "r"(&cam_mtx), "r"(&proj_h), "r"(cube), "r"(faces),
	                 "r"(face_shade), "r"(floor_colors), "r"(&cam_eye), "r"(&cam_target), "r"(&cam_up), "r"(&cam_speed),
	                 "r"(&cam_min), "r"(&cam_max), "r"(&view_mtx), "r"(camera_look_at));

	for (;;) {
		display_clear(24, 24, 48);
		ot_begin_frame();
		render_begin();
		input_update();
		update_objects();
		/* TODO 3 (README 7.3): update_camera(); aim cam_target at objects[CENTRE]; camera_look_at(&cam_eye, &cam_target, &cam_up); */
		draw_floor();
		for (int i = 0; i < N_OBJECTS; i++)
			draw_object(&objects[i]);
		render_end();
		ot_draw();
		display_swap();
		frame_no++;
		frame_done();
	}
	return 0;
}
