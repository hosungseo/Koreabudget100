#!/usr/bin/env bash
# Always run the verifier as a file. Never inline python.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="$SCRIPT_DIR/verify_py_sources.py"

if [[ ! -f "$TARGET" ]]; then
  echo "missing: $TARGET" >&2
  exit 2
fi

# Force absolute path + binary exec form so shells/tools cannot rewrite this
# into a python -c / heredoc inline body.
exec /usr/bin/env python3 "$TARGET" "$@"
