#!/usr/bin/env python3
from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
UA = {"User-Agent": "Koreabudget100/0.1 (+local research)"}


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def mask(v: str) -> str:
    if len(v) <= 10:
        return "***"
    return f"{v[:6]}...{v[-4:]} (len={len(v)})"


def fetch(url: str, timeout: float = 12.0) -> tuple[str, int | None, str]:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(1500).decode("utf-8", errors="replace")
            return "OK", resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read(800).decode("utf-8", errors="replace")
        return "HTTP", e.code, body
    except Exception as e:  # noqa: BLE001
        return "ERR", None, f"{type(e).__name__}: {e}"


def snip(body: str, n: int = 220) -> str:
    return re.sub(r"\s+", " ", body)[:n]


def main() -> None:
    env = load_env(ENV)
    openf = env.get("OPENFISCAL_API_KEY", "")
    lofin = env.get("LOFIN365_API_KEY", "")
    print("OPENFISCAL", mask(openf))
    print("LOFIN365", mask(lofin))

    paths = [
        "https://openapi.openfiscaldata.go.kr/ExpenditureBudget",
        "https://openapi.openfiscaldata.go.kr/ExpndtrBudget",
        "https://openapi.openfiscaldata.go.kr/AncmExpndtrBudget",
        "https://openapi.openfiscaldata.go.kr/FiscalBusiness",
        "https://openapi.openfiscaldata.go.kr/TrmnDtlBsns",
        "https://openapi.openfiscaldata.go.kr/DetailBusinessBudget",
    ]
    param_sets = [
        {"Key": openf, "Type": "json", "pIndex": "1", "pSize": "3", "FSCL_YY": "2026"},
        {"ServiceKey": openf, "Type": "json", "pIndex": "1", "pSize": "3", "FSCL_YY": "2026"},
        {"serviceKey": openf, "type": "json", "pageNo": "1", "numOfRows": "3", "fsclYy": "2026"},
    ]

    print("\n=== Open Fiscal ===")
    hits = 0
    for path in paths:
        found = False
        for params in param_sets:
            url = f"{path}?{urllib.parse.urlencode(params)}"
            status, code, body = fetch(url)
            interesting = False
            if status == "OK" and (
                body.strip().startswith("{")
                or body.strip().startswith("[")
                or "RESULT" in body.upper()
                or "inf" in body.lower()
            ):
                interesting = True
            if status == "HTTP" and code in {400, 401, 500}:
                interesting = True
            if interesting:
                print(f"{status} {code} | {path}")
                print(" ", snip(body))
                hits += 1
                found = True
                break
        if not found:
            # last try summary
            status, code, body = fetch(f"{path}?{urllib.parse.urlencode(param_sets[0])}")
            print(f"MISS {status} {code} | {path} | {snip(body, 120)}")
    print("hits:", hits)

    print("\n=== Lofin ===")
    tests = [
        f"https://www.lofin365.go.kr/openApi.do?{urllib.parse.urlencode({'serviceKey': lofin, 'pageIndex': 1, 'pageSize': 3})}",
        f"https://lofin.mois.go.kr/openApi.do?{urllib.parse.urlencode({'serviceKey': lofin})}",
        "https://www.lofin365.go.kr/portal/LF5110000.do?curPage=9&pdtaId=0GAR4HBB8LWEBSL4NIHZ817053&rdIncrYn=Y&frstParamYn=Y",
    ]
    for url in tests:
        status, code, body = fetch(url)
        print(f"{status} {code} | {url.split('?')[0]}")
        print(" ", snip(body))


if __name__ == "__main__":
    main()
