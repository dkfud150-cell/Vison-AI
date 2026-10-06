"""
엔진 — 패키지를 읽어서 돈다. 특정 공정 · 시나리오를 모른다.

    ① 트리거      apply(신호)             신호 사전대로 사실 저장소에 넣는다
    ② 상황 인식    modes.evaluate_modes    규칙의 when → 지금 켜진 모드
    ③ 작업 전 게이트 gates.run_gates        문서가 들어오면 대조
    ④ 감지 · 판정  update_video + 판정표    영상 사실(검출 · 인원) + 판정표 rows
    ⑤ 기록 · 알림  EventLog                무음 기록 · 중복 억제 · 전후 클립

영상 없이도 돈다(run_scenario.py) — tick(시각)으로 시간만 흘려도 만료 같은 조건이 판정된다.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from . import modes as M
from .checks import check_hits
from .conditions import Ctx, evaluate
from .detector import Det, Persistence
from .events import EventLog
from .facts import FactStore, apply_signal
from .gates import GateResult, run_gates
from .judge import LEVELS, RANK, LevelState, eval_table, response
from .modes import expand_zones
from .signals import Signal


class Engine:
    def __init__(self, pkg, rules: dict, start: datetime, *, log: EventLog, scenario_dir: Path | None = None,
                 zones=None, detect_cfg: dict | None = None):
        self.pkg = pkg
        self.site = pkg.site
        self.signals = pkg.signals
        self.rules = rules
        self.now = start
        self.log = log
        self.scenario_dir = scenario_dir
        self.zones = zones                     # zones.Zones (영상일 때만)
        self.video_on = False
        self.video_t: float | None = None
        self.store = FactStore()
        self.levels: dict[tuple[str, str], LevelState] = {}
        self.mode_since: dict[tuple[str, str], datetime] = {}
        self.modes: dict[str, list] = {}
        self.gates: dict[str, list[GateResult]] = {}
        self.persons: list[Det] = []
        self.objects: dict[str, list[Det]] = {}
        self._dwell: dict[tuple, datetime] = {}
        dc = detect_cfg or pkg.detect
        pc = dc.get("persistence", {})
        self._pers_cfg = (pc.get("on_frames", 5), pc.get("off_frames", 15))
        self.persistence: dict[tuple[str, str], Persistence] = {}
        self.detect_polys = {"flame": dc.get("flame", {}).get("polygons", ["hazard"])}
        for x in dc.get("extra", []):
            self.detect_polys[x["name"]] = x.get("polygons", ["hazard", "work"])
        self.tables = {n: t for n, t in rules.get("judgments", {}).items() if not n.startswith("_")}
        self.table_zones = {n: expand_zones(t.get("zones", ["*"]), self.site) for n, t in self.tables.items()}

    def ctx(self, zone: str, **kw) -> Ctx:
        return Ctx(self, zone, self.now, **kw)

    # ================================================================== ① 트리거
    def apply(self, sig: Signal) -> list[str]:
        if sig.ts > self.now:
            self.now = sig.ts
        notes, docs = apply_signal(sig, self.signals, self.site, self.store, self.scenario_dir)
        spec = self.signals.get(sig.signal, {})
        if "reset" in spec and sig.zone:
            rs = spec["reset"]
            if evaluate(rs.get("if", True), self.ctx(sig.zone)).ok:
                n = 0
                for e in self.store.events:
                    if e.fact in rs.get("events", []) and e.zone == sig.zone and e.cleared_at is None and e.ts <= sig.ts:
                        e.cleared_at = sig.ts
                        n += 1
                if n:
                    notes.append(f"이전 {'/'.join(rs.get('events', []))} 기록 {n}건 해제")
        self._refresh_modes()
        for d in docs:
            for g in run_gates(d, sig.zone, self, self.now):
                self.gates.setdefault(sig.zone, []).append(g)
                notes.append(g.message)
                if g.blocked:
                    gd = next(x for x in self.rules.get("gates", []) if x["id"] == g.gate_id)
                    self.log.emit(kind="gate", ts=sig.ts, zone=sig.zone, mode=M.label_mode(self.modes.get(sig.zone, [])),
                                  violation_type=gd.get("violation", g.gate_id), level="작업 전 차단", alerted=True,
                                  reason="; ".join(g.problems), response=gd.get("response", ""), video_t=self.video_t,
                                  extra={"gate_id": g.gate_id})
        self.evaluate()
        if any(a.get("do") == "accident" for a in (spec["do"] if isinstance(spec.get("do"), list) else [spec])):
            notes += self._accident(sig)
        return notes

    def tick(self, now: datetime):
        """시간만 흐른다 (측정 만료 · 체류 시간 같은 조건이 여기서 판정된다)."""
        if now > self.now:
            self.now = now
        self.evaluate()

    def _accident(self, sig: Signal) -> list[str]:
        z = sig.zone
        for (zone, tname), ls in self.levels.items():
            if zone != z:
                continue
            thr = self.tables[tname].get("accident_prevented_at", "최고 경보")
            if RANK[ls.level] >= RANK[thr]:
                msg = (f"{ls.raised_at:%H:%M} {ls.level}({tname})로 작업이 멈춘 상태 — "
                       f"이 사고는 일어나지 않는다고 본다 (가정)")
                self.log.emit(kind="info", ts=sig.ts, zone=z, mode=None, violation_type="사고_예방", level=None,
                              alerted=False, reason=msg, video_t=self.video_t)
                return [msg]
        self.log.emit(kind="accident", ts=sig.ts, zone=z, mode=None, violation_type=sig.label or sig.signal,
                      level=None, alerted=False, reason=sig.note or "사고 발생", video_t=self.video_t)
        return ["사고 발생 — 기록"]

    # ================================================================== ② 모드
    def _refresh_modes(self):
        self.modes = M.evaluate_modes(self, self.now)

    # ================================================================== ④ 영상
    def update_video(self, now: datetime, video_t: float, persons: list[Det], objects: dict[str, list[Det]]):
        self.now, self.video_t, self.video_on = now, video_t, True
        self.persons, self.objects = persons, objects
        Z = self.zones
        people: dict[str, list[set[str]]] = {}
        for p in persons:
            p.polys = Z.locate(Z.ground_point(p.xyxy))
            by_zone: dict[str, set[str]] = {}
            for q in p.polys:
                by_zone.setdefault(q.zone, set()).add(q.type)
            for z, types in by_zone.items():
                people.setdefault(z, []).append(types)
        self.store.people = people
        for name, dets in objects.items():
            want = set(self.detect_polys.get(name, ["hazard"]))
            hit = set()
            for d in dets:
                d.polys = Z.locate(Z.center(d.xyxy))
                hit |= {q.zone for q in d.polys if q.type in want}
            for z in {q.zone for q in Z.polys if q.type in want}:
                g = self.persistence.setdefault((name, z), Persistence(*self._pers_cfg))
                on = g.update(z in hit)
                rec = self.store.detections.setdefault((name, z), {"on": False, "since": None, "last": None})
                if on and not rec["on"]:
                    rec["since"] = now
                if on:
                    rec["last"] = now
                rec["on"] = on
        self._refresh_modes()
        self._run_checks()
        self.evaluate()

    def _run_checks(self):
        now = self.now
        hit_keys = set()
        for zone in (self.zones.zones() if self.zones else []):
            active = self.modes.get(zone, [])
            names = {n for n, _ in active}
            for mname, m in M.mode_items(self.rules):
                if zone not in expand_zones(m.get("zones"), self.site):
                    continue
                is_on = mname in names
                for ck in m.get("checks", []):
                    if not is_on and not ck.get("shadow_when_off"):
                        continue
                    for key, detail, tid in check_hits(ck, zone, self):
                        dk = (zone, mname, ck["violation"], key)
                        hit_keys.add(dk)
                        first = self._dwell.setdefault(dk, now)
                        if (now - first).total_seconds() < ck.get("dwell_s", 0):
                            continue
                        self.log.emit(kind="check", ts=now, zone=zone, mode=mname if is_on else M.label_mode(active),
                                      violation_type=ck["violation"], level=ck.get("level", "주의"), alerted=is_on,
                                      reason=detail + ("" if is_on else f" · '{mname}' 모드가 꺼져 있어 무음 기록"),
                                      response=ck.get("response", ""), track_id=tid,
                                      dedup=(zone, ck["violation"], key), video_t=self.video_t,
                                      extra={"rule_mode": mname})
        for k in [k for k in self._dwell if k not in hit_keys]:
            self._dwell.pop(k)

    # ================================================================== ④ 판정표
    def evaluate(self):
        self._refresh_modes()
        for tname, table in self.tables.items():
            for z in self.table_zones[tname]:
                ls = self.levels.setdefault((z, tname), LevelState())
                res = eval_table(tname, table, self.ctx(z, raised_at=ls.raised_at))
                self._update_level(z, tname, table, ls, res)

    def _update_level(self, zone: str, tname: str, table: dict, ls: LevelState, res):
        ls.result = res
        cur, new = RANK[ls.level], RANK[res.level]
        if new > cur or (new == cur and new > 0 and res.violation != ls.violation):
            ls.level, ls.row, ls.violation = res.level, res.row, res.violation
            ls.raised_at, ls.lower_since = self.now, None
            ls.history.append((self.now, res.level, res.row))
            active = self.modes.get(zone, [])
            alerted = M.alerting(self.rules, active, tname)
            c = self.ctx(zone, axes=res.axes)
            present = evaluate(table["presence"], c).ok if "presence" in table else bool(self.store.people.get(zone))
            self.log.emit(kind="stage", ts=self.now, zone=zone, mode=M.label_mode(active), violation_type=res.violation,
                          level=res.level, alerted=alerted, reason=res.reason, row=res.row,
                          response=response(table, res.level, present),
                          axes={a.name: a.state for a in res.axes.values()}, video_t=self.video_t,
                          extra={"table": tname})
        elif new < cur:
            lw = table.get("lower", {})
            ls.lower_since = ls.lower_since or self.now
            hold = timedelta(minutes=float(lw.get("hold_min", 5)))
            ok = evaluate(lw.get("when", True), self.ctx(zone, axes=res.axes, raised_at=ls.raised_at)).ok
            if ok and self.now - ls.lower_since >= hold:
                ls.level = LEVELS[cur - 1]
                if RANK[res.level] == cur - 1:
                    ls.row, ls.violation = res.row, res.violation
                ls.lower_since = self.now
                ls.history.append((self.now, ls.level, ls.row))
        else:
            ls.lower_since = None

    # ================================================================== 화면 · 요약용
    def zone_level(self, zone: str) -> tuple[str, LevelState | None, str | None]:
        """그 구역의 판정표들 중 가장 높은 단계."""
        best, bl, bt = "정상", None, None
        for (z, t), ls in self.levels.items():
            if z == zone and (bl is None or RANK[ls.level] > RANK[best]):
                best, bl, bt = ls.level, ls, t
        return best, bl, bt

    def snapshot(self, zone: str) -> dict:
        active = self.modes.get(zone) or [(M.default_mode(self.rules), None)]
        tables = [(t, self.levels[(zone, t)]) for t in self.tables if (zone, t) in self.levels]
        return {"zone": zone, "now": self.now, "modes": active, "view": M.merged_view(self.rules, active),
                "tables": tables, "gates": self.gates.get(zone, []), "people": self.store.people.get(zone, []),
                "persistence": {n: g for (n, z), g in self.persistence.items() if z == zone}}
