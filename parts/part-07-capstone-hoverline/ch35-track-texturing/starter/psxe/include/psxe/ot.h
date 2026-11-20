#ifndef PSXE_OT_H
#define PSXE_OT_H

#include <stddef.h>
#include <stdint.h>

#define OT_LENGTH     64      /* depth levels: 0 (nearest) .. OT_LENGTH-1 (farthest) */
#define PRIM_BUF_SIZE 32768   /* bytes of primitives per frame (Chapter 34: up to 31360 with outlines; Chapter 35: 40-byte textured quads, up to 40320; Chapters 20-33 used 2048) */
#define GUARD_SIZE    16      /* sentinel bytes after each primitive buffer */
#define GUARD_BYTE    0xA5

/* Everything one frame needs. There are two, one per display buffer. */
typedef struct {
	uint32_t ot[OT_LENGTH];
	uint8_t  prim[PRIM_BUF_SIZE];
	uint8_t  guard[GUARD_SIZE];     /* must still be all GUARD_BYTE after any frame */
} OtFrame;

extern OtFrame ot_frames[2];

/* Start a frame: clear this frame's ordering table (reverse) and empty its primitive buffer. */
void ot_begin_frame(void);

/* Take `size` bytes (rounded up to a multiple of 4) from the primitive buffer.
   Returns NULL, and writes nothing, when they do not fit. */
void *ot_alloc(size_t size);

/* Link a primitive into the table at `depth` (0 = nearest; clamped to 0..OT_LENGTH-1). */
void ot_add(void *prim, int depth);

/* Send the table to the GPU (DrawOTag, returns at once) and switch to the other frame. */
void ot_draw(void);

#endif
