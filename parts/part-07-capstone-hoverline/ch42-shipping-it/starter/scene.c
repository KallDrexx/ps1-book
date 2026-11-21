#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "cdrom.h"
#include "tpk.h"
#include "scene.h"

extern TpkTextures store;           /* the texture store (main.c) */

Object     *object_head;
int32_t     object_count;
Object      object_pool[SCENE_MAX_OBJECTS];
SceneShape  scene_shapes[SCENE_MAX_SHAPES];
int32_t     scene_shape_count;
int32_t     scene_cull_radius;
int32_t     scene_status;
int32_t     scene_shp_status;

static uint32_t rd16(const uint8_t *p) { return p[0] | (p[1] << 8); }
static uint32_t rd32(const uint8_t *p) { return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t) p[3] << 24); }
static int32_t  rds32(const uint8_t *p) { return (int32_t) rd32(p); }

void scene_unload(void)
{
	for (int i = 0; i < SCENE_MAX_SHAPES; i++) {
		free(scene_shapes[i].buf);
		memset(&scene_shapes[i], 0, sizeof scene_shapes[i]);
	}
	object_head = NULL;
	object_count = 0;
	scene_shape_count = 0;
}

static int name_ok(const uint8_t *n)
{
	int len = 0;

	while (len < 12 && n[len])
		len++;
	if (len == 0 || len == 12)
		return 0;
	for (int i = 0; i < len; i++)
		if (!((n[i] >= 'A' && n[i] <= 'Z') || (n[i] >= '0' && n[i] <= '9') || n[i] == '_' || n[i] == '.'))
			return 0;
	return 1;
}

static int coord_ok(int32_t v) { return v >= -SCENE_MAX_COORD && v <= SCENE_MAX_COORD; }

static int validate(const uint8_t *d, size_t size)
{
	uint32_t shapes, objects, cull;
	uint32_t sh_off, ob_off;

	if ((uintptr_t) d & 3)
		return SCENE_ERR_ALIGN;
	if (size < 4 || memcmp(d, "SCN1", 4) != 0)
		return SCENE_ERR_MAGIC;
	if (size < 0x20 || rd32(d + 4) != size)
		return SCENE_ERR_HEADER;
	shapes = rd16(d + 8);
	objects = rd16(d + 10);
	sh_off = rd32(d + 12);
	ob_off = rd32(d + 16);
	cull = rd32(d + 20);
	if (shapes == 0 || shapes > SCENE_MAX_SHAPES || objects == 0 || objects > SCENE_MAX_OBJECTS)
		return SCENE_ERR_HEADER;
	if (sh_off != 0x20 || ob_off != 0x20 + 16 * shapes || size != ob_off + 24 * objects)    /* 32-bit math is safe: counts are u16 and limited */
		return SCENE_ERR_HEADER;
	if (cull == 0 || cull > SCENE_MAX_CULL)
		return SCENE_ERR_HEADER;
	for (uint32_t i = 0; i < shapes; i++) {
		const uint8_t *s = d + sh_off + 16 * i;
		uint32_t radius = rd32(s + 12);

		if (!name_ok(s))
			return SCENE_ERR_SHAPE;
		if (radius == 0 || radius > SCENE_MAX_RADIUS)
			return SCENE_ERR_SHAPE;
	}
	for (uint32_t i = 0; i < objects; i++) {
		const uint8_t *o = d + ob_off + 24 * i;
		uint32_t scale = rd16(o + 22);

		if (rd16(o) >= shapes)
			return SCENE_ERR_OBJECT;
		if (rd16(o + 2) & ~(uint32_t) OBJ_ALWAYS_DRAW)
			return SCENE_ERR_OBJECT;
		if (scale == 0 || scale > SCENE_MAX_SCALE)
			return SCENE_ERR_OBJECT;
		if (!coord_ok(rds32(o + 4)) || !coord_ok(rds32(o + 8)) || !coord_ok(rds32(o + 12)))
			return SCENE_ERR_OBJECT;
	}
	return SCENE_OK;
}

static int load_shapes(const uint8_t *d, uint32_t shapes)
{
	for (uint32_t i = 0; i < shapes; i++) {
		const uint8_t *s = d + 0x20 + 16 * i;
		SceneShape *sh = &scene_shapes[i];
		char path[32] = "\\DATA\\";
		int code;

		memcpy(sh->name, s, 12);
		sh->radius = (int32_t) rd32(s + 12);
		strcat(path, sh->name);
		strcat(path, ";1");
		scene_shape_count = (int32_t) i + 1;            /* so that scene_unload frees what is loaded so far */
		sh->buf = cd_load_file(path, &sh->size);
		if (!sh->buf)
			return SCENE_ERR_READ;
		code = shp_parse(sh->buf, sh->size, &sh->shp);
		if (code) {
			scene_shp_status = code;
			return SCENE_ERR_SHP;
		}
		if (sh->shp.texture_count > (uint32_t) store.count)
			return SCENE_ERR_STORE;
	}
	return SCENE_OK;
}

static int load(const void *data, size_t size)
{
	const uint8_t *d = data;
	uint32_t shapes, objects, ob_off;
	int code = validate(d, size);

	if (code)
		return code;
	shapes = rd16(d + 8);
	objects = rd16(d + 10);
	ob_off = rd32(d + 16);
	scene_unload();
	scene_shp_status = 0;
	scene_cull_radius = (int32_t) rd32(d + 20);
	code = load_shapes(d, shapes);
	if (code) {
		scene_unload();
		return code;
	}
	for (uint32_t i = 0; i < objects; i++) {
		const uint8_t *o = d + ob_off + 24 * i;
		Object *n = &object_pool[i];

		n->shape = (int32_t) rd16(o);
		n->flags = (int32_t) rd16(o + 2);
		n->x = rds32(o + 4);
		n->y = rds32(o + 8);
		n->z = rds32(o + 12);
		n->rx = (int16_t) rd16(o + 16);
		n->ry = (int16_t) rd16(o + 18);
		n->rz = (int16_t) rd16(o + 20);
		n->scale = (int32_t) rd16(o + 22);
		n->radius = (scene_shapes[n->shape].radius * n->scale) >> 12;
		n->visible = 0;
		obj_append(&object_head, n);                  /* the file's order: node i is entry i */
	}
	object_count = (int32_t) objects;
	return SCENE_OK;
}

int scene_load(const void *data, size_t size)
{
	scene_status = load(data, size);
	return scene_status;
}
