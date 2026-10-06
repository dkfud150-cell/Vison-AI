"""
시정지시서 초안 (현장 이미지 분석 포함)

사람이 사진을 올리는 것이 아니라, 위반 이벤트에 붙은 CCTV 프레임을 시스템이 넘긴다.
그 시점의 규칙셋 · 같은 위반의 최근 건수 · 조치 기한은 코드가 채우고,
LLM은 장면 설명 · 위험 요인 · 위반 사항 · 시정 조치 문장만 쓴다.

  draft_corrective_order()   초안 생성
  log_corrective()           발행 기록 (추가 전용) → 의무 이행 관리의 '조치 기한'으로 이어진다
  list_correctives()         발행한 시정지시서와 조치 완료 여부
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .assessment import CATEGORIES
from .config import RECORD_DIR, ROOT, append_jsonl, latest_by, legal_ref, now, read_jsonl, zone_name
from .llm import LLMClient
from .risk import correction_deadline, correction_deadline_date, severity_level

CORRECTIVE_LOG = RECORD_DIR / "corrective_log.jsonl"

CORRECTIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "scene": {"type": "string",
                  "description": "영상에서 보이는 현장 상황 2~3문장. 보이지 않는 것은 쓰지 말 것"},
        "hazards": {
            "type": "array", "maxItems": 5,
            "items": {"type": "object",
                      "properties": {"rank": {"type": "integer"},
                                     "hazard": {"type": "string"},
                                     "reason": {"type": "string"}},
                      "required": ["rank", "hazard", "reason"]},
            "description": "위험 기인물·요인 최대 5개, 위험한 순서",
        },
        "violation": {"type": "string", "description": "규칙셋 기준 위반 사항 한두 문장"},
        "corrective_actions": {
            "type": "array",
            "items": {"type": "object",
                      "properties": {"category": {"type": "string", "enum": CATEGORIES},
                                     "text": {"type": "string"}},
                      "required": ["category", "text"]},
        },
        "legal_ids": {"type": "array", "items": {"type": "string"}},
        "uncertain": {"type": "string", "description": "영상만으로 확인할 수 없는 점"},
    },
    "required": ["scene", "hazards", "violation", "corrective_actions", "legal_ids"],
}

SYSTEM = """당신은 철강 산세 공장의 안전관리자입니다. CCTV 프레임과 감지 이벤트 정보를 보고 시정지시서 초안을 씁니다.
규칙:
- 이미지에서 실제로 보이는 것만 scene 에 쓰세요. 추정은 uncertain 에 따로 적으세요.
- 위반 판단은 제공된 규칙셋 기준으로만 하세요.
- 시정 조치는 공학적 → 관리적 → 보호구 순으로 검토하세요.
- 법적 근거는 제공된 조문 목록 id 중에서만 고르세요.
- 특정 개인을 지목하지 마세요.
- 조치 기한·문서번호·날짜는 시스템이 채우므로 쓰지 마세요."""


def _prompt(ev, rulesets, legal, same_recent):
    m = rulesets["modes"].get(ev["mode"], {})
    legal_list = "\n".join(f"- {a['id']}: {a['law']} {a['article']}({a['title']})"
                           for a in legal.values())
    return f"""[감지 이벤트]
- 이벤트: {ev['event_id']} / {ev['ts']}
- 구역: {ev['zone']} {zone_name(rulesets, ev['zone'])}
- 작업 모드: {ev['mode']} (트리거: {m.get('trigger', '-')})
- 감지된 위반: {ev['violation_type']} (판정 단계: {ev.get('level') or '-'})
- 적용 규칙: {'자동 강화 중 (' + ev['adj_id'] + ')' if ev.get('adj_id') else '기본 규칙'}
- 같은 구역·같은 위반 최근 14일: {same_recent}건

[이 모드의 규칙셋]
- 필수 보호구: {', '.join(m.get('ppe', []))}
- 규칙: {'; '.join(m.get('rules', [])) or '-'}
- 최소 인원: {m.get('min_persons', '-')}, 화재감시자: {m.get('fire_watch', '-')}

[고를 수 있는 법 조문]
{legal_list}

