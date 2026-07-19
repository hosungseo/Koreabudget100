#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "[pilot] compile"
/usr/bin/env python3 -m py_compile \
  "$ROOT/code/extract_with_kordoc.py" \
  "$ROOT/code/parse_pdfs_kordoc.py"

echo "[pilot] parse cards from kordoc sample outputs"
/usr/bin/env python3 "$ROOT/code/parse_pdfs_kordoc.py" --pilot-samples

echo "[pilot] DONE"
ls -la "$ROOT/data/normalized/pdf_business_cards_pilot_samples.json" \
  "$ROOT/data/normalized/pdf_parse_summary_pilot_samples.json"
