#ifndef RACE_H
#define RACE_H

#include <stdint.h>
#include "track.h"

/* ---- the race (README 5.5 - 5.9) ---------------------------------------------------------------------------------------------
   A 3-lap time trial. Time is counted in TICKS (one per video frame: 1/60 s NTSC, 1/50 s PAL, Chapter 37) and shown in
   minutes, seconds and hundredths with `hz` = 60 or 50 (race_hz). Laps are counted from the sections the ship passes, not from where it is. */

#define RACE_MAX_LAPS  8
#define RACE_LINES     12
#define RACE_LINE_LEN  32

/* The state the verifier reads: 19 words at `race`, in this order. race_reset() zeroes it (prev_section = -1). */
typedef struct {
	int32_t cd_ticks;             /* +0   countdown ticks run so far */
	int32_t ticks;                /* +4   race ticks since GO */
	int32_t lap;                  /* +8   laps completed, 0 .. laps */
	int32_t progress;             /* +12  net section steps since the start: forward +1, backward -1 (can be negative) */
	int32_t furthest;             /* +16  the largest `progress` so far (0 at the start) */
	int32_t prev_section;         /* +20  ship_section at the end of the last race tick; -1 = none yet */
	int32_t wrong_way;            /* +24  1 while the ship is `race_cfg.wrong_way` or more sections behind its furthest point */
	int32_t finished;             /* +28  1 once `laps` laps are done */
	int32_t total;                /* +32  ticks of the whole race (set when finished), else 0 */
	int32_t best_lap;             /* +36  the fastest lap of THIS race (set when finished), else 0 */
	int32_t new_best;             /* +40  1 if that lap beat race_best */
	int32_t lap_ticks[RACE_MAX_LAPS];   /* +44 the time of each completed lap, in ticks (0 = not done) */
} Race;
_Static_assert(sizeof(Race) == 76, "the verifier reads 19 words at the `race` symbol");

/* The tunable constants. 4 words; patchable (the verifier writes them to prove nothing is hard-coded). */
typedef struct {
	int32_t laps;                 /* 3 : laps to finish; used as clamp(laps, 1, RACE_MAX_LAPS) */
	int32_t wrong_way;            /* 2 : sections behind the furthest point that raise the warning; used as max(wrong_way, 1) */
	int32_t count_from;           /* 3 : countdown seconds; used as clamp(count_from, 1, 9) */
	int32_t reserved;
} RaceCfg;
_Static_assert(sizeof(RaceCfg) == 16, "the verifier patches 4 words at `race_cfg`");

/* return values */
#define RACE_LAP     0x01         /* race_tick: a lap was completed */
#define RACE_FINISH  0x02         /* race_tick: ... and it was the last one */
#define RACE_BEEP    0x01         /* race_countdown_tick: a beep sounds on this tick */
#define RACE_GO      0x02         /* race_countdown_tick: the countdown is over */

extern Race    race;
extern RaceCfg race_cfg;
extern int32_t race_best;                           /* the fastest lap since power-on, in ticks; 0 = none yet. Survives restarts, lives in RAM only */
extern char    race_text[RACE_LINES][RACE_LINE_LEN]; /* the text race_format_text last wrote (README 5.8) */

/* ---- given ----------------------------------------------------------------------------------------------------------------- */

/* Zero *r, then prev_section = -1. Called when the countdown starts. */
void race_reset(Race *r);

/* 60 for NTSC, 50 for PAL (video_mode). */
int32_t race_hz(void);

/* ---- you write ------------------------------------------------------------------------------------------------------------- */

/* One step along the ring (README 5.5): +1 if section `cur` is section `prev`'s `next`, -1 if it is its `prev`, otherwise 0 (the same
   section, a jump, or either index not a section). The links are followed, never `prev + 1` (a ring may be numbered in any order).
   When both links name `cur` (a two-section ring) the answer is +1. */
int race_section_step(const Track *t, int prev, int cur);

/* One tick of racing (README 5.5, 5.6, 5.9), in this order. `section` is ship_section after collide_ship (it may be negative: no section).
     1. r->ticks++
     2. step = 0; if section >= 0: if r->prev_section >= 0, step = race_section_step(t, prev_section, section); r->prev_section = section.
     3. r->progress += step; r->furthest = max(furthest, progress).
     4. r->wrong_way = (furthest - progress >= max(race_cfg.wrong_way, 1)) ? 1 : 0.
     5. Unless r->finished: if progress >= (lap + 1) * t->section_count then
          lap_ticks[lap] = ticks - (the sum of lap_ticks[0 .. lap - 1]);  lap++;  result |= RACE_LAP;
          if lap >= L (L = clamp(race_cfg.laps, 1, RACE_MAX_LAPS)):
              finished = 1;  total = ticks;  best_lap = the smallest of lap_ticks[0 .. L - 1];
              if race_best == 0 or best_lap < race_best: race_best = best_lap, new_best = 1;
              result |= RACE_FINISH.
   Returns the RACE_* bits. A step takes at most one lap boundary, so at most one lap is completed per call. */
int race_tick(Race *r, const Track *t, int section);

/* One tick of the countdown (README 5.7), hz = race_hz(). cf = clamp(race_cfg.count_from, 1, 9). In this order:
     beep = (r->cd_ticks % hz == 0);  r->cd_ticks++;  go = (r->cd_ticks >= cf * hz).
   Returns RACE_GO if go, else RACE_BEEP if beep, else 0. (With hz 60 and cf 3: beeps on ticks 0, 60, 120 of the countdown, GO on tick 179.) */
int race_countdown_tick(Race *r, int32_t hz);

/* "M:SS.cc" into out (at most 12 bytes with the terminator): ticks -> hundredths cs = ticks * 100 / hz (C division) after limiting ticks to
   0 .. 360000, then cs limited to 599999; minutes = cs / 6000 (no padding), seconds = (cs / 100) % 60 and hundredths = cs % 100 (two digits each).
   A negative `ticks` means "no time": the text "-:--.--". Example: 3725 ticks at 60 Hz: cs = 6208: "1:02.08". */
void race_format_time(char *out, int32_t ticks, int32_t hz);

/* The text of the HUD and the screens (README 5.8): fills race_text for the state `state` (game.h's STATE_*). Every line is first emptied
   (first byte 0). `<t(x)>` is race_format_time(x, hz). L = clamp(race_cfg.laps, 1, RACE_MAX_LAPS), cf = clamp(race_cfg.count_from, 1, 9).
     STATE_TITLE      line 0: "BEST LAP <t(race_best)>" if race_best > 0.
     STATE_COUNTDOWN  line 0: "GET READY n" with n = max(cf - cd_ticks / hz, 1).
     STATE_RACE       line 0: "LAP a/L" with a = min(lap + 1, L).      line 1: "TIME <t(ticks)>".
                      line 2: "LAST <t(l)>  BEST <t(b)>" (two spaces) with l = lap_ticks[lap - 1] if lap > 0 else -1, and b = race_best if > 0 else -1.
                      line 3: "WRONG WAY" if wrong_way.
     STATE_RESULTS    line 0: "RESULTS".   lines 1 .. L: "LAP k  <t(lap_ticks[k - 1])>" (two spaces).   line L + 1: "TOTAL <t(total)>".
                      line L + 2: "BEST <t(b)>" with b as above.   line L + 3: "NEW BEST LAP" if new_best.
   Lines are at most 31 characters. */
void race_format_text(const Race *r, int32_t state, int32_t hz);

#endif
