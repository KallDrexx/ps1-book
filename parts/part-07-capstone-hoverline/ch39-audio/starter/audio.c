/* Chapter 39: your work is in this file. Read audio.h first: it is the specification (README 5). Every function below is a stub
   that compiles and does nothing; the verifier tells you, check by check, what is still missing. */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <psxapi.h>
#include <psxcd.h>
#include <psxspu.h>
#include <hwregs_c.h>
#include "cdrom.h"
#include "audio.h"

AudioSample audio_samples[SMP_COUNT];
AudioCfg audio_cfg = { .idle_mul = 2048, .span_mul = 6400, .engine_vol = 0x1800, .sfx_vol = 0x3000, .music_track = 2, .music_vol = 0x6000 };
AudioStats audio_stats = { .last_voice = -1 };
int32_t audio_status;

/* ---- given ------------------------------------------------------------------------------------------------------------------ */
static uint32_t next_addr = SPU_RAM_FIRST;     /* the allocator: the next free byte of SPU RAM */
static int voice_next = 1;                     /* round-robin cursor over the one-shot voices */
static int32_t prev_section = -1;              /* the event detector's memory */
static int32_t was_off_road;
static volatile int music_ended;               /* set by the auto-pause callback: the CD track has ended */

static const char *const paths[SMP_COUNT] = {
	"\\DATA\\ENGINE.VAG;1", "\\DATA\\BOOST.VAG;1", "\\DATA\\THUD.VAG;1", "\\DATA\\BEEP.VAG;1", "\\DATA\\GO.VAG;1",
};

/* A big-endian 32-bit field of a VAG header (README 5.2). */
__attribute__((unused)) static uint32_t be32(const uint8_t *p)
{
	return ((uint32_t) p[0] << 24) | ((uint32_t) p[1] << 16) | ((uint32_t) p[2] << 8) | p[3];
}

/* The callback for CdAutoPauseCallback: the drive paused at the end of the track. */
__attribute__((unused)) static void music_end_cb(CdlIntrResult intr, uint8_t *result)
{
	(void) result;
	if (intr == CdlDataEnd)
		music_ended = 1;
}

/* ---- yours (README 5.2 to 5.7) ---------------------------------------------------------------------------------------------- */

int audio_upload_sample(int id, const char *path)
{
	(void) id; (void) path; (void) next_addr;
	return 0;                                      /* TODO: README 5.2 */
}

int audio_init(void)
{
	return 0;                                      /* TODO: SpuInit, reset next_addr and voice_next, upload the five samples (README 5.2) */
}

int32_t audio_pitch_for_speed(int32_t speed)
{
	(void) speed;
	return 0;                                      /* TODO: README 5.5 */
}

int audio_voice_alloc(void)
{
	(void) voice_next;
	return 1;                                      /* TODO: README 5.4 */
}

void audio_play_sfx(int id)
{
	(void) id;                                     /* TODO: README 5.4 */
}

void audio_engine_start(void)
{
	/* TODO: README 5.5 */
}

void audio_engine_stop(void)
{
	/* TODO: README 5.5 */
}

void audio_engine_update(int32_t speed)
{
	(void) speed;                                  /* TODO: README 5.5 */
}

void audio_event(int type)
{
	(void) type;                                   /* TODO: README 5.6 */
}

int32_t audio_lateral(const TrkSection *s, const int32_t pos[3])
{
	(void) s; (void) pos;
	return 0;                                      /* TODO: README 5.6 */
}

int audio_section_boost(const Track *t, int sec)
{
	(void) t; (void) sec;
	return 0;                                      /* TODO: README 5.6 */
}

void audio_events_reset(const Track *t, const Ship *s, int32_t section)
{
	(void) t; (void) s; (void) section; (void) prev_section; (void) was_off_road;   /* TODO: README 5.6 */
}

void audio_events_update(const Track *t, const Ship *s, int32_t section)
{
	(void) t; (void) s; (void) section;            /* TODO: README 5.6 */
}

void audio_music_start(void)
{
	/* TODO: README 5.7 */
}

void audio_update(void)
{
	(void) music_ended;                            /* TODO: README 5.7 (the restart) and the diagnostics of audio.h */
}
