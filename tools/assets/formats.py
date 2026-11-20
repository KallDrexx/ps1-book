"""Writers and reference parsers for the book's own binary formats (Appendix E):
MODEL.BIN, .SHP, .TPK, .TRK, SCENE.BIN.

Everything is little-endian unless stated (MODEL.BIN's header counts are big-endian
by design). The parsers validate strictly and raise FormatError. The selftest does
NOT use these parsers: it has independent ones written straight from the appendix.
"""
import struct, zlib
import lzss

class FormatError(ValueError):
    pass

def _check(cond, msg):
    if not cond:
        raise FormatError(msg)

def name16(s: str) -> bytes:
    b = s.encode("ascii")
    _check(len(b) <= 15, "name longer than 15 characters")
    return b.ljust(16, b"\0")

def cstr(b: bytes) -> str:
    return b.split(b"\0")[0].decode("ascii")

def pad4(b: bytes) -> bytes:
    return b + bytes(-len(b) % 4)

# ============================================================== MODEL.BIN
MODEL_MAGIC = b"MDL1"
NO_INDEX = 0xFF                 # face index 3 == 0xFF -> triangle

def build_model_bin(verts, faces) -> bytes:
    """verts: [(x,y,z)] int16; faces: [((i0,i1,i2[,i3]), (r,g,b))]."""
    _check(len(verts) <= 255, "MODEL.BIN holds at most 255 vertices")
    out = bytearray(MODEL_MAGIC + struct.pack(">I", len(verts)))
    for x, y, z in verts:
        out += struct.pack("<hhhh", x, y, z, 0)
    out += struct.pack(">I", len(faces))
    for idx, (r, g, b) in faces:
        i = list(idx) + ([NO_INDEX] if len(idx) == 3 else [])
        _check(all(0 <= k < len(verts) for k in idx), "index out of range")
        out += bytes(i) + bytes((r, g, b, 0))
    return bytes(out)

def parse_model_bin(d: bytes):
    _check(d[:4] == MODEL_MAGIC, "bad MODEL.BIN magic")
    nv = struct.unpack_from(">I", d, 4)[0]
    pos = 8
    verts = [struct.unpack_from("<hhh", d, pos + 8 * i) for i in range(nv)]
    pos += 8 * nv
    nf = struct.unpack_from(">I", d, pos)[0]; pos += 4
    _check(len(d) == pos + 8 * nf, "MODEL.BIN size mismatch")
    faces = []
    for i in range(nf):
        r = d[pos + 8 * i:pos + 8 * i + 8]
        idx = tuple(r[:3]) if r[3] == NO_INDEX else tuple(r[:4])
        _check(all(k < nv for k in idx), "index out of range")
        faces.append((idx, tuple(r[4:7])))
    return dict(verts=verts, faces=faces)

# ============================================================== .TPK
TPK_MAGIC = b"TPK1"

def build_tpk(tims) -> bytes:
    _check(0 < len(tims) <= 255, "1..255 textures")
    for t in tims:
        _check(len(t) % 4 == 0, "each TIM must be a multiple of 4 bytes")
    raw = b"".join(tims)
    comp = lzss.compress(raw)
    hdr = TPK_MAGIC + struct.pack("<IIII", len(tims), len(raw), len(comp), zlib.crc32(raw) & 0xFFFFFFFF)
    hdr += struct.pack("<%dI" % len(tims), *[len(t) for t in tims])
    return pad4(hdr + comp)

def parse_tpk(d: bytes):
    _check(d[:4] == TPK_MAGIC, "bad TPK magic")
    n, raw_size, comp_size, crc = struct.unpack_from("<IIII", d, 4)
    sizes = list(struct.unpack_from("<%dI" % n, d, 20))
    _check(sum(sizes) == raw_size, "size table does not add up")
    start = 20 + 4 * n
    comp = d[start:start + comp_size]
    _check(len(comp) == comp_size and len(d) - start - comp_size < 4, "compressed size mismatch")
    raw = lzss.decompress(comp, raw_size)
    _check(zlib.crc32(raw) & 0xFFFFFFFF == crc, "CRC32 mismatch")
    out, pos = [], 0
    for s in sizes:
        out.append(raw[pos:pos + s]); pos += s
    return dict(count=n, raw_size=raw_size, comp_size=comp_size, crc32=crc, sizes=sizes, tims=out)

