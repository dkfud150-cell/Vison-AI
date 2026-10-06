"""
모드 판정 — 규칙의 modes 에 적힌 when 조건으로 지금 어떤 작업 상황인지 정한다.

  when   : 조건어 (예: {"fact": "ptw"} — 작업허가가 켜져 있으면)
  zones  : 이 모드가 적용되는 구역 ("*" = 전 구역)
  scope  : all  = zones 중 한 곳에서라도 when 이 맞으면 zones 전체에 켜짐
           zone = when 이 맞는 구역에만 켜짐
  judge  : 이 모드가 켜지면 경보를 울리는 판정표 이름들 (꺼져 있으면 판정은 무음 기록)
  default: 다른 모드가 하나도 없을 때의 모드 (평상시)
여러 모드가 동시에 켜질 수 있다.
"""
from __future__ import annotations

from datetime import datetime

from .conditions import Ctx, evaluate


def mode_items(rules: dict):
    return [(n, m) for n, m in rules.get("modes", {}).items() if not n.startswith("_")]


def default_mode(rules: dict) -> str:
    return next((n for n, m in mode_items(rules) if m.get("default")), "평상시")


def expand_zones(zs, site: dict) -> list[str]:
    zs = zs or []
    return list(site.get("zones", {})) if "*" in zs else list(zs)


def evaluate_modes(eng, now: datetime) -> dict[str, list[tuple[str, datetime | None]]]:
    rules, site = eng.rules, eng.site
    active: dict[str, list[tuple[str, datetime]]] = {z: [] for z in site.get("zones", {})}
    for name, m in mode_items(rules):
        if m.get("default"):
            continue
        if "enabled" in m and not Ctx(eng, "", now).val(m["enabled"]):
            continue
        zones = expand_zones(m.get("zones"), site)
        when = m.get("when", False)
        if m.get("scope", "zone") == "all":
            on_zones = zones if any(evaluate(when, Ctx(eng, z, now)).ok for z in zones) else []
        else:
            on_zones = [z for z in zones if evaluate(when, Ctx(eng, z, now)).ok]
        for z in zones:
            key = (name, z)
            if z in on_zones:
                since = eng.mode_since.setdefault(key, now)
                active.setdefault(z, []).append((name, since))
            else:
                eng.mode_since.pop(key, None)
    dm = default_mode(rules)
    return {z: (sorted(v, key=lambda x: x[1]) or [(dm, None)]) for z, v in active.items()}


def label_mode(active: list) -> str:
    """이벤트에 적을 모드 — 가장 나중에 켜진 모드."""
    return active[-1][0] if active else "평상시"


def alerting(rules: dict, active: list, table: str) -> bool:
    modes = rules.get("modes", {})
    for n, _ in active:
        j = modes.get(n, {}).get("judge")
        if j is True or j == "*" or (isinstance(j, list) and table in j):
            return True
    return False


def active_poly_types(rules: dict, active: list, present: set[str]) -> set[str]:
    """화면 표시용 — 지금 켜진 폴리곤 종류.

    hazard 는 설비 때문에 상시 위험이라 늘 켜진다. 나머지(hazard_repair · work · restricted)는
    기본 모드(평상시)가 아닌 모드가 그 구역에 켜져 있을 때만 켜진다 — 평상시에 좁고
    작업 중에 넓어지는 그림이 여기서 나온다. 모드에 "polygons": ["hazard_repair"] 처럼
    적어 두면 그 종류만 켠다. 안 적으면 켜진 모드가 있을 때 전부 켜진다.
    판정이 아니라 그리기에만 쓴다 — 경보 여부는 modes.judge 가 정한다.
    """
    out = {t for t in present if t == "hazard"}
    on = [n for n, since in active if since is not None]
    if not on:
        return out
    modes = rules.get("modes", {})
    for n in on:
        p = modes.get(n, {}).get("polygons")
        out |= set(p) if p else present   # 안 적은 모드는 전부 켠다
    return out


def merged_view(rules: dict, active: list) -> dict:
    """화면 표시용 — 켜진 모드들의 PPE · 규칙 메모를 합친다."""
    modes = rules.get("modes", {})
    ppe, notes = [], []
    for n, _ in active:
        m = modes.get(n, {})
        ppe += [p for p in m.get("ppe", []) if p not in ppe]
        notes += [x for x in m.get("notes", []) if x not in notes]
    return {"ppe": ppe, "notes": notes}
