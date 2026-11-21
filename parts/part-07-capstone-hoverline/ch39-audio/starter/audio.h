#ifndef AUDIO_H
#define AUDIO_H

#include <stdint.h>
#include "track.h"
#include "ship.h"

/* ---- the sounds (README 5.1) ---------------------------------------------------------------------------------------------
   Five samples, one per .VAG file in \DATA\. A sample id is an index into audio_samples[]. */
enum { SMP_ENGINE, SMP_BOOST, SMP_THUD, SMP_BEEP, SMP_GO, SMP_COUNT };

#define AUDIO_VOICES     24        /* the SPU has 24 voices */
#define ENGINE_VOICE     0         /* the engine hum owns voice 0; one-shots use 1 .. 23 */
#define SPU_RAM_FIRST    0x1010    /* the first byte of SPU RAM a sample may use (README 5.1) */
#define SPU_PITCH_MAX    0x3FFF    /* the largest pitch the program writes (about 4 x native: two octaves up) */
#define VAG_HEADER_SIZE  48

/* One uploaded sample. The verifier reads audio_samples[SMP_COUNT]: 4 words each, in this order. */
typedef struct {
	uint32_t addr;                 /* +0   byte address of its first block in SPU RAM; 0 = not uploaded */
	uint32_t size;                 /* +4   bytes of ADPCM data (the header's size field, a multiple of 16) */
	uint32_t rate;                 /* +8   sample rate in Hz, from the header */
	uint32_t loop;                 /* +12  1 if the last block has the repeat bit (flags & 2), else 0 */
} AudioSample;
_Static_assert(sizeof(AudioSample) == 16, "the verifier reads 4 words per sample");

/* The tunable constants. 8 words; patchable (the verifier writes them to prove nothing is hard-coded). */
typedef struct {
	int32_t idle_mul;              /* 2048 = 0.5 : the engine pitch at speed 0 is native * idle_mul / 4096 */
	int32_t span_mul;              /* 6400       : the extra multiplier at the top speed is span_mul * (speed >> 8) >> 10 (README 5.5) */
	int32_t engine_vol;            /* 0x1800     : engine volume, left and right (0 .. 0x3FFF) */
	int32_t sfx_vol;               /* 0x3000     : one-shot volume, left and right */
	int32_t music_track;           /* 2          : the CD track CdlPlay is given (track 1 is the data track) */
	int32_t music_vol;             /* 0x6000     : the SPU's CD input volume, left and right */
	int32_t reserved[2];
} AudioCfg;
_Static_assert(sizeof(AudioCfg) == 32, "the verifier patches 8 words at `audio_cfg`");

/* Counters and diagnostics the verifier reads: 12 words at `audio_stats`. */
typedef struct {
	int32_t sfx_played;            /* audio_play_sfx calls that started a voice */
	int32_t engine_starts;         /* key-ons of the engine voice */
	int32_t music_cmds;            /* CdlPlay commands sent (music start + restarts) */
	int32_t events_boost;          /* EV_BOOST events raised */
	int32_t events_thud;           /* EV_THUD events raised */
	int32_t last_voice;            /* the voice the last one-shot used (-1 before the first) */
	int32_t engine_pitch;          /* the last value audio_engine_update wrote to the engine voice's pitch register */
	int32_t music_restarts;        /* +28 how many of music_cmds were restarts after the track ended */
	int32_t endx;                  /* +32 the SPU's ENDX register as audio_update last read it: bit v = voice v has passed a block with the end flag */
	int32_t env_engine;            /* +36 the envelope level (SPU_CH_ADSR_VOL) of ENGINE_VOICE at that moment: 0 = silent */
	int32_t env_last;              /* +40 the same for the voice of the last one-shot (0 before the first) */
	int32_t reserved;
} AudioStats;
_Static_assert(sizeof(AudioStats) == 48, "the verifier reads 12 words at `audio_stats`");

/* Game events (README 5.6). */
enum { EV_NONE = 0, EV_BOOST = 1, EV_THUD = 2 };

extern AudioSample audio_samples[SMP_COUNT];
extern AudioCfg    audio_cfg;
extern AudioStats  audio_stats;
extern int32_t     audio_status;   /* 0 = every sample uploaded; otherwise a negative AUDIO_ERR_* of the first failure */

#define AUDIO_ERR_READ   -1        /* the file could not be read from the disc */
#define AUDIO_ERR_HEADER -2        /* not a VAG: bad magic, size field, or size not a multiple of 16 */
#define AUDIO_ERR_SPU    -3        /* the sample does not fit in SPU RAM */

