#include <stdint.h>
#include <stdio.h>
#include <psxgpu.h>
#include <psxgte.h>
#include <inline_c.h>
#include <psxe/display.h>
#include <psxe/ot.h>
#include <psxe/gfx.h>

#define CX (SCREEN_W / 2)
#define CY (SCREEN_H / 2)
#define N_CUBES 64

/* One cube of the field: where it is, how it is turned, how fast it spins, how big it is. Ten int32 words, in this order. */
typedef struct {
	int32_t x, y, z;          /* center, world units (the camera adds cam.vz to z) */
	int32_t ax, ay, az;       /* angles about X, Y, Z: 4096 = one turn, kept in 0..4095 */
	int32_t sx, sy, sz;       /* added to the angles every frame (may be negative) */
	int32_t size;             /* half the cube's edge, units */
} Cube;

/* State the verifier reads and patches. Do not change the layout, the order or the initial values. */

/* An 8 x 8 grid: cube i is in column i & 7, row i >> 3. */
Cube cubes[N_CUBES] = {
	{ -4032, -3136,    0,   100,  300,    0,   16,  24, -18,  280 },
	{ -2880, -3136,  256,   161,  397,   29,   21,  31,   0,  280 },
	{ -1728, -3136,  512,   222,  494,   58,   26,  38,  18,  280 },
	{  -576, -3136,  768,   283,  591,   87,   31,  45, -18,  280 },
	{   576, -3136,    0,   344,  688,  116,   36,  52,   0,  280 },
	{  1728, -3136,  256,   405,  785,  145,   41,  24,  18,  280 },
	{  2880, -3136,  512,   466,  882,  174,   46,  31, -18,  280 },
	{  4032, -3136,  768,   527,  979,  203,   16,  38,   0,  280 },
	{ -4032, -2240,  512,   588, 1076,  232,   21,  45,  18,  280 },
	{ -2880, -2240,  768,   649, 1173,  261,   26,  52, -18,  280 },
	{ -1728, -2240,    0,   710, 1270,  290,   31,  24,   0,  280 },
	{  -576, -2240,  256,   771, 1367,  319,   36,  31,  18,  280 },
	{   576, -2240,  512,   832, 1464,  348,   41,  38, -18,  280 },
	{  1728, -2240,  768,   893, 1561,  377,   46,  45,   0,  280 },
	{  2880, -2240,    0,   954, 1658,  406,   16,  52,  18,  280 },
	{  4032, -2240,  256,  1015, 1755,  435,   21,  24, -18,  280 },
	{ -4032, -1344,    0,  1076, 1852,  464,   26,  31,   0,  280 },
	{ -2880, -1344,  256,  1137, 1949,  493,   31,  38,  18,  280 },
	{ -1728, -1344,  512,  1198, 2046,  522,   36,  45, -18,  280 },
	{  -576, -1344,  768,  1259, 2143,  551,   41,  52,   0,  280 },
	{   576, -1344,    0,  1320, 2240,  580,   46,  24,  18,  280 },
	{  1728, -1344,  256,  1381, 2337,  609,   16,  31, -18,  280 },
	{  2880, -1344,  512,  1442, 2434,  638,   21,  38,   0,  280 },
	{  4032, -1344,  768,  1503, 2531,  667,   26,  45,  18,  280 },
	{ -4032,  -448,  512,  1564, 2628,  696,   31,  52, -18,  280 },
	{ -2880,  -448,  768,  1625, 2725,  725,   36,  24,   0,  280 },
	{ -1728,  -448,    0,  1686, 2822,  754,   41,  31,  18,  280 },
	{  -576,  -448,  256,  1747, 2919,  783,   46,  38, -18,  280 },
	{   576,  -448,  512,  1808, 3016,  812,   16,  45,   0,  280 },
	{  1728,  -448,  768,  1869, 3113,  841,   21,  52,  18,  280 },
	{  2880,  -448,    0,  1930, 3210,  870,   26,  24, -18,  280 },
	{  4032,  -448,  256,  1991, 3307,  899,   31,  31,   0,  280 },
	{ -4032,   448,    0,  2052, 3404,  928,   36,  38,  18,  280 },
	{ -2880,   448,  256,  2113, 3501,  957,   41,  45, -18,  280 },
	{ -1728,   448,  512,  2174, 3598,  986,   46,  52,   0,  280 },
	{  -576,   448,  768,  2235, 3695, 1015,   16,  24,  18,  280 },
	{   576,   448,    0,  2296, 3792, 1044,   21,  31, -18,  280 },
	{  1728,   448,  256,  2357, 3889, 1073,   26,  38,   0,  280 },
	{  2880,   448,  512,  2418, 3986, 1102,   31,  45,  18,  280 },
	{  4032,   448,  768,  2479, 4083, 1131,   36,  52, -18,  280 },
	{ -4032,  1344,  512,  2540,   84, 1160,   41,  24,   0,  280 },
	{ -2880,  1344,  768,  2601,  181, 1189,   46,  31,  18,  280 },
	{ -1728,  1344,    0,  2662,  278, 1218,   16,  38, -18,  280 },
	{  -576,  1344,  256,  2723,  375, 1247,   21,  45,   0,  280 },
	{   576,  1344,  512,  2784,  472, 1276,   26,  52,  18,  280 },
	{  1728,  1344,  768,  2845,  569, 1305,   31,  24, -18,  280 },
	{  2880,  1344,    0,  2906,  666, 1334,   36,  31,   0,  280 },
	{  4032,  1344,  256,  2967,  763, 1363,   41,  38,  18,  280 },
	{ -4032,  2240,    0,  3028,  860, 1392,   46,  45, -18,  280 },
	{ -2880,  2240,  256,  3089,  957, 1421,   16,  52,   0,  280 },
	{ -1728,  2240,  512,  3150, 1054, 1450,   21,  24,  18,  280 },
	{  -576,  2240,  768,  3211, 1151, 1479,   26,  31, -18,  280 },
	{   576,  2240,    0,  3272, 1248, 1508,   31,  38,   0,  280 },
	{  1728,  2240,  256,  3333, 1345, 1537,   36,  45,  18,  280 },
	{  2880,  2240,  512,  3394, 1442, 1566,   41,  52, -18,  280 },
	{  4032,  2240,  768,  3455, 1539, 1595,   46,  24,   0,  280 },
	{ -4032,  3136,  512,  3516, 1636, 1624,   16,  31,  18,  280 },
	{ -2880,  3136,  768,  3577, 1733, 1653,   21,  38, -18,  280 },
	{ -1728,  3136,    0,  3638, 1830, 1682,   26,  45,   0,  280 },
	{  -576,  3136,  256,  3699, 1927, 1711,   31,  52,  18,  280 },
	{   576,  3136,  512,  3760, 2024, 1740,   36,  24, -18,  280 },
	{  1728,  3136,  768,  3821, 2121, 1769,   41,  31,   0,  280 },
	{  2880,  3136,    0,  3882, 2218, 1798,   46,  38,  18,  280 },
	{  4032,  3136,  256,  3943, 2315, 1827,   16,  45, -18,  280 },
};

