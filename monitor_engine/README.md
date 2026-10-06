# 트리거형 안전관제 — 엔진

회사가 만든 파일 묶음(**패키지**)을 받아서 돌리는 시스템 코드만 있다.
엔진은 특정 공정 · 위험 · 시나리오를 모른다. 사업장 · 신호 · 판정표 · 모드 · 게이트 · 개정안은 전부 패키지 파일에서 온다.
패키지를 바꾸면 다른 사업장 · 다른 위험이 같은 코드로 돈다.

## 흐름

```
패키지 ─ package.py (읽기 · 검사 · 개정안 적용)
            │
신호 ───────┼→ facts.py      신호 사전대로 사실 저장 (켜짐/꺼짐 · 사건 · 측정 · 표시 · 문서)
(CSV·버튼·   ├→ modes.py      규칙의 when → 지금 켜진 모드
 PLC·PTW)    ├→ gates.py      문서가 들어오면 작업 전 대조 → 막기
            ├→ judge.py      판정표: 축 상태 → 위에서부터 첫 번째로 맞는 줄 → 단계
            │    └ conditions.py  조건어 평가기 (규칙은 이것만 조합해서 쓴다)
영상 ───────┼→ detector.py · zones.py  사람 · 불꽃 · 그 밖 물체 → 폴리곤 → 검출 확정(N프레임)
            ├→ checks.py     모드별 영상 규칙 (출입 금지 · 최소 · 최대 인원)
            └→ events.py     이벤트 로그 · 무음 기록 · 중복 억제 · 전후 클립
engine.py 가 위를 묶고, runner.py(타임라인) · video.py(영상)가 엔진을 돌린다.
```

| 파일 | 하는 일 |
|---|---|
| `safety_monitor/package.py` | 패키지 읽기, 규격 검사, 개정안(set/add) 적용 |
| `safety_monitor/signals.py` · `facts.py` | 신호 모양, 타임라인 CSV, 사실 저장소 |
| `safety_monitor/conditions.py` | 조건어 평가기 |
| `safety_monitor/judge.py` | 판정표 평가, 단계 유지 · 하강 |
| `safety_monitor/modes.py` · `gates.py` · `checks.py` | 모드, 작업 전 게이트, 영상 규칙 |
| `safety_monitor/engine.py` | 위를 묶는 엔진 |
| `safety_monitor/runner.py` · `video.py` | 타임라인 실행(1분씩 시간 경과) · 기대 결과 대조 / 영상 실행 |
| `safety_monitor/detector.py` · `zones.py` · `draw.py` | 탐지, 폴리곤 · 접지점 · 호모그래피, 영상 위 최소 표시 |
| `safety_monitor/events.py` · `stats.py` · `video_io.py` | 기록 · 클립, 탐지 요약, 한글 경로 대비 입출력 |
| `run.py` · `validate.py` · `calibrate.py` | 실행, 패키지 검사, 카메라 폴리곤 찍기 |
| `config/detect.json` · `models/` | 시스템 기본 탐지 설정, 사람 탐지 가중치 |

## 실행

```bash
pip install -r requirements.txt

python validate.py <패키지>                          # 받은 파일이 규격에 맞나
python run.py <패키지> [<시나리오>]                   # 타임라인 실행 + 기대 결과 대조
python run.py <패키지> <시나리오> --changes R1,R3     # 개정안을 골라서 (none · all · docgen)
python run.py <패키지> <시나리오> --scene <장면>      # 영상 (scenario.json scenes)
python run.py <패키지> --video 파일 --at 09:15 --camera <ID> [--show] [--save]
python calibrate.py <패키지> --camera <ID> --video 파일 --name <폴리곤> --type <종류> --zone <구역>
```

`<패키지>`는 `packages/` 아래 이름이거나 아무 폴더 경로다. 결과는 `outputs/<시각>/`에 쌓인다.
실제 사업장 패키지는 `packages/<이름>/` 에 넣는다. 기능 확인용 예시 패키지는 폴더 맨 위 `예시데이터_삭제가능/사업장패키지/` 에 있다(지워도 된다):

