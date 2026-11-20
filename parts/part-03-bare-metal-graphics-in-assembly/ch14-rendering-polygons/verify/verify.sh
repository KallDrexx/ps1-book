#!/usr/bin/env bash
# Chapter verify entry point. Copy to <chapter>/verify/verify.sh and chmod +x.
# Thin wrapper: all logic lives in tools/verify-lib/harness.py and ./checks.py.
#
#   ./verify.sh [path-to-reader-project]   verify a project (default: ../starter)
#   ./verify.sh --solution                 verify ../solution (used by CI)
#   ./verify.sh -v                         also show build output + emulator log
#   ./verify.sh --keep                     keep the temp work dir (screenshots, VRAM, logs)
#
# Exit code: 0 = all checks passed, 1 = build error or failed checks, 2 = tooling problem.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHAPTER_DIR="$(cd "$HERE/.." && pwd)"
# <repo>/parts/part-NN-slug/chNN-slug/verify/verify.sh  ->  repo root is 4 levels up from here
ROOT="$(cd "$HERE/../../../.." && pwd)"
[[ -f "$ROOT/tools/env.sh" ]] || { echo "verify.sh: book root not found at $ROOT (run it from inside the book checkout)" >&2; exit 2; }
# shellcheck source=/dev/null
source "$ROOT/tools/env.sh"
exec "$PS1BOOK_PYTHON" "$ROOT/tools/verify-lib/harness.py" --chapter-dir "$CHAPTER_DIR" "$@"
