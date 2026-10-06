"""
판정표 평가 — 패키지의 judgments 에 적힌 표를 그대로 돈다.

  axes : 축마다 상태 목록. 위에서부터 조건이 맞는 첫 상태가 그 축의 상태.
  rows : 판정 줄. 위에서부터 조건이 맞는 첫 줄에서 멈춘다 (통합 문서 4장 '판정 순서').
  lower: 내려갈 때 조건. 계산된 단계가 낮아져도 hold_min 동안 유지되고 when 이 맞아야 한 단계씩 내린다.

단계 이름은 네 개로 고정이다 — 정상 · 주의 · 경보 · 최고 경보.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .conditions import Ctx, evaluate

LEVELS = ["정상", "주의", "경보", "최고 경보"]
RANK = {lv: i for i, lv in enumerate(LEVELS)}


@dataclass
class AxisResult:
    name: str
    state: str
    tone: str
    why: list[str] = field(default_factory=list)
    why_not: list[str] = field(default_factory=list)


@dataclass
class TableResult:
    table: str
    zone: str
    axes: dict[str, AxisResult]
    level: str
    row: int | None
    violation: str | None
    reason: str


@dataclass
class LevelState:
    level: str = "정상"
    row: int | None = None
    violation: str | None = None
    raised_at: datetime | None = None
    lower_since: datetime | None = None
    result: TableResult | None = None
    history: list[tuple[datetime, str, int | None]] = field(default_factory=list)


def _tone(i: int, n: int) -> str:
    return "danger" if i == 0 else ("mute" if i == n - 1 else "warn")


def eval_table(name: str, table: dict, c: Ctx) -> TableResult:
    axes: dict[str, AxisResult] = {}
    c.axes = axes
    for ax in table.get("axes", []):
        misses: list[str] = []
        states = ax["states"]
        for i, st in enumerate(states):
            r = evaluate(st["when"], c)
            if r.ok:
                axes[ax["name"]] = AxisResult(ax["name"], st["state"], st.get("tone") or _tone(i, len(states)), r.ev, misses)
                break
            misses += r.why_not
        else:
            axes[ax["name"]] = AxisResult(ax["name"], "-", "mute", [], misses)
    for row in table.get("rows", []):
        r = evaluate(row["when"], c)
        if r.ok:
            ev = list(dict.fromkeys(r.ev))
            reason = " · ".join(([row["label"]] if row.get("label") else []) + ev)
            return TableResult(name, c.zone, axes, row["level"], row.get("row"), row.get("violation"), reason)
    d = table.get("default", {"level": "정상"})
    return TableResult(name, c.zone, axes, d.get("level", "정상"), d.get("row"), None, "")


def response(table: dict, level: str, present: bool) -> str:
    r = table.get("responses", {}).get(level)
    if not r:
        return ""
    if isinstance(r, str):
        return r
    return r.get("present" if present else "absent", "")
