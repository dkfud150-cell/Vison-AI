"""
작업허가서(PTW) 점검 — 허가 발급 시점(08:00~08:05)에 계획서의 빈칸을 찾는다.

판정은 전부 코드가 한다. LLM은 찾은 항목을 사람이 읽을 지적 문장으로 옮기기만 한다.

  check_ptw()        최소 필드 · 격리 목록 첨부 · 계통도 대조(R1) · 밸브 단독 격리(R2)
                     · 퍼지·측정 기준(R4) · 동시작업 간섭
  draft_ptw_notes()  찾은 항목마다 지적 문안 (LLM, 실패하면 템플릿 문장)
  log_ptw_check()    점검 기록 (추가 전용)

격리 기준값은 config/rulesets.json 의 isolation 블록, 계통도는 config/piping.json 에서 읽는다.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .config import (RECORD_DIR, ROOT, SAMPLE_DIR, append_jsonl, latest_by, legal_ref, now,
                     read_csv, read_jsonl, sample_file, use_sample_data)
from .llm import LLMClient

PTW_DIR = SAMPLE_DIR / "ptw"          # 예시 허가서 (예시데이터_삭제가능/문서자동화/ptw — 지우면 없어진다)
PTW_INBOX = RECORD_DIR / "ptw"        # 관제 입력창에서 등록한 허가서 — handoff.register_ptw() 가 쓴다
PTW_LOG = RECORD_DIR / "ptw_checks.jsonl"

# 허가서 유형별 최소 필드 — KOSHA GUIDE P-94-2021 안전작업허가지침의 항목을 줄인 것
REQUIRED = {
    "정비": [("work", "작업 내용"), ("zone", "작업 구역"), ("start", "작업 기간"),
             ("supervisor", "작업책임자"), ("workers", "작업 인원"),
             ("isolation_list_file", "격리 목록"), ("purge", "퍼지 기록"), ("gas_tests", "가스 측정")],
    "화기": [("work", "작업 내용"), ("zone", "작업 구역"), ("start", "작업 기간"),
             ("supervisor", "작업책임자"), ("workers", "작업 인원"),
             ("gas_tests", "가스 측정"), ("fire_watch", "화재감시자")],
}

# 항목 코드 → (제목, 근거 조문 id)
FINDING_INFO = {
    "FIELD":  ("최소 필드 누락", ["R-278"]),
    "LIST":   ("격리 목록 미첨부", ["R-278", "R-240"]),
    "R1":     ("계통도에 있는데 격리 목록에 없는 배관", ["R-278", "R-240"]),
    "R2":     ("맹판 없이 밸브만으로 격리된 배관", ["R-240"]),
    "R4":     ("퍼지·가스 측정이 완료 기준에 못 미침", ["R-278", "R-241"]),
    "SIMOPS": ("정비 중 같은 구역·인접 구역 화기 작업", ["R-241", "R-241-2"]),
}

NOTES_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "점검 결과 한두 문장 요약"},
        "notes": {"type": "array",
                  "items": {"type": "object",
                            "properties": {"code": {"type": "string"}, "text": {"type": "string"}},
                            "required": ["code", "text"]},
                  "description": "찾은 항목 코드마다 작업책임자에게 보낼 지적 문장 1~2문장"},
    },
    "required": ["summary", "notes"],
}

SYSTEM = """당신은 철강 산세 공장의 안전관리자입니다. 작업허가서 점검에서 시스템이 찾은 항목을
작업책임자가 바로 조치할 수 있는 지적 문장으로 옮깁니다.
규칙:
- 제공된 항목 코드마다 한 개씩만 쓰세요. 새 항목을 만들지 마세요.
- 숫자(시간, 지점 수, 기준값)는 제공된 값만 쓰세요.
- 특정 개인을 지목하지 마세요."""


def list_ptws() -> list[dict]:
    """
    점검 대상 허가서 = 예시(예시데이터_삭제가능/문서자동화/ptw) + 관제 입력창에서 등록한 것(records/ptw).
    입력 창구는 관제 화면 한 곳이다 — 문서 자동화는 등록된 허가서를 읽기만 한다.
    """
    dirs = ([PTW_DIR] if use_sample_data() else []) + [PTW_INBOX]
    found: dict[str, dict] = {}
    for d in dirs:
        for p in sorted(d.glob("PTW-*.json")) if d.exists() else []:
            x = json.loads(p.read_text(encoding="utf-8"))
            if d == PTW_DIR and x.get("isolation_list_file"):     # 예시 허가서의 첨부는 예시 폴더 기준
                x["isolation_list_file"] = sample_file(x["isolation_list_file"])
            found.setdefault(x["ptw_id"], x)       # 같은 번호는 먼저 있던 것 (등록은 새 번호만 받는다)
    return [found[k] for k in sorted(found)]


def load_isolation(ptw: dict, uploaded: str | Path | None = None) -> list[dict] | None:
    """업로드한 CSV가 있으면 그것을, 없으면 허가서에 첨부된 파일을 읽는다."""
    src = uploaded or (ROOT / ptw["isolation_list_file"] if ptw.get("isolation_list_file") else None)
    return read_csv(src) if src else None


def _t(ptw, key):
    return datetime.fromisoformat(ptw[key])


def check_ptw(ptw: dict, all_ptws: list[dict], piping: dict, rulesets: dict,
              isolation: list[dict] | None) -> dict:
    iso_cfg = rulesets.get("isolation", {})
    findings = []

    # ① 최소 필드
    missing = [label for key, label in REQUIRED.get(ptw["type"], []) if not ptw.get(key)]
    if missing:
        findings.append({"code": "FIELD", "detail": ", ".join(missing), "values": {"missing": missing}})

    lines = piping.get(ptw["zone"], {}).get("lines", [])
    iso_rows = isolation or []
    if ptw["type"] == "정비" and lines:
        # ② 격리 목록 첨부
        if iso_cfg.get("require_list") and not iso_rows:
            findings.append({"code": "LIST", "detail": "허가서에 격리 목록이 없다", "values": {}})
        listed = {r.get("line_id") for r in iso_rows}
        # ③ R1 — 계통도 대조
        if iso_cfg.get("cross_check_pid") and iso_rows:
            miss = [ln for ln in lines if ln["line_id"] not in listed]
            if miss:
                findings.append({"code": "R1",
                                 "detail": ", ".join(f"{m['line_id']} {m['name']}" for m in miss),
                                 "values": {"pid_count": len(lines), "list_count": len(iso_rows),
                                            "missing": [m["line_id"] for m in miss]}})
        # ④ R2 — 밸브 단독 격리 (목록에서 방법이 밸브이거나, 목록에 없는 가연물 배관)
        if iso_cfg.get("valve_only_is_not_cleared"):
            yes = {"O", "○", "Y", "YES", "예", "완료"}
            valve_only = [r.get("line_id") for r in iso_rows
                          if r.get("격리방법") != "맹판" or r.get("맹판설치", "").strip().upper() not in yes]
            valve_only += [ln["line_id"] for ln in lines
                           if ln["line_id"] not in listed and ln.get("hazard_source")]
            if valve_only:
                findings.append({"code": "R2", "detail": ", ".join(valve_only),
                                 "values": {"lines": valve_only}})
        # ⑤ R4 — 퍼지 시간 · 측정 지점
        purge = iso_cfg.get("purge", {})
        minutes = (ptw.get("purge") or {}).get("minutes", 0)
        measured = {g.get("line_id") for g in ptw.get("gas_tests", []) if g.get("line_id")}
        need_points = [ln["line_id"] for ln in lines if ln.get("hazard_source")]
        short = []
        if minutes < purge.get("min_minutes", 0):
            short.append(f"퍼지 {minutes}분 < 기준 {purge['min_minutes']}분")
        if purge.get("all_points_required"):
            unmeasured = [p for p in need_points if p not in measured]
            if unmeasured:
                short.append(f"측정 {len(measured)}지점 / 가연물 배관 {len(need_points)}지점 (미측정 {', '.join(unmeasured)})")
        if short:
            findings.append({"code": "R4", "detail": " · ".join(short),
                             "values": {"purge_minutes": minutes, "min_minutes": purge.get("min_minutes"),
                                        "measured": sorted(measured), "need": need_points}})

    # ⑥ 동시작업 — 정비 허가와 시간이 겹치는 같은/인접 구역 화기 허가
    adj = piping.get("adjacent_zones", {}).get(ptw["zone"], [ptw["zone"]])
    others = []
    for o in all_ptws:
        if o["ptw_id"] == ptw["ptw_id"] or o["zone"] not in adj:
            continue
        overlap = _t(o, "start") < _t(ptw, "end") and _t(ptw, "start") < _t(o, "end")
        pair = {ptw["type"], o["type"]}
        if overlap and pair == {"정비", "화기"}:
            others.append(f"{o['ptw_id']} {o['work']} ({o['start'][11:]}~{o['end'][11:]})")
    if others:
        findings.append({"code": "SIMOPS", "detail": "; ".join(others), "values": {"permits": others}})

    for f in findings:
        f["title"], f["legal_ids"] = FINDING_INFO[f["code"]]
    return {"ptw": ptw, "findings": findings, "iso_rows": iso_rows, "pid_lines": lines,
            "result": "보완 필요 — 작업 시작 전 조치" if findings else "적합"}


def _template(check: dict) -> dict:
    notes = [{"code": f["code"], "text": f"{f['title']}: {f['detail']}. 작업 시작 전에 보완하십시오."}
             for f in check["findings"]]
    return {"summary": f"{check['ptw']['ptw_id']} 점검 결과 {len(notes)}건 보완 필요." if notes
            else f"{check['ptw']['ptw_id']} 점검 결과 적합.", "notes": notes}


def draft_ptw_notes(check: dict, legal: dict, llm: LLMClient | None = None) -> dict:
    """찾은 항목을 지적 문장으로. LLM이 실패하거나 코드에 없는 항목을 쓰면 템플릿으로 채운다."""
    llm = llm or LLMClient()
    ptw = check["ptw"]
    items = "\n".join(f"- {f['code']} {f['title']}: {f['detail']}" for f in check["findings"]) or "- 없음"
    user = f"""[작업허가서] {ptw['ptw_id']} · {ptw['type']} · {ptw['zone']} · {ptw['work']}
