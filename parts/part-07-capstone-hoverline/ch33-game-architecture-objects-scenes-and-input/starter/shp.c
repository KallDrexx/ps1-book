#include <stdint.h>
#include <string.h>
#include <psxgpu.h>
#include "shp.h"

static const uint8_t REC_SIZE[SHP_TYPES] = { 16, 20, 24, 32, 24, 32, 32, 44 };

static uint32_t rd16(const uint8_t *p) { return p[0] | (p[1] << 8); }
static uint32_t rd32(const uint8_t *p) { return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t) p[3] << 24); }

/* The traits of a type tag: tri/quad, textured, Gouraud. */
static int is_quad(unsigned t)     { return t & 1; }
static int is_textured(unsigned t) { return t >= SHP_FT3; }
static int is_gouraud(unsigned t)  { return t == SHP_G3 || t == SHP_G4 || t == SHP_GT3 || t == SHP_GT4; }

uint32_t shp_record_size(unsigned type)
{
	return type < SHP_TYPES ? REC_SIZE[type] : 0;
}

uint32_t shp_decode(const uint8_t *rec, ShpPrim *p)
{
	unsigned t = rec[0], nv = is_quad(t) ? 4 : 3;
	const uint8_t *q = rec + 4;

	p->type = t;
	p->flags = rec[1];
	p->size = rd16(rec + 2);
	for (unsigned k = 0; k < nv; k++, q += 2)
		p->v[k] = rd16(q);
	p->normal = rd16(q);
	q += is_quad(t) ? 4 : 2;                      /* the normal index, plus the pad of a quad */
	if (is_textured(t)) {
		for (unsigned k = 0; k < nv; k++, q += 2) {
			p->uv[k][0] = q[0];
			p->uv[k][1] = q[1];
		}
		p->tex = rd16(q);
		q += is_quad(t) ? 4 : 2;                  /* the texture index, plus the pad of a quad */
	}
	for (unsigned k = 0; k < (is_gouraud(t) ? nv : 1); k++, q += 4)
		for (int c = 0; c < 4; c++)
			p->rgb[k][c] = q[c];
	return REC_SIZE[t];
}

int shp_parse(const void *data, size_t size, Shp *s)
{
	const uint8_t *d = data;
	uint32_t vn, nn, pn, tn, voff, noff, poff, psize;
	const uint8_t *rec, *end;

	if ((uintptr_t) data & 3)
		return SHP_ERR_ALIGN;
	if (size < 4 || memcmp(d, "SHP1", 4) != 0)
		return SHP_ERR_MAGIC;
	if (size < 0x40 || rd32(d + 4) != size)
		return SHP_ERR_HEADER;
	vn = rd16(d + 0x18);
	nn = rd16(d + 0x1A);
	pn = rd16(d + 0x1C);
	tn = rd16(d + 0x1E);
	voff = rd32(d + 0x20);
	noff = rd32(d + 0x24);
	poff = rd32(d + 0x28);
	psize = rd32(d + 0x2C);
	if (vn < 1 || vn > SHP_MAX_VERTS || pn < 1 || tn > 255)
		return SHP_ERR_HEADER;
	if (voff != 0x40 || noff != 0x40 + 8 * vn || poff != noff + 8 * nn)
		return SHP_ERR_HEADER;
	if (psize != size - poff || poff > size)      /* poff + psize == size, without overflow */
		return SHP_ERR_HEADER;

	memset(s->counts, 0, sizeof s->counts);
	rec = d + poff;
	end = d + size;
	for (uint32_t i = 0; i < pn; i++) {
		ShpPrim p;
		uint32_t n;

		if (end - rec < 4 || rec[0] >= SHP_TYPES)
			return SHP_ERR_PRIM;
		n = REC_SIZE[rec[0]];
		if (rd16(rec + 2) != n || (uint32_t) (end - rec) < n)
			return SHP_ERR_PRIM;
		shp_decode(rec, &p);
		for (unsigned k = 0; k < (is_quad(p.type) ? 4u : 3u); k++)
			if (p.v[k] >= vn)
				return SHP_ERR_INDEX;
		if (p.normal >= nn)
			return SHP_ERR_INDEX;
		if (is_textured(p.type) && p.tex >= tn)
			return SHP_ERR_TEXTURE;
		s->counts[p.type]++;
		rec += n;
	}
	if (rec != end)
		return SHP_ERR_PRIM;

	memcpy(s->name, d + 8, 16);
	s->name[16] = 0;
	s->vertex_count = vn;
	s->normal_count = nn;
	s->prim_count = pn;
	s->texture_count = tn;
	s->verts = (const SVECTOR *) (d + voff);
	s->normals = (const SVECTOR *) (d + noff);
	s->prims = d + poff;
	s->prims_size = psize;
	for (int k = 0; k < 6; k++)
		s->bbox[k] = (int16_t) rd16(d + 0x30 + 2 * k);
	return SHP_OK;
}