# ============================================================== .SHP
SHP_MAGIC = b"SHP1"
PRIM_TYPES = ["F3", "F4", "G3", "G4", "FT3", "FT4", "GT3", "GT4"]
PRIM_SIZE = {"F3": 16, "F4": 20, "G3": 24, "G4": 32, "FT3": 24, "FT4": 32, "GT3": 32, "GT4": 44}
F_DOUBLE_SIDED, F_SEMI_TRANS, F_UNLIT = 1, 2, 4

def prim_traits(t: str):
    """(vertex count, textured, gouraud)"""
    return (3 if t.endswith("3") else 4, t.startswith(("FT", "GT")), t.startswith("G"))

def build_shp(name, verts, normals, prims, flat_bbox=None) -> bytes:
    """verts [(x,y,z)], normals [(x,y,z) 4.12], prims [dict(type, flags, v, n, colors[(r,g,b)], uv[(u,v)], tex)]."""
    vb = b"".join(struct.pack("<hhhh", x, y, z, 0) for x, y, z in verts)
    nb = b"".join(struct.pack("<hhhh", x, y, z, 0) for x, y, z in normals)
    pb = bytearray()
    for p in prims:
        t = p["type"]
        nv, tex, gour = prim_traits(t)
        rec = bytearray(struct.pack("<BBH", PRIM_TYPES.index(t), p.get("flags", 0), PRIM_SIZE[t]))
        _check(len(p["v"]) == nv, "wrong vertex count for " + t)
        rec += struct.pack("<%dH" % nv, *p["v"])
        rec += struct.pack("<H", p["n"])
        if nv == 4:
            rec += b"\0\0"
        if tex:
            for u, v in p["uv"]:
                rec += bytes((u, v))
            rec += struct.pack("<H", p["tex"])
            if nv == 4:
                rec += b"\0\0"
        cols = p["colors"]
        _check(len(cols) == (nv if gour else 1), "wrong colour count for " + t)
        for r, g, b in cols:
            rec += bytes((r, g, b, 0))
        _check(len(rec) == PRIM_SIZE[t], f"internal: {t} record is {len(rec)} bytes")
        pb += rec
    xs, ys, zs = zip(*verts)
    bbox = (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))
    ntex = max([p["tex"] + 1 for p in prims if "tex" in p and prim_traits(p["type"])[1]] or [0])
    off_v = 0x40; off_n = off_v + len(vb); off_p = off_n + len(nb)
    total = off_p + len(pb)
    hdr = SHP_MAGIC + struct.pack("<I", total) + name16(name)
    hdr += struct.pack("<HHHH", len(verts), len(normals), len(prims), ntex)
    hdr += struct.pack("<IIII", off_v, off_n, off_p, len(pb))
    hdr += struct.pack("<6h", *bbox) + bytes(4)
    assert len(hdr) == 0x40
    return hdr + vb + nb + bytes(pb)

def parse_shp(d: bytes):
    _check(d[:4] == SHP_MAGIC, "bad SHP magic")
    total = struct.unpack_from("<I", d, 4)[0]
    _check(total == len(d), "file_size mismatch")
    name = cstr(d[8:24])
    nv, nn, npr, ntex = struct.unpack_from("<HHHH", d, 0x18)
    off_v, off_n, off_p, size_p = struct.unpack_from("<IIII", d, 0x20)
    bbox = struct.unpack_from("<6h", d, 0x30)
    _check(off_n == off_v + 8 * nv and off_p == off_n + 8 * nn and off_p + size_p == len(d), "section offsets inconsistent")
    verts = [struct.unpack_from("<hhh", d, off_v + 8 * i) for i in range(nv)]
    normals = [struct.unpack_from("<hhh", d, off_n + 8 * i) for i in range(nn)]
    prims, pos = [], off_p
    for _ in range(npr):
        ty, fl, sz = struct.unpack_from("<BBH", d, pos)
        _check(ty < 8, "bad primitive type")
        t = PRIM_TYPES[ty]
        _check(sz == PRIM_SIZE[t], f"{t} size field {sz}")
        nvv, tex, gour = prim_traits(t)
        p = dict(type=t, flags=fl)
        q = pos + 4
        p["v"] = struct.unpack_from("<%dH" % nvv, d, q); q += 2 * nvv
        p["n"] = struct.unpack_from("<H", d, q)[0]; q += 2
        if nvv == 4: q += 2
        _check(all(i < nv for i in p["v"]) and p["n"] < nn, "index out of range")
        if tex:
            p["uv"] = [(d[q + 2 * i], d[q + 2 * i + 1]) for i in range(nvv)]; q += 2 * nvv
            p["tex"] = struct.unpack_from("<H", d, q)[0]; q += 2
            _check(p["tex"] < ntex, "texture index >= texture_count")
            if nvv == 4: q += 2
        p["colors"] = [tuple(d[q + 4 * i:q + 4 * i + 3]) for i in range(nvv if gour else 1)]
        q += 4 * (nvv if gour else 1)
        _check(q == pos + sz, "internal parser error")
        prims.append(p); pos += sz
    return dict(name=name, vertices=verts, normals=normals, prims=prims, texture_count=ntex, bbox=bbox)

