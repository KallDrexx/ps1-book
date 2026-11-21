#ifndef GAME_H
#define GAME_H

#include <stdint.h>
#include <psxgte.h>
#include "object.h"
#include "track.h"

/* The states of the game's state machine (README 5.8). The verifier reads game_state. */
enum { STATE_TITLE = 0, STATE_GAME = 1 };

/* State the verifier reads. */
extern int32_t game_state;           /* STATE_TITLE or STATE_GAME */
extern int32_t state_changes;        /* how many times game_state has changed since boot */
extern int32_t submitted_objects;    /* objects drawn in the last game frame (0 in the title) */
extern int32_t proj_h;               /* projection distance h, in pixels */
extern int32_t frame_no;             /* frames completed */
extern int32_t subdiv_enabled;       /* 0 (default): Chapter 36 subdivision off, 1: on (about half the frame rate). R1 toggles it (edge-triggered). Patchable */

#define MAX_TICKS 4                  /* most physics ticks one frame may run */

/* One step of the state machine. Call once per frame, right after input_update.
   First measures the ticks of this frame (README 5.7): frame_ticks = VSync(-1) - the last reading, clamped to 1..MAX_TICKS.
   TITLE: input_pressed(START) -> GAME. GAME: input_pressed(START) -> TITLE; otherwise input_pressed(SELECT) toggles wire_mode,
   input_pressed(TRIANGLE) toggles subdiv_debug, input_pressed(R1) toggles subdiv_enabled, then frame_ticks times
   ship_update(&ship, input_buttons(), dt_scale) (ship_ticks++ each), then chase_camera_update(&ship).
   Entering GAME runs ship_place(&ship, &track), sets ship_ticks = 0 and calls chase_camera_update.
   Every change of state increments state_changes. Edge-triggered: holding START changes the state once. */
void game_update(void);

/* Draw the frame for the current state: display_clear, ot_begin_frame, the state's picture, ot_draw, display_swap.
   TITLE: title_draw only; submitted_objects = 0. GAME: draw_track(). */
void game_draw(void);

/* The game picture of this chapter (README 5.6): render_begin(); then the whole track, sections 0 .. section_count - 1, with track_draw. */
void draw_track(void);

/* Chapter 37: the ship (README 5.6): ship_matrix, d = ship.pos - cam_eye as the translation, composed with the view rotation; render_shp(&ship_shp, &ship_store). */
void draw_ship(void);

/* Chapter 33's scene picture (README 5.7): not called in this chapter (the track alone fills the primitive buffer), kept for later chapters.
   The game picture of Chapter 33: render_begin(); then for every node of the list: cull_test with the camera
   (cam_eye, scene_cull_radius); set o->visible; draw the visible ones with draw_object. submitted_objects = how many were drawn. */
void draw_scene(void);

/* Draw one visible object. `d` is its position relative to the eye (cull_test's output). Composes the object's rotation and scale
   with the camera's rotation, puts d through it as the translation, loads the result into the GTE and calls render_shp. */
void draw_object(const Object *o, const VECTOR *d);

#endif
