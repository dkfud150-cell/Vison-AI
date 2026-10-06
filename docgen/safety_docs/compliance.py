"""
의무 이행 관리 — 사업장 규모·업종별 법정 의무, 근거 조문, 기한, 보존 기간, 다가오면 알림

두 종류의 기한
  달력형 : 마지막 실시일 + 주기 (위험성평가 정기, 중처법 반기 점검, 산보위, 작업환경측정, 교육)
  사건형 : 사건 발생일 + 기한 (산업재해조사표, 중대재해 보고, 수시평가, 시정지시 조치, 제보 조치)
           → 사건형은 이 시스템의 기록(사고, 수시평가 제안, 시정지시서, 안전소통 제보)에서 자동으로 생긴다.

완료 처리
  records/compliance_done.jsonl 에 한 줄씩 추가만 한다 (수정·삭제 없음).
  담당자는 config/staff.json 에서 고르고, 이름 · 부서 · 직책이 함께 남는다. 이행일은 YYYY-MM-DD 로 맞춘다.
  확정된 위험성평가(관리자 + 근로자 대표 서명)는 정기평가 · 해당 행의 수시평가 완료로 자동 인정한다.
  안전소통 제보는 '완료'로 바뀌면 일정에서 빠진다.
"""
from __future__ import annotations

import calendar
import json
import re
from datetime import date, timedelta

from .assessment import list_assessments
from .config import CONFIG_DIR, RECORD_DIR, load_staff, now, parse_date, read_jsonl
from .config import to_date as _d
from .corrective import list_correctives
from .risk import row_key
from .voice import list_reports

DONE_LOG = RECORD_DIR / "compliance_done.jsonl"


# ------------------------------------------------------------------ 읽기
def load_obligations() -> dict:
    return json.loads((CONFIG_DIR / "obligations.json").read_text(encoding="utf-8"))


def done_records() -> list[dict]:
    """완료 기록: 화면에서 누른 이행 처리 + 확정된 위험성평가."""
    recs = read_jsonl(DONE_LOG)
    for ra in list_assessments():
        if ra["state"] != "confirmed" or not ra.get("confirmed_at"):
            continue
        day = ra["confirmed_at"][:10]
        if "정기" in ra.get("kind", ""):
            recs.append({"ob_id": "ra_regular", "done_date": day, "by": ra["manager"], "ref": ra["ra_id"],
                         "note": "위험성평가 확정(정기)"})
        for r in ra.get("rows", []):
            recs.append({"ob_id": "adhoc_review", "done_date": day, "by": ra["manager"], "ref": row_key(r),
                         "note": f"{ra['ra_id']} 확정으로 수시평가 반영"})
    return recs


def last_done(ob_id: str, profile: dict, recs: list[dict], ref: str | None = None) -> date | None:
    """의무별 마지막 실시일. ref 가 있으면 그 사건(사고 번호·문서 번호)에 대한 완료만 본다."""
    days = []
    if ref is None and profile.get("last_done", {}).get(ob_id):
        days.append(_d(profile["last_done"][ob_id]))
    for r in recs:
        if r["ob_id"] != ob_id:
            continue
        if ref is not None and r.get("ref") not in (ref, "*"):
            continue
        days.append(_d(r["done_date"]))
    return max(days) if days else None


# ------------------------------------------------------------------ 대상 판정
def applicable(ob: dict, profile: dict) -> tuple[bool, str]:
    """사업장 조건으로 이 의무가 해당되는지. (해당 여부, 이유)"""
    cond = ob.get("applies_if", {})
    w = int(profile.get("workers", 0))
    if w < cond.get("min_workers", 0):
        return False, f"상시근로자 {w}명 < 기준 {cond['min_workers']}명"
    inds = cond.get("industries")
    if inds and profile.get("industry") not in inds:
        return False, f"업종 기준({', '.join(inds)})에 해당하지 않음"
    for req in cond.get("requires", []):
        if not profile.get(req):
            label = {"hazardous_agents": "측정 대상 유해인자 노출"}.get(req, req)
            return False, f"{label} 없음"
    parts = [f"상시근로자 {w}명 ≥ {cond.get('min_workers', 0)}명"]
    if inds:
        parts.append(profile.get("industry"))
    if cond.get("requires"):
        parts.append("유해인자 노출")
    return True, " · ".join(parts)


