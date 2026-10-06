"""
관제 공통 — 경로 · 설정 · 사업장 패키지 · 시계 · 관제 이벤트 읽기.

관제 이벤트 = 예시 기록(예시데이터_삭제가능/문서자동화/events.json — 도입 전 관제 기록처럼 쓴다. 폴더를 지우면 빠진다)
            + 실시간 세션이 쌓은 기록(control/records/live/<세션>/events.jsonl).
재생 비교의 기록은 넣지 않는다 — 시나리오는 시스템을 검증하는 도구이고 현장 기록이 아니다.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

from . import ROOT

CONTROL_DIR = ROOT / "control"
RECORD_DIR = CONTROL_DIR / "records"
LIVE_DIR = RECORD_DIR / "live"
REPLAY_DIR = RECORD_DIR / "replay"
DOCGEN_DIR = ROOT / "docgen"
ENGINE_DIR = ROOT / "monitor_engine"

LEVEL_KIND = {"최고 경보": "crit", "경보": "warn", "주의": "note", "정상": "ok", None: "mute", "": "mute"}
LEVEL_DOT = {"최고 경보": "🔴", "경보": "🟠", "주의": "🟡", "정상": "🟢"}
DETECT_KINDS = {"stage", "check"}


def load_config() -> dict:
    return json.loads((CONTROL_DIR / "config.json").read_text(encoding="utf-8"))


def sample_root() -> Path:
    """기능 확인용 예시 데이터 폴더 (문서 자동화와 같은 곳). 지우면 예시 없이 돈다."""
    from safety_docs.config import SAMPLE_ROOT
    return SAMPLE_ROOT


class PackageMissing(RuntimeError):
    pass


def package_candidates(name: str) -> list[Path]:
    p = Path(name)
    if not p.is_absolute():
        p = ROOT / p
    return [p, ENGINE_DIR / "packages" / name, sample_root() / "사업장패키지" / name]


def package_dir() -> Path:
    """
    사업장 패키지 폴더. control/config.json 의 package 가 경로면 그대로, 이름이면
    monitor_engine/packages/<이름> (실제 패키지를 넣는 곳) → 예시데이터_삭제가능/사업장패키지/<이름> 순서로 찾는다.
    """
    name = load_config().get("package", "steel_pickling")
    for p in package_candidates(name):
        if (p / "site.json").exists():
            return p.resolve()
    raise PackageMissing(
        f"사업장 패키지 '{name}' 를 찾지 못했다. 실제 패키지(site.json · rules.json · signals.json …)를 "
        f"monitor_engine/packages/<이름>/ 에 넣고 control/config.json 의 package 에 그 이름을 적는다. "
        f"찾아본 곳: {', '.join(str(x) for x in package_candidates(name))}")


def dashboard() -> dict:
    """패키지의 dashboard.json — 시연 기본값(demo) · 부서 대응(departments). 없으면 빈 값."""
    p = package_dir() / "dashboard.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def setup_env():
    """문서 자동화가 같은 사업장 패키지(구역 이름 · 배관 계통도)를 읽게 한다. 폴더 맨 위 app.py 가 먼저 부른다."""
    os.environ.setdefault("SITE_PACKAGE", str(package_dir()))


@lru_cache(maxsize=1)
def _pkg_cached(path: str, stamp: float):
    from safety_monitor.package import load_package
    return load_package(path)


_stamp = {"t": 0.0, "d": None, "v": 0.0, "bump": 0}


def package():
    """사업장 패키지. 파일이 바뀌면 다시 읽는다 (시나리오를 불러오거나 규칙을 고친 뒤 — 2초 안에 반영)."""
    import time
    d = package_dir()
    if _stamp["d"] != str(d) or time.time() - _stamp["t"] > 2:
        files = list(d.rglob("*.json")) + list(d.rglob("*.csv"))
        _stamp.update(d=str(d), t=time.time(),
                      v=max((p.stat().st_mtime for p in files), default=0) + len(files) * 1e-6 + _stamp["bump"])
    return _pkg_cached(str(d), _stamp["v"])


def package_changed():
    """화면에서 패키지 파일을 고친 직후 — 2초를 기다리지 않고 다음 package() 가 다시 읽게 한다 (파일을 지운 경우도)."""
    _stamp["bump"] += 1
    _stamp["t"] = 0.0


def zone_name(zone: str | None) -> str:
    if not zone:
        return ""
    return package().site.get("zones", {}).get(zone, {}).get("name", zone)


def zones() -> list[str]:
    return [z for z in package().site.get("zones", {}) if not z.startswith("_")]


def demo_day() -> date:
    from safety_docs.config import load_profile
    d = load_profile().get("demo_today")
    return date.fromisoformat(d) if d else date.today()


def system_now() -> datetime:
    """관제의 '지금' — 실시간 세션이 돌고 있으면 그 시연 시계, 아니면 문서 자동화의 시계(demo_today + 지금 시각)."""
    from .session import SESSION
    t = SESSION.clock()
    if t is not None:
        return t
    from safety_docs.config import now
    return now()


def read_jsonl(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue            # 쓰는 중에 끊긴 마지막 줄 — 다음 번에 읽힌다
    return out


def append_jsonl(path: Path, row: dict) -> dict:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return row


def _naive(ts: str) -> datetime:
    t = datetime.fromisoformat(str(ts))
    return t.replace(tzinfo=None) if t.tzinfo else t


def live_sessions() -> list[Path]:
    return sorted(p for p in LIVE_DIR.iterdir() if p.is_dir()) if LIVE_DIR.exists() else []


def load_control_events(include_sample: bool = True) -> list[dict]:
    """
    관제 이벤트 전부 (게이트 · 사고 · 참고 포함). 각 줄에 붙이는 것:
      _ts   시각(datetime) · _src  출처(샘플 · 세션 이름) · _base  프레임 · 클립 경로의 기준 폴더
    오탐 표시(문서 자동화 records/false_positive_marks.jsonl)를 덮어 읽는다.
    """
    from safety_docs.config import SAMPLE_DIR, false_positive_marks, use_sample_data
    out: list[dict] = []
    if include_sample and use_sample_data() and (SAMPLE_DIR / "events.json").exists():
        data = json.loads((SAMPLE_DIR / "events.json").read_text(encoding="utf-8"))
        for e in data["events"]:
            out.append({**e, "kind": e.get("kind") or ("stage" if e.get("level") in ("최고 경보", "경보") else "check"),
                        "_src": "샘플", "_base": str(SAMPLE_DIR)})
    for d in live_sessions():
        for e in read_jsonl(d / "events.jsonl"):
            out.append({**e, "_src": d.name, "_base": str(d)})
    fp = false_positive_marks()
    for e in out:
        e["_ts"] = _naive(e["ts"])
        if e["event_id"] in fp:
            e["false_positive"] = True
            e["fp_by"] = fp[e["event_id"]].get("by", "")
            e["fp_note"] = fp[e["event_id"]].get("reason", "")
    out.sort(key=lambda e: e["_ts"])
    return out


def detections(events: list[dict]) -> list[dict]:
    """감지(3축 판정 · 모드 규칙)만 — 통계 · 피드백이 센다."""
    return [e for e in events if e.get("kind", "stage") in DETECT_KINDS and e.get("violation_type")]


def frame_file(e: dict) -> Path | None:
    fp = e.get("frame_path")
    if not fp:
        return None
    p = Path(fp)
    if not p.is_absolute():
        p = Path(e.get("_base") or DOCGEN_DIR) / p
    return p if p.exists() else None


def ruleset_status() -> dict:
    """현재 규칙셋 — 문서 자동화에서 위험성평가 확정으로 쌓인 개정안과 버전."""
    from safety_docs.assessment import current_ruleset_version, ruleset_revisions
    from safety_monitor.package import docgen_confirmed_changes
    ids = docgen_confirmed_changes()
    revs = ruleset_revisions()
    return {"version": current_ruleset_version(), "ids": ids, "last": revs[-1] if revs else None}
