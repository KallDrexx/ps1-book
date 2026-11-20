#ifndef CULL_H
#define CULL_H

#include <stdint.h>
#include <psxgte.h>
#include "object.h"

/* The GTE takes 16-bit vertex and translation inputs, so an object more than this far from the eye on ANY axis cannot be
   transformed. It is also what makes the squared sum safe: 3 * 32000^2 = 3.07e9 fits in a uint32_t. */
#define DRAW_LIMIT 32000

/* Should `o` be drawn for a camera at `eye`? Always fills *d = (o->x - eye->vx, o->y - eye->vy, o->z - eye->vz), in s32.
   The rule, in this order (README 5.6):
     1. any |d| component above DRAW_LIMIT          -> 0   (even for OBJ_ALWAYS_DRAW)
     2. OBJ_ALWAYS_DRAW set                          -> 1
     3. dx^2 + dy^2 + dz^2 <= (cull_radius + o->radius)^2   -> 1, else 0   (u32 arithmetic; every term is exact after step 1)
   Preconditions: the positions and the eye are within +-2,000,000 (so d fits in s32); cull_radius + o->radius <= DRAW_LIMIT. */
int cull_test(const Object *o, const VECTOR *eye, int32_t cull_radius, VECTOR *d);

#endif
