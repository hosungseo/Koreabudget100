# API Notes

## 열린재정 (핵심)

### ExpenditureBudgetAdd2  ← 2026 세출 세목 예산편성현황 (확정)
- Endpoint (portal preview proxy):
  `POST https://www.openfiscaldata.go.kr/openApi/preview/ExpenditureBudgetAdd2`
- Official openapi host may 400/307 from some environments; preview proxy works with Key + browser UA.
- Auth: JSON body `Key`
- Params: `Type=json`, `pIndex`, `pSize`(max 1000), `FSCL_YY`, optional `OFFC_NM`/`PGM_NM`/`ACTV_NM`/`SACTV_NM`
- Response: **double-encoded JSON string** → parse twice
- Rows path: `data["ExpenditureBudgetAdd2"][1]["row"]`
- Total: `data["ExpenditureBudgetAdd2"][0]["head"][0]["list_total_count"]`
- Amount field (기준): `Y_YY_DFN_KCUR_AMT` 본예산 확정액 **천원**
- Hierarchy: OFFC_NM → FSCL_NM → PGM_NM → ACTV_NM → SACTV_NM → CITM_NM(목) → EITM_NM(세목)

### TotalExpenditure1
- Still valid for older years (confirmed 2022). 2023–2026 empty as of 2026-07-19.
- Endpoint: `https://openapi.openfiscaldata.go.kr/TotalExpenditure1`

### Pilot fetch (2026 ExpenditureBudgetAdd2)
- 행정안전부 3,312 lines / 76,905,548,000,000원
- 국토교통부 3,770 lines / 45,018,494,000,000원
- 산업통상부 2,268 lines / 11,622,629,000,000원
- 산업통상자원부(구명칭) 0
- Aggregated unique detail businesses: 1,401
- Total amount (3 ministries): 133,546,671,000,000원

## 지방재정365 (정정 완료 · 2026-07-19)

### 핵심 정정
- 이전 “지방재정365 불가능” 판단은 **오판**.
- 열린재정과 패턴이 다름: 서비스명 통일 API가 아니라 **데이터셋마다 고유 짧은 hub 코드**.
- 예: `QWGJK` = 세부사업별 세출현황, `UCMZQA` 등 다른 코드도 존재.
- 메뉴/카탈로그는 사이트 내부 API(`/menu/list.do` 등)로 목록 확인 가능.
- 응답은 보통 **단일 JSON** (`json.loads` 1회). 열린재정처럼 이중 JSON 아님.

### Base
- `GET https://www.lofin365.go.kr/lf/hub/{svcCd}`
- Auth query param: `Key`
- Common: `Type=json`, `pIndex`, `pSize`(max 1000)

### QWGJK · 세부사업별 세출현황 (핵심)
- Endpoint: `https://www.lofin365.go.kr/lf/hub/QWGJK`
- Required:
  - `fyr` 회계연도 (예: 2026)
  - `exe_ymd` 집행일자 `YYYYMMDD` (**필수**, 없으면 ERROR-300)
    - 스냅샷 시점으로 보이며 `20260101`, `20260630` 등 여러 값 가능
- Optional:
  - `dbiz_nm` 세부사업명 **키워드**
  - `laf_cd` 자치단체코드
  - `wa_laf_cd` 광역코드
- 전국 규모: exe_ymd에 따라 **수십만 건** (예: 41만+ 언급/실측)
- 금액 필드:
  - `bdg_ntep` = **국비** (지자체 예산에 반영된 국비)
  - 기타: `bdg_cash_amt`, `capep`(시도비), `sggep`(시군구비), `ep_amt` 등
- 자치단체 구분:
  - `laf_hg_nm`: 서울본청 / 서울종로구 등
  - `laf_cd` 7자리 `AA BBB CC`에서 **BBB(`code[2:5]`)=`000` → 광역 본청**, 아니면 기초
  - 주의: `endswith('000')` 쓰면 기초(종로구 1111000, 강화군 2871000 등)까지 광역으로 오분류됨
- **매칭 방식**: 국가 세부사업명과 문자열 완전일치 불가.
  - 지자체마다 사업명 표기가 다름
  - 반드시 `dbiz_nm` **키워드 매칭**으로 접근
  - 예: `dbiz_nm=사회연대경제` → 대구본청/인천본청/대전중구/인천강화군 등 국비 반영분 추적

