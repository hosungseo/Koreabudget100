#!/usr/bin/env python3
from __future__ import annotations

import ssl
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "pdfs"
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}
CTX = ssl.create_default_context()

FILES = [
    (
        "mois/mois_2026_budget_explainer.pdf",
        "https://www.mois.go.kr/cmm/fms/FileDown.do?atchFileId=FILE_00142213YDPOPGP&fileSn=0",
        "https://www.mois.go.kr/frt/bbs/type001/commonSelectBoardArticle.do?bbsId=BBSMSTR_000000000031&nttId=123327",
    ),
    (
        "molit/molit_2026_budget.pdf",
        "https://www.molit.go.kr/LCMS/DWN.jsp?fold=/IN0103_B/&fileName=1.+2026%EB%85%84+%EC%82%AC%EC%97%85%EB%B3%84+%EC%84%A4%EB%AA%85%EC%9E%90%EB%A3%8C%28%EC%98%88%EC%82%B0%29_%EA%B5%AD%ED%86%A0%EA%B5%90%ED%86%B5%EB%B6%802.pdf",
        "https://www.molit.go.kr/USR/BORD0201/m_34879/DTL.jsp?mode=view&idx=31111",
    ),
    (
        "molit/molit_2026_rnd_info.pdf",
        "https://www.molit.go.kr/LCMS/DWN.jsp?fold=/IN0103_B/&fileName=2.+2026%EB%85%84+%EC%82%AC%EC%97%85%EB%B3%84+%EC%84%A4%EB%AA%85%EC%9E%90%EB%A3%8C%28R_D%2C+%EC%A0%95%EB%B3%B4%ED%99%94%29_%EA%B5%AD%ED%86%A0%EA%B5%90%ED%86%B5%EB%B6%80.pdf",
        "https://www.molit.go.kr/USR/BORD0201/m_34879/DTL.jsp?mode=view&idx=31111",
    ),
    (
        "molit/molit_2026_fund.pdf",
        "https://www.molit.go.kr/LCMS/DWN.jsp?fold=/IN0103_B/&fileName=3.+2026%EB%85%84+%EC%82%AC%EC%97%85%EB%B3%84+%EC%84%A4%EB%AA%85%EC%9E%90%EB%A3%8C%28%EA%B8%B0%EA%B8%88%29_%EA%B5%AD%ED%86%A0%EA%B5%90%ED%86%B5%EB%B6%80.pdf",
        "https://www.molit.go.kr/USR/BORD0201/m_34879/DTL.jsp?mode=view&idx=31111",
    ),
    (
        "motir/motir_2026_1_gijo.pdf",
        "https://www.motir.go.kr/attach/down/9d1310a06d8b72194692f5f443143824/01ad6125c39401d80fdad94fb60c2755/9a9db098b587ee18b321c826f3707a49",
        "https://www.motir.go.kr/kor/article/ATCL3f70bb6cf/48/view",
    ),
    (
        "motir/motir_2026_2_saneop_policy.pdf",
        "https://www.motir.go.kr/attach/down/9d1310a06d8b72194692f5f443143824/01ad6125c39401d80fdad94fb60c2755/778bdbf5db9ced7c8fd52756c00bf0cd",
        "https://www.motir.go.kr/kor/article/ATCL3f70bb6cf/48/view",
    ),
    (
        "motir/motir_2026_3_saneop_growth.pdf",
        "https://www.motir.go.kr/attach/down/9d1310a06d8b72194692f5f443143824/01ad6125c39401d80fdad94fb60c2755/13055e35ba7465cb478c5b4be490c5a8",
        "https://www.motir.go.kr/kor/article/ATCL3f70bb6cf/48/view",
    ),
    (
        "motir/motir_2026_4_resource_security.pdf",
        "https://www.motir.go.kr/attach/down/9d1310a06d8b72194692f5f443143824/01ad6125c39401d80fdad94fb60c2755/007d741c7b5aa2f9ec3e7211ce70c950",
        "https://www.motir.go.kr/kor/article/ATCL3f70bb6cf/48/view",
    ),
    (
        "motir/motir_2026_5_trade.pdf",
        "https://www.motir.go.kr/attach/down/9d1310a06d8b72194692f5f443143824/01ad6125c39401d80fdad94fb60c2755/debc2e19d8870bf491bf5e73464259e8",
        "https://www.motir.go.kr/kor/article/ATCL3f70bb6cf/48/view",
    ),
]


def download(rel: str, url: str, referer: str) -> None:
    out = OUT / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_size > 10000 and out.read_bytes()[:4] == b"%PDF":
        print("SKIP", rel, out.stat().st_size)
        return
    req = urllib.request.Request(url, headers={**UA, "Referer": referer})
    with urllib.request.urlopen(req, context=CTX, timeout=180) as resp:
        data = resp.read()
        ctype = resp.headers.get("Content-Type", "")
        print("GET", rel, resp.status, len(data), ctype[:80], "sig", data[:8])
        out.write_bytes(data)


def main() -> None:
    for rel, url, referer in FILES:
        try:
            download(rel, url, referer)
        except Exception as exc:  # noqa: BLE001
            print("ERR", rel, type(exc).__name__, exc)
    print("--- summary ---")
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            print(p.relative_to(OUT), p.stat().st_size, p.read_bytes()[:4])


if __name__ == "__main__":
    main()
