#ifndef SCENE_H
#define SCENE_H

#include <stddef.h>
#include <stdint.h>
#include "object.h"
#include "shp.h"

/* Return codes of scene_load. 0 is success; every failure is negative. */
#define SCENE_OK          0
#define SCENE_ERR_READ   -1   /* a shape's .SHP could not be read from the disc */
#define SCENE_ERR_ALIGN  -2   /* the image is not 4-byte aligned */
#define SCENE_ERR_MAGIC  -3   /* fewer than 4 bytes, or the first four are not "SCN1" */
#define SCENE_ERR_HEADER -4   /* header inconsistent with itself, with the file size or with the limits below */
#define SCENE_ERR_SHAPE  -5   /* a shape-table entry is bad: name or radius */
#define SCENE_ERR_OBJECT -6   /* an object entry is bad: shape index, flags, scale or position */
#define SCENE_ERR_SHP    -7   /* a shape's .SHP failed shp_parse (its code is in scene_shp_status) */
#define SCENE_ERR_STORE  -8   /* a shape needs more textures than the texture store holds */

/* The program's limits (they are what keeps the arithmetic of cull.h safe). */
#define SCENE_MAX_SHAPES        16
#define SCENE_MAX_OBJECTS      128
#define SCENE_MAX_CULL       20000      /* cull_radius */
#define SCENE_MAX_RADIUS      6000      /* a shape's radius */
#define SCENE_MAX_SCALE       8192      /* 2.0 in 4.12 */
#define SCENE_MAX_COORD    1000000      /* |x|, |y|, |z| of an object */

/* A model of the scene's shape table, loaded from disc. */
typedef struct {
	char     name[16];            /* the table's name, NUL-padded: "PYLON.SHP" */
	int32_t  radius;              /* the table's radius */
	void    *buf;                 /* the file image (malloc'ed); shp points into it */
	uint32_t size;
	Shp      shp;                 /* parsed with shp_parse */
} SceneShape;
_Static_assert(sizeof(SceneShape) == 100, "the verifier steps through scene_shapes in 100-byte strides: do not change SceneShape");

/* State the verifier reads. Do not rename. */
extern Object      *object_head;                          /* the first node of the scene's list, NULL when no scene is loaded */
extern int32_t      object_count;                         /* nodes in that list */
extern Object       object_pool[SCENE_MAX_OBJECTS];       /* the nodes: scene_load takes them from here, in file order */
extern SceneShape   scene_shapes[SCENE_MAX_SHAPES];
extern int32_t      scene_shape_count;
extern int32_t      scene_cull_radius;                    /* from the file */
extern int32_t      scene_status;                         /* what the last scene_load returned */
extern int32_t      scene_shp_status;                     /* the shp_parse code behind SCENE_ERR_SHP */

/* Load a SCENE.BIN image of exactly `size` bytes (Appendix E.9) and the shapes it names.
   Validation comes first and touches nothing; checks in this order, returning at the first failure:
     SCENE_ERR_ALIGN   `data` is not a multiple of 4;
     SCENE_ERR_MAGIC   size < 4, or no "SCN1";
     SCENE_ERR_HEADER  size < 0x20; file_size != size; shape_count 0 or above SCENE_MAX_SHAPES; object_count 0 or above SCENE_MAX_OBJECTS;
                       shapes_offset != 0x20; objects_offset != 0x20 + 16 * shape_count; size != objects_offset + 24 * object_count;
                       cull_radius 0 or above SCENE_MAX_CULL;
     SCENE_ERR_SHAPE   walking the shape table: a name with no NUL in its 12 bytes, an empty name, or a character outside A-Z 0-9 _ .;
                       a radius of 0 or above SCENE_MAX_RADIUS;
     SCENE_ERR_OBJECT  walking the object table: shape >= shape_count; flags with a bit other than bit 0; scale 0 or above SCENE_MAX_SCALE;
                       a position coordinate below -SCENE_MAX_COORD or above SCENE_MAX_COORD. (Per object, in that order.)
   Then it discards any scene already loaded (scene_unload), reads and parses every shape of the table from "\DATA\<name>;1":
     SCENE_ERR_READ    cd_load_file failed;
     SCENE_ERR_SHP     shp_parse failed (scene_shp_status = its code);
     SCENE_ERR_STORE   shp.texture_count > store.count.
   On success: object_head is the first of object_count nodes in the FILE's order (node i = file entry i), each with visible = 0 and
   radius = shape radius * scale >> 12; scene_cull_radius is the file's. On any failure after the validation the scene is left empty.
   The result is also stored in scene_status. */
int scene_load(const void *data, size_t size);

/* Free the shapes' file images and empty the list: object_head NULL, object_count 0, scene_shape_count 0. */
void scene_unload(void);

#endif
