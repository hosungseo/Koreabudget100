# Koreabudget100 작업 완료 보고

- 기준일: 2026-07-19
- 프로젝트 경로: `/Users/seohoseong/Koreabudget100`
- GitHub: `https://github.com/hosungseo/Koreabudget100`
- 라이브 페이지: `https://hosungseo.github.io/Koreabudget100/`
- 완료 범위: **행정안전부·국토교통부·산업통상부 2026년 3부처 파일럿**
- 상태: **완료**

## 1. 완료 결과

열린재정 `ExpenditureBudgetAdd2`를 정본으로 삼아 1,401개 세부사업의 계층과 금액을 만들고, 부처 사업설명 PDF와 지방재정365 QWGJK 결과를 보강 정보로 붙였다. 최종 주 화면은 `지역사회 자생적 창조역량 강화` 한 사업을 기준으로, 중앙 확정예산의 **PDF 내용별 분해**와 **Add2 회계별 분해**를 평행 비교하고 지방 예산 관측은 확정 흐름과 분리한 **예산체계도**다.

| 항목 | 최종 결과 |
|---|---:|
| 열린재정 원본 세목 행 | 9,350 |
| 정규 세부사업(6단계 복합키) | 1,401 |
| 3부처 국회확정액 합계 | 133,546,671,000,000원 |
| 전체 추출 PDF | 4개 / 6,728쪽 |
| 구조화 PDF 사업카드 | 790 |
| PDF 확정 매칭 | 712카드 / 710개 정규 사업 |
| PDF 보류 / 미매칭 | 21 / 57 |
| 지자체 이전액이 양수인 중앙사업 | 163 |
| LOFIN 조회 가능 중앙사업 / 고유 키워드 | 160 / 141 |
| PDF 내역사업 보강 검색 | 1 (`사회연대경제`) |
| LOFIN 양수 후보가 발견된 중앙사업 | 64 |
| LOFIN `keyword_candidate` 행 | 2,294 |
| PDF 명시 절차 기반 `documented_flow` | 292개 사업 |
| PDF 문맥 기반 `structured_facts` | 418개 사업 |
| 열린재정 기반 `api_only` | 691개 사업 |
| 업무 체계도 노드 / 연결 | 11,865 / 7,597 |
| PDF 근거 섹션 | 4,248 |
| 세부사업 예산체계도 | 1,401 |
| API 목·세목 원 단위 대사 완료 | 1,401 |
| PDF 내역사업 추출 / 총액 대사 완료 | 45 / 37 |
| 기준 사례 수작업 전액 대사 | 237.53억원 / 차이 0원 |
| 기준 사례 LOFIN 시계열 | 7개 조회일 / 최신 27행 |

최종 화면:

- `artifacts/reference_budget_flow_map.html` — **주 화면: 단일 세부사업 예산체계도**
- `artifacts/budget_flow_map.html` — 1,401개 세부사업 탐색기
- `artifacts/budget_flow_map_2026.html`
- `artifacts/detail_business_structure.html`
- `artifacts/detail_business_structure_2026.html`
- `artifacts/detailed_business_workflows.html`
- `artifacts/detailed_business_workflows_2026.html`

최종 데이터:

- `data/normalized/canonical_business_2026_pilots.json`
- `data/normalized/canonical_business_tree_2026_pilots.json`
- `data/normalized/canonical_business_2026_pilots_summary.json`
- `data/normalized/business_workflows_2026_pilots.json`
- `data/normalized/budget_flow_maps_2026_pilots.json`
- `data/normalized/reference_lofin_timeline_2026.json`
- `artifacts/integration_status.json`
- `artifacts/business_workflows_2026_pilots_summary.json`
- `artifacts/budget_flow_maps_2026_pilots_summary.json`

## 2. 정본과 보강 레이어

