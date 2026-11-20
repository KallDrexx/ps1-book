#ifndef PSXE_INPUT_H
#define PSXE_INPUT_H

#include <stdint.h>

/* Button masks: bit set = button down ("active-high"). These are the bit positions of the pad's
   16-bit button word (the same values as PAD_* in <psxpad.h>). */
#define INPUT_SELECT    0x0001
#define INPUT_L3        0x0002
#define INPUT_R3        0x0004
#define INPUT_START     0x0008
#define INPUT_UP        0x0010
#define INPUT_RIGHT     0x0020
#define INPUT_DOWN      0x0040
#define INPUT_LEFT      0x0080
#define INPUT_L2        0x0100
#define INPUT_R2        0x0200
#define INPUT_L1        0x0400
#define INPUT_R1        0x0800
#define INPUT_TRIANGLE  0x1000
#define INPUT_CIRCLE    0x2000
#define INPUT_CROSS     0x4000
#define INPUT_SQUARE    0x8000

/* Start the BIOS pad driver for port 1 (call once, after display_init). No button is down afterwards. */
void input_init(void);

/* Take a new reading of port 1. Call exactly once per frame, before any query. */
void input_update(void);

/* Each query returns 1 if ANY button of `mask` qualifies, else 0 (0 for an empty mask).
   They look only at the last two readings, so they can be called any number of times per frame.
   held:     down in the latest reading.
   pressed:  down in the latest reading and up in the one before (the frame it went down).
   released: up in the latest reading and down in the one before (the frame it came up). */
int input_held(uint16_t mask);
int input_pressed(uint16_t mask);
int input_released(uint16_t mask);

#endif
