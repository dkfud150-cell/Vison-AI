"""
위험성평가 — 숫자 계산 부분 (LLM 없음)

  aggregate_events()    구역 × 모드 × 위반 유형별 건수
  calc_risk()           건수 → 가능성(1~5), 위반 유형 → 중대성(1~4), 곱 = 위험도
  check_adhoc_review()  기준 초과 시 수시평가 제안
  measure_effect()      대책 적용일 전후 위반 건수로 개선 후 위험도를 '실측'한다

숫자는 전부 여기서 나온다. LLM은 이 값을 읽기만 하고 바꾸지 못한다.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

TOP_ALERT = "최고 경보"


def row_key(r: dict) -> str:
    return f"{r['zone']}|{r['mode']}|{r['violation_type']}"


def aggregate_events(events: list[dict], as_of: datetime, scales: dict) -> list[dict]:
    """
    최근 window_days(90일) 동안의 위반을 구역 × 모드 × 위반 유형으로 묶는다.

    세는 것 / 빼는 것
    - 무음(섀도) 기록(alerted=False)은 뺀다. 그 모드에서는 위반이 아니라 통행이기 때문이다.
    - 오탐 표시(false_positive=True)는 뺀다.
    - 강화 기간(adj_id 있음)에 잡힌 건은 따로 센다. 감시가 민감해진 기간이라 같은 기준으로
      세면 가능성이 부풀기 때문이다 (피드백 루프 '자기강화 폭주' 방지).
    - 최고 경보 건수는 따로 센다 → 가능성 하한 규칙에 쓴다.
    """
    start = as_of - timedelta(days=scales["window_days"])
    recent_start = as_of - timedelta(days=scales["recent_days"])

    groups: dict[tuple, dict] = defaultdict(lambda: {
        "base_count": 0, "adj_count": 0, "recent_count": 0, "top_alert_count": 0,
        "event_ids": [], "adj_event_ids": [], "silent_count": 0, "false_positive_count": 0,
    })

    for e in events:
        t = e["_ts"]
        if not (start <= t <= as_of):
            continue
        g = groups[(e["zone"], e["mode"], e["violation_type"])]
        if not e.get("alerted", True):
            g["silent_count"] += 1
            continue
        if e.get("false_positive"):
            g["false_positive_count"] += 1
            continue
        if e.get("level") == TOP_ALERT:
            g["top_alert_count"] += 1
        if e.get("adj_id"):
            g["adj_count"] += 1
            g["adj_event_ids"].append(e["event_id"])
            continue
        g["base_count"] += 1
        g["event_ids"].append(e["event_id"])
        if t >= recent_start:
            g["recent_count"] += 1

    rows = []
    for (zone, mode, vtype), g in groups.items():
        if g["base_count"] == 0 and g["adj_count"] == 0:
            continue  # 무음 기록·오탐만 있는 조합은 평가 대상이 아니다
        rows.append({"zone": zone, "mode": mode, "violation_type": vtype, **g,
                     "window_from": start.isoformat(timespec="minutes"),
                     "window_to": as_of.isoformat(timespec="minutes")})
    return rows


def likelihood_level(count: float, scales: dict) -> tuple[int, str]:
    for step in scales["likelihood_steps"]:
        limit = step["max_count"]
        if limit is None or count <= limit:
            return step["level"], step["label"]
    last = scales["likelihood_steps"][-1]
    return last["level"], last["label"]


def severity_level(violation_type: str, scales: dict, mode: str | None = None) -> tuple[int, str]:
    """위반 유형별 중대성. 모드별 하한(산세 구역 화기 = 3)이 있으면 올린다."""
    s = scales["severity_by_violation"].get(violation_type, scales["severity_default"])
    floor = scales.get("severity_floor_by_mode", {}).get(mode) if mode else None
    if isinstance(floor, int):
        s = max(s, floor)
    return s, scales["severity_labels"][str(s)]


def grade_of(score: int, scales: dict) -> dict:
    for g in scales["grades"]:
        if score <= g["max_score"]:
            return g
    return scales["grades"][-1]


def calc_risk(rows: list[dict], scales: dict, accidents: list[dict] | None = None) -> list[dict]:
    """
    가능성 × 중대성 = 위험도 (1~20).
    - 가능성: 기본 규칙으로 잡힌 90일 건수. 강화 기간에만 잡혔으면 1건으로 본다.
    - 하한: 최고 경보 1건 → 최소 4, 이 조합의 이벤트가 사고와 이어졌으면 → 5.
      (처음 일어난 큰 일이 '가능성 1'로 기록되는 것을 막는다)
    """
    floor_cfg = scales.get("likelihood_floor", {})
    acc_events = {}
    for a in accidents or []:
        for eid in a.get("event_ids", []):
            acc_events[eid] = a["id"]

    out = []
    for r in rows:
        count = r["base_count"] or (1 if r["adj_count"] else 0)
        L, L_label = likelihood_level(count, scales)
        floor_note = ""
        if r["top_alert_count"] and L < floor_cfg.get("top_alert", 4):
            L = floor_cfg.get("top_alert", 4)
            floor_note = f"최고 경보 {r['top_alert_count']}건 → 하한 {L}"
        linked = sorted({acc_events[e] for e in r["event_ids"] + r["adj_event_ids"] if e in acc_events})
        if linked and L < floor_cfg.get("accident", 5):
            L = floor_cfg.get("accident", 5)
            floor_note = f"사고 {', '.join(linked)} 와 이어짐 → 하한 {L}"
        if floor_note:
            L_label = f"{L_label} · {floor_note}"
        S, S_label = severity_level(r["violation_type"], scales, r["mode"])
        score = L * S
        g = grade_of(score, scales)
        out.append({**r, "count_used": count, "accident_ids": linked,
                    "likelihood": L, "likelihood_label": L_label,
                    "severity": S, "severity_label": S_label,
                    "score": score, "grade": g["label"], "grade_action": g["action"]})
    out.sort(key=lambda x: (-x["score"], -x["severity"], x["zone"]))
    return out


def check_adhoc_review(rows: list[dict], scales: dict) -> list[dict]:
    """
    수시평가 제안 대상 (사업장 위험성평가에 관한 지침 제15조제2항의 수시평가로 이어진다).
    - 위험도가 기준(12) 이상
    - 중대성 최고 등급(4) 위반이 1건이라도 있음 → 통계를 기다리지 않는다
    """
    cfg = scales["adhoc_review"]
    alerts = []
    for r in rows:
        reasons = []
        if r["score"] >= cfg["score_at_least"]:
            reasons.append(f"위험도 {r['score']} ≥ {cfg['score_at_least']}")
        if r["severity"] >= cfg["severity_at_least"]:
            reasons.append(f"중대성 {r['severity']}등급 위반 발생")
        if reasons:
            alerts.append({"zone": r["zone"], "mode": r["mode"],
                           "violation_type": r["violation_type"],
                           "score": r["score"], "reasons": reasons})
    return alerts


def measure_effect(row: dict, applied: datetime, events: list[dict], as_of: datetime,
                   scales: dict) -> dict:
    """
    개선 후 위험도 '실측'. 예측하지 않는다.
    대책 적용일(=위험성평가 확정일) 이후 기간과, 그 직전 같은 길이 기간의 위반 건수를 비교한다.
    적용 후 기간이 min_days(14일)보다 짧으면 '측정 중'으로 돌려준다.
    """
    min_days = scales.get("effect_measure", {}).get("min_days", 14)
    days = (as_of - applied).total_seconds() / 86400
    if days < min_days:
        return {"status": "측정 중", "days": max(0, int(days)), "min_days": min_days,
                "text": f"측정 중 — 적용 후 {max(0, int(days))}일 / {min_days}일"}
    n = min(days, scales["window_days"])

    def count(a, b):
        return sum(1 for e in events
                   if e["zone"] == row["zone"] and e["mode"] == row["mode"]
                   and e["violation_type"] == row["violation_type"]
                   and e.get("alerted", True) and not e.get("false_positive") and not e.get("adj_id")
                   and a <= e["_ts"] < b)

    before = count(applied - timedelta(days=n), applied)
    after = count(applied, applied + timedelta(days=n))
    per90 = after * scales["window_days"] / n          # 척도는 90일 건수 기준이라 환산한다
    L, _ = likelihood_level(round(per90), scales)
    S = row["severity"]
    g = grade_of(L * S, scales)
    change = "" if before == 0 else f" ({(after - before) / before:+.0%})"
    return {"status": "측정 완료", "days": int(n), "before": before, "after": after,
            "likelihood": L, "severity": S, "score": L * S, "grade": g["label"],
            "text": f"적용 전 {int(n)}일 {before}건 → 적용 후 {after}건{change} · 위험도 {L * S} {g['label']}"}


def correction_deadline_date(severity: int, issued: datetime, scales: dict) -> str:
    """조치 기한 날짜 (YYYY-MM-DD) — 의무 이행 관리 화면이 쓴다."""
    days = scales["correction_deadline_days"].get(str(severity), 7)
    return (issued + timedelta(days=days)).strftime("%Y-%m-%d")


def correction_deadline(severity: int, issued: datetime, scales: dict) -> str:
    days = scales["correction_deadline_days"].get(str(severity), 7)
    if days == 0:
        return f"{issued:%Y-%m-%d} 당일 즉시"
    return f"{(issued + timedelta(days=days)):%Y-%m-%d}까지 ({days}일 이내)"
