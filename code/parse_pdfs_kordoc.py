#!/usr/bin/env python3
"""Build business cards from kordoc chunks/markdown (primary)."""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDF_ROOT = ROOT / "data" / "raw" / "pdfs"
KORDOC_ROOT = ROOT / "data" / "raw" / "kordoc"
TEXT_ROOT = ROOT / "data" / "raw" / "pdf_text"
OUT = ROOT / "data" / "normalized"
ART = ROOT / "artifacts"
KORDOC_VERSION = "4.2.1"

EXEC_PATTERNS = [
    (r"직접\s*수행|직접\s*집행|직접\s*시행|직접사업", "직접"),
    (r"위탁|민간위탁|공공기관\s*위탁|출연", "위탁/출연"),
    (r"자치단체\s*보조|민간\s*보조|보조금|보조", "보조"),
    (r"융자|이차보전", "융자"),
    (r"출자", "출자"),
    (r"기금\s*운용|기금", "기금"),
]

BIZ_ANCHOR = re.compile(
    r"(사\s*업\s*명\s*[\(（]?\s*\d*\s*[\)）]?|"
    r"[\(（]\s*\d{1,3}\s*[\)）]\s*[가-힣A-Za-z].{0,80}?"
    r"[\(（]\s*\d{3,6}\s*[-–]\s*\d{2,6}\s*[\)）])"
)
CODE_RE = re.compile(r"[\(（]\s*(\d{3,6}\s*[-–]\s*\d{2,6})\s*[\)）]")
BUSINESS_HEADING_RE = re.compile(
    r"^\s*#{1,6}\s*[\(（]\s*(?P<ordinal>\d{1,4})\s*[\)）]\s*"
    r"(?P<title>.+?)\s*[\(（]\s*"
    r"(?P<code>\d{3,6}\s*[-–]\s*\d{2,6}"
    r"(?:\s*(?:\\?~|～|,)\s*\d{2,6})*)\s*[\)）]\s*$"
)
NOISE_TITLE = re.compile(
    r"(목차|페이지|백만원|억원|결산|해당없음|작성유의사항|법적근거|기능별|예산액|집행률|구분|코드|명칭)"
)
BANNED_TITLES = {
    "사업명",
    "사업개요",
    "산출근거",
    "추진체계",
    "구분",
    "코드",
    "명칭",
}
COMMON_PLACEHOLDER_RE = re.compile(
    r"^(?:-|없음|미정|미상|n/?a|해당\s*(?:사항)?\s*없음|추후\s*(?:결정|확정))"
    r"(?:\s*[\(（][^\)）]*[\)）])?$",
    re.IGNORECASE,
)
PERIOD_PLACEHOLDER_RE = re.compile(
    r"^(?:0{2,4}|x{2,4}|y{2,4})(?:년)?\s*[-~～]\s*"
    r"(?:0{2,4}|x{2,4}|y{2,4})(?:년)?$",
    re.IGNORECASE,
)
FIELD_PLACEHOLDER_RE = re.compile(
    r"^(?:기관명|구분|명칭|사업|사업명|절차내용|시행방법|사업시행방법|"
    r"20\d{2}년\s*결산)$"
)
IMPLEMENTER_PLACEHOLDER_RE = re.compile(
    r"^(?:직접\s*수행(?:\s*[\(（][^\)）]*[\)）])?|"
    r"지자체\s*보조(?:\s*[,，].*)?)$"
)