기간 {ptw['start']} ~ {ptw['end']}

[시스템이 찾은 항목]
{items}

항목마다 지적 문장을 쓰세요."""
    source = "LLM"
    try:
        raw = llm.generate_json("ptw", SYSTEM, user, NOTES_SCHEMA, mock_key=ptw["ptw_id"])
    except Exception as ex:                 # 시연 중 API 장애 — 문서는 반드시 나와야 한다
        raw, source = _template(check), f"템플릿 (LLM 실패: {str(ex)[:80]})"
    codes = {f["code"] for f in check["findings"]}
    notes = {n["code"]: n["text"].strip() for n in raw.get("notes", []) if n.get("code") in codes}
    tmpl = {n["code"]: n["text"] for n in _template(check)["notes"]}
    for c in codes - notes.keys():           # LLM이 빠뜨린 항목은 템플릿 문장으로
        notes[c] = tmpl[c]
    for f in check["findings"]:
        f["note"] = notes[f["code"]]
        f["legal_refs"] = [legal_ref(legal[i]) for i in f["legal_ids"] if i in legal]
    return {**check, "summary": raw.get("summary", "").strip() or _template(check)["summary"],
            "text_source": source, "checked_at": now().isoformat(timespec="seconds")}


def log_ptw_check(result: dict, docx_path: str | None = None) -> dict:
    ptw = result["ptw"]
    return append_jsonl(PTW_LOG, {
        "check_id": f"PC-{ptw['ptw_id']}", "ptw_id": ptw["ptw_id"], "ts": result["checked_at"],
        "zone": ptw["zone"], "type": ptw["type"], "result": result["result"],
        "codes": [f["code"] for f in result["findings"]], "file": docx_path})


def list_ptw_checks() -> list[dict]:
    return list(latest_by(read_jsonl(PTW_LOG), "check_id").values())
