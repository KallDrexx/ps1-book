#include <stdint.h>
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

/* TODO (README 5.5): one step along the ring. */
int race_section_step(const Track *t, int prev, int cur)
{
	(void) t;
	(void) prev;
	(void) cur;
	return 0;
}

/* TODO (README 5.5, 5.6, 5.9): one racing tick: the clock, progress, the wrong-way flag, laps, the finish. The placeholder only counts ticks. */
int race_tick(Race *r, const Track *t, int section)
{
	(void) t;
	(void) section;
	r->ticks++;
	return 0;
}

/* TODO (README 5.7): one tick of the countdown. The placeholder never ends it. */
int race_countdown_tick(Race *r, int32_t hz)
{
	(void) r;
	(void) hz;
	return 0;
}

/* TODO (README 5.8): "M:SS.cc". The placeholder writes an empty string. */
void race_format_time(char *out, int32_t ticks, int32_t hz)
{
	(void) ticks;
	(void) hz;
	out[0] = 0;
}

/* TODO (README 5.8): the HUD and the screens. The placeholder writes nothing: race_text stays as it is (all empty). */
void race_format_text(const Race *r, int32_t state, int32_t hz)
{
	(void) r;
	(void) state;
	(void) hz;
}
