"""
피드백 루프 — 누적된 감지 기록으로 규칙의 '감시 강도'를 바꾸는 층 (통합 문서 6장 · 피드백 루프 설계)

자동으로 하는 것은 딱 여기까지다 — ① 감시 강도를 ② 강화 방향으로 ③ 기한을 두고.
  알림 단계 상향(1 = 현장 → 2 = 현장 + 관리자), 꺼져 있던 구역 규칙 임시 활성화(무음 기록 → 경보), 관리자 알림.
규칙 내용(PPE · 인원 · 폴리곤 · 모든 완화)은 자동으로 바꾸지 않는다 — 위험성평가를 사람이 확정해야 반영된다(긴 루프).

  1단 자동 조정   중대(중대성 4 · 1건) · 급증(24시간 ≥ 14일 평균 × 2, 최소 3건) · 신규(기준선 0건 조합의 첫 발생)
  2단 개정 제안   같은 구역 14일 안에 조정 3회(승격) · 절대 기준(주간 10건 초과 · 위험도 12 이상) · 오탐 과다(30%)
  알림만          급감(기준선의 30% 이하) — 완화하지 않고 카메라 점검 알림

조정 로그 control/records/adjustments.jsonl — 이벤트 로그와 따로 둔다. 추가 전용이다.
  예시 데이터를 쓰는 동안은 예시데이터_삭제가능/관제/sample_adjustments.jsonl(예시 이벤트에 붙은 adj_id 의 조정)을 앞에 붙여 읽는다.
  같은 adj_id 의 줄이 여러 개면 마지막 줄이 현재 상태다 (applied · pending · rejected · expired · reverted).
  toggle(자동 ↔ 승인형) · promoted(승격)도 사유와 함께 이 파일에 남는다.
강화 기간에 잡힌 기록에는 adj_id 가 붙고(session.LiveEventLog), 기준선을 셀 때 뺀다 — 자기강화 폭주 방지.
설정은 사업장 패키지 rules.json 의 feedback 블록(없으면 아래 기본값).
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta

from .common import RECORD_DIR, append_jsonl, detections, load_control_events, package, read_jsonl, zone_name

ADJ_LOG = RECORD_DIR / "adjustments.jsonl"
ACTIVE_STATES = {"applied"}
OPEN_STATES = {"applied", "pending"}
STATE_LABEL = {"applied": "적용 중", "pending": "승인 대기", "rejected": "거부", "expired": "만료",
               "reverted": "되돌림", "promoted": "개정 제안으로 승격", "toggle": "방식 전환"}
REASON_LABEL = {"severe": "중대", "spike": "급증", "new": "신규"}

DEFAULTS = {
    "mode": "auto",
    "severe": {"severity": 4},
    "spike": {"ratio": 2.0, "min_count": 3, "window_h": 24, "baseline_days": 14},
    "new": {"baseline_days": 14},
    "absolute": {"weekly_count": 10, "risk_score": 12},
    "drop": {"ratio": 0.3, "min_baseline": 5},
    "false_positive": {"ratio": 0.3, "min_count": 5},
    "auto_actions": {"alert_level": {"max_up": 2}, "enable_zone_rule": True, "notify_manager": True},
    "expire_h": 72,
    "promote": {"count": 3, "within_days": 14},
}


def config() -> dict:
    def merge(a, b):
        out = copy.deepcopy(a)
        for k, v in (b or {}).items():
            if k.startswith("_"):
                continue
            out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
        return out
    return merge(DEFAULTS, package().rules_base.get("feedback", {}))


# ---------------------------------------------------------------------- 읽기 (파일이 바뀔 때만 다시 읽는다)
_cache: dict = {"mtime": None, "rows": []}
def _sample_adj():
    """예시 이벤트에 붙은 조정 (예시데이터_삭제가능/관제/sample_adjustments.jsonl) — 예시를 끄거나 지우면 안 읽는다."""
    from .common import sample_root
    return sample_root() / "관제" / "sample_adjustments.jsonl"



def rows() -> list[dict]:
    """조정 로그 줄 전부 (샘플 → 실제 순). 사람이 샘플 조정을 되돌리면 그 줄은 실제 로그에 쌓인다."""
    from safety_docs.config import use_sample_data
    sample = use_sample_data()
    m = (ADJ_LOG.stat().st_mtime if ADJ_LOG.exists() else None, sample)
    if m != _cache["mtime"]:
        base = [{**r, "sample": True} for r in read_jsonl(_sample_adj())] if sample else []
        _cache.update(mtime=m, rows=base + read_jsonl(ADJ_LOG))
    return _cache["rows"]


def _t(s) -> datetime:
    return datetime.fromisoformat(str(s))


def mode() -> str:
    """auto = 자동 적용 · approval = 승인형(사람이 승인해야 적용)."""
    tg = [r for r in rows() if r.get("state") == "toggle"]
    return tg[-1]["feedback_mode"] if tg else config().get("mode", "auto")


def set_mode(new_mode: str, actor: str, note: str, now: datetime) -> dict:
    if new_mode not in ("auto", "approval"):
        raise ValueError("방식은 auto(자동) 또는 approval(승인형)")
    if not actor.strip() or not note.strip():
        raise ValueError("방식을 바꾸려면 이름과 사유를 적는다 — 조정 로그에 남는다")
    return append_jsonl(ADJ_LOG, {"adj_id": f"TGL-{now:%Y%m%d-%H%M%S}", "ts": now.isoformat(timespec="seconds"),
                                  "state": "toggle", "feedback_mode": new_mode, "actor": actor.strip(),
                                  "note": note.strip()})


def adjustments() -> dict[str, dict]:
    """adj_id → 현재 상태(마지막 줄을 앞 줄 위에 덮은 것) + history. ts 는 처음 건 시각이다."""
    out: dict[str, dict] = {}
    for r in rows():
        if not str(r.get("adj_id", "")).startswith("ADJ-"):
            continue
        a = out.setdefault(r["adj_id"], {"history": []})
        a["history"].append({k: r.get(k) for k in ("ts", "state", "actor", "note")})
        a.update({k: v for k, v in r.items() if v is not None})
    for a in out.values():                   # ts = 처음 건 시각, updated = 마지막 줄 시각
        a["updated"] = a["ts"]
        a["ts"] = a["history"][0]["ts"]
    return out


def promotions() -> list[dict]:
    return [r for r in rows() if r.get("state") == "promoted"]


def is_active(a: dict, now: datetime) -> bool:
    return a.get("state") in ACTIVE_STATES and _t(a["expires_at"]) > now and _t(a.get("applied_at", a["ts"])) <= now


def active(now: datetime) -> list[dict]:
    return sorted((a for a in adjustments().values() if is_active(a, now)), key=lambda a: a["ts"], reverse=True)


def pending() -> list[dict]:
    return [a for a in adjustments().values() if a.get("state") == "pending"]


def lookup(zone: str, ts: datetime) -> tuple[str | None, bool]:
    """기록 한 줄이 강화 기간에 잡혔나 — (adj_id, 구역 규칙 임시 활성화 여부). session.LiveEventLog 가 부른다."""
    for a in active(ts):
        if a.get("zone") == zone:
            return a["adj_id"], bool((a.get("action") or {}).get("enable_zone_rule"))
    return None, False


def zone_alert_level(zone: str, now: datetime) -> dict:
    cfg = config()
    act = [a for a in active(now) if a.get("zone") == zone]
    top = 1 + cfg["auto_actions"]["alert_level"]["max_up"]
    return {"level": min(top, 1 + len(act)), "adj_ids": [a["adj_id"] for a in act],
            "enable": any((a.get("action") or {}).get("enable_zone_rule") for a in act)}


# ---------------------------------------------------------------------- 표시
def reason_text(a: dict) -> str:
    r = a.get("reason") or {}
    t = r.get("type")
    vt = a.get("violation_type") or ""
    if t == "severe":
        return f"중대 · {r.get('event_id')} ({vt}, 중대성 {r.get('severity')})"
    if t == "spike":
        return f"급증 · 24시간 {r.get('count')}건 (평소 {r.get('baseline'):.1f}건) · {vt}"
    if t == "new":
        return f"신규 · 기준선 0건 조합의 첫 발생 · {vt}"
    return t or "-"


def action_text(a: dict) -> str:
    ac = a.get("action") or {}
    out = [f"알림 단계 {ac.get('before')} → {ac.get('after')}"]
    if ac.get("enable_zone_rule"):
        out.append("구역 규칙 임시 활성화(무음 → 경보)")
    if ac.get("notify_manager"):
        out.append("알림 대상에 관리자 추가")
    return " · ".join(out)


# ---------------------------------------------------------------------- 1단 — 이탈 조건 → 자동 조정
def _next_id(now: datetime) -> str:
    base = f"ADJ-{now:%Y%m%d}-"
    n = [int(k.rsplit("-", 1)[1]) for k in adjustments() if k.startswith(base)]
    return f"{base}{max(n, default=0) + 1:03d}"


def _create(zone, mode_name, vt, reason, evidence, now, cfg) -> dict:
    cur = zone_alert_level(zone, now)["level"]
    top = 1 + cfg["auto_actions"]["alert_level"]["max_up"]
    fb_mode = mode()
    row = {"adj_id": _next_id(now), "ts": now.isoformat(timespec="seconds"),
           "state": "applied" if fb_mode == "auto" else "pending",
           "zone": zone, "mode": mode_name, "violation_type": vt, "reason": reason,
           "action": {"param": "alert_level", "before": cur, "after": min(top, cur + 1),
                      "enable_zone_rule": bool(cfg["auto_actions"].get("enable_zone_rule")),
                      "notify_manager": bool(cfg["auto_actions"].get("notify_manager"))},
           "applied_at": now.isoformat(timespec="seconds"),
           "expires_at": (now + timedelta(hours=cfg["expire_h"])).isoformat(timespec="seconds"),
           "feedback_mode": fb_mode, "actor": "system", "evidence_event_ids": evidence, "note": None}
    append_jsonl(ADJ_LOG, row)
    rows()
    return row


def evaluate(now: datetime | None = None, events: list[dict] | None = None) -> list[dict]:
    """만료를 정리하고 이탈 조건을 본다. 새로 만든 조정 줄을 돌려준다."""
    from safety_docs.config import load_scales
    from safety_docs.risk import severity_level

    from .common import system_now
    cfg = config()
    now = now or system_now()
    for a in adjustments().values():
        if a.get("state") == "applied" and _t(a["expires_at"]) <= now:
            append_jsonl(ADJ_LOG, {"adj_id": a["adj_id"], "ts": a["expires_at"], "state": "expired", "actor": "system"})
    rows()
    scales = load_scales()
    evs = [e for e in detections(events if events is not None else load_control_events())
           if not e.get("false_positive") and e["_ts"] <= now]
    cur = adjustments()
    used = {x for a in cur.values() for x in a.get("evidence_event_ids", [])}

    def open_for(zone, rtype, vt):
        return any(a.get("zone") == zone and (a.get("reason") or {}).get("type") == rtype and a.get("violation_type") == vt
                   and a.get("state") in OPEN_STATES and _t(a["expires_at"]) > now for a in adjustments().values())

    new: list[dict] = []
    top = 1 + cfg["auto_actions"]["alert_level"]["max_up"]
    made: set[str] = set()

    def room(zone) -> bool:
        """한 번 볼 때 구역마다 하나만, 그리고 이미 최대로 올려 둔 구역은 더 걸지 않는다 (같은 사건으로 조정이 겹쳐 승격되는 것 방지)."""
        return zone not in made and zone_alert_level(zone, now)["level"] < top

    def create(zone, *a):
        row = _create(zone, *a)
        made.add(zone)
        new.append(row)
        return row

    # 중대 — 중대성 최고 등급 1건이면 통계를 기다리지 않는다
    horizon = now - timedelta(hours=cfg["expire_h"])
    for e in evs:
        if not e.get("alerted") or e["event_id"] in used or e["_ts"] < horizon:
            continue
        sev, _ = severity_level(e["violation_type"], scales, e.get("mode"))
        if sev >= cfg["severe"]["severity"] and not open_for(e["zone"], "severe", e["violation_type"]) and room(e["zone"]):
            create(e["zone"], e.get("mode"), e["violation_type"],
                   {"type": "severe", "severity": sev, "event_id": e["event_id"]}, [e["event_id"]], now, cfg)
            used.add(e["event_id"])
    # 급증 · 신규 — 강화 기간(adj_id)에 잡힌 기록은 기준선에서 뺀다
    sp = cfg["spike"]
    w0 = now - timedelta(hours=sp["window_h"])
    b0 = w0 - timedelta(days=sp["baseline_days"])
    win = [e for e in evs if e["_ts"] > w0]
    base = [e for e in evs if b0 <= e["_ts"] <= w0 and not e.get("adj_id")]
    groups: dict[tuple, list] = {}
    for e in win:
        groups.setdefault((e["zone"], e["violation_type"]), []).append(e)
    per = sp["baseline_days"] * 24 / sp["window_h"]
    for (z, vt), es in groups.items():
        bc = sum(1 for e in base if e["zone"] == z and e["violation_type"] == vt)
        avg = bc / per
        if len(es) >= sp["min_count"] and len(es) >= sp["ratio"] * avg and not open_for(z, "spike", vt) and room(z):
            create(z, es[-1].get("mode"), vt, {"type": "spike", "count": len(es), "baseline": avg},
                   [e["event_id"] for e in es], now, cfg)
    if base:                                  # 기준선 기간에 기록이 하나도 없으면 전부 '신규'가 되므로 보지 않는다
        seen = {(e["zone"], e.get("mode"), e["violation_type"]) for e in base}
        for e in win:
            k = (e["zone"], e.get("mode"), e["violation_type"])
            if k not in seen and not open_for(e["zone"], "new", e["violation_type"]) and e["event_id"] not in used \
                    and room(e["zone"]):
                create(e["zone"], e.get("mode"), e["violation_type"], {"type": "new"}, [e["event_id"]], now, cfg)
                seen.add(k)
    # 승격 — 같은 구역에서 조정이 반복되면 지침이 현실과 맞지 않는다는 증거다
    pr = cfg["promote"]
    since = now - timedelta(days=pr["within_days"])
    done = {p["zone"] for p in promotions() if _t(p["ts"]) >= since}
    by_zone: dict[str, list] = {}
    for a in adjustments().values():
        if _t(a["ts"]) >= since and a.get("state") != "rejected":
            by_zone.setdefault(a["zone"], []).append(a["adj_id"])
    for z, ids in by_zone.items():
        if len(ids) >= pr["count"] and z not in done:
            append_jsonl(ADJ_LOG, {"adj_id": f"PRM-{now:%Y%m%d-%H%M%S}-{z}", "ts": now.isoformat(timespec="seconds"),
                                   "state": "promoted", "zone": z, "adj_ids": sorted(ids), "actor": "system",
                                   "note": f"{pr['within_days']}일 안에 조정 {len(ids)}회 — 개정 제안(2단)으로 올림"})
    rows()
    return new


# ---------------------------------------------------------------------- 사람이 하는 일
def _change(adj_id: str, state: str, actor: str, note: str, now: datetime, need_note: bool, **extra) -> dict:
    a = adjustments().get(adj_id)
    if not a:
        raise ValueError(f"없는 조정: {adj_id}")
    if need_note and not note.strip():
        raise ValueError("사유를 적어야 한다 — 조정 로그에 남는다")
    if not actor.strip():
        raise ValueError("처리자 이름을 적는다")
    return append_jsonl(ADJ_LOG, {"adj_id": adj_id, "ts": now.isoformat(timespec="seconds"), "state": state,
                                  "actor": actor.strip(), "note": note.strip() or None, **extra})


def approve(adj_id: str, actor: str, now: datetime) -> dict:
    a = adjustments().get(adj_id) or {}
    if a.get("state") != "pending":
        raise ValueError(f"{adj_id} 는 승인 대기가 아니다")
    exp = now + timedelta(hours=config()["expire_h"])
    return _change(adj_id, "applied", actor, "승인", now, False, applied_at=now.isoformat(timespec="seconds"),
                   expires_at=exp.isoformat(timespec="seconds"))


def reject(adj_id: str, actor: str, note: str, now: datetime) -> dict:
    if (adjustments().get(adj_id) or {}).get("state") != "pending":
        raise ValueError(f"{adj_id} 는 승인 대기가 아니다")
    return _change(adj_id, "rejected", actor, note, now, True)


def revert(adj_id: str, actor: str, note: str, now: datetime) -> dict:
    if (adjustments().get(adj_id) or {}).get("state") != "applied":
        raise ValueError(f"{adj_id} 는 적용 중이 아니다")
    return _change(adj_id, "reverted", actor, note, now, True)


def promote(adj_id: str, actor: str, note: str, now: datetime) -> dict:
    a = adjustments().get(adj_id)
    if not a:
        raise ValueError(f"없는 조정: {adj_id}")
    if not actor.strip():
        raise ValueError("처리자 이름을 적는다")
    return append_jsonl(ADJ_LOG, {"adj_id": f"PRM-{now:%Y%m%d-%H%M%S}-{a['zone']}", "ts": now.isoformat(timespec="seconds"),
                                  "state": "promoted", "zone": a["zone"], "adj_ids": [adj_id], "actor": actor.strip(),
                                  "note": note.strip() or "사람이 개정 제안으로 올림"})


# ---------------------------------------------------------------------- 2단 · 알림 — 화면에 보이는 제안
def proposals(now: datetime, events: list[dict] | None = None) -> list[dict]:
    """긴 루프로 넘길 것 — 승격 · 절대 기준 · 오탐 과다, 그리고 급감(카메라 점검 알림)."""
    from safety_docs.assessment import build_rows
    from safety_docs.config import load_events, load_profile, load_scales
    cfg = config()
    out = []
    for p in promotions():
        out.append({"kind": "승격", "zone": p["zone"], "text": p.get("note", ""), "ref": ", ".join(p.get("adj_ids", [])),
                    "ts": p["ts"], "go": "ra"})
    evs = [e for e in detections(events if events is not None else load_control_events()) if e["_ts"] <= now]
    wk = now - timedelta(days=7)
    cnt: dict[tuple, int] = {}
    for e in evs:
        if e["_ts"] > wk and not e.get("false_positive"):
            cnt[(e["zone"], e["violation_type"])] = cnt.get((e["zone"], e["violation_type"]), 0) + 1
    for (z, vt), n in sorted(cnt.items()):
        if n > cfg["absolute"]["weekly_count"]:
            out.append({"kind": "절대 기준", "zone": z, "text": f"{vt} 주간 {n}건 > {cfg['absolute']['weekly_count']}건",
                        "ref": "", "ts": now.isoformat(timespec="seconds"), "go": "ra"})
    dev, as_of = load_events()
    rows_, _ = build_rows(dev, as_of, load_scales(), load_profile().get("accidents"))
    for r in rows_:
        if r["score"] >= cfg["absolute"]["risk_score"]:
            out.append({"kind": "위험도", "zone": r["zone"], "text": f"{r['mode']} · {r['violation_type']} 위험도 {r['score']} ≥ {cfg['absolute']['risk_score']}",
                        "ref": "", "ts": as_of.isoformat(timespec="seconds"), "go": "ra"})
    fp = cfg["false_positive"]
    tot: dict[tuple, list] = {}
    for e in evs:
        tot.setdefault((e["zone"], e["violation_type"]), []).append(e)
    for (z, vt), es in tot.items():
        n_fp = sum(1 for e in es if e.get("false_positive"))
        if len(es) >= fp["min_count"] and n_fp / len(es) > fp["ratio"]:
            out.append({"kind": "오탐 과다", "zone": z, "text": f"{vt} 오탐 {n_fp}/{len(es)} — 완화 제안(사람 승인 · 자동으로 풀지 않는다)",
                        "ref": "", "ts": now.isoformat(timespec="seconds"), "go": "ra"})
    dr = cfg["drop"]
    b0 = now - timedelta(days=7 + cfg["spike"]["baseline_days"])
    for z in {e["zone"] for e in evs}:
        base = sum(1 for e in evs if e["zone"] == z and b0 <= e["_ts"] < wk) / (cfg["spike"]["baseline_days"] / 7)
        last = sum(1 for e in evs if e["zone"] == z and e["_ts"] >= wk)
        if base >= dr["min_baseline"] and last <= dr["ratio"] * base:
            out.append({"kind": "급감", "zone": z, "text": f"최근 7일 {last}건 · 평소 주 {base:.1f}건 — 카메라 · 시스템 점검 (완화하지 않는다)",
                        "ref": "", "ts": now.isoformat(timespec="seconds"), "go": None})
    return out


def zone_counts(now: datetime, days: int = 14) -> dict[str, int]:
    since = now - timedelta(days=days)
    out: dict[str, int] = {}
    for a in adjustments().values():
        if _t(a["ts"]) >= since and a.get("state") != "rejected":
            out[a["zone"]] = out.get(a["zone"], 0) + 1
    return out


STEP_NAMES = ["규칙 변경 제안", "관리자 서명", "근로자 확인", "위험성평가 확정", "규칙셋 반영"]
STEP_LABEL = {"done": "완료", "now": "진행 중", "wait": "대기", "rej": "반려"}
PHASE_TEXT = {"none": "제안 없음", "draft": "관리자 서명 대기", "worker": "근로자 확인 대기", "rejected": "반려",
              "ra_rejected": "위험성평가 반려", "rejected_final": "반려 — 확정에서 제외", "confirmed": "확정 — 새 세션부터 반영",
              "live": "규칙셋 반영됨"}


def _js(v) -> str:
    import json
    return json.dumps(v, ensure_ascii=False)


def rule_changes_view(drafts: list[dict] | None = None, live: dict | None = None) -> list[dict]:
    """
    긴 루프 — 규칙셋 변경안(패키지 rule_changes)마다 무엇이 바뀌는지(diff)와 다섯 단계 중 어디까지 왔는지.
      ① 규칙 변경 제안    위험성평가 감소대책에 그 변경안 id 가 연결된다 (서명 전 초안이어도 된다 — drafts)
      ② 관리자 서명       평가표 서명 → records/assessments/RA-*.json
      ③ 근로자 확인       근로자 대표 확인 (안전소통 › 근로자 확인)
      ④ 위험성평가 확정   ③과 같은 순간 — 규칙셋 버전이 오른다 (ruleset_log)
      ⑤ 규칙셋 반영       지금 도는 관제 세션의 규칙셋에 그 변경안이 켜져 있다 (live) — 확정분은 새 세션부터 켜진다
    변경안 하나만 반려하면(②와 ③ 사이, 여기 화면에서) ③에 '반려'로 서고, 확정할 때 그 변경안만 빠진다.
    위험성평가 감소대책에 R id 가 달려야 여기로 이어진다 (문서 자동화 › 위험성평가).
    step(0 · 2 · 3) · status · ra 는 예전 화면(Gradio)용으로 그대로 둔다.
    """
    from safety_docs.assessment import linked_rules, list_assessments, ruleset_revisions
    from safety_monitor.package import docgen_confirmed_changes
    pkg = package()
    base = pkg.rules_base
    confirmed = set(docgen_confirmed_changes())
    revs = ruleset_revisions()
    ras = list_assessments()                                  # 최근 것부터
    live = live or {}
    live_on = set(live.get("applied") or [])

    def get(path):
        d = base
        for k in path.split("."):
            d = d.get(k) if isinstance(d, dict) else None
        return d

    def rows_for(rid, rows):
        out = []
        for r in rows or []:
            ms = [m for m in r.get("measures", []) if m.get("rule_id") == rid]
            if ms:
                out.append({"zone": r["zone"], "zname": zone_name(r["zone"]), "mode": r.get("mode"),
                            "violation_type": r.get("violation_type"), "hazard": r.get("hazard", ""),
                            "cause": r.get("cause", ""), "score": r.get("score"), "grade": r.get("grade"),
                            "adhoc": r.get("adhoc_reasons", []), "event_ids": r.get("event_ids", []),
                            "accident_ids": r.get("accident_ids", []), "measures": [f"[{m['category']}] {m['text']}" for m in ms]})
        return out

    out = []
    for rid, ch in base.get("rule_changes", {}).items():
        if rid.startswith("_"):
            continue
        diff, change = [], []
        for path, val in ch.get("set", {}).items():
            diff.append(("ctx", f"{path}"))
            diff.append(("del", f"-  {_js(get(path))}"))
            diff.append(("add", f"+  {_js(val)}"))
            change.append({"path": path, "before": _js(get(path)), "after": _js(val)})
        for path, vals in ch.get("add", {}).items():
            diff.append(("ctx", f"{path}  {_js(get(path))}"))
            diff += [("add", f"+  {_js(v)}") for v in vals]
            change.append({"path": path, "before": _js(get(path)), "after": _js(list(get(path) or []) + list(vals))})

        linked = [ra for ra in ras if rid in linked_rules(ra)]
        pend = next((ra for ra in linked if ra["state"] == "worker_pending"), None)
        rev = next((r for r in revs if rid in r.get("rule_ids", [])), None)
        draft_rows = rows_for(rid, drafts)
        ra, rej = None, None
        if rid in confirmed:
            phase = "live" if rid in live_on else "confirmed"
            ra = next((x for x in linked if rev and x["ra_id"] == rev.get("ra_id")), linked[0] if linked else None)
        elif pend:
            ra = pend
            rej = pend["rule_rejected"].get(rid)
            phase = "rejected" if rej else "worker"
        elif draft_rows:
            phase = "draft"
        elif linked:
            ra = linked[0]
            rej = ra["rule_rejected"].get(rid)
            phase = "ra_rejected" if ra["state"] == "rejected" else "rejected_final" if rej else "confirmed"
        else:
            phase = "none"

        conf = next((h for h in reversed((ra or {}).get("history", [])) if h.get("state") == "confirmed"), None)
        ra_rej = next((h for h in reversed((ra or {}).get("history", [])) if h.get("state") == "rejected"), None)
        st = {"none": ["wait"] * 5, "draft": ["done", "now", "wait", "wait", "wait"],
              "worker": ["done", "done", "now", "wait", "wait"], "rejected": ["done", "done", "rej", "wait", "wait"],
              "ra_rejected": ["done", "done", "rej", "wait", "wait"], "rejected_final": ["done", "done", "rej", "wait", "wait"],
              "confirmed": ["done", "done", "done", "done", "now"], "live": ["done"] * 5}[phase]
        zs = list(dict.fromkeys(r["zone"] for r in (rows_for(rid, ra["rows"]) if ra else draft_rows)))
        sub = [
            (f"{ra['ra_id']} 감소대책 · {' · '.join(zs)}" if ra else
             "초안 감소대책에 연결됨 (서명 전)" if phase == "draft" else "위험성평가 감소대책에 연결되면 올라온다"),
            (f"{ra.get('manager', '')} · {ra.get('created_at', '')[5:16].replace('T', ' ')}" if ra else
             "관리자 검토 · 서명 대기 — 문서 자동화 › 위험성평가" if phase == "draft" else "관리자 검토 · 서명"),
            (f"반려 · {rej.get('name', '')} · {rej.get('note', '')}" if rej else
             f"위험성평가 반려 · {(ra_rej or {}).get('name', '')} · {(ra_rej or {}).get('note', '')}" if phase == "ra_rejected" else
             f"{(conf or {}).get('worker_rep') or (conf or {}).get('name', '')} · {(conf or {}).get('ts', '')[5:16].replace('T', ' ')}" if conf else
             "근로자 대표 확인 대기 — 안전소통 › 근로자 확인" if phase == "worker" else "근로자 대표 의견 · 확인"),
            (f"규칙셋 v{rev['version']} · {rev['ts'][5:16].replace('T', ' ')}" if rev and phase in ("confirmed", "live") else
             f"평가는 {(conf or {}).get('ts', '')[5:16].replace('T', ' ')} 확정 — 이 변경안만 빠졌다" if phase == "rejected_final" and conf else
             "근로자 확인이 끝나면 함께 확정 — 규칙셋 버전이 오른다"),
            (f"관제 세션 {live.get('sid') or '(미리 보기)'} 에 켜짐" if phase == "live" else
             "확정분은 새 관제 세션부터 켜진다 (규칙셋 '문서 자동화 확정분')" if phase == "confirmed" else
             "확정 후 운영 규칙셋에 반영"),
        ]
        steps = [{"name": n, "state": s_, "label": STEP_LABEL[s_], "sub": sb} for n, s_, sb in zip(STEP_NAMES, st, sub)]
        detail_rows = rows_for(rid, ra["rows"]) if ra else draft_rows
        r0 = detail_rows[0] if detail_rows else {}
        reason = ""
        if r0:
            reason = f"{r0.get('hazard') or r0.get('violation_type')} · 위험도 {r0.get('score')} ({r0.get('grade')})"
            if r0.get("adhoc"):
                reason += " · 수시평가 사유: " + ", ".join(r0["adhoc"])
        ev = list(dict.fromkeys(e for r in detail_rows for e in r.get("event_ids", [])))
        acc = list(dict.fromkeys(a for r in detail_rows for a in r.get("accident_ids", [])))
        # 예전 화면(Gradio)용 값
        if phase in ("confirmed", "live"):
            status, step = "규칙셋 반영됨", 3
        elif pend:
            status, step = (f"근로자 확인 대기 · {pend['ra_id']}" if not rej else f"반려 · {pend['ra_id']} · {rej.get('note', '')}"), 2
        else:
            status, step = "제안 없음 — 위험성평가 감소대책에 연결되면 올라온다", 0
        out.append({"id": rid, "text": ch.get("text", ""), "diff": diff, "status": status, "step": step,
                    "ra": pend["ra_id"] if pend else None,
                    "phase": phase, "phase_text": PHASE_TEXT[phase], "steps": steps, "change": change,
                    "ra_id": ra["ra_id"] if ra else "", "ra_kind": (ra or {}).get("kind", ""),
                    "ra_state": (ra or {}).get("state_label", "초안 (서명 전)" if phase == "draft" else ""),
                    "zones": [{"id": z, "name": zone_name(z)} for z in zs],
                    "proposer": (ra or {}).get("manager", "") or ("초안 작성 중 (서명 전)" if phase == "draft" else ""),
                    "created": ((ra or {}).get("created_at", "") or "").replace("T", " ")[:16],
                    "reason": reason, "evidence": ev, "accidents": acc, "rows": detail_rows,
                    "rejection": ({"name": rej.get("name", ""), "role": rej.get("role", ""), "note": rej.get("note", ""),
                                   "ts": rej.get("ts", "").replace("T", " ")[:16]} if rej else None),
                    "version": rev["version"] if rev and phase in ("confirmed", "live") else None,
                    "can_reject": phase == "worker", "can_restore": phase == "rejected",
                    "demo_on": rid in live_on and phase not in ("confirmed", "live")})
    return out


def _pending_ra_for(rule_id: str) -> dict:
    from safety_docs.assessment import linked_rules, list_assessments
    ra = next((x for x in list_assessments() if x["state"] == "worker_pending" and rule_id in linked_rules(x)), None)
    if not ra:
        raise ValueError(f"{rule_id} 는 근로자 확인을 기다리는 위험성평가에 연결돼 있지 않다 — "
                         "변경안 반려는 관리자 서명 뒤 · 근로자 확인 전에만 한다")
    return ra


def reject_rule_change(rule_id: str, actor: str, role: str, note: str) -> dict:
    """긴 루프 — 변경안 하나만 반려. 기록은 문서 자동화 records/rule_rejections.jsonl (위험성평가와 같은 곳)."""
    from safety_docs.assessment import reject_rule
    ra = _pending_ra_for(rule_id)
    return reject_rule(ra["ra_id"], rule_id, role, actor, note)


def restore_rule_change(rule_id: str, actor: str, role: str, note: str) -> dict:
    from safety_docs.assessment import restore_rule
    ra = _pending_ra_for(rule_id)
    return restore_rule(ra["ra_id"], rule_id, role, actor, note)


# ---------------------------------------------------------------------- 조정 로그 (전체 이력) — 짧은 루프 + 긴 루프
def current_label(a: dict, now: datetime) -> tuple[str, str]:
    """조정 하나의 지금 상태 — (키, 화면 이름)."""
    st = a.get("state")
    if st == "applied":
        if _t(a.get("applied_at", a["ts"])) > now:
            return "scheduled", "적용 예정"
        return ("applied", "적용 중") if _t(a["expires_at"]) > now else ("expired", "만료")
    return st, STATE_LABEL.get(st, st)


def log_rows(now: datetime) -> list[dict]:
    """
    조정 로그 화면의 줄 — 상태가 바뀔 때마다 한 줄 (최근 것부터).
      짧은 루프   adjustments.jsonl 의 ADJ-* 줄 (첫 줄의 결과 = 그 조정의 지금 상태). 만료 시각이 지났는데
                 정리 줄이 아직 없으면 '만료(정리 전)' 줄을 붙여 보인다 — 파일에는 쓰지 않는다
      승격       PRM-* 줄 — 짧은 루프가 긴 루프로 올라간 것
      방식 전환   TGL-* 줄
      긴 루프     문서 자동화 기록에서 읽기만 한다 — 규칙 변경이 연결된 위험성평가의 서명 · 확인 · 반려,
                 변경안 단위 반려 · 취소(rule_rejections), 규칙셋 버전(ruleset_log)
    """
    from safety_docs.assessment import linked_rules, list_assessments, rule_rejection_log, ruleset_revisions
    adjs = adjustments()
    out: list[dict] = []
    seen: set[str] = set()

    def add(ts, loop, kind, id_, zone, text, state, label, actor, note="", expires="", sample=False):
        out.append({"ts": str(ts).replace("T", " ")[:16], "loop": loop, "kind": kind, "id": id_, "zone": zone or "",
                    "zname": zone_name(zone) if zone else "", "text": text, "state": state, "label": label,
                    "actor": actor or "", "note": note or "", "expires": str(expires).replace("T", " ")[5:16],
                    "sample": sample})

    for r in rows():
        aid, st = str(r.get("adj_id", "")), r.get("state")
        if aid.startswith("ADJ-") and aid in adjs:
            a = adjs[aid]
            if aid not in seen:
                seen.add(aid)
                k, lab = current_label(a, now)
                add(r["ts"], "short", "짧은 루프", aid, a.get("zone"),
                    ("자동 조정 적용 — " if st == "applied" else "자동 조정 제안(승인형) — ") + action_text(a),
                    k, lab, r.get("actor") or "system", reason_text(a), a.get("expires_at", ""), bool(r.get("sample")))
                continue
            text = {"applied": "승인 — 적용 시작", "rejected": "거부 — 적용하지 않음", "reverted": "되돌림 — 원래 값으로",
                    "expired": "만료 — 원래 값으로 복원"}.get(st, STATE_LABEL.get(st, st))
            add(r["ts"], "short", "짧은 루프", aid, a.get("zone"), text, st if st != "applied" else "approved",
                "승인" if st == "applied" else STATE_LABEL.get(st, st), r.get("actor") or "system", r.get("note") or "",
                sample=bool(r.get("sample")))
        elif st == "promoted":
            add(r["ts"], "long", "승격", aid, r.get("zone"), "개정 제안(2단)으로 승격 — " + ", ".join(r.get("adj_ids", [])),
                "promoted", "승격", r.get("actor") or "system", r.get("note") or "", sample=bool(r.get("sample")))
        elif st == "toggle":
            add(r["ts"], "toggle", "방식 전환", aid, "", f"피드백 방식 → {'자동' if r.get('feedback_mode') == 'auto' else '승인형'}",
                "toggle", "전환", r.get("actor"), r.get("note") or "")
    for a in adjs.values():                     # 만료 시각이 지났는데 아직 정리 줄이 없는 것
        if a.get("state") == "applied" and _t(a["expires_at"]) <= now:
            add(a["expires_at"], "short", "짧은 루프", a["adj_id"], a.get("zone"), "만료 — 원래 값으로 복원 (정리 전)",
                "expired", "만료", "system", "기한 경과 — '이탈 조건 지금 보기'를 누르면 정리 줄이 남는다", sample=bool(a.get("sample")))

    ras = {ra["ra_id"]: ra for ra in list_assessments()}

    def ra_zone(ra, rule_ids):
        zs = [r["zone"] for r in ra.get("rows", []) for m in r.get("measures", []) if m.get("rule_id") in rule_ids]
        return " · ".join(dict.fromkeys(zs))

    for ra in ras.values():
        rules = linked_rules(ra)
        if not rules:
            continue
        zs = ra_zone(ra, rules)
        for h in ra["history"]:
            if h["state"] == "submitted":
                add(h["ts"], "long", "긴 루프", ra["ra_id"], zs, f"관리자 서명 — 감소대책에 {', '.join(rules)} 연결",
                    "signed", "서명", h.get("name") or ra.get("manager"), h.get("note", ""))
            elif h["state"] == "confirmed":
                add(h["ts"], "long", "긴 루프", ra["ra_id"], zs, "근로자 확인 · 위험성평가 확정",
                    "confirmed", "확정", h.get("worker_rep") or h.get("name"), h.get("note", ""))
            elif h["state"] == "rejected":
                add(h["ts"], "long", "긴 루프", ra["ra_id"], zs, "위험성평가 반려 — 변경안 전부 반영하지 않음",
                    "ra_rejected", "반려", h.get("name"), h.get("note", ""))
    for r in rule_rejection_log():
        ra = ras.get(r["ra_id"], {})
        add(r["ts"], "long", "긴 루프", f"{r['rule_id']} · {r['ra_id']}", ra_zone(ra, [r["rule_id"]]) if ra else "",
            f"변경안 {r['rule_id']} " + ("반려 — 확정해도 규칙셋에 올리지 않음" if r["state"] == "rejected" else "반려 취소"),
            "rule_rejected" if r["state"] == "rejected" else "restored", "반려" if r["state"] == "rejected" else "취소",
            f"{r.get('name', '')} ({r.get('role', '')})" if r.get("role") else r.get("name"), r.get("note", ""))
    for v in ruleset_revisions():
        ra = ras.get(v.get("ra_id"), {})
        add(v["ts"], "long", "긴 루프", f"v{v['version']}", ra_zone(ra, v.get("rule_ids", [])) if ra else "",
            f"규칙셋 v{v['version']} 반영 — {', '.join(v.get('rule_ids', []))}", "reflected", "반영", v.get("by", ""),
            f"근거 {v.get('ra_id', '')}")
    out.sort(key=lambda x: x["ts"], reverse=True)
    return out


def trend(now: datetime, days: int = 14) -> dict:
    """최근 14일 조정 — 날짜별 건수(막대)와 전주 대비. zone_counts 와 같은 기준(처음 건 시각 · 거부 제외)."""
    since = (now - timedelta(days=days - 1)).date()
    daily = {since + timedelta(days=i): 0 for i in range(days)}
    for a in adjustments().values():
        d = _t(a["ts"]).date()
        if a.get("state") != "rejected" and d in daily:
            daily[d] += 1
    vals = [daily[k] for k in sorted(daily)]
    this_w, prev_w = sum(vals[-7:]), sum(vals[-14:-7])
    return {"days": [k.strftime("%m-%d") for k in sorted(daily)], "vals": vals, "this_week": this_w, "prev_week": prev_w,
            "delta": this_w - prev_w, "pct": round((this_w - prev_w) / prev_w * 100) if prev_w else None}


def zone_label(z: str) -> str:
    return f"{z} {zone_name(z)}"
