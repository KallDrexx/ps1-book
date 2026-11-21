#include <stdint.h>
#include <stdlib.h>
#include <psxgpu.h>
#include <psxgte.h>
#include <inline_c.h>
#include <psxe/display.h>
#include <psxe/ot.h>
#include <psxe/input.h>
#include "cdrom.h"
#include "tim.h"
#include "tpk.h"
#include "shp.h"
#include "object.h"
#include "scene.h"
#include "cull.h"
#include "camera.h"
#include "render.h"
#include "track.h"
#include "track_render.h"
#include "track_tex.h"
#include "subdiv.h"
#include "title.h"
#include "ship.h"
#include "track_vis.h"
#include "audio.h"
#include "collide.h"
#include "handling.h"
#include "race.h"
#include "trackload.h"
#include "game.h"

#define TPK_PATH   "\\DATA\\PROPS.TPK;1"      /* the textures of the scenery shapes, shared by all of them */
#define SCENE_PATH "\\DATA\\SCENE.BIN;1"
#define TRACK_PATH "\\DATA\\TRACK.TRK;1"
#define TRACK_TPK_PATH "\\DATA\\TRACK.TPK;1"   /* the eight track tiles (Chapter 35) */
#define SHIP_PATH  "\\DATA\\SHIP.SHP;1"       /* the player's ship (Chapter 32's model) ... */
#define SHIP_TPK_PATH "\\DATA\\SHIP.TPK;1"    /* ... and its three textures */

/* State the verifier reads and patches. Do not change the names or types. */
TpkTextures store;                   /* PROPS.TPK's textures */
int32_t     load_status;             /* 0 = loaded; 100 = CdInit failed; 1 = tpk_load failed; 2 = the scene file or scene_load failed
                                        (scene_status has the code); 3 = the logo failed; 4 = TRACK.TRK could not be read or
                                        parsed (track_status has the code); 5 = SHIP.TPK or SHIP.SHP could not be loaded */
int32_t     tpk_status;              /* what tpk_load returned */
Shp         ship_shp;                /* Chapter 37: SHIP.SHP, parsed in place; its file image is kept */
TpkTextures ship_store;              /* SHIP.TPK */
int32_t     video_mode;              /* 0 = NTSC, 1 = PAL: what the console is (README 5.4); decide it once at the start of main */
int32_t     dt_scale = DT_NTSC;      /* the time-step factor of video_mode (README 5.7) */

__attribute__((noinline)) void frame_done(void) { __asm__ volatile("" ::: "memory"); }

static void load_assets(void)
{
	uint32_t size;
	void *file;

	if (!cd_init()) {
		load_status = 100;
		return;
	}
	if (title_load()) {
		load_status = 3;
		return;
	}
	tpk_status = tpk_load(TPK_PATH, &store);
	if (tpk_status) {
		load_status = 1;
		return;
	}
	tpk_free_raw(&store);                /* the pixels are in VRAM; tex[] stays valid */
	track_tex_load(TRACK_TPK_PATH);      /* tex_status has the result; a failure is NOT fatal: the faces are then drawn flat (Chapter 34) */
	file = cd_load_file(SCENE_PATH, &size);
	if (!file) {
		scene_status = SCENE_ERR_READ;
		load_status = 2;
		return;
	}
	if (scene_load(file, size))          /* the scene keeps nothing of the file image: the objects are copies */
		load_status = 2;
	free(file);
	if (load_status)
		return;
	file = cd_load_file(TRACK_PATH, &size);
	if (!file) {
		track_status = TRK_ERR_READ;
		load_status = 4;
		return;
	}
	track_status = track_parse(file, size, &track);   /* the track uses the file image in place: it is NOT freed */
	if (track_status) {
		free(file);
		load_status = 4;
		return;
	}
	track_image = file;                  /* Chapter 40: kept, so track_switch can free it (README 5.9) */
	track_selected = 1;
	if (tpk_load(SHIP_TPK_PATH, &ship_store)) {
		load_status = 5;
		return;
	}
	tpk_free_raw(&ship_store);
	file = cd_load_file(SHIP_PATH, &size);
	if (!file || shp_parse(file, size, &ship_shp) || ship_shp.texture_count > (uint32_t) ship_store.count)
		load_status = 5;              /* the ship's image is kept: ship_shp points into it */
	if (load_status)
		return;
	audio_init();                        /* Chapter 39: the five samples go to SPU RAM; a failure is NOT fatal (audio_status has the code): the game runs silent */
	audio_music_start();                 /* the CD track plays from the title on */
}