uint32_t shp_packet_size(unsigned type, int textured)
{
	if (type >= SHP_TYPES)
		return 0;
	if (!textured && is_textured(type))
		type -= 4;                                /* FT3 -> F3, FT4 -> F4, GT3 -> G3, GT4 -> G4 */
	switch (type) {
	case SHP_F3:  return sizeof(POLY_F3);
	case SHP_F4:  return sizeof(POLY_F4);
	case SHP_G3:  return sizeof(POLY_G3);
	case SHP_G4:  return sizeof(POLY_G4);
	case SHP_FT3: return sizeof(POLY_FT3);
	case SHP_FT4: return sizeof(POLY_FT4);
	case SHP_GT3: return sizeof(POLY_GT3);
	default:      return sizeof(POLY_GT4);
	}
}

#define X(i) ((int16_t) sxy[p->v[i]])
#define Y(i) ((int16_t) (sxy[p->v[i]] >> 16))
#define U(i) ((uint8_t) (p->uv[i][0] + tex->u))
#define V(i) ((uint8_t) (p->uv[i][1] + tex->v))
#define COL(q, k) setRGB##k(q, p->rgb[k][0], p->rgb[k][1], p->rgb[k][2])

void shp_fill(void *pkt, const ShpPrim *p, const int32_t *sxy, const Tex *tex)
{
	unsigned t = p->type;
	int semi = (p->flags & SHP_SEMI_TRANS) != 0;

	if (!tex && is_textured(t))
		t -= 4;
	switch (t) {
	case SHP_F3: {
		POLY_F3 *q = pkt;
		setPolyF3(q);
		COL(q, 0);
		setXY3(q, X(0), Y(0), X(1), Y(1), X(2), Y(2));
		setSemiTrans(q, semi);
		break; }
	case SHP_F4: {
		POLY_F4 *q = pkt;
		setPolyF4(q);
		COL(q, 0);
		setXY4(q, X(0), Y(0), X(1), Y(1), X(2), Y(2), X(3), Y(3));
		setSemiTrans(q, semi);
		break; }
	case SHP_G3: {
		POLY_G3 *q = pkt;
		setPolyG3(q);
		COL(q, 0); COL(q, 1); COL(q, 2);
		setXY3(q, X(0), Y(0), X(1), Y(1), X(2), Y(2));
		setSemiTrans(q, semi);
		break; }
	case SHP_G4: {
		POLY_G4 *q = pkt;
		setPolyG4(q);
		COL(q, 0); COL(q, 1); COL(q, 2); COL(q, 3);
		setXY4(q, X(0), Y(0), X(1), Y(1), X(2), Y(2), X(3), Y(3));
		setSemiTrans(q, semi);
		break; }
	case SHP_FT3: {
		POLY_FT3 *q = pkt;
		setPolyFT3(q);
		COL(q, 0);
		setXY3(q, X(0), Y(0), X(1), Y(1), X(2), Y(2));
		setUV3(q, U(0), V(0), U(1), V(1), U(2), V(2));
		q->tpage = tex->tpage;
		q->clut = tex->clut;
		setSemiTrans(q, semi);
		break; }
	case SHP_FT4: {
		POLY_FT4 *q = pkt;
		setPolyFT4(q);
		COL(q, 0);
		setXY4(q, X(0), Y(0), X(1), Y(1), X(2), Y(2), X(3), Y(3));
		setUV4(q, U(0), V(0), U(1), V(1), U(2), V(2), U(3), V(3));
		q->tpage = tex->tpage;
		q->clut = tex->clut;
		setSemiTrans(q, semi);
		break; }
	case SHP_GT3: {
		POLY_GT3 *q = pkt;
		setPolyGT3(q);
		COL(q, 0); COL(q, 1); COL(q, 2);
		setXY3(q, X(0), Y(0), X(1), Y(1), X(2), Y(2));
		setUV3(q, U(0), V(0), U(1), V(1), U(2), V(2));
		q->tpage = tex->tpage;
		q->clut = tex->clut;
		setSemiTrans(q, semi);
		break; }
	default: {
		POLY_GT4 *q = pkt;
		setPolyGT4(q);
		COL(q, 0); COL(q, 1); COL(q, 2); COL(q, 3);
		setXY4(q, X(0), Y(0), X(1), Y(1), X(2), Y(2), X(3), Y(3));
		setUV4(q, U(0), V(0), U(1), V(1), U(2), V(2), U(3), V(3));
		q->tpage = tex->tpage;
		q->clut = tex->clut;
		setSemiTrans(q, semi);
		break; }
	}
}
