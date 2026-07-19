#!/usr/bin/env python3
"""Offline integrity checks for the money-first budget-flow deliverables."""

from __future__ import annotations

import collections
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "normalized" / "budget_flow_maps_2026_pilots.json"
SUMMARY = ROOT / "artifacts" / "budget_flow_maps_2026_pilots_summary.json"
HTML = ROOT / "artifacts" / "budget_flow_map.html"
HTML_YEAR = ROOT / "artifacts" / "budget_flow_map_2026.html"

EXPECTED_COUNT = 1_401
EXPECTED_TOTAL = 133_546_671_000_000
REFERENCE_ID = "kb-ace0474d507615f7"
REFERENCE_TITLE = "지역사회 자생적 창조역량 강화"
REFERENCE_TOTAL = 23_753_000_000


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AssertionError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AssertionError(f"invalid JSON: {path}: {exc}") from exc


def amount(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(result):
        return 0
    return int(round(result))


def same(left: Any, right: Any) -> bool:
    return amount(left) == amount(right)


def verify_all_maps(payload: dict[str, Any]) -> dict[str, Any]:
    maps = payload.get("maps")
    assert isinstance(maps, list), "maps must be a list"
    assert len(maps) == EXPECTED_COUNT, f"map count {len(maps)} != {EXPECTED_COUNT}"
    ids = [str(row.get("id") or "") for row in maps if isinstance(row, dict)]
    assert len(ids) == len(maps), "every map must be an object"
    assert "" not in ids, "map id missing"
    assert len(set(ids)) == len(ids), "duplicate map ids"

    total = 0
    channel_counts: collections.Counter[str] = collections.Counter()
    for row in maps:
        map_id = str(row["id"])
        core = row.get("core")
        assert isinstance(core, dict), f"{map_id}: core missing"
        business_total = amount(core.get("congress_amt"))
        assert business_total >= 0, f"{map_id}: negative total"
        total += business_total

        items = row.get("budget_items")
        channels = row.get("channels")
        assert isinstance(items, list), f"{map_id}: budget items must be a list"
        assert isinstance(channels, list), f"{map_id}: channels must be a list"
        if business_total:
            assert items, f"{map_id}: funded business has no budget items"
            assert channels, f"{map_id}: funded business has no channels"
        else:
            assert not items and not channels, f"{map_id}: zero business must not invent items or channels"
        item_ids = [str(item.get("id") or "") for item in items]
        channel_ids = [str(channel.get("id") or "") for channel in channels]
        assert "" not in item_ids and len(set(item_ids)) == len(item_ids), f"{map_id}: invalid item ids"
        assert "" not in channel_ids and len(set(channel_ids)) == len(channel_ids), f"{map_id}: invalid channel ids"
        assert sum(amount(item.get("amount_won")) for item in items) == business_total, f"{map_id}: item total mismatch"
        assert sum(amount(channel.get("amount_won")) for channel in channels) == business_total, f"{map_id}: channel total mismatch"

        referenced_items: list[str] = []
        item_by_id = {str(item["id"]): item for item in items}
        channel_by_id = {str(channel["id"]): channel for channel in channels}
        for channel in channels:
            code = str(channel.get("code") or "")
            assert code, f"{map_id}: channel code missing"
            channel_counts[code] += amount(channel.get("amount_won"))
            refs = channel.get("item_ids")
            assert isinstance(refs, list) and refs, f"{map_id}: empty channel item list"
            referenced_items.extend(str(value) for value in refs)
            assert sum(amount(item_by_id[str(value)].get("amount_won")) for value in refs) == amount(channel.get("amount_won")), f"{map_id}: channel item sum mismatch"
            for value in refs:
                item = item_by_id.get(str(value))
                assert item is not None, f"{map_id}: unknown channel item {value}"
                assert str(item.get("channel_code")) == code, f"{map_id}: item channel code mismatch"
        assert collections.Counter(referenced_items) == collections.Counter(item_ids), f"{map_id}: items must belong to exactly one channel"

        reconciliation = row.get("reconciliation")
        assert isinstance(reconciliation, dict), f"{map_id}: reconciliation missing"
        assert reconciliation.get("budget_items_reconciled") is True, f"{map_id}: API reconciliation false"
        assert same(reconciliation.get("business_total_won"), business_total), f"{map_id}: reconciliation business total"
        assert same(reconciliation.get("budget_item_total_won"), business_total), f"{map_id}: reconciliation item total"
        if reconciliation.get("subprojects_reconciled") is True:
            assert sum(amount(value.get("amount_won")) for value in row.get("subprojects") or []) == business_total, f"{map_id}: PDF reconciliation false"

        sub_ids = {str(value.get("id") or "") for value in row.get("subprojects") or []}
        for crosswalk in row.get("crosswalks") or []:
            assert str(crosswalk.get("subproject_id")) in sub_ids, f"{map_id}: unknown crosswalk subproject"
            assert str(crosswalk.get("channel_id")) in channel_by_id, f"{map_id}: unknown crosswalk channel"
            assert amount(crosswalk.get("amount_won")) > 0, f"{map_id}: empty crosswalk amount"

        for candidate in row.get("local_candidates") or []:
            assert candidate.get("match_status") == "keyword_candidate", f"{map_id}: LOFIN status"
            assert candidate.get("additive") is False, f"{map_id}: LOFIN candidate must be non-additive"

    assert total == EXPECTED_TOTAL, f"portfolio total {total} != {EXPECTED_TOTAL}"
    return {"maps": maps, "total": total, "channel_counts": channel_counts}


def verify_reference(maps: list[dict[str, Any]]) -> None:
    rows = [row for row in maps if row.get("id") == REFERENCE_ID]
    assert len(rows) == 1, "reference business missing or duplicated"
    row = rows[0]
    assert row.get("title") == REFERENCE_TITLE
    assert amount(row.get("core", {}).get("congress_amt")) == REFERENCE_TOTAL
    assert row.get("is_reference") is True
    expected_subprojects = {
        "청년 유입 및 체류 지원": 6_764_000_000,
        "데이터 기반 지역문제해결 사업": 1_000_000_000,
        "지역주도 민관협력체계 구축 및 확산": 2_500_000_000,
        "다부처 협업 지역역량성장거점 활성화": 1_650_000_000,
        "사회연대경제 활성화": 11_839_000_000,
    }
    actual_subprojects = {
        str(value.get("label")): amount(value.get("amount_won"))
        for value in row.get("subprojects") or []
    }
    assert actual_subprojects == expected_subprojects
    expected_items = {
        "자치단체경상보조": 11_950_000_000,
        "일반용역비": 9_939_000_000,
        "민간위탁사업비": 982_000_000,
        "일반수용비": 414_000_000,
        "정책연구비": 300_000_000,
        "임차료": 77_000_000,
        "국내여비": 57_000_000,
        "사업추진비": 34_000_000,
    }
    actual_items = {
        str(value.get("semok_name")): amount(value.get("amount_won"))
        for value in row.get("budget_items") or []
    }
    assert actual_items == expected_items
    expected_channels = {
        "local_subsidy": 11_950_000_000,
        "private_delegation": 982_000_000,
        "procurement": 10_239_000_000,
        "internal": 582_000_000,
    }
    actual_channels = {
        str(value.get("code")): amount(value.get("amount_won"))
        for value in row.get("channels") or []
    }
    assert actual_channels == expected_channels
    local = next(value for value in row["channels"] if value.get("code") == "local_subsidy")
    assert local.get("support_rate") == "50%"
    assert amount(row.get("reconciliation", {}).get("documented_crosswalk_won")) == 14_421_000_000
    assert row.get("local_candidates") == []
    assert row.get("implementation", {}).get("beneficiary") == "일반 국민"
    assert any("17개 광역시도" in str(value) for value in row.get("insights") or [])


def verify_summary(summary: dict[str, Any], checked: dict[str, Any]) -> None:
    assert amount(summary.get("map_count")) == EXPECTED_COUNT
    assert amount(summary.get("business_total_won")) == EXPECTED_TOTAL
    assert amount(summary.get("api_reconciled_count")) == EXPECTED_COUNT
    assert summary.get("default_business_id") == REFERENCE_ID
    assert summary.get("reference_business_title") == REFERENCE_TITLE
    actual = {str(key): amount(value) for key, value in (summary.get("channel_totals_won") or {}).items()}
    assert actual == dict(checked["channel_counts"])


def verify_html(payload: dict[str, Any]) -> None:
    try:
        html = HTML.read_text(encoding="utf-8")
        alias = HTML_YEAR.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AssertionError(f"missing HTML output: {exc.filename}") from exc
    assert html == alias, "year HTML alias differs"
    required = [
        "Koreabudget100 · 2026 예산체계도",
        "확정재원이 갈라지고 닿는 구조",
        "재원·회계 → 내역사업 → 목·세목 → 집행채널 → 기관·지역·수혜",
        "PDF↔API 직접 대사",
        "업무 절차 · 보조",
        REFERENCE_TITLE,
        REFERENCE_ID,
    ]
    for value in required:
        assert value in html, f"HTML missing {value!r}"
    assert '<meta http-equiv="refresh"' not in html.lower(), "budget map must not redirect"
    match = re.search(
        r'<script id="budget-data" type="application/json">(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    assert match, "embedded budget JSON missing"
    embedded = json.loads(match.group(1))
    assert embedded.get("meta") == payload.get("meta"), "embedded meta differs"
    assert len(embedded.get("maps") or []) == EXPECTED_COUNT, "embedded map count differs"


def main() -> int:
    try:
        payload = load_json(DATA)
        summary = load_json(SUMMARY)
        assert isinstance(payload, dict) and isinstance(summary, dict)
        checked = verify_all_maps(payload)
        verify_reference(checked["maps"])
        verify_summary(summary, checked)
        verify_html(payload)
    except AssertionError as exc:
        print(f"BUDGET_FLOW_VERIFY_FAILED: {exc}", file=sys.stderr)
        return 1
    print(
        "BUDGET_FLOW_VERIFY_OK "
        f"maps={EXPECTED_COUNT} total={EXPECTED_TOTAL} reference={REFERENCE_ID}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
