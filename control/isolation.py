"""
격리 목록 대조 — 관제의 입력 창구 (작업허가서 · 격리 목록 · 작업계획서는 여기서만 받는다)

  register()    작업허가서 등록 — 격리 목록 CSV 를 배관 계통도와 대조하고,
                ① 문서 자동화에 점검 대상으로 저장(docgen handoff.register_ptw)
                ② 실시간 세션이 돌고 있으면 엔진에 신호로 넣는다(작업 종류 → 모드 신호, 격리 목록 → 작업 전 게이트)
  step()        배관마다 단계 입력 — 맹판 설치 완료(R2) · 가스 측정(R4) · 퍼지 시간(R4)
                control/records/isolation_steps.jsonl 에 추가만 하고, 세션이 돌면 엔진에도 넣는다
  view()        허가서 하나의 대조 결과 — 계통도 ↔ 목록 · 맹판 · 측정 · 퍼지 · 발생 축 해제 인정 여부

배관 계통도는 사업장 패키지 site.json 의 references.piping 이 원본이다(문서 자동화도 같은 것을 읽는다).
기준값(퍼지 최소 시간 · LEL 기준)은 문서 자동화 config/rulesets.json 의 isolation 블록.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta

from .common import RECORD_DIR, append_jsonl, load_config, read_jsonl

STEP_LOG = RECORD_DIR / "isolation_steps.jsonl"
YES = {"O", "○", "Y", "YES", "예", "완료", "TRUE", "1"}
COLS = ["line_id", "배관", "격리방법", "맹판설치", "벤트", "가스측정"]


def piping() -> dict:
    from safety_docs.config import load_piping
    return load_piping()


def iso_cfg() -> dict:
    from safety_docs.config import load_rulesets
    return load_rulesets().get("isolation", {})


def ptws() -> list[dict]:
    from safety_docs.ptw import list_ptws
    return list_ptws()


def steps(ptw_id: str | None = None) -> list[dict]:
    return [r for r in read_jsonl(STEP_LOG) if ptw_id is None or r.get("ptw_id") == ptw_id]


def parse_csv(text: str) -> list[dict]:
    text = (text or "").lstrip("﻿").strip()
    if not text:
        return []
    rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(io.StringIO(text))]
    if rows and "line_id" not in rows[0]:
        raise ValueError("첫 줄에 line_id 열이 없다 — 열: " + ", ".join(COLS))
    rows = [r for r in rows if r.get("line_id")]
    if not rows:
        raise ValueError("배관 줄이 하나도 없다")
    return rows


def sample_csv(zone: str) -> str:
    """예시 채우기 — 계통도의 마지막 줄을 일부러 뺀 목록 (누락이 어떻게 잡히는지 보이려고)."""
    lines = piping().get(zone, {}).get("lines", [])
    if not lines:
        return ""
    keep = lines[:-1] if len(lines) > 1 else lines
    out = [",".join(COLS)]
    for i, ln in enumerate(keep):              # 첫 줄만 맹판 설치 완료 — 나머지는 단계 입력으로 받는 모습을 보이려고
        out.append(f"{ln['line_id']},{ln['name']},맹판,{'O' if i == 0 else ''},O,{'O' if ln.get('hazard_source') else 'X'}")
    return "\n".join(out)


def cross_check(zone: str, rows: list[dict] | None) -> dict:
    """계통도 ↔ 목록. 계통도에만 있으면 누락(R1 게이트), 목록에만 있으면 계통도 확인 필요."""
    p = piping().get(zone, {})
    ref = p.get("lines", [])
    listed = {r.get("line_id"): r for r in (rows or [])}
    lines = []
    for ln in ref:
        r = listed.get(ln["line_id"])
        if rows is None:
            lines.append({**ln, "in_list": False, "blind": "none", "row": None})
        elif r is None:
            lines.append({**ln, "in_list": False, "blind": "valve", "row": None})
        else:
            done = r.get("격리방법", "맹판") == "맹판" and r.get("맹판설치", "").strip().upper() in YES
            method_valve = r.get("격리방법") and r.get("격리방법") != "맹판"
            lines.append({**ln, "in_list": True, "blind": "done" if done else ("valve" if method_valve else "pending"), "row": r})
    extra = [f"{r['line_id']} {r.get('배관', '')}".strip() for r in (rows or []) if r.get("line_id") not in {x["line_id"] for x in ref}]
    return {"equipment": p.get("equipment", zone), "lines": lines, "extra": extra, "has_pid": bool(ref)}


def next_ptw_id(day: str) -> str:
    d = day.replace("-", "")[:8]
    n = [int(p["ptw_id"].rsplit("-", 1)[1]) for p in ptws() if p["ptw_id"].startswith(f"PTW-{d}-")]
    return f"PTW-{d}-{max(n, default=0) + 1:02d}"


def register(zone: str, work_type: str, start: str, end: str, work: str, supervisor: str, workers: int | None,
             csv_text: str | None, no_list: bool) -> dict:
    """작업허가서 등록 — 입력 창구 한 곳. 등록 결과와 엔진이 남긴 메모를 돌려준다."""
    from safety_docs.handoff import register_ptw
    from .session import SESSION
    wt = load_config()["work_types"].get(work_type)
    if not wt:
        raise ValueError(f"작업 종류를 고른다 ({', '.join(k for k in load_config()['work_types'] if not k.startswith('_'))})")
    if not work.strip():
        raise ValueError("작업 내용을 적는다")
    try:
        t0, t1 = datetime.fromisoformat(start), datetime.fromisoformat(end)
    except ValueError:
        raise ValueError("시작 · 종료는 2026-10-12T13:00 모양으로") from None
    if t1 <= t0:
        raise ValueError("종료가 시작보다 늦어야 한다")
    rows = None if no_list else parse_csv(csv_text or "")
    if not no_list and not rows:
        raise ValueError("격리 목록 CSV 를 올리거나 붙여넣는다. 목록이 없으면 '목록 없이 등록'을 켠다")
    chk = cross_check(zone, rows)
    ptw = {"ptw_id": next_ptw_id(start[:10]), "type": wt["ptw_type"], "zone": zone, "work": work.strip(),
           "work_type": work_type, "start": t0.isoformat(timespec="minutes"), "end": t1.isoformat(timespec="minutes"),
           "supervisor": supervisor.strip(), "workers": int(workers) if workers else None,
           "purge": None, "gas_tests": [], "fire_watch": None, "source": "관제 입력창"}
    rec = register_ptw(ptw, rows if rows is not None else None)
    notes = []
    if SESSION.sid:
        notes += SESSION.apply_signal(wt["signal"], zone, value=work_type, source="입력창", note=f"{rec['ptw_id']} {work}")
        if rows is not None:
            from safety_docs.config import ROOT as DOCGEN_ROOT
            path = DOCGEN_ROOT / rec["isolation_list_file"]
            notes += SESSION.apply_signal("isolation_list", zone, value=str(path), source="입력창",
                                          note=f"{rec['ptw_id']} 격리 목록")
    return {"ptw": rec, "check": chk, "engine_notes": notes}


def step(ptw: dict, kind: str, line_id: str | None, value: str | None, by: str) -> list[str]:
    """
    단계 입력 하나.  blind = 맹판 설치 완료 · gas = 가스 측정(LEL %) · purge = 퍼지 완료(분)
    기록은 추가만 한다. 실시간 세션이 돌면 같은 것을 엔진 신호로 넣는다 (blind_installed · gas_test · purge_start/end).
    """
    from .session import SESSION
    if kind not in ("blind", "gas", "purge"):
        raise ValueError(kind)
    if kind in ("blind", "gas") and not line_id:
        raise ValueError("배관을 고른다")
    if kind in ("gas", "purge"):
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise ValueError("숫자를 적는다 (가스 측정은 LEL %, 퍼지는 분)") from None
        if v < 0:
            raise ValueError("0 이상")
    from .common import system_now
    now = system_now()
    append_jsonl(STEP_LOG, {"ts": now.isoformat(timespec="seconds"), "ptw_id": ptw["ptw_id"], "zone": ptw["zone"],
                            "kind": kind, "line_id": line_id, "value": value, "by": by.strip()})
    notes = []
    if SESSION.sid:
        z = ptw["zone"]
        if kind == "blind":
            notes += SESSION.apply_signal("blind_installed", z, line_id, source="입력창", note=f"{ptw['ptw_id']} 맹판 설치 완료")
        elif kind == "gas":
            notes += SESSION.apply_signal("gas_test", z, line_id, str(value), source="입력창", note=f"{ptw['ptw_id']} 가스 측정")
        else:
            t = SESSION.clock()
            notes += SESSION.apply_signal("purge_start", z, source="입력창", ts=t - timedelta(minutes=float(value)),
                                          note=f"{ptw['ptw_id']} 퍼지 {value}분")
            notes += SESSION.apply_signal("purge_end", z, source="입력창", note=f"{ptw['ptw_id']} 퍼지 종료")
    return notes


def view(ptw: dict) -> dict:
    """허가서 하나의 대조 결과 — 화면(계통도 · 목록 · 단계 입력 · 해제 판정)이 그대로 쓴다."""
    from safety_docs.ptw import load_isolation
    try:
        rows = load_isolation(ptw)
    except (OSError, ValueError):
        rows = None
    chk = cross_check(ptw["zone"], rows)
    st = steps(ptw["ptw_id"])
    blinds = {s["line_id"] for s in st if s["kind"] == "blind"}
    for ln in chk["lines"]:
        if ln["line_id"] in blinds and ln["blind"] != "done":
            ln["blind"] = "done"
            ln["blind_by_step"] = True
    cfg = iso_cfg()
    purge_cfg = cfg.get("purge", {})
    lel_max = purge_cfg.get("lel_max", 5)
    # 측정 지점 — 가연물 배관이 있으면 그것, 없으면 목록의 배관
    haz = [ln for ln in chk["lines"] if ln.get("hazard_source")]
    points = haz or [ln for ln in chk["lines"] if ln["in_list"]]
    meas = {}
    for g in ptw.get("gas_tests") or []:
        if g.get("line_id"):
            meas[g["line_id"]] = {"time": g.get("time", ""), "value": g.get("lel_pct"), "src": "허가서"}
    for s in st:
        if s["kind"] == "gas":
            meas[s["line_id"]] = {"time": s["ts"][11:16], "value": float(s["value"]), "src": "단계 입력"}
    mrows = []
    for ln in points:
        m = meas.get(ln["line_id"])
        ok = m is not None and m["value"] is not None and float(m["value"]) <= lel_max
        mrows.append({"point": f"{ln['line_id']} {'벤트' if ln['in_list'] else '하류'}", "line_id": ln["line_id"],
                      "time": m["time"] if m else "—", "value": f"LEL {m['value']}%" if m else "—", "ok": ok,
                      "measured": m is not None})
    purge_min = (ptw.get("purge") or {}).get("minutes")
    for s in st:
        if s["kind"] == "purge":
            purge_min = float(s["value"])
    need = purge_cfg.get("min_minutes", 30)
    no_list = rows is None
    miss = [ln for ln in chk["lines"] if not ln["in_list"]] if not no_list else []
    pend = [ln for ln in chk["lines"] if ln["in_list"] and ln["blind"] != "done"]
    meas_bad = [m for m in mrows if not m["ok"]]
    purge_ok = purge_min is not None and purge_min >= need
    if not chk["has_pid"]:
        st_ = ("mute", "계통도 없음", f"{ptw['zone']} 에는 배관 계통도가 없어 대조할 수 없다 — 사업장 패키지 site.json 의 piping 에 넣는다", "판단 불가")
    elif no_list:
        st_ = ("warn", "목록 미첨부", "격리 목록이 첨부되지 않았다 — 작업 전에 첨부해야 한다 (LIST)", "판단 불가")
    elif miss:
        st_ = ("crit", f"누락 {len(miss)}건",
               f"계통도 {len(chk['lines'])}건 · 목록 {len(chk['lines']) - len(miss)}건 → 목록에 없는 연결 {len(miss)}건 · 작업 전 차단 (R1)", "불인정")
    elif chk["extra"]:
        st_ = ("warn", f"계통도 확인 {len(chk['extra'])}건",
               f"목록에만 있는 배관 {len(chk['extra'])}건 — 계통도가 낡았거나 목록이 틀렸다. 확인 전까지 해제하지 않는다", "불인정")
    elif pend or meas_bad or not purge_ok:
        bits = ["대조는 일치"] + ([f"맹판 설치 대기 {len(pend)}건 (R2)"] if pend else []) + \
               [f"측정 {len(mrows) - len(meas_bad)}/{len(mrows)}지점 (R4)"] + \
               ([f"퍼지 {purge_min if purge_min is not None else '-'}분 < {need}분 (R4)"] if not purge_ok else [])
        st_ = ("note", f"맹판 대기 {len(pend)}" if pend else ("측정 대기" if meas_bad else "퍼지 미달"), " · ".join(bits), "불인정 (가능 유지)")
    else:
        st_ = ("ok", "대조 일치", "계통도와 목록 일치 · 맹판 전부 설치 · 전 지점 측정 기준 이하 · 퍼지 기준 충족", "인정")
    return {"ptw": ptw, "check": chk, "rows": rows, "no_list": no_list, "miss": miss, "pend": pend,
            "meas": mrows, "purge_min": purge_min, "purge_need": need, "lel_max": lel_max, "steps": st,
            "kind": st_[0], "tag": st_[1], "bar": st_[2], "clear": st_[3],
            "open": _is_open(ptw)}


def _is_open(ptw: dict) -> bool:
    from .common import system_now
    try:
        return datetime.fromisoformat(ptw["start"]) <= system_now() <= datetime.fromisoformat(ptw["end"])
    except (KeyError, ValueError):
        return False
