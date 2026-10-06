"""
히트맵 · 통계 — 구역 · 부서 단위 통계다. 개인을 평가하지 않는다.
무음 기록도 세어서, 모드가 꺼진 구간에 무엇이 일어났는지 같이 본다.

  heat()        구역 × 시간(시) — 최근 14일 위반 건수 (전체 · 경보만 · 무음 기록만)
  mode_rates()  작업 모드가 켜졌을 때 vs 평상시 — 시간당 위반 (같은 구역).
                모드가 켜져 있던 시간은 실시간 세션이 남긴 modes.jsonl 에서 센다. 시간이 기록된 것만 비율을 낸다.
  helmet()      안전모 — 탐지 모델이 붙어 있으면 착용률(사람이 보인 시간 중 미착용 시간), 없으면 미착용 기록 건수.
                부서 · 협력사로 묶는 대응표는 사업장 패키지 dashboard.json 의 departments.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .common import detections, live_sessions, read_jsonl, zone_name, zones


def _window(events, now, days):
    since = now - timedelta(days=days)
    return [e for e in detections(events) if since < e["_ts"] <= now and not e.get("false_positive")]


def heat(events: list[dict], now: datetime, days: int = 14, which: str = "all") -> dict:
    evs = _window(events, now, days)
    if which == "alert":
        evs = [e for e in evs if e.get("alerted")]
    elif which == "shadow":
        evs = [e for e in evs if not e.get("alerted")]
    hours = sorted({e["_ts"].hour for e in evs} | set(range(8, 18)))
    grid: dict[str, dict[int, int]] = {}
    for e in evs:
        grid.setdefault(e["zone"], {}).setdefault(e["_ts"].hour, 0)
        grid[e["zone"]][e["_ts"].hour] += 1
    order = [z for z in zones() if z in grid]
    return {"hours": hours, "rows": [(z, [grid[z].get(h, 0) for h in hours]) for z in order], "n": len(evs)}


def mode_intervals(now: datetime) -> list[tuple[str, str, datetime, datetime]]:
    """실시간 세션들이 남긴 모드 켜짐 구간 (구역, 모드, 시작, 끝)."""
    out = []
    for d in live_sessions():
        open_: dict[tuple, datetime] = {}
        last = None
        for r in read_jsonl(d / "modes.jsonl"):
            t = datetime.fromisoformat(r["ts"])
            last = t
            k = (r["zone"], r["mode"])
            if r["on"]:
                open_[k] = t
            elif k in open_:
                out.append((k[0], k[1], open_.pop(k), t))
        ev_last = max((datetime.fromisoformat(e["ts"]) for e in read_jsonl(d / "events.jsonl")), default=last)
        end = max(x for x in (last, ev_last) if x) if (last or ev_last) else None
        for k, t0 in open_.items():
            if end and end > t0:
                out.append((k[0], k[1], t0, end))
    return out


def session_spans() -> list[tuple[datetime, datetime]]:
    """세션마다 관제가 실제로 돈 구간 (시작 ~ 마지막 기록)."""
    out = []
    for d in live_sessions():
        meta = read_jsonl(d / "session.json")
        if not meta:
            continue
        t0 = datetime.fromisoformat(meta[0]["start"])
        ts = [datetime.fromisoformat(r["ts"]) for r in read_jsonl(d / "modes.jsonl")] + \
             [datetime.fromisoformat(e["ts"]) for e in read_jsonl(d / "events.jsonl")]
        if ts and max(ts) > t0:
            out.append((t0, max(ts)))
    return out


def mode_rates(events: list[dict], now: datetime) -> list[dict]:
    """모드가 켜진 구간과 꺼진 구간의 시간당 위반. 실시간 세션 기록만 쓴다(샘플에는 모드 시간이 없다)."""
    ivs = mode_intervals(now)
    spans = session_spans()
    live = [e for e in detections(events) if e.get("_src", "샘플") != "샘플" and not e.get("false_positive")]
    out = []
    for z in zones():
        z_ivs = [(m, a, b) for zz, m, a, b in ivs if zz == z and m != "평상시"]
        if not z_ivs:
            continue
        on_h = sum((b - a).total_seconds() for _, a, b in z_ivs) / 3600
        tot_h = sum((b - a).total_seconds() for a, b in spans) / 3600
        off_h = max(tot_h - on_h, 0)
        in_on = [e for e in live if e["zone"] == z and any(a <= e["_ts"] <= b for _, a, b in z_ivs)]
        in_off = [e for e in live if e["zone"] == z and e not in in_on]
        modes = " · ".join(dict.fromkeys(m for m, _, _ in z_ivs))
        out.append({"zone": z, "label": f"{z} {modes}", "rate": len(in_on) / on_h if on_h > 0 else 0, "hours": on_h,
                    "n": len(in_on), "kind": "on"})
        out.append({"zone": z, "label": f"{z} 평상시", "rate": len(in_off) / off_h if off_h > 0 else 0, "hours": off_h,
                    "n": len(in_off), "kind": "off"})
    return out


def helmet(events: list[dict], now: datetime, days: int = 14) -> dict:
    """안전모 — 탐지 모델이 있으면 착용률, 없으면 미착용 기록 건수를 부서 · 협력사로 묶는다."""
    from .common import dashboard, package
    deps = {k: v for k, v in dashboard().get("departments", {}).items() if not k.startswith("_")}
    has_model = any(x.get("name") in ("no_helmet", "helmet") for x in package().detect.get("extra", []))
    evs = [e for e in _window(events, now, days) if "안전모" in (e.get("violation_type") or "")]
    by_dep: dict[str, dict] = {}
    for e in evs:
        d = deps.get(e["zone"], f"{e['zone']} {zone_name(e['zone'])}")
        by_dep.setdefault(d, {"n": 0, "zones": set()})
        by_dep[d]["n"] += 1
        by_dep[d]["zones"].add(e["zone"])
    rate = {}
    if has_model:
        ps: dict[str, float] = {}
        nh: dict[str, float] = {}
        for d in live_sessions():
            snaps = [m for m in read_jsonl(d / "session.json") if "person_seconds" in m]
            if not snaps:
                continue
            m = snaps[-1]                   # 누적값이 한 줄씩 쌓인다 — 마지막 줄이 그 세션의 합계
            for z, s in (m.get("person_seconds") or {}).items():
                ps[deps.get(z, z)] = ps.get(deps.get(z, z), 0) + s
            for z, s in (m.get("no_helmet_seconds") or {}).items():
                nh[deps.get(z, z)] = nh.get(deps.get(z, z), 0) + s
        rate = {d: 1 - nh.get(d, 0) / s for d, s in ps.items() if s > 0}
    return {"has_model": has_model, "by_dep": by_dep, "rate": rate, "n": len(evs)}
