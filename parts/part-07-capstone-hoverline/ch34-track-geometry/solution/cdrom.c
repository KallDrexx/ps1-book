#include <stdint.h>
#include <stdlib.h>
#include <psxapi.h>
#include <psxgpu.h>
#include <psxcd.h>
#include "cdrom.h"

#define CD_TIMEOUT_FRAMES 600        /* 10 seconds of video frames */

int cd_init(void)
{
	for (int attempt = 0; attempt < 3; attempt++)
		if (CdInit())
			return 1;
	return 0;
}

void *cd_load_file(const char *path, uint32_t *size)
{
	CdlFILE file;
	uint32_t *buf;
	int sectors, left, frames = 0;

	if (size)
		*size = 0;
	if (!CdSearchFile(&file, path) || file.size <= 0)
		return NULL;

	/* The drive delivers whole sectors, so the buffer must hold the rounded-up count. */
	sectors = (file.size + CD_SECTOR_SIZE - 1) / CD_SECTOR_SIZE;
	buf = malloc((size_t) sectors * CD_SECTOR_SIZE);
	if (!buf)
		return NULL;

	CdControlB(CdlSetloc, &file.pos, 0);
	if (!CdRead(sectors, buf, CdlModeSpeed)) {
		free(buf);
		return NULL;
	}
	/* Poll instead of blocking forever: a bad disc or open lid must not hang the program. */
	while ((left = CdReadSync(1, 0)) > 0) {
		if (++frames > CD_TIMEOUT_FRAMES) {
			CdReadBreak();
			CdReadSync(0, 0);
			free(buf);
			return NULL;
		}
		VSync(0);
	}
	if (left < 0) {
		free(buf);
		return NULL;
	}
	if (size)
		*size = (uint32_t) file.size;
	return buf;
}
