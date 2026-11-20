#include <stdint.h>
#include <psxgte.h>
#include <psxe/fixed.h>
#include <psxe/input.h>
#include "ship.h"

/* Chapter 37: the ship's physics. ship.h is the specification of every function below; README 5 explains the rules.
   The constants are given. Everything else is yours. The stubs compile and do nothing. */

Ship ship;

ShipCfg ship_cfg = {
	.thrust = 3072, .brake = 6144, .speed_cap = 60 * 4096, .yaw_accel = 8192, .yaw_damp = 512, .roll_gain = 16,
	.roll_smooth = 1024, .hover = 120, .back_dist = 900, .cam_height = 250, .look_ahead = 1200, .start_section = -1,
};

/* TODO (README 5.3): the heading of (x, z), as ship.h defines it. */
int32_t heading_angle(int32_t x, int32_t z)
{
	(void) x; (void) z;
	return 0;
}

/* TODO (README 5.3): the pitch angle of a direction with this y component, as ship.h defines it. */
int32_t pitch_angle(int32_t y)
{
	(void) y;
	return 0;
}

/* TODO (README 5.3): put the ship on the start line. */
int ship_place(Ship *s, const Track *t)
{
	(void) s; (void) t;
	return -1;
}

/* TODO (README 5.4): the ship's forward unit vector (4.12). */
void ship_forward(const Ship *s, int32_t out[3])
{
	(void) s;
	out[0] = out[1] = out[2] = 0;
}

/* TODO (README 5.5): one physics tick, in the order ship.h gives. Keep `noinline`: the verifier hooks the entry and the return. */
__attribute__((noinline)) void ship_update(Ship *s, uint16_t pad, int32_t dt)
{
	(void) s; (void) pad; (void) dt;
	__asm__ volatile("" ::: "memory");
}

/* TODO (README 5.4): the rotation matrix, M = Ry(yaw) * (Rx(pitch) * Rz(roll)). */
void ship_matrix(const Ship *s, MATRIX *out)
{
	(void) s;
	*out = (MATRIX) { { { 4096, 0, 0 }, { 0, 4096, 0 }, { 0, 0, 4096 } }, { 0, 0, 0 } };
}
