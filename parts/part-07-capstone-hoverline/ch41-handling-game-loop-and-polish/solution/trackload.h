#ifndef TRACKLOAD_H
#define TRACKLOAD_H

#include <stdint.h>
#include "track.h"

/* ---- loading a track from the disc (README 5.9) ---------------------------------------------------------------------------------
   The tracks on the disc are \DATA\TRACK.TRK (track 1, loaded at boot) and \DATA\TRACK2.TRK (track 2). The title screen picks one with
   LEFT / RIGHT (game.c calls track_switch); entering the game uses whatever is loaded. */
#define TRACK_COUNT 2

/* State the verifier reads. */
extern int32_t  track_selected;   /* 1 or 2: the track that `track` holds. main.c sets it to 1 after the boot load */
extern void    *track_image;      /* the malloc'ed file image `track` points into (main.c stores the boot load here); NULL if none */
extern const char *const track_paths[TRACK_COUNT];   /* "\\DATA\\TRACK.TRK;1", "\\DATA\\TRACK2.TRK;1" */

/* Make track number `n` (1 .. TRACK_COUNT) the current track (README 5.9).
     n out of range: return -1, nothing changes.
     Load the file (cd_load_file); NULL: return TRK_ERR_READ, nothing changes.
     Parse it into a SEPARATE Track (track_parse zeroes its output on failure): on an error free the image, return the code, nothing changes.
   On success: `track` = the new Track, free the old track_image, track_image = the new file, track_selected = n, track_status = 0,
   ship_section = -1 (the old section number means nothing on another track). Return 0.
   Every call that reads the disc (n in range), success or not, ends with audio_music_start(): reading the disc interrupted the CD-DA music (one laser). */
int track_switch(int n);

#endif
