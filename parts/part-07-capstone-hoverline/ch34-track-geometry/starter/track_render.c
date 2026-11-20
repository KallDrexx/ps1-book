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
   terminator word 0x55555555. 32 bytes; the tag's length is 7 words (README 5.8). */
typedef struct {
	uint32_t tag;
	uint32_t rgbc;                   /* r | g << 8 | b << 16 | 0x48 << 24 */
	uint32_t xy[5];                  /* x in the low 16 bits, y in the high 16 */
	uint32_t term;                   /* 0x55555555 */
} LINE_P5;
_Static_assert(sizeof(LINE_P5) == 32, "LINE_P5 is 32 bytes");

static int budget_gone;              /* the primitive buffer ran out in this track_draw: allocate nothing more */

/* Given: load a MATRIX into the GTE (the SDK macros clobber $t0/$t1; Chapter 25). Rotation AND translation registers. */
static __attribute__((noipa)) void load_matrix(const MATRIX *m)
{
	gte_SetRotMatrix(m);
	gte_SetTransMatrix(m);
}

uint32_t track_colour(uint16_t flags)
{
	/* TODO (README 7.3, step 3): the legend of track_render.h. START, else BOOST, else WALL, else FLOOR, else COL_OTHER. */
	(void) flags;
	return 0;
}

/* Make vertex i camera-relative and project it, at most once per track_draw; returns VS_OK or VS_FAR.
   TODO (step 4): d = vertex - cam_eye in 32 bits; any |component| above TRK_FAR_LIMIT -> trk_vstate[i] = VS_FAR, nothing loaded.
   Otherwise trk_rel[i] = d, gte_ldv0, gte_rtps, gte_stsxy -> trk_sxy[i], gte_stsz -> trk_sz[i], trk_vstate[i] = VS_OK. */
static __attribute__((unused)) int vertex_prepare(const Track *t, int i)
{
	(void) t;
	(void) i;
	return VS_FAR;
}

/* One face through the rules of README 5.6, each face landing in exactly one track_stats bucket.
   TODO (step 5): faces_seen++; classify ALL FOUR vertices with vertex_prepare; then, in this order:
   any VS_FAR -> faces_far; any trk_sz < TRK_NEAR_Z -> faces_near; NCLIP of v0 v1 v2 <= 0 -> faces_back;
   screen box wider than TRK_MAX_W or taller than TRK_MAX_H -> faces_big; ot_alloc fails -> faces_dropped (and prims_dropped,
   and no more allocations in this track_draw); else link a POLY_F4 in the legend colour (and, with wire_mode, a LINE_P5)
   at slot (AVSZ4 of the four trk_sz) >> OTZ_SHIFT, faces_drawn++ (wire_prims++), prims_submitted += packets. */
static __attribute__((unused)) void draw_face(const Track *t, const TrkFace *f)
{
	(void) t;
	(void) f;
	(void) budget_gone;
}

void track_draw(const Track *t, int first, int count)
{
	memset(&track_stats, 0, sizeof track_stats);
	memset(trk_vstate, VS_UNSEEN, sizeof trk_vstate);
	budget_gone = 0;
	/* TODO (step 6): cut and wrap the window; load the view ROTATION (a copy of view_mtx with t = 0) with load_matrix;
	   draw_face for every face of every section of the window. */
	(void) t;
	(void) first;
	(void) count;
	(void) load_matrix;
}
