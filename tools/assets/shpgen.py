#!/usr/bin/env python3
"""shpgen.py -- generate the book's original models and their JSON manifests.

  shpgen.py ship     OUT.SHP   [--manifest OUT.json]   hover-ship with all 8 primitive types
  shpgen.py pylon|arch|tower OUT.SHP [--manifest ...]  scenery objects (Chapter 33)
  shpgen.py --model-bin OUT.BIN [--manifest OUT.json]  simple convex ship for Chapter 29 (MODEL.BIN)

Conventions (Appendix E): +X right, +Y down, +Z forward; a face is front-facing when
its vertices run clockwise as seen from outside, so the cross product
(v1-v0)x(v2-v0) points INTO the solid; the stored normal points out.
Quads are in Z order: triangles (v0,v1,v2) and (v1,v3,v2).
"""
import argparse, hashlib, json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import formats as F, layout, tim

# ------------------------------------------------------------------ mesh builder

def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

def newell(pts):
    """Area vector of the loop. Quads (Z order) are traversed v0,v1,v3,v2."""
    loop = pts if len(pts) == 3 else [pts[0], pts[1], pts[3], pts[2]]
    n = (0, 0, 0)
    for i in range(len(loop)):
        c = _cross(loop[i], loop[(i + 1) % len(loop)])
        n = (n[0] + c[0], n[1] + c[1], n[2] + c[2])
    return n

def flip_order(nv): return [0, 2, 1] if nv == 3 else [1, 0, 3, 2]

class Mesh:
    def __init__(self, name):
        self.name = name; self.verts = []; self._vm = {}; self.normals = []; self._nm = {}; self.prims = []

    def _v(self, p):
        p = tuple(round(c) for c in p)
        if p not in self._vm:
            self._vm[p] = len(self.verts); self.verts.append(p)
        return self._vm[p]

    def _n(self, n):
        if n not in self._nm:
            self._nm[n] = len(self.normals); self.normals.append(n)
        return self._nm[n]

    def add(self, t, pts, colors, uv=None, tex=None, flags=0, inside=None, outward=None):
        """Add a primitive. pts: 3 or 4 points. The winding is fixed up so the face points away from `inside`
        (a point inside the solid) or along `outward` (a direction)."""
        nv, textured, gouraud = F.prim_traits(t)
        assert len(pts) == nv
        pts = [tuple(round(c) for c in p) for p in pts]
        nrm = newell(pts)
        if inside is not None:
            cen = tuple(sum(p[k] for p in pts) / nv for k in range(3))
            flip = _dot(nrm, _sub(cen, inside)) > 0       # area vector must point inward
        else:
            flip = _dot(nrm, outward) > 0
        order = flip_order(nv) if flip else list(range(nv))
        pts = [pts[i] for i in order]
        if gouraud: colors = [colors[i] for i in order]
        if uv: uv = [uv[i] for i in order]
        nrm = newell(pts)
        ln = math.sqrt(_dot(nrm, nrm)) or 1.0
        n12 = tuple(max(-4096, min(4096, round(-c / ln * 4096))) for c in nrm)
        p = dict(type=t, flags=flags, v=[self._v(q) for q in pts], n=self._n(n12), colors=list(colors))
        if textured:
            p["uv"] = uv; p["tex"] = tex
        self.prims.append(p)

    def box(self, c, h, kinds, colors, inside=None):
        """Axis-aligned box centre c, half-extents h. kinds/colors: dict face->type/colour; faces '+x','-x','+y','-y','+z','-z'."""
        (cx, cy, cz), (hx, hy, hz) = c, h
        def P(sx, sy, sz): return (cx + sx * hx, cy + sy * hy, cz + sz * hz)
        faces = {"+x": [P(1, -1, -1), P(1, -1, 1), P(1, 1, -1), P(1, 1, 1)],
                 "-x": [P(-1, -1, -1), P(-1, -1, 1), P(-1, 1, -1), P(-1, 1, 1)],
                 "+y": [P(-1, 1, -1), P(1, 1, -1), P(-1, 1, 1), P(1, 1, 1)],
                 "-y": [P(-1, -1, -1), P(1, -1, -1), P(-1, -1, 1), P(1, -1, 1)],
                 "+z": [P(-1, -1, 1), P(1, -1, 1), P(-1, 1, 1), P(1, 1, 1)],
                 "-z": [P(-1, -1, -1), P(1, -1, -1), P(-1, 1, -1), P(1, 1, -1)]}
        for k, t in kinds.items():
            col = colors[k]
            cols = col if isinstance(col, list) else [col]
            kw = {}
            if F.prim_traits(t)[1]:
                kw = dict(uv=[(0, 0), (31, 0), (0, 63), (31, 63)], tex=0)
            self.add(t, faces[k], cols, inside=c, **kw)

    def build(self) -> bytes:
        return F.build_shp(self.name, self.verts, self.normals, self.prims)