```text
Open Fiscal ExpenditureBudgetAdd2
  └─ 정본: 연도 → 부처 → 회계 → 프로그램 → 단위사업 → 세부사업
       ├─ 금액·집행채널: Add2 세목 집계
       ├─ 예산체계도: PDF 내역사업 ↔ Add2 목·세목 ↔ 집행채널
       ├─ PDF 보강: 확정 매칭된 설명·시행주체·집행방식·근거 페이지
       └─ LOFIN 보강: 중앙사업명 또는 PDF 내역사업명으로 찾은 지방 편성·재원구성·지출 스냅샷
```

적용 원칙:

- 이름·계층·금액은 열린재정 API만 정본으로 사용한다.
- PDF 금액 표기는 정본 금액을 덮어쓰지 않는다.
- PDF `ambiguous`·`unmatched`·범위형 제목은 정규 사업에 자동 부착하지 않는다.
- LOFIN은 중앙사업 6단계 복합키가 붙은 후보 행만 해당 사업에 연결한다. PDF 내역사업 키워드는 그 중앙사업 안에서만 사용한다.
- LOFIN의 광역·기초 반영액 합은 같은 재원을 중복 표현할 수 있으므로 중앙예산 집행액이나 대사액으로 해석하지 않는다.

## 3. 열린재정 정본

- 서비스: `ExpenditureBudgetAdd2`
- 엔드포인트: `POST https://www.openfiscaldata.go.kr/openApi/preview/ExpenditureBudgetAdd2`
- 금액 필드: `Y_YY_DFN_KCUR_AMT` (국회확정액, API 단위 천원 → 저장 단위 원)
- 정규 키: 연도 + 부처 + 회계 + 프로그램 + 단위사업 + 세부사업

| 부처 | 세목 행 | 세부사업 | 금액 |
|---|---:|---:|---:|
| 행정안전부 | 3,312 | 287 | 76,905,548,000,000원 |
| 국토교통부 | 3,770 | 642 | 45,018,494,000,000원 |
| 산업통상부 | 2,268 | 472 | 11,622,629,000,000원 |
| **합계** | **9,350** | **1,401** | **133,546,671,000,000원** |

수집 안전장치도 반영했다. 필수 3부처 중 하나라도 API 행 수·페이지·부처 범위 검증에 실패하면 기존 정본 파일을 덮어쓰지 않고 실패 종료한다. 구 `TotalExpenditure1` 수집기는 `legacy_totalexpenditure1_*` 이름으로 격리해 Add2의 `latest` 파일을 덮어쓸 수 없다.

## 4. PDF 추출과 조인

### 4.1 추출

본선 추출기는 `kordoc@4.2.1 --format chunks`로 고정했다. 캐시는 입력 PDF 크기·mtime, Kordoc 버전, 출력 크기, 첫/마지막 페이지 커버리지가 모두 맞을 때만 재사용한다. 페이지 범위 실험은 별도 파일명으로 저장되며 전체 추출을 덮어쓰지 않는다.

| 문서 | 쪽수 | 카드 |
|---|---:|---:|
| 행정안전부 예산 사업설명자료 | 2,170 | 285 |
| 국토교통부 사업별 설명자료(예산) | 3,121 | 347 |
| 국토교통부 사업별 설명자료(기금) | 386 | 58 |
| 국토교통부 사업별 설명자료(R&D·정보화) | 1,051 | 100 |
| **합계** | **6,728** | **790** |

모든 카드에 제목, 사업코드 힌트, PDF 경로, 시작·끝 페이지, Kordoc chunk 근거를 저장한다. 체크 표식 `○`, `ㅇ`을 포함해 실제 선택된 집행방식만 읽고, 표 헤더·시행주체 placeholder·금액 줄바꿈 노이즈를 제거했다.

### 4.2 조인

| 상태 | 카드 | 비율 |
|---|---:|---:|
| 확정 매칭 | 712 | 90.1% |
| 보류(`ambiguous`) | 21 | 2.7% |
| 미매칭 | 57 | 7.2% |

