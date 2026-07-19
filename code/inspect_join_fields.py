#!/usr/bin/env python3
"""Inspect normalized API/PDF fields for join/correction design."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NORM = ROOT / "data" / "normalized"

FILES = [
    "detail_business_2026_pilots.json",
    "detail_business_tree_2026_pilots.json",
    "expbudgetadd2_2026_pilots_details.json",
    "expbudgetadd2_2026_pilots_lines.json",
    "lofin_detail_business_pilot.json",
    "lofin_qwgjk_keyword_matches.json",
    "pdf_business_cards_pilot_samples.json",
    "pdf_business_cards.json",
]


def brief(obj, depth=0):
    if isinstance(obj, list):
        print(f" list n={len(obj)}")
        if not obj:
            return
        x = obj[0]
        if isinstance(x, dict):
            print(" item_keys:", sorted(x.keys()))
            print(" sample:", json.dumps(x, ensure_ascii=False)[:700])
        else:
            print(" item_type:", type(x).__name__, str(x)[:200])
        return
    if isinstance(obj, dict):
        print(" dict_keys:", list(obj.keys())[:30])
        for k, v in list(obj.items())[:6]:
            if isinstance(v, list):
                print(f"  {k}: list n={len(v)}")
                if v and isinstance(v[0], dict):
                    print("   item_keys:", sorted(v[0].keys()))
                    print("   sample:", json.dumps(v[0], ensure_ascii=False)[:450])
            elif isinstance(v, dict):
                print(f"  {k}: dict keys={list(v.keys())[:12]}")
            else:
                print(f"  {k}: {type(v).__name__}={str(v)[:120]}")
        return
    print(" type:", type(obj).__name__)


def main() -> int:
    for name in FILES:
        p = NORM / name
        print("\n===" , name)
        if not p.exists():
            print(" MISS")
            continue
        obj = json.loads(p.read_text(encoding="utf-8"))
        brief(obj)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