### curl 예시
```bash
curl "https://www.lofin365.go.kr/lf/hub/QWGJK?Key=<키>&Type=json&pIndex=1&pSize=10&fyr=2026&exe_ymd=20260630&dbiz_nm=사회연대경제"
```

### Other confirmed / useful
- `AIDFA` 구조별 기능별 세출예산 (`fyr` 중심)
- 수집 스크립트:
  - `code/fetch_lofin.py` (초기 probe/region pilot)
  - `code/fetch_lofin_keyword.py` (수동 키워드 진단)
  - `code/fetch_lofin_local_transfer_candidates.py` (**Add2 지자체 이전 양수사업 선택 수집 본선**)

### Catalog source
- API catalog reference: `https://github.com/yangheeseok1/lofin-api-mcp` (146 APIs; local mirror is not published in this repository)
- plus live menu discovery on lofin365

## PDF business explainers
- MOIS 2026: 2,170쪽 / 285카드
- MOLIT 2026 (budget/R&D/fund): 4,558쪽 / 505카드
- 합계: 4개 PDF / 6,728쪽 / 790카드
- MOTIR 2026: `/attach/down/...` 404/500, 공식 뷰어 한 권도 후반 페이지 누락. Add2 정본만 포함하고 PDF는 `api_only`로 명시

## Architecture implication
- Central budget tree (열린재정 ExpenditureBudgetAdd2) shows national program/detail structure + amount.
- Local finance QWGJK keyword search can resolve **where national funds were reflected** across wide-area HQ and basic local governments.
- Use this to turn “미배분/광역·기초 미상” buckets into concrete `laf_hg_nm` recipients when names can be keyword-linked.


### Verified keyword pilots (2026-07-19, exe_ymd=20260630)
- `사회연대경제`: 24 rows, national reflection sum ≈ 132.3억
  - 광역본청 17 / 기초 7 (인천강화군, 대전중구, 경기광명시, 강원평창군 등)
- `주거급여`: 297 rows, national reflection sum ≈ 6.26조
  - 광역본청 18 / 기초 279
- 두 합계 모두 광역·기초 단계 중복을 포함할 수 있어 재정 총액이 아님
- Outputs:
  - `data/normalized/lofin_qwgjk_keyword_matches.json`
  - `data/lofin_keyword_fetch_summary.json`
  - `code/fetch_lofin_keyword.py`

## PDF parser A/B (2026-07-19)

Sample windows (15 pages each):
- MOIS `mois_2026_budget_explainer.pdf` p798-812
- MOLIT `molit_2026_budget.pdf` p148-162

Tools compared on same samples:
1. current `pdftotext -layout`
2. `kordoc` markdown + chunks (`npx kordoc`)
3. OpenDataLoader PDF local (`markdown/json/text`, `table_method=cluster`)

Heuristic signal score totals:

| output | total score | notes |
|---|---:|---|
| **kordoc_chunks** | **637.4** | best overall |
| odl_md | 540.0 | most markdown table rows |
| kordoc_md | 497.4 | clean titles + tables |
| pdftotext | 384.0 | fast baseline, no tables |
| odl_text | 334.4 | weaker than odl markdown |

Timing on 15p samples:
- pdftotext ~0.04-0.08s
- kordoc ~0.6-1.2s
- OpenDataLoader ~2.0-2.8s

Decision:
- Main extract layer: **`kordoc@4.2.1 --format chunks`**
- Secondary/fallback: OpenDataLoader
- Probe-only: pdftotext
- Production result: 4 PDFs / 6,728 pages / 790 coded cards, with full-page cache metadata and source chunk provenance

Artifacts:
- `data/parser_ab/`
- `data/parser_ab/reports/ab_score.json`
- `code/run_odl_ab.py`, `code/score_parser_ab.py`

## Production integration result

- PDF reconcile: matched 712 / ambiguous 21 / unmatched 57
- Canonical businesses with PDF enrichment: 710
- Positive Add2 local-transfer businesses: 163
- LOFIN: 160 queryable businesses / 140 unique keywords / 63 businesses with positive candidates / 2,271 rows
- Canonical build and offline verification: `bash code/run_pipeline.sh` → `PIPELINE_OK`