- 기금 설명자료를 제외한 732카드는 710개가 확정 매칭(97.0%), 보류 포함 726개가 후보 식별(99.2%)됐다.
- 기금 자료는 사업명이 Add2 세출 세부사업 명칭과 다른 운용 항목이 많아 58개 중 2개 확정, 5개 보류, 51개 미매칭이다. 미매칭 카드는 버리지 않고 unresolved에 보존한다.
- 여러 세부사업을 한 제목으로 묶은 코드 범위/목록형 7개는 임의의 단일 API 사업에 붙이지 않고 `aggregate_heading` 보류로 남겼다.
- 동일 부처 안의 동명 사업은 회계·단위사업을 구분할 근거가 없으면 자동 선택하지 않는다.
- 점수는 0–100으로 제한하고, 부처 간 교차 매칭은 허용하지 않는다.

15쪽 파일럿 정답지는 행안부 2개 + 국토부 3개, 총 5개이며 모두 high/exact로 매칭됐다. 집행경로도 행안부 2개는 직접+출연, 국토부 3개는 직접으로 확인했다.

## 5. 지방재정365 선택 수집

- 서비스: `QWGJK`
- 기준일자: `exe_ymd=20260630`
- 선택 조건: Add2 세목 중 지자체 이전 채널 금액이 양수인 중앙사업
- 국비 필드: `bdg_ntep > 0`
- 지역 예산·집행 필드: `bdg_cash_amt`, `capep`, `sggep`, `etc_amt`, `ep_amt`, `cpl_amt`
- 지자체 단계: 7자리 `laf_cd`의 `code[2:5] == "000"`이면 광역본청, 아니면 기초

처리 결과:

- 중앙 후보 163개
- 보수적인 키워드를 만들 수 있는 사업 160개
- 중앙사업명 검색 140개 + PDF 내역사업명 검색 1개
- 양수 후보가 발견된 중앙사업 64개
- 정규화·중복 제거 후보 행 2,294개

각 행에는 `central_business_key`, 중앙사업명, 사용 키워드와 생성 전략, 중앙 지자체 이전액, 지역·지자체·지방사업 코드, 예산현액, 국비·시도비·시군구비·기타, 지출액, 편성액, `match_scope`, `match_status=keyword_candidate`를 저장한다. 범용 탐색기의 기준일은 `2026-06-30`이며 2,294행을 유지한다.

단일 기준 사례는 PDF 내역사업 `사회연대경제 활성화`를 키워드 `사회연대경제`로 7개 조회일에 반복 조회한다. 최신 `2026-07-18`의 국비 양수 27행은 PDF 핵심 표현과 맞는 A 강한 후보 9행, 포괄 제목인 B 유사 후보 3행, PDF에 없는 `청년 일경험` 계열인 C 별도 사업 가능성 15행으로 나눈다. 같은 키워드를 공유하는 중앙사업과 광역·기초 중복이 있을 수 있으므로 행 수·관측합·관측 비율은 확정 교부처·중앙 순지출 총액이 아니다.

관련 파일:

- `code/fetch_lofin_local_transfer_candidates.py`
- `code/fetch_reference_lofin_timeline.py`
- `data/normalized/lofin_local_transfer_candidates_2026.json`
- `data/normalized/lofin_local_transfer_candidates_2026_summary.json`
- `data/normalized/reference_lofin_timeline_2026.json`

## 6. 산업통상부 PDF 커버리지

산업통상부 472개 세부사업과 금액은 Add2 정본에 모두 포함됐다. 다만 2026-07-19 기준 공식 게시물의 5개 첨부 다운로드가 서버 오류(`302 → /error/500 → 404`)를 반환한다. 공식 뷰어도 한 권이 선언 2,214쪽 중 1,116쪽 이후 이미지가 없어 완전 복원이 불가능했다.

부분 PDF만 섞으면 부처 내 커버리지를 오해할 수 있어 최종 산출물에서는 산업통상부를 **API-only**로 명시했다. 이는 3부처 정본 완성의 결손이 아니라 PDF 설명 레이어의 공개 원본 커버리지 공백이다.

공식 게시물: https://www.motir.go.kr/kor/article/ATCL3f70bb6cf/48/view

## 7. 구조도 HTML

### 7.1 단일 세부사업 예산체계도 — 주 화면

