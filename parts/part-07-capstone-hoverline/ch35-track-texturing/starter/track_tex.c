#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "cdrom.h"
#include "tim.h"
#include "tpk.h"
#include "track_tex.h"

const TileSlot vram_layout[LAYOUT_TILE_COUNT] = LAYOUT_INIT;

int32_t tex_status = TT_ERR_READ;
int32_t track_tex_count;
Tex     track_tex[LAYOUT_TILE_COUNT];

int track_tex_load(const char *path)
{
	/* TODO (README 7.3, step 4). The contract is in track_tex.h. Chapter 29 gave you cd_load_file, Chapter 31 tpk_parse and tpk_unpack;
	   tim_parse describes each tile; tim_upload_at copies it to a place of your choosing. Until you write it, no tile is loaded
	   and every face is drawn flat, as in Chapter 34. */
	(void) path;
	return tex_status = TT_ERR_READ;
}

int track_face_uv(const TrkFace *f, uint8_t uv[8], uint16_t *tpage, uint16_t *clut)
{
	/* TODO (README 7.3, step 5). The contract is in track_tex.h. Until you write it, every face is flat. */
	(void) f;
	(void) uv;
	(void) tpage;
	(void) clut;
	return 0;
}
