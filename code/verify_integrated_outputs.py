#!/usr/bin/env python3
"""Offline integrity checks for the Koreabudget100 integrated pilot outputs.

This verifier deliberately performs no network access.  It cross-checks the
Open Fiscal source rows, the API-first canonical dataset, the enriched tree,
PDF reconciliation, optional LOFIN keyword candidates, and the generated HTML.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
NORM = ROOT / "data" / "normalized"
ART = ROOT / "artifacts"

EXPECTED_YEAR = "2026"
EXPECTED_LINE_COUNT = 9_350
EXPECTED_DETAIL_COUNT = 1_401
EXPECTED_TOTAL_WON = Decimal("133546671000000")
EXPECTED_LOCAL_TRANSFER_BUSINESS_COUNT = 163
EXPECTED_PDF_SOURCE_COUNTS = {
    "mois/mois_2026_budget_explainer.pdf": 285,
    "molit/molit_2026_budget.pdf": 347,
    "molit/molit_2026_fund.pdf": 58,
    "molit/molit_2026_rnd_info.pdf": 100,
}
EXPECTED_PDF_COUNT = sum(EXPECTED_PDF_SOURCE_COUNTS.values())
EXPECTED_RECON_STATUS_COUNTS = Counter(
    {"matched": 712, "ambiguous": 21, "unmatched": 57}
)
EXPECTED_OFFICES = {"행정안전부", "국토교통부", "산업통상부"}

DETAIL_FIELDS = (
    "office_name",
    "account_name",
    "program_name",
    "unit_business_name",
    "detail_business_name",
)
CODE_RE = re.compile(r"^\d{3,6}-\d{2,6}(?:(?:~|,)\d{2,6})*$")
HTML_TREE_RE = re.compile(
    r"<script\b(?=[^>]*\bid=[\"']tree-data[\"'])[^>]*>(.*?)</script\s*>",
    re.IGNORECASE | re.DOTALL,
)


class Audit:
    """Collect useful failures so one run reports more than the first defect."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.passes: list[str] = []
        self.skips: list[str] = []
        self._suppressed = 0

    def require(self, condition: bool, message: str) -> bool:
        if condition:
            return True
        if len(self.errors) < 200:
            self.errors.append(message)
        else:
            self._suppressed += 1
        return False

    def passed(self, message: str) -> None:
        self.passes.append(message)
        print(f"[PASS] {message}")

    def skipped(self, message: str) -> None:
        self.skips.append(message)
        print(f"[SKIP] {message}")

    def finish(self) -> int:
        if self.errors:
            for message in self.errors:
                print(f"[FAIL] {message}", file=sys.stderr)
            if self._suppressed:
                print(
                    f"[FAIL] {self._suppressed} additional failures suppressed",
                    file=sys.stderr,
                )
            print(
                f"VERIFY_FAILED errors={len(self.errors) + self._suppressed} "
                f"passes={len(self.passes)} skips={len(self.skips)}",
                file=sys.stderr,
            )
            return 1
        print(
            f"VERIFY_OK passes={len(self.passes)} skips={len(self.skips)} "
            f"details={EXPECTED_DETAIL_COUNT} lines={EXPECTED_LINE_COUNT} "
            f"total_won={int(EXPECTED_TOTAL_WON)} pdf_cards={EXPECTED_PDF_COUNT}"
        )
        return 0


