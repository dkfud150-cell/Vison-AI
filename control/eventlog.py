"""
이벤트 로그 — 거르기 · 검색

화면(이벤트 로그 표)과 '보이는 경보 이상 넘기기'가 이 함수 하나로 거른다. 화면에서만 거르면
화면에 안 보이는 기록까지 문서 자동화로 넘어가기 때문이다.

  한 개 고르기     작업 모드 · 구역 · 기간
  여러 개 고르기   종류 · 단계 · 위반 유형 · 규칙셋 · 표시(강화 중 · 오탐 · 영상 증거)
                  같은 칸 안에서는 하나라도 맞으면 되고, 칸끼리는 모두 맞아야 한다.
  출처            예시 데이터 · 실시간 세션 전체 · 세션 하나
  검색            띄어쓰기로 나눈 낱말이 모두 들어 있는 기록만 (대소문자 구분 없음).
                  화면에 보이는 이름(작업 전 차단 · 무음 기록 · 오탐 · 강화 …)과 구역 이름으로도 찾는다.
                  표에 안 보이는 칸(판정 근거 · 대응 · 규칙셋 · 출처 · 판정표)에서 맞았으면 그 칸 이름을 돌려준다.
예전 화면이 보내던 alert(all · alert · shadow)도 그대로 받는다.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from .common import DETECT_KINDS, DOCGEN_DIR, frame_file, system_now, zone_name

PERIODS = {"today": 0, "14": 14, "90": 90, "all": None}
KIND_T = {"gate": "작업 전 게이트", "accident": "사고", "info": "참고", "stage": "3축 판정", "check": "모드 규칙(영상)"}
KIND_ORDER = ["stage", "check", "gate", "accident", "info"]
LEVELS = ["주의", "경보", "최고 경보", "무음"]
LEVEL_T = {"주의": "주의", "경보": "경보", "최고 경보": "최고 경보", "무음": "무음 기록"}
FLAGS = {"adj": "강화 중 기록", "fp": "오탐 표시됨", "media": "영상 증거 있음"}
VISIBLE = {"ID", "일시", "구역", "모드", "위반 유형", "단계", "강화", "오탐"}     # 표에 보이는 칸 — 여기서 맞으면 따로 알리지 않는다
NO_RULESET = "(기록 없음)"


def kind_of(e: dict) -> str:
    return e.get("kind") or "stage"


def level_of(e: dict) -> str | None:
    """단계 칸 값 — 감지 기록만 있다. 모드가 꺼진 구간의 검출은 '무음'."""
    if kind_of(e) not in DETECT_KINDS:
        return None
    if not e.get("alerted"):
        return "무음"
    return e.get("level") or e.get("computed_level") or "무음"


def tag_text(e: dict) -> str:
    """화면 단계 칸에 보이는 말 (app.js kindTag 와 같다)."""
    k = kind_of(e)
    if k == "gate":
        return "작업 전 차단"
    if k == "accident":
        return "사고"
    if k == "info":
        vt = e.get("violation_type")
        return "작업중지 지시" if vt == "작업중지_지시" else "입력 취소" if vt == "입력_취소" else "참고"
    lv = level_of(e)
    return "무음 기록" if lv == "무음" else (f"무음 · {e['level']}" if not e.get("alerted") and e.get("level") else lv or "")


def has_media(e: dict) -> bool:
    """대표 프레임이나 전후 클립 파일이 실제로 있나 (경로만 적혀 있고 파일이 없으면 아니다)."""
    if "_media" not in e:
        ok = frame_file(e) is not None
        cp = e.get("clip_path")
        if not ok and cp:
            q = Path(cp)
            ok = (q if q.is_absolute() else Path(e.get("_base") or DOCGEN_DIR) / q).exists()
        e["_media"] = ok
    return e["_media"]


def src_kind(e: dict) -> str:
    return "sample" if e.get("_src") == "샘플" else "live"


def fields(e: dict) -> dict[str, str]:
    """검색이 뒤지는 칸 — 칸 이름 → 글자."""
    vt = e.get("violation_type") or ""
    ts = str(e.get("ts", "")).replace("T", " ")
    f = {"ID": e.get("event_id", ""), "일시": f"{ts} {ts[5:16]}", "구역": f"{e.get('zone') or ''} {zone_name(e.get('zone'))}",
         "모드": e.get("mode") or "-", "위반 유형": f"{vt} {vt.replace('_', ' ')}",
         "단계": f"{tag_text(e)} {KIND_T.get(kind_of(e), '')} {e.get('level') or ''}",
         "판정 근거": f"{e.get('reason') or ''} {str(e['row']) + '번 줄' if e.get('row') else ''}",
         "대응": e.get("response") or "", "규칙셋": f"{e.get('ruleset') or ''} {' '.join(e.get('applied_changes') or [])}",
         "판정표": e.get("table") or "",
         "출처": "샘플 예시 데이터" if src_kind(e) == "sample" else f"{e.get('_src', '')} 실시간 세션"}
    if e.get("adj_id"):
        f["강화"] = f"강화 {e['adj_id']}"
    if e.get("false_positive"):
        f["오탐"] = f"오탐 {e.get('fp_by', '')} {e.get('fp_note', '')}"
    return f


def tokens(q: str | None) -> list[str]:
    return [t.casefold() for t in str(q or "").split() if t.strip()]


def match(e: dict, toks: list[str]) -> list[str] | None:
    """낱말이 모두 들어 있으면 맞은 칸 이름(표에 안 보이는 칸만), 아니면 None."""
    if not toks:
        return []
    fs = {k: v.casefold() for k, v in fields(e).items()}
    hidden: list[str] = []
    for t in toks:
        hit = [k for k, v in fs.items() if t in v]
        if not hit:
            return None
        if not any(k in VISIBLE for k in hit):
            hidden += [k for k in hit if k not in hidden]
    return hidden


def _many(f: dict, key: str) -> set:
    v = f.get(key)
    return set(v) if isinstance(v, (list, tuple, set)) else set()


def detail_on(f: dict) -> bool:
    """기간 말고 좁히는 조건이 걸렸나 — '기간 밖에도 N건' 안내를 띄울지."""
    return bool(tokens(f.get("q")) or any(_many(f, k) for k in ("kinds", "levels", "types", "rulesets", "flags"))
                or f.get("src") or f.get("mode") not in (None, "", "전체") or f.get("zone") not in (None, "", "전체"))


def filter_events(evs: list[dict], f: dict, now=None, ignore_period: bool = False) -> list[tuple[dict, list[str]]]:
    """조건에 맞는 기록과, 검색이 표에 안 보이는 칸에서 맞았으면 그 칸 이름. 시간 순(오래된 것부터)."""
    now = now or system_now()
    kinds, levels, types = _many(f, "kinds"), _many(f, "levels"), _many(f, "types")
    rulesets, flags = _many(f, "rulesets"), _many(f, "flags")
    src = f.get("src") or ""
    toks = tokens(f.get("q"))
    days = None if ignore_period else PERIODS.get(str(f.get("period", "14")), 14)
    out = []
    for ev in evs:
        k = kind_of(ev)
        if f.get("kinds") == "detect" and k not in DETECT_KINDS:      # 예전 호출
            continue
        if f.get("mode") not in (None, "", "전체") and (ev.get("mode") or "-") != f["mode"]:
            continue
        if f.get("alert") == "alert" and not ev.get("alerted"):
            continue
        if f.get("alert") == "shadow" and (ev.get("alerted") or k not in DETECT_KINDS):
            continue
        if f.get("zone") not in (None, "", "전체") and ev.get("zone") != f["zone"]:
            continue
        if days == 0 and ev["_ts"].date() != now.date():
            continue
        if days and not (now - timedelta(days=days) < ev["_ts"]):
            continue
        if kinds and k not in kinds:
            continue
        if levels and level_of(ev) not in levels:
            continue
        if types and (ev.get("violation_type") or "") not in types:
            continue
        if rulesets and (ev.get("ruleset") or NO_RULESET) not in rulesets:
            continue
        if flags:
            on = {"adj": bool(ev.get("adj_id")), "fp": bool(ev.get("false_positive")), "media": has_media(ev)}
            if not any(on.get(x) for x in flags):
                continue
        if src == "sample" and src_kind(ev) != "sample":
            continue
        if src == "live" and src_kind(ev) != "live":
            continue
        if src not in ("", "sample", "live") and ev.get("_src") != src:
            continue
        hit = match(ev, toks)
        if hit is None:
            continue
        out.append((ev, hit))
    return out


def facets(evs: list[dict]) -> dict:
    """고를 수 있는 값 — 기록에 실제로 있는 것만, 많은 순."""
    def count(fn):
        c: dict = {}
        for e in evs:
            v = fn(e)
            if v is not None:
                c[v] = c.get(v, 0) + 1
        return sorted(c.items(), key=lambda x: (-x[1], str(x[0])))
    kinds = dict(count(kind_of))
    levels = dict(count(level_of))
    sessions = count(lambda e: e.get("_src") if src_kind(e) == "live" else None)
    return {"kinds": [{"v": k, "label": KIND_T[k], "n": kinds.get(k, 0)} for k in KIND_ORDER if kinds.get(k)],
            "levels": [{"v": lv, "label": LEVEL_T[lv], "n": levels.get(lv, 0)} for lv in LEVELS if levels.get(lv)],
            "types": [{"v": v, "label": v or "(없음)", "n": n} for v, n in count(lambda e: e.get("violation_type") or "")],
            "rulesets": [{"v": v, "label": v, "n": n} for v, n in count(lambda e: e.get("ruleset") or NO_RULESET)],
            "flags": [{"v": k, "label": t, "n": sum(1 for e in evs if (e.get("adj_id") if k == "adj" else e.get("false_positive")
                                                                            if k == "fp" else has_media(e)))}
                      for k, t in FLAGS.items()],
            "sources": ([{"v": "sample", "label": "예시 데이터", "n": sum(1 for e in evs if src_kind(e) == "sample")}]
                        if any(src_kind(e) == "sample" for e in evs) else [])
                       + ([{"v": "live", "label": "실시간 세션 전체", "n": sum(n for _, n in sessions)}] if sessions else [])
                       + [{"v": s, "label": s, "n": n} for s, n in sorted(sessions, reverse=True)]}
