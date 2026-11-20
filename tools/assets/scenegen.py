#!/usr/bin/env python3
"""scenegen.py -- generate SCENE.BIN (landscape objects around a track) and a JSON manifest.

  scenegen.py TRACK.TRK OUT.BIN [--manifest OUT.json]

Objects: pylons every eighth section (i % 8 == 4) on both sides of the road, an arch over the start
line, towers well outside the circuit. Rotation is yaw only: ry = atan2(hx, hz) in
4096ths of a turn, so the model's +Z axis points along heading (sin ry, 0, cos ry).
"""
import argparse, hashlib, json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import formats as F, shpgen

CULL_RADIUS = 20000

def yaw4096(hx, hz): return round(math.atan2(hx, hz) / (2 * math.pi) * 4096) % 4096

def shape_radius(maker):
    m = maker(); shpgen.fix_prop_textures(m.name, m)
    return math.ceil(max(math.sqrt(x * x + y * y + z * z) for x, y, z in m.verts))

def generate(trk_bytes):
    trk = F.parse_trk(trk_bytes)
    shapes = [("PYLON.SHP", shape_radius(shpgen.make_pylon)), ("ARCH.SHP", shape_radius(shpgen.make_arch)),
              ("TOWER.SHP", shape_radius(shpgen.make_tower))]
    objs = []
    def obj(shape, pos, ry, flags=0):
        objs.append(dict(shape=shape, flags=flags, pos=tuple(pos), rot=(0, ry, 0), scale=4096))
    secs = trk["sections"]
    for i, s in enumerate(secs):
        f, r = s["forward"], s["right"]
        ry = yaw4096(f[0], f[2])
        if i == trk["start_section"]:
            obj(1, s["centre"], ry, F.OBJ_ALWAYS_DRAW)
        if i % 8 == 4:
            for side in (-1, 1):
                off = side * 1000
                obj(0, (s["centre"][0] + r[0] * off // 4096, s["centre"][1] + r[1] * off // 4096, s["centre"][2] + r[2] * off // 4096), ry)
    b = trk["bbox"]
    cx, cz = (b[0] + b[3]) // 2, (b[2] + b[5]) // 2
    hx, hz = (b[3] - b[0]) // 2 + 5000, (b[5] - b[2]) // 2 + 5000
    for k in range(6):
        t = 2 * math.pi * (k + 0.5) / 6
        obj(2, (cx + round(hx * math.cos(t)), 0, cz + round(hz * math.sin(t))), yaw4096(-math.cos(t), -math.sin(t)))
    return F.build_scene(shapes, objs, CULL_RADIUS)

def manifest(data):
    d = F.parse_scene(data)
    per = [sum(1 for o in d["objects"] if o["shape"] == i) for i in range(len(d["shapes"]))]
    xs, ys, zs = zip(*[o["pos"] for o in d["objects"]])
    return dict(file="SCENE.BIN", size=len(data), sha256=hashlib.sha256(data).hexdigest(), object_count=len(d["objects"]),
                shape_count=len(d["shapes"]), shapes=[dict(name=n, radius=r, count=c) for (n, r), c in zip(d["shapes"], per)],
                cull_radius=d["cull_radius"], pos_bbox=[min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)],
                objects=[dict(index=i, shape=o["shape"], flags=o["flags"], pos=list(o["pos"]), rot=list(o["rot"]), scale=o["scale"])
                         for i, o in enumerate(d["objects"])])

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trk"); ap.add_argument("out"); ap.add_argument("--manifest")
    a = ap.parse_args(argv)
    data = generate(Path(a.trk).read_bytes())
    Path(a.out).write_bytes(data)
    if a.manifest:
        Path(a.manifest).write_text(json.dumps(manifest(data), indent=1, sort_keys=True) + "\n")
    print(f"{a.out}: {len(data)} bytes")

if __name__ == "__main__":
    main()
