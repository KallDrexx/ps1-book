#include <stdint.h>
#ifndef TITLE_H
#define TITLE_H

#define LOGO_PATH "\\DATA\\LOGO.TIM;1"
#define LOGO_X 96                    /* the logo is drawn 1:1, 128 x 64 pixels, with its top-left corner here */
#define LOGO_Y 56

/* Load LOGO.TIM from the disc into VRAM. Returns 0 on success, nonzero if the file is missing or not a usable TIM. */
int title_load(void);

/* Queue the title screen: a gradient backdrop, the logo, and a blinking "press start" bar (on for 32 frames, off for 32). Given. */
void title_draw(int32_t frame);

#endif