첨부한 CCTV 프레임을 보고 시정지시서 초안을 작성하세요."""


def draft_corrective_order(ev: dict, events: list[dict], rulesets, legal, scales,
                           llm: LLMClient | None = None, issued: datetime | None = None) -> dict:
    llm = llm or LLMClient()
    issued = issued or now()

    # 같은 구역·모드·위반의 최근 14일 건수 (오탐·무음 제외) — 코드가 센다
    since = ev["_ts"] - timedelta(days=14)
    same_recent = sum(1 for e in events
                      if e["zone"] == ev["zone"] and e["violation_type"] == ev["violation_type"]
                      and e["mode"] == ev["mode"] and e.get("alerted", True)
                      and not e.get("false_positive") and since <= e["_ts"] <= ev["_ts"])

    images = []
    if ev.get("frame_path") and (ROOT / ev["frame_path"]).exists():
        images.append(str(ROOT / ev["frame_path"]))

    warnings = []
    try:
        raw = llm.generate_json("corrective", SYSTEM, _prompt(ev, rulesets, legal, same_recent),
                                CORRECTIVE_SCHEMA, images=images, mock_key=ev["event_id"])
    except Exception as ex:                 # 시연 중 API 장애 — 문서는 반드시 나와야 한다
        m = rulesets["modes"].get(ev["mode"], {})
        raw = {"scene": "(LLM 호출 실패 — 프레임을 보고 직접 작성)", "hazards": [],
               "violation": f"{ev['mode']} 모드에서 {ev['violation_type'].replace('_', ' ')} 감지 "
                            f"(판정 {ev.get('level') or '-'}). 적용 규칙: {'; '.join(m.get('rules', [])) or '-'}",
               "corrective_actions": [{"category": "관리적", "text": "시정 조치 직접 작성"}],
               "legal_ids": [], "uncertain": ""}
        warnings.append(f"LLM 호출 실패({str(ex)[:120]}) — 템플릿 문장")
    legal_ids = [i for i in raw.get("legal_ids", []) if i in legal]
    for i in raw.get("legal_ids", []):
        if i not in legal:
            warnings.append(f"목록에 없는 조문 제외: {i}")
    for i in legal_ids:
        if not legal[i].get("verified", True):
            warnings.append(f"{legal[i]['article']} 은 세부 호를 원문과 대조하지 못함")
    actions = [a for a in raw.get("corrective_actions", []) if a.get("category") in CATEGORIES]
    hazards = sorted(raw.get("hazards", []), key=lambda h: h.get("rank", 99))[:5]
    if not images:
        warnings.append("프레임 이미지가 없어 이벤트 정보만으로 작성됨")

    S, S_label = severity_level(ev["violation_type"], scales, ev["mode"])
    return {
        # EV-1044 → CO-…-1044, 관제 엔진의 EV-10120915-003 → CO-…-10120915-003 (끝 번호만 쓰면 겹친다)
        "doc_no": f"CO-{issued:%Y%m%d}-{ev['event_id'].split('-', 1)[-1]}",
        "issued": issued.strftime("%Y-%m-%d %H:%M"),
        "event": {k: v for k, v in ev.items() if not k.startswith("_")},
        "zone_name": zone_name(rulesets, ev["zone"]),
        "rule_state": f"자동 강화 중 ({ev['adj_id']})" if ev.get("adj_id") else "기본 규칙",
        "same_recent": same_recent,
        "severity": S, "severity_label": S_label,
        "deadline": correction_deadline(S, issued, scales),
        "deadline_date": correction_deadline_date(S, issued, scales),
        "frame_path": images[0] if images else None,
        "scene": raw.get("scene", "").strip(),
        "hazards": hazards,
        "violation": raw.get("violation", "").strip(),
        "actions": actions,
        "legal_ids": legal_ids,
        "legal_refs": [legal_ref(legal[i]) for i in legal_ids],
        "uncertain": raw.get("uncertain", "").strip(),
        "warnings": warnings,
    }


def log_corrective(order: dict, docx_path: str | None = None) -> None:
    """
    발행한 시정지시서를 기록한다 (추가 전용).
    의무 이행 관리 화면이 이 기록을 읽어 '조치 기한' 알림을 만든다.
    같은 문서번호를 다시 만들면 나중 줄이 앞 줄을 덮어쓴 것으로 본다.
    """
    ev = order["event"]
    append_jsonl(CORRECTIVE_LOG, {
        "doc_no": order["doc_no"], "event_id": ev["event_id"], "issued": order["issued"],
        "deadline_date": order["deadline_date"], "severity": order["severity"],
        "zone": ev["zone"], "mode": ev["mode"], "violation_type": ev["violation_type"],
        "summary": order["violation"][:80], "file": docx_path, "state": "issued"})


def list_correctives() -> list[dict]:
    """발행 기록의 문서별 마지막 상태."""
    return list(latest_by(read_jsonl(CORRECTIVE_LOG), "doc_no").values())