# ------------------------------------------------------------------ 날짜 계산
def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def period_bounds(d: date, period: str) -> tuple[date, date]:
    """d 가 속한 기간(분기·반기·연)의 첫날과 마지막 날."""
    if period == "year":
        return date(d.year, 1, 1), date(d.year, 12, 31)
    size = 3 if period == "quarter" else 6
    start_m = (d.month - 1) // size * size + 1
    end_m = start_m + size - 1
    return date(d.year, start_m, 1), date(d.year, end_m, calendar.monthrange(d.year, end_m)[1])


def calendar_due(ob: dict, last: date | None, today: date) -> tuple[date, str]:
    """(기한, 설명)"""
    cyc = ob["cycle"]
    if cyc["type"] == "rolling":
        if not last:
            return today, "실시 기록 없음"
        return add_months(last, cyc["months"]), f"직전 {last:%Y-%m-%d} + {cyc['months']}개월"

    # 기간형: 이번 기간 안에 1회
    p_start, p_end = period_bounds(today, cyc["period"])
    label = {"quarter": "분기", "half": "반기", "year": "연"}[cyc["period"]]
    prev_start, _ = period_bounds(p_start - timedelta(days=1), cyc["period"])
    if last and last >= p_start:
        # 이번 기간은 끝냄 → 다음 기간 말일
        _, next_end = period_bounds(p_end + timedelta(days=1), cyc["period"])
        return next_end, f"이번 {label} 실시 완료({last:%m-%d}) · 다음 {label}"
    if not last or last < prev_start:
        # 직전 기간도 안 했다 → 이미 기한을 놓친 것
        _, prev_end = period_bounds(prev_start, cyc["period"])
        return prev_end, f"직전 {label} 미실시" + (f" (마지막 {last:%Y-%m-%d})" if last else "")
    return p_end, f"이번 {label} 안에 1회 (직전 {last:%Y-%m-%d})"


def status_of(due: date, today: date, alert_days: list[int]) -> tuple[str, str, int]:
    """(표시, 등급, D-값). 등급: overdue / urgent / soon / upcoming / ok"""
    dd = (due - today).days
    if dd < 0:
        return f"🔴 기한 경과 {-dd}일", "overdue", dd
    a = sorted(alert_days)          # 예: [1, 7, 30]
    if dd <= a[0]:
        return ("🔴 오늘 마감" if dd == 0 else f"🔴 D-{dd}"), "urgent", dd
    if len(a) > 1 and dd <= a[1]:
        return f"🟠 D-{dd}", "soon", dd
    if len(a) > 2 and dd <= a[2]:
        return f"🟡 D-{dd}", "upcoming", dd
    return f"🟢 D-{dd}", "ok", dd


