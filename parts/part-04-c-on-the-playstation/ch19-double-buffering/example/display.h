#ifndef DISPLAY_H
#define DISPLAY_H

#include <stdint.h>

#define SCREEN_W 320
#define SCREEN_H 240

/* Reset the GPU, set up ONE display/draw environment pair, switch the picture on. */
void display_init(void);

/* Start a frame: set the clear color and queue the clear. */
void display_clear(uint8_t r, uint8_t g, uint8_t b);

/* End a frame: wait for the GPU, then for VBlank. */
void display_swap(void);

#endif
