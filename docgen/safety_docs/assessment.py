"""
위험성평가 — 초안 작성(LLM)과 사람 확정 (두 단계 서명)

  build_rows()           이벤트 → 집계 → 위험도 계산 (코드)
  draft_assessment()     계산된 행마다 LLM이 문장 부분만 채운다
  submit_for_review()    관리자가 검토·수정 후 서명 → 근로자 확인 대기
  confirm_revision()     근로자 대표가 확인 → 확정. 감소대책이 가리킨 규칙 변경(R1~R4)이 규칙셋에 반영된다
  reject_revision()      반려 (사유 필수) — 평가 전체를 돌려보낸다
  reject_rule()          규칙 변경안 하나만 반려 (사유 필수) — 평가는 그대로 근로자 확인을 기다리고,
                         확정할 때 그 변경안만 규칙셋에 올리지 않는다. 관제 › 피드백 · 조정 로그(긴 루프)에서 누른다
  restore_rule()         변경안 반려 취소 — 근로자 확인 전까지만

저장 방식 (추가 전용)
  records/assessments/RA-*.json   관리자가 서명한 순간의 평가표 내용. 이후 고치지 않는다
  records/revision_log.jsonl      상태 변화(submitted → confirmed / rejected)를 한 줄씩 추가
  records/ruleset_log.jsonl       확정으로 오른 규칙셋 버전
  records/rule_rejections.jsonl   변경안 단위 반려 · 반려 취소 (평가 번호 + 변경안 id). 마지막 줄이 현재 상태
  현재 상태 = revision_log 에서 그 RA 의 마지막 줄
"""
from __future__ import annotations

import json

from .config import RECORD_DIR, append_jsonl, legal_ref, now, read_jsonl, zone_name
from .llm import LLMClient
from .risk import aggregate_events, calc_risk, check_adhoc_review, row_key

CATEGORIES = ["공학적", "관리적", "보호구"]
RA_DIR = RECORD_DIR / "assessments"
REVISION_LOG = RECORD_DIR / "revision_log.jsonl"
RULESET_LOG = RECORD_DIR / "ruleset_log.jsonl"
RULE_REJECT_LOG = RECORD_DIR / "rule_rejections.jsonl"

# LLM이 돌려줄 형식. 숫자 칸은 일부러 없다.
ASSESSMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "unit_work": {"type": "string", "description": "단위작업 이름 (모드·구역 기준, 20자 이내)"},
        "hazard": {"type": "string", "description": "유해·위험요인 한 줄 제목"},
        "cause": {"type": "string", "description": "발생 원인·상황 1~2문장. 원인을 단정하지 말고 감지 근거로 서술"},
        "current_measures": {"type": "array", "items": {"type": "string"},
                             "description": "규칙셋에 적힌 현재 안전조치만. 새로 지어내지 말 것"},
        "measures": {
            "type": "array",
            "items": {"type": "object",
                      "properties": {"category": {"type": "string", "enum": CATEGORIES},
                                     "text": {"type": "string"},
                                     "rule_id": {"type": "string",
                                                 "description": "이 대책이 규칙셋 변경안 목록의 어느 것과 같으면 그 id, 아니면 빈 문자열"}},
                      "required": ["category", "text"]},
            "description": "감소대책 2~4개. 공학적 > 관리적 > 보호구 순으로 우선 검토",
        },
        "legal_ids": {"type": "array", "items": {"type": "string"},
                      "description": "제공된 조문 목록의 id 중 1~3개"},
        "check_needed": {"type": "string", "description": "현장 확인이 필요한 점 (없으면 빈 문자열)"},
    },
    "required": ["unit_work", "hazard", "cause", "current_measures", "measures", "legal_ids"],
}

