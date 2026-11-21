#ifndef HANDLING_H
#define HANDLING_H

#include <stdint.h>
#include "track.h"
#include "ship.h"

/* ---- handling (README 5.1 - 5.4) ---------------------------------------------------------------------------------------------
   Three layered forces on top of Chapter 37's ship, all in the integer arithmetic of the book (4.12 fractions, fx_mul = (a * b) >> 12 with a
   64-bit product and an arithmetic shift, so negative products round DOWN). Each acts per tick and is scaled by dt (4.12: DT_NTSC 4096,
   DT_PAL 4915), and each fraction is clamped to 4096 (1.0) after the scaling so that a long PAL tick cannot overshoot its target.
     drag    a share of the speed lost every tick (air resistance);
     skid    the velocity follows the facing only a fraction of the way each tick (lateral slip);
     pitch   the nose follows the slope of the road under the ship. */

/* The tunable constants. 4 words; patchable (the verifier writes them to prove nothing is hard-coded). */
typedef struct {
	int32_t drag;                 /* 64   = 1/64:  the fraction of the speed lost per NTSC tick (4.12). Top speed with thrust 0.75: 0.75 * 63 = 47.25 (README 5.2) */
	int32_t grip;                 /* 1024 = 1/4:   the fraction of the gap between vel and forward * speed closed per NTSC tick (4.12) */
	int32_t pitch_smooth;         /* 1024 = 1/4:   the fraction of the pitch error closed per NTSC tick (4.12) */
	int32_t reserved;
} HandlingCfg;
_Static_assert(sizeof(HandlingCfg) == 16, "the verifier patches 4 words at `handling_cfg`");

#define PITCH_LIMIT 256           /* auto-pitch searches the whole-unit angles -PITCH_LIMIT .. PITCH_LIMIT (22.5 degrees) */

extern HandlingCfg handling_cfg;

/* ---- you write ------------------------------------------------------------------------------------------------------------- */

/* Air resistance (README 5.2). With f = min(fx_mul(handling_cfg.drag, dt), 4096):  return speed - fx_mul(speed, f).
   No clamping of the result (ship_update clamps the speed afterwards). */
int32_t handling_drag(int32_t speed, int32_t dt);

/* Skid (README 5.3). With g = min(fx_mul(handling_cfg.grip, dt), 4096), for each axis i = 0, 1, 2 (in place):
     vel[i] += fx_mul(target[i] - vel[i], g).
   grip 4096 makes vel equal target at once (Chapter 37's ship: no skid); a small grip lets the ship slide. */
void handling_skid(int32_t vel[3], const int32_t target[3], int32_t dt);

/* The pitch the nose wants over a road whose `up` vector (4.12, -y is up) is up[3], heading `yaw` (12.12 angle; a = yaw >> 12 is the whole-unit
   angle isin / icos take), README 5.4:
     if up[1] > -256 (a plane that is nearly vertical or upside down): return 0.
     hx = isin(a), hz = icos(a);  num = up[0] * hx + up[2] * hz;
     g  = (-num) / up[1]          (C division, truncating; the slope of the road along the heading, 4.12; negative = the road climbs)
     g clamped to -32767 .. 32767;  y = (g * 4096) / collide_isqrt(4096 * 4096 + g * g)     (truncating: the y component of the unit vector along the slope)
     p = the whole-unit angle in -PITCH_LIMIT .. PITCH_LIMIT that minimizes |isin(p) + y| (the first, i.e. the smallest, on a tie)
   and the result is p << 12 as a 12.12 angle (nose up = positive: a climbing road, y < 0, gives p > 0).
   A scan of the 513 angles costs about 40,000 instructions, too many for every tick: isin rises strictly over this range, so a binary search finds p. */
int32_t handling_pitch_target(const int32_t up[3], int32_t yaw);

/* Auto-pitch (README 5.4): ease the ship's pitch toward the target of section `sec`. Does nothing if `sec` is not a section.
   Otherwise  target = handling_pitch_target(section.up as int32_t[3], s->yaw);
              f = min(fx_mul(handling_cfg.pitch_smooth, dt), 4096);   s->pitch += fx_mul(target - s->pitch, f).
   Nothing else of the ship changes. */
void handling_auto_pitch(Ship *s, const Track *t, int sec, int32_t dt);

#endif
