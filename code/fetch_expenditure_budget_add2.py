#!/usr/bin/env python3
"""Fetch Open Fiscal ExpenditureBudgetAdd2 via portal preview proxy."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw" / "openfiscal" / "ExpenditureBudgetAdd2"
NORM = DATA / "normalized"
ENDPOINT = "https://www.openfiscaldata.go.kr/openApi/preview/ExpenditureBudgetAdd2"
SERVICE = "ExpenditureBudgetAdd2"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
REQUIRED_MINISTRIES = ("행정안전부", "국토교통부", "산업통상부")
OPTIONAL_ALIASES = ("산업통상자원부",)
PILOTS = REQUIRED_MINISTRIES + OPTIONAL_ALIASES


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch the canonical 2026 pilot from Open Fiscal "
            "ExpenditureBudgetAdd2. Canonical files are replaced only after all "
            "three required ministry responses pass completeness checks."
        )
    )
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--workers", type=int, default=6)
    return parser.parse_args(argv)


def atomic_write_json(path: Path, value, *, indent: int | None = None) -> None:
    """Write one JSON artifact without exposing a partially written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=indent)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def load_key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("OPENFISCAL_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("OPENFISCAL_API_KEY missing")


def parse_double_json(text: str):
    outer = json.loads(text)
    if isinstance(outer, str):
        return json.loads(outer)
    return outer


def fetch_page(key: str, year: int, page: int, psize: int = 1000, offc_nm: str | None = None) -> dict:
    body = {
        "Key": key,
        "Type": "json",
        "pIndex": str(page),
        "pSize": str(psize),
        "FSCL_YY": str(year),
    }
    if offc_nm:
        body["OFFC_NM"] = offc_nm
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": UA,
            "Accept": "application/json,text/plain,*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return parse_double_json(raw)
    except urllib.error.HTTPError as err:
        body_txt = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {err.code}: {body_txt[:400]}") from err


def extract_rows(payload: dict) -> tuple[list[dict], dict]:
    meta: dict = {}
    rows: list[dict] = []
    if not isinstance(payload, dict):
        return [], {"raw_type": type(payload).__name__}
    if isinstance(payload.get("RESULT"), dict) and SERVICE not in payload:
        meta["RESULT"] = payload["RESULT"]
        return [], meta
    block = payload.get(SERVICE)
    if not isinstance(block, list):
        # fallback generic
        for k, v in payload.items():
            if isinstance(v, list):
                block = v
                meta["list_key"] = k
                break
    if not isinstance(block, list):
        meta["preview"] = str(payload)[:300]
        return [], meta
    for item in block:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("head"), list):
            for h in item["head"]:
                if isinstance(h, dict):
                    if "list_total_count" in h:
                        meta["list_total_count"] = h.get("list_total_count")
                    if isinstance(h.get("RESULT"), dict):
                        meta["RESULT"] = h["RESULT"]
        if isinstance(item.get("row"), list):
            rows.extend([r for r in item["row"] if isinstance(r, dict)])
    return rows, meta


