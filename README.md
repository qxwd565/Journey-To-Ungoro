# Journey-To-Ungoro

HSdeck schema 1 카드 API. 한국 시간(Asia/Seoul) 기준 최초 사용 가능 날짜에 초기 스펙을 `data/<cardID>.json`의 `card`에 기록하고, 이후 변경 부분만 `card.patches`에 기록했습니다.

- `cards.json`: 현재 카드 정보(기존 원화 경로 유지)
- `render.json`: 날짜별 이력 통합 WebGL API
- `history.json`: 구버전 HScard API
- `release-policy.json`: 한국 시간 기준 출시 날짜

원본 ZIP에 과거 수치가 없으므로, 공식 자료로 확인하지 못한 초기 값은 `initialSpecStatus: unverified`로 표시합니다. 기존 `art/`, `golden/` 파일은 그대로 유지했습니다.

## 날짜별 이력 편집과 검증

- 정규 원본은 `data/<cardID>.json`이며, `card`는 최초 스펙, `card.patches`는 한국 적용일 순서의 변경입니다.
- 변경 이벤트는 `changes` 값 대입과 `remove` 키 삭제를 구분합니다. 누락 키는 이전 값 유지이며 `0`, `false`, `null`, 빈 문자열, 빈 배열은 실제 값입니다.
- 기존 API에는 내부 `remove` 연산을 노출하지 않습니다. 과거 상태에서 현재 필드를 삭제해야 하는 카드의 전체 레거시 타임라인은 호환성 보류 목록에 기록됩니다.
- 표시용 `text`의 줄바꿈은 `<br></br>`로 정규화합니다. 원문 `nativeRawText`는 변환하지 않습니다.
- 검증: `python -m unittest discover -s tests -v`; 생성: `python tools/build-api.py`.
- 자세한 규약: [docs/history-operations.md](docs/history-operations.md).


## API 공개 범위·편집 규칙 (2026-11-14)

- 카드와 시각 자료의 공개 원본은 `cards.json`(카드 ID·현재 목록), `data/<CARD_ID>.json`(한국 날짜별 카드 상태·변경), `art/`(일반 카드), `golden/`(황금 원화·애니메이션), `frame/`(프레임·재질·셰이더·텍스처)입니다. 실제 존재하지 않는 시각 자료를 생성하지 않습니다.
- 중복 집계 `render.json`, `history.json`, `*-date.json`은 Git에 재커밋·게시하지 않습니다. CI가 생성할 때도 비교/검증용 임시 출력일 뿐입니다. 중복 schema/호환 래퍼를 새로 추가하지 않습니다.
- 날짜별 첫 한국 실제 대전 사용 가능일을 사용합니다. 베타 북미 날짜의 한국 시간 환산, 모험 지구 개방, 이벤트 개시, 토큰·자식카드의 부모 생성 가능일을 구분합니다. 사전 클라이언트 탑재일은 사용일이 아닙니다.
- 오기입된 과거 날짜는 새 날짜만 추가하지 않고 기존 날짜 키를 삭제·통합합니다. 후속 날짜는 바뀐 필드만 저장하고 표시 줄바꿈은 `<br></br>`를 사용합니다. 미확정 출시 당시 스펙을 현행 값으로 단정하지 않습니다.
- `sources/`, `tools/`, `tests/`, `.github/` 원본 검증·빌드 재현성을 위해 참조 중인 파일과 황금/프레임 원본 바이너리는 삭제·재인코딩하지 않습니다.
