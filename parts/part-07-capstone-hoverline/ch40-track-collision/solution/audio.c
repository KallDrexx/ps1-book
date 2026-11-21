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

static uint32_t next_addr = SPU_RAM_FIRST;     /* the allocator: the next free byte of SPU RAM */
static int voice_next = 1;                     /* round-robin cursor over the one-shot voices */
static volatile int music_ended;

static const char *const paths[SMP_COUNT] = {
	"\\DATA\\ENGINE.VAG;1", "\\DATA\\BOOST.VAG;1", "\\DATA\\THUD.VAG;1", "\\DATA\\BEEP.VAG;1", "\\DATA\\GO.VAG;1",
};

static uint32_t be32(const uint8_t *p)
{
	return ((uint32_t) p[0] << 24) | ((uint32_t) p[1] << 16) | ((uint32_t) p[2] << 8) | p[3];
}

int audio_upload_sample(int id, const char *path)
{
	uint32_t file_size, size, padded;
	uint8_t *file, *copy;

	if (id < 0 || id >= SMP_COUNT)
		return AUDIO_ERR_HEADER;
	file = cd_load_file(path, &file_size);
	if (!file)
		return AUDIO_ERR_READ;
	size = file_size >= VAG_HEADER_SIZE ? be32(file + 12) : 0;
	if (file_size < VAG_HEADER_SIZE + 32 || memcmp(file, "VAGp", 4) != 0 || size != file_size - VAG_HEADER_SIZE || (size & 15)) {
		free(file);
		return AUDIO_ERR_HEADER;
	}
	padded = (size + 63) & ~63u;                     /* the SPU transfer works in 64-byte blocks */
	if (next_addr + padded > 0x80000) {
		free(file);
		return AUDIO_ERR_SPU;
	}
	copy = calloc(1, padded);                        /* the file buffer may end before `padded` bytes: copy into a zero-filled one */
	if (!copy) {
		free(file);
		return AUDIO_ERR_READ;
	}
	memcpy(copy, file + VAG_HEADER_SIZE, size);
	SpuSetTransferMode(SPU_TRANSFER_BY_DMA);
	SpuSetTransferStartAddr(next_addr);
	SpuWrite((const uint32_t *) copy, padded);
	SpuIsTransferCompleted(SPU_TRANSFER_WAIT);
	audio_samples[id] = (AudioSample) { next_addr, size, be32(file + 16), (file[VAG_HEADER_SIZE + size - 15] & 2) ? 1u : 0u };
	next_addr += padded;
	free(copy);
	free(file);
	return 0;
}

int audio_init(void)
{
	SpuInit();
	next_addr = SPU_RAM_FIRST;
	voice_next = 1;
	audio_status = 0;
	for (int i = 0; i < SMP_COUNT; i++) {
		int r = audio_upload_sample(i, paths[i]);

		if (r && !audio_status)
			audio_status = r;
	}
	return audio_status;
}

int32_t audio_pitch_for_speed(int32_t speed)
{
	const AudioSample *e = &audio_samples[SMP_ENGINE];
	int32_t base, mul, p;

	if (!e->addr)
		return 0;
	if (speed < 0)
		speed = 0;
	base = (int32_t) ((e->rate * 4096u) / 44100u);
	mul = audio_cfg.idle_mul + (((speed >> 8) * audio_cfg.span_mul) >> 10);
	p = (base * mul) >> 12;
	return p > SPU_PITCH_MAX ? SPU_PITCH_MAX : p;
}

int audio_voice_alloc(void)
{
	int v = voice_next;

	voice_next = v + 1 >= AUDIO_VOICES ? 1 : v + 1;
	return v;
}

