/* Chapter 28 worked example: a camera orbiting a spinning cube that stands on a grid.
 * The eye circles the cube at a fixed height and radius; camera_look_at() turns (eye, target, up) into the view matrix;
 * every object is composed with it. Two switches break the camera on purpose:
 *   WRONG_ORDER 1      compose object * view instead of view * object
 *   SKIP_TRANSLATION 1 leave out the "- R * eye" part of the view matrix
 * Run it as shipped first, then try each. */
#include <stdint.h>
#include <psxgpu.h>
#include <psxgte.h>
#include <inline_c.h>
#include <psxe/display.h>
#include <psxe/ot.h>

#define WRONG_ORDER      0
#define SKIP_TRANSLATION 0

#define CX (SCREEN_W / 2)
#define CY (SCREEN_H / 2)
#define DEGENERATE 524288                /* |forward x up| below 2^24 / 32: up is parallel to forward */
#define GRID 4                           /* the ground is (2 * GRID) x (2 * GRID) tiles of 1500 units, 1500 units below the origin */
#define TILE 1500

static SVECTOR cube[8] = {
	{ -4096, -4096, -4096 }, {  4096, -4096, -4096 }, { -4096,  4096, -4096 }, {  4096,  4096, -4096 },
	{ -4096, -4096,  4096 }, {  4096, -4096,  4096 }, { -4096,  4096,  4096 }, {  4096,  4096,  4096 },
};
static uint8_t faces[6][4] = { { 0, 1, 2, 3 }, { 5, 4, 7, 6 }, { 4, 0, 6, 2 }, { 1, 5, 3, 7 }, { 4, 5, 0, 1 }, { 2, 3, 6, 7 } };
static uint8_t shade[6] = { 255, 205, 175, 230, 190, 160 };

static VECTOR cam_eye    = { 0, -3000, -9000 };
static VECTOR cam_target = { 0, 0, 0 };
static VECTOR cam_up     = { 0, -4096, 0 };
static MATRIX view_mtx;

static __attribute__((noipa)) void load_matrix(const MATRIX *m)    /* README 9 of Chapter 26: why noipa */
{
	gte_SetRotMatrix(m);
	gte_SetTransMatrix(m);
}

static int32_t abs32(int32_t v) { return v < 0 ? -v : v; }

/* Unit vector (4.12) in the direction of v. Returns 0 if v is the zero vector. VectorNormalS loads its input into 16-bit
   GTE registers and sums the squares with a trapping `add` (2^31 or more: an overflow exception), so the vector is first
   shifted down until its largest component is at most 8192; then one Newton step repairs the table's error (up to about
   0.8%): scale by 1.5 - 0.5 * |v|^2. */
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
		view_mtx.t[i] = SKIP_TRANSLATION ? 0 : -((view_mtx.m[i][0] * eye->vx + view_mtx.m[i][1] * eye->vy + view_mtx.m[i][2] * eye->vz) >> 12);
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

static void draw_ground(void)
{
	int32_t sxy[2 * GRID + 1][2 * GRID + 1];

	load_matrix(&view_mtx);                         /* the ground is the world itself: the view matrix alone */
	for (int r = 0; r <= 2 * GRID; r++) {
		for (int c = 0; c <= 2 * GRID; c++) {
			SVECTOR v = { (c - GRID) * TILE, 1500, (r - GRID) * TILE, 0 };

			gte_ldv0(&v);
			gte_rtps();
			gte_stsxy(&sxy[r][c]);
		}
	}
	for (int r = 0; r < 2 * GRID; r++) {
		for (int c = 0; c < 2 * GRID; c++) {
			int32_t area;

			gte_ldsxy3(sxy[r + 1][c], sxy[r + 1][c + 1], sxy[r][c]);
			gte_nclip();
			gte_stopz(&area);
			if (area <= 0)
				continue;
			if ((r + c) & 1)
				put_quad(sxy[r + 1][c], sxy[r + 1][c + 1], sxy[r][c], sxy[r][c + 1], 168, 168, 190, OT_LENGTH - 1);
			else
				put_quad(sxy[r + 1][c], sxy[r + 1][c + 1], sxy[r][c], sxy[r][c + 1], 72, 72, 96, OT_LENGTH - 1);
		}
	}
}

static void draw_cube(int angle)
{
	SVECTOR rot = { angle, angle * 2, 0, 0 };
	VECTOR  scl = { 1000, 1000, 1000 };
	VECTOR  pos = { 0, 0, 0 };
	MATRIX  m, world;
	int32_t sxy[8], sz[8];

	RotMatrix(&rot, &m);
	ScaleMatrix(&m, &scl);
	TransMatrix(&m, &pos);
#if WRONG_ORDER
	CompMatrixLV(&m, &view_mtx, &world);             /* object * view: the wrong way round */
#else
	CompMatrixLV(&view_mtx, &m, &world);             /* view * object: object -> world -> view */
#endif
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
		put_quad(sxy[a], sxy[b], sxy[c], sxy[d], 230 * shade[f] >> 8, 140 * shade[f] >> 8, 40 * shade[f] >> 8, otz >> 7);
	}
}

int main(void)
{
	int frame = 0;

	display_init();
	InitGeom();
	gte_SetGeomOffset(CX, CY);
	gte_SetGeomScreen(256);
	for (;;) {
		SVECTOR a = { frame * 24, 0, 0, 0 };
		int32_t s = isin(a.vx), c = icos(a.vx);

		cam_eye.vx = (9000 * s) >> 12;                /* a circle of radius 9000 around the cube, 3000 units up */
		cam_eye.vz = (-9000 * c) >> 12;
		display_clear(24, 24, 48);
		ot_begin_frame();
		camera_look_at(&cam_eye, &cam_target, &cam_up);
		draw_ground();
		draw_cube(frame * 17);
		ot_draw();
		display_swap();
		frame++;
	}
	return 0;
}
