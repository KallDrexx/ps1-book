#include <psxgpu.h>
#include <psxe/ot.h>

#define G16 { [0 ... GUARD_SIZE - 1] = GUARD_BYTE }

OtFrame ot_frames[2] = {
	{ .guard = G16 },
	{ .guard = G16 },
};

static int    cur;     /* frame being built */
static size_t used;    /* bytes taken from ot_frames[cur].prim */

void ot_begin_frame(void)
{
	ClearOTagR(ot_frames[cur].ot, OT_LENGTH);
	used = 0;
}

void *ot_alloc(size_t size)
{
	void *p;

	size = (size + 3) & ~(size_t) 3;
	if (size > PRIM_BUF_SIZE - used)
		return NULL;
	p = &ot_frames[cur].prim[used];
	used += size;
	return p;
}

size_t ot_bytes_left(void)
{
	return PRIM_BUF_SIZE - used;
}

static int clamp_depth(int depth)
{
	if (depth < 0)
		return 0;
	if (depth > OT_LENGTH - 1)
		return OT_LENGTH - 1;
	return depth;
}

void ot_add(void *prim, int depth)
{
	addPrim(&ot_frames[cur].ot[clamp_depth(depth)], prim);
}

void ot_draw(void)
{
	/* ClearOTagR links entry i to entry i-1: start at the LAST entry. */
	DrawOTag(&ot_frames[cur].ot[OT_LENGTH - 1]);
	cur ^= 1;
}
