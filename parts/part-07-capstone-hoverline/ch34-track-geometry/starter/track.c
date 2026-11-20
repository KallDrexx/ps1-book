#include <stdint.h>
#include <string.h>
#include "track.h"

Track   track;
int32_t track_status;

/* Little-endian readers that work at any alignment (README 5.4): use them for every field of the file. */
static uint32_t rd16(const uint8_t *p) { return p[0] | (p[1] << 8); }
static uint32_t rd32(const uint8_t *p) { return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t) p[3] << 24); }
static int32_t  rds32(const uint8_t *p) { return (int32_t) rd32(p); }

int track_parse(const void *data, size_t size, Track *out)
{
	/* TODO (README 7.3, step 2): validate in the order documented in track.h, then fill *out.
	   Zero *out first, so that every failure leaves it all zero.
	   Until you write it, the starter reports a bad header for every file. */
	(void) data;
	(void) size;
	(void) rd16;
	(void) rd32;
	(void) rds32;
	memset(out, 0, sizeof *out);
	return TRK_ERR_HEADER;
}

const TrkVertex *track_vertex(const Track *t, int i)
{
	/* TODO: &t->vertices[i], or NULL when i is outside 0 .. vertex_count - 1. */
	(void) t;
	(void) i;
	return NULL;
}

const TrkFace *track_face(const Track *t, int i)
{
	/* TODO */
	(void) t;
	(void) i;
	return NULL;
}

const TrkSection *track_section(const Track *t, int i)
{
	/* TODO */
	(void) t;
	(void) i;
	return NULL;
}
