/* Chapter 21 starter: everything in one file (Chapters 19 and 20 pasted together).
   Your job: split it into the psxe library (README section 7). */
#include <stdint.h>
#include <stddef.h>
#include <psxgpu.h>

#define SCREEN_W 320
#define SCREEN_H 240
#define OT_LENGTH     64
#define PRIM_BUF_SIZE 2048
#define GUARD_SIZE    16
#define GUARD_BYTE    0xA5

/* ---- display (Chapter 19) ---- */
static DISPENV disp[2];
static DRAWENV draw[2];
static int     back;

void display_init(void)
{
	ResetGraph(0);

	/* Buffer 0 at VRAM (0,0), buffer 1 at (0,240). */
	SetDefDispEnv(&disp[0], 0, 0,        SCREEN_W, SCREEN_H);
	SetDefDrawEnv(&draw[0], 0, 0,        SCREEN_W, SCREEN_H);
	SetDefDispEnv(&disp[1], 0, SCREEN_H, SCREEN_W, SCREEN_H);
	SetDefDrawEnv(&draw[1], 0, SCREEN_H, SCREEN_W, SCREEN_H);
	draw[0].isbg = 1;
	draw[1].isbg = 1;

	back = 0;
	PutDispEnv(&disp[1]);   /* show the (empty) other buffer while we draw into 0 */
	SetDispMask(1);
}

void display_clear(uint8_t r, uint8_t g, uint8_t b)
{
	setRGB0(&draw[back], r, g, b);
	PutDrawEnv(&draw[back]);
}

__attribute__((noinline)) void display_swap(void)   /* noinline: the verifier hooks this symbol; drop it once the code is in a library */
{
	DrawSync(0);
	VSync(0);
	PutDispEnv(&disp[back]);
	back ^= 1;
}

/* ---- ordering table (Chapter 20) ---- */
typedef struct {
	uint32_t ot[OT_LENGTH];
	uint8_t  prim[PRIM_BUF_SIZE];
	uint8_t  guard[GUARD_SIZE];
} OtFrame;

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

void ot_add(void *prim, int depth)
{
	if (depth < 0)
		depth = 0;
	if (depth > OT_LENGTH - 1)
		depth = OT_LENGTH - 1;
	addPrim(&ot_frames[cur].ot[depth], prim);
}

void ot_draw(void)
{
	/* ClearOTagR links entry i to entry i-1: start at the LAST entry. */
	DrawOTag(&ot_frames[cur].ot[OT_LENGTH - 1]);
	cur ^= 1;
}

/* ---- the program ---- */
#define NUM_QUADS 16

typedef struct {
	int16_t x, y, w, h;
	uint8_t r, g, b, pad;
	int32_t depth;          /* 0 = nearest .. OT_LENGTH-1 = farthest */
} Quad;                     /* 16 bytes */

/* State the verifier reads and patches. Do not change the initial values. */
Quad scene[NUM_QUADS] = {
	{   8,   8, 90, 70,  25, 255, 255, 0, 10 },
	{  80,   4, 90, 70,  33,  15, 153, 0, 54 },
	{ 136,  10, 90, 70, 140,  25, 255, 0,  6 },
	{ 209,   6, 90, 70, 153,  15, 119, 0, 50 },
	{  13,  53, 90, 70,  25, 255, 169, 0, 18 },
	{  71,  59, 90, 70,  15, 153,  50, 0,  2 },
	{ 142,  56, 90, 70, 226, 255,  25, 0, 42 },
	{ 206,  60, 90, 70, 153,  15,  15, 0, 34 },
	{   6, 106, 90, 70, 255, 198,  25, 0, 58 },
	{  78, 102, 90, 70,  15, 101, 153, 0, 22 },
	{ 140, 109, 90, 70,  54, 255,  25, 0, 46 },
	{ 201, 104, 90, 70, 153,  67,  15, 0, 14 },
	{  11, 160, 90, 70, 226,  25, 255, 0, 26 },
	{  74, 156, 90, 70,  15,  50, 153, 0, 30 },
	{ 136, 153, 90, 70, 255,  25, 112, 0, 38 },
	{ 212, 158, 90, 70,  84, 153,  15, 0, 62 },
};
volatile uint32_t frame_no    = 0;   /* frames drawn so far */
volatile uint32_t copies      = 1;   /* times the whole scene is submitted per frame */
volatile uint32_t depth_step  = 1;   /* added to every depth after each frame */

static void draw_scene(void)
{
	uint32_t n = copies;

	for (uint32_t c = 0; c < n; c++) {
		for (int i = 0; i < NUM_QUADS; i++) {
			const Quad *q = &scene[i];
			POLY_F4 *p = (POLY_F4 *) ot_alloc(sizeof(POLY_F4));

			if (!p)
				return;
			setPolyF4(p);
			setXYWH(p, q->x, q->y, q->w, q->h);
			setRGB0(p, q->r, q->g, q->b);
			ot_add(p, q->depth);
		}
	}
}
static void advance(void)
{
	frame_no++;
	for (int i = 0; i < NUM_QUADS; i++)
		scene[i].depth = (int32_t) (((uint32_t) scene[i].depth + depth_step) % OT_LENGTH);
}

int main(void)
{
	display_init();

	for (;;) {
		display_clear(24, 24, 32);
		ot_begin_frame();
		draw_scene();
		ot_draw();
		display_swap();
		advance();
	}
	return 0;
}
