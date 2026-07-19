#!/usr/bin/env python3
"""Offline integrity checks for the evidence-backed workflow deliverables."""

from __future__ import annotations

import argparse
import collections
import json
import math
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
NORM = ROOT / "data" / "normalized"
ART = ROOT / "artifacts"
KORDOC = ROOT / "data" / "raw" / "kordoc"

DEFAULT_CANONICAL = NORM / "canonical_business_2026_pilots.json"
DEFAULT_WORKFLOWS = NORM / "business_workflows_2026_pilots.json"
DEFAULT_SUMMARY = ART / "business_workflows_2026_pilots_summary.json"
DEFAULT_LOFIN = NORM / "lofin_local_transfer_candidates_2026.json"
DEFAULT_HTML = ART / "detailed_business_workflows.html"
DEFAULT_HTML_YEAR = ART / "detailed_business_workflows_2026.html"

EXPECTED_WORKFLOW_COUNT = 1_401
EXPECTED_INDUSTRY_COUNT = 472
EXPECTED_PHASES = [
    {"id": "G0", "label": "근거·목적", "order": 0},
    {"id": "G1", "label": "예산 확정·구성", "order": 1},
    {"id": "G2", "label": "시행 구조", "order": 2},
    {"id": "G3", "label": "신청·선정·협약", "order": 3},
    {"id": "G4", "label": "집행·사업수행", "order": 4},
    {"id": "G5", "label": "지방재정 반영", "order": 5},
    {"id": "G6", "label": "성과·정산·환류", "order": 6},
]
ALLOWED_COVERAGE = {"documented_flow", "structured_facts", "api_only"}
ALLOWED_ASSERTIONS = {"api", "documented", "derived", "candidate"}
ALLOWED_EDGE_TYPES = {
    "sequence", "fund", "delivery", "information", "feedback", "candidate", "context"
}

CHUNK_FILES = {
    "mois/mois_2026_budget_explainer.pdf": KORDOC / "mois" / "mois_2026_budget_explainer" / "mois_2026_budget_explainer.chunks.json",
    "molit/molit_2026_budget.pdf": KORDOC / "molit" / "molit_2026_budget" / "molit_2026_budget.chunks.json",
    "molit/molit_2026_fund.pdf": KORDOC / "molit" / "molit_2026_fund" / "molit_2026_fund.chunks.json",
    "molit/molit_2026_rnd_info.pdf": KORDOC / "molit" / "molit_2026_rnd_info" / "molit_2026_rnd_info.chunks.json",
}


@dataclass
class Issues:
    """Collect many failures while keeping terminal output bounded."""

    counts: collections.Counter[str] = field(default_factory=collections.Counter)
    examples: dict[str, list[str]] = field(default_factory=dict)
    examples_per_code: int = 4

    def add(self, code: str, message: str) -> None:
        self.counts[code] += 1
        bucket = self.examples.setdefault(code, [])
        if len(bucket) < self.examples_per_code:
            bucket.append(message)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def report(self) -> None:
        for code in sorted(self.counts):
            print(f"[FAIL] {code} count={self.counts[code]}", file=sys.stderr)
            for example in self.examples.get(code, []):
                print(f"       {example}", file=sys.stderr)
        print(
            f"WORKFLOW_VERIFY_FAILED errors={self.total} categories={len(self.counts)}",
            file=sys.stderr,
        )


def path_arg(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path


def load_json(path: Path, issues: Issues, label: str) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        issues.add("missing_file", f"{label}: {path}")
    except json.JSONDecodeError as exc:
        issues.add("invalid_json", f"{label}: {path}: {exc}")
    except OSError as exc:
        issues.add("read_error", f"{label}: {path}: {exc}")
    return None


def read_text(path: Path, issues: Issues, label: str) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        issues.add("missing_file", f"{label}: {path}")
    except (OSError, UnicodeDecodeError) as exc:
        issues.add("read_error", f"{label}: {path}: {exc}")
    return None


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def amount(value: Any) -> float | None:
    return float(value) if is_number(value) else None


def same_amount(left: Any, right: Any) -> bool:
    a, b = amount(left), amount(right)
    return a is not None and b is not None and math.isclose(a, b, rel_tol=0, abs_tol=0.5)


def compact_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^0-9a-z가-힣]", "", text)