SYSTEM = """당신은 한국 제조업(철강 산세 공장) 사업장의 위험성평가 초안을 쓰는 산업안전 담당자입니다.
규칙:
- 가능성·중대성·위험도 숫자는 이미 시스템이 계산했습니다. 숫자를 바꾸거나 새로 제시하지 마세요.
- 현재 안전조치는 제공된 규칙셋 내용에서만 가져오세요.
- 감소대책은 공학적 대책을 먼저 검토하고, 관리적 대책과 보호구는 보완으로 제시하세요.
- 감소대책이 제공된 규칙셋 변경안과 같은 내용이면 그 id(R1 등)를 rule_id 에 적으세요.
- 법적 근거는 제공된 조문 목록의 id 중에서만 고르세요. 맞는 조문이 없으면 빈 배열로 두세요.
- 특정 개인을 지목하거나 원인을 단정하지 마세요. 이것은 조사 결과가 아니라 초안입니다.
- 영상 감지만으로 알 수 없는 사실은 check_needed 에 적으세요.
- 한국어, 짧은 문장, 현장 용어를 쓰세요."""


def build_rows(events, as_of, scales, accidents=None):
    """이벤트 → 집계 → 위험도. LLM 없이 끝나는 부분이라 홈 화면도 이걸 쓴다."""
    rows = calc_risk(aggregate_events(events, as_of, scales), scales, accidents)
    adhoc = check_adhoc_review(rows, scales)
    adhoc_keys = {(a["zone"], a["mode"], a["violation_type"]): a["reasons"] for a in adhoc}
    for r in rows:
        r["adhoc_reasons"] = adhoc_keys.get((r["zone"], r["mode"], r["violation_type"]), [])
    return rows, adhoc


def _prompt(r, rulesets, legal) -> str:
    mode_rules = rulesets["modes"].get(r["mode"], {})
    legal_list = "\n".join(f"- {a['id']}: {a['law']} {a['article']}({a['title']}) — {a['summary']}"
                           for a in legal.values())
    changes = "\n".join(f"- {k}: {v}" for k, v in rulesets.get("rule_changes", {}).items()
                        if not k.startswith("_"))
    acc = f"\n- 이어진 사고: {', '.join(r['accident_ids'])}" if r.get("accident_ids") else ""
    return f"""[평가 대상]
- 구역: {r['zone']} {zone_name(rulesets, r['zone'])}
- 작업 모드: {r['mode']} (트리거: {mode_rules.get('trigger', '-')})
- 감지된 위반 유형: {r['violation_type']}

[감지 근거 — {r['window_from'][:10]} ~ {r['window_to'][:10]}]
- 기본 규칙으로 잡힌 위반: {r['base_count']}건 (최근 14일 {r['recent_count']}건)
- 강화 기간에 잡힌 위반: {r['adj_count']}건 (참고용)
- 최고 경보: {r['top_alert_count']}건{acc}

[시스템이 계산한 값 — 바꾸지 말 것]
- 가능성 {r['likelihood']} ({r['likelihood_label']}) × 중대성 {r['severity']} ({r['severity_label']}) = 위험도 {r['score']} ({r['grade']})

[이 모드의 규칙셋 = 현재 안전조치]
- 필수 보호구: {', '.join(mode_rules.get('ppe', []))}
- 규칙: {'; '.join(mode_rules.get('rules', [])) or '-'}
- 최소 인원: {mode_rules.get('min_persons', '-')}, 화재감시자: {mode_rules.get('fire_watch', '-')}

[규칙셋 변경안 — 대책이 같은 내용이면 rule_id 로 연결]
{changes or '-'}

[고를 수 있는 법 조문]
{legal_list}

위 정보로 위험성평가표 한 행의 문장 부분을 작성하세요."""


