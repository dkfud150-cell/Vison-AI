"""
영상 규칙 — 모드가 켜져 있을 때 영상으로 보는 규칙 (모드의 checks).

종류 (checks[].type):
  no_entry    : polygons 안에 사람이 있다                     — 배관 랙 하부 진입
  min_persons : polygons 안 인원이 min 보다 적다 (0명은 제외) — 2인 1조, 화재감시자
  max_persons : polygons 안 인원이 max 보다 많다              — 인원 상한
공통: when (조건어 — 맞을 때만 본다), dwell_s (그만큼 이어져야 위반), level, violation,
      shadow_when_off (모드가 꺼져 있어도 무음 기록으로 남긴다)
새 종류가 필요하면 CHECK_TYPES 에 함수 하나를 더한다.
"""
from __future__ import annotations

from .conditions import Ctx, count_people, evaluate


def _types(ck: dict) -> set[str]:
    p = ck.get("polygons", ["work"])
    return set(p if isinstance(p, list) else [p])


def _no_entry(ck, zone, eng):
    out = []
    want = _types(ck)
    for p in eng.persons:
        polys = [q for q in p.polys if q.type in want and q.zone == zone]
        if polys:
            key = p.track_id if p.track_id is not None else "-"
            out.append((key, f"{polys[0].label} 안에 사람" + (f" #{p.track_id}" if p.track_id is not None else ""), p.track_id))
    return out


def _min_persons(ck, zone, eng):
    n = count_people(eng.store, zone, sorted(_types(ck)))
    if 0 < n < ck["min"]:
        return [("zone", f"{zone} {'/'.join(sorted(_types(ck)))} {n}명 < {ck['min']}명", None)]
    return []


def _max_persons(ck, zone, eng):
    n = count_people(eng.store, zone, sorted(_types(ck)))
    if n > ck["max"]:
        return [("zone", f"{zone} {'/'.join(sorted(_types(ck)))} {n}명 > {ck['max']}명", None)]
    return []


CHECK_TYPES = {"no_entry": _no_entry, "min_persons": _min_persons, "max_persons": _max_persons}


def check_hits(ck: dict, zone: str, eng) -> list[tuple]:
    if "when" in ck and not evaluate(ck["when"], Ctx(eng, zone, eng.now)).ok:
        return []
    return CHECK_TYPES[ck["type"]](ck, zone, eng)