# ------------------------------------------------------------------ 일정표
def build_schedule(profile: dict, today: date, adhoc: list[dict] | None = None,
                   adhoc_date: date | None = None) -> tuple[list[dict], list[dict]]:
    """
    반환: (일정 목록, 대상 판정 목록)
    adhoc      : risk.check_adhoc_review() 결과 (수시평가 제안)
    adhoc_date : 제안이 뜬 날 (기본 today)
    """
    obs = load_obligations()
    alert = obs["alert_days"]
    recs = done_records()
    items, judged = [], []

    def add(ob, due, why, kind, ref=None, name=None, doc=None, basis=None, verified=None, category=None):
        label, level, dd = status_of(due, today, alert)
        items.append({"ob_id": ob["id"], "kind": kind, "name": name or ob["name"], "doc": doc or ob["doc"],
                      "ref": ref or "", "category": category or ob.get("category", ""),
                      "due": due.isoformat(), "status": label, "level": level, "d": dd,
                      "why": why, "basis": basis or ob["basis"], "retention": ob.get("retention", ""),
                      "verified": "확인됨" if (ob["verified"] if verified is None else verified) else "원문 확인 필요"})

    # 달력형
    for ob in obs["calendar"]:
        ok, reason = applicable(ob, profile)
        judged.append({"의무": ob["name"], "구분": ob.get("category", ""), "대상": "대상" if ok else "비대상",
                       "판정 이유": reason, "주기": _cycle_text(ob), "근거 조문": ob["basis"],
                       "서류 보존": ob.get("retention", "")})
        if not ok:
            continue
        last = last_done(ob["id"], profile, recs)
        due, why = calendar_due(ob, last, today)
        add(ob, due, why, "달력형")

        fu = ob.get("follow_up")
        if fu and last:
            rep = last_done(fu["id"], profile, recs)
            if not rep or rep < last:          # 이번 측정에 대한 보고를 아직 안 함
                add({**ob, "id": fu["id"]}, last + timedelta(days=fu["days"]),
                    f"측정 {last:%Y-%m-%d} + {fu['days']}일", "달력형", name=fu["name"], doc="결과 보고",
                    basis=fu["basis"], verified=fu["verified"], category="보고")

    ev = {e["id"]: e for e in obs["event"]}

    # 사건형 ① 사고 → 산업재해조사표 / 중대재해 보고
    for acc in profile.get("accidents", []):
        a_day = _d(acc["date"])
        if acc.get("fatal"):
            e = ev["serious_report"]
            if not last_done(e["id"], profile, recs, ref=acc["id"]):
                add(e, a_day, f"{acc['id']} {acc['summary']} — {e['deadline_rule']}", "사건형", acc["id"])
        if acc.get("fatal") or acc.get("lost_days", 0) >= 3:
            e = ev["accident_report"]
            if not last_done(e["id"], profile, recs, ref=acc["id"]):
                add(e, add_months(a_day, 1),
                    f"{acc['id']} {acc['summary']} (휴업 {acc.get('lost_days', 0)}일) — {e['deadline_rule']}",
                    "사건형", acc["id"])

    # 사건형 ② 수시평가 제안 → 그 행이 들어간 확정 평가가 제안일 이후에 있으면 완료
    e = ev["adhoc_review"]
    a_day = adhoc_date or today
    for a in adhoc or []:
        ref = row_key(a)
        done = last_done(e["id"], profile, recs, ref=ref)
        if done and done >= a_day:
            continue
        add(e, a_day + timedelta(days=e["days"]),
            f"{a['zone']} {a['mode']} {a['violation_type']} — {', '.join(a['reasons'])}", "사건형", ref)

    # 사건형 ③ 시정지시서 → 조치 기한
    e = ev["corrective"]
    for row in list_correctives():
        if last_done(e["id"], profile, recs, ref=row["doc_no"]):
            continue
        add(e, _d(row["deadline_date"]),
            f"{row['doc_no']} · {row['zone']} {row['violation_type']} (중대성 {row['severity']})",
            "사건형", row["doc_no"])

    # 사건형 ④ 안전소통 제보 → 조치 기한 (완료되면 빠진다)
    e = ev.get("voice_action")
    if e:
        for r in list_reports():
            if r["state"] == "완료":
                continue
            add(e, _d(r["ts"]) + timedelta(days=e["days"]),
                f"{r['report_id']} {r['kind']} · {r['zone']} · {r['state']}", "사건형", r["report_id"])

    items.sort(key=lambda x: (x["d"], x["name"]))
    return items, judged


def _cycle_text(ob) -> str:
    c = ob["cycle"]
    if c["type"] == "rolling":
        return f"{c['months']}개월마다"
    return {"quarter": "분기 1회", "half": "반기 1회", "year": "연 1회"}[c["period"]]


def alert_summary(items: list[dict]) -> dict:
    out = {"overdue": 0, "urgent": 0, "soon": 0, "upcoming": 0, "ok": 0}
    for it in items:
        out[it["level"]] += 1
    return out