def _validate(raw: dict, legal: dict, rule_changes: dict) -> tuple[dict, list[str]]:
    """LLM 결과 검사. 목록 밖 조문·규칙 id·이상한 구분은 버리고, 버린 내용은 경고로 남긴다."""
    warnings = []
    ids = []
    for i in raw.get("legal_ids", []):
        if i in legal:
            ids.append(i)
        else:
            warnings.append(f"목록에 없는 조문 제외: {i}")
    measures = []
    for m in raw.get("measures", []):
        if m.get("category") not in CATEGORIES or not m.get("text", "").strip():
            warnings.append(f"구분이 잘못된 대책 제외: {m}")
            continue
        rid = (m.get("rule_id") or "").strip()
        if rid and rid not in rule_changes:
            warnings.append(f"규칙셋 변경안에 없는 id 제외: {rid}")
            rid = ""
        measures.append({"category": m["category"], "text": m["text"].strip(), "rule_id": rid})
    if not measures:
        warnings.append("감소대책이 비어 있음 — 직접 작성 필요")
    for i in ids:
        if not legal[i].get("verified", True):
            warnings.append(f"{legal[i]['article']} 은 세부 호를 원문과 대조하지 못함")
    clean = {
        "unit_work": raw.get("unit_work", "").strip(),
        "hazard": raw.get("hazard", "").strip(),
        "cause": raw.get("cause", "").strip(),
        "current_measures": [s.strip() for s in raw.get("current_measures", []) if s.strip()],
        "measures": measures,
        "legal_ids": ids,
        "check_needed": raw.get("check_needed", "").strip(),
    }
    return clean, warnings


def _template(r, rulesets) -> dict:
    """LLM이 실패했을 때의 문장. 숫자와 규칙셋에서 바로 만들 수 있는 것만 채운다."""
    m = rulesets["modes"].get(r["mode"], {})
    return {"unit_work": f"{r['mode']} ({r['zone']})", "hazard": r["violation_type"].replace("_", " "),
            "cause": f"최근 {r['window_from'][:10]}~{r['window_to'][:10]} 기본 규칙 위반 {r['base_count']}건 감지.",
            "current_measures": m.get("rules", []),
            "measures": [{"category": "관리적", "text": "감소대책 직접 작성", "rule_id": ""}],
            "legal_ids": [], "check_needed": ""}


def draft_assessment(rows, rulesets, legal, scales, llm: LLMClient | None = None,
                     progress=None) -> list[dict]:
    """계산된 각 행에 LLM 문장을 붙인다. 개선 후 위험도는 비워 둔다 — 적용 후 실측한다."""
    llm = llm or LLMClient()
    rule_changes = {k: v for k, v in rulesets.get("rule_changes", {}).items() if not k.startswith("_")}
    drafts = []
    for n, r in enumerate(rows, 1):
        if progress:
            progress(n, len(rows), row_key(r))
        try:
            raw = llm.generate_json("assessment", SYSTEM, _prompt(r, rulesets, legal),
                                    ASSESSMENT_SCHEMA, mock_key=row_key(r))
            fallback = False
        except Exception as ex:             # 시연 중 API 장애 — 문서는 반드시 나와야 한다
            raw, fallback = _template(r, rulesets), str(ex)[:120]
        text, warnings = _validate(raw, legal, rule_changes)
        if fallback:
            warnings.insert(0, f"LLM 호출 실패({fallback}) — 템플릿 문장. 문장 칸을 직접 작성")
        drafts.append({**{k: v for k, v in r.items() if not k.startswith("_")}, **text,
                       "after": None, "warnings": warnings,
                       "legal_refs": [legal_ref(legal[i]) for i in text["legal_ids"]]})
    return drafts


# ------------------------------------------------------------------ 확정 (두 단계)
def _now() -> str:
    return now().isoformat(timespec="seconds")


