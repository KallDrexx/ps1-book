#!/usr/bin/env python3
"""selftest.py -- prove the asset generators match Appendix E.

Runs every generator with fixed seeds, then validates the outputs with INDEPENDENT parsers
written in this file straight from the appendix (it does not import formats.py, tim.py,
lzss.py or vag.py for checking). Also: LZSS round trips, VAG encode->decode SNR, hash-stable
determinism, and that the appendix's hex dumps are what the generators really produce.

  selftest.py [-v]       prints a PASS/FAIL table, exit 1 on any failure
"""
import hashlib, json, math, os, random, struct, sys, tempfile, traceback, wave, zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent.parent
VERBOSE = "-v" in sys.argv

RESULTS = []
CHECKS = []

def check(name):
    def deco(fn):
        CHECKS.append((name, fn)); return fn
    return deco

def need(cond, msg):
    if not cond: raise AssertionError(msg)

# ============================================================ independent parsers (from Appendix E)

def lz_decode(comp, out_size):
    ring = bytearray(4096); r = 4078; out = bytearray(); i = 0
    while len(out) < out_size:
        flags = comp[i]; i += 1
        for bit in range(8):
            if len(out) >= out_size: break
            if flags >> bit & 1:
                c = comp[i]; i += 1
                out.append(c); ring[r] = c; r = (r + 1) % 4096
            else:
                lo, hi = comp[i], comp[i + 1]; i += 2
                pos = lo | ((hi & 0xF0) << 4); n = (hi & 15) + 3
                for k in range(n):
                    c = ring[(pos + k) % 4096]
                    out.append(c); ring[r] = c; r = (r + 1) % 4096
    need(len(out) == out_size, "overrun"); need(i == len(comp), "unused input")
    return bytes(out)

def tim_parse(d):
    need(struct.unpack_from("<I", d, 0)[0] == 0x10, "magic")
    flags = struct.unpack_from("<I", d, 4)[0]
    bpp = {0: 4, 1: 8, 2: 16, 3: 24}[flags & 3]
    need(flags & ~0xB == 0 and bool(flags & 8) == (bpp <= 8), "flags")
    pos, blocks = 8, []
    for _ in range(2 if flags & 8 else 1):
        bnum, x, y, w, h = struct.unpack_from("<IHHHH", d, pos)
        need(bnum == 12 + 2 * w * h, "bnum"); need(pos + bnum <= len(d), "short")
        blocks.append((x, y, w, h, d[pos + 12:pos + bnum])); pos += bnum
    need(pos == len(d), "trailing")
    return bpp, (blocks[0] if flags & 8 else None), blocks[-1]

def tim_pixels(d):
    """-> (w_px, h, [(r5,g5,b5,transparent)])  exact 5-bit values"""
    bpp, clut, img = tim_parse(d)
    x, y, w, h, data = img
    if bpp == 16:
        vals = struct.unpack("<%dH" % (w * h), data); wpx = w
        return wpx, h, [(v & 31, v >> 5 & 31, v >> 10 & 31, v == 0) for v in vals]
    pal = struct.unpack("<%dH" % (clut[2] * clut[3]), clut[4])
    if bpp == 8: idx = list(data); wpx = w * 2
    else:
        idx = []
        for b in data: idx += [b & 15, b >> 4]
        wpx = w * 4
    return wpx, h, [(pal[i] & 31, pal[i] >> 5 & 31, pal[i] >> 10 & 31, pal[i] == 0) for i in idx]

def tpk_parse(d):
    need(d[:4] == b"TPK1", "magic")
    n, raw_size, comp_size, crc = struct.unpack_from("<IIII", d, 4)
    sizes = struct.unpack_from("<%dI" % n, d, 20)
    need(sum(sizes) == raw_size, "sizes")
    off = 20 + 4 * n
    raw = lz_decode(d[off:off + comp_size], raw_size)
    need(zlib.crc32(raw) == crc, "crc")
    need(len(d) - off - comp_size in range(4), "file size")
    out, p = [], 0
    for s in sizes: out.append(raw[p:p + s]); p += s
    return out, dict(n=n, raw=raw_size, comp=comp_size, crc=crc, sizes=list(sizes))

