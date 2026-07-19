#!/usr/bin/env python3
from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://www.lofin365.go.kr/lf/hub"
CTX = ssl.create_default_context()
UA = {"User-Agent": "Koreabudget100/0.1"}


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
        "pSize": str(params.get("pSize", 5)),
    }
    for k, v in params.items():
        if k in ("pIndex", "pSize") or v in (None, ""):
            continue
        q[k] = str(v)
    url = f"{BASE}/{svc}?{urllib.parse.urlencode(q)}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, context=CTX, timeout=60) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    data = json.loads(text)
    if isinstance(data, str):
        data = json.loads(data)
    return data


def extract(payload):
    rows = []
    meta = {}
    if not isinstance(payload, dict):
        return rows, {"raw": str(payload)[:200]}
    if isinstance(payload.get("RESULT"), dict):
        meta["RESULT"] = payload["RESULT"]
    for key, val in payload.items():
        if key == "RESULT" or not isinstance(val, list):
            continue
        for item in val:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("head"), list):
                for h in item["head"]:
                    if not isinstance(h, dict):
                        continue
                    if "list_total_count" in h:
                        meta["total"] = h.get("list_total_count")
                    if isinstance(h.get("RESULT"), dict):
                        meta["RESULT"] = h["RESULT"]
            if isinstance(item.get("row"), list):
                rows.extend([r for r in item["row"] if isinstance(r, dict)])
        if rows:
            meta["list_key"] = key
            break
    return rows, meta


def main():
    key = load_key()
    details = json.loads(
        (ROOT / "data/normalized/detail_business_pilots_latest.json").read_text(
            encoding="utf-8"
        )
    )
    names = []
    for x in details:
        n = (x.get("detail_business_name") or "").strip()
        if n and n not in names:
            names.append(n)

    keywords = [
        "주거급여",
        "지방행정연구원",
        "무역보험",
        "스마트시티",
        "주택",
        "도로",
        "연구",
        "출연",
        "보조금",
        "SOC",
    ]
    for n in names[:40]:
        tok = n.replace(" ", "")
        if len(tok) >= 4:
            keywords.append(tok[:6])
            keywords.append(tok[:4])

    seen = set()
    kws = []
    for k in keywords:
        if k and k not in seen:
            seen.add(k)
            kws.append(k)

    print("unique_details", len(names))
    print("keywords", len(kws), kws[:15])

    hits = []
    for kw in kws[:20]:
        for ymd in ["20260701", "20260618", "20251231", "20241231"]:
            year = int(ymd[:4])
            payload = call(
                key,
                "QWGJK",
                {
                    "fyr": year,
                    "exe_ymd": ymd,
                    "dbiz_nm": kw,
                    "pSize": 5,
                },
            )
            rows, meta = extract(payload)
            code = (meta.get("RESULT") or {}).get("CODE")
            print(
                "KW",
                kw,
                ymd,
                "rows",
                len(rows),
                "total",
                meta.get("total"),
                "code",
                code,
            )
            if rows:
                hits.append(
                    {
                        "keyword": kw,
                        "exe_ymd": ymd,
                        "total": meta.get("total"),
                        "sample": rows[0],
                        "sample_keys": sorted(rows[0].keys()),
                    }
                )
                break
        if len(hits) >= 8:
            break

    out = {
        "mode": "QWGJK keyword matching via dbiz_nm",
        "note": "No region filter; local names vary so keyword match is intentional",
        "hits": hits,
    }
    out_path = ROOT / "data" / "raw" / "lofin" / "qwgjk_keyword_probe.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("hits", len(hits))
    print("wrote", out_path)
    for h in hits:
        s = h["sample"]
        print(
            "---",
            h["keyword"],
            h["exe_ymd"],
            "total",
            h["total"],
            "dbiz",
            s.get("dbiz_nm"),
            "laf",
            s.get("laf_hg_nm") or s.get("wa_laf_hg_nm"),
            "nat",
            s.get("bdg_ntep"),
        )


if __name__ == "__main__":
    main()
