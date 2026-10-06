"""
산업재해조사표 초안 (산업안전보건법 시행규칙 별지 제30호서식 기준)

사람이 기억해서 쓰는 대신, 사고 전후의 관제 기록으로 경과를 채운다.
  - 발생 일시·장소·구역, 사고 전 타임라인, 그 시각 적용 중이던 규칙(adj_id), 관련 허가서 → 코드
  - 경과 서술 · 재발방지 계획 초안 → LLM (원인을 단정하지 않는다)
  - 재해자 인적사항 · 원인 판단 · 제출 → 사람

  build_accident_facts()   코드가 채우는 칸
  draft_accident_report()  LLM 문장 + 실패 시 템플릿
  log_accident_report()    작성 기록 (추가 전용)

제출 기한: 재해 발생일부터 1개월 이내 (산업안전보건법 제57조제3항, 시행규칙 제73조제1항)
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .assessment import CATEGORIES
from .compliance import add_months
from .config import RECORD_DIR, append_jsonl, latest_by, now, read_jsonl, zone_name
from .llm import LLMClient

ACC_LOG = RECORD_DIR / "accident_reports.jsonl"
LOOKBACK_HOURS = 3

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "narrative": {"type": "string",
                      "description": "재해 발생 경과 3~5문장. 타임라인 순서대로, 기록에 있는 사실만. 원인 단정 금지"},
        "prevention": {"type": "array",
                       "items": {"type": "object",
                                 "properties": {"category": {"type": "string", "enum": CATEGORIES},
                                                "text": {"type": "string"}},
                                 "required": ["category", "text"]},
                       "description": "재발방지 계획 초안 2~4개"},
        "check_needed": {"type": "string", "description": "기록만으로 알 수 없어 조사자가 확인할 점"},
    },
    "required": ["narrative", "prevention"],
}

SYSTEM = """당신은 산업재해조사표 초안을 쓰는 안전관리자입니다.
규칙:
- 제공된 타임라인과 기록에 있는 사실만 쓰세요. 추정은 check_needed 에 적으세요.
- 원인을 단정하지 마세요("~때문에 발생했다" 금지). 원인 판단은 조사자가 합니다.
- 재해자나 작업자를 지목하지 마세요.
- 시각·건수 같은 숫자는 제공된 값만 쓰세요."""


def build_accident_facts(acc: dict, events: list[dict], rulesets: dict, ptws: list[dict]) -> dict:
    at = datetime.fromisoformat(f"{acc['date']}T{acc.get('time', '00:00')}")
    since = at - timedelta(hours=LOOKBACK_HOURS)
    timeline = []
    for p in ptws:
        if p["ptw_id"] in acc.get("ptw_ids", []):
            timeline.append({"ts": p["start"], "what": f"허가 {p['ptw_id']} 시작 — {p['work']}", "src": "PTW"})
    for e in sorted(events, key=lambda x: x["_ts"]):
        if e["zone"] != acc["zone"] or not (since <= e["_ts"] <= at):
            continue
        rule = f"강화 중 {e['adj_id']}" if e.get("adj_id") else "기본 규칙"
        lvl = e.get("level") or "무음 기록"
        timeline.append({"ts": e["ts"], "what": f"{e['violation_type']} · {lvl} · {rule}",
                         "src": e["event_id"], "clip": e.get("clip_path")})
    timeline.append({"ts": at.isoformat(timespec="minutes"), "what": acc["summary"], "src": acc["id"]})
    timeline.sort(key=lambda x: x["ts"])
    adj_ids = sorted({e.get("adj_id") for e in events if e.get("adj_id") and e["zone"] == acc["zone"]
                      and since <= e["_ts"] <= at})
    return {
        "acc": acc, "at": at.isoformat(timespec="minutes"),
        "zone_label": f"{acc['zone']} {zone_name(rulesets, acc['zone'])}",
        "timeline": timeline, "active_adjustments": adj_ids,
        "lookback_hours": LOOKBACK_HOURS,
        "due": add_months(at.date(), 1).isoformat(),     # 발생일부터 1개월 이내
    }


def _template(f: dict) -> dict:
    steps = " → ".join(f"{t['ts'][11:16]} {t['what']}" for t in f["timeline"])
    return {"narrative": f"기록된 경과: {steps}",
            "prevention": [{"category": "관리적", "text": "조사 결과에 따라 작성"}],
            "check_needed": "LLM 없이 템플릿으로 작성됨 — 경과 서술과 재발방지 계획을 직접 작성"}


def draft_accident_report(facts: dict, llm: LLMClient | None = None) -> dict:
    llm = llm or LLMClient()
    acc = facts["acc"]
    tl = "\n".join(f"- {t['ts'].replace('T', ' ')} [{t['src']}] {t['what']}" for t in facts["timeline"])
    user = f"""[재해]
- 번호: {acc['id']} / 발생 {facts['at'].replace('T', ' ')} / 장소 {facts['zone_label']}
- 개요: {acc['summary']} / 부상 {acc.get('injured', '-')}명 / 휴업 {acc.get('lost_days', '-')}일

[사고 전 {facts['lookback_hours']}시간 관제 기록과 허가]
{tl}

- 그 시각 적용 중이던 자동 조정: {', '.join(facts['active_adjustments']) or '없음 (기본 규칙)'}

산업재해조사표의 경과 서술과 재발방지 계획 초안을 쓰세요."""
    source = "LLM"
    try:
        raw = llm.generate_json("accident", SYSTEM, user, REPORT_SCHEMA, mock_key=acc["id"])
    except Exception as ex:                 # 시연 중 API 장애 — 문서는 반드시 나와야 한다
        raw, source = _template(facts), f"템플릿 (LLM 실패: {str(ex)[:80]})"
    prevention = [p for p in raw.get("prevention", []) if p.get("category") in CATEGORIES and p.get("text")]
    return {**facts, "narrative": raw.get("narrative", "").strip() or _template(facts)["narrative"],
            "prevention": prevention or _template(facts)["prevention"],
            "check_needed": raw.get("check_needed", "").strip(), "text_source": source,
            "drafted_at": now().isoformat(timespec="seconds")}


def log_accident_report(report: dict, docx_path: str | None = None) -> dict:
    acc = report["acc"]
    return append_jsonl(ACC_LOG, {"report_id": f"AR-{acc['id']}", "acc_id": acc["id"],
                                  "ts": report["drafted_at"], "zone": acc["zone"], "due": report["due"],
                                  "summary": acc["summary"], "file": docx_path, "state": "draft"})


def list_accident_reports() -> list[dict]:
    return list(latest_by(read_jsonl(ACC_LOG), "report_id").values())
