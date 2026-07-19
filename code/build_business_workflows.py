#!/usr/bin/env python3
"""Build evidence-backed workflow maps for every canonical detail business.

The two APIs and ministry explainers have different authority:

* Open Fiscal Add2 is authoritative for hierarchy, amounts, and budget lines.
* Ministry PDFs may explicitly document actors, steps, timing, and outcomes.
* LOFIN rows are keyword candidates, never confirmed central-to-local transfers.

The G0-G6 phases in this output are a presentation taxonomy.  They make unlike
businesses readable on the same swimlane canvas, but do not create procedures
that are absent from the sources.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import tempfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
NORM = ROOT / "data" / "normalized"
ART = ROOT / "artifacts"
KORDOC = ROOT / "data" / "raw" / "kordoc"

DEFAULT_CANONICAL = NORM / "canonical_business_2026_pilots.json"
DEFAULT_LINES = NORM / "expbudgetadd2_2026_pilots_lines.json"
DEFAULT_RECONCILE = NORM / "reconcile_pdf_api_full.json"
DEFAULT_LOFIN = NORM / "lofin_local_transfer_candidates_2026.json"
DEFAULT_OUT = NORM / "business_workflows_2026_pilots.json"
DEFAULT_SUMMARY = ART / "business_workflows_2026_pilots_summary.json"

PHASES = [
    {"id": "G0", "label": "근거·목적", "order": 0},
    {"id": "G1", "label": "예산 확정·구성", "order": 1},
    {"id": "G2", "label": "시행 구조", "order": 2},
    {"id": "G3", "label": "신청·선정·협약", "order": 3},
    {"id": "G4", "label": "집행·사업수행", "order": 4},
    {"id": "G5", "label": "지방재정 반영", "order": 5},
    {"id": "G6", "label": "성과·정산·환류", "order": 6},
]

CHUNK_FILES = {
    "mois/mois_2026_budget_explainer.pdf": (
        KORDOC
        / "mois"
        / "mois_2026_budget_explainer"
        / "mois_2026_budget_explainer.chunks.json"
    ),
    "molit/molit_2026_budget.pdf": (
        KORDOC / "molit" / "molit_2026_budget" / "molit_2026_budget.chunks.json"
    ),
    "molit/molit_2026_fund.pdf": (
        KORDOC / "molit" / "molit_2026_fund" / "molit_2026_fund.chunks.json"
    ),
    "molit/molit_2026_rnd_info.pdf": (
        KORDOC
        / "molit"
        / "molit_2026_rnd_info"
        / "molit_2026_rnd_info.chunks.json"
    ),
}

SECTION_SPECS = [
    (
        "purpose",
        "사업 목적·내용",
        r"(?:^|\s)(?:1\)\s*)?사업\s*목적[·ㆍ\s]*내용|사업\s*목적",
        [r"(?:^|\s)2\)\s*사업\s*개요", r"사업\s*근거\s*및\s*추진경위"],
        1500,
    ),
    (
        "legal_history",
        "법적 근거·추진 경위",
        r"사업\s*근거\s*및\s*추진경위|법령상\s*근거",
        [r"주요\s*내용", r"(?:^|\s)3\)\s*20?26.*산출\s*근거"],
        2400,
    ),
    (
        "implementation",
        "시행 구조·수혜자",
        r"사업\s*추진\s*체계|사업시행방법|사업\s*시행\s*방법",
        [r"(?:^|\s)3\)\s*20?26.*산출\s*근거", r"(?:^|\s)4\)\s*사업\s*효과"],
        1800,
    ),
    (
        "budget_basis",
        "예산 산출근거",
        r"(?:3\)\s*)?20?26년도\s*예산\s*산출\s*근거|산출\s*세부내역\s*비교",
        [r"(?:^|\s)4\)\s*사업\s*효과", r"사업\s*효과"],
        2200,
    ),
    (
        "effects",
        "사업 효과·성과지표",
        r"(?:4\)\s*)?사업\s*효과|성과\s*지표",
        [r"(?:^|\s)5\)\s*타당성", r"총사업비\s*대상사업", r"사업\s*집행\s*절차"],
        2400,
    ),
    (
        "procedure",
        "사업 집행절차",
        r"(?:7\)\s*)?사업\s*집행\s*절차|추진\s*절차|지원\s*절차|처리\s*절차",
        [
            r"(?:^|\s)8\)\s*중기재정",
            r"(?:^|\s)8\)\s*각종\s*평가",
            r"(?:^|\s)9\)\s*최근",
            r"각종\s*평가",
            r"최근\s*\d+년간.*외부지적",
            r"##\s*다\.",
        ],
        4200,
    ),
    (
        "review",
        "외부 지적·평가·결산",
        r"최근\s*\d+년간.*(?:외부지적|평가)|주요\s*외부지적사항|최근\s*\d+년간\s*결산",
        [r"부처\s*건의사항", r"##\s*다\.", r"###\s*사\s*업"],
        2200,
    ),
]

ARROW_RE = re.compile(r"\s*(?:→|⇒|➜|⇢|⇨|⟶|▶|=>|->)\s*")
NUMBERED_RE = re.compile(r"(?:^|\s)[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]\s*")
STEP_HINT_RE = re.compile(
    r"신청|수요조사|조사|계획|공고|접수|검토|심사|선정|협의|협약|계약|입찰|"
    r"배정|교부|지급|집행|시행|수행|추진|운영|구축|설계|발주|착공|준공|"
    r"승인|확정|납부|회수|교육|연수|개발|관리|유지|작성|제출|결재|처리|"
    r"점검|보고|평가|정산|완료|통보|등록|발간"
)
G3_RE = re.compile(r"신청|수요조사|계획|공고|접수|검토|심사|선정|협의|협약|계약|입찰|배정|교부")
G6_RE = re.compile(r"점검|성과|평가|정산|결산|완료|최종|보고서|결과|환류|지적|시정")
ACTOR_ORG_RE = re.compile(
    r"부|청|원|공사|공단|연구원|진흥원|재단|센터|위원회|지자체|지방자치단체|"
    r"부서|과|실|국|팀|기관|협회|대학|기업|수혜자|국민"
)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"missing input: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON {path}: {exc}") from exc


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "\x1f".join(str(part or "") for part in parts).encode("utf-8")
    return f"{prefix}-" + hashlib.sha256(raw).hexdigest()[:14]


def norm(value: Any) -> str:
    return re.sub(
        r"\s+",
        " ",
        unicodedata.normalize("NFKC", html.unescape(str(value or ""))),
    ).strip()


def key_tuple(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        str(row.get("year") or ""),
        str(row.get("office_name") or ""),
        str(row.get("account_name") or ""),
        str(row.get("program_name") or ""),
        str(row.get("unit_business_name") or ""),
        str(row.get("detail_business_name") or ""),
    )


def raw_to_plain(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw or "", flags=re.IGNORECASE)
    text = re.sub(r"</(?:td|th)>", "\t", text, flags=re.IGNORECASE)
    text = re.sub(r"</(?:tr|table|p|div|li|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = text.replace("\\~", "~")
    lines = []
    for line in text.splitlines():
        cleaned = re.sub(r"[ \t]+", " ", line).strip(" |\t")
        cleaned = re.sub(r"!\[image\]\([^)]*\)", "", cleaned).strip()
        if cleaned and not re.fullmatch(r"[-:| ]+", cleaned):
            lines.append(cleaned)
    return "\n".join(lines)


def clean_excerpt(value: str, limit: int) -> str:
    lines = []
    for line in raw_to_plain(value).splitlines():
        line = re.sub(r"^#{1,6}\s*", "", line).strip(" -·□○ㅇ")
        if line and line not in lines:
            lines.append(line)
    text = "\n".join(lines)
    return text[:limit].rstrip()


def usable_text(value: str) -> bool:
    compact = re.sub(r"[^0-9A-Za-z가-힣]", "", value)
    if len(compact) < 8:
        return False
    without_heading = re.sub(
        r"(?:사업집행절차|추진절차|지원절차|처리절차|해당없음|해당사항없음)",
        "",
        compact,
    )
    return len(without_heading) >= 6


class ChunkStore:
    def __init__(self) -> None:
        self.chunks: dict[str, list[dict[str, Any]]] = {}
        self.indices: dict[str, dict[str, int]] = {}
        for source, path in CHUNK_FILES.items():
            data = load_json(path)
            if not isinstance(data, list):
                raise SystemExit(f"expected chunk list: {path}")
            rows = [row for row in data if isinstance(row, dict)]
            self.chunks[source] = rows
            self.indices[source] = {
                str(row.get("id")): index
                for index, row in enumerate(rows)
                if row.get("id") is not None
            }

    def block(self, pdf: dict[str, Any]) -> list[dict[str, Any]]:
        source = str(pdf.get("source_pdf") or "")
        rows = self.chunks.get(source)
        index = self.indices.get(source)
        if rows is None or index is None:
            return []
        start = index.get(str(pdf.get("source_chunk_start") or ""))
        end = index.get(str(pdf.get("source_chunk_end") or ""))
        if start is None or end is None or start > end:
            return []
        return rows[start : end + 1]


def section_from_block(
    block: list[dict[str, Any]],
    section_id: str,
    label: str,
    start_pattern: str,
    stop_patterns: list[str],
    limit: int,
    pdf: dict[str, Any],
) -> dict[str, Any] | None:
    start = None
    # A narrative subsection may mention "추진절차" before the numbered
    # execution-procedure section.  Prefer the structural heading when it is
    # present so unrelated tables do not become workflow steps.
    if section_id == "procedure":
        for index, chunk in enumerate(block):
            candidate = raw_to_plain(str(chunk.get("text") or ""))
            if re.search(r"사업\s*집행\s*절차", candidate, re.IGNORECASE):
                start = index
                break
    for index, chunk in enumerate(block):
        if start is not None:
            break
        if re.search(start_pattern, raw_to_plain(str(chunk.get("text") or "")), re.IGNORECASE):
            start = index
            break
    if start is None:
        return None
    end = len(block)
    for index in range(start + 1, len(block)):
        chunk = block[index]
        candidate = raw_to_plain(str(chunk.get("text") or ""))
        if any(re.search(pattern, candidate, re.IGNORECASE) for pattern in stop_patterns):
            end = index
            break
    selected = block[start:end]
    raw = "\n".join(str(chunk.get("text") or "") for chunk in selected)
    text = clean_excerpt(raw, limit)
    if section_id == "procedure" and re.search(
        r"사업\s*집행\s*절차\s*[:：]?\s*해당\s*(?:사항)?\s*없음",
        text[:180],
        re.IGNORECASE,
    ):
        return None
    if not usable_text(text):
        return None
    pages = [chunk.get("page") for chunk in selected if isinstance(chunk.get("page"), int)]
    return {
        "id": stable_id(
            "ev",
            pdf.get("source_pdf"),
            pdf.get("source_chunk_start"),
            section_id,
        ),
        "section": section_id,
        "label": label,
        "text": text,
        "source_type": "ministry_pdf",
        "source_pdf": pdf.get("source_pdf"),
        "page_start": min(pages) if pages else pdf.get("page_start"),
        "page_end": max(pages) if pages else pdf.get("page_end"),
        "chunk_start": selected[0].get("id") if selected else pdf.get("source_chunk_start"),
        "chunk_end": selected[-1].get("id") if selected else pdf.get("source_chunk_end"),
        "match": {
            "confidence": pdf.get("confidence"),
            "score": pdf.get("score"),
            "method": pdf.get("method"),
        },
        # Kept only while extracting explicit steps.  It is removed before the
        # normalized evidence section is published.
        "_raw": raw,
    }


def extract_sections(block: list[dict[str, Any]], pdf: dict[str, Any]) -> list[dict[str, Any]]:
    sections = []
    seen = set()
    for spec in SECTION_SPECS:
        section = section_from_block(block, *spec, pdf)
        if section is None:
            continue
        key = (section["section"], section["text"][:120])
        if key not in seen:
            seen.add(key)
            sections.append(section)
    return sections


def valid_actor(value: Any) -> str | None:
    text = norm(value).strip(" :-·|,;")
    if not 2 <= len(text) <= 120:
        return None
    compact = re.sub(r"\s+", "", text)
    if re.search(r"\d{3,}|백만원|202[0-9]년결산|colspan|rowspan", text, re.IGNORECASE):
        return None
    if compact in {
        "사업명", "구분", "기관명", "소관부처", "실·국·과(팀)", "실국과", "사업시행주체",
        "직접수행", "해당없음", "해당사항없음", "절차내용",
    }:
        return None
    return text


def extract_labeled_value(text: str, labels: list[str], limit: int = 180) -> str | None:
    for label in labels:
        match = re.search(
            rf"{label}\s*[:：]\s*([^\n]+)",
            text,
            re.IGNORECASE,
        )
        if match:
            value = norm(match.group(1)).strip(" -·|,;")
            if value and "해당없음" not in re.sub(r"\s+", "", value):
                return value[:limit]
    return None


def actor_id(business_id: str, role: str, name: str) -> str:
    return stable_id("a", business_id, role, name)


def node_id(business_id: str, kind: str, label: str, ordinal: int) -> str:
    return stable_id("p", business_id, kind, label, ordinal)


def source_ref_for_section(section: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_type": section.get("source_type"),
        "source_pdf": section.get("source_pdf"),
        "page_start": section.get("page_start"),
        "page_end": section.get("page_end"),
        "chunk_start": section.get("chunk_start"),
        "chunk_end": section.get("chunk_end"),
        "evidence_id": section.get("id"),
    }


def source_ref_for_pdf_card(pdf: dict[str, Any], field: str) -> dict[str, Any]:
    """Point to a structured PDF-card field when no extracted section exists."""

    return {
        "source_type": "ministry_pdf",
        "source_pdf": pdf.get("source_pdf"),
        "page_start": pdf.get("page_start"),
        "page_end": pdf.get("page_end"),
        "chunk_start": pdf.get("source_chunk_start"),
        "chunk_end": pdf.get("source_chunk_end"),
        "field": field,
    }


def clean_step(value: str) -> str | None:
    text = raw_to_plain(value)
    text = re.sub(r"^#{1,6}\s*", "", text)
    text = re.sub(
        r"^(?:\(?\d{1,2}\)?|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳])\s*[.)]?\s*",
        "",
        text,
    )
    text = re.sub(r"^(?:사업\s*집행\s*절차|추진\s*절차)\s*[:：-]?\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -·□○ㅇ:;|>")
    if not 2 <= len(text) <= 220:
        return None
    if re.fullmatch(r"해당\s*(?:사항)?\s*없음", text):
        return None
    if re.fullmatch(r"\([^)]*(?:협의|중심)\)", text):
        return None
    compact = re.sub(r"[^0-9A-Za-z가-힣]", "", text)
    if compact in {
        "추진절차", "시행주체", "절차내용", "추진절차시행주체절차내용",
        "부처", "피출연피보조기관", "간접보조사업자", "사업수행자",
        "수행기관", "주관연구개발기관", "전담기관",
        "중기재정계획", "각종평가", "대외공개평가해당없음", "자체평가해당없음",
    }:
        return None
    if re.fullmatch(r"[\d,().백만원원%\s]+", text):
        return None
    # Workflow nodes are actions, not actor names or table headers.  Actor-only
    # arrows remain visible in the evidence section instead of being promoted
    # into an asserted procedure.
    if not STEP_HINT_RE.search(text):
        return None
    return text


def html_table_steps(raw: str) -> list[str]:
    steps = []
    for table_match in re.finditer(
        r"<table[^>]*>(.*?)</table>", raw, re.IGNORECASE | re.DOTALL
    ):
        table = table_match.group(1)
        table_plain = raw_to_plain(table)
        if not re.search(
            r"추진\s*계획|세부\s*일정|추진\s*절차|절차\s*내용|시행\s*주체",
            table_plain,
        ):
            continue
        for row_match in re.finditer(
            r"<tr[^>]*>(.*?)</tr>", table, re.IGNORECASE | re.DOTALL
        ):
            row = row_match.group(1)
            cells = []
            for cell_match in re.finditer(
                r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.IGNORECASE | re.DOTALL
            ):
                cell = clean_excerpt(cell_match.group(1), 900)
                if cell:
                    cells.append(cell)
            if not cells or any(
                re.search(r"추진\s*계획|절차\s*내용|세부\s*일정", cell)
                for cell in cells
            ):
                continue
            action_cells = [cell for cell in cells if STEP_HINT_RE.search(cell)]
            for cell in action_cells[:2]:
                pieces = re.split(r"\n|\s*[•❍]\s*|\s+-\s+(?=[가-힣A-Za-z])", cell)
                for piece in pieces:
                    step = clean_step(piece)
                    if step and step not in steps:
                        steps.append(step)
    return steps


def markdown_table_steps(text: str) -> list[str]:
    steps = []
    groups: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if "|" in line:
            current.append(line)
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    for group in groups:
        if not re.search(
            r"추진\s*계획|세부\s*일정|추진\s*절차|절차\s*내용|시행\s*주체",
            " ".join(group),
        ):
            continue
        for line in group:
            if re.fullmatch(r"[| :\-]+", line.strip()):
                continue
            cells = [norm(cell) for cell in line.strip().strip("|").split("|")]
            if any(re.search(r"추진\s*계획|절차\s*내용|세부\s*일정", cell) for cell in cells):
                continue
            for cell in cells:
                if not STEP_HINT_RE.search(cell):
                    continue
                step = clean_step(cell)
                if step and step not in steps:
                    steps.append(step)
    return steps


def procedure_steps(section: dict[str, Any], raw_section: str = "") -> list[str]:
    text = section.get("text") or ""
    candidates: list[str] = []
    if ARROW_RE.search(text):
        # PDF line wrapping frequently splits one arrow-delimited step across
        # two chunks.  Join lines inside the already bounded procedure section
        # before splitting so the final action is not lost.
        arrow_blob = re.sub(r"\s*\n\s*", " ", text)
        for piece in ARROW_RE.split(arrow_blob):
            step = clean_step(piece)
            if step and step not in candidates:
                candidates.append(step)
    if len(candidates) < 2:
        parts = NUMBERED_RE.split(text)
        if len(parts) >= 3:
            for piece in parts[1:]:
                step = clean_step(piece)
                if step and step not in candidates:
                    candidates.append(step)
    for step in html_table_steps(raw_section):
        if step not in candidates:
            candidates.append(step)
    if len(candidates) < 2:
        for step in markdown_table_steps(raw_section):
            if step not in candidates:
                candidates.append(step)
    return candidates[:24] if len(candidates) >= 2 else []


def phase_for_step(label: str) -> str:
    if G6_RE.search(label):
        return "G6"
    if G3_RE.search(label):
        return "G3"
    return "G4"


def actor_for_step(
    label: str,
    ministry_actor: str,
    implementer_actor: str | None,
    beneficiary_actor: str | None,
    ministry_name: str,
    implementer_name: str | None,
    beneficiary_name: str | None,
) -> tuple[str, str]:
    compact = re.sub(r"\s+", "", label)
    if beneficiary_actor and re.search(r"수혜|국민|주민|대상자|신청자", compact):
        assertion = "documented" if beneficiary_name and re.sub(r"\s+", "", beneficiary_name) in compact else "derived"
        return beneficiary_actor, assertion
    if implementer_actor and implementer_name and re.sub(r"\s+", "", implementer_name) in compact:
        return implementer_actor, "documented"
    if (
        re.sub(r"\s+", "", ministry_name) in compact
        or re.search(r"부처|행안부|국토부|행정안전부|국토교통부", compact)
    ):
        return ministry_actor, "documented"
    return implementer_actor or ministry_actor, "derived"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", default=str(DEFAULT_CANONICAL))
    parser.add_argument("--lines", default=str(DEFAULT_LINES))
    parser.add_argument("--reconcile", default=str(DEFAULT_RECONCILE))
    parser.add_argument("--lofin", default=str(DEFAULT_LOFIN))
    parser.add_argument("--output", default=str(DEFAULT_OUT))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    args = parser.parse_args()

    canonical = load_json(Path(args.canonical))
    lines = load_json(Path(args.lines))
    reconcile = load_json(Path(args.reconcile))
    lofin = load_json(Path(args.lofin)) if Path(args.lofin).exists() else []
    if not isinstance(canonical, dict) or not isinstance(canonical.get("businesses"), list):
        raise SystemExit("canonical envelope has no businesses list")
    if not isinstance(lines, list) or not isinstance(reconcile, list) or not isinstance(lofin, list):
        raise SystemExit("lines, reconcile, and LOFIN inputs must be lists")

    chunk_store = ChunkStore()

    lines_by_key: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in lines:
        if isinstance(row, dict):
            lines_by_key[key_tuple(row)].append(row)

    pdfs_by_key: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in reconcile:
        if not isinstance(row, dict) or row.get("status") != "matched":
            continue
        match = row.get("api_match") or {}
        pdf = dict(row.get("pdf") or {})
        pdf.update(
            {
                "confidence": row.get("confidence"),
                "score": row.get("score"),
                "method": row.get("method"),
            }
        )
        pdfs_by_key[key_tuple(match)].append(pdf)

    lofin_by_key: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    identity_to_keys: dict[tuple[str, ...], set[tuple[str, ...]]] = defaultdict(set)
    for row in lofin:
        if not isinstance(row, dict):
            continue
        central = row.get("central_business_key")
        if not isinstance(central, list) or len(central) != 6:
            continue
        central_key = tuple(str(value or "") for value in central)
        try:
            if int(row.get("year")) != 2026 or float(row.get("national_amt") or 0) <= 0:
                continue
        except (TypeError, ValueError):
            continue
        lofin_by_key[central_key].append(row)
        identity = (
            str(row.get("exe_ymd") or ""),
            str(row.get("local_gov_code") or row.get("local_gov_name") or ""),
            str(row.get("detail_business_code") or row.get("detail_business_name") or ""),
            str(row.get("national_amt") or ""),
        )
        identity_to_keys[identity].add(central_key)

    workflows = []
    coverage_counts: Counter[str] = Counter()
    source_section_count = 0
    total_nodes = 0
    total_edges = 0
    total_lofin_rows = 0

    businesses = sorted(
        canonical["businesses"],
        key=lambda item: tuple(str(value or "") for value in item.get("canonical_key") or []),
    )
    for business in businesses:
        business_id = str(business.get("id") or "")
        core = dict(business.get("api_core") or {})
        central_key = tuple(str(value or "") for value in business.get("canonical_key") or [])
        if len(central_key) != 6:
            central_key = key_tuple(core)
        business_lines = lines_by_key.get(central_key, [])
        pdf_rows = pdfs_by_key.get(central_key, [])
        local_rows = lofin_by_key.get(central_key, [])

        breakdown_map: dict[tuple[str, str], dict[str, Any]] = {}
        for row in business_lines:
            budget_key = (str(row.get("mok_name") or "(목 미상)"), str(row.get("semok_name") or "(세목 미상)"))
            item = breakdown_map.setdefault(
                budget_key,
                {
                    "mok_name": budget_key[0],
                    "semok_name": budget_key[1],
                    "amount_won": 0.0,
                    "line_count": 0,
                    "source": "openfiscal_ExpenditureBudgetAdd2",
                    "amount_field": "Y_YY_DFN_KCUR_AMT",
                },
            )
            item["amount_won"] += float(row.get("congress_amt") or 0)
            item["line_count"] += 1
        total_amount = float(core.get("congress_amt") or 0)
        budget_breakdown = sorted(
            breakdown_map.values(),
            key=lambda item: (-item["amount_won"], item["mok_name"], item["semok_name"]),
        )
        for item in budget_breakdown:
            item["share"] = round(item["amount_won"] / total_amount, 8) if total_amount else 0.0

        evidence_sections: list[dict[str, Any]] = []
        raw_procedures: dict[str, str] = {}
        for pdf in sorted(
            pdf_rows,
            key=lambda item: (str(item.get("source_pdf") or ""), int(item.get("page_start") or 0)),
        ):
            block = chunk_store.block(pdf)
            sections = extract_sections(block, pdf)
            for section in sections:
                if section.get("section") == "procedure":
                    raw_procedures[section["id"]] = str(section.pop("_raw", ""))
                else:
                    section.pop("_raw", None)
            evidence_sections.extend(sections)
        evidence_sections.sort(
            key=lambda item: (str(item.get("source_pdf") or ""), int(item.get("page_start") or 0), item["section"])
        )

        by_section: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for section in evidence_sections:
            by_section[section["section"]].append(section)

        ministry_name = str(core.get("office_name") or "소관부처")
        ministry_actor = actor_id(business_id, "ministry", ministry_name)
        actors = [
            {
                "id": ministry_actor,
                "name": ministry_name,
                "role": "소관부처",
                "assertion": "api",
                "source_refs": [
                    {
                        "source_type": "openfiscal_api",
                        "service": "ExpenditureBudgetAdd2",
                        "year": core.get("year"),
                    }
                ],
            }
        ]

        implementation_text = "\n".join(item["text"] for item in by_section.get("implementation", []))
        implementer_name = None
        implementer_pdf = None
        for pdf in pdf_rows:
            implementer_name = valid_actor(pdf.get("implementer"))
            if implementer_name:
                implementer_pdf = pdf
                break
        if implementer_name is None:
            implementer_name = valid_actor(
                extract_labeled_value(implementation_text, [r"사업\s*시행\s*주체", r"시행\s*주체"])
            )
        implementer_actor = None
        if implementer_name and re.sub(r"\s+", "", implementer_name) != re.sub(r"\s+", "", ministry_name):
            implementer_actor = actor_id(business_id, "implementer", implementer_name)
            actors.append(
                {
                    "id": implementer_actor,
                    "name": implementer_name,
                    "role": "문서상 시행주체",
                    "assertion": "documented",
                    "source_refs": (
                        [source_ref_for_section(by_section["implementation"][0])]
                        if by_section.get("implementation")
                        else [source_ref_for_pdf_card(implementer_pdf, "implementer")]
                        if implementer_pdf
                        else []
                    ),
                }
            )

        beneficiary_name = valid_actor(
            extract_labeled_value(implementation_text, [r"사업\s*수혜자", r"수혜\s*대상", r"지원\s*대상"])
        )
        beneficiary_actor = None
        if beneficiary_name:
            beneficiary_actor = actor_id(business_id, "beneficiary", beneficiary_name)
            actors.append(
                {
                    "id": beneficiary_actor,
                    "name": beneficiary_name,
                    "role": "문서상 수혜자",
                    "assertion": "documented",
                    "source_refs": [source_ref_for_section(by_section["implementation"][0])]
                    if by_section.get("implementation")
                    else [],
                }
            )

        local_actor = None
        if local_rows:
            local_actor = actor_id(business_id, "local", "광역·기초 지방자치단체")
            actors.append(
                {
                    "id": local_actor,
                    "name": "광역·기초 지방자치단체",
                    "role": "LOFIN 지방사업 후보",
                    "assertion": "candidate",
                    "source_refs": [{"source_type": "lofin_api", "service": "QWGJK"}],
                }
            )

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        def add_node(
            phase: str,
            actor: str,
            kind: str,
            label: str,
            detail: str,
            assertion: str,
            refs: list[dict[str, Any]],
            amount_won: float | None = None,
            actor_assertion: str | None = None,
        ) -> str:
            identifier = node_id(business_id, kind, label, len(nodes))
            node = {
                "id": identifier,
                "display_id": f"P{len(nodes) + 1:02d}",
                "phase": phase,
                "actor": actor,
                "kind": kind,
                "label": norm(label)[:180],
                "detail": norm(detail)[:900],
                "assertion": assertion,
                "actor_assertion": actor_assertion or assertion,
                "source_refs": refs,
            }
            if amount_won is not None:
                node["amount_won"] = amount_won
            nodes.append(node)
            return identifier

        def add_edge(
            source: str,
            target: str,
            edge_type: str,
            assertion: str,
            refs: list[dict[str, Any]],
            label: str = "",
        ) -> None:
            edges.append(
                {
                    "id": stable_id("e", business_id, source, target, edge_type, len(edges)),
                    "from": source,
                    "to": target,
                    "type": edge_type,
                    "label": label,
                    "assertion": assertion,
                    "source_refs": refs,
                }
            )

        purpose_node = None
        if by_section.get("purpose"):
            section = by_section["purpose"][0]
            purpose_node = add_node(
                "G0", ministry_actor, "purpose", "사업 목적·내용", section["text"],
                "documented", [source_ref_for_section(section)]
            )
        if by_section.get("legal_history"):
            section = by_section["legal_history"][0]
            legal_node = add_node(
                "G0", ministry_actor, "basis", "법적 근거·추진 경위", section["text"],
                "documented", [source_ref_for_section(section)]
            )
            if purpose_node:
                add_edge(legal_node, purpose_node, "context", "derived", [], "근거·목적 분류")

        budget_node = add_node(
            "G1",
            ministry_actor,
            "budget",
            "2026년 국회확정액",
            "열린재정 ExpenditureBudgetAdd2의 목·세목 합계",
            "api",
            [
                {
                    "source_type": "openfiscal_api",
                    "service": "ExpenditureBudgetAdd2",
                    "field": "Y_YY_DFN_KCUR_AMT",
                    "year": core.get("year"),
                }
            ],
            total_amount,
        )
        for item in budget_breakdown[:8]:
            budget_item = add_node(
                "G1",
                ministry_actor,
                "budget_item",
                f"{item['mok_name']} · {item['semok_name']}",
                f"원자료 {item['line_count']}행 · 사업액 대비 {item['share'] * 100:.1f}%",
                "api",
                [
                    {
                        "source_type": "openfiscal_api",
                        "service": "ExpenditureBudgetAdd2",
                        "field": "Y_YY_DFN_KCUR_AMT",
                    }
                ],
                float(item["amount_won"]),
            )
            add_edge(
                budget_node,
                budget_item,
                "fund",
                "api",
                [
                    {
                        "source_type": "openfiscal_api",
                        "service": "ExpenditureBudgetAdd2",
                        "field": "Y_YY_DFN_KCUR_AMT",
                    }
                ],
                "목·세목 구성",
            )

        implementation_node = None
        if by_section.get("implementation"):
            section = by_section["implementation"][0]
            implementation_node = add_node(
                "G2",
                implementer_actor or ministry_actor,
                "implementation",
                "시행방법·시행주체",
                section["text"],
                "documented",
                [source_ref_for_section(section)],
            )
        if beneficiary_actor and beneficiary_name:
            refs = [source_ref_for_section(by_section["implementation"][0])] if by_section.get("implementation") else []
            beneficiary_node = add_node(
                "G2", beneficiary_actor, "beneficiary", "사업 수혜자", beneficiary_name,
                "documented", refs
            )
            if implementation_node:
                add_edge(implementation_node, beneficiary_node, "delivery", "documented", refs, "문서상 수혜 관계")

        explicit_sequences: list[list[str]] = []
        for section in by_section.get("procedure", []):
            steps = procedure_steps(section, raw_procedures.get(section["id"], ""))
            if steps:
                explicit_sequences.append(steps)
                refs = [source_ref_for_section(section)]
                sequence_nodes = []
                for step in steps:
                    phase = phase_for_step(step)
                    actor, actor_assertion = actor_for_step(
                        step,
                        ministry_actor,
                        implementer_actor,
                        beneficiary_actor,
                        ministry_name,
                        implementer_name,
                        beneficiary_name,
                    )
                    sequence_nodes.append(
                        add_node(
                            phase,
                            actor,
                            "procedure",
                            step,
                            step,
                            "documented",
                            refs,
                            actor_assertion=actor_assertion,
                        )
                    )
                for source, target in zip(sequence_nodes, sequence_nodes[1:]):
                    add_edge(source, target, "sequence", "documented", refs, "문서 명시 순서")

        local_reflections = []
        local_nodes = []
        for row in sorted(
            local_rows,
            key=lambda item: (-float(item.get("national_amt") or 0), str(item.get("local_gov_name") or "")),
        ):
            identity = (
                str(row.get("exe_ymd") or ""),
                str(row.get("local_gov_code") or row.get("local_gov_name") or ""),
                str(row.get("detail_business_code") or row.get("detail_business_name") or ""),
                str(row.get("national_amt") or ""),
            )
            local_reflections.append(
                {
                    "source": "lofin_QWGJK",
                    "match_status": "keyword_candidate",
                    "central_business_key": list(central_key),
                    "keyword": row.get("keyword"),
                    "keyword_strategy": row.get("keyword_strategy"),
                    "year": int(row.get("year")),
                    "exe_ymd": row.get("exe_ymd"),
                    "local_gov_code": row.get("local_gov_code"),
                    "local_gov_name": row.get("local_gov_name"),
                    "local_level": row.get("local_level"),
                    "account_name": row.get("account_name"),
                    "field_name": row.get("field_name"),
                    "section_name": row.get("section_name"),
                    "detail_business_name": row.get("detail_business_name"),
                    "detail_business_code": row.get("detail_business_code"),
                    "budget_cash_amt": row.get("budget_cash_amt"),
                    "national_amt": row.get("national_amt"),
                    "sido_amt": row.get("sido_amt"),
                    "sigungu_amt": row.get("sigungu_amt"),
                    "spend_amt": row.get("spend_amt"),
                    "compile_amt": row.get("compile_amt"),
                    "shared_keyword_duplicate": len(identity_to_keys[identity]) > 1,
                    "additive": False,
                }
            )
        if local_actor:
            for item in local_reflections[:12]:
                local_node = add_node(
                    "G5",
                    local_actor,
                    "local_candidate",
                    f"{item.get('local_gov_name') or '지자체'} · {item.get('detail_business_name') or '지방사업'}",
                    (
                        f"{item.get('local_level') or '단계 미상'} · 기준일 {item.get('exe_ymd') or '-'} · "
                        "중앙사업과의 관계는 keyword_candidate"
                    ),
                    "candidate",
                    [
                        {
                            "source_type": "lofin_api",
                            "service": "QWGJK",
                            "exe_ymd": item.get("exe_ymd"),
                            "match_status": "keyword_candidate",
                        }
                    ],
                    float(item.get("national_amt") or 0),
                )
                local_nodes.append(local_node)
                add_edge(
                    budget_node,
                    local_node,
                    "candidate",
                    "candidate",
                    [
                        {
                            "source_type": "lofin_api",
                            "service": "QWGJK",
                            "match_status": "keyword_candidate",
                            "exe_ymd": item.get("exe_ymd"),
                        }
                    ],
                    "LOFIN 키워드 후보·합산 불가",
                )

        for section_key, label, kind in [
            ("effects", "사업 효과·성과지표", "performance"),
            ("review", "외부 지적·평가·결산", "review"),
        ]:
            if by_section.get(section_key):
                section = by_section[section_key][0]
                add_node(
                    "G6",
                    ministry_actor,
                    kind,
                    label,
                    section["text"],
                    "documented",
                    [source_ref_for_section(section)],
                )

        if explicit_sequences:
            coverage = "documented_flow"
        elif pdf_rows:
            coverage = "structured_facts"
        else:
            coverage = "api_only"
        coverage_counts[coverage] += 1

        warning_list = []
        if coverage == "api_only":
            warning_list.append("PDF 확정 매칭이 없어 실제 업무 순서를 생성하지 않음")
        elif coverage == "structured_facts":
            warning_list.append("PDF 문맥은 있으나 명시적 다단계 순서가 부족해 절차 연결을 생성하지 않음")
        if any(channel.get("code") == "direct" for channel in business.get("execution_channels") or []):
            warning_list.append("direct 집행채널은 목·세목 규칙의 잔여 분류이며 실제 직접수행의 증거가 아님")
        if local_rows:
            warning_list.append("LOFIN은 keyword_candidate이며 광역·기초 금액은 비가산적")

        workflow = {
            "id": business_id,
            "canonical_key": list(central_key),
            "title": core.get("detail_business_name"),
            "core": core,
            "coverage": {
                "level": coverage,
                "pdf_card_count": len(pdf_rows),
                "explicit_procedure": bool(explicit_sequences),
                "explicit_sequence_count": len(explicit_sequences),
                "phase_model": "presentation_derived",
                "warnings": warning_list,
            },
            "actors": actors,
            "phases": PHASES,
            "nodes": nodes,
            "edges": edges,
            "execution_channels": business.get("execution_channels") or [],
            "budget_breakdown": budget_breakdown,
            "local_summary": business.get("local_summary"),
            "local_reflections": local_reflections,
            "evidence_sections": evidence_sections,
            "pdf_cards": [
                {
                    key: pdf.get(key)
                    for key in (
                        "clean_title", "raw_title", "code_hint", "code_type", "implementer",
                        "exec_paths", "source_pdf", "page_start", "page_end", "anchor_chunk_id",
                        "source_chunk_start", "source_chunk_end", "confidence", "score", "method",
                    )
                }
                for pdf in pdf_rows
            ],
        }
        workflows.append(workflow)
        source_section_count += len(evidence_sections)
        total_nodes += len(nodes)
        total_edges += len(edges)
        total_lofin_rows += len(local_reflections)

    default_business_id = next(
        (
            item["id"]
            for item in workflows
            if re.sub(r"\s+", "", str(item.get("title") or ""))
            == "한국지방행정연구원정책개발연구등지원"
        ),
        workflows[0]["id"] if workflows else None,
    )
    summary = {
        "year": 2026,
        "scope": "three-ministry pilot",
        "workflow_count": len(workflows),
        "coverage_counts": dict(coverage_counts),
        "pdf_context_business_count": sum(
            item["coverage"]["level"] != "api_only" for item in workflows
        ),
        "explicit_procedure_business_count": coverage_counts["documented_flow"],
        "api_only_business_count": coverage_counts["api_only"],
        "node_count": total_nodes,
        "edge_count": total_edges,
        "evidence_section_count": source_section_count,
        "lofin_candidate_row_count": total_lofin_rows,
        "phase_model": "G0-G6 presentation taxonomy; not a source assertion",
        "default_business_id": default_business_id,
        "sources": {
            "openfiscal": "ExpenditureBudgetAdd2",
            "pdf": "matched ministry budget explainer Kordoc chunks",
            "lofin": "QWGJK keyword_candidate",
        },
    }
    envelope = {"schema_version": "1.0", "meta": summary, "workflows": workflows}
    write_json_atomic(Path(args.output), envelope)
    write_json_atomic(Path(args.summary), summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("wrote", args.output)
    print("wrote", args.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
