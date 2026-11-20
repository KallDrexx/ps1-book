#ifndef MODEL_H
#define MODEL_H

#include <stdint.h>
#include <psxgte.h>

/* One face record of MODEL.BIN, exactly as it is in the file (Appendix E.7). */
typedef struct {
	uint8_t i[4];                    /* vertex indices; i[3] == 0xFF means a triangle */
	uint8_t r, g, b, pad;            /* flat colour */
} ModelFace;

/* A parsed model. `verts` and `faces` point INTO the buffer that was parsed: free that, not these. */
typedef struct {
	uint32_t         vertex_count;
	uint32_t         face_count;
	const SVECTOR   *verts;
	const ModelFace *faces;
} Model;

/* Read a big-endian u32 from 4 bytes, one byte at a time (never cast the pointer). */
uint32_t read_be32(const uint8_t *p);

/* Parse a MODEL.BIN image of `size` bytes at `data` (4-byte aligned). Returns 1 and fills *m, or 0
   if anything is wrong: misaligned, too small, bad magic, vertex_count outside 1..255, a size that
   is not exactly 12 + 8*V + 8*F, a face index >= V. Writes *m only on success. */
int model_parse(Model *m, const void *data, uint32_t size);

#endif
