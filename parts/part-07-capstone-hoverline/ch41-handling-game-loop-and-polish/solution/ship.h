#ifndef SHIP_H
#define SHIP_H

#include <stdint.h>
#include <psxgte.h>
#include "track.h"
#include "shp.h"
#include "tpk.h"

/* ---- units (README 5.2) --------------------------------------------------------------------------------------------------
   World:  +x right, +y DOWN, +z forward (the book's axes). Positions are whole world units.
   Time:   one TICK = one video frame (1/60 s NTSC, 1/50 s PAL). Rates are "per NTSC tick"; a step is scaled by dt_scale (4.12):
           DT_NTSC = 4096 (1.0), DT_PAL = 4915 (60/50 = 1.2, rounded down).
   Speed:  4.12 world units per NTSC tick (60 units/tick = 245760).
   Angles: 12.12 fixed point: 4096 units per turn << 12, so one turn is ANGLE_TURN = 1 << 24. Stored angles are in [0, ANGLE_TURN).
           `angle >> 12` is the whole-unit angle that isin / icos / RotMatrix take. */
#define DT_NTSC     4096
#define DT_PAL      4915
#define ANGLE_SHIFT 12
#define ANGLE_TURN  (1 << 24)
#define ANGLE_MASK  (ANGLE_TURN - 1)
#define YAW_DEAD    16            /* |yaw_vel| below this (after damping) is set to 0 (about 0.004 units per tick) */

/* The ship. The verifier reads it through the `ship` symbol: 14 words, in this order. */
typedef struct {
	int32_t pos[3];               /* +0   world units */
	int32_t pos_frac[3];          /* +12  the sub-unit remainder of each coordinate, 0..4095 (1/4096 unit) */
	int32_t vel[3];               /* +24  4.12 world units per NTSC tick, = forward * speed */
	int32_t speed;                /* +36  4.12 units per NTSC tick along `forward`, 0 .. speed_cap */
	int32_t yaw;                  /* +40  12.12 angle: turns +z toward +x (the book's RotMatrix vy); heading of the nose */
	int32_t pitch;                /* +44  nose up is positive (set at the start, then eased toward the road's slope by handling_auto_pitch, Chapter 41) */
	int32_t roll;                 /* +48  right wing down is positive */
	int32_t yaw_vel;              /* +52  12.12 angle per NTSC tick */
} Ship;
_Static_assert(sizeof(Ship) == 56, "the verifier reads 14 words at the `ship` symbol");

/* The tunable constants. 13 words; patchable (the verifier writes them to prove nothing is hard-coded). */
typedef struct {
	int32_t thrust;               /* 3072  = 0.75: speed gained per NTSC tick while CROSS is held (4.12) */
	int32_t brake;                /* 6144  = 1.50: speed lost per NTSC tick while SQUARE is held (4.12) */
	int32_t speed_cap;            /* 245760 = 60.0: the largest speed (4.12) */
	int32_t yaw_accel;            /* 8192  = 2.0: yaw_vel change per NTSC tick while LEFT / RIGHT is held (12.12 angle) */
	int32_t yaw_damp;             /* 512   = 1/8: the fraction of yaw_vel removed per NTSC tick (4.12) */
	int32_t roll_gain;            /* 16    : roll target = yaw_vel * roll_gain (a plain integer) */
	int32_t roll_smooth;          /* 1024  = 1/4: the fraction of the roll error closed per NTSC tick (4.12) */
	int32_t hover;                /* 120   : world units above the road surface at the start (along the section's up) */
	int32_t back_dist;            /* 900   : the chase camera sits this far behind the ship ... */
	int32_t cam_height;           /* 250   : ... and this far above it */
	int32_t look_ahead;           /* 1200  : ... and looks at the point this far in front of the ship */
	int32_t start_section;        /* -1    : the section to start on, or -1 for the track's START section */
	int32_t reserved;             /* 0 */
} ShipCfg;
_Static_assert(sizeof(ShipCfg) == 52, "the verifier patches 13 words at `ship_cfg`");

/* ---- state the verifier reads --------------------------------------------------------------------------------------------- */
extern Ship        ship;          /* the player's ship */
extern ShipCfg     ship_cfg;      /* the constants above (initialised data) */
extern int32_t     video_mode;    /* 0 = NTSC, 1 = PAL. Read once at the start of main (README 5.7) */
extern int32_t     dt_scale;      /* DT_NTSC or DT_PAL, from video_mode */
extern int32_t     frame_ticks;   /* physics ticks run in the last game frame (README 5.7) */
extern int32_t     ship_ticks;    /* ship_update calls made by the game since the ship was placed */
extern Shp         ship_shp;      /* the parsed SHIP.SHP */
extern TpkTextures ship_store;    /* SHIP.TPK's textures */

