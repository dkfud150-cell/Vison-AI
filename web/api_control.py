"""
관제 여섯 화면의 데이터 — 실시간 관제 · 격리 목록 대조 · 이벤트 로그 · 재생 비교 · 피드백 · 히트맵 · 통계.

화면(web/static)은 시안 그대로의 HTML 이고, 여기 있는 함수가 control/ 의 기능을 불러 JSON 으로 돌려준다.
판단은 전부 control/ · monitor_engine/ 에 있다 — 여기는 모양만 바꾼다.
"""
from __future__ import annotations

import shutil
import tempfile
import time
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, Response

from control import eventlog, feedback, isolation, replay, scenes, stats
from control.common import (DOCGEN_DIR, dashboard, frame_file, load_config, load_control_events,
                            package, ruleset_status, system_now, zone_name, zones)
from control.session import RULESETS, SESSION

router = APIRouter(prefix="/api")

KIND_T = {"gate": "작업 전 게이트", "accident": "사고", "info": "참고", "stage": "3축 판정", "check": "모드 규칙(영상)"}


def hm(t) -> str:
    return f"{t:%H:%M}" if t else ""


def _cams() -> list[dict]:
    return list(package().cameras.values())


def _cam_polys(cam: dict, scene: dict | None) -> list[dict]:
    """카메라 자리 그림의 구역 — 지금 세션의 영상 장면에 그린 구역이 있고 같은 카메라면 그것, 아니면 카메라 기본 구역."""
    polys = scene["polygons"] if scene and scene.get("polygons") and scene.get("camera") == cam["camera_id"] else cam.get("polygons", [])
    return [{"label": p.get("label") or p.get("name"), "type": p.get("type"), "points": p.get("points")}
            for p in polys if p.get("space", "image") == "image"]


# ====================================================================== 공통 — 메뉴 · 머리글
@router.get("/meta")
def meta():
    """화면을 처음 열 때 한 번 — 구역 · 카메라 · 스케줄 · 규칙셋 · 버튼 · 작업 종류 · 담당자."""
    from safety_docs.config import load_profile, load_staff, staff_label, use_sample_data
    from safety_docs.voice import KINDS, STATES
    from safety_docs.compliance import load_obligations
    pkg = package()
    cfg = load_config()
    demo = dashboard().get("demo", {})
    pip = isolation.piping()
    keys = pkg.scenario_keys()
    sched0 = demo.get("schedule") if demo.get("schedule") in keys else ""
    focus = demo.get("focus_zone") if demo.get("focus_zone") in zones() else (zones()[0] if zones() else None)
    prof = load_profile()
    return {
        "package": pkg.root.name, "site_name": prof.get("site_name", ""), "sample": use_sample_data(),
        "zones": [{"id": z, "name": zone_name(z), "cams": [c["camera_id"] for c in _cams() if c.get("zone") == z],
                   "piping": bool(pip.get(z, {}).get("lines")), "equip": pip.get(z, {}).get("equipment") or "",
                   "lines": [x["line_id"] for x in pip.get(z, {}).get("lines", [])]} for z in zones()],
        "cams_total": len(pkg.cameras),
        "zone_types": [{"key": k, "label": v["label"], "color": v["color"], "builtin": v["builtin"]} for k, v in scenes.all_types().items()],
        "schedules": [{"key": k, "title": pkg.scenario(k).title,
                       "scenes": [{"name": x["name"], "at": x.get("at"), "camera": x.get("camera"), "own": bool(x.get("polygons"))}
                                  for x in pkg.scenario(k).scenes() if x.get("at")]} for k in keys],
        "rulesets": [{"key": k, "label": v} for k, v in RULESETS.items()] + [{"key": i, "label": f"{i}만"} for i in pkg.change_ids()],
        "buttons": [{"key": k, "label": b.get("label", b["signal"]), "zone": b.get("zone")}
                    for k, b in pkg.buttons.items() if not k.startswith("_")],
        "signals": [{"key": k, "label": v.get("label", "")} for k, v in pkg.signals.items() if not k.startswith("_")],
        "work_types": [k for k in cfg["work_types"] if not k.startswith("_")],
        "live": {"schedule": sched0, "scene": (demo.get("scene") or "") if sched0 else "",
                 "ruleset": cfg["live"].get("ruleset", "docgen"), "start": cfg["live"].get("start", "07:55"),
                 "speed": cfg["live"].get("speed", 10)},
        "focus_zone": focus,
        "staff": [{"id": p["id"], "label": staff_label(p), "name": p["name"]} for p in load_staff()],
        "voice": {"kinds": KINDS, "states": STATES},
        "profile": {"industry": prof.get("industry", ""), "workers": prof.get("workers", 0),
                    "hazardous": bool(prof.get("hazardous_agents"))},
        "industries": ["1차 금속 제조업", "기타 제조업"],
        "duty_cats": load_obligations()["categories"],
    }


_badge = {"t": 0.0, "v": {}}


