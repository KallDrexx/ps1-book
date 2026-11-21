#ifndef SUBDIV_H
#define SUBDIV_H

#include <stddef.h>
#include <stdint.h>
#include <psxgte.h>
#include "track.h"

/* ---- the rules of Chapter 36 (README 5) ------------------------------------------------------------------------------- */

#define SUBDIV_MAX_LEVEL 2          /* a face is split at most twice: 1 -> 4 -> 16 quads */
#define SUBDIV_Z1        4000       /* nearest road-edge depth below this (view z): level >= 1 */
#define SUBDIV_Z2        2000       /* ... below this: level 2 */
#define SUBDIV_RESERVE   8192       /* bytes of the primitive buffer kept for the rest of the track (default of subdiv_reserve) */

/* The debug outline of a quad produced at depth 0, 1, 2 (GPU words, r | g << 8 | b << 16). Depth 0 is the Chapter 34 wireframe yellow. */
#define COL_LEVEL0 0x0000FFFF       /* (255, 255,   0)  yellow: not split */
#define COL_LEVEL1 0x00FFFF00       /* (  0, 255, 255)  cyan:   one split */
#define COL_LEVEL2 0x00FF00FF       /* (255,   0, 255)  magenta: two splits */

/* What subdiv_face returns: how the face as a whole is counted in track_stats. The first of these that applies. */
#define SD_DRAWN   0                /* at least one leaf quad was linked */
#define SD_DROPPED 1                /* none linked, and the primitive buffer was full for at least one */
#define SD_NEAR    2                /* none, and at least one leaf had a vertex nearer than TRK_NEAR_Z */
#define SD_BIG     3                /* none, and at least one leaf was too big for the GPU */
#define SD_BACK    4                /* every leaf faced away */

/* ---- state the verifier reads (13 words, in this order) ---------------------------------------------------------------- */
typedef struct {
	int32_t faces_level0;           /* faces that were not VS_FAR, by the level the CRITERION chose (before the budget rule) */
	int32_t faces_level1;
	int32_t faces_level2;
	int32_t leaves_drawn0;          /* quads linked, by depth: 0 = a whole face, 1 / 2 = a quarter / a sixteenth of one */
	int32_t leaves_drawn1;
	int32_t leaves_drawn2;
	int32_t leaves_near;            /* leaf quads skipped: a vertex nearer than TRK_NEAR_Z */
	int32_t leaves_back;            /* ... NCLIP says facing away */
	int32_t leaves_big;             /* ... wider than TRK_MAX_W or taller than TRK_MAX_H */
	int32_t leaves_dropped;         /* ... the primitive buffer was full */
	int32_t budget_cuts;            /* faces whose level the budget rule lowered */
	int32_t outlines;               /* debug outlines linked (subdiv_debug) */
	int32_t backings;               /* backing quads linked (README 5.8) */
} SubdivStats;
extern SubdivStats subdiv_stats;

extern int32_t subdiv_debug;        /* 1 = every quad drawn gets an outline in the colour of its depth (toggled in game_update) */
extern int32_t subdiv_reserve;      /* the budget rule's reserve in bytes; starts as SUBDIV_RESERVE; the verifier may patch it */

/* One vertex of a subdivided face. */
typedef struct {
	SVECTOR  p;                     /* camera-relative position (d = vertex - eye): the GTE input, always within s16 */
	int32_t  u, v;                  /* absolute texel position */
	uint32_t sxy;                   /* projected position: x in the low 16 bits, y in the high 16 */
	int32_t  sz;                    /* projected depth */
} SdVert;

/* The criterion (README 5.4). Level 0, 1 or 2 from the depth `z` of the nearest usable road-edge vertex of a section: 2 below SUBDIV_Z2, 1 below SUBDIV_Z1, else 0. */
int subdiv_level(int32_t z);

/* The level of every face of a section (README 5.4): z = the smallest `sz` among the section's four road-edge vertices (edges[0..3]) that are VS_OK
   and not nearer than TRK_NEAR_Z (none: level 0); then subdiv_level(z). Vertices are prepared with track_vertex_prepare. */
int subdiv_section_level(const Track *t, const TrkSection *s);

/* The budget rule (README 5.7): while level > 0 and ot_bytes_left() < subdiv_reserve + (4^level + 1) * leaf_bytes (the leaves and the backing quad), lower the level. Returns the level to use. */
int subdiv_budget_level(int level, size_t leaf_bytes);

/* The midpoint of two vertices (README 5.3): p, u, v each (a + b) >> 1 (arithmetic shift). Does not project. */
void subdiv_mid(const SdVert *a, const SdVert *b, SdVert *m);

/* Project n vertices (1..3 per RTPT; the GTE already holds the view rotation): fills sxy and sz. */
void subdiv_project(SdVert *v, int n);

/* Draw one face at `level` (1 or 2) as 4^level quads (README 5.5). `a[0..3]` are the face's own four vertices in Z order, already
   camera-relative and projected, with absolute UVs (for a flat face u, v are 0 and `textured` is 0). The GTE holds the view rotation.
   Splits recursively, culls and emits every leaf (README 5.6), then the backing quad (5.8). Returns SD_*. Updates subdiv_stats' leaf counters. */
int subdiv_face(const TrkFace *f, SdVert a[4], int level, int textured, uint16_t tpage, uint16_t clut);

#endif
