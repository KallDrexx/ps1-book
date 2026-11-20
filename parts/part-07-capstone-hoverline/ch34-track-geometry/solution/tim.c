#include <stdint.h>
#include <psxgpu.h>
#include "tim.h"

static uint32_t rd16(const uint8_t *p) { return p[0] | (p[1] << 8); }
static uint32_t rd32(const uint8_t *p) { return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t) p[3] << 24); }

/* Check the block at `off` and report its rectangle and the offset of its pixels; returns the offset after it, or 0. */
static uint32_t block(const uint8_t *d, uint32_t size, uint32_t off, int32_t r[4], uint32_t *pixels)
{
	uint32_t bnum, x, y, w, h;

	if (off > size || size - off < 12)
		return 0;
	bnum = rd32(d + off);
	x = rd16(d + off + 4);
	y = rd16(d + off + 6);
	w = rd16(d + off + 8);
	h = rd16(d + off + 10);
	if (w < 1 || h < 1 || x + w > 1024 || y + h > 512)
		return 0;
	if (bnum != 12 + w * h * 2 || bnum > size - off)
		return 0;
	r[0] = x; r[1] = y; r[2] = w; r[3] = h;
	*pixels = off + 12;
	return off + bnum;
}

int tim_parse(TimInfo *t, const void *data, uint32_t size)
{
	const uint8_t *d = data;
	TimInfo n;
	int32_t r[4];
	uint32_t flags, pmode, off = 8, px, mult;

	if (((uintptr_t) d & 3) || size < 20)
		return 0;
	flags = rd32(d + 4);
	pmode = flags & 7;
	if (rd32(d) != 0x10 || (flags & ~0xFu) || pmode > 2 || ((flags >> 3) & 1) != (pmode < 2))
		return 0;
	n.bpp = 4 << pmode;
	n.clut_x = n.clut_y = n.clut_w = n.clut_h = 0;
	n.clut_data = 0;
	if (pmode < 2) {
		off = block(d, size, off, r, &px);
		if (!off || (r[0] & 15) || r[2] != (pmode == 0 ? 16 : 256))
			return 0;
		n.clut_x = r[0]; n.clut_y = r[1]; n.clut_w = r[2]; n.clut_h = r[3];
		n.clut_data = (const uint32_t *) (d + px);
	}
	off = block(d, size, off, r, &px);
	if (!off || off != size)
		return 0;
	n.img_x = r[0]; n.img_y = r[1]; n.img_w = r[2]; n.img_h = r[3];
	n.img_data = (const uint32_t *) (d + px);
	/* the image must lie inside one texture page: 256 x 256 texels */
	mult = pmode == 0 ? 4 : pmode == 1 ? 2 : 1;
	if ((uint32_t) (n.img_x % 64 + n.img_w) * mult > 256 || n.img_y % 256 + n.img_h > 256)
		return 0;
	*t = n;
	return 1;
}

void tim_upload(const TimInfo *t)
{
	RECT r;

	if (t->clut_w) {
		setRECT(&r, t->clut_x, t->clut_y, t->clut_w, t->clut_h);
		LoadImage(&r, t->clut_data);
		DrawSync(0);
	}
	setRECT(&r, t->img_x, t->img_y, t->img_w, t->img_h);
	LoadImage(&r, t->img_data);
	DrawSync(0);
}

void tex_from_tim(Tex *tex, const TimInfo *t)
{
	int tp = t->bpp == 4 ? 0 : t->bpp == 8 ? 1 : 2;
	int mult = 4 >> tp;

	tex->tpage = getTPage(tp, 0, t->img_x, t->img_y);
	tex->clut = t->clut_w ? getClut(t->clut_x, t->clut_y) : 0;
	tex->u = (t->img_x % 64) * mult;
	tex->v = t->img_y % 256;
	tex->w = t->img_w * mult;
	tex->h = t->img_h;
}
