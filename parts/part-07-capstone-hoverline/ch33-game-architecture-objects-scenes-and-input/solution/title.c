#include <stdint.h>
#include <stdlib.h>
#include <psxgpu.h>
#include <psxe/display.h>
#include <psxe/ot.h>
#include "cdrom.h"
#include "tim.h"
#include "title.h"

static Tex logo;

int title_load(void)
{
	TimInfo info;
	uint32_t size;
	void *file = cd_load_file(LOGO_PATH, &size);

	if (!file)
		return 1;
	if (!tim_parse(&info, file, size)) {
		free(file);
		return 2;
	}
	tim_upload(&info);                      /* the pixels are copied into VRAM: the file image is not needed any more */
	tex_from_tim(&logo, &info);
	free(file);
	return 0;
}

void title_draw(int32_t frame)
{
	POLY_G4 *bg = ot_alloc(sizeof(POLY_G4));
	POLY_FT4 *lg = ot_alloc(sizeof(POLY_FT4));
	POLY_F4 *bar = (frame & 32) ? NULL : ot_alloc(sizeof(POLY_F4));

	if (bg) {
		setPolyG4(bg);
		setXYWH(bg, 0, 0, SCREEN_W, SCREEN_H);
		setRGB0(bg, 8, 8, 40);
		setRGB1(bg, 8, 8, 40);
		setRGB2(bg, 96, 24, 96);
		setRGB3(bg, 96, 24, 96);
		ot_add(bg, OT_LENGTH - 1);
	}
	if (lg) {
		setPolyFT4(lg);
		setXYWH(lg, LOGO_X, LOGO_Y, 128, 64);
		setUVWH(lg, logo.u, logo.v, 127, 63);       /* the last texel is at +127, +63 */
		setRGB0(lg, 128, 128, 128);                 /* modulation 128 leaves the texels unchanged */
		lg->tpage = logo.tpage;
		lg->clut = logo.clut;
		ot_add(lg, 1);
	}
	if (bar) {
		setPolyF4(bar);
		setXYWH(bar, 112, 172, 96, 10);
		setRGB0(bar, 255, 224, 48);
		ot_add(bar, 0);
	}
}
