#include <stdint.h>
#include <psxgte.h>
#include <psxe/fixed.h>
#include "track.h"
#include "ship.h"
#include "collide.h"
#include "handling.h"

HandlingCfg handling_cfg = { .drag = 64, .grip = 1024, .pitch_smooth = 1024 };

/* TODO (README 5.2): air resistance. The placeholder leaves the speed alone. */
int32_t handling_drag(int32_t speed, int32_t dt)
{
	(void) dt;
	return speed;
}

/* TODO (README 5.3): skid. The placeholder puts the velocity on the target at once, as Chapter 37 did. */
void handling_skid(int32_t vel[3], const int32_t target[3], int32_t dt)
{
	(void) dt;
	for (int i = 0; i < 3; i++)
		vel[i] = target[i];
}

/* TODO (README 5.4): the pitch target. The placeholder wants a level nose. */
int32_t handling_pitch_target(const int32_t up[3], int32_t yaw)
{
	(void) up;
	(void) yaw;
	return 0;
}

/* TODO (README 5.4): auto-pitch. The placeholder does nothing. */
void handling_auto_pitch(Ship *s, const Track *t, int sec, int32_t dt)
{
	(void) s;
	(void) t;
	(void) sec;
	(void) dt;
}
