#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "track.h"
#include "ship.h"
#include "game.h"
#include "race.h"

Race race;
RaceCfg race_cfg = { .laps = 3, .wrong_way = 2, .count_from = 3 };
int32_t race_best;
char race_text[RACE_LINES][RACE_LINE_LEN];

void race_reset(Race *r)
{
	memset(r, 0, sizeof *r);
	r->prev_section = -1;
}

int32_t race_hz(void)
{
	return video_mode ? 50 : 60;
}

static int32_t clampi(int32_t v, int32_t lo, int32_t hi)
{
	return v < lo ? lo : (v > hi ? hi : v);
}

int race_section_step(const Track *t, int prev, int cur)
{
	const TrkSection *p = track_section(t, prev);

	if (!p || !track_section(t, cur))
		return 0;
	if (p->next == cur)
		return 1;
	if (p->prev == cur)
		return -1;
	return 0;
}

int race_tick(Race *r, const Track *t, int section)
{
	int result = 0, step = 0;
	int32_t laps = clampi(race_cfg.laps, 1, RACE_MAX_LAPS), limit = race_cfg.wrong_way < 1 ? 1 : race_cfg.wrong_way;

	r->ticks++;
	if (section >= 0) {
		if (r->prev_section >= 0)
			step = race_section_step(t, r->prev_section, section);
		r->prev_section = section;
	}
	r->progress += step;
	if (r->progress > r->furthest)
		r->furthest = r->progress;
	r->wrong_way = r->furthest - r->progress >= limit;
	if (!r->finished && r->progress >= (r->lap + 1) * t->section_count) {
		int32_t before = 0;

		for (int i = 0; i < r->lap; i++)
			before += r->lap_ticks[i];
		r->lap_ticks[r->lap] = r->ticks - before;
		r->lap++;
		result |= RACE_LAP;
		if (r->lap >= laps) {
			int32_t best = r->lap_ticks[0];

			for (int i = 1; i < laps; i++)
				if (r->lap_ticks[i] < best)
					best = r->lap_ticks[i];
			r->finished = 1;
			r->total = r->ticks;
			r->best_lap = best;
			if (race_best == 0 || best < race_best) {
				race_best = best;
				r->new_best = 1;
			}
			result |= RACE_FINISH;
		}
	}
	return result;
}

int race_countdown_tick(Race *r, int32_t hz)
{
	int32_t cf = clampi(race_cfg.count_from, 1, 9);
	int beep = r->cd_ticks % hz == 0;

	r->cd_ticks++;
	if (r->cd_ticks >= cf * hz)
		return RACE_GO;
	return beep ? RACE_BEEP : 0;
}

void race_format_time(char *out, int32_t ticks, int32_t hz)
{
	int32_t cs;

	if (ticks < 0) {
		strcpy(out, "-:--.--");
		return;
	}
	cs = clampi(ticks, 0, 360000) * 100 / hz;
	if (cs > 599999)
		cs = 599999;
	snprintf(out, 12, "%d:%02d.%02d", (int) (cs / 6000), (int) ((cs / 100) % 60), (int) (cs % 100));
}

void race_format_text(const Race *r, int32_t state, int32_t hz)
{
	int32_t laps = clampi(race_cfg.laps, 1, RACE_MAX_LAPS), cf = clampi(race_cfg.count_from, 1, 9);
	char a[16], b[16];

	for (int i = 0; i < RACE_LINES; i++)
		race_text[i][0] = 0;
	if (state == STATE_TITLE) {
		if (race_best > 0) {
			race_format_time(a, race_best, hz);
			snprintf(race_text[0], RACE_LINE_LEN, "BEST LAP %s", a);
		}
	} else if (state == STATE_COUNTDOWN) {
		int32_t n = cf - r->cd_ticks / hz;

		snprintf(race_text[0], RACE_LINE_LEN, "GET READY %d", (int) (n < 1 ? 1 : n));
	} else if (state == STATE_RACE) {
		int32_t last = r->lap > 0 ? r->lap_ticks[r->lap - 1] : -1;

		snprintf(race_text[0], RACE_LINE_LEN, "LAP %d/%d", (int) (r->lap + 1 > laps ? laps : r->lap + 1), (int) laps);
		race_format_time(a, r->ticks, hz);
		snprintf(race_text[1], RACE_LINE_LEN, "TIME %s", a);
		race_format_time(a, last, hz);
		race_format_time(b, race_best > 0 ? race_best : -1, hz);
		snprintf(race_text[2], RACE_LINE_LEN, "LAST %s  BEST %s", a, b);
		if (r->wrong_way)
			strcpy(race_text[3], "WRONG WAY");
	} else if (state == STATE_RESULTS) {
		strcpy(race_text[0], "RESULTS");
		for (int k = 1; k <= laps; k++) {
			race_format_time(a, r->lap_ticks[k - 1], hz);
			snprintf(race_text[k], RACE_LINE_LEN, "LAP %d  %s", k, a);
		}
		race_format_time(a, r->total, hz);
		snprintf(race_text[laps + 1], RACE_LINE_LEN, "TOTAL %s", a);
		race_format_time(a, race_best > 0 ? race_best : -1, hz);
		snprintf(race_text[laps + 2], RACE_LINE_LEN, "BEST %s", a);
		if (r->new_best)
			strcpy(race_text[laps + 3], "NEW BEST LAP");
	}
}
