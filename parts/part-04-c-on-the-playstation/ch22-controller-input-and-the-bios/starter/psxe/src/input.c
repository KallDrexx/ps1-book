#include <psxe/input.h>

/* TODO (README 7.3): the BIOS pad driver and the three queries.
   Every function below is a stub: the program builds, and the cursor never moves. */

void input_init(void)
{
}

void input_update(void)
{
}

int input_held(uint16_t mask)     { (void) mask; return 0; }
int input_pressed(uint16_t mask)  { (void) mask; return 0; }
int input_released(uint16_t mask) { (void) mask; return 0; }
