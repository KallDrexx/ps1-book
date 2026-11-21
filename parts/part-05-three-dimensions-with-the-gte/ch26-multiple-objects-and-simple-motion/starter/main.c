#include <stdint.h>
#include <psxgpu.h>
#include <psxgte.h>
#include <inline_c.h>
#include <psxe/display.h>
#include <psxe/ot.h>
#include <psxe/fixed.h>

#define CX (SCREEN_W / 2)
#define CY (SCREEN_H / 2)
#define OTZ_SHIFT 7                  /* OT slot = OTZ >> 7 (Chapter 25) */
#define FLOOR_SLOT (OT_LENGTH - 1)   /* the floor is always the farthest thing */

#define FLOOR_COLS 8                 /* tiles along x */
#define FLOOR_ROWS 6                 /* tiles along z */
#define TILE       2048              /* tile edge, world units */
#define N_OBJECTS  3

/* One bouncing cube. Every field is an int32, in this order: the verifier reads and patches the array. */
typedef struct {
	int32_t x, y, z;          /* center, world units; y is 20.12 fixed point (y >> 12 = units), y grows DOWN */
	int32_t vy;               /* vertical velocity, 20.12 units per frame (positive = falling) */
	int32_t ax, ay, az;       /* angles about X, Y, Z, 0..4095 */
	int32_t sx, sy, sz;       /* added to the angles every frame */
	int32_t size;             /* half the cube's edge, units */
	int32_t radius;           /* collision radius, units (center to floor at rest) */
	int32_t bounce;           /* restitution, 4.12 (4096 = loses no speed) */
	int32_t colour;           /* r | g << 8 | b << 16 */
	int32_t bounces;          /* floor contacts so far */
} Object;

/* State the verifier reads and patches. Do not change the layout, the order or the initial values. */
Object objects[N_OBJECTS] = {
	{ -4400, -3000 * 4096, -1200,        0,  300,   0, 120,   0, 56,   0, 1200, 1500, 3277, 0x3030E0, 0 },   /* red   */
	{     0, -4000 * 4096,  1800, -60 * 4096,   0, 500, 200,  40,  0,   0, 1700, 2125, 2867, 0x40C830, 0 },   /* green */
	{  4400, -2500 * 4096,     0,  30 * 4096, 700, 150,   0,   0,  0, -48, 2200, 2750, 3482, 0xF06040, 0 },   /* blue  */
};

int32_t gravity = 4 * 4096;               /* added to every vy each frame (20.12 units per frame squared) */
int32_t floor_y = 4096;                   /* the floor's world y (the eye is at y = 0) */
VECTOR  cam     = { 0, 0, 14336 };        /* the fixed "camera": added to every world position */
int32_t proj_h  = 256;                    /* projection distance h, in pixels */

SVECTOR cube[8] = {                       /* the unit cube, +-1.0 (4096); corner i: x from bit 0, y from bit 1, z from bit 2 */
	{ -4096, -4096, -4096 }, {  4096, -4096, -4096 }, { -4096,  4096, -4096 }, {  4096,  4096, -4096 },
	{ -4096, -4096,  4096 }, {  4096, -4096,  4096 }, { -4096,  4096,  4096 }, {  4096,  4096,  4096 },
};
uint8_t faces[6][4] = {                   /* Chapter 25's table */
	{ 0, 1, 2, 3 }, { 5, 4, 7, 6 }, { 4, 0, 6, 2 }, { 1, 5, 3, 7 }, { 4, 5, 0, 1 }, { 2, 3, 6, 7 },
};
uint16_t face_shade[6] = { 256, 208, 176, 232, 192, 160 };   /* face f color = channel * shade >> 8 */
uint8_t floor_colors[2][3] = { { 72, 72, 96 }, { 168, 168, 190 } };   /* tile (col + row) even / odd */

MATRIX  cam_mtx;                          /* identity rotation, translation = cam */
int32_t frame_no;                         /* frames completed */

__attribute__((noinline)) void render_begin(void) { __asm__ volatile("" ::: "memory"); }
__attribute__((noinline)) void render_end(void)   { __asm__ volatile("" ::: "memory"); }
__attribute__((noinline)) void frame_done(void)   { __asm__ volatile("" ::: "memory"); }

/* Given: load a MATRIX into the GTE (RT and TR). PSn00bSDK 0.24's gte_SetRotMatrix/gte_SetTransMatrix overwrite $t0 and
   $t1 without declaring it, so a value the compiler keeps there across them is lost. Call them only from here: `noipa`
   makes this an opaque call that may clobber every temporary register (README 9). */
static __attribute__((noipa, unused)) void load_matrix(const MATRIX *m)
{
	gte_SetRotMatrix(m);
	gte_SetTransMatrix(m);
}

/* TODO 1 (README 7.3): build cam_mtx once. Identity rotation (4096 on the diagonal), translation = cam. */
static void init_world(void)
{
}

/* TODO 2: advance every object by one frame: gravity, the floor, the spin (README 5.5). */
static void update_objects(void)
{
}

/* Given: one flat quad, corners as packed SXY words (x in the low half, y in the high half), at ordering-table slot `slot`. */
__attribute__((unused))
static void put_quad(int32_t a, int32_t b, int32_t c, int32_t d, int r, int g, int bl, int slot)
{
	POLY_F4 *p = (POLY_F4 *) ot_alloc(sizeof(POLY_F4));

	if (!p)
		return;
	setPolyF4(p);
	setRGB0(p, r, g, bl);
	setXY4(p, (int16_t) a, a >> 16, (int16_t) b, b >> 16, (int16_t) c, c >> 16, (int16_t) d, d >> 16);
	ot_add(p, slot);
}

/* TODO 3: the checkerboard floor: upload the camera matrix (load_matrix), transform the 9 x 7 corners, one quad per tile (README 7.3). */
static void draw_floor(void)
{
}

/* TODO 4: one cube: its own matrix, uploaded with load_matrix, then its eight corners and its visible faces (README 7.3). */
static void draw_object(const Object *o)
{
	(void) o;
}

int main(void)
{
	display_init();
	InitGeom();
	gte_SetGeomOffset(CX, CY);
	gte_SetGeomScreen(proj_h);
	init_world();
	/* Keeps the state above linked in even where your code does not read it. Leave this line in. */
	__asm__ volatile("" :: "r"(objects), "r"(&gravity), "r"(&floor_y), "r"(&cam), "r"(&proj_h), "r"(cube), "r"(faces),
	                 "r"(face_shade), "r"(floor_colors), "r"(&cam_mtx));

	for (;;) {
		display_clear(24, 24, 48);
		ot_begin_frame();
		render_begin();
		update_objects();
		draw_floor();
		for (int i = 0; i < N_OBJECTS; i++)
			draw_object(&objects[i]);
		render_end();
		ot_draw();
		display_swap();
		frame_no++;
		frame_done();
	}
	return 0;
}