def list_ids(
    values: Any,
    path: str,
    issues: Issues,
    global_seen: set[str] | None = None,
) -> tuple[list[dict[str, Any]], set[str]]:
    if not isinstance(values, list):
        issues.add("invalid_list", f"{path} must be a list")
        return [], set()
    rows: list[dict[str, Any]] = []
    ids: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            issues.add("invalid_object", f"{path}[{index}] must be an object")
            continue
        rows.append(value)
        identifier = value.get("id")
        if not isinstance(identifier, str) or not identifier:
            issues.add("missing_id", f"{path}[{index}]")
            continue
        ids.append(identifier)
        if global_seen is not None:
            if identifier in global_seen:
                issues.add("duplicate_global_id", f"{path}[{index}] id={identifier}")
            global_seen.add(identifier)
    for identifier, count in collections.Counter(ids).items():
        if count > 1:
            issues.add("duplicate_local_id", f"{path} id={identifier} count={count}")
    return rows, set(ids)


@dataclass
class ChunkCatalog:
    source_pdf: str
    rows: list[dict[str, Any]]
    index: dict[str, int]
    pdf_pages: int
    checked: set[tuple[Any, ...]] = field(default_factory=set)

    def validate_span(
        self,
        value: dict[str, Any],
        label: str,
        issues: Issues,
        start_key: str = "chunk_start",
        end_key: str = "chunk_end",
        anchor_key: str | None = None,
    ) -> None:
        page_start, page_end = value.get("page_start"), value.get("page_end")
        chunk_start, chunk_end = value.get(start_key), value.get(end_key)
        anchor = value.get(anchor_key) if anchor_key else None
        cache_key = (page_start, page_end, chunk_start, chunk_end, anchor)
        if cache_key in self.checked:
            return
        self.checked.add(cache_key)
        if not isinstance(page_start, int) or isinstance(page_start, bool):
            issues.add("invalid_pdf_page", f"{label}: page_start={page_start!r}")
            return
        if not isinstance(page_end, int) or isinstance(page_end, bool):
            issues.add("invalid_pdf_page", f"{label}: page_end={page_end!r}")
            return
        if not 1 <= page_start <= page_end <= self.pdf_pages:
            issues.add("invalid_pdf_page_range", f"{label}: {page_start}-{page_end}/{self.pdf_pages}")
        start_index = self.index.get(str(chunk_start or ""))
        end_index = self.index.get(str(chunk_end or ""))
        if start_index is None or end_index is None:
            issues.add("unknown_pdf_chunk", f"{label}: {chunk_start!r}-{chunk_end!r}")
            return
        if start_index > end_index:
            issues.add("reversed_pdf_chunk_range", f"{label}: {chunk_start}>{chunk_end}")
            return
        pages = [
            row.get("page")
            for row in self.rows[start_index : end_index + 1]
            if isinstance(row.get("page"), int) and not isinstance(row.get("page"), bool)
        ]
        if not pages:
            issues.add("chunk_range_without_pages", f"{label}: {chunk_start}-{chunk_end}")
        elif min(pages) != page_start or max(pages) != page_end:
            issues.add(
                "pdf_page_chunk_mismatch",
                f"{label}: declared={page_start}-{page_end}, chunks={min(pages)}-{max(pages)}",
            )
        if anchor_key:
            anchor_index = self.index.get(str(anchor or ""))
            if anchor_index is None:
                issues.add("unknown_pdf_anchor", f"{label}: {anchor!r}")
            elif not start_index <= anchor_index <= end_index:
                issues.add("pdf_anchor_outside_range", f"{label}: {anchor!r}")


def load_chunk_catalogs(issues: Issues) -> dict[str, ChunkCatalog]:
    catalogs: dict[str, ChunkCatalog] = {}
    for source_pdf, path in CHUNK_FILES.items():
        data = load_json(path, issues, f"Kordoc chunks {source_pdf}")
        meta = load_json(path.with_suffix(".meta.json"), issues, f"Kordoc meta {source_pdf}")
        if not isinstance(data, list) or not isinstance(meta, dict):
            continue
        rows = [row for row in data if isinstance(row, dict)]
        ids = [str(row.get("id")) for row in rows if row.get("id") is not None]
        if len(ids) != len(set(ids)):
            issues.add("duplicate_chunk_id", source_pdf)
        pdf_pages = meta.get("pdf_pages")
        if not isinstance(pdf_pages, int) or pdf_pages <= 0:
            issues.add("invalid_pdf_page_count", f"{source_pdf}: {pdf_pages!r}")
            continue
        catalogs[source_pdf] = ChunkCatalog(
            source_pdf,
            rows,
            {str(row.get("id")): i for i, row in enumerate(rows) if row.get("id") is not None},
            pdf_pages,
        )
    return catalogs


def validate_pdf_span(
    value: dict[str, Any],
    label: str,
    catalogs: dict[str, ChunkCatalog],
    issues: Issues,
    start_key: str = "chunk_start",
    end_key: str = "chunk_end",
    anchor_key: str | None = None,
) -> None:
    source_pdf = str(value.get("source_pdf") or "")
    catalog = catalogs.get(source_pdf)
    if catalog is None:
        issues.add("unknown_source_pdf", f"{label}: {source_pdf!r}")
        return
    catalog.validate_span(value, label, issues, start_key, end_key, anchor_key)


