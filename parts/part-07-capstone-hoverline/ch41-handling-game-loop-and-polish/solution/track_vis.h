#ifndef TRACK_VIS_H
#define TRACK_VIS_H

#include <stdint.h>
#include "track.h"

/* ---- state the verifier reads and patches (README 5) --------------------------------------------------------------------- */

extern int32_t ship_section;      /* the section nearest to the ship (the metric below); -1 until the game is entered */
extern int32_t prims_this_frame;  /* packets linked for the track and the ship in the last game frame (before the readout text) */
extern int32_t vis_ahead;         /* sections drawn ahead of ship_section: default VIS_AHEAD. Patchable */
extern int32_t vis_behind;        /* sections drawn behind it: default VIS_BEHIND. Patchable */
extern int32_t vis_mode;          /* 0 = a window of sections (the main path), 1 = the .TRK's visibility list (stretch). Patchable */
extern int32_t vis_lost;          /* world units: a result farther than this from the ship is not trusted (README 5.5). Default VIS_LOST. Patchable */
extern int32_t vis_brute_runs;    /* how many times the brute-force search ran since boot (the verifier counts them) */
extern int32_t vis_first;         /* the first section of the window drawn in the last frame, and ... */
extern int32_t vis_count;         /* ... how many sections it holds (list mode: the list's length) */
extern int32_t vis_list_done;     /* 1 if you implemented track_draw_list (the stretch goal), else 0 */
extern char    vis_text[32];      /* the readout line of the last frame, as it was drawn */

#define VIS_AHEAD   24            /* defaults: the manifest's vis_rule (Appendix E.10.5) */
#define VIS_BEHIND  4
#define VIS_LOST    4000          /* about four section lengths */
#define VIS_MAX_STEPS 4           /* neighbour steps one update may take before it gives up and searches everything */

/* The metric (README 5.3): d2(i) = dx^2 + dy^2 + dz^2 as an UNSIGNED 64-bit value, where each d is `pos - centre` computed in 64 bits
   (no overflow while every |d| is below 2^31, i.e. pos within about +-2,000,000,000 of the track: far beyond any world the format allows).
   The nearest section minimizes d2; a tie goes to the LOWEST section index. */

/* The nearest section by looking at every section: the one with the smallest d2 (lowest index on a tie).
   Returns -1 when the track has no sections. `pos` is the ship's position (world units). Increments vis_brute_runs. */
int track_nearest_brute(const Track *t, const int32_t pos[3]);

/* The incremental update (README 5.4). `cur` is last frame's answer.
   - cur outside 0..section_count-1 (including -1): the brute-force search.
   - otherwise start at `cur` and repeat: among the section, its `next` and its `prev` (by the links, never by index + 1) pick the one
     with the smallest (d2, index); if it is the section itself, stop; if not, move there. Up to VIS_MAX_STEPS moves are allowed
     (so up to VIS_MAX_STEPS + 1 looks); a walk that wants move number VIS_MAX_STEPS + 1 gives up.
   - if the walk gave up, or the section it stopped on is farther from `pos` than `vis_lost` (d2 > vis_lost^2): the result is the
     brute-force search instead. */
int track_nearest_update(const Track *t, const int32_t pos[3], int cur);

/* The window around section `s` (README 5.2): sections s - vis_behind .. s + vis_ahead along the loop, indices modulo section_count.
   *first = (s - vis_behind) mod n, *count = vis_behind + vis_ahead + 1; when that is n or more: *first = 0, *count = n (the whole track).
   A negative vis_ahead or vis_behind counts as 0. Sets vis_first and vis_count. */
void track_window(const Track *t, int s, int *first, int *count);

/* List mode (stretch): draw the sections of s's visibility slice with track_draw_begin / track_draw_section, in list order.
   Sets vis_first = the first entry and vis_count = the slice's length. Returns the number of sections drawn (0 = not implemented). */
int track_draw_list(const Track *t, int s);

/* The frame's picture of the track (called by draw_track): vis_mode 0: track_window(ship_section) then track_draw; vis_mode 1: track_draw_list. */
void track_draw_visible(const Track *t, int s);

/* The readout (README 5.7): writes "SEC nnn  PRIMS nnnn" (section right-aligned in 3 columns, packets in 4: printf "%3d" and "%4d") into
   vis_text (at most 31 characters + NUL), from ship_section and prims_this_frame. */
void vis_readout_format(void);

#endif
