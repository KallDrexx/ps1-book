#include <stdint.h>
#include <stdlib.h>
#include <psxapi.h>
#include <psxgpu.h>
#include <psxcd.h>
#include "cdrom.h"

#define CD_TIMEOUT_FRAMES 600        /* 10 seconds of video frames */

/* Given. */
int cd_init(void)
{
	for (int attempt = 0; attempt < 3; attempt++)
		if (CdInit())
			return 1;
	return 0;
}

/* TODO (README 7.2, 7.3): the contract is in cdrom.h.
   1. *size = 0 first; find the file (CdSearchFile); NULL if not found or empty.
   2. sectors = ceil(size / 2048); malloc(sectors * 2048); NULL if it fails.
   3. CdlSetloc to the file's position, then CdRead(sectors, buf, CdlModeSpeed).
   4. Poll CdReadSync(1, 0) (+ VSync(0)) until it returns 0; give up after CD_TIMEOUT_FRAMES
      (CdReadBreak) or on a negative result. Free the buffer on every failure.
   5. *size = the file's size from the directory entry; return the buffer. */
void *cd_load_file(const char *path, uint32_t *size)
{
	(void) path;
	if (size)
		*size = 0;
	return NULL;
}
