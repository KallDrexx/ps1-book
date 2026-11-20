#ifndef CAMERA_H
#define CAMERA_H

#include <stdint.h>
#include <psxgte.h>

#define DEGENERATE 524288            /* |forward x up| below this: up is parallel to forward (Chapter 28) */

/* The camera. Positions are world units; +x right, +y DOWN, +z into the screen. The verifier reads and patches these. */
extern VECTOR  cam_eye;              /* where the camera is */
extern int32_t cam_yaw;              /* heading, 4096 = one turn: 0 looks along +z, 1024 along +x */
extern VECTOR  cam_target;           /* what it looks at: the eye plus 1000 units along the heading (set every frame) */
extern VECTOR  cam_up;               /* which way is up: -y */
extern int32_t cam_speed;            /* units per frame while a direction is held */
extern int32_t cam_turn;             /* yaw units per frame while L2 / R2 is held */
extern VECTOR  cam_min, cam_max;     /* the eye stays inside this box */
extern MATRIX  view_mtx;             /* world -> view: rows right, down, forward; t = -R * eye (the eye may be far from the origin) */

/* Chapter 28's look-at (given): fills view_mtx. */
void camera_look_at(const VECTOR *eye, const VECTOR *target, const VECTOR *up);

/* Chapter 28's fly camera plus a turn (given). Reads the pad (call input_update first), moves cam_eye in WORLD axes
   (RIGHT/LEFT: +x/-x; UP/DOWN: +z/-z; R1/L1: +y/-y, i.e. down/up), turns cam_yaw (R2 turns toward +x, L2 toward -x),
   clamps the eye to [cam_min, cam_max], sets cam_target and calls camera_look_at. */
void camera_update(void);

#endif