def validate_source_refs(
    owner: dict[str, Any],
    path: str,
    evidence_by_id: dict[str, dict[str, Any]],
    catalogs: dict[str, ChunkCatalog],
    issues: Issues,
) -> None:
    refs = owner.get("source_refs")
    if not isinstance(refs, list):
        issues.add("invalid_source_refs", path)
        return
    pdf_count = 0
    for index, ref in enumerate(refs):
        ref_path = f"{path}.source_refs[{index}]"
        if not isinstance(ref, dict):
            issues.add("invalid_source_ref", ref_path)
            continue
        source_type = ref.get("source_type")
        if source_type not in {"openfiscal_api", "ministry_pdf", "lofin_api"}:
            issues.add("invalid_source_type", f"{ref_path}: {source_type!r}")
            continue
        if source_type == "ministry_pdf":
            pdf_count += 1
            evidence_id = ref.get("evidence_id")
            if evidence_id is not None:
                evidence = evidence_by_id.get(str(evidence_id))
                if evidence is None:
                    issues.add("invalid_evidence_ref", f"{ref_path}: {evidence_id!r}")
                    continue
                for key in ("source_pdf", "page_start", "page_end", "chunk_start", "chunk_end"):
                    if ref.get(key) != evidence.get(key):
                        issues.add("evidence_ref_mismatch", f"{ref_path}: {key}")
            elif not ref.get("field"):
                issues.add("pdf_ref_without_evidence_or_field", ref_path)
            validate_pdf_span(ref, ref_path, catalogs, issues)
        elif ref.get("evidence_id") is not None:
            issues.add("non_pdf_evidence_ref", ref_path)
    assertion = owner.get("assertion")
    if assertion not in ALLOWED_ASSERTIONS:
        issues.add("invalid_assertion", f"{path}: {assertion!r}")
    if assertion == "documented" and not pdf_count:
        issues.add("documented_without_pdf", path)


def lofin_identity(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        tuple(str(value or "") for value in row.get("central_business_key") or []),
        str(row.get("keyword") or ""),
        str(row.get("exe_ymd") or ""),
        str(row.get("local_gov_code") or row.get("local_gov_name") or ""),
        str(row.get("detail_business_code") or row.get("detail_business_name") or ""),
        float(row.get("national_amt") or 0),
    )


def validate_lofin_row(
    row: dict[str, Any], path: str, canonical_key: list[Any], issues: Issues, require_additive: bool
) -> None:
    if row.get("source") != "lofin_QWGJK":
        issues.add("invalid_lofin_source", f"{path}: {row.get('source')!r}")
    if row.get("match_status") != "keyword_candidate":
        issues.add("invalid_lofin_status", f"{path}: {row.get('match_status')!r}")
    if row.get("central_business_key") != canonical_key:
        issues.add("lofin_central_key_mismatch", path)
    if row.get("year") != 2026:
        issues.add("invalid_lofin_year", f"{path}: {row.get('year')!r}")
    if not str(row.get("exe_ymd") or "").startswith("2026"):
        issues.add("invalid_lofin_date", f"{path}: {row.get('exe_ymd')!r}")
    national_amount = amount(row.get("national_amt"))
    if national_amount is None or national_amount <= 0:
        issues.add("invalid_lofin_amount", f"{path}: {row.get('national_amt')!r}")
    if require_additive and row.get("additive") is not False:
        issues.add("lofin_must_be_non_additive", f"{path}: {row.get('additive')!r}")


def reachable(adjacency: dict[str, set[str]], source: str, target: str) -> bool:
    if source == target:
        return False
    pending, visited = [source], {source}
    while pending:
        current = pending.pop()
        for nxt in adjacency.get(current, set()):
            if nxt == target:
                return True
            if nxt not in visited:
                visited.add(nxt)
                pending.append(nxt)
    return False


