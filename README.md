# Koreabudget100

열린재정 Add2를 정본으로, 부처 사업설명 PDF와 지방재정365 QWGJK를 결합한 2026년 예산 세부사업 계층도와 **사업별 상세 업무 체계도**입니다.

현재 완료 범위는 행정안전부·국토교통부·산업통상부 3개 부처입니다.

라이브 페이지: https://hosungseo.github.io/Koreabudget100/

- 9,350 세목 행
- 1,401 정규 세부사업
- 133,546,671,000,000원
- 790 PDF 사업카드
- 2,271 LOFIN `keyword_candidate` 행
- PDF에 명시된 절차를 가진 상세 체계도 292개
- 목적·근거·시행구조 중심 체계도 418개
- 예산·목세목만 표시하는 API-only 체계도 691개

주요 결과 화면:

- `artifacts/detailed_business_workflows.html` — 단계 × 수행주체 업무 체계도
- `artifacts/detail_business_structure.html` — 전체 예산 계층 탐색기

상세 완료 보고: `docs/project_status.md`

체계도 생성 원칙: `docs/workflow_methodology.md`

## 재생성

```bash
cd /Users/seohoseong/Koreabudget100
bash code/run_pipeline.sh
```

원본 PDF 추출 또는 LOFIN 새 조회가 필요할 때만 옵션을 사용합니다.

```bash
bash code/run_pipeline.sh --extract
bash code/run_pipeline.sh --refresh-lofin
bash code/run_pipeline.sh --lofin-cache-only
```

독립 검증:

```bash
python3 code/verify_integrated_outputs.py --require-lofin
python3 code/verify_workflow_outputs.py
```

## 구조

- `code/`: 수집·파싱·조인·빌드·검증
- `data/normalized/`: 재현 가능한 정규화·통합 JSON
- `data/raw/`: 대용량 원본과 Kordoc/LOFIN 캐시 (`gitignore`)
- `artifacts/`: 독립 실행 HTML과 요약
- `docs/`: 상태·API·출처 문서
- `secrets/`, `.env`: 로컬 인증정보 (`gitignore`)

## 해석 주의

- 이름·계층·금액의 정본은 `ExpenditureBudgetAdd2`와 `Y_YY_DFN_KCUR_AMT`입니다.
- PDF는 확정 매칭된 설명만 붙이며, 보류·미매칭은 별도 보존합니다.
- `documented_flow`만 PDF의 명시적 화살표·번호·추진계획 표를 절차 순서로 사용합니다. G0~G6은 화면 배치를 위한 분석 분류입니다.
- LOFIN 결과는 키워드 후보입니다. 광역·기초 반영액은 중복될 수 있어 중앙예산 합계와 직접 대사하면 안 됩니다.
- 산업통상부는 공식 첨부 서버 장애로 PDF 설명 없이 Add2 정본만 제공합니다.

## 보안

API 키는 `.env` 또는 `secrets/`에만 보관하고 공개 파일·로그·커밋에 포함하지 마세요.
