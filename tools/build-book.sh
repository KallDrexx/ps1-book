#!/usr/bin/env bash
# Build the book as PDF and EPUB:  tools/build-book.sh REVISION
# Output: output/Programming-PS1-Games-r<REVISION>.pdf and .epub
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$here/env.sh"
exec "$PS1BOOK_PYTHON" "$here/build_book.py" "$@"
