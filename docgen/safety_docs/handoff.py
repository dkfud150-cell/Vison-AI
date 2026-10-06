"""
관제 → 문서 자동화 인계

관제 대시보드와 문서 자동화는 한 프로그램이다. 관제 화면에서 '문서 자동화로 넘기기'를 누르면
그 감지 내역이 여기로 들어오고, 문서 자동화의 이벤트로 합쳐져 보고서 초안의 근거가 된다.

  receive()            감지 내역 받기 — 프레임을 복사하고 records/monitor_events.jsonl 에 한 줄씩 추가
  receive_file()       관제 엔진 결과 파일(events.jsonl · events_for_docgen.json)에서 받기
                       — 문서 자동화만 띄웠을 때 엔진 결과로 바로 시험하는 길
  list_handoffs() · get_handoff()
  report_candidates()  인계 한 건에서 만들 수 있는 보고서 — 시정지시서 · 수시 위험성평가 · 허가서 점검 · 조사표
  make_correctives()   고른 이벤트로 시정지시서 초안 → 워드 · 발행 기록 (사람이 버튼을 눌렀을 때만)
  register_ptw()       관제 입력창에서 등록한 작업허가서 · 격리 목록을 점검 대상으로 저장

원칙
- 받은 내역은 고치거나 지우지 않는다(추가 전용). 같은 내역을 두 번 넘기면 두 번째는 건너뛴다.
- 넘기는 것만으로 문서가 발행되지 않는다. 보고서는 사람이 '만들기'를 눌러야 생긴다.
- 숫자(중대성 · 기한 · 위험도)는 코드가, 문장은 LLM이 쓰는 것은 다른 문서와 같다.

관제 코드에서 부르는 법 (같은 프로그램 안):
    from safety_docs.handoff import receive
    ho = receive(log.rows, source="실시간 관제", base_dir=out_dir)   # log = 엔진 EventLog, out_dir = 엔진 출력 폴더
    ho["handoff_id"]  → 문서 자동화 › 안전 문서 › 관제 인계 화면에서 이 번호로 연다
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from .config import (MONITOR_EVENTS, RECORD_DIR, ROOT, append_jsonl, now, read_csv, read_jsonl)

HANDOFF_LOG = RECORD_DIR / "handoffs.jsonl"
FRAME_DIR = RECORD_DIR / "monitor_frames"      # 넘어온 위반 순간 프레임 (시정지시서 이미지 분석 · 증빙)

# 문서 자동화가 읽는 이벤트 필드 — 관제 엔진 events.py 의 export_docgen() 과 같다
DOC_FIELDS = ("event_id", "ts", "zone", "mode", "violation_type", "level", "alerted",
              "adj_id", "false_positive", "clip_path", "frame_path")
# 관제 쪽 필드 중 같이 남겨 둘 것 — 보고서 근거(판정표 몇 번 줄 · 이유 · 적용 규칙셋)
EXTRA_FIELDS = ("kind", "row", "computed_level", "reason", "response", "axes", "ruleset", "applied_changes")
DETECT_KINDS = {"stage", "check"}              # 3축 판정 · 모드 규칙(영상). kind 가 없으면 감지로 본다
REPORT_LEVELS = ("경보", "최고 경보")            # 시정지시서 후보 = 경보 이상


# ------------------------------------------------------------------ 받기
def _existing_ids() -> dict[str, dict]:
    """이미 있는 이벤트 번호 — 샘플과 이전 인계 모두. 번호가 겹치지 않게 하려는 것."""
    from .config import load_events
    events, _ = load_events()
    return {e["event_id"]: e for e in events}


def _same(a: dict, b: dict) -> bool:
    return all(str(a.get(k)) == str(b.get(k)) for k in ("ts", "zone", "mode", "violation_type"))


def _new_handoff_id() -> str:
    base = f"HO-{now():%Y%m%d-%H%M%S}"
    taken = {h["handoff_id"] for h in read_jsonl(HANDOFF_LOG)}
    hid, n = base, 2
    while hid in taken:
        hid, n = f"{base}-{n}", n + 1
    return hid


def _resolve(p: str | None, base_dir: Path | None) -> Path | None:
    if not p:
        return None
    q = Path(p)
    if not q.is_absolute() and base_dir is not None:
        q = Path(base_dir) / q
    return q if q.exists() else None


def receive(events: list[dict], *, source: str = "관제", base_dir: str | Path | None = None,
            by: str = "", note: str = "", auto: bool = False) -> dict:
    """
    감지 내역을 받아 문서 자동화 이벤트로 합친다.

    events   관제 엔진 EventLog.rows 그대로, 또는 export_docgen() 모양(docgen 필드만)
    source   어디서 넘겼나 — 화면에 그대로 보인다 (예: '실시간 관제', '재생 비교 · 개정 전')
    base_dir clip_path · frame_path 가 상대 경로일 때 기준 폴더 (엔진 출력 폴더)
    auto     기록할 때마다 넘기는 길(집계 · 증빙 누적용)이면 True — 관제 인계 화면 목록에는 기본으로 숨긴다

    감지(kind = stage · check)만 이벤트로 합친다. 게이트 · 사고 · 참고는 인계 기록에만 남기고
    '만들 보고서' 안내(허가서 점검 · 조사표)로 쓴다 — 위험도 집계에 섞지 않는다.
    """
    base_dir = Path(base_dir) if base_dir else None
    hid = _new_handoff_id()
    existing = _existing_ids()
    received, duplicates, others, warnings = [], [], [], []

    for raw in events:
        kind = raw.get("kind")
        if kind and kind not in DETECT_KINDS:
            others.append({"kind": kind, "ts": raw.get("ts"), "zone": raw.get("zone"),
                           "violation_type": raw.get("violation_type"), "reason": raw.get("reason", ""),
                           "event_id": raw.get("event_id")})
            continue
        if not all(raw.get(k) for k in ("event_id", "ts", "zone", "violation_type")):
            warnings.append(f"필수 필드가 없어 건너뜀: {raw.get('event_id') or raw.get('ts') or '?'}")
            continue
        try:
            datetime.fromisoformat(str(raw["ts"]))
        except ValueError:
            warnings.append(f"시각을 읽을 수 없어 건너뜀: {raw['event_id']} ({raw['ts']})")
            continue

        ev = {k: raw.get(k) for k in DOC_FIELDS}
        ev["alerted"] = bool(raw.get("alerted", ev.get("level") is not None))
        ev["false_positive"] = bool(raw.get("false_positive", False))
        eid = str(ev["event_id"])
        if eid in existing:
            if _same(existing[eid], ev):
                duplicates.append(eid)            # 같은 내역을 다시 넘김 — 건너뛴다
                continue
            n = 2                                 # 번호만 같고 다른 내역 (엔진을 여러 번 돌린 경우)
            while f"{eid}-{n}" in existing:
                n += 1
            warnings.append(f"번호가 겹쳐 {eid} → {eid}-{n} 로 받음")
            eid = f"{eid}-{n}"
        ev["event_id"] = eid

        # 프레임은 복사해 둔다 — 엔진 출력 폴더를 지워도 시정지시서 근거가 남도록
        src = _resolve(raw.get("frame_path"), base_dir)
        if src is not None:
            FRAME_DIR.mkdir(parents=True, exist_ok=True)
            dst = FRAME_DIR / f"{eid}{src.suffix or '.jpg'}"
            shutil.copy2(src, dst)
            ev["frame_path"] = dst.relative_to(ROOT).as_posix()
        elif raw.get("frame_path"):
            warnings.append(f"{eid}: 프레임 파일을 찾지 못함 ({raw['frame_path']})")
            ev["frame_path"] = None
        clip = _resolve(raw.get("clip_path"), base_dir)
        if clip is not None:
            ev["clip_path"] = str(clip.resolve())   # 클립은 크기 때문에 복사하지 않고 위치만 남긴다

        ev.update({k: raw[k] for k in EXTRA_FIELDS if k in raw})
        ev.update({"handoff_id": hid, "source": source})
        append_jsonl(MONITOR_EVENTS, ev)
        existing[eid] = ev
        received.append(eid)

    header = {"handoff_id": hid, "ts": now().isoformat(timespec="seconds"), "source": source, "auto": auto,
              "by": by, "note": note, "base_dir": str(base_dir) if base_dir else None,
              "event_ids": received, "duplicates": duplicates, "others": others, "warnings": warnings}
    append_jsonl(HANDOFF_LOG, header)
    return header


def read_monitor_file(path: str | Path) -> list[dict]:
    """관제 엔진 결과 파일 — events.jsonl(한 줄 한 이벤트) 또는 events_for_docgen.json({"events": [...]})."""
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    return data["events"] if isinstance(data, dict) else data


def receive_file(path: str | Path, *, source: str | None = None, base_dir: str | Path | None = None,
                 by: str = "", note: str = "") -> dict:
    """엔진 출력 파일에서 받는다. 프레임 · 클립 경로는 그 파일이 있는 폴더 기준이다."""
    path = Path(path)
    return receive(read_monitor_file(path), source=source or f"엔진 결과 파일 · {path.name}",
                   base_dir=base_dir or path.parent, by=by, note=note)


# ------------------------------------------------------------------ 읽기
def list_handoffs(include_auto: bool = True) -> list[dict]:
    """인계 기록, 최근 것부터. include_auto=False 면 자동 인계(기록할 때마다 넘긴 것)는 뺀다."""
    return [h for h in reversed(read_jsonl(HANDOFF_LOG)) if include_auto or not h.get("auto")]


def mark_false_positive(event_id: str, by: str, reason: str = "", undo: bool = False) -> dict:
    """
    오탐 표시 (관제 이벤트 로그의 '오탐 표시' 버튼). 원본 기록은 고치지 않고 표시만 따로 쌓는다.
    표시된 이벤트는 위험성평가 집계에서 빠진다(config.load_events 가 덮는다). 누가 표시했는지 남는다 —
    오탐 버튼 악용을 막는 장치이고, 오탐을 근거로 한 완화는 사람이 승인해야 한다(피드백 2단).
    """
    from .config import FP_MARKS
    if not by.strip():
        raise ValueError("오탐 표시는 표시자 이름이 필요합니다")
    return append_jsonl(FP_MARKS, {"event_id": event_id, "ts": now().isoformat(timespec="seconds"),
                                   "by": by.strip(), "reason": reason.strip(), "undo": undo})


def get_handoff(handoff_id: str) -> dict | None:
    return next((h for h in read_jsonl(HANDOFF_LOG) if h["handoff_id"] == handoff_id), None)


def handoff_events(handoff_id: str, events: list[dict]) -> list[dict]:
    """
    인계 한 건의 내역 = 이번에 새로 받은 것 + 이미 받아 둔 것(중복).
    관제가 기록을 먼저 넘겨 두고(자동) 나중에 같은 내역을 버튼으로 다시 넘겨도 보고서 후보가 비지 않게 한다.
    """
    h = get_handoff(handoff_id) or {}
    ids = set(h.get("event_ids", [])) | set(h.get("duplicates", []))
    return sorted((e for e in events if e["event_id"] in ids), key=lambda e: e["ts"])


def report_candidates(handoff_id: str, events: list[dict], as_of: datetime, scales: dict,
                      accidents: list[dict] | None = None) -> dict:
    """
    인계 한 건으로 만들 수 있는 보고서를 코드가 고른다.
      시정지시서   경보 이상 · 오탐 아님 (이미 발행한 것은 표시만)
      위험성평가   이 인계의 이벤트가 들어간 행 중 수시평가 기준(위험도 12 · 중대성 4)에 걸린 것
      허가서 점검  게이트(작업 전 대조)가 막은 기록이 있으면
      조사표       사고 기록이 있으면 — 재해자 정보는 사람이 넣는다
    """
    from .assessment import build_rows
    from .corrective import list_correctives

    h = get_handoff(handoff_id) or {}
    evs = handoff_events(handoff_id, events)
    issued = {c["event_id"]: c["doc_no"] for c in list_correctives()}
    corrective = [{"event_id": e["event_id"], "ts": e["ts"], "zone": e["zone"], "mode": e.get("mode"),
                   "violation_type": e["violation_type"], "level": e.get("level"),
                   "frame": bool(e.get("frame_path")), "issued": issued.get(e["event_id"])}
                  for e in evs if e.get("alerted") and e.get("level") in REPORT_LEVELS
                  and not e.get("false_positive")]
    ids = {e["event_id"] for e in evs}
    rows, _ = build_rows(events, as_of, scales, accidents)
    adhoc = [{"zone": r["zone"], "mode": r["mode"], "violation_type": r["violation_type"],
              "score": r["score"], "grade": r["grade"], "reasons": r["adhoc_reasons"]}
             for r in rows if r["adhoc_reasons"] and ids & set(r["event_ids"] + r["adj_event_ids"])]
    others = h.get("others", [])
    return {"handoff": h, "events": evs, "corrective": corrective, "adhoc": adhoc,
            "gates": [o for o in others if o["kind"] == "gate"],
            "accidents": [o for o in others if o["kind"] == "accident"]}


# ------------------------------------------------------------------ 보고서 만들기
def make_correctives(event_ids: list[str], events: list[dict], rulesets: dict, legal: dict, scales: dict,
                     llm, issued: datetime | None = None, out_dir: Path | None = None) -> list[dict]:
    """
    고른 이벤트마다 시정지시서 초안을 만들고 워드로 저장 · 발행 기록을 남긴다.
    안전 문서 › 시정지시서 화면의 버튼과 같은 일을 여러 건에 한 번에 한다.
    """
    from .config import OUTPUT_DIR
    from .corrective import draft_corrective_order, log_corrective
    from .export import corrective_to_docx

    out_dir = out_dir or OUTPUT_DIR
    by_id = {e["event_id"]: e for e in events}
    made = []
    for eid in event_ids:
        ev = by_id.get(eid)
        if ev is None:
            continue
        order = draft_corrective_order(ev, events, rulesets, legal, scales, llm, issued=issued or now())
        path = corrective_to_docx(order, Path(out_dir) / f"시정지시서_{eid}.docx")
        log_corrective(order, str(path))
        made.append({"event_id": eid, "doc_no": order["doc_no"], "deadline": order["deadline"],
                     "severity": order["severity"], "path": str(path), "warnings": order["warnings"]})
    return made


# ------------------------------------------------------------------ 작업허가서 등록 (관제 입력창)
def register_ptw(ptw: dict, isolation: list[dict] | str | bytes | Path | None = None) -> dict:
    """
    관제 입력창에서 받은 작업허가서와 격리 목록을 문서 자동화의 점검 대상으로 저장한다.
    같은 파일이 관제 엔진에는 문서 입력 신호로, 여기서는 작업허가서 점검 대상으로 쓰인다.

    ptw        ptw_id · type(정비 · 화기) · zone · work · start · end 는 필수. 나머지는 예시 허가서(예시데이터_삭제가능/문서자동화/ptw)와 같은 모양
    isolation  격리 목록 — 행 목록, CSV 파일 경로, CSV 글자(bytes) 중 하나. 열: line_id, 배관, 격리방법, 맹판설치, 벤트, 가스측정
    이미 있는 번호는 덮어쓰지 않는다 (추가 전용).
    """
    import csv
    import io

    from .ptw import PTW_INBOX, list_ptws

    need = [k for k in ("ptw_id", "type", "zone", "work", "start", "end") if not ptw.get(k)]
    if need:
        raise ValueError(f"작업허가서 필수 항목이 비었습니다: {', '.join(need)}")
    if any(p["ptw_id"] == ptw["ptw_id"] for p in list_ptws()):
        raise ValueError(f"이미 있는 허가서 번호입니다: {ptw['ptw_id']} — 고칠 때는 새 번호로 다시 등록합니다")
    PTW_INBOX.mkdir(parents=True, exist_ok=True)
    rec = {**ptw, "registered_at": now().isoformat(timespec="seconds")}
    if isolation is not None:
        rows = isolation if isinstance(isolation, list) else read_csv(isolation)
        cols = ["line_id", "배관", "격리방법", "맹판설치", "벤트", "가스측정"]
        cols += [c for r in rows for c in r if c not in cols]
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(dict.fromkeys(cols)))
        w.writeheader()
        w.writerows(rows)
        iso_path = PTW_INBOX / f"isolation_{ptw['ptw_id']}.csv"
        iso_path.write_text(buf.getvalue(), encoding="utf-8-sig")
        rec["isolation_list_file"] = iso_path.relative_to(ROOT).as_posix()
    (PTW_INBOX / f"{ptw['ptw_id']}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return rec