/* The 8 corners, +-1.0 (4096). Corner i has x = +1 if bit 0 of i is set, y = +1 if bit 1, z = +1 if bit 2. */
SVECTOR cube[8] = {
	{ -4096, -4096, -4096 }, {  4096, -4096, -4096 }, { -4096,  4096, -4096 }, {  4096,  4096, -4096 },
	{ -4096, -4096,  4096 }, {  4096, -4096,  4096 }, { -4096,  4096,  4096 }, {  4096,  4096,  4096 },
};

int32_t path __attribute__((section(".data"))) = 0;   /* 0 = RTPS per corner, 1 = RTPT batches (in .data so the verifier can patch it) */
VECTOR  cam    = { 0, 0, 8192 };          /* the common camera: added to every cube's position (no rotation) */
int32_t proj_h = 256;                     /* projection distance h, in pixels */

MATRIX  cube_mtx[N_CUBES];                /* cube i's matrix: rotation * size, translation = position + cam (built for you) */
int32_t screen_xy[N_CUBES][8];            /* cube i, corner c: one SXY word, x in the low 16 bits, y in the high 16 */
int32_t screen_z[N_CUBES][8];             /* cube i, corner c: SZ */
int32_t field_cycles[2];                  /* CPU cycles the transform of the whole field took, last frame, per path */
int32_t frame_no;                         /* frames completed */

__attribute__((noinline)) void render_begin(void)    { __asm__ volatile("" ::: "memory"); }   /* the verifier times the whole frame's work from here ... */
__attribute__((noinline)) void render_end(void)      { __asm__ volatile("" ::: "memory"); }   /* ... to here */
__attribute__((noinline)) void transform_begin(void) { __asm__ volatile("" ::: "memory"); }   /* and the transform of the field from here ... */
__attribute__((noinline)) void transform_end(void)   { __asm__ volatile("" ::: "memory"); }   /* ... to here */
__attribute__((noinline)) void frame_done(void)      { __asm__ volatile("" ::: "memory"); }

/* ---- given: the timer, the cubes' motion, the matrices -------------------------------------------------------------- */

#define RC0_COUNT (*(volatile uint16_t *) 0x1F801100)   /* root counter 0 ... */
#define RC0_MODE  (*(volatile uint16_t *) 0x1F801104)   /* ... mode 0: counts CPU cycles (33.8688 MHz), wraps at 65536 */