def submit_for_review(drafts: list[dict], manager: str, kind: str = "수시", note: str = "") -> dict:
    """관리자 검토·서명. 이 순간의 평가표 내용을 저장하고 근로자 확인을 기다린다."""
    if not drafts:
        raise ValueError("서명할 초안이 없습니다.")
    if not manager.strip():
        raise ValueError("관리자 이름을 입력해야 서명할 수 있습니다.")
    t = now()
    ra_id = f"RA-{t:%Y%m%d-%H%M%S}"
    record = {
        "ra_id": ra_id, "kind": kind, "created_at": t.isoformat(timespec="seconds"),
        "manager": manager.strip(), "manager_note": note.strip(),
        "basis_period": [drafts[0]["window_from"], drafts[0]["window_to"]],
        "rows": [{k: v for k, v in d.items() if not k.startswith("_")} for d in drafts],
    }
    RA_DIR.mkdir(parents=True, exist_ok=True)
    (RA_DIR / f"{ra_id}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    append_jsonl(REVISION_LOG, {"ra_id": ra_id, "ts": record["created_at"], "state": "submitted",
                                "role": "관리자", "name": record["manager"], "kind": kind,
                                "rows": len(drafts), "note": record["manager_note"]})
    return get_assessment(ra_id)


def confirm_revision(ra_id: str, worker_rep: str, note: str = "") -> dict:
    """
    근로자 대표 확인 → 확정 (산업안전보건법 제36조제2항 · 위험성평가 지침 제6조 근로자 참여).
    감소대책에 연결된 규칙 변경(R1~R4)이 있으면 규칙셋 버전을 올려 기록한다.
    """
    ra = get_assessment(ra_id)
    if ra["state"] != "worker_pending":
        raise ValueError(f"{ra_id} 는 근로자 확인 대기 상태가 아닙니다 ({ra['state_label']}).")
    if not worker_rep.strip():
        raise ValueError("근로자 대표 이름을 입력해야 확인할 수 있습니다.")
    ts = _now()
    excluded = sorted(ra.get("rule_rejected", {}))            # 변경안 단위로 반려된 것은 규칙셋에 올리지 않는다
    append_jsonl(REVISION_LOG, {"ra_id": ra_id, "ts": ts, "state": "confirmed", "role": "근로자 대표",
                                "name": worker_rep.strip(), "manager": ra["manager"],
                                "worker_rep": worker_rep.strip(), "note": note.strip(),
                                **({"rules_excluded": excluded} if excluded else {})})
    rule_ids = sorted(set(linked_rules(ra)) - set(excluded))
    if rule_ids:
        append_jsonl(RULESET_LOG, {"version": current_ruleset_version() + 1, "ts": ts, "ra_id": ra_id,
                                   "rule_ids": rule_ids, "by": f"{ra['manager']} · {worker_rep.strip()}"})
    return get_assessment(ra_id)


def reject_revision(ra_id: str, role: str, name: str, reason: str) -> dict:
    """반려. 사유가 없으면 반려할 수 없다."""
    if not name.strip() or not reason.strip():
        raise ValueError("반려하려면 이름과 사유를 모두 적어야 합니다.")
    ra = get_assessment(ra_id)
    if ra["state"] != "worker_pending":
        raise ValueError(f"{ra_id} 는 반려할 수 있는 상태가 아닙니다 ({ra['state_label']}).")
    append_jsonl(REVISION_LOG, {"ra_id": ra_id, "ts": _now(), "state": "rejected", "role": role,
                                "name": name.strip(), "note": reason.strip()})
    return get_assessment(ra_id)


def linked_rules(ra: dict) -> list[str]:
    """평가표 감소대책에 연결된 규칙 변경안 id (R1 …)."""
    return sorted({m["rule_id"] for r in ra.get("rows", []) for m in r.get("measures", []) if m.get("rule_id")})


def _rule_change(ra_id: str, rule_id: str, state: str, role: str, name: str, note: str) -> dict:
    ra = get_assessment(ra_id)
    if ra["state"] != "worker_pending":
        raise ValueError(f"{ra_id} 는 근로자 확인 대기가 아니라 변경안을 {'반려' if state == 'rejected' else '되살릴'} 수 없습니다 "
                         f"({ra['state_label']}). 확정된 변경은 새 위험성평가로만 되돌린다.")
    if rule_id not in linked_rules(ra):
        raise ValueError(f"{ra_id} 감소대책에 {rule_id} 가 연결돼 있지 않습니다.")
    return append_jsonl(RULE_REJECT_LOG, {"ra_id": ra_id, "rule_id": rule_id, "ts": _now(), "state": state,
                                          "role": role.strip(), "name": name.strip(), "note": note.strip()})


