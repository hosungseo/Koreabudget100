#!/usr/bin/env python3
"""Fetch a small QWGJK time series for the single-business reference page."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from fetch_lofin_local_transfer_candidates import (
    dedupe_rows,
    load_key,
    load_or_fetch_keyword,
    normalize_row,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "normalized" / "reference_lofin_timeline_2026.json"
YEAR = 2026
KEYWORD = "사회연대경제"
DATES = (
    "20260131",
    "20260228",
    "20260331",
    "20260430",
    "20260531",
    "20260630",
    "20260718",
)
CENTRAL_KEY = [
    "2026",
    "행정안전부",
    "지역균형발전특별회계",
    "정부혁신조직",
    "주민참여 지역문제 해결 확산",
    "지역사회 자생적 창조역량 강화",
]


def number(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^0-9a-z가-힣]+", "", text)


def tier_for_title(value: Any) -> str:
    title = normalize(value)
    if "혁신모델" in title:
        return "strong"
    if (
        "생태계활성화" in title
        or "활력제고" in title
        or ("사회연대경제활성화" in title and "청년일경험" not in title)
    ):
        return "broad"
    return "verify"


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    budget = sum(number(row.get("budget_cash_amt")) for row in rows)
    spend = sum(number(row.get("spend_amt")) for row in rows)
    return {
        "row_count": len(rows),
        "local_gov_count": len(
            {
                str(row.get("local_gov_code") or row.get("local_gov_name") or "")
                for row in rows
            }
        ),
        "budget_cash_amt": budget,
        "national_amt": sum(number(row.get("national_amt")) for row in rows),
        "sido_amt": sum(number(row.get("sido_amt")) for row in rows),
        "sigungu_amt": sum(number(row.get("sigungu_amt")) for row in rows),
        "spend_amt": spend,
        "observed_rate": round(spend / budget, 6) if budget else None,
        "non_additive": True,
    }


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.refresh and args.cache_only:
        parser.error("--refresh and --cache-only are mutually exclusive")

    key = None if args.cache_only else load_key()
    candidate = {
        "central_business_key": CENTRAL_KEY,
        "central_business_name": CENTRAL_KEY[-1],
        "central_local_transfer_amount_won": 11_950_000_000,
        "keyword": KEYWORD,
        "keyword_strategy": "documented_pdf_subproject_title",
        "match_scope": "pdf_subproject_keyword",
        "matched_subproject_name": "사회연대경제 활성화",
    }
    snapshots = []
    for date in DATES:
        raw_rows, pages, source, path = load_or_fetch_keyword(
            key,
            year=YEAR,
            exe_ymd=date,
            keyword=KEYWORD,
            psize=1000,
            max_pages=10,
            delay=0.12,
            refresh=args.refresh,
            cache_only=args.cache_only,
        )
        rows = []
        for raw in raw_rows:
            row = normalize_row(raw, candidate, YEAR, date)
            if row is None:
                continue
            row["candidate_tier"] = tier_for_title(row.get("detail_business_name"))
            rows.append(row)
        rows = dedupe_rows(rows)
        rows.sort(
            key=lambda row: (
                {"strong": 0, "broad": 1, "verify": 2}[str(row["candidate_tier"])],
                -number(row.get("national_amt")),
                str(row.get("local_gov_name") or ""),
                str(row.get("detail_business_code") or ""),
            )
        )
        snapshots.append(
            {
                "exe_ymd": date,
                "cache_source": source,
                "cache_path": str(path.relative_to(ROOT)),
                "page_count": len(pages),
                "row_count": len(rows),
                "tiers": {
                    tier: summarize(
                        [row for row in rows if row.get("candidate_tier") == tier]
                    )
                    for tier in ("strong", "broad", "verify")
                },
                "rows": rows,
            }
        )
        print(date, len(rows), source)

    payload = {
        "schema_version": "1.0",
        "source": "lofin_QWGJK",
        "year": YEAR,
        "keyword": KEYWORD,
        "match_status": "keyword_candidate",
        "snapshot_semantics": "조회기준일의 지방 세부사업별 예산현액·재원·지출 상태",
        "non_additive": True,
        "dates": list(DATES),
        "snapshots": snapshots,
    }
    atomic_json(OUT, payload)
    print(json.dumps({"output": str(OUT), "snapshots": len(snapshots)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
