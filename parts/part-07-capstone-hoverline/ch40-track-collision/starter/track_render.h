#ifndef TRACK_RENDER_H
#define TRACK_RENDER_H

#include <stddef.h>
#include <stdint.h>
#include <psxgte.h>
#include "track.h"

/* ---- the rules every face goes through (README 5.6) ---------------------------------------------------------------- */

#define TRK_FAR_LIMIT 32767          /* a vertex with any |vertex - eye| component above this cannot be loaded into the GTE */
#define TRK_NEAR_Z    128            /* a face with a vertex nearer than this (view z) is skipped */
#define TRK_MAX_W     1023           /* a face wider than this many pixels is skipped: the GPU would drop it ... */
#define TRK_MAX_H     511            /* ... and taller than this */

/* The legend: the colour a face is drawn in, as a GPU word (r | g << 8 | b << 16). */
#define COL_FLOOR   0x00504846       /* ( 70,  72,  80)  grey */
#define COL_WALL    0x00783C28       /* ( 40,  60, 120)  blue */
#define COL_BOOST   0x00FFC800       /* (  0, 200, 255)  cyan */
#define COL_START   0x00F0F0F0       /* (240, 240, 240)  white */
#define COL_OTHER   0x00FF00FF       /* magenta: a face with none of the four flags */
#define COL_WIRE    0x0000FFFF       /* (255, 255,   0)  yellow, the wireframe overlay */

/* ---- state the verifier reads --------------------------------------------------------------------------------------- */

/* How each vertex was handled by the last track_draw. A vertex is only looked at when a face of the drawn range uses it. */
#define VS_UNSEEN 0                  /* no face of the range uses it */
#define VS_OK     1                  /* camera-relative d is within +-TRK_FAR_LIMIT: trk_rel[i] = d, projected: trk_sxy[i], trk_sz[i] */
#define VS_FAR    2                  /* some |d| component is above TRK_FAR_LIMIT: nothing was loaded or projected */

extern SVECTOR  trk_rel[TRK_MAX_VERTICES];     /* vertex - eye, as it was loaded into the GTE (valid where VS_OK) */
extern uint32_t trk_sxy[TRK_MAX_VERTICES];     /* the projected screen position: x in the low 16 bits, y in the high 16 */
extern int32_t  trk_sz[TRK_MAX_VERTICES];      /* the projected view-space depth */
extern uint8_t  trk_vstate[TRK_MAX_VERTICES];  /* VS_UNSEEN / VS_OK / VS_FAR */

/* Where every face of the last track_draw went: each face of the range is in exactly ONE of the counters below
   (faces_seen = the sum of the other six; wire_prims counts packets). The verifier reads these 8 words in this order. */
typedef struct {
	int32_t faces_seen;              /* faces of the drawn sections */
	int32_t faces_far;               /* some vertex is VS_FAR */
	int32_t faces_near;              /* some vertex nearer than TRK_NEAR_Z */
	int32_t faces_back;              /* NCLIP: facing away or edge-on */
	int32_t faces_big;               /* wider than TRK_MAX_W or taller than TRK_MAX_H */
	int32_t faces_dropped;           /* passed every test but the primitive buffer was full */
	int32_t faces_drawn;             /* a quad was linked (a split face counts once, when any of its leaves was; Chapter 36, README 5.6) */
	int32_t wire_prims;              /* outline packets linked */
} TrackStats;
extern TrackStats track_stats;

extern int32_t wire_mode;            /* 0 = filled faces only, 1 = with the wireframe overlay (toggled in game_update) */

/* ---- shared with Chapter 36's subdiv.c --------------------------------------------------------------------------------- */

/* Make vertex i camera-relative and project it (once per track_draw). Returns VS_OK or VS_FAR. */
int track_vertex_prepare(const Track *t, int i);

/* Bytes one drawn quad takes in the primitive buffer: 40 textured or 24 flat, plus 32 for its outline when wire_mode or subdiv_debug is on. */
size_t track_leaf_bytes(int textured);

/* Link one quad (Chapter 35's fill and outline code): `sxy` the four projected corners in Z order, `uv` the eight absolute texels (textured only),
   `otz` its depth (AVSZ4 of the corners); `depth` 0..2 picks the outline colour when subdiv_debug is on (-1: a backing quad, which has no outline). Returns 1, or 0 when the primitive
   buffer is full (then prims_dropped is counted and every later quad of this track_draw is dropped too). Counts prims_submitted and wire_prims. */
int track_emit(const TrkFace *f, int textured, const uint32_t sxy[4], const uint8_t uv[8], uint16_t tpage, uint16_t clut, int32_t otz, int depth);

/* The colour of a face with these flags (a GPU word): START, else BOOST, else WALL, else FLOOR, else COL_OTHER. */
uint32_t track_colour(uint16_t flags);

/* The two halves of track_draw, for callers that choose the sections themselves (Chapter 38). track_draw_begin resets track_stats and
   trk_vstate and loads the view rotation into the GTE; track_draw_section draws the faces of ONE section (an index outside the track draws nothing).
   Call begin once per frame, then any number of sections; every section drawn twice is drawn twice. */
void track_draw_begin(const Track *t);
void track_draw_section(const Track *t, int index);

/* Draw `count` consecutive sections starting at `first` (indices wrap modulo section_count; count above section_count
   is cut to section_count, count <= 0 draws nothing) for the camera in cam_eye / view_mtx. Resets track_stats and
   trk_vstate first. Every packet goes into the current frame's ordering table (README 5.6, 5.7). */
void track_draw(const Track *t, int first, int count);

#endif
