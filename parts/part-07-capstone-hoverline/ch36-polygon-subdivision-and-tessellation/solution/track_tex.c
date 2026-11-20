#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "cdrom.h"
#include "tim.h"
#include "tpk.h"
#include "track_tex.h"

const TileSlot vram_layout[LAYOUT_TILE_COUNT] = LAYOUT_INIT;

int32_t tex_status = TT_ERR_READ;
int32_t track_tex_count;
Tex     track_tex[LAYOUT_TILE_COUNT];

static int fail(int code, void *a, void *b)
{
	free(a);
	free(b);
	track_tex_count = 0;
	memset(track_tex, 0, sizeof track_tex);
	return tex_status = code;
}

/* bits per pixel of a texture-page word: bits 7-8 are 0 (4), 1 (8) or 2 (16) */
static int tpage_bpp(uint16_t tpage)
{
	int tp = (tpage >> 7) & 3;

	return tp == 0 ? 4 : tp == 1 ? 8 : tp == 2 ? 16 : 0;
}

static int slot_ok(const TileSlot *s, int bpp)
{
	int clut_x = (s->clut & 63) * 16, clut_y = s->clut >> 6;
	int clut_w = bpp == 4 ? 16 : 256;

	if (s->w < 1 || s->h < 1 || s->x + s->w > 1024 || s->y + s->h > 512)
		return 0;
	if (bpp != 16 && (clut_x + clut_w > 1024 || clut_y > 511))
		return 0;
	return s->tpage == (uint16_t) getTPage(bpp == 4 ? 0 : bpp == 8 ? 1 : 2, 0, s->x, s->y);
}

int track_tex_load(const char *path)
{
	TpkHeader h;
	uint32_t size, off = 0;
	uint8_t *raw;
	void *file;

	tex_status = TT_ERR_READ;
	track_tex_count = 0;
	memset(track_tex, 0, sizeof track_tex);
	file = cd_load_file(path, &size);
	if (!file)
		return fail(TT_ERR_READ, 0, 0);
	if (tpk_parse(file, size, &h))
		return fail(TT_ERR_PACK, file, 0);
	if (h.count > LAYOUT_TILE_COUNT)
		return fail(TT_ERR_COUNT, file, 0);
	raw = malloc(h.raw_size);
	if (!raw)
		return fail(TT_ERR_PACK, file, 0);
	if (tpk_unpack(file, size, raw, h.raw_size))
		return fail(TT_ERR_PACK, file, raw);
	free(file);
	file = 0;
	/* every tile is checked before the first byte goes to VRAM */
	for (uint32_t i = 0; i < h.count; i++) {
		TimInfo info;
		const TileSlot *s = &vram_layout[i];
		int bpp = tpage_bpp(s->tpage);

		if (!tim_parse(&info, raw + off, h.sizes[i]))
			return fail(TT_ERR_TIM, raw, 0);
		if (!bpp || !slot_ok(s, bpp))
			return fail(TT_ERR_SLOT, raw, 0);
		if (info.bpp != bpp || info.img_w != s->w || info.img_h != s->h)
			return fail(TT_ERR_FIT, raw, 0);
		off += h.sizes[i];
	}
	off = 0;
	for (uint32_t i = 0; i < h.count; i++) {
		TimInfo info;
		const TileSlot *s = &vram_layout[i];
		int bpp = tpage_bpp(s->tpage), mult = 4 >> (bpp == 4 ? 0 : bpp == 8 ? 1 : 2);

		tim_parse(&info, raw + off, h.sizes[i]);
		tim_upload_at(&info, s->x, s->y, (s->clut & 63) * 16, s->clut >> 6);
		track_tex[i].tpage = s->tpage;
		track_tex[i].clut = bpp == 16 ? 0 : s->clut;
		track_tex[i].u = (s->x % 64) * mult;
		track_tex[i].v = s->y % 256;
		track_tex[i].w = s->w * mult;
		track_tex[i].h = s->h;
		off += h.sizes[i];
	}
	free(raw);                               /* the pixels are in VRAM */
	track_tex_count = h.count;
	return tex_status = 0;
}

int track_face_uv(const TrkFace *f, uint8_t uv[8], uint16_t *tpage, uint16_t *clut)
{
	const Tex *t;
	int umin = 255, umax = 0;

	if (f->tex == TRK_UNTEXTURED || f->tex >= track_tex_count)
		return 0;
	t = &track_tex[f->tex];
	for (int k = 0; k < 4; k++) {
		if (f->uv[2 * k] < umin) umin = f->uv[2 * k];
		if (f->uv[2 * k] > umax) umax = f->uv[2 * k];
	}
	for (int k = 0; k < 4; k++) {
		int u = f->uv[2 * k];

		if (f->flags & TRK_FLIP_H)
			u = umin + umax - u;                 /* mirror inside the face's own U range: u = 0 <-> 63 for a full tile */
		uv[2 * k] = t->u + u;
		uv[2 * k + 1] = t->v + f->uv[2 * k + 1];
	}
	*tpage = t->tpage;
	*clut = t->clut;
	return 1;
}
