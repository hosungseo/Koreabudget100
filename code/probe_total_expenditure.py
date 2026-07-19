#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEY = ""
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("OPENFISCAL_API_KEY="):
        KEY = line.split("=", 1)[1].strip()
        break

SERVICE = "https://openapi.openfiscaldata.go.kr/TotalExpenditure1"
UA = {"User-Agent": "Koreabudget100/0.1"}


def parse_payload(text: str) -> object:
    data = json.loads(text)
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            pass
    return data


def call(params: dict, lowercase_key: bool = False) -> object:
    if lowercase_key:
        q = {
            "key": KEY,
            "type": "json",
            "pindex": "1",
            "psize": "5",
        }
    else:
        q = {
            "Key": KEY,
            "Type": "json",
            "pIndex": "1",
            "pSize": "5",
        }
    for k, v in params.items():
        if v is not None:
            q[k] = str(v)
    url = SERVICE + "?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=45) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    return parse_payload(text)


def summarize(data: object) -> str:
    if not isinstance(data, dict):
        return "type=%s preview=%s" % (type(data).__name__, str(data)[:160])
    result = data.get("RESULT") if isinstance(data.get("RESULT"), dict) else {}
    code = result.get("CODE")
    msg = result.get("MESSAGE")
    rows = 0
    sample = None
    list_key = None
    for k, v in data.items():
        if k == "RESULT":
            continue
        if isinstance(v, list):
            rows = len(v)
            list_key = k
            if v and isinstance(v[0], dict):
                sample = {
                    "OFFC_NM": v[0].get("OFFC_NM"),
                    "SACTV_NM": v[0].get("SACTV_NM"),
                    "AMT": v[0].get("Y_YY_DFN_MEDI_KCUR_AMT"),
                    "keys": list(v[0].keys())[:15],
                }
            break
        if isinstance(v, dict):
            for kk, vv in v.items():
                if isinstance(vv, list):
                    rows = len(vv)
                    list_key = "%s.%s" % (k, kk)
                    if vv and isinstance(vv[0], dict):
                        sample = {
                            "OFFC_NM": vv[0].get("OFFC_NM"),
                            "SACTV_NM": vv[0].get("SACTV_NM"),
                            "AMT": vv[0].get("Y_YY_DFN_MEDI_KCUR_AMT"),
                            "keys": list(vv[0].keys())[:15],
                        }
                    break
    return "code=%s list=%s rows=%s msg=%s sample=%s" % (code, list_key, rows, msg, sample)


def main() -> None:
    trials = []
    for year in ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018"]:
        trials.append(({"FSCL_YY": year}, False))
        trials.append(({"FSCL_YY": year, "ANEXP_INQ_STND_CD": "1"}, False))
        trials.append(({"FSCL_YY": year, "ANEXP_INQ_STND_CD": "1", "BDG_FND_DIV_CD": "1"}, False))
        trials.append(({"FSCL_YY": year, "ANEXP_INQ_STND_CD": "2", "BDG_FND_DIV_CD": "1"}, False))
        trials.append(({"FSCL_YY": year, "OFFC_NM": "기획재정부", "ANEXP_INQ_STND_CD": "1", "BDG_FND_DIV_CD": "1"}, False))
        trials.append(({"FSCL_YY": year, "OFFC_NM": "행정안전부", "ANEXP_INQ_STND_CD": "1", "BDG_FND_DIV_CD": "1"}, False))
        trials.append(({"FSCL_YY": year, "OFFC_NM": "기획재정부", "ANEXP_INQ_STND_CD": "1", "BDG_FND_DIV_CD": "1"}, True))

    hits = []
    for params, lower in trials:
        try:
            data = call(params, lowercase_key=lower)
            line = summarize(data)
            print(("L " if lower else "  ") + str(params) + " => " + line)
            if "rows=" in line:
                n = int(line.split("rows=")[1].split(" ")[0])
                if n > 0:
                    hits.append({"params": params, "lower": lower, "summary": line})
                    out = ROOT / "data" / "raw" / "openfiscal" / "probe_hit.json"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_text(
                        json.dumps({"params": params, "lower": lower, "data": data}, ensure_ascii=False, indent=2)[:300000],
                        encoding="utf-8",
                    )
                    print("HIT saved", out)
                    break
        except Exception as exc:
            print("ERR", params, lower, exc)
    print("hits", len(hits))


if __name__ == "__main__":
    main()
