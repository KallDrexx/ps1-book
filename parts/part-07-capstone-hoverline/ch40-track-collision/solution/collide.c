#include <stdint.h>
#include <stdio.h>
#include <psxe/fixed.h>
#include "track.h"
#include "ship.h"
#include "track_vis.h"
#include "audio.h"
#include "collide.h"

CollideCfg collide_cfg = {
	.radius = 90, .wall_damp = 2048, .yaw_fix = 2048, .boost_impulse = 5 * 4096, .thud_gap = 12, .off_limit = 1200,
};
CollideState collide_state;
char collide_text[32];

#define HALF (ANGLE_TURN / 2)

static int32_t clamp_d(int32_t v)
{
	return v > COLL_CLAMP ? COLL_CLAMP : (v < -COLL_CLAMP ? -COLL_CLAMP : v);
}

/* ---- given ---------------------------------------------------------------------------------------------------------------- */

uint32_t collide_isqrt(uint32_t n)
{
	uint32_t root = 0, bit = 1u << 30;

	while (bit > n)
		bit >>= 2;
	while (bit) {
		if (n >= root + bit) {
			n -= root + bit;
			root = (root >> 1) + bit;
		} else {
			root >>= 1;
		}
		bit >>= 2;
	}
	return root;
}

/* The cross-product error of the angle a for the direction (x, z), or -1 when a points the other way. */
static int32_t head_err(int32_t a, int32_t x, int32_t z)
{
	int32_t s = isin(a), c = icos(a), e;

	if (s * x + c * z <= 0)
		return -1;
	e = s * z - c * x;
	return e < 0 ? -e : e;
}

int32_t collide_heading(int32_t x, int32_t z)
{
	int32_t ba = 0, bb = -1, best = 0, be = -1;

	if (x == 0 && z == 0)
		return 0;
	for (int32_t a = 0; a < 4096; a += 64) {
		int32_t e = head_err(a, x, z);

		if (e >= 0 && (bb < 0 || e < bb)) {
			bb = e;
			ba = a;
		}
	}
	for (int32_t a = ba - 64; a <= ba + 64; a++) {
		int32_t aa = a & 4095, e = head_err(aa, x, z);

		if (e >= 0 && (be < 0 || e < be || (e == be && aa < best))) {
			be = e;
			best = aa;
		}
	}
	return best;
}

void collide_reset(void)
{
	collide_state = (CollideState) { 0 };
	collide_state.last_hit = -1000000;
	collide_state.face = -1;
}

/* ---- the edges ------------------------------------------------------------------------------------------------------------ */

static int irregular_edge(const int32_t a[2], const int32_t b[2], const int32_t r[2])
{
	int32_t ex = b[0] - a[0], ez = b[1] - a[1];

	if (ex == 0 && ez == 0)
		return 1;
	return ex * clamp_d(r[1] - a[1]) - ez * clamp_d(r[0] - a[0]) == 0;
}

int collide_edges(const Track *t, int sec, CollideEdges *e)
{
	const TrkSection *s = track_section(t, sec);
	CollideEdges o;

	if (!s)
		return -1;
	for (int k = 0; k < 4; k++) {
		const TrkVertex *v = track_vertex(t, s->edges[k]);

		o.p[k][0] = v ? v->x : 0;
		o.p[k][1] = v ? v->z : 0;
	}
	o.fallback = irregular_edge(o.p[0], o.p[2], o.p[1]) || irregular_edge(o.p[1], o.p[3], o.p[0]);
	if (o.fallback) {
		for (int side = 0; side < 2; side++) {
			int32_t sgn = side ? 1 : -1;

			for (int ax = 0; ax < 2; ax++) {
				int i = ax ? 2 : 0;                     /* x, then z */
				int32_t start = s->centre[i] + ((sgn * s->right[i] * s->half_width) >> 12);

				o.p[side][ax] = start;
				o.p[side + 2][ax] = start + ((s->forward[i] * s->length) >> 12);
			}
		}
	}
	*e = o;
	return o.fallback;
}

