#!/usr/bin/env python3
"""Collect conservative LOFIN QWGJK candidates for central local transfers.

The Open Fiscal ``ExpenditureBudgetAdd2`` lines decide *which* central detail
businesses are eligible: only businesses with a positive local-government
transfer channel are queried.  LOFIN names are not canonical identifiers, so
every result is deliberately labelled ``keyword_candidate`` and carries the
full central business key that caused the query.

The resulting national-reflection amounts are not additive across wide-area
and basic local governments.  They must not be presented as a reconciliation
to the central budget amount.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw" / "lofin"
NORM = DATA / "normalized"
BASE = "https://www.lofin365.go.kr/lf/hub"
SERVICE = "QWGJK"
UA = {"User-Agent": "Koreabudget100/0.1"}
CTX = ssl.create_default_context()

KEY_FIELDS = (
    "office_name",
    "account_name",
    "program_name",
    "unit_business_name",
    "detail_business_name",
)
NON_ADDITIVE_WARNING = (
    "LOFIN bdg_ntep는 지자체 예산에 반영된 국비 후보액이다. 광역·기초 행에 "
    "같은 재원이 중복 표현될 수 있으므로 합계를 중앙예산 집행액 또는 대사액으로 "
    "해석하지 않는다."
)

# These phrases were checked against QWGJK in the 2026 pilot.  Substring rules
# intentionally favour precision over recall; every hit remains a candidate.
KEYWORD_OVERRIDES = (
    ("지역사랑상품권", "지역사랑상품권"),
    ("재해위험지역", "재해위험지역"),
    ("사회연대경제", "사회연대경제"),
    ("청년월세", "청년월세"),
    ("스마트시티", "스마트시티"),
    ("주거급여", "주거급여"),
)
GENERIC_KEYWORDS = {
    "건설사업",
    "기반시설",
    "관리사업",
    "보조사업",
    "시설개선",
    "운영지원",
    "재정지원",
    "지역개발",
    "투자유치",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def load_key() -> str:
    env_path = ROOT / ".env"
    if not env_path.exists():
        raise RuntimeError(f"LOFIN365_API_KEY missing: {env_path} does not exist")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("LOFIN365_API_KEY="):
            key = line.split("=", 1)[1].strip()
            if key:
                return key
    raise RuntimeError("LOFIN365_API_KEY missing from .env")


def clean_text(value) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def compact_text(value) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", clean_text(value)).casefold()


def as_number(value) -> int | float:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        number = float(str(value).replace(",", "").strip())
    return int(number) if number.is_integer() else number


def central_key(row: dict, year: int | None = None) -> tuple[str, ...]:
    resolved_year = year if year is not None else row.get("year")
    return (str(resolved_year or ""),) + tuple(
        clean_text(row.get(field)) for field in KEY_FIELDS
    )


def is_local_transfer(row: dict) -> bool:
    mok = clean_text(row.get("mok_name"))
    semok = clean_text(row.get("semok_name"))
    return "자치단체이전" in f"{mok} {semok}" or "자치단체" in semok


def select_candidates(details: list[dict], lines: list[dict], year: int) -> list[dict]:
    canonical = {
        central_key(row): row
        for row in details
        if str(row.get("year") or "") == str(year)
    }
    amounts: dict[tuple[str, ...], float] = defaultdict(float)
    line_counts: dict[tuple[str, ...], int] = defaultdict(int)
    for row in lines:
        if str(row.get("year") or "") != str(year) or not is_local_transfer(row):
            continue
        key = central_key(row)
        if key not in canonical:
            continue
        amounts[key] += float(as_number(row.get("congress_amt")))
        line_counts[key] += 1

    selected = []
    for key, amount in amounts.items():
        if amount <= 0:
            continue
        detail = canonical[key]
        keyword, strategy, reason = choose_keyword(detail.get("detail_business_name"))
        selected.append(
            {
                "central_business_key": list(key),
                "central_business_name": detail.get("detail_business_name"),
                "central_local_transfer_amount_won": as_number(amount),
                "local_transfer_line_count": line_counts[key],
                "keyword": keyword,
                "keyword_strategy": strategy,
                "keyword_skip_reason": reason,
            }
        )
    return sorted(selected, key=lambda item: tuple(item["central_business_key"]))


def choose_keyword(name) -> tuple[str | None, str | None, str | None]:
    original = clean_text(name)
    compact = compact_text(original)
    for needle, keyword in KEYWORD_OVERRIDES:
        if compact_text(needle) in compact:
            return keyword, f"verified_override:{needle}", None

    # Parentheses usually contain accounting/channel qualifiers such as 보조,
    # 자율, 세종, 제주, or R&D; excluding them improves name compatibility
    # without broadening the meaningful title itself.
    candidate = re.sub(r"\([^()]*\)", " ", original)
    candidate = re.sub(r"[·ㆍ,/~]+", " ", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip(" -_")
    candidate = re.sub(r"(?:\s+)(?:사업|지원|추진)$", "", candidate).strip()
    semantic_length = len(compact_text(candidate))
    if semantic_length < 5:
        return None, None, "keyword_shorter_than_5_semantic_characters"
    if compact_text(candidate) in {compact_text(x) for x in GENERIC_KEYWORDS}:
        return None, None, "keyword_is_generic"
    strategy = (
        "normalized_without_parenthetical_qualifier"
        if candidate != original
        else "normalized_full_title"
    )
    return candidate, strategy, None


def classify_local(laf_cd) -> str:
    code = re.sub(r"\D", "", str(laf_cd or ""))
    if len(code) >= 5:
        return "광역본청" if code[2:5] == "000" else "기초"
    return "unknown"


def parse_payload(text: str):
    data = json.loads(text)
    if isinstance(data, str):
        data = json.loads(data)
    return data


def call_api(key: str, params: dict, retries: int = 3):
    query = {
        "Key": key,
        "Type": "json",
        **{k: str(v) for k, v in params.items() if v not in (None, "")},
    }
    request = urllib.request.Request(
        f"{BASE}/{SERVICE}?{urllib.parse.urlencode(query)}", headers=UA
    )
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, context=CTX, timeout=90) as response:
                return parse_payload(response.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt == retries:
                raise
            time.sleep(0.5 * attempt)
    raise AssertionError("unreachable")


def extract_rows(payload) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    meta = {"payload_type": type(payload).__name__}
    if not isinstance(payload, dict):
        return rows, meta
    if isinstance(payload.get("RESULT"), dict):
        meta["RESULT"] = payload["RESULT"]
    for name, value in payload.items():
        if name == "RESULT" or not isinstance(value, list):
            continue
        meta["list_key"] = name
        for item in value:
            if not isinstance(item, dict):
                continue
            for head in item.get("head") or []:
                if not isinstance(head, dict):
                    continue
                if "list_total_count" in head:
                    meta["list_total_count"] = head.get("list_total_count")
                if isinstance(head.get("RESULT"), dict):
                    meta["RESULT"] = head["RESULT"]
            if isinstance(item.get("row"), list):
                rows.extend(row for row in item["row"] if isinstance(row, dict))
        if rows:
            break
    return rows, meta


def fetch_all(
    key: str,
    *,
    year: int,
    exe_ymd: str,
    keyword: str,
    psize: int,
    max_pages: int,
    delay: float,
) -> tuple[list[dict], list[dict]]:
    all_rows: list[dict] = []
    pages: list[dict] = []
    expected_total: int | None = None
    for page in range(1, max_pages + 1):
        params = {
            "pIndex": page,
            "pSize": psize,
            "fyr": year,
            "exe_ymd": exe_ymd,
            "dbiz_nm": keyword,
        }
        payload = call_api(key, params)
        rows, meta = extract_rows(payload)
        result = meta.get("RESULT") or {}
        code = result.get("CODE")
        if code and code != "INFO-000":
            raise RuntimeError(f"QWGJK returned {code}: {result.get('MESSAGE', '')}")
        pages.append({"page": page, "row_count": len(rows), "meta": meta})
        all_rows.extend(rows)
        try:
            if meta.get("list_total_count") is not None:
                expected_total = int(meta["list_total_count"])
        except (TypeError, ValueError):
            expected_total = None
        if not rows or len(rows) < psize:
            break
        if expected_total is not None and len(all_rows) >= expected_total:
            break
        time.sleep(delay)
    if expected_total is not None and len(all_rows) < expected_total:
        raise RuntimeError(
            f"QWGJK pagination incomplete for {keyword!r}: "
            f"got {len(all_rows)} of {expected_total} rows"
        )
    return all_rows, pages


def cache_path(year: int, exe_ymd: str, keyword: str) -> Path:
    digest = hashlib.sha256(keyword.encode("utf-8")).hexdigest()[:16]
    return RAW / "candidate_cache" / str(year) / exe_ymd / f"{digest}.json"


def cache_is_valid(data: dict, *, year: int, exe_ymd: str, keyword: str) -> bool:
    return (
        isinstance(data, dict)
        and data.get("schema_version") == "1.0"
        and data.get("service") == SERVICE
        and data.get("year") == year
        and data.get("exe_ymd") == exe_ymd
        and data.get("keyword") == keyword
        and isinstance(data.get("rows"), list)
        and data.get("complete") is True
    )


def load_or_fetch_keyword(
    key: str | None,
    *,
    year: int,
    exe_ymd: str,
    keyword: str,
    psize: int,
    max_pages: int,
    delay: float,
    refresh: bool,
    cache_only: bool,
) -> tuple[list[dict], list[dict], str, Path]:
    path = cache_path(year, exe_ymd, keyword)
    if path.exists() and not refresh:
        cached = load_json(path)
        if cache_is_valid(cached, year=year, exe_ymd=exe_ymd, keyword=keyword):
            return cached["rows"], cached.get("pages") or [], "cache", path
    if cache_only:
        raise RuntimeError(f"valid cache missing for keyword {keyword!r}: {path}")
    if key is None:
        raise RuntimeError("LOFIN API key was not loaded")
    rows, pages = fetch_all(
        key,
        year=year,
        exe_ymd=exe_ymd,
        keyword=keyword,
        psize=psize,
        max_pages=max_pages,
        delay=delay,
    )
    cached = {
        "schema_version": "1.0",
        "service": SERVICE,
        "year": year,
        "exe_ymd": exe_ymd,
        "keyword": keyword,
        "complete": True,
        "pages": pages,
        "rows": rows,
    }
    atomic_write_json(path, cached)
    return rows, pages, "network", path


def normalize_row(raw: dict, candidate: dict, year: int, exe_ymd: str) -> dict | None:
    try:
        if int(raw.get("fyr")) != year or str(raw.get("exe_ymd")) != exe_ymd:
            return None
        national_amount = as_number(raw.get("bdg_ntep"))
    except (TypeError, ValueError):
        return None
    if national_amount <= 0:
        return None
    laf_cd = raw.get("laf_cd")
    return {
        "source": "lofin_QWGJK",
        "match_status": "keyword_candidate",
        "match_mode": "keyword_dbiz_nm",
        "central_business_key": candidate["central_business_key"],
        "central_business_name": candidate["central_business_name"],
        "central_local_transfer_amount_won": candidate[
            "central_local_transfer_amount_won"
        ],
        "keyword": candidate["keyword"],
        "keyword_strategy": candidate["keyword_strategy"],
        "year": year,
        "exe_ymd": exe_ymd,
        "region_code": raw.get("wa_laf_cd"),
        "region_name": raw.get("wa_laf_hg_nm"),
        "local_gov_code": laf_cd,
        "local_gov_name": raw.get("laf_hg_nm"),
        "local_level": classify_local(laf_cd),
        "account_name": raw.get("acnt_dv_nm"),
        "detail_business_name": raw.get("dbiz_nm"),
        "detail_business_code": raw.get("dbiz_cd"),
        "field_name": raw.get("fld_nm"),
        "section_name": raw.get("part_nm") or raw.get("sect_nm"),
        "budget_cash_amt": as_number(raw.get("bdg_cash_amt")),
        "national_amt": national_amount,
        "sido_amt": as_number(raw.get("capep")),
        "sigungu_amt": as_number(raw.get("sggep")),
        "spend_amt": as_number(raw.get("ep_amt")),
        "compile_amt": as_number(raw.get("cpl_amt")),
    }


def row_identity(row: dict) -> tuple:
    local_identity = clean_text(row.get("local_gov_code")) or clean_text(
        row.get("local_gov_name")
    )
    detail_identity = clean_text(row.get("detail_business_code")) or compact_text(
        f"{row.get('account_name', '')} {row.get('detail_business_name', '')}"
    )
    return (
        tuple(str(value) for value in row.get("central_business_key") or []),
        str(row.get("exe_ymd") or ""),
        local_identity,
        detail_identity,
    )


def dedupe_rows(rows: list[dict]) -> list[dict]:
    chosen = {}
    for row in rows:
        identity = row_identity(row)
        previous = chosen.get(identity)
        if previous is None:
            chosen[identity] = row
            continue
        # Duplicate API rows should be identical.  A deterministic JSON tie
        # breaker keeps output stable if the service returns inconsistent data.
        if json.dumps(row, ensure_ascii=False, sort_keys=True) < json.dumps(
            previous, ensure_ascii=False, sort_keys=True
        ):
            chosen[identity] = row
    return [chosen[key] for key in sorted(chosen)]


def make_plan_summary(candidates: list[dict], year: int, exe_ymd: str) -> dict:
    queryable = [item for item in candidates if item.get("keyword")]
    return {
        "schema_version": "1.0",
        "service": SERVICE,
        "endpoint": f"{BASE}/{SERVICE}",
        "year": year,
        "exe_ymd": exe_ymd,
        "selection": "positive ExpenditureBudgetAdd2 local-government transfer channel",
        "match_status": "keyword_candidate",
        "candidate_business_count": len(candidates),
        "queryable_business_count": len(queryable),
        "skipped_business_count": len(candidates) - len(queryable),
        "unique_keyword_count": len({item["keyword"] for item in queryable}),
        "non_additive_warning": NON_ADDITIVE_WARNING,
        "businesses": candidates,
    }


def run_self_test() -> None:
    assert choose_keyword("주거급여지원")[:2] == (
        "주거급여",
        "verified_override:주거급여",
    )
    assert choose_keyword("특수상황지역개발(제주)")[0] == "특수상황지역개발"
    assert choose_keyword("지가조사")[0] is None
    assert classify_local("1100000") == "광역본청"
    assert classify_local("1111000") == "기초"
    details = [
        {
            "year": 2026,
            "office_name": "부",
            "account_name": "회계",
            "program_name": "프로그램",
            "unit_business_name": "단위",
            "detail_business_name": "주거급여지원",
        }
    ]
    lines = [
        {
            **details[0],
            "mok_name": "자치단체이전",
            "semok_name": "자치단체경상보조",
            "congress_amt": 10,
        }
    ]
    planned = select_candidates(details, lines, 2026)
    assert len(planned) == 1 and planned[0]["central_local_transfer_amount_won"] == 10
    duplicate = {
        "central_business_key": planned[0]["central_business_key"],
        "exe_ymd": "20260630",
        "local_gov_code": "1100000",
        "detail_business_code": "A",
    }
    assert len(dedupe_rows([duplicate, dict(duplicate)])) == 1
    print("self-test: ok")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch LOFIN QWGJK keyword candidates only for positive central "
            "local-government transfer businesses."
        )
    )
    parser.add_argument(
        "--details",
        default=str(NORM / "expbudgetadd2_2026_pilots_details.json"),
        help="canonical ExpenditureBudgetAdd2 detail JSON",
    )
    parser.add_argument(
        "--lines",
        default=str(NORM / "expbudgetadd2_2026_pilots_lines.json"),
        help="ExpenditureBudgetAdd2 line JSON used to select transfer channels",
    )
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--exe-ymd", default="20260630")
    parser.add_argument("--psize", type=int, default=1000)
    parser.add_argument("--max-pages", type=int, default=50)
    parser.add_argument("--delay", type=float, default=0.12)
    parser.add_argument(
        "--output",
        help="normalized row JSON (default: data/normalized/lofin_local_transfer_candidates_YEAR.json)",
    )
    parser.add_argument(
        "--summary-output",
        help="summary JSON (default: matching *_summary.json)",
    )
    parser.add_argument(
        "--refresh", action="store_true", help="ignore valid per-keyword caches"
    )
    parser.add_argument(
        "--cache-only",
        action="store_true",
        help="perform no network calls; fail if a required cache is absent",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="show selected businesses/keywords without loading an API key or writing output",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="run offline unit checks and exit"
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        return 0
    if args.refresh and args.cache_only:
        parser.error("--refresh and --cache-only are mutually exclusive")
    if not re.fullmatch(r"\d{8}", args.exe_ymd) or not args.exe_ymd.startswith(
        str(args.year)
    ):
        parser.error("--exe-ymd must be an 8-digit date in --year")
    if not 1 <= args.psize <= 1000:
        parser.error("--psize must be between 1 and 1000")
    if args.max_pages < 1:
        parser.error("--max-pages must be positive")

    details = load_json(Path(args.details))
    lines = load_json(Path(args.lines))
    if not isinstance(details, list) or not isinstance(lines, list):
        raise RuntimeError("--details and --lines must each contain a JSON list")
    candidates = select_candidates(details, lines, args.year)
    summary = make_plan_summary(candidates, args.year, args.exe_ymd)
    if args.plan_only:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    key = None if args.cache_only else load_key()
    by_keyword: dict[str, list[dict]] = defaultdict(list)
    for candidate in candidates:
        if candidate.get("keyword"):
            by_keyword[candidate["keyword"]].append(candidate)

    raw_by_keyword: dict[str, list[dict]] = {}
    fetch_reports = []
    errors = []
    for index, keyword in enumerate(sorted(by_keyword), 1):
        print(f"[{index}/{len(by_keyword)}] QWGJK {keyword}", flush=True)
        try:
            rows, pages, source, path = load_or_fetch_keyword(
                key,
                year=args.year,
                exe_ymd=args.exe_ymd,
                keyword=keyword,
                psize=args.psize,
                max_pages=args.max_pages,
                delay=args.delay,
                refresh=args.refresh,
                cache_only=args.cache_only,
            )
            raw_by_keyword[keyword] = rows
            fetch_reports.append(
                {
                    "keyword": keyword,
                    "source": source,
                    "cache_path": str(path.relative_to(ROOT)),
                    "raw_row_count": len(rows),
                    "page_count": len(pages),
                }
            )
        except Exception as exc:  # keep other caches, never publish partial normalized data
            errors.append({"keyword": keyword, "error": f"{type(exc).__name__}: {exc}"})
    if errors:
        print(json.dumps({"complete": False, "errors": errors}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    normalized = []
    business_reports = []
    for candidate in candidates:
        keyword = candidate.get("keyword")
        rows = []
        if keyword:
            for raw in raw_by_keyword.get(keyword, []):
                normalized_row = normalize_row(raw, candidate, args.year, args.exe_ymd)
                if normalized_row is not None:
                    rows.append(normalized_row)
            normalized.extend(rows)
        business_reports.append(
            {
                **candidate,
                "candidate_row_count": len(dedupe_rows(rows)),
                "collection_status": (
                    "skipped_no_conservative_keyword"
                    if not keyword
                    else "keyword_candidates_found"
                    if rows
                    else "no_positive_national_reflection_rows"
                ),
            }
        )
    normalized = dedupe_rows(normalized)

    output = Path(args.output) if args.output else NORM / (
        f"lofin_local_transfer_candidates_{args.year}.json"
    )
    summary_output = (
        Path(args.summary_output)
        if args.summary_output
        else NORM / f"lofin_local_transfer_candidates_{args.year}_summary.json"
    )
    summary.update(
        {
            "complete": True,
            "positive_national_reflection_only": True,
            "normalized_row_count": len(normalized),
            "matched_business_count": sum(
                report["candidate_row_count"] > 0 for report in business_reports
            ),
            "national_reflection_sum_won": sum(
                float(row.get("national_amt") or 0) for row in normalized
            ),
            "fetches": fetch_reports,
            "businesses": business_reports,
            "output": str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output),
        }
    )
    atomic_write_json(output, normalized)
    atomic_write_json(summary_output, summary)
    print(json.dumps({k: summary[k] for k in (
        "candidate_business_count",
        "queryable_business_count",
        "unique_keyword_count",
        "matched_business_count",
        "normalized_row_count",
        "national_reflection_sum_won",
        "non_additive_warning",
    )}, ensure_ascii=False, indent=2))
    print("wrote", output)
    print("wrote", summary_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