```bash
python run.py ../예시데이터_삭제가능/사업장패키지/steel_pickling                      # 시나리오 A · B, 기대 결과 대조
python run.py ../예시데이터_삭제가능/사업장패키지/steel_pickling B_맹판격리 --scene "그라인더 불티" --changes "개정 후"
python run.py ../예시데이터_삭제가능/사업장패키지/confined_space_example             # 다른 업종 · 다른 판정표(질식)
```

---

## 입력 파일 규격 — 패키지

```
<패키지>/
  site.json        사업장 · 구역 · 설비 참조 목록          (필수)
  dashboard.json   관제 화면용 — 시연 기본값 · 부서 대응     (선택, 관제 화면만 읽는다)
  signals.json     신호 사전                               (필수)
  rules.json       규칙                                    (필수)
  cameras/<ID>.json 카메라별 폴리곤                         (영상을 쓸 때)
  buttons.json     재생 중 키 → 신호                        (선택)
  detect.json      config/detect.json 덮어쓰기             (선택)
  scenarios/<이름>/ scenario.json · timeline.csv · 입력 문서 (선택)
```

### site.json
```json
{"name": "사업장 이름", "industry": "업종",
 "zones": {"Z8": {"name": "구역 이름", "hazard": "fuel_gas"}},
 "references": {"piping": {"Z8": [{"id": "FG-01", "name": "주 배관", "hazard": "fuel_gas"}]}}}
```
구역 속성(`hazard` 등)은 조건어 `zone_attr`가 읽는다. 참조 목록은 `covers` · `unmarked` · 게이트가 읽고, 신호 대상(`target`)으로 구역을 찾을 때도 쓴다.

### signals.json — 신호 사전
```json
{"signals": {
  "exhaust_stop": {"label": "배기 정지", "do": "on",  "fact": "exhaust_stopped"},
  "gas_test":     {"label": "가스 측정", "do": "measure", "fact": "gas",
                   "reset": {"events": ["release"], "if": {"cond": "clearance"}}},
  "flange_open":  {"label": "잔류 가스 방출", "do": "event", "fact": "release", "attrs_from": ["zone", "ref:piping"]},
  "strip_break":  {"label": "스트립 파단", "do": [{"do": "on", "fact": "line_stopped"}, {"do": "event", "fact": "strip_break"}]}}}
```
| do | 하는 일 |
|---|---|
| `on` / `off` | 상태(fact)를 켜고 끈다. 켜져 있던 구간도 남는다 |
| `event` | 일어난 일을 남긴다. 속성은 `attrs`(직접) · `attrs_from`(`zone` · `ref:<참조>`) |
| `measure` | 측정값(신호 value, 숫자). 대상(target)이 측정 지점 |
| `mark` / `unmark` | 대상에 표시를 붙이거나 뗀다 (예: 맹판 설치 완료) |
| `document` | 신호 value 에 적힌 파일(CSV · JSON)을 시나리오 폴더에서 읽는다 → 게이트가 대조 |
| `accident` | 사고 |

`reset`: 신호가 들어온 뒤 `if` 조건이 맞으면 그 전의 `events`를 지운다. 사전에 없는 신호가 들어오면 같은 이름의 event로 남긴다.