def load_json(path: Path, audit: Audit, label: str, required: bool = True) -> Any:
    if not path.is_file():
        if required:
            audit.require(False, f"missing required {label}: {path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        audit.require(False, f"invalid {label} JSON {path}: {exc}")
        return None


def money(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal(0)
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"not a numeric amount: {value!r}") from exc


def year_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def detail_key(row: dict[str, Any], include_year: bool = True) -> tuple[str, ...]:
    fields = tuple(str(row.get(field) or "") for field in DETAIL_FIELDS)
    if include_year:
        return (year_text(row.get("year")), *fields)
    return fields


def expected_id(key: tuple[str, ...]) -> str:
    digest = hashlib.sha256("\x1f".join(key).encode("utf-8")).hexdigest()[:16]
    return "kb-" + digest


def normalized_name(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", str(value or "")).lower()


def validate_openfiscal(
    audit: Audit, details: Any, lines: Any
) -> tuple[dict[tuple[str, ...], dict[str, Any]], dict[tuple[str, ...], Decimal]]:
    if not audit.require(isinstance(details, list), "API details must be a JSON list"):
        return {}, {}
    if not audit.require(isinstance(lines, list), "API lines must be a JSON list"):
        return {}, {}

    audit.require(
        len(details) == EXPECTED_DETAIL_COUNT,
        f"API detail count {len(details)} != {EXPECTED_DETAIL_COUNT}",
    )
    audit.require(
        len(lines) == EXPECTED_LINE_COUNT,
        f"API line count {len(lines)} != {EXPECTED_LINE_COUNT}",
    )

    detail_map: dict[tuple[str, ...], dict[str, Any]] = {}
    detail_total = Decimal(0)
    for index, row in enumerate(details):
        if not audit.require(isinstance(row, dict), f"API detail[{index}] is not an object"):
            continue
        key = detail_key(row)
        audit.require(key[0] == EXPECTED_YEAR, f"API detail[{index}] has year {key[0]!r}")
        audit.require(
            all(key), f"API detail[{index}] has a blank canonical key component: {key!r}"
        )
        audit.require(key not in detail_map, f"duplicate API detail composite key: {key!r}")
        detail_map[key] = row
        try:
            amount = money(row.get("congress_amt"))
            audit.require(amount == amount.to_integral_value(), f"non-integer detail amount: {key!r}")
            detail_total += amount
        except ValueError as exc:
            audit.require(False, f"API detail amount error for {key!r}: {exc}")

    audit.require(
        len(detail_map) == EXPECTED_DETAIL_COUNT,
        f"unique API composite keys {len(detail_map)} != {EXPECTED_DETAIL_COUNT}",
    )
    audit.require(
        detail_total == EXPECTED_TOTAL_WON,
        f"API detail total {detail_total} != {EXPECTED_TOTAL_WON}",
    )
    audit.require(
        {key[1] for key in detail_map} == EXPECTED_OFFICES,
        f"API offices differ: {sorted({key[1] for key in detail_map})!r}",
    )

    line_amounts: dict[tuple[str, ...], Decimal] = defaultdict(Decimal)
    line_counts: Counter[tuple[str, ...]] = Counter()
    line_total = Decimal(0)
    for index, row in enumerate(lines):
        if not audit.require(isinstance(row, dict), f"API line[{index}] is not an object"):
            continue
        key = detail_key(row)
        audit.require(key in detail_map, f"API line[{index}] references unknown detail: {key!r}")
        try:
            amount = money(row.get("congress_amt"))
            raw = row.get("raw") or {}
            raw_amount = money(raw.get("Y_YY_DFN_KCUR_AMT")) * Decimal(1000)
            audit.require(
                amount == raw_amount,
                f"Add2 unit conversion mismatch at line[{index}]: {amount} != {raw_amount}",
            )
            audit.require(amount == amount.to_integral_value(), f"non-integer line amount: {key!r}")
            line_amounts[key] += amount
            line_counts[key] += 1
            line_total += amount
        except ValueError as exc:
            audit.require(False, f"API line amount error at line[{index}]: {exc}")

    audit.require(
        line_total == EXPECTED_TOTAL_WON,
        f"API line total {line_total} != {EXPECTED_TOTAL_WON}",
    )
    audit.require(
        set(line_amounts) == set(detail_map),
        "API line/detail composite-key sets differ",
    )
    for key, detail in detail_map.items():
        expected_amount = money(detail.get("congress_amt"))
        audit.require(
            line_amounts.get(key, Decimal(0)) == expected_amount,
            f"line-to-detail amount mismatch for {key!r}",
        )
        audit.require(
            line_counts.get(key, 0) == int(detail.get("line_count") or 0),
            f"line_count mismatch for {key!r}",
        )

    if not audit.errors:
        audit.passed("Open Fiscal Add2: 9,350 lines → 1,401 unique businesses; amount preserved")
    else:
        # Still mark the section only when all fixed headline invariants hold.
        if (
            len(details) == EXPECTED_DETAIL_COUNT
            and len(lines) == EXPECTED_LINE_COUNT
            and len(detail_map) == EXPECTED_DETAIL_COUNT
            and detail_total == line_total == EXPECTED_TOTAL_WON
        ):
            audit.passed("Open Fiscal headline counts and total")
    return detail_map, line_amounts


def validate_pdf(
    audit: Audit,
    cards: Any,
    parse_summary: Any,
    reconcile: Any,
    detail_map: dict[tuple[str, ...], dict[str, Any]],
) -> tuple[set[tuple[Any, ...]], Counter[str]]:
    if not audit.require(isinstance(cards, list), "PDF cards must be a JSON list"):
        return set(), Counter()
    if not audit.require(isinstance(reconcile, list), "PDF reconciliation must be a JSON list"):
        return set(), Counter()
    audit.require(len(cards) == EXPECTED_PDF_COUNT, f"PDF card count {len(cards)} != {EXPECTED_PDF_COUNT}")
    audit.require(
        len(reconcile) == len(cards),
        f"PDF reconciliation rows {len(reconcile)} != cards {len(cards)}",
    )

    source_counts: Counter[str] = Counter()
    card_provenance: Counter[tuple[Any, ...]] = Counter()
    banned_titles = {"사업명", "사업개요", "산출근거", "추진체계", "구분", "코드", "명칭"}
    placeholder_implementers = {
        "기관명", "구분", "미정", "해당없음", "해당 없음", "사업", "사업명",
        "직접수행", "절차내용", "지자체 보조", "2024년결산",
    }
    allowed_paths = {"직접", "위탁/출연", "보조", "융자", "출자", "기금"}
    aggregate_count = 0
    for index, card in enumerate(cards):
        if not audit.require(isinstance(card, dict), f"PDF card[{index}] is not an object"):
            continue
        source = str(card.get("source_pdf") or "")
        title = str(card.get("title") or "").strip()
        fields = card.get("fields") or {}
        code = str(fields.get("세부사업코드") or "")
        start = card.get("page_start")
        end = card.get("page_end")
        source_counts[source] += 1
        audit.require(source in EXPECTED_PDF_SOURCE_COUNTS, f"unexpected PDF source: {source!r}")
        audit.require(card.get("extractor") == "kordoc_chunks", f"non-kordoc PDF card[{index}]")
        audit.require(bool(title) and title not in banned_titles, f"invalid PDF title[{index}]: {title!r}")
        audit.require(
            not any(token in title.lower() for token in ("colspan", "rowspan", "</", "|")),
            f"table/HTML noise in PDF title[{index}]: {title!r}",
        )
        audit.require(bool(CODE_RE.fullmatch(code)), f"invalid PDF code[{index}]: {code!r}")
        audit.require(
            isinstance(start, int) and isinstance(end, int) and 1 <= start <= end,
            f"invalid PDF page provenance[{index}]: {start!r}-{end!r}",
        )
        audit.require(bool(card.get("anchor_chunk_id")), f"missing PDF anchor chunk[{index}]")
        audit.require(bool(card.get("source_chunk_start")), f"missing PDF chunk start[{index}]")
        audit.require(bool(card.get("source_chunk_end")), f"missing PDF chunk end[{index}]")
        code_type = str(fields.get("코드유형") or "")
        audit.require(code_type in {"detail", "aggregate"}, f"invalid PDF code type[{index}]")
        if code_type == "aggregate":
            aggregate_count += 1
        implementer = str(fields.get("사업시행주체") or "").strip()
        if implementer:
            audit.require(
                implementer not in placeholder_implementers,
                f"placeholder PDF implementer[{index}]: {implementer!r}",
            )
        paths = card.get("exec_paths") or []
        audit.require(isinstance(paths, list), f"PDF exec_paths[{index}] is not a list")
        if isinstance(paths, list):
            audit.require(
                all(path in allowed_paths for path in paths),
                f"unknown PDF execution path[{index}]: {paths!r}",
            )
            audit.require(len(paths) == len(set(paths)), f"duplicate PDF execution paths[{index}]")
        mentions = card.get("amount_mentions", card.get("amounts", [])) or []
        audit.require(isinstance(mentions, list), f"PDF amount_mentions[{index}] is not a list")
        if isinstance(mentions, list):
            audit.require(
                all("\n" not in str(value) and "\r" not in str(value) for value in mentions),
                f"un-normalized PDF amount mention[{index}]",
            )
        card_provenance[(source, start, end, title, code)] += 1

    audit.require(
        dict(source_counts) == EXPECTED_PDF_SOURCE_COUNTS,
        f"PDF per-source counts differ: {dict(source_counts)!r}",
    )
    audit.require(
        all(count == 1 for count in card_provenance.values()),
        "duplicate PDF card provenance/title/code tuple",
    )
    audit.require(aggregate_count == 7, f"aggregate PDF heading count {aggregate_count} != 7")

    if isinstance(parse_summary, dict):
        audit.require(parse_summary.get("total_cards") == len(cards), "PDF summary total_cards mismatch")
        summary_counts = {
            str(item.get("pdf") or ""): int(item.get("cards") or 0)
            for item in (parse_summary.get("pdfs") or [])
            if isinstance(item, dict)
        }
        audit.require(summary_counts == EXPECTED_PDF_SOURCE_COUNTS, "PDF parse summary per-source counts differ")
        audit.require(
            parse_summary.get("by_ministry") == {"행정안전부": 285, "국토교통부": 505},
            f"PDF parse summary ministry counts differ: {parse_summary.get('by_ministry')!r}",
        )
    else:
        audit.require(False, "PDF parse summary must be an object")

    api_name_counts = Counter(
        (key[1], normalized_name(key[-1])) for key in detail_map
    )
    recon_provenance: Counter[tuple[Any, ...]] = Counter()
    matched_attachment_keys: set[tuple[Any, ...]] = set()
    statuses: Counter[str] = Counter()
    for index, row in enumerate(reconcile):
        if not audit.require(isinstance(row, dict), f"reconcile[{index}] is not an object"):
            continue
        pdf = row.get("pdf") or {}
        source = str(pdf.get("source_pdf") or "")
        title = str(pdf.get("clean_title") or pdf.get("raw_title") or "").strip()
        code = str(pdf.get("code_hint") or "")
        start = pdf.get("page_start")
        end = pdf.get("page_end")
        # code_hint is intentionally only a hint: aggregate headings such as
        # 6040-301~902 may be shortened by the reconciler's code extractor.
        recon_provenance[(source, start, end, str(pdf.get("raw_title") or "").strip())] += 1
        status = str(row.get("status") or "")
        statuses[status] += 1
        audit.require(status in {"matched", "ambiguous", "unmatched"}, f"invalid reconcile status[{index}]")
        try:
            score = money(row.get("score"))
            audit.require(Decimal(0) <= score <= Decimal(100), f"score out of range[{index}]: {score}")
        except ValueError as exc:
            audit.require(False, f"invalid reconcile score[{index}]: {exc}")
        for rank in row.get("top3") or []:
            try:
                rank_score = money(rank.get("score"))
                audit.require(
                    Decimal(0) <= rank_score <= Decimal(100),
                    f"top3 score out of range[{index}]: {rank_score}",
                )
            except (AttributeError, ValueError) as exc:
                audit.require(False, f"invalid top3 row[{index}]: {exc}")
        match = row.get("api_match")
        if status == "matched":
            if not audit.require(isinstance(match, dict), f"matched reconcile[{index}] lacks api_match"):
                continue
            key = detail_key(match)
            audit.require(key in detail_map, f"matched reconcile[{index}] references unknown API key")
            audit.require(pdf.get("ministry") == match.get("office_name"), f"cross-ministry match[{index}]")
            if str(row.get("method") or "").startswith("exact_norm"):
                name_key = (str(match.get("office_name") or ""), normalized_name(match.get("detail_business_name")))
                audit.require(
                    api_name_counts[name_key] == 1,
                    f"duplicate exact API name was attached without disambiguation: {name_key!r}",
                )
            matched_attachment_keys.add((key, source, code, title))
        else:
            audit.require(match is None, f"{status} reconcile[{index}] must not carry api_match")
        if pdf.get("code_type") == "aggregate":
            audit.require(
                status == "ambiguous" and row.get("method") == "aggregate_heading",
                f"aggregate reconcile[{index}] was not held unresolved",
            )
        reflections = row.get("lofin_reflections") or []
        audit.require(
            row.get("lofin_hit_count", 0) == len(reflections),
            f"LOFIN reconcile hit count mismatch[{index}]",
        )
        for reflection in reflections:
            central_key = reflection.get("central_business_key")
            if central_key is not None:
                audit.require(
                    status == "matched"
                    and isinstance(match, dict)
                    and isinstance(central_key, list)
                    and tuple(str(value or "") for value in central_key) == detail_key(match),
                    f"keyed LOFIN reflection attached to the wrong reconcile row[{index}]",
                )

    # Reconciler preserves every source/page/title tuple from the parser.
    normalized_cards = Counter()
    for card in cards:
        fields = card.get("fields") or {}
        normalized_cards[
            (
                str(card.get("source_pdf") or ""),
                card.get("page_start"),
                card.get("page_end"),
                str(card.get("title") or "").strip(),
            )
        ] += 1
    audit.require(recon_provenance == normalized_cards, "PDF provenance changed during reconciliation")
    audit.require(sum(statuses.values()) == len(cards), "reconcile status counts do not cover every card")
    audit.require(
        statuses == EXPECTED_RECON_STATUS_COUNTS,
        f"reconcile status counts differ: {dict(statuses)!r}",
    )
    if cards:
        audit.require(
            statuses["matched"] / len(cards) >= 0.75,
            f"PDF matched coverage below 75%: {statuses['matched']}/{len(cards)}",
        )

    if (
        len(cards) == EXPECTED_PDF_COUNT
        and dict(source_counts) == EXPECTED_PDF_SOURCE_COUNTS
        and len(reconcile) == len(cards)
    ):
        audit.passed(
            "PDF: 790 coded cards with source pages; reconciliation is scoped and bounded"
        )
    return matched_attachment_keys, statuses


def validate_canonical(
    audit: Audit,
    envelope: Any,
    canonical_summary: Any,
    detail_map: dict[tuple[str, ...], dict[str, Any]],
    matched_attachment_keys: set[tuple[Any, ...]],
    reconcile_statuses: Counter[str],
) -> tuple[dict[tuple[str, ...], dict[str, Any]], dict[str, dict[str, Any]]]:
    if not audit.require(isinstance(envelope, dict), "canonical dataset must be an envelope object"):
        return {}, {}
    audit.require(
        envelope.get("schema_version") == "1.1",
        "canonical schema_version must be 1.1",
    )
    records = envelope.get("businesses")
    if not audit.require(isinstance(records, list), "canonical businesses must be a list"):
        return {}, {}
    audit.require(
        len(records) == EXPECTED_DETAIL_COUNT,
        f"canonical business count {len(records)} != {EXPECTED_DETAIL_COUNT}",
    )

    record_map: dict[tuple[str, ...], dict[str, Any]] = {}
    id_map: dict[str, dict[str, Any]] = {}
    canonical_total = Decimal(0)
    attached_pdf_keys: set[tuple[Any, ...]] = set()
    local_transfer_count = 0
    for index, record in enumerate(records):
        if not audit.require(isinstance(record, dict), f"canonical business[{index}] is not an object"):
            continue
        core = record.get("api_core") or {}
        key = detail_key(core)
        supplied_key = tuple(str(value) for value in (record.get("canonical_key") or []))
        audit.require(supplied_key == key, f"canonical_key/core mismatch[{index}]: {supplied_key!r} != {key!r}")
        audit.require(key in detail_map, f"canonical business[{index}] references unknown API detail")
        audit.require(key not in record_map, f"duplicate canonical key: {key!r}")
        record_map[key] = record
        business_id = str(record.get("id") or "")
        audit.require(business_id == expected_id(key), f"unstable canonical id[{index}]: {business_id!r}")
        audit.require(business_id not in id_map, f"duplicate canonical id: {business_id!r}")
        id_map[business_id] = record
        amount = money(core.get("congress_amt"))
        canonical_total += amount

        channels = record.get("execution_channels") or []
        audit.require(isinstance(channels, list) and bool(channels), f"missing channels for {key!r}")
        if isinstance(channels, list):
            channel_amount = sum((money(item.get("amount_won")) for item in channels), Decimal(0))
            channel_lines = sum(int(item.get("line_count") or 0) for item in channels)
            audit.require(channel_amount == amount, f"channel amount mismatch for {key!r}")
            audit.require(
                channel_lines == int(core.get("line_count") or 0),
                f"channel line_count mismatch for {key!r}",
            )
            has_positive_local = any(
                item.get("code") == "local_subsidy" and money(item.get("amount_won")) > 0
                for item in channels
            )
            local_transfer_count += int(has_positive_local)
            if record.get("local_reflections") or record.get("local_summary"):
                audit.require(has_positive_local, f"LOFIN attached to non-local-transfer business: {key!r}")

        for pdf in record.get("pdf_enrichment") or []:
            pdf_key = (
                key,
                str(pdf.get("source_pdf") or ""),
                str(pdf.get("code_hint") or ""),
                str(pdf.get("title") or "").strip(),
            )
            attached_pdf_keys.add(pdf_key)
            audit.require(
                isinstance(pdf.get("page_start"), int) and isinstance(pdf.get("page_end"), int),
                f"canonical PDF attachment lacks page provenance: {pdf_key!r}",
            )
            audit.require(money(pdf.get("score")) <= 100, f"canonical PDF score > 100: {pdf_key!r}")

        refs = record.get("source_refs") or []
        api_refs = [item for item in refs if item.get("source") == "openfiscal_ExpenditureBudgetAdd2"]
        audit.require(len(api_refs) == 1, f"canonical business lacks one Add2 source ref: {key!r}")
        if api_refs:
            audit.require(
                api_refs[0].get("amount_field") == "Y_YY_DFN_KCUR_AMT",
                f"wrong canonical amount-field provenance: {key!r}",
            )

    audit.require(set(record_map) == set(detail_map), "canonical/API composite-key sets differ")
    audit.require(len(id_map) == EXPECTED_DETAIL_COUNT, "canonical IDs are not one-to-one")
    audit.require(canonical_total == EXPECTED_TOTAL_WON, "canonical total amount differs from Add2")
    audit.require(
        local_transfer_count == EXPECTED_LOCAL_TRANSFER_BUSINESS_COUNT,
        f"positive local-transfer businesses {local_transfer_count} != {EXPECTED_LOCAL_TRANSFER_BUSINESS_COUNT}",
    )
    audit.require(
        attached_pdf_keys == matched_attachment_keys,
        "canonical PDF attachments differ from the matched-only reconciliation set",
    )

    unresolved = envelope.get("unresolved") or {}
    ambiguous = unresolved.get("pdf_ambiguous") or []
    unmatched = unresolved.get("pdf_unmatched") or []
    audit.require(len(ambiguous) == reconcile_statuses["ambiguous"], "canonical ambiguous count mismatch")
    audit.require(len(unmatched) == reconcile_statuses["unmatched"], "canonical unmatched count mismatch")
    audit.require(
        all(row.get("api_match") is None for row in [*ambiguous, *unmatched]),
        "canonical unresolved PDF rows must not carry api_match",
    )

    meta = envelope.get("meta") or {}
    if isinstance(canonical_summary, dict):
        audit.require(meta == canonical_summary, "canonical envelope meta/summary file differ")
    else:
        audit.require(False, "canonical summary must be an object")
    audit.require(meta.get("canonical_business_count") == EXPECTED_DETAIL_COUNT, "canonical meta count mismatch")
    audit.require(money(meta.get("total_amount_won")) == EXPECTED_TOTAL_WON, "canonical meta total mismatch")
    audit.require(meta.get("pdf_card_count") == EXPECTED_PDF_COUNT, "canonical meta PDF count mismatch")
    audit.require(
        meta.get("pdf_matched_card_count") == reconcile_statuses["matched"],
        "canonical meta matched PDF count mismatch",
    )
    audit.require(
        meta.get("local_transfer_candidate_count") == EXPECTED_LOCAL_TRANSFER_BUSINESS_COUNT,
        "canonical meta local-transfer candidate count mismatch",
    )
    sources = meta.get("sources") or {}
    audit.require(sources.get("api") == "ExpenditureBudgetAdd2", "canonical meta API source mismatch")

    if (
        len(record_map) == EXPECTED_DETAIL_COUNT
        and len(id_map) == EXPECTED_DETAIL_COUNT
        and canonical_total == EXPECTED_TOTAL_WON
    ):
        audit.passed("Canonical envelope: stable IDs, channels, sources, and matched-only enrichment")
    return record_map, id_map


def validate_tree(
    audit: Audit,
    tree: Any,
    record_map: dict[tuple[str, ...], dict[str, Any]],
    id_map: dict[str, dict[str, Any]],
) -> None:
    if not audit.require(isinstance(tree, dict), "canonical tree must be an object"):
        return
    seen_ids: list[str] = []

    def walk(node: dict[str, Any], path: tuple[str, ...], depth: int) -> tuple[Decimal, int]:
        children = node.get("children") or []
        audit.require(isinstance(children, list), f"tree children is not a list at {path!r}")
        child_amount = Decimal(0)
        child_count = 0
        if isinstance(children, list):
            names = [str(child.get("name") or "") for child in children if isinstance(child, dict)]
            audit.require(len(names) == len(set(names)), f"duplicate sibling tree name at {path!r}")
            for child in children:
                if not audit.require(isinstance(child, dict), f"non-object tree child at {path!r}"):
                    continue
                amount, count = walk(child, (*path, str(child.get("name") or "")), depth + 1)
                child_amount += amount
                child_count += count

        node_amount = money(node.get("amount"))
        node_count = int(node.get("count") or 0)
        business = node.get("business")
        if business is not None:
            audit.require(depth == 5, f"tree business occurs at depth {depth}, path={path!r}")
            audit.require(not children, f"tree business node has children: {path!r}")
            business_id = str((business or {}).get("id") or "")
            seen_ids.append(business_id)
            record = id_map.get(business_id)
            audit.require(record is not None, f"tree references unknown canonical id: {business_id!r}")
            if record is not None:
                key = tuple(str(value) for value in record.get("canonical_key") or [])
                audit.require(key[1:] == path, f"tree path/canonical key mismatch: {path!r} != {key!r}")
                expected_amount = money(record["api_core"].get("congress_amt"))
                audit.require(node_amount == expected_amount, f"tree leaf amount mismatch: {path!r}")
            audit.require(node_count == 1, f"tree business count must be 1: {path!r}")
            return node_amount, 1

        if children:
            audit.require(node_amount == child_amount, f"tree child amount sum mismatch at {path!r}")
            audit.require(node_count == child_count, f"tree child count sum mismatch at {path!r}")
            return node_amount, node_count
        audit.require(False, f"tree leaf lacks canonical business metadata: {path!r}")
        return node_amount, node_count

    amount, count = walk(tree, tuple(), 0)
    audit.require(tree.get("name") == "root", "canonical tree root name must be 'root'")
    audit.require(amount == EXPECTED_TOTAL_WON, "canonical tree total amount mismatch")
    audit.require(count == EXPECTED_DETAIL_COUNT, "canonical tree leaf count mismatch")
    audit.require(len(seen_ids) == EXPECTED_DETAIL_COUNT, "canonical tree business metadata count mismatch")
    audit.require(len(set(seen_ids)) == EXPECTED_DETAIL_COUNT, "canonical tree repeats business IDs")
    audit.require(set(seen_ids) == set(id_map), "canonical tree/dataset ID sets differ")
    if amount == EXPECTED_TOTAL_WON and count == EXPECTED_DETAIL_COUNT and len(set(seen_ids)) == count:
        audit.passed("Canonical tree: 1,401 unique leaves and exact recursive amount/count sums")


def lofin_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    detail_identity = str(row.get("detail_business_code") or row.get("detail_business_name") or "")
    return (
        str(row.get("exe_ymd") or ""),
        str(row.get("local_gov_code") or ""),
        detail_identity,
    )


def validate_lofin(
    audit: Audit,
    candidate_path: Path,
    candidate_summary_path: Path,
    require_lofin: bool,
    envelope: Any,
    record_map: dict[tuple[str, ...], dict[str, Any]],
) -> None:
    meta = envelope.get("meta") if isinstance(envelope, dict) else {}
    sources = (meta or {}).get("sources") or {}
    selected_name = sources.get("lofin")
    if not candidate_path.is_file():
        if require_lofin:
            audit.require(False, f"required LOFIN candidate file is missing: {candidate_path}")
        else:
            audit.require(
                selected_name in (None, ""),
                f"canonical meta names missing LOFIN file: {selected_name!r}",
            )
            attached = sum(
                len(record.get("local_reflections") or []) for record in record_map.values()
            )
            audit.require(attached == 0, "LOFIN candidate file absent but canonical rows are attached")
            audit.skipped(
                "LOFIN candidate integrity: candidate file explicitly absent; canonical build has no LOFIN source"
            )
        return

    rows = load_json(candidate_path, audit, "LOFIN candidates")
    if not audit.require(isinstance(rows, list), "LOFIN candidates must be a JSON list"):
        return
    audit.require(bool(rows), "LOFIN candidate file is present but empty")
    audit.require(selected_name == candidate_path.name, "canonical meta does not select the LOFIN candidate file")
    summary = load_json(candidate_summary_path, audit, "LOFIN candidate summary")
    if isinstance(summary, dict):
        warning = str(summary.get("non_additive_warning") or summary.get("sum_warning") or "")
        audit.require(bool(warning), "LOFIN summary lacks the non-additive hierarchy warning")
        audit.require(summary.get("complete") is True, "LOFIN candidate collection is not complete")
        audit.require(
            summary.get("positive_national_reflection_only") is True,
            "LOFIN summary does not guarantee positive national reflection rows",
        )
        audit.require(
            summary.get("candidate_business_count") == EXPECTED_LOCAL_TRANSFER_BUSINESS_COUNT,
            "LOFIN selected central-business count mismatch",
        )
        summary_count = summary.get(
            "normalized_row_count",
            summary.get("row_count", summary.get("candidate_row_count")),
        )
        if summary_count is not None:
            audit.require(int(summary_count) == len(rows), "LOFIN summary row count mismatch")
    else:
        audit.require(False, "LOFIN candidate summary must be an object")

    source_keys: set[tuple[tuple[str, ...], str, str, str]] = set()
    for index, row in enumerate(rows):
        if not audit.require(isinstance(row, dict), f"LOFIN row[{index}] is not an object"):
            continue
        supplied = row.get("central_business_key") or []
        key = tuple(str(value) for value in supplied)
        audit.require(len(key) == 6, f"LOFIN row[{index}] has invalid central key: {key!r}")
        if len(key) != 6:
            continue
        record = record_map.get(key)
        audit.require(record is not None, f"LOFIN row[{index}] references unknown central key")
        audit.require(key[0] == EXPECTED_YEAR, f"LOFIN row[{index}] central key year mismatch")
        audit.require(year_text(row.get("year")) == key[0], f"LOFIN row[{index}] year mismatch")
        exe_ymd = str(row.get("exe_ymd") or "")
        audit.require(exe_ymd.startswith(key[0]) and len(exe_ymd) == 8, f"LOFIN row[{index}] exe_ymd mismatch")
        audit.require(row.get("source") == "lofin_QWGJK", f"LOFIN row[{index}] source mismatch")
        audit.require(row.get("match_status") == "keyword_candidate", f"LOFIN row[{index}] is not candidate-only")
        audit.require(row.get("match_mode") == "keyword_dbiz_nm", f"LOFIN row[{index}] match mode mismatch")
        keyword = re.sub(r"\s+", "", str(row.get("keyword") or ""))
        audit.require(len(keyword) >= 4, f"LOFIN row[{index}] keyword is too broad: {keyword!r}")
        audit.require(bool(row.get("keyword_strategy")), f"LOFIN row[{index}] lacks keyword_strategy")
        audit.require(str(row.get("central_business_name") or "") == key[-1], f"LOFIN row[{index}] central name/key mismatch")
        try:
            national_amount = money(row.get("national_amt"))
            audit.require(national_amount > 0, f"LOFIN row[{index}] has non-positive bdg_ntep")
        except ValueError as exc:
            audit.require(False, f"LOFIN row[{index}] national amount error: {exc}")
        identity = lofin_identity(row)
        audit.require(all(identity), f"LOFIN row[{index}] lacks stable local identity")
        unique_key = (key, *identity)
        audit.require(unique_key not in source_keys, f"duplicate LOFIN candidate row: {unique_key!r}")
        source_keys.add(unique_key)
        if record is not None:
            channels = record.get("execution_channels") or []
            central_local = sum(
                (money(item.get("amount_won")) for item in channels if item.get("code") == "local_subsidy"),
                Decimal(0),
            )
            audit.require(central_local > 0, f"LOFIN row[{index}] central business has no local transfer")
            audit.require(
                money(row.get("central_local_transfer_amount_won")) == central_local,
                f"LOFIN row[{index}] central local-transfer amount mismatch",
            )

    attached_keys: set[tuple[tuple[str, ...], str, str, str]] = set()
    attached_count = 0
    matched_business_count = 0
    for key, record in record_map.items():
        attached = record.get("local_reflections") or []
        local_summary = record.get("local_summary")
        if not attached:
            audit.require(local_summary is None, f"local_summary without LOFIN rows: {key!r}")
            continue
        matched_business_count += 1
        attached_count += len(attached)
        audit.require(isinstance(local_summary, dict), f"LOFIN rows lack local_summary: {key!r}")
        if isinstance(local_summary, dict):
            audit.require(local_summary.get("match_status") == "keyword_candidate", f"wrong local match status: {key!r}")
            audit.require(local_summary.get("row_count") == len(attached), f"local_summary row_count mismatch: {key!r}")
            audit.require(bool(local_summary.get("sum_warning")), f"local_summary lacks sum warning: {key!r}")
        for row in attached:
            attached_key = (key, *lofin_identity(row))
            audit.require(attached_key not in attached_keys, f"duplicate canonical LOFIN reflection: {attached_key!r}")
            attached_keys.add(attached_key)
            audit.require(year_text(row.get("year")) == key[0], f"canonical LOFIN year mismatch: {attached_key!r}")

    audit.require(attached_keys == source_keys, "canonical LOFIN attachments differ from keyed candidate rows")
    audit.require(meta.get("lofin_row_count") == attached_count, "canonical meta LOFIN row count mismatch")
    audit.require(
        meta.get("lofin_matched_business_count") == matched_business_count,
        "canonical meta LOFIN matched-business count mismatch",
    )
    if rows and attached_keys == source_keys:
        audit.passed(
            "LOFIN: positive, year-compatible keyword candidates attach only by full central key"
        )


def validate_html(audit: Audit, tree: Any) -> None:
    primary = ART / "detail_business_structure.html"
    year_copy = ART / "detail_business_structure_2026.html"
    if not primary.is_file():
        audit.require(False, f"missing required HTML artifact: {primary}")
        return
    if not year_copy.is_file():
        audit.require(False, f"missing required HTML artifact: {year_copy}")
        return
    try:
        html = primary.read_text(encoding="utf-8")
        year_html = year_copy.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        audit.require(False, f"cannot read HTML artifacts: {exc}")
        return
    audit.require(html == year_html, "generic/year-specific HTML artifacts differ")
    for marker in (
        "ExpenditureBudgetAdd2",
        "Y_YY_DFN_KCUR_AMT",
        "LOFIN QWGJK",
        "keyword_candidate",
        "execution_channels",
        "pdf_enrichment",
        "local_summary",
    ):
        audit.require(marker in html, f"HTML lacks required marker: {marker}")
    for forbidden in ("TotalExpenditure1", "Y_YY_DFN_MEDI_KCUR_AMT"):
        audit.require(forbidden not in html, f"HTML contains stale provenance marker: {forbidden}")
    audit.require("광역" in html and "기초" in html and "중복" in html, "HTML lacks LOFIN hierarchy-overlap warning")
    match = HTML_TREE_RE.search(html)
    if not audit.require(match is not None, "HTML lacks <script id='tree-data'> JSON payload"):
        return
    payload = match.group(1).strip()
    audit.require("</" not in payload, "embedded tree JSON contains an unescaped closing-tag sequence")
    try:
        embedded = json.loads(payload.replace("<\\/", "</"))
    except json.JSONDecodeError as exc:
        audit.require(False, f"embedded HTML tree JSON is invalid: {exc}")
        return
    embedded_tree = embedded.get("tree") if isinstance(embedded, dict) else None
    embedded_meta = embedded.get("meta") if isinstance(embedded, dict) else None
    audit.require(embedded_tree == tree, "HTML embedded tree differs from canonical tree JSON")
    audit.require(
        isinstance(embedded_meta, dict)
        and embedded_meta.get("source") == "ExpenditureBudgetAdd2"
        and embedded_meta.get("amount_field") == "Y_YY_DFN_KCUR_AMT",
        "HTML embedded metadata has incorrect canonical provenance",
    )
    if embedded_tree == tree and html == year_html:
        audit.passed("HTML: enriched canonical tree embedded safely with correct Add2/LOFIN provenance")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-lofin",
        action="store_true",
        help="fail if the selective LOFIN candidate dataset is absent",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="repository root (primarily for isolated verification fixtures)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    global NORM, ART
    NORM = root / "data" / "normalized"
    ART = root / "artifacts"
    audit = Audit()

    paths = {
        "details": NORM / "expbudgetadd2_2026_pilots_details.json",
        "lines": NORM / "expbudgetadd2_2026_pilots_lines.json",
        "cards": NORM / "pdf_business_cards.json",
        "pdf_summary": NORM / "pdf_parse_summary.json",
        "reconcile": NORM / "reconcile_pdf_api_full.json",
        "canonical": NORM / "canonical_business_2026_pilots.json",
        "canonical_summary": NORM / "canonical_business_2026_pilots_summary.json",
        "tree": NORM / "canonical_business_tree_2026_pilots.json",
    }
    loaded = {name: load_json(path, audit, name) for name, path in paths.items()}

    detail_map, _ = validate_openfiscal(audit, loaded["details"], loaded["lines"])
    matched_keys, reconcile_statuses = validate_pdf(
        audit,
        loaded["cards"],
        loaded["pdf_summary"],
        loaded["reconcile"],
        detail_map,
    )
    record_map, id_map = validate_canonical(
        audit,
        loaded["canonical"],
        loaded["canonical_summary"],
        detail_map,
        matched_keys,
        reconcile_statuses,
    )
    validate_tree(audit, loaded["tree"], record_map, id_map)
    validate_lofin(
        audit,
        NORM / "lofin_local_transfer_candidates_2026.json",
        NORM / "lofin_local_transfer_candidates_2026_summary.json",
        args.require_lofin,
        loaded["canonical"],
        record_map,
    )
    validate_html(audit, loaded["tree"])
    return audit.finish()


if __name__ == "__main__":
    raise SystemExit(main())
