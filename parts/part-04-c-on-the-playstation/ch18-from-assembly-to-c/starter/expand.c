#include <stdint.h>
#include "expand.h"

/* TODO: widen a 5-bit channel (0..31) to 8 bits (0..255):
 * c5 << 3, with the top 3 bits of c5 copied into the bottom 3 (Chapter 9's c8 = c5<<3 | c5>>2).
 * Keep it a plain function of one argument: you will read its assembly. */
uint32_t expand5(uint32_t c5)
{
	(void)c5;
	return 0;
}
