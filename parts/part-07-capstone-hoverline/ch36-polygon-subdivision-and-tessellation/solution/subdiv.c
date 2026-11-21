#include <stdint.h>
#include <psxgpu.h>
#include <psxgte.h>
#include <inline_c.h>
#include <psxe/ot.h>
#include "track_render.h"
#include "subdiv.h"

SubdivStats subdiv_stats;
int32_t     subdiv_debug;
int32_t     subdiv_reserve = SUBDIV_RESERVE;

/* ---- the criterion ---------------------------------------------------------------------------------------------------- */

int subdiv_level(int32_t z)
{
	if (z < SUBDIV_Z2)
		return 2;
	if (z < SUBDIV_Z1)
		return 1;
	return 0;
}

int subdiv_section_level(const Track *t, const TrkSection *s)
{
	int32_t z = 0x7FFFFFFF;

	for (int k = 0; k < 4; k++) {
		int i = s->edges[k];

		if (track_vertex_prepare(t, i) == VS_OK && trk_sz[i] >= TRK_NEAR_Z && trk_sz[i] < z)
			z = trk_sz[i];
	}
	return z == 0x7FFFFFFF ? 0 : subdiv_level(z);
}

int subdiv_budget_level(int level, size_t leaf_bytes)
{
	while (level > 0 && (int32_t) ot_bytes_left() < subdiv_reserve + (((int32_t) leaf_bytes << (2 * level)) + (int32_t) leaf_bytes))
		level--;
	return level;
}

/* ---- midpoints and projection ----------------------------------------------------------------------------------------- */

void subdiv_mid(const SdVert *a, const SdVert *b, SdVert *m)
{
	m->p.vx = (a->p.vx + b->p.vx) >> 1;
	m->p.vy = (a->p.vy + b->p.vy) >> 1;
	m->p.vz = (a->p.vz + b->p.vz) >> 1;
	m->u = (a->u + b->u) >> 1;               /* exact: the texel between two texels, rounded down; never outside the tile */
	m->v = (a->v + b->v) >> 1;
}

void subdiv_project(SdVert *v, int n)
{
	SdVert *v1 = n > 1 ? &v[1] : &v[0], *v2 = n > 2 ? &v[2] : &v[0];
	uint32_t xy[3];
	int32_t  z[3];

	__asm__ volatile("" ::: "memory");       /* gte_ldv3's asm has no memory clobber: the stores of p must be done first */
	gte_ldv3(&v[0].p, &v1->p, &v2->p);
	gte_rtpt();
	gte_stsxy3(&xy[0], &xy[1], &xy[2]);
	gte_stsz3(&z[0], &z[1], &z[2]);
	for (int k = 0; k < n; k++) {
		v[k].sxy = xy[k];
		v[k].sz = z[k];
	}
}

/* ---- the recursion ---------------------------------------------------------------------------------------------------- */

typedef struct {
	const TrkFace *f;
	int      textured, level;
	uint16_t tpage, clut;
	int32_t  maxotz;                 /* the largest AVSZ4 of the leaves linked: the backing quad goes behind them */
	int      drawn, dropped, near, big, back;
} SdFace;

