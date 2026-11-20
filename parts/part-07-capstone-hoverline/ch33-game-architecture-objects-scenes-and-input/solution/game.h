#ifndef GAME_H
#define GAME_H

#include <stdint.h>
#include <psxgte.h>
#include "object.h"

/* The states of the game's state machine (README 5.8). The verifier reads game_state. */
enum { STATE_TITLE = 0, STATE_GAME = 1 };

/* State the verifier reads. */
extern int32_t game_state;           /* STATE_TITLE or STATE_GAME */
extern int32_t state_changes;        /* how many times game_state has changed since boot */
extern int32_t submitted_objects;    /* objects drawn in the last game frame (0 in the title) */
extern int32_t proj_h;               /* projection distance h, in pixels */
extern int32_t frame_no;             /* frames completed */

/* One step of the state machine. Call once per frame, right after input_update.
   TITLE: input_pressed(START) -> GAME. GAME: input_pressed(START) -> TITLE; otherwise camera_update().
   Every change of state increments state_changes. Edge-triggered: holding START changes the state once. */
void game_update(void);

/* Draw the frame for the current state: display_clear, ot_begin_frame, the state's picture, ot_draw, display_swap.
   TITLE: title_draw only; submitted_objects = 0. GAME: draw_scene(). */
void game_draw(void);

/* The game picture (README 5.7): render_begin(); then for every node of the list: cull_test with the camera
   (cam_eye, scene_cull_radius); set o->visible; draw the visible ones with draw_object. submitted_objects = how many were drawn. */
void draw_scene(void);

/* Draw one visible object. `d` is its position relative to the eye (cull_test's output). Composes the object's rotation and scale
   with the camera's rotation, puts d through it as the translation, loads the result into the GTE and calls render_shp. */
void draw_object(const Object *o, const VECTOR *d);

#endif
