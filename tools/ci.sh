#!/usr/bin/env bash
# For every chapter under parts/: verify.sh --solution must exit 0 and verify.sh
# on the untouched starter must build and then exit 1 (failed checks, not a
# build error or tooling crash). Prints a table.
#   tools/ci.sh            all chapters
#   tools/ci.sh ch07       only chapter dirs whose path contains "ch07"
# Before the chapters, tools/assets/selftest.py proves the asset generators match Appendix E
# (set PS1BOOK_SKIP_ASSET_SELFTEST=1 to skip it).
# PS1BOOK_PARTS_DIR overrides the parts/ location (used for testing the CI itself).
TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$TOOLS/.." && pwd)"
PARTS="${PS1BOOK_PARTS_DIR:-$ROOT/parts}"
FILTER="${1:-}"

if [[ -z "${PS1BOOK_SKIP_ASSET_SELFTEST:-}" ]]; then
  ST_LOG="$(mktemp)"
  if ( source "$TOOLS/env.sh"; exec timeout 300 "$PS1BOOK_PYTHON" "$TOOLS/assets/selftest.py" ) >"$ST_LOG" 2>&1; then
    echo "ci: asset selftest OK ($(tail -1 "$ST_LOG"))"; rm -f "$ST_LOG"
  else
    cat "$ST_LOG"; rm -f "$ST_LOG"; echo "ci: asset selftest FAILED (tools/assets vs appendices/E-file-formats.md)"; exit 1
  fi
fi

shopt -s nullglob
chapters=()
for d in "$PARTS"/*/ch*/; do
  d="${d%/}"
  [[ -n "$FILTER" && "$d" != *"$FILTER"* ]] && continue
  chapters+=("$d")
done

if [[ ${#chapters[@]} -eq 0 ]]; then
  echo "ci: no chapters found under $PARTS${FILTER:+ matching '$FILTER'}; nothing to verify."
  exit 0
fi

"$TOOLS/doctor.sh" >/dev/null 2>&1 || { echo "ci: tools/doctor.sh reports missing tools; run tools/setup.sh"; exit 2; }

LOGDIR="$(mktemp -d)"; trap 'rm -rf "$LOGDIR"' EXIT
fails=0
rows=()
for ch in "${chapters[@]}"; do
  name="$(basename "$ch")"
  v="$ch/verify/verify.sh"
  if [[ ! -x "$v" ]]; then
    rows+=("$(printf '%-34s %-10s %-10s %s' "$name" "-" "-" "BAD (no executable verify/verify.sh)")")
    fails=$((fails+1)); continue
  fi
  "$v" --solution >"$LOGDIR/$name.sol.log" 2>&1; src=$?
  if [[ -d "$ch/starter" ]]; then
    "$v" >"$LOGDIR/$name.st.log" 2>&1; trc=$?
  else
    trc=-1; echo "starter/ directory is missing" >"$LOGDIR/$name.st.log"
  fi
  s_res="pass"; [[ $src -ne 0 ]] && s_res="FAIL($src)"
  t_res="fails"; [[ $trc -ne 1 ]] && t_res="WRONG($trc)"
  # The starter must build (Summary §3: "compiles, but incomplete"); a build error is not a valid failure.
  if [[ $trc -eq 1 ]] && grep -q 'FAILED (build error)' "$LOGDIR/$name.st.log"; then t_res="NOBUILD"; trc=3; fi
  status="OK"
  if [[ $src -ne 0 || $trc -ne 1 ]]; then status="BAD"; fails=$((fails+1)); fi
  rows+=("$(printf '%-34s %-10s %-10s %s' "$name" "$s_res" "$t_res" "$status")")
  if [[ $src -ne 0 ]]; then echo "---- $name: solution should PASS (exit $src) ----"; tail -25 "$LOGDIR/$name.sol.log"; fi
  if [[ $trc -ne 1 ]]; then echo "---- $name: starter should build, then FAIL its checks with exit 1 (got: $t_res) ----"; tail -25 "$LOGDIR/$name.st.log"; fi
done

echo
printf '%-34s %-10s %-10s %s\n' "CHAPTER" "SOLUTION" "STARTER" "STATUS"
printf '%-34s %-10s %-10s %s\n' "-------" "--------" "-------" "------"
printf '%s\n' "${rows[@]}"
echo
echo "(SOLUTION must pass; STARTER must build and then fail its checks with exit 1)"
if [[ $fails -eq 0 ]]; then echo "ci: all ${#chapters[@]} chapter(s) OK"; exit 0
else echo "ci: $fails chapter(s) BAD"; exit 1; fi
