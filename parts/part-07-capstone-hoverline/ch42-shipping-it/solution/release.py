#!/usr/bin/env python3
"""release.py BUILD_DIR OUT_DIR: gather the release (README 5.5).

OUT_DIR gets the disc image, its cue sheet, the unstripped ELF (for crash analysis; it is not on the disc), the two papers, MANIFEST.txt (what is
ON the disc: sha256, size, path) and SHA256SUMS (what is in OUT_DIR, in `sha256sum -c` format). Every list is sorted, so the output does not depend
on the order the filesystem returns things in."""
import hashlib
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

build, out = Path(sys.argv[1]), Path(sys.argv[2])
here = Path(__file__).resolve().parent


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


shutil.rmtree(out, ignore_errors=True)
out.mkdir(parents=True)
for name in ("hoverline.bin", "hoverline.cue"):
    shutil.copy(build / name, out / name)
shutil.copy(build / "game.elf", out / "hoverline.elf")
for name in ("NOTICES.TXT", "RELEASE.md"):
    shutil.copy(here / name, out / name)

# The disc's contents come from the project file mkpsxiso was given (CMake wrote it into the build directory).
xml = sorted(build.glob("cd_image_*.xml"))
if len(xml) != 1:
    sys.exit("release.py: expected exactly one cd_image_*.xml in " + str(build))
rows = []


def walk(node, prefix):
    for e in node:
        if e.tag == "dir":
            walk(e, prefix + e.get("name") + "/")
        elif e.tag == "file":
            src = Path(e.get("source"))
            src = src if src.is_absolute() else build / src
            rows.append((prefix + e.get("name"), src.stat().st_size, sha(src)))


root = ET.parse(xml[0]).getroot()
walk(root.find("track[@type='data']/directory_tree"), "")
for t in root.findall("track[@type='audio']"):
    src = build / t.get("source")
    rows.append(("TRACK02.WAV", src.stat().st_size, sha(src)))
(out / "MANIFEST.txt").write_text("".join(f"{h}  {n:>9}  {p}\n" for p, n, h in sorted(rows)))

files = sorted(p for p in out.iterdir() if p.name != "SHA256SUMS")
(out / "SHA256SUMS").write_text("".join(f"{sha(p)}  {p.name}\n" for p in files))
print(f"release.py: {len(rows)} disc files, {len(files)} release files in {out}")
