#include <stdint.h>
#include "model.h"

/* TODO: assemble p[0]..p[3] into a big-endian u32 (p[0] is the most significant byte). */
uint32_t read_be32(const uint8_t *p)
{
	(void) p;
	return 0;
}

/* TODO (README 5.8, 7.2): parse and validate a MODEL.BIN image; the contract is in model.h and Appendix E.7.
   Check, in this order: alignment and size >= 12; magic "MDL1"; vertex_count (big-endian) in 1..255 and the
   vertex table inside the image; face_count (big-endian, at 8 + 8 * V) fits and size == 12 + 8 * V + 8 * F
   (watch for overflow in 8 * F); every face index < V (i[3] == 0xFF means a triangle).
   Only then fill *m: verts = data + 8, faces = data + 12 + 8 * V. */
int model_parse(Model *m, const void *data, uint32_t size)
{
	(void) m; (void) data; (void) size;
	return 0;
}
