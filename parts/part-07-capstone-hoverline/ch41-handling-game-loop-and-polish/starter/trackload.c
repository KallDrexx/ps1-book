#include <stdint.h>
#include <stdlib.h>
#include "cdrom.h"
#include "track.h"
#include "track_vis.h"
#include "audio.h"
#include "trackload.h"

int32_t track_selected = 1;
void   *track_image;
const char *const track_paths[TRACK_COUNT] = { "\\DATA\\TRACK.TRK;1", "\\DATA\\TRACK2.TRK;1" };

int track_switch(int n)
{
	Track fresh;
	uint32_t size;
	void *file;
	int rc;

	if (n < 1 || n > TRACK_COUNT)
		return -1;
	file = cd_load_file(track_paths[n - 1], &size);
	if (!file) {
		audio_music_start();
		return TRK_ERR_READ;
	}
	rc = track_parse(file, size, &fresh);
	if (rc) {
		free(file);
		audio_music_start();
		return rc;
	}
	track = fresh;
	free(track_image);
	track_image = file;
	track_selected = n;
	track_status = 0;
	ship_section = -1;
	audio_music_start();
	return 0;
}
