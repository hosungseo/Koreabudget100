#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the one-business budget structure page used as the primary demo."""

from __future__ import annotations

import json
import re
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "normalized" / "budget_flow_maps_2026_pilots.json"
TIMELINE = ROOT / "data" / "normalized" / "reference_lofin_timeline_2026.json"
OUT = ROOT / "artifacts" / "reference_budget_flow_map.html"
REFERENCE_ID = "kb-ace0474d507615f7"

DETAILED_CROSSWALK = (
    {
        "subproject_id": "sub-01",
        "allocations": (
            ("general_service", 6_689_000_000, "내용·금액 대사"),
            ("management", 75_000_000, "문서 산출"),
        ),
    },
    {
        "subproject_id": "sub-02",
        "allocations": (
            ("private_delegation", 982_000_000, "문서·API 직접 대사"),
            ("management", 18_000_000, "문서 산출"),
        ),
    },
    {
        "subproject_id": "sub-03",
        "allocations": (
            ("policy_research", 300_000_000, "내용·금액 대사"),
            ("general_service", 2_150_000_000, "내용·금액 대사"),
            ("management", 50_000_000, "문서 산출"),
        ),
    },
    {
        "subproject_id": "sub-04",
        "allocations": (
            ("local_subsidy", 1_600_000_000, "문서·API 직접 대사"),
            ("management", 50_000_000, "문서 산출"),
        ),
    },
    {
        "subproject_id": "sub-05",
        "allocations": (
            ("local_subsidy", 10_350_000_000, "문서·API 직접 대사"),
            ("general_service", 1_100_000_000, "문서 산출·금액 대사"),
            ("management", 389_000_000, "문서 산출"),
        ),
    },
)

BUCKET_LABELS = {
    "local_subsidy": "지자체경상보조",
    "general_service": "일반용역비",
    "private_delegation": "민간위탁사업비",
    "policy_research": "정책연구비",
    "management": "운영·사업관리",
}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return value


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


def candidate_tier(row: dict[str, Any]) -> str:
    """Separate PDF-wording candidates from broad QWGJK keyword neighbours."""

    title = normalize(row.get("detail_business_name"))
    alignment = str(row.get("name_alignment") or "")
    if "혁신모델" in title:
        return "strong"
    if (
        "생태계활성화" in title
        or "활력제고" in title
        or alignment in {"exact_title", "title_overlap"}
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
        "wide_area_row_count": sum(row.get("local_level") == "광역본청" for row in rows),
        "basic_row_count": sum(row.get("local_level") == "기초" for row in rows),
        "budget_cash_amt": budget,
        "national_amt": sum(number(row.get("national_amt")) for row in rows),
        "sido_amt": sum(number(row.get("sido_amt")) for row in rows),
        "sigungu_amt": sum(number(row.get("sigungu_amt")) for row in rows),
        "other_amt": sum(number(row.get("other_amt")) for row in rows),
        "spend_amt": spend,
        "execution_rate": round(spend / budget, 6) if budget else None,
        "non_additive": True,
    }


