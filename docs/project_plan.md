# Koreabudget100 — 구현 계획과 완료 기준

## 완료 범위

2026년 행정안전부·국토교통부·산업통상부 3부처를 대상으로 다음 결과를 만든다.

1. 열린재정 Add2 기반 정규 세부사업 계층과 금액
2. 부처 사업설명 PDF의 시행주체·집행방식·근거 페이지 보강
3. 지자체 이전 사업에 한정한 LOFIN QWGJK 후보 반영처
4. 세부사업별 재원→내역→목·세목→채널→기관·수혜 예산체계도
5. 독립 실행 가능한 검색형 HTML
6. PDF 명시 절차를 보는 단계 × 수행주체 보조 화면
7. 한 명령으로 재생성되는 오프라인 검증 파이프라인

위 범위는 2026-07-19 완료됐다. 상세 수치는 `docs/project_status.md`를 따른다.

## 데이터 모델

```text
CanonicalBusiness
  ├─ id                    # 전체 6단계 키의 안정 SHA-256 ID
  ├─ canonical_key         # 연도/부처/회계/프로그램/단위/세부사업
  ├─ api_core              # Add2 정본 이름·계층·금액
  ├─ execution_channels[]  # Add2 목/세목 집계
  ├─ pdf_enrichment[]      # 확정 매칭된 PDF 근거만
  ├─ local_reflections[]   # LOFIN keyword_candidate
  ├─ local_summary         # 광역/기초 소계와 비가산 경고
  └─ source_refs[]

BusinessWorkflow
  ├─ coverage_tier         # documented_flow / structured_facts / api_only
  ├─ phases[]              # G0~G6 화면 배치 분류
  ├─ actors[]              # 부처·시행주체·이전채널·지자체 후보
  ├─ nodes[]               # 행동·예산·근거 노드
  ├─ edges[]               # sequence / fund / context / delivery / candidate
  ├─ evidence_sections[]   # PDF 페이지·chunk 및 원문 구간
  └─ quality               # 출처 assertion과 추론 경계

BudgetFlowMap
  ├─ core                  # Add2 세부사업 계층·국회확정액
  ├─ subprojects[]         # PDF 내역사업·산출근거
  ├─ budget_items[]        # Add2 목·세목 확정액
  ├─ channels[]            # 세목 규칙 기반 집행채널
  ├─ crosswalks[]          # 문서·금액으로 직접 확인한 내역↔채널 연결
  ├─ local_candidates[]    # LOFIN 비가산 keyword_candidate
  ├─ implementation        # 시행방법·주체·수혜자 문서 근거
  └─ reconciliation        # 총액·세목·내역·직접대사 차이
```

## 처리 순서

```text
Add2 details/lines
      │
      ├─ 집행채널 집계 ───────────────┐
      │                               │
PDF → Kordoc chunks → 카드 → 조인 ───┼→ canonical dataset/tree → 계층 HTML
      │                               │
      ├─ ambiguous/unmatched 보존     │
      ├─ 예산 산출·시행 구조 → budget flow map → 예산체계도
      └─ 사업 전체 chunk → workflow graph → 업무 절차 보조 화면
                                      │
Add2 지자체이전 양수사업 → QWGJK 후보 ┘
```

## 완료 기준

- [x] Add2 9,350행, 복합키 1,401개, 133,546,671,000,000원 보존
- [x] 4개 PDF 6,728쪽 전체 Kordoc 추출 및 버전/페이지 캐시 검증
- [x] 790개 코드형 사업카드와 PDF/chunk provenance
- [x] 부처 스코프·동점·범위형 제목을 안전하게 처리하는 조인
- [x] 163개 양수 지자체 이전 사업만 LOFIN 선택
- [x] full central key로 LOFIN 후보를 정규 사업에 부착
- [x] Add2/PDF/LOFIN 보강 HTML
- [x] 1,401개 세부사업별 예산체계도와 검색
- [x] API 목·세목·채널 합계 전 사업 원 단위 대사
- [x] PDF 내역사업과 Add2 세목을 별도 분해로 보존
- [x] 문서·금액으로 확인되는 내역↔채널만 직접 대사
- [x] 기관·지역·수혜의 확인·후보·미상 상태 분리
- [x] 1,401개 세부사업별 workflow graph
- [x] 명시 절차 292개, 구조화 사실 418개, API-only 691개 등급 분리
- [x] G0~G6 단계 × 수행주체 스윔레인과 노드별 근거 패널
- [x] LOFIN 연결을 비가산 `keyword_candidate`로 제한
- [x] API·canonical·tree·PDF·LOFIN·HTML 오프라인 무결성 검사
- [x] workflow graph·상세 HTML 독립 검증
- [x] budget flow model·HTML 독립 검증
- [x] `bash code/run_pipeline.sh` → `PIPELINE_OK`

## 별도 확장 단계

다음은 현재 완료 범위에 포함되지 않는다.

- 전국 전 부처 Add2 확장
- 산업통상부 완전 PDF가 다시 공개된 뒤 PDF enrichment 추가
- LOFIN 후보의 공식 코드 교차표 또는 수동 판정
- 기금 운용 항목 전용 매핑 모델