def validate_ordered_terms(
    workflow: dict[str, Any],
    groups: list[tuple[str, ...]],
    fixture_name: str,
    issues: Issues,
) -> None:
    procedure_nodes = [
        node
        for node in workflow.get("nodes") or []
        if isinstance(node, dict) and node.get("kind") == "procedure"
    ]
    node_text = {
        str(node.get("id")): compact_text(f"{node.get('label', '')} {node.get('detail', '')}")
        for node in procedure_nodes
    }
    adjacency: dict[str, set[str]] = collections.defaultdict(set)
    for edge in workflow.get("edges") or []:
        if (
            isinstance(edge, dict)
            and edge.get("type") == "sequence"
            and edge.get("assertion") == "documented"
        ):
            adjacency[str(edge.get("from"))].add(str(edge.get("to")))
    candidates: list[list[str]] = []
    for group in groups:
        terms = tuple(compact_text(term) for term in group)
        matches = [node_id for node_id, text in node_text.items() if all(term in text for term in terms)]
        candidates.append(matches)
        if not matches:
            issues.add("fixture_missing_term", f"{fixture_name}: no procedure node contains {group}")
    if any(not matches for matches in candidates):
        return
    possible = set(candidates[0])
    for matches in candidates[1:]:
        possible = {
            target
            for target in matches
            if any(reachable(adjacency, source, target) for source in possible)
        }
        if not possible:
            issues.add("fixture_sequence_broken", f"{fixture_name}: requested order is not connected")
            return


def find_workflow(
    workflows: Iterable[dict[str, Any]], title: str, office: str | None = None
) -> dict[str, Any] | None:
    wanted = compact_text(title)
    for workflow in workflows:
        if compact_text(workflow.get("title")) != wanted:
            continue
        core = workflow.get("core") if isinstance(workflow.get("core"), dict) else {}
        if office is None or core.get("office_name") == office:
            return workflow
    return None


def validate_fixtures(workflows: list[dict[str, Any]], issues: Issues) -> None:
    policy = find_workflow(workflows, "정책연구개발", "행정안전부")
    if policy is None:
        issues.add("fixture_missing_business", "행정안전부 정책연구개발")
    else:
        if (policy.get("coverage") or {}).get("level") != "documented_flow":
            issues.add("fixture_wrong_coverage", "행정안전부 정책연구개발")
        validate_ordered_terms(
            policy,
            [
                ("신청",),
                ("사전", "검토"),
                ("심의", "선정"),
                ("결과", "통보", "예산", "배정"),
                ("용역", "추진"),
                ("결과", "등록"),
            ],
            "행정안전부 정책연구개발",
            issues,
        )

    institute = find_workflow(
        workflows, "한국지방행정연구원정책개발연구등지원", "행정안전부"
    )
    if institute is None:
        issues.add("fixture_missing_business", "한국지방행정연구원정책개발연구등지원")
    else:
        validate_ordered_terms(
            institute,
            [("수요조사",), ("착수",), ("보고",)],
            "한국지방행정연구원정책개발연구등지원",
            issues,
        )
        procedure_evidence = " ".join(
            str(section.get("text") or "")
            for section in institute.get("evidence_sections") or []
            if isinstance(section, dict) and section.get("section") == "procedure"
        )
        if "분기" not in procedure_evidence:
            issues.add(
                "fixture_missing_term",
                "한국지방행정연구원정책개발연구등지원: procedure evidence lacks 분기",
            )

    mobility = find_workflow(workflows, "교통약자 이동편의 증진", "국토교통부")
    if mobility is None:
        issues.add("fixture_missing_business", "교통약자 이동편의 증진")
    elif not mobility.get("local_reflections"):
        issues.add("fixture_missing_lofin", "교통약자 이동편의 증진")
    elif not any(
        isinstance(node, dict) and node.get("kind") == "local_candidate"
        for node in mobility.get("nodes") or []
    ):
        issues.add("fixture_missing_lofin", "교통약자 이동편의 증진: no candidate node")


def validate_html(
    html_text: str,
    expected: dict[str, Any],
    path: Path,
    issues: Issues,
) -> None:
    open_match = re.search(
        r"<script\b(?=[^>]*\bid=[\"']workflow-data[\"'])[^>]*>",
        html_text,
        re.IGNORECASE,
    )
    if open_match is None:
        issues.add("html_missing_embed", f"{path}: script#workflow-data")
        return
    remainder = html_text[open_match.end() :]
    close_match = re.search(r"</script\s*>", remainder, re.IGNORECASE)
    if close_match is None:
        issues.add("html_missing_embed_close", str(path))
        return
    close_start = open_match.end() + close_match.start()
    close_end = open_match.end() + close_match.end()
    payload = html_text[open_match.end() : close_start].strip()
    if "<" in payload:
        issues.add("unsafe_html_json", f"{path}: embedded JSON contains raw '<'")
    try:
        embedded = json.loads(payload)
    except json.JSONDecodeError as exc:
        issues.add("invalid_html_json", f"{path}: {exc}")
        embedded = None
    if embedded is not None and embedded != expected:
        issues.add("html_data_mismatch", f"{path}: embedded JSON differs from normalized output")

    outside = html_text[: open_match.start()] + html_text[close_end:]
    for tab in ("workflow", "budget", "evidence"):
        if not re.search(
            rf"<button\b[^>]*\bdata-tab=[\"']{tab}[\"']", outside, re.IGNORECASE
        ):
            issues.add("html_missing_tab", f"{path}: button[data-tab={tab}]")
        if not re.search(
            rf"<section\b[^>]*\bid=[\"']tab-{tab}[\"']", outside, re.IGNORECASE
        ):
            issues.add("html_missing_tab_panel", f"{path}: section#tab-{tab}")
    if not re.search(
        r"<input\b(?=[^>]*(?:type=[\"']search[\"']|id=[\"'][^\"']*search[^\"']*[\"']))[^>]*>",
        outside,
        re.IGNORECASE,
    ):
        issues.add("html_missing_search", str(path))
    if not re.search(r"addEventListener\s*\(\s*[\"']input[\"']", outside):
        issues.add("html_search_not_wired", str(path))
    if "evidence_sections" not in outside or "source_refs" not in outside:
        issues.add("html_missing_evidence_logic", str(path))
    if not all(term in outside for term in ("LOFIN", "keyword_candidate")):
        issues.add("html_missing_lofin_warning", f"{path}: LOFIN/keyword_candidate")
    if not any(term in outside for term in ("합산", "비가산", "중복")):
        issues.add("html_missing_lofin_warning", f"{path}: non-additive warning")


