#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "cdrom.h"
#include "tim.h"
#include "tpk.h"

#define RING 4096
#define RING_START 4078          /* RING - 18 */

static uint32_t rd32(const uint8_t *p)
{
	return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t) p[3] << 24);
}

uint32_t tpk_crc32(const uint8_t *p, size_t n)
{
	uint32_t crc = 0xFFFFFFFFu;

	while (n--) {
		crc ^= *p++;
		for (int k = 0; k < 8; k++)
			crc = (crc >> 1) ^ (0xEDB88320u & -(crc & 1));
	}
	return ~crc;
}

__attribute__((noinline)) int lzss_decode(const uint8_t *src, size_t src_size, uint8_t *dst, size_t dst_size)
{
	static uint8_t ring[RING];
	const uint8_t *in = src, *end = src + src_size;
	size_t o = 0;
	unsigned r = RING_START;

	memset(ring, 0, sizeof ring);
	while (o < dst_size) {
		unsigned flags;

		if (in >= end)
			return TPK_ERR_DATA;
		flags = *in++;
		for (int bit = 0; bit < 8 && o < dst_size; bit++, flags >>= 1) {
			if (flags & 1) {                                   /* literal */
				uint8_t c;

				if (in >= end)
					return TPK_ERR_DATA;
				c = *in++;
				dst[o++] = ring[r] = c;
				r = (r + 1) & (RING - 1);
			} else {                                           /* reference: 12-bit absolute position, 4-bit length - 3 */
				unsigned b0, b1, pos, len;

				if (end - in < 2)
					return TPK_ERR_DATA;
				b0 = in[0];
				b1 = in[1];
				in += 2;
				pos = b0 | ((b1 & 0xF0) << 4);
				len = (b1 & 15) + 3;
				if (len > dst_size - o)
					return TPK_ERR_DATA;
				while (len--) {
					uint8_t c = ring[pos];

					pos = (pos + 1) & (RING - 1);
					dst[o++] = ring[r] = c;
					r = (r + 1) & (RING - 1);
				}
			}
		}
	}
	return in == end ? TPK_OK : TPK_ERR_DATA;
}

int tpk_parse(const void *file, size_t size, TpkHeader *h)
{
	const uint8_t *d = file;
	uint32_t count, table_end, sum = 0;

	if (size < 4 || d[0] != 'T' || d[1] != 'P' || d[2] != 'K' || d[3] != '1')
		return TPK_ERR_MAGIC;
	if (size < 0x14)
		return TPK_ERR_HEADER;
	count = rd32(d + 4);
	if (count < 1 || count > TPK_MAX)
		return TPK_ERR_HEADER;
	table_end = 0x14 + 4 * count;
	if (size < table_end)
		return TPK_ERR_HEADER;
	h->count = count;
	h->raw_size = rd32(d + 8);
	h->comp_size = rd32(d + 12);
	h->crc32 = rd32(d + 16);
	for (uint32_t i = 0; i < count; i++) {
		uint32_t s = rd32(d + 0x14 + 4 * i);

		if (s == 0 || (s & 3) || s > TPK_MAX_RAW)
			return TPK_ERR_HEADER;
		sum += s;
		if (sum > TPK_MAX_RAW)
			return TPK_ERR_HEADER;
		h->sizes[i] = s;
	}
	if (sum != h->raw_size || h->raw_size == 0)
		return TPK_ERR_HEADER;
	if (h->comp_size == 0 || h->comp_size > size - table_end || size - table_end - h->comp_size > 3)
		return TPK_ERR_HEADER;
	h->stream = d + table_end;
	return TPK_OK;
}

int tpk_unpack(const void *file, size_t size, uint8_t *dst, size_t dst_size)
{
	TpkHeader h;
	int rc = tpk_parse(file, size, &h);

	if (rc)
		return rc;
	if (dst_size < h.raw_size)
		return TPK_ERR_SPACE;
	rc = lzss_decode(h.stream, h.comp_size, dst, h.raw_size);
	if (rc)
		return rc;
	return tpk_crc32(dst, h.raw_size) == h.crc32 ? TPK_OK : TPK_ERR_CRC;
}

int tpk_load(const char *path, TpkTextures *out)
{
	TpkHeader h;
	uint32_t size, off = 0;
	uint8_t *raw;
	void *file;
	int rc;

	out->count = 0;
	out->raw = NULL;
	out->raw_size = 0;
	file = cd_load_file(path, &size);
	if (!file)
		return TPK_ERR_READ;
	rc = tpk_parse(file, size, &h);
	if (rc) {
		free(file);
		return rc;
	}
	raw = malloc(h.raw_size);
	if (!raw) {
		free(file);
		return TPK_ERR_MEM;
	}
	rc = tpk_unpack(file, size, raw, h.raw_size);
	free(file);                                   /* the compressed image is not needed any more */
	if (rc) {
		free(raw);
		return rc;
	}
	for (uint32_t i = 0; i < h.count; i++) {
		TimInfo info;

		if (!tim_parse(&info, raw + off, h.sizes[i])) {
			free(raw);
			return TPK_ERR_TIM;
		}
		tim_upload(&info);
		tex_from_tim(&out->tex[i], &info);
		off += h.sizes[i];
	}
	out->count = h.count;
	out->raw = raw;
	out->raw_size = h.raw_size;
	return TPK_OK;
}

void tpk_free_raw(TpkTextures *out)
{
	free(out->raw);
	out->raw = NULL;
	out->raw_size = 0;
}
