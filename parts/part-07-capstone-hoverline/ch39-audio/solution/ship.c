#include <stdint.h>
#include <psxgte.h>
#include <psxe/fixed.h>
#include <psxe/input.h>
#include "ship.h"

Ship ship;

ShipCfg ship_cfg = {
	.thrust = 3072, .brake = 6144, .speed_cap = 60 * 4096, .yaw_accel = 8192, .yaw_damp = 512, .roll_gain = 16,
	.roll_smooth = 1024, .hover = 120, .back_dist = 900, .cam_height = 250, .look_ahead = 1200, .start_section = -1,
};

int32_t heading_angle(int32_t x, int32_t z)
{
	int32_t best = 0, best_err = 0x7FFFFFFF;

	for (int32_t a = 0; a < 4096; a++) {
		int32_t s = isin(a), c = icos(a), err = s * z - c * x;

		if (s * x + c * z <= 0)
			continue;                              /* pointing the other way */
		if (err < 0) err = -err;
		if (err < best_err) {
			best_err = err;
			best = a;
		}
	}
	return best;
}

int32_t pitch_angle(int32_t y)
{
	int32_t best = -1024, best_err = 1 << 30;

	for (int32_t p = -1024; p <= 1024; p++) {
		int32_t e = isin(p) + y;

		if (e < 0) e = -e;
		if (e < best_err) {
			best_err = e;
			best = p;
		}
	}
	return best;
}

int ship_place(Ship *s, const Track *t)
{
	int sec = ship_cfg.start_section < 0 ? t->start_section : ship_cfg.start_section;
	const TrkSection *c = track_section(t, sec);

	if (!c)
		return -1;
	*s = (Ship) { 0 };
	for (int i = 0; i < 3; i++)
		s->pos[i] = c->centre[i] + ((c->up[i] * ship_cfg.hover) >> 12);
	s->yaw = heading_angle(c->forward[0], c->forward[2]) << ANGLE_SHIFT;
	s->pitch = pitch_angle(c->forward[1]) * (1 << ANGLE_SHIFT);
	return 0;
}

void ship_forward(const Ship *s, int32_t out[3])
{
	int32_t a = s->yaw >> ANGLE_SHIFT, p = s->pitch >> ANGLE_SHIFT;

	out[0] = fx_mul(isin(a), icos(p));
	out[1] = -isin(p);
	out[2] = fx_mul(icos(a), icos(p));
}

__attribute__((noinline)) void ship_update(Ship *s, uint16_t pad, int32_t dt)
{
	const ShipCfg *c = &ship_cfg;
	int32_t steer = ((pad & INPUT_RIGHT) != 0) - ((pad & INPUT_LEFT) != 0);
	int32_t f[3];

	s->yaw_vel += fx_mul(steer * c->yaw_accel, dt);
	s->yaw_vel -= fx_mul(s->yaw_vel, fx_mul(c->yaw_damp, dt));
	if (s->yaw_vel > -YAW_DEAD && s->yaw_vel < YAW_DEAD)
		s->yaw_vel = 0;
	s->yaw = (s->yaw + fx_mul(s->yaw_vel, dt)) & ANGLE_MASK;

	s->roll += fx_mul(s->yaw_vel * c->roll_gain - s->roll, fx_mul(c->roll_smooth, dt));

	if (pad & INPUT_CROSS)
		s->speed += fx_mul(c->thrust, dt);
	if (pad & INPUT_SQUARE)
		s->speed -= fx_mul(c->brake, dt);
	if (s->speed > c->speed_cap) s->speed = c->speed_cap;
	if (s->speed < 0) s->speed = 0;

	ship_forward(s, f);
	for (int i = 0; i < 3; i++) {
		int32_t t;

		s->vel[i] = fx_mul(f[i], s->speed);
		t = s->pos_frac[i] + fx_mul(s->vel[i], dt);
		s->pos[i] += t >> 12;
		s->pos_frac[i] = t & 4095;
	}
}

void ship_matrix(const Ship *s, MATRIX *out)
{
	SVECTOR a = { (int16_t) (s->pitch >> ANGLE_SHIFT), 0, (int16_t) (s->roll >> ANGLE_SHIFT), 0 };
	SVECTOR b = { 0, (int16_t) (s->yaw >> ANGLE_SHIFT), 0, 0 };
	MATRIX  ma, mb;

	RotMatrix(&a, &ma);
	RotMatrix(&b, &mb);
	MulMatrix0(&mb, &ma, out);
	out->t[0] = out->t[1] = out->t[2] = 0;
}
