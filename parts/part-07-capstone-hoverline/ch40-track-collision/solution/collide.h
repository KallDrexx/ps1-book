#ifndef COLLIDE_H
#define COLLIDE_H

#include <stdint.h>
#include "track.h"
#include "ship.h"

/* ---- units (README 5.1) ----------------------------------------------------------------------------------------------------
   The road is tested in the XZ plane (E.10.4): +x right, +z forward, +y down is ignored except for the ground height.
   Distances are whole world units; a "unit normal" is a 4.12 vector (4096 = 1.0), stored as an (x, z) pair.
   A point or direction is passed as int32_t[2] = { x, z } unless the name says pos (int32_t[3] = { x, y, z }).
   Every difference `p - a` is clamped to -32767 .. 32767 per axis BEFORE it is multiplied (a ship far away must not overflow), and the
   program assumes every edge vector has |x|, |z| <= 8192 (the generated tracks: about 1100 at most). */
#define COLL_CLAMP   32767
#define COLL_WALK    4            /* section moves collide_section may make before it gives up and searches everything */

/* The tunable constants. 8 words; patchable (the verifier writes them to prove nothing is hard-coded). */
typedef struct {
	int32_t radius;               /* 90    : the ship's centre stays at least this far inside each road edge (world units) */
	int32_t wall_damp;            /* 2048  = 0.5: a head-on hit removes this fraction of the speed (4.12) */
	int32_t yaw_fix;              /* 2048  = 0.5: the fraction of the heading error removed by a hit (4.12) */
	int32_t boost_impulse;        /* 20480 = 5.0: speed added when the ship enters a boost face (4.12 units per NTSC tick) */
	int32_t thud_gap;             /* 12    : ticks without a hit before the next hit raises EV_THUD again */
	int32_t off_limit;            /* 1200  : farther than this OUTSIDE an edge the ship is respawned instead of pushed back */
	int32_t reserved[2];
} CollideCfg;
_Static_assert(sizeof(CollideCfg) == 32, "the verifier patches 8 words at `collide_cfg`");

/* Counters and the last readings. The verifier reads 12 words at `collide_state`. collide_reset() zeroes them (last_hit: see below). */
typedef struct {
	int32_t hits;                 /* +0  wall hits: edges that pushed the ship back (a tick can hit both edges: 2) */
	int32_t thuds;                /* +4  EV_THUD events raised */
	int32_t boosts;               /* +8  boost-face entries (EV_BOOST events raised) */
	int32_t respawns;             /* +12 respawns */
	int32_t on_boost;             /* +16 1 if the ship ended the last tick over a boost face */
	int32_t last_hit;             /* +20 ship_ticks of the last hit; -1000000 after collide_reset */
	int32_t dist_left;            /* +24 the distance to the left edge, measured at the start of the last collide_ship call */
	int32_t dist_right;           /* +28 ... to the right edge */
	int32_t face;                 /* +32 the floor face under the ship after the last call (a face index), -1 for none */
	int32_t reserved[3];
} CollideState;
_Static_assert(sizeof(CollideState) == 48, "the verifier reads 12 words at `collide_state`");

/* What collide_ship returns: a bit mask. */
#define COLL_HIT_LEFT    0x01     /* the left edge pushed the ship back */
#define COLL_HIT_RIGHT   0x02
#define COLL_BOOST       0x04     /* the ship entered a boost face: speed impulse + EV_BOOST */
#define COLL_RESPAWN     0x08     /* the ship was too far outside an edge and was put back at the section's centre */
#define COLL_THUD        0x10     /* EV_THUD was raised */

/* The road edges of one section in the XZ plane (README 5.3): the four points of E.10.4's recipe, in the order of the section's edges[]. */
typedef struct {
	int32_t p[4][2];              /* left_start, right_start, left_end, right_end: { x, z } of vertices[edges[k]] (or the fallback points) */
	int32_t fallback;             /* 1 if the fallback was used, else 0 */
} CollideEdges;

extern CollideCfg   collide_cfg;
extern CollideState collide_state;
extern char         collide_text[32];   /* the debug readout of the last frame (README 5.3), as it was drawn */

/* ---- given ----------------------------------------------------------------------------------------------------------------- */

/* floor(sqrt(n)) for an unsigned 32-bit value. */
uint32_t collide_isqrt(uint32_t n);

/* The same answer as heading_angle (Chapter 37: the first whole-unit angle that points the way and minimizes the cross product), found
   in 129 + 64 evaluations of isin / icos instead of 4096: a hit may happen on every tick, and 4096 evaluations are about 330,000 instructions. (0, 0) gives 0. */
int32_t collide_heading(int32_t x, int32_t z);

/* Start of a game: zero collide_state, then last_hit = -1000000. Called by set_state when the game is entered. */
void collide_reset(void);

/* ---- you write ------------------------------------------------------------------------------------------------------------- */

/* The edges of section `sec` (README 5.3). Returns 0 if the recipe worked, 1 if the fallback was used (also stored in e->fallback),
   -1 (e untouched) if `sec` is not a section.
   Recipe: p[k] = { x, z } of vertices[edges[k]], k = 0..3 (left_start, right_start, left_end, right_end).
   A section is IRREGULAR when, for the left edge (p0 -> p2, reference point p1) or the right edge (p1 -> p3, reference p0):
     the edge has zero length (both components of b - a are 0), or  ex * clamp(rz - az) - ez * clamp(rx - ax) == 0.
   Fallback (both edges are replaced, per axis, with >> the arithmetic shift): with c = centre, w = half_width, r = right (4.12), f = forward, L = length:
     left_start  = c + ((-r * w) >> 12)   (the product is negated BEFORE the shift),   right_start = c + ((r * w) >> 12),
     each end    = its start + ((f * L) >> 12).   Only the x and z components are used. */
