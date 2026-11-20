#include <stdint.h>
#include "expand.h"

/* 5-bit channel (0..31) -> 8-bit channel (0..255): c << 3 | c >> 2 */
uint32_t expand5(uint32_t c5)
{
	return (c5 << 3) | (c5 >> 2);
}