static void voice_start(int v, const AudioSample *s, int32_t pitch, int32_t vol)
{
	SpuSetKey(0, 1u << v);
	SpuSetVoiceVolume(v, vol, vol);
	SpuSetVoicePitch(v, pitch);
	SpuSetVoiceStartAddr(v, s->addr);
	SPU_CH_ADSR1(v) = 0x00FF;                        /* attack shift 0 and step 0 (the fastest: full level in 3 samples), sustain level 15 (the top: the decay has nothing to remove) */
	SPU_CH_ADSR2(v) = 0x000A;                        /* release: linear, shift 10 (about 50 ms from the top to silence when the voice is keyed off) */
	SpuSetKey(1, 1u << v);
}

void audio_play_sfx(int id)
{
	const AudioSample *s;
	int v;

	if (id <= SMP_ENGINE || id >= SMP_COUNT || !audio_samples[id].addr)
		return;
	s = &audio_samples[id];
	v = audio_voice_alloc();
	voice_start(v, s, (int32_t) ((s->rate * 4096u) / 44100u), audio_cfg.sfx_vol);
	audio_stats.sfx_played++;
	audio_stats.last_voice = v;
}

void audio_engine_start(void)
{
	if (!audio_samples[SMP_ENGINE].addr)
		return;
	audio_stats.engine_pitch = audio_pitch_for_speed(0);
	voice_start(ENGINE_VOICE, &audio_samples[SMP_ENGINE], audio_stats.engine_pitch, audio_cfg.engine_vol);
	audio_stats.engine_starts++;
}

void audio_engine_stop(void)
{
	SpuSetKey(0, 1u << ENGINE_VOICE);
}

void audio_engine_update(int32_t speed)
{
	if (!audio_samples[SMP_ENGINE].addr)
		return;
	audio_stats.engine_pitch = audio_pitch_for_speed(speed);
	SpuSetVoicePitch(ENGINE_VOICE, audio_stats.engine_pitch);
}

void audio_event(int type)
{
	if (type == EV_BOOST) {
		audio_stats.events_boost++;
		audio_play_sfx(SMP_BOOST);
	} else if (type == EV_THUD) {
		audio_stats.events_thud++;
		audio_play_sfx(SMP_THUD);
	}
}

static int32_t clamp_d(int32_t v)
{
	return v > 32767 ? 32767 : (v < -32767 ? -32767 : v);
}

int32_t audio_lateral(const TrkSection *s, const int32_t pos[3])
{
	int32_t sum = 0;

	for (int i = 0; i < 3; i++)
		sum += clamp_d(pos[i] - s->centre[i]) * s->right[i];
	return sum >> 12;
}

int audio_section_boost(const Track *t, int sec)
{
	const TrkSection *s = track_section(t, sec);

	if (!s)
		return 0;
	for (int i = 0; i < s->face_count; i++) {
		const TrkFace *f = track_face(t, s->first_face + i);

		if (f && (f->flags & TRK_BOOST))
			return 1;
	}
	return 0;
}

static void music_end_cb(CdlIntrResult intr, uint8_t *result)
{
	(void) result;
	if (intr == CdlDataEnd)
		music_ended = 1;
}

static void music_play(void)
{
	uint8_t track = (uint8_t) audio_cfg.music_track;

	CdControl(CdlPlay, &track, 0);
	audio_stats.music_cmds++;
}

void audio_music_start(void)
{
	CdlATV mix = { 128, 0, 128, 0 };
	uint8_t mode = CdlModeDA | CdlModeAP;

	CdMix(&mix);
	SpuSetCommonCDVolume(audio_cfg.music_vol, audio_cfg.music_vol);
	CdControl(CdlSetmode, &mode, 0);
	CdAutoPauseCallback(music_end_cb);
	music_ended = 0;
	music_play();
}

void audio_update(void)
{
	if (music_ended) {
		music_ended = 0;
		music_play();
		audio_stats.music_restarts++;
	}
	audio_stats.endx = (int32_t) (SPU_CHAN_STATUS1 | ((uint32_t) SPU_CHAN_STATUS2 << 16));
	audio_stats.env_engine = SPU_CH_ADSR_VOL(ENGINE_VOICE);
	audio_stats.env_last = audio_stats.last_voice >= 0 ? SPU_CH_ADSR_VOL(audio_stats.last_voice) : 0;
}
