#!/usr/bin/env python3
"""Build a money-first budget-flow model for every canonical detail business.

The Open Fiscal Add2 total and budget-item rows are the accounting source of
truth.  Ministry PDF sections add project allocations, implementers, subsidy
rates and beneficiaries only where the source says so.  LOFIN rows remain
non-additive keyword candidates and never alter a central-government total.
"""

from __future__ import annotations

import collections
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "normalized" / "business_workflows_2026_pilots.json"
OUT = ROOT / "data" / "normalized" / "budget_flow_maps_2026_pilots.json"
SUMMARY = ROOT / "artifacts" / "budget_flow_maps_2026_pilots_summary.json"

REFERENCE_TITLE = "지역사회 자생적 창조역량 강화"
REFERENCE_ID = "kb-ace0474d507615f7"

CHANNELS = {
    "local_subsidy": {
        "label": "지방자치단체 보조",
        "destination": "지방자치단체",
        "description": "자치단체 이전 세목에 따른 보조 교부",
        "order": 10,
    },
    "private_delegation": {
        "label": "민간위탁",
        "destination": "민간 위탁기관",
        "description": "민간위탁 세목에 따른 위탁 집행",
        "order": 20,
    },
    "private_subsidy": {
        "label": "민간보조",
        "destination": "민간 보조사업자",
        "description": "민간보조 세목에 따른 보조 집행",
        "order": 30,
    },
    "contribution": {
        "label": "출연",
        "destination": "출연기관",
        "description": "출연금 세목에 따른 기관 출연",
        "order": 40,
    },
    "procurement": {
        "label": "용역·연구계약",
        "destination": "용역·연구 수행기관",
        "description": "용역·연구비 세목에 따른 계약 집행",
        "order": 50,
    },
    "loan": {
        "label": "융자",
        "destination": "융자 수행기관·대상",
        "description": "융자 세목에 따른 자금 공급",
        "order": 60,
    },
    "equity": {
        "label": "출자",
        "destination": "출자기관·사업",
        "description": "출자 세목에 따른 자금 투입",
        "order": 70,
    },
    "personnel": {
        "label": "인건비",
        "destination": "소관기관·사업인력",
        "description": "인건비 세목에 따른 내부 집행",
        "order": 80,
    },
    "construction": {
        "label": "시설·자산",
        "destination": "공사·자산 취득 대상",
        "description": "시설비·자산취득비 세목에 따른 집행",
        "order": 90,
    },
    "internal": {
        "label": "운영·사업관리",
        "destination": "소관부처·직접집행",
        "description": "수용비·여비·임차료 등 사업 운영비",
        "order": 100,
    },
    "other": {
        "label": "기타 집행",
        "destination": "세목별 집행대상 미분류",
        "description": "세목 명칭만으로 수급 주체를 확정할 수 없음",
        "order": 110,
    },
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"missing source: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"expected object: {path}")
    return value


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                value,
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def number(value: Any) -> int:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(result):
        return 0
    return int(round(result))


def compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def evidence_map(workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in workflow.get("evidence_sections") or []:
        if isinstance(row, dict) and row.get("id"):
            result[str(row["section"])] = row
    return result


def evidence_ref(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": str(row.get("id") or ""),
        "label": str(row.get("label") or row.get("section") or "문서 근거"),
        "source_type": str(row.get("source_type") or "ministry_pdf"),
        "source_pdf": str(row.get("source_pdf") or ""),
        "page_start": number(row.get("page_start")),
        "page_end": number(row.get("page_end")),
        "chunk_start": str(row.get("chunk_start") or ""),
        "chunk_end": str(row.get("chunk_end") or ""),
    }


def budget_basis_summary(section: dict[str, Any] | None) -> dict[str, Any] | None:
    if not section:
        return None
    raw = str(section.get("text") or "")
    if not raw.strip():
        return None
    # Some source sections carry the following performance/feasibility page in
    # the same extracted span.  Keep only the allocation-facing prefix.
    cut_points = [
        position
        for token in ("사업영향,", "4) 사업효과", "5) 타당성조사", "6) 총사업비")
        if (position := raw.find(token)) > 0
    ]
    if cut_points:
        raw = raw[: min(cut_points)]
    raw = re.sub(r"^\s*3\)\s*2026년도\s*예산\s*산출\s*근거\s*", "", raw)
    return {
        "label": "PDF 예산 산출근거",
        "text": compact(raw)[:720],
        "source_ref": str(section.get("id") or ""),
    }


def extract_line(text: str, labels: list[str]) -> str:
    for label in labels:
        match = re.search(
            rf"{re.escape(label)}\s*[:：]\s*([^\n]+)", text, flags=re.IGNORECASE
        )
        if match:
            return compact(match.group(1))
    return ""


SUBPROJECT_RE = re.compile(
    r"(?:^|\n)\s*([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]|\d+[.)])\s*"
    r"([^:\n]{2,100}?)\s*:\s*\(?(?:2026\s*)?예산\)?\s*([0-9,]+)\s*백만원",
    flags=re.MULTILINE,
)


def parse_subprojects(section: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not section:
        return []
    text = str(section.get("text") or "")
    matches = list(SUBPROJECT_RE.finditer(text))
    rows: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        detail = compact(text[start:end])
        amount_won = number(match.group(3).replace(",", "")) * 1_000_000
        if amount_won <= 0:
            continue
        rows.append(
            {
                "id": f"sub-{index + 1:02d}",
                "marker": compact(match.group(1)),
                "label": compact(match.group(2)),
                "amount_won": amount_won,
                "detail": detail[:640],
                "source_refs": [str(section.get("id") or "")],
                "crosswalks": [],
            }
        )
    return rows


def classify_item(mok: str, semok: str) -> str:
    text = f"{mok} {semok}".replace(" ", "")
    if "자치단체" in text and ("보조" in text or "이전" in text):
        return "local_subsidy"
    if "민간위탁" in text:
        return "private_delegation"
    if "민간" in text and "보조" in text:
        return "private_subsidy"
    if "출연" in text:
        return "contribution"
    if "융자" in text or "대여" in text:
        return "loan"
    if "출자" in text:
        return "equity"
    if "용역" in text or "연구비" in text or "연구개발" in text:
        return "procurement"
    if "인건비" in text or "보수" in text or "직급보조" in text:
        return "personnel"
    if any(token in text for token in ("시설비", "건설", "자산취득", "토지매입")):
        return "construction"
    if any(
        token in text
        for token in (
            "운영비",
            "수용비",
            "여비",
            "임차료",
            "업무추진비",
            "사업추진비",
            "공공요금",
            "포상금",
        )
    ):
        return "internal"
    return "other"


def build_budget_items(workflow: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    groups: dict[str, dict[str, Any]] = {}
    breakdown = workflow.get("budget_breakdown") or []
    for index, raw in enumerate(breakdown):
        if not isinstance(raw, dict):
            continue
        amount_won = number(raw.get("amount_won"))
        if amount_won <= 0:
            continue
        mok = compact(raw.get("mok_name")) or "목 미상"
        semok = compact(raw.get("semok_name")) or "세목 미상"
        channel = classify_item(mok, semok)
        item_id = f"item-{index + 1:02d}"
        items.append(
            {
                "id": item_id,
                "mok_name": mok,
                "semok_name": semok,
                "amount_won": amount_won,
                "line_count": number(raw.get("line_count")),
                "channel_code": channel,
                "source": "openfiscal_ExpenditureBudgetAdd2",
                "amount_field": "Y_YY_DFN_KCUR_AMT",
                "assertion": "confirmed",
            }
        )
        group = groups.setdefault(
            channel,
            {
                "id": f"channel-{channel}",
                "code": channel,
                "label": CHANNELS[channel]["label"],
                "description": CHANNELS[channel]["description"],
                "destination": CHANNELS[channel]["destination"],
                "amount_won": 0,
                "item_ids": [],
                "assertion": "classified",
            },
        )
        group["amount_won"] += amount_won
        group["item_ids"].append(item_id)
    channels = sorted(
        groups.values(), key=lambda row: (CHANNELS[row["code"]]["order"], row["label"])
    )
    return items, channels


def reference_crosswalks(
    subprojects: list[dict[str, Any]], channels: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Attach only PDF-explicit crosswalks for the reference business.

    The source explicitly identifies the 982 million private commission, the
    two 50% local subsidies and the 1,489 million service block.  It does not
    provide a complete line-by-line mapping from every allocation formula to
    every Add2 item, so the remainder stays unresolved instead of being guessed.
    """

    by_label = {compact(row.get("label")): row for row in subprojects}
    by_code = {str(row.get("code")): row for row in channels}
    definitions = [
        ("데이터 기반 지역문제해결 사업", "private_delegation", 982_000_000, "PDF 과제공모액과 API 민간위탁사업비가 일치"),
        ("다부처 협업 지역역량성장거점 활성화", "local_subsidy", 1_600_000_000, "PDF 지자체보조·보조율 50% 명시"),
        ("사회연대경제 활성화", "local_subsidy", 10_350_000_000, "PDF 자치단체경상보조·보조율 50% 명시"),
        ("사회연대경제 활성화", "procurement", 1_489_000_000, "PDF 용역사업 1,489백만원 명시"),
    ]
    rows: list[dict[str, Any]] = []
    for label, channel_code, amount_won, note in definitions:
        subproject = by_label.get(label)
        channel = by_code.get(channel_code)
        if not subproject or not channel:
            continue
        crosswalk = {
            "id": f"cross-{len(rows) + 1:02d}",
            "subproject_id": subproject["id"],
            "channel_id": channel["id"],
            "amount_won": amount_won,
            "assertion": "documented_reconciled",
            "note": note,
        }
        rows.append(crosswalk)
        subproject["crosswalks"].append(crosswalk["id"])
    return rows


def build_local_candidates(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    candidates = [row for row in workflow.get("local_reflections") or [] if isinstance(row, dict)]
    candidates.sort(
        key=lambda row: (
            -number(row.get("national_amt")),
            compact(row.get("local_gov_name")),
            compact(row.get("detail_business_name")),
            compact(row.get("detail_business_code")),
        )
    )
    for index, raw in enumerate(candidates[:12]):
        rows.append(
            {
                "id": f"local-{index + 1:02d}",
                "local_gov_name": compact(raw.get("local_gov_name")) or "지역명 미상",
                "local_level": compact(raw.get("local_level")),
                "detail_business_name": compact(raw.get("detail_business_name")),
                "national_amt": number(raw.get("national_amt")),
                "sido_amt": number(raw.get("sido_amt")),
                "sigungu_amt": number(raw.get("sigungu_amt")),
                "budget_cash_amt": number(raw.get("budget_cash_amt")),
                "match_status": "keyword_candidate",
                "additive": False,
                "source": "lofin_QWGJK",
            }
        )
    return rows


def reference_subproject_details(subprojects: list[dict[str, Any]]) -> None:
    details = {
        "청년 유입 및 체류 지원": {
            "summary": "청년마을 22개소 조성·활성화와 사업관리",
            "components": [
                {"label": "청년마을 조성", "amount_won": 5_500_000_000},
                {"label": "활성화 지원", "amount_won": 1_189_000_000},
                {"label": "사업관리", "amount_won": 75_000_000},
            ],
        },
        "데이터 기반 지역문제해결 사업": {
            "summary": "5개 과제 공모와 심사·컨설팅 관리",
            "components": [
                {"label": "과제공모", "amount_won": 982_000_000},
                {"label": "사업관리", "amount_won": 18_000_000},
            ],
        },
        "지역주도 민관협력체계 구축 및 확산": {
            "summary": "17개 광역 전수조사, 7개 지역 실증, 성과분석",
            "components": [
                {"label": "17개 광역 전수조사", "amount_won": 300_000_000},
                {"label": "7개 지역 실증", "amount_won": 2_100_000_000},
                {"label": "성과분석", "amount_won": 50_000_000},
                {"label": "사업관리", "amount_won": 50_000_000},
            ],
        },
        "다부처 협업 지역역량성장거점 활성화": {
            "summary": "기초지자체 2개소 보조와 공모·점검 관리",
            "components": [
                {"label": "2개소 지자체보조", "amount_won": 1_600_000_000},
                {"label": "사업관리", "amount_won": 50_000_000},
            ],
        },
        "사회연대경제 활성화": {
            "summary": "지자체보조, 통계·아카이브·홍보 용역과 사업관리",
            "components": [
                {"label": "지자체경상보조", "amount_won": 10_350_000_000},
                {"label": "용역·사업관리", "amount_won": 1_489_000_000},
            ],
        },
    }
    for row in subprojects:
        extra = details.get(str(row.get("label")))
        if extra:
            row.update(extra)


def reference_channel_details(channels: list[dict[str, Any]]) -> None:
    details = {
        "local_subsidy": {
            "destination": "지방자치단체",
            "destination_note": "성장거점 2개소 16억원은 기초지자체, 사회연대경제 103.5억원은 광역·기초 층위 미배분",
            "support_rate": "50%",
        },
        "private_delegation": {
            "destination": "민간 위탁기관",
            "destination_note": "사업설명자료 시행주체 목록에 한국지역정보개발원 명시",
        },
        "procurement": {
            "destination": "용역·연구 수행기관",
            "destination_note": "17개 광역시도는 3억원 전수조사의 대상이며 수급기관은 자료에서 특정되지 않음",
        },
        "internal": {
            "destination": "행정안전부",
            "destination_note": "일반수용비·임차료·국내여비·사업추진비의 합계",
        },
    }
    for row in channels:
        extra = details.get(str(row.get("code")))
        if extra:
            row.update(extra)


def build_map(workflow: dict[str, Any]) -> dict[str, Any]:
    core = workflow.get("core") if isinstance(workflow.get("core"), dict) else {}
    total_won = number(core.get("congress_amt"))
    evidence = evidence_map(workflow)
    budget_basis = evidence.get("budget_basis")
    implementation = evidence.get("implementation")
    implementation_text = str((implementation or {}).get("text") or "")
    items, channels = build_budget_items(workflow)
    subprojects = parse_subprojects(budget_basis)
    is_reference = str(workflow.get("id")) == REFERENCE_ID or str(workflow.get("title")) == REFERENCE_TITLE
    if is_reference:
        reference_subproject_details(subprojects)
        reference_channel_details(channels)
    crosswalks = reference_crosswalks(subprojects, channels) if is_reference else []
    local_candidates = build_local_candidates(workflow)

    item_total = sum(number(row.get("amount_won")) for row in items)
    subproject_total = sum(number(row.get("amount_won")) for row in subprojects)
    crosswalk_total = sum(number(row.get("amount_won")) for row in crosswalks)
    method = extract_line(implementation_text, ["사업시행방법", "사업 시행방법"])
    implementer = extract_line(implementation_text, ["사업시행주체", "사업 시행주체"])
    beneficiary = extract_line(implementation_text, ["사업 수혜자", "사업수혜자"])

    warnings: list[str] = []
    if total_won == 0:
        warnings.append("국회확정액이 0원이라 목·세목과 집행채널이 생성되지 않음")
    if item_total != total_won:
        warnings.append(f"API 세목 합계와 세부사업 확정액 차이 {item_total - total_won:+,}원")
    if subprojects and subproject_total != total_won:
        warnings.append(f"PDF 내역사업 합계와 확정액 차이 {subproject_total - total_won:+,}원")
    if local_candidates:
        warnings.append("LOFIN 지역 행은 키워드 후보이며 중앙예산에 가산하지 않음")
    if not beneficiary:
        warnings.append("사업설명자료에서 수혜자를 확인하지 못함")

    evidence_refs = [
        ref
        for ref in (
            evidence_ref(budget_basis),
            evidence_ref(implementation),
            evidence_ref(evidence.get("purpose")),
            evidence_ref(evidence.get("effects")),
        )
        if ref
    ]

    return {
        "id": str(workflow.get("id") or ""),
        "title": str(workflow.get("title") or core.get("detail_business_name") or ""),
        "is_reference": is_reference,
        "core": {
            "year": number(core.get("year")),
            "office_name": compact(core.get("office_name")),
            "account_name": compact(core.get("account_name")),
            "field_name": compact(core.get("field_name")),
            "section_name": compact(core.get("section_name")),
            "program_name": compact(core.get("program_name")),
            "unit_business_name": compact(core.get("unit_business_name")),
            "detail_business_name": compact(core.get("detail_business_name")),
            "congress_amt": total_won,
            "line_count": number(core.get("line_count")),
        },
        "coverage": str((workflow.get("coverage") or {}).get("level") or "api_only"),
        "implementation": {
            "method": method,
            "implementer": implementer,
            "beneficiary": beneficiary,
            "source_ref": str((implementation or {}).get("id") or ""),
        },
        "budget_basis_summary": budget_basis_summary(budget_basis),
        "subprojects": subprojects,
        "budget_items": items,
        "channels": channels,
        "crosswalks": crosswalks,
        "local_candidates": local_candidates,
        "local_candidate_total_count": len(workflow.get("local_reflections") or []),
        "evidence": evidence_refs,
        "reconciliation": {
            "business_total_won": total_won,
            "budget_item_total_won": item_total,
            "budget_item_difference_won": item_total - total_won,
            "budget_items_reconciled": item_total == total_won,
            "subproject_total_won": subproject_total,
            "subproject_difference_won": subproject_total - total_won if subprojects else None,
            "subprojects_reconciled": bool(subprojects) and subproject_total == total_won,
            "documented_crosswalk_won": crosswalk_total,
            "documented_crosswalk_share": round(crosswalk_total / total_won, 6) if total_won else 0,
        },
        "warnings": warnings,
        "insights": (
            [
                "PDF의 5개 내역사업 합계와 열린재정 API의 8개 목·세목 합계가 각각 237.53억원으로 일치합니다.",
                "자치단체경상보조 119.5억원은 보조율 50%가 명시된 두 항목 16억원과 103.5억원의 합과 정확히 일치합니다.",
                "17개 광역시도는 3억원 전수조사의 조사 대상이지 보조금 수령기관이라는 근거가 아닙니다.",
                "LOFIN에서 이 사업의 개별 지방자치단체 수령 내역을 확인하지 못했으므로 지역명은 추정하지 않았습니다.",
                "내역사업과 API 세목의 직접 연결은 문서·금액으로 확인되는 144.21억원만 실선 대사로 표시합니다.",
            ]
            if is_reference
            else []
        ),
    }


def main() -> int:
    source = load_json(SOURCE)
    workflows = source.get("workflows")
    if not isinstance(workflows, list) or not workflows:
        raise SystemExit(f"no workflows in {SOURCE}")

    maps = [build_map(row) for row in workflows if isinstance(row, dict)]
    maps.sort(
        key=lambda row: (
            0 if row.get("is_reference") else 1,
            str((row.get("core") or {}).get("office_name") or ""),
            str(row.get("title") or ""),
            str(row.get("id") or ""),
        )
    )
    ids = [str(row.get("id") or "") for row in maps]
    if len(set(ids)) != len(ids) or "" in ids:
        raise SystemExit("budget map ids are missing or duplicated")

    channel_totals: collections.Counter[str] = collections.Counter()
    for budget_map in maps:
        for channel in budget_map["channels"]:
            channel_totals[str(channel["code"])] += number(channel["amount_won"])

    meta = {
        "year": 2026,
        "scope": "three-ministry pilot",
        "map_count": len(maps),
        "default_business_id": REFERENCE_ID if REFERENCE_ID in ids else ids[0],
        "reference_business_title": REFERENCE_TITLE,
        "source_of_truth": "openfiscal_ExpenditureBudgetAdd2.Y_YY_DFN_KCUR_AMT",
        "pdf_role": "documented allocation, implementer, subsidy rate and beneficiary context",
        "lofin_role": "non-additive keyword_candidate only",
        "channel_totals_won": dict(sorted(channel_totals.items())),
    }
    payload = {"meta": meta, "maps": maps}
    summary = {
        **meta,
        "business_total_won": sum(row["core"]["congress_amt"] for row in maps),
        "api_reconciled_count": sum(
            1 for row in maps if row["reconciliation"]["budget_items_reconciled"]
        ),
        "pdf_subproject_count": sum(1 for row in maps if row["subprojects"]),
        "pdf_subproject_reconciled_count": sum(
            1 for row in maps if row["reconciliation"]["subprojects_reconciled"]
        ),
        "lofin_candidate_business_count": sum(1 for row in maps if row["local_candidates"]),
    }
    atomic_json(OUT, payload)
    atomic_json(SUMMARY, summary)
    print(
        json.dumps(
            {
                "output": str(OUT),
                "summary": str(SUMMARY),
                "map_count": len(maps),
                "default_business_id": meta["default_business_id"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