/* ---- the API -------------------------------------------------------------------------------------------------------------- */

/* Start the SPU (SpuInit), reset the allocator to SPU_RAM_FIRST, reset the round-robin cursor of audio_voice_alloc to voice 1, and upload the five samples
   ENGINE BOOST THUD BEEP GO (\DATA\<NAME>.VAG;1) with audio_upload_sample. Sets audio_status. Call once, after cd_init().
   Returns audio_status. */
int audio_init(void);

/* Load the VAG file `path` from the disc, check its header, upload its ADPCM data to the next free SPU RAM address
   (8-byte aligned, in practice a multiple of 64 because the transfer works in 64-byte blocks) and fill audio_samples[id].
   Returns 0, or AUDIO_ERR_*; on failure audio_samples[id].addr stays 0. */
int audio_upload_sample(int id, const char *path);

/* The pitch of the engine voice for a speed (README 5.5): base = rate * 4096 / 44100 (integer division, rate = the ENGINE sample's),
   mul = idle_mul + (((speed >> 8) * span_mul) >> 10) with speed clamped below at 0, pitch = min((base * mul) >> 12, SPU_PITCH_MAX).
   A pure function of its argument, audio_samples[SMP_ENGINE].rate and audio_cfg. Returns 0 when the engine sample is not loaded. */
int32_t audio_pitch_for_speed(int32_t speed);

/* The next voice for a one-shot: 1, 2, ... 23, 1, 2, ... (round robin; the engine's voice 0 is never returned).
   The first call after audio_init returns 1. */
int audio_voice_alloc(void);

/* Play sample `id` once on audio_voice_alloc()'s voice (README 5.4): key-off, volume sfx_vol on both sides, pitch from the sample's rate
   (rate * 4096 / 44100), start address, the envelope, key-on. Ignores an id outside 0 .. SMP_COUNT - 1 and a sample that is not loaded
   (and SMP_ENGINE, which is not a one-shot). Updates audio_stats.sfx_played and last_voice. */
void audio_play_sfx(int id);

/* The engine hum: start it on ENGINE_VOICE (volume engine_vol, pitch audio_pitch_for_speed(0), looped sample, key-on once;
   audio_stats.engine_starts++), stop it (key-off), and follow the ship: write audio_pitch_for_speed(speed) to the pitch register
   of ENGINE_VOICE (and audio_stats.engine_pitch). */
void audio_engine_start(void);
void audio_engine_stop(void);
void audio_engine_update(int32_t speed);

/* Raise a game event (README 5.6): EV_BOOST plays SMP_BOOST, EV_THUD plays SMP_THUD; the matching events_ counter is incremented
   even when the sample is missing. */
void audio_event(int type);

/* Where the ship is across the road: ((dx * right.x + dy * right.y + dz * right.z) >> 12) with d = pos - section.centre, each
   component of d first clamped to -32767 .. 32767. Positive = to the right of the centre line. */
int32_t audio_lateral(const TrkSection *s, const int32_t pos[3]);

/* 1 if any face of section `sec` has TRK_BOOST in its flags (0 for an invalid index). */
int audio_section_boost(const Track *t, int sec);

/* The game's event detector (README 5.6). Reset when the game state is entered: remembers `section` as the previous section and
   whether the ship is off the road; raises nothing. Update once per frame after the section update:
     EV_BOOST  when `section` differs from the remembered one and audio_section_boost(section);
     EV_THUD   when the ship is off the road (|audio_lateral| > half_width of `section`) and was not the last time.
   Both are remembered afterwards. An invalid `section` (< 0) does nothing. */
void audio_events_reset(const Track *t, const Ship *s, int32_t section);
void audio_events_update(const Track *t, const Ship *s, int32_t section);

/* The music (README 5.7): CdMix to the default matrix {128, 0, 128, 0}, the SPU's CD volume to music_vol, mode CdlModeDA | CdlModeAP,
   an auto-pause callback that records "the track ended", then CdlPlay with the track number music_track. audio_stats.music_cmds++.
   audio_update (once per frame) sends CdlPlay again when the track has ended (music_cmds++ and music_restarts++), then reads the
   diagnostics: audio_stats.endx = SPU_CHAN_STATUS1 | SPU_CHAN_STATUS2 << 16, env_engine = SPU_CH_ADSR_VOL(ENGINE_VOICE),
   env_last = SPU_CH_ADSR_VOL(last_voice) (0 while last_voice < 0). */
void audio_music_start(void);
void audio_update(void);

#endif