def badges() -> dict:
    """메뉴 옆 숫자 — 3초에 한 번만 센다."""
    if time.time() - _badge["t"] < 3:
        return _badge["v"]
    from safety_docs.assessment import list_assessments
    from safety_docs.config import load_events, load_profile, load_scales
    from safety_docs.corrective import list_correctives
    from safety_docs.handoff import list_handoffs
    from safety_docs.home import home_summary
    from safety_docs.voice import list_reports, voice_summary
    s = SESSION.snapshot()
    now = system_now()
    evs, as_of = load_events()
    prof = load_profile()
    from control.common import demo_day
    h = home_summary(evs, as_of, load_scales(), prof, demo_day())
    issued = {c["event_id"] for c in list_correctives()}
    by_id = {e["event_id"]: e for e in evs}
    todo = set()
    for ho in list_handoffs(include_auto=False):
        for i in ho.get("event_ids", []):
            e = by_id.get(i)
            if e and e.get("alerted") and e.get("level") in ("경보", "최고 경보") and i not in issued:
                todo.add(i)
    v = {"live": sum(1 for st in s["zones"].values() if st["alerting"] and st["level"] != "정상"),
         "iso": sum(1 for p in isolation.ptws() if isolation.view(p)["kind"] in ("crit", "warn")),
         "feedback": len(feedback.active(now)) + len(feedback.pending()),
         "home": h["cards"][0]["num"],
         "docs": len(todo),
         "voice": voice_summary(list_reports())["open"] + sum(1 for ra in list_assessments() if ra["state"] == "worker_pending")}
    _badge.update(t=time.time(), v=v)
    return v


@router.get("/status")
def status():
    """머리글 · 메뉴 숫자 · 경보 팝업 — 화면이 2초마다 읽는다."""
    from safety_docs.config import llm_provider
    s = SESSION.snapshot()
    rs = ruleset_status()
    on = [(z, st["modes"]) for z, st in s["zones"].items() if st["modes"]]
    alarms = []
    for z, st in s["zones"].items():
        if st["alerting"] and st["level"] != "정상":
            alarms.append({"key": f"{z}|{st['level']}|{st['since']:%H%M%S}" if st.get("since") else f"{z}|{st['level']}",
                           "zone": z, "name": zone_name(z), "level": st["level"], "row": st.get("row"),
                           "since": hm(st.get("since")), "reason": st.get("reason") or st.get("violation") or "",
                           "response": st.get("response") or "", "adj": s["adjust"].get(z, {}).get("adj_ids", [])})
    order = {"최고 경보": 3, "경보": 2, "주의": 1}
    alarms.sort(key=lambda a: -order.get(a["level"], 0))
    incidents = [{"key": r["event_id"], "id": r["event_id"], "kind": r["kind"], "zone": r.get("zone"),
                  "name": zone_name(r.get("zone")), "t": r["ts"][11:16], "reason": r.get("reason") or r.get("violation_type") or ""}
                 for r in s["rows"] if r.get("kind") in ("gate", "accident")]
    return {"now": s["now"].isoformat(timespec="seconds"), "sid": s["sid"], "running": s["running"], "speed": s["speed"],
            "modes_on": sum(len(x) for _, x in on), "zones_on": len(on),
            "ruleset": {"version": rs["version"], "ids": rs["ids"]}, "feedback_mode": feedback.mode(),
            "llm": _provider["v"] or llm_provider(),
            "video": bool(s.get("video")), "scene": (s.get("scene") or {}).get("name") or "",   # 머리줄 '영상' 칩
            "badges": badges(), "alarms": alarms, "incidents": incidents}


_provider = {"v": None}


def provider() -> str:
    from safety_docs.config import llm_provider
    return _provider["v"] or llm_provider()


@router.post("/llm")
def set_llm(body: dict):
    from safety_docs.llm import LLMClient
    p = str(body.get("provider", "mock")).lower()
    LLMClient(p)                         # 키가 없으면 여기서 알려 준다
    _provider["v"] = p
    return {"llm": p}


# ====================================================================== 1. 실시간 관제
def _axes(st: dict) -> list[dict]:
    out = []
    for name, a in (st.get("axes") or {}).items():
        out.append({"name": name, "state": a.state, "tone": a.tone, "why": list(dict.fromkeys(a.why)),
                    "why_not": list(a.why_not[:2])})
    return out


def _judge(st: dict) -> list[dict]:
    t = st.get("tdef")
    if not t:
        return []
    hit = st.get("row") if st.get("computed") != "정상" else None
    vio = st.get("violation")
    rows = []
    for r in t.get("rows", []) + [t.get("default", {})]:
        n = r.get("row")
        # 같은 번호의 줄이 둘 이상이면(예: 7번 '축적 단독' · '허가 · 측정이 끝난 점화원') 위반 이름까지 맞는 줄만 칠한다
        same_n = n is not None and n == hit
        rows.append({"n": n, "label": r.get("label") or r.get("violation") or "그 외", "level": r.get("level", "정상"),
                     "violation": r.get("violation") or "",
                     "hit": same_n and (not vio or not r.get("violation") or r.get("violation") == vio)})
    return rows


def _ptw_cards(zone: str) -> list[dict]:
    out = []
    for p in sorted((p for p in isolation.ptws() if p["zone"] == zone), key=lambda x: x.get("start", ""), reverse=True)[:3]:
        v = isolation.view(p)
        out.append({"id": p["ptw_id"], "work": p["work"], "type": p.get("type", ""), "kind": v["kind"], "tag": v["tag"],
                    "clear": v["clear"], "when": f"{p.get('start', '')[5:16].replace('T', ' ')} ~ {p.get('end', '')[11:16]}"})
    return out