int collide_edges(const Track *t, int sec, CollideEdges *e);

/* The signed distance of the point p from the line a -> b (README 5.2), positive on the side of the reference point r, and the unit
   normal of that line pointing to that side. seg = { ax, az, bx, bz, rx, rz }. n receives { nx, nz } (4.12).
     ex = bx - ax, ez = bz - az, len = collide_isqrt(ex*ex + ez*ez); if len == 0: return 0, n = { 0, 0 }.
     cross(v) = ex * vz - ez * vx;   s = -1 if cross(r - a) < 0, else +1   (with both differences clamped)
     dist = (s * cross(p - a)) / len   (C division: truncates toward zero)
     n = { (s * -ez * 4096) / len, (s * ex * 4096) / len }. */
int32_t collide_edge_dist(const int32_t seg[6], const int32_t p[2], int32_t n[2]);

/* The section the ship is over (README 5.4): its slab, the part of the plane between its start ring line and its end ring line.
   With e = collide_edges (the fallback counts) and the start ring line = (p0 -> p1, reference p2), the end ring line = (p2 -> p3, reference p0):
     ds = collide_edge_dist(start line, pos), de = collide_edge_dist(end line, pos)   (positive toward the section's inside)
   The section is `cur` when de > 0 and ds >= 0. Otherwise: de <= 0 means "move to next", else (ds < 0) "move to prev" (by the links).
   Up to COLL_WALK moves; a walk that wants move number COLL_WALK + 1 gives up. A give-up, or a `cur` that is not a section, is followed by
   track_nearest_brute(t, pos) and a second walk from its answer with the same rules; if that gives up too, the result is the section the
   second walk stopped on. Returns -1 when the track has no sections. pos is {x, y, z}; only x and z are used. */
int collide_section(const Track *t, int cur, const int32_t pos[3]);

/* The y of the road surface under (pos.x, pos.z) in section `sec` (README 5.5): the plane through the section's centre with normal `up`:
     dx = clamp(x - centre.x), dz = clamp(z - centre.z), num = up.x * dx + up.z * dz;   if |up.y| < 256: return centre.y;
     return centre.y + (-num) / up.y     (C division, truncating). */
int32_t collide_ground(const Track *t, int sec, const int32_t pos[3]);

/* The first FLOOR face of section `sec` (in table order) whose quad contains (pos.x, pos.z), or -1 (README 5.6). The quad's corners go
   v0, v1, v3, v2 (the faces are Z ordered). Contained: of the four values  cross(b - a) * clamp(p - a)  for the four sides a -> b (the
   same cross as above), not both a positive and a negative one (a point on a side counts as inside). */
int collide_floor_face(const Track *t, int sec, const int32_t pos[3]);

/* One physics tick of collision, called right after ship_update (README 5.7). t is the track; s the ship; the section comes from and goes to
   the global ship_section; the clock is ship_ticks. In this order:
     1. ship_section = collide_section(t, ship_section, s->pos). If it is < 0: return 0.
     2. dl, nl = distance and normal for the left edge (p0 -> p2, reference p1); dr, nr for the right edge (p1 -> p3, reference p0).
        collide_state.dist_left / dist_right = dl, dr.
     3. If dl < -off_limit or dr < -off_limit: respawn at the section (collide_respawn), respawns++, on_boost = 0, return COLL_RESPAWN.
     4. For the left edge, then the right edge, if its distance d < radius (hit; hits++; depth = radius - d):
          pos.x += (n.x * depth) >> 12;  pos.z += (n.z * depth) >> 12
          f = ship_forward(s); dot = fx_mul(f.x, n.x) + fx_mul(f.z, n.z)
          if dot < 0 (heading into the wall): impact = min(-dot, 4096); speed -= fx_mul(speed, fx_mul(wall_damp, impact));
              target = collide_heading(edge.x, edge.z) << 12 (edge = the edge's own b - a);
              err = ((target - yaw + HALF) & ANGLE_MASK) - HALF  (HALF = ANGLE_TURN / 2);   yaw = (yaw + fx_mul(err, yaw_fix)) & ANGLE_MASK
              yaw_vel = 0;  vel = fx_mul(forward, speed) per axis (forward of the NEW yaw)
          if ship_ticks - last_hit >= thud_gap: thuds++, audio_event(EV_THUD), result |= COLL_THUD.   last_hit = ship_ticks.
        The two edges use the distances and normals of step 2 (not measured again after the first push).
     5. pos.y = collide_ground(t, section, pos) - ship_cfg.hover;  pos_frac[1] = 0.
     6. face = collide_floor_face(t, section, pos); collide_state.face = face. on = face >= 0 and that face has TRK_BOOST.
        If on and not on_boost: speed = min(speed + boost_impulse, ship_cfg.speed_cap); vel as above; boosts++, audio_event(EV_BOOST), result |= COLL_BOOST.
        on_boost = on.
   Returns the bits COLL_* (0 for none). */
int collide_ship(const Track *t, Ship *s);

/* Put the ship back on the road at section `sec` the way ship_place puts it on the start line: pos = centre + ((up * hover) >> 12) per axis,
   pos_frac, vel, speed, roll, yaw_vel = 0, yaw = heading_angle(forward.x, forward.z) << 12, pitch = pitch_angle(forward.y) << 12.
   Does nothing if `sec` is not a section. */
void collide_respawn(const Track *t, Ship *s, int sec);

/* The debug readout (README 5.3): writes "L%5d R%5d F%3d" (collide_state.dist_left, dist_right, face) into collide_text (printf style, at most 31 characters). */
void collide_format(void);

#endif
