#include <stdint.h>
#include <string.h>
#include "track.h"

Track   track;
int32_t track_status;

static uint32_t rd16(const uint8_t *p) { return p[0] | (p[1] << 8); }
static uint32_t rd32(const uint8_t *p) { return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t) p[3] << 24); }
static int32_t  rds32(const uint8_t *p) { return (int32_t) rd32(p); }

/* Header, offsets and sizes (everything the later loops rely on). */
static int check_header(const uint8_t *d, size_t size)
{
	uint32_t ns, nv, nf, nvis, start, off_v, off_f, off_s, off_vis, vis_bytes;

	if (size < 0x60 || rd32(d + 4) != size)
		return TRK_ERR_HEADER;
	ns = rd16(d + 0x18);
	nv = rd16(d + 0x1A);
	nf = rd16(d + 0x1C);
	nvis = rd16(d + 0x1E);
	start = rd16(d + 0x20);
	if (ns == 0 || ns > TRK_MAX_SECTIONS || nv == 0 || nv > TRK_MAX_VERTICES || nf == 0 || nf > TRK_MAX_FACES || nvis > TRK_MAX_VIS)
		return TRK_ERR_HEADER;
	if (start >= ns)
		return TRK_ERR_HEADER;
	off_v = rd32(d + 0x28);
	off_f = rd32(d + 0x2C);
	off_s = rd32(d + 0x30);
	off_vis = rd32(d + 0x34);
	if (off_v != 0x60 || off_f != off_v + 12 * nv || off_s != off_f + 24 * nf || off_vis != off_s + 64 * ns)
		return TRK_ERR_HEADER;
	vis_bytes = (2 * nvis + 3) & ~3u;
	if (size != off_vis + vis_bytes)
		return TRK_ERR_HEADER;
	return TRK_OK;
}

int track_parse(const void *data, size_t size, Track *out)
{
	const uint8_t *d = data;
	const uint8_t *fv, *ff, *fs, *fvis;
	uint32_t ns, nv, nf, nvis, ntex;
	int rc;

	memset(out, 0, sizeof *out);
	if ((uintptr_t) data & 3)
		return TRK_ERR_ALIGN;
	if (size < 4 || memcmp(d, "TRK1", 4) != 0)
		return TRK_ERR_MAGIC;
	rc = check_header(d, size);
	if (rc)
		return rc;
	ns = rd16(d + 0x18);
	nv = rd16(d + 0x1A);
	nf = rd16(d + 0x1C);
	nvis = rd16(d + 0x1E);
	ntex = rd16(d + 0x24);
	fv = d + rd32(d + 0x28);
	ff = d + rd32(d + 0x2C);
	fs = d + rd32(d + 0x30);
	fvis = d + rd32(d + 0x34);

	for (uint32_t i = 0; i < nv; i++) {
		for (int k = 0; k < 3; k++) {
			int32_t c = rds32(fv + 12 * i + 4 * k);

			if (c < -TRK_MAX_COORD || c > TRK_MAX_COORD)
				return TRK_ERR_VERTEX;
		}
	}
	for (uint32_t i = 0; i < nf; i++) {
		const uint8_t *f = ff + 24 * i;
		uint32_t flags = rd16(f + 8), tex = f[10];

		for (int k = 0; k < 4; k++)
			if (rd16(f + 2 * k) >= nv)
				return TRK_ERR_FACE;
		if (flags & ~(uint32_t) TRK_FLAGS_KNOWN)
			return TRK_ERR_FACE;
		if (!(flags & (TRK_FLOOR | TRK_WALL)))
			return TRK_ERR_FACE;
		if ((flags & (TRK_BOOST | TRK_START)) && !(flags & TRK_FLOOR))
			return TRK_ERR_FACE;
		if (tex != TRK_UNTEXTURED && tex >= ntex)
			return TRK_ERR_FACE;
	}
	for (uint32_t i = 0; i < ns; i++) {
		const uint8_t *s = fs + 64 * i;

		if (rd16(s + 0x2C) >= ns || rd16(s + 0x2E) >= ns)
			return TRK_ERR_SECTION;
		if (rd16(s + 0x28) + rd16(s + 0x2A) > nf)
			return TRK_ERR_SECTION;
		for (int k = 0; k < 4; k++)
			if (rd16(s + 0x36 + 2 * k) >= nv)
				return TRK_ERR_SECTION;
		if (rd16(s + 0x30) & ~(uint32_t) TRK_SEC_FLAGS_KNOWN)
			return TRK_ERR_SECTION;
		if (rd16(s + 0x32) + rd16(s + 0x34) > nvis)
			return TRK_ERR_SECTION;
	}
	for (uint32_t i = 0; i < nvis; i++)
		if (rd16(fvis + 2 * i) >= ns)
			return TRK_ERR_VIS;

	out->vertices = (const TrkVertex *) fv;
	out->faces = (const TrkFace *) ff;
	out->sections = (const TrkSection *) fs;
	out->vis = (const uint16_t *) fvis;
	out->section_count = ns;
	out->vertex_count = nv;
	out->face_count = nf;
	out->vis_count = nvis;
	out->start_section = rd16(d + 0x20);
	out->flags = rd16(d + 0x22);
	out->texture_count = ntex;
	out->total_length = rd32(d + 0x38);
	return TRK_OK;
}

const TrkVertex *track_vertex(const Track *t, int i)
{
	return (i >= 0 && i < t->vertex_count) ? &t->vertices[i] : NULL;
}

const TrkFace *track_face(const Track *t, int i)
{
	return (i >= 0 && i < t->face_count) ? &t->faces[i] : NULL;
}

const TrkSection *track_section(const Track *t, int i)
{
	return (i >= 0 && i < t->section_count) ? &t->sections[i] : NULL;
}