def _ev_row(e: dict) -> dict:
    return {"id": e["event_id"], "ts": e["ts"], "date": e["ts"][:10], "time": e["ts"][11:16], "zone": e.get("zone") or "",
            "mode": e.get("mode") or "-", "type": e.get("violation_type") or (e.get("reason") or "")[:30],
            "level": e.get("computed_level") or e.get("level"), "alerted": bool(e.get("alerted")),
            "kind": e.get("kind", "stage"), "adj": e.get("adj_id"), "fp": bool(e.get("false_positive")),
            "src": e.get("_src", ""), "frame": bool(e.get("frame_path")), "clip": bool(e.get("clip_path"))}


@router.get("/live")
def live():
    from web.api_docs import adhoc_count
    s = SESSION.snapshot()
    now = s["now"]
    m = s["meta"]
    nxt = s["next"]
    zs = []
    for z, st in s["zones"].items():
        cams = [c["camera_id"] for c in _cams() if c.get("zone") == z]
        zs.append({"id": z, "name": zone_name(z), "level": st["level"], "computed": st["computed"],
                   "alerting": st["alerting"], "row": st.get("row"), "since": hm(st.get("since")),
                   "reason": st.get("reason") or "", "violation": st.get("violation") or "", "modes": st["modes"],
                   "people": st["people"], "present": bool(st.get("present")), "response": st.get("response") or "",
                   "table": st.get("table"), "axes": _axes(st), "judge": _judge(st), "cams": cams,
                   "ptws": _ptw_cards(z), "adj": s["adjust"].get(z, {}),
                   "ignition": any((f, z) in s["on"] for f in ("ignition_manual",)),
                   "equip": isolation.piping().get(z, {}).get("equipment") or "",
                   "piping": bool(isolation.piping().get(z, {}).get("lines")),
                   "polys": [q for c in _cams() if c.get("zone") == z for q in _cam_polys(c, s["scene"])]})
    if s["sid"]:
        today = [_ev_row(r) for r in s["rows"]]
        log_src = "이 세션"
    else:
        today = [_ev_row(e) for e in load_control_events() if e["_ts"].date() == now.date()]
        log_src = "오늘 기록"
    rows = s["rows"]
    counts = {"alerts": sum(1 for r in rows if r.get("kind") in ("stage", "check") and r.get("alerted")
                            and r.get("level") in ("경보", "최고 경보")),
              "adhoc": adhoc_count(), "gates": sum(1 for r in rows if r.get("kind") == "gate")}
    scene = s["scene"]
    return {"now": now.isoformat(timespec="seconds"), "sid": s["sid"], "running": s["running"], "speed": s["speed"],
            "video": s["video"], "video_note": s["video_note"],
            "video_pos": [round(x, 1) for x in s["video_pos"]] if s["video_pos"] else None,
            "undo": s["undo"],
            "scene": {"name": scene.get("name"), "at": scene.get("at"), "camera": scene.get("camera"),
                      "zone": next((c.get("zone") for c in _cams() if c["camera_id"] == scene.get("camera")), None),
                      "video": scene.get("video") or "", "started": s["scene_started"],
                      "own": bool(scene.get("polygons"))} if scene else None,
            "meta": {"schedule": m.get("schedule", ""), "schedule_title": m.get("schedule_title", ""),
                     "ruleset": m.get("ruleset", ""), "rules_label": m.get("rules_label", ""),
                     "start": hm(m.get("start")), "scene": m.get("scene", "")},
            "next": {"t": hm(nxt.ts), "text": nxt.note or nxt.short()} if nxt else None,
            "zones": zs, "events": list(reversed(today))[:200], "log_src": log_src,
            "notes": [{"t": f"{t:%H:%M:%S}", "msg": msg} for t, msg in s["notes"][:14]],
            "counts": counts, "frames": sorted(s["frames"])}


