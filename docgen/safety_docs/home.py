"""
홈 — 오늘 처리할 것 · 구역별 문서 상태판 · 증빙 누적 현황 (LLM 없음)

다른 화면의 계산 함수를 그대로 불러 요약만 한다. 홈에서만 쓰는 숫자는 없다.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from .assessment import build_rows, list_assessments
from .compliance import build_schedule
from .corrective import list_correctives
from .ptw import list_ptw_checks
from .risk import row_key
from .voice import list_reports, voice_summary

EVIDENCE_DAYS = 14


def home_summary(events, as_of, scales, profile, today: date) -> dict:
    rows, adhoc = build_rows(events, as_of, scales, profile.get("accidents"))
    ras = list_assessments()
    items, _ = build_schedule(profile, today, adhoc, as_of.date())
    reports = list_reports()
    vs = voice_summary(reports)

    pending = [ra for ra in ras if ra["state"] == "worker_pending"]
    adhoc_open = [it for it in items if it["ob_id"] == "adhoc_review"]
    hot = [it for it in items if it["level"] in ("overdue", "urgent", "soon")]
    co_open = [it for it in items if it["ob_id"] == "corrective"]

    cards = [
        {"title": "확정 대기", "num": len(adhoc_open) + len(pending),
         "lines": [f"수시평가 제안 {len(adhoc_open)}건 — 초안 생성 필요",
                   f"근로자 확인 대기 {len(pending)}건 — 안전소통에서 확인"],
         "go": "안전 문서"},
        {"title": "기한 임박 의무", "num": len(hot),
         "lines": [f"{it['status']} {it['name']}" for it in hot[:3]] or ["30일 안에 마감되는 의무 없음"],
         "go": "의무 이행 관리"},
        {"title": "미조치", "num": len(co_open) + vs["open"],
         "lines": [f"시정지시 조치 대기 {len(co_open)}건", f"근로자 제보 미조치 {vs['open']}건"],
         "go": "안전소통"},
    ]

    # 구역 · 모드별 상태판
    confirmed_keys, pending_keys = set(), set()
    for ra in ras:
        keys = {row_key(r) for r in ra.get("rows", [])}
        if ra["state"] == "confirmed":
            confirmed_keys |= keys
        elif ra["state"] == "worker_pending":
            pending_keys |= keys
    open_adhoc = {it["ref"] for it in adhoc_open}          # 제안일 이후 확정된 평가가 없는 행
    open_docs = {it["ref"] for it in co_open}
    co_by_zone = defaultdict(int)
    for co in list_correctives():
        if co["doc_no"] in open_docs:
            co_by_zone[co["zone"]] += 1
    voice_by_zone = defaultdict(int)
    for r in reports:
        if r["state"] != "완료":
            voice_by_zone[r["zone"]] += 1
    ptw_by_zone = {c["zone"]: c for c in list_ptw_checks()}

    board = defaultdict(lambda: {"rows": []})
    for r in rows:
        board[(r["zone"], r["mode"])]["rows"].append(r)
    zone_rows = []
    for (zone, mode), b in sorted(board.items(), key=lambda kv: -max(x["score"] for x in kv[1]["rows"])):
        keys = {row_key(x) for x in b["rows"]}
        top = max(b["rows"], key=lambda x: x["score"])
        if keys & pending_keys:
            ra_state = "서명 대기"
        elif keys & open_adhoc:
            ra_state = "수시평가 필요"
        elif keys <= confirmed_keys:
            ra_state = "확정"
        else:
            ra_state = "정기평가 반영 대기"
        ptw = ptw_by_zone.get(zone)
        zone_rows.append({"zone": zone, "mode": mode, "score": top["score"], "grade": top["grade"],
                          "types": len(b["rows"]), "ra": ra_state,
                          "co": co_by_zone.get(zone, 0), "voice": voice_by_zone.get(zone, 0),
                          "ptw": ptw["result"] if ptw else "-"})

    # 증빙 누적 — 관제 기록은 사람이 쓰지 않아도 매일 쌓인다. 끊긴 날은 카메라·시스템 점검 대상
    start = as_of.date() - timedelta(days=EVIDENCE_DAYS - 1)
    days = {e["_ts"].date() for e in events if start <= e["_ts"].date() <= as_of.date()}
    gaps = [start + timedelta(days=i) for i in range(EVIDENCE_DAYS) if start + timedelta(days=i) not in days]
    evidence = {"period": f"{start} ~ {as_of.date()}", "days": EVIDENCE_DAYS, "recorded": len(days),
                "gaps": [d.isoformat() for d in gaps],
                "events": sum(1 for e in events if start <= e["_ts"].date() <= as_of.date()),
                "silent": sum(1 for e in events if start <= e["_ts"].date() <= as_of.date() and not e.get("alerted", True)),
                "docs": sum(1 for ra in ras if ra["state"] == "confirmed")}

    checklist = [it for it in items if it["kind"] == "달력형"][:5]
    return {"cards": cards, "zones": zone_rows, "evidence": evidence, "checklist": checklist,
            "rows": rows, "adhoc": adhoc, "items": items}