def prepare_payload(
    source: dict[str, Any], timeline: dict[str, Any]
) -> dict[str, Any]:
    maps = source.get("maps")
    if not isinstance(maps, list):
        raise SystemExit("budget-flow maps missing")
    matches = [row for row in maps if isinstance(row, dict) and row.get("id") == REFERENCE_ID]
    if len(matches) != 1:
        raise SystemExit(f"reference business count must be 1, got {len(matches)}")
    budget_map = deepcopy(matches[0])
    baseline_rows = [
        row for row in budget_map.get("local_candidates") or [] if isinstance(row, dict)
    ]
    snapshots = timeline.get("snapshots")
    if not isinstance(snapshots, list) or len(snapshots) < 2:
        raise SystemExit("reference LOFIN timeline is missing snapshots")
    latest = snapshots[-1]
    rows = [deepcopy(row) for row in latest.get("rows") or [] if isinstance(row, dict)]
    for row in rows:
        row["candidate_tier"] = str(row.get("candidate_tier") or candidate_tier(row))
    order = {"strong": 0, "broad": 1, "verify": 2}
    rows.sort(
        key=lambda row: (
            order[str(row["candidate_tier"])],
            -number(row.get("national_amt")),
            str(row.get("region_name") or ""),
            str(row.get("local_gov_name") or ""),
            str(row.get("detail_business_code") or ""),
        )
    )
    budget_map["local_candidates"] = rows
    tier_summary = {
        tier: summarize([row for row in rows if row["candidate_tier"] == tier])
        for tier in ("strong", "broad", "verify")
    }
    assert len(baseline_rows) == 23
    assert [tier_summary[tier]["row_count"] for tier in ("strong", "broad", "verify")] == [9, 3, 15]
    assert tier_summary["strong"]["national_amt"] == 4_000_000_000
    assert tier_summary["strong"]["spend_amt"] == 2_041_015_000
    central_subsidy = next(
        number(row.get("amount_won"))
        for row in budget_map.get("crosswalks") or []
        if row.get("subproject_id") == "sub-05"
        and row.get("channel_id") == "channel-local_subsidy"
    )
    latest_summary = summarize(rows)
    latest_summary.update(
        {
            "candidate_count": len(rows),
            "snapshot_date": str(latest.get("exe_ymd") or ""),
            "wide_area_row_count": sum(
                row.get("local_level") == "광역본청" for row in rows
            ),
            "basic_row_count": sum(row.get("local_level") == "기초" for row in rows),
            "region_count": len(
                {str(row.get("region_code") or row.get("region_name") or "") for row in rows}
            ),
        }
    )
    observed_national = number(latest_summary.get("national_amt"))
    budget_map["local_candidate_total_count"] = len(rows)
    budget_map.pop("local_groups", None)
    budget_map.pop("local_group_total_count", None)
    budget_map.pop("crosswalks", None)
    budget_map["insights"] = [
        "PDF 내역사업과 Add2 회계버킷은 같은 237.53억원을 보는 두 분류입니다.",
        "PDF 산출내용·금액과 Add2 회계버킷을 수작업 검토해 237.53억원 전액을 대사했습니다.",
        "사회연대경제 활성화 118.39억원 중 지방이전 연결 기준은 지자체보조 103.50억원입니다.",
        f"LOFIN 최신 {len(rows)}행은 명칭 근거에 따라 A/B/C 후보로 분리했습니다.",
        "LOFIN 행과 시계열은 지방 예산·지출 스냅샷이며 중앙 교부표나 거래 이력이 아닙니다.",
    ]
    subprojects = {
        str(row.get("id")): row for row in budget_map.get("subprojects") or []
    }
    items = {str(row.get("semok_name")): row for row in budget_map.get("budget_items") or []}
    expected_buckets = {
        "local_subsidy": number(items["자치단체경상보조"].get("amount_won")),
        "general_service": number(items["일반용역비"].get("amount_won")),
        "private_delegation": number(items["민간위탁사업비"].get("amount_won")),
        "policy_research": number(items["정책연구비"].get("amount_won")),
        "management": sum(
            number(items[label].get("amount_won"))
            for label in ("일반수용비", "임차료", "국내여비", "사업추진비")
        ),
    }
    bucket_totals = {key: 0 for key in BUCKET_LABELS}
    detailed_crosswalk = []
    for definition in DETAILED_CROSSWALK:
        subproject_id = str(definition["subproject_id"])
        subproject = subprojects[subproject_id]
        allocations = [
            {
                "bucket_id": bucket_id,
                "bucket_label": BUCKET_LABELS[bucket_id],
                "amount_won": amount_won,
                "assertion_label": assertion_label,
            }
            for bucket_id, amount_won, assertion_label in definition["allocations"]
        ]
        assert sum(row["amount_won"] for row in allocations) == number(
            subproject.get("amount_won")
        )
        for allocation in allocations:
            bucket_totals[allocation["bucket_id"]] += allocation["amount_won"]
        detailed_crosswalk.append(
            {
                "subproject_id": subproject_id,
                "subproject_marker": subproject.get("marker"),
                "subproject_label": subproject.get("label"),
                "amount_won": number(subproject.get("amount_won")),
                "allocations": allocations,
                "assertion": "content_amount_reconciled",
                "transaction_flow": False,
            }
        )
    for subproject in budget_map.get("subprojects") or []:
        if isinstance(subproject, dict):
            subproject.pop("crosswalks", None)
    assert bucket_totals == expected_buckets
    assert sum(bucket_totals.values()) == number(budget_map["core"]["congress_amt"])
    budget_map["detailed_crosswalk"] = detailed_crosswalk
    budget_map["accounting_buckets"] = [
        {
            "id": key,
            "label": BUCKET_LABELS[key],
            "amount_won": bucket_totals[key],
            "assertion": "confirmed_add2",
        }
        for key in BUCKET_LABELS
    ]
    budget_map["detailed_reconciliation"] = {
        "amount_won": sum(bucket_totals.values()),
        "share": 1.0,
        "difference_won": 0,
        "transaction_flow": False,
        "method": "PDF content and amount to Add2 accounting-bucket reconciliation",
    }
    budget_map["candidate_tier_summary"] = tier_summary
    budget_map["local_summary"] = latest_summary
    budget_map["comparison_warning"] = {
        "central_subsidy_won": central_subsidy,
        "observed_national_won": observed_national,
        "difference_won": observed_national - central_subsidy,
        "difference_ratio": round((observed_national - central_subsidy) / central_subsidy, 6),
        "reconcilable": False,
    }
    return {
        "meta": {
            "year": (source.get("meta") or {}).get("year", 2026),
            "business_id": REFERENCE_ID,
            "scope": "single-business reference",
        },
        "map": budget_map,
        "timeline": timeline,
    }


