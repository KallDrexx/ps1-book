#include <stdint.h>
#include <psxgpu.h>
#include "tim.h"

/* TODO (README 7.3): read little-endian 16- and 32-bit values from a byte pointer, one byte at a time. */

/* TODO: tim_parse, the checks of README 5.4, in that order. Fill *t only when the whole image has passed;
   otherwise return 0 and leave *t untouched. */
int tim_parse(TimInfo *t, const void *data, uint32_t size)
{
	(void) t; (void) data; (void) size;
	return 0;
}

/* TODO: tim_upload: LoadImage the CLUT (if there is one), then the image, each to the rectangle the TIM names; DrawSync(0). */
void tim_upload(const TimInfo *t)
{
	(void) t;
}

/* TODO: tex_from_tim: the tpage word, the CLUT word and the texel origin and size (README 5.2 and 5.3). */
void tex_from_tim(Tex *tex, const TimInfo *t)
{
	(void) tex; (void) t;
}
