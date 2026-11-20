#include <stddef.h>
#include "object.h"

/* Chapter 33, part 1 of 4: the linked list (README 7.3 step 2). object.h is the contract: read it first.
   Every function is a stub that compiles and does nothing useful. Replace the bodies; keep the names and signatures. */

void obj_insert(Object **head, Object *o)
{
	/* TODO: put o first. */
	(void) head;
	(void) o;
}

void obj_append(Object **head, Object *o)
{
	/* TODO: put o last (o->next = NULL); the empty list is a case too. */
	(void) head;
	(void) o;
}

int obj_remove(Object **head, Object *o)
{
	/* TODO: unlink o by pointer; 1 if it was in the list, else 0. Mind the head, the NULLs and o->next afterwards. */
	(void) head;
	(void) o;
	return 0;
}

int obj_count(const Object *head)
{
	/* TODO */
	(void) head;
	return 0;
}