def validate_all(
    canonical: dict[str, Any],
    envelope: dict[str, Any],
    summary: dict[str, Any],
    lofin_source: list[Any],
    catalogs: dict[str, ChunkCatalog],
    issues: Issues,
) -> dict[str, int]:
    canonical_rows = canonical.get("businesses")
    workflows = envelope.get("workflows")
    if not isinstance(canonical_rows, list):
        issues.add("invalid_canonical_schema", "canonical.businesses must be a list")
        canonical_rows = []
    if not isinstance(workflows, list):
        issues.add("invalid_workflow_schema", "workflows must be a list")
        workflows = []
    canonical_rows = [row for row in canonical_rows if isinstance(row, dict)]
    workflows = [row for row in workflows if isinstance(row, dict)]
    if len(canonical_rows) != EXPECTED_WORKFLOW_COUNT:
        issues.add("canonical_count_mismatch", f"expected=1401 actual={len(canonical_rows)}")
    if len(workflows) != EXPECTED_WORKFLOW_COUNT:
        issues.add("workflow_count_mismatch", f"expected=1401 actual={len(workflows)}")

    canonical_by_id: dict[str, dict[str, Any]] = {}
    for index, business in enumerate(canonical_rows):
        identifier = business.get("id")
        if not isinstance(identifier, str) or not identifier:
            issues.add("missing_canonical_id", f"businesses[{index}]")
        elif identifier in canonical_by_id:
            issues.add("duplicate_canonical_id", identifier)
        else:
            canonical_by_id[identifier] = business
    workflow_ids = [str(row.get("id") or "") for row in workflows]
    for identifier, count in collections.Counter(workflow_ids).items():
        if not identifier:
            issues.add("missing_workflow_id", f"count={count}")
        elif count > 1:
            issues.add("duplicate_workflow_id", f"{identifier} count={count}")
    if set(workflow_ids) != set(canonical_by_id):
        issues.add("workflow_canonical_id_set_mismatch", "workflow/canonical ID sets differ")

    actor_seen: set[str] = set()
    node_seen: set[str] = set()
    edge_seen: set[str] = set()
    evidence_seen: set[str] = set()
    coverage_counts: collections.Counter[str] = collections.Counter()
    workflow_lofin: collections.Counter[tuple[Any, ...]] = collections.Counter()

    for workflow_index, workflow in enumerate(workflows):
        workflow_id = str(workflow.get("id") or "")
        prefix = f"workflows[{workflow_index}]({workflow_id})"
        business = canonical_by_id.get(workflow_id)
        if business is None:
            continue
        if workflow.get("canonical_key") != business.get("canonical_key"):
            issues.add("canonical_key_mismatch", prefix)
        if workflow.get("core") != business.get("api_core"):
            issues.add("canonical_core_mismatch", prefix)
        core = workflow.get("core") if isinstance(workflow.get("core"), dict) else {}
        canonical_core = business.get("api_core") if isinstance(business.get("api_core"), dict) else {}
        if workflow.get("title") != canonical_core.get("detail_business_name"):
            issues.add("canonical_title_mismatch", prefix)
        if not same_amount(core.get("congress_amt"), canonical_core.get("congress_amt")):
            issues.add("canonical_amount_mismatch", prefix)
        if workflow.get("execution_channels") != business.get("execution_channels"):
            issues.add("execution_channel_mismatch", prefix)
        if workflow.get("local_summary") != business.get("local_summary"):
            issues.add("local_summary_mismatch", prefix)

        coverage = workflow.get("coverage") if isinstance(workflow.get("coverage"), dict) else {}
        level = coverage.get("level")
        if level not in ALLOWED_COVERAGE:
            issues.add("invalid_coverage_level", f"{prefix}: {level!r}")
        else:
            coverage_counts[level] += 1
        if coverage.get("phase_model") != "presentation_derived":
            issues.add("unmarked_derived_phase_model", prefix)

        actors, actor_ids = list_ids(workflow.get("actors"), f"{prefix}.actors", issues, actor_seen)
        phases, phase_ids = list_ids(workflow.get("phases"), f"{prefix}.phases", issues)
        nodes, node_ids = list_ids(workflow.get("nodes"), f"{prefix}.nodes", issues, node_seen)
        edges, _ = list_ids(workflow.get("edges"), f"{prefix}.edges", issues, edge_seen)
        evidence, _ = list_ids(
            workflow.get("evidence_sections"), f"{prefix}.evidence_sections", issues, evidence_seen
        )
        evidence_by_id = {str(row.get("id")): row for row in evidence}
        if phases != EXPECTED_PHASES or phase_ids != {f"G{i}" for i in range(7)}:
            issues.add("invalid_phase_model", prefix)

        for index, section in enumerate(evidence):
            section_path = f"{prefix}.evidence_sections[{index}]"
            if section.get("source_type") != "ministry_pdf":
                issues.add("invalid_evidence_source", section_path)
            if not compact_text(section.get("text")):
                issues.add("empty_evidence_text", section_path)
            match = section.get("match")
            if not isinstance(match, dict):
                issues.add("invalid_pdf_match", section_path)
            else:
                score = amount(match.get("score"))
                if score is None or not 0 <= score <= 100:
                    issues.add("invalid_pdf_match_score", f"{section_path}: {match.get('score')!r}")
                if match.get("confidence") not in {"high", "medium"}:
                    issues.add("invalid_pdf_match_confidence", section_path)
            validate_pdf_span(section, section_path, catalogs, issues)

        node_by_id = {str(node.get("id")): node for node in nodes}
        for index, actor in enumerate(actors):
            validate_source_refs(actor, f"{prefix}.actors[{index}]", evidence_by_id, catalogs, issues)
        display_ids = [node.get("display_id") for node in nodes]
        if len(display_ids) != len(set(display_ids)):
            issues.add("duplicate_display_id", prefix)
        for index, node in enumerate(nodes):
            node_path = f"{prefix}.nodes[{index}]"
            if node.get("actor") not in actor_ids:
                issues.add("invalid_node_actor_ref", node_path)
            if node.get("phase") not in phase_ids:
                issues.add("invalid_node_phase_ref", node_path)
            validate_source_refs(node, node_path, evidence_by_id, catalogs, issues)

        local_node_ids = {str(n.get("id")) for n in nodes if n.get("kind") == "local_candidate"}
        sequence_edges = 0
        candidate_edges = 0
        for index, edge in enumerate(edges):
            edge_path = f"{prefix}.edges[{index}]"
            if edge.get("from") not in node_ids or edge.get("to") not in node_ids:
                issues.add("invalid_edge_endpoint", edge_path)
            edge_type, assertion = edge.get("type"), edge.get("assertion")
            if edge_type not in ALLOWED_EDGE_TYPES:
                issues.add("invalid_edge_type", f"{edge_path}: {edge_type!r}")
            validate_source_refs(edge, edge_path, evidence_by_id, catalogs, issues)
            if edge_type == "sequence" and assertion == "documented":
                sequence_edges += 1
            if edge_type == "context" and assertion != "derived":
                issues.add("derived_edge_not_marked", edge_path)
            if assertion == "derived" and edge_type != "context":
                issues.add("unexpected_derived_edge", edge_path)
            if edge_type == "fund":
                source = node_by_id.get(str(edge.get("from")), {})
                target = node_by_id.get(str(edge.get("to")), {})
                if assertion != "api" or source.get("kind") != "budget" or target.get("kind") != "budget_item":
                    issues.add("invalid_fund_edge", edge_path)
            touches_local = edge.get("from") in local_node_ids or edge.get("to") in local_node_ids
            if touches_local:
                if edge_type != "candidate" or assertion != "candidate":
                    issues.add("lofin_confirmed_as_fund", edge_path)
                else:
                    candidate_edges += 1
            if edge_type == "candidate" and not touches_local:
                issues.add("candidate_edge_without_lofin_node", edge_path)
        if candidate_edges != len(local_node_ids):
            issues.add("lofin_candidate_edge_count_mismatch", prefix)

        pdf_cards = workflow.get("pdf_cards") if isinstance(workflow.get("pdf_cards"), list) else []
        for index, card in enumerate(pdf_cards):
            if not isinstance(card, dict):
                issues.add("invalid_pdf_card", f"{prefix}.pdf_cards[{index}]")
                continue
            validate_pdf_span(
                card, f"{prefix}.pdf_cards[{index}]", catalogs, issues,
                "source_chunk_start", "source_chunk_end", "anchor_chunk_id"
            )
        if coverage.get("pdf_card_count") != len(pdf_cards):
            issues.add("pdf_card_count_mismatch", prefix)

        explicit = coverage.get("explicit_procedure")
        if level == "documented_flow" and (explicit is not True or sequence_edges < 1):
            issues.add("documented_flow_without_sequence", prefix)
        if level != "documented_flow" and explicit is not False:
            issues.add("explicit_procedure_coverage_mismatch", prefix)
        if level == "structured_facts" and (not pdf_cards or sequence_edges):
            issues.add("invalid_structured_facts", prefix)
        if level == "api_only":
            pdf_refs = [
                ref for owner in actors + nodes + edges for ref in owner.get("source_refs", [])
                if isinstance(ref, dict) and ref.get("source_type") == "ministry_pdf"
            ]
            documented = [owner for owner in actors + nodes + edges if owner.get("assertion") == "documented"]
            if pdf_cards or evidence or pdf_refs or documented:
                issues.add("api_only_has_pdf_evidence", prefix)

        channels = workflow.get("execution_channels")
        if not isinstance(channels, list):
            issues.add("invalid_execution_channels", prefix)
            channels = []
        breakdown = workflow.get("budget_breakdown")
        if not isinstance(breakdown, list):
            issues.add("invalid_budget_breakdown", prefix)
            breakdown = []
        channel_total = sum(
            float(row.get("amount_won") or 0)
            for row in channels
            if isinstance(row, dict) and is_number(row.get("amount_won"))
        )
        breakdown_total = sum(
            float(row.get("amount_won") or 0)
            for row in breakdown
            if isinstance(row, dict) and is_number(row.get("amount_won"))
        )
        if not same_amount(channel_total, core.get("congress_amt")):
            issues.add(
                "execution_channel_amount_mismatch",
                f"{prefix}: channels={channel_total} core={core.get('congress_amt')!r}",
            )
        if not same_amount(breakdown_total, core.get("congress_amt")):
            issues.add(
                "budget_breakdown_amount_mismatch",
                f"{prefix}: breakdown={breakdown_total} core={core.get('congress_amt')!r}",
            )
        for index, row in enumerate(breakdown):
            if not isinstance(row, dict):
                issues.add("invalid_budget_breakdown_row", f"{prefix}.budget_breakdown[{index}]")
                continue
            if row.get("source") != "openfiscal_ExpenditureBudgetAdd2":
                issues.add("invalid_budget_source", f"{prefix}.budget_breakdown[{index}]")
            if row.get("amount_field") != "Y_YY_DFN_KCUR_AMT":
                issues.add("invalid_budget_amount_field", f"{prefix}.budget_breakdown[{index}]")

        local_rows = workflow.get("local_reflections")
        if not isinstance(local_rows, list):
            issues.add("invalid_local_reflections", prefix)
            local_rows = []
        expected_local_nodes = min(len(local_rows), 12)
        if len(local_node_ids) != expected_local_nodes:
            issues.add(
                "lofin_node_count_mismatch",
                f"{prefix}: nodes={len(local_node_ids)} expected={expected_local_nodes} rows={len(local_rows)}",
            )
        canonical_key = workflow.get("canonical_key")
        if not isinstance(canonical_key, list):
            issues.add("invalid_canonical_key", prefix)
            canonical_key = []
        for index, row in enumerate(local_rows):
            local_path = f"{prefix}.local_reflections[{index}]"
            if not isinstance(row, dict):
                issues.add("invalid_lofin_row", local_path)
                continue
            validate_lofin_row(row, local_path, canonical_key, issues, require_additive=True)
            workflow_lofin[lofin_identity(row)] += 1

    actual_counts = {
        "workflow_count": len(workflows),
        "node_count": sum(len(row.get("nodes") or []) for row in workflows),
        "edge_count": sum(len(row.get("edges") or []) for row in workflows),
        "evidence_section_count": sum(
            len(row.get("evidence_sections") or []) for row in workflows
        ),
        "lofin_candidate_row_count": sum(
            len(row.get("local_reflections") or []) for row in workflows
        ),
        "pdf_context_business_count": sum(
            1 for row in workflows if (row.get("coverage") or {}).get("level") != "api_only"
        ),
        "explicit_procedure_business_count": coverage_counts["documented_flow"],
        "api_only_business_count": coverage_counts["api_only"],
    }

    meta = envelope.get("meta") if isinstance(envelope.get("meta"), dict) else {}
    if not meta:
        issues.add("missing_workflow_meta", "workflow envelope")
    if meta != summary:
        issues.add("summary_meta_mismatch", "artifact summary differs from workflow meta")
    for key, actual in actual_counts.items():
        if meta.get(key) != actual:
            issues.add("summary_count_mismatch", f"{key}: expected={actual} actual={meta.get(key)!r}")
    if meta.get("coverage_counts") != dict(coverage_counts):
        issues.add(
            "summary_coverage_mismatch",
            f"expected={dict(coverage_counts)} actual={meta.get('coverage_counts')!r}",
        )
    if meta.get("year") != 2026:
        issues.add("invalid_workflow_year", f"meta.year={meta.get('year')!r}")
    if meta.get("phase_model") != "G0-G6 presentation taxonomy; not a source assertion":
        issues.add("invalid_phase_model_notice", f"meta.phase_model={meta.get('phase_model')!r}")
    if meta.get("default_business_id") not in set(workflow_ids):
        issues.add("invalid_default_business", str(meta.get("default_business_id")))

    industry = [
        row for row in workflows
        if isinstance(row.get("core"), dict) and row["core"].get("office_name") == "산업통상부"
    ]
    if len(industry) != EXPECTED_INDUSTRY_COUNT:
        issues.add("industry_count_mismatch", f"expected=472 actual={len(industry)}")
    industry_non_api = [
        row for row in industry if (row.get("coverage") or {}).get("level") != "api_only"
    ]
    if industry_non_api:
        issues.add("industry_not_api_only", f"count={len(industry_non_api)}")

    source_lofin: collections.Counter[tuple[Any, ...]] = collections.Counter()
    for index, row in enumerate(lofin_source):
        path = f"lofin_source[{index}]"
        if not isinstance(row, dict):
            issues.add("invalid_lofin_source_row", path)
            continue
        canonical_key = row.get("central_business_key")
        validate_lofin_row(
            row,
            path,
            canonical_key if isinstance(canonical_key, list) else [],
            issues,
            require_additive=False,
        )
        source_lofin[lofin_identity(row)] += 1
    if source_lofin != workflow_lofin:
        missing = sum((source_lofin - workflow_lofin).values())
        extra = sum((workflow_lofin - source_lofin).values())
        issues.add("lofin_source_mismatch", f"missing={missing} extra={extra}")

    validate_fixtures(workflows, issues)
    return {
        **actual_counts,
        "documented_flow": coverage_counts["documented_flow"],
        "structured_facts": coverage_counts["structured_facts"],
        "api_only": coverage_counts["api_only"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify the normalized workflow graph and standalone workflow HTML outputs."
    )
    parser.add_argument("--canonical", type=path_arg, default=DEFAULT_CANONICAL)
    parser.add_argument("--workflows", type=path_arg, default=DEFAULT_WORKFLOWS)
    parser.add_argument("--summary", type=path_arg, default=DEFAULT_SUMMARY)
    parser.add_argument("--lofin", type=path_arg, default=DEFAULT_LOFIN)
    parser.add_argument("--html", type=path_arg, default=DEFAULT_HTML)
    parser.add_argument("--html-year", type=path_arg, default=DEFAULT_HTML_YEAR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    issues = Issues()
    canonical = load_json(args.canonical, issues, "canonical")
    envelope = load_json(args.workflows, issues, "workflows")
    summary = load_json(args.summary, issues, "summary")
    lofin_source = load_json(args.lofin, issues, "LOFIN")
    catalogs = load_chunk_catalogs(issues)

    stats: dict[str, int] = {}
    if isinstance(canonical, dict) and isinstance(envelope, dict) and isinstance(summary, dict):
        if not isinstance(lofin_source, list):
            issues.add("invalid_lofin_schema", "LOFIN source must be a list")
            lofin_source = []
        stats = validate_all(canonical, envelope, summary, lofin_source, catalogs, issues)
        for path in (args.html, args.html_year):
            html_text = read_text(path, issues, "workflow HTML")
            if html_text is not None:
                validate_html(html_text, envelope, path, issues)

    if issues.total:
        issues.report()
        return 1

    print(
        "WORKFLOW_VERIFY_OK "
        f"workflows={stats['workflow_count']} "
        f"documented={stats['documented_flow']} "
        f"structured={stats['structured_facts']} "
        f"api_only={stats['api_only']} "
        f"nodes={stats['node_count']} "
        f"edges={stats['edge_count']} "
        f"evidence_sections={stats['evidence_section_count']} "
        f"lofin_candidates={stats['lofin_candidate_row_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
