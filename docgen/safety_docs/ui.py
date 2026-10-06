"""
문서 자동화 화면 — 한 프로그램의 사이드바 메뉴 묶음 '문서 자동화'

  홈 · 의무 이행 관리 · 안전 문서(관제 인계 · 위험성평가 · 시정지시서 · 작업허가서 점검 · 산업재해조사표)
  · 안전소통 · 기록

docgen_section() 이 틀(shell.py)에 넣을 묶음을 돌려준다. 관제 화면과 같은 틀에 나란히 들어간다.
관제에서 넘어온 감지 내역은 안전 문서 › 관제 인계에서 보고, 거기서 보고서를 만든다 (handoff.py).

원칙: 숫자는 코드가 계산하고, 문장만 AI가 쓰고, 확정은 사람이 한다.
"""
from __future__ import annotations

import html
import re
from datetime import date

import gradio as gr
import pandas as pd

from .accident import build_accident_facts, draft_accident_report, log_accident_report
from .archive import document_rows, effect_rows, revision_rows, ruleset_rows
from .assessment import (build_rows, confirm_revision, draft_assessment, get_assessment, list_assessments,
                         reject_revision, submit_for_review)
from .compliance import alert_summary, build_schedule, done_list, load_obligations, mark_done
from .config import (OUTPUT_DIR, ROOT, load_documents, load_events, load_legal, load_piping, load_profile,
                     load_rulesets, load_scales, load_staff, parse_date, read_csv, staff_label, use_sample_data,
                     zone_name)
from .corrective import draft_corrective_order, log_corrective
from .export import accident_to_docx, assessment_to_excel, corrective_to_docx, ptw_to_docx
from .handoff import (get_handoff, list_handoffs, make_correctives, receive_file,
                      report_candidates)
from .home import home_summary
from .llm import LLMClient, LLMError
from .ptw import check_ptw, draft_ptw_notes, list_ptws, load_isolation, log_ptw_check
from .shell import Section
from .voice import KINDS, STATES, list_reports, submit_report, update_report, voice_summary

SCALES, RULESETS, LEGAL, PIPING = load_scales(), load_rulesets(), load_legal(), load_piping()
DOCS, PROFILE = load_documents(), load_profile()
TODAY = date.fromisoformat(PROFILE["demo_today"]) if PROFILE.get("demo_today") else date.today()
ZONES = list(RULESETS["zones"].keys())
INDUSTRIES = ["1차 금속 제조업", "기타 제조업"]
CATS = load_obligations()["categories"]
MEASURE_RE = re.compile(r"^\[(공학적|관리적|보호구)(?:·(R\d+))?\]\s*(.+)$")
GRADE_CHIP = {"낮음": "ok", "보통": "note", "높음": "warn", "매우 높음": "crit"}
PAGES = [("home", "홈"), ("duty", "의무 이행 관리"), ("docs", "안전 문서"), ("voice", "안전소통"), ("archive", "기록")]
e = html.escape


class _Data:
    """
    이벤트 · 허가서는 화면을 열 때마다 다시 읽는다.
    관제가 감지 내역을 넘기거나 입력창에서 허가서를 등록하면 프로그램을 다시 켜지 않아도 바로 보인다.
    """
    def __init__(self):
        self.refresh()

    def refresh(self):
        self.events, self.as_of = load_events()
        self.ptws = list_ptws()
        return self


D = _Data()


def chip(text, kind="mute"):
    return f"<span class='chip {kind}'>{e(str(text))}</span>"


def llm(provider):
    try:
        return LLMClient(provider)
    except LLMError as ex:
        raise gr.Error(str(ex))


def subtitle() -> str:
    D.refresh()
    n_recv = sum(1 for x in D.events if x.get("handoff_id"))
    src = (f"샘플 {len(D.events) - n_recv} + 관제 인계 {n_recv}" if use_sample_data() else f"관제 인계 {n_recv}")
    return (f"{e(PROFILE['site_name'])} · 기준일 {TODAY} · 관제 기록 {D.as_of:%Y-%m-%d %H:%M}까지 {len(D.events)}건 "
            f"({src}) · 숫자는 코드, 문장은 AI 초안, 확정은 사람")


# ================================================================ 홈
def home_view():
    D.refresh()
    h = home_summary(D.events, D.as_of, SCALES, PROFILE, TODAY)
    cards = "".join(
        f"<div class='card'><div class='t'>{e(c['title'])}</div><div class='n'>{c['num']}</div>"
        f"<ul>{''.join(f'<li>{e(x)}</li>' for x in c['lines'])}</ul></div>" for c in h["cards"])
    ra_kind = {"확정": "ok", "서명 대기": "note", "수시평가 필요": "crit", "정기평가 반영 대기": "mute"}
    board = "".join(
        f"<tr><td><b>{e(z['zone'])}</b> {e(zone_name(RULESETS, z['zone']))}</td><td>{e(z['mode'])}</td>"
        f"<td>{chip(str(z['score']) + ' ' + z['grade'], GRADE_CHIP.get(z['grade'], 'mute'))}</td>"
        f"<td>{chip(z['ra'], ra_kind.get(z['ra'], 'mute'))}</td>"
        f"<td>{z['co'] or '-'}</td><td>{z['voice'] or '-'}</td><td>{e(z['ptw'])}</td></tr>" for z in h["zones"])
    ev = h["evidence"]
    strip = "".join(f"<i class='{'gap' if d in ev['gaps'] else ''}'></i>" for d in
                    [str(pd.Timestamp(ev['period'][:10]) + pd.Timedelta(days=i))[:10] for i in range(ev["days"])])
    checklist = "".join(
        f"<tr><td>{e(it['status'])}</td><td>{e(it['name'])}</td><td class='muted'>{e(it['basis'])}</td></tr>"
        for it in h["checklist"])
    hos = [x for x in list_handoffs(include_auto=False) if x["event_ids"] or x.get("duplicates")]
    handoff_line = (f"<p class='muted'>관제 인계 {len(hos)}회 · 마지막 {e(hos[0]['handoff_id'])} "
                    f"({e(hos[0]['source'])}, 감지 {len(hos[0]['event_ids']) + len(hos[0].get('duplicates', []))}건) — 안전 문서 › 관제 인계</p>" if hos else "")
    return f"""
<div class='cards'>{cards}</div>
<div class='sec'>구역 · 작업 모드별 문서 상태</div>
<table class='tbl'><thead><tr><th>구역</th><th>작업 모드</th><th>최고 위험도</th><th>위험성평가</th>
<th>시정지시 미조치</th><th>제보 미조치</th><th>작업허가서 점검</th></tr></thead><tbody>{board}</tbody></table>
<div class='two'>
 <div><div class='sec'>증빙 누적 — 관제 기록</div>
  <div class='strip'>{strip}</div>
  <p>{ev['period']} · 기록된 날 <b>{ev['recorded']}/{ev['days']}</b> · 이벤트 {ev['events']}건 (무음 기록 {ev['silent']}건) · 확정 평가 {ev['docs']}건</p>
  <p class='muted'>{'끊긴 날: ' + ', '.join(ev['gaps']) + ' — 카메라·시스템 점검 대상' if ev['gaps'] else '끊긴 날 없음. 관제 기록은 사람이 쓰지 않아도 매일 쌓인다.'}</p>
  {handoff_line}</div>
 <div><div class='sec'>정기 의무</div><table class='tbl'><tbody>{checklist}</tbody></table></div>
</div>"""