def safe_json(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


HTML = r'''<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="color-scheme" content="light dark" />
  <meta name="description" content="지역사회 자생적 창조역량 강화 단일 세부사업의 중앙예산·사업설명자료·지방재정 관측을 구분한 예산체계도" />
  <title>지역사회 자생적 창조역량 강화 · 예산체계도</title>
  <style>
    :root {
      --bg: #f4f6f1;
      --surface: #ffffff;
      --surface-2: #edf1eb;
      --surface-3: #e3e9e1;
      --ink: #15221c;
      --muted: #5c6b63;
      --line: #cbd4ca;
      --line-strong: #95a398;
      --brand: #176246;
      --brand-soft: #e1f0e8;
      --blue: #426c9b;
      --blue-soft: #e4edf7;
      --amber: #a96d1f;
      --amber-soft: #f6ead9;
      --violet: #746294;
      --violet-soft: #ede8f5;
      --red: #a84c3d;
      --red-soft: #f5e5e1;
      --shadow: 0 8px 24px rgba(27, 43, 35, .08);
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #101713;
        --surface: #17211b;
        --surface-2: #1e2a23;
        --surface-3: #26332b;
        --ink: #eef4ef;
        --muted: #acbbb1;
        --line: #34453a;
        --line-strong: #6e8074;
        --brand: #69b892;
        --brand-soft: #1d392c;
        --blue: #82a9d3;
        --blue-soft: #1d3044;
        --amber: #deb16c;
        --amber-soft: #3e3020;
        --violet: #b6a2d4;
        --violet-soft: #302842;
        --red: #e18b7e;
        --red-soft: #402621;
        --shadow: none;
      }
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background: var(--bg);
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
      font-size: 15px;
      line-height: 1.5;
    }
    button, a { font: inherit; }
    a { color: inherit; }
    .hero { color: #eef7f1; background: #0e2119; border-top: 6px solid #2a936a; }
    .hero-inner, main, footer { width: min(1480px, calc(100% - 40px)); margin: 0 auto; }
    .hero-inner { padding: 26px 0 30px; }
    .topline, .hero-status, .section-head, .legend, .tier-summary, .source-head {
      display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
    }
    .brand { font-weight: 500; letter-spacing: -.02em; }
    .eyebrow { color: #91b5a3; font-size: 12px; }
    h1 { margin: 18px 0 6px; max-width: 1100px; font-size: clamp(28px, 4vw, 50px); line-height: 1.15; font-weight: 500; letter-spacing: -.04em; }
    h2 { margin: 0; font-size: 22px; line-height: 1.25; font-weight: 500; letter-spacing: -.02em; }
    h3 { margin: 0; font-size: 16px; font-weight: 500; }
    p { margin: 0; }
    .hero-copy { max-width: 980px; color: #bed0c6; }
    .hero-status { justify-content: flex-start; margin-top: 18px; }
    .status { padding: 6px 10px; border: 1px solid #315a48; border-radius: 999px; color: #d8e9df; font-size: 12px; }
    .status strong { color: #79d2a6; font-weight: 500; }
    main { padding: 24px 0 50px; }
    section { margin-top: 22px; }
    .panel { min-width: 0; padding: 20px; background: var(--surface); border: 1px solid var(--line); border-radius: 16px; box-shadow: var(--shadow); }
    .section-copy { margin-top: 4px; color: var(--muted); font-size: 13px; }
    .legend { justify-content: flex-start; color: var(--muted); font-size: 12px; }
    .legend span { display: inline-flex; align-items: center; gap: 6px; }
    .swatch { width: 24px; height: 5px; border-radius: 4px; background: var(--brand); }
    .swatch.document { background: var(--blue); }
    .swatch.candidate { height: 0; border-top: 2px dashed var(--amber); background: none; }
    .total-node { display: grid; grid-template-columns: 1fr auto; gap: 10px 20px; margin: 22px auto 18px; max-width: 720px; padding: 16px 18px; color: #eff8f2; background: #174d39; border-radius: 12px; }
    .total-node span { color: #b9d7c7; font-size: 12px; }
    .total-node strong { align-self: center; grid-row: 1 / 3; grid-column: 2; font-size: 24px; font-weight: 500; }
    .fork { position: relative; height: 32px; margin: 0 22%; border-top: 1px solid var(--line-strong); }
    .fork::before, .fork::after { content: ""; position: absolute; top: 0; height: 32px; border-left: 1px solid var(--line-strong); }
    .fork::before { left: 0; } .fork::after { right: 0; }
    .parallel { display: grid; grid-template-columns: minmax(0, 1fr) 300px minmax(0, 1fr); gap: 16px; align-items: start; }
    .ledger { min-width: 0; }
    .ledger-head { min-height: 56px; }
    .source-badge, .state-badge, .tier-badge { display: inline-flex; align-items: center; width: fit-content; padding: 3px 7px; border-radius: 999px; font-size: 11px; font-weight: 500; }
    .source-badge.api, .state-badge.confirmed { color: var(--brand); background: var(--brand-soft); }
    .source-badge.pdf, .state-badge.documented { color: var(--blue); background: var(--blue-soft); }
    .source-badge.lofin, .state-badge.candidate { color: var(--amber); background: var(--amber-soft); }
    .stack { display: flex; min-height: 54px; margin: 12px 0; overflow: hidden; border-radius: 9px; background: var(--surface-2); }
    .stack-segment { position: relative; min-width: 2px; border-right: 2px solid var(--surface); }
    .stack-segment:last-child { border-right: 0; }
    .stack-segment.pdf { background: var(--blue); }
    .stack-segment.api { background: var(--brand); }
    .stack-segment.focus { background: var(--amber); }
    .money-list { display: grid; gap: 7px; }
    .money-row { display: grid; grid-template-columns: 12px minmax(0, 1fr) auto; gap: 9px; align-items: center; padding: 8px 9px; background: var(--surface-2); border-left: 3px solid transparent; }
    .money-row.focus { border-left-color: var(--amber); background: var(--amber-soft); }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--blue); }
    .api-row .dot { background: var(--brand); }
    .money-row.focus .dot { background: var(--amber); }
    .money-row small { display: block; color: var(--muted); }
    .amount { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; font-weight: 500; }
    .crosswalk { align-self: stretch; padding: 14px; background: var(--surface-2); border: 1px dashed var(--line-strong); border-radius: 12px; }
    .crosswalk h3 { text-align: center; }
    .crosswalk p { margin-top: 4px; color: var(--muted); text-align: center; font-size: 12px; }
    .cross-list { display: grid; gap: 8px; margin-top: 14px; }
    .cross-item { padding: 9px; background: var(--surface); border-radius: 8px; font-size: 12px; }
    .cross-item strong { display: block; font-weight: 500; }
    .cross-item span { color: var(--muted); }
    .cross-total { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--line); text-align: center; }
    .cross-total strong { display: block; font-size: 18px; font-weight: 500; }
    .focus-flow { display: grid; grid-template-columns: minmax(220px, .8fr) 48px minmax(260px, 1fr) 58px minmax(280px, 1.15fr); gap: 10px; align-items: center; margin-top: 20px; }
    .flow-node { min-width: 0; padding: 15px; background: var(--surface-2); border-left: 4px solid var(--blue); }
    .flow-node.focus { border-left-color: var(--amber); background: var(--amber-soft); }
    .flow-node.candidate { border: 1px dashed var(--amber); background: var(--surface); }
    .flow-node strong { display: block; margin: 5px 0 2px; font-size: 19px; font-weight: 500; }
    .flow-node span { color: var(--muted); font-size: 12px; }
    .branches { display: grid; gap: 8px; }
    .branch { padding: 11px; background: var(--surface-2); border-left: 3px solid var(--brand); }
    .branch.secondary { border-left-color: var(--violet); }
    .branch strong { display: block; font-weight: 500; }
    .arrow { color: var(--line-strong); text-align: center; font-size: 28px; }
    .candidate-arrow { color: var(--amber); font-size: 11px; text-align: center; }
    .candidate-arrow::after { content: "⇢"; display: block; font-size: 30px; line-height: 1; }
    .warning-strip { margin-top: 14px; padding: 10px 12px; color: var(--red); background: var(--red-soft); border-left: 4px solid var(--red); font-size: 13px; }
    .timeline-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-top: 18px; }
    .chart-wrap h3 { margin-bottom: 5px; }
    .chart-wrap p { color: var(--muted); font-size: 12px; }
    .timeline-chart { display: block; width: 100%; height: auto; margin-top: 9px; overflow: visible; }
    .timeline-chart .axis { stroke: var(--line-strong); stroke-width: 1; }
    .timeline-chart .grid { stroke: var(--line); stroke-width: 1; }
    .timeline-chart .label { fill: var(--muted); font-size: 11px; }
    .timeline-chart .value { fill: var(--ink); font-size: 11px; font-weight: 500; }
    .timeline-chart .strong-mark { fill: var(--brand); stroke: var(--brand); }
    .timeline-chart .broad-mark { fill: var(--blue); stroke: var(--blue); }
    .timeline-chart .verify-mark { fill: var(--red); stroke: var(--red); }
    .timeline-chart .budget-line { fill: none; stroke: var(--blue); stroke-width: 2.5; }
    .timeline-chart .spend-line { fill: none; stroke: var(--brand); stroke-width: 2.5; }
    .timeline-note { margin-top: 12px; padding: 10px 12px; color: var(--muted); background: var(--surface-2); font-size: 12px; }
    .metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 18px; }
    .metric { padding: 13px; background: var(--surface-2); }
    .metric span { display: block; color: var(--muted); font-size: 12px; }
    .metric strong { display: block; margin-top: 4px; font-size: 21px; font-weight: 500; }
    .tier-grid { display: grid; min-width: 0; gap: 12px; margin-top: 16px; }
    .tier { min-width: 0; border-top: 1px solid var(--line); padding-top: 14px; }
    details.tier > summary { cursor: pointer; list-style: none; }
    details.tier > summary::-webkit-details-marker { display: none; }
    details.tier > summary::after { content: "펼쳐 보기"; flex: 0 0 auto; color: var(--muted); font-size: 11px; }
    details.tier[open] > summary::after { content: "접기"; }
    .tier-summary { align-items: flex-start; }
    .tier-copy { max-width: 760px; color: var(--muted); font-size: 12px; }
    .tier-badge.strong { color: var(--brand); background: var(--brand-soft); }
    .tier-badge.broad { color: var(--blue); background: var(--blue-soft); }
    .tier-badge.verify { color: var(--red); background: var(--red-soft); }
    .tier-totals { text-align: right; font-variant-numeric: tabular-nums; }
    .tier-totals strong { display: block; font-weight: 500; }
    .table-wrap { width: 100%; max-width: 100%; min-width: 0; margin-top: 10px; overflow-x: auto; }
    table { width: 100%; min-width: 980px; border-collapse: collapse; font-size: 12px; }
    caption { padding: 0 0 7px; color: var(--muted); text-align: left; }
    th, td { padding: 8px 7px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: middle; }
    th { color: var(--muted); font-weight: 500; }
    td.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
    .local-name strong { display: block; font-weight: 500; }
    .local-name span { color: var(--muted); }
    .funding { min-width: 170px; }
    .funding-bar { display: flex; height: 7px; overflow: hidden; border-radius: 5px; background: var(--surface-3); }
    .funding-bar span:nth-child(1) { background: var(--blue); }
    .funding-bar span:nth-child(2) { background: var(--brand); }
    .funding-bar span:nth-child(3) { background: var(--amber); }
    .funding-bar span:nth-child(4) { background: var(--violet); }
    .funding-label { margin-top: 3px; color: var(--muted); font-size: 10px; white-space: nowrap; }
    .evidence-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 16px; }
    .source { padding: 14px; background: var(--surface-2); }
    .source h3 { margin: 7px 0 5px; }
    .source p { color: var(--muted); font-size: 12px; }
    .rules { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }
    .rule { padding: 12px; border-left: 4px solid var(--brand); background: var(--brand-soft); }
    .rule.no { border-left-color: var(--red); background: var(--red-soft); }
    .rule strong { display: block; font-weight: 500; }
    .rule span { color: var(--muted); font-size: 12px; }
    footer { padding: 0 0 30px; color: var(--muted); font-size: 12px; }
    .footer-links { display: flex; gap: 16px; flex-wrap: wrap; }
    .print-button { padding: 7px 11px; color: #eff8f2; background: transparent; border: 1px solid #567363; border-radius: 8px; cursor: pointer; }
    .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
    @media (max-width: 980px) {
      .parallel { grid-template-columns: 1fr; }
      .fork { display: none; }
      .crosswalk { order: 3; }
      .focus-flow { grid-template-columns: 1fr; }
      .arrow { transform: rotate(90deg); }
      .candidate-arrow::after { content: "⇣"; }
      .metrics, .evidence-grid, .rules, .timeline-grid { grid-template-columns: 1fr; }
      .tier-totals { text-align: left; }
    }
    @media (max-width: 560px) {
      .hero-inner, main, footer { width: min(100% - 24px, 1480px); }
      .hero-inner { padding: 20px 0 24px; }
      .panel { padding: 14px; border-radius: 12px; }
      .total-node { grid-template-columns: 1fr; }
      .total-node strong { grid-area: auto; text-align: left; }
      .money-row { grid-template-columns: 10px minmax(0, 1fr); }
      .money-row .amount { grid-column: 2; text-align: left; }
    }
    @media print {
      @page { size: A3 landscape; margin: 8mm; }
      :root { --bg: #fff; --surface: #fff; --surface-2: #f2f4ef; --surface-3: #e4e8e1; --ink: #111; --muted: #444; --line: #aaa; --shadow: none; }
      body { background: #fff; font-size: 11px; }
      .hero { color: #111; background: #fff; border-top-color: #111; }
      .hero-copy, .eyebrow { color: #333; }
      .status { color: #222; border-color: #777; }
      .status strong { color: #111; }
      .print-button, .footer-links { display: none; }
      .panel, .tier, table, tr { break-inside: avoid; }
    }
  </style>
</head>
<body>
  <header class="hero">
    <div class="hero-inner">
      <div class="topline">
        <div><span class="brand">Koreabudget100</span> <span class="eyebrow">· 단일 세부사업 예산체계도</span></div>
        <button class="print-button" id="print-button" type="button">현재 체계도 인쇄</button>
      </div>
      <h1 id="title"></h1>
      <p class="hero-copy">중앙의 확정액, 부처 설명자료의 목적별 배분, 지방재정365의 지역 예산 관측을 한 장에서 읽되 서로 다른 장부를 합치지 않습니다.</p>
      <div class="hero-status" id="hero-status"></div>
    </div>
  </header>

  <main>
    <section class="panel" aria-labelledby="central-heading">
      <div class="section-head">
        <div><h2 id="central-heading">같은 237.53억원을 두 장부로 분해</h2><p class="section-copy">PDF 내역사업과 Add2 목·세목은 상하 단계가 아니라 같은 총액을 다르게 분류한 평행 장부입니다.</p></div>
        <div class="legend"><span><i class="swatch document"></i>PDF 문서</span><span><i class="swatch"></i>Add2 확정</span><span><i class="swatch candidate"></i>LOFIN 후보</span></div>
      </div>
      <div class="total-node"><div><span>Open Fiscal · 국회확정액</span><div id="total-path"></div></div><strong id="total-amount"></strong></div>
      <div class="fork" aria-hidden="true"></div>
      <div class="parallel">
        <article class="ledger"><div class="ledger-head"><span class="source-badge pdf">PDF · 목적별 배분</span><h3>내역사업 5개</h3></div><div class="stack" id="subproject-stack" aria-label="PDF 내역사업 금액 비중"></div><div class="money-list" id="subproject-list"></div></article>
        <aside class="crosswalk"><h3>내용·금액 교차대사</h3><p>실제 거래 흐름이 아니라 PDF 산출내용을 Add2 회계버킷에 맞춘 대사</p><div class="cross-list" id="cross-list"></div><div class="cross-total"><span>대사 범위</span><strong id="cross-total"></strong><span id="cross-share"></span></div></aside>
        <article class="ledger"><div class="ledger-head"><span class="source-badge api">Add2 · 회계별 배분</span><h3>회계버킷 5개 · 세목 8개</h3></div><div class="stack" id="channel-stack" aria-label="Add2 회계버킷 금액 비중"></div><div class="money-list" id="channel-list"></div></article>
      </div>
    </section>

    <section class="panel" aria-labelledby="focus-heading">
      <div class="section-head"><div><h2 id="focus-heading">⑤ 사회연대경제 활성화 집중 경로</h2><p class="section-copy">지방재정 API가 실제로 보강하는 구간만 확대합니다.</p></div><span class="state-badge documented">PDF↔Add2 금액 확인</span></div>
      <div class="focus-flow">
        <div class="flow-node focus"><span>PDF 내역사업</span><strong>118.39억원</strong><p>사회연대경제 활성화</p></div>
        <div class="arrow" aria-hidden="true">→</div>
        <div class="branches"><div class="branch"><span>지자체경상보조 · 보조율 50%</span><strong>103.50억원</strong></div><div class="branch secondary"><span>일반용역</span><strong>11.00억원</strong></div><div class="branch secondary"><span>운영·사업관리</span><strong>3.89억원</strong></div></div>
        <div class="candidate-arrow"><span>명칭 검색<br />교부 근거 아님</span></div>
        <div class="flow-node candidate"><span id="latest-date">LOFIN QWGJK</span><strong id="latest-count"></strong><p id="latest-tiers"></p></div>
      </div>
      <div class="warning-strip" id="comparison-warning"></div>
    </section>

    <section class="panel" aria-labelledby="timeline-heading">
      <div class="section-head"><div><h2 id="timeline-heading">지방재정 API는 한 시점보다 시간축에서 더 유용</h2><p class="section-copy">월말 스냅샷을 이어 지역사업의 관측 범위와 지출 상태가 언제 바뀌었는지 봅니다.</p></div><span class="state-badge candidate">거래 흐름 아님</span></div>
      <div class="timeline-grid">
        <article class="chart-wrap"><h3>검색 결과 구성 변화</h3><p>A·B·C 후보 행이 조회일마다 몇 건 포착됐는지 표시합니다.</p><svg class="timeline-chart" id="count-chart" viewBox="0 0 680 270" role="img" aria-label="2026년 1월부터 7월까지 LOFIN 후보 행 수 변화"></svg></article>
        <article class="chart-wrap"><h3>A 강한 후보의 예산현액·지출 관측</h3><p>PDF 문구 근접 행만 남겨 같은 척도로 비교합니다.</p><svg class="timeline-chart" id="money-chart" viewBox="0 0 680 270" role="img" aria-label="2026년 1월부터 7월까지 강한 후보 예산현액과 지출액 변화"></svg></article>
      </div>
      <p class="timeline-note">행 수나 금액이 늘었다고 중앙정부가 그날 교부했다는 뜻은 아닙니다. QWGJK는 각 조회기준일의 지방 세부사업별 예산현액·재원·지출 상태를 다시 관측한 스냅샷입니다.</p>
    </section>

    <section class="panel" aria-labelledby="local-heading">
      <div class="section-head"><div><h2 id="local-heading">최신 지방 편성·지출 후보를 세 단계로 판독</h2><p class="section-copy"><span id="latest-date-copy"></span> 결과를 하나의 수령처 목록으로 취급하지 않고, PDF 문구와의 근접도에 따라 분리합니다.</p></div><span class="state-badge candidate">전 행 비가산</span></div>
      <div class="metrics" id="metrics"></div>
      <div class="tier-grid" id="tier-grid"></div>
    </section>

    <section class="panel" aria-labelledby="evidence-heading">
      <div class="section-head"><div><h2 id="evidence-heading">근거와 해석 경계</h2><p class="section-copy">선의 모양보다 출처와 주장 수준을 먼저 읽습니다.</p></div></div>
      <div class="evidence-grid">
        <article class="source"><span class="source-badge api">확정</span><h3>Open Fiscal Add2</h3><p>국회확정액과 8개 목·세목. 금액 필드 Y_YY_DFN_KCUR_AMT. 세목 합계는 237.53억원과 차이 0원.</p></article>
        <article class="source"><span class="source-badge pdf">문서 대사</span><h3>행정안전부 설명자료</h3><p>p.2089–2093. 내역사업 5개, 시행방법·주체·수혜자, 사회연대경제 보조 103.50억원과 용역·관리 14.89억원.</p></article>
        <article class="source"><span class="source-badge lofin">명칭 후보</span><h3>LOFIN QWGJK</h3><p><span id="source-latest-date"></span> 스냅샷. 지방사업명·지자체·예산현액·재원구성·지출액. 중앙 교부처를 확정하는 데이터는 아님.</p></article>
      </div>
      <div class="rules"><div class="rule"><strong>확인 가능한 것</strong><span>중앙 총액, 두 장부의 각 합계, PDF 내용·금액과 Add2 회계버킷의 237.53억원 전액 대사, 지방 행 내부의 예산현액·재원구성·지출률.</span></div><div class="rule no"><strong>하면 안 되는 것</strong><span>교차대사를 실제 거래 경로로 읽거나, LOFIN 최신 검색 결과를 중앙 보조금 수령처로 확정하거나, 국비 관측합을 103.50억원과 대사·합산하는 것.</span></div><div class="rule no"><strong>PDF 원문 산식 점검</strong><span>‘2,100백만원 = 7개 지역 × 3,000백만원’은 산식이 맞지 않고, ‘1,189백만원 = 54백만원 × 22개소’도 계산값 1,188백만원과 1백만원 차이가 납니다.</span></div><div class="rule"><strong>보조율 해석</strong><span>103.50억원 항목의 보조율 50%는 문서 사실이지만, LOFIN 후보의 지방비 총액을 단순 역산하거나 119.50억원을 두 배로 늘리는 근거는 아닙니다.</span></div></div>
    </section>
  </main>

  <footer><div class="footer-links"><a href="budget_flow_map.html?business=kb-ace0474d507615f7">전체 사업 탐색기</a><a href="https://github.com/hosungseo/Koreabudget100/blob/main/docs/budget_flow_methodology.md">방법론</a><a href="https://github.com/hosungseo/Koreabudget100">GitHub</a></div></footer>

  <script id="reference-data" type="application/json">__PAYLOAD__</script>
  <script>
    const DATA = JSON.parse(document.getElementById('reference-data').textContent);
    const MAP = DATA.map;
    const TIMELINE = DATA.timeline;
    const TIER = {
      strong: { title: 'A · PDF 문구 근접 후보', badge: '강한 후보', copy: 'PDF의 특징적인 산출 문구 ‘혁신모델 발굴·사업지원’이 지방사업명에 나타납니다. 포착된 행들은 국비 100%로 보여 PDF 보조율 50%와 불일치하므로 확정 교부처는 아닙니다.' },
      broad: { title: 'B · 포괄 유사 후보', badge: '검토 후보', copy: '‘생태계 활성화’·‘활력제고’·‘활성화(보조)’처럼 같은 정책 영역이지만 PDF의 특징적 산출 문구와 직접 일치하지 않습니다.' },
      verify: { title: 'C · 별도 확인 필요', badge: '다른 사업 가능', copy: '‘청년 일경험’은 PDF 내역사업 산출 문구에 없습니다. 같은 검색어를 공유한 별도 국고사업일 가능성이 있어 수령처 해석에서 제외합니다.' },
    };
    const byId = id => document.getElementById(id);
    const array = value => Array.isArray(value) ? value : [];
    const LATEST = array(TIMELINE.snapshots).at(-1);
    const number = value => Number(value) || 0;
    const el = (tag, className, value) => { const node = document.createElement(tag); if (className) node.className = className; if (value != null) node.textContent = String(value); return node; };
    const won = (value, exact=false) => { const n=number(value); if (exact) return `${n.toLocaleString('ko-KR')}원`; const eok=n/100000000; return `${eok.toLocaleString('ko-KR',{minimumFractionDigits:eok<100?2:1,maximumFractionDigits:2})}억원`; };
    const pct = (part,total) => total ? `${(number(part)*100/number(total)).toLocaleString('ko-KR',{maximumFractionDigits:1})}%` : '0%';
    const dateLabel = value => { const raw=String(value || '').replace(/\D/g,''); return raw.length===8?`${raw.slice(0,4)}-${raw.slice(4,6)}-${raw.slice(6,8)}`:String(value || ''); };
    const total = number(MAP.core.congress_amt);

    byId('title').textContent = `${MAP.title} — ${won(total)}의 예산체계도`;
    byId('total-path').textContent = `${MAP.core.office_name} · ${MAP.core.account_name} · ${MAP.core.program_name} · ${MAP.core.unit_business_name}`;
    byId('total-amount').textContent = won(total);
    const hero = byId('hero-status');
    [
      ['Add2', '목·세목 차이 0원'],
      ['PDF', '내역사업 차이 0원'],
      ['LOFIN', `${LATEST.row_count}건 · ${dateLabel(LATEST.exe_ymd)} · 시간축 확보`],
    ].forEach(([label,value]) => { const node=el('span','status'); const strong=el('strong','',label); node.append(strong,document.createTextNode(` · ${value}`)); hero.append(node); });

    function renderStack(targetId, rows, kind, focusId) {
      const target=byId(targetId); target.replaceChildren();
      rows.forEach(row => { const segment=el('span',`stack-segment ${kind}${row.id===focusId?' focus':''}`); segment.style.width=`${number(row.amount_won)*100/total}%`; segment.setAttribute('aria-label',`${row.label || row.semok_name} ${won(row.amount_won)}`); target.append(segment); });
    }
    function renderMoneyList(targetId, rows, kind, focusId) {
      const target=byId(targetId); target.replaceChildren();
      rows.forEach((row,index) => { const item=el('div',`money-row ${kind==='api'?'api-row':''}${row.id===focusId?' focus':''}`); const dot=el('i','dot'); const label=el('div'); label.append(el('span','',`${row.marker || String(index+1).padStart(2,'0')} ${row.label || row.semok_name}`),el('small','',row.summary || row.description || row.mok_name || '')); item.append(dot,label,el('div','amount',won(row.amount_won))); target.append(item); });
    }
    renderStack('subproject-stack',array(MAP.subprojects),'pdf','sub-05');
    renderMoneyList('subproject-list',array(MAP.subprojects),'pdf','sub-05');
    renderStack('channel-stack',array(MAP.accounting_buckets),'api','local_subsidy');
    renderMoneyList('channel-list',array(MAP.accounting_buckets),'api','local_subsidy');

    const crossList=byId('cross-list');
    array(MAP.detailed_crosswalk).forEach(row => { const item=el('div','cross-item'); const allocationText=array(row.allocations).map(value=>`${value.bucket_label} ${won(value.amount_won)}`).join(' + '); item.append(el('strong','',`${row.subproject_marker || ''} ${row.subproject_label}`),el('span','',`${allocationText} · 내용·금액 대사`)); crossList.append(item); });
    byId('cross-total').textContent=won(MAP.detailed_reconciliation.amount_won);
    byId('cross-share').textContent='총액의 100% · 차이 0원';

    const summary=MAP.local_summary;
    const comparison=MAP.comparison_warning;
    byId('comparison-warning').textContent=`대사 금지: 최신 ${summary.candidate_count}건의 국비 관측합 ${won(comparison.observed_national_won)}은 중앙 보조 ${won(comparison.central_subsidy_won)}보다 ${won(comparison.difference_won)}(${pct(comparison.difference_won,comparison.central_subsidy_won)}) 큽니다. 같은 검색어의 다른 국고사업과 광역·기초 중복이 섞였다는 신호입니다.`;
    byId('latest-date').textContent=`LOFIN QWGJK · ${dateLabel(summary.snapshot_date)}`;
    byId('source-latest-date').textContent=dateLabel(summary.snapshot_date);
    byId('latest-count').textContent=`검색 결과 ${summary.candidate_count}건`;
    byId('latest-tiers').textContent=`강한 후보 ${MAP.candidate_tier_summary.strong.row_count} · 포괄 유사 ${MAP.candidate_tier_summary.broad.row_count} · 별도 사업 가능 ${MAP.candidate_tier_summary.verify.row_count}`;
    byId('latest-date-copy').textContent=`${dateLabel(summary.snapshot_date)} 기준 ${summary.candidate_count}건`;
    const metrics=byId('metrics');
    [
      ['검색 결과',`${summary.candidate_count}건 · ${summary.local_gov_count}개 지자체`,`광역 ${summary.wide_area_row_count}건 · 기초 ${summary.basic_row_count}건`],
      ['A · 강한 후보',`${MAP.candidate_tier_summary.strong.row_count}건 · 예산현액 ${won(MAP.candidate_tier_summary.strong.budget_cash_amt)}`,`지출 ${won(MAP.candidate_tier_summary.strong.spend_amt)} · 국비 100% 불일치`],
      ['B/C · 검토·격리',`B ${MAP.candidate_tier_summary.broad.row_count}건 · C ${MAP.candidate_tier_summary.verify.row_count}건`,'C ‘청년 일경험’은 본 흐름에서 제외'],
    ].forEach(([label,value,note]) => { const node=el('div','metric'); node.append(el('span','',label),el('strong','',value),el('span','',note)); metrics.append(node); });

    function fundingCell(row) {
      const td=el('td','funding'); const values=[number(row.national_amt),number(row.sido_amt),number(row.sigungu_amt),number(row.other_amt)]; const sum=values.reduce((a,b)=>a+b,0); const bar=el('div','funding-bar'); values.forEach(value=>{const segment=el('span');segment.style.width=`${sum?value*100/sum:0}%`;bar.append(segment);}); td.append(bar,el('div','funding-label',`국 ${won(values[0])} · 시도 ${won(values[1])} · 시군구 ${won(values[2])}`)); return td;
    }
    function renderTier(tier) {
      const rows=array(MAP.local_candidates).filter(row=>row.candidate_tier===tier); const info=TIER[tier]; const sum=MAP.candidate_tier_summary[tier];
      const section=document.createElement('details'); section.className='tier'; section.open=tier==='strong'; const head=el('summary','tier-summary'); const left=el('div'); left.append(el('span',`tier-badge ${tier}`,info.badge),el('h3','',info.title),el('p','tier-copy',info.copy)); const totals=el('div','tier-totals'); totals.append(el('strong','',`${sum.row_count}건 · 국비 관측합 ${won(sum.national_amt)}`),el('span','tier-copy',`예산현액 ${won(sum.budget_cash_amt)} · 지출 ${won(sum.spend_amt)} · 관측 ${pct(sum.spend_amt,sum.budget_cash_amt)}`)); head.append(left,totals);
      const wrap=el('div','table-wrap'); const table=document.createElement('table'); const caption=el('caption','',`${info.title} — 개별 행은 서로 더하지 않음`); const thead=document.createElement('thead'); const hr=document.createElement('tr'); ['지자체','지방 세부사업','재원 구성','예산현액','지출액','관측 집행률'].forEach(value=>hr.append(el('th','',value))); thead.append(hr); const tbody=document.createElement('tbody');
      rows.forEach(row=>{const tr=document.createElement('tr'); const gov=el('td','local-name'); gov.append(el('strong','',`${row.local_gov_name} · ${row.local_level}`),el('span','',row.region_name)); const name=el('td','local-name'); name.append(el('strong','',row.detail_business_name),el('span','',`${row.account_name} · ${row.detail_business_code}`)); tr.append(gov,name,fundingCell(row),el('td','num',won(row.budget_cash_amt)),el('td','num',won(row.spend_amt)),el('td','num',pct(row.spend_amt,row.budget_cash_amt))); tbody.append(tr);});
      table.append(caption,thead,tbody); wrap.append(table); section.append(head,wrap); return section;
    }
    const tierGrid=byId('tier-grid'); ['strong','broad','verify'].forEach(tier=>tierGrid.append(renderTier(tier)));

    const SVG_NS='http://www.w3.org/2000/svg';
    function svgEl(tag,attrs={},value='') { const node=document.createElementNS(SVG_NS,tag); Object.entries(attrs).forEach(([key,val])=>node.setAttribute(key,String(val))); if(value) node.textContent=value; return node; }
    function addTitle(node,value) { node.append(svgEl('title',{},value)); return node; }
    function timelineX(index,count,left,width) { return count<=1?left+width/2:left+index*width/(count-1); }
    function renderCountChart() {
      const svg=byId('count-chart'); const rows=array(TIMELINE.snapshots); const W=680,H=270,L=44,R=28,T=18,B=42,PW=W-L-R,PH=H-T-B; const max=Math.max(10,Math.ceil(Math.max(...rows.map(row=>number(row.row_count)))/10)*10); svg.replaceChildren();
      [0,max/3,max*2/3,max].forEach(value=>{const y=T+PH-value/max*PH;svg.append(svgEl('line',{x1:L,y1:y,x2:W-R,y2:y,class:'grid'}),svgEl('text',{x:L-8,y:y+4,'text-anchor':'end',class:'label'},String(Math.round(value))));});
      svg.append(svgEl('line',{x1:L,y1:T+PH,x2:W-R,y2:T+PH,class:'axis'}));
      const barWidth=Math.min(44,PW/(rows.length*1.7));
      rows.forEach((row,index)=>{const x=timelineX(index,rows.length,L+barWidth/2,PW-barWidth);let used=0;['strong','broad','verify'].forEach(tier=>{const count=number(row.tiers?.[tier]?.row_count);if(!count)return;const height=count/max*PH;const rect=svgEl('rect',{x:x-barWidth/2,y:T+PH-used-height,width:barWidth,height,class:`${tier}-mark`});addTitle(rect,`${dateLabel(row.exe_ymd)} · ${TIER[tier].badge} ${count}건`);svg.append(rect);used+=height;});svg.append(svgEl('text',{x,y:T+PH-used-6,'text-anchor':'middle',class:'value'},String(row.row_count)),svgEl('text',{x,y:H-14,'text-anchor':'middle',class:'label'},`${String(row.exe_ymd).slice(4,6)}/${String(row.exe_ymd).slice(6,8)}`));});
      const labels=[['A',W-155,'strong-mark'],['B',W-105,'broad-mark'],['C',W-55,'verify-mark']]; labels.forEach(([label,x,cls])=>{svg.append(svgEl('circle',{cx:x-15,cy:12,r:4,class:cls}),svgEl('text',{x,y:16,class:'label'},label));});
    }
    function renderMoneyChart() {
      const svg=byId('money-chart'); const rows=array(TIMELINE.snapshots); const W=680,H=270,L=52,R=95,T=18,B=42,PW=W-L-R,PH=H-T-B; const values=rows.flatMap(row=>[number(row.tiers?.strong?.budget_cash_amt),number(row.tiers?.strong?.spend_amt)]); const maxWon=Math.max(1,...values); const maxEok=Math.max(10,Math.ceil(maxWon/100000000/10)*10); svg.replaceChildren();
      [0,maxEok/2,maxEok].forEach(value=>{const y=T+PH-value/maxEok*PH;svg.append(svgEl('line',{x1:L,y1:y,x2:W-R,y2:y,class:'grid'}),svgEl('text',{x:L-8,y:y+4,'text-anchor':'end',class:'label'},`${Math.round(value)}억`));});
      svg.append(svgEl('line',{x1:L,y1:T+PH,x2:W-R,y2:T+PH,class:'axis'}));
      const points=kind=>rows.map((row,index)=>{const x=timelineX(index,rows.length,L,PW);const value=number(row.tiers?.strong?.[kind]);const y=T+PH-(value/100000000)/maxEok*PH;return{x,y,value,date:row.exe_ymd};});
      [['budget_cash_amt','budget-line','예산현액'],['spend_amt','spend-line','지출']].forEach(([kind,cls,label])=>{const series=points(kind);svg.append(svgEl('path',{d:series.map((point,index)=>`${index?'L':'M'} ${point.x} ${point.y}`).join(' '),class:cls}));series.forEach(point=>{const circle=svgEl('circle',{cx:point.x,cy:point.y,r:4,class:kind==='budget_cash_amt'?'broad-mark':'strong-mark'});addTitle(circle,`${dateLabel(point.date)} · ${label} ${won(point.value)}`);svg.append(circle);});const last=series.at(-1);svg.append(svgEl('text',{x:last.x+9,y:last.y+(kind==='budget_cash_amt'?-7:15),class:'value'},`${label} ${won(last.value)}`));});
      rows.forEach((row,index)=>{const x=timelineX(index,rows.length,L,PW);svg.append(svgEl('text',{x,y:H-14,'text-anchor':'middle',class:'label'},`${String(row.exe_ymd).slice(4,6)}/${String(row.exe_ymd).slice(6,8)}`));});
    }
    renderCountChart(); renderMoneyChart();
    byId('print-button').addEventListener('click',()=>window.print());
  </script>
</body>
</html>
'''


def main() -> int:
    payload = prepare_payload(load_json(SOURCE), load_json(TIMELINE))
    rendered = HTML.replace("__PAYLOAD__", safe_json(payload))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(rendered)
    print(
        json.dumps(
            {
                "output": str(OUT),
                "bytes": OUT.stat().st_size,
                "business_id": REFERENCE_ID,
                "local_candidate_rows": len(payload["map"]["local_candidates"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
