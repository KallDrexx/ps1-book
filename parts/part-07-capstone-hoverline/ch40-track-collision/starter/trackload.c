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
	(void) n;
	return -1;                                          /* TODO README 7.3 step 7: see trackload.h */
}
