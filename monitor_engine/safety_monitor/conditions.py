"""
조건어 평가기 — 패키지의 규칙(rules.json)에 적힌 조건을 현장 상태에 비춰 참/거짓을 낸다.

회사는 아래 조건어만 조합해서 규칙을 쓴다. 조건어는 특정 공정 · 시나리오를 모른다.
새 위험 유형이 와도 조건어를 조합해 판정표를 쓰면 되고, 엔진은 바뀌지 않는다.

  묶기     all · any · not · cond(이름 붙인 조건) · var(규칙 값)
  상태     fact(켜진 상태) · duration(켜져 있던 시간) · event(일어난 일) · document(입력된 문서)
  측정     measured(유효한 측정이 있나) · measure(최근 측정값 비교) · covers(모든 지점을 쟀나)
  대상     unmarked(표시 안 된 대상이 있나 — 맹판 미설치 배관 등)
  영상     detect(불꽃 등 검출 확정) · persons(폴리곤 안 인원) · video(영상이 도는 중인가)
  구역     zone_in · zone_attr(구역 속성)
  판정표   axis(같은 판정표 안의 축 상태)

값에 '@이름' 을 쓰면 rules.json 의 vars 값을 가리킨다.
어떤 조건이든 "label" 을 달면, 거짓일 때 화면 · 로그에 그 이름으로 이유가 남는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

# 조건어 → 같이 쓸 수 있는 키 (검사기 validate 가 쓴다)
PREDICATES: dict[str, set[str]] = {
    "all": set(), "any": set(), "not": set(), "cond": set(), "var": {"is"},
    "fact": {"zones", "for_min", "any_zone"},
    "event": {"attr", "within_min"},
    "measured": {"max_age_min", "max", "min", "invalidated_by", "after"},
    "measure": {"op", "value", "max_age_min"},
    "duration": {"op", "value"},
    "covers": set(), "unmarked": set(), "document": set(),
    "detect": {"hold_min"},
    "persons": {"op", "value"},
    "video": set(),
    "zone_in": set(),
    "zone_attr": {"in", "is"},
    "axis": {"is", "in"},
}
OPS = {">=": lambda a, b: a >= b, ">": lambda a, b: a > b, "<=": lambda a, b: a <= b,
       "<": lambda a, b: a < b, "==": lambda a, b: a == b, "!=": lambda a, b: a != b}


class ConditionError(ValueError):
    pass


@dataclass
class R:
    ok: bool
    ev: list[str] = field(default_factory=list)        # 참일 때 근거
    why_not: list[str] = field(default_factory=list)   # 거짓일 때 이유


class Ctx:
    """조건 하나를 평가할 때의 맥락 — 어느 구역, 몇 시, 영상이 도는지, 같은 판정표의 축 상태."""

    def __init__(self, eng, zone: str, now: datetime, axes: dict | None = None, raised_at: datetime | None = None):
        self.eng = eng
        self.store = eng.store
        self.rules = eng.rules
        self.site = eng.site
        self.zone = zone
        self.now = now
        self.axes = axes or {}
        self.raised_at = raised_at
        self._depth = 0

    @property
    def video(self) -> bool:
        return self.eng.video_on

    def var(self, name: str):
        vs = self.rules.get("vars", {})
        if name not in vs:
            raise ConditionError(f"vars 에 없는 값: @{name}")
        return vs[name]

    def val(self, v):
        if isinstance(v, str) and v.startswith("@"):
            return self.var(v[1:])
        return v

    def as_list(self, v) -> list:
        v = self.val(v)
        if v is None:
            return []
        return list(v) if isinstance(v, (list, tuple, set)) else [v]


# ---------------------------------------------------------------------- 평가
def evaluate(p, c: Ctx) -> R:
    if p is True or p is False:
        return R(bool(p))
    if not isinstance(p, dict):
        raise ConditionError(f"조건은 true/false 또는 {{조건어: ...}} 여야 합니다: {p!r}")
    keys = [k for k in p if k in PREDICATES]
    if len(keys) != 1:
        raise ConditionError(f"조건어가 정확히 하나여야 합니다: {sorted(k for k in p if not k.startswith('_'))}")
    r = HANDLERS[keys[0]](p, c)
    label = p.get("label")
    if not r.ok and label:
        r = R(False, [], [label + (f" — {'; '.join(r.why_not)}" if r.why_not else "")])
    return r


def _all(p, c):
    rs = [evaluate(x, c) for x in p["all"]]
    ok = all(r.ok for r in rs)
    return R(ok, [e for r in rs for e in r.ev] if ok else [], [w for r in rs if not r.ok for w in r.why_not])


def _any(p, c):
    rs = [evaluate(x, c) for x in p["any"]]
    ok = any(r.ok for r in rs)
    return R(ok, [e for r in rs if r.ok for e in r.ev], [] if ok else [w for r in rs for w in r.why_not])


def _not(p, c):
    r = evaluate(p["not"], c)
    return R(not r.ok, [], r.ev if r.ok else [])


def _cond(p, c):
    name = p["cond"]
    conds = c.rules.get("conditions", {})
    if name not in conds:
        raise ConditionError(f"conditions 에 없는 조건: {name}")
    c._depth += 1
    if c._depth > 20:
        raise ConditionError(f"조건이 자기 자신을 부릅니다: {name}")
    try:
        return evaluate(conds[name], c)
    finally:
        c._depth -= 1


def _var(p, c):
    v = c.var(p["var"])
    return R(v == p["is"]) if "is" in p else R(bool(v))


def _fact(p, c):
    name = p["fact"]
    if "zones" in p and c.zone not in c.as_list(p["zones"]):
        return R(False)
    zones = [z for (f, z) in c.store.on if f == name] if p.get("any_zone") else [c.zone]
    for z in zones:
        rec = c.store.on.get((name, z))
        if rec and rec.ts <= c.now:
            if "for_min" in p and (c.now - rec.ts) < timedelta(minutes=float(c.val(p["for_min"]))):
                continue
            return R(True, [f"{rec.ts:%H:%M} {rec.label}"])
    return R(False)


def _match_attrs(attrs: dict, want: dict, c: Ctx) -> bool:
    for k, v in want.items():
        allowed = c.as_list(v)
        if attrs.get(k) not in allowed:
            return False
    return True


def _event(p, c):
    name = p["event"]
    want = p.get("attr", {})
    hits = [e for e in c.store.events
            if e.fact == name and e.zone == c.zone and e.ts <= c.now
            and (e.cleared_at is None or e.cleared_at > c.now)
            and _match_attrs(e.attrs, want, c)]
    if "within_min" in p:
        lim = timedelta(minutes=float(c.val(p["within_min"])))
        hits = [e for e in hits if c.now - e.ts <= lim]
    if not hits:
        return R(False)
    e = max(hits, key=lambda x: x.ts)
    return R(True, [f"{e.ts:%H:%M} {e.label}" + (f" {e.target}" if e.target else "")])


def _valid_measures(name: str, c: Ctx, max_age=None, invalid=None, vmax=None, vmin=None, after_raise=False):
    out, why = [], []
    inv = c.as_list(invalid) if invalid is not None else []
    for m in c.store.measures:
        if m.fact != name or m.zone != c.zone or m.ts > c.now:
            continue
        if max_age is not None and c.now - m.ts > timedelta(minutes=float(c.val(max_age))):
            why.append(f"{m.ts:%H:%M} 측정 만료")
            continue
        killer = next((e for e in c.store.events if e.fact in inv and e.zone == c.zone and m.ts < e.ts <= c.now), None)
        if killer:
            why.append(f"{m.ts:%H:%M} 측정은 {killer.ts:%H:%M} {killer.label} 이전이라 무효")
            continue
        if vmax is not None and m.value > float(c.val(vmax)):
            why.append(f"{m.ts:%H:%M} 측정 {m.value:g} > {c.val(vmax)}")
            continue
        if vmin is not None and m.value < float(c.val(vmin)):
            why.append(f"{m.ts:%H:%M} 측정 {m.value:g} < {c.val(vmin)}")
            continue
        if after_raise and (c.raised_at is None or m.ts <= c.raised_at):
            continue
        out.append(m)
    return out, why


def _measured(p, c):
    ms, why = _valid_measures(p["measured"], c, p.get("max_age_min"), p.get("invalidated_by"),
                              p.get("max"), p.get("min"), p.get("after") == "raise")
    if not ms:
        return R(False, [], why[-1:] or ["측정 기록 없음"])
    m = max(ms, key=lambda x: x.ts)
    return R(True, [f"{m.ts:%H:%M} {m.label}" + (f" {m.target}" if m.target else "") + f" {m.value:g}"])


def _measure(p, c):
    ms, _ = _valid_measures(p["measure"], c, p.get("max_age_min"))
    if not ms:
        return R(False)
    m = max(ms, key=lambda x: x.ts)
    op = p.get("op", ">=")
    ok = OPS[op](m.value, float(c.val(p["value"])))
    return R(ok, [f"{m.ts:%H:%M} {m.label} {m.value:g}"] if ok else [])


def _duration(p, c):
    name = p["duration"]
    iv = c.store.intervals.get((name, c.zone), [])
    if not iv:
        return R(False, [], [f"{c.store.labels.get(name, name)} 기록 없음"])
    start, end = iv[-1]
    mins = ((end or c.now) - start).total_seconds() / 60
    op, val = p.get("op", ">="), float(c.val(p["value"]))
    ok = OPS[op](mins, val)
    return R(ok, [f"{c.store.labels.get(name, name)} {mins:.0f}분"] if ok else [], [] if ok else [f"{mins:.0f}분 (기준 {op} {val:g}분)"])


def points(spec, c: Ctx) -> list[str]:
    """대상 목록 — site.json 참조 목록이나 입력된 문서에서 뽑는다. 여러 개면 합친다."""
    specs = spec if isinstance(spec, list) else [spec]
    out: list[str] = []
    for s in specs:
        if "if" in s and not evaluate(s["if"], c).ok:
            continue
        if "ref" in s:
            items = c.site.get("references", {}).get(s["ref"], {}).get(c.zone, [])
            if s.get("where"):
                items = [i for i in items if i.get(s["where"])]
            out += [str(i[s.get("field", "id")]) for i in items]
        elif "document" in s:
            doc = c.store.documents.get((s["document"], c.zone))
            if doc:
                out += [r.get(s["field"], "") for r in doc["rows"] if r.get(s["field"])]
    return list(dict.fromkeys(out))


def _covers(p, c):
    s = p["covers"]
    need = points(s["points"], c)
    ms, _ = _valid_measures(s["measure"], c, s.get("max_age_min"), s.get("invalidated_by"), s.get("max"))
    got = {m.target for m in ms if m.target}
    miss = [x for x in need if x not in got]
    return R(not miss, [f"{', '.join(need)} 측정"] if not miss else [], [f"{', '.join(miss)} 미측정"] if miss else [])


def _unmarked(p, c):
    s = p["unmarked"]
    need = points(s["points"], c)
    marked = c.store.marks.get(s["mark"], {})
    left = [x for x in need if x not in marked]
    lab = c.store.labels.get(s["mark"], s["mark"])
    return R(bool(left), [f"{lab} 없음: {', '.join(left)}"] if left else [])


def _document(p, c):
    d = c.store.documents.get((p["document"], c.zone))
    return R(bool(d), [f"{d['ts']:%H:%M} {d['label']}"] if d else [])


def _detect(p, c):
    d = c.store.detections.get((p["detect"], c.zone))
    if not d:
        return R(False)
    if d["on"]:
        return R(True, [f"{d['since']:%H:%M:%S} 영상 {p['detect']}"])
    if "hold_min" in p and d.get("last") and c.now - d["last"] <= timedelta(minutes=float(c.val(p["hold_min"]))):
        return R(True, [f"{d['last']:%H:%M:%S} 영상 {p['detect']} (유지)"])
    return R(False)


def _persons(p, c):
    if not c.video:
        return R(False)
    n = count_people(c.store, c.zone, p["persons"])
    ok = OPS[p.get("op", ">=")](n, float(c.val(p.get("value", 1))))
    return R(ok, [f"사람 {n}명"] if ok else [])


def count_people(store, zone: str, types) -> int:
    """구역 안 사람 수. types = 'all' 또는 폴리곤 종류(들). 한 사람이 두 폴리곤에 걸쳐도 한 번만 센다."""
    people = store.people.get(zone, [])
    if types == "all":
        return len(people)
    want = set(types if isinstance(types, list) else [types])
    return sum(1 for s in people if s & want)


def _video(p, c):
    return R(c.video == bool(p["video"]))


def _zone_in(p, c):
    return R(c.zone in c.as_list(p["zone_in"]))


def _zone_attr(p, c):
    v = c.site.get("zones", {}).get(c.zone, {}).get(p["zone_attr"])
    if "is" in p:
        return R(v == c.val(p["is"]))
    ok = v in c.as_list(p.get("in", []))
    return R(ok, [], [] if ok else [f"{v or '-'} 미등록"])


def _axis(p, c):
    name = p["axis"]
    if name not in c.axes:
        raise ConditionError(f"축 '{name}' 은 이 판정표에서 아직 계산되지 않았습니다 (축 순서 확인)")
    a = c.axes[name]
    ok = a.state == p["is"] if "is" in p else a.state in p.get("in", [])
    return R(ok, ([f"{name} {a.state}" + (f"({', '.join(a.why)})" if a.why else "")] if ok else []))


HANDLERS = {
    "all": _all, "any": _any, "not": _not, "cond": _cond, "var": _var,
    "fact": _fact, "event": _event, "measured": _measured, "measure": _measure, "duration": _duration,
    "covers": _covers, "unmarked": _unmarked, "document": _document, "detect": _detect,
    "persons": _persons, "video": _video, "zone_in": _zone_in, "zone_attr": _zone_attr, "axis": _axis,
}