# ------------------------------------------------------------------ the ship

RING = lambda z, s: [(0, -70 * s, z), (-140 * s, 10 * s, z), (0, 40 * s, z), (140 * s, 10 * s, z)]   # T, L, B, R
EDGES = [(0, 1), (1, 2), (2, 3), (3, 0)]
QUV = [(0, 0), (63, 0), (0, 63), (63, 63)]
TUV = [(0, 63), (63, 63), (32, 0)]

def shade(base, k):
    return tuple(max(0, min(255, int(c * k))) for c in base)

def make_ship() -> Mesh:
    m = Mesh("SHIP")
    c0 = (0, -10, 0)
    nose, r1, r2, r3, tail = (0, 0, 300), RING(100, 0.6), RING(-60, 1.0), RING(-150, 0.8), (0, 5, -210)
    neutral = (128, 128, 128)
    # nose: two top tris Gouraud-textured (GT3), two bottom Gouraud (G3)
    for e, (i, j) in enumerate(EDGES):
        pts = [nose, r1[i], r1[j]]
        if e in (0, 3):
            m.add("GT3", pts, [(200, 200, 210), (150, 150, 170), (150, 150, 170)], uv=TUV, tex=e // 3, inside=c0)
        else:
            m.add("G3", pts, [(120, 130, 150), (70, 75, 90), (70, 75, 90)], inside=c0)
    # r1 -> r2 quads
    for e, (i, j) in enumerate(EDGES):
        pts = [r1[i], r1[j], r2[i], r2[j]]
        if e == 0:   m.add("GT4", pts, [(190, 190, 200), (150, 150, 170), (170, 170, 190), (130, 130, 150)], uv=QUV, tex=0, inside=c0)
        elif e == 3: m.add("GT4", pts, [(150, 150, 170), (190, 190, 200), (130, 130, 150), (170, 170, 190)], uv=QUV, tex=1, inside=c0)
        elif e == 1: m.add("G4", pts, [(90, 100, 120), (60, 64, 80), (80, 90, 110), (50, 54, 70)], inside=c0)
        else:        m.add("F4", pts, [(70, 76, 96)], inside=c0)
    # r2 -> r3 quads: two FT4, two F4
    for e, (i, j) in enumerate(EDGES):
        pts = [r2[i], r2[j], r3[i], r3[j]]
        if e in (0, 3): m.add("FT4", pts, [neutral], uv=QUV, tex=1 - e // 3, inside=c0)
        else:           m.add("F4", pts, [shade((120, 130, 150), 1.0 - 0.25 * (e == 2))], inside=c0)
    # tail: two FT3, two F3
    for e, (i, j) in enumerate(EDGES):
        pts = [r3[i], r3[j], tail]
        if e in (0, 3): m.add("FT3", pts, [neutral], uv=TUV, tex=e // 3, inside=c0)
        else:           m.add("F3", pts, [(60, 64, 80)], inside=c0)
    # wings (double sided, planar quads): left textured, right Gouraud
    lw = [(-120, 8, 60), (-330, 20, -110), (-120, 8, -120), (-330, 20, -150)]
    rw = [(-x, y, z) for x, y, z in lw]
    m.add("FT4", lw, [neutral], uv=[(0, 0), (63, 0), (0, 31), (63, 31)], tex=2, flags=F.F_DOUBLE_SIDED, outward=(0, -1, 0))
    m.add("G4", rw, [(60, 80, 140), (200, 40, 60), (60, 80, 140), (200, 40, 60)], flags=F.F_DOUBLE_SIDED, outward=(0, -1, 0))
    # tail fin (double sided, textured triangle)
    m.add("FT3", [(0, -70, -100), (0, -190, -210), (0, -55, -210)], [neutral], uv=TUV, tex=1, flags=F.F_DOUBLE_SIDED, outward=(1, 0, 0))
    # canopy: semi-transparent Gouraud pyramid
    ap, base = (0, -95, 0), [(-35, -55, 50), (35, -55, 50), (35, -60, -40), (-35, -60, -40)]
    for i in range(4):
        m.add("G3", [ap, base[i], base[(i + 1) % 4]], [(220, 240, 255), (40, 90, 170), (40, 90, 170)],
              flags=F.F_SEMI_TRANS, inside=(0, -65, 5))
    # engine pods: flat boxes with a Gouraud glowing back face
    for sx in (-1, 1):
        c = (sx * 100, 15, -185)
        kinds = {"+x": "F4", "-x": "F4", "+y": "F4", "-y": "F4", "-z": "G4"}
        glow = [(255, 200, 80), (255, 120, 30), (255, 120, 30), (200, 40, 10)]
        m.box(c, (22, 22, 45), kinds, {"+x": (90, 96, 110), "-x": (90, 96, 110), "+y": (50, 54, 66), "-y": (110, 116, 130), "-z": glow})
    return m

SHIP_TEXTURES = ["hull_a", "hull_b", "wing"]

# ------------------------------------------------------------------ scenery

def make_pylon() -> Mesh:
    m = Mesh("PYLON"); c = (0, -200, 0)
    for k in range(4):
        a, b = [(-40, 0, -40), (40, 0, -40), (40, 0, 40), (-40, 0, 40)][k], [(-40, 0, -40), (40, 0, -40), (40, 0, 40), (-40, 0, 40)][(k + 1) % 4]
        top = lambda p: (p[0] * 0.5, -400, p[2] * 0.5)
        m.add("FT4", [top(a), top(b), a, b], [(128, 128, 128)], uv=[(0, 0), (31, 0), (0, 63), (31, 63)], tex=0, inside=c)
    m.add("G4", [(-20, -400, -20), (20, -400, -20), (-20, -400, 20), (20, -400, 20)],
          [(255, 240, 160), (255, 160, 60), (255, 160, 60), (255, 100, 30)], outward=(0, -1, 0))
    return m

def make_arch() -> Mesh:
    m = Mesh("ARCH")
    legs = {"+x": "F4", "-x": "F4", "+z": "F4", "-z": "F4", "-y": "G4"}
    for sx in (-1, 1):
        m.box((sx * 700, -250, 0), (50, 250, 50), legs,
              {"+x": (80, 86, 100), "-x": (80, 86, 100), "+z": (110, 116, 130), "-z": (110, 116, 130),
               "-y": [(0, 220, 240), (0, 140, 200), (0, 140, 200), (0, 80, 160)]})
    m.box((0, -550, 0), (750, 50, 50), {"+z": "G4", "-z": "G4", "-y": "F4", "+y": "F4"},
          {"+z": [(0, 220, 240), (0, 220, 240), (230, 40, 170), (230, 40, 170)],
           "-z": [(0, 220, 240), (0, 220, 240), (230, 40, 170), (230, 40, 170)],
           "-y": (60, 70, 90), "+y": (40, 46, 60)})
    return m

def make_tower() -> Mesh:
    m = Mesh("TOWER")
    kinds = {k: "FT4" for k in ("+x", "-x", "+z", "-z")}
    m.box((0, -600, 0), (90, 600, 90), kinds, {k: (128, 128, 128) for k in kinds})
    apex, base = (0, -1500, 0), [(-100, -1200, -100), (100, -1200, -100), (100, -1200, 100), (-100, -1200, 100)]
    for i in range(4):
        m.add("F3", [apex, base[i], base[(i + 1) % 4]], [(220, 60 + 30 * i, 40)], inside=(0, -1300, 0))
    return m

OBJECTS = {"ship": make_ship, "pylon": make_pylon, "arch": make_arch, "tower": make_tower}
OBJECT_SET = {"ship": "ship", "pylon": "props", "arch": None, "tower": "props"}
PROP_TEX = {"pylon": 0, "tower": 1}       # texture index in PROPS.TPK used by each object (tex field must match)

def fix_prop_textures(name, m):
    """pylon/tower use texture index 0/1 of PROPS.TPK."""
    if name in PROP_TEX:
        for p in m.prims:
            if "tex" in p: p["tex"] = PROP_TEX[name]

# ------------------------------------------------------------------ manifests

def sha(b): return hashlib.sha256(b).hexdigest()

def shp_manifest(name, data, set_name):
    d = F.parse_shp(data)
    counts = {t: 0 for t in F.PRIM_TYPES}
    for p in d["prims"]: counts[p["type"]] += 1
    man = dict(file="%s.SHP" % name, name=d["name"], size=len(data), sha256=sha(data),
               vertex_count=len(d["vertices"]), normal_count=len(d["normals"]), prim_count=len(d["prims"]),
               prim_counts=counts, texture_count=d["texture_count"], bbox=list(d["bbox"]),
               first_vertex=list(d["vertices"][0]), last_vertex=list(d["vertices"][-1]))
    textures = []
    if d["texture_count"]:
        for i in range(d["texture_count"]):
            pl = layout.placement(set_name, i)
            u0, v0 = tim.uv_origin(pl["x"], pl["y"], pl["bpp"])
            textures.append(dict(index=i, name=pl["name"], bpp=pl["bpp"], x=pl["x"], y=pl["y"], clut_x=pl["clut_x"],
                                 clut_y=pl["clut_y"], uv_origin=[u0, v0],
                                 cba=tim.cba(pl["clut_x"], pl["clut_y"]), tsb_abr0=tim.tsb(pl["x"], pl["y"], pl["bpp"], 0)))
    man["texture_set"] = set_name if textures else None
    man["textures"] = textures
    prims = []
    for i, p in enumerate(d["prims"]):
        if "tex" in p:
            t = textures[p["tex"]]
            abr = 0
            prims.append(dict(index=i, type=p["type"], tex=p["tex"], tsb=tim.tsb(t["x"], t["y"], t["bpp"], abr), cba=t["cba"],
                              uv_abs=[[u + t["uv_origin"][0], v + t["uv_origin"][1]] for u, v in p["uv"]]))
    man["textured_prims"] = prims
    return man

def model_bin_manifest(data):
    d = F.parse_model_bin(data)
    return dict(file="MODEL.BIN", size=len(data), sha256=sha(data), vertex_count=len(d["verts"]), face_count=len(d["faces"]),
                triangles=sum(1 for i, _ in d["faces"] if len(i) == 3), quads=sum(1 for i, _ in d["faces"] if len(i) == 4),
                first_vertex=list(d["verts"][0]), last_vertex=list(d["verts"][-1]),
                first_face=dict(indices=list(d["faces"][0][0]), color=list(d["faces"][0][1])),
                last_face=dict(indices=list(d["faces"][-1][0]), color=list(d["faces"][-1][1])),
                header_hex=data[:12].hex())

# ------------------------------------------------------------------ MODEL.BIN

def make_model_bin() -> bytes:
    """Convex ship (nose + 3 rings + cap): 13 vertices, 13 faces (4+4+4 tris/quads, 1 cap quad)."""
    c0 = (0, -10, 0)
    nose, r1, r2, r3 = (0, 0, 300), RING(100, 0.6), RING(-60, 1.0), RING(-150, 0.8)
    m = Mesh("MODEL")
    def faces():
        for i, j in EDGES: yield [nose, r1[i], r1[j]]
        for i, j in EDGES: yield [r1[i], r1[j], r2[i], r2[j]]
        for i, j in EDGES: yield [r2[i], r2[j], r3[i], r3[j]]
        yield [r3[0], r3[1], r3[3], r3[2]]
    # vertices in a fixed order: nose, r1 (T L B R), r2, r3
    for p in [nose] + r1 + r2 + r3: m._v(p)
    out = []
    for pts in faces():
        t = "F3" if len(pts) == 3 else "F4"
        before = len(m.prims)
        m.add(t, pts, [(0, 0, 0)], inside=c0)
        p = m.prims[before]
        n = m.normals[p["n"]]
        k = 0.45 + 0.55 * max(0.0, min(1.0, 0.5 - 0.5 * n[1] / 4096 + 0.35 * n[2] / 4096))
        col = tuple(int(c * k) for c in (200, 210, 230))
        out.append((tuple(p["v"]), col))
    return F.build_model_bin(m.verts, out)

# ------------------------------------------------------------------ CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", nargs="?", choices=list(OBJECTS))
    ap.add_argument("out")
    ap.add_argument("--model-bin", action="store_true")
    ap.add_argument("--manifest")
    a = ap.parse_args(argv)
    if a.model_bin:
        data = make_model_bin(); man = model_bin_manifest(data)
    else:
        if not a.what: ap.error("name an object (ship, pylon, arch, tower) or use --model-bin")
        m = OBJECTS[a.what](); fix_prop_textures(a.what, m)
        data = m.build(); man = shp_manifest(a.what.upper(), data, OBJECT_SET[a.what] or "props")
    Path(a.out).write_bytes(data)
    if a.manifest:
        Path(a.manifest).write_text(json.dumps(man, indent=2, sort_keys=True) + "\n")
    print(f"{a.out}: {len(data)} bytes")

if __name__ == "__main__":
    main()
