#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "cdrom.h"
#include "tpk.h"
#include "scene.h"

/* Chapter 33, part 3 of 4: SCENE.BIN into a list (README 7.3 step 4). scene.h is the contract: the codes, the limits, the order of the checks. */

extern TpkTextures store;           /* the texture store (main.c) */

/* The state the verifier reads (given). */
Object     *object_head;
int32_t     object_count;
Object      object_pool[SCENE_MAX_OBJECTS];
SceneShape  scene_shapes[SCENE_MAX_SHAPES];
int32_t     scene_shape_count;
int32_t     scene_cull_radius;
int32_t     scene_status;
int32_t     scene_shp_status;

/* Given: little-endian reads, one byte at a time (the file's fields are not aligned for a wider load). */
static __attribute__((unused)) uint32_t rd16(const uint8_t *p) { return p[0] | (p[1] << 8); }
static __attribute__((unused)) uint32_t rd32(const uint8_t *p) { return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t) p[3] << 24); }

void scene_unload(void)
{
	/* TODO: free every scene_shapes[i].buf, clear the shape table, object_head = NULL, object_count = 0, scene_shape_count = 0. */
}

int scene_load(const void *data, size_t size)
{
	/* TODO: validate (scene.h's order, touching nothing), scene_unload(), load every shape from "\DATA\<name>;1" with cd_load_file + shp_parse,
	   then take one node per object from object_pool and obj_append it. Store the result in scene_status. */
	(void) data;
	(void) size;
	(void) store;
	scene_status = SCENE_ERR_HEADER;
	return scene_status;
}
