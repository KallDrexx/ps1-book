#include "cull.h"

static uint32_t abs32(int32_t v) { return v < 0 ? (uint32_t) 0 - (uint32_t) v : (uint32_t) v; }

int cull_test(const Object *o, const VECTOR *eye, int32_t cull_radius, VECTOR *d)
{
	uint32_t ax, ay, az, r, sum;

	d->vx = o->x - eye->vx;
	d->vy = o->y - eye->vy;
	d->vz = o->z - eye->vz;
	ax = abs32(d->vx);
	ay = abs32(d->vy);
	az = abs32(d->vz);
	if (ax > DRAW_LIMIT || ay > DRAW_LIMIT || az > DRAW_LIMIT)
		return 0;                                   /* beyond the GTE's reach; also keeps the squares below small */
	if (o->flags & OBJ_ALWAYS_DRAW)
		return 1;
	r = (uint32_t) (cull_radius + o->radius);
	sum = ax * ax + ay * ay + az * az;              /* at most 3 * 32000^2 = 3.07e9 < 2^32 */
	return sum <= r * r;                            /* r <= 32000: r * r <= 1.024e9 */
}
