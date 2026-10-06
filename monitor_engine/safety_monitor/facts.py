"""
사실 저장소 — 지금까지 들어온 신호가 남긴 것.

신호 사전(signals.json)의 do 종류대로 저장만 한다. 그것이 위험한지는 규칙(rules.json)이 정한다.
  on / off  켜진 상태와 켜져 있던 구간      (작업허가, 배기 정지, 퍼지 …)
  event     일어난 일 + 속성                (가연물 방출 hazard=fuel_gas …)
  measure   측정값                          (가스 측정 FG-01 0 …)
  mark      대상에 표시                     (맹판 설치 완료 FG-02 …)
  document  입력된 문서                     (격리 목록 CSV, 작업허가서 JSON)
  accident  사고
영상은 detections(검출 확정)과 people(폴리곤 안 사람)을 엔진이 채운다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .signals import Signal, read_csv


@dataclass
class OnRec:
    ts: datetime
    label: str


@dataclass
class EventRec:
    fact: str
    zone: str | None
    target: str | None
    ts: datetime
    label: str
    attrs: dict = field(default_factory=dict)
    cleared_at: datetime | None = None


@dataclass
class MeasureRec:
    fact: str
    zone: str | None
    target: str | None
    ts: datetime
    value: float
    label: str


class FactStore:
    def __init__(self):
        self.on: dict[tuple[str, str | None], OnRec] = {}
        self.intervals: dict[tuple[str, str | None], list[list]] = {}
        self.events: list[EventRec] = []
        self.measures: list[MeasureRec] = []
        self.marks: dict[str, dict[str, datetime]] = {}
        self.documents: dict[tuple[str, str | None], dict] = {}
        self.detections: dict[tuple[str, str], dict] = {}
        self.people: dict[str, list[set[str]]] = {}
        self.accidents: list[Signal] = []
        self.labels: dict[str, str] = {}
        self.history: list[Signal] = []


def zone_of_target(site: dict, target: str | None) -> str | None:
    """대상 ID(배관 FG-01 등) → site.json 참조 목록에서 그 대상이 있는 구역."""
    if not target:
        return None
    for ref in site.get("references", {}).values():
        for z, items in ref.items():
            if z.startswith("_") or not isinstance(items, list):
                continue
            if any(str(i.get("id")) == target for i in items):
                return z
    return None


def ref_item(site: dict, ref: str, zone: str | None, target: str | None) -> dict | None:
    for i in site.get("references", {}).get(ref, {}).get(zone or "", []) or []:
        if str(i.get("id")) == target:
            return i
    return None


def actions_of(spec: dict) -> list[dict]:
    do = spec.get("do")
    return do if isinstance(do, list) else [spec]


def apply_signal(sig: Signal, signals: dict, site: dict, store: FactStore, scenario_dir: Path | None) -> tuple[list[str], list[str]]:
    """
    신호 한 건을 저장소에 넣는다. (메모, 들어온 문서 이름들) 을 돌려준다.
    신호 사전에 없는 신호는 같은 이름의 event 로 남긴다 — 규칙이 {"event": 이름} 으로 쓸 수 있다.
    """
    notes: list[str] = []
    docs: list[str] = []
    spec = signals.get(sig.signal)
    if spec is None:
        spec = {"label": sig.signal, "do": "event", "fact": sig.signal}
        notes.append(f"신호 사전에 없는 신호 '{sig.signal}' — event 로 기록")
    sig.label = spec.get("label", sig.signal)
    sig.zone = sig.zone or zone_of_target(site, sig.target)
    z = sig.zone
    store.history.append(sig)

    for a in actions_of(spec):
        do, fact = a.get("do"), a.get("fact")
        if fact:
            store.labels.setdefault(fact, sig.label)
        if do == "on":
            if (fact, z) not in store.on:
                store.on[(fact, z)] = OnRec(sig.ts, sig.label)
                store.intervals.setdefault((fact, z), []).append([sig.ts, None])
        elif do == "off":
            store.on.pop((fact, z), None)
            iv = store.intervals.get((fact, z))
            if iv and iv[-1][1] is None:
                iv[-1][1] = sig.ts
                notes.append(f"{sig.label} — 켜져 있던 시간 {(sig.ts - iv[-1][0]).total_seconds() / 60:.0f}분")
        elif do == "event":
            attrs: dict = {}
            for src in a.get("attrs_from", []):
                if src == "zone":
                    attrs.update({k: v for k, v in site.get("zones", {}).get(z, {}).items() if k != "name"})
                elif src.startswith("ref:"):
                    item = ref_item(site, src[4:], z, sig.target)
                    if item:
                        attrs.update({k: v for k, v in item.items() if k not in ("id", "name")})
            attrs.update(a.get("attrs", {}))
            store.events.append(EventRec(fact, z, sig.target, sig.ts, sig.label, attrs))
        elif do == "measure":
            try:
                v = float(sig.value)
            except (TypeError, ValueError):
                notes.append(f"측정값이 숫자가 아님: {sig.value!r} — 무시")
                continue
            store.measures.append(MeasureRec(fact, z, sig.target, sig.ts, v, sig.label))
            sig.extra["measure"] = True
        elif do == "mark":
            store.marks.setdefault(fact, {})[sig.target] = sig.ts
        elif do == "unmark":
            store.marks.get(fact, {}).pop(sig.target, None)
        elif do == "document":
            store.documents[(fact, z)] = load_document(sig, scenario_dir)
            docs.append(fact)
        elif do == "accident":
            store.accidents.append(sig)
        else:
            notes.append(f"알 수 없는 do: {do}")
    return notes, docs


def load_document(sig: Signal, scenario_dir: Path | None) -> dict:
    """신호 값에 적힌 파일(CSV · JSON)을 시나리오 폴더에서 읽는다."""
    name = sig.value or ""
    cands = [Path(name)] + ([scenario_dir / name] if scenario_dir else [])
    path = next((p for p in cands if p.exists()), None)
    if path is None:
        raise FileNotFoundError(f"문서 파일이 없습니다: {name} (시나리오 폴더에 두세요)")
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else [data]
    else:
        rows = read_csv(path)
        data = None
    return {"rows": rows, "data": data if isinstance(data, dict) else (rows[0] if rows else {}),
            "ts": sig.ts, "name": path.name, "label": sig.label}
