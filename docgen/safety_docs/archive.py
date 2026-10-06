"""
기록 — 모든 문서와 개정 이력을 한곳에, 문서별 보존 기한까지 (LLM 없음)

보존 기간과 근거는 config/documents.json 에서 읽는다.
  - 위험성평가표 3년 (산업안전보건법 시행규칙 제37조제2항)
  - 산업재해조사표 3년 (산업안전보건법 제164조제1항제4호)
  - 시정지시서 · 안전소통 · 의무 이행 기록 5년 (중대재해처벌법 시행령 제13조)
  - 작업허가서 점검 5년 (법정 기간 없음 — 중처법 이행 증빙으로 둠)
기한은 '보존 시작일(기산일) + 보존 기간'이다. 기산일이 아직 없으면(조치 전 등) 그렇게 표시한다.
이 시스템은 기록을 지우지 않는다(추가 전용). 보존 기한은 '그 전에 지우면 안 되는 날'이다.
"""
from __future__ import annotations

from datetime import date, datetime

from .accident import list_accident_reports
from .assessment import list_assessments, rule_rejection_log, ruleset_revisions
from .compliance import DONE_LOG, _ob_index, done_records
from .config import read_jsonl, to_date
from .corrective import list_correctives
from .ptw import list_ptw_checks
from .risk import measure_effect
from .voice import list_reports


def _plus_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:                      # 2월 29일
        return d.replace(year=d.year + years, day=28)


def _keep(doc_cfg: dict, start) -> str:
    y = doc_cfg["retention_years"]
    if not start:
        return f"{y}년 — 기산일 전"
    return f"{_plus_years(to_date(start), y)}까지 ({y}년)"


def document_rows(docs_cfg: dict) -> list[dict]:
    out = []
    done = done_records()

    for ra in list_assessments():
        cfg = docs_cfg["risk_assessment"]
        start = ra["confirmed_at"] if ra["state"] == "confirmed" else None
        who = " · ".join(filter(None, [f"관리자 {ra.get('manager')}" if ra.get("manager") else "",
                                       f"근로자 대표 {ra.get('worker_rep')}" if ra.get("worker_rep") else ""]))
        n_ev = sum(len(r.get("event_ids", [])) for r in ra.get("rows", []))
        out.append({"종류": cfg["name"], "번호": ra["ra_id"], "상태": ra["state_label"] +
                    (f" — {ra['reject_reason']}" if ra.get("reject_reason") else ""),
                    "날짜": (start or ra.get("created_at", ""))[:16].replace("T", " "), "서명·처리": who,
                    "근거 기록": f"{len(ra.get('rows', []))}행 · 이벤트 {n_ev}건", "보존 기한": _keep(cfg, start),
                    "보존 근거": cfg["retention_basis"], "파일": ""})

    for co in list_correctives():
        cfg = docs_cfg["corrective_order"]
        fin = [d for d in done if d["ob_id"] == "corrective" and d.get("ref") == co["doc_no"]]
        start = max((d["done_date"] for d in fin), default=None)
        out.append({"종류": cfg["name"], "번호": co["doc_no"],
                    "상태": f"조치 완료 {start}" if start else f"조치 대기 (기한 {co['deadline_date']})",
                    "날짜": co["issued"], "서명·처리": fin[-1]["by"] if fin else "",
                    "근거 기록": f"{co['event_id']} · {co['zone']} {co['violation_type']}",
                    "보존 기한": _keep(cfg, start), "보존 근거": cfg["retention_basis"], "파일": co.get("file") or ""})

    for pc in list_ptw_checks():
        cfg = docs_cfg["ptw_check"]
        out.append({"종류": cfg["name"], "번호": pc["check_id"], "상태": pc["result"],
                    "날짜": pc["ts"][:16].replace("T", " "), "서명·처리": "",
                    "근거 기록": f"{pc['ptw_id']} · 지적 {', '.join(pc['codes']) or '없음'}",
                    "보존 기한": _keep(cfg, pc["ts"]), "보존 근거": cfg["retention_basis"], "파일": pc.get("file") or ""})

    for ar in list_accident_reports():
        cfg = docs_cfg["accident_report"]
        out.append({"종류": cfg["name"], "번호": ar["report_id"], "상태": f"초안 — 제출 기한 {ar['due']}",
                    "날짜": ar["ts"][:16].replace("T", " "), "서명·처리": "",
                    "근거 기록": f"{ar['acc_id']} · {ar['summary']}",
                    "보존 기한": _keep(cfg, ar["ts"]), "보존 근거": cfg["retention_basis"], "파일": ar.get("file") or ""})

    for r in list_reports():
        cfg = docs_cfg["voice_report"]
        start = (r.get("updated") or r["ts"]) if r["state"] == "완료" else None
        out.append({"종류": cfg["name"], "번호": r["report_id"], "상태": r["state"] + (" (샘플)" if r.get("sample") else ""),
                    "날짜": r["ts"].replace("T", " "), "서명·처리": r.get("by", ""),
                    "근거 기록": f"{r['kind']} · {r['zone']}",
                    "보존 기한": _keep(cfg, start),
                    "보존 근거": cfg["retention_basis"], "파일": ""})

    cfg = docs_cfg["obligation_record"]
    names = {k: v["name"] for k, v in _ob_index().items()}
    for d in read_jsonl(DONE_LOG):
        out.append({"종류": cfg["name"],
                    "번호": names.get(d["ob_id"], d["ob_id"]) + (f" · {d['ref']}" if d.get("ref") else ""),
                    "상태": "이행", "날짜": d["done_date"],
                    "서명·처리": " · ".join(filter(None, [d.get("by"), d.get("by_dept"), d.get("by_position")])),
                    "근거 기록": d.get("note", ""), "보존 기한": _keep(cfg, d["done_date"]),
                    "보존 근거": cfg["retention_basis"], "파일": ""})
    out.sort(key=lambda x: x["날짜"], reverse=True)
    return out


