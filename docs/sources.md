# 데이터 출처

기준일: 2026-07-19

## 열린재정 — 중앙예산 정본

- 서비스: `ExpenditureBudgetAdd2`
- 호출: `POST https://www.openfiscaldata.go.kr/openApi/preview/ExpenditureBudgetAdd2`
- 인증: `.env`의 `OPENFISCAL_API_KEY`
- 기준 필드: `Y_YY_DFN_KCUR_AMT` (국회확정액, 천원)
- 계층: `OFFC_NM → FSCL_NM → PGM_NM → ACTV_NM → SACTV_NM → CITM_NM → EITM_NM`
- Open API 목록: https://www.openfiscaldata.go.kr/op/ko/ds/UOPKODSA06

2026년 3부처 정본 결과는 9,350행, 복합키 기준 1,401개 세부사업, 133,546,671,000,000원이다. 구 `TotalExpenditure1`은 2026 정본이 아니며 legacy 출력으로만 격리한다.

## 지방재정365 — 지역 반영 후보

- 서비스: `QWGJK` 세부사업별 세출현황
- 호출: `GET https://www.lofin365.go.kr/lf/hub/QWGJK`
- 인증: `.env`의 `LOFIN365_API_KEY`
- 필수: `fyr`, `exe_ymd`, `pIndex`, `pSize`
- 키워드: `dbiz_nm`
- 국비: `bdg_ntep`
- 예산·집행: `bdg_cash_amt`(예산현액), `capep`(시도비), `sggep`(시군구비), `etc_amt`(기타), `ep_amt`(지출액), `cpl_amt`(편성액)
- 기준 스냅샷: `exe_ymd=20260630`
- 원 데이터 안내: https://www.data.go.kr/data/15059434/openapi.do

지자체 단계는 7자리 `laf_cd`에서 `code[2:5] == "000"`이면 광역본청, 그 외는 기초로 분류한다. 중앙 세부사업명뿐 아니라 설명자료에 금액이 명시된 내역사업명도 보수적인 검색 키워드로 쓸 수 있다. 결과는 명칭 변형을 고려한 `keyword_candidate`이며 확정 교부처 교차표가 아니다. 광역·기초 행은 같은 재원을 중복 표현할 수 있다.

## 부처 사업설명자료

### 행정안전부

- 게시물: https://www.mois.go.kr/frt/bbs/type001/commonSelectBoardArticle.do?bbsId=BBSMSTR_000000000031&nttId=123327
- 제목: 2026년도 예산 사업설명자료
- 로컬 원본: `data/raw/pdfs/mois/mois_2026_budget_explainer.pdf`
- 커버리지: 2,170쪽 / 285카드

### 국토교통부

- 게시물: https://www.molit.go.kr/USR/BORD0201/m_34879/DTL.jsp?mode=view&idx=31111
- 로컬 원본:
  - `data/raw/pdfs/molit/molit_2026_budget.pdf` — 3,121쪽 / 347카드
  - `data/raw/pdfs/molit/molit_2026_fund.pdf` — 386쪽 / 58카드
  - `data/raw/pdfs/molit/molit_2026_rnd_info.pdf` — 1,051쪽 / 100카드

### 산업통상부

- 게시물: https://www.motir.go.kr/kor/article/ATCL3f70bb6cf/48/view
- 제목: 26년도 예산 및 기금운용계획 사업설명자료
- 상태: 2026-07-19 기준 5개 공식 첨부 다운로드가 서버 오류를 반환한다. 공식 뷰어 한 권도 선언 페이지 후반이 누락돼 완전 복원이 불가능하다.
- 적용: Add2 정본 472개 사업은 포함하고, PDF enrichment는 `api_only` 커버리지 공백으로 표시한다.

## 추출 도구

- 본선: `kordoc@4.2.1 --format chunks`
- 검증/진단: Poppler `pdfinfo`, `pdftotext`
- 기존 A/B 기록: `data/parser_ab/reports/ab_score.json`

Kordoc 전체 커버리지는 4개 PDF, 6,728쪽이며 추출 메타데이터가 입력 파일·버전·페이지 1..마지막 쪽을 검증한다.

## 산출물 출처 정책

- 이름·계층·금액: 열린재정 Add2
- 시행주체·집행경로·설명: 확정 매칭된 부처 PDF
- 지역 반영 탐색: LOFIN QWGJK `keyword_candidate`
- 근거 누락·동점·범위형 제목: 자동 채택하지 않고 unresolved로 보존
