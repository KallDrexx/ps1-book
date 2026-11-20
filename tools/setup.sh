#!/usr/bin/env bash
# Installs the PS1 book toolchain into <repo>/.toolchain (no sudo).
#   tools/setup.sh            install anything missing, then run doctor.sh
#   tools/setup.sh --force    reinstall everything
# Idempotent: finished components leave a stamp in .toolchain/stamps/.
set -euo pipefail

TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$TOOLS/.." && pwd)"
TC="${PS1BOOK_TOOLCHAIN:-$ROOT/.toolchain}"
# shellcheck source=versions.txt
source "$TOOLS/versions.txt"
FORCE=0; [[ "${1:-}" == "--force" ]] && FORCE=1

DL="$TC/dl"; OPT="$TC/opt"; BIN="$TC/bin"; STAMPS="$TC/stamps"
mkdir -p "$DL" "$OPT" "$BIN" "$STAMPS"

say()  { printf '\n==> %s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not installed. $2"; }

done_stamp() { [[ $FORCE -eq 0 && -f "$STAMPS/$1" ]]; }
mark_done()  { echo "$2" > "$STAMPS/$1"; }

need curl    "Install it with your package manager (e.g. sudo apt install curl)."
need python3 "Python >= $PYTHON_MIN is required."
need git     "Install it with your package manager."
python3 - <<PY || die "Python >= $PYTHON_MIN required"
import sys; sys.exit(0 if sys.version_info >= tuple(map(int,"$PYTHON_MIN".split("."))) else 1)
PY

fetch() { # url sha256 outfile
  local url="$1" sha="$2" out="$3"
  if [[ -f "$out" ]] && echo "$sha  $out" | sha256sum -c --status 2>/dev/null; then return; fi
  echo "  downloading $(basename "$out")"
  curl -sSfL --retry 3 -o "$out.part" "$url"
  echo "$sha  $out.part" | sha256sum -c --status || die "checksum mismatch for $url"
  mv "$out.part" "$out"
}

# Extract a zip preserving unix modes (no 'unzip' needed).
unzip_py() { # zip destdir
  python3 - "$1" "$2" <<'PY'
import sys, zipfile, os
z = zipfile.ZipFile(sys.argv[1]); d = sys.argv[2]
for i in z.infolist():
    p = z.extract(i, d)
    mode = i.external_attr >> 16
    if mode and not i.is_dir(): os.chmod(p, (mode & 0o7777) | 0o600)
PY
}

link() { ln -sfn "$1" "$BIN/$2"; }

# ---------------------------------------------------------------- PSn00bSDK
install_psn00bsdk() {
  done_stamp "psn00bsdk-$PSN00BSDK_VERSION" && { echo "PSn00bSDK $PSN00BSDK_VERSION: already installed"; return; }
  say "PSn00bSDK $PSN00BSDK_VERSION (SDK + mipsel-none-elf GCC)"
  fetch "$PSN00BSDK_URL" "$PSN00BSDK_SHA256" "$DL/psn00bsdk-$PSN00BSDK_VERSION.zip"
  rm -rf "$OPT/psn00bsdk"; mkdir -p "$OPT/psn00bsdk.tmp"
  unzip_py "$DL/psn00bsdk-$PSN00BSDK_VERSION.zip" "$OPT/psn00bsdk.tmp"
  mv "$OPT/psn00bsdk.tmp/PSn00bSDK-$PSN00BSDK_VERSION-Linux" "$OPT/psn00bsdk"
  rmdir "$OPT/psn00bsdk.tmp"
  for f in "$OPT"/psn00bsdk/bin/mipsel-none-elf-* "$OPT"/psn00bsdk/bin/{elf2x,elf2cpe,lzpack,smxlink,dumpsxiso}; do
    link "$f" "$(basename "$f")"
  done
  # ninja ships with the SDK; only link it if the system has none.
  command -v ninja >/dev/null 2>&1 || link "$OPT/psn00bsdk/bin/ninja" ninja
  mark_done "psn00bsdk-$PSN00BSDK_VERSION" ok
}

# ---------------------------------------------------------------- mkpsxiso
install_mkpsxiso() {
  done_stamp "mkpsxiso-$MKPSXISO_VERSION" && { echo "mkpsxiso $MKPSXISO_VERSION: already installed"; return; }
  say "mkpsxiso $MKPSXISO_VERSION"
  fetch "$MKPSXISO_URL" "$MKPSXISO_SHA256" "$DL/mkpsxiso-$MKPSXISO_VERSION.zip"
  rm -rf "$OPT/mkpsxiso"; mkdir -p "$OPT/mkpsxiso.tmp"
  unzip_py "$DL/mkpsxiso-$MKPSXISO_VERSION.zip" "$OPT/mkpsxiso.tmp"
  mv "$OPT/mkpsxiso.tmp/mkpsxiso-$MKPSXISO_VERSION-Linux" "$OPT/mkpsxiso"; rmdir "$OPT/mkpsxiso.tmp"
  link "$OPT/mkpsxiso/bin/mkpsxiso" mkpsxiso
  link "$OPT/mkpsxiso/bin/dumpsxiso" dumpsxiso   # overrides the SDK's older copy
  mark_done "mkpsxiso-$MKPSXISO_VERSION" ok
}

# ---------------------------------------------------------------- PCSX-Redux
install_redux() {
  done_stamp "redux-$REDUX_VERSION" && { echo "PCSX-Redux $REDUX_VERSION: already installed"; return; }
  say "PCSX-Redux $REDUX_VERSION (AppImage, extracted so FUSE is not needed)"
  fetch "$REDUX_URL" "$REDUX_SHA256" "$DL/pcsx-redux-$REDUX_VERSION.zip"
  rm -rf "$OPT/pcsx-redux"; mkdir -p "$OPT/pcsx-redux"
  unzip_py "$DL/pcsx-redux-$REDUX_VERSION.zip" "$OPT/pcsx-redux"
  local img; img="$(ls "$OPT"/pcsx-redux/*.AppImage | head -1)"
  chmod +x "$img"
  ( cd "$OPT/pcsx-redux" && "$img" --appimage-extract >/dev/null )
  rm -f "$img"
  # Wrapper: always run the extracted AppRun (fast start, works without FUSE).
  cat > "$BIN/pcsx-redux" <<WRAP
#!/usr/bin/env bash
exec "$OPT/pcsx-redux/squashfs-root/AppRun" "\$@"
WRAP
  chmod +x "$BIN/pcsx-redux"
  mark_done "redux-$REDUX_VERSION" ok
}

# ---------------------------------------------------------------- armips
install_armips() {
  done_stamp "armips-$ARMIPS_COMMIT" && { echo "armips ${ARMIPS_COMMIT:0:8}: already installed"; return; }
  say "armips ${ARMIPS_COMMIT:0:8} (built from source)"
  need cmake "Install cmake >= $CMAKE_MIN (e.g. sudo apt install cmake)."
  command -v g++ >/dev/null 2>&1 || command -v c++ >/dev/null 2>&1 || die "A C++ compiler is required (e.g. sudo apt install build-essential)."
  local src="$TC/src/armips"
  rm -rf "$src"; mkdir -p "$src"
  git -C "$src" init -q
  git -C "$src" remote add origin "$ARMIPS_REPO"
  git -C "$src" fetch -q --depth 1 origin "$ARMIPS_COMMIT"
  git -C "$src" checkout -q FETCH_HEAD
  git -C "$src" submodule update -q --init --depth 1 --recursive
  local log="$TC/armips-build.log"
  { cmake -S "$src" -B "$src/build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
      && cmake --build "$src/build" -j"$(nproc 2>/dev/null || echo 2)" --target armips-bin; } >"$log" 2>&1 \
    || { tail -30 "$log" >&2; die "armips build failed (full log: $log)"; }
  mkdir -p "$OPT/armips"
  cp "$src/build/armips" "$OPT/armips/armips"
  link "$OPT/armips/armips" armips
  mark_done "armips-$ARMIPS_COMMIT" ok
}

# ---------------------------------------------------------------- Python deps
install_python_deps() {
  done_stamp "pydeps-$(sha256sum "$TOOLS/requirements.txt" | cut -c1-12)" && { echo "Python deps: already installed"; return; }
  say "Python dependencies (venv at .toolchain/venv)"
  python3 -m venv "$TC/venv" || die "python3 -m venv failed. On Debian/Ubuntu: sudo apt install python3-venv"
  "$TC/venv/bin/pip" install -q --disable-pip-version-check -r "$TOOLS/requirements.txt"
  mark_done "pydeps-$(sha256sum "$TOOLS/requirements.txt" | cut -c1-12)" ok
}

if [[ "${PS1BOOK_USE_SYSTEM:-0}" == "1" ]]; then
  echo "PS1BOOK_USE_SYSTEM=1: only installing components not already on PATH"
  command -v armips >/dev/null || install_armips
  command -v mipsel-none-elf-gcc >/dev/null || install_psn00bsdk
  command -v mkpsxiso >/dev/null || install_mkpsxiso
  command -v pcsx-redux >/dev/null || install_redux
else
  install_psn00bsdk
  install_mkpsxiso
  install_redux
  install_armips
fi
install_python_deps

if ! command -v xvfb-run >/dev/null 2>&1; then
  echo
  echo "note: xvfb-run not found. The harness runs PCSX-Redux with -cli and does not need it;"
  echo "      it is only useful for running the GUI build on a headless machine"
  echo "      (Debian/Ubuntu: sudo apt install xvfb)."
fi

say "Running doctor.sh"
exec "$TOOLS/doctor.sh"
