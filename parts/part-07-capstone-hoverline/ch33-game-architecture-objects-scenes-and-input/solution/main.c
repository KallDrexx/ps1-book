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
#include "title.h"
#include "game.h"

#define TPK_PATH   "\\DATA\\PROPS.TPK;1"      /* the textures of the scenery shapes, shared by all of them */
#define SCENE_PATH "\\DATA\\SCENE.BIN;1"

/* State the verifier reads and patches. Do not change the names or types. */
TpkTextures store;                   /* PROPS.TPK's textures */
int32_t     load_status;             /* 0 = loaded; 100 = CdInit failed; 1 = tpk_load failed; 2 = the scene file or scene_load failed
                                        (scene_status has the code); 3 = the logo failed */
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
	file = cd_load_file(SCENE_PATH, &size);
	if (!file) {
		scene_status = SCENE_ERR_READ;
		load_status = 2;
		return;
	}
	if (scene_load(file, size))          /* the scene keeps nothing of the file image: the objects are copies */
		load_status = 2;
	free(file);
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
