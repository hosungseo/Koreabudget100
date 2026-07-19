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

NAMES = [
    "ExpendituresSettlement",
    "ExpenditureSettlement",
    "ExpndtrSettlement",
    "ExpendituresBudget",
    "ExpenditureBudget",
    "ExpndtrBudget",
    "Expenditures",
    "Expenditure",
    "BudgetExpenditure",
    "BudgetExpenditures",
    "DtlBsnsExpenditures",
    "DetailBusinessExpenditures",
    "ExpenditureDetailBusinessBudget",
    "ExpndtrDtlBsnsBudget",
    "SessExpenditureBudget",
    "SessExpendituresBudget",
    "AncmExpenditureBudget",
    "AncmExpendituresBudget",
    "LqdnExpenditureBudget",
    "LqdnExpendituresBudget",
    "TotalExpenditureBudget",
    "TotalExpndtrBudget",
    "TotExpndtrBudget",
    "TotExpenditureBudget",
    "ExpenditureBudgetCompile",
    "ExpndtrBudgetCompile",
    "BusinessBudget",
    "BizBudget",
    "ProgramBudget",
    "UnitBusinessBudget",
    "ActvBudget",
    "CitmBudget",
]


def call(name: str, params: dict) -> tuple[str, int | None, str]:
    url = f"https://openapi.openfiscaldata.go.kr/{name}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = resp.read(800).decode("utf-8", errors="replace")
            return "OK", resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read(500).decode("utf-8", errors="replace")
        return "HTTP", e.code, body
    except Exception as e:  # noqa: BLE001
        return "ERR", None, f"{type(e).__name__}: {e}"


def main() -> None:
    base = {"Key": KEY, "Type": "json", "pIndex": "1", "pSize": "3", "FSCL_YY": "2026"}
    # also lowercase key variants used in SAS sample
    variants = [
        base,
        {"key": KEY, "type": "json", "pindex": "1", "psize": "3", "FSCL_YY": "2026"},
        {"Key": KEY, "Type": "json", "pIndex": "1", "pSize": "3"},
    ]
    hits = []
    for name in NAMES:
        for params in variants:
            status, code, body = call(name, params)
            if "ERROR-310" in body:
                continue
            hits.append(
                {
                    "name": name,
                    "params": list(params),
                    "status": status,
                    "code": code,
                    "body": body[:300],
                }
            )
            print("HIT", name, status, code, re.sub(r"\s+", " ", body)[:220])
            break
    print("hits", len(hits))
    out = ROOT / "data" / "openfiscal_known_hits.json"
    out.write_text(json.dumps(hits, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