def mark_done(ob_id: str, done_date, staff_id: str, ref: str = "", note: str = "",
              today: date | None = None) -> dict:
    """
    이행 처리 — 한 줄 추가.
    담당자는 staff.json 의 id 로만 받는다(직접 입력 없음). 이행일은 YYYY-MM-DD 로 맞추고,
    기준일(today)보다 뒤이면 받지 않는다.
    """
    staff = {p["id"]: p for p in load_staff()}
    if staff_id not in staff:
        raise ValueError("담당자를 목록에서 고르세요. 목록은 config/staff.json 에 있습니다.")
    day = parse_date(done_date, year=today.year if today else None)
    if today and day > today:
        raise ValueError(f"이행일 {day} 이 기준일 {today} 보다 뒤입니다.")
    p = staff[staff_id]
    row = {"ob_id": ob_id, "done_date": day.isoformat(), "by": p["name"], "by_id": p["id"],
           "by_dept": p.get("dept", ""), "by_position": p.get("position", ""), "ref": ref,
           "note": note.strip(), "logged_at": now().isoformat(timespec="seconds")}
    RECORD_DIR.mkdir(parents=True, exist_ok=True)
    with open(DONE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _keep_until(retention: str, day: date) -> str:
    """'5년 (고시 물질이 들어 있으면 30년) — 조문' → '5년 · 2031-10-10까지 (고시 물질 30년)'. 조문은 해야 할 일 표에 있다."""
    head = retention.split(" — ")[0].strip()
    m = re.match(r"^(\d+)년\s*(.*)$", head)
    if not m:
        return head or "-"
    years, extra = int(m.group(1)), m.group(2).strip()
    try:
        until = day.replace(year=day.year + years)
    except ValueError:                       # 2월 29일
        until = day.replace(year=day.year + years, day=28)
    extra = re.sub(r"\(고시 물질이 들어 있으면 (\d+년)\)", r"(고시 물질 \1)", extra)
    return f"{years}년 · {until}까지" + (f" {extra}" if extra else "")


def _ob_index() -> dict:
    """ob_id → 의무 이름 · 구분 · 서류 보존 (후속 의무 포함)."""
    obs = load_obligations()
    idx = {}
    for ob in obs["calendar"] + obs["event"]:
        idx[ob["id"]] = ob
        fu = ob.get("follow_up")
        if fu:
            idx[fu["id"]] = {**fu, "category": "보고", "retention": ob.get("retention", "")}
    return idx


def done_list(profile: dict, cats: list[str] | None = None) -> list[dict]:
    """
    이행 완료 기록 — 최근 이행일 순.
      직접 처리   : 화면에서 누른 이행 처리 (compliance_done.jsonl)
      자동 인정   : 확정된 위험성평가로 완료된 정기 · 수시평가
      사업장 정보 : site_profile.json 의 마지막 실시일 (시스템 도입 전 기록)
    옛 기록처럼 이름만 있으면 staff.json 에서 같은 이름을 찾아 부서 · 직책을 채운다.
    """
    idx = _ob_index()
    by_name = {p["name"]: p for p in load_staff()}
    direct = read_jsonl(DONE_LOG)
    rows = [(r, "직접 처리") for r in direct]
    rows += [(r, "자동 인정 — 위험성평가 확정") for r in done_records()[len(direct):]]
    rows += [({"ob_id": k, "done_date": v, "by": "", "ref": "", "note": ""}, "사업장 정보 (도입 전 기록)")
             for k, v in (profile.get("last_done") or {}).items()]
    out = []
    for r, src in rows:
        ob = idx.get(r["ob_id"], {"name": r["ob_id"], "category": "", "retention": ""})
        if cats and ob.get("category") not in cats:
            continue
        p = by_name.get(r.get("by", ""), {})
        out.append({"이행일": str(parse_date(r["done_date"])), "의무": ob["name"], "구분": ob.get("category", ""),
                    "대상": r.get("ref") or "-",
                    "담당자": r.get("by") or "-",
                    "부서": r.get("by_dept") or p.get("dept") or "-",
                    "직책": r.get("by_position") or p.get("position") or "-",
                    "비고": r.get("note") or "", "출처": src,
                    "기록 시각": (r.get("logged_at") or "").replace("T", " "),
                    "서류 보존": _keep_until(ob.get("retention", ""), parse_date(r["done_date"]))})
    out.sort(key=lambda x: (x["이행일"], x["기록 시각"]), reverse=True)
    return out
