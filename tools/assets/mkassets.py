#!/usr/bin/env python3
"""mkassets.py -- build the whole Hoverline asset set (what a chapter's `make assets` calls).

  mkassets.py OUTDIR [--seed N] [--keep-png]

Writes into OUTDIR:   demo TIMs (CRATE PANEL LOGO SKY16 .TIM)  SHIP/TRACK/PROPS .TPK
                      SHIP PYLON ARCH TOWER .SHP  MODEL.BIN  TRACK.TRK TRACK2.TRK  SCENE.BIN
                      ENGINE BOOST THUD BEEP GO .VAG        manifest/*.json (one per file) + manifest/index.json
Everything is deterministic: the same seed gives byte-identical files.
"""
import argparse, hashlib, json, shutil, sys, tempfile, zlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import formats as F, img2tim, layout, shpgen, scenegen, sfxgen, texgen, tim, trkgen, wav2vag


def _sha(b): return hashlib.sha256(b).hexdigest()


def tim_info(name, data, extra=None):
    t = tim.parse(data)
    m = dict(file=name, size=len(data), sha256=_sha(data), bpp=t.bpp, width=t.pixel_width, height=t.height,
             image=dict(x=t.image.x, y=t.image.y, w=t.image.w, h=t.image.h),
             tsb_abr0=tim.tsb(t.image.x, t.image.y, t.bpp, 0), uv_origin=list(tim.uv_origin(t.image.x, t.image.y, min(t.bpp, 16))))
    if t.clut:
        m["clut"] = dict(x=t.clut.x, y=t.clut.y, w=t.clut.w, h=t.clut.h); m["cba"] = tim.cba(t.clut.x, t.clut.y)
    m.update(extra or {})
    return m


def build(out: Path, seed=1, keep_png=False):
    out.mkdir(parents=True, exist_ok=True)
    man = out / "manifest"; man.mkdir(exist_ok=True)
    files = {}                                     # filename -> bytes
    manifests = {}
    pngdir = out / "png" if keep_png else Path(tempfile.mkdtemp(prefix="mkassets-"))
    pngdir.mkdir(exist_ok=True)
    texs = texgen.generate(seed)
    for n, (im, _) in texs.items():
        im.save(pngdir / f"{n}.png")

    def make_tim(name):
        for sname, entries in layout.SETS.items():
            for i, (n, bpp, x, y, cx, cy) in enumerate(entries):
                if n == name:
                    return img2tim.convert(pngdir / f"{n}.png", bpp, x, y, cx, cy), sname, i
        raise KeyError(name)

    for n in ("crate", "panel", "logo", "sky16"):
        data, _, _ = make_tim(n)
        files[n.upper() + ".TIM"] = data
        manifests[n.upper() + ".TIM"] = tim_info(n.upper() + ".TIM", data)

    for sname, fname in (("ship", "SHIP.TPK"), ("track", "TRACK.TPK"), ("props", "PROPS.TPK")):
        tims = [make_tim(e[0])[0] for e in layout.SETS[sname]]
        data = F.build_tpk(tims)
        d = F.parse_tpk(data)
        files[fname] = data
        manifests[fname] = dict(file=fname, size=len(data), sha256=_sha(data), count=d["count"], sizes=d["sizes"], raw_size=d["raw_size"],
                                comp_size=d["comp_size"], crc32=d["crc32"],
                                textures=[tim_info(e[0] + ".tim", t, dict(index=i)) for i, (e, t) in enumerate(zip(layout.SETS[sname], tims))])

    for obj in ("ship", "pylon", "arch", "tower"):
        m = shpgen.OBJECTS[obj](); shpgen.fix_prop_textures(obj, m)
        data = m.build(); fn = obj.upper() + ".SHP"
        files[fn] = data; manifests[fn] = shpgen.shp_manifest(obj.upper(), data, shpgen.OBJECT_SET[obj] or "props")
    data = shpgen.make_model_bin(); files["MODEL.BIN"] = data; manifests["MODEL.BIN"] = shpgen.model_bin_manifest(data)

    for k, fn in ((1, "TRACK.TRK"), (2, "TRACK2.TRK")):
        data, meta = trkgen.generate(k); files[fn] = data; manifests[fn] = trkgen.manifest(data, meta)
    data = scenegen.generate(files["TRACK.TRK"]); files["SCENE.BIN"] = data; manifests["SCENE.BIN"] = scenegen.manifest(data)

    for name, fn in sfxgen.SOUNDS.items():
        s = fn()
        loop = name == "ENGINE"
        data = wav2vag.convert(s, sfxgen.RATE, name.lower(), loop=loop)
        files[name + ".VAG"] = data
        manifests[name + ".VAG"] = dict(file=name + ".VAG", size=len(data), sha256=_sha(data), samples=len(s), sample_rate=sfxgen.RATE,
                                        loop=loop, blocks=(len(data) - 48) // 16, header_hex=data[:48].hex(), wav_crc32=zlib.crc32(
                                            b"".join(int(v).to_bytes(2, "little", signed=True) for v in s)) & 0xFFFFFFFF)
    for fn, data in files.items():
        (out / fn).write_bytes(data)
        (man / (fn + ".json")).write_text(json.dumps(manifests[fn], indent=1, sort_keys=True) + "\n")
    (man / "index.json").write_text(json.dumps({fn: _sha(d) for fn, d in sorted(files.items())}, indent=1) + "\n")
    if not keep_png:
        shutil.rmtree(pngdir, ignore_errors=True)
    return files, manifests


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir"); ap.add_argument("--seed", type=int, default=1); ap.add_argument("--keep-png", action="store_true")
    a = ap.parse_args(argv)
    files, _ = build(Path(a.outdir), a.seed, a.keep_png)
    print(f"{len(files)} files written to {a.outdir}")


if __name__ == "__main__":
    main()
