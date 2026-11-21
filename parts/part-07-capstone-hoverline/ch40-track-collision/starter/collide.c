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

static __attribute__((unused)) int32_t clamp_d(int32_t v)   /* given: README 5.2 */
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

/* ---- you write: the edges (README 5.3) ------------------------------------------------------------------------------------- */

int collide_edges(const Track *t, int sec, CollideEdges *e)
{
	(void) t; (void) sec; (void) e;
	return -1;                                          /* TODO README 7.3 step 1 */
}

int32_t collide_edge_dist(const int32_t seg[6], const int32_t p[2], int32_t n[2])
{
	(void) seg; (void) p;
	n[0] = n[1] = 0;
	return 0;                                           /* TODO README 7.3 step 1 */
}

/* ---- the section ------------------------------------------------------------------------------------------------------------ */

int collide_section(const Track *t, int cur, const int32_t pos[3])
{
	(void) t; (void) pos;
	return cur;                                         /* TODO README 7.3 step 2: walk the ring lines */
}

/* ---- the ground and the face ------------------------------------------------------------------------------------------------ */

int32_t collide_ground(const Track *t, int sec, const int32_t pos[3])
{
	(void) t; (void) sec; (void) pos;
	return 0;                                           /* TODO README 7.3 step 3 */
}

int collide_floor_face(const Track *t, int sec, const int32_t pos[3])
{
	(void) t; (void) sec; (void) pos;
	return -1;                                          /* TODO README 7.3 step 3 */
}

/* ---- the step --------------------------------------------------------------------------------------------------------------- */

void collide_respawn(const Track *t, Ship *s, int sec)
{
	(void) t; (void) s; (void) sec;                     /* TODO README 7.3 step 5 */
}

int collide_ship(const Track *t, Ship *s)
{
	/* A placeholder so the starter still scrolls the track: Chapter 38's nearest section, no collision. TODO README 7.3 step 4: replace the body. */
	ship_section = track_nearest_update(t, s->pos, ship_section);
	return 0;
}

void collide_format(void)
{
	collide_text[0] = 0;                                /* TODO README 7.3 step 6 */
}
