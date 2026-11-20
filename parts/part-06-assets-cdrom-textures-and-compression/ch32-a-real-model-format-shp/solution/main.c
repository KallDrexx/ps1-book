#include <stdint.h>
#include <stdlib.h>
#include <psxgpu.h>
#include <psxgte.h>
#include <inline_c.h>
#include <psxe/display.h>
#include <psxe/ot.h>
#include "cdrom.h"
#include "tim.h"
#include "tpk.h"
#include "shp.h"

#define CX (SCREEN_W / 2)
#define CY (SCREEN_H / 2)
#define OTZ_SHIFT 3                  /* OT slot = OTZ >> 3 */

#define TPK_PATH "\\DATA\\SHIP.TPK;1"
#define SHP_PATH "\\DATA\\SHIP.SHP;1"

/* State the verifier reads and patches. Do not change the names, types, order or initial values. */

typedef struct {
	int32_t prim_counts[8];          /* records of each type: F3 F4 G3 G4 FT3 FT4 GT3 GT4 */
	int32_t vertex_count;
	int32_t normal_count;
	int32_t prim_count;
	int32_t texture_count;
	char    name[16];                /* the header's name field, copied */
} ShpInfo;

ShpInfo     shp_info;
Shp         shp;                     /* the parsed model; its pointers point into shp_buf */
void       *shp_buf;
uint32_t    shp_size;
TpkTextures store;                   /* the texture store of SHIP.TPK */
int32_t     load_status;             /* 0 = loaded; 100 = CdInit failed; 1 = tpk_load failed; 2 = .SHP read/parse/store check failed */
int32_t     tpk_status;              /* what tpk_load returned */
int32_t     shp_status;              /* SHP_OK or the SHP_ERR_* code */

int32_t render_mode = 1;             /* 0 = flat fallback (untextured), 1 = textured */
int32_t angle_x = 160;               /* the ship's rotation, 4096 = one turn */
int32_t angle_y = 0;
int32_t angle_z = 0;
int32_t spin_step = 8;               /* added to angle_y after every frame */
int32_t cam_z = 1000;                /* z of the ship's origin, in model units */
int32_t proj_h = 360;                /* projection distance h, in pixels */

MATRIX  mtx;                         /* the matrix uploaded to the GTE this frame */
int32_t screen_xy[SHP_MAX_VERTS];    /* vertex i: low half = x, high half = y */
int32_t screen_z[SHP_MAX_VERTS];     /* vertex i: SZ */
int32_t prims_submitted;             /* GPU primitives linked into the table this frame */
int32_t frame_no;                    /* frames completed */

__attribute__((noinline)) void frame_done(void) { __asm__ volatile("" ::: "memory"); }

/* Given: load a MATRIX into the GTE (see Chapter 25: the SDK macros clobber $t0/$t1). */
static __attribute__((noipa)) void load_matrix(const MATRIX *m)
{
	gte_SetRotMatrix(m);
	gte_SetTransMatrix(m);
}

static void load_assets(void)
{
	if (!cd_init()) {
		load_status = 100;
		return;
	}
	tpk_status = tpk_load(TPK_PATH, &store);
	if (tpk_status) {
		load_status = 1;
		return;
	}
	tpk_free_raw(&store);            /* the pixels are in VRAM; tex[] stays valid */
	shp_buf = cd_load_file(SHP_PATH, &shp_size);
	shp_status = shp_buf ? shp_parse(shp_buf, shp_size, &shp) : SHP_ERR_READ;
	if (shp_status == SHP_OK && shp.texture_count > store.count)
		shp_status = SHP_ERR_STORE;
	if (shp_status) {
		load_status = 2;
		return;
	}
	for (int t = 0; t < SHP_TYPES; t++)
		shp_info.prim_counts[t] = shp.counts[t];
	shp_info.vertex_count = shp.vertex_count;
	shp_info.normal_count = shp.normal_count;
	shp_info.prim_count = shp.prim_count;
	shp_info.texture_count = shp.texture_count;
	for (int k = 0; k < 16; k++)
		shp_info.name[k] = shp.name[k];
}

static void upload_matrix(void)
{
	SVECTOR rot = { (int16_t) angle_x, (int16_t) angle_y, (int16_t) angle_z, 0 };
	VECTOR pos = { 0, 0, cam_z };

	RotMatrix(&rot, &mtx);
	TransMatrix(&mtx, &pos);
	load_matrix(&mtx);
}

static void transform_vertices(void)
{
	for (uint32_t i = 0; i < shp.vertex_count; i++) {
		gte_ldv0(&shp.verts[i]);
		gte_rtps();
		gte_stsxy(&screen_xy[i]);
		gte_stsz(&screen_z[i]);
	}
}

static void draw_shp(void)
{
	const uint8_t *rec = shp.prims;

	prims_submitted = 0;
	for (uint32_t i = 0; i < shp.prim_count; i++) {
		ShpPrim p;
		int quad, textured;
		int32_t area, otz;
		const Tex *tex;
		void *pkt;

		rec += shp_decode(rec, &p);
		quad = p.type & 1;
		textured = p.type >= SHP_FT3;

		gte_ldsxy3(screen_xy[p.v[0]], screen_xy[p.v[1]], screen_xy[p.v[2]]);
		gte_nclip();
		gte_stopz(&area);
		if (area == 0 || (area < 0 && !(p.flags & SHP_DOUBLE_SIDED)))
			continue;                                  /* edge-on, or facing away */

		if (quad) {
			gte_ldsz4(screen_z[p.v[0]], screen_z[p.v[1]], screen_z[p.v[2]], screen_z[p.v[3]]);
			gte_avsz4();
		} else {
			gte_ldsz3(screen_z[p.v[0]], screen_z[p.v[1]], screen_z[p.v[2]]);
			gte_avsz3();
		}
		gte_stotz(&otz);

		tex = (render_mode == 1 && textured) ? &store.tex[p.tex] : NULL;
		pkt = ot_alloc(shp_packet_size(p.type, tex != NULL));
		if (!pkt)
			break;
		shp_fill(pkt, &p, screen_xy, tex);
		ot_add(pkt, otz >> OTZ_SHIFT);
		prims_submitted++;
	}
}

int main(void)
{
	display_init();
	InitGeom();
	gte_SetGeomOffset(CX, CY);
	gte_SetGeomScreen(proj_h);
	load_assets();
	/* Keeps the state above linked in even where your code does not read it. Leave this line in. */
	__asm__ volatile("" :: "r"(&shp_info), "r"(&shp), "r"(&shp_buf), "r"(&shp_size), "r"(&store), "r"(&load_status),
	                 "r"(&tpk_status), "r"(&shp_status), "r"(&render_mode), "r"(&angle_x), "r"(&angle_y), "r"(&angle_z),
	                 "r"(&spin_step), "r"(&cam_z), "r"(&proj_h), "r"(&mtx), "r"(screen_xy), "r"(screen_z), "r"(&prims_submitted),
	                 "r"(shp_parse), "r"(shp_decode), "r"(shp_record_size), "r"(shp_packet_size), "r"(shp_fill));

	for (;;) {
		if (load_status)
			display_clear(96, 0, 0);                   /* red screen: loading failed */
		else
			display_clear(16, 16, 32);
		ot_begin_frame();
		if (!load_status) {
			upload_matrix();
			transform_vertices();
			draw_shp();
			angle_y = (angle_y + spin_step) & 4095;
		}
		ot_draw();
		display_swap();
		frame_no++;
		frame_done();
	}
	return 0;
}