int main(void)
{
	/* TODO (README 5.4): video_mode is 0 (NTSC) until you ask the console what it is. */
	dt_scale = video_mode ? DT_PAL : DT_NTSC;
	display_init_mode(video_mode != 0);
	input_init();
	InitGeom();
	gte_SetGeomOffset(SCREEN_W / 2, SCREEN_H / 2);
	gte_SetGeomScreen(proj_h);
	FntLoad(960, 0);                     /* the SDK font: VRAM x 960..991, y 0..31 and its CLUT below (README 5.7) */
	load_assets();
	/* Keeps the state above linked in even where your code does not read it. Leave this line in. */
	__asm__ volatile("" :: "r"(&game_state), "r"(&state_changes), "r"(&submitted_objects), "r"(&proj_h), "r"(&store),
	                 "r"(&load_status), "r"(&tpk_status), "r"(&object_head), "r"(&object_count), "r"(object_pool),
	                 "r"(scene_shapes), "r"(&scene_shape_count), "r"(&scene_cull_radius), "r"(&scene_status),
	                 "r"(&scene_shp_status), "r"(&cam_eye), "r"(&cam_yaw), "r"(&cam_target), "r"(&cam_up), "r"(&cam_speed),
	                 "r"(&cam_turn), "r"(&cam_min));
	__asm__ volatile("" :: "r"(&track), "r"(&track_status), "r"(&wire_mode), "r"(&track_stats), "r"(trk_rel), "r"(trk_sxy), "r"(trk_sz),
	                 "r"(trk_vstate), "r"(track_parse), "r"(track_vertex), "r"(track_face), "r"(track_section), "r"(track_colour),
	                 "r"(track_draw));
	__asm__ volatile("" :: "r"(&tex_status), "r"(&track_tex_count), "r"(track_tex), "r"(vram_layout), "r"(track_tex_load),
	                 "r"(track_face_uv));
	__asm__ volatile("" :: "r"(&subdiv_stats), "r"(&subdiv_debug), "r"(&subdiv_reserve), "r"(subdiv_level), "r"(subdiv_section_level),
	                 "r"(subdiv_budget_level), "r"(subdiv_mid), "r"(subdiv_project), "r"(subdiv_face), "r"(track_emit));
	__asm__ volatile("" :: "r"(&ship), "r"(&ship_cfg), "r"(&video_mode), "r"(&dt_scale), "r"(&frame_ticks), "r"(&ship_ticks),
	                 "r"(&subdiv_enabled), "r"(ship_update), "r"(ship_place), "r"(ship_forward), "r"(ship_matrix), "r"(heading_angle),
	                 "r"(pitch_angle), "r"(chase_camera_update), "r"(draw_ship), "r"(&cam_max), "r"(&view_mtx), "r"(&prims_submitted), "r"(&prims_dropped),
	                 "r"(obj_insert), "r"(obj_append), "r"(obj_remove), "r"(obj_count), "r"(cull_test), "r"(scene_load),
	                 "r"(scene_unload));

	__asm__ volatile("" :: "r"(&ship_section), "r"(&prims_this_frame), "r"(&vis_ahead), "r"(&vis_behind), "r"(&vis_mode), "r"(&vis_lost),
	                 "r"(&vis_brute_runs), "r"(&vis_first), "r"(&vis_count), "r"(&vis_list_done), "r"(vis_text), "r"(track_nearest_brute),
	                 "r"(track_nearest_update), "r"(track_window), "r"(track_draw_list), "r"(track_draw_visible), "r"(vis_readout_format));

	__asm__ volatile("" :: "r"(audio_samples), "r"(&audio_cfg), "r"(&audio_stats), "r"(&audio_status), "r"(audio_pitch_for_speed),
	                 "r"(audio_voice_alloc), "r"(audio_play_sfx), "r"(audio_event), "r"(audio_lateral), "r"(audio_section_boost),
	                 "r"(audio_upload_sample), "r"(audio_engine_update));

	__asm__ volatile("" :: "r"(&collide_cfg), "r"(&collide_state), "r"(collide_text), "r"(&track_selected), "r"(&track_image), "r"(collide_edges),
	                 "r"(collide_edge_dist), "r"(collide_section), "r"(collide_ground), "r"(collide_floor_face), "r"(collide_ship),
	                 "r"(collide_respawn), "r"(collide_format), "r"(collide_reset), "r"(track_switch), "r"(collide_heading), "r"(collide_isqrt));

	__asm__ volatile("" :: "r"(&handling_cfg), "r"(handling_drag), "r"(handling_skid), "r"(handling_pitch_target), "r"(handling_auto_pitch),
	                 "r"(&race), "r"(&race_cfg), "r"(&race_best), "r"(race_text), "r"(race_section_step), "r"(race_tick),
	                 "r"(race_countdown_tick), "r"(race_format_time), "r"(race_format_text), "r"(race_reset), "r"(race_hz));

	for (;;) {
		input_update();
		game_update();
		audio_update();
		game_draw();
		frame_no++;
		frame_done();
	}
	return 0;
}
