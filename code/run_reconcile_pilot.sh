#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
/usr/bin/env python3 -m py_compile "$ROOT/code/reconcile_pdf_with_api.py"
/usr/bin/env python3 "$ROOT/code/reconcile_pdf_with_api.py" --tag pilot_samples
