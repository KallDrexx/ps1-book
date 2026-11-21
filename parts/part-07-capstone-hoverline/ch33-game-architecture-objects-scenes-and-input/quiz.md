# Chapter 33 quiz

Answers are hidden under each question.

**1.** Name the three stages of the main loop and one thing each must *not* do.

<details><summary>Answer</summary>
Input (read the pad once; it must not change the world), update (change the camera, objects and game state; it must not draw), render (read the world and fill the ordering table; it must not change the world). Keeping them apart means logic can be tested without a picture, and a skipped or repeated render cannot change the game.
</details>

**2.** The scene loader builds the list with `obj_insert` instead of `obj_append`. The probe finds every position right but still fails. Why?

<details><summary>Answer</summary>
`obj_insert` puts each new node first, so the list ends up in the *reverse* of the file's order: node 0 is the last object. Positions and shapes are all there, but node *i* is no longer file entry *i*, which is the documented contract. `obj_append` keeps the file's order.
</details>

**3.** Why does `obj_remove(Object **head, Object *o)` take a pointer to the head pointer, and what must it do to `o` afterwards?

<details><summary>Answer</summary>
Removing the first node must change the head itself, so the function needs the head pointer's address. With a `link` that starts at `head` and then moves to `&node->next`, the first node needs no special case: make `*link` skip `o`. It then clears `o->next`, so a stale pointer cannot walk into the old list, and returns 1 (0, changing nothing, when `o` is not in the list).
</details>

**4.** This loop removes the nodes with `visible == 0` and misbehaves. Why, and what is the fix?

`for (Object *o = head; o; o = o->next) if (!o->visible) obj_remove(&head, o);`

<details><summary>Answer</summary>
`obj_remove` clears `o->next`, so the loop's `o = o->next` is NULL and the walk stops after the first removal (with an implementation that leaves `next` alone it would follow a pointer into a node that is no longer in the list). Read `next = o->next` before removing and continue with `next`.
</details>

**5.** An object is at `dx = 65536`, `dy = dz = 0` from the camera. What does `dx*dx + dy*dy + dz*dz <= R*R` compute in 32-bit arithmetic, and how does the book's rule avoid it?

<details><summary>Answer</summary>
`65536 * 65536 = 2^32`, which wraps to 0, so the object looks like it is at distance 0 and is drawn from 65,536 units away. The rule first rejects any object with a coordinate difference above 32000 on any axis; after that each square is at most 1.024e9 and the sum of three is below 2^32 in `uint32_t`, so the comparison with `(cull_radius + radius)^2` is exact.
</details>

**6.** Why is the object's own radius added to `cull_radius`?

<details><summary>Answer</summary>
The distance is measured to the object's *origin*, but the model extends up to its radius around it. An object whose origin is 20,100 units away (cull radius 20,000) with a 401-unit radius already reaches inside the range, so culling by origin alone would make it vanish while part of it is still visible.
</details>

**7.** Why does `draw_object` use the translation `d = pos - eye` and the view *rotation*, instead of `view_mtx` with its translation?

<details><summary>Answer</summary>
With the full `view_mtx` the object's translation would be its world position, and the SDK's `CompMatrixLV` passes that translation through 16-bit registers; the file allows coordinates up to +-1,000,000. Subtracting the eye in 32-bit C first leaves `d` within 32000 on every axis (the cull guarantees it), and `R * d` is exactly the object's position in view space.
</details>

**8.** Start is tested with `input_held`. What do you see when you press it once?

<details><summary>Answer</summary>
While the button stays down, the state flips every frame (title, game, title, ...), because each frame's `held` is true again after the previous change. The state you end in depends on the parity of how many frames you held it. `input_pressed` is true only on the frame the button went down, so one press is one change.
</details>

**9.** The scene file has 3 shapes and 35 objects. How many `.SHP` files does `scene_load` read, and which entry of the file gives each object's radius?

<details><summary>Answer</summary>
Three, once each: every object that names shape 0 shares the loaded `PYLON.SHP`. The object's radius is the *table's* radius for its shape index times the object's `scale` (4.12), shifted right by 12. It is not taken from the `.SHP` and not a constant.
</details>
