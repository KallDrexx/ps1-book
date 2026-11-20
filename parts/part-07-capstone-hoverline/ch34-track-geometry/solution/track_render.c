#include <stdint.h>
#include <string.h>
#include <psxgpu.h>
#include <psxgte.h>
#include <inline_c.h>
#include <psxe/ot.h>
#include "camera.h"
#include "render.h"
#include "track_render.h"

SVECTOR    trk_rel[TRK_MAX_VERTICES];
uint32_t   trk_sxy[TRK_MAX_VERTICES];
int32_t    trk_sz[TRK_MAX_VERTICES];
uint8_t    trk_vstate[TRK_MAX_VERTICES];
TrackStats track_stats;
int32_t    wire_mode;

/* A closed outline: GPU command 0x48, a flat POLYLINE of five points (the first repeated at the end), ended by the
   terminator word 0x55555555. 32 bytes; the tag's length is 7 words. */
typedef struct {
	uint32_t tag;
	uint32_t rgbc;                   /* r | g << 8 | b << 16 | 0x48 << 24 */
	uint32_t xy[5];
	uint32_t term;
} LINE_P5;
_Static_assert(sizeof(LINE_P5) == 32, "LINE_P5 is 32 bytes");

static int budget_gone;              /* the primitive buffer ran out in this track_draw */

/* Load a MATRIX into the GTE (the SDK macros clobber $t0/$t1; Chapter 25). */
static __attribute__((noipa)) void load_matrix(const MATRIX *m)
{
	gte_SetRotMatrix(m);
	gte_SetTransMatrix(m);
}

uint32_t track_colour(uint16_t flags)
{
	if (flags & TRK_START)
		return COL_START;
	if (flags & TRK_BOOST)
		return COL_BOOST;
	if (flags & TRK_WALL)
		return COL_WALL;
	if (flags & TRK_FLOOR)
		return COL_FLOOR;
	return COL_OTHER;
}

static int32_t abs32(int32_t v) { return v < 0 ? -v : v; }

/* Make vertex i camera-relative and project it, once per track_draw. Returns VS_OK or VS_FAR. */
static int vertex_prepare(const Track *t, int i)
{
	const TrkVertex *v = &t->vertices[i];
	int32_t dx, dy, dz;

	if (trk_vstate[i] != VS_UNSEEN)
		return trk_vstate[i];
	dx = v->x - cam_eye.vx;                          /* 32-bit: the difference is what has to fit in 16 bits */
	dy = v->y - cam_eye.vy;
	dz = v->z - cam_eye.vz;
	if (abs32(dx) > TRK_FAR_LIMIT || abs32(dy) > TRK_FAR_LIMIT || abs32(dz) > TRK_FAR_LIMIT)
		return trk_vstate[i] = VS_FAR;
	trk_rel[i].vx = dx;
	trk_rel[i].vy = dy;
	trk_rel[i].vz = dz;
	gte_ldv0(&trk_rel[i]);
	gte_rtps();
	gte_stsxy(&trk_sxy[i]);
	gte_stsz(&trk_sz[i]);
	return trk_vstate[i] = VS_OK;
}

static void draw_face(const Track *t, const TrkFace *f)
{
	const uint16_t *v = f->v;
	int far = 0, minx, maxx, miny, maxy;
	int32_t area, otz;
	size_t bytes = sizeof(POLY_F4) + (wire_mode ? sizeof(LINE_P5) : 0);
	POLY_F4 *fill;
	LINE_P5 *wire;
	int slot;

	track_stats.faces_seen++;
	for (int k = 0; k < 4; k++)                      /* classify all four: the verifier counts the vertices seen */
		if (vertex_prepare(t, v[k]) == VS_FAR)
			far = 1;
	if (far) {
		track_stats.faces_far++;
		return;
	}
	for (int k = 0; k < 4; k++) {
		if (trk_sz[v[k]] < TRK_NEAR_Z) {
			track_stats.faces_near++;
			return;
		}
	}
	gte_ldsxy3(trk_sxy[v[0]], trk_sxy[v[1]], trk_sxy[v[2]]);
	gte_nclip();
	gte_stopz(&area);
	if (area <= 0) {
		track_stats.faces_back++;
		return;
	}
	minx = maxx = (int16_t) trk_sxy[v[0]];
	miny = maxy = (int16_t) (trk_sxy[v[0]] >> 16);
	for (int k = 1; k < 4; k++) {
		int x = (int16_t) trk_sxy[v[k]], y = (int16_t) (trk_sxy[v[k]] >> 16);

		if (x < minx) minx = x;
		if (x > maxx) maxx = x;
		if (y < miny) miny = y;
		if (y > maxy) maxy = y;
	}
	if (maxx - minx > TRK_MAX_W || maxy - miny > TRK_MAX_H) {
		track_stats.faces_big++;
		return;
	}
	fill = budget_gone ? NULL : ot_alloc(bytes);
	if (!fill) {
		budget_gone = 1;
		track_stats.faces_dropped++;
		prims_dropped++;
		return;
	}
	gte_ldsz4(trk_sz[v[0]], trk_sz[v[1]], trk_sz[v[2]], trk_sz[v[3]]);
	gte_avsz4();
	gte_stotz(&otz);
	slot = otz >> OTZ_SHIFT;

	setPolyF4(fill);
	{
		uint32_t c = track_colour(f->flags);

		setRGB0(fill, c & 255, (c >> 8) & 255, (c >> 16) & 255);
	}
	*(uint32_t *) &fill->x0 = trk_sxy[v[0]];
	*(uint32_t *) &fill->x1 = trk_sxy[v[1]];
	*(uint32_t *) &fill->x2 = trk_sxy[v[2]];
	*(uint32_t *) &fill->x3 = trk_sxy[v[3]];
	if (wire_mode) {                                 /* same slot, linked first so that it is drawn AFTER the fill (addPrim puts the newest first) */
		wire = (LINE_P5 *) ((uint8_t *) fill + sizeof(POLY_F4));
		wire->tag = (uint32_t) 7 << 24;                  /* seven words follow the tag; ot_add fills in the link */
		wire->rgbc = COL_WIRE | (0x48u << 24);
		wire->xy[0] = trk_sxy[v[0]];
		wire->xy[1] = trk_sxy[v[1]];
		wire->xy[2] = trk_sxy[v[3]];                 /* Z order: the outline goes v0, v1, v3, v2, back to v0 */
		wire->xy[3] = trk_sxy[v[2]];
		wire->xy[4] = trk_sxy[v[0]];
		wire->term = 0x55555555;
		ot_add(wire, slot);
		track_stats.wire_prims++;
		prims_submitted++;
	}
	ot_add(fill, slot);
	track_stats.faces_drawn++;
	prims_submitted++;
}

void track_draw(const Track *t, int first, int count)
{
	MATRIX vr = view_mtx;
	int n = t->section_count;

	memset(&track_stats, 0, sizeof track_stats);
	memset(trk_vstate, VS_UNSEEN, sizeof trk_vstate);
	budget_gone = 0;
	if (n <= 0 || count <= 0)
		return;
	if (count > n)
		count = n;
	first = ((first % n) + n) % n;
	vr.t[0] = vr.t[1] = vr.t[2] = 0;                 /* rotation only: the eye is NOT in TR; d = vertex - eye is already camera-relative */
	load_matrix(&vr);
	for (int k = 0; k < count; k++) {
		const TrkSection *s = &t->sections[(first + k) % n];

		for (int j = 0; j < s->face_count; j++)
			draw_face(t, &t->faces[s->first_face + j]);
	}
}
