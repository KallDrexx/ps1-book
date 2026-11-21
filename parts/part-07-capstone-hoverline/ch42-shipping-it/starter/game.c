#include <stdint.h>
#include <stdio.h>
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
#include "collide.h"
#include "handling.h"
#include "race.h"
#include "trackload.h"
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
	if (s == STATE_COUNTDOWN) {
		ship_place(&ship, &track);                   /* the start line, every time a race begins */
		ship_ticks = 0;
		chase_camera_update(&ship);
		ship_section = track_nearest_brute(&track, ship.pos);   /* Chapter 40 (README 5.3): the first answer comes from the full search */
		collide_reset();                                        /* the counters and the hit clock start here */
		race_reset(&race);                                      /* Chapter 41: a new race, a new clock */
		audio_engine_start();                                   /* the engine hum idles during the countdown */
	} else if (s != STATE_RACE) {
		audio_engine_stop();                                    /* title and results: silent engine */
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

/* TODO (README 5.3): the debug keys and the debug readout (draw_readout, vis_readout_format, collide_format) belong to the development disc only: leave them out
   when HOVERLINE_RELEASE is defined (`make release` defines it).
   The debug keys of Chapters 34 and 36 (edge-triggered): Select = wireframe, Triangle = subdivision outlines, R1 = subdivision on / off. */
static void debug_toggles(void)
{
	if (input_pressed(INPUT_SELECT))
		wire_mode ^= 1;
	if (input_pressed(INPUT_TRIANGLE))
		subdiv_debug ^= 1;
	if (input_pressed(INPUT_R1))
		subdiv_enabled ^= 1;
}

void game_update(void)
{
	measure_ticks();
	if (game_state == STATE_TITLE) {
		if (input_pressed(INPUT_LEFT))
			track_switch(1);                             /* Chapter 40 (README 5.9): the title's track menu */
		else if (input_pressed(INPUT_RIGHT))
			track_switch(2);
		if (input_pressed(INPUT_START))
			set_state(STATE_COUNTDOWN);
	} else if (game_state == STATE_COUNTDOWN) {
		if (input_pressed(INPUT_START)) {
			set_state(STATE_TITLE);
			return;
		}
		debug_toggles();
		for (int k = 0; k < frame_ticks; k++) {
			int ev = race_countdown_tick(&race, race_hz());

			if (ev == RACE_BEEP)
				audio_play_sfx(SMP_BEEP);
			if (ev == RACE_GO) {
				audio_play_sfx(SMP_GO);
				set_state(STATE_RACE);
				break;
			}
		}
		chase_camera_update(&ship);
	} else if (game_state == STATE_RACE) {
		if (input_pressed(INPUT_START)) {
			set_state(STATE_TITLE);
			return;
		}
		debug_toggles();
		for (int k = 0; k < frame_ticks; k++) {
			int ev;

			ship_update(&ship, input_buttons(), dt_scale);
			collide_ship(&track, &ship);                 /* after every tick, so a fast frame cannot skip a wall (Chapter 40) */
			handling_auto_pitch(&ship, &track, ship_section, dt_scale);
			ship_ticks++;
			ev = race_tick(&race, &track, ship_section);
			if (ev & RACE_FINISH) {
				set_state(STATE_RESULTS);
				break;
			}
			if (ev & RACE_LAP)
				audio_play_sfx(SMP_BEEP);
		}
		chase_camera_update(&ship);
		if (game_state == STATE_RACE)
			audio_engine_update(ship.speed);             /* the hum follows the speed (Chapter 39) */
	} else {
		if (input_pressed(INPUT_START))
			set_state(STATE_TITLE);
		else if (input_pressed(INPUT_CROSS))
			set_state(STATE_COUNTDOWN);
		else
			debug_toggles();
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
	pri = ot_alloc(READOUT_BYTES);
	if (pri)
		FntSort(ot_slot(0), pri, READOUT_X, READOUT_Y + 12, collide_text);       /* Chapter 40: the edge distances, one line below */
}

/* The text of race_format_text, one FntSort per non-empty line, in slot 0 (on top). x, y: the first line. */
static void draw_race_text(int x, int y)
{
	for (int i = 0; i < RACE_LINES; i++) {
		void *pri;

		if (!race_text[i][0])
			continue;
		pri = ot_alloc(READOUT_BYTES);
		if (pri)
			FntSort(ot_slot(0), pri, x, y + 12 * i, race_text[i]);
	}
}

/* The title's track menu: "< TRACK n >" under the logo. */
static void draw_menu(void)
{
	char text[24];
	void *pri = ot_alloc(READOUT_BYTES);

	snprintf(text, sizeof text, "< TRACK %d >", (int) track_selected);
	if (pri)
		FntSort(ot_slot(0), pri, 112, 192, text);
}

void draw_track(void)
{
	submitted_objects = 0;
	render_begin();
	track_draw_visible(&track, ship_section);
	draw_ship();
	prims_this_frame = prims_submitted;              /* counted BEFORE the readout's characters are added */
	vis_readout_format();
	collide_format();
	draw_readout();
	race_format_text(&race, game_state, race_hz());      /* Chapter 41 (README 5.8) */
	if (game_state == STATE_RESULTS)
		draw_race_text(96, 56);
	else
		draw_race_text(8, 44);
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
		draw_menu();
		race_format_text(&race, STATE_TITLE, race_hz());
		draw_race_text(96, 208);
	} else if (!load_status) {
		draw_track();
	}
	ot_draw();
	display_swap();
}
