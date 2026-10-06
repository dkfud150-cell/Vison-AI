"""
화면 없이 한 번에 돌려 보는 스크립트. 다섯 화면이 쓰는 계산을 순서대로 돌리고 문서를 만든다.

  python run_demo.py                  # .env 의 LLM_PROVIDER 로 실행 (기본 mock)
  python run_demo.py --provider claude
  python run_demo.py --provider openai

결과: outputs/ 에 위험성평가표(엑셀) · 시정지시서 · 작업허가서 점검 · 산업재해조사표(워드)
기록: records/ 에 시정지시 · 허가서 점검 · 조사표 작성 기록 (위험성평가 확정은 화면에서 사람이 한다)
"""
import argparse

from safety_docs.accident import build_accident_facts, draft_accident_report, log_accident_report
from safety_docs.assessment import build_rows, draft_assessment
from safety_docs.compliance import alert_summary, build_schedule
from safety_docs.config import (OUTPUT_DIR, load_events, load_legal, load_piping,
                                load_profile, load_rulesets, load_scales)
from safety_docs.corrective import draft_corrective_order, log_corrective
from safety_docs.export import accident_to_docx, assessment_to_excel, corrective_to_docx, ptw_to_docx
from safety_docs.home import home_summary
from safety_docs.llm import LLMClient
from safety_docs.ptw import (check_ptw, draft_ptw_notes, list_ptws, load_isolation,
                             log_ptw_check)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["mock", "claude", "openai"])
    ap.add_argument("--events", help="이벤트 JSON 경로 (기본: 예시 이벤트 + 관제 인계 기록)")
    args = ap.parse_args()

    scales, rulesets, legal, piping = load_scales(), load_rulesets(), load_legal(), load_piping()
    profile = load_profile()
    events, as_of = load_events(args.events)
    llm = LLMClient(args.provider)
    print(f"LLM: {llm.provider}  /  이벤트 {len(events)}건  /  기준 시각 {as_of}")

    # 안전 문서 ① 작업허가서 점검 — 08:00 허가 발급 시점
    print("\n[작업허가서 점검]")
    ptws = list_ptws()
    for p in ptws:
        chk = draft_ptw_notes(check_ptw(p, ptws, piping, rulesets, load_isolation(p)), legal, llm)
        path = ptw_to_docx(chk, OUTPUT_DIR / f"작업허가서점검_{p['ptw_id']}.docx")
        log_ptw_check(chk, str(path))
        print(f"  {p['ptw_id']} {chk['result']} — {', '.join(f['code'] for f in chk['findings']) or '없음'} → {path.name}")

    # 안전 문서 ② 시정지시서 — 프레임이 있는 위반 이벤트
    print("\n[시정지시서]")
    for ev in [e for e in events if e.get("frame_path")]:
        order = draft_corrective_order(ev, events, rulesets, legal, scales, llm, issued=as_of)
        path = corrective_to_docx(order, OUTPUT_DIR / f"시정지시서_{ev['event_id']}.docx")
        log_corrective(order, str(path))
        print(f"  {ev['event_id']} {ev['violation_type']} (기한 {order['deadline']}) → {path.name}")

    # 안전 문서 ③ 위험성평가 초안 — 확정은 화면에서 관리자 서명 → 근로자 확인
    rows, adhoc = build_rows(events, as_of, scales, profile.get("accidents"))
    print(f"\n[위험성평가] 평가 대상 {len(rows)}행, 수시평가 제안 {len(adhoc)}건")
    for r in rows:
        print(f"  {r['zone']} {r['mode']} {r['violation_type']}: 가능성 {r['likelihood']} × 중대성 {r['severity']}"
              f" = {r['score']} {r['grade']}{'  ← 수시평가' if r['adhoc_reasons'] else ''}")
    drafts = draft_assessment(rows, rulesets, legal, scales, llm)
    xlsx = assessment_to_excel(drafts, OUTPUT_DIR / "위험성평가표_초안.xlsx", rulesets=rulesets, scales=scales)
    print(f"  → {xlsx.name}")

    # 안전 문서 ④ 산업재해조사표 — 관제 이벤트와 이어진 사고
    print("\n[산업재해조사표]")
    for acc in profile.get("accidents", []):
        if not acc.get("event_ids"):
            continue
        rep = draft_accident_report(build_accident_facts(acc, events, rulesets, ptws), llm)
        path = accident_to_docx(rep, OUTPUT_DIR / f"산업재해조사표_{acc['id']}.docx", profile)
        log_accident_report(rep, str(path))
        print(f"  {acc['id']} 타임라인 {len(rep['timeline'])}줄 · 제출 기한 {rep['due']} → {path.name}")

    # 의무 이행 관리
    items, _ = build_schedule(profile, as_of.date(), adhoc, as_of.date())
    s = alert_summary(items)
    print(f"\n[의무 이행 관리] 기준일 {as_of.date()} · 기한 경과 {s['overdue']} · 1일 이내 {s['urgent']} · "
          f"7일 이내 {s['soon']} · 30일 이내 {s['upcoming']}")
    for it in items:
        if it["level"] != "ok":
            print(f"  {it['status']:<12} [{it['category']}] {it['name']} ({it['due']}) — {it['basis']}")

    # 홈
    h = home_summary(events, as_of, scales, profile, as_of.date())
    print("\n[홈] " + " · ".join(f"{c['title']} {c['num']}" for c in h["cards"]))
    ev = h["evidence"]
    print(f"  증빙 {ev['period']}: 기록된 날 {ev['recorded']}/{ev['days']} · 끊긴 날 {', '.join(ev['gaps']) or '없음'}")


if __name__ == "__main__":
    main()