### rules.json — 규칙
```json
{"vars": {"lel_top": 25, "hazard_sources": ["acid"]},
 "conditions": {"gas_valid": {"measured": "gas", "max_age_min": 120}},
 "judgments": {"<판정표>": {
    "zones": ["Z8"],
    "axes": [{"name": "축적", "states": [
               {"state": "●", "when": {"fact": "exhaust_stopped"}},
               {"state": "○", "when": true}]}],
    "rows": [{"row": 1, "level": "최고 경보", "violation": "위반_이름", "when": {"axis": "축적", "is": "●"}}],
    "default": {"row": 8, "level": "정상"},
    "lower": {"hold_min": 5, "when": true},
    "presence": {"persons": "all", "op": ">=", "value": 1},
    "responses": {"경보": {"present": "사람 있을 때 대응", "absent": "없을 때"}},
    "accident_prevented_at": "최고 경보"}},
 "modes": {"평상시": {"default": true, "zones": ["*"]},
           "<모드>": {"when": {"fact": "ptw"}, "scope": "all", "zones": ["Z8"], "judge": ["<판정표>"],
                      "checks": [{"type": "no_entry", "polygons": ["restricted"], "violation": "진입",
                                  "level": "경보", "dwell_s": 1, "shadow_when_off": true}]}},
 "gates": [{"id": "g1", "type": "missing_in_document", "on_document": "isolation_list", "enabled": "@require_list",
            "document_field": "line_id", "ref": "piping", "ref_field": "id", "violation": "목록_누락"}],
 "rule_changes": {"R1": {"text": "개정 내용", "set": {"vars.require_list": true}, "add": {"vars.hazard_sources": ["fuel_gas"]}}}}
```
- **판정표**: 축은 위에서부터 첫 번째로 맞는 상태, 줄도 위에서부터 첫 번째로 맞는 줄에서 멈춘다. 뒤의 축은 앞의 축을 `axis`로 볼 수 있다. 판정표는 여러 개 둘 수 있다(위험 유형별).
- **단계**: `정상` · `주의` · `경보` · `최고 경보` 네 개로 고정이다. 내려갈 때는 `lower.hold_min` 동안 유지되고 `lower.when`이 맞아야 한 단계씩 내린다.
- **모드**: `scope: all`이면 zones 중 한 곳에서라도 맞을 때 전체에 켜지고, `zone`이면 맞는 구역에만 켜진다. `judge`에 적은 판정표는 모드가 켜져 있을 때만 경보를 울리고, 꺼져 있으면 무음 기록이다.
- **영상 규칙**(`checks.type`): `no_entry` · `min_persons`(`min`) · `max_persons`(`max`). 모두 `when`을 달 수 있다.
- **게이트**(`gates.type`): `missing_in_document`(참조 목록에 있는데 문서에 없는 항목), `required_fields`(`fields`, `time_after_event`).
- **개정안**: `set`은 값 바꾸기, `add`는 목록에 더하기. 경로는 점(.)으로 잇는다.
- `"@이름"`은 vars 값이다. 어떤 조건이든 `"label"`을 달면 거짓일 때 그 이름이 이유로 남는다.

### 조건어
| 조건어 | 참이 되는 때 | 같이 쓰는 키 |
|---|---|---|
| `all` · `any` · `not` | 묶기 | |
| `cond` · `var` | 이름 붙인 조건 / vars 값 | `is` |
| `fact` | 그 상태가 켜져 있다 | `zones`(이 구역들에서만) · `for_min` · `any_zone` |
| `duration` | 마지막으로 켜져 있던 시간 비교 | `op` · `value`(분) |
| `event` | 지워지지 않은 사건이 있다 | `attr`(속성 일치) · `within_min` |
| `measured` | 유효한 측정이 있다 | `max_age_min` · `max` · `min` · `invalidated_by`(이 사건 이전 측정은 무효) · `after: "raise"` |
| `measure` | 최근 측정값 비교 | `op` · `value` · `max_age_min` |
| `covers` | 대상 전부를 쟀다 | `{"measure", "points", "max", "max_age_min"}` |
| `unmarked` | 표시 안 된 대상이 있다 | `{"mark", "points"}` |
| `document` | 그 문서가 들어왔다 | |
| `detect` | 영상 검출 확정 | `hold_min` |
| `persons` | 폴리곤 종류별 인원 비교 | `op` · `value` |
| `video` | 영상이 도는 중이다 | |
| `zone_in` · `zone_attr` | 구역이 목록에 있다 / 구역 속성 | `in` · `is` |
| `axis` | 같은 판정표의 축 상태 | `is` · `in` |

`points`: `{"ref": "piping", "field": "id", "where": "hazard"}` 또는 `{"document": "isolation_list", "field": "line_id"}`. 목록으로 여러 개를 쓰면 합친다.

