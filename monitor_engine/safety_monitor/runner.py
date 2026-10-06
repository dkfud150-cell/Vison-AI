"""
타임라인 실행 — 시나리오의 신호를 시각 순서대로 엔진에 넣고, 1분씩 시간을 흘린다.
시나리오에 기대 결과(expect)가 있으면 대조한다.

영상 없이 돈다. 신호가 없는 분에도 판정을 다시 해서, 측정 만료처럼 시간이 지나서 바뀌는 조건을 잡는다.
"""
from __future__ import annotations

import csv
import unicodedata
from datetime import timedelta
from pathlib import Path

from .engine import Engine
from .events import EventLog
from .judge import RANK
from .package import Package, PackageError, Scenario


def run_timeline(pkg: Package, sc: Scenario, changes: list[str], label: str, out_dir: Path,
                 step_min: int = 1, zone: str | None = None, table: str | None = None) -> dict:
    rules = pkg.rules(changes)
    rules["_label"] = label
    zone = zone or sc.zone
    table = table or sc.data.get("table") or next((t for t in rules.get("judgments", {}) if not t.startswith("_")), None)
    tl = sc.timeline()
    if not tl:
        raise PackageError(f"{sc.key}: 타임라인이 비었다")
    log = EventLog(out_dir, rules, quiet=True)
    eng = Engine(pkg, rules, tl[0].ts, log=log, scenario_dir=sc.dir)
    t, end = tl[0].ts.replace(second=0), tl[-1].ts
    i, prev = 0, None
    states: dict[str, dict] = {}
    trace: list[dict] = []
    while t <= end:
        sigs = []
        while i < len(tl) and tl[i].ts <= t:
            sigs.append(tl[i])
            i += 1
        n0 = len(log.rows)
        notes: list[str] = []
        for s in sigs:
            notes += eng.apply(s)
        eng.tick(t)
        ls = eng.levels.get((zone, table))
        axes = dict(ls.result.axes) if ls and ls.result else {}
        st = {"level": ls.level if ls else "정상", "row": ls.row if ls else None,
              "axes": {k: a.state for k, a in axes.items()}, "zone_max": eng.zone_level(zone)[0],
              "modes": [n for n, _ in eng.modes.get(zone, [])]}
        states[f"{t:%H:%M}"] = st
        new = log.rows[n0:]
        if sigs or (st["level"], st["row"]) != prev or new:
            trace.append({"t": t, "signals": sigs, "state": st, "axes": axes, "notes": notes, "events": new,
                          "reason": ls.result.reason if ls and ls.result else ""})
        prev = (st["level"], st["row"])
        t += timedelta(minutes=step_min)
    save_trace_csv(trace, out_dir / "trace.csv")
    return {"engine": eng, "rules": rules, "label": label, "zone": zone, "table": table,
            "states": states, "trace": trace, "log": log}


# ---------------------------------------------------------------------- 기대 결과
def check_expect(run: dict, expect: list[dict]) -> list[tuple[bool, str]]:
    """
    expect 항목 (scenario.json):
      {"at": "09:15", "level": "최고 경보", "row": 2}   그 분의 판정 단계(와 줄)
      {"at": "08:40", "axis": {"발생": "가능"}}          그 분의 축 상태
      {"at": "08:05", "gate": "게이트 id"}               그 분에 게이트가 막았다
      {"at": "09:22", "accident": false}                 그 분에 사고가 났다 / 안 났다
      {"before": "09:15", "max_level": "정상"}           그 시각 전까지 이 단계를 넘지 않았다
    """
    out = []
    states, rows = run["states"], run["log"].rows
    for ex in expect:
        if "before" in ex:
            worst = max(((k, v) for k, v in states.items() if k < ex["before"]),
                        key=lambda kv: RANK[kv[1]["level"]], default=None)
            ok = worst is None or RANK[worst[1]["level"]] <= RANK[ex["max_level"]]
            out.append((ok, f"{ex['before']} 이전 최고 단계 ≤ {ex['max_level']}"
                        + ("" if ok else f" · 실제 {worst[0]} {worst[1]['level']}")))
            continue
        at = ex["at"]
        st = states.get(at)
        if st is None:
            out.append((False, f"{at} — 타임라인 시간 밖"))
            continue
        if "level" in ex:
            ok = st["level"] == ex["level"] and ("row" not in ex or st["row"] == ex["row"])
            want = ex["level"] + (f"({ex['row']}줄)" if "row" in ex else "")
            out.append((ok, f"{at} {want}" + ("" if ok else f" · 실제 {st['level']}({st['row']}줄)")))
        for k, v in ex.get("axis", {}).items():
            ok = st["axes"].get(k) == v
            out.append((ok, f"{at} {k} = {v}" + ("" if ok else f" · 실제 {st['axes'].get(k)}")))
        if "gate" in ex:
            ok = any(e["kind"] == "gate" and e.get("gate_id") == ex["gate"] and e["ts"][11:16] == at for e in rows)
            out.append((ok, f"{at} 게이트 {ex['gate']} 차단" + ("" if ok else " · 차단 안 됨")))
        if "accident" in ex:
            hit = any(e["kind"] == "accident" and e["ts"][11:16] == at for e in rows)
            ok = hit == ex["accident"]
            out.append((ok, f"{at} 사고 {'발생' if ex['accident'] else '없음'}" + ("" if ok else f" · 실제 {'발생' if hit else '없음'}")))
    return out


# ---------------------------------------------------------------------- 출력
def _dw(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def _pad(s, w: int) -> str:
    s = str(s)
    while _dw(s) > w:
        s = s[:-1]
    return s + " " * (w - _dw(s))


def print_trace(run: dict, pkg: Package):
    table = pkg.rules_base.get("judgments", {}).get(run["table"], {})
    ax_names = [a["name"] for a in table.get("axes", [])]
    W = [6, 36] + [8] * len(ax_names) + [6, 12]
    print("  ".join(_pad(h, w) for h, w in zip(["시각", "신호"] + ax_names + ["줄", "판정"], W)))
    print("-" * (sum(W) + 2 * len(W)))
    for r in run["trace"]:
        sig = " + ".join(s.short() for s in r["signals"]) or "(시간 경과)"
        gates = [e for e in r["events"] if e["kind"] == "gate"]
        st = r["state"]
        cells = [f"{r['t']:%H:%M}", sig] + [st["axes"].get(a, "-") for a in ax_names]
        cells += ["게이트", "작업 전 차단"] if gates else [st["row"] or "", st["level"]]
        print("  ".join(_pad(x, w) for x, w in zip(cells, W)))
        for n in r["notes"]:
            print(" " * 8 + f"└ {n}")
        if gates:
            print(" " * 8 + "└ (아래는 게이트를 무시하고 그대로 진행했다고 가정 — 2차 방어)")


def save_trace_csv(trace: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    ax_names = list(dict.fromkeys(k for r in trace for k in r["state"]["axes"]))
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["시각", "신호", "입력"] + ax_names + ["줄", "판정", "모드", "근거", "메모"])
        for r in trace:
            st = r["state"]
            w.writerow([f"{r['t']:%H:%M}", " + ".join(s.short() for s in r["signals"]),
                        "/".join(dict.fromkeys(s.source for s in r["signals"]))]
                       + [st["axes"].get(a, "") for a in ax_names]
                       + [st["row"] or "", st["level"], " · ".join(st["modes"]), r["reason"], " / ".join(r["notes"])])
