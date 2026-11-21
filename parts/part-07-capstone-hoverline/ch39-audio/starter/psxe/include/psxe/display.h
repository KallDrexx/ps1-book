#ifndef PSXE_DISPLAY_H
#define PSXE_DISPLAY_H

#include <stdint.h>

#define SCREEN_W 320
#define SCREEN_H 240

/* Reset the GPU, build the two environment pairs, switch the picture on. */
void display_init(void);

/* The same, but first selects the video standard: pal = 0 NTSC (60 Hz), 1 PAL (50 Hz): GP1(08h) bit 3 (Chapter 37). */
void display_init_mode(int pal);

/* Start a frame: set the back buffer's clear colour and queue its clear. */
void display_clear(uint8_t r, uint8_t g, uint8_t b);

/* End a frame: wait for the GPU, wait for VBlank, show the buffer just drawn. */
void display_swap(void);

#endif
