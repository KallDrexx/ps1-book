#ifndef GAME_H
#define GAME_H

#include <stdint.h>
#include <psxgte.h>
#include "object.h"
#include "track.h"

/* The states of the game's state machine (README 5.7). The verifier reads game_state.
   TITLE -> COUNTDOWN -> RACE -> RESULTS -> (TITLE | COUNTDOWN). Chapter 40's single STATE_GAME is split in three. */
enum { STATE_TITLE = 0, STATE_COUNTDOWN = 1, STATE_RACE = 2, STATE_RESULTS = 3 };

/* State the verifier reads. */
extern int32_t game_state;           /* STATE_TITLE, STATE_COUNTDOWN, STATE_RACE or STATE_RESULTS */
extern int32_t state_changes;        /* how many times game_state has changed since boot */
extern int32_t submitted_objects;    /* objects drawn in the last game frame (0 in the title) */
extern int32_t proj_h;               /* projection distance h, in pixels */
extern int32_t frame_no;             /* frames completed */
extern int32_t subdiv_enabled;       /* 0 (default): Chapter 36 subdivision off, 1: on (about half the frame rate). R1 toggles it (edge-triggered). Patchable */

#define MAX_TICKS 4                  /* most physics ticks one frame may run */

/* One step of the state machine (README 5.7). Call once per frame, right after input_update.
   First measures the ticks of this frame (given: frame_ticks = VSync(-1) - the last reading, clamped to 1..MAX_TICKS), then by state:
   TITLE      LEFT / RIGHT: track_switch(1) / track_switch(2) (LEFT wins if both are pressed in one frame); START: set_state(STATE_COUNTDOWN).
   COUNTDOWN  START: set_state(STATE_TITLE). Otherwise debug_toggles(), then frame_ticks times: ev = race_countdown_tick(&race, race_hz());
              RACE_BEEP: audio_play_sfx(SMP_BEEP); RACE_GO: audio_play_sfx(SMP_GO), set_state(STATE_RACE) and the rest of this frame's ticks are
              dropped. Then chase_camera_update(&ship). The ship does not move and the pad is not read for steering.
   RACE       START: set_state(STATE_TITLE). Otherwise debug_toggles(), then frame_ticks times, in this order:
                ship_update(&ship, input_buttons(), dt_scale);  collide_ship(&track, &ship);  handling_auto_pitch(&ship, &track, ship_section, dt_scale);
                ship_ticks++;  ev = race_tick(&race, &track, ship_section);
              RACE_FINISH: set_state(STATE_RESULTS), the rest of this frame's ticks are dropped. Else RACE_LAP: audio_play_sfx(SMP_BEEP).
              Then chase_camera_update(&ship) and, while still racing, audio_engine_update(ship.speed).
   RESULTS    START: set_state(STATE_TITLE); CROSS: set_state(STATE_COUNTDOWN) (the restart); debug_toggles(). Nothing else moves.
   Edge-triggered throughout (input_pressed): a held button acts once. set_state (given) counts every change in state_changes and does the entry work. */
void game_update(void);

/* Draw the frame for the current state: display_clear, ot_begin_frame, the state's picture, ot_draw, display_swap.
   TITLE: title_draw and the menu; submitted_objects = 0. COUNTDOWN, RACE, RESULTS: draw_track() and the race text (README 5.8). */
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