def to_num(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return None


def normalize(rows: list[dict], year: int, ministry_query: str | None = None) -> list[dict]:
    out = []
    for r in rows:
        out.append(
            {
                "year": year,
                "ministry_query": ministry_query,
                "office_name": r.get("OFFC_NM"),
                "account_name": r.get("FSCL_NM"),
                "acct_name": r.get("ACCT_NM"),
                "field_name": r.get("FLD_NM"),
                "section_name": r.get("SECT_NM"),
                "program_name": r.get("PGM_NM"),
                "unit_business_name": r.get("ACTV_NM"),
                "detail_business_name": r.get("SACTV_NM"),
                "mok_name": r.get("CITM_NM"),
                "semok_name": r.get("EITM_NM"),
                "budget_confirm_amt_thousands": to_num(r.get("Y_YY_DFN_KCUR_AMT")),
                "budget_modified_amt_thousands": to_num(r.get("Y_YY_MEDI_KCUR_AMT")),
                "budget_confirm_plus_mod_amt_thousands": to_num(r.get("Y_YY_DFN_MEDI_KCUR_AMT")),
                # convert thousand-won to won for tree consistency with prior pilot
                "congress_amt": (to_num(r.get("Y_YY_DFN_KCUR_AMT")) or 0) * 1000,
                "raw": r,
            }
        )
    return out


def build_tree(rows: list[dict]) -> dict:
    root = {"name": "root", "children": {}, "amount": 0.0, "count": 0}

    def ensure(node, name):
        ch = node["children"]
        if name not in ch:
            ch[name] = {"name": name, "children": {}, "amount": 0.0, "count": 0}
        return ch[name]

    for r in rows:
        amt = float(r.get("congress_amt") or 0.0)
        m = ensure(root, r.get("office_name") or r.get("ministry_query") or "UNKNOWN")
        a = ensure(m, r.get("account_name") or "(회계미상)")
        p = ensure(a, r.get("program_name") or "(프로그램미상)")
        u = ensure(p, r.get("unit_business_name") or "(단위사업미상)")
        d = ensure(u, r.get("detail_business_name") or "(세부사업미상)")
        # optional mok/semok under detail
        mok = r.get("mok_name")
        semok = r.get("semok_name")
        leaf = d
        if mok:
            leaf = ensure(d, mok)
        if semok:
            leaf = ensure(leaf, semok)
        leaf["amount"] += amt
        leaf["count"] += 1
        for n in (d, u, p, a, m, root):
            if n is leaf:
                continue
            n["amount"] += amt
            n["count"] = n.get("count", 0) + 1
        if leaf is not d:
            # already counted leaf; ensure intermediate mok counted once via loop above if present
            pass
    return root


def tree_to_jsonable(node: dict) -> dict:
    children = [tree_to_jsonable(c) for c in node["children"].values()]
    children.sort(key=lambda x: x.get("amount") or 0, reverse=True)
    out = {"name": node["name"], "amount": node.get("amount", 0), "count": node.get("count", 0)}
    if children:
        out["children"] = children
    return out


def fetch_all_for_ministry(key: str, year: int, ministry: str, workers: int = 6) -> tuple[list[dict], dict]:
    first = fetch_page(key, year, 1, 1000, ministry)
    rows1, meta = extract_rows(first)
    try:
        total = int(meta["list_total_count"])
    except (KeyError, TypeError, ValueError):
        total = None
    # A missing total is deliberately not inferred from page 1: doing so could
    # bless a truncated 1,000-row response as complete. The validation gate below
    # will reject it without replacing canonical artifacts.
    pages_needed = max(1, (total + 999) // 1000) if total else 1
    all_rows = list(rows1)
    page_meta = [{"page": 1, "n": len(rows1), "meta": meta}]
    if pages_needed <= 1 or not rows1:
        return all_rows, {"total": total, "pages": page_meta}

    def one(page: int):
        payload = fetch_page(key, year, page, 1000, ministry)
        rows, m = extract_rows(payload)
        return page, rows, m

    page_results: dict[int, tuple[list[dict], dict]] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = [ex.submit(one, p) for p in range(2, pages_needed + 1)]
        for fut in as_completed(futs):
            page, rows, m = fut.result()
            page_results[page] = (rows, m)
    # Preserve API page order regardless of thread completion order so the raw
    # and normalized outputs are deterministic.
    for page in sorted(page_results):
        rows, m = page_results[page]
        page_meta.append({"page": page, "n": len(rows), "meta": m})
        all_rows.extend(rows)
    return all_rows, {"total": total, "pages": page_meta}


def completeness_issues(rows: list[dict], meta: dict, expected_ministry: str | None = None) -> list[str]:
    issues: list[str] = []
    total = meta.get("total")
    pages = meta.get("pages") or []
    if not rows:
        issues.append("response has no rows")
    if total is None:
        issues.append("API list_total_count is missing")
    elif total != len(rows):
        issues.append(f"API total is {total}, but {len(rows)} rows were fetched")
    page_numbers = [p.get("page") for p in pages]
    if page_numbers != list(range(1, len(pages) + 1)):
        issues.append(f"page sequence is incomplete: {page_numbers}")
    if sum(int(p.get("n") or 0) for p in pages) != len(rows):
        issues.append("page row counts do not equal the collected row count")
    if expected_ministry:
        returned_ministries = {row.get("OFFC_NM") for row in rows}
        if returned_ministries != {expected_ministry}:
            issues.append(
                f"OFFC_NM scope mismatch: expected {expected_ministry!r}, "
                f"got {sorted(str(x) for x in returned_ministries)!r}"
            )
    return issues


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    key = load_key()
    year = args.year
    RAW.mkdir(parents=True, exist_ok=True)
    NORM.mkdir(parents=True, exist_ok=True)

    # Fetch into memory first. No canonical or raw artifact is changed until all
    # required collections have passed the completeness gate.
    fetched: dict[str, dict] = {}
    for ministry in PILOTS:
        print("==", ministry, year)
        try:
            rows, meta = fetch_all_for_ministry(key, year, ministry, workers=args.workers)
        except Exception as exc:
            print(" error", exc)
            fetched[ministry] = {"error": str(exc)}
            continue
        norm = normalize(rows, year, ministry)
        total_amt = sum((x.get("congress_amt") or 0) for x in norm)
        print(" rows", len(norm), "api_total", meta.get("total"), "amt_won", f"{total_amt:,.0f}")
        fetched[ministry] = {"rows": rows, "meta": meta, "norm": norm, "total_amt": total_amt}
        time.sleep(0.2)

    gate_failures: list[str] = []
    for ministry in REQUIRED_MINISTRIES:
        result = fetched.get(ministry) or {}
        if result.get("error"):
            gate_failures.append(f"{ministry}: {result['error']}")
            continue
        for issue in completeness_issues(
            result.get("rows") or [], result.get("meta") or {}, expected_ministry=ministry
        ):
            gate_failures.append(f"{ministry}: {issue}")
    if gate_failures:
        print("CANONICAL OUTPUT NOT UPDATED")
        for failure in gate_failures:
            print(" -", failure)
        raise SystemExit("required ministry completeness gate failed")

    # The legacy ministry name is diagnostic only. Even if it unexpectedly
    # returns rows, it is excluded from canonical aggregation to prevent double
    # counting the current 산업통상부 response.
    all_norm = [row for ministry in REQUIRED_MINISTRIES for row in fetched[ministry]["norm"]]
    summary = {
        "year": year,
        "service": SERVICE,
        "endpoint": ENDPOINT,
        "complete": True,
        "canonical": True,
        "required_ministries": list(REQUIRED_MINISTRIES),
        "optional_aliases": list(OPTIONAL_ALIASES),
        "ministries": [],
    }
    for ministry in PILOTS:
        result = fetched.get(ministry) or {}
        entry = {
            "ministry": ministry,
            "required": ministry in REQUIRED_MINISTRIES,
            "included_in_canonical": ministry in REQUIRED_MINISTRIES,
        }
        if result.get("error"):
            entry["error"] = result["error"]
        else:
            norm = result.get("norm") or []
            meta = result.get("meta") or {}
            entry.update(
                {
                    "rows": len(norm),
                    "api_total": meta.get("total"),
                    "complete": not completeness_issues(
                        result.get("rows") or [], meta, expected_ministry=ministry
                    ),
                    "congress_sum_won": result.get("total_amt") or 0,
                    "sample": [x.get("detail_business_name") for x in norm[:5]],
                    "pages": len(meta.get("pages") or []),
                }
            )
        summary["ministries"].append(entry)

    # aggregate by detail business (sum mok/semok)
    detail_agg = {}
    for r in all_norm:
        keyp = (
            r.get("office_name"),
            r.get("account_name"),
            r.get("program_name"),
            r.get("unit_business_name"),
            r.get("detail_business_name"),
        )
        if keyp not in detail_agg:
            detail_agg[keyp] = {
                "year": year,
                "office_name": r.get("office_name"),
                "account_name": r.get("account_name"),
                "field_name": r.get("field_name"),
                "section_name": r.get("section_name"),
                "program_name": r.get("program_name"),
                "unit_business_name": r.get("unit_business_name"),
                "detail_business_name": r.get("detail_business_name"),
                "congress_amt": 0.0,
                "line_count": 0,
            }
        detail_agg[keyp]["congress_amt"] += float(r.get("congress_amt") or 0)
        detail_agg[keyp]["line_count"] += 1
    details = list(detail_agg.values())

    tree = tree_to_jsonable(build_tree(all_norm))
    # also detail-level tree without mok/semok
    tree_detail = tree_to_jsonable(build_tree([{**d, "mok_name": None, "semok_name": None} for d in details]))

    summary["total_lines"] = len(all_norm)
    summary["total_details"] = len(details)
    summary["total_amount_won"] = sum(d.get("congress_amt") or 0 for d in details)

    for ministry, result in fetched.items():
        if result.get("error"):
            continue
        atomic_write_json(
            RAW / f"{year}_{ministry}.json",
            {"meta": result["meta"], "rows": result["rows"]},
        )
    atomic_write_json(NORM / f"expbudgetadd2_{year}_pilots_lines.json", all_norm)
    atomic_write_json(NORM / f"expbudgetadd2_{year}_pilots_details.json", details, indent=2)
    atomic_write_json(NORM / f"expbudgetadd2_tree_{year}_pilots.json", tree_detail, indent=2)
    # These generic aliases are owned exclusively by the canonical Add2 fetcher.
    atomic_write_json(NORM / "detail_business_tree_pilots_latest.json", tree_detail, indent=2)
    atomic_write_json(NORM / "detail_business_pilots_latest.json", details, indent=2)
    atomic_write_json(DATA / f"fetch_summary_expbudgetadd2_{year}.json", summary, indent=2)
    atomic_write_json(DATA / "fetch_summary_latest.json", summary, indent=2)
    print("DONE lines", len(all_norm), "details", len(details), "amount", summary["total_amount_won"])


if __name__ == "__main__":
    main()
