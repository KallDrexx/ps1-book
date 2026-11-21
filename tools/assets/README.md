# tools/assets: the book's asset generators

Host-side Python (3.10+, standard library plus Pillow) that makes every asset of the book and defines,
by being tested against it, the file formats of [Appendix E](../../appendices/E-file-formats.md).
Run with the repo's Python: `source tools/env.sh; $PS1BOOK_PYTHON tools/assets/<tool>.py ...`.

Everything is **deterministic**: same arguments and seed, byte-identical files (`selftest.py` checks it).
All art, models, tracks and sounds are original to this book.

## Convention for generated files

Generated binaries are **not committed** (`.gitignore` covers `build/assets/`). A chapter's `make assets`
runs `mkassets.py` (or the single tool it needs) into the chapter's `build/assets/`; its `verify.sh` does the same
before it builds. The generators and Appendix E are the source of truth, not the bytes. A chapter's `starter/` may
commit a small file only when the reader needs it before the chapter introduces the tool (e.g. a TIM for Chapter 16-style `.incbin` work).

## Tools

| Tool | Command line | Notes |
|---|---|---|
| `mkassets.py` | `mkassets.py OUTDIR [--seed N] [--keep-png] [--music]` | The whole set (below) plus `OUTDIR/manifest/*.json`. `--music` also writes `MUSIC.WAV` (the CD-DA track; Chapter 39 on; off by default so earlier chapters' builds and checksums are unchanged). |
| `texgen.py` | `texgen.py OUTDIR [--seed N]`, `--list` | 17 PNGs: `crate` (8 bpp), `panel`, `logo` (128x64 "HOVERLINE"), `hull_a`, `hull_b`, `wing`, `asphalt`, `asphalt_worn`, `lane_stripe`, `boost`, `start_line`, `wall_a`, `wall_b`, `glow`, `pylon`, `tower`, `sky16` (16 bpp). |
| `img2tim.py` | `img2tim.py in.png out.tim --bpp 4\|8\|16\|24 [--x --y --cx --cy]`; `--check f.tim...`; `--to-png f.tim out.png` | Palette from the PNG's colors (exact when it has at most 16/256), else median-cut. Alpha < 128 is transparent (CLUT index 0). `--check` exits 1 on an invalid TIM. |
| `tim.py` | library | `parse`, `build`, `decode_rgba`, `tsb`, `cba`, `uv_origin`, `fits_in_page`. |
| `lzss.py` | library | `compress(data)`, `decompress(data, out_size=None)`. Appendix E.5. |
| `tpkpack_ref.py` | `pack OUT.TPK a.tim ...` (or a directory), `unpack IN.TPK DIR`, `verify IN.TPK` | The **oracle**. Chapter 31's reader writes their own `tpkpack.py`; use this one to check it. |
| `shpgen.py` | `shpgen.py ship\|pylon\|arch\|tower OUT.SHP [--manifest m.json] [--variant 1]`; `shpgen.py --model-bin OUT.BIN [--manifest m.json]` | Ship mixes all 8 primitive types; `--variant 1` (ship only) is Chapter 32's alternate ship (no canopy, two more GT4); `--model-bin` is Chapter 29's `MODEL.BIN`. |
| `trkgen.py` | `trkgen.py OUT.TRK [--track 1\|2] [--sections N] [--manifest m.json]` | Track 1: 112 sections (~1000 units each); track 2: 104. |
| `scenegen.py` | `scenegen.py TRACK.TRK OUT.BIN [--manifest m.json]` | 35 objects around the track. |
| `sfxgen.py` | `sfxgen.py OUTDIR` | `ENGINE BOOST THUD BEEP GO` `.WAV`, 16-bit mono 22050 Hz. |
| `musicgen.py` | `musicgen.py OUT.WAV` | `MUSIC.WAV`: an original 24 s loop (A minor, 120 BPM, 12 bars; bass, arpeggio, pad, drums), 44.1 kHz 16-bit stereo = Red Book CD audio, 4,233,644 bytes, 2.7 s to generate, deterministic, stdlib only. The last 1500 frames fade out so a restart does not click. |
| `wav2vag.py` | `wav2vag.py in.wav out.vag [--name N] [--loop] [--loop-start SAMPLE]` | SPU-ADPCM encoder (5 filters, shift search per block). |
| `vag2wav.py`, `vag.py` | `vag2wav.py in.vag out.wav` | Decoder for verification. |
| `formats.py` | library | Reference writers/parsers: `build_/parse_` `model_bin`, `tpk`, `shp`, `trk`, `scene`. Dicts out, `FormatError` on bad input. |
| `layout.py` | library | Default VRAM placement of every texture (`SETS`). (The *disc* layout is each chapter's `iso.xml`; from Chapter 39 it adds `<track type="audio" source="assets/MUSIC.WAV"/>`.) |
| `examples.py` | `examples.py` prints the dumps used in the appendix | |
| `selftest.py` | `selftest.py [-v]` | PASS/FAIL table; exit 1 on failure. Run by `tools/ci.sh`. |

`mkassets.py` output (names are 8.3 for the disc): `CRATE.TIM PANEL.TIM LOGO.TIM SKY16.TIM`, `SHIP.TPK` (3 textures: hull_a, hull_b, wing),
`TRACK.TPK` (8 tiles), `PROPS.TPK` (pylon, tower), `SHIP.SHP PYLON.SHP ARCH.SHP TOWER.SHP`, `MODEL.BIN`, `TRACK.TRK TRACK2.TRK`, `SCENE.BIN`,
`ENGINE.VAG` (looped) `BOOST.VAG THUD.VAG BEEP.VAG GO.VAG`, (with `--music`) `MUSIC.WAV`, and `manifest/<file>.json` plus `manifest/index.json` (sha256 of each file).

## Manifests (what `verify` scripts compare against)

One JSON file per asset, `manifest/<FILE>.json`, keys sorted, integers only (except `vis_rule.near_factor`). Full schemas are in Appendix E next to each format:

| Manifest | Main keys | Used by |
|---|---|---|
| `MODEL.BIN.json` | `vertex_count face_count triangles quads first_vertex last_vertex first_face last_face` | Ch 29 |
| `<TIM>.TIM.json` | `bpp width height image{x,y,w,h} clut{x,y,w,h} tsb_abr0 cba uv_origin` | Ch 30 |
| `<PACK>.TPK.json` | `count sizes raw_size comp_size crc32 textures[...]` (each a TIM manifest + `index`) | Ch 31, 35 |
| `SHIP.SHP.json` etc. | `prim_counts texture_count bbox textures[...] textured_prims[{index,type,tex,tsb,cba,uv_abs}]` | Ch 32 |
| `SCENE.BIN.json` | `object_count shapes[...] cull_radius objects[{pos,rot,shape,flags}]` | Ch 33 |
| `TRACK.TRK.json` | `section_count vertex_count face_count total_length centre_line edges vis boost_sections start_faces face_counts` | Ch 34-40 |
| `<NAME>.VAG.json` | `sample_rate samples loop blocks header_hex wav_crc32` | Ch 39 |
| `MUSIC.WAV.json` | `size sha256 sample_rate channels bits frames seconds bpm bars pcm_crc32 peak` | Ch 39 (the disc check) |

## Using the tools from a chapter's `verify/checks.py`

```python
import sys, json, pathlib, subprocess, os
TOOLS = pathlib.Path(os.environ["PS1BOOK_ROOT"]) / "tools" / "assets"
sys.path.insert(0, str(TOOLS))
import mkassets, formats, lzss, tim           # reference parsers, LZSS and TIM helpers

files, manifests = mkassets.build(pathlib.Path(workdir) / "assets", seed=1)   # same bytes every time
trk = formats.parse_trk(files["TRACK.TRK"])                                   # dict: sections, faces, vertices...
expected = manifests["TRACK.TRK"]["section_count"]
raw = lzss.decompress(comp_bytes, raw_size)                                   # reference decompressor
```

Rules: compare the reader's parse with the **manifest** or with `formats.parse_*`, never with numbers typed into `checks.py`;
check RAM against the file bytes at the symbol the starter declares; for a reader-written packer, run
`tpkpack_ref.py verify` on its output and compare `crc32`. `PS1BOOK_ROOT` is set by `tools/env.sh`.
`selftest.py` is the guard that keeps these tools and the appendix in step: run it after any change to a generator, and
update the appendix's hex dumps with `examples.py` (the selftest fails when they drift).
