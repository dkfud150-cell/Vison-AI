"""
작업 전 게이트 — 문서가 들어올 때 한 번 대조해서, 맞지 않으면 작업을 시작시키지 않는다.
판정표(8줄 등)를 타지 않는다.

게이트 종류 (규칙의 gates[].type):
  missing_in_document : 참조 목록(site.json)에 있는데 문서에 없는 항목이 있나   — 격리 목록 ↔ 배관 계통도
  required_fields     : 문서의 필수 칸이 비었나, 시각 칸이 어떤 사건보다 앞서나 — 긴급 작업허가서 최소 필드
새 종류가 필요하면 아래 GATE_TYPES 에 함수 하나를 더한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .conditions import Ctx
from .signals import parse_clock


@dataclass
class GateResult:
    gate_id: str
    label: str
    zone: str
    enabled: bool
    blocked: bool = False
    problems: list[str] = field(default_factory=list)
    message: str = ""
    ts: datetime | None = None


def _missing_in_document(g: dict, doc: dict, zone: str, eng) -> list[str]:
    col = g.get("document_field", "id")
    have = {str(r.get(col, "")).strip() for r in doc["rows"]}
    items = [i for i in eng.site.get("references", {}).get(g["ref"], {}).get(zone, []) or []]
    miss = [i for i in items if str(i.get(g.get("ref_field", "id"))) not in have]
    out = [f"{i.get(g.get('ref_field', 'id'))} {i.get(g.get('ref_label', 'name'), '')}".strip() for i in miss]
    if out:
        return [f"참조 {len(items)}건 ↔ 문서 {len(have)}건 · 문서에 없는 항목 {len(out)}건 ({', '.join(out)})"]
    return []


def _required_fields(g: dict, doc: dict, zone: str, eng) -> list[str]:
    data = doc.get("data") or {}
    probs = [f"'{f}' 칸이 비었다" for f in g.get("fields", []) if not str(data.get(f, "") or "").strip()]
    ta = g.get("time_after_event")
    if ta and str(data.get(ta["field"], "")).strip():
        t = parse_clock(str(data[ta["field"]]), doc["ts"].date())
        evs = [e for e in eng.store.events if e.fact == ta["event"] and e.zone == zone and e.ts <= doc["ts"]]
        if evs:
            e = max(evs, key=lambda x: x.ts)
            if t < e.ts:
                probs.append(f"'{ta['field']}' {t:%H:%M} 이 {e.label}({e.ts:%H:%M}) 이전")
    return probs


GATE_TYPES = {"missing_in_document": _missing_in_document, "required_fields": _required_fields}


def run_gates(doc_fact: str, zone: str, eng, now: datetime) -> list[GateResult]:
    out = []
    doc = eng.store.documents.get((doc_fact, zone))
    for g in eng.rules.get("gates", []):
        if g.get("on_document") != doc_fact or doc is None:
            continue
        enabled = bool(Ctx(eng, zone, now).val(g.get("enabled", True)))
        res = GateResult(g["id"], g.get("label", g["id"]), zone, enabled, ts=now)
        if not enabled:
            res.message = f"{res.label} — 대조하지 않음 (게이트 꺼짐)"
        else:
            res.problems = GATE_TYPES[g["type"]](g, doc, zone, eng)
            res.blocked = bool(res.problems)
            res.message = f"{res.label}: " + ("; ".join(res.problems) + " — 작업 시작 차단" if res.blocked else "이상 없음")
        out.append(res)
    return out
