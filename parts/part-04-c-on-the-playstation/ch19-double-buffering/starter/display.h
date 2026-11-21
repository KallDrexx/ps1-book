#ifndef DISPLAY_H
#define DISPLAY_H

#include <stdint.h>

#define SCREEN_W 320
#define SCREEN_H 240

/* Reset the GPU, build the two environment pairs, switch the picture on. */
void display_init(void);

/* Start a frame: set the back buffer's clear color and queue its clear. */
void display_clear(uint8_t r, uint8_t g, uint8_t b);

/* End a frame: wait for the GPU, wait for VBlank, show the buffer just drawn. */
void display_swap(void);

#endif