# ============================================================== .TRK
TRK_MAGIC = b"TRK1"
TRK_HEADER = 0x60
FACE_FLOOR, FACE_WALL, FACE_BOOST, FACE_START, FACE_FLIP_H = 1, 2, 4, 8, 16
SEC_JUNCTION, SEC_START = 1, 2
TRK_LOOP = 1
NO_TEXTURE = 0xFF

def build_trk(name, verts, faces, sections, vis, start_section, total_length, texture_count, loop=True) -> bytes:
    """verts [(x,y,z) int32]; faces [dict(v[4], flags, tex, uv[4], color)];
    sections [dict(centre, half_width, length, forward, right, up, first_face, face_count, next, prev, flags,
                   edges(left_start,right_start,left_end,right_end))]; vis [[section indices] per section]."""
    vb = b"".join(struct.pack("<iii", *v) for v in verts)
    fb = bytearray()
    for f in faces:
        fb += struct.pack("<4HHBB", *f["v"], f["flags"], f["tex"], 0)
        for u, v in f["uv"]:
            fb += bytes((u, v))
        fb += bytes(f["color"]) + b"\0"
    visflat, sb = [], bytearray()
    for s, lst in zip(sections, vis):
        first = len(visflat); visflat += lst
        sb += struct.pack("<iii", *s["centre"]) + struct.pack("<HH", s["half_width"], s["length"])
        for k in ("forward", "right", "up"):
            sb += struct.pack("<hhhh", *s[k], 0)
        sb += struct.pack("<HHHHH", s["first_face"], s["face_count"], s["next"], s["prev"], s["flags"])
        sb += struct.pack("<HH", first, len(lst)) + struct.pack("<4H", *s["edges"]) + bytes(2)
    assert len(sb) == 64 * len(sections), len(sb)
    visb = pad4(struct.pack("<%dH" % len(visflat), *visflat))
    off_v = TRK_HEADER; off_f = off_v + len(vb); off_s = off_f + len(fb); off_vis = off_s + len(sb)
    total = off_vis + len(visb)
    xs, ys, zs = zip(*verts)
    hdr = TRK_MAGIC + struct.pack("<I", total) + name16(name)
    hdr += struct.pack("<HHHH", len(sections), len(verts), len(faces), len(visflat))
    hdr += struct.pack("<HHHH", start_section, TRK_LOOP if loop else 0, texture_count, 0)
    hdr += struct.pack("<IIII", off_v, off_f, off_s, off_vis) + struct.pack("<II", total_length, 0)
    hdr += struct.pack("<6i", min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)) + bytes(8)
    assert len(hdr) == TRK_HEADER, len(hdr)
    return hdr + vb + bytes(fb) + bytes(sb) + visb

