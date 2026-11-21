#include <stddef.h>
#include "object.h"

void obj_insert(Object **head, Object *o)
{
	o->next = *head;
	*head = o;
}

void obj_append(Object **head, Object *o)
{
	Object **link = head;               /* the pointer that points at the node we look at: the head, then some ->next */

	while (*link)
		link = &(*link)->next;
	o->next = NULL;
	*link = o;
}

int obj_remove(Object **head, Object *o)
{
	Object **link;

	if (!head || !o)
		return 0;
	for (link = head; *link; link = &(*link)->next) {
		if (*link == o) {
			*link = o->next;            /* the pointer that pointed at o now skips it */
			o->next = NULL;
			return 1;
		}
	}
	return 0;
}

int obj_count(const Object *head)
{
	int n = 0;

	for (; head; head = head->next)
		n++;
	return n;
}
