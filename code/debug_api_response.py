#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("OPENFISCAL_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("missing key")


def main() -> None:
    key = load_key()
    params = {
        "Key": key,
        "Type": "json",
        "pIndex": "1",
        "pSize": "3",
        "FSCL_YY": "2026",
        "OFFC_NM": "행정안전부",
        "ANEXP_INQ_STND_CD": "1",
        "BDG_FND_DIV_CD": "1",
    }
    url = "https://openapi.openfiscaldata.go.kr/TotalExpenditure1?" + urllib.parse.urlencode(params)
    print("URL", url.replace(key, "***"))
    req = urllib.request.Request(url, headers={"User-Agent": "Koreabudget100/0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
        status = resp.status
    text = raw.decode("utf-8", errors="replace")
    print("status", status, "len", len(raw))
    print(text[:2000])
    data = json.loads(text)
    print("type", type(data).__name__)
    if isinstance(data, dict):
        print("keys", list(data.keys())[:40])
        for k, v in data.items():
            tname = type(v).__name__
            extra = ""
            if isinstance(v, list):
                extra = f" len={len(v)}"
                if v:
                    extra += f" first_type={type(v[0]).__name__} first={str(v[0])[:250]}"
            elif isinstance(v, dict):
                extra = f" keys={list(v.keys())[:20]}"
            elif isinstance(v, str):
                extra = f" val={v[:120]}"
            print(f"  {k}: {tname}{extra}")
    elif isinstance(data, list):
        print("list_len", len(data))
        if data:
            print("first", str(data[0])[:400])


if __name__ == "__main__":
    main()
