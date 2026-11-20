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
#include "title.h"
#include "game.h"

/* Chapter 33, part 4 of 4: the state machine and the scene drawing (README 7.3 steps 5 and 6). game.h is the contract. */

int32_t game_state;                  /* STATE_TITLE (0) at boot */
int32_t state_changes;
int32_t submitted_objects;
int32_t proj_h = 320;
int32_t frame_no;

extern int32_t load_status;          /* main.c: 0 = everything loaded */

/* Given: load a MATRIX into the GTE (the SDK macros clobber $t0/$t1; see Chapter 25). */
static __attribute__((noipa, unused)) void load_matrix(const MATRIX *m)
{
	gte_SetRotMatrix(m);
	gte_SetTransMatrix(m);
}

static __attribute__((unused)) void set_state(int32_t s)
{
	game_state = s;
	state_changes++;
}

void game_update(void)
{
	/* TODO (README 7.3 step 5): the state machine of game.h. TITLE: Start pressed (an EDGE: input_pressed) -> GAME.
	   GAME: Start pressed -> TITLE, otherwise camera_update(). Count every change in state_changes (set_state does it). */
	(void) set_state;
}

void draw_object(const Object *o, const VECTOR *d)
{
	/* TODO (README 7.3 step 6): the object's rotation (and scale if it is not 4096) composed with the camera's ROTATION (view_mtx with t = 0),
	   d as the translation, load_matrix, then render_shp(&scene_shapes[o->shape].shp). */
	(void) o;
	(void) d;
	(void) load_matrix;
}

void draw_scene(void)
{
	/* TODO (README 7.3 step 6): submitted_objects = 0; render_begin(); for every node: o->visible = cull_test(...); draw the visible ones. */
	submitted_objects = 0;
	render_begin();
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
		draw_scene();
	}
	ot_draw();
	display_swap();
}
