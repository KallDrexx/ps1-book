#ifndef OBJECT_H
#define OBJECT_H

#include <stdint.h>

#define OBJ_ALWAYS_DRAW 1            /* flags bit 0: never culled by distance (Appendix E.9) */

/* One thing in the world: a node of a singly linked list. The verifier walks this struct through the `object_head`
   symbol, so the layout is fixed: twelve 32-bit words, `next` first. */
typedef struct Object {
	struct Object *next;             /* +0   the next node, or NULL at the end of the list */
	int32_t shape;                   /* +4   index into the scene's shape table */
	int32_t flags;                   /* +8   OBJ_ALWAYS_DRAW, ... */
	int32_t x, y, z;                 /* +12  world position of the model's origin (+y is down) */
	int32_t rx, ry, rz;              /* +24  rotation, 4096 = one turn (the scene only uses ry) */
	int32_t scale;                   /* +36  uniform scale, 4.12: 4096 = 1.0 */
	int32_t radius;                  /* +40  bounding radius in world units: the shape's radius * scale >> 12 */
	int32_t visible;                 /* +44  1 if the last game frame drew this object, else 0 */
} Object;

/* The list is a pointer to its first node (`Object *head`, NULL when empty). Nodes belong to the CALLER: no function
   here allocates or frees anything. A node is in at most one list, at most once. */

/* Put `o` first in the list. O(1). */
void obj_insert(Object **head, Object *o);

/* Put `o` last in the list (o->next = NULL). O(n): it walks to the end. */
void obj_append(Object **head, Object *o);

/* Unlink `o` (the node itself, found by pointer, not by value). Returns 1 and sets o->next = NULL if it was in the list;
   returns 0 and changes nothing if it was not (an empty list, a NULL `o` and a NULL `head` included). */
int obj_remove(Object **head, Object *o);

/* Number of nodes. */
int obj_count(const Object *head);

/* for (OBJ_EACH(o, head)) { ... }  Do not obj_remove(o) inside it without saving o->next first. */
#define OBJ_EACH(o, head) Object *o = (head); o; o = o->next

#endif