### cameras/<ID>.json
```json
{"camera_id": "CAM-01", "zone": "Z8",
 "polygons": [{"name": "E5", "type": "hazard", "zone": "Z8", "label": "이름", "space": "image",
               "points": [[0.18, 0.40], [0.52, 0.40], [0.56, 0.78]]}],
 "floor_calib": null}
```
좌표는 화면 비율(0~1)이다. `type`은 규칙이 부르는 이름과 맞춘다. 사람은 발(박스 아래 가운데), 검출 물체는 박스 가운데로 판정한다. `floor_calib`에 바닥 네 점을 넣으면 `space: "floor"`(m) 폴리곤을 쓸 수 있다.

### scenarios/<이름>/
- `timeline.csv`: `time,signal,zone,target,value,source,note`. source 가 `영상`인 줄은 영상 실행 때 넣지 않는다(탐지가 대신 만든다).
- `scenario.json`:
```json
{"name": "이름", "date": "2026-10-12", "zone": "Z8", "table": "<판정표>", "timeline": "timeline.csv",
 "variants": {"개정 전": {"changes": [], "expect": [{"at": "09:15", "level": "주의", "row": 7}]},
              "개정 후": {"changes": ["R1"], "expect": [{"at": "08:05", "gate": "g1"}, {"at": "09:22", "accident": false}]}},
 "scenes": [{"name": "장면", "at": "09:15", "camera": "CAM-01", "video": "videos/a.mp4"}]}
```
`expect`에 쓸 수 있는 것: `{"at", "level", "row"}` · `{"at", "axis": {축: 상태}}` · `{"at", "gate"}` · `{"at", "accident"}` · `{"before", "max_level"}`.

## 출력 — outputs/<시각>/
- `events.jsonl`: 한 줄에 이벤트 하나. `kind`는 stage(판정표) · check(영상 규칙) · gate · accident · info. 필드는 docgen 이벤트와 같다(event_id · ts · zone · mode · violation_type · level · alerted · clip_path …).
- `trace.csv`: 타임라인 실행 때 시각별 축 · 줄 · 단계 · 모드 · 근거.
- `clips/` · `frames/` · `detect_summary.json` · `events_for_docgen.json`: 영상 실행 때 나온다.

### 문서 자동화로 넘기기 (관제 인계)
관제와 문서 자동화는 한 프로그램이다. 감지 내역은 `docgen/safety_docs/handoff.py` 의 `receive()` 로 넘긴다.
```python
from safety_docs.handoff import receive
receive(log.rows, source="실시간 관제", base_dir=out_dir)   # log = EventLog, out_dir = 이 실행의 출력 폴더
```
`kind` 가 stage · check 인 것만 문서 자동화 이벤트가 되고, 프레임(`frames/`)은 docgen 쪽으로 복사된다.
게이트 · 사고는 인계 기록에만 남아 ‘작업허가서 점검 · 산업재해조사표’ 안내로 쓰인다.
관제 화면 없이 시험할 때는 문서 자동화의 안전 문서 › 관제 인계에 `events.jsonl` 이나 `events_for_docgen.json` 을 올린다.
문서 자동화에서 위험성평가가 확정되면 `--changes docgen` 으로 그 개정안을 적용해 돌린다.

## 엔진을 늘릴 때
새 조건어는 `conditions.py`의 `HANDLERS`, 새 게이트는 `gates.py`의 `GATE_TYPES`, 새 영상 규칙은 `checks.py`의 `CHECK_TYPES`에 함수 하나를 더한다. 새 물체 탐지는 `detect.json`의 `extra`에 가중치를 적으면 된다. 코드를 고치지 않아도 되는 일(구역 · 신호 · 판정표 · 모드 · 개정안)은 전부 패키지 쪽이다.

## 여기 없는 것
DB(지금은 파일 기록), PPE(안전모) 탐지 모델, 받을 파일(실제 패키지 · 영상).
관제 화면 · 피드백 루프(자동 조정 · 조정 로그)는 폴더 맨 위 `control/` 에 있다 — 이 엔진을 불러 쓴다 (`python app.py`, 맨 위 README).
