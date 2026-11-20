# Part V: Three Dimensions with the GTE

**Theme.** The math of 3D graphics in fixed point, and the Geometry Transformation Engine (GTE), the coprocessor that does it in hardware.

**Part outcome.** You render several transformed, back-face-culled 3D objects viewed through a camera you can fly with the controller.

## Chapters

| # | Chapter | You build | Status |
|---|---|---|---|
| 23 | [Fixed-Point Math](ch23-fixed-point-math/README.md) | `fixed.h/.c`: `fx_mul`, `fx_div`, `fx_from_int`, `fx_lerp`, `fx_sqrt`, `fx_rotate`, and a float-vs-fixed benchmark | available |
| 24 | [3D Projection Fundamentals](ch24-3d-projection-fundamentals/README.md) | "Software Cube": a spinning wireframe cube projected on the CPU; `fixed` joins `psxe` | available |
| 25 | [The GTE Coprocessor](ch25-the-gte-coprocessor/README.md) | "Solid Cube": a flat-shaded cube with GTE transforms, back-face culling and depth sorting | available |
| 26 | [Multiple Objects and Simple Motion](ch26-multiple-objects-and-simple-motion/README.md) | "Bouncing Cubes": three cubes under fixed-point gravity on a checkerboard floor | available |
| 27 | Batching GTE Work: RTPT and Timing | A 64-cube field transformed per corner (`RTPS`) and batched (`RTPT`), with the cycles of each compared | planned |
| 28 | The Camera | `camera_look_at` and a free-fly camera | planned |

## How the part flows

```
fixed point -> projection -> the GTE -> many objects -> batching -> camera
   (Ch 23)       (Ch 24)      (Ch 25)      (Ch 26)       (Ch 27)    (Ch 28)
```

Chapter 23 gives you the number system: the PS1 has no FPU, and the GTE itself computes in 4.12 fixed point, so every later chapter depends on it. Chapter 24 builds the 3D pipeline (model, world, view, perspective divide, screen) on the CPU, so you see each step. Chapter 25 hands the same steps to the GTE through PSn00bSDK's `gte_*` macros and adds back-face culling and depth sorting. Chapter 26 gives each object its own transform and adds motion. Chapter 27 looks at what the GTE costs: its full register set, command timing and hazards, and batching three vertices per command with `RTPT`. Chapter 28 turns the camera into a matrix and puts it under your control.

## Before you start

Finish Part IV. You will use:

- the C project structure and the `psxe` library from Chapters 18 to 22 (display, ordering table, primitives, pad);
- `mult`/`mfhi`/`mflo` and instruction costs from Chapter 12;
- arithmetic shifts and rounding from Chapter 9;
- the O32 calling convention from Chapter 10, which the verifier checks on your C functions too.

The workflow is the Part IV one: `source tools/env.sh`, `make` in `starter/`, `verify.sh`. Chapter 23 has no graphics: its verifier calls your functions directly and compares them with Python.

## Fixed-point conventions

Part V uses two formats throughout:

| Format | Type | 1.0 is | Used for |
|---|---|---|---|
| 4.12 | `int16_t` | 4096 | GTE matrices, `SVECTOR`s, `isin`/`icos` results |
| 20.12 | `int32_t` (`fx`) | 4096 | CPU-side math |

psx-spx names the same formats 1.3.12 and 1.19.12 (sign bit counted separately). Angles are **4096 units per full turn**. From Chapter 24 on, `fixed.h/.c` lives in the `psxe` library as the `fixed` module (`#include <psxe/fixed.h>`); see the module table in the [Part IV README](../part-04-c-on-the-playstation/README.md#the-psxe-library).
