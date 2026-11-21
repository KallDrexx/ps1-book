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
#include "ship.h"
#include "track_vis.h"
#include "tpk.h"
#include "audio.h"
#include "game.h"

int32_t game_state;                  /* STATE_TITLE (0) at boot */
int32_t state_changes;
int32_t submitted_objects;
int32_t proj_h = 320;
int32_t frame_no;
int32_t frame_ticks = 1;
int32_t ship_ticks;
int32_t subdiv_enabled = 0;

#define READOUT_X     8
#define READOUT_Y     8
#define READOUT_BYTES 512                /* room for the characters of one line (FntSort writes about 16 bytes per character) */

extern int32_t load_status;          /* main.c: 0 = everything loaded */
extern TpkTextures store;            /* main.c: PROPS.TPK, shared by the scenery shapes */

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
	if (s == STATE_GAME) {
		ship_place(&ship, &track);                   /* the start line, every time the game is entered */
		ship_ticks = 0;
		chase_camera_update(&ship);
		ship_section = track_nearest_brute(&track, ship.pos);   /* README 5.3: the first answer comes from the full search */
		audio_events_reset(&track, &ship, ship_section);        /* Chapter 39 (README 5.6): the detector's memory starts here */
		audio_engine_start();                                   /* ... and the engine hum with it */
	} else {
		audio_engine_stop();
	}
}

static int32_t last_vsync;

/* How many ticks (video frames) the world advances this frame: the vertical blanks since the last measurement, 1 to MAX_TICKS. */
static void measure_ticks(void)
{
	int32_t now = VSync(-1), n = now - last_vsync;

	last_vsync = now;
	frame_ticks = n < 1 ? 1 : (n > MAX_TICKS ? MAX_TICKS : n);
}

void game_update(void)
{
	measure_ticks();
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
			if (input_pressed(INPUT_R1))
				subdiv_enabled ^= 1;
			for (int k = 0; k < frame_ticks; k++) {
				ship_update(&ship, input_buttons(), dt_scale);
				ship_ticks++;
			}
			chase_camera_update(&ship);
			ship_section = track_nearest_update(&track, ship.pos, ship_section);   /* README 5.4 */
			audio_events_update(&track, &ship, ship_section);                      /* Chapter 39: boost chime, thud (README 5.6) */
			audio_engine_update(ship.speed);                                       /* the hum follows the speed (README 5.5) */
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
	render_shp(&scene_shapes[o->shape].shp, &store);
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

void draw_ship(void)
{
	MATRIX m, vr = view_mtx, world;
	VECTOR d = { ship.pos[0] - cam_eye.vx, ship.pos[1] - cam_eye.vy, ship.pos[2] - cam_eye.vz };

	vr.t[0] = vr.t[1] = vr.t[2] = 0;                 /* rotation only: the position goes in camera-relative (Chapter 33) */
	ship_matrix(&ship, &m);
	TransMatrix(&m, &d);
	CompMatrixLV(&vr, &m, &world);
	load_matrix(&world);
	render_shp(&ship_shp, &ship_store);
}

/* The readout: vis_text sorted into slot 0 of the table (the nearest slot, drawn last: on top of everything), 8 x 8 white characters at (8, 8). */
static void draw_readout(void)
{
	void *pri = ot_alloc(READOUT_BYTES);

	if (pri)
		FntSort(ot_slot(0), pri, READOUT_X, READOUT_Y, vis_text);
}

void draw_track(void)
{
	submitted_objects = 0;
	render_begin();
	track_draw_visible(&track, ship_section);
	draw_ship();
	prims_this_frame = prims_submitted;              /* counted BEFORE the readout's characters are added */
	vis_readout_format();
	draw_readout();
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
