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

/* Everything below is yours (README 7.3). track_render.c is given and already calls these functions; with the stubs as they are, every
   section gets level 0 and the track is drawn as in Chapter 35, so the program runs from the first build. Read subdiv.h first. */

/* ---- the criterion (README 5.4) --------------------------------------------------------------------------------------- */

int subdiv_level(int32_t z)
{
	/* TODO (step 2): 2 below SUBDIV_Z2, 1 below SUBDIV_Z1, else 0. */
	(void) z;
	return 0;
}

int subdiv_section_level(const Track *t, const TrkSection *s)
{
	/* TODO (step 2): z = the smallest trk_sz among the section's four road-edge vertices (s->edges[0..3]) that track_vertex_prepare says VS_OK and
	   that are not nearer than TRK_NEAR_Z; none usable: level 0; otherwise subdiv_level(z). */
	(void) t;
	(void) s;
	return 0;
}

int subdiv_budget_level(int level, size_t leaf_bytes)
{
	/* TODO (step 6): README 5.7. As it stands the budget never cuts. */
	(void) leaf_bytes;
	return level;
}

/* ---- midpoints and projection (README 5.3, 5.5) -------------------------------------------------------------------------- */

void subdiv_mid(const SdVert *a, const SdVert *b, SdVert *m)
{
	/* TODO (step 3): p.vx/vy/vz, u and v: (a + b) >> 1 each, exactly. */
	(void) a;
	(void) b;
	(void) m;
}

void subdiv_project(SdVert *v, int n)
{
	/* TODO (step 3): n = 1..3 vertices through one RTPT (the GTE already holds the view rotation, TR = 0): sxy and sz of each.
	   Chapter 27: a memory barrier before gte_ldv3 (its asm has no "memory" clobber), and pad the unused slots with a valid vertex. */
	(void) v;
	(void) n;
}

/* ---- the recursion (README 5.5, 5.6, 5.8) -------------------------------------------------------------------------------- */

int subdiv_face(const TrkFace *f, SdVert a[4], int level, int textured, uint16_t tpage, uint16_t clut)
{
	/* TODO (steps 4 and 5): split `a` recursively `level` times (children in Z order), cull and emit every leaf with track_emit
	   (README 5.6: near, NCLIP, big, then the slot from AVSZ4), count it in subdiv_stats.leaves_drawn0..2 / leaves_near / ..., then
	   the backing quad (README 5.8, depth -1). Return SD_DRAWN, SD_DROPPED, SD_NEAR, SD_BIG or SD_BACK (the first that applies). */
	(void) f;
	(void) a;
	(void) level;
	(void) textured;
	(void) tpage;
	(void) clut;
	return SD_BACK;
}
