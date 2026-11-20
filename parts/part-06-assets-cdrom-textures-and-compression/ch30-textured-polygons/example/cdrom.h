#ifndef CDROM_H
#define CDROM_H

#include <stdint.h>

#define CD_SECTOR_SIZE 2048          /* bytes of data in one CD-ROM sector */

/* Start the CD-ROM library (CdInit, retried a few times). Call once, after display_init()
   (ResetGraph). Returns 1 when the drive answered, 0 if not. */
int cd_init(void);

/* Load a whole file from the disc.
   path   the file's full disc path as CdSearchFile wants it, e.g. "\\DATA\\MODEL.BIN;1".
   size   out: the file's size in bytes, from its directory entry; 0 on failure. May be NULL.
   Returns a malloc'ed buffer holding the file, which the caller releases with free(). The buffer
   is a whole number of sectors long (the last sector is read in full), 4-byte aligned, and bytes
   after `*size` are padding.
   Returns NULL (and *size = 0) if the file is not found, is empty, malloc fails, the read
   reports an error, or the read has not finished after CD_TIMEOUT_FRAMES video frames. */
void *cd_load_file(const char *path, uint32_t *size);

#endif
