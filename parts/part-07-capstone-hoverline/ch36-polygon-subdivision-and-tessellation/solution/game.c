#include <stdint.h>
#include <psxgpu.h>
#include <psxgte.h>
#include <inline_c.h>
#include <psxe/display.h>
#include <psxe/ot.h>
#include <psxe/input.h>
#include "camera.h"
#include "cull.h"
#include "scene.h"
#include "render.h"
#include "track.h"
#include "track_render.h"
#include "subdiv.h"
#include "title.h"
#include "game.h"

int32_t game_state;                  /* STATE_TITLE (0) at boot */
int32_t state_changes;
int32_t submitted_objects;
int32_t proj_h = 320;
int32_t frame_no;

extern int32_t load_status;          /* main.c: 0 = everything loaded */

/* Given: load a MATRIX into the GTE (the SDK macros clobber $t0/$t1; see Chapter 25). */
static __attribute__((noipa)) void load_matrix(const MATRIX *m)
{
	gte_SetRotMatrix(m);
	gte_SetTransMatrix(m);
}

static void set_state(int32_t s)
{
	game_state = s;
	state_changes++;
}

void game_update(void)
{
	if (game_state == STATE_TITLE) {
		if (input_pressed(INPUT_START))
			set_state(STATE_GAME);
	} else {
		if (input_pressed(INPUT_START))
			set_state(STATE_TITLE);
		else {
			if (input_pressed(INPUT_SELECT))
				wire_mode ^= 1;                          /* edge-triggered: one toggle per press */
			if (input_pressed(INPUT_TRIANGLE))
				subdiv_debug ^= 1;                       /* the same for the subdivision outlines (README 7.1) */
			camera_update();
		}
	}
}

void draw_object(const Object *o, const VECTOR *d)
{
	SVECTOR rot = { (int16_t) o->rx, (int16_t) o->ry, (int16_t) o->rz, 0 };
	MATRIX m, vr = view_mtx, world;
	VECTOR pos = *d;

	vr.t[0] = vr.t[1] = vr.t[2] = 0;                 /* rotation only: the position goes in camera-relative, so it stays small */
	RotMatrix(&rot, &m);
	if (o->scale != 4096) {
		VECTOR s = { o->scale, o->scale, o->scale };

		ScaleMatrix(&m, &s);
	}
	TransMatrix(&m, &pos);
	CompMatrixLV(&vr, &m, &world);                   /* world.t = view rotation * d */
	load_matrix(&world);
	render_shp(&scene_shapes[o->shape].shp);
}

void draw_scene(void)
{
	submitted_objects = 0;
	render_begin();
	for (OBJ_EACH(o, object_head)) {
		VECTOR d;

		o->visible = cull_test(o, &cam_eye, scene_cull_radius, &d);
		if (!o->visible)
			continue;
		submitted_objects++;
		draw_object(o, &d);
	}
}

void draw_track(void)
{
	submitted_objects = 0;
	render_begin();
	track_draw(&track, 0, track.section_count);
}

void game_draw(void)
{
	if (game_state == STATE_TITLE)
		display_clear(0, 0, 0);
	else if (load_status)
		display_clear(96, 0, 0);                     /* red screen: loading failed */
	else
		display_clear(24, 24, 48);
	ot_begin_frame();
	if (game_state == STATE_TITLE) {
		submitted_objects = 0;
		render_begin();
		title_draw(frame_no);
	} else if (!load_status) {
		draw_track();
	}
	ot_draw();
	display_swap();
}
