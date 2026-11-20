#include <stdint.h>
#include <stdio.h>
#include "track.h"
#include "track_render.h"
#include "track_vis.h"

int32_t ship_section = -1;
int32_t prims_this_frame;
int32_t vis_ahead = VIS_AHEAD;
int32_t vis_behind = VIS_BEHIND;
int32_t vis_mode;
int32_t vis_lost = VIS_LOST;
int32_t vis_brute_runs;
int32_t vis_first;
int32_t vis_count;
int32_t vis_list_done = 1;
char    vis_text[32];

static uint64_t dist2(const Track *t, int i, const int32_t pos[3])
{
	const TrkSection *s = &t->sections[i];
	int64_t dx = (int64_t) pos[0] - s->centre[0];
	int64_t dy = (int64_t) pos[1] - s->centre[1];
	int64_t dz = (int64_t) pos[2] - s->centre[2];

	return (uint64_t) (dx * dx) + (uint64_t) (dy * dy) + (uint64_t) (dz * dz);
}

int track_nearest_brute(const Track *t, const int32_t pos[3])
{
	int best = -1;
	uint64_t bd = 0;

	vis_brute_runs++;
	for (int i = 0; i < t->section_count; i++) {
		uint64_t d = dist2(t, i, pos);

		if (best < 0 || d < bd) {                    /* strictly smaller: the first (lowest) index wins a tie */
			best = i;
			bd = d;
		}
	}
	return best;
}

int track_nearest_update(const Track *t, const int32_t pos[3], int cur)
{
	uint64_t cd, lost2;
	int steps;

	if (cur < 0 || cur >= t->section_count)
		return track_nearest_brute(t, pos);
	cd = dist2(t, cur, pos);
	for (steps = 0; steps <= VIS_MAX_STEPS; steps++) {
		const TrkSection *s = &t->sections[cur];
		int cand[2] = { s->prev, s->next };
		int best = cur;
		uint64_t bd = cd;

		for (int k = 0; k < 2; k++) {
			uint64_t d = dist2(t, cand[k], pos);

			if (d < bd || (d == bd && cand[k] < best)) {
				best = cand[k];
				bd = d;
			}
		}
		if (best == cur)
			break;
		cur = best;
		cd = bd;
	}
	lost2 = (uint64_t) (vis_lost < 0 ? 0 : vis_lost);
	lost2 *= lost2;
	if (steps > VIS_MAX_STEPS || cd > lost2)
		return track_nearest_brute(t, pos);
	return cur;
}

void track_window(const Track *t, int s, int *first, int *count)
{
	int n = t->section_count, a = vis_ahead < 0 ? 0 : vis_ahead, b = vis_behind < 0 ? 0 : vis_behind;
	int c = a + b + 1;

	if (c >= n) {
		*first = 0;
		*count = n;
	} else {
		*first = ((s - b) % n + n) % n;
		*count = c;
	}
	vis_first = *first;
	vis_count = *count;
}

int track_draw_list(const Track *t, int s)
{
	const TrkSection *sec;

	if (s < 0 || s >= t->section_count)
		return 0;
	sec = &t->sections[s];
	vis_first = t->vis[sec->vis_first];
	vis_count = sec->vis_count;
	track_draw_begin(t);
	for (int k = 0; k < sec->vis_count; k++)
		track_draw_section(t, t->vis[sec->vis_first + k]);
	return sec->vis_count;
}

void track_draw_visible(const Track *t, int s)
{
	int first, count;

	if (vis_mode == 1 && track_draw_list(t, s))
		return;
	track_window(t, s, &first, &count);
	track_draw(t, first, count);
}

void vis_readout_format(void)
{
	snprintf(vis_text, sizeof vis_text, "SEC %3d  PRIMS %4d", (int) ship_section, (int) prims_this_frame);
}
