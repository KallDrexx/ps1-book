# Chapter 14 Quiz

**1. List the four untextured polygon commands and their word counts.**
<details><summary>Answer</summary>
`20h` flat triangle (4 words), `28h` flat quad (5), `30h` Gouraud triangle (6), `38h` Gouraud quad (8). Bit 3 = quad (+08h), bit 4 = Gouraud (+10h).
</details>

**2. In which words of a `38h` packet does the command byte appear?**
<details><summary>Answer</summary>
Only in word 1, the first color word (`38BBGGRR`). The other three color words are `00BBGGRR`. Word layout: c1, v1, c2, v2, c3, v3, c4, v4.
</details>

**3. You hold x = -90 and y = 100 in registers. Which word do you send, and what goes wrong if you skip the mask on x?**
<details><summary>Answer</summary>
`(100 << 16) | (-90 & 0xFFFF)` = `0x0064FFA6`. Without the mask, `-90` is `0xFFFFFFA6`, its upper 16 bits are all ones and OR-ing it in turns the whole y half into `0xFFFF`: y is destroyed.
</details>

**4. A quad has corners top-left, top-right, bottom-left, bottom-right. In which order do you send them, and which triangles does the GPU draw?**
<details><summary>Answer</summary>
Z order: top-left, top-right, bottom-left, bottom-right (v1 v2 v3 v4). The GPU draws triangles v1 v2 v3 and v2 v3 v4, sharing the diagonal v2-v3.
</details>

**5. Does it matter whether a triangle's vertices go clockwise or counterclockwise?**
<details><summary>Answer</summary>
No. The GPU draws both; it does no back-face culling.
</details>

**6. What color is the center of a Gouraud triangle with vertex colors red, green, blue? A pixel very near the red vertex?**
<details><summary>Answer</summary>
The center has weights 1/3 each: about (85, 85, 85) gray. Near the red vertex the weight of red is close to 1, so it is nearly pure red.
</details>

**7. The drawing offset is (160, 120) and a vertex is (-90, -100). Where does it land? Does the fill rectangle (`02h`) use the offset?**
<details><summary>Answer</summary>
At screen (70, 20). The fill rectangle is a VRAM operation: it ignores the offset (and the drawing area).
</details>

**8. What happens to a triangle whose vertices are 1200 pixels apart horizontally?**
<details><summary>Answer</summary>
It is dropped entirely: the limit is 1023 horizontally and 511 vertically between vertices. It is not clipped to the drawing area. Engines split large polygons.
</details>

**9. How do you draw a 50% blend of a color over what is already on screen?**
<details><summary>Answer</summary>
Set bit 1 of the command byte (for example `2Ah` for a flat quad) and set `E1h` bits 5-6 to 0 (`B/2 + F/2`), keeping bit 10 set: `0xE1000400`. Modes 1, 2, 3 are `B+F`, `B-F`, `B+F/4`.
</details>
