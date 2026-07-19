#!/usr/bin/env python3
"""Fetch lofin365 QWGJK by keyword (dbiz_nm) for local-gov national-fund tracing.

Correction 2026-07-19:
- Local finance is NOT impossible.
- Each dataset has its own hub code; QWGJK = detail business expenditure status.
- Required: Key, Type, pIndex, pSize, fyr, exe_ymd
- Optional: dbiz_nm (keyword), laf_cd, wa_laf_cd
- Response is usually single JSON (not double-encoded).
- Local business names vary; use keyword matching.
- laf_cd 7-digit AA BBB CC; BBB(code[2:5])==000 => wide-area HQ else basic local gov.
- bdg_ntep = national funds reflected in local budget.
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw" / "lofin"
NORM = DATA / "normalized"
ART = ROOT / "artifacts"
BASE = "https://www.lofin365.go.kr/lf/hub"
UA = {"User-Agent": "Koreabudget100/0.1"}
CTX = ssl.create_default_context()


def load_key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("LOFIN365_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("LOFIN365_API_KEY missing")


def call(key: str, svc: str, params: dict):
    q = {
        "Key": key,
        "Type": "json",
        "pIndex": str(params.get("pIndex", 1)),
        "pSize": str(params.get("pSize", 100)),
    }
    for k, v in params.items():
        if k in ("pIndex", "pSize") or v in (None, ""):
            continue
        q[k] = str(v)
    url = f"{BASE}/{svc}?{urllib.parse.urlencode(q)}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, context=CTX, timeout=90) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    data = json.loads(text)
    if isinstance(data, str):
        data = json.loads(data)
    return data


def extract_rows(payload):
    rows = []
    meta = {"payload_type": type(payload).__name__}
    if not isinstance(payload, dict):
        meta["raw_preview"] = str(payload)[:300]
        return rows, meta
    if isinstance(payload.get("RESULT"), dict) and len(payload) == 1:
        meta["RESULT"] = payload["RESULT"]
        return rows, meta
    for key, val in payload.items():
        if key == "RESULT" or not isinstance(val, list):
            continue
        meta["list_key"] = key
        for item in val:
            if not isinstance(item, dict):
                continue
            head = item.get("head")
            if isinstance(head, list):
                for h in head:
                    if not isinstance(h, dict):
                        continue
                    if "list_total_count" in h:
                        meta["list_total_count"] = h.get("list_total_count")
                    if isinstance(h.get("RESULT"), dict):
                        meta["RESULT"] = h["RESULT"]
            row = item.get("row")
            if isinstance(row, list):
                rows.extend([r for r in row if isinstance(r, dict)])
        if rows:
            break
    return rows, meta


def fetch_all(key: str, params: dict, max_pages: int = 50):
    all_rows = []
    pages = []
    psize = int(params.get("pSize", 1000))
    for page in range(1, max_pages + 1):
        p = dict(params)
        p["pIndex"] = page
        p["pSize"] = psize
        payload = call(key, "QWGJK", p)
        rows, meta = extract_rows(payload)
        pages.append({"page": page, "n": len(rows), "meta": meta})
        if not rows:
            if page == 1:
                RAW.mkdir(parents=True, exist_ok=True)
                safe = str(params.get("dbiz_nm", "none")).replace("/", "_")[:40]
                (RAW / f"debug_QWGJK_{safe}.json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2)[:200000],
                    encoding="utf-8",
                )
            break
        all_rows.extend(rows)
        total = meta.get("list_total_count")
        try:
            total = int(total) if total is not None else None
        except Exception:
            total = None
        if total is not None and len(all_rows) >= total:
            break
        if len(rows) < psize:
            break
        time.sleep(0.12)
    return all_rows, pages


def classify_local(laf_cd):
    code = re.sub(r"\D", "", str(laf_cd or ""))
    if len(code) >= 5:
        if code[2:5] == "000":
            return "광역본청"
        return "기초"
    if code:
        return "unknown"
    return "unknown"


def normalize_row(r, keyword):
    laf_cd = r.get("laf_cd")
    return {
        "source": "lofin_QWGJK",
        "match_mode": "keyword_dbiz_nm",
        "keyword": keyword,
        "year": r.get("fyr"),
        "exe_ymd": r.get("exe_ymd"),
        "region_code": r.get("wa_laf_cd"),
        "region_name": r.get("wa_laf_hg_nm"),
        "local_gov_code": laf_cd,
        "local_gov_name": r.get("laf_hg_nm"),
        "local_level": classify_local(laf_cd),
        "account_name": r.get("acnt_dv_nm"),
        "detail_business_name": r.get("dbiz_nm"),
        "detail_business_code": r.get("dbiz_cd"),
        "field_name": r.get("fld_nm"),
        "section_name": r.get("part_nm") or r.get("sect_nm"),
        "budget_cash_amt": r.get("bdg_cash_amt"),
        "national_amt": r.get("bdg_ntep"),
        "sido_amt": r.get("capep"),
        "sigungu_amt": r.get("sggep"),
        "spend_amt": r.get("ep_amt"),
        "compile_amt": r.get("cpl_amt"),
        "raw": r,
    }


def summarize(rows):
    by_level = defaultdict(lambda: {"count": 0, "national_amt": 0.0})
    by_name = defaultdict(lambda: {"count": 0, "national_amt": 0.0, "level": None})
    total_nat = 0.0
    names = set()
    for r in rows:
        lvl = r.get("local_level") or "unknown"
        nat = float(r.get("national_amt") or 0)
        total_nat += nat
        by_level[lvl]["count"] += 1
        by_level[lvl]["national_amt"] += nat
        name = r.get("local_gov_name") or "?"
        by_name[name]["count"] += 1
        by_name[name]["national_amt"] += nat
        by_name[name]["level"] = lvl
        if r.get("detail_business_name"):
            names.add(r["detail_business_name"])
    top = sorted(by_name.items(), key=lambda kv: kv[1]["national_amt"], reverse=True)[:30]
    return {
        "row_count": len(rows),
        "national_amt_sum": total_nat,
        "by_level": dict(by_level),
        "top_local_govs": [{"name": k, **v} for k, v in top],
        "sample_names": sorted(names)[:40],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--exe-ymd", default="20260630")
    ap.add_argument("--keyword", action="append", dest="keywords")
    ap.add_argument("--psize", type=int, default=1000)
    ap.add_argument("--max-pages", type=int, default=50)
    args = ap.parse_args()

    keywords = args.keywords or ["사회연대경제", "주거급여", "스마트시티"]
    key = load_key()
    RAW.mkdir(parents=True, exist_ok=True)
    NORM.mkdir(parents=True, exist_ok=True)
    ART.mkdir(parents=True, exist_ok=True)

    all_norm = []
    report = {
        "service": "QWGJK",
        "endpoint": f"{BASE}/QWGJK",
        "year": args.year,
        "exe_ymd": args.exe_ymd,
        "match_mode": "keyword_dbiz_nm",
        "note": (
            "Local names vary; keyword matching intentional. "
            "bdg_ntep=national funds reflected locally. "
            "Previous lofin-impossible conclusion is corrected."
        ),
        "keywords": [],
    }

    for kw in keywords:
        params = {
            "fyr": args.year,
            "exe_ymd": args.exe_ymd,
            "dbiz_nm": kw,
            "pSize": args.psize,
        }
        print("FETCH", kw, params)
        rows, pages = fetch_all(key, params, max_pages=args.max_pages)
        norm = [normalize_row(r, kw) for r in rows]
        all_norm.extend(norm)
        safe = kw.replace("/", "_")[:40]
        (RAW / f"QWGJK_kw_{safe}_{args.exe_ymd}.json").write_text(
            json.dumps({"params": params, "pages": pages, "rows": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        summary = summarize(norm)
        report["keywords"].append({
            "keyword": kw,
            "params": params,
            "pages": pages,
            "summary": summary,
        })
        print("  rows", summary["row_count"], "national_sum", summary["national_amt_sum"], "levels", summary["by_level"])
        if summary["sample_names"]:
            print("  sample dbiz", summary["sample_names"][:8])
        if summary["top_local_govs"]:
            print("  top", [(x["name"], x["national_amt"], x["level"]) for x in summary["top_local_govs"][:8]])

    (NORM / "lofin_qwgjk_keyword_matches.json").write_text(
        json.dumps(all_norm, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (DATA / "lofin_keyword_fetch_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ART / "lofin_keyword_fetch_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("wrote", NORM / "lofin_qwgjk_keyword_matches.json")
    print("total_norm", len(all_norm))


if __name__ == "__main__":
    main()
