"""Chapter 38 reference model: the exact metric, the nearest section by brute force, the window and the visibility list, in Python integers.
The verifier and the README's worked example use it; it is the specification of track_vis.h in executable form."""

import math

MAX_STEPS = 4
LOST = 4000


def d2(centre, pos):
    """The metric: squared 3D distance between the ship and a section centre (Python integers: no overflow)."""
    return sum((p - c) * (p - c) for p, c in zip(pos, centre))


def nearest(sections, pos):
    """Brute force: the smallest d2, the LOWEST index on a tie."""
    best, bd = -1, 0
    for i, s in enumerate(sections):
        d = d2(s["centre"], pos)
        if best < 0 or d < bd:
            best, bd = i, d
    return best


def update(sections, pos, cur, lost=LOST):
    """The incremental rule of track_vis.h: returns (section, used_brute_force)."""
    n = len(sections)
    if not 0 <= cur < n:
        return nearest(sections, pos), True
    cd = d2(sections[cur]["centre"], pos)
    for step in range(MAX_STEPS + 2):
        s = sections[cur]
        best, bd = cur, cd
        for c in (s["prev"], s["next"]):
            d = d2(sections[c]["centre"], pos)
            if d < bd or (d == bd and c < best):
                best, bd = c, d
        if best == cur:
            break
        cur, cd = best, bd
        if step == MAX_STEPS:
            return nearest(sections, pos), True      # the (MAX_STEPS + 1)th move: give up
    if cd > lost * lost:
        return nearest(sections, pos), True
    return cur, False


def window(n, s, ahead, behind):
    """(first, count) of the sections s - behind .. s + ahead along the loop; the whole track when that is n sections or more."""
    a, b = max(ahead, 0), max(behind, 0)
    c = a + b + 1
    if c >= n:
        return 0, n
    return (s - b) % n, c


def window_sections(n, s, ahead, behind):
    first, count = window(n, s, ahead, behind)
    return [(first + k) % n for k in range(count)]


def heading(dx, dz):
    """The whole-unit yaw (0 along +z, 1024 along +x) of a direction, from floats: good to a unit or two, which is all a camera needs."""
    return round(math.atan2(dx, dz) * 4096 / (2 * math.pi)) % 4096


if __name__ == "__main__":
    # README 6: the worked example on track 1 (built from the book's generator, seed 1).
    import sys, tempfile
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools" / "assets"))
    import mkassets, formats
    with tempfile.TemporaryDirectory() as tmp:
        files, _ = mkassets.build(Path(tmp), seed=1)
    secs = formats.parse_trk(files["TRACK.TRK"])["sections"]
    for pos in ([23829, -746, 487], [23953, -728, 1186]):
        print(pos, {i: d2(secs[i]["centre"], pos) for i in (111, 0, 1, 2)}, "nearest", nearest(secs, pos), "update from 0", update(secs, pos, 0))
    print("window(112, 2, 24, 4) =", window(112, 2, 24, 4), window_sections(112, 2, 24, 4)[:5], "...")