def parse_trk(d: bytes):
    _check(d[:4] == TRK_MAGIC, "bad TRK magic")
    _check(struct.unpack_from("<I", d, 4)[0] == len(d), "file_size mismatch")
    name = cstr(d[8:24])
    ns, nv, nf, nvis = struct.unpack_from("<HHHH", d, 0x18)
    start, flags, ntex, _ = struct.unpack_from("<HHHH", d, 0x20)
    off_v, off_f, off_s, off_vis = struct.unpack_from("<IIII", d, 0x28)
    total_length = struct.unpack_from("<I", d, 0x38)[0]
    bbox = struct.unpack_from("<6i", d, 0x40)
    _check(off_f == off_v + 12 * nv and off_s == off_f + 24 * nf and off_vis == off_s + 64 * ns, "section offsets inconsistent")
    _check(off_vis + 2 * nvis + (nvis & 1) * 2 == len(d), "vis list size mismatch")
    verts = [struct.unpack_from("<iii", d, off_v + 12 * i) for i in range(nv)]
    faces = []
    for i in range(nf):
        o = off_f + 24 * i
        v = struct.unpack_from("<4H", d, o)
        fl, tex = struct.unpack_from("<HB", d, o + 8)
        uv = [(d[o + 12 + 2 * k], d[o + 13 + 2 * k]) for k in range(4)]
        _check(all(x < nv for x in v), "face index out of range")
        faces.append(dict(v=v, flags=fl, tex=tex, uv=uv, color=tuple(d[o + 20:o + 23])))
    visflat = list(struct.unpack_from("<%dH" % nvis, d, off_vis))
    secs = []
    for i in range(ns):
        o = off_s + 64 * i
        s = dict(centre=struct.unpack_from("<iii", d, o), half_width=struct.unpack_from("<H", d, o + 12)[0],
                 length=struct.unpack_from("<H", d, o + 14)[0])
        for k, off in (("forward", 16), ("right", 24), ("up", 32)):
            s[k] = struct.unpack_from("<hhh", d, o + off)
        (s["first_face"], s["face_count"], s["next"], s["prev"], s["flags"],
         vf, vc) = struct.unpack_from("<7H", d, o + 40)
        s["edges"] = struct.unpack_from("<4H", d, o + 54)
        s["vis"] = visflat[vf:vf + vc]
        _check(s["next"] < ns and s["prev"] < ns and s["first_face"] + s["face_count"] <= nf, "bad section links")
        secs.append(s)
    return dict(name=name, vertices=verts, faces=faces, sections=secs, start_section=start, flags=flags,
                texture_count=ntex, total_length=total_length, bbox=bbox)

# ============================================================== SCENE.BIN
SCN_MAGIC = b"SCN1"
OBJ_ALWAYS_DRAW = 1

def build_scene(shapes, objects, cull_radius) -> bytes:
    """shapes [(filename<=11 chars, radius)], objects [dict(shape, flags, pos(x,y,z), rot(rx,ry,rz), scale)]."""
    sb = b"".join(name.encode("ascii").ljust(12, b"\0") + struct.pack("<I", r) for name, r in shapes)
    ob = b"".join(struct.pack("<HHiii3hH", o["shape"], o["flags"], *o["pos"], *o["rot"], o["scale"]) for o in objects)
    off_s = 0x20; off_o = off_s + len(sb)
    total = off_o + len(ob)
    hdr = SCN_MAGIC + struct.pack("<IHHIIIII", total, len(shapes), len(objects), off_s, off_o, cull_radius, 0, 0)
    assert len(hdr) == 0x20
    return hdr + sb + ob

def parse_scene(d: bytes):
    _check(d[:4] == SCN_MAGIC, "bad SCENE magic")
    total, ns, no, off_s, off_o, cull, _, _ = struct.unpack_from("<IHHIIIII", d, 4)
    _check(total == len(d) and off_o == off_s + 16 * ns and off_o + 24 * no == total, "layout mismatch")
    shapes = [(cstr(d[off_s + 16 * i:off_s + 16 * i + 12]), struct.unpack_from("<I", d, off_s + 16 * i + 12)[0]) for i in range(ns)]
    objs = []
    for i in range(no):
        sh, fl, x, y, z, rx, ry, rz, sc = struct.unpack_from("<HHiii3hH", d, off_o + 24 * i)
        _check(sh < ns, "shape index out of range")
        objs.append(dict(shape=sh, flags=fl, pos=(x, y, z), rot=(rx, ry, rz), scale=sc))
    return dict(shapes=shapes, objects=objs, cull_radius=cull)