# ================================================================ 의무 이행 관리
def _profile(industry, workers, hazardous):
    return {**PROFILE, "industry": industry, "workers": int(workers or 0), "hazardous_agents": bool(hazardous)}


def _day(value, what="기준일"):
    try:
        return parse_date(value)
    except ValueError as ex:
        raise gr.Error(f"{what}: {ex}")


def schedule_view(industry, workers, hazardous, today_value, cats):
    today = _day(today_value)
    profile = _profile(industry, workers, hazardous)
    _, adhoc = build_rows(D.events, D.as_of, SCALES, PROFILE.get("accidents"))
    items, judged = build_schedule(profile, today, adhoc, D.as_of.date())
    if cats:
        items = [it for it in items if it["category"] in cats]
    s = alert_summary(items)
    banner = (f"### 기준일 {today}\n🔴 기한 경과 **{s['overdue']}** · 🔴 1일 이내 **{s['urgent']}** · "
              f"🟠 7일 이내 **{s['soon']}** · 🟡 30일 이내 **{s['upcoming']}** · 🟢 여유 {s['ok']}")
    sched = pd.DataFrame([{"상태": it["status"], "기한": it["due"], "의무": it["name"], "구분": it["category"],
                           "근거 조문": it["basis"], "서류 보존": it["retention"], "산정 근거": it["why"],
                           "서류": it["doc"], "유형": it["kind"]} for it in items])
    choices = [(f"{it['name']} {('· ' + it['ref']) if it['ref'] else ''} (기한 {it['due']})",
                f"{it['ob_id']}||{it['ref']}") for it in items]
    return (banner, sched, pd.DataFrame(judged), gr.update(choices=choices, value=None),
            *done_view(industry, workers, hazardous, cats))


def done_view(industry, workers, hazardous, cats):
    """이행 완료 기록 — 직접 처리 · 위험성평가 확정 자동 인정 · 도입 전 실시일."""
    rows = done_list(_profile(industry, workers, hazardous), cats or None)
    n_direct = sum(1 for r in rows if r["출처"] == "직접 처리")
    n_auto = sum(1 for r in rows if r["출처"].startswith("자동"))
    msg = (f"이행 기록 **{len(rows)}건** — 직접 처리 {n_direct} · 위험성평가 확정 자동 인정 {n_auto} · "
           f"도입 전 기록 {len(rows) - n_direct - n_auto}" + (f" · 구분 {', '.join(cats)}" if cats else ""))
    cols = ["이행일", "의무", "구분", "대상", "담당자", "부서", "직책", "비고", "출처", "기록 시각", "서류 보존"]
    return msg, pd.DataFrame(rows, columns=cols)


def staff_choices():
    """담당자 목록은 화면을 열 때마다 config/staff.json 에서 다시 읽는다."""
    return gr.update(choices=[(staff_label(p), p["id"]) for p in load_staff()])


def norm_day(value, today_value):
    """이행일 칸을 벗어나거나 Enter 를 치면 YYYY-MM-DD 로 바꿔 보여 준다 (2026.10.10 · 10/10 → 2026-10-10)."""
    if not str(value or "").strip():
        return gr.update()
    try:
        return parse_date(value, year=_day(today_value).year).isoformat()
    except ValueError as ex:
        gr.Warning(f"이행일: {ex}")
        return gr.update()


def do_mark(choice, done_date, staff_id, note, *sched_inputs):
    if not choice:
        raise gr.Error("이행 처리할 항목을 고르세요.")
    if not staff_id:
        raise gr.Error("담당자를 고르세요.")
    today = _day(sched_inputs[3])
    ob_id, ref = choice.split("||", 1)
    try:
        day = parse_date(done_date, year=today.year) if str(done_date or "").strip() else today
    except ValueError as ex:
        raise gr.Error(f"이행일: {ex}")
    try:
        row = mark_done(ob_id, day, staff_id, ref, note, today=today)
    except ValueError as ex:
        raise gr.Error(str(ex))
    gr.Info(f"이행 처리 — {row['done_date']} · {row['by']} ({row['by_dept']} · {row['by_position']})")
    return (*schedule_view(*sched_inputs), row["done_date"], "")


# ================================================================ 안전 문서 — 위험성평가
def calc_table():
    D.refresh()
    rows, adhoc = build_rows(D.events, D.as_of, SCALES, PROFILE.get("accidents"))
    df = pd.DataFrame([{
        "No": i, "구역": f"{r['zone']} {zone_name(RULESETS, r['zone'])}", "작업 모드": r["mode"],
        "위반 유형": r["violation_type"],
        "근거 (기본 / 최근14일 / 강화 / 최고경보)": f"{r['base_count']} / {r['recent_count']} / {r['adj_count']} / {r['top_alert_count']}",
        "가능성": r["likelihood"], "중대성": r["severity"], "위험도": r["score"], "등급": r["grade"],
        "가능성 설명": r["likelihood_label"], "수시평가": ", ".join(r["adhoc_reasons"]),
    } for i, r in enumerate(rows, 1)])
    msg = ("**수시평가 제안** (위험성평가 지침 제15조제2항)\n" + "\n".join(
        f"- {a['zone']} · {a['mode']} · {a['violation_type']} — {', '.join(a['reasons'])}" for a in adhoc)
           if adhoc else "수시평가 제안 없음")
    kind = "수시" if adhoc else "정기"
    return df, msg, rows, gr.update(value=kind)


def _measures_cell(ms):
    return "\n".join(f"[{m['category']}{'·' + m['rule_id'] if m.get('rule_id') else ''}] {m['text']}" for m in ms)


def drafts_to_df(drafts):
    return pd.DataFrame([{
        "No": i, "구역": d["zone"], "작업 모드": d["mode"], "위험도": f"{d['score']} {d['grade']}",
        "단위작업": d.get("unit_work", ""), "유해·위험요인": d.get("hazard", ""), "발생 원인": d.get("cause", ""),
        "현재 안전조치": "\n".join(d.get("current_measures", [])), "감소대책": _measures_cell(d.get("measures", [])),
        "법적 근거": "\n".join(d.get("legal_refs", [])),
        "확인 필요": "\n".join(filter(None, [d.get("check_needed", "")] + d.get("warnings", []))),
    } for i, d in enumerate(drafts, 1)])


def make_drafts(provider, rows, progress=gr.Progress()):
    if not rows:
        raise gr.Error("먼저 ① 위험도 계산을 누르세요.")
    try:
        drafts = draft_assessment(rows, RULESETS, LEGAL, SCALES, llm(provider),
                                  progress=lambda n, t, k: progress(n / t, desc=f"초안 {n}/{t}"))
    except LLMError as ex:
        raise gr.Error(str(ex))
    path = assessment_to_excel(drafts, OUTPUT_DIR / "위험성평가표_초안.xlsx", rulesets=RULESETS, scales=SCALES)
    return drafts_to_df(drafts), drafts, str(path)