`reference_budget_flow_map.html`은 `지역사회 자생적 창조역량 강화` 237.53억원을 한 화면에서 깊게 파고든다. PDF 내역사업과 Add2 세목은 순차 집행단계가 아니라 같은 총액을 보는 두 분류이므로 평행 레저로 놓았다.

- PDF 내역사업 5개 합계 237.53억원
- Add2 회계버킷 5개 합계 237.53억원
- PDF 산출내용과 금액을 수작업 검토한 전액 교차 대사 237.53억원, 차이 0원
- `사회연대경제 활성화` 118.39억원을 지자체보조 103.50억원, 일반용역 11.00억원, 사업관리 3.89억원으로 정확히 분리
- LOFIN 후보는 중앙 확정축과 물리적으로 분리하고 A/B/C 근거 등급과 7개 조회일 변화를 함께 표시
- 변화한 행 수·예산현액·지출액은 스냅샷 관측치이며 교부·송금 이력이 아님을 화면에 명시
- PDF 원문의 산식 불일치 2건을 경고로 보존

전액 교차 대사는 실제 거래원장이 아니라 **PDF 내용·금액과 Add2 세목의 검토 결과**다. A 강한 후보도 최신 관측상 국비 100%로 표시되어 PDF 보조율 50%와 맞지 않으므로 확정 수혜지로 승격하지 않았다.

### 7.2 전체 세부사업 예산체계도 — 탐색기

`budget_flow_map.html`은 1,401개 사업 중 하나를 선택해 다음 돈의 구조를 한 장에 표시한다.

```text
중앙 확정재원 → 세부사업·내역 → 목·세목·집행채널 → 중앙 집행대상 → 지방 편성 후보 → 지출·수혜·검증
```

- Add2 국회확정액과 목·세목 합계를 전 사업 원 단위 대사
- PDF 산출근거에서 내역사업을 추출하되 총액과 별도 대사
- 내역사업↔세목은 문서·지원율·금액으로 직접 확인되는 구간만 연결
- 세목을 지방보조·민간위탁·민간보조·출연·용역·융자·출자·시설·인건비·운영·기타 채널로 분류
- 실제 기관·지역이 확인되지 않으면 `미상`으로 표시
- LOFIN 2,294행은 비가산 후보로 표시하고, 선택 사업에서는 권역·지자체·지방사업·예산현액·재원구성·지출액·관측 집행률을 펼쳐 표시
- 사업 검색, 노드 연결 강조, 근거 페이지, 대사표, 모바일 세로 보기, A3 인쇄 지원

탐색기의 기본 예시도 같은 사업이지만, 수작업 전액 대사·후보 등급·시계열은 위의 전용 주 화면에서 다룬다.

세부 원칙은 `docs/budget_flow_methodology.md`에 기록했다.

### 7.3 전체 예산 계층 탐색기

`detail_business_structure.html`은 canonical tree를 입력으로 사용한다.

- Add2 계층·금액·비목 기반 집행채널
- 확정 매칭 PDF 제목·시행주체·집행방식·출처 페이지
- LOFIN 후보 행 수·광역/기초 소계·상위 지역·비가산 경고
- 사업명, 시행주체, 집행채널, PDF 경로, 지역명 통합 검색
- 내장 JSON의 `</script>` 종료 문자열 이스케이프
- 잘못된 구 출처명 `TotalExpenditure1`과 금액 필드 표기 제거

### 7.4 세부사업별 업무 절차 보조 화면

`detailed_business_workflows.html`은 1,401개 세부사업 중 하나를 선택해 **단계 행 × 수행주체 열**의 스윔레인으로 보여 준다. 단계 `G0~G6`은 서로 다른 사업을 같은 화면 문법으로 비교하기 위한 표현 분류이며, 원문이 주장한 법정 절차 단계가 아니다.