def reject_rule(ra_id: str, rule_id: str, role: str, name: str, reason: str) -> dict:
    """변경안 하나만 반려. 평가는 근로자 확인을 계속 기다리고, 확정할 때 이 변경안만 규칙셋에서 빠진다."""
    if not name.strip() or not reason.strip():
        raise ValueError("반려하려면 이름과 사유를 모두 적어야 합니다.")
    if rule_id in rejected_rules(ra_id):
        raise ValueError(f"{rule_id} 는 이미 반려돼 있습니다.")
    return _rule_change(ra_id, rule_id, "rejected", role or "관리자", name, reason)


def restore_rule(ra_id: str, rule_id: str, role: str, name: str, note: str = "") -> dict:
    """변경안 반려 취소 — 근로자 확인 전까지만."""
    if not name.strip():
        raise ValueError("처리자 이름을 적어야 합니다.")
    if rule_id not in rejected_rules(ra_id):
        raise ValueError(f"{rule_id} 는 반려돼 있지 않습니다.")
    return _rule_change(ra_id, rule_id, "restored", role or "관리자", name, note or "반려 취소")


def rule_rejection_log() -> list[dict]:
    return read_jsonl(RULE_REJECT_LOG)


def rejected_rules(ra_id: str, log: list[dict] | None = None) -> dict[str, dict]:
    """그 평가에서 지금 반려 상태인 변경안 — rule_id → 반려한 줄."""
    out: dict[str, dict] = {}
    for r in (log if log is not None else rule_rejection_log()):
        if r.get("ra_id") != ra_id:
            continue
        if r.get("state") == "rejected":
            out[r["rule_id"]] = r
        else:
            out.pop(r["rule_id"], None)
    return out


# ------------------------------------------------------------------ 읽기
STATE_LABEL = {"worker_pending": "근로자 확인 대기", "confirmed": "확정", "rejected": "반려"}


def _history() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in read_jsonl(REVISION_LOG):
        out.setdefault(row["ra_id"], []).append(row)
    return out


def get_assessment(ra_id: str, history: dict | None = None, rule_log: list[dict] | None = None) -> dict:
    ra = json.loads((RA_DIR / f"{ra_id}.json").read_text(encoding="utf-8"))
    hist = (history or _history()).get(ra_id, [])
    last = hist[-1] if hist else {}
    state = {"submitted": "worker_pending", "confirmed": "confirmed",
             "rejected": "rejected"}.get(last.get("state"), "confirmed")   # 기록이 없는 옛 파일은 확정본
    confirmed = next((h for h in reversed(hist) if h["state"] == "confirmed"), None)
    ra.setdefault("kind", "정기·수시")                                       # 두 단계 서명 이전 형식
    ra.setdefault("manager", (confirmed or {}).get("manager", ""))
    return {**ra, "state": state, "state_label": STATE_LABEL[state], "history": hist,
            "worker_rep": (confirmed or {}).get("worker_rep") or ra.get("worker_rep", ""),
            "confirmed_at": (confirmed or {}).get("ts") or ra.get("confirmed_at", ""),
            "reject_reason": last.get("note", "") if state == "rejected" else "",
            "rule_rejected": rejected_rules(ra_id, rule_log)}


def list_assessments() -> list[dict]:
    if not RA_DIR.exists():
        return []
    hist = _history()
    rlog = rule_rejection_log()
    return [get_assessment(p.stem, hist, rlog) for p in sorted(RA_DIR.glob("RA-*.json"), reverse=True)]


def ruleset_revisions() -> list[dict]:
    return read_jsonl(RULESET_LOG)


def current_ruleset_version(base: int = 1) -> int:
    revs = ruleset_revisions()
    return max([base] + [r["version"] for r in revs])