def apply_edits(df: pd.DataFrame, drafts: list[dict]) -> list[dict]:
    """표에서 사람이 고친 문장을 초안에 되돌려 넣는다. 숫자 칸은 표에서 고쳐도 반영하지 않는다."""
    changes = RULESETS.get("rule_changes", {})
    out = []
    for (_, row), d in zip(df.iterrows(), drafts):
        measures = []
        for line in str(row["감소대책"]).splitlines():
            line = line.strip()
            if not line:
                continue
            m = MEASURE_RE.match(line)
            rid = m.group(2) if m and m.group(2) in changes else ""
            measures.append({"category": m.group(1), "text": m.group(3), "rule_id": rid} if m
                            else {"category": "관리적", "text": line, "rule_id": ""})
        out.append({**d, "unit_work": str(row["단위작업"]).strip(), "hazard": str(row["유해·위험요인"]).strip(),
                    "cause": str(row["발생 원인"]).strip(),
                    "current_measures": [s for s in str(row["현재 안전조치"]).splitlines() if s.strip()],
                    "measures": measures,
                    "legal_refs": [s for s in str(row["법적 근거"]).splitlines() if s.strip()]})
    return out


def sign_manager(df, drafts, kind, manager, note):
    if not drafts:
        raise gr.Error("서명할 초안이 없습니다. ② AI 초안 생성을 먼저 누르세요.")
    try:
        ra = submit_for_review(apply_edits(df, drafts), manager, kind, note)
    except ValueError as ex:
        raise gr.Error(str(ex))
    path = assessment_to_excel(ra["rows"], OUTPUT_DIR / f"위험성평가표_{ra['ra_id']}.xlsx",
                               rulesets=RULESETS, scales=SCALES, record=ra)
    rules = sorted({m["rule_id"] for r in ra["rows"] for m in r["measures"] if m.get("rule_id")})
    return (f"**관리자 서명 완료 — {ra['ra_id']}** ({ra['kind']}) · 근로자 확인 대기\n\n"
            f"근로자 대표가 **안전소통 → 근로자 확인**에서 확인하면 확정됩니다. "
            f"확정되면 규칙 변경 {', '.join(rules) or '없음'}이 규칙셋에 반영됩니다."), str(path)


# ================================================================ 안전 문서 — 시정지시서
def event_choices():
    evs = [x for x in D.events if x.get("alerted", True) and not x.get("false_positive")]
    evs.sort(key=lambda x: (x.get("frame_path") is None, x["ts"]))
    return [(f"{x['event_id']} | {x['ts'][5:16].replace('T', ' ')} | {x['zone']} | {x['violation_type']} | "
             f"{x.get('level') or ''}{'  📷' if x.get('frame_path') else ''}{'  ⇠관제' if x.get('handoff_id') else ''}",
             x["event_id"]) for x in evs]


def default_event():
    """처음에는 시연 시나리오의 09:15 최고 경보(프레임 있는 것)를 띄운다."""
    return next((x["event_id"] for x in D.events if x.get("level") == "최고 경보" and x.get("frame_path")), None)


def show_event(event_id):
    ev = next((x for x in D.events if x["event_id"] == event_id), None)
    if not ev:
        return None, ""
    img = str(ROOT / ev["frame_path"]) if ev.get("frame_path") else None
    src = f"  \n관제 인계 {ev['handoff_id']} · {ev.get('source', '')}" if ev.get("handoff_id") else ""
    why = f"  \n판정 근거 {ev['row']}번 줄 — {ev.get('reason', '')}" if ev.get("row") else ""
    return img, (f"**{ev['event_id']}** · {ev['ts'].replace('T', ' ')} · 판정 **{ev.get('level') or '-'}**  \n"
                 f"구역 {ev['zone']} {zone_name(RULESETS, ev['zone'])} · 모드 {ev['mode']}  \n"
                 f"위반 {ev['violation_type']} · 규칙 {'강화 중 ' + ev['adj_id'] if ev.get('adj_id') else '기본'}  \n"
                 f"클립 {ev.get('clip_path')}{why}{src}")


def make_order(provider, event_id):
    D.refresh()
    ev = next((x for x in D.events if x["event_id"] == event_id), None)
    if not ev:
        raise gr.Error("이벤트를 고르세요.")
    try:
        order = draft_corrective_order(ev, D.events, RULESETS, LEGAL, SCALES, llm(provider), issued=D.as_of)
    except LLMError as ex:
        raise gr.Error(str(ex))
    path = corrective_to_docx(order, OUTPUT_DIR / f"시정지시서_{event_id}.docx")
    log_corrective(order, str(path))
    md = [f"### 시정지시서 {order['doc_no']}",
          f"중대성 {order['severity']}등급 · 조치 기한 **{order['deadline']}** · 같은 위반 최근 14일 {order['same_recent']}건",
          f"\n**현장 상황**  \n{order['scene']}", "\n**위험 기인물·요인**"]
    md += [f"{h['rank']}. {h['hazard']} — {h['reason']}" for h in order["hazards"]]
    md += [f"\n**위반 사항**  \n{order['violation']}", "\n**시정 요구 사항**"]
    md += [f"- [{a['category']}] {a['text']}" for a in order["actions"]]
    md += ["\n**법적 근거**"] + [f"- {r}" for r in order["legal_refs"]]
    if order["uncertain"] or order["warnings"]:
        md += ["\n**확인 필요**"] + [f"- {x}" for x in [order["uncertain"], *order["warnings"]] if x]
    md += ["\n<small>보존: 조치 이행일부터 5년 (중대재해처벌법 시행령 제13조)</small>"]
    return "\n".join(md), str(path)


# ================================================================ 안전 문서 — 작업허가서 점검
def ptw_choices():
    return [(f"{p['ptw_id']} · {p['type']} · {p['zone']} · {p['work']}", p["ptw_id"]) for p in D.ptws]


def show_ptw(ptw_id):
    p = next((x for x in D.ptws if x["ptw_id"] == ptw_id), None)
    if not p:
        return "", None
    info = (f"**{p['ptw_id']}** · {p['type']} · {p['zone']} {zone_name(RULESETS, p['zone'])}  \n"
            f"{p['work']}  \n{p['start'].replace('T', ' ')} ~ {p['end'][11:]} · 인원 {p.get('workers', '-')} · "
            f"작업책임자 {p.get('supervisor') or '(비어 있음)'} · 퍼지 {(p.get('purge') or {}).get('minutes', '-')}분"
            + (f"  \n관제 입력창에서 등록 · {p['registered_at'].replace('T', ' ')}" if p.get("registered_at") else ""))
    iso = load_isolation(p)
    return info, pd.DataFrame(iso) if iso else pd.DataFrame([{"격리 목록": "첨부 없음"}])


def run_ptw(provider, ptw_id, upload):
    p = next((x for x in D.ptws if x["ptw_id"] == ptw_id), None)
    if not p:
        raise gr.Error("작업허가서를 고르세요.")
    try:
        iso = read_csv(upload) if upload else load_isolation(p)
    except ValueError as ex:
        raise gr.Error(str(ex))
    res = draft_ptw_notes(check_ptw(p, D.ptws, PIPING, RULESETS, iso), LEGAL, llm(provider))
    path = ptw_to_docx(res, OUTPUT_DIR / f"작업허가서점검_{ptw_id}.docx")
    log_ptw_check(res, str(path))
    listed = {r.get("line_id"): r for r in res["iso_rows"]}
    yn = lambda v: {"O": "예", "X": "아니오"}.get(str(v).strip().upper(), v or "-")  # noqa: E731
    pid = pd.DataFrame([{"배관": ln["line_id"], "이름": ln["name"], "유체": ln["fluid"],
                         "격리 목록": "있음" if ln["line_id"] in listed else "없음 ◀",
                         "격리 방법": listed.get(ln["line_id"], {}).get("격리방법", "-"),
                         "맹판": yn(listed.get(ln["line_id"], {}).get("맹판설치")),
                         "측정": yn(listed.get(ln["line_id"], {}).get("가스측정"))} for ln in res["pid_lines"]])
    fnd = pd.DataFrame([{"항목": f"{f['code']} {f['title']}", "찾은 내용": f["detail"], "지적 사항": f["note"],
                         "근거 조문": "\n".join(f["legal_refs"])} for f in res["findings"]])
    md = f"### {res['result']}\n{res['summary']}\n\n<small>판정은 코드 · 문장은 {res['text_source']}</small>"
    return md, pid, fnd, str(path)


