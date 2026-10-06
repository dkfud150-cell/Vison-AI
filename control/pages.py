"""
관제 여섯 화면 — 한 프로그램의 틀(docgen safety_docs/shell.py)에 들어가는 '관제' 메뉴 묶음.

  live      실시간 관제         시연 시계 · 구역 상태 · 카메라 · 3축 신호판 · 판정표 · 작업허가서 · 다음 처리
                                + 시연 제어(스케줄 · 규칙셋 · 영상 장면 · 속도) · 현장 입력(버튼 · 신호)
  iso       격리 목록 대조      작업허가서 등록(입력 창구는 여기 한 곳) · 계통도 ↔ 목록 · 맹판 · 퍼지 · 가스 측정 단계 입력
  log       이벤트 로그         필터 · 상세(프레임 · 판정 근거) · 오탐 표시 · 문서 자동화로 넘기기
  replay    재생 비교           시나리오 × 규칙셋 · 기대 결과 대조 · 플레이어
  feedback  피드백 · 조정 로그  짧은 루프(자동 조정 · 되돌리기 · 승인) · 긴 루프(규칙셋 변경안 · 제안) · 방식 전환
  stats     히트맵 · 통계       구역 × 시간 · 모드가 켜졌을 때 vs 평상시 · 안전모

문서 자동화와의 연결은 ctx.refs 로 한다 — docgen.open_handoff(넘긴 뒤 관제 인계 화면 열기) · docgen.open_tab(탭 열기).
"""
from __future__ import annotations

from pathlib import Path

import gradio as gr
import pandas as pd

from safety_docs.shell import Section

from . import feedback, isolation, replay, stats
from . import views as V
from .common import dashboard, frame_file, load_config, load_control_events, package, ruleset_status, system_now, zone_name, zones
from .session import RULESETS, SESSION

PAGES = [("live", "실시간 관제"), ("iso", "격리 목록 대조"), ("log", "이벤트 로그"), ("replay", "재생 비교"),
         ("feedback", "피드백 · 조정 로그"), ("stats", "히트맵 · 통계")]
e = V.e


def sec(title: str, sub: str = "") -> str:
    return V.wrap(f"<div class='ph'><h3>{e(title)}</h3><span class='sub'>{e(sub)}</span></div>")


def subtitle() -> str:
    """화면 제목 아래 한 줄 — 화면을 열 때 한 번 계산한다 (시연 시계 · 세션은 화면 안 상태 줄이 1초마다 보인다)."""
    fbm = "자동" if feedback.mode() == "auto" else "승인형"
    rs = ruleset_status()
    return (f"사업장 패키지 {e(package().root.name)} · 운영 규칙셋 v{rs['version']} "
            f"({e(' '.join(rs['ids']) or '개정 없음 — 기본 규칙')}) · 피드백 {fbm} · 관제 기록은 추가만 된다")


def _err(fn):
    """화면 함수의 ValueError · RuntimeError · KeyError 를 화면 알림으로 바꾼다."""
    def w(*a):
        try:
            return fn(*a)
        except (ValueError, RuntimeError, KeyError) as ex:
            raise gr.Error(str(ex).strip("'")) from None
    w.__name__ = fn.__name__
    return w


def _for_handoff(evs: list[dict]) -> list[dict]:
    """넘길 줄 — 화면용 키(_ts 등)를 빼고, 프레임 · 클립 경로를 절대 경로로 바꾼다 (여러 세션 기록을 한 번에 넘기려고)."""
    out = []
    for ev in evs:
        r = {k: v for k, v in ev.items() if not k.startswith("_") and k not in ("fp_by",)}
        f = frame_file(ev)
        r["frame_path"] = str(f) if f else None
        cp = ev.get("clip_path")
        if cp and not Path(cp).is_absolute() and ev.get("_base"):
            c = Path(ev["_base"]) / cp
            r["clip_path"] = str(c) if c.exists() else cp
        out.append(r)
    return out


_adhoc = {"key": None, "n": 0}


def adhoc_count() -> int:
    """수시 위험성평가 제안 건수 — 문서 자동화의 계산 그대로 (넘어온 기록 · 오탐 표시가 바뀔 때만 다시 센다)."""
    from safety_docs.assessment import build_rows
    from safety_docs.config import FP_MARKS, MONITOR_EVENTS, load_events, load_profile, load_scales
    key = tuple(p.stat().st_mtime if p.exists() else 0 for p in (MONITOR_EVENTS, FP_MARKS))
    if key != _adhoc["key"]:
        evs, as_of = load_events()
        _, ad = build_rows(evs, as_of, load_scales(), load_profile().get("accidents"))
        _adhoc.update(key=key, n=len(ad))
    return _adhoc["n"]


# ====================================================================== 실시간 관제
def _default_zone(s) -> str:
    sc = SESSION.scenario
    if sc and sc.zone in s["zones"]:
        return sc.zone
    return next((z for z, st in s["zones"].items() if st.get("table")), next(iter(s["zones"])))


def live_view(sel, follow, last):
    s = SESSION.snapshot()
    w = V.worst_zone(s)
    if follow and w and w[1]["level"] != "정상":
        sel = w[0]
    if sel not in s["zones"]:
        sel = _default_zone(s)
    choices = [(V.zone_label(z, st), z) for z, st in s["zones"].items()]
    key = [choices, sel]
    radio = gr.skip() if key == last else gr.update(choices=choices, value=sel)
    rows = s["rows"]
    counts = {"alerts": sum(1 for r in rows if r.get("kind") in ("stage", "check") and r.get("alerted")
                            and r.get("level") in ("경보", "최고 경보")),
              "adhoc": adhoc_count(), "gates": sum(1 for r in rows if r.get("kind") == "gate")}
    st = s["zones"][sel]
    cams = [c for c in V._cams() if c.get("zone") == sel]
    cam_sub = (" · ".join(c["camera_id"] for c in cams) or "카메라 없음") + (" · 영상 탐지 중" if s["video"] else "")
    play = gr.update(value="⏸ 멈춤" if s["running"] else ("▶ 계속" if s["sid"] else "▶ 시작"))
    return (V.status_bar(s), V.alarm(s), radio, V.tiles(s, sel),
            sec(f"카메라 — {sel} {zone_name(sel)}", cam_sub) + V.camera(s, sel, None),
            sec(f"오늘 이 구역 기록 — {sel}", "이 세션 · 무음 기록 포함") + V.zone_log(s, sel),
            sec(f"3축 신호판 — {sel} {zone_name(sel)}", " · ".join(st["modes"]) or "평상시") + V.axes(s, sel)
            + V.judge_table(s, sel),
            sec("작업허가서", sel) + V.ptw_card(sel), V.next_cards(s, counts), V.notes(s), sel, key, play)


def pick_zone(z):
    return z, False


