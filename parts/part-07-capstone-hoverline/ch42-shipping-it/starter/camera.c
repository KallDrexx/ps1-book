#include <stdint.h>
#include <psxgte.h>
#include <psxe/input.h>
#include "camera.h"

/* Everything in this file is given: Chapter 28's camera, unchanged, plus a heading. */

/* Start: just behind the arch over the start line (the book's TRACK.TRK, section 0), looking along the track. */
VECTOR  cam_eye    = { 23883, -1500, -2500 };
int32_t cam_yaw    = 66;
VECTOR  cam_target = { 23883, -1500, -1500 };
VECTOR  cam_up     = { 0, -4096, 0 };
int32_t cam_speed  = 200;
int32_t cam_turn   = 24;
VECTOR  cam_min    = { -80000, -30000, -80000 };
VECTOR  cam_max    = {  80000,   2000,  80000 };
MATRIX  view_mtx;

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

void camera_update(void)
{
	int dx = input_held(INPUT_RIGHT) - input_held(INPUT_LEFT);
	int dy = input_held(INPUT_R1) - input_held(INPUT_L1);      /* +y is down: R1 lowers, L1 raises */
	int dz = input_held(INPUT_UP) - input_held(INPUT_DOWN);
	int dt = input_held(INPUT_R2) - input_held(INPUT_L2);

	cam_eye.vx = clamp(cam_eye.vx + dx * cam_speed, cam_min.vx, cam_max.vx);
	cam_eye.vy = clamp(cam_eye.vy + dy * cam_speed, cam_min.vy, cam_max.vy);
	cam_eye.vz = clamp(cam_eye.vz + dz * cam_speed, cam_min.vz, cam_max.vz);
	cam_yaw = (cam_yaw + dt * cam_turn) & 4095;
	cam_target.vx = cam_eye.vx + ((isin(cam_yaw) * 1000) >> 12);
	cam_target.vy = cam_eye.vy;
	cam_target.vz = cam_eye.vz + ((icos(cam_yaw) * 1000) >> 12);
	camera_look_at(&cam_eye, &cam_target, &cam_up);
}