static void leaf(SdFace *F, const SdVert q[4], int depth)
{
	int32_t area, otz;
	int minx, maxx, miny, maxy;
	uint32_t sxy[4];
	uint8_t uv[8];

	for (int k = 0; k < 4; k++) {
		if (q[k].sz < TRK_NEAR_Z) {
			F->near++;
			subdiv_stats.leaves_near++;
			return;
		}
	}
	gte_ldsxy3(q[0].sxy, q[1].sxy, q[2].sxy);
	gte_nclip();
	gte_stopz(&area);
	if (area <= 0) {
		F->back++;
		subdiv_stats.leaves_back++;
		return;
	}
	minx = maxx = (int16_t) q[0].sxy;
	miny = maxy = (int16_t) (q[0].sxy >> 16);
	for (int k = 1; k < 4; k++) {
		int x = (int16_t) q[k].sxy, y = (int16_t) (q[k].sxy >> 16);

		if (x < minx) minx = x;
		if (x > maxx) maxx = x;
		if (y < miny) miny = y;
		if (y > maxy) maxy = y;
	}
	if (maxx - minx > TRK_MAX_W || maxy - miny > TRK_MAX_H) {
		F->big++;
		subdiv_stats.leaves_big++;
		return;
	}
	for (int k = 0; k < 4; k++) {
		sxy[k] = q[k].sxy;
		uv[2 * k] = q[k].u;
		uv[2 * k + 1] = q[k].v;
	}
	gte_ldsz4(q[0].sz, q[1].sz, q[2].sz, q[3].sz);
	gte_avsz4();
	gte_stotz(&otz);
	if (!track_emit(F->f, F->textured, sxy, uv, F->tpage, F->clut, otz, depth)) {
		F->dropped++;
		subdiv_stats.leaves_dropped++;
		return;
	}
	F->drawn++;
	if (otz > F->maxotz)
		F->maxotz = otz;
	(&subdiv_stats.leaves_drawn0)[depth]++;
}

static void split(SdFace *F, const SdVert q[4], int depth)
{
	SdVert m[5];                     /* m01, m02, m13, m23, center */
	SdVert c[4][4];

	if (depth == F->level) {
		leaf(F, q, depth);
		return;
	}
	subdiv_mid(&q[0], &q[1], &m[0]);
	subdiv_mid(&q[0], &q[2], &m[1]);
	subdiv_mid(&q[1], &q[3], &m[2]);
	subdiv_mid(&q[2], &q[3], &m[3]);
	subdiv_mid(&m[0], &m[3], &m[4]);
	subdiv_project(&m[0], 3);
	subdiv_project(&m[3], 2);
	c[0][0] = q[0];   c[0][1] = m[0];   c[0][2] = m[1];   c[0][3] = m[4];
	c[1][0] = m[0];   c[1][1] = q[1];   c[1][2] = m[4];   c[1][3] = m[2];
	c[2][0] = m[1];   c[2][1] = m[4];   c[2][2] = q[2];   c[2][3] = m[3];
	c[3][0] = m[4];   c[3][1] = m[2];   c[3][2] = m[3];   c[3][3] = q[3];
	for (int k = 0; k < 4; k++)
		split(F, c[k], depth + 1);
}

int subdiv_face(const TrkFace *f, SdVert a[4], int level, int textured, uint16_t tpage, uint16_t clut)
{
	SdFace F = { .f = f, .textured = textured, .level = level, .tpage = tpage, .clut = clut };
	int back_ok = 1, minx, maxx, miny, maxy;

	split(&F, a, 0);
	/* the backing quad (README 5.8): the whole face once, behind its leaves, only when the face as a whole could be drawn (nothing near, not too big) */
	minx = maxx = (int16_t) a[0].sxy;
	miny = maxy = (int16_t) (a[0].sxy >> 16);
	for (int k = 0; k < 4; k++) {
		int x = (int16_t) a[k].sxy, y = (int16_t) (a[k].sxy >> 16);

		if (a[k].sz < TRK_NEAR_Z)
			back_ok = 0;
		if (x < minx) minx = x;
		if (x > maxx) maxx = x;
		if (y < miny) miny = y;
		if (y > maxy) maxy = y;
	}
	if (maxx - minx > TRK_MAX_W || maxy - miny > TRK_MAX_H)
		back_ok = 0;
	if (F.drawn && back_ok) {
		uint32_t sxy[4];
		uint8_t uv[8];

		for (int k = 0; k < 4; k++) {
			sxy[k] = a[k].sxy;
			uv[2 * k] = a[k].u;
			uv[2 * k + 1] = a[k].v;
		}
		if (track_emit(f, textured, sxy, uv, tpage, clut, F.maxotz, -1))
			subdiv_stats.backings++;
		else
			subdiv_stats.leaves_dropped++;
	}
	return F.drawn ? SD_DRAWN : F.dropped ? SD_DROPPED : F.near ? SD_NEAR : F.big ? SD_BIG : SD_BACK;
}
