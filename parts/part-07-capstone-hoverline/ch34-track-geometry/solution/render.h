#ifndef RENDER_H
#define RENDER_H

#include <stdint.h>
#include "shp.h"

#define NEAR_Z    128                /* a polygon with a vertex nearer than this (view z) is skipped: its projection is meaningless */
#define OTZ_SHIFT 7                  /* OT slot = OTZ >> 7 (Chapter 25) */

/* State the verifier reads. */
extern int32_t prims_submitted;      /* GPU packets linked this frame */
extern int32_t prims_dropped;        /* polygons that passed culling but found the primitive buffer full this frame */

/* Start a frame's counters (call once per frame, before the first render_shp). */
void render_begin(void);

/* Draw one model with the matrix that is ALREADY loaded in the GTE (object space -> view space): Chapter 32's draw_shp, given.
   Every vertex through RTPS, then per record: NCLIP back-face rule (double-sided records also from behind), the NEAR_Z skip,
   the OT slot from AVSZ3/AVSZ4, the packet from shp_fill with the texture from `store`. When ot_alloc says the buffer is full the
   polygon is counted in prims_dropped, and so is every later one this frame. Returns the packets linked. */
int render_shp(const Shp *shp);

#endif
