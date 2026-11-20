#include <psxgpu.h>
#include "ot.h"

#define G16 { [0 ... GUARD_SIZE - 1] = GUARD_BYTE }

/* Given: the two frames, each with its sentinel bytes after the primitive buffer. */
OtFrame ot_frames[2] = {
	{ .guard = G16 },
	{ .guard = G16 },
};

/* TODO: which frame is being built (0 or 1), and how many bytes of its
   primitive buffer are used. */

void ot_begin_frame(void)
{
	(void) *(volatile uint8_t *) ot_frames;   /* keeps ot_frames linked until you use it */
	/* TODO (README 7.2): ClearOTagR on this frame's table; empty its primitive buffer. */
}

void *ot_alloc(size_t size)
{
	(void) size;
	/* TODO (README 7.2): bump allocator with the overflow guard; NULL when it does not fit. */
	return NULL;
}

void ot_add(void *prim, int depth)
{
	(void) prim; (void) depth;
	/* TODO (README 7.2): clamp depth, then addPrim into this frame's table. */
}

void ot_draw(void)
{
	/* TODO (README 7.2): DrawOTag from the right entry, then switch to the other frame. */
}
