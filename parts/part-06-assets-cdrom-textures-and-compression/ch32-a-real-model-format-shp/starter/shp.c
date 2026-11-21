#include <stdint.h>
#include <string.h>
#include <psxgpu.h>
#include "shp.h"

/* Chapter 32, part 1 of 2: the .SHP parser and the per-type packet builders (README 7). shp.h is the contract: read it first.
   Every function below is a stub that compiles and does nothing useful. Replace the bodies; keep the names and signatures. */

uint32_t shp_record_size(unsigned type)
{
	/* TODO (README 7.3 step 2): 16 20 24 32 24 32 32 44 for the tags 0..7, 0 for anything else. A small table. */
	(void) type;
	return 0;
}

uint32_t shp_decode(const uint8_t *rec, ShpPrim *p)
{
	/* TODO (README 7.3 step 2): read the fields of the record at `rec` one byte at a time (never cast rec to a wider pointer type).
	   The layout of every type is in README 5.2 / Appendix E.8.2. Return the record's size. */
	(void) rec;
	(void) p;
	return 0;
}

int shp_parse(const void *data, size_t size, Shp *s)
{
	/* TODO (README 7.3 step 3): validate in the order shp.h lists (README 5.4), then fill *s (pointers INTO `data`, counts[] by type tag). */
	(void) data;
	(void) size;
	(void) s;
	return SHP_ERR_MAGIC;
}

uint32_t shp_packet_size(unsigned type, int textured)
{
	/* TODO (README 7.3 step 4): sizeof(POLY_xx) of the packet shp_fill will build. */
	(void) type;
	(void) textured;
	return 0;
}

void shp_fill(void *pkt, const ShpPrim *p, const int32_t *sxy, const Tex *tex)
{
	/* TODO (README 7.3 steps 4 and 6): one case per packet kind: setPolyXX, colors, setXY3/setXY4, and for textured kinds setUV3/setUV4 + tpage + clut. */
	(void) pkt;
	(void) p;
	(void) sxy;
	(void) tex;
}