# ================================================================ 안전 문서 — 산업재해조사표
def acc_choices():
    return [(f"{a['id']} · {a['date']} · {a['zone']} · {a['summary']} (휴업 {a.get('lost_days', 0)}일)", a["id"])
            for a in PROFILE.get("accidents", []) if a.get("fatal") or a.get("lost_days", 0) >= 3]


DEFAULT_ACC = next((a["id"] for a in reversed(PROFILE.get("accidents", [])) if a.get("event_ids")), None)


def _timeline_df(facts):
    return pd.DataFrame([{"시각": t["ts"].replace("T", " ")[5:16], "기록": t["src"], "내용": t["what"]}
                         for t in facts["timeline"]])


def show_acc(acc_id):
    acc = next((a for a in PROFILE.get("accidents", []) if a["id"] == acc_id), None)
    if not acc:
        return None
    return _timeline_df(build_accident_facts(acc, D.events, RULESETS, D.ptws))


def make_acc(provider, acc_id):
    D.refresh()
    acc = next((a for a in PROFILE.get("accidents", []) if a["id"] == acc_id), None)
    if not acc:
        raise gr.Error("사고를 고르세요.")
    rep = draft_accident_report(build_accident_facts(acc, D.events, RULESETS, D.ptws), llm(provider))
    path = accident_to_docx(rep, OUTPUT_DIR / f"산업재해조사표_{acc_id}.docx", PROFILE)
    log_accident_report(rep, str(path))
    md = [f"### 산업재해조사표 초안 {acc_id} — 제출 기한 **{rep['due']}**",
          "<small>산업안전보건법 제57조제3항 · 시행규칙 제73조제1항 (발생일부터 1개월) · 보존 3년 (법 제164조제1항제4호)</small>",
          f"\n**재해 발생 경과** ({rep['text_source']} 초안)  \n{rep['narrative']}",
          "\n**재해 발생 원인** — 조사자가 작성 (AI는 원인을 단정하지 않는다)",
          "\n**재발방지 계획 초안**"] + [f"- [{p['category']}] {p['text']}" for p in rep["prevention"]]
    if rep.get("check_needed"):
        md += [f"\n**조사자 확인 필요**  \n{rep['check_needed']}"]
    return "\n".join(md), _timeline_df(rep), str(path)


# ================================================================ 안전 문서 — 관제 인계
def handoff_choices(include_auto: bool = False):
    out = []
    for h in list_handoffs(include_auto):
        extra = [f"게이트 {n}" for n in [sum(1 for o in h["others"] if o["kind"] == "gate")] if n]
        extra += [f"사고 {n}" for n in [sum(1 for o in h["others"] if o["kind"] == "accident")] if n]
        out.append((f"{h['handoff_id']} · {h['source']} · 감지 {len(h['event_ids']) + len(h.get('duplicates', []))}건"
                    + (" · " + " · ".join(extra) if extra else ""), h["handoff_id"]))
    return out


def _latest_handoff():
    hs = list_handoffs(include_auto=False)
    return hs[0]["handoff_id"] if hs else None


EMPTY_HANDOFF = ("넘어온 감지 내역이 아직 없다. 관제 화면에서 **문서 자동화로 넘기기**를 누르면 여기에 쌓인다. "
                 "관제 화면이 없을 때는 아래 ‘관제 엔진 결과 파일로 넘기기’로 엔진 결과를 바로 넣어 볼 수 있다.")


def show_handoff(hid):
    """인계 한 건 — 넘어온 내역과 코드가 고른 '만들 수 있는 보고서'."""
    D.refresh()
    if not hid or not get_handoff(hid):
        return EMPTY_HANDOFF, pd.DataFrame(), "", gr.update(choices=[], value=[])
    c = report_candidates(hid, D.events, D.as_of, SCALES, PROFILE.get("accidents"))
    h = c["handoff"]
    info = [f"**{hid}** · {h['source']} · 받은 시각 {h['ts'].replace('T', ' ')}" + (f" · {h['by']}" if h.get("by") else ""),
            f"감지 {len(h['event_ids'])}건 받음 · 이미 받은 내역 {len(h['duplicates'])}건 건너뜀 · "
            f"게이트 {len(c['gates'])} · 사고 {len(c['accidents'])}"]
    if h.get("note"):
        info.append(f"메모: {h['note']}")
    info += [f"⚠ {w}" for w in h.get("warnings", [])]
    df = pd.DataFrame([{"시각": x["ts"][5:16].replace("T", " "), "번호": x["event_id"], "구역": x["zone"],
                        "작업 모드": x.get("mode") or "-", "위반": x["violation_type"],
                        "판정": x.get("level") or "무음 기록", "판정 근거": (f"{x['row']}번 줄 · " if x.get("row") else "")
                        + (x.get("reason") or ""), "프레임": "📷" if x.get("frame_path") else ""}
                       for x in c["events"]])

    cand = ["### 만들 수 있는 보고서", "<small>코드가 고른 후보다. 넘기는 것만으로는 아무 문서도 발행되지 않는다.</small>"]
    n_new = sum(1 for x in c["corrective"] if not x["issued"])
    cand.append(f"\n**시정지시서** — 경보 이상 {len(c['corrective'])}건"
                + (f" (이미 발행 {len(c['corrective']) - n_new}건)" if len(c["corrective"]) != n_new else "")
                + (" · 아래에서 골라 만든다" if c["corrective"] else " · 해당 없음"))
    if c["adhoc"]:
        cand.append("\n**수시 위험성평가 제안** — 이 인계의 감지가 들어간 행 (위험성평가 지침 제15조제2항)")
        cand += [f"- {a['zone']} · {a['mode']} · {a['violation_type']} — 위험도 {a['score']} {a['grade']} · "
                 f"{', '.join(a['reasons'])}" for a in c["adhoc"]]
        cand.append("\n→ **위험성평가로**: ① 계산 → ② AI 초안 → ③ 관리자 서명 → 근로자 확인")
    else:
        cand.append("\n**수시 위험성평가** — 기준(위험도 12 · 중대성 4)에 걸린 행 없음")
    if c["gates"]:
        cand.append("\n**작업허가서 점검** — 관제의 작업 전 게이트가 막은 기록이 있다. 같은 판정을 문서로 남긴다")
        cand += [f"- {g['ts'][11:16]} {g['zone']} {g['violation_type']} — {g.get('reason', '')}" for g in c["gates"]]
    if c["accidents"]:
        cand.append("\n**산업재해조사표** — 사고 기록이 있다. 사망 · 휴업 3일 이상이면 조사표 대상이다. "
                    "재해자 수 · 휴업일수는 사람이 넣는다 (지금은 config/site_profile.json 의 accidents)")
        cand += [f"- {a['ts'][11:16]} {a['zone']} {a['violation_type']} — {a.get('reason', '')}" for a in c["accidents"]]

    picks = [(f"{x['ts'][11:16]} {x['event_id']} · {x['zone']} · {x['violation_type']} · {x['level']}"
              + ("  📷" if x["frame"] else "") + (f"  · 발행됨 {x['issued']}" if x["issued"] else ""), x["event_id"])
             for x in c["corrective"]]
    return ("  \n".join(info), df, "\n".join(cand),
            gr.update(choices=picks, value=[x["event_id"] for x in c["corrective"] if not x["issued"]]))