int32_t collide_edge_dist(const int32_t seg[6], const int32_t p[2], int32_t n[2])
{
	int32_t ex = seg[2] - seg[0], ez = seg[3] - seg[1], len, s, cr;

	n[0] = n[1] = 0;
	len = (int32_t) collide_isqrt((uint32_t) (ex * ex + ez * ez));
	if (len == 0)
		return 0;
	s = ex * clamp_d(seg[5] - seg[1]) - ez * clamp_d(seg[4] - seg[0]) < 0 ? -1 : 1;
	cr = ex * clamp_d(p[1] - seg[1]) - ez * clamp_d(p[0] - seg[0]);
	n[0] = (s * -ez * 4096) / len;
	n[1] = (s * ex * 4096) / len;
	return (s * cr) / len;
}

/* ---- the section ---------------------------------------------------------------------------------------------------------- */

/* -1: move to prev, +1: move to next, 0: stay. */
static int slab_move(const Track *t, int sec, const int32_t pos[3])
{
	CollideEdges e;
	int32_t p[2] = { pos[0], pos[2] }, n[2], ds, de;
	int32_t start[6], end[6];

	collide_edges(t, sec, &e);
	for (int k = 0; k < 2; k++) {
		start[k] = e.p[0][k]; start[2 + k] = e.p[1][k]; start[4 + k] = e.p[2][k];
		end[k] = e.p[2][k];   end[2 + k] = e.p[3][k];   end[4 + k] = e.p[0][k];
	}
	ds = collide_edge_dist(start, p, n);
	de = collide_edge_dist(end, p, n);
	if (de <= 0)
		return 1;
	return ds < 0 ? -1 : 0;
}

/* Walks from `cur`; returns the section it stopped on and sets *settled to 0 if it still wanted to move. */
static int walk(const Track *t, int cur, const int32_t pos[3], int *settled)
{
	for (int moves = 0;; moves++) {
		int m = slab_move(t, cur, pos);

		if (m == 0) {
			*settled = 1;
			return cur;
		}
		if (moves == COLL_WALK) {
			*settled = 0;
			return cur;
		}
		cur = m > 0 ? track_section(t, cur)->next : track_section(t, cur)->prev;
	}
}

int collide_section(const Track *t, int cur, const int32_t pos[3])
{
	int ok;

	if (t->section_count <= 0)
		return -1;
	if (cur < 0 || cur >= t->section_count)
		cur = track_nearest_brute(t, pos);
	cur = walk(t, cur, pos, &ok);
	if (ok)
		return cur;
	return walk(t, track_nearest_brute(t, pos), pos, &ok);
}

/* ---- the ground and the face ---------------------------------------------------------------------------------------------- */

int32_t collide_ground(const Track *t, int sec, const int32_t pos[3])
{
	const TrkSection *s = track_section(t, sec);
	int32_t num, uy;

	if (!s)
		return 0;
	uy = s->up[1];
	if (uy < 256 && uy > -256)
		return s->centre[1];
	num = s->up[0] * clamp_d(pos[0] - s->centre[0]) + s->up[2] * clamp_d(pos[2] - s->centre[2]);
	return s->centre[1] + (-num) / uy;
}

int collide_floor_face(const Track *t, int sec, const int32_t pos[3])
{
	const TrkSection *s = track_section(t, sec);

	if (!s)
		return -1;
	for (int i = 0; i < s->face_count; i++) {
		const TrkFace *f = track_face(t, s->first_face + i);
		int32_t c[4][2];
		int plus = 0, minus = 0;

		if (!f || !(f->flags & TRK_FLOOR))
			continue;
		for (int k = 0; k < 4; k++) {
			static const uint8_t order[4] = { 0, 1, 3, 2 };
			const TrkVertex *v = track_vertex(t, f->v[order[k]]);

			c[k][0] = v ? v->x : 0;
			c[k][1] = v ? v->z : 0;
		}
		for (int k = 0; k < 4; k++) {
			const int32_t *a = c[k], *b = c[(k + 1) & 3];
			int32_t cr = (b[0] - a[0]) * clamp_d(pos[2] - a[1]) - (b[1] - a[1]) * clamp_d(pos[0] - a[0]);

			plus += cr > 0;
			minus += cr < 0;
		}
		if (!(plus && minus))
			return s->first_face + i;
	}
	return -1;
}

/* ---- the step ------------------------------------------------------------------------------------------------------------- */

static void refresh_vel(Ship *s)
{
	int32_t f[3];

	ship_forward(s, f);
	for (int i = 0; i < 3; i++)
		s->vel[i] = fx_mul(f[i], s->speed);
}

