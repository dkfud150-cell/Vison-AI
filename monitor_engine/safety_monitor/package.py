"""
패키지 — 회사가 만드는 파일 묶음을 읽고 검사한다.

  packages/<이름>/
    site.json      사업장 · 구역(속성) · 설비 참조 목록
    signals.json   신호 사전 (신호 → 무엇을 켜고 끄나)
    rules.json     vars · conditions · judgments(판정표) · modes · gates · rule_changes
    cameras/*.json 카메라별 폴리곤
    buttons.json   재생 중 키보드 신호 (선택)
    detect.json    탐지 설정 덮어쓰기 (선택)
    scenarios/<이름>/scenario.json + timeline.csv + 입력 문서

엔진은 이 폴더만 읽는다. 폴더를 통째로 바꾸면 다른 사업장 · 다른 위험이 같은 코드로 돈다.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .conditions import OPS, PREDICATES
from .judge import LEVELS
from .signals import Signal, load_timeline
from .zones import BUILTIN_TYPES, hex_bgr

ROOT = Path(__file__).resolve().parent.parent
PACKAGES_DIR = ROOT / "packages"
CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = ROOT / "outputs"
MODEL_DIR = ROOT / "models"

DO_TYPES = {"on", "off", "event", "measure", "mark", "unmark", "document", "accident"}


class PackageError(ValueError):
    pass


def load_json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PackageError(f"{path.name}: JSON 형식 오류 — {e.msg} (줄 {e.lineno}, 칸 {e.colno})") from e


def deep_merge(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in b.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


# ====================================================================== 패키지
@dataclass
class Scenario:
    dir: Path
    key: str
    data: dict

    @property
    def title(self) -> str:
        return self.data.get("name", self.key)

    @property
    def day(self) -> date:
        return date.fromisoformat(self.data.get("date", "2026-10-12"))

    @property
    def zone(self) -> str | None:
        return self.data.get("zone")

    def timeline(self) -> list[Signal]:
        return load_timeline(self.dir / self.data.get("timeline", "timeline.csv"), self.day)

    def variants(self) -> dict:
        return self.data.get("variants", {})

    def scenes(self) -> list[dict]:
        return self.data.get("scenes", [])


@dataclass
class Package:
    root: Path
    site: dict
    signals: dict
    rules_base: dict
    cameras: dict = field(default_factory=dict)
    buttons: dict = field(default_factory=dict)
    detect: dict = field(default_factory=dict)
    zone_types: list = field(default_factory=list)   # 관리자가 더한 구역 종류 (zone_types.json) — 기본 네 종류 밖

    @property
    def name(self) -> str:
        return self.site.get("name", self.root.name)

    def rules(self, changes: list[str] | None = None) -> dict:
        return apply_changes(self.rules_base, changes or [])

    def change_ids(self) -> list[str]:
        return [k for k in self.rules_base.get("rule_changes", {}) if not k.startswith("_")]

    def scenario_keys(self) -> list[str]:
        d = self.root / "scenarios"
        return sorted(p.name for p in d.iterdir() if (p / "scenario.json").exists()) if d.exists() else []

    def scenario(self, key: str) -> Scenario:
        d = self.root / "scenarios" / key
        if not (d / "scenario.json").exists():
            raise PackageError(f"시나리오가 없습니다: {key} (있는 것: {', '.join(self.scenario_keys())})")
        return Scenario(d, key, load_json(d / "scenario.json"))

    def camera(self, cam_id: str | None = None) -> dict:
        if not self.cameras:
            raise PackageError(f"{self.root.name}/cameras/ 에 카메라 파일이 없습니다")
        if cam_id is None:
            return next(iter(self.cameras.values()))
        if cam_id not in self.cameras:
            raise PackageError(f"카메라가 없습니다: {cam_id} (있는 것: {', '.join(self.cameras)})")
        return self.cameras[cam_id]

    def scene_camera(self, scene: dict) -> dict:
        """장면이 쓸 카메라 설정. 장면에 polygons(화면에서 그린 구역)가 있으면 카메라 기본 구역 대신 그걸 쓴다."""
        cam = self.camera(scene.get("camera"))
        if scene.get("polygons"):
            cam = {**cam, "polygons": scene["polygons"]}
        return cam


def find_package(arg: str | Path) -> Path:
    p = Path(arg)
    if (p / "site.json").exists():
        return p
    q = PACKAGES_DIR / str(arg)
    if (q / "site.json").exists():
        return q
    have = ", ".join(sorted(x.name for x in PACKAGES_DIR.iterdir() if (x / "site.json").exists())) if PACKAGES_DIR.exists() else "-"
    raise PackageError(f"패키지를 찾을 수 없습니다: {arg} (있는 것: {have})")


def load_package(arg: str | Path, strict: bool = True) -> Package:
    root = find_package(arg)
    for f in ("site.json", "signals.json", "rules.json"):
        if not (root / f).exists():
            raise PackageError(f"{root.name}/{f} 가 없습니다")
    cams = {}
    for f in sorted((root / "cameras").glob("*.json")) if (root / "cameras").exists() else []:
        c = load_json(f)
        c.setdefault("camera_id", f.stem)
        c["_path"] = str(f)
        cams[c["camera_id"]] = c
    buttons = {k: v for k, v in load_json(root / "buttons.json").items() if not k.startswith("_")} if (root / "buttons.json").exists() else {}
    detect = load_json(CONFIG_DIR / "detect.json")
    if (root / "detect.json").exists():
        detect = deep_merge(detect, load_json(root / "detect.json"))
    zt = load_json(root / "zone_types.json").get("types", []) if (root / "zone_types.json").exists() else []
    for c in cams.values():                         # 그리기(zones.py)가 새 종류의 색을 알게
        c["type_colors"] = {t["key"]: t.get("color") for t in zt if t.get("key")}
    pkg = Package(root, load_json(root / "site.json"),
                  {k: v for k, v in load_json(root / "signals.json").get("signals", {}).items() if not k.startswith("_")},
                  load_json(root / "rules.json"), cams, buttons, detect, zt)
    if strict:
        errors, _ = validate_package(pkg)
        if errors:
            raise PackageError(f"패키지 {root.name} 에 오류 {len(errors)}건 — python validate.py {root.name} 로 확인\n  " + "\n  ".join(errors[:10]))
    return pkg


# ====================================================================== 개정안
def _walk(d: dict, dotted: str, create: bool = True):
    keys = dotted.split(".")
    for k in keys[:-1]:
        if k not in d and not create:
            raise KeyError(dotted)
        d = d.setdefault(k, {})
    return d, keys[-1]


def apply_changes(base: dict, ids: list[str]) -> dict:
    """rule_changes 의 개정안을 규칙 위에 덮어쓴다. set = 값 바꾸기, add = 목록에 더하기."""
    rs = copy.deepcopy(base)
    changes = base.get("rule_changes", {})
    for rid in ids:
        ch = changes.get(rid)
        if not ch or rid.startswith("_"):
            raise PackageError(f"규칙에 없는 개정안: {rid} (있는 것: {', '.join(k for k in changes if not k.startswith('_'))})")
        for path, val in ch.get("set", {}).items():
            parent, key = _walk(rs, path)
            parent[key] = copy.deepcopy(val)
        for path, vals in ch.get("add", {}).items():
            parent, key = _walk(rs, path)
            cur = list(parent.get(key, []))
            parent[key] = cur + [v for v in vals if v not in cur]
    rs["_applied"] = list(ids)
    return rs


def docgen_confirmed_changes() -> list[str]:
    """법정 문서 쪽(../docgen/records/ruleset_log.jsonl)에서 위험성평가 확정으로 쌓인 개정안."""
    log = ROOT.parent / "docgen" / "records" / "ruleset_log.jsonl"
    if not log.exists():
        return []
    ids: list[str] = []
    for line in log.read_text(encoding="utf-8").splitlines():
        if line.strip():
            ids += [r for r in json.loads(line).get("rule_ids", []) if r not in ids]
    return sorted(ids)


def resolve_changes(arg: str | None, pkg: Package, scenario: Scenario | None = None) -> tuple[list[str], str]:
    """--changes 해석 → (개정안 목록, 표시 이름). 시나리오 variants 이름도 받는다."""
    if arg is None or arg.strip().lower() in ("", "none", "base", "기본"):
        return [], "기본 규칙"
    a = arg.strip()
    if scenario and a in scenario.variants():
        return list(scenario.variants()[a].get("changes", [])), a
    if a.lower() == "all":
        return pkg.change_ids(), "개정안 전부"
    if a.lower() == "docgen":
        ids = docgen_confirmed_changes()
        return ids, f"docgen 확정분 ({' '.join(ids) or '없음'})"
    ids = [x.strip() for x in a.split(",") if x.strip()]
    return ids, "개정안 " + " ".join(ids)


# ====================================================================== 검사
class _V:
    def __init__(self, pkg: Package):
        self.pkg = pkg
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.vars = pkg.rules_base.get("vars", {})
        self.conds = pkg.rules_base.get("conditions", {})
        self.zones = set(pkg.site.get("zones", {}))
        self.refs = set(pkg.site.get("references", {}))
        self.tables = pkg.rules_base.get("judgments", {})
        self.docs = {a.get("fact") for s in pkg.signals.values() for a in (s["do"] if isinstance(s.get("do"), list) else [s])
                     if a.get("do") == "document"}
        self.poly_types = {p.get("type") for c in pkg.cameras.values() for p in c.get("polygons", [])}
        self.known_types = set(BUILTIN_TYPES) | {t.get("key") for t in pkg.zone_types}

    def e(self, msg):
        self.errors.append(msg)

    def w(self, msg):
        self.warnings.append(msg)

    def vals(self, v, where):
        if isinstance(v, str) and v.startswith("@") and v[1:] not in self.vars:
            self.e(f"{where}: vars 에 없는 값 {v}")
        elif isinstance(v, dict):
            for k, x in v.items():
                self.vals(x, where)
        elif isinstance(v, list):
            for x in v:
                self.vals(x, where)

    def pred(self, p, where, axes=None):
        if p is True or p is False:
            return
        if not isinstance(p, dict):
            self.e(f"{where}: 조건은 true/false 또는 {{조건어: …}} 여야 한다 → {p!r}")
            return
        keys = [k for k in p if k in PREDICATES]
        if len(keys) != 1:
            self.e(f"{where}: 조건어가 정확히 하나여야 한다 → {[k for k in p if not k.startswith('_')]}")
            return
        k = keys[0]
        for x in p:
            if x not in PREDICATES and x != "label" and not x.startswith("_") and x not in PREDICATES[k]:
                self.e(f"{where}: '{k}' 에 쓸 수 없는 키 '{x}' (쓸 수 있는 키: {sorted(PREDICATES[k]) or '없음'})")
        self.vals({x: p[x] for x in p if x not in ("all", "any", "not")}, where)
        if k in ("all", "any"):
            if not isinstance(p[k], list):
                self.e(f"{where}: {k} 는 목록이어야 한다")
                return
            for i, x in enumerate(p[k]):
                self.pred(x, f"{where}.{k}[{i}]", axes)
        elif k == "not":
            self.pred(p["not"], f"{where}.not", axes)
        elif k == "cond" and p["cond"] not in self.conds:
            self.e(f"{where}: conditions 에 없는 조건 '{p['cond']}'")
        elif k == "var" and p["var"] not in self.vars:
            self.e(f"{where}: vars 에 없는 값 '{p['var']}'")
        elif k == "axis":
            if axes is None:
                self.e(f"{where}: axis 는 판정표 안에서만 쓸 수 있다")
            elif p["axis"] not in axes:
                self.e(f"{where}: 축 '{p['axis']}' 이 없거나 이 축보다 뒤에 있다 (있는 축: {', '.join(axes) or '없음'})")
        elif k in ("covers", "unmarked"):
            spec = p[k]
            pts = spec.get("points")
            for s in (pts if isinstance(pts, list) else [pts]):
                if isinstance(s, dict) and "ref" in s and s["ref"] not in self.refs:
                    self.e(f"{where}: site.json references 에 없는 참조 '{s['ref']}'")
                if isinstance(s, dict) and "document" in s and s["document"] not in self.docs:
                    self.w(f"{where}: 문서 '{s['document']}' 를 입력하는 신호가 signals.json 에 없다")
        elif k == "zone_attr" and not any(p["zone_attr"] in z for z in self.pkg.site.get("zones", {}).values()):
            self.w(f"{where}: 어느 구역에도 '{p['zone_attr']}' 속성이 없다")
        if "op" in p and p["op"] not in OPS:
            self.e(f"{where}: op 는 {', '.join(OPS)} 중 하나")

    def zones_list(self, zs, where):
        for z in zs or []:
            if z != "*" and z not in self.zones:
                self.e(f"{where}: site.json 에 없는 구역 '{z}'")


def validate_package(pkg: Package) -> tuple[list[str], list[str]]:
    V = _V(pkg)
    site, rules = pkg.site, pkg.rules_base
    if not V.zones:
        V.e("site.json: zones 가 비었다")
    for rname, ref in site.get("references", {}).items():
        for z in ref:
            if not z.startswith("_") and z not in V.zones:
                V.e(f"site.json references.{rname}: 없는 구역 '{z}'")

    # ---- 신호 사전
    for name, s in pkg.signals.items():
        acts = s["do"] if isinstance(s.get("do"), list) else [s]
        for a in acts:
            do = a.get("do")
            if do not in DO_TYPES:
                V.e(f"signals.{name}: do 는 {', '.join(sorted(DO_TYPES))} 중 하나 → {do!r}")
            if do not in ("accident",) and not a.get("fact"):
                V.e(f"signals.{name}: fact 가 없다")
            for src in a.get("attrs_from", []):
                if src != "zone" and not (src.startswith("ref:") and src[4:] in V.refs):
                    V.e(f"signals.{name}: attrs_from '{src}' — 'zone' 또는 'ref:<site.json 참조 이름>'")
        if "reset" in s:
            V.pred(s["reset"].get("if", True), f"signals.{name}.reset.if")

    # ---- 규칙
    for cname, c in V.conds.items():
        if not cname.startswith("_"):
            V.pred(c, f"conditions.{cname}")
    for tname, t in V.tables.items():
        if tname.startswith("_"):
            continue
        w = f"judgments.{tname}"
        V.zones_list(t.get("zones"), w)
        seen: list[str] = []
        for ax in t.get("axes", []):
            if not ax.get("states"):
                V.e(f"{w}.axes.{ax.get('name')}: states 가 없다")
            for i, st in enumerate(ax.get("states", [])):
                V.pred(st.get("when"), f"{w}.axes.{ax.get('name')}[{i}]", seen)
            if ax.get("states") and ax["states"][-1].get("when") is not True:
                V.w(f"{w}.axes.{ax.get('name')}: 마지막 상태의 when 이 true 가 아니다 — 아무 상태도 안 맞으면 '-'")
            seen.append(ax.get("name"))
        for i, r in enumerate(t.get("rows", [])):
            if r.get("level") not in LEVELS:
                V.e(f"{w}.rows[{i}]: level 은 {', '.join(LEVELS)} 중 하나 → {r.get('level')!r}")
            V.pred(r.get("when"), f"{w}.rows[{i}]", seen)
        if t.get("default", {}).get("level", "정상") not in LEVELS:
            V.e(f"{w}.default: level 오류")
        if "lower" in t:
            V.pred(t["lower"].get("when", True), f"{w}.lower", seen)
        if "presence" in t:
            V.pred(t["presence"], f"{w}.presence")
        for lv in t.get("responses", {}):
            if lv not in LEVELS:
                V.e(f"{w}.responses: 단계 이름 오류 '{lv}'")
        if t.get("accident_prevented_at", "최고 경보") not in LEVELS:
            V.e(f"{w}.accident_prevented_at: 단계 이름 오류")

    modes = {n: m for n, m in rules.get("modes", {}).items() if not n.startswith("_")}
    if sum(1 for m in modes.values() if m.get("default")) != 1:
        V.e("modes: default 모드(평상시)가 정확히 하나여야 한다")
    check_types = {"no_entry", "min_persons", "max_persons"}
    for n, m in modes.items():
        w = f"modes.{n}"
        V.zones_list(m.get("zones"), w)
        if not m.get("default"):
            V.pred(m.get("when"), f"{w}.when")
        j = m.get("judge", [])
        for t in (j if isinstance(j, list) else []):
            if t not in V.tables:
                V.e(f"{w}.judge: 판정표 '{t}' 가 없다")
        for i, ck in enumerate(m.get("checks", [])):
            if ck.get("type") not in check_types:
                V.e(f"{w}.checks[{i}]: type 은 {', '.join(sorted(check_types))} 중 하나")
            if ck.get("level", "주의") not in LEVELS:
                V.e(f"{w}.checks[{i}]: level 오류")
            if "when" in ck:
                V.pred(ck["when"], f"{w}.checks[{i}].when")
            for pt in (ck.get("polygons") if isinstance(ck.get("polygons"), list) else [ck.get("polygons", "work")]):
                if V.poly_types and pt not in V.poly_types:
                    V.w(f"{w}.checks[{i}]: 카메라에 '{pt}' 종류 폴리곤이 없다 (영상에서 이 규칙은 걸리지 않는다)")
        if "enabled" in m:
            V.vals(m["enabled"], w)

    from .gates import GATE_TYPES
    for i, g in enumerate(rules.get("gates", [])):
        w = f"gates[{i}]({g.get('id')})"
        if g.get("type") not in GATE_TYPES:
            V.e(f"{w}: type 은 {', '.join(GATE_TYPES)} 중 하나")
        if g.get("on_document") not in V.docs:
            V.e(f"{w}: on_document '{g.get('on_document')}' 를 입력하는 document 신호가 없다")
        if g.get("ref") and g["ref"] not in V.refs:
            V.e(f"{w}: site.json 에 없는 참조 '{g['ref']}'")
        V.vals(g.get("enabled", True), w)

    for rid, ch in rules.get("rule_changes", {}).items():
        if rid.startswith("_"):
            continue
        for path in ch.get("set", {}):
            try:
                parent, key = _walk(copy.deepcopy(rules), path, create=False)
                if key not in parent:
                    raise KeyError
            except (KeyError, AttributeError):
                V.e(f"rule_changes.{rid}: 규칙에 없는 경로 '{path}'")
        for path in ch.get("add", {}):
            try:
                parent, key = _walk(copy.deepcopy(rules), path, create=False)
                if not isinstance(parent.get(key), list):
                    raise KeyError
            except (KeyError, AttributeError):
                V.e(f"rule_changes.{rid}: add 는 목록 경로에만 — '{path}'")

    # ---- 구역 종류 (관리자가 더한 것)
    seen = set()
    for i, t in enumerate(pkg.zone_types):
        k = t.get("key")
        if not isinstance(k, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", k):
            V.e(f"zone_types[{i}]: key 는 영문 소문자로 시작하는 영문 · 숫자 · _ → {k!r}")
        elif k in BUILTIN_TYPES or k in seen:
            V.e(f"zone_types[{i}]: key '{k}' 가 기본 종류이거나 두 번 나온다")
        seen.add(k)
        if not t.get("label"):
            V.e(f"zone_types[{i}]({k}): label 이 없다")
        if not hex_bgr(t.get("color", "")):
            V.e(f"zone_types[{i}]({k}): color 는 #RRGGBB")

    # ---- 카메라
    for cid, c in pkg.cameras.items():
        if c.get("zone") and c["zone"] not in V.zones:
            V.e(f"cameras/{cid}: 없는 구역 '{c['zone']}'")
        for p in c.get("polygons", []):
            if p.get("zone") and p["zone"] not in V.zones:
                V.e(f"cameras/{cid}.{p.get('name')}: 없는 구역 '{p['zone']}'")
            if p.get("type", "work") not in V.known_types:
                V.w(f"cameras/{cid}.{p.get('name')}: 모르는 종류 '{p.get('type')}' — zone_types.json 에 더하거나 종류를 고친다")
            pts = p.get("points", [])
            if len(pts) < 3:
                V.e(f"cameras/{cid}.{p.get('name')}: 점이 3개 이상이어야 한다")
            if p.get("space", "image") == "image" and any(not (0 <= x <= 1 and 0 <= y <= 1) for x, y in pts):
                V.e(f"cameras/{cid}.{p.get('name')}: 화면 좌표는 0~1 비율")

    # ---- 시나리오
    for key in pkg.scenario_keys():
        w = f"scenarios/{key}"
        try:
            sc = pkg.scenario(key)
            tl = sc.timeline()
        except Exception as ex:  # noqa: BLE001
            V.e(f"{w}: {ex}")
            continue
        for s in tl:
            if s.signal not in pkg.signals:
                V.w(f"{w}: 신호 사전에 없는 신호 '{s.signal}' ({s.ts:%H:%M}) — event 로 기록된다")
            if s.zone and s.zone not in V.zones:
                V.e(f"{w}: 없는 구역 '{s.zone}' ({s.ts:%H:%M} {s.signal})")
            spec = pkg.signals.get(s.signal, {})
            acts = spec["do"] if isinstance(spec.get("do"), list) else [spec]
            if any(a.get("do") == "document" for a in acts) and not (sc.dir / (s.value or "")).exists():
                V.e(f"{w}: 문서 파일이 없다 '{s.value}' ({s.ts:%H:%M})")
        for vn, v in sc.variants().items():
            for rid in v.get("changes", []):
                if rid not in pkg.change_ids():
                    V.e(f"{w}.variants.{vn}: 없는 개정안 '{rid}'")
            for i, ex in enumerate(v.get("expect", [])):
                if "level" in ex and ex["level"] not in LEVELS:
                    V.e(f"{w}.variants.{vn}.expect[{i}]: level 오류")
                if "gate" in ex and ex["gate"] not in {g.get("id") for g in rules.get("gates", [])}:
                    V.e(f"{w}.variants.{vn}.expect[{i}]: 없는 게이트 '{ex['gate']}'")
        if sc.data.get("table") and sc.data["table"] not in V.tables:
            V.e(f"{w}: 없는 판정표 '{sc.data['table']}'")
        for sn in sc.scenes():
            if sn.get("camera") and sn["camera"] not in pkg.cameras:
                V.e(f"{w}.scenes.{sn.get('name')}: 없는 카메라 '{sn['camera']}'")
            for p in sn.get("polygons", []):          # 화면에서 그린 장면 구역 — 카메라 구역과 같은 검사
                where = f"{w}.scenes.{sn.get('name')}.{p.get('name')}"
                if p.get("zone") and p["zone"] not in V.zones:
                    V.e(f"{where}: 없는 구역 '{p['zone']}'")
                if p.get("type", "work") not in V.known_types:
                    V.w(f"{where}: 모르는 종류 '{p.get('type')}' — zone_types.json 에 더하거나 종류를 고친다")
                pts = p.get("points", [])
                if len(pts) < 3:
                    V.e(f"{where}: 점이 3개 이상이어야 한다")
                if any(not (0 <= x <= 1 and 0 <= y <= 1) for x, y in pts):
                    V.e(f"{where}: 화면 좌표는 0~1 비율")
            if sn.get("video") and not any((b / sn["video"]).exists() for b in (sc.dir, pkg.root, ROOT, Path("."))):
                V.w(f"{w}.scenes.{sn.get('name')}: 영상 파일이 아직 없다 '{sn['video']}'")
    return V.errors, V.warnings
