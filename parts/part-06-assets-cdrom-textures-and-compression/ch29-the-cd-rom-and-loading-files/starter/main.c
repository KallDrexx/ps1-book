#include <stdint.h>
#include <stdlib.h>
#include <psxgpu.h>
#include <psxgte.h>
#include <inline_c.h>
#include <psxe/display.h>
#include <psxe/ot.h>
#include "cdrom.h"
#include "model.h"

#define CX (SCREEN_W / 2)
#define CY (SCREEN_H / 2)
#define OTZ_SHIFT 3                  /* OT slot = OTZ >> 3: the ship is close, so a finer shift than Chapter 25's 7 */

#define MODEL_PATH "\\DATA\\MODEL.BIN;1"

/* State the verifier reads. Do not change the layout, the order or the initial values. */

typedef struct {
	int32_t vertex_count;            /* what the parser found in the file */
	int32_t face_count;
	int16_t first_vertex[3];         /* x, y, z of vertex 0 */
	int16_t last_vertex[3];          /* x, y, z of the last vertex */
} ModelInfo;

ModelInfo model_info;
Model     model;                     /* the parsed model; its pointers point into model_buf */
void     *model_buf;                 /* what cd_load_file returned for MODEL_PATH */
uint32_t  model_size;                /* the size it reported */
int32_t   load_status;               /* 0 = loaded and parsed; 1 = CD init failed; 2 = load failed; 3 = parse failed */

SVECTOR rot      = { 160, 0, 0, 0 }; /* angles about X, Y, Z: 4096 = one turn */
SVECTOR rot_step = {   0, 8, 0, 0 }; /* added to rot every frame: a slow turn about Y */
int32_t cam_z    = 800;              /* z of the model's origin, in model units */
int32_t proj_h   = 256;              /* projection distance h, in pixels */

MATRIX  mtx;                         /* the matrix uploaded to the GTE this frame */
int32_t screen_xy[256];              /* vertex i: low half = x, high half = y */
int32_t screen_z[256];               /* vertex i: SZ */
int32_t prims_submitted;             /* polygons linked into the table this frame */
int32_t frame_no;                    /* frames completed */

__attribute__((noinline)) void frame_done(void) { __asm__ volatile("" ::: "memory"); }

/* Given: load a MATRIX into the GTE (see Chapter 25: the SDK macros clobber $t0/$t1). */
static __attribute__((noipa)) void load_matrix(const MATRIX *m)
{
	gte_SetRotMatrix(m);
	gte_SetTransMatrix(m);
}

static void update_angles(void)
{
	rot.vx = (rot.vx + rot_step.vx) & 4095;
	rot.vy = (rot.vy + rot_step.vy) & 4095;
	rot.vz = (rot.vz + rot_step.vz) & 4095;
}

static void upload_matrix(void)
{
	VECTOR pos = { 0, 0, cam_z };

	RotMatrix(&rot, &mtx);
	TransMatrix(&mtx, &pos);
	load_matrix(&mtx);
}

static void load_model(void)
{
	if (!cd_init()) {
		load_status = 1;
		return;
	}
	model_buf = cd_load_file(MODEL_PATH, &model_size);
	if (!model_buf) {
		load_status = 2;
		return;
	}
	if (!model_parse(&model, model_buf, model_size)) {
		load_status = 3;
		return;
	}
	/* TODO: fill model_info from `model`: both counts, vertex 0 and the LAST vertex (x, y, z each). */
}

/* TODO (README 7.5): transform every vertex of `model` with the GTE (gte_ldv0 / gte_rtps / gte_stsxy / gte_stsz)
   into screen_xy[] and screen_z[]. */
static void transform_vertices(void)
{
}

/* TODO (README 7.5): for every face: NCLIP on corners 0, 1, 2 (area <= 0: skip); AVSZ3 (triangle) or AVSZ4 (quad)
   for the depth; allocate a POLY_F3 or POLY_F4 with ot_alloc (stop if it returns NULL), set the color from the
   face record and the corners from screen_xy[], link it with ot_add(prim, otz >> OTZ_SHIFT); count it in
   prims_submitted (reset to 0 at the start). */
static void draw_faces(void)
{
	prims_submitted = 0;
}

int main(void)
{
	display_init();
	InitGeom();
	gte_SetGeomOffset(CX, CY);
	gte_SetGeomScreen(proj_h);
	load_model();
	/* Keeps the state above linked in even where your code does not read it. Leave this line in. */
	__asm__ volatile("" :: "r"(&model_info), "r"(&model), "r"(&model_buf), "r"(&model_size), "r"(&load_status),
	                 "r"(&rot), "r"(&rot_step), "r"(&cam_z), "r"(&proj_h), "r"(&mtx), "r"(screen_xy),
	                 "r"(screen_z), "r"(&prims_submitted));

	for (;;) {
		if (load_status)
			display_clear(96, 0, 0);                   /* red screen: loading failed */
		else
			display_clear(16, 16, 32);
		ot_begin_frame();
		if (!load_status) {
			update_angles();
			upload_matrix();
			transform_vertices();
			draw_faces();
		}
		ot_draw();
		display_swap();
		frame_no++;
		frame_done();
	}
	return 0;
}