static void update_cubes(void)
{
	for (int i = 0; i < N_CUBES; i++) {
		Cube *c = &cubes[i];

		c->ax = (c->ax + c->sx) & 4095;
		c->ay = (c->ay + c->sy) & 4095;
		c->az = (c->az + c->sz) & 4095;
	}
}

static void build_matrices(void)
{
	for (int i = 0; i < N_CUBES; i++) {
		const Cube *c = &cubes[i];
		SVECTOR rot = { c->ax, c->ay, c->az, 0 };
		VECTOR  scl = { c->size, c->size, c->size };
		VECTOR  pos = { c->x + cam.vx, c->y + cam.vy, c->z + cam.vz };

		RotMatrix(&rot, &cube_mtx[i]);
		ScaleMatrix(&cube_mtx[i], &scl);
		TransMatrix(&cube_mtx[i], &pos);
	}
}

/* Load cube i's matrix into the GTE (RT and TR). `noipa`: the SDK's gte_SetRotMatrix/gte_SetTransMatrix overwrite $t0 and
   $t1 without declaring it (README 5.7). The compiler must treat this function as an opaque call that clobbers every
   temporary register, not inline it and not look inside it. */
static __attribute__((noipa)) void load_matrix(int i)
{
	gte_SetRotMatrix(&cube_mtx[i]);
	gte_SetTransMatrix(&cube_mtx[i]);
}

/* ---- path 0 (given): one RTPS per corner, Chapter 25's code ------------------------------------------------------- */

static void transform_field_rtps(void)
{
	for (int i = 0; i < N_CUBES; i++) {
		load_matrix(i);
		for (int c = 0; c < 8; c++) {
			gte_ldv0(&cube[c]);
			gte_rtps();
			gte_stsxy(&screen_xy[i][c]);
			gte_stsz(&screen_z[i][c]);
		}
	}
}

/* ---- path 1 (yours): RTPT -------------------------------------------------------------------------------------------- */

static void transform_field_rtpt(void)
{
	for (int i = 0; i < N_CUBES; i++) {
		load_matrix(i);
		/* three batches: corners 0-2, 3-5 and 5-7 (corner 5 is transformed twice, so every slot of the last batch is a real corner) */
		gte_ldv3c(&cube[0]);
		gte_rtpt();
		gte_stsxy3c(&screen_xy[i][0]);
		gte_stsz3c(&screen_z[i][0]);
		gte_ldv3c(&cube[3]);
		gte_rtpt();
		gte_stsxy3c(&screen_xy[i][3]);
		gte_stsz3c(&screen_z[i][3]);
		gte_ldv3c(&cube[5]);
		gte_rtpt();
		gte_stsxy3c(&screen_xy[i][5]);
		gte_stsz3c(&screen_z[i][5]);
	}
}

/* ---- given: drawing ------------------------------------------------------------------------------------------------- */

/* A colored 8 x 8 tile at the middle of each cube (halfway between the projected corners 0 and 7). */
static void draw_tiles(void)
{
	for (int i = 0; i < N_CUBES; i++) {
		int32_t a = screen_xy[i][0], b = screen_xy[i][7];
		int x = ((int16_t) a + (int16_t) b) >> 1;
		int y = ((a >> 16) + (b >> 16)) >> 1;

		gfx_quad_f4(x - 4, y - 4, 8, 8, 64 + ((i * 37) & 127), 64 + ((i * 53) & 127), 64 + ((i * 71) & 127),
		            (screen_z[i][0] + screen_z[i][7]) >> 10);
	}
}

int main(void)
{
	display_init();
	InitGeom();
	gte_SetGeomOffset(CX, CY);
	gte_SetGeomScreen(proj_h);
	RC0_MODE = 0;
	/* Keeps the state above linked in even where your code does not read it. Leave this line in. */
	__asm__ volatile("" :: "r"(cubes), "r"(cube), "r"(&path), "r"(&cam), "r"(&proj_h), "r"(cube_mtx), "r"(screen_xy),
	                 "r"(screen_z), "r"(field_cycles));

	for (;;) {
		uint16_t t0, t1;

		display_clear(16, 16, 32);
		ot_begin_frame();
		render_begin();
		update_cubes();
		build_matrices();
		transform_begin();
		t0 = RC0_COUNT;
		if (path == 0)
			transform_field_rtps();
		else
			transform_field_rtpt();
		t1 = RC0_COUNT;
		transform_end();
		field_cycles[path != 0] = (uint16_t) (t1 - t0);
		draw_tiles();
		render_end();
		ot_draw();
		display_swap();
		frame_no++;
		if ((frame_no % 120) == 0)
			printf("path %d: %d cycles for 64 cubes\n", (int) path, (int) field_cycles[path != 0]);
		frame_done();
	}
	return 0;
}
