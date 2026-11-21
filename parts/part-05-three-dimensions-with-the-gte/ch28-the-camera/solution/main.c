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
#define DEGENERATE 524288            /* |forward x up| below this (2^24 / 32): up is parallel to forward */
#define CENTRE     1                 /* the cube the camera looks at: the green one */

/* One bouncing cube. Every field is an int32, in this order: the verifier reads and patches the array. */
typedef struct {
	int32_t x, y, z;          /* center, world units; y is 20.12 fixed point (y >> 12 = units), y grows DOWN */
	int32_t vy;               /* vertical velocity, 20.12 units per frame (positive = falling) */
	int32_t ax, ay, az;       /* angles about X, Y, Z, 0..4095 */
	int32_t sx, sy, sz;       /* added to the angles every frame */
	int32_t size;             /* half the cube's edge, units */
	int32_t radius;           /* collision radius, units (center to floor at rest) */
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
uint16_t face_shade[6] = { 256, 208, 176, 232, 192, 160 };   /* face f color = channel * shade >> 8 */
uint8_t floor_colors[2][3] = { { 72, 72, 96 }, { 168, 168, 190 } };   /* tile (col + row) even / odd */

/* The camera (README 7.2). Positions are world units; +x right, +y DOWN, +z into the screen. */
VECTOR  cam_eye    = { 0, 0, -14336 };    /* where the camera is: the old fixed camera's place, seen from the world */
VECTOR  cam_target = { 0, -4000, 1800 };  /* what it looks at: main sets it to the center cube every frame */
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

/* Unit vector (4.12) in the direction of v. Returns 0 if v is the zero vector. VectorNormalS loads its input into 16-bit
   GTE registers and sums the squares with a trapping `add` (2^31 or more: an overflow exception), so the vector is first
   shifted down until its largest component is at most 8192; then one Newton step repairs the table's error (up to about
   0.8%): scale by 1.5 - 0.5 * |v|^2. */
static int32_t abs32(int32_t v) { return v < 0 ? -v : v; }

static int normalize(const VECTOR *v, SVECTOR *out)
{
	int32_t m = abs32(v->vx), n;
	VECTOR  s;
	int     sh = 0, n2;

	if (abs32(v->vy) > m) m = abs32(v->vy);
	if (abs32(v->vz) > m) m = abs32(v->vz);
	if (m == 0)
		return 0;
	while ((m >> sh) > 8192)
		sh++;
	s.vx = v->vx >> sh;
	s.vy = v->vy >> sh;
	s.vz = v->vz >> sh;
	VectorNormalS(&s, out);
	n2 = out->vx * out->vx + out->vy * out->vy + out->vz * out->vz;
	n  = (3 * (1 << 24) - n2) >> 13;
	out->vx = (out->vx * n) >> 12;
	out->vy = (out->vy * n) >> 12;
	out->vz = (out->vz * n) >> 12;
	return 1;
}

/* a x b with the full 2^24-scale products (no shift). */
static void cross(const SVECTOR *a, const SVECTOR *b, VECTOR *c)
{
	c->vx = a->vy * b->vz - a->vz * b->vy;
	c->vy = a->vz * b->vx - a->vx * b->vz;
	c->vz = a->vx * b->vy - a->vy * b->vx;
}

/* |c| < DEGENERATE, compared squared after >> 10 (c is at most about 2^24 long, so the squares stay below 2^29). */
static int degenerate(const VECTOR *c)
{
	int32_t x = c->vx >> 10, y = c->vy >> 10, z = c->vz >> 10, d = DEGENERATE >> 10;

	return x * x + y * y + z * z < d * d;
}

__attribute__((noinline)) void camera_look_at(const VECTOR *eye, const VECTOR *target, const VECTOR *up)
{
	static const VECTOR fallback[2] = { { 0, 0, 4096 }, { 0, -4096, 0 } };
	VECTOR  d = { target->vx - eye->vx, target->vy - eye->vy, target->vz - eye->vz };
	SVECTOR f, u, r, dn;
	VECTOR  c;
	int     k = 0;

	if (!normalize(&d, &f))
		f = (SVECTOR) { 0, 0, 4096, 0 };           /* eye == target: look straight ahead */
	if (!normalize(up, &u))
		u = (SVECTOR) { 0, 0, 0, 0 };
	cross(&f, &u, &c);
	while (degenerate(&c) && k < 2) {              /* up is parallel to forward: try +z, then -y */
		normalize(&fallback[k++], &u);
		cross(&f, &u, &c);
	}
	normalize(&c, &r);                             /* right   = forward x up   */
	cross(&f, &r, &c);                             /* down    = forward x right (both unit: one shift) */
	dn.vx = c.vx >> 12;
	dn.vy = c.vy >> 12;
	dn.vz = c.vz >> 12;

	view_mtx.m[0][0] = r.vx;  view_mtx.m[0][1] = r.vy;  view_mtx.m[0][2] = r.vz;
	view_mtx.m[1][0] = dn.vx; view_mtx.m[1][1] = dn.vy; view_mtx.m[1][2] = dn.vz;
	view_mtx.m[2][0] = f.vx;  view_mtx.m[2][1] = f.vy;  view_mtx.m[2][2] = f.vz;
	for (int i = 0; i < 3; i++)
		view_mtx.t[i] = -((view_mtx.m[i][0] * eye->vx + view_mtx.m[i][1] * eye->vy + view_mtx.m[i][2] * eye->vz) >> 12);
}

static int32_t clamp(int32_t v, int32_t lo, int32_t hi)
{
	return v < lo ? lo : (v > hi ? hi : v);
}

/* Pad -> eye (README 5.7): world axes, cam_speed units per frame, then clamped to [cam_min, cam_max]. */
static void update_camera(void)
{
	int dx = input_held(INPUT_RIGHT) - input_held(INPUT_LEFT);
	int dy = input_held(INPUT_R1) - input_held(INPUT_L1);      /* +y is down: R1 lowers, L1 raises */
	int dz = input_held(INPUT_UP) - input_held(INPUT_DOWN);

	cam_eye.vx = clamp(cam_eye.vx + dx * cam_speed, cam_min.vx, cam_max.vx);
	cam_eye.vy = clamp(cam_eye.vy + dy * cam_speed, cam_min.vy, cam_max.vy);
	cam_eye.vz = clamp(cam_eye.vz + dz * cam_speed, cam_min.vz, cam_max.vz);
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

	load_matrix(&view_mtx);
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
	CompMatrixLV(&view_mtx, &m, &world);  /* then through the camera */
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
	/* Keeps the state above linked in even where your code does not read it. Leave this line in. */
	__asm__ volatile("" :: "r"(objects), "r"(&gravity), "r"(&floor_y), "r"(&proj_h), "r"(cube), "r"(faces),
	                 "r"(face_shade), "r"(floor_colors), "r"(&cam_eye), "r"(&cam_target), "r"(&cam_up), "r"(&cam_speed),
	                 "r"(&cam_min), "r"(&cam_max), "r"(&view_mtx), "r"(camera_look_at));

	for (;;) {
		display_clear(24, 24, 48);
		ot_begin_frame();
		render_begin();
		input_update();
		update_objects();
		update_camera();
		cam_target.vx = objects[CENTRE].x;
		cam_target.vy = objects[CENTRE].y >> 12;
		cam_target.vz = objects[CENTRE].z;
		camera_look_at(&cam_eye, &cam_target, &cam_up);
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
