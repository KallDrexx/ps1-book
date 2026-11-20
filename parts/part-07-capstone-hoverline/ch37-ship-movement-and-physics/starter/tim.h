#ifndef TIM_H
#define TIM_H

#include <stdint.h>

/* What tim_parse learns from a TIM file (Appendix E.3). All VRAM coordinates are exactly as the file's blocks say:
   x and w in 16-bit VRAM units, y and h in lines. The data pointers point INTO the file image (nothing is copied). */
typedef struct {
	int32_t bpp;                     /* 4, 8 or 16 */
	int32_t clut_x, clut_y;          /* the CLUT's rectangle; clut_w = 0 means "no CLUT" (16 bpp) */
	int32_t clut_w, clut_h;
	int32_t img_x, img_y;            /* the image's rectangle */
	int32_t img_w, img_h;
	const uint32_t *clut_data;       /* the CLUT block's pixels, or NULL */
	const uint32_t *img_data;        /* the image block's pixels */
} TimInfo;

/* Everything a polygon needs to use one texture. u, v, w, h are in TEXELS: (u, v) is the top-left texel
   of the image inside its texture page, w x h its size. */
typedef struct {
	uint16_t tpage;                  /* the polygon's texture-page word (abr = 0: opaque) */
	uint16_t clut;                   /* the polygon's CLUT word; 0 for 16 bpp */
	uint16_t u, v;
	uint16_t w, h;
} Tex;

/* Validate a TIM image and describe it. Returns 1 and fills *t, or returns 0 and leaves *t untouched. */
int tim_parse(TimInfo *t, const void *data, uint32_t size);

/* Copy the CLUT (if any) and the image into VRAM, at the rectangles *t holds, and wait until the GPU is done. */
void tim_upload(const TimInfo *t);

/* Like tim_upload, but to a place of your choosing: the image's top-left corner goes to (img_x, img_y) and the CLUT's to
   (clut_x, clut_y) instead of the rectangles the TIM names (sizes unchanged; the CLUT is ignored for a 16-bpp image).
   This is how a program RELOCATES a tile: the pixels do not change, only where they are copied. Chapter 35. */
void tim_upload_at(const TimInfo *t, int img_x, int img_y, int clut_x, int clut_y);

/* Work out the texture-page word, CLUT word and the texel origin and size for the image *t describes. */
void tex_from_tim(Tex *tex, const TimInfo *t);

#endif
