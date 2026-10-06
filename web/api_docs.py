"""
문서 자동화 다섯 화면의 데이터 — 홈 · 의무 이행 관리 · 안전 문서(관제 인계 · 위험성평가 · 시정지시서 ·
작업허가서 점검 · 산업재해조사표) · 안전소통 · 기록.

계산 · 문장 생성 · 기록은 전부 docgen/safety_docs 에 있다. 여기는 그 함수를 불러 화면이 쓰는 JSON 으로 바꾼다.
원칙: 숫자는 코드, 문장은 AI 초안, 확정은 사람.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, Response

from safety_docs.accident import build_accident_facts, draft_accident_report, log_accident_report
from safety_docs.archive import document_rows, effect_rows, revision_rows, ruleset_rows
from safety_docs.assessment import (build_rows, confirm_revision, draft_assessment, get_assessment, list_assessments,
                                    reject_revision, submit_for_review)
from safety_docs.compliance import alert_summary, build_schedule, done_list, mark_done
from safety_docs.config import (OUTPUT_DIR, load_documents, load_events, load_legal, load_piping, load_profile,
                                load_rulesets, load_scales, parse_date)
from safety_docs.corrective import draft_corrective_order, list_correctives, log_corrective
from safety_docs.export import accident_to_docx, assessment_to_excel, corrective_to_docx, ptw_to_docx
from safety_docs.handoff import get_handoff, list_handoffs, make_correctives, receive_file, report_candidates
from safety_docs.home import home_summary
from safety_docs.llm import LLMClient
from safety_docs.ptw import check_ptw, draft_ptw_notes, list_ptws, load_isolation, log_ptw_check
from safety_docs.voice import list_reports, submit_report, update_report, voice_summary

router = APIRouter(prefix="/api")
MEASURE_RE = re.compile(r"^\[(공학적|관리적|보호구)(?:·(R\d+))?\]\s*(.+)$")
LEVEL_KIND = {"overdue": "crit", "urgent": "crit", "soon": "warn", "upcoming": "note", "ok": "mute"}
EMOJI = re.compile(r"^[🔴🟠🟡🟢⚪]\s*")


def _today():
    from control.common import demo_day
    return demo_day()


def _llm() -> LLMClient:
    from web.api_control import provider
    return LLMClient(provider())


def file_url(path) -> str | None:
    """만든 문서 파일 → 내려받기 주소. docgen/outputs 안의 파일만 내준다."""
    if not path:
        return None
    name = Path(str(path).replace("\\", "/")).name
    return f"/api/file?name={name}" if (OUTPUT_DIR / name).exists() else None


@router.get("/file")
def get_file(name: str):
    p = OUTPUT_DIR / Path(name).name
    if not p.exists():
        return Response(status_code=404)
    return FileResponse(p, filename=p.name)


_adhoc = {"key": None, "n": 0}


def adhoc_count() -> int:
    """수시 위험성평가 제안 건수 — 넘어온 기록 · 오탐 표시가 바뀔 때만 다시 센다."""
    from safety_docs.config import FP_MARKS, MONITOR_EVENTS
    key = tuple(p.stat().st_mtime if p.exists() else 0 for p in (MONITOR_EVENTS, FP_MARKS))
    if key != _adhoc["key"]:
        evs, as_of = load_events()
        _, ad = build_rows(evs, as_of, load_scales(), load_profile().get("accidents"))
        _adhoc.update(key=key, n=len(ad))
    return _adhoc["n"]


def _zn(z: str) -> str:
    from control.common import zone_name
    return zone_name(z)


# ====================================================================== 홈
@router.get("/home")
def home():
    from control.common import load_control_events
    evs, as_of = load_events()
    prof = load_profile()
    h = home_summary(evs, as_of, load_scales(), prof, _today())
    go = {"안전 문서": ("docs", "ra"), "의무 이행 관리": ("duty", None), "안전소통": ("voice", None)}
    cards = [{"title": c["title"], "num": c["num"], "lines": [EMOJI.sub("", x) for x in c["lines"]],
              "go": go.get(c["go"], ("home", None))[0], "tab": go.get(c["go"], ("home", None))[1]} for c in h["cards"]]
    since = as_of - timedelta(days=14)
    ctl = [e for e in load_control_events() if since < e["_ts"] <= as_of]
    ras = list_assessments()
    cos = list_correctives()
    ev = h["evidence"]
    hos = [x for x in list_handoffs(include_auto=False) if x["event_ids"] or x.get("duplicates")]
    return {"cards": cards,
            "zones": [{**z, "zname": _zn(z["zone"])} for z in h["zones"]],
            "evidence": {"events": ev["events"], "silent": ev["silent"], "alerts": ev["events"] - ev["silent"],
                         "days": ev["days"], "recorded": ev["recorded"], "gaps": ev["gaps"], "period": ev["period"],
                         "clips": sum(1 for e in ctl if e.get("clip_path")),
                         "gates": sum(1 for e in ctl if e.get("kind") == "gate"),
                         "confirmed": sum(1 for r in ras if r["state"] == "confirmed"), "correctives": len(cos)},
            "handoff": ({"id": hos[0]["handoff_id"], "source": hos[0]["source"], "n": len(hos),
                         "events": len(hos[0]["event_ids"]) + len(hos[0].get("duplicates", []))} if hos else None)}


# ====================================================================== 의무 이행 관리
def _profile(body: dict) -> dict:
    prof = load_profile()
    return {**prof, "industry": body.get("industry") or prof.get("industry"),
            "workers": int(body.get("workers") or prof.get("workers") or 0),
            "hazardous_agents": bool(body.get("hazardous", prof.get("hazardous_agents")))}


@router.post("/duty")
def duty(body: dict):
    evs, as_of = load_events()
    today = parse_date(body["today"]) if body.get("today") else _today()
    prof = _profile(body)
    _, adhoc = build_rows(evs, as_of, load_scales(), prof.get("accidents"))
    items, judged = build_schedule(prof, today, adhoc, as_of.date())
    cat = body.get("cat")
    if cat and cat != "전체":
        items = [it for it in items if it["category"] == cat]
    done = done_list(prof, [cat] if cat and cat != "전체" else None)
    return {"today": today.isoformat(), "summary": alert_summary(items),
            "items": [{"key": f"{it['ob_id']}||{it['ref']}", "status": EMOJI.sub("", it["status"]),
                       "kind": LEVEL_KIND.get(it["level"], "mute"), "level": it["level"], "name": it["name"],
                       "ref": it["ref"], "category": it["category"], "basis": it["basis"], "due": it["due"],
                       "retention": it["retention"].split(" — ")[0], "why": it["why"], "type": it["kind"]} for it in items],
            "judged": judged, "done": done}


@router.post("/duty/done")
def duty_done(body: dict):
    choice = body.get("key")
    if not choice:
        raise ValueError("이행 처리할 항목을 고른다")
    if not body.get("staff"):
        raise ValueError("담당자를 고른다")
    today = parse_date(body["today"]) if body.get("today") else _today()
    ob_id, ref = choice.split("||", 1)
    day = parse_date(body["day"], year=today.year) if str(body.get("day") or "").strip() else today
    row = mark_done(ob_id, day, body["staff"], ref, body.get("note") or "", today=today)
    return {"msg": f"이행 처리 — {row['done_date']} · {row['by']} ({row['by_dept']} · {row['by_position']})",
            "day": row["done_date"]}


@router.get("/norm-day")
def norm_day(value: str, today: str | None = None):
    t = parse_date(today) if today else _today()
    return {"day": parse_date(value, year=t.year).isoformat()}


# ====================================================================== 안전 문서 — 위험성평가
_ra = {"rows": [], "drafts": [], "file": None}


@router.get("/docs/ra")
def ra_calc():
    evs, as_of = load_events()
    rows, adhoc = build_rows(evs, as_of, load_scales(), load_profile().get("accidents"))
    _ra.update(rows=rows)
    return {"as_of": as_of.isoformat(timespec="minutes"),
            "rows": [{"i": i, "zone": r["zone"], "zname": _zn(r["zone"]), "mode": r["mode"], "type": r["violation_type"],
                      "count": r["count_used"], "base": r["base_count"], "recent": r["recent_count"], "adj": r["adj_count"],
                      "top": r["top_alert_count"], "likelihood": r["likelihood"], "l_label": r["likelihood_label"],
                      "severity": r["severity"], "score": r["score"], "grade": r["grade"], "adhoc": r["adhoc_reasons"]}
                     for i, r in enumerate(rows)],
            "adhoc": adhoc, "drafts": _drafts_json(), "file": file_url(_ra["file"]),
            "window": [rows[0]["window_from"], rows[0]["window_to"]] if rows else None}


def _measures_text(ms, rejected: dict | None = None) -> str:
    """감소대책 한 줄씩. rejected = 변경안 단위로 반려된 것(관제 › 피드백 · 조정 로그) — 그 줄 끝에 표시한다."""
    rej = rejected or {}

    def tail(m):
        r = rej.get(m.get("rule_id") or "")
        return f"  ← 규칙 변경 {m['rule_id']} 반려 ({r.get('name', '')} · {r.get('note', '')}) — 확정해도 규칙셋에 올리지 않는다" if r else ""
    return "\n".join(f"[{m['category']}{'·' + m['rule_id'] if m.get('rule_id') else ''}] {m['text']}{tail(m)}" for m in ms)


def _drafts_json() -> list[dict]:
    return [{"i": i, "zone": d["zone"], "zname": _zn(d["zone"]), "mode": d["mode"], "type": d["violation_type"],
             "likelihood": d["likelihood"], "severity": d["severity"], "score": d["score"], "grade": d["grade"],
             "event_ids": d.get("event_ids", []), "accident_ids": d.get("accident_ids", []),
             "unit_work": d.get("unit_work", ""), "hazard": d.get("hazard", ""), "cause": d.get("cause", ""),
             "current_measures": "\n".join(d.get("current_measures", [])), "measures": _measures_text(d.get("measures", [])),
             "legal_refs": "\n".join(d.get("legal_refs", [])),
             "check": "\n".join(filter(None, [d.get("check_needed", "")] + d.get("warnings", [])))}
            for i, d in enumerate(_ra["drafts"])]


@router.post("/docs/ra/draft")
def ra_draft(body: dict):
    if not _ra["rows"]:
        ra_calc()
    rows = _ra["rows"]
    pick = body.get("rows")                              # 고른 행만 (없으면 수시평가 제안 행, 그것도 없으면 전부)
    if pick:
        rows = [rows[i] for i in pick if 0 <= i < len(rows)]
    elif any(r["adhoc_reasons"] for r in rows):
        rows = [r for r in rows if r["adhoc_reasons"]]
    if not rows:
        raise ValueError("초안을 만들 행이 없다 — 관제 기록이 없다")
    rs = load_rulesets()
    drafts = draft_assessment(rows, rs, load_legal(), load_scales(), _llm())
    path = assessment_to_excel(drafts, OUTPUT_DIR / "위험성평가표_초안.xlsx", rulesets=rs, scales=load_scales())
    _ra.update(drafts=drafts, file=str(path))
    return {"drafts": _drafts_json(), "file": file_url(path)}


def _apply_edits(edits: list[dict]) -> list[dict]:
    """화면에서 고친 문장 칸을 초안에 되돌려 넣는다. 숫자 칸은 받지 않는다."""
    changes = load_rulesets().get("rule_changes", {})
    by_i = {int(x["i"]): x for x in edits or []}
    out = []
    for i, d in enumerate(_ra["drafts"]):
        x = by_i.get(i)
        if not x:
            out.append(d)
            continue
        measures = []
        for line in str(x.get("measures", "")).splitlines():
            line = line.strip()
            if not line:
                continue
            m = MEASURE_RE.match(line)
            rid = m.group(2) if m and m.group(2) in changes else ""
            measures.append({"category": m.group(1), "text": m.group(3), "rule_id": rid} if m
                            else {"category": "관리적", "text": line, "rule_id": ""})
        out.append({**d, "unit_work": str(x.get("unit_work", "")).strip(), "hazard": str(x.get("hazard", "")).strip(),
                    "cause": str(x.get("cause", "")).strip(),
                    "current_measures": [s for s in str(x.get("current_measures", "")).splitlines() if s.strip()],
                    "measures": measures, "legal_refs": [s for s in str(x.get("legal_refs", "")).splitlines() if s.strip()]})
    return out


@router.post("/docs/ra/sign")
def ra_sign(body: dict):
    if not _ra["drafts"]:
        raise ValueError("서명할 초안이 없다 — AI 초안 생성을 먼저 누른다")
    ra = submit_for_review(_apply_edits(body.get("edits")), body.get("manager") or "", body.get("kind") or "수시",
                           body.get("note") or "")
    rs = load_rulesets()
    path = assessment_to_excel(ra["rows"], OUTPUT_DIR / f"위험성평가표_{ra['ra_id']}.xlsx", rulesets=rs,
                               scales=load_scales(), record=ra)
    rules = sorted({m["rule_id"] for r in ra["rows"] for m in r["measures"] if m.get("rule_id")})
    _ra.update(drafts=[], file=None)
    return {"ra_id": ra["ra_id"], "file": file_url(path),
            "msg": f"관리자 서명 완료 — {ra['ra_id']} ({ra['kind']}) · 근로자 확인 대기. 근로자 대표가 안전소통 › 근로자 확인에서 "
                   f"확인하면 확정된다. 확정되면 규칙 변경 {', '.join(rules) or '없음'}이 규칙셋에 반영된다."}


# ====================================================================== 안전 문서 — 시정지시서
@router.get("/docs/co")
def co_events():
    evs, _ = load_events()
    issued = {c["event_id"]: c for c in list_correctives()}
    xs = [x for x in evs if x.get("alerted", True) and not x.get("false_positive") and x.get("level") in ("경보", "최고 경보")]
    xs.sort(key=lambda x: x["ts"], reverse=True)
    default = next((x["event_id"] for x in xs if x.get("level") == "최고 경보" and x.get("frame_path")),
                   xs[0]["event_id"] if xs else None)
    return {"events": [{"id": x["event_id"], "ts": x["ts"][5:16].replace("T", " "), "zone": x["zone"], "level": x.get("level"),
                        "type": x["violation_type"], "frame": bool(x.get("frame_path")), "handoff": x.get("handoff_id"),
                        "issued": (issued.get(x["event_id"]) or {}).get("doc_no")} for x in xs], "default": default}


def _docgen_event(eid: str) -> dict:
    evs, _ = load_events()
    ev = next((x for x in evs if x["event_id"] == eid), None)
    if not ev:
        raise KeyError(f"문서 자동화에 없는 이벤트: {eid} — 관제에서 넘겨야 보인다")
    return ev


def _frame_path(ev: dict) -> Path | None:
    from safety_docs.config import ROOT
    fp = ev.get("frame_path")
    if not fp:
        return None
    p = Path(fp)
    if not p.is_absolute():
        p = ROOT / p
    return p if p.exists() else None


@router.get("/docs/co/{eid}")
def co_event(eid: str):
    ev = _docgen_event(eid)
    issued = next((c for c in list_correctives() if c["event_id"] == eid), None)
    return {"id": eid, "ts": ev["ts"].replace("T", " "), "zone": ev["zone"], "zname": _zn(ev["zone"]), "mode": ev.get("mode"),
            "type": ev["violation_type"], "level": ev.get("level"), "row": ev.get("row"), "reason": ev.get("reason", ""),
            "adj": ev.get("adj_id"), "clip": ev.get("clip_path"), "handoff": ev.get("handoff_id"),
            "source": ev.get("source", ""), "frame": _frame_path(ev) is not None,
            "issued": {"doc_no": issued["doc_no"], "deadline": issued["deadline_date"], "file": file_url(issued.get("file"))} if issued else None}


@router.get("/docs/co/{eid}/frame")
def co_frame(eid: str):
    p = _frame_path(_docgen_event(eid))
    return FileResponse(p) if p else Response(status_code=404)


def _order_json(o: dict, path) -> dict:
    return {"doc_no": o["doc_no"], "issued": o["issued"], "zone": o["event"]["zone"], "zname": o["zone_name"],
            "event_id": o["event"]["event_id"], "level": o["event"].get("level"), "type": o["event"]["violation_type"],
            "mode": o["event"].get("mode"), "rule_state": o["rule_state"], "same_recent": o["same_recent"],
            "severity": o["severity"], "severity_label": o["severity_label"], "deadline": o["deadline"],
            "clip": o["event"].get("clip_path"), "scene": o["scene"], "hazards": o["hazards"], "violation": o["violation"],
            "actions": o["actions"], "legal_refs": o["legal_refs"], "uncertain": o["uncertain"], "warnings": o["warnings"],
            "file": file_url(path)}


@router.post("/docs/co")
def co_make(body: dict):
    evs, as_of = load_events()
    ev = next((x for x in evs if x["event_id"] == body.get("event_id")), None)
    if not ev:
        raise ValueError("이벤트를 고른다")
    order = draft_corrective_order(ev, evs, load_rulesets(), load_legal(), load_scales(), _llm(), issued=as_of)
    path = corrective_to_docx(order, OUTPUT_DIR / f"시정지시서_{ev['event_id']}.docx")
    log_corrective(order, str(path))
    return _order_json(order, path)


# ====================================================================== 안전 문서 — 작업허가서 점검
@router.get("/docs/ptw")
def ptw_list():
    return {"ptws": [{"id": p["ptw_id"], "type": p.get("type", ""), "zone": p["zone"], "work": p["work"]} for p in list_ptws()]}


@router.get("/docs/ptw/{pid}")
def ptw_show(pid: str):
    p = next((x for x in list_ptws() if x["ptw_id"] == pid), None)
    if not p:
        raise KeyError(f"없는 작업허가서: {pid}")
    try:
        iso = load_isolation(p)
    except (OSError, ValueError):
        iso = None
    return {"ptw": {k: p.get(k) for k in ("ptw_id", "type", "zone", "work", "start", "end", "supervisor", "workers",
                                          "registered_at", "source")},
            "zname": _zn(p["zone"]), "purge": (p.get("purge") or {}).get("minutes"), "iso": iso}


@router.post("/docs/ptw/{pid}")
def ptw_check(pid: str):
    ps = list_ptws()
    p = next((x for x in ps if x["ptw_id"] == pid), None)
    if not p:
        raise ValueError("작업허가서를 고른다")
    try:
        iso = load_isolation(p)
    except (OSError, ValueError):
        iso = None
    res = draft_ptw_notes(check_ptw(p, ps, load_piping(), load_rulesets(), iso), load_legal(), _llm())
    path = ptw_to_docx(res, OUTPUT_DIR / f"작업허가서점검_{pid}.docx")
    log_ptw_check(res, str(path))
    listed = {r.get("line_id"): r for r in res["iso_rows"]}
    return {"result": res["result"], "summary": res["summary"], "text_source": res["text_source"],
            "findings": [{"code": f["code"], "title": f["title"], "detail": f["detail"], "note": f["note"],
                          "legal_refs": f["legal_refs"]} for f in res["findings"]],
            "pid": [{"line_id": ln["line_id"], "name": ln["name"], "fluid": ln["fluid"], "listed": ln["line_id"] in listed,
                     "method": listed.get(ln["line_id"], {}).get("격리방법", "-"),
                     "blind": listed.get(ln["line_id"], {}).get("맹판설치", ""),
                     "gas": listed.get(ln["line_id"], {}).get("가스측정", "")} for ln in res["pid_lines"]],
            "file": file_url(path)}


# ====================================================================== 안전 문서 — 산업재해조사표
def _accs():
    return [a for a in load_profile().get("accidents", []) if a.get("fatal") or a.get("lost_days", 0) >= 3]


@router.get("/docs/acc")
def acc_list():
    accs = _accs()
    default = next((a["id"] for a in reversed(accs) if a.get("event_ids")), accs[-1]["id"] if accs else None)
    return {"accidents": [{"id": a["id"], "date": a["date"], "time": a.get("time", ""), "zone": a["zone"],
                           "summary": a["summary"], "lost_days": a.get("lost_days", 0)} for a in accs], "default": default}


def _timeline(facts) -> list[dict]:
    return [{"t": t["ts"].replace("T", " ")[5:16], "src": t["src"], "what": t["what"],
             "kind": "hit" if t["src"].startswith("ACC") else ("shadow" if "무음" in t["what"] else "")}
            for t in facts["timeline"]]


@router.get("/docs/acc/{aid}")
def acc_show(aid: str):
    acc = next((a for a in load_profile().get("accidents", []) if a["id"] == aid), None)
    if not acc:
        raise KeyError(f"없는 사고: {aid}")
    evs, _ = load_events()
    f = build_accident_facts(acc, evs, load_rulesets(), list_ptws())
    return {"acc": acc, "zname": _zn(acc["zone"]), "timeline": _timeline(f), "due": f["due"]}


@router.post("/docs/acc/{aid}")
def acc_make(aid: str):
    acc = next((a for a in load_profile().get("accidents", []) if a["id"] == aid), None)
    if not acc:
        raise ValueError("사고를 고른다")
    evs, _ = load_events()
    rep = draft_accident_report(build_accident_facts(acc, evs, load_rulesets(), list_ptws()), _llm())
    path = accident_to_docx(rep, OUTPUT_DIR / f"산업재해조사표_{aid}.docx", load_profile())
    log_accident_report(rep, str(path))
    return {"acc": acc, "zname": _zn(acc["zone"]), "due": rep["due"], "narrative": rep["narrative"],
            "prevention": rep["prevention"], "check": rep.get("check_needed", ""), "text_source": rep["text_source"],
            "timeline": _timeline(rep), "file": file_url(path)}


# ====================================================================== 안전 문서 — 관제 인계
@router.get("/docs/handoff")
def handoff_list():
    out = []
    for h in list_handoffs(include_auto=False):
        out.append({"id": h["handoff_id"], "source": h["source"], "ts": h["ts"].replace("T", " ")[:16],
                    "n": len(h["event_ids"]) + len(h.get("duplicates", [])),
                    "gates": sum(1 for o in h.get("others", []) if o["kind"] == "gate"),
                    "accidents": sum(1 for o in h.get("others", []) if o["kind"] == "accident")})
    return {"handoffs": out}


@router.get("/docs/handoff/{hid}")
def handoff_show(hid: str):
    if not get_handoff(hid):
        raise KeyError(f"없는 인계: {hid}")
    evs, as_of = load_events()
    c = report_candidates(hid, evs, as_of, load_scales(), load_profile().get("accidents"))
    h = c["handoff"]
    return {"id": hid, "source": h["source"], "ts": h["ts"].replace("T", " "), "by": h.get("by", ""), "note": h.get("note", ""),
            "received": len(h["event_ids"]), "duplicates": len(h.get("duplicates", [])), "warnings": h.get("warnings", []),
            "events": [{"id": x["event_id"], "t": x["ts"][5:16].replace("T", " "), "zone": x["zone"], "mode": x.get("mode") or "-",
                        "type": x["violation_type"], "level": x.get("level"), "alerted": x.get("alerted", True),
                        "why": (f"{x['row']}번 줄 · " if x.get("row") else "") + (x.get("reason") or ""),
                        "frame": bool(x.get("frame_path"))} for x in c["events"]],
            "corrective": [{"id": x["event_id"], "t": x["ts"][11:16], "zone": x["zone"], "type": x["violation_type"],
                            "level": x["level"], "frame": x["frame"], "issued": x["issued"]} for x in c["corrective"]],
            "adhoc": c["adhoc"],
            "gates": [{"t": g["ts"][11:16], "zone": g["zone"], "type": g.get("violation_type"), "reason": g.get("reason", "")}
                      for g in c["gates"]],
            "accidents": [{"t": a["ts"][11:16], "zone": a["zone"], "type": a.get("violation_type"), "reason": a.get("reason", "")}
                          for a in c["accidents"]]}


@router.post("/docs/handoff/{hid}/make")
def handoff_make(hid: str, body: dict):
    picked = body.get("event_ids") or []
    if not picked:
        raise ValueError("시정지시서를 만들 이벤트를 고른다")
    evs, as_of = load_events()
    made = make_correctives(list(picked), evs, load_rulesets(), load_legal(), load_scales(), _llm(), issued=as_of)
    return {"made": [{"doc_no": m["doc_no"], "event_id": m["event_id"], "severity": m["severity"], "deadline": m["deadline"],
                      "warnings": m["warnings"], "file": file_url(m["path"])} for m in made]}


@router.post("/docs/handoff/upload")
async def handoff_upload(file: UploadFile = File(...), base_dir: str = Form(""), source: str = Form("")):
    suffix = Path(file.filename or "events.jsonl").suffix or ".jsonl"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        path = tmp.name
    try:
        h = receive_file(path, source=source.strip() or f"엔진 결과 파일 · {file.filename}",
                         base_dir=base_dir.strip().strip('"') or None)
    finally:
        Path(path).unlink(missing_ok=True)
    return {"handoff_id": h["handoff_id"], "msg": f"{h['handoff_id']} — 감지 {len(h['event_ids'])}건 받음"
            + (f" · 이미 받은 {len(h['duplicates'])}건 건너뜀" if h["duplicates"] else "")}


# ====================================================================== 안전소통
@router.get("/voice")
def voice():
    reps = list_reports()
    s = voice_summary(reps)
    since = f"{_today() - timedelta(days=30)}"
    pend = [ra for ra in list_assessments() if ra["state"] == "worker_pending"]
    return {"summary": {"total": s["total"], "open": s["open"], "doing": sum(1 for r in reps if r["state"] == "조치 중"),
                        "done": s["done"], "rate": round(s["rate"]), "recent": sum(1 for r in reps if r["ts"][:10] >= since)},
            "reports": [{"id": r["report_id"], "ts": r["ts"].replace("T", " "), "kind": r["kind"], "zone": r["zone"],
                         "text": r["text"], "reporter": r.get("reporter") or "익명", "state": r["state"],
                         "action": r.get("action", ""), "by": r.get("by", "")} for r in reps],
            "pending": [{"id": ra["ra_id"], "kind": ra["kind"], "manager": ra["manager"], "n": len(ra["rows"])} for ra in pend]}


@router.get("/voice/ra/{ra_id}")
def voice_ra(ra_id: str):
    ra = get_assessment(ra_id)
    return {"id": ra_id, "kind": ra["kind"], "manager": ra["manager"],
            "rule_rejected": sorted(ra.get("rule_rejected", {})),
            "rows": [{"zone": r["zone"], "mode": r["mode"], "score": r["score"], "grade": r["grade"],
                      "hazard": r.get("hazard", ""), "measures": _measures_text(r.get("measures", []), ra.get("rule_rejected"))}
                     for r in ra["rows"]]}


@router.post("/voice/report")
def voice_submit(body: dict):
    r = submit_report(body.get("kind"), body.get("zone"), body.get("text") or "", body.get("reporter") or "")
    return {"msg": f"{r['report_id']} 접수 — {r['kind']} · {r['zone']}"}


@router.post("/voice/update")
def voice_update(body: dict):
    if not body.get("id"):
        raise ValueError("제보를 고른다")
    update_report(body["id"], body.get("state"), body.get("action") or "", body.get("by") or "")
    return {"msg": f"{body['id']} → {body.get('state')}"}


@router.post("/voice/confirm")
def voice_confirm(body: dict):
    ra_id = body.get("ra_id")
    if not ra_id:
        raise ValueError("확인할 평가를 고른다")
    ra = confirm_revision(ra_id, body.get("name") or "", body.get("note") or "")
    assessment_to_excel(ra["rows"], OUTPUT_DIR / f"위험성평가표_{ra_id}.xlsx", rulesets=load_rulesets(),
                        scales=load_scales(), record=ra)
    excluded = sorted(ra.get("rule_rejected", {}))
    rules = [i for i in sorted({m["rule_id"] for r in ra["rows"] for m in r["measures"] if m.get("rule_id")}) if i not in excluded]
    return {"msg": f"확정 — {ra_id} · 관리자 {ra['manager']} · 근로자 대표 {ra['worker_rep']}. "
                   + (f"규칙셋에 {', '.join(rules)} 반영 → 기록의 규칙셋 개정 이력" if rules else "규칙 변경 없음")
                   + (f" · 반려된 변경안 {', '.join(excluded)} 은 올리지 않았다" if excluded else "")}


@router.post("/voice/reject")
def voice_reject(body: dict):
    ra_id = body.get("ra_id")
    if not ra_id:
        raise ValueError("반려할 평가를 고른다")
    reject_revision(ra_id, "근로자 대표", body.get("name") or "", body.get("reason") or "")
    return {"msg": f"반려 — {ra_id} · 사유: {body.get('reason')}"}


# ====================================================================== 기록
@router.get("/archive")
def archive():
    evs, as_of = load_events()
    docs = load_documents()
    return {"docs": [{**d, "url": file_url(d.get("파일"))} for d in document_rows(docs)],
            "revisions": revision_rows(), "rulesets": ruleset_rows(load_rulesets()),
            "effects": effect_rows(evs, as_of, load_scales()),
            "retention": [{"name": d["name"], "years": d["retention_years"], "basis": d["retention_basis"],
                           "from": d["retention_from"], "statutory": d["statutory"]} for d in docs.values()]}


@router.post("/docs/upload-csv")
async def read_csv_upload(file: UploadFile = File(...)):
    """격리 목록 CSV 파일 → 글자 (UTF-8 · CP949)."""
    raw = await file.read()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return {"text": raw.decode(enc)}
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV 글자를 읽지 못했다 (UTF-8 또는 CP949)")

