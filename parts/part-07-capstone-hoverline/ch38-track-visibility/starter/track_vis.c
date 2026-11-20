#include <stdint.h>
#include <stdio.h>
#include "track.h"
#include "track_render.h"
#include "track_vis.h"

/* Chapter 38: your work is in this file. Read track_vis.h first: it is the specification (README 7). */

int32_t ship_section = -1;
int32_t prims_this_frame;
int32_t vis_ahead = VIS_AHEAD;
int32_t vis_behind = VIS_BEHIND;
int32_t vis_mode;
int32_t vis_lost = VIS_LOST;
int32_t vis_brute_runs;
int32_t vis_first;
int32_t vis_count;
int32_t vis_list_done;               /* set to 1 when you have written track_draw_list (the stretch goal) */
char    vis_text[32];

/* TODO 1: the squared distance (README 5.3), then the brute-force search: the smallest, the lowest index on a tie. Count vis_brute_runs. */
int track_nearest_brute(const Track *t, const int32_t pos[3])
{
	(void) t;
	(void) pos;
	return 0;
}

/* TODO 2: the incremental update (README 5.4): the section and its prev / next links, at most VIS_MAX_STEPS moves,
   the full search when it gives up or the answer is farther than vis_lost. */
int track_nearest_update(const Track *t, const int32_t pos[3], int cur)
{
	(void) t;
	(void) pos;
	return cur;
}

/* TODO 3: the window (README 5.2). For now it is the whole track, as in Chapter 37. */
void track_window(const Track *t, int s, int *first, int *count)
{
	(void) s;
	*first = 0;
	*count = t->section_count;
	vis_first = *first;
	vis_count = *count;
}

/* STRETCH: draw the sections of s's visibility slice (README 5.8) with track_draw_begin and track_draw_section; then set vis_list_done = 1. */
int track_draw_list(const Track *t, int s)
{
	(void) t;
	(void) s;
	return 0;
}

/* Given: the frame's picture of the track. */
void track_draw_visible(const Track *t, int s)
{
	int first, count;

	if (vis_mode == 1 && track_draw_list(t, s))
		return;
	track_window(t, s, &first, &count);
	track_draw(t, first, count);
}

/* TODO 4: the readout text (README 5.7): "SEC nnn  PRIMS nnnn". */
void vis_readout_format(void)
{
	vis_text[0] = 0;
}
