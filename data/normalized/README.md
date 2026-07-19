# 정규화 데이터 안내

2026년 3부처 통합본의 정본 파일은 다음 세 개입니다.

- `canonical_business_2026_pilots.json`
- `canonical_business_tree_2026_pilots.json`
- `canonical_business_2026_pilots_summary.json`

세부사업별 상세 업무 체계도의 정규화 입력은 다음 파일입니다.

- `business_workflows_2026_pilots.json`

이 파일은 1,401개 사업을 `documented_flow`, `structured_facts`, `api_only`로 구분하고 actor·phase·node·edge·evidence를 보존합니다. `G0~G6`은 화면 배치 분류이며, LOFIN 연결은 모두 비가산 `keyword_candidate`입니다.

입력 정본은 `expbudgetadd2_2026_pilots_details.json`과 `expbudgetadd2_2026_pilots_lines.json`입니다.

`detail_business_2022_*`, 빈 `detail_business_2026_*`, `detail_business_*_latest` 파일은 초기 `TotalExpenditure1` 실험의 legacy 산출물입니다. 2026년 분석·HTML·검증에서는 사용하지 마세요. `code/fetch_total_expenditure.py`도 이제 `legacy_totalexpenditure1_*` 이름만 쓰며 Add2의 최신 파일을 덮어쓰지 않습니다.

LOFIN 본선은 `lofin_local_transfer_candidates_2026.json`입니다. `lofin_qwgjk_keyword_matches.json`과 `lofin_detail_business_pilot.json`은 초기 수동 키워드·지역 파일럿입니다.