def scene_choices(schedule: str):
    if not schedule:
        return gr.update(choices=[("영상 없음 — 신호로만 판정", "")], value="")
    sc = package().scenario(schedule)
    ch = [("영상 없음 — 신호로만 판정", "")] + [(f"{x['name']} · {x.get('at') or '시각 없음'} · {x.get('camera')}", x["name"])
                                                for x in sc.scenes() if x.get("at")]
    return gr.update(choices=ch, value="")


@_err
def new_session(schedule, ruleset, scene, start, speed):
    SESSION.reset(schedule or None, ruleset, (start or "07:55").strip(), scene or None, float(speed or 10))
    SESSION.start()
    m = SESSION.meta
    return (f"**새 세션 {SESSION.sid}** — {m['schedule_title']} · 규칙 {m['rules_label']} · {m['start']:%H:%M} 부터"
            + (f" · 영상 장면 '{scene}'" if scene else "") + "  \n기록: `control/records/live/" + SESSION.sid + "/`")


def toggle_play(schedule, ruleset, scene, start, speed):
    if not SESSION.sid:                      # 아직 시작 전 — 고른 값으로 새 세션
        return new_session(schedule, ruleset, scene, start, speed)
    if SESSION.running:
        SESSION.pause()
        return "멈췄다 — 시연 시계가 선다. 기록은 그대로다."
    SESSION.start()
    return f"계속 — {SESSION.speed:g}× · 세션 {SESSION.sid}"


def set_speed(v):
    SESSION.set_speed(float(v))


@_err
def press(key):
    b = package().buttons[key]
    notes = SESSION.press(key)
    return f"**{key} · {b.get('label', b['signal'])}** 넣음 ({SESSION.clock():%H:%M:%S})" + "".join(f"  \n- {n}" for n in notes)


@_err
def put_signal(signal, zone, target, value, note):
    if not signal:
        raise ValueError("신호를 고른다")
    notes = SESSION.apply_signal(signal, zone or None, (target or "").strip() or None, (value or "").strip() or None,
                                 source="입력창", note=(note or "").strip())
    return f"**{signal}** {zone or ''} {target or ''} {value or ''} 넣음 ({SESSION.clock():%H:%M:%S})" + \
        "".join(f"  \n- {n}" for n in notes)


@_err
def handoff_session():
    ho = SESSION.handoff()
    return ho["handoff_id"]


@_err
def last_alert_event():
    """시정지시서로 — 이 세션의 마지막 경보 이상 기록(없으면 전체 기록의 마지막)을 넘겨 두고 그 번호를 돌려준다."""
    rows = [r for r in (SESSION.log.rows if SESSION.sid and SESSION.log else [])
            if r.get("kind") in ("stage", "check") and r.get("alerted") and r.get("level") in ("경보", "최고 경보")]
    if rows:
        SESSION.handoff([rows[-1]["event_id"]])
        from safety_docs.config import load_events
        evs, _ = load_events()
        ids = {x["event_id"] for x in evs}
        return rows[-1]["event_id"] if rows[-1]["event_id"] in ids else None
    return None


# ====================================================================== 격리 목록 대조
ISO_FILTER = {"전체": "all", "진행 중": "open", "문제 있음": "bad"}


def iso_choices(filt: str, cur: str | None):
    items = []
    for p in sorted(isolation.ptws(), key=lambda x: x.get("start", ""), reverse=True):
        v = isolation.view(p)
        if filt == "open" and not v["open"]:
            continue
        if filt == "bad" and v["kind"] not in ("crit", "warn"):
            continue
        items.append((f"{p['ptw_id']} · {p.get('type', '')} · {p['zone']} · {p['work'][:28]} — {v['tag']}", p["ptw_id"]))
    ids = [i for _, i in items]
    return gr.update(choices=items, value=cur if cur in ids else (ids[0] if ids else None))


def iso_show(ptw_id):
    p = next((x for x in isolation.ptws() if x["ptw_id"] == ptw_id), None)
    if not p:
        empty = V.wrap("<p class='empty'>작업허가서를 고른다. 없으면 아래 '+ 작업허가서 등록'으로 넣는다.</p>")
        return ("", empty, "", "", "", "", gr.update(choices=[], value=None), gr.update(choices=[], value=None))
    v = isolation.view(p)
    info = (f"**{p['ptw_id']}** · {p.get('type', '')} · {p['zone']} {zone_name(p['zone'])} · "
            f"{p.get('start', '').replace('T', ' ')} ~ {p.get('end', '')[11:16]} · {'진행 중' if v['open'] else '시간 밖'}  \n"
            f"{p['work']} · 작업책임자 {p.get('supervisor') or '(비어 있음)'} · 인원 {p.get('workers') or '-'}"
            + (f" · {p['source']}" if p.get("source") else ""))
    pend = [(f"{ln['line_id']} {ln['name']}", ln["line_id"]) for ln in v["check"]["lines"]
            if ln["in_list"] and ln["blind"] != "done"]
    pts = [(m["point"], m["line_id"]) for m in v["meas"]]
    return (info, V.iso_kpis(v), sec(f"배관 계통도 — {v['check']['equipment']}", "시스템이 가진 설비 정보 · site.json") + V.iso_diagram(v),
            sec("격리 목록 — 작업계획서", "허가서에 첨부된 CSV") + V.iso_list(v),
            sec("맹판 설치 단계 입력", "R2 · 밸브만 잠근 것은 해제가 아니다") + V.iso_blinds(v),
            sec("퍼지 · 가스 측정", "R4") + V.iso_meas(v),
            gr.update(choices=pend, value=pend[0][1] if pend else None),
            gr.update(choices=pts, value=pts[0][1] if pts else None))


@_err
def iso_step(kind, ptw_id, line, value, by):
    p = next((x for x in isolation.ptws() if x["ptw_id"] == ptw_id), None)
    if not p:
        raise ValueError("작업허가서를 고른다")
    if not (by or "").strip():
        raise ValueError("입력자 이름을 적는다 — 단계 입력 기록에 남는다")
    notes = isolation.step(p, kind, line, None if value is None else str(value), by)
    what = {"blind": f"{line} 맹판 설치 완료", "gas": f"{line} 가스 측정 LEL {value}%", "purge": f"퍼지 {value}분"}[kind]
    eng = "  \n엔진: " + " · ".join(notes) if notes else ("" if SESSION.sid else "  \n(세션이 돌지 않아 엔진에는 넣지 않았다 — 기록만)")
    return f"**{p['ptw_id']}** {what} 입력 · {by.strip()}{eng}"


def reg_sample(zone):
    wts = [k for k in load_config()["work_types"] if not k.startswith("_")]
    wt = wts[0] if wts else None
    day = system_now().date().isoformat()
    return (wt, f"{day}T13:00", f"{day}T17:00", f"{zone_name(zone)} 연결 배관 격리 후 정비",
            "김정비", 3, isolation.sample_csv(zone), False)


def read_csv_file(path):
    if not path:
        return gr.skip()
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise gr.Error("CSV 글자를 읽지 못했다 (UTF-8 또는 CP949)")


