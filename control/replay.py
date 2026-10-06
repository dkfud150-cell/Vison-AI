"""
재생 비교 — 시나리오는 시스템이 제대로 도는지 확인하는 도구다.

타임라인 CSV 를 규칙셋(variants)마다 엔진에 넣어 돌리고(monitor_engine runner.run_timeline),
결과를 시나리오에 적어 둔 기대 결과(expect)와 맞춰 본다. 규칙셋을 바꿨을 때 앞뒤를 나란히 본다.
기록은 control/records/replay/<시나리오>/<variant>/ 에 남지만 관제 기록(이벤트 로그 · 통계 · 피드백)에는 넣지 않는다.
결과를 문서 자동화로 넘기는 것은 사람이 고를 때만 한다(개정 전 사고를 조사표 초안으로 만들어 볼 때 등).
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from safety_monitor.judge import RANK
from safety_monitor.runner import check_expect, run_timeline

from .common import REPLAY_DIR, package

_cache: dict[str, dict] = {}


def scenario_keys() -> list[str]:
    return package().scenario_keys()


def run(key: str, force: bool = False) -> dict:
    pkg = package()
    stamp = str(pkg.root.stat().st_mtime) + key
    if not force and key in _cache and _cache[key]["stamp"] == stamp:
        return _cache[key]
    sc = pkg.scenario(key)
    vs = sc.variants() or {"기본 규칙": {"changes": []}}
    out_root = REPLAY_DIR / key
    if out_root.exists():
        shutil.rmtree(out_root, ignore_errors=True)
    variants = {}
    for name, v in vs.items():
        r = run_timeline(pkg, sc, v.get("changes", []), name, out_root / name.replace(" ", ""))
        checks = check_expect(r, v.get("expect", []))
        variants[name] = {"run": r, "changes": v.get("changes", []), "checks": checks, "out_dir": out_root / name.replace(" ", ""),
                          "summary": summarize(r)}
    res = {"key": key, "title": sc.title, "zone": sc.zone, "table": r["table"], "basis": sc.data.get("basis", ""),
           "variants": variants, "stamp": stamp, "times": _times(variants)}
    _cache[key] = res
    return res


def run_all(force: bool = False) -> dict[str, dict]:
    return {k: run(k, force) for k in scenario_keys()}


def score(res: dict) -> tuple[int, int]:
    ok = sum(1 for v in res["variants"].values() for c, _ in v["checks"] if c)
    n = sum(len(v["checks"]) for v in res["variants"].values())
    return ok, n


def summarize(r: dict) -> dict:
    """variant 하나의 한 줄 — 게이트가 막은 시각, 가장 높은 단계와 그 시각 · 줄, 사고."""
    rows = r["log"].rows
    gate = next((e for e in rows if e["kind"] == "gate"), None)
    acc = next((e for e in rows if e["kind"] == "accident"), None)
    prevented = next((e for e in rows if e["kind"] == "info" and e.get("violation_type") == "사고_예방"), None)
    best = None
    for t, st in sorted(r["states"].items()):
        if best is None or RANK[st["level"]] > RANK[best[1]["level"]]:
            best = (t, st)
    head = f"{gate['ts'][11:16]} 차단" if gate else (f"{best[0]} {best[1]['level']}" if best and best[1]["level"] != "정상" else "경보 없음")
    parts = []
    if gate:
        parts.append(f"작업 전 게이트 — {gate.get('reason', '')}")
    if best and best[1]["level"] != "정상":
        parts.append(f"가장 높은 단계 {best[1]['level']}({best[1]['row']}줄) · {best[0]}")
    if acc:
        parts.append(f"{acc['ts'][11:16]} 사고")
    elif prevented:
        parts.append("사고 없음 — 그 전에 작업이 멈춘다고 본다")
    return {"head": head, "text": " · ".join(parts) or "판정 변화 없음", "accident": bool(acc), "gate": bool(gate),
            "hot": bool(gate) or (not acc and bool(prevented))}


def _times(variants: dict) -> list[str]:
    ts = set()
    for v in variants.values():
        for tr in v["run"]["trace"]:
            ts.add(f"{tr['t']:%H:%M}")
    return sorted(ts)


def merged_rows(res: dict) -> list[dict]:
    """시각마다 한 줄 — 신호 · 입력, 그리고 variant 마다 그 시각의 판정(게이트면 '작업 전 차단')."""
    names = list(res["variants"])
    by_t: dict[str, dict] = {}
    for n in names:
        for tr in res["variants"][n]["run"]["trace"]:
            t = f"{tr['t']:%H:%M}"
            row = by_t.setdefault(t, {"t": t, "signals": "", "source": "", "cells": {}, "notes": []})
            if tr["signals"] and not row["signals"]:
                row["signals"] = " + ".join(s.note or s.short() for s in tr["signals"])
                row["source"] = "/".join(dict.fromkeys(s.source for s in tr["signals"]))
            gates = [e for e in tr["events"] if e["kind"] == "gate"]
            st = tr["state"]
            if gates:
                row["cells"][n] = ("gate", "작업 전 차단")
            else:
                ax = " · ".join(f"{k} {v}" for k, v in st["axes"].items())
                lab = st["level"] + (f" · {st['row']}줄" if st["row"] and st["level"] != "정상" else "")
                row["cells"][n] = (st["level"], f"{lab}  ({ax})" if ax else lab)
            if any(e["kind"] == "accident" for e in tr["events"]):
                row["cells"][n] = ("acc", "사고")
    return [by_t[t] for t in sorted(by_t)]


def state_at(res: dict, name: str, t: str) -> dict:
    """player 커서 시각의 상태 — 그 시각까지의 마지막 상태."""
    st = res["variants"][name]["run"]["states"]
    keys = [k for k in sorted(st) if k <= t]
    return st[keys[-1]] if keys else {"level": "정상", "row": None, "axes": {}, "modes": []}


def import_zip(path: str) -> str:
    """'+ 불러오기' — 시나리오 폴더를 zip 으로 받아 사업장 패키지 scenarios/ 에 푼다 (scenario.json · timeline.csv · 입력 문서)."""
    pkg = package()
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        sj = [n for n in names if n.endswith("scenario.json")]
        if not sj:
            raise ValueError("zip 안에 scenario.json 이 없다")
        prefix = sj[0][: -len("scenario.json")]
        key = Path(prefix.rstrip("/")).name or Path(path).stem
        dest = pkg.root / "scenarios" / key
        if dest.exists():
            raise ValueError(f"같은 이름의 시나리오가 이미 있다: {key}")
        for n in names:
            if not n.startswith(prefix) or ".." in n:
                continue
            rel = n[len(prefix):]
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(z.read(n))
    try:
        from safety_monitor.package import load_package
        load_package(pkg.root)          # 규격 검사 — 틀리면 되돌린다
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    from . import common
    common._stamp["t"] = 0                 # 패키지를 바로 다시 읽게
    return key
