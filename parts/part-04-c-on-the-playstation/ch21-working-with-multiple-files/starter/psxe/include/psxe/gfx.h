/* TODO: add an include guard (README 5.3) */
#include <stdint.h>

/* Draw a flat-coloured rectangle: top-left (x, y), size w by h, colour r g b, at ordering-table
   `depth` (0 = nearest). Takes its packet from the current frame (ot_alloc) and links it (ot_add).
   Returns 0 on success, -1 when the frame's primitive buffer is full (nothing is drawn). */
int gfx_quad_f4(int16_t x, int16_t y, int16_t w, int16_t h,
                uint8_t r, uint8_t g, uint8_t b, int depth);

