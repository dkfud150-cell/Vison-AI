"""
안전소통 — 근로자 위험제보 · 아차사고 · 건의를 받고 조치까지 기록한다.

근거
  - 중대재해처벌법 시행령 제4조제7호: 종사자 의견 청취 절차, 개선방안 이행 여부 반기 1회 이상 점검
  - 위험성평가 지침 제15조제4항제1호: 근로자 제안 · 아차사고 확인으로 유해·위험요인 발굴(상시평가)

기록: records/voice_log.jsonl (추가 전용). 접수 한 줄, 상태가 바뀔 때마다 한 줄 더.
예시 제보(예시데이터_삭제가능/문서자동화/voice_seed.json)는 기록이 없어도 화면이 비지 않게 앞에 붙인다.

  submit_report()    제보 접수 (제보자는 비우면 익명)
  update_report()    상태 변경 — 접수 → 조치 중 → 완료 (완료는 조치 내용 필수)
  list_reports()     제보별 현재 상태
  voice_summary()    총 · 완료 · 미조치 · 조치율
"""
from __future__ import annotations

import json
from datetime import datetime

from .config import RECORD_DIR, SAMPLE_DIR, append_jsonl, latest_by, now, read_jsonl, use_sample_data

VOICE_LOG = RECORD_DIR / "voice_log.jsonl"
KINDS = ["위험제보", "아차사고", "건의"]
STATES = ["접수", "조치 중", "완료"]


def _seed() -> list[dict]:
    p = SAMPLE_DIR / "voice_seed.json"
    if not use_sample_data() or not p.exists():
        return []
    return [{**r, "sample": True} for r in json.loads(p.read_text(encoding="utf-8"))["reports"]]


def list_reports() -> list[dict]:
    rows = _seed() + read_jsonl(VOICE_LOG)
    out = list(latest_by(rows, "report_id").values())
    out.sort(key=lambda r: r["ts"], reverse=True)
    return out


def _next_id(t: datetime) -> str:
    n = sum(1 for r in list_reports() if r["report_id"].startswith(f"V-{t:%Y}-")) + 1
    return f"V-{t:%Y}-{n:03d}"


def submit_report(kind: str, zone: str, text: str, reporter: str = "") -> dict:
    if kind not in KINDS:
        raise ValueError(f"구분은 {', '.join(KINDS)} 중 하나입니다.")
    if not text.strip():
        raise ValueError("내용을 적어 주세요.")
    t = now()
    return append_jsonl(VOICE_LOG, {"report_id": _next_id(t), "ts": t.isoformat(timespec="minutes"),
                                    "kind": kind, "zone": zone, "text": text.strip(),
                                    "reporter": reporter.strip(), "state": "접수", "action": "", "by": ""})


def update_report(report_id: str, state: str, action: str, by: str) -> dict:
    if state not in STATES:
        raise ValueError(f"상태는 {', '.join(STATES)} 중 하나입니다.")
    if not by.strip():
        raise ValueError("처리자 이름을 적어 주세요.")
    if state == "완료" and not action.strip():
        raise ValueError("완료로 바꾸려면 조치 내용을 적어야 합니다.")
    if report_id not in {r["report_id"] for r in list_reports()}:
        raise ValueError(f"없는 제보 번호: {report_id}")
    return append_jsonl(VOICE_LOG, {"report_id": report_id, "state": state, "action": action.strip(),
                                    "by": by.strip(), "updated": now().isoformat(timespec="minutes")})


def voice_summary(reports: list[dict] | None = None) -> dict:
    reports = reports if reports is not None else list_reports()
    total = len(reports)
    done = sum(1 for r in reports if r["state"] == "완료")
    return {"total": total, "done": done, "open": total - done,
            "rate": (done / total * 100) if total else 0.0}
