# 예시 데이터 — 기능 확인용, 지워도 된다

프로그램이 돌아가는지 확인하려고 만든 가짜 데이터다. 시스템 코드가 아니다.
실제 데이터를 받으면 **이 폴더를 통째로 지운다.** 코드는 이 폴더가 없으면 예시 없이 돈다.

```
예시데이터_삭제가능/
├─ 사업장패키지/
│  ├─ steel_pickling/          산세 공장 — 구역 Z1~Z10 · 신호 사전 · 판정표 · 개정안 R1~R4 · 카메라 1대
│  │  ├─ scenarios/            시나리오 A(파단 절단) · B(맹판 격리) — 타임라인 CSV · 기대 결과
│  │  ├─ videos/               합성 테스트 영상 1개 (AI 생성 영상이 오면 바꾼다)
│  │  └─ dashboard.json        관제 화면 시연 기본값(스케줄 B · 먼저 볼 구역) · 구역 → 부서 대응
│  └─ confined_space_example/  다른 업종 · 다른 판정표(질식) — 엔진이 특정 공정을 모르는지 확인용
├─ 문서자동화/
│  ├─ events.json · frames/    도입 전 관제 기록처럼 쓰는 이벤트 51건 · 위반 순간 프레임 3장
│  ├─ ptw/                     작업허가서 2건 · 격리 목록 (FG-02 를 일부러 뺐다)
│  ├─ voice_seed.json          근로자 제보 3건
│  ├─ site_profile.json        시연 날짜(2026-10-12) · 샘플 사고 4건 · 의무별 마지막 실시일
│  ├─ staff.json               이행 처리 담당자(가상 인물)
│  └─ make_sample_data.py      events.json · frames/ 를 다시 만드는 스크립트
└─ 관제/
   └─ sample_adjustments.jsonl 예시 이벤트에 붙은 자동 조정 기록 3건
```

## 지우면 어떻게 되나

| 화면 | 예시가 있을 때 | 지운 뒤 |
| --- | --- | --- |
| 관제 전부 | 예시 패키지로 돈다 | **실제 사업장 패키지가 있어야 켜진다** — 아래 '실제 데이터 넣기' |
| 이벤트 로그 · 히트맵 · 통계 | 예시 이벤트 51건 + 실시간 세션 기록 | 실시간 세션 기록만 (`control/records/live/`) |
| 피드백 · 조정 로그 | 예시 조정 3건 + 실제 조정 | 실제 조정만 (`control/records/adjustments.jsonl`) |
| 재생 비교 | 시나리오 A · B | 실제 패키지의 시나리오 (없으면 빈 목록) |
| 문서 자동화 — 이벤트 · 허가서 · 제보 | 예시 + 관제 인계 · 입력창 등록 | 관제 인계 · 입력창 등록 · 실제 제보만 (`docgen/records/`) |
| 시연 날짜 | 2026-10-12 로 고정 | 진짜 오늘 |
| 사고 · 마지막 실시일 · 담당자 | 예시 값 | `docgen/config/site_profile.json` · `staff.json` 에 적은 것 |

지우지 않고 잠깐 끄기만 하려면 `docgen/.env` 에 `DOCGEN_SAMPLE_DATA=off` (패키지는 그대로 쓴다).

## 실제 데이터 넣기

1. **사업장 패키지** — 받은 폴더를 `monitor_engine/packages/<이름>/` 에 넣고, `control/config.json` 의 `package` 에 이름을 적는다.
   규격은 `monitor_engine/README.md` '입력 파일 규격 — 패키지'. `python monitor_engine/validate.py <이름>` 으로 검사한다.
   관제 화면용 `dashboard.json`(시연 기본값 · 부서 대응)은 선택이다 — 이 폴더의 것을 본떠 만든다.
2. **사업장 정보** — `docgen/config/site_profile.json` (사업장 이름 · 업종 · 인원 · 의무별 마지막 실시일 · 사고).
3. **담당자** — `docgen/config/staff.json`.
4. **관제 기록** — 실시간 관제가 돌면서 `control/records/` 에 쌓고, 문서 자동화로 자동 인계된다. 따로 넣을 것은 없다.
   DB 에서 읽게 바꿀 때는 `docgen/safety_docs/config.py` 의 `load_events()` 와 `control/common.py` 의 `load_control_events()`.
5. **영상** — 패키지 `scenarios/<시나리오>/scenario.json` 의 `scenes` 에 경로를 적거나, 카메라를 직접 붙인다(`monitor_engine/README.md`).

`docgen/mock/` 의 미리 써 둔 문장(LLM 없이 도는 mock 모드)은 예시 이벤트 번호에 맞춰 쓴 것이다.
실제 데이터로는 Claude · OpenAI 키를 `docgen/.env` 에 넣고 쓴다.
