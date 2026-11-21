#ifndef TRACK_RENDER_H
#define TRACK_RENDER_H

#include <stdint.h>
#include <psxgte.h>
#include "track.h"

/* ---- the rules every face goes through (README 5.6) ---------------------------------------------------------------- */

#define TRK_FAR_LIMIT 32767          /* a vertex with any |vertex - eye| component above this cannot be loaded into the GTE */
#define TRK_NEAR_Z    128            /* a face with a vertex nearer than this (view z) is skipped */
#define TRK_MAX_W     1023           /* a face wider than this many pixels is skipped: the GPU would drop it ... */
#define TRK_MAX_H     511            /* ... and taller than this */

/* The legend: the color a face is drawn in, as a GPU word (r | g << 8 | b << 16). */
#define COL_FLOOR   0x00504846       /* ( 70,  72,  80)  gray */
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
   (faces_seen = the sum of the six that follow it; wire_prims counts packets, not faces). The verifier reads these 8 words in this order. */
typedef struct {
	int32_t faces_seen;              /* faces of the drawn sections */
	int32_t faces_far;               /* some vertex is VS_FAR */
	int32_t faces_near;              /* some vertex nearer than TRK_NEAR_Z */
	int32_t faces_back;              /* NCLIP: facing away or edge-on */
	int32_t faces_big;               /* wider than TRK_MAX_W or taller than TRK_MAX_H */
	int32_t faces_dropped;           /* passed every test but the primitive buffer was full */
	int32_t faces_drawn;             /* a POLY_F4 was linked (and, in wire mode, a line packet with it) */
	int32_t wire_prims;              /* line packets linked */
} TrackStats;
extern TrackStats track_stats;

extern int32_t wire_mode;            /* 0 = filled faces only, 1 = with the wireframe overlay (toggled in game_update) */

/* The color of a face with these flags (a GPU word): START, else BOOST, else WALL, else FLOOR, else COL_OTHER. */
uint32_t track_colour(uint16_t flags);

/* Draw `count` consecutive sections starting at `first` (indices wrap modulo section_count; count above section_count
   is cut to section_count, count <= 0 draws nothing) for the camera in cam_eye / view_mtx. Resets track_stats and
   trk_vstate first. Every packet goes into the current frame's ordering table (README 5.6, 5.7). */
void track_draw(const Track *t, int first, int count);

#endif