@_err
def reg_check(zone, csv_text, no_list):
    rows = None if no_list else isolation.parse_csv(csv_text or "")
    if not no_list and not rows:
        raise ValueError("격리 목록 CSV 를 붙여넣거나 올린다")
    return V.reg_preview(zone, isolation.cross_check(zone, rows))


@_err
def reg_save(zone, wt, start, end, work, sup, workers, csv_text, no_list):
    r = isolation.register(zone, wt, (start or "").strip(), (end or "").strip(), work or "", sup or "", workers,
                           csv_text, bool(no_list))
    p, chk = r["ptw"], r["check"]
    miss = [x for x in chk["lines"] if not x["in_list"]] if not no_list else []
    msg = [f"**등록 — {p['ptw_id']}** · {p['type']} · {zone} · 문서 자동화 › 작업허가서 점검에서도 바로 보인다"]
    if no_list:
        msg.append("격리 목록 없이 등록했다 — 작업 전 게이트(LIST)가 걸린다")
    elif miss:
        msg.append(f"목록에 없는 연결 {len(miss)}건 ({', '.join(x['line_id'] for x in miss)}) — 작업 전 게이트(R1)")
    if r["engine_notes"]:
        msg.append("엔진: " + " · ".join(r["engine_notes"]))
    elif not SESSION.sid:
        msg.append("세션이 돌지 않아 엔진에는 넣지 않았다 — 실시간 관제에서 세션을 시작하면 이후 입력부터 들어간다")
    return "  \n".join(msg), p["ptw_id"]


# ====================================================================== 이벤트 로그
PERIODS = {"오늘": 0, "최근 14일": 14, "최근 90일": 90, "전체": None}
ALERT_F = {"전체": "all", "경보": "alert", "무음 기록": "shadow"}
LOG_COLS = ["번호", "일시", "구역", "모드", "위반 유형", "단계", "비고"]
KIND_T = {"gate": "작업 전 게이트", "accident": "사고", "info": "참고", "stage": "3축 판정", "check": "모드 규칙"}


def _filter(evs, mode, alert, zone, period, kinds, src):
    from datetime import timedelta
    now = system_now()
    out = []
    for ev in evs:
        k = ev.get("kind", "stage")
        if kinds == "감지만" and k not in ("stage", "check"):
            continue
        if mode and mode != "전체" and (ev.get("mode") or "-") != mode:
            continue
        if alert == "alert" and not ev.get("alerted"):
            continue
        if alert == "shadow" and (ev.get("alerted") or k not in ("stage", "check")):
            continue
        if zone and zone != "전체" and ev.get("zone") != zone:
            continue
        days = PERIODS.get(period)
        if days == 0 and ev["_ts"].date() != now.date():
            continue
        if days and not (now - timedelta(days=days) < ev["_ts"]):
            continue
        if src == "샘플" and ev["_src"] != "샘플":
            continue
        if src == "실시간 세션" and ev["_src"] == "샘플":
            continue
        out.append(ev)
    return out


def log_filters():
    evs = load_control_events()
    modes = ["전체"] + sorted({ev.get("mode") or "-" for ev in evs})
    return gr.update(choices=modes), gr.update(choices=["전체"] + zones())


def log_view(mode, alert, zone, period, kinds, src):
    evs = _filter(load_control_events(), mode, ALERT_F.get(alert, "all"), zone, period, kinds, src)
    evs = list(reversed(evs))
    rows = []
    for ev in evs:
        k = ev.get("kind", "stage")
        lvl = ev.get("computed_level") or ev.get("level") or ""
        if k in ("gate", "accident", "info"):
            stage = KIND_T[k]
        else:
            stage = (lvl or "-") if ev.get("alerted") else f"무음 · {lvl or '-'}"
        memo = [x for x in ("강화 중" if ev.get("adj_id") else "", "오탐" if ev.get("false_positive") else "",
                            "샘플" if ev["_src"] == "샘플" else "실시간") if x]
        rows.append({"번호": ev["event_id"], "일시": ev["ts"][5:16].replace("T", " "), "구역": ev.get("zone", ""),
                     "모드": ev.get("mode") or "-", "위반 유형": ev.get("violation_type") or ev.get("reason", "")[:30],
                     "단계": stage, "비고": " · ".join(memo)})
    df = pd.DataFrame(rows, columns=LOG_COLS)
    na = sum(1 for ev in evs if ev.get("alerted") and ev.get("kind", "stage") in ("stage", "check"))
    ns = sum(1 for ev in evs if not ev.get("alerted") and ev.get("kind", "stage") in ("stage", "check"))
    head = sec(f"이벤트 {len(evs)}건 · 경보 {na} · 무음 기록 {ns}", "events.jsonl · 추가만 되고 지워지지 않는다 · 줄을 누르면 상세")
    return head, df, [ev["event_id"] for ev in evs]


def log_select(ids, evt: gr.SelectData):
    i = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
    eid = ids[i] if ids and 0 <= i < len(ids) else None
    return eid, log_detail(eid)


def log_detail(eid):
    ev = next((x for x in load_control_events() if x["event_id"] == eid), None) if eid else None
    return V.event_detail(ev)


@_err
def mark_fp(eid, by, reason, undo):
    from safety_docs.handoff import mark_false_positive
    if not eid:
        raise ValueError("표에서 이벤트를 고른다")
    mark_false_positive(eid, by or "", reason or "", undo=undo)
    return f"**{eid}** 오탐 표시 {'취소' if undo else ''} · {by.strip()}" + (f" · 사유: {reason}" if reason else "") + \
        "  \n위험성평가 집계 · 통계에서 빠진다(취소하면 다시 들어간다). 오탐을 근거로 한 완화는 사람이 승인한다."


@_err
def handoff_events(eids: list[str], source: str):
    from safety_docs.handoff import receive
    evs = [x for x in load_control_events() if x["event_id"] in set(eids)]
    if not evs:
        raise ValueError("넘길 이벤트가 없다")
    return receive(_for_handoff(evs), source=source)["handoff_id"]


def handoff_one(eid):
    if not eid:
        raise gr.Error("표에서 이벤트를 고른다")
    return handoff_events([eid], "이벤트 로그 · 한 건")


def handoff_visible(mode, alert, zone, period, kinds, src):
    evs = _filter(load_control_events(), mode, ALERT_F.get(alert, "all"), zone, period, kinds, src)
    evs = [x for x in evs if (x.get("alerted") and x.get("level") in ("경보", "최고 경보")) or x.get("kind") in ("gate", "accident")]
    if not evs:
        raise gr.Error("보이는 목록에 경보 이상 · 게이트 · 사고가 없다")
    return handoff_events([x["event_id"] for x in evs], f"이벤트 로그 · {period} · {zone} · 경보 이상")


