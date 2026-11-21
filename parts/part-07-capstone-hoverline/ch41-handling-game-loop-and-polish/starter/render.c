#include <stdint.h>
#include <psxgpu.h>
#include <psxgte.h>
#include <inline_c.h>
#include <psxe/ot.h>
#include "tpk.h"
#include "render.h"

int32_t prims_submitted;
int32_t prims_dropped;
static int budget_gone;              /* the primitive buffer ran out this frame */

void render_begin(void)
{
	prims_submitted = 0;
	prims_dropped = 0;
	budget_gone = 0;
}

int render_shp(const Shp *shp, const TpkTextures *st)
{
	static int32_t sxy[SHP_MAX_VERTS], sz[SHP_MAX_VERTS];
	const uint8_t *rec = shp->prims;
	int linked = 0;

	for (uint32_t i = 0; i < shp->vertex_count; i++) {
		gte_ldv0(&shp->verts[i]);
		gte_rtps();
		gte_stsxy(&sxy[i]);
		gte_stsz(&sz[i]);
	}
	for (uint32_t i = 0; i < shp->prim_count; i++) {
		ShpPrim p;
		int quad, textured, n;
		int32_t area, otz;
		const Tex *tex;
		void *pkt;

		rec += shp_decode(rec, &p);
		quad = p.type & 1;
		textured = p.type >= SHP_FT3;
		n = quad ? 4 : 3;

		gte_ldsxy3(sxy[p.v[0]], sxy[p.v[1]], sxy[p.v[2]]);
		gte_nclip();
		gte_stopz(&area);
		if (area == 0 || (area < 0 && !(p.flags & SHP_DOUBLE_SIDED)))
			continue;                                  /* edge-on, or facing away */
		for (int k = 0; k < n; k++)
			if (sz[p.v[k]] < NEAR_Z)
				goto skip;                             /* too close to, or behind, the eye */

		if (budget_gone) {
			prims_dropped++;
			continue;
		}
		if (quad) {
			gte_ldsz4(sz[p.v[0]], sz[p.v[1]], sz[p.v[2]], sz[p.v[3]]);
			gte_avsz4();
		} else {
			gte_ldsz3(sz[p.v[0]], sz[p.v[1]], sz[p.v[2]]);
			gte_avsz3();
		}
		gte_stotz(&otz);

		tex = textured ? &st->tex[p.tex] : NULL;
		pkt = ot_alloc(shp_packet_size(p.type, tex != NULL));
		if (!pkt) {
			budget_gone = 1;
			prims_dropped++;
			continue;
		}
		shp_fill(pkt, &p, sxy, tex);
		ot_add(pkt, otz >> OTZ_SHIFT);
		prims_submitted++;
		linked++;
skip:
		;
	}
	return linked;
}
