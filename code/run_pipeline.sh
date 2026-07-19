#!/usr/bin/env bash
# Deterministic API-offline rebuild. Networked extraction/LOFIN refreshes are opt-in.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CODE="$ROOT/code"
NORM="$ROOT/data/normalized"
LOFIN="$NORM/lofin_local_transfer_candidates_2026.json"

WITH_EXTRACTION=0
REFRESH_LOFIN=0
LOFIN_CACHE_ONLY=0

usage() {
  printf '%s\n' \
    "Usage: code/run_pipeline.sh [--extract] [--refresh-lofin | --lofin-cache-only]" \
    "" \
    "Default: rebuild from existing kordoc chunks and normalized LOFIN candidates." \
    "  --extract           Re-run full kordoc extraction (may invoke npm/network)." \
    "  --refresh-lofin     Refresh selective LOFIN candidates (network/API key required)." \
    "  --lofin-cache-only  Rebuild LOFIN candidates from a complete local cache." \
    "  -h, --help          Show this help."
}

while (($#)); do
  case "$1" in
    --extract)
      WITH_EXTRACTION=1
      ;;
    --refresh-lofin)
      REFRESH_LOFIN=1
      ;;
    --lofin-cache-only)
      LOFIN_CACHE_ONLY=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if ((REFRESH_LOFIN && LOFIN_CACHE_ONLY)); then
  printf '%s\n' '--refresh-lofin and --lofin-cache-only are mutually exclusive' >&2
  exit 2
fi

export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
cd "$ROOT"

printf '%s\n' '[1/9] Python source verification'
bash "$CODE/check_py.sh"

if ((WITH_EXTRACTION)); then
  printf '%s\n' '[2/9] Full kordoc extraction (explicit opt-in)'
  /usr/bin/env python3 "$CODE/extract_with_kordoc.py" --all --chunks-only
else
  printf '%s\n' '[2/9] Reusing existing full kordoc chunks'
fi

printf '%s\n' '[3/9] Parse full PDF business cards'
/usr/bin/env python3 "$CODE/parse_pdfs_kordoc.py"

if ((REFRESH_LOFIN)); then
  printf '%s\n' '[4/9] Refresh selective LOFIN local-transfer candidates'
  /usr/bin/env python3 "$CODE/fetch_lofin_local_transfer_candidates.py"
elif ((LOFIN_CACHE_ONLY)); then
  printf '%s\n' '[4/9] Rebuild selective LOFIN candidates from cache'
  /usr/bin/env python3 "$CODE/fetch_lofin_local_transfer_candidates.py" --cache-only
elif [[ -f "$LOFIN" ]]; then
  printf '%s\n' '[4/9] Reusing normalized selective LOFIN candidates'
else
  printf '%s\n' '[4/9] LOFIN candidate file absent; canonical build will record no LOFIN source'
fi

printf '%s\n' '[5/9] Reconcile PDF cards to the Add2 canonical hierarchy'
/usr/bin/env python3 "$CODE/reconcile_pdf_with_api.py" \
  --pdf-cards "$NORM/pdf_business_cards.json" \
  --api-details "$NORM/expbudgetadd2_2026_pilots_details.json" \
  --lofin "$LOFIN" \
  --tag full \
  --quiet

printf '%s\n' '[6/9] Build canonical dataset and enriched tree'
/usr/bin/env python3 "$CODE/build_canonical_dataset.py" \
  --api-details "$NORM/expbudgetadd2_2026_pilots_details.json" \
  --api-lines "$NORM/expbudgetadd2_2026_pilots_lines.json" \
  --reconcile "$NORM/reconcile_pdf_api_full.json" \
  --lofin "$LOFIN" \
  --year 2026

printf '%s\n' '[7/9] Build workflow and budget-flow models'
/usr/bin/env python3 "$CODE/build_business_workflows.py"
/usr/bin/env python3 "$CODE/build_budget_flow_maps.py"

printf '%s\n' '[8/9] Build three standalone HTML views'
/usr/bin/env python3 "$CODE/build_structure_html.py"
/usr/bin/env python3 "$CODE/build_workflow_html.py"
/usr/bin/env python3 "$CODE/build_budget_flow_html.py"

printf '%s\n' '[9/9] Offline integrated-output verification'
VERIFY_ARGS=()
if [[ -f "$LOFIN" ]]; then
  VERIFY_ARGS+=(--require-lofin)
fi
/usr/bin/env python3 "$CODE/verify_integrated_outputs.py" "${VERIFY_ARGS[@]}"
/usr/bin/env python3 "$CODE/verify_workflow_outputs.py"
/usr/bin/env python3 "$CODE/verify_budget_flow_outputs.py"

printf '%s\n' 'PIPELINE_OK'
