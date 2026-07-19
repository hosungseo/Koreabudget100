#!/usr/bin/env python3
"""Discover Open Fiscal OpenAPI request URLs via site internal endpoints."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "openfiscal_api_meta.json"
UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Koreabudget100/0.1",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json;charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://www.openfiscaldata.go.kr",
    "Referer": "https://www.openfiscaldata.go.kr/op/ko/ds/UOPKODSA06",
}

# From Open API list search "세부사업"
ODT_CANDIDATES = [
    "76UC47ZA3U6HHNJ7260UD5O8H",  # opened from list
]


def post_json(url: str, payload: dict) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=UA, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


def get_text(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


def extract_odt_ids_from_list_page() -> list[str]:
    # Search page is JS-rendered; try common list AJAX endpoints later.
    return list(ODT_CANDIDATES)


def try_meta(odt_id: str) -> dict:
    endpoints = [
        "https://www.openfiscaldata.go.kr/op/ko/sd/dtsStatsAcol/selectAcolViewList.do",
        "https://www.openfiscaldata.go.kr/op/ko/ds/selectOpenApiDetail.do",
        "https://www.openfiscaldata.go.kr/op/ko/ds/selectApiInfo.do",
        "https://www.openfiscaldata.go.kr/op/ko/sd/selectOpenApiInfo.do",
    ]
    payloads = [
        {"odtId": odt_id},
        {"odtId": odt_id, "rlsSvTyCd": "A"},
        {"odtId": odt_id, "rlsSvTyCd": "S"},
        {"odtId": odt_id, "odtSvSeq": "1"},
        {"odtId": odt_id, "rlsSvTyCd": "A", "odtSvSeq": "1"},
        {"paramVO": {"odtId": odt_id}},
        {"paramVO": {"odtId": odt_id, "rlsSvTyCd": "A"}},
        {"paramVO": {"odtId": odt_id, "rlsSvTyCd": "A", "odtSvSeq": 1}},
        {"S_odtId": odt_id, "S_rlsSvTyCd": "A"},
        {"searchVO": {"odtId": odt_id}},
    ]
    results = []
    for ep in endpoints:
        for payload in payloads:
            code, body = post_json(ep, payload)
            interesting = False
            if "dmndUrl" in body and '"dmndUrl":null' not in body:
                interesting = True
            if "openapi.openfiscaldata.go.kr" in body:
                interesting = True
            if code == 200 and body.strip().startswith("{") and "selectApiRes" in body:
                # keep compact always for first few
                interesting = interesting or True
            if interesting:
                results.append(
                    {
                        "endpoint": ep,
                        "payload": payload,
                        "status": code,
                        "body_head": body[:2500],
                    }
                )
                # stop early if we got a real URL
                if "openapi.openfiscaldata.go.kr" in body or re.search(
                    r'"dmndUrl"\s*:\s*"https?://', body
                ):
                    return {"odtId": odt_id, "hits": results, "found": True}
    return {"odtId": odt_id, "hits": results[:8], "found": False}


def probe_services() -> list[dict]:
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    key = env.get("OPENFISCAL_API_KEY", "")

    names = [
        "ExpendituresSettlement",
        "ExpenditureBudget",
        "ExpndtrBudget",
        "AncmExpndtrBudget",
        "LqdnExpndtrBudget",
        "ExpendituresBudget",
        "DetailBusinessBudget",
        "DtlBsnsBudget",
        "SessDtlBsnsBudget",
        "ExpenditureDetailBusiness",
        "ExpndtrDtlBsns",
        "BudgetDetailBusiness",
        "DtlBizBudget",
        "FiscalBusinessBudget",
        "TrmnDtlBsns",
        "LqdnDtlBsns",
        "AncmDtlBsns",
        "SessExpndtrBudget",
        "SessExpenditureBudget",
        "TotalExpenditureBudget",
        "TotExpndtrBudget",
        "ExpndtrBudgetTot",
        "ExpndtrBudgetTotal",
        "ExpenditureBudgetTotal",
        "ExpenditureBudgetTotAmt",
        "ExpndtrBudgetTotAmt",
        "DtlBsnsBudgetTotAmt",
        "DtlBsnsBudgetTotExpndtr",
        "SessDtlBsnsBudgetTotAmt",
        "SessDtlBsnsBudgetTotExpndtr",
        "VwOpenApiExpndtrBudget",
        "OpenApiExpndtrBudget",
        "CMP02010101",
        "CMP02_010101",
    ]
    hits = []
    for name in names:
        for year in ("2024", "2025", "2026", "2023"):
            params = {
                "Key": key,
                "Type": "json",
                "pIndex": "1",
                "pSize": "5",
                "FSCL_YY": year,
            }
            url = f"https://openapi.openfiscaldata.go.kr/{name}?{urllib.parse.urlencode(params)}"
            code, body = get_text(url)
            if "ERROR-310" in body:
                break  # service missing
            item = {
                "service": name,
                "year": year,
                "status": code,
                "body": body[:300],
            }
            hits.append(item)
            # if service exists, try next year too, but print once
            if "INFO-000" in body or '"row"' in body.lower() or "OFFC_NM" in body:
                break
            if "INFO-200" in body:
                continue
            break
    return hits


def main() -> None:
    odt_ids = extract_odt_ids_from_list_page()
    meta = [try_meta(oid) for oid in odt_ids]
    service_hits = probe_services()
    out = {
        "meta": meta,
        "service_hits": service_hits,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT)
    print("meta_found", any(m.get("found") for m in meta))
    print("service_hits", len(service_hits))
    for h in service_hits[:20]:
        print(h["service"], h["year"], h["status"], re.sub(r"\s+", " ", h["body"])[:120])


if __name__ == "__main__":
    main()
