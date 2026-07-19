#!/usr/bin/env python3
from __future__ import annotations

import json
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw" / "lofin"
NORM = DATA / "normalized"
UA = {"User-Agent": "Koreabudget100/0.1"}
CTX = ssl.create_default_context()
BASE = "https://www.lofin365.go.kr/lf/hub"


def load_key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("LOFIN365_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("LOFIN365_API_KEY missing")


def parse_payload(text: str):
    data = json.loads(text)
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            pass
    return data


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
        return parse_payload(resp.read().decode("utf-8", errors="replace"))


def extract_rows(payload):
    meta = {"payload_type": type(payload).__name__}
    rows = []
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
            if isinstance(item.get("head"), list):
                for h in item["head"]:
                    if isinstance(h, dict):
                        if "list_total_count" in h:
                            meta["list_total_count"] = h.get("list_total_count")
                        if isinstance(h.get("RESULT"), dict):
                            meta["RESULT"] = h["RESULT"]
            if isinstance(item.get("row"), list):
                rows.extend([r for r in item["row"] if isinstance(r, dict)])
        if rows:
            break
    if not rows:
        for key, val in payload.items():
            if key == "RESULT":
                continue
            if isinstance(val, list) and val and isinstance(val[0], dict):
                if any(("row" in x or "head" in x) for x in val if isinstance(x, dict)):
                    continue
                rows = [x for x in val if isinstance(x, dict)]
                meta["list_key"] = key
                break
    return rows, meta


def fetch_pages(key: str, svc: str, base_params: dict, max_pages: int = 20):
    all_rows = []
    pages = []
    psize = int(base_params.get("pSize", 100))
    for page in range(1, max_pages + 1):
        params = dict(base_params)
        params["pIndex"] = page
        params["pSize"] = psize
        payload = call(key, svc, params)
        rows, meta = extract_rows(payload)
        pages.append({"page": page, "n": len(rows), "meta": meta})
        if not rows:
            if page == 1:
                RAW.mkdir(parents=True, exist_ok=True)
                (RAW / f"debug_{svc}.json").write_text(
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
        time.sleep(0.15)
    return all_rows, pages


def page_api_total(pages: list[dict]) -> int | None:
    for page in pages:
        raw = (page.get("meta") or {}).get("list_total_count")
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def probe(key: str):
    hits = []
    seen = set()
    trials = []
    for year in [2026, 2025, 2024, 2023, 2022]:
        for ymd in [f"{year}1231", f"{year}0701", f"{year}0618", f"{year}1230"]:
            trials.append(
                (
                    "QWGJK",
                    {
                        "fyr": year,
                        "exe_ymd": ymd,
                        "wa_laf_cd": "1100000",
                        "pSize": 5,
                    },
                )
            )
        trials.append(("AIDFA", {"fyr": year, "wa_laf_cd": "1100000", "pSize": 5}))
        trials.append(("CDDFA", {"fyr": year, "pSize": 5}))

    for svc, params in trials:
        try:
            payload = call(key, svc, params)
            rows, meta = extract_rows(payload)
            code = None
            if isinstance(meta.get("RESULT"), dict):
                code = meta["RESULT"].get("CODE")
            print(
                "TRY",
                svc,
                params,
                "rows",
                len(rows),
                "code",
                code,
                "total",
                meta.get("list_total_count"),
            )
            if rows:
                keyname = f"{svc}:{json.dumps(params, sort_keys=True, ensure_ascii=False)}"
                if keyname in seen:
                    continue
                seen.add(keyname)
                hits.append(
                    {
                        "svc": svc,
                        "params": params,
                        "n": len(rows),
                        "sample": rows[0],
                        "meta": meta,
                    }
                )
                RAW.mkdir(parents=True, exist_ok=True)
                (RAW / f"probe_hit_{svc}.json").write_text(
                    json.dumps(
                        {"params": params, "rows": rows[:20], "meta": meta},
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                have_q = any(h["svc"] == "QWGJK" for h in hits)
                have_a = any(h["svc"] == "AIDFA" for h in hits)
                if have_q and have_a:
                    break
        except Exception as exc:
            print("ERR", svc, params, type(exc).__name__, exc)
    return hits


def main():
    key = load_key()
    RAW.mkdir(parents=True, exist_ok=True)
    NORM.mkdir(parents=True, exist_ok=True)
    print("probing lofin...")
    hits = probe(key)
    print("hits", len(hits))
    summary = {
        "scope": "pilot_partial",
        # This generic fetch intentionally caps pages and must never be treated as
        # a complete LOFIN dump by downstream integration code.
        "complete": False,
        "hits": [
            {"svc": h["svc"], "params": h["params"], "n": h["n"], "meta": h["meta"]}
            for h in hits
        ]
    }
    collected = {}
    qhits = [h for h in hits if h["svc"] == "QWGJK"]
    ahits = [h for h in hits if h["svc"] == "AIDFA"]
    if qhits:
        params = dict(qhits[0]["params"])
        params["pSize"] = 1000
        rows, pages = fetch_pages(key, "QWGJK", params, max_pages=5)
        collected["QWGJK"] = {"params": params, "rows": rows, "pages": pages}
        (RAW / "QWGJK_pilot.json").write_text(
            json.dumps(collected["QWGJK"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("QWGJK rows", len(rows))
    if ahits:
        params = dict(ahits[0]["params"])
        params["pSize"] = 1000
        rows, pages = fetch_pages(key, "AIDFA", params, max_pages=20)
        collected["AIDFA"] = {"params": params, "rows": rows, "pages": pages}
        (RAW / "AIDFA_pilot.json").write_text(
            json.dumps(collected["AIDFA"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("AIDFA rows", len(rows))

    norm = []
    for r in collected.get("QWGJK", {}).get("rows", []):
        norm.append(
            {
                "source": "lofin_QWGJK",
                "year": r.get("fyr"),
                "region_code": r.get("wa_laf_cd"),
                "region_name": r.get("wa_laf_hg_nm"),
                "local_gov_code": r.get("laf_cd"),
                "local_gov_name": r.get("laf_hg_nm"),
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
                "exe_ymd": r.get("exe_ymd"),
                "raw": r,
            }
        )
    (NORM / "lofin_detail_business_pilot.json").write_text(
        json.dumps(norm, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary["qwgjk_rows"] = len(norm)
    summary["aidfa_rows"] = len(collected.get("AIDFA", {}).get("rows", []))
    q_pages = collected.get("QWGJK", {}).get("pages", [])
    a_pages = collected.get("AIDFA", {}).get("pages", [])
    summary["qwgjk_api_total"] = page_api_total(q_pages)
    summary["aidfa_api_total"] = page_api_total(a_pages)
    # QWGJK is the detail-business collection represented by the normalized
    # pilot file, so expose its reported total at the top level as well.
    summary["api_total"] = summary["qwgjk_api_total"]
    (DATA / "lofin_fetch_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("wrote", DATA / "lofin_fetch_summary.json")


if __name__ == "__main__":
    main()