void collide_respawn(const Track *t, Ship *s, int sec)
{
	const TrkSection *c = track_section(t, sec);

	if (!c)
		return;
	for (int i = 0; i < 3; i++) {
		s->pos[i] = c->centre[i] + ((c->up[i] * ship_cfg.hover) >> 12);
		s->pos_frac[i] = 0;
		s->vel[i] = 0;
	}
	s->speed = s->roll = s->yaw_vel = 0;
	s->yaw = heading_angle(c->forward[0], c->forward[2]) << ANGLE_SHIFT;
	s->pitch = pitch_angle(c->forward[1]) * (1 << ANGLE_SHIFT);
}

int collide_ship(const Track *t, Ship *s)
{
	const CollideCfg *c = &collide_cfg;
	CollideState *st = &collide_state;
	CollideEdges e;
	int32_t p[2], seg[2][6], n[2][2], d[2], edge[2][2];
	int result = 0, face;

	ship_section = collide_section(t, ship_section, s->pos);
	if (ship_section < 0)
		return 0;
	collide_edges(t, ship_section, &e);
	p[0] = s->pos[0];
	p[1] = s->pos[2];
	for (int k = 0; k < 2; k++) {                       /* 0: left (p0 -> p2, reference p1), 1: right (p1 -> p3, reference p0) */
		const int32_t *a = e.p[k], *b = e.p[k + 2], *r = e.p[1 - k];

		seg[k][0] = a[0]; seg[k][1] = a[1]; seg[k][2] = b[0]; seg[k][3] = b[1]; seg[k][4] = r[0]; seg[k][5] = r[1];
		edge[k][0] = b[0] - a[0];
		edge[k][1] = b[1] - a[1];
		d[k] = collide_edge_dist(seg[k], p, n[k]);
	}
	st->dist_left = d[0];
	st->dist_right = d[1];
	if (d[0] < -c->off_limit || d[1] < -c->off_limit) {
		collide_respawn(t, s, ship_section);
		st->respawns++;
		st->on_boost = 0;
		return COLL_RESPAWN;
	}
	for (int k = 0; k < 2; k++) {
		int32_t depth, f[3], dot;

		if (d[k] >= c->radius)
			continue;
		result |= k ? COLL_HIT_RIGHT : COLL_HIT_LEFT;
		st->hits++;
		depth = c->radius - d[k];
		s->pos[0] += (n[k][0] * depth) >> 12;
		s->pos[2] += (n[k][1] * depth) >> 12;
		ship_forward(s, f);
		dot = fx_mul(f[0], n[k][0]) + fx_mul(f[2], n[k][1]);
		if (dot < 0) {
			int32_t impact = -dot > 4096 ? 4096 : -dot;
			int32_t target = collide_heading(edge[k][0], edge[k][1]) << ANGLE_SHIFT;
			int32_t err = ((target - s->yaw + HALF) & ANGLE_MASK) - HALF;

			s->speed -= fx_mul(s->speed, fx_mul(c->wall_damp, impact));
			s->yaw = (s->yaw + fx_mul(err, c->yaw_fix)) & ANGLE_MASK;
			s->yaw_vel = 0;
			refresh_vel(s);
		}
		if (ship_ticks - st->last_hit >= c->thud_gap) {
			st->thuds++;
			audio_event(EV_THUD);
			result |= COLL_THUD;
		}
		st->last_hit = ship_ticks;
	}
	s->pos[1] = collide_ground(t, ship_section, s->pos) - ship_cfg.hover;
	s->pos_frac[1] = 0;
	face = collide_floor_face(t, ship_section, s->pos);
	st->face = face;
	{
		const TrkFace *f = track_face(t, face);
		int on = f && (f->flags & TRK_BOOST) ? 1 : 0;

		if (on && !st->on_boost) {
			s->speed += c->boost_impulse;
			if (s->speed > ship_cfg.speed_cap)
				s->speed = ship_cfg.speed_cap;
			refresh_vel(s);
			st->boosts++;
			audio_event(EV_BOOST);
			result |= COLL_BOOST;
		}
		st->on_boost = on;
	}
	return result;
}

void collide_format(void)
{
	snprintf(collide_text, sizeof collide_text, "L%5d R%5d F%3d", (int) collide_state.dist_left, (int) collide_state.dist_right,
	         (int) collide_state.face);
}
