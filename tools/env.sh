# Source this to put the book toolchain on PATH:  source tools/env.sh
_PS1B_TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PS1BOOK_ROOT="$(cd "$_PS1B_TOOLS/.." && pwd)"
PS1BOOK_TOOLCHAIN="${PS1BOOK_TOOLCHAIN:-$PS1BOOK_ROOT/.toolchain}"
export PS1BOOK_ROOT PS1BOOK_TOOLCHAIN
export PATH="$PS1BOOK_TOOLCHAIN/bin:$PATH"
export PSN00BSDK_LIBS="${PSN00BSDK_LIBS:-$PS1BOOK_TOOLCHAIN/opt/psn00bsdk/lib/libpsn00b}"
if [ -x "$PS1BOOK_TOOLCHAIN/venv/bin/python" ]; then
  export PS1BOOK_PYTHON="$PS1BOOK_TOOLCHAIN/venv/bin/python"
else
  export PS1BOOK_PYTHON="$(command -v python3)"
fi
unset _PS1B_TOOLS
