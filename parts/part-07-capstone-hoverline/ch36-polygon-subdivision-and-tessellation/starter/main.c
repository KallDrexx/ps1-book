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
#include "game.h"

#define TPK_PATH   "\\DATA\\PROPS.TPK;1"      /* the textures of the scenery shapes, shared by all of them */
#define SCENE_PATH "\\DATA\\SCENE.BIN;1"
#define TRACK_PATH "\\DATA\\TRACK.TRK;1"
#define TRACK_TPK_PATH "\\DATA\\TRACK.TPK;1"   /* the eight track tiles (Chapter 35) */

/* State the verifier reads and patches. Do not change the names or types. */
TpkTextures store;                   /* PROPS.TPK's textures */
int32_t     load_status;             /* 0 = loaded; 100 = CdInit failed; 1 = tpk_load failed; 2 = the scene file or scene_load failed
                                        (scene_status has the code); 3 = the logo failed; 4 = TRACK.TRK could not be read or
                                        parsed (track_status has the code) */
int32_t     tpk_status;              /* what tpk_load returned */

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
	}
}

int main(void)
{
	display_init();
	input_init();
	InitGeom();
	gte_SetGeomOffset(SCREEN_W / 2, SCREEN_H / 2);
	gte_SetGeomScreen(proj_h);
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
	__asm__ volatile("" :: "r"(&cam_max), "r"(&view_mtx), "r"(&prims_submitted), "r"(&prims_dropped),
	                 "r"(obj_insert), "r"(obj_append), "r"(obj_remove), "r"(obj_count), "r"(cull_test), "r"(scene_load),
	                 "r"(scene_unload));

	for (;;) {
		input_update();
		game_update();
		game_draw();
		frame_no++;
		frame_done();
	}
	return 0;
}