@router.get("/live/frame/{cam}")
def live_frame(cam: str):
    b = SESSION.frames.get(cam)
    if not b:
        return Response(status_code=404)
    return Response(b, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/live/session")
def live_session(body: dict):
    SESSION.reset(body.get("schedule") or None, body.get("ruleset") or "docgen", (body.get("start") or "07:55").strip(),
                  body.get("scene") or None, float(body.get("speed") or 10))
    SESSION.start()
    m = SESSION.meta
    return {"msg": f"새 세션 {SESSION.sid} — {m['schedule_title']} · 규칙 {m['rules_label']} · {m['start']:%H:%M} 부터"
                   + (f" · 영상 장면 '{body.get('scene')}'" if body.get("scene") else ""), "sid": SESSION.sid}


# ====================================================================== 영상 장면 — 영상 올리기 · 구역 그리기
@router.get("/scene/options")
def scene_options(schedule: str):
    return scenes.options(schedule)


@router.post("/scene/upload")
async def scene_upload(schedule: str = Form(...), file: UploadFile = File(...)):
    d = scenes.save_upload(schedule, file.filename or "", file.file)
    return {**d, "msg": f"영상을 올렸다 — {d['file']} ({d['w']}×{d['h']}" + (f" · {d['seconds']:g}초" if d.get("seconds") else "") + ")"}


@router.get("/scene/frame")
def scene_frame(video: str, schedule: str = ""):
    jpg, _ = scenes.first_frame(scenes.resolve_video(video, schedule or None))
    return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/scene/info")
def scene_info(video: str, schedule: str = ""):
    _, info = scenes.first_frame(scenes.resolve_video(video, schedule or None))
    return info


@router.post("/scene/save")
def scene_save(body: dict):
    d = scenes.save_scene(body)
    SESSION.refresh_scene(body.get("schedule") or "", d.get("name"), body.get("orig") or None)
    return d


@router.post("/scene/type")
def scene_type(body: dict):
    """구역 종류 더하기 · 고치기 (관리자) — 패키지 zone_types.json"""
    return scenes.save_type(body)


@router.post("/scene/type/remove")
def scene_type_remove(body: dict):
    return scenes.remove_type(body)


@router.post("/scene/camera")
def scene_camera(body: dict):
    """카메라 한 대 더하기 — 패키지 cameras/<id>.json (기본 구역 없이)"""
    return scenes.save_camera(body)


@router.post("/scene/camera/remove")
def scene_camera_remove(body: dict):
    return scenes.remove_camera(body)


@router.post("/scene/remove")
def scene_remove(body: dict):
    d = scenes.remove_scene(body)
    SESSION.refresh_scene(body.get("schedule") or "", None, body.get("name"))
    return d


@router.post("/live/play")
def live_play(body: dict):
    if not SESSION.sid:
        return live_session(body)
    if SESSION.running:
        SESSION.pause()
        return {"msg": "멈췄다 — 시연 시계가 선다. 기록은 그대로다."}
    SESSION.start()
    return {"msg": f"계속 — {SESSION.speed:g}× · 세션 {SESSION.sid}"}


@router.post("/live/scene-now")
def live_scene_now(body: dict):
    """고른 영상 장면을 지금 관제 화면에 튼다. 세션이 없거나 스케줄 · 장면이 다르면 새 세션부터 시작한다."""
    if not body.get("scene"):
        raise ValueError("영상 장면을 고른다 — 시연 제어의 '영상 장면'")
    m = SESSION.meta
    fresh = not SESSION.sid or (m.get("schedule") or "") != (body.get("schedule") or "") or (m.get("scene") or "") != body["scene"]
    if fresh:
        live_session(body)
    msg = SESSION.play_scene_now()
    return {"msg": ("새 세션 " + SESSION.sid + " · " if fresh else "") + msg, "sid": SESSION.sid}


@router.post("/live/speed")
def live_speed(body: dict):
    SESSION.set_speed(float(body.get("speed") or 10))
    return {"speed": SESSION.speed}


@router.post("/live/press")
def live_press(body: dict):
    key = body.get("key")
    b = package().buttons[key]
    notes = SESSION.press(key)
    return {"msg": f"{b.get('label', b['signal'])} 넣음 ({SESSION.clock():%H:%M:%S})", "notes": notes}


@router.post("/live/undo")
def live_undo(body: dict):
    """마지막 현장 입력(버튼 · 입력창) 되돌리기. 관제 기록은 지우지 않는다(추가 전용)."""
    return SESSION.undo_last()


@router.post("/live/signal")
def live_signal(body: dict):
    sig = body.get("signal")
    if not sig:
        raise ValueError("신호를 고른다")
    notes = SESSION.apply_signal(sig, body.get("zone") or None, (body.get("target") or "").strip() or None,
                                 (body.get("value") or "").strip() or None, source="입력창", note=(body.get("note") or "").strip())
    return {"msg": f"{sig} 넣음 ({SESSION.clock():%H:%M:%S})", "notes": notes}


@router.post("/live/stop-order")
def live_stop_order(body: dict):
    """작업중지 지시 — 관제실이 지시한 시각을 기록으로 남긴다 (방송 설비와의 연동은 아직 없다)."""
    zone = body.get("zone")
    ev = SESSION.stop_order(zone)
    return {"msg": f"{zone} 작업중지 지시 기록 — {ev['event_id']} ({ev['ts'][11:19]}). 방송 설비 연동은 아직 없어 현장 전달은 무전 · 전화로 한다."}


@router.post("/live/handoff")
def live_handoff(body: dict):
    ids = body.get("event_ids") or None
    ho = SESSION.handoff(ids)
    return {"handoff_id": ho["handoff_id"], "msg": f"{ho['handoff_id']} — 감지 {len(ho['event_ids'])}건 넘김"}


@router.post("/live/corrective")
def live_corrective():
    """시정지시서 초안으로 — 이 세션의 마지막 경보 이상 기록을 넘기고 번호를 돌려준다."""
    rows = [r for r in (SESSION.log.rows if SESSION.sid and SESSION.log else [])
            if r.get("kind") in ("stage", "check") and r.get("alerted") and r.get("level") in ("경보", "최고 경보")]
    if not rows:
        return {"event_id": None}
    SESSION.handoff([rows[-1]["event_id"]], source="실시간 관제 · 시정지시서")
    return {"event_id": rows[-1]["event_id"]}


# ====================================================================== 2. 격리 목록 대조
_new_ptws: set[str] = set()


def _ptw_row(p: dict) -> dict:
    v = isolation.view(p)
    return {"id": p["ptw_id"], "zone": p["zone"], "zname": zone_name(p["zone"]), "work": p["work"], "type": p.get("type", ""),
            "work_type": p.get("work_type") or p.get("type", ""), "start": p.get("start", ""), "end": p.get("end", ""),
            "kind": v["kind"], "tag": v["tag"], "open": v["open"], "new": p["ptw_id"] in _new_ptws,
            "source": p.get("source", "")}


@router.get("/iso")
def iso_list():
    ps = sorted(isolation.ptws(), key=lambda x: x.get("start", ""), reverse=True)
    ps.sort(key=lambda x: x["ptw_id"] not in _new_ptws)          # 방금 등록한 것이 맨 앞
    return {"ptws": [_ptw_row(p) for p in ps]}


@router.get("/iso/{ptw_id}")
def iso_detail(ptw_id: str):
    p = next((x for x in isolation.ptws() if x["ptw_id"] == ptw_id), None)
    if not p:
        raise KeyError(f"없는 작업허가서: {ptw_id}")
    v = isolation.view(p)
    lines = [{"line_id": ln["line_id"], "name": ln["name"], "fluid": ln.get("fluid", ""), "hazard": bool(ln.get("hazard_source")),
              "in_list": ln["in_list"], "blind": ln["blind"], "by_step": bool(ln.get("blind_by_step")),
              "row": ln.get("row") or {}} for ln in v["check"]["lines"]]
    return {"ptw": {k: p.get(k) for k in ("ptw_id", "type", "zone", "work", "work_type", "start", "end", "supervisor",
                                          "workers", "source")},
            "zname": zone_name(p["zone"]), "equipment": v["check"]["equipment"], "has_pid": v["check"]["has_pid"],
            "lines": lines, "extra": v["check"]["extra"], "no_list": v["no_list"], "miss": len(v["miss"]),
            "pend": [ln["line_id"] for ln in v["pend"]], "meas": v["meas"], "purge_min": v["purge_min"],
            "purge_need": v["purge_need"], "lel_max": v["lel_max"], "kind": v["kind"], "tag": v["tag"], "bar": v["bar"],
            "clear": v["clear"], "open": v["open"],
            "steps": [{"t": s["ts"][11:16], "kind": s["kind"], "line_id": s.get("line_id"), "value": s.get("value"),
                       "by": s.get("by")} for s in v["steps"]]}


@router.post("/iso/check")
def iso_check(body: dict):
    zone, no_list = body.get("zone"), bool(body.get("no_list"))
    rows = None if no_list else isolation.parse_csv(body.get("csv") or "")
    if not no_list and not rows:
        raise ValueError("격리 목록 CSV 를 올리거나 붙여넣는다. 목록이 없으면 ‘목록 없이 등록’을 켠다")
    chk = isolation.cross_check(zone, rows)
    if not chk["has_pid"]:
        raise ValueError(f"{zone} 에는 배관 계통도가 등록돼 있지 않아 대조할 수 없다. 사업장 패키지 site.json 의 piping 에 먼저 넣는다.")
    return {"lines": [{"line_id": x["line_id"], "name": x["name"], "in_list": x["in_list"], "blind": x["blind"]}
                      for x in chk["lines"]], "extra": chk["extra"], "no_list": no_list}


@router.get("/iso-sample")
def iso_sample(zone: str):
    wts = [k for k in load_config()["work_types"] if not k.startswith("_")]
    day = system_now().date().isoformat()
    return {"work_type": wts[0] if wts else "", "start": f"{day}T13:00", "end": f"{day}T17:00",
            "work": f"{zone_name(zone)} 연결 배관 격리 후 정비", "supervisor": "김정비", "workers": 3,
            "csv": isolation.sample_csv(zone)}


@router.post("/iso/register")
def iso_register(body: dict):
    r = isolation.register(body.get("zone"), body.get("work_type"), (body.get("start") or "").strip(),
                           (body.get("end") or "").strip(), body.get("work") or "", body.get("supervisor") or "",
                           body.get("workers") or None, body.get("csv"), bool(body.get("no_list")))
    p, chk = r["ptw"], r["check"]
    _new_ptws.add(p["ptw_id"])
    v = isolation.view(p)
    msg = f"{p['ptw_id']} 등록됨 — 대조 결과: {v['tag']}"
    if chk["extra"]:
        msg += f" · 계통도에 없는 줄 {len(chk['extra'])}건"
    if r["engine_notes"]:
        msg += ". 관제 엔진에 신호로 들어갔고 문서 자동화의 작업허가서 점검에도 넘어갔다."
    elif not SESSION.sid:
        msg += ". 문서 자동화의 작업허가서 점검에 넘어갔다. 실시간 세션이 돌지 않아 엔진에는 넣지 않았다."
    else:
        msg += ". 관제 엔진과 문서 자동화에 같이 넘어갔다."
    return {"ptw_id": p["ptw_id"], "msg": msg}


@router.post("/iso/step")
def iso_step(body: dict):
    p = next((x for x in isolation.ptws() if x["ptw_id"] == body.get("ptw_id")), None)
    if not p:
        raise ValueError("작업허가서를 고른다")
    by = (body.get("by") or "").strip()
    if not by:
        raise ValueError("입력자 이름을 적는다 — 단계 입력 기록에 남는다")
    kind, line, value = body.get("kind"), body.get("line_id"), body.get("value")
    notes = isolation.step(p, kind, line, None if value in (None, "") else str(value), by)
    what = {"blind": f"{line} 맹판 설치 완료", "gas": f"{line} 가스 측정 LEL {value}%", "purge": f"퍼지 {value}분"}[kind]
    tail = (" · 엔진: " + " · ".join(notes)) if notes else ("" if SESSION.sid else " · 세션이 돌지 않아 엔진에는 넣지 않았다 (기록만)")
    return {"msg": f"{p['ptw_id']} {what} 입력 · {by}{tail}"}


# ====================================================================== 3. 이벤트 로그
def _filter(evs, f: dict) -> list[dict]:
    """거르기 · 검색은 control/eventlog.py — '보이는 경보 이상 넘기기'도 같은 조건을 쓴다."""
    return [ev for ev, _ in eventlog.filter_events(evs, f or {})]


@router.post("/log")
def log_rows(body: dict):
    all_ = load_control_events()
    hits = list(reversed(eventlog.filter_events(all_, body)))
    evs = [ev for ev, _ in hits]
    modes = sorted({ev.get("mode") or "-" for ev in all_})
    na = sum(1 for ev in evs if ev.get("alerted") and ev.get("kind", "stage") in ("stage", "check"))
    ns = sum(1 for ev in evs if not ev.get("alerted") and ev.get("kind", "stage") in ("stage", "check"))
    extra = 0
    if str(body.get("period", "14")) != "all" and eventlog.detail_on(body):
        extra = len(eventlog.filter_events(all_, body, ignore_period=True)) - len(evs)
    return {"rows": [{**_ev_row(e), "hit": h} for e, h in hits], "n": len(evs), "alerts": na, "shadow": ns, "modes": modes,
            "extra": max(0, extra), "tokens": eventlog.tokens(body.get("q")), "facets": eventlog.facets(all_)}


def _event(eid: str) -> dict:
    ev = next((x for x in load_control_events() if x["event_id"] == eid), None)
    if not ev:
        raise KeyError(f"없는 이벤트: {eid}")
    return ev


@router.get("/event/{eid}")
def event_detail(eid: str):
    ev = _event(eid)
    clip = _clip_file(ev)
    return {**_ev_row(ev), "zname": zone_name(ev.get("zone")), "reason": ev.get("reason") or "", "row": ev.get("row"),
            "response": ev.get("response") or "", "ruleset": ev.get("ruleset") or "", "kind_t": KIND_T.get(ev.get("kind"), ""),
            "clip_path": ev.get("clip_path") or "", "has_frame": frame_file(ev) is not None, "has_clip": clip is not None,
            "fp_by": ev.get("fp_by", ""), "fp_note": ev.get("fp_note", ""), "ts_full": ev["ts"].replace("T", " "),
            "tag": eventlog.tag_text(ev)}


def _clip_file(ev: dict) -> Path | None:
    cp = ev.get("clip_path")
    if not cp:
        return None
    p = Path(cp)
    if not p.is_absolute():
        p = Path(ev.get("_base") or DOCGEN_DIR) / p
    return p if p.exists() else None


@router.get("/event/{eid}/frame")
def event_frame(eid: str):
    f = frame_file(_event(eid))
    return FileResponse(f) if f else Response(status_code=404)


@router.get("/event/{eid}/clip")
def event_clip(eid: str):
    f = _clip_file(_event(eid))
    return FileResponse(f, media_type="video/mp4") if f else Response(status_code=404)


@router.post("/log/fp")
def log_fp(body: dict):
    from safety_docs.handoff import mark_false_positive
    eid, by = body.get("event_id"), (body.get("by") or "").strip()
    if not eid:
        raise ValueError("표에서 이벤트를 고른다")
    undo = bool(body.get("undo"))
    mark_false_positive(eid, by, body.get("reason") or "", undo=undo)
    return {"msg": f"{eid} 오탐 표시{' 취소' if undo else ''} · {by} — 위험성평가 집계 · 통계에서 "
                   f"{'다시 들어간다' if undo else '빠진다'}. 오탐을 근거로 한 완화는 사람이 승인한다."}


def _for_handoff(evs: list[dict]) -> list[dict]:
    out = []
    for ev in evs:
        r = {k: v for k, v in ev.items() if not k.startswith("_") and k not in ("fp_by",)}
        f = frame_file(ev)
        r["frame_path"] = str(f) if f else None
        c = _clip_file(ev)
        if c:
            r["clip_path"] = str(c)
        out.append(r)
    return out


def handoff_events(eids: list[str], source: str) -> str:
    from safety_docs.handoff import receive
    evs = [x for x in load_control_events() if x["event_id"] in set(eids)]
    if not evs:
        raise ValueError("넘길 이벤트가 없다")
    return receive(_for_handoff(evs), source=source)["handoff_id"]


@router.post("/log/handoff")
def log_handoff(body: dict):
    if body.get("event_ids"):
        hid = handoff_events(body["event_ids"], body.get("source") or "이벤트 로그 · 한 건")
        return {"handoff_id": hid}
    evs = _filter(load_control_events(), body.get("filter") or {})
    evs = [x for x in evs if (x.get("alerted") and x.get("level") in ("경보", "최고 경보")) or x.get("kind") in ("gate", "accident")]
    if not evs:
        raise ValueError("보이는 목록에 경보 이상 · 게이트 · 사고가 없다")
    return {"handoff_id": handoff_events([x["event_id"] for x in evs], "이벤트 로그 · 보이는 경보 이상")}


@router.post("/log/corrective")
def log_corrective(body: dict):
    eid = body.get("event_id")
    ev = _event(eid)
    if not ev.get("alerted") or ev.get("kind", "stage") not in ("stage", "check"):
        raise ValueError("시정지시서는 경보로 울린 감지 기록으로 만든다 (무음 기록 · 게이트 · 사고는 아니다)")
    handoff_events([eid], "이벤트 로그 · 시정지시서")
    return {"event_id": eid}


# ====================================================================== 4. 재생 비교
def _variant(name: str, v: dict) -> dict:
    sm = v["summary"]
    return {"name": name, "changes": v["changes"], "head": sm["head"], "text": sm["text"], "hot": sm["hot"],
            "accident": sm["accident"], "gate": sm["gate"], "ok": sum(1 for c, _ in v["checks"] if c), "n": len(v["checks"])}


@router.get("/replay")
def replay_list(force: int = 0):
    out = []
    for k in replay.scenario_keys():
        res = replay.run(k, bool(force))
        ok, n = replay.score(res)
        out.append({"key": k, "title": res["title"], "zone": res["zone"], "table": res["table"], "ok": ok, "n": n})
    return {"scenarios": out}


@router.get("/replay/{key}")
def replay_detail(key: str):
    res = replay.run(key)
    ok, n = replay.score(res)
    names = list(res["variants"])
    return {"key": key, "title": res["title"], "zone": res["zone"], "zname": zone_name(res["zone"]), "table": res["table"],
            "basis": res["basis"], "ok": ok, "n": n, "times": res["times"],
            "variants": [_variant(k, v) for k, v in res["variants"].items()],
            "rows": [{"t": r["t"], "signals": r["signals"] or "(시간 경과)", "source": r["source"],
                      "cells": [list(r["cells"].get(nm, ("", ""))) for nm in names]} for r in replay.merged_rows(res)],
            "expect": [{"variant": nm, "ok": c, "msg": msg} for nm, v in res["variants"].items() for c, msg in v["checks"]]}


@router.get("/replay/{key}/at")
def replay_at(key: str, t: str):
    res = replay.run(key)
    out = []
    for name in res["variants"]:
        st = replay.state_at(res, name, t)
        out.append({"name": name, "level": st["level"], "row": st.get("row"), "modes": st.get("modes", []),
                    "axes": " · ".join(f"{k} {v}" for k, v in st.get("axes", {}).items())})
    return {"t": t, "states": out}


@router.post("/replay/import")
async def replay_import(file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        path = tmp.name
    try:
        key = replay.import_zip(path)
    finally:
        Path(path).unlink(missing_ok=True)
    return {"key": key, "msg": f"불러옴 — {key} · 사업장 패키지 scenarios/ 에 풀었다"}


@router.post("/replay/{key}/handoff")
def replay_handoff(key: str, body: dict):
    from safety_docs.handoff import receive
    res = replay.run(key)
    name = body.get("variant")
    v = res["variants"].get(name)
    if not v:
        raise ValueError("넘길 규칙셋 결과를 고른다")
    ho = receive(v["run"]["log"].rows, source=f"재생 비교 · {res['title']} · {name}", base_dir=v["out_dir"])
    return {"handoff_id": ho["handoff_id"]}


# ====================================================================== 5. 피드백 · 조정 로그
HIST_T = {"applied": "적용", "pending": "승인 대기로 생성", "rejected": "거부", "expired": "만료", "reverted": "되돌림"}


def _adj_card(a: dict, now) -> dict:
    k, lab = feedback.current_label(a, now)
    ac = a.get("action") or {}
    return {"adj_id": a["adj_id"], "state": a["state"], "state_key": k, "state_label": lab,
            "zone": a["zone"], "zname": zone_name(a["zone"]), "mode": a.get("mode") or "", "violation_type": a.get("violation_type") or "",
            "action": feedback.action_text(a), "reason": feedback.reason_text(a),
            "level_before": ac.get("before"), "level_after": ac.get("after"),
            "zone_rule": bool(ac.get("enable_zone_rule")), "notify": bool(ac.get("notify_manager")),
            "start": (a.get("applied_at") or a["ts"]).replace("T", " "), "expires_at": a["expires_at"],
            "expires": a["expires_at"][5:16].replace("T", " "), "ts": a["ts"][5:16].replace("T", " "),
            "severe": (a.get("reason") or {}).get("type") == "severe", "feedback_mode": a.get("feedback_mode", ""),
            "evidence": a.get("evidence_event_ids") or [],
            "history": [{"ts": (h.get("ts") or "").replace("T", " ")[:16],
                         "state": ("승인 — 적용" if i and h.get("state") == "applied" else HIST_T.get(h.get("state"), h.get("state"))),
                         "actor": h.get("actor") or "system", "note": h.get("note") or ""} for i, h in enumerate(a.get("history", []))],
            "sample": bool(a.get("sample"))}


def _live_rules() -> dict:
    m = SESSION.meta or {}
    return {"sid": SESSION.sid, "applied": m.get("applied") or [], "label": m.get("rules_label", ""), "ruleset": m.get("ruleset", "")}


@router.get("/feedback")
def feedback_view():
    from web.api_docs import _ra
    now = system_now()
    act = feedback.active(now)
    pend = feedback.pending()
    counts = feedback.zone_counts(now)
    rs = ruleset_status()
    cfg = feedback.config()
    sp = cfg["spike"]
    short = [("중대", f"중대성 {cfg['severe']['severity']}등급 1건", "1단 즉시"),
             ("급증", f"{sp['window_h']}시간 ≥ {sp['baseline_days']}일 평균 × {sp['ratio']:g}, 최소 {sp['min_count']}건", "1단"),
             ("신규", "기준선 0건인 조합의 첫 발생", "1단")]
    long_ = [("승격", f"같은 구역 {cfg['promote']['within_days']}일 안에 조정 {cfg['promote']['count']}회", "2단"),
             ("절대 기준", f"주간 {cfg['absolute']['weekly_count']}건 초과 또는 위험도 {cfg['absolute']['risk_score']} 이상", "2단"),
             ("오탐 과다", f"오탐 표시 {cfg['false_positive']['ratio'] * 100:.0f}% 초과 (최소 {cfg['false_positive']['min_count']}건)", "2단 (완화 제안)"),
             ("급감", f"기준선의 {cfg['drop']['ratio'] * 100:.0f}% 이하", "카메라 점검 알림")]
    live = _live_rules()
    rcs = feedback.rule_changes_view(_ra.get("drafts") or [], live)
    long_wait = [r for r in rcs if r["phase"] in ("draft", "worker")]
    last = rs.get("last") or {}
    return {"now": now.isoformat(timespec="seconds"),
            "kpis": {"active": len(act), "active_zones": list(dict.fromkeys(a["zone"] for a in act)), "pending": len(pend),
                     "long_wait": len(long_wait), "long_wait_ids": [r["id"] for r in long_wait],
                     "n14": sum(counts.values()), "trend": feedback.trend(now),
                     "version": rs["version"], "ids": rs["ids"], "last_ts": (last.get("ts") or "").replace("T", " ")[:16],
                     "mode": feedback.mode(), "live_rules": live["label"]},
            "open": [_adj_card(a, now) for a in sorted(act + pend, key=lambda a: a["ts"], reverse=True)],
            "rcs": rcs,
            "proposals": [{**p, "ts": (p.get("ts") or "").replace("T", " ")[:16], "zname": zone_name(p.get("zone"))}
                          for p in feedback.proposals(now)],
            "zone_counts": [{"zone": z, "name": zone_name(z), "n": counts.get(z, 0)} for z in zones() if counts.get(z)],
            "criteria": short + long_, "criteria_short": short, "criteria_long": long_,
            "expire_h": cfg["expire_h"], "promote": cfg["promote"], "max_up": cfg["auto_actions"]["alert_level"]["max_up"],
            "log": feedback.log_rows(now), "zones": [{"id": z, "name": zone_name(z)} for z in zones()]}


@router.post("/feedback/rule")
def feedback_rule(body: dict):
    """긴 루프 — 변경안 하나 반려 · 반려 취소. 기록은 문서 자동화 쪽(rule_rejections.jsonl)에 남아 위험성평가 화면에도 보인다."""
    rid, act = body.get("rule_id") or "", body.get("action")
    actor, role, note = body.get("actor") or "", body.get("role") or "관리자", body.get("note") or ""
    if act == "reject":
        r = feedback.reject_rule_change(rid, actor, role, note)
        msg = f"{rid} 반려 — {r['ra_id']} · {actor} · 사유: {note}. 확정해도 이 변경안은 규칙셋에 올리지 않는다"
    elif act == "restore":
        r = feedback.restore_rule_change(rid, actor, role, note)
        msg = f"{rid} 반려 취소 — {r['ra_id']} 근로자 확인을 다시 기다린다"
    else:
        raise ValueError(act)
    _badge["t"] = 0
    return {"msg": msg}


@router.post("/feedback/mode")
def feedback_mode(body: dict):
    new = body.get("mode")
    if new == feedback.mode():
        return {"msg": "이미 그 방식이다"}
    feedback.set_mode(new, body.get("actor") or "", body.get("note") or "", system_now())
    _badge["t"] = 0
    return {"msg": f"피드백 방식 → {'자동' if new == 'auto' else '승인형'} — 조정 로그에 남았다"}


@router.post("/feedback/act")
def feedback_act(body: dict):
    action, adj_id = body.get("action"), body.get("adj_id")
    actor, note = body.get("actor") or "", body.get("note") or ""
    now = system_now()
    if action == "revert":
        feedback.revert(adj_id, actor, note, now)
        msg = f"{adj_id} 되돌림 · {actor} · 사유: {note}"
    elif action == "approve":
        feedback.approve(adj_id, actor, now)
        msg = f"{adj_id} 승인 — 적용 · {actor}"
    elif action == "reject":
        feedback.reject(adj_id, actor, note, now)
        msg = f"{adj_id} 거부 · {actor} · 사유: {note}"
    elif action == "promote":
        feedback.promote(adj_id, actor, note, now)
        msg = f"{adj_id} → 개정 제안으로 승격 · 문서 자동화 › 위험성평가에서 감소대책(규칙 변경)으로 확정한다"
    else:
        raise ValueError(action)
    _badge["t"] = 0
    return {"msg": msg}


@router.post("/feedback/eval")
def feedback_eval():
    new = feedback.evaluate(system_now())
    _badge["t"] = 0
    if not new:
        return {"msg": "이탈 조건에 걸린 새 조합이 없다 (만료 정리만 했다)"}
    return {"msg": "새 자동 조정 — " + " · ".join(f"{a['adj_id']} {a['zone']} {feedback.reason_text(a)}" for a in new)}


# ====================================================================== 6. 히트맵 · 통계
@router.get("/stats")
def stats_view(which: str = "all"):
    now = system_now()
    evs = load_control_events()
    h = stats.heat(evs, now, 14, which)
    hm_ = stats.helmet(evs, now)
    return {"heat": {"hours": h["hours"], "n": h["n"],
                     "rows": [{"zone": z, "name": zone_name(z), "vals": vals} for z, vals in h["rows"]]},
            "rates": stats.mode_rates(evs, now),
            "helmet": {"has_model": hm_["has_model"], "n": hm_["n"],
                       "rate": [{"dep": d, "rate": r} for d, r in sorted(hm_["rate"].items())],
                       "by_dep": [{"dep": d, "n": v["n"]} for d, v in sorted(hm_["by_dep"].items())]}}
