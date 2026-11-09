# Journey-To-Ungoro

HSdeck schema 1 카드 API. 한국 시간(Asia/Seoul) 기준 최초 사용 가능 날짜에 초기 스펙을 `data/<cardID>.json`의 `card`에 기록하고, 이후 변경 부분만 `card.patches`에 기록했습니다.

- `cards.json`: 현재 카드 정보(기존 원화 경로 유지)
- `render.json`: 날짜별 이력 통합 WebGL API
- `history.json`: 구버전 HScard API
- `release-policy.json`: 한국 시간 기준 출시 날짜

원본 ZIP에 과거 수치가 없으므로, 공식 자료로 확인하지 못한 초기 값은 `initialSpecStatus: unverified`로 표시합니다. 기존 `art/`, `golden/` 파일은 그대로 유지했습니다.
