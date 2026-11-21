#include <stdint.h>
#include <psxgte.h>
#include "camera.h"
#include "ship.h"

void chase_camera_update(const Ship *s)
{
	const ShipCfg *c = &ship_cfg;
	int32_t f[3];

	ship_forward(s, f);
	cam_eye.vx = s->pos[0] - ((f[0] * c->back_dist) >> 12);
	cam_eye.vy = s->pos[1] - ((f[1] * c->back_dist) >> 12) - c->cam_height;
	cam_eye.vz = s->pos[2] - ((f[2] * c->back_dist) >> 12);
	cam_target.vx = s->pos[0] + ((f[0] * c->look_ahead) >> 12);
	cam_target.vy = s->pos[1] + ((f[1] * c->look_ahead) >> 12);
	cam_target.vz = s->pos[2] + ((f[2] * c->look_ahead) >> 12);
	camera_look_at(&cam_eye, &cam_target, &cam_up);
}
