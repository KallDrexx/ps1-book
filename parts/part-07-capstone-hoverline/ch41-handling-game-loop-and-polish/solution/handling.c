#include <stdint.h>
#include <psxgte.h>
#include <psxe/fixed.h>
#include "track.h"
#include "ship.h"
#include "collide.h"
#include "handling.h"

HandlingCfg handling_cfg = { .drag = 64, .grip = 1024, .pitch_smooth = 1024 };

static int32_t scaled(int32_t k, int32_t dt)
{
	int32_t f = fx_mul(k, dt);

	return f > 4096 ? 4096 : f;
}

int32_t handling_drag(int32_t speed, int32_t dt)
{
	return speed - fx_mul(speed, scaled(handling_cfg.drag, dt));
}

void handling_skid(int32_t vel[3], const int32_t target[3], int32_t dt)
{
	int32_t g = scaled(handling_cfg.grip, dt);

	for (int i = 0; i < 3; i++)
		vel[i] += fx_mul(target[i] - vel[i], g);
}

int32_t handling_pitch_target(const int32_t up[3], int32_t yaw)
{
	int32_t a = yaw >> ANGLE_SHIFT, hx, hz, num, g, y, lo, hi;

	if (up[1] > -256)
		return 0;
	hx = isin(a);
	hz = icos(a);
	num = up[0] * hx + up[2] * hz;
	g = (-num) / up[1];
	if (g > 32767) g = 32767;
	if (g < -32767) g = -32767;
	y = (g * 4096) / (int32_t) collide_isqrt(4096 * 4096 + g * g);
	/* the first p in -PITCH_LIMIT .. PITCH_LIMIT with isin(p) + y >= 0 (isin rises strictly here); the answer is it or the one before */
	lo = -PITCH_LIMIT;
	hi = PITCH_LIMIT + 1;
	while (lo < hi) {
		int32_t mid = (lo + hi) >> 1;

		if (isin(mid) + y >= 0)
			hi = mid;
		else
			lo = mid + 1;
	}
	if (lo > -PITCH_LIMIT) {
		int32_t e1 = isin(lo - 1) + y, e2 = lo > PITCH_LIMIT ? 0x7FFFFFFF : isin(lo) + y;

		if (e1 < 0) e1 = -e1;
		if (e2 < 0) e2 = -e2;
		if (e1 <= e2)
			lo--;
	}
	if (lo > PITCH_LIMIT)
		lo = PITCH_LIMIT;
	return lo * (1 << ANGLE_SHIFT);
}

void handling_auto_pitch(Ship *s, const Track *t, int sec, int32_t dt)
{
	const TrkSection *c = track_section(t, sec);
	int32_t up[3];

	if (!c)
		return;
	up[0] = c->up[0];
	up[1] = c->up[1];
	up[2] = c->up[2];
	s->pitch += fx_mul(handling_pitch_target(up, s->yaw) - s->pitch, scaled(handling_cfg.pitch_smooth, dt));
}