@_err
def co_event(eid):
    """시정지시서로 — 넘겨 두고(이미 넘어가 있으면 그대로) 번호를 돌려준다."""
    if not eid:
        raise ValueError("표에서 이벤트를 고른다")
    ev = next((x for x in load_control_events() if x["event_id"] == eid), None)
    if not ev or not ev.get("alerted") or ev.get("kind", "stage") not in ("stage", "check"):
        raise ValueError("시정지시서는 경보로 울린 감지 기록으로 만든다 (무음 기록 · 게이트 · 사고는 아니다)")
    handoff_events([eid], "이벤트 로그 · 시정지시서")
    return eid


# ====================================================================== 재생 비교
def _mins(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _hhmm(v: float) -> str:
    v = int(round(v))
    return f"{v // 60:02d}:{v % 60:02d}"


def sc_choices(cur=None, force=False):
    items = []
    for k in replay.scenario_keys():
        res = replay.run(k, force)
        ok, n = replay.score(res)
        items.append((f"{res['title']} · 기대 결과 {ok}/{n}{' ✓' if ok == n else ' ✗'}", k))
    ids = [k for _, k in items]
    return gr.update(choices=items, value=cur if cur in ids else (ids[0] if ids else None))


def sc_show(key):
    if not key:
        return "", "", gr.update(), "", "", "", gr.update(choices=[], value=None)
    res = replay.run(key)
    ts = res["times"]
    lo, hi = (_mins(ts[0]), _mins(ts[-1])) if ts else (0, 1)
    head = (f"**{res['title']}** · 구역 {res['zone']} {zone_name(res['zone'])} · 판정표 {res['table']}  \n"
            f"{res['basis']}")
    names = list(res["variants"])
    return (head, V.versus(res), gr.update(minimum=lo, maximum=max(hi, lo + 1), value=lo),
            *sc_cursor(key, lo)[:2], V.expect_list(res), gr.update(choices=names, value=names[0] if names else None))


def sc_cursor(key, v):
    if not key:
        return "", "", ""
    res = replay.run(key)
    t = _hhmm(v)
    return (sec(f"커서 {t}", "그 시각까지의 마지막 판정") + V.cursor_cards(res, t),
            sec("타임라인", "timeline.csv · 규칙셋마다 같은 신호를 넣은 결과") + V.merged_table(res, t), t)


def sc_tick(key, v, speed, playing):
    if not key or not playing:
        return gr.skip(), gr.Timer(active=False), False, gr.update(value="▶ 재생")
    res = replay.run(key)
    hi = _mins(res["times"][-1]) if res["times"] else 0
    nv = min(hi, float(v or 0) + float(speed) * 0.5 / 60)
    if nv >= hi:
        return nv, gr.Timer(active=False), False, gr.update(value="▶ 재생")
    return nv, gr.skip(), True, gr.skip()


def sc_play(key, v, playing):
    if playing:
        return gr.Timer(active=False), False, gr.update(value="▶ 재생"), gr.skip()
    res = replay.run(key)
    lo, hi = (_mins(res["times"][0]), _mins(res["times"][-1])) if res["times"] else (0, 0)
    start = lo if (v is None or float(v) >= hi) else v
    return gr.Timer(active=True), True, gr.update(value="⏸ 멈춤"), start


@_err
def sc_import(path):
    if not path:
        raise ValueError("시나리오 폴더를 묶은 zip 을 올린다 (scenario.json · timeline.csv · 입력 문서)")
    key = replay.import_zip(path)
    return key, f"**불러옴 — {key}** · 사업장 패키지 scenarios/ 에 풀었다"


@_err
def sc_handoff(key, name):
    from safety_docs.handoff import receive
    res = replay.run(key)
    v = res["variants"].get(name)
    if not v:
        raise ValueError("넘길 규칙셋 결과를 고른다")
    return receive(v["run"]["log"].rows, source=f"재생 비교 · {res['title']} · {name}", base_dir=v["out_dir"])["handoff_id"]


# ====================================================================== 피드백
def fb_view(rc_id):
    now = system_now()
    act = feedback.active(now)
    pend = feedback.pending()
    adjs = feedback.adjustments()
    n14 = sum(feedback.zone_counts(now).values())
    rs = ruleset_status()
    mode = feedback.mode()
    open_ = sorted(act + pend, key=lambda a: a["ts"], reverse=True)
    rcs = feedback.rule_changes_view()
    rc_ids = [(f"{r['id']} · {r['status'].split(' ·')[0]}", r["id"]) for r in rcs]
    rc_cur = rc_id if rc_id in [r["id"] for r in rcs] else next((r["id"] for r in rcs if r["step"] == 2), rcs[0]["id"] if rcs else None)
    rc = next((r for r in rcs if r["id"] == rc_cur), None)
    toggles = [r for r in feedback.rows() if r.get("state") == "toggle"]
    return (V.fb_kpis(now, act, pend, n14, rs, mode), gr.update(value="자동" if mode == "auto" else "승인형"),
            sec("활성 조정 · 짧은 루프", "자동 · 기한부 · 강화 방향만") + V.adj_cards(open_, now),
            gr.update(choices=[(f"{a['adj_id']} · {a['zone']} · {a['state']}", a["adj_id"]) for a in open_],
                      value=open_[0]["adj_id"] if open_ else None),
            gr.update(choices=rc_ids, value=rc_cur), V.rc_view(rc) if rc else V.wrap("<p class='empty'>규칙셋 변경안이 없다</p>"),
            sec("제안 · 알림", "승격 · 절대 기준 · 위험도 · 오탐 과다 · 급감") + V.proposals_html(feedback.proposals(now)),
            sec("구역별 조정 횟수", "최근 14일") + V.zone_bars(feedback.zone_counts(now)),
            sec("이탈 조건", "사업장 패키지 rules.json feedback") + V.criteria_table(feedback.config()),
            sec("조정 로그", "adjustments.jsonl") + V.adj_log_table(adjs, toggles))


def rc_show(rc_id):
    rc = next((r for r in feedback.rule_changes_view() if r["id"] == rc_id), None)
    return V.rc_view(rc) if rc else ""


@_err
def fb_set_mode(label, actor, note):
    new = "auto" if label == "자동" else "approval"
    if new == feedback.mode():
        return f"이미 {label} 방식이다"
    feedback.set_mode(new, actor or "", note or "", system_now())
    return f"**피드백 방식 → {label}** · {actor} · 사유: {note} — 조정 로그에 남았다"


@_err
def fb_act(action, adj_id, actor, note):
    if not adj_id:
        raise ValueError("조정을 고른다")
    now = system_now()
    if action == "revert":
        feedback.revert(adj_id, actor or "", note or "", now)
        return f"**{adj_id} 되돌림** · {actor} · 사유: {note}"
    if action == "approve":
        feedback.approve(adj_id, actor or "", now)
        return f"**{adj_id} 승인 — 적용** · {actor}"
    if action == "reject":
        feedback.reject(adj_id, actor or "", note or "", now)
        return f"**{adj_id} 거부** · {actor} · 사유: {note}"
    feedback.promote(adj_id, actor or "", note or "", now)
    return f"**{adj_id} → 개정 제안으로 승격** · 문서 자동화 › 위험성평가에서 감소대책(규칙 변경)으로 확정한다"


@_err
def fb_eval():
    new = feedback.evaluate(system_now())
    if not new:
        return "이탈 조건에 걸린 새 조합이 없다 (만료 정리만 했다)"
    return "**새 자동 조정**" + "".join(f"  \n- {a['adj_id']} · {a['zone']} · {feedback.reason_text(a)} · {a['state']}" for a in new)


# ====================================================================== 통계
HEAT_F = {"전체": "all", "경보만": "alert", "무음 기록만": "shadow"}


def stats_view(which):
    now = system_now()
    evs = load_control_events()
    h = stats.heat(evs, now, 14, HEAT_F.get(which, "all"))
    hm = stats.helmet(evs, now)
    return (sec(f"구역 × 시간 — 최근 14일 위반 건수 ({h['n']}건)", "오탐 표시 제외 · 무음 기록 포함") + V.heat_table(h),
            sec("작업 모드가 켜졌을 때 vs 평상시", "시간당 위반 · 같은 구역 · 실시간 세션 기록") + V.rate_bars(stats.mode_rates(evs, now)),
            sec("안전모 착용률" if hm["has_model"] and hm["rate"] else "안전모 미착용 기록",
                "부서 · 협력사별 · 최근 14일 (샘플 대응표 control/config.json)") + V.helmet_panel(hm))


# ====================================================================== 화면 만들기
def build(ctx):
    pkg = package()
    cfg = load_config()["live"]
    demo = dashboard().get("demo", {})
    focus = demo.get("focus_zone") if demo.get("focus_zone") in zones() else (zones()[0] if zones() else None)
    sched0 = demo.get("schedule") if demo.get("schedule") in pkg.scenario_keys() else ""
    refs = {}

    # ---------------------------------------------------------- 실시간 관제
    with ctx.page("live"):
        status = gr.HTML()
        with gr.Accordion("시연 제어 — 오늘 신호 스케줄 · 규칙셋 · 영상 장면 · 속도", open=True):
            with gr.Row():
                sc_keys = pkg.scenario_keys()
                sched = gr.Dropdown([("스케줄 없음 — 버튼으로만", "")] + [(pkg.scenario(k).title, k) for k in sc_keys],
                                    value=sched0, label="신호 스케줄 (PLC · PTW · 센서 대신)", scale=3)
                rs_choices = [(v, k) for k, v in RULESETS.items()] + [(f"{i}만", i) for i in pkg.change_ids()]
                ruleset = gr.Dropdown(rs_choices, value=cfg.get("ruleset", "docgen"), label="규칙셋", scale=2)
                scene = gr.Dropdown([("영상 없음 — 신호로만 판정", "")], value="", label="영상 장면", scale=3)
                start = gr.Textbox(value=cfg.get("start", "07:55"), label="시작 시각", scale=1, min_width=90)
                speed = gr.Radio([1, 10, 60], value=cfg.get("speed", 10), label="속도 (배)", scale=2)
            with gr.Row():
                b_new = gr.Button("새 세션 시작", variant="primary", scale=1)
                b_play = gr.Button("▶ 시작", scale=1)
                follow = gr.Checkbox(value=True, label="경보 구역 따라가기", scale=1)
            ctl_md = gr.Markdown()
        alarm = gr.HTML()
        zone_r = gr.Radio([], label="구역 (🔴 최고 경보 · 🟠 경보 · 🟡 주의 · ⚪ 무음으로 판정 중 · 🟢 정상)", elem_classes="ctl-btns")
        with gr.Accordion("구역 전체 보기", open=False):
            tiles = gr.HTML()
        with gr.Row(equal_height=False):
            with gr.Column(scale=3):
                cam = gr.HTML()
                zlog = gr.HTML()
                go_log = gr.Button("이벤트 로그 전체 →", size="sm")
            with gr.Column(scale=2):
                axes = gr.HTML()
                ptw_h = gr.HTML()
        gr.HTML(sec("다음 처리", "관제 → 문서 자동화 · 넘기는 것만으로 문서가 발행되지는 않는다"))
        nxt = gr.HTML()
        with gr.Row():
            b_send = gr.Button("문서 자동화로 넘기기 — 이 세션 기록", variant="primary")
            b_co = gr.Button("시정지시서 초안으로 →", size="sm")
            b_ra = gr.Button("위험성평가로 →", size="sm")
        with gr.Accordion("현장 입력 — 버튼 · 신호 (누른 순간의 시연 시계로 들어간다)", open=False):
            btns = {}
            keys = [k for k in pkg.buttons if not k.startswith("_")]
            for i in range(0, len(keys), 4):
                with gr.Row():
                    for k in keys[i:i + 4]:
                        btns[k] = gr.Button(f"{k} · {pkg.buttons[k].get('label', pkg.buttons[k]['signal'])}", size="sm")
            sig_names = [k for k in pkg.signals if not k.startswith("_")]
            with gr.Row():
                s_sig = gr.Dropdown([(f"{k} · {pkg.signals[k].get('label', '')}", k) for k in sig_names], label="신호", scale=3)
                s_zone = gr.Dropdown(zones(), value=focus, label="구역", scale=1)
                s_tgt = gr.Textbox(label="대상 (배관 등)", scale=1)
                s_val = gr.Textbox(label="값", scale=1)
                s_note = gr.Textbox(label="메모", scale=2)
                b_sig = gr.Button("넣기", scale=1)
            in_md = gr.Markdown()
        with gr.Accordion("엔진 메모 — 신호가 무엇을 바꿨나", open=False):
            notes = gr.HTML()
        sel_zone, last_key = gr.State(None), gr.State(None)
        hid_live, co_live = gr.State(None), gr.State(None)
        timer = gr.Timer(1.0, active=True)

    live_out = [status, alarm, zone_r, tiles, cam, zlog, axes, ptw_h, nxt, notes, sel_zone, last_key, b_play]
    timer.tick(live_view, inputs=[sel_zone, follow, last_key], outputs=live_out, show_progress="hidden")
    ctx.on_show("live", live_view, inputs=[sel_zone, follow, last_key], outputs=live_out)
    ctx.on_show("live", scene_choices, inputs=sched, outputs=scene)
    zone_r.input(pick_zone, inputs=zone_r, outputs=[sel_zone, follow]).then(
        live_view, inputs=[sel_zone, follow, last_key], outputs=live_out)
    sched.change(scene_choices, inputs=sched, outputs=scene)
    speed.change(set_speed, inputs=speed)
    b_new.click(new_session, inputs=[sched, ruleset, scene, start, speed], outputs=ctl_md).then(
        live_view, inputs=[sel_zone, follow, last_key], outputs=live_out)
    b_play.click(toggle_play, inputs=[sched, ruleset, scene, start, speed], outputs=ctl_md).then(live_view, inputs=[sel_zone, follow, last_key], outputs=live_out)
    for k, b in btns.items():
        b.click(press, inputs=gr.State(k), outputs=in_md).then(
            live_view, inputs=[sel_zone, follow, last_key], outputs=live_out)
    b_sig.click(put_signal, inputs=[s_sig, s_zone, s_tgt, s_val, s_note], outputs=in_md).then(
        live_view, inputs=[sel_zone, follow, last_key], outputs=live_out)
    ctx.link(go_log, "log")
    refs["live"] = (b_send, hid_live, b_co, co_live, b_ra)

    # ---------------------------------------------------------- 격리 목록 대조
    with ctx.page("iso"):
        gr.Markdown("작업허가서에 붙은 격리 목록을 배관 계통도와 맞춘다. 목록에 없는 연결이 있으면 작업 시작 전에 막는다(R1). "
                    "맹판 설치와 퍼지 · 측정은 배관마다 단계 입력으로 받는다(R2 · R4). "
                    "**작업허가서 · 격리 목록은 여기서만 받는다** — 문서 자동화의 작업허가서 점검도 같은 것을 읽는다.")
        with gr.Row():
            i_filter = gr.Radio(list(ISO_FILTER), value="전체", label="허가서", scale=1)
            i_dd = gr.Dropdown([], label="작업허가서", scale=4)
        i_info = gr.Markdown()
        i_kpi = gr.HTML()
        with gr.Row(equal_height=False):
            i_dg = gr.HTML()
            i_list = gr.HTML()
        with gr.Row(equal_height=False):
            with gr.Column():
                i_bl = gr.HTML()
                with gr.Row():
                    i_bl_line = gr.Dropdown([], label="맹판 설치할 배관", scale=2)
                    b_bl = gr.Button("맹판 설치 완료 입력", scale=1)
            with gr.Column():
                i_ms = gr.HTML()
                with gr.Row():
                    i_ms_line = gr.Dropdown([], label="측정 지점", scale=2)
                    i_lel = gr.Number(value=0, label="LEL %", scale=1, minimum=0)
                    b_gas = gr.Button("가스 측정 입력", scale=1)
                with gr.Row():
                    i_purge = gr.Number(value=30, label="퍼지 시간 (분)", scale=1, minimum=0)
                    b_purge = gr.Button("퍼지 완료 입력", scale=1)
        with gr.Row():
            i_by = gr.Textbox(label="입력자 (단계 입력 기록에 남는다)", scale=2)
            go_ptw = gr.Button("문서 자동화 › 작업허가서 점검으로 →", size="sm", scale=1)
        i_md = gr.Markdown()
        with gr.Accordion("+ 작업허가서 등록 — 입력 창구", open=False):
            with gr.Row():
                piped = [z for z in zones() if isolation.piping().get(z, {}).get("lines")]
                z0 = focus if focus in piped else (piped[0] if piped else focus)
                r_zone = gr.Dropdown(piped + [z for z in zones() if z not in piped], value=z0,
                                     label="구역 (계통도가 있는 구역이 먼저)", scale=1)
                wts = [k for k in load_config()["work_types"] if not k.startswith("_")]
                r_wt = gr.Dropdown(wts, value=wts[0] if wts else None, label="작업 종류 (→ 작업 모드 신호)", scale=2)
                r_start = gr.Textbox(label="시작 (2026-10-12T13:00)", scale=1)
                r_end = gr.Textbox(label="종료", scale=1)
            with gr.Row():
                r_work = gr.Textbox(label="작업 내용", scale=3)
                r_sup = gr.Textbox(label="작업책임자", scale=1)
                r_n = gr.Number(label="인원", precision=0, scale=1)
            with gr.Row(equal_height=False):
                with gr.Column(scale=3):
                    r_csv = gr.Textbox(label="격리 목록 CSV (line_id,배관,격리방법,맹판설치,벤트,가스측정)", lines=6)
                    with gr.Row():
                        r_file = gr.File(label="CSV 파일로 올리기", file_types=[".csv"], type="filepath")
                        r_nolist = gr.Checkbox(value=False, label="목록 없이 등록 (게이트가 걸린다)")
                with gr.Column(scale=2):
                    r_prev = gr.HTML()
            with gr.Row():
                b_rs = gr.Button("예시 채우기", size="sm")
                b_rc = gr.Button("미리 대조")
                b_rsave = gr.Button("등록", variant="primary")
            r_md = gr.Markdown()
        new_ptw = gr.State(None)

    iso_out = [i_info, i_kpi, i_dg, i_list, i_bl, i_ms, i_bl_line, i_ms_line]
    ctx.on_show("iso", lambda f, c: iso_choices(ISO_FILTER[f], c), inputs=[i_filter, i_dd], outputs=i_dd)
    ctx.on_show("iso", iso_show, inputs=i_dd, outputs=iso_out)
    i_filter.change(lambda f, c: iso_choices(ISO_FILTER[f], c), inputs=[i_filter, i_dd], outputs=i_dd)
    i_dd.change(iso_show, inputs=i_dd, outputs=iso_out)
    for b, kind, line, val in ((b_bl, "blind", i_bl_line, None), (b_gas, "gas", i_ms_line, i_lel),
                               (b_purge, "purge", None, i_purge)):
        ins = [gr.State(kind), i_dd, line if line is not None else gr.State(None),
               val if val is not None else gr.State(None), i_by]
        b.click(iso_step, inputs=ins, outputs=i_md).then(iso_show, inputs=i_dd, outputs=iso_out)
    b_rs.click(reg_sample, inputs=r_zone, outputs=[r_wt, r_start, r_end, r_work, r_sup, r_n, r_csv, r_nolist]).then(
        reg_check, inputs=[r_zone, r_csv, r_nolist], outputs=r_prev)
    r_file.upload(read_csv_file, inputs=r_file, outputs=r_csv)
    b_rc.click(reg_check, inputs=[r_zone, r_csv, r_nolist], outputs=r_prev)
    b_rsave.click(reg_save, inputs=[r_zone, r_wt, r_start, r_end, r_work, r_sup, r_n, r_csv, r_nolist],
                  outputs=[r_md, new_ptw]).then(
        lambda p: iso_choices("all", p), inputs=new_ptw, outputs=i_dd).then(
        lambda: "전체", outputs=i_filter).then(iso_show, inputs=i_dd, outputs=iso_out)
    refs["iso"] = (go_ptw, i_dd)

    # ---------------------------------------------------------- 이벤트 로그
    with ctx.page("log"):
        with gr.Row():
            f_mode = gr.Dropdown(["전체"], value="전체", label="작업 모드", scale=2)
            f_alert = gr.Radio(list(ALERT_F), value="전체", label="경보 / 무음 기록", scale=2)
            f_zone = gr.Dropdown(["전체"], value="전체", label="구역", scale=1)
            f_period = gr.Dropdown(list(PERIODS), value="최근 14일", label="기간", scale=1)
            f_kind = gr.Dropdown(["감지만", "게이트 · 사고 포함"], value="게이트 · 사고 포함", label="종류", scale=1)
            f_src = gr.Dropdown(["전체", "샘플", "실시간 세션"], value="전체", label="출처", scale=1)
        with gr.Row():
            b_apply = gr.Button("새로 읽기", size="sm")
            b_reset = gr.Button("초기화", size="sm")
            b_vis = gr.Button("보이는 경보 이상 · 게이트 · 사고를 문서 자동화로 넘기기", size="sm", variant="primary")
        with gr.Row(equal_height=False):
            with gr.Column(scale=7):
                l_head = gr.HTML()
                l_df = gr.Dataframe(interactive=False, wrap=True, max_height=640,
                                    column_widths=["19%", "13%", "7%", "17%", "19%", "11%", "14%"])
            with gr.Column(scale=4):
                l_det = gr.HTML(V.event_detail(None))
                with gr.Row():
                    fp_by = gr.Textbox(label="표시자", scale=1)
                    fp_why = gr.Textbox(label="오탐 사유", scale=2)
                with gr.Row():
                    b_fp = gr.Button("오탐 표시", size="sm")
                    b_unfp = gr.Button("오탐 취소", size="sm")
                with gr.Row():
                    b_one = gr.Button("이 이벤트 넘기기 →", size="sm", variant="primary")
                    b_lco = gr.Button("시정지시서 초안으로 →", size="sm")
                l_md = gr.Markdown()
        l_ids, l_sel = gr.State([]), gr.State(None)
        hid_log, co_log = gr.State(None), gr.State(None)

    filt = [f_mode, f_alert, f_zone, f_period, f_kind, f_src]
    ctx.on_show("log", log_filters, outputs=[f_mode, f_zone])
    ctx.on_show("log", log_view, inputs=filt, outputs=[l_head, l_df, l_ids])
    ctx.on_show("log", log_detail, inputs=l_sel, outputs=l_det)
    for c in filt:
        c.input(log_view, inputs=filt, outputs=[l_head, l_df, l_ids])
    b_apply.click(log_filters, outputs=[f_mode, f_zone]).then(log_view, inputs=filt, outputs=[l_head, l_df, l_ids])
    b_reset.click(lambda: ("전체", "전체", "전체", "최근 14일", "게이트 · 사고 포함", "전체"), outputs=filt).then(
        log_view, inputs=filt, outputs=[l_head, l_df, l_ids])
    l_df.select(log_select, inputs=l_ids, outputs=[l_sel, l_det])
    b_fp.click(mark_fp, inputs=[l_sel, fp_by, fp_why, gr.State(False)], outputs=l_md).then(
        log_detail, inputs=l_sel, outputs=l_det).then(log_view, inputs=filt, outputs=[l_head, l_df, l_ids])
    b_unfp.click(mark_fp, inputs=[l_sel, fp_by, fp_why, gr.State(True)], outputs=l_md).then(
        log_detail, inputs=l_sel, outputs=l_det).then(log_view, inputs=filt, outputs=[l_head, l_df, l_ids])
    refs["log"] = (b_one, b_vis, b_lco, l_sel, filt, hid_log, co_log)

    # ---------------------------------------------------------- 재생 비교
    with ctx.page("replay"):
        gr.Markdown("시나리오는 **시스템이 제대로 도는지 확인하는 도구**다. 타임라인 CSV 를 규칙셋에 넣어 돌리고, 결과를 시나리오에 "
                    "적어 둔 기대 결과와 맞춰 본다. 규칙셋을 바꿨을 때 앞뒤를 나란히 본다. 재생 결과는 관제 기록(이벤트 로그 · "
                    "통계 · 피드백)에 넣지 않는다.")
        with gr.Row(equal_height=False):
            with gr.Column(scale=1, min_width=240):
                sc_r = gr.Radio([], label="시나리오")
                b_all = gr.Button("전체 다시 돌리기", size="sm")
                with gr.Accordion("+ 불러오기 (zip)", open=False):
                    sc_zip = gr.File(label="시나리오 폴더 zip", file_types=[".zip"], type="filepath")
                    b_imp = gr.Button("불러오기", size="sm")
                sc_md = gr.Markdown()
            with gr.Column(scale=4):
                sc_head = gr.Markdown()
                sc_vs = gr.HTML()
                with gr.Row():
                    b_playr = gr.Button("▶ 재생", scale=1)
                    sc_speed = gr.Radio([1, 10, 60], value=60, label="재생 속도 (배)", scale=2)
                    sc_t = gr.Textbox(label="커서", interactive=False, scale=1, min_width=80)
                sc_slider = gr.Slider(0, 1, value=0, step=1, label="시각 (분) — 끌어서 옮긴다", show_label=True)
                sc_cur = gr.HTML()
                sc_tl = gr.HTML()
                gr.HTML(sec("기대 결과 대조", "scenario.json · expect"))
                sc_exp = gr.HTML()
                with gr.Row():
                    sc_var = gr.Dropdown([], label="이 규칙셋 결과를", scale=2)
                    b_sc_send = gr.Button("문서 자동화로 넘기기 (조사표 초안 시험 등)", scale=2)
        sc_timer = gr.Timer(0.5, active=False)
        sc_playing, hid_sc = gr.State(False), gr.State(None)

    ctx.on_show("replay", lambda k: sc_choices(k), inputs=sc_r, outputs=sc_r)
    ctx.on_show("replay", sc_show, inputs=sc_r, outputs=[sc_head, sc_vs, sc_slider, sc_cur, sc_tl, sc_exp, sc_var])
    sc_r.input(sc_show, inputs=sc_r, outputs=[sc_head, sc_vs, sc_slider, sc_cur, sc_tl, sc_exp, sc_var])
    sc_slider.change(sc_cursor, inputs=[sc_r, sc_slider], outputs=[sc_cur, sc_tl, sc_t], show_progress="hidden")
    sc_timer.tick(sc_tick, inputs=[sc_r, sc_slider, sc_speed, sc_playing], outputs=[sc_slider, sc_timer, sc_playing, b_playr],
                  show_progress="hidden")
    b_playr.click(sc_play, inputs=[sc_r, sc_slider, sc_playing], outputs=[sc_timer, sc_playing, b_playr, sc_slider])
    b_all.click(lambda k: sc_choices(k, force=True), inputs=sc_r, outputs=sc_r).then(
        sc_show, inputs=sc_r, outputs=[sc_head, sc_vs, sc_slider, sc_cur, sc_tl, sc_exp, sc_var]).then(
        lambda: "전체 다시 돌렸다 — control/records/replay/", outputs=sc_md)
    b_imp.click(sc_import, inputs=sc_zip, outputs=[sc_r, sc_md]).then(
        lambda k: sc_choices(k), inputs=sc_r, outputs=sc_r).then(
        sc_show, inputs=sc_r, outputs=[sc_head, sc_vs, sc_slider, sc_cur, sc_tl, sc_exp, sc_var])
    refs["replay"] = (b_sc_send, sc_r, sc_var, hid_sc)

    # ---------------------------------------------------------- 피드백 · 조정 로그
    with ctx.page("feedback"):
        gr.Markdown("자동으로 바꾸는 것은 **감시 강도를 기한부로 올리는 것뿐**이다(알림 단계 · 꺼져 있던 구역 규칙 임시 활성화 · 관리자 알림). "
                    "규칙 내용(PPE · 인원 · 폴리곤 · 모든 완화)은 위험성평가를 사람이 확정해야 반영된다.")
        fb_k = gr.HTML()
        with gr.Row():
            fb_mode = gr.Radio(["자동", "승인형"], label="피드백 방식", scale=1)
            fb_actor = gr.Textbox(label="처리자", scale=1)
            fb_note = gr.Textbox(label="사유 (되돌리기 · 거부 · 방식 전환은 필수)", scale=3)
            b_mode = gr.Button("방식 바꾸기", size="sm", scale=1)
        with gr.Row(equal_height=False):
            with gr.Column():
                fb_adj = gr.HTML()
                fb_dd = gr.Dropdown([], label="조정")
                with gr.Row():
                    b_rev = gr.Button("되돌리기 (사유 필수)", size="sm")
                    b_apr = gr.Button("승인", size="sm")
                    b_rej = gr.Button("거부 (사유 필수)", size="sm")
                    b_prm = gr.Button("개정 제안으로 승격", size="sm")
                b_eval = gr.Button("이탈 조건 지금 보기", size="sm")
                fb_md = gr.Markdown()
            with gr.Column():
                gr.HTML(sec("승인 대기 · 긴 루프", "규칙셋 변경안 — 위험성평가 확정으로만 반영"))
                rc_dd = gr.Dropdown([], label="변경안")
                rc_h = gr.HTML()
                b_fb_ra = gr.Button("위험성평가에서 확정 →", size="sm", variant="primary")
                fb_prop = gr.HTML()
        with gr.Row(equal_height=False):
            fb_bars = gr.HTML()
            fb_crit = gr.HTML()
        fb_log = gr.HTML()

    fb_out = [fb_k, fb_mode, fb_adj, fb_dd, rc_dd, rc_h, fb_prop, fb_bars, fb_crit, fb_log]
    ctx.on_show("feedback", fb_view, inputs=rc_dd, outputs=fb_out)
    rc_dd.input(rc_show, inputs=rc_dd, outputs=rc_h)
    b_mode.click(fb_set_mode, inputs=[fb_mode, fb_actor, fb_note], outputs=fb_md).then(fb_view, inputs=rc_dd, outputs=fb_out)
    for b, act in ((b_rev, "revert"), (b_apr, "approve"), (b_rej, "reject"), (b_prm, "promote")):
        b.click(fb_act, inputs=[gr.State(act), fb_dd, fb_actor, fb_note], outputs=fb_md).then(
            fb_view, inputs=rc_dd, outputs=fb_out)
    b_eval.click(fb_eval, outputs=fb_md).then(fb_view, inputs=rc_dd, outputs=fb_out)
    refs["feedback"] = b_fb_ra

    # ---------------------------------------------------------- 히트맵 · 통계
    with ctx.page("stats"):
        gr.Markdown("구역 · 부서 단위 통계다. **개인을 평가하지 않는다.** 무음 기록도 세어서, 모드가 꺼진 구간에 무엇이 일어났는지 같이 본다.")
        st_f = gr.Radio(list(HEAT_F), value="전체", label="히트맵")
        st_heat = gr.HTML()
        with gr.Row(equal_height=False):
            st_rate = gr.HTML()
            st_helm = gr.HTML()
    ctx.on_show("stats", stats_view, inputs=st_f, outputs=[st_heat, st_rate, st_helm])
    st_f.change(stats_view, inputs=st_f, outputs=[st_heat, st_rate, st_helm])

    # ---------------------------------------------------------- 문서 자동화와 잇기 (모든 화면을 만든 뒤)
    def wire(c):
        open_handoff = c.refs.get("docgen.open_handoff")
        open_tab = c.refs.get("docgen.open_tab")
        # 화면을 떠나면 실시간 관제의 1초 갱신과 재생을 멈춘다
        for pid in c.columns:
            if pid != "live":
                c.on_show(pid, lambda: gr.Timer(active=False), outputs=timer)
            if pid != "replay":
                c.on_show(pid, lambda: (gr.Timer(active=False), False, gr.update(value="▶ 재생")),
                          outputs=[sc_timer, sc_playing, b_playr])
        c.on_show("live", lambda: gr.Timer(active=True), outputs=timer)
        if not (open_handoff and open_tab):
            return                          # 문서 자동화 묶음 없이 관제만 띄웠을 때
        b_send_, hid_live_, b_co_, co_live_, b_ra_ = refs["live"]
        open_handoff(b_send_.click(handoff_session, outputs=hid_live_), hid_live_)
        open_tab(b_co_.click(last_alert_event, outputs=co_live_), "co", co_live_)
        open_tab(b_ra_.click(lambda: None), "ra")
        go_ptw_, i_dd_ = refs["iso"]
        open_tab(go_ptw_.click(lambda: None), "ptw", i_dd_)
        b_one_, b_vis_, b_lco_, l_sel_, filt_, hid_log_, co_log_ = refs["log"]
        open_handoff(b_one_.click(handoff_one, inputs=l_sel_, outputs=hid_log_), hid_log_)
        open_handoff(b_vis_.click(handoff_visible, inputs=filt_, outputs=hid_log_), hid_log_)
        open_tab(b_lco_.click(co_event, inputs=l_sel_, outputs=co_log_), "co", co_log_)
        b_sc_send_, sc_r_, sc_var_, hid_sc_ = refs["replay"]
        open_handoff(b_sc_send_.click(sc_handoff, inputs=[sc_r_, sc_var_], outputs=hid_sc_), hid_sc_)
        open_tab(refs["feedback"].click(lambda: None), "ra")

    ctx.after(wire)


def badges() -> dict:
    """메뉴 옆 숫자 — 실시간 관제: 경보가 울리는 구역 · 격리 목록 대조: 문제 있는 허가서 · 피드백: 걸려 있는 조정."""
    s = SESSION.snapshot()
    now = system_now()
    return {"live": sum(1 for st in s["zones"].values() if st["alerting"] and st["level"] != "정상"),
            "iso": sum(1 for p in isolation.ptws() if isolation.view(p)["kind"] in ("crit", "warn")),
            "feedback": len(feedback.active(now)) + len(feedback.pending())}


def control_section() -> Section:
    """틀(shell.sidebar_app)에 넣을 '관제' 메뉴 묶음."""
    return Section("관제", PAGES, build, subtitle=subtitle, badges=badges)
