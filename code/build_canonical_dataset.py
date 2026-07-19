#!/usr/bin/env python3
"""Build the API-first canonical business dataset and enriched tree.

Open Fiscal is authoritative for hierarchy and amounts.  Matched PDF cards add
execution context, while LOFIN rows are attached only to businesses that have a
local-government transfer line in the central budget.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from reconcile_pdf_with_api import norm_text

ROOT = Path(__file__).resolve().parents[1]
NORM = ROOT / "data" / "normalized"
ART = ROOT / "artifacts"
DEFAULT_LOFIN = NORM / "lofin_local_transfer_candidates_2026.json"
LEGACY_LOFIN = NORM / "lofin_qwgjk_keyword_matches.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def detail_key(row: dict) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("office_name") or ""),
        str(row.get("account_name") or ""),
        str(row.get("program_name") or ""),
        str(row.get("unit_business_name") or ""),
        str(row.get("detail_business_name") or ""),
    )


def canonical_business_key(row: dict) -> tuple[str, ...]:
    return (str(row.get("year") or ""), *detail_key(row))


def normalize_central_key(value) -> tuple[str, ...] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 6:
        return None
    return tuple(str(item or "").strip() for item in value)


def numeric(value) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).replace(",", "").strip())


def stable_id(key: tuple[str, ...]) -> str:
    raw = "\x1f".join(key).encode("utf-8")
    return "kb-" + hashlib.sha256(raw).hexdigest()[:16]


def classify_channel(mok: str | None, semok: str | None) -> tuple[str, str]:
    mok = str(mok or "")
    semok = str(semok or "")
    blob = mok + " " + semok
    if "자치단체이전" in blob or "자치단체" in semok:
        return "local_subsidy", "지자체 이전"
    if "민간이전" in blob:
        return "private_transfer", "민간 이전"
    if "출연금" in blob:
        return "contribution", "출연"
    if "융자" in blob:
        return "loan", "융자"
    if "출자" in blob:
        return "equity", "출자"
    if "해외이전" in blob:
        return "international", "해외 이전"
    if mok in {"건설비", "유형자산", "무형자산", "건설보상비"}:
        return "capital", "시설·자산"
    return "direct", "직접 집행"


def aggregate_channels(lines: list[dict]) -> dict[tuple[str, ...], list[dict]]:
    grouped: dict[tuple[str, ...], dict[str, dict]] = defaultdict(dict)
    for row in lines:
        key = detail_key(row)
        code, label = classify_channel(row.get("mok_name"), row.get("semok_name"))
        bucket = grouped[key].setdefault(
            code,
            {"code": code, "label": label, "amount_won": 0.0, "line_count": 0},
        )
        bucket["amount_won"] += float(row.get("congress_amt") or 0)
        bucket["line_count"] += 1
    result = {}
    for key, buckets in grouped.items():
        total = sum(item["amount_won"] for item in buckets.values())
        values = sorted(buckets.values(), key=lambda item: item["amount_won"], reverse=True)
        for item in values:
            item["share"] = round(item["amount_won"] / total, 6) if total else 0.0
        result[key] = values
    return result


def pdf_by_detail(rows: list[dict]) -> dict[tuple[str, ...], list[dict]]:
    out: dict[tuple[str, ...], list[dict]] = defaultdict(list)
    seen = set()
    for row in rows:
        if row.get("status") != "matched" or not row.get("api_match"):
            continue
        match = row["api_match"]
        key = detail_key(match)
        pdf = row.get("pdf") or {}
        item = {
            "title": pdf.get("clean_title") or pdf.get("raw_title"),
            "code_hint": pdf.get("code_hint"),
            "code_type": pdf.get("code_type"),
            "implementer": pdf.get("implementer"),
            "execution_paths": pdf.get("exec_paths") or [],
            "source_pdf": pdf.get("source_pdf"),
            "page_start": pdf.get("page_start"),
            "page_end": pdf.get("page_end"),
            "anchor_chunk_id": pdf.get("anchor_chunk_id"),
            "anchor_chunk_ids": pdf.get("anchor_chunk_ids") or [],
            "source_chunk_start": pdf.get("source_chunk_start"),
            "source_chunk_end": pdf.get("source_chunk_end"),
            "snippet": pdf.get("snippet"),
            "confidence": row.get("confidence"),
            "score": row.get("score"),
            "method": row.get("method"),
        }
        dedup = (
            key,
            item["source_pdf"],
            item["page_start"],
            item["code_hint"],
            item["title"],
        )
        if dedup in seen:
            continue
        seen.add(dedup)
        out[key].append(item)
    return out


def local_summary(rows: list[dict]) -> dict:
    by_level = defaultdict(lambda: {"row_count": 0, "national_amount_won": 0.0})
    by_gov = defaultdict(
        lambda: {"row_count": 0, "national_amount_won": 0.0, "level": "unknown"}
    )
    total = 0.0
    for row in rows:
        amount = numeric(
            row.get("national_amount_won")
            if row.get("national_amount_won") is not None
            else row.get("national_amt")
        )
        total += amount
        level = str(row.get("local_level") or "unknown")
        by_level[level]["row_count"] += 1
        by_level[level]["national_amount_won"] += amount
        gov = str(row.get("local_gov_name") or "미상")
        by_gov[gov]["row_count"] += 1
        by_gov[gov]["national_amount_won"] += amount
        by_gov[gov]["level"] = level
    top = sorted(by_gov.items(), key=lambda item: item[1]["national_amount_won"], reverse=True)
    return {
        "match_status": "keyword_candidate",
        "attachment_methods": sorted(
            {str(row.get("attachment_method") or "unknown") for row in rows}
        ),
        "row_count": len(rows),
        "national_reflection_sum_won": total,
        "sum_warning": (
            "광역·기초 반영액이 같은 재원을 중복 표현할 수 있어 중앙예산과 직접 대사하지 않음"
        ),
        "by_level": dict(by_level),
        "top_local_govs": [{"name": name, **value} for name, value in top[:20]],
    }


def attach_lofin(
    detail: dict,
    pdf_items: list[dict],
    channels: list[dict],
    lofin_rows: list[dict],
) -> tuple[list[dict], dict | None]:
    local_amount = sum(
        item["amount_won"] for item in channels if item["code"] == "local_subsidy"
    )
    if local_amount <= 0:
        return [], None

    target_key = canonical_business_key(detail)
    exact_rows = []
    legacy_rows = []
    for row in lofin_rows:
        try:
            if int(row.get("year")) != int(detail.get("year")):
                continue
            if numeric(row.get("national_amt")) <= 0:
                continue
        except (TypeError, ValueError):
            continue
        row_key = normalize_central_key(row.get("central_business_key"))
        if row_key is not None:
            if row_key == target_key:
                exact_rows.append(row)
            # A keyed row belongs only to its declared central business.  It
            # must never be reconsidered by fuzzy/keyword fallback.
            continue
        legacy_rows.append(row)

    attachment_method = "exact_central_business_key"
    candidate_rows = exact_rows
    if not candidate_rows:
        attachment_method = "legacy_keyword_fallback"
        corpus_parts = [str(detail.get("detail_business_name") or "")]
        for item in pdf_items:
            corpus_parts.extend(
                [str(item.get("title") or ""), str(item.get("snippet") or "")]
            )
        corpus = norm_text(" ".join(corpus_parts))
        central_name = norm_text(detail.get("detail_business_name"))
        candidate_rows = []
        for row in legacy_rows:
            keyword = norm_text(row.get("keyword"))
            local_name = norm_text(row.get("detail_business_name"))
            keyword_hit = len(keyword) >= 4 and keyword in corpus
            name_hit = (
                len(central_name) >= 4
                and len(local_name) >= 4
                and (central_name in local_name or local_name in central_name)
            )
            if keyword_hit or name_hit:
                candidate_rows.append(row)

    hits = []
    seen = set()
    for row in candidate_rows:
        dedup = (
            target_key,
            str(row.get("exe_ymd") or ""),
            str(row.get("local_gov_code") or row.get("local_gov_name") or ""),
            str(
                row.get("detail_business_code")
                or row.get("detail_business_name")
                or ""
            ),
        )
        if dedup in seen:
            continue
        seen.add(dedup)
        hits.append(
            {
                "source": row.get("source") or "lofin_QWGJK",
                "match_status": row.get("match_status") or "keyword_candidate",
                "attachment_method": attachment_method,
                "central_business_key": row.get("central_business_key"),
                "keyword": row.get("keyword"),
                "keyword_strategy": row.get("keyword_strategy"),
                "local_gov_code": row.get("local_gov_code"),
                "local_gov_name": row.get("local_gov_name"),
                "local_level": row.get("local_level"),
                "detail_business_name": row.get("detail_business_name"),
                "detail_business_code": row.get("detail_business_code"),
                "national_amount_won": row.get("national_amt"),
                "year": row.get("year"),
                "exe_ymd": row.get("exe_ymd"),
            }
        )
    if not hits:
        return [], None
    summary = local_summary(hits)
    summary["central_local_transfer_amount_won"] = local_amount
    return hits, summary


def build_tree(records: list[dict]) -> dict:
    root = {"name": "root", "amount": 0.0, "count": 0, "children": {}}

    def ensure(node: dict, name: str) -> dict:
        return node["children"].setdefault(
            name,
            {"name": name, "amount": 0.0, "count": 0, "children": {}},
        )

    for record in records:
        core = record["api_core"]
        amount = float(core.get("congress_amt") or 0)
        path = [
            core.get("office_name") or "(부처미상)",
            core.get("account_name") or "(회계미상)",
            core.get("program_name") or "(프로그램미상)",
            core.get("unit_business_name") or "(단위사업미상)",
        ]
        nodes = [root]
        current = root
        for name in path:
            current = ensure(current, str(name))
            nodes.append(current)
        leaf = ensure(current, str(core.get("detail_business_name") or "(세부사업미상)"))
        leaf["amount"] += amount
        leaf["count"] += 1
        leaf["business"] = {
            "id": record["id"],
            "execution_channels": record["execution_channels"],
            "pdf_enrichment": record["pdf_enrichment"],
            "local_summary": record["local_summary"],
            "source_refs": record["source_refs"],
        }
        for node in nodes:
            node["amount"] += amount
            node["count"] += 1

    def freeze(node: dict) -> dict:
        children = [freeze(child) for child in node.pop("children").values()]
        children.sort(key=lambda child: child.get("amount") or 0, reverse=True)
        if children:
            node["children"] = children
        return node

    return freeze(root)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--api-details",
        default=str(NORM / "expbudgetadd2_2026_pilots_details.json"),
    )
    ap.add_argument(
        "--api-lines",
        default=str(NORM / "expbudgetadd2_2026_pilots_lines.json"),
    )
    ap.add_argument(
        "--reconcile",
        default=str(NORM / "reconcile_pdf_api_full.json"),
    )
    ap.add_argument(
        "--lofin",
        default=str(DEFAULT_LOFIN),
        help=(
            "keyed LOFIN candidate JSON; when the default does not exist, "
            "the legacy keyword pilot is used as a compatibility fallback"
        ),
    )
    ap.add_argument("--year", type=int, default=2026)
    args = ap.parse_args()

    details = load_json(Path(args.api_details))
    lines = load_json(Path(args.api_lines))
    reconcile_path = Path(args.reconcile)
    reconcile_rows = load_json(reconcile_path) if reconcile_path.exists() else []
    lofin_path = Path(args.lofin)
    if not lofin_path.exists() and args.lofin == str(DEFAULT_LOFIN) and LEGACY_LOFIN.exists():
        lofin_path = LEGACY_LOFIN
    lofin_rows = load_json(lofin_path) if lofin_path.exists() else []

    channels_by_key = aggregate_channels(lines)
    pdf_items_by_key = pdf_by_detail(reconcile_rows)
    records = []
    for detail in details:
        key = detail_key(detail)
        channels = channels_by_key.get(key, [])
        pdf_items = pdf_items_by_key.get(key, [])
        local_rows, local = attach_lofin(detail, pdf_items, channels, lofin_rows)
        source_refs = [
            {
                "source": "openfiscal_ExpenditureBudgetAdd2",
                "year": detail.get("year"),
                "amount_field": "Y_YY_DFN_KCUR_AMT",
            }
        ]
        for item in pdf_items:
            source_refs.append(
                {
                    "source": "ministry_budget_explainer_pdf",
                    "path": item.get("source_pdf"),
                    "page_start": item.get("page_start"),
                    "page_end": item.get("page_end"),
                    "anchor_chunk_id": item.get("anchor_chunk_id"),
                }
            )
        if local is not None:
            source_refs.append(
                {
                    "source": "lofin_QWGJK",
                    "row_count": local["row_count"],
                }
            )
        records.append(
            {
                "id": stable_id((str(detail.get("year") or ""), *key)),
                "canonical_key": [str(detail.get("year") or ""), *key],
                "api_core": detail,
                "execution_channels": channels,
                "pdf_enrichment": pdf_items,
                "local_reflections": local_rows,
                "local_summary": local,
                "source_refs": source_refs,
            }
        )

    tree = build_tree(records)
    matched_card_count = sum(row.get("status") == "matched" for row in reconcile_rows)
    status_counts = Counter(str(row.get("status") or "unknown") for row in reconcile_rows)
    source_counts = Counter(
        str((row.get("pdf") or {}).get("source_pdf") or "unknown")
        for row in reconcile_rows
    )
    summary = {
        "year": args.year,
        "scope": "three-ministry pilot",
        "pilot_ministries": ["행정안전부", "국토교통부", "산업통상부"],
        "api_line_count": len(lines),
        "canonical_business_count": len(records),
        "total_amount_won": sum(
            float(record["api_core"].get("congress_amt") or 0) for record in records
        ),
        "pdf_card_count": len(reconcile_rows),
        "pdf_matched_card_count": matched_card_count,
        "pdf_status_counts": dict(status_counts),
        "pdf_matched_business_count": sum(bool(record["pdf_enrichment"]) for record in records),
        "local_transfer_candidate_count": sum(
            any(
                item["code"] == "local_subsidy" and item["amount_won"] > 0
                for item in record["execution_channels"]
            )
            for record in records
        ),
        "lofin_matched_business_count": sum(record["local_summary"] is not None for record in records),
        "lofin_row_count": sum(
            (record["local_summary"] or {}).get("row_count", 0) for record in records
        ),
        "pdf_coverage": {
            "행정안전부": {
                "status": "parsed",
                "source_pdf_count": 1,
                "card_count": source_counts.get("mois/mois_2026_budget_explainer.pdf", 0),
            },
            "국토교통부": {
                "status": "parsed",
                "source_pdf_count": 3,
                "card_count": sum(
                    count for source, count in source_counts.items() if source.startswith("molit/")
                ),
            },
            "산업통상부": {
                "status": "api_only",
                "source_pdf_count": 0,
                "card_count": 0,
                "reason": (
                    "official attachment download returns server errors; one official viewer volume "
                    "is also incomplete, so no partial PDF enrichment is published"
                ),
                "official_page": "https://www.motir.go.kr/kor/article/ATCL3f70bb6cf/48/view",
            },
        },
        "sources": {
            "api": "ExpenditureBudgetAdd2",
            "pdf_reconcile": reconcile_path.name if reconcile_path.exists() else None,
            "lofin": lofin_path.name if lofin_path.exists() else None,
        },
    }

    NORM.mkdir(parents=True, exist_ok=True)
    ART.mkdir(parents=True, exist_ok=True)
    dataset_path = NORM / f"canonical_business_{args.year}_pilots.json"
    tree_path = NORM / f"canonical_business_tree_{args.year}_pilots.json"
    summary_path = NORM / f"canonical_business_{args.year}_pilots_summary.json"
    unresolved = {
        "pdf_ambiguous": [
            row for row in reconcile_rows if row.get("status") == "ambiguous"
        ],
        "pdf_unmatched": [
            row for row in reconcile_rows if row.get("status") == "unmatched"
        ],
    }
    envelope = {
        "schema_version": "1.1",
        "meta": summary,
        "businesses": records,
        "unresolved": unresolved,
    }
    write_json_atomic(dataset_path, envelope)
    write_json_atomic(tree_path, tree)
    write_json_atomic(summary_path, summary)
    write_json_atomic(ART / summary_path.name, summary)
    write_json_atomic(
        ART / "integration_status.json",
        {
            "schema_version": "1.0",
            "complete": True,
            "scope": summary["scope"],
            "canonical_summary": summary,
            "limitations": [
                "산업통상부는 공식 첨부 서버 장애로 PDF 설명 레이어 없이 API 정본만 제공",
                "LOFIN 연결은 keyword_candidate이며 광역·기초 반영액은 비가산적",
                "전국 전 부처 덤프가 아니라 3개 부처 파일럿 범위",
            ],
        },
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("wrote", dataset_path)
    print("wrote", tree_path)
    print("wrote", summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
