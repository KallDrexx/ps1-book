#include <stdint.h>
#include "model.h"

uint32_t read_be32(const uint8_t *p)
{
	return ((uint32_t) p[0] << 24) | ((uint32_t) p[1] << 16) | ((uint32_t) p[2] << 8) | p[3];
}

int model_parse(Model *m, const void *data, uint32_t size)
{
	const uint8_t *b = data;
	uint32_t nv, nf, face_off;

	if (((uintptr_t) data & 3) || size < 12)
		return 0;
	if (b[0] != 'M' || b[1] != 'D' || b[2] != 'L' || b[3] != '1')
		return 0;
	nv = read_be32(b + 4);
	if (nv < 1 || nv > 255 || size < 12 + 8 * nv)
		return 0;
	face_off = 8 + 8 * nv;
	nf = read_be32(b + face_off);
	if (nf > (size - 12 - 8 * nv) / 8 || size != 12 + 8 * nv + 8 * nf)
		return 0;

	const ModelFace *f = (const ModelFace *) (b + face_off + 4);
	for (uint32_t k = 0; k < nf; k++) {
		int n = f[k].i[3] == 0xFF ? 3 : 4;
		for (int j = 0; j < n; j++)
			if (f[k].i[j] >= nv)
				return 0;
	}
	m->vertex_count = nv;
	m->face_count   = nf;
	m->verts        = (const SVECTOR *) (b + 8);
	m->faces        = f;
	return 1;
}