- `documented_flow` 292개: PDF에 명시된 번호·화살표·추진계획 표의 순서만 절차선으로 사용
- `structured_facts` 418개: PDF 목적·근거·시행주체·문맥을 구조화하되 순서를 임의 생성하지 않음
- `api_only` 691개: Add2 예산 계층·확정액·목세목 집행채널만 표시
- 원천 주장 노드·연결에는 Add2 필드, PDF 페이지·chunk 또는 LOFIN 조회 근거를 부착하고, 화면 배치용 `derived` 관계는 별도 표시
- LOFIN 2,294행은 모두 비가산 `keyword_candidate` 점선으로 표시
- 원문에 없는 승인·반려·보완·병목·성과 환류를 자동 생성하지 않음

세부 방법론은 `docs/workflow_methodology.md`에 기록했다.

## 8. 실행과 검증

전체 오프라인 재생성:

```bash
cd /Users/seohoseong/Koreabudget100
bash code/run_pipeline.sh
```

선택 옵션:

```bash
bash code/run_pipeline.sh --extract          # Kordoc 전체 재추출
bash code/run_pipeline.sh --refresh-lofin    # LOFIN API 새로 조회
bash code/run_pipeline.sh --lofin-cache-only # 중앙사업 140개 + PDF 내역 1개 캐시로 LOFIN 재생성
python3 code/fetch_reference_lofin_timeline.py --refresh # 기준 사례 7개 조회일 갱신
```

최종 검증 결과:

```text
VERIFY_OK passes=6 skips=0 details=1401 lines=9350
total_won=133546671000000 pdf_cards=790
WORKFLOW_VERIFY_OK workflows=1401 documented=292 structured=418 api_only=691
nodes=11865 edges=7597 evidence_sections=4248 lofin_candidates=2294
BUDGET_FLOW_VERIFY_OK maps=1401 total=133546671000000 reference=kb-ace0474d507615f7
PIPELINE_OK
```

검증 항목:

- Add2 9,350행 → 복합키 1,401개 → 금액 합 보존
- canonical ID·집행채널·출처와 matched-only PDF 부착
- 트리 말단 1,401개 및 재귀 금액·count 일치
- PDF 790카드의 코드·페이지·출처·점수 범위
- LOFIN 연도·양수 금액·복합키 부착·중복 제거
- HTML의 정본 출처·LOFIN 경고·내장 데이터 안전성
- 업무 체계도 1,401개 ID·actor·phase·node·edge 참조 무결성
- 세 등급 합계, 예산 분해 합계, PDF/LOFIN 근거 상태와 비가산 규칙
- 행안부·국토부 명시 절차 표본, LOFIN 후보 표본, 산업통상부 472개 API-only 회귀검사
- 상세 HTML 내장 데이터, 검색·탭·노드 선택·근거 패널의 브라우저 실행 검사
- 예산체계도 1,401개 목·세목·채널 합계, 기본 예시 5개 내역·8개 세목·4개 채널 회귀검사
- 단일 기준 사례 237.53억원 전액 교차 대사, LOFIN 7개 조회일, 최신 A/B/C 9/3/15행 회귀검사
- 예산체계도 검색 전환, 연결선, 모바일 390px, 데스크톱 1,600px, 브라우저 콘솔 오류 검사

## 9. 완료 경계와 후속 확장

이번 작업의 완료 경계는 **2026년 3개 부처 파일럿을 재현 가능한 통합 데이터, 전체 예산 계층 탐색기, 세부사업별 증거 기반 예산체계도, 업무 절차 보조 화면으로 제공하는 것**이다. 이 범위에서 필요한 작업은 모두 끝났다.

다음 항목은 결함이 아니라 별도 확장 단계다.

- 3개 부처 밖의 전국·전 부처 Add2 수집
- 산업통상부가 완전한 공식 PDF를 다시 제공할 때 설명 레이어 추가
- LOFIN 키워드 후보의 수동 검토 또는 공식 사업코드 교차표 확보
- 기금 운용 항목과 Add2 세출사업 사이의 별도 매핑 모델

## 10. 한 줄 현황

> **3부처 2026 파일럿을 통합하고, 한 세부사업 237.53억원을 PDF 내용별·Add2 회계별로 전액 교차 대사한 뒤 LOFIN 7개 스냅샷을 후보 등급별로 분리한 단일사업 예산체계도를 주 화면으로 제공한다.**
