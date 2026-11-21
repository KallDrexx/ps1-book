#!/usr/bin/env python3
"""Mutation test of the verifier (README 8): each mutant is a plausible WRONG release made by editing a copy of solution/; verify.sh must exit 1 on it.

  python3 mutants.py              every mutant (about 1.5 minutes each: a full verify.sh run)
  python3 mutants.py NAME ...     only those

Prints, per mutant, the exit code and the checks that failed. Not part of tools/ci.sh (the CI proves solution passes and starter fails)."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOLUTION = HERE.parent / "solution"

# name: (file, old text, new text, what it models)
MUTANTS = {
    "volume_dates_missing": ("iso.xml", 'creation_date ="2026010100000000"\n\t\t\tmodification_date="2026010100000000"', "", "the volume stamps the build time"),
    "file_dates_missing": ("iso.xml", '<dir name="DATA" date="20260101000000">', '<dir name="DATA">', "one directory keeps its files' modification times"),
    "sdk_mkpsxiso": ("Makefile", " -DMKPSXISO=$(MKPSXISO)", "", "the SDK's bundled mkpsxiso builds the image and ignores the dates"),
    "region_constant": ("main.c", "video_mode = (GetVideoMode() == MODE_PAL);", "video_mode = 0;", "NTSC everywhere"),
    "region_inverted": ("main.c", "video_mode = (GetVideoMode() == MODE_PAL);", "video_mode = (GetVideoMode() != MODE_PAL);", "PAL on NTSC consoles"),
    "readout_kept": ("game.c", "#ifndef HOVERLINE_RELEASE\n\tvis_readout_format();", "#if 1\n\tvis_readout_format();", "the release still draws the debug readout", ("#ifndef HOVERLINE_RELEASE\n/* The readout", "#if 1\n/* The readout")),
    "keys_kept": ("game.c", "#ifndef HOVERLINE_RELEASE                /* a shipped disc has no debug keys (README 5.3) */", "#if 1", "the release still has the debug keys"),
    "copyright_dangling": ("iso.xml", 'copyright     ="NOTICES.TXT;1"', 'copyright     ="README.TXT;1"', "the copyright identifier names no file"),
    "manifest_wrong_hash": ("release.py", "rows.append((prefix + e.get(\"name\"), src.stat().st_size, sha(src)))", "rows.append((prefix + e.get(\"name\"), src.stat().st_size, sha(src)[::-1]))", "a manifest with wrong hashes"),
    "notices_not_on_disc": ("iso.xml", '<file name="NOTICES.TXT" type="data" source="${PROJECT_SOURCE_DIR}/NOTICES.TXT" date="20260101000000" />', "", "the notices stay in the folder"),
}


def run(name):
    f, old, new, why, *more = MUTANTS[name]
    with tempfile.TemporaryDirectory(prefix="ch42mut-") as t:
        proj = Path(t) / "solution"
        shutil.copytree(SOLUTION, proj, ignore=shutil.ignore_patterns("build", "build-release", "release", "__pycache__"))
        p = proj / f
        text = p.read_text()
        if old not in text:
            return None, f"mutation does not apply to {f}"
        text = text.replace(old, new, 1)
        for o2, n2 in more:
            text = text.replace(o2, n2, 1)
        p.write_text(text)
        r = subprocess.run([str(HERE / "verify.sh"), str(proj)], capture_output=True, text=True, timeout=600)
        out = r.stdout + r.stderr
        failed = [l.strip()[6:] for l in out.splitlines() if l.strip().startswith("FAIL  ")]
        return r.returncode, "; ".join(failed) or out[-300:]


if __name__ == "__main__":
    names = sys.argv[1:] or list(MUTANTS)
    bad = 0
    for n in names:
        rc, info = run(n)
        ok = rc == 1
        bad += not ok
        print(f"{'ok ' if ok else 'BAD'} {n:24} exit {rc}: {info}")
    sys.exit(1 if bad else 0)
