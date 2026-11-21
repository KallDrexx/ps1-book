#!/usr/bin/env bash
# Checks that every tool the book needs is present and the right version.
# Prints OK / MISSING / WARN per tool. Exit code 1 if anything required is missing.
TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=versions.txt
source "$TOOLS/versions.txt"
# shellcheck source=env.sh
source "$TOOLS/env.sh"

missing=0
row() { printf '  %-8s %-14s %s\n' "$1" "$2" "$3"; }
ok()   { row "OK" "$1" "$2"; }
bad()  { row "MISSING" "$1" "$2"; missing=$((missing+1)); }
warn() { row "WARN" "$1" "$2"; }

echo "PS1 book toolchain check (toolchain dir: $PS1BOOK_TOOLCHAIN)"

# armips
if command -v armips >/dev/null 2>&1; then
  v="$(armips 2>&1 | head -1)"
  if [[ "$v" =~ $ARMIPS_VERSION_RE ]]; then ok armips "$v"; else bad armips "wrong version: '$v' (want $ARMIPS_VERSION_RE); run tools/setup.sh --force"; fi
else bad armips "not found; run tools/setup.sh"; fi

# GCC
if command -v mipsel-none-elf-gcc >/dev/null 2>&1; then
  v="$(mipsel-none-elf-gcc --version 2>&1 | head -1)"
  if [[ "$v" =~ $GCC_VERSION_RE ]]; then ok mips-gcc "$v"; else warn mips-gcc "unexpected version: $v (book pinned to $GCC_VERSION_RE)"; fi
else bad mips-gcc "mipsel-none-elf-gcc not found; run tools/setup.sh"; fi
for t in mipsel-none-elf-nm mipsel-none-elf-objdump; do
  command -v $t >/dev/null 2>&1 || bad "$t" "binutils tool not found; run tools/setup.sh"
done

# PSn00bSDK
if [[ -f "$PSN00BSDK_LIBS/cmake/sdk.cmake" ]]; then ok psn00bsdk "PSN00BSDK_LIBS=$PSN00BSDK_LIBS"
else bad psn00bsdk "sdk.cmake not found under PSN00BSDK_LIBS=$PSN00BSDK_LIBS; run tools/setup.sh"; fi

# PCSX-Redux
if command -v pcsx-redux >/dev/null 2>&1; then
  v="$(pcsx-redux -version 2>/dev/null | sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' | head -1)"
  if [[ -z "$v" ]]; then bad pcsx-redux "installed but '-version' failed (needs OpenGL libs? see appendices/F-troubleshooting.md)"
  elif [[ "$v" == "$REDUX_VERSION" ]]; then ok pcsx-redux "build $v"
  else warn pcsx-redux "build $v (book pinned to $REDUX_VERSION)"; fi
else bad pcsx-redux "not found; run tools/setup.sh"; fi

# mkpsxiso
if command -v mkpsxiso >/dev/null 2>&1; then
  v="$(mkpsxiso 2>&1 | head -1)"
  if [[ "$v" == *"$MKPSXISO_VERSION"* ]]; then ok mkpsxiso "$v"; else warn mkpsxiso "$v (book pinned to $MKPSXISO_VERSION)"; fi
else bad mkpsxiso "not found; run tools/setup.sh"; fi

# cmake / make
if command -v cmake >/dev/null 2>&1; then
  v="$(cmake --version | head -1 | awk '{print $3}')"
  if [[ "$(printf '%s\n%s\n' "$CMAKE_MIN" "$v" | sort -V | head -1)" == "$CMAKE_MIN" ]]; then ok cmake "$v"; else bad cmake "$v < required $CMAKE_MIN"; fi
else bad cmake "not found (Debian/Ubuntu: sudo apt install cmake)"; fi
command -v make >/dev/null 2>&1 && ok make "$(make --version | head -1)" || bad make "not found (sudo apt install build-essential)"
if command -v ninja >/dev/null 2>&1; then ok ninja "$(ninja --version)"; else bad ninja "not found; run tools/setup.sh"; fi

# Python
py="$PS1BOOK_PYTHON"
if [[ -n "$py" ]] && "$py" -c "import sys; sys.exit(0 if sys.version_info >= tuple(map(int,'$PYTHON_MIN'.split('.'))) else 1)" 2>/dev/null; then
  ok python "$($py --version 2>&1) ($py)"
  if "$py" -c "import PIL" 2>/dev/null; then ok pillow "$($py -c 'import PIL; print(PIL.__version__)')"; else bad pillow "Python package missing; run tools/setup.sh"; fi
else bad python "Python >= $PYTHON_MIN not found"; fi

# optional
if command -v xvfb-run >/dev/null 2>&1; then ok xvfb-run "(optional) present"; else warn xvfb-run "(optional) not found; harness uses 'pcsx-redux -cli' and does not need it"; fi

echo
if [[ $missing -eq 0 ]]; then echo "doctor: all required tools OK"; exit 0
else echo "doctor: $missing required item(s) missing"; exit 1; fi
