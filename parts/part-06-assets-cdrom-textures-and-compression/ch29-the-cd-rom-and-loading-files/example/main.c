/* Chapter 29 worked example: the CD-ROM call sequence, step by step, with its results printed.
   It loads \SYSTEM.CNF;1 and \DATA\MODEL.BIN;1 and prints what the bytes say. Output goes to the
   TTY: run with `make run` (PCSX-Redux prints it on the terminal because of -stdout). */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <psxgpu.h>
#include <psxcd.h>

static void *load(const char *path, int *size)
{
	CdlFILE file;
	int sectors;
	uint32_t *buf;

	if (!CdSearchFile(&file, path)) {                      /* 1. name -> position + size */
		printf("%s: not found (CdIsoError %d)\n", path, CdIsoError());
		return NULL;
	}
	sectors = (file.size + 2047) / 2048;                   /* 2. whole sectors */
	printf("%s: sector %d, %d bytes -> %d sector(s)\n", path, CdPosToInt(&file.pos), file.size, sectors);
	buf = malloc(sectors * 2048);                          /* 3. a buffer for all of them */
	if (!buf)
		return NULL;
	CdControlB(CdlSetloc, &file.pos, 0);                   /* 4. where to start */
	CdRead(sectors, buf, CdlModeSpeed);                    /* 5. start reading at 2x */
	if (CdReadSync(0, 0) < 0) {                            /* 6. wait; negative = error */
		printf("read error\n");
		free(buf);
		return NULL;
	}
	*size = file.size;
	return buf;
}

int main(void)
{
	int size;
	uint8_t *p;

	ResetGraph(0);                                         /* the CD library needs the interrupts set up */
	if (!CdInit()) {
		printf("CdInit failed\n");
		return 1;
	}

	p = load("\\SYSTEM.CNF;1", &size);
	if (p) {
		printf("---- SYSTEM.CNF ----\n%.*s\n--------------------\n", size, (char *) p);
		free(p);
	}

	p = load("\\DATA\\MODEL.BIN;1", &size);
	if (p) {
		printf("first 12 bytes:");
		for (int i = 0; i < 12; i++)
			printf(" %02x", p[i]);
		printf("\n");
		/* The same four bytes, read two ways. */
		uint32_t be = ((uint32_t) p[4] << 24) | (p[5] << 16) | (p[6] << 8) | p[7];
		uint32_t le = ((uint32_t) p[7] << 24) | (p[6] << 16) | (p[5] << 8) | p[4];
		printf("vertex_count as big-endian: %u, as little-endian: %u\n", (unsigned) be, (unsigned) le);
		free(p);
	}

	p = load("\\DATA\\NOFILE.BIN;1", &size);
	printf("a missing file gives %s\n", p ? "a buffer?!" : "NULL");

	for (;;)
		VSync(0);
	return 0;
}