def chunks_to_text(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    parts = []
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                parts.append(str(item))
                continue
            bc = item.get("breadcrumb")
            if isinstance(bc, list) and bc:
                parts.append(" > ".join(map(str, bc)))
            for key in ("text", "content", "markdown", "heading", "title"):
                val = item.get(key)
                if val:
                    parts.append(str(val))
    elif isinstance(data, dict):
        parts.append(json.dumps(data, ensure_ascii=False))
    return "\n".join(parts)


def html_to_plain(raw: str) -> str:
    """Convert kordoc HTML/table fragments to field-friendly plain text."""
    text = re.sub(r"<br\s*/?>", "\n", raw or "", flags=re.IGNORECASE)
    text = re.sub(
        r"</(?:td|th|tr|table|p|div|li|h[1-6])>",
        "\n",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = []
    for line in text.splitlines():
        cleaned = re.sub(r"[ \t]+", " ", line).strip(" |")
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def load_chunks(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def normalize_text_value(raw: str) -> str:
    """Decode HTML entities and normalize Unicode/whitespace for stable fields."""
    value = re.sub(
        r"\s+",
        " ",
        unicodedata.normalize("NFC", html.unescape(raw or "")),
    ).strip()
    # Kordoc escapes a literal tilde in some headings (for example railway
    # sections).  API names use a normal hyphen, so normalize all range glyphs
    # at the structural boundary.
    return value.replace("\\~", "-").replace("～", "-").replace("~", "-")


def anchored_title(raw: str) -> str | None:
    """Validate a coded heading title without broad substring noise rules."""
    decoded = html.unescape(raw or "")
    title = normalize_text_value(re.sub(r"<[^>]+>", " ", decoded)).strip(" :-·.|")
    if len(title) < 2 or len(title) > 120:
        return None
    if title in BANNED_TITLES or "|" in title or "</" in title:
        return None
    return title


def collect_business_anchors(
    chunks: list[dict],
) -> list[tuple[int, int, re.Match[str]]]:
    """Find direct and two-chunk coded headings on the same page."""
    anchors = []
    idx = 0
    while idx < len(chunks):
        item = chunks[idx]
        if item.get("type") != "heading":
            idx += 1
            continue
        text = str(item.get("text") or "")
        match = BUSINESS_HEADING_RE.match(text)
        if match is not None:
            anchors.append((idx, 1, match))
            idx += 1
            continue
        if idx + 1 < len(chunks):
            nxt = chunks[idx + 1]
            if nxt.get("type") == "heading" and nxt.get("page") == item.get("page"):
                left = re.sub(r"^\s*#{1,6}\s*", "", text).strip()
                right = re.sub(r"^\s*#{1,6}\s*", "", str(nxt.get("text") or "")).strip()
                combined = "### " + left + " " + right
                match = BUSINESS_HEADING_RE.match(combined)
                if match is not None:
                    anchors.append((idx, 2, match))
                    idx += 2
                    continue
        idx += 1
    return anchors


def cards_from_chunks(
    path: Path,
    ministry: str,
    source_pdf: str,
) -> tuple[list[dict], int]:
    """Build exactly one card per coded business heading.

    Kordoc marks real business boundaries as headings such as
    ``(9) 과표양성화를 위한 시가표준액 조사 (1337-300)``.  Tables inside
    the business repeat ``사업명`` many times, so text-level splitting creates
    duplicate/noise cards.  Heading anchors avoid that failure mode.
    """
    chunks = load_chunks(path)
    anchors = collect_business_anchors(chunks)

    def chunk_reference(item: dict, index: int) -> str:
        return str(item.get("id") or item.get("chunk_id") or f"index:{index}")

    cards = []
    for pos, (start, anchor_width, match) in enumerate(anchors):
        end = anchors[pos + 1][0] if pos + 1 < len(anchors) else len(chunks)
        block_items = chunks[start:end]
        raw_block = "\n".join(str(item.get("text") or "") for item in block_items)
        plain_block = html_to_plain(raw_block)
        title = anchored_title(match.group("title"))
        if title is None:
            continue
        code = (
            match.group("code")
            .replace("–", "-")
            .replace("～", "~")
            .replace("\\~", "~")
            .replace(" ", "")
        )
        fields = extract_fields(plain_block)
        fields["사업명"] = title
        fields["세부사업코드"] = code
        fields["코드유형"] = "aggregate" if re.search(r"[~,]", code) else "detail"
        pages = [item.get("page") for item in block_items if isinstance(item.get("page"), int)]
        anchor_ids = [
            chunk_reference(chunks[index], index)
            for index in range(start, min(start + anchor_width, len(chunks)))
        ]
        cards.append(
            {
                "ministry": ministry,
                "source_pdf": source_pdf,
                "extractor": "kordoc_chunks",
                "title": title,
                "heading_ordinal": int(match.group("ordinal")),
                "exec_paths": find_exec_paths_from_chunks(block_items, plain_block),
                "amount_mentions": find_amounts(plain_block),
                "fields": fields,
                "page_start": min(pages) if pages else None,
                "page_end": max(pages) if pages else None,
                "anchor_chunk_id": anchor_ids[0],
                "anchor_chunk_ids": anchor_ids,
                "source_chunk_start": chunk_reference(chunks[start], start),
                "source_chunk_end": chunk_reference(chunks[end - 1], end - 1),
                "source_chunk_index_start": start,
                "source_chunk_index_end": end - 1,
                "snippet": re.sub(r"\s+", " ", plain_block)[:600],
            }
        )
    return cards, sum(len(str(item.get("text") or "")) for item in chunks)


def pdftotext_fallback(pdf: Path, max_pages: int = 80) -> str:
    TEXT_ROOT.mkdir(parents=True, exist_ok=True)
    txt = TEXT_ROOT / (pdf.stem + ".fallback.txt")
    cmd = [
        "pdftotext",
        "-layout",
        "-f",
        "1",
        "-l",
        str(max_pages),
        str(pdf),
        str(txt),
    ]
    subprocess.run(cmd, check=False, capture_output=True)
    if txt.exists():
        return txt.read_text(encoding="utf-8", errors="replace")
    return ""


def find_exec_paths(text: str) -> list[str]:
    found = []
    for pat, label in EXEC_PATTERNS:
        if re.search(pat, text):
            found.append(label)
    return sorted(set(found))


SUPPORT_HEADER_MAP = {
    "직접": "직접",
    "출자": "출자",
    "출연": "위탁/출연",
    "보조": "보조",
    "융자": "융자",
}


def checked_support_paths(raw_table: str) -> list[str]:
    """Read checked cells only, excluding the table's option headers."""
    rows = []
    for line in (raw_table or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and not all(re.fullmatch(r"[-: ]+", cell or "-") for cell in cells):
            rows.append(cells)
    if len(rows) < 2:
        return []
    headers = rows[0]
    values = rows[-1] + [""] * max(0, len(headers) - len(rows[-1]))
    found = []
    for header, value in zip(headers, values):
        label = SUPPORT_HEADER_MAP.get(re.sub(r"\s+", "", header))
        if label and re.search(r"[○●◯✓✔ㅇ]|\b[OoVv]\b", value):
            found.append(label)
    return sorted(set(found))


def find_exec_paths_from_chunks(block_items: list[dict], plain_text: str) -> list[str]:
    """Extract selected support types or an explicit execution-method value."""
    selected = []
    for idx, item in enumerate(block_items):
        if "사업 지원 형태" not in str(item.get("text") or ""):
            continue
        for candidate in block_items[idx + 1 : idx + 4]:
            ctext = str(candidate.get("text") or "")
            if "직접" in ctext and "출자" in ctext:
                selected.extend(checked_support_paths(ctext))
                break
    if selected:
        return sorted(set(selected))
    fields = extract_fields(plain_text)
    method = fields.get("사업시행방법") or fields.get("지원형태") or ""
    return find_exec_paths(method)


def find_amounts(text: str) -> list[str]:
    amts = re.findall(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?\s*(?:백만원|억원|원)?", text)
    amts += re.findall(r"(?<![\d,])\d+(?:\.\d+)?\s*(?:백만원|억원)", text)
    out = []
    seen = set()
    for a in amts:
        a = re.sub(r"\s+", " ", a).strip()
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out[:12]


def is_placeholder(value: str, field: str = "") -> bool:
    normalized = normalize_text_value(value).strip(" .:;·|")
    compact = re.sub(r"\s+", " ", normalized)
    if not compact or COMMON_PLACEHOLDER_RE.fullmatch(compact):
        return True
    if FIELD_PLACEHOLDER_RE.fullmatch(compact):
        return True
    if field == "사업시행주체" and IMPLEMENTER_PLACEHOLDER_RE.fullmatch(compact):
        return True
    if field == "사업기간" and PERIOD_PLACEHOLDER_RE.fullmatch(compact):
        return True
    return False


def extract_fields(text: str) -> dict:
    """Extract explicit narrative fields; hierarchy is supplied by the API."""
    fields = {}
    patterns = {
        "사업시행방법": r"(?:사업시행방법|사업시행\s*방법)\s*[:：]\s*([^\n]+)",
        "사업기간": r"사업기간\s*[:：]\s*([^\n]+)",
        "총사업비": r"총사업비\s*[:：]\s*([^\n]+)",
        "지원형태": r"지원형태\s*[:：]\s*([^\n]+)",
        "추진체계": r"추진체계\s*[:：]\s*([^\n]+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text)
        if m is None:
            continue
        val = normalize_text_value(m.group(1)).strip(" :-·")
        if not is_placeholder(val, key):
            fields[key] = val[:200]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for label in ("사업시행주체", "시행주체"):
        try:
            idx = lines.index(label)
        except ValueError:
            continue
        for value in lines[idx + 1 : idx + 5]:
            if value in {
                "구분",
                "기관명",
                "소관부처",
                "시행기관",
                "기관",
                "실·국·과(팀)",
                "사업명",
            }:
                continue
            if value.startswith("#") or value.startswith("(단위:"):
                break
            if is_placeholder(value, "사업시행주체"):
                break
            fields["사업시행주체"] = normalize_text_value(value)[:200]
            break
        if "사업시행주체" in fields:
            break
    mcode = CODE_RE.search(text)
    if mcode is not None:
        fields["세부사업코드"] = mcode.group(1).replace("–", "-").replace(" ", "")
    return fields


def clean_title(raw: str) -> str | None:
    decoded = html.unescape(raw or "")
    t = normalize_text_value(re.sub(r"<[^>]+>", " ", decoded)).strip(" :-·.|")
    t = re.sub(r"^[\(（]?\s*\d{1,3}\s*[\)）]\s*", "", t).strip()
    t = re.sub(r"[\(（]\s*\d{3,6}\s*[-–]\s*\d{2,6}\s*[\)）]\s*$", "", t).strip()
    if len(t) < 4 or len(t) > 80:
        return None
    if NOISE_TITLE.search(t):
        return None
    if t.startswith("|") or "colspan" in t or "</" in t:
        return None
    if t in BANNED_TITLES:
        return None
    return t


def guess_title(block: str) -> str | None:
    head = "\n".join(block.splitlines()[:10])
    # (9) title (1337-300)
    m = re.search(
        r"[\(（]\s*\d{1,3}\s*[\)）]\s*([가-힣A-Za-z0-9()·\s/\-]{4,80}?)\s*[\(（]\s*\d{3,6}\s*[-–]\s*\d{2,6}\s*[\)）]",
        head,
    )
    if m is not None:
        ct = clean_title(m.group(1))
        if ct is not None:
            return ct
    # 사 업 명 ... title
    m = re.search(r"사\s*업\s*명\s*[\(（]?\s*\d*\s*[\)）]?\s*(.+)", head)
    if m is not None:
        ct = clean_title(m.group(1))
        if ct is not None:
            return ct
    fields = extract_fields(block)
    if "사업명" in fields:
        ct = clean_title(fields["사업명"])
        if ct is not None:
            return ct
    for ln in block.splitlines()[:12]:
        ct = clean_title(ln)
        if ct is not None:
            return ct
    return None


def score_section(text: str) -> int:
    score = 0
    if re.search(r"사업명|사업\s*코드|지원형태|시행주체|예산\s*총괄|산출\s*근거|추진체계", text):
        score += 2
    if re.search(r"백만원|억원", text):
        score += 1
    if re.search(r"위탁|보조|직접|출연|융자|출자", text):
        score += 1
    if CODE_RE.search(text):
        score += 1
    return score


def split_sections(text: str) -> list[str]:
    matches = list(BIZ_ANCHOR.finditer(text))
    if len(matches) >= 2:
        sections = []
        for i, m in enumerate(matches):
            start = m.start()
            if i + 1 < len(matches):
                end = matches[i + 1].start()
            else:
                end = len(text)
            part = text[start:end].strip()
            if len(part) >= 80:
                sections.append(part)
        if sections:
            return sections
    parts = re.split(r"\n(?=\s*(?:□|○|#{1,3}\s|\d+\.\s))", text)
    out = []
    for p in parts:
        if p and len(p.strip()) >= 80:
            out.append(p.strip())
    return out


def cards_from_text(text: str, ministry: str, source_pdf: str, extractor: str) -> list[dict]:
    cards = []
    for block in split_sections(text):
        if score_section(block) < 2:
            continue
        fields = extract_fields(block)
        title = guess_title(block)
        cards.append(
            {
                "ministry": ministry,
                "source_pdf": source_pdf,
                "extractor": extractor,
                "title": title,
                "exec_paths": find_exec_paths(block),
                "amount_mentions": find_amounts(block),
                "fields": fields,
                "snippet": re.sub(r"\s+", " ", block)[:400],
            }
        )
    uniq = []
    seen = set()
    for c in cards:
        key = (c.get("title") or "", (c.get("snippet") or "")[:100])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    return uniq


def resolve_kordoc_outputs(pdf: Path, ministry_key: str):
    d = KORDOC_ROOT / ministry_key / pdf.stem
    chunks = d / (pdf.stem + ".chunks.json")
    md = d / (pdf.stem + ".md")
    if chunks.exists() or md.exists():
        c = chunks if chunks.exists() else None
        m = md if md.exists() else None
        return c, m

    ab = ROOT / "data" / "parser_ab" / "kordoc"
    c2 = ab / (pdf.stem + ".chunks.json")
    m2 = ab / (pdf.stem + ".md")
    if c2.exists() or m2.exists():
        c = c2 if c2.exists() else None
        m = m2 if m2.exists() else None
        return c, m
    return None, None


def pdf_page_count(pdf: Path) -> int:
    proc = subprocess.run(
        ["pdfinfo", str(pdf)],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        match = re.search(r"^Pages:\s*(\d+)\s*$", proc.stdout or "", re.MULTILINE)
        if match is not None:
            return int(match.group(1))
    raise RuntimeError(f"cannot determine PDF page count for {pdf}: {(proc.stderr or '')[-300:]}")


def validate_full_kordoc_extract(pdf: Path, chunks_path: Path) -> None:
    """Reject stale, partial, or unpinned chunks before a canonical parse."""
    suffix = ".chunks.json"
    if not chunks_path.name.endswith(suffix):
        raise RuntimeError(f"unexpected kordoc chunks filename: {chunks_path}")
    meta_path = chunks_path.with_name(
        chunks_path.name[: -len(suffix)] + ".chunks.meta.json"
    )
    if not meta_path.is_file():
        raise RuntimeError(f"missing kordoc extraction metadata: {meta_path}")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as err:
        raise RuntimeError(f"invalid kordoc extraction metadata: {meta_path}") from err
    pdf_stat = pdf.stat()
    chunks_stat = chunks_path.stat()
    expected = {
        "returncode": 0,
        "format": "chunks",
        "kordoc_version": KORDOC_VERSION,
        "pages": None,
        "input_bytes": pdf_stat.st_size,
        "input_mtime_ns": pdf_stat.st_mtime_ns,
        "out_bytes": chunks_stat.st_size,
    }
    mismatches = [
        f"{key}={meta.get(key)!r} expected {value!r}"
        for key, value in expected.items()
        if meta.get(key) != value
    ]
    try:
        if Path(str(meta.get("pdf", ""))).resolve() != pdf.resolve():
            mismatches.append("pdf path does not match source PDF")
        if Path(str(meta.get("out", ""))).resolve() != chunks_path.resolve():
            mismatches.append("output path does not match chunks file")
    except (OSError, RuntimeError, ValueError):
        mismatches.append("metadata contains an invalid path")

    chunks = load_chunks(chunks_path)
    page_values = [
        item.get("page")
        for item in chunks
        if isinstance(item.get("page"), int)
    ]
    expected_pages = pdf_page_count(pdf)
    page_min = min(page_values) if page_values else None
    page_max = max(page_values) if page_values else None
    if page_min != 1 or page_max != expected_pages:
        mismatches.append(
            f"chunk page coverage is {page_min}-{page_max}, expected 1-{expected_pages}"
        )
    for key, value in {
        "page_min": page_min,
        "page_max": page_max,
        "pdf_pages": expected_pages,
        "pages_with_chunks": len(set(page_values)),
    }.items():
        if meta.get(key) != value:
            mismatches.append(f"{key}={meta.get(key)!r} expected {value!r}")
    if mismatches:
        raise RuntimeError(
            f"invalid full kordoc extraction for {pdf.name}: " + "; ".join(mismatches)
        )


def parse_one(
    pdf: Path,
    ministry_name: str,
    ministry_key: str,
    require_kordoc: bool = True,
) -> dict:
    if PDF_ROOT in pdf.parents:
        source_pdf = str(pdf.relative_to(PDF_ROOT))
    else:
        source_pdf = str(pdf)

    chunks_path, md_path = resolve_kordoc_outputs(pdf, ministry_key)
    text = ""
    extractor = "none"
    parsed_chars = 0

    cards = None
    if chunks_path is not None and chunks_path.exists():
        if require_kordoc and KORDOC_ROOT in chunks_path.resolve().parents:
            validate_full_kordoc_extract(pdf, chunks_path)
        cards, parsed_chars = cards_from_chunks(chunks_path, ministry_name, source_pdf)
        if cards:
            extractor = "kordoc_chunks"
        elif require_kordoc:
            raise RuntimeError(f"kordoc chunks contain no coded headings: {chunks_path}")
        else:
            # An empty/unsupported chunks result must not suppress markdown or
            # pdftotext fallback when diagnostics explicitly allow fallback.
            cards = None
    elif require_kordoc:
        raise RuntimeError(f"missing full kordoc chunks for {pdf}")

    if cards is None:
        if md_path is not None and md_path.exists():
            text = md_path.read_text(encoding="utf-8", errors="replace")
            extractor = "kordoc_markdown"
        if len(text) < 200:
            max_pages = 120 if pdf.stat().st_size > 15_000_000 else 80
            text = pdftotext_fallback(pdf, max_pages=max_pages)
            extractor = "pdftotext_fallback"
        parsed_chars = len(text)
        cards = cards_from_text(text, ministry_name, source_pdf, extractor)
    exec_counter = Counter()
    for c in cards:
        for e in c.get("exec_paths") or []:
            exec_counter[e] += 1
    return {
        "ministry": ministry_name,
        "pdf": source_pdf,
        "extractor": extractor,
        "chars": parsed_chars,
        "cards": cards,
        "cards_with_code": sum(1 for c in cards if (c.get("fields") or {}).get("세부사업코드")),
        "cards_with_implementer": sum(
            1 for c in cards if (c.get("fields") or {}).get("사업시행주체")
        ),
        "exec_path_counts": dict(exec_counter),
        "sample_titles": [c.get("title") for c in cards[:15]],
    }


def collect_jobs(pilot_samples: bool):
    jobs = []
    if pilot_samples:
        sample_dir = ROOT / "data" / "parser_ab" / "samples"
        for pdf in sorted(sample_dir.glob("*.pdf")):
            key = "mois" if "mois" in pdf.name else "molit"
            name = "행정안전부" if key == "mois" else "국토교통부"
            jobs.append((pdf, name, key))
        return jobs

    mapping = {
        "mois": "행정안전부",
        "molit": "국토교통부",
        "motir": "산업통상부",
    }
    for key, name in mapping.items():
        d = PDF_ROOT / key
        if not d.exists():
            continue
        for pdf in sorted(d.glob("*.pdf")):
            if pdf.stat().st_size < 1000:
                continue
            if pdf.read_bytes()[:4] != b"%PDF":
                continue
            jobs.append((pdf, name, key))
    return jobs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot-samples", action="store_true")
    ap.add_argument(
        "--allow-fallback",
        action="store_true",
        help="allow partial pdftotext fallback for diagnostics only",
    )
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    ART.mkdir(parents=True, exist_ok=True)

    jobs = collect_jobs(args.pilot_samples)
    if not jobs:
        raise SystemExit("no pdf jobs")

    results = []
    all_cards = []
    for pdf, ministry_name, ministry_key in jobs:
        print("parse", pdf.name, ministry_name)
        res = parse_one(
            pdf,
            ministry_name,
            ministry_key,
            require_kordoc=not args.allow_fallback,
        )
        results.append(res)
        all_cards.extend(res["cards"])
        print(
            " ",
            res["extractor"],
            "cards",
            len(res["cards"]),
            "exec",
            res["exec_path_counts"],
            "titles",
            res["sample_titles"][:5],
        )

    by_ministry = defaultdict(list)
    for c in all_cards:
        by_ministry[c["ministry"]].append(c)

    summary = {
        "mode": "fallback_diagnostic" if args.allow_fallback else "kordoc_primary",
        "pdfs": [
            {
                "pdf": r["pdf"],
                "ministry": r["ministry"],
                "extractor": r["extractor"],
                "cards": len(r["cards"]),
                "cards_with_code": r["cards_with_code"],
                "cards_with_implementer": r["cards_with_implementer"],
                "exec_path_counts": r["exec_path_counts"],
                "sample_titles": r["sample_titles"],
            }
            for r in results
        ],
        "total_cards": len(all_cards),
        "by_ministry": {k: len(v) for k, v in by_ministry.items()},
    }

    suffix_parts = []
    if args.pilot_samples:
        suffix_parts.append("pilot_samples")
    if args.allow_fallback:
        suffix_parts.append("fallback_diagnostic")
    suffix = "_" + "_".join(suffix_parts) if suffix_parts else ""
    cards_path = OUT / ("pdf_business_cards" + suffix + ".json")
    summary_path = OUT / ("pdf_parse_summary" + suffix + ".json")
    cards_path.write_text(json.dumps(all_cards, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    artifact_path = ART / ("pdf_parse_summary" + suffix + ".json")
    artifact_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("total_cards", len(all_cards))
    print("wrote", cards_path)
    print("wrote", summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