def make_from_handoff(provider, hid, picked, progress=gr.Progress()):
    if not hid:
        raise gr.Error("인계 기록을 고르세요.")
    if not picked:
        raise gr.Error("시정지시서를 만들 이벤트를 고르세요.")
    D.refresh()
    progress(0, desc=f"시정지시서 {len(picked)}건")
    try:
        made = make_correctives(list(picked), D.events, RULESETS, LEGAL, SCALES, llm(provider), issued=D.as_of)
    except LLMError as ex:
        raise gr.Error(str(ex))
    md = [f"**시정지시서 초안 {len(made)}건** — 발행 기록이 남고 의무 이행 관리에 조치 기한이 올라간다"]
    md += [f"- {m['doc_no']} ← {m['event_id']} · 중대성 {m['severity']} · 조치 기한 **{m['deadline']}**"
           + (f"  \n  <small>{' · '.join(m['warnings'])}</small>" if m["warnings"] else "") for m in made]
    return "\n".join(md), [m["path"] for m in made]


def upload_handoff(path, base_dir, source):
    if not path:
        raise gr.Error("관제 엔진 결과 파일(events.jsonl 또는 events_for_docgen.json)을 올리세요.")
    base = str(base_dir or "").strip().strip('"') or None
    try:
        h = receive_file(path, source=(source or "").strip() or None, base_dir=base)
    except (ValueError, KeyError, OSError) as ex:
        raise gr.Error(f"파일을 읽을 수 없습니다: {ex}")
    gr.Info(f"{h['handoff_id']} — 감지 {len(h['event_ids'])}건 받음"
            + (f" · 이미 받은 {len(h['duplicates'])}건 건너뜀" if h["duplicates"] else ""))
    return gr.update(choices=handoff_choices(), value=h["handoff_id"])


def docs_refresh(ev_id, ptw_id, hid):
    """안전 문서 화면을 열 때 — 새로 넘어온 이벤트 · 새로 등록된 허가서 · 새 인계를 목록에 반영한다."""
    D.refresh()
    evc, ptc, hoc = event_choices(), ptw_choices(), handoff_choices()
    ev_ids, pt_ids, ho_ids = {v for _, v in evc}, {v for _, v in ptc}, {v for _, v in hoc}
    return (gr.update(choices=evc, value=ev_id if ev_id in ev_ids else default_event()),
            gr.update(choices=ptc, value=ptw_id if ptw_id in pt_ids else (ptc[0][1] if ptc else None)),
            gr.update(choices=hoc, value=hid if hid in ho_ids else _latest_handoff()))


# ================================================================ 안전소통
def voice_view():
    reps = list_reports()
    s = voice_summary(reps)
    summ = (f"<div class='cards'>"
            f"<div class='card'><div class='t'>총 제보</div><div class='n'>{s['total']}</div></div>"
            f"<div class='card'><div class='t'>조치 완료</div><div class='n'>{s['done']}</div></div>"
            f"<div class='card'><div class='t'>미조치</div><div class='n'>{s['open']}</div></div>"
            f"<div class='card'><div class='t'>조치율</div><div class='n'>{s['rate']:.0f}%</div></div></div>"
            "<p class='muted'>중대재해처벌법 시행령 제4조제7호 — 종사자 의견 청취와 개선방안 이행 여부를 반기 1회 이상 점검. "
            "기록 보존 5년 (시행령 제13조).</p>")
    df = pd.DataFrame([{"번호": r["report_id"], "접수": r["ts"].replace("T", " "), "구분": r["kind"], "구역": r["zone"],
                        "내용": r["text"], "제보자": r.get("reporter") or "익명", "상태": r["state"],
                        "조치": r.get("action", ""), "처리자": r.get("by", "")} for r in reps])
    choices = [(f"{r['report_id']} · {r['kind']} · {r['zone']} · {r['state']}", r["report_id"]) for r in reps]
    return summ, df, gr.update(choices=choices, value=None)


def do_submit(kind, zone, text, reporter):
    try:
        submit_report(kind, zone, text, reporter)
    except ValueError as ex:
        raise gr.Error(str(ex))
    return (*voice_view(), "")


def do_update(rid, state, action, by):
    if not rid:
        raise gr.Error("제보를 고르세요.")
    try:
        update_report(rid, state, action, by)
    except ValueError as ex:
        raise gr.Error(str(ex))
    return voice_view()


def pending_choices():
    return gr.update(choices=[(f"{ra['ra_id']} · {ra['kind']} · 관리자 {ra['manager']} · {len(ra['rows'])}행", ra["ra_id"])
                              for ra in list_assessments() if ra["state"] == "worker_pending"], value=None)


def show_pending(ra_id):
    if not ra_id:
        return None
    ra = get_assessment(ra_id)
    return pd.DataFrame([{"구역": r["zone"], "작업 모드": r["mode"], "위험도": f"{r['score']} {r['grade']}",
                          "유해·위험요인": r.get("hazard", ""), "감소대책": _measures_cell(r.get("measures", []))}
                         for r in ra["rows"]])


def do_confirm(ra_id, name, note):
    if not ra_id:
        raise gr.Error("확인할 평가를 고르세요.")
    try:
        ra = confirm_revision(ra_id, name, note)
    except ValueError as ex:
        raise gr.Error(str(ex))
    assessment_to_excel(ra["rows"], OUTPUT_DIR / f"위험성평가표_{ra_id}.xlsx", rulesets=RULESETS, scales=SCALES, record=ra)
    rules = sorted({m["rule_id"] for r in ra["rows"] for m in r["measures"] if m.get("rule_id")})
    msg = (f"**확정 — {ra_id}** · 관리자 {ra['manager']} · 근로자 대표 {ra['worker_rep']} ({ra['confirmed_at']})  \n"
           + (f"규칙셋에 {', '.join(rules)} 반영 → 기록 화면의 규칙셋 개정 이력" if rules else "규칙 변경 없음"))
    return msg, pending_choices(), None


def do_reject(ra_id, name, reason):
    if not ra_id:
        raise gr.Error("반려할 평가를 고르세요.")
    try:
        reject_revision(ra_id, "근로자 대표", name, reason)
    except ValueError as ex:
        raise gr.Error(str(ex))
    return f"**반려 — {ra_id}** · 사유: {reason}", pending_choices(), None


# ================================================================ 기록
def archive_view():
    D.refresh()
    retention = pd.DataFrame([{"문서": d["name"], "보존": f"{d['retention_years']}년", "근거": d["retention_basis"],
                               "기산일": d["retention_from"], "법정 문서": "예" if d["statutory"] else "내부 기록",
                               "관련 조문": "\n".join(d["basis"])} for d in DOCS.values()])
    return (pd.DataFrame(document_rows(DOCS)), pd.DataFrame(revision_rows()), pd.DataFrame(ruleset_rows(RULESETS)),
            pd.DataFrame(effect_rows(D.events, D.as_of, SCALES)), retention)