F = [(0, 0), (60, 0), (115, -52), (98, -55), (122, -60)]
def adpcm_decode_stream(blocks):
    h1 = h2 = 0; samples = []; flagsl = []
    for bi in range(len(blocks) // 16):
        b = blocks[bi * 16:bi * 16 + 16]
        shift, filt, flags = b[0] & 15, b[0] >> 4, b[1]
        need(filt <= 4 and shift <= 12, "bad shift/filter")
        flagsl.append(flags)
        for i in range(28):
            byte = b[2 + i // 2]; n = byte >> 4 if i % 2 else byte & 15
            if n > 7: n -= 16
            v = (n << 12 >> shift) + ((h1 * F[filt][0] + h2 * F[filt][1] + 32) >> 6)
            v = max(-32768, min(32767, v)); samples.append(v); h2, h1 = h1, v
    return samples, flagsl

def vag_parse(d):
    need(d[:4] == b"VAGp", "magic")
    ver, res, size, rate = struct.unpack(">IIII", d[4:20])
    need(res == 0 and d[20:32] == bytes(12), "reserved")
    need(size == len(d) - 48 and size % 16 == 0, "size")
    return dict(version=ver, size=size, rate=rate, name=d[32:48].rstrip(b"\0").decode(), blocks=d[48:])

def sub(a, b): return tuple(x - y for x, y in zip(a, b))
def dot(a, b): return sum(x * y for x, y in zip(a, b))
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def area_vec(p):
    loop = p if len(p) == 3 else [p[0], p[1], p[3], p[2]]
    return cross(sub(loop[1], loop[0]), sub(loop[2], loop[0])) if len(p) == 3 else tuple(
        sum(cross(loop[i], loop[(i + 1) % 4])[k] for i in range(4)) for k in range(3))
def unit(a):
    l = math.sqrt(dot(a, a)); return tuple(x / l for x in a)

# ============================================================ shared context

class Ctx: pass
CTX = Ctx()

def build_assets(seed=1, keep_png=False):
    import mkassets
    d = Path(tempfile.mkdtemp(prefix="assets-selftest-"))
    files, man = mkassets.build(d, seed, keep_png)
    return d, files, man

# ============================================================ checks

@check("determinism: mkassets twice, identical hashes")
def _():
    d2, f2, _ = build_assets(1)
    same = all(CTX.files[k] == f2[k] for k in CTX.files) and set(CTX.files) == set(f2)
    need(same, "different output on the second run")
    d3, f3, _ = build_assets(2)
    need(any(f3[k] != CTX.files[k] for k in ("CRATE.TIM", "TRACK.TPK")), "seed has no effect on textures")
    import shutil; shutil.rmtree(d2, ignore_errors=True); shutil.rmtree(d3, ignore_errors=True)
    return f"{len(CTX.files)} files, seed 1 stable"

@check("lzss: random/edge round trips, independent decoder")
def _():
    import lzss
    rnd = random.Random(1234)
    cases = [b"", b"a", b"ab", b"abc", bytes(5000), b"abcabcabc" * 700, bytes(range(256)) * 20]
    cases += [bytes(rnd.randrange(256) for _ in range(n)) for n in (1, 17, 18, 19, 4095, 4096, 4097, 10000)]
    cases += [bytes(rnd.choice(b"ab ") for _ in range(30000)), bytes(rnd.randrange(4) for _ in range(20000))]
    for k in ("CRATE.TIM", "LOGO.TIM", "SKY16.TIM", "TRACK.TRK", "SHIP.SHP"):
        cases.append(CTX.files[k])
    cases.append(b"".join(CTX.tims))
    tot_in = tot_out = 0
    for c in cases:
        z = lzss.compress(c)
        need(lz_decode(z, len(c)) == c if c else z == b"", "independent decode mismatch (len %d)" % len(c))
        need(lzss.decompress(z, len(c)) == c, "reference decode mismatch")
        need(lzss.decompress(z) == c, "decode without size")
        tot_in += len(c); tot_out += len(z)
    need(len(lzss.compress(bytes(5000))) < 700, "zeros should compress well")
    # hand-made stream from the spec: 'A' literal, then 'AAA' via a reference to the ring slot holding 'A' (4078)
    need(lz_decode(bytes([0x01, 0x41, 0xEE, 0xF0]), 4) == b"AAAA", "spec example 1")
    # malformed streams are rejected
    for bad in (b"\x00\xEE", b"\xFF", b"\x01A\x00"):
        try: lzss.decompress(bad, 10); need(False, "accepted malformed input")
        except lzss.LzssError: pass
    return f"{len(cases)} cases, {tot_in} -> {tot_out} bytes"

@check("tim: every TIM parses, round-trips PNG pixels, VRAM rules")
def _():
    n = 0
    names = [f for f in CTX.files if f.endswith(".TIM")]
    for f in names:
        png = CTX.png / (f[:-4].lower() + ".png")
        w, h, px = tim_pixels(CTX.files[f])
        from PIL import Image
        im = Image.open(png).convert("RGBA"); need(im.size == (w, h), f"{f} size")
        exp = list(im.get_flattened_data()) if hasattr(im, 'get_flattened_data') else list(im.getdata())
        bpp = tim_parse(CTX.files[f])[0]
        bad = sum(1 for (r, g, b, a), (r5, g5, b5, t) in zip(exp, px) if (r >> 3, g >> 3, b >> 3) != (r5, g5, b5) and not (r5 == g5 == b5 == 1 and r >> 3 == 0 and g >> 3 == 0 and b >> 3 == 0))
        need(bad == 0, f"{f}: {bad} pixels differ from the PNG")
        n += 1
    # TPK members
    for tp in ("SHIP.TPK", "TRACK.TPK", "PROPS.TPK"):
        tims, _ = tpk_parse(CTX.files[tp])
        for t in tims: tim_parse(t); n += 1
    # layout rules
    import layout
    rects = []
    for sname, ents in layout.SETS.items():
        for (nm, bpp, x, y, cx, cy) in ents:
            wpx, hh = {"sky16": (64, 64)}.get(nm, (None, None))
            from PIL import Image
            im = Image.open(CTX.png / (nm + ".png")); wu = {4: im.width // 4, 8: im.width // 2, 16: im.width}[bpp]
            need((x % 64) * {4: 4, 8: 2, 16: 1}[bpp] + wu * {4: 4, 8: 2, 16: 1}[bpp] <= 256 and y % 256 + im.height <= 256, f"{nm} crosses a texture page")
            rects.append((nm, x, y, wu, im.height))
            if bpp <= 8:
                need(cx % 16 == 0, "CLUT x"); rects.append((nm + ".clut", cx, cy, 16 if bpp == 4 else 256, 1))
    for i, a in enumerate(rects):
        need(a[1] + a[3] <= 1024 and a[2] + a[4] <= 512, f"{a[0]} outside VRAM")
        for b in rects[i + 1:]:
            ov = a[1] < b[1] + b[3] and b[1] < a[1] + a[3] and a[2] < b[2] + b[4] and b[2] < a[2] + a[4]
            need(not ov, f"{a[0]} overlaps {b[0]}")
        if not a[0].endswith(".clut"):
            need(not (a[1] < 320 and a[2] < 480), f"{a[0]} overlaps the framebuffers")
    return f"{n} TIMs parsed, {len(rects)} VRAM rects disjoint"

@check("tpk: header, size table, LZSS blob, CRC32, manifest")
def _():
    for tp in ("SHIP.TPK", "TRACK.TPK", "PROPS.TPK"):
        tims, h = tpk_parse(CTX.files[tp])
        m = CTX.man[tp]
        need(h["n"] == m["count"] and h["crc"] == m["crc32"] and h["sizes"] == m["sizes"], tp + " manifest")
        need(all(len(t) % 4 == 0 for t in tims), "TIM alignment")
        need(len(CTX.files[tp]) % 4 == 0, "file size alignment")
    need(tpk_parse(CTX.files["TRACK.TPK"])[1]["n"] == 8, "TRACK.TPK has 8 textures")
    return "3 packs OK"

@check("vag: encode->decode SNR, block flags, header, loop")
def _():
    import sfxgen
    rep = []
    for name, fn in sfxgen.SOUNDS.items():
        d = CTX.files[name + ".VAG"]; v = vag_parse(d)
        need(v["rate"] == 22050 and v["version"] == 0x20, "header")
        smp, fl = adpcm_decode_stream(v["blocks"])
        need(fl[0] == 0 and not any(v["blocks"][:16]), "first block must be silent")
        orig = fn()
        dec = smp[28:28 + len(orig)]
        sig = sum(x * x for x in orig); err = sum((a - b) ** 2 for a, b in zip(orig, dec)) or 1
        snr = 10 * math.log10(sig / err)
        need(snr > 20, f"{name}: SNR {snr:.1f} dB too low")
        if name == "ENGINE":
            need(fl[1] == 4 and fl[-1] == 3 and all(f == 0 for f in fl[2:-1]), "loop flags")
        else:
            need(fl[-1] == 1 and v["blocks"][-16:] == bytes([0, 1]) + bytes(14) and all(f == 0 for f in fl[:-1]), "end block")
        rep.append(f"{name} {snr:.0f}dB")
    # wav2vag / vag2wav CLIs round trip
    import wav2vag, vag2wav, sfxgen as S
    t = Path(tempfile.mkdtemp()); S.write_wav(t / "a.wav", S.thud())
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        wav2vag.main([str(t / "a.wav"), str(t / "a.vag"), "--name", "thud"]); vag2wav.main([str(t / "a.vag"), str(t / "b.wav")])
    with wave.open(str(t / "b.wav")) as w: need(w.getnframes() >= len(S.thud()) and w.getframerate() == 22050, "vag2wav")
    import shutil; shutil.rmtree(t, ignore_errors=True)
    return ", ".join(rep)

@check("MODEL.BIN: big-endian header, vertices, faces, winding, manifest")
def _():
    d = CTX.files["MODEL.BIN"]; m = CTX.man["MODEL.BIN"]
    need(d[:4] == b"MDL1", "magic")
    nv = struct.unpack_from(">I", d, 4)[0]
    need(nv == m["vertex_count"] and struct.unpack_from("<I", d, 4)[0] != nv, "vertex count must be big-endian")
    verts = [struct.unpack_from("<hhhh", d, 8 + 8 * i) for i in range(nv)]
    need(all(v[3] == 0 for v in verts), "vertex pad")
    nf = struct.unpack_from(">I", d, 8 + 8 * nv)[0]
    need(nf == m["face_count"] and len(d) == 12 + 8 * nv + 8 * nf, "size")
    cen = tuple(sum(v[k] for v in verts) / nv for k in range(3))
    tri = 0
    for i in range(nf):
        r = d[12 + 8 * nv + 8 * i:][:8]
        idx = list(r[:3]) if r[3] == 0xFF else list(r[:4]); tri += r[3] == 0xFF
        need(all(k < nv for k in idx) and r[7] == 0, "face record")
        pts = [verts[k][:3] for k in idx]
        fc = tuple(sum(p[k] for p in pts) / len(pts) for k in range(3))
        need(dot(area_vec(pts), sub(fc, cen)) < 0, f"face {i} winding is not clockwise-from-outside")
    need(tri == m["triangles"], "triangles")
    need(list(verts[0][:3]) == m["first_vertex"] and list(verts[-1][:3]) == m["last_vertex"], "first/last vertex")
    return f"{nv} vertices, {nf} faces"

SIZES = {"F3": 16, "F4": 20, "G3": 24, "G4": 32, "FT3": 24, "FT4": 32, "GT3": 32, "GT4": 44}
TYPES = ["F3", "F4", "G3", "G4", "FT3", "FT4", "GT3", "GT4"]

def shp_walk(d):
    need(d[:4] == b"SHP1" and struct.unpack_from("<I", d, 4)[0] == len(d), "header")
    nv, nn, npr, nt = struct.unpack_from("<HHHH", d, 0x18)
    ov, on, op, sp = struct.unpack_from("<IIII", d, 0x20)
    need(ov == 0x40 and on == ov + 8 * nv and op == on + 8 * nn and op + sp == len(d), "offsets")
    verts = [struct.unpack_from("<hhh", d, ov + 8 * i) for i in range(nv)]
    norms = [struct.unpack_from("<hhh", d, on + 8 * i) for i in range(nn)]
    prims, pos = [], op
    for _ in range(npr):
        ty, fl, sz = struct.unpack_from("<BBH", d, pos); t = TYPES[ty]
        need(sz == SIZES[t] and sz % 4 == 0, "record size")
        n = 3 if t[-1] == "3" else 4; q = pos + 4
        idx = struct.unpack_from("<%dH" % n, d, q); q += 2 * n
        nm = struct.unpack_from("<H", d, q)[0]; q += 2 + (2 if n == 4 else 0)
        rec = dict(t=t, flags=fl, idx=idx, n=nm)
        if "T" in t:
            rec["uv"] = [(d[q + 2 * i], d[q + 2 * i + 1]) for i in range(n)]; q += 2 * n
            rec["tex"] = struct.unpack_from("<H", d, q)[0]; q += 2 + (2 if n == 4 else 0)
        nc = n if t.startswith("G") else 1
        rec["col"] = [tuple(d[q + 4 * i:q + 4 * i + 3]) for i in range(nc)]
        need(all(d[q + 4 * i + 3] == 0 for i in range(nc)), "colour pad"); q += 4 * nc
        need(q == pos + sz, "walk"); prims.append(rec); pos += sz
    return dict(nv=nv, nn=nn, nt=nt, verts=verts, norms=norms, prims=prims,
                bbox=struct.unpack_from("<6h", d, 0x30), name=d[8:24].rstrip(b"\0").decode())

@check("SHP: layout, all 8 primitive types, normals, UVs, TSB/CBA, manifest")
def _():
    out = []
    for fn in ("SHIP.SHP", "PYLON.SHP", "ARCH.SHP", "TOWER.SHP"):
        d = CTX.files[fn]; m = CTX.man[fn]; s = shp_walk(d)
        need(s["name"] == fn[:-4] and (s["nv"], s["nn"], len(s["prims"])) == (m["vertex_count"], m["normal_count"], m["prim_count"]), "counts")
        cnt = {t: sum(1 for p in s["prims"] if p["t"] == t) for t in TYPES}
        need(cnt == m["prim_counts"], "per-type counts differ from manifest")
        xs = list(zip(*s["verts"])); need(list(s["bbox"]) == [min(a) for a in xs] + [max(a) for a in xs], "bbox")
        for p in s["prims"]:
            pts = [s["verts"][i] for i in p["idx"]]
            av = area_vec(pts); l = math.sqrt(dot(av, av)); need(l > 0, "degenerate face")
            nrm = s["norms"][p["n"]]
            exp = tuple(-c / l * 4096 for c in av)
            need(all(abs(a - b) <= 2 for a, b in zip(nrm, exp)), "stored normal != -area vector direction")
            need(all(0 <= c <= 255 for col in p["col"] for c in col), "colour")
            if "uv" in p:
                need(p["tex"] < s["nt"], "texture index")
        if fn == "SHIP.SHP":
            need(all(c > 0 for c in cnt.values()), "ship must contain every primitive type")
            need(s["nt"] == 3, "ship uses 3 textures")
            for p in s["prims"][:16]:                    # hull: front faces point away from the hull axis point
                pts = [s["verts"][i] for i in p["idx"]]
                fc = tuple(sum(q[k] for q in pts) / len(pts) for k in range(3))
                need(dot(s["norms"][p["n"]], sub(fc, (0, -10, 0))) > 0, "hull face points inward")
            # TSB / CBA / absolute UVs vs independent formulas
            import layout
            tp = tpk_parse(CTX.files["SHIP.TPK"])[0]
            for mp in m["textured_prims"]:
                p = s["prims"][mp["index"]]
                x, y, w, h, _d = tim_parse(tp[p["tex"]])[2]; cb = tim_parse(tp[p["tex"]])[1]
                bpp = tim_parse(tp[p["tex"]])[0]
                tsb = x // 64 | (y // 256) << 4 | 0 << 5 | {4: 0, 8: 1, 16: 2}[bpp] << 7
                cba = cb[0] // 16 | cb[1] << 6
                need((mp["tsb"], mp["cba"]) == (tsb, cba), "TSB/CBA mismatch")
                wpx = w * {4: 4, 8: 2, 16: 1}[bpp]
                u0, v0 = (x % 64) * {4: 4, 8: 2, 16: 1}[bpp], y % 256
                for (u, v), (ua, va) in zip(p["uv"], mp["uv_abs"]):
                    need(u < wpx and v < h and (ua, va) == (u + u0, v + v0), "UV range / absolute UV")
        out.append(f"{fn[:-4]} {len(s['prims'])}p")
    return ", ".join(out)

@check("TRK: layout, links, frames, faces, winding, flags, vis, manifest")
def _():
    out = []
    for fn, nsec_exp in (("TRACK.TRK", 112), ("TRACK2.TRK", 104)):
        d = CTX.files[fn]; m = CTX.man[fn]
        need(d[:4] == b"TRK1" and struct.unpack_from("<I", d, 4)[0] == len(d), "header")
        ns, nv, nf, nvis = struct.unpack_from("<HHHH", d, 0x18)
        start, flags, ntex, _r = struct.unpack_from("<HHHH", d, 0x20)
        ov, of, os_, ovis = struct.unpack_from("<IIII", d, 0x28)
        tl = struct.unpack_from("<I", d, 0x38)[0]
        need(ns == nsec_exp == m["section_count"] and nv == 6 * ns and nf == 5 * ns, "counts")
        need((ov, of, os_, ovis) == (0x60, 0x60 + 12 * nv, 0x60 + 12 * nv + 24 * nf, 0x60 + 12 * nv + 24 * nf + 64 * ns), "offsets")
        need(ovis + 2 * nvis + 2 * (nvis % 2) == len(d) and flags & 1, "tail/flags")
        V = [struct.unpack_from("<iii", d, ov + 12 * i) for i in range(nv)]
        need(max(abs(c) for v in V for c in v) < 2 ** 31, "range")
        faces = []
        for i in range(nf):
            o = of + 24 * i
            v = struct.unpack_from("<4H", d, o); fl, tex, pad = struct.unpack_from("<HBB", d, o + 8)
            uv = [(d[o + 12 + 2 * k], d[o + 13 + 2 * k]) for k in range(4)]
            need(pad == 0 and d[o + 23] == 0 and fl < 32 and (tex < ntex or tex == 255), "face fields")
            need(all(x < nv for x in v) and all(u <= 63 and w <= 63 for u, w in uv), "face indices / UV")
            faces.append((v, fl, tex, uv))
        secs = []
        for i in range(ns):
            o = os_ + 64 * i
            c = struct.unpack_from("<iii", d, o); hw, ln = struct.unpack_from("<HH", d, o + 12)
            fw, rt, up = [struct.unpack_from("<hhh", d, o + k) for k in (16, 24, 32)]
            ff, fc, nx, pv, sf, vf, vc = struct.unpack_from("<7H", d, o + 40)
            ed = struct.unpack_from("<4H", d, o + 54)
            need(d[o + 62:o + 64] == b"\0\0" and all(d[o + k + 6:o + k + 8] == b"\0\0" for k in (16, 24, 32)), "pads")
            secs.append(dict(c=c, hw=hw, ln=ln, fw=fw, rt=rt, up=up, ff=ff, fc=fc, nx=nx, pv=pv, sf=sf, vf=vf, vc=vc, ed=ed))
        visflat = struct.unpack_from("<%dH" % nvis, d, ovis)
        centres = []
        for i, s in enumerate(secs):
            need(s["nx"] == (i + 1) % ns and s["pv"] == (i - 1) % ns, "links")
            need(s["ff"] == 5 * i and s["fc"] == 5, "face ranges")
            need(s["ed"][2] == secs[(i + 1) % ns]["ed"][0] and s["ed"][3] == secs[(i + 1) % ns]["ed"][1], "rings shared with next section")
            L0, R0, L1, R1 = [V[k] for k in s["ed"]]
            a = tuple((L0[k] + R0[k]) / 2 for k in range(3)); b = tuple((L1[k] + R1[k]) / 2 for k in range(3))
            centres.append(tuple((a[k] + b[k]) / 2 for k in range(3)))
            need(all(abs(s["c"][k] - centres[-1][k]) <= 1.5 for k in range(3)), "centre != midpoint of ring centres")
            chord = sub(b, a); need(abs(s["ln"] - math.sqrt(dot(chord, chord))) <= 1, "length")
            need(abs(s["hw"] - math.sqrt(dot(sub(R0, L0), sub(R0, L0))) / 2) <= 1, "half width")
            for nm, v in (("fw", s["fw"]), ("rt", s["rt"]), ("up", s["up"])):
                need(abs(math.sqrt(dot(v, v)) - 4096) <= 12, nm + " not unit")
            for p, q in (("fw", "rt"), ("fw", "up"), ("rt", "up")):
                need(abs(dot(s[p], s[q])) / 4096 ** 2 < 0.01, f"{p} not orthogonal to {q}: {dot(s[p], s[q]) / 4096 ** 2:.4f}")
            need(dot(s["fw"], unit(chord)) > 4096 * 0.999, "forward != chord direction")
            need(s["up"][1] < 0, "up must point to -y")
            ra_, rb_ = unit(sub(R0, L0)), unit(sub(R1, L1)); fwu = unit(chord)
            R = tuple(x + y for x, y in zip(ra_, rb_)); R = unit(sub(R, tuple(dot(R, fwu) * c for c in fwu)))
            need(dot(R, unit(s["rt"])) > 0.998, "right != normalised mean of the two ring L->R vectors")
            need((s["sf"] & 2) == (2 if i == start else 0), "start flag")
            # faces: ring vertices, winding, flags
            ra = s["ed"][0] - 1; rb = s["ed"][2] - 1
            ring = set(range(ra, ra + 6)) | set(range(rb, rb + 6))
            for k in range(5):
                v, fl, tex, uv = faces[s["ff"] + k]
                need(set(v) <= ring and len(set(v)) == 4, "face vertices not from this section's rings")
                av = area_vec([V[x] for x in v])
                lat = dot(sub(V[v[0]], s["c"]), unit(s["rt"]))
                if k == 0:   need(dot(av, unit(s["rt"])) < 0 and fl & 3 == 2 and lat < 0, "left wall")
                elif k == 4: need(dot(av, unit(s["rt"])) > 0 and fl & 3 == 2 and lat > 0, "right wall")
                else:        need(dot(av, unit(s["up"])) < 0 and fl & 3 == 1, "floor winding/flag")
                need(bool(fl & 4) == (k == 2 and i in m["boost_sections"]), "boost flags")
                need(bool(fl & 8) == (i == start and k in (1, 2, 3)), "start-line flags")
                if tex != 255: need(tex < ntex, "texture")
        need(sum(s["ln"] for s in secs) == tl == m["total_length"], "total_length")
        # visibility rule
        avg = sum(s["ln"] for s in secs) / ns; r = m["vis_rule"]
        for i, s in enumerate(secs):
            lst = list(visflat[s["vf"]:s["vf"] + s["vc"]])
            exp = [(i + o) % ns for o in range(ns) if o <= r["ahead"] or o >= ns - r["behind"] or
                   math.dist(s["c"], secs[(i + o) % ns]["c"]) <= r["near_factor"] * avg]
            need(lst == exp and lst[0] == i, "vis list")
        need(m["vis_entries"] == nvis, "vis entries")
        # manifest cross-checks
        need([list(s["c"]) for s in secs] == m["centre_line"], "centre_line")
        need(sum(1 for f in faces if f[1] & 4) == m["face_counts"]["boost"], "boost count")
        need(max(V[k][0] for k in range(nv)) - min(V[k][0] for k in range(nv)) > 32767, "track should exceed the int16 range")
        out.append(f"{fn[:-4]} {ns}s/{nf}f/{tl}u")
    return ", ".join(out)

@check("TRK: banking leans into turns (right edge lower in right turns)")
def _():
    d = CTX.files["TRACK.TRK"]; ns = struct.unpack_from("<H", d, 0x18)[0]
    ov, os_ = struct.unpack_from("<I", d, 0x28)[0], struct.unpack_from("<I", d, 0x30)[0]
    V = lambda i: struct.unpack_from("<iii", d, ov + 12 * i)
    S = [struct.unpack_from("<4H", d, os_ + 64 * i + 54) for i in range(ns)]
    C = [tuple((V(e[0])[k] + V(e[1])[k]) / 2 for k in range(3)) for e in S]
    good = total = 0
    for i in range(ns):
        a = sub(C[i], C[i - 1]); b = sub(C[(i + 1) % ns], C[i])
        # heading change; the right-hand side of heading (hx,hz) is (hz,-hx)
        turn = b[0] * a[2] - b[2] * a[0]
        if abs(turn) < 0.05 * math.sqrt(dot(a, a) * dot(b, b)): continue
        rise = V(S[i][1])[1] - V(S[i][0])[1]          # y of right edge minus y of left edge (+y is down)
        total += 1; good += (turn > 0) == (rise > 0)
    need(total >= 4 and good == total, f"{good}/{total} banked sections lean the right way")
    return f"{good}/{total} turns banked correctly"

@check("SCENE.BIN: layout, shapes exist, objects near the track, manifest")
def _():
    d = CTX.files["SCENE.BIN"]; m = CTX.man["SCENE.BIN"]
    need(d[:4] == b"SCN1", "magic")
    total, ns, no, os_, oo, cull = struct.unpack_from("<IHHIII", d, 4)
    need(total == len(d) and os_ == 0x20 and oo == os_ + 16 * ns and oo + 24 * no == total and no >= 20, "layout")
    names = []
    for i in range(ns):
        nm = d[os_ + 16 * i:os_ + 16 * i + 12].rstrip(b"\0").decode(); r = struct.unpack_from("<I", d, os_ + 16 * i + 12)[0]
        need(nm in CTX.files and r > 0, f"shape {nm} missing from asset set"); names.append(nm)
    sd = CTX.files["TRACK.TRK"]; nsec = struct.unpack_from("<H", sd, 0x18)[0]; osec = struct.unpack_from("<I", sd, 0x30)[0]
    cs = [struct.unpack_from("<iii", sd, osec + 64 * i) for i in range(nsec)]
    for i in range(no):
        sh, fl, x, y, z, rx, ry, rz, sc = struct.unpack_from("<HHiii3hH", d, oo + 24 * i)
        need(sh < ns and sc == 4096 and rx == 0 and rz == 0 and 0 <= ry < 4096, "object fields")
        mo = m["objects"][i]; need(mo["pos"] == [x, y, z] and mo["shape"] == sh, "manifest object")
        if names[sh] == "PYLON.SHP":
            need(min(math.dist((x, y, z), c) for c in cs) < 1600, "pylon not beside the track")
    need(sum(1 for i in range(no) if struct.unpack_from("<HH", d, oo + 24 * i)[1] & 1) >= 1, "arch always-draw")
    need(m["object_count"] == no and cull == m["cull_radius"], "manifest")
    return f"{no} objects, {ns} shapes"

@check("formats.py reference parsers agree with the independent ones")
def _():
    import formats as Fm
    Fm.parse_model_bin(CTX.files["MODEL.BIN"]); [Fm.parse_shp(CTX.files[f]) for f in ("SHIP.SHP", "PYLON.SHP", "ARCH.SHP", "TOWER.SHP")]
    for f in ("TRACK.TRK", "TRACK2.TRK"):
        t = Fm.parse_trk(CTX.files[f]); need(len(t["sections"]) == CTX.man[f]["section_count"], f)
    Fm.parse_scene(CTX.files["SCENE.BIN"]); [Fm.parse_tpk(CTX.files[f]) for f in ("SHIP.TPK", "TRACK.TPK", "PROPS.TPK")]
    s = Fm.parse_shp(CTX.files["SHIP.SHP"]); need(len(s["prims"]) == shp_walk(CTX.files["SHIP.SHP"])["nv"] * 0 + CTX.man["SHIP.SHP"]["prim_count"], "prims")
    return "ok"

@check("appendix: hex dumps match what the generators produce")
def _():
    import examples as E
    app = (ROOT / "appendices" / "E-file-formats.md")
    need(app.exists(), "appendices/E-file-formats.md missing")
    text = app.read_text()
    blocks = {"tiny TIM": E.xxd(E.tiny_tim()), "tiny VAG": E.xxd(E.tiny_vag()), "tiny TPK": E.xxd(E.tiny_tpk()),
              "LZSS example": E.xxd(E.lzss_example()[1]), "LZSS trace": E.lzss_trace(E.lzss_example()[1], len(E.LZSS_TEXT))}
    for nm, (f, off, ln) in E.slices(CTX.files).items():
        blocks[nm] = E.xxd(CTX.files[f][off:off + ln], off)
    for nm, b in blocks.items():
        need(b in text, f"appendix is missing the current '{nm}' dump (re-run tools/assets/examples.py --print)")
    return f"{len(blocks)} dumps found"

# ============================================================ runner

def main():
    import time
    t0 = time.time()
    d, files, man = build_assets(1, keep_png=True)
    CTX.files, CTX.man, CTX.png = files, man, d / "png"
    CTX.tims = [files[k] for k in sorted(files) if k.endswith(".TIM")]
    width = max(len(n) for n, _ in CHECKS)
    fails = 0
    for name, fn in CHECKS:
        try:
            info = fn() or ""
            RESULTS.append((name, "PASS", info))
        except Exception as e:
            fails += 1
            RESULTS.append((name, "FAIL", f"{type(e).__name__}: {e}"))
            if VERBOSE: traceback.print_exc()
    for name, st, info in RESULTS:
        print(f"{st:4s}  {name:{width}s}  {info}")
    print(f"\nasset selftest: {len(RESULTS) - fails}/{len(RESULTS)} passed in {time.time() - t0:.1f}s")
    import shutil
    shutil.rmtree(d, ignore_errors=True)
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main())