/* Place the ship on the start line (README 5.3): section = ship_cfg.start_section, or t->start_section if that is negative.
   Returns 0, or -1 (and changes nothing) when the section is out of range. Sets every field of *s:
     pos       = section centre + ((up * hover) >> 12) per axis (up is the section's 4.12 `up`: -y is up, so the ship ends ABOVE the road);
     pos_frac, vel, speed, roll, yaw_vel = 0;
     yaw       = heading_angle(forward.x, forward.z) << 12;     pitch = pitch_angle(forward.y) << 12 (nose up when the road climbs). */
int ship_place(Ship *s, const Track *t);

/* The heading of the direction (x, z): the whole-unit angle a in 0..4095, 0 along +z and 1024 along +x, that points the same way
   (isin(a) * x + icos(a) * z > 0) and minimises |isin(a) * z - icos(a) * x| (the first one on a tie). Minimising the CROSS product, not
   maximising the dot product: the dot is flat at its peak, so table errors would move the maximum by a few units. (0, 0) gives 0. |x|, |z| <= 8192. */
int32_t heading_angle(int32_t x, int32_t z);

/* The whole-unit angle p in -1024..1024 that minimises |isin(p) + y| (the first on a tie), y the 4.12 y component of a unit
   direction: nose up for y < 0 (+y is down). |y| <= 4096. */
int32_t pitch_angle(int32_t y);

/* The 4.12 forward unit vector of the ship (README 5.4): with a = yaw >> 12, p = pitch >> 12 (each as the whole-unit angle):
     out[0] = fx_mul(isin(a), icos(p));   out[1] = -isin(p);   out[2] = fx_mul(icos(a), icos(p)).
   For pitch 0 this is (sin yaw, 0, cos yaw). Roll does not change it. */
void ship_forward(const Ship *s, int32_t out[3]);

/* One physics tick (README 5.5), in this exact order, every step in the integer arithmetic given there. pad = INPUT_* mask
   (active high), dt = DT_NTSC or DT_PAL (any 4.12 factor is allowed). All constants from ship_cfg.
     1. steer  = RIGHT - LEFT (1, 0 or -1)
     2. yaw_vel += fx_mul(steer * yaw_accel, dt);   yaw_vel -= fx_mul(yaw_vel, fx_mul(yaw_damp, dt));   |yaw_vel| < YAW_DEAD -> 0
     3. yaw = (yaw + fx_mul(yaw_vel, dt)) & ANGLE_MASK
     4. roll += fx_mul(yaw_vel * roll_gain - roll, fx_mul(roll_smooth, dt));   roll is signed and is not wrapped
     5. CROSS: speed += fx_mul(thrust, dt);   SQUARE: speed -= fx_mul(brake, dt);   speed = handling_drag(speed, dt)   (Chapter 41);
        then speed = clamp(speed, 0, speed_cap)
     6. target = forward * speed (each axis fx_mul(forward[i], speed));   handling_skid(vel, target, dt)   (Chapter 41: vel follows target, it is no longer equal to it)
     7. each axis: t = pos_frac + fx_mul(vel, dt); pos += t >> 12; pos_frac = t & 4095
   The pitch is not changed here: game.c calls handling_auto_pitch after collide_ship (Chapter 41). */
void ship_update(Ship *s, uint16_t pad, int32_t dt);

/* The ship's rotation (README 5.4): M = Ry(yaw) * (Rx(pitch) * Rz(roll)): yaw about the WORLD y axis, then pitch about the ship's
   right axis, then roll about its nose. Built from two RotMatrix calls and MulMatrix0; the translation part t is 0. */
void ship_matrix(const Ship *s, MATRIX *out);

/* The chase camera (README 5.8): fills cam_eye and cam_target from the ship and calls camera_look_at. Call after ship_update.
     eye    = pos - (forward * back_dist >> 12) + (0, -cam_height, 0)      (per axis, arithmetic shift; -y is above)
     target = pos + (forward * look_ahead >> 12)
     up     = (0, -4096, 0) (the world's up: the camera does not roll with the ship) */
void chase_camera_update(const Ship *s);

#endif