# ================================================================ 화면 — 틀(shell.py)에 넣을 묶음
def build(ctx):
    """문서 자동화 다섯 화면. 틀이 gr.Blocks 안에서 부른다."""
    provider = ctx.provider

    # ---------------------------------------------------------- 홈
    with ctx.page("home"):
        home_html = gr.HTML()
        with gr.Row():
            go_refresh = gr.Button("새로고침", size="sm")
            go_docs = gr.Button("안전 문서로", size="sm")
            go_duty = gr.Button("의무 이행 관리로", size="sm")
            go_voice = gr.Button("안전소통으로", size="sm")
    ctx.on_show("home", home_view, outputs=home_html)
    go_refresh.click(home_view, outputs=home_html)

    # ---------------------------------------------------------- 의무 이행 관리
    with ctx.page("duty"):
        gr.Markdown("사업장 조건에 따라 해당 의무가 달라진다. 사건형(재해조사표 · 수시평가 · 시정지시 · 제보 조치)은 "
                    "이 시스템의 기록에서 자동으로 생긴다.")
        with gr.Row():
            in_ind = gr.Dropdown(INDUSTRIES, value=PROFILE["industry"], label="업종")
            in_w = gr.Number(value=PROFILE["workers"], label="상시근로자 수", precision=0)
            in_hz = gr.Checkbox(value=PROFILE["hazardous_agents"], label="작업환경측정 대상 유해인자 노출")
            in_today = gr.DateTime(value=TODAY.isoformat(), include_time=False, type="string", label="기준일 (시연용)")
        in_cat = gr.CheckboxGroup(CATS, value=[], label="구분 (비우면 전체)")
        with gr.Tabs():
            with gr.Tab("해야 할 일"):
                banner_md = gr.Markdown()
                sched_df = gr.Dataframe(label="해야 할 일 (기한 순)", interactive=False, wrap=True,
                                        column_widths=["9%", "8%", "12%", "6%", "22%", "14%", "15%", "9%", "5%"])
                with gr.Accordion("대상 판정 — 사업장 조건별 · 근거 조문 · 서류 보존", open=False):
                    judge_df = gr.Dataframe(interactive=False, wrap=True)
                gr.Markdown("#### 이행 처리  \n이행일은 2026.10.10 · 10/10 처럼 쳐도 2026-10-10 으로 맞춰 저장된다. "
                            "담당자는 목록(config/staff.json)에서 고른다. 기록은 한 줄씩 추가만 되고 "
                            "지워지지 않는다 (records/compliance_done.jsonl · 보존 5년).")
                with gr.Row():
                    done_dd = gr.Dropdown(label="이행한 항목", choices=[], value=None, scale=3)
                    # 날짜 선택기(gr.DateTime)는 YYYY-MM-DD 가 아닌 입력을 조용히 버린다 → 글상자로 받고 양식을 맞춘다
                    done_day = gr.Textbox(value=TODAY.isoformat(), label="이행일", scale=1, min_width=140,
                                          placeholder="2026.10.12 · 10/12 도 됨")
                    done_by = gr.Dropdown(label="담당자 · 부서 · 직책", scale=2,
                                          choices=[(staff_label(p), p["id"]) for p in load_staff()], value=None)
                    done_note = gr.Textbox(label="비고", scale=2)
                btn_done = gr.Button("이행 처리")
            with gr.Tab("이행 완료") as t_done:
                done_md = gr.Markdown()
                done_df = gr.Dataframe(label="이행 완료 기록 (최근 이행일 순)", interactive=False, wrap=True,
                                       column_widths=["8%", "12%", "5%", "11%", "6%", "10%", "11%", "9%", "10%",
                                                      "7%", "11%"])
    sched_inputs = [in_ind, in_w, in_hz, in_today, in_cat]
    sched_outputs = [banner_md, sched_df, judge_df, done_dd, done_md, done_df]
    for comp in sched_inputs:
        comp.change(schedule_view, inputs=sched_inputs, outputs=sched_outputs)
    done_day.blur(norm_day, inputs=[done_day, in_today], outputs=done_day)
    done_day.submit(norm_day, inputs=[done_day, in_today], outputs=done_day)
    btn_done.click(do_mark, inputs=[done_dd, done_day, done_by, done_note] + sched_inputs,
                   outputs=sched_outputs + [done_day, done_note])
    t_done.select(done_view, inputs=[in_ind, in_w, in_hz, in_cat], outputs=[done_md, done_df])
    ctx.on_show("duty", schedule_view, inputs=sched_inputs, outputs=sched_outputs)
    ctx.on_show("duty", staff_choices, outputs=done_by)

    # ---------------------------------------------------------- 안전 문서
    with ctx.page("docs"):
        with gr.Tabs() as doc_tabs:
            with gr.Tab("관제 인계", id="handoff"):
                gr.Markdown("관제 화면에서 **문서 자동화로 넘기기**를 누른 감지 내역이 여기 쌓인다. "
                            "넘기는 것만으로 문서가 발행되지는 않는다 — 보고서는 여기서 고른 것만 만든다. "
                            "넘어온 내역은 위험성평가 · 의무 이행 관리 · 홈의 집계에도 바로 들어간다.")
                with gr.Row():
                    with gr.Column(scale=2):
                        ho_dd = gr.Dropdown(label="인계 기록 (최근 순)", choices=handoff_choices(),
                                            value=_latest_handoff())
                        ho_info = gr.Markdown()
                        with gr.Accordion("관제 엔진 결과 파일로 넘기기 — 관제 화면이 없을 때 시험용", open=False):
                            gr.Markdown("monitor_engine 의 `outputs/<시각>/…/events.jsonl` 또는 "
                                        "`events_for_docgen.json` 을 올린다. 프레임 · 클립이 있으면 그 파일이 있던 "
                                        "폴더를 적어야 프레임을 찾아 복사한다.")
                            ho_file = gr.File(label="엔진 결과 파일", file_types=[".json", ".jsonl"], type="filepath")
                            ho_base = gr.Textbox(label="엔진 출력 폴더 (선택)",
                                                 placeholder=r"예: C:\…\monitor_engine\outputs\20261012-091500\…\개정후")
                            ho_src = gr.Textbox(label="출처 이름 (선택)", placeholder="예: 재생 비교 · 개정 전")
                            btn_ho_recv = gr.Button("받기")
                    with gr.Column(scale=3):
                        ho_cand = gr.Markdown()
                        ho_pick = gr.CheckboxGroup(label="시정지시서를 만들 이벤트 (경보 이상)", choices=[], value=[])
                        btn_ho_make = gr.Button("선택한 이벤트로 시정지시서 초안 만들기", variant="primary")
                        ho_made = gr.Markdown()
                        ho_files = gr.File(label="만든 문서 (워드)", file_count="multiple")
                        with gr.Row():
                            go_ra = gr.Button("위험성평가로", size="sm")
                            go_ptw = gr.Button("작업허가서 점검으로", size="sm")
                            go_acc = gr.Button("산업재해조사표로", size="sm")
                ho_df = gr.Dataframe(label="넘어온 감지 내역 — 관제 판정 그대로 (판정 근거 = 판정표 몇 번 줄 · 켜진 축)",
                                     interactive=False, wrap=True)

            with gr.Tab("위험성평가", id="ra"):
                gr.Markdown("가능성 5 × 중대성 4. 숫자는 관제 이벤트로 코드가 계산하고, 문장만 AI가 쓴다. "
                            "관리자 서명 → 근로자 대표 확인(안전소통)으로 확정된다 — 산업안전보건법 제36조 · 시행규칙 제37조(보존 3년).")
                rows_state, drafts_state = gr.State([]), gr.State([])
                btn_calc = gr.Button("① 이벤트 집계 · 위험도 계산")
                calc_df = gr.Dataframe(label="코드가 계산한 값 — 최근 90일, 무음 기록 · 오탐 · 강화 기간 제외",
                                       interactive=False, wrap=True)
                adhoc_md = gr.Markdown()
                btn_draft = gr.Button("② AI 초안 생성", variant="primary")
                draft_df = gr.Dataframe(label="초안 — 문장 칸은 직접 고칠 수 있다. 감소대책은 한 줄에 하나, "
                                              "[공학적]·[관리적]·[보호구]로 시작. 규칙 변경과 같으면 [공학적·R1]처럼 적는다",
                                        interactive=True, wrap=True)
                draft_file = gr.File(label="초안 엑셀")
                with gr.Row():
                    ra_kind = gr.Radio(["수시", "정기"], value="수시", label="평가 구분")
                    manager = gr.Textbox(label="관리자 (검토·서명)")
                    mnote = gr.Textbox(label="비고")
                btn_sign = gr.Button("③ 관리자 서명 → 근로자 확인 요청", variant="primary")
                sign_md = gr.Markdown()
                sign_file = gr.File(label="서명본 엑셀")
                btn_calc.click(calc_table, outputs=[calc_df, adhoc_md, rows_state, ra_kind])
                btn_draft.click(make_drafts, inputs=[provider, rows_state], outputs=[draft_df, drafts_state, draft_file])
                btn_sign.click(sign_manager, inputs=[draft_df, drafts_state, ra_kind, manager, mnote],
                               outputs=[sign_md, sign_file])

            with gr.Tab("시정지시서", id="co"):
                gr.Markdown("위반 이벤트의 CCTV 프레임을 시스템이 넘기고, AI가 장면 · 위험 요인 · 시정 조치를 쓴다. "
                            "조치 기한과 근거 기록은 코드가 채운다. 발행하면 의무 이행 관리에 조치 기한이 올라간다. "
                            "⇠관제 = 관제에서 넘어온 이벤트.")
                with gr.Row():
                    with gr.Column(scale=2):
                        ev_dd = gr.Dropdown(choices=event_choices(), value=default_event(),
                                            label="위반 이벤트 (📷 = 프레임 있음)")
                        ev_img = gr.Image(label="CCTV 프레임", type="filepath", interactive=False)
                        ev_info = gr.Markdown()
                        btn_order = gr.Button("시정지시서 초안 생성", variant="primary")
                    with gr.Column(scale=3):
                        order_md = gr.Markdown()
                        order_file = gr.File(label="시정지시서 (워드)")
                ev_dd.change(show_event, inputs=ev_dd, outputs=[ev_img, ev_info])
                btn_order.click(make_order, inputs=[provider, ev_dd], outputs=[order_md, order_file])

            with gr.Tab("작업허가서 점검", id="ptw"):
                gr.Markdown("허가 발급 시점에 계획서의 빈칸을 찾는다. 격리 목록을 배관 계통도와 대조(R1)하고, "
                            "밸브만 잠근 배관(R2) · 퍼지 · 측정 기준(R4) · 동시작업을 코드로 판정한다. AI는 지적 문장만 쓴다. "
                            "허가서는 관제의 입력창에서 등록한 것을 읽는다 (입력 창구는 한 곳).")
                with gr.Row():
                    with gr.Column(scale=2):
                        ptw_dd = gr.Dropdown(choices=ptw_choices(), value=D.ptws[0]["ptw_id"] if D.ptws else None,
                                             label="작업허가서")
                        ptw_info = gr.Markdown()
                        iso_df = gr.Dataframe(label="첨부된 격리 목록", interactive=False, wrap=True)
                        iso_up = gr.File(label="격리 목록 CSV로 바꿔 넣기 (선택)", file_types=[".csv"], type="filepath")
                        btn_ptw = gr.Button("점검", variant="primary")
                    with gr.Column(scale=3):
                        ptw_md = gr.Markdown()
                        pid_df = gr.Dataframe(label="배관 계통도 ↔ 격리 목록", interactive=False, wrap=True)
                        fnd_df = gr.Dataframe(label="찾은 항목", interactive=False, wrap=True,
                                              column_widths=["20%", "25%", "37%", "18%"])
                        ptw_file = gr.File(label="점검 결과 (워드)")
                ptw_dd.change(show_ptw, inputs=ptw_dd, outputs=[ptw_info, iso_df])
                btn_ptw.click(run_ptw, inputs=[provider, ptw_dd, iso_up], outputs=[ptw_md, pid_df, fnd_df, ptw_file])

            with gr.Tab("산업재해조사표", id="acc"):
                gr.Markdown("사고 전 관제 기록 · 허가서로 발생 경과를 채운다. 재해자 정보와 원인 판단은 사람이 한다. "
                            "제출은 재해 발생일부터 1개월 이내 (산업안전보건법 제57조제3항 · 시행규칙 제73조).")
                with gr.Row():
                    with gr.Column(scale=2):
                        acc_dd = gr.Dropdown(choices=acc_choices(), value=DEFAULT_ACC, label="사고 (사망 또는 휴업 3일 이상)")
                        acc_tl = gr.Dataframe(label="관제 기록 타임라인", interactive=False, wrap=True)
                        btn_acc = gr.Button("조사표 초안 생성", variant="primary")
                    with gr.Column(scale=3):
                        acc_md = gr.Markdown()
                        acc_file = gr.File(label="산업재해조사표 초안 (워드)")
                acc_dd.change(show_acc, inputs=acc_dd, outputs=acc_tl)
                btn_acc.click(make_acc, inputs=[provider, acc_dd], outputs=[acc_md, acc_tl, acc_file])

    ho_outputs = [ho_info, ho_df, ho_cand, ho_pick]
    ho_dd.change(show_handoff, inputs=ho_dd, outputs=ho_outputs)
    btn_ho_recv.click(upload_handoff, inputs=[ho_file, ho_base, ho_src], outputs=ho_dd).then(
        show_handoff, inputs=ho_dd, outputs=ho_outputs).then(
        docs_refresh, inputs=[ev_dd, ptw_dd, ho_dd], outputs=[ev_dd, ptw_dd, ho_dd])
    btn_ho_make.click(make_from_handoff, inputs=[provider, ho_dd, ho_pick], outputs=[ho_made, ho_files]).then(
        show_handoff, inputs=ho_dd, outputs=ho_outputs).then(
        docs_refresh, inputs=[ev_dd, ptw_dd, ho_dd], outputs=[ev_dd, ptw_dd, ho_dd])
    go_ra.click(lambda: gr.Tabs(selected="ra"), outputs=doc_tabs).then(
        calc_table, outputs=[calc_df, adhoc_md, rows_state, ra_kind])
    go_ptw.click(lambda: gr.Tabs(selected="ptw"), outputs=doc_tabs)
    go_acc.click(lambda: gr.Tabs(selected="acc"), outputs=doc_tabs)
    ctx.on_show("docs", docs_refresh, inputs=[ev_dd, ptw_dd, ho_dd], outputs=[ev_dd, ptw_dd, ho_dd])
    ctx.on_show("docs", show_event, inputs=ev_dd, outputs=[ev_img, ev_info])
    ctx.on_show("docs", show_ptw, inputs=ptw_dd, outputs=[ptw_info, iso_df])
    ctx.on_show("docs", show_acc, inputs=acc_dd, outputs=acc_tl)
    ctx.on_show("docs", show_handoff, inputs=ho_dd, outputs=ho_outputs)

    def open_handoff(event, hid_component):
        """
        관제 쪽에서 쓰는 연결 — '문서 자동화로 넘기기' 이벤트 뒤에 붙이면
        안전 문서 › 관제 인계 화면이 열리고 방금 넘긴 인계가 선택된다.
            ev = send_btn.click(send_fn, inputs=..., outputs=hid_state)   # send_fn 이 handoff.receive() 를 부르고 번호를 돌려준다
            ctx.refs["docgen.open_handoff"](ev, hid_state)
        ctx.after(...) 안에서 부른다 (모든 화면이 만들어진 뒤).
        """
        ev = ctx.goto_event(event, "docs")
        return ev.then(lambda h: (gr.Tabs(selected="handoff"), gr.update(choices=handoff_choices(), value=h)),
                       inputs=hid_component, outputs=[doc_tabs, ho_dd]).then(
            show_handoff, inputs=ho_dd, outputs=ho_outputs)

    def open_tab(event, tab, value_component=None):
        """
        관제 쪽에서 안전 문서의 탭 하나를 여는 연결.  tab = ra · co · ptw · acc · handoff
        value_component 를 주면 그 값으로 고른다 — co 는 이벤트 번호, ptw 는 작업허가서 번호.
            ctx.refs["docgen.open_tab"](btn.click(...), "ptw", ptw_state)
        """
        ev = ctx.goto_event(event, "docs")
        if tab == "co" and value_component is not None:
            return ev.then(lambda v: (gr.Tabs(selected="co"), gr.update(choices=event_choices(), value=v)),
                           inputs=value_component, outputs=[doc_tabs, ev_dd]).then(
                show_event, inputs=ev_dd, outputs=[ev_img, ev_info])
        if tab == "ptw" and value_component is not None:
            return ev.then(lambda v: (gr.Tabs(selected="ptw"), gr.update(choices=ptw_choices(), value=v)),
                           inputs=value_component, outputs=[doc_tabs, ptw_dd]).then(
                show_ptw, inputs=ptw_dd, outputs=[ptw_info, iso_df])
        ev = ev.then(lambda: gr.Tabs(selected=tab), outputs=doc_tabs)
        if tab == "ra":
            ev = ev.then(calc_table, outputs=[calc_df, adhoc_md, rows_state, ra_kind])
        return ev

    ctx.refs["docgen.open_handoff"] = open_handoff
    ctx.refs["docgen.open_tab"] = open_tab
    ctx.refs["docgen.doc_tabs"] = doc_tabs

    # ---------------------------------------------------------- 안전소통
    with ctx.page("voice"):
        voice_summ = gr.HTML()
        voice_df = gr.Dataframe(label="제보 목록", interactive=False, wrap=True)
        with gr.Row():
            with gr.Column():
                gr.Markdown("#### 제보 접수 (제보자는 비우면 익명)")
                v_kind = gr.Radio(KINDS, value=KINDS[0], label="구분")
                v_zone = gr.Dropdown(ZONES, value=ZONES[0], label="구역")
                v_text = gr.Textbox(label="내용", lines=2)
                v_rep = gr.Textbox(label="제보자 (선택)")
                btn_v = gr.Button("접수", variant="primary")
            with gr.Column():
                gr.Markdown("#### 조치 기록")
                u_dd = gr.Dropdown(label="제보", choices=[], value=None)
                u_state = gr.Radio(STATES, value="조치 중", label="상태")
                u_act = gr.Textbox(label="조치 내용 (완료는 필수)", lines=2)
                u_by = gr.Textbox(label="처리자")
                btn_u = gr.Button("기록")
        gr.Markdown("#### 근로자 확인 — 위험성평가 (산업안전보건법 제36조제2항 · 위험성평가 지침 제6조 근로자 참여)")
        with gr.Row():
            p_dd = gr.Dropdown(label="근로자 확인 대기 평가", choices=[], value=None)
            p_name = gr.Textbox(label="근로자 대표")
            p_note = gr.Textbox(label="의견 · 반려 사유")
        p_df = gr.Dataframe(label="평가 내용", interactive=False, wrap=True)
        with gr.Row():
            btn_ok = gr.Button("확인 — 확정", variant="primary")
            btn_no = gr.Button("반려 (사유 필수)")
        p_md = gr.Markdown()
    voice_outs = [voice_summ, voice_df, u_dd]
    btn_v.click(do_submit, inputs=[v_kind, v_zone, v_text, v_rep], outputs=voice_outs + [v_text])
    btn_u.click(do_update, inputs=[u_dd, u_state, u_act, u_by], outputs=voice_outs)
    p_dd.change(show_pending, inputs=p_dd, outputs=p_df)
    btn_ok.click(do_confirm, inputs=[p_dd, p_name, p_note], outputs=[p_md, p_dd, p_df])
    btn_no.click(do_reject, inputs=[p_dd, p_name, p_note], outputs=[p_md, p_dd, p_df])
    ctx.on_show("voice", voice_view, outputs=voice_outs)
    ctx.on_show("voice", pending_choices, outputs=p_dd)

    # ---------------------------------------------------------- 기록
    with ctx.page("archive"):
        gr.Markdown("모든 문서와 개정 이력. 기록은 추가만 되고 지워지지 않는다. "
                    "보존 기한은 그 전에 지우면 안 되는 날이다.")
        arc_docs = gr.Dataframe(label="문서 — 보존 기한", interactive=False, wrap=True)
        arc_eff = gr.Dataframe(label="개선 효과 — 개선 후 위험도 실측 (적용일 전후 같은 기간 위반 건수)",
                               interactive=False, wrap=True)
        with gr.Row():
            arc_rev = gr.Dataframe(label="위험성평가 개정 로그", interactive=False, wrap=True)
            arc_rule = gr.Dataframe(label="규칙셋 개정 이력", interactive=False, wrap=True)
        with gr.Accordion("문서별 보존 기간과 근거 조문", open=False):
            arc_ret = gr.Dataframe(interactive=False, wrap=True)
    ctx.on_show("archive", archive_view, outputs=[arc_docs, arc_rev, arc_rule, arc_eff, arc_ret])

    # ---------------------------------------------------------- 화면 사이 이동 (홈의 바로가기)
    ctx.link(go_docs, "docs")
    ctx.link(go_duty, "duty")
    ctx.link(go_voice, "voice")


def badges() -> dict:
    """메뉴 옆 숫자 — 홈: 확정 대기(수시평가 제안 + 근로자 확인 대기) · 안전소통: 미조치 제보 + 근로자 확인 대기."""
    D.refresh()
    h = home_summary(D.events, D.as_of, SCALES, PROFILE, TODAY)
    pend = sum(1 for ra in list_assessments() if ra["state"] == "worker_pending")
    return {"home": h["cards"][0]["num"], "voice": voice_summary(list_reports())["open"] + pend}


def docgen_section() -> Section:
    """틀(shell.sidebar_app)에 넣을 '문서 자동화' 메뉴 묶음."""
    return Section("문서 자동화", PAGES, build, subtitle=subtitle, badges=badges)
