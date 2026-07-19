#!/usr/bin/env bash
# File-only Python health check for Koreabudget100.
# Never uses python3 -c or heredoc bodies.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CODE="$ROOT/code"

echo "[check_py] root=$ROOT"

if (( $# > 1 )) || { (( $# == 1 )) && [[ "$1" != "--fix" ]]; }; then
  echo "usage: $0 [--fix]" >&2
  exit 2
fi

# A broken source cannot compile, so repair must precede every compile check.
if [[ "${1:-}" == "--fix" ]]; then
  /usr/bin/env python3 "$CODE/_fix_newlines.py" --fix
  echo "[check_py] _fix_newlines --fix and re-verification ok"
else
  /usr/bin/env python3 "$CODE/_fix_newlines.py"
  echo "[check_py] _fix_newlines scan ok"
fi

# Compile every project script as files (glob expands to paths, not stdin).
/usr/bin/env python3 -m py_compile "$CODE"/*.py
echo "[check_py] py_compile ok"

# Run verifier through the shell wrapper (absolute file path).
bash "$CODE/run_verify.sh"
echo "[check_py] verify_py_sources ok"

echo "CHECK_OK"
