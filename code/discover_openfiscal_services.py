#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEY = None
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("OPENFISCAL_API_KEY="):
        KEY = line.split("=", 1)[1].strip()
        break

UA = {"User-Agent": "Koreabudget100/0.1"}


def call(name: str) -> tuple[str, int | None, str]:
    params = {
        "Key": KEY,
        "Type": "json",
        "pIndex": "1",
        "pSize": "2",
        "FSCL_YY": "2026",
    }
    url = f"https://openapi.openfiscaldata.go.kr/{name}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = resp.read(600).decode("utf-8", errors="replace")
            return "OK", resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read(400).decode("utf-8", errors="replace")
        return "HTTP", e.code, body
    except Exception as e:  # noqa: BLE001
        return "ERR", None, f"{type(e).__name__}: {e}"


NAMES = [
    # common openfiscal path styles
    "ExpenditureBudget",
    "ExpndtrBudget",
    "AncmExpndtrBudget",
    "LqdnExpndtrBudget",
    "ExpndtrBudgetInfo",
    "DetailBusinessBudget",
    "DtlBsnsBudget",
    "DtlBsnsBdg",
    "ExpndtrDtlBsns",
    "ExpenditureDetailBusiness",
    "SessDtlBsnsBudget",
    "SessExpndtrBudget",
    "SessExpndtrDtlBsns",
    "OpenApiExpndtrBudget",
    "VwOpenApiExpndtrBudget",
    "ExpenditureBudgetStatus",
    "ExpndtrBudgetTotal",
    "ExpndtrBudgetTotExpnd",
    "DtlBizBudget",
    "DtlBizExpndtr",
    # total amount / total expenditure variants
    "ExpenditureBudgetTotAmt",
    "ExpenditureBudgetTotExpndtr",
    "ExpndtrBudgetTotAmt",
    "ExpndtrBudgetTotExpndtr",
    "DtlBsnsBudgetTotAmt",
    "DtlBsnsBudgetTotExpndtr",
    "SessDtlBsnsBudgetTotAmt",
    "SessDtlBsnsBudgetTotExpndtr",
    # korean-ish
    "SebuSaeopYesan",
    "YesanPyeonseong",
    "BudgetCompileDetail",
    # ids sometimes used
    "FSAS",
    "FSAS01",
    "CMP02_010101",
]


def main() -> None:
    print("key_len", len(KEY or ""))
    hits = []
    for name in NAMES:
        status, code, body = call(name)
        if "ERROR-310" in body:
            continue
        hits.append((name, status, code, body[:240]))
        print("HIT", name, status, code, re.sub(r"\s+", " ", body)[:200])
    print("hits", len(hits))
    out = ROOT / "data" / "openfiscal_service_discovery.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(hits, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