def revision_rows() -> list[dict]:
    out = []
    for ra in list_assessments():
        for h in ra["history"]:
            out.append({"시각": h["ts"].replace("T", " "), "평가 번호": ra["ra_id"], "구분": ra.get("kind", ""),
                        "상태": {"submitted": "관리자 서명", "confirmed": "확정", "rejected": "반려"}.get(h["state"], h["state"]),
                        "서명·처리": f"{h.get('role', '')} {h.get('name') or h.get('manager', '')}".strip(),
                        "비고": h.get("note", "")})
    kinds = {ra["ra_id"]: ra.get("kind", "") for ra in list_assessments()}
    for r in rule_rejection_log():                      # 변경안 단위 반려 · 반려 취소 (관제 › 피드백 · 조정 로그)
        out.append({"시각": r["ts"].replace("T", " "), "평가 번호": r["ra_id"], "구분": kinds.get(r["ra_id"], ""),
                    "상태": f"변경안 {r['rule_id']} " + ("반려" if r["state"] == "rejected" else "반려 취소"),
                    "서명·처리": f"{r.get('role', '')} {r.get('name', '')}".strip(), "비고": r.get("note", "")})
    out.sort(key=lambda x: x["시각"], reverse=True)
    return out


def ruleset_rows(rulesets: dict) -> list[dict]:
    changes = rulesets.get("rule_changes", {})
    base = rulesets.get("version", 1)
    out = [{"버전": base, "시각": "-", "근거 평가": "-", "반영한 변경": "기준 규칙셋", "확정자": "-"}]
    for r in ruleset_revisions():
        out.append({"버전": r["version"], "시각": r["ts"].replace("T", " "), "근거 평가": r["ra_id"],
                    "반영한 변경": "\n".join(f"{i} {changes.get(i, '')}" for i in r["rule_ids"]),
                    "확정자": r.get("by", "")})
    return out


def effect_rows(events, as_of, scales) -> list[dict]:
    """확정된 평가의 개선 후 위험도 — 적용일 전후 위반 건수로 실측."""
    out = []
    for ra in list_assessments():
        if ra["state"] != "confirmed" or not ra.get("confirmed_at"):
            continue
        applied = datetime.fromisoformat(ra["confirmed_at"])
        for r in ra.get("rows", []):
            if "severity" not in r:
                continue
            m = measure_effect(r, applied, events, as_of, scales)
            out.append({"평가 번호": ra["ra_id"], "구역": r["zone"], "작업 모드": r["mode"],
                        "위반 유형": r["violation_type"], "개선 전 위험도": f"{r['score']} {r.get('grade', '')}",
                        "개선 후 (실측)": m["text"]})
    return out
