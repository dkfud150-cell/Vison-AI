"""
사고 레이더 — 공개 사고 사례를 우리 위험성평가와 대조한다 (LLM 없음)

  relevance()        사례와 우리 사업장의 관련도 (0~100, 코드 계산)
  our_coverage()     우리가 '감지하는' 요인과 '대책을 세운' 요인
  compare_case()     사례의 요인 중 우리 위험성평가에 대책이 없는 것
  radar()            관련도 순 목록 + 최고 경보와 같은 메커니즘인 사례에 '경보 관련' 표시

사례는 config/incident_cases.json. 요인 어휘(factor_vocab)가 같아야 코드로 대조된다.
대규모 사고 DB가 아니라 근거 사례 몇 건을 '대조'하는 화면이다.
"""
from __future__ import annotations


def our_coverage(rows: list[dict], assessments: list[dict], cases_cfg: dict,
                 ptw_checks: list[dict] | None = None) -> dict:
    """
    detected : 관제가 잡고 있는 위반 유형 + 작업허가서 점검에서 나온 항목이 다루는 요인
    planned  : 확정된 위험성평가 대책이 규칙 변경(R1~R4)으로 다루는 요인
    pending  : 서명 대기 중인 평가의 대책이 다루는 요인
    """
    fmap = cases_cfg["our_factor_map"]
    detected = set()
    for r in rows:
        detected |= set(fmap["violation"].get(r["violation_type"], []))
    for c in ptw_checks or []:
        for code in c.get("codes", []):
            detected |= set(fmap.get("ptw_finding", {}).get(code, []))
    planned, pending = set(), set()
    for ra in assessments:
        if ra["state"] == "rejected":
            continue
        target = planned if ra["state"] == "confirmed" else pending
        for row in ra.get("rows", []):
            for m in row.get("measures", []):
                target |= set(fmap["rule_change"].get(m.get("rule_id") or "", []))
    return {"detected": detected, "planned": planned, "pending": pending - planned}


def relevance(case: dict, profile: dict, detected: set) -> int:
    """업종 20 + 공정 30 × 겹친 비율 + 우리가 감지·점검한 요인과 겹친 것 1개당 12.5 (최대 50)."""
    score = 20 if case.get("industry") == profile.get("industry_group") else 0
    tags = set(case.get("process_tags", []))
    if tags:
        score += 30 * len(tags & set(profile.get("process_tags", []))) / len(tags)
    score += min(50, 12.5 * len(set(case.get("factors", [])) & detected))
    return round(score)


def compare_case(case: dict, cov: dict) -> list[dict]:
    """사례 요인마다 우리 상태: 대책 있음 / 서명 대기 / 감지만 / 없음."""
    out = []
    for f in case.get("factors", []):
        if f in cov["planned"]:
            st = "대책 있음"
        elif f in cov["pending"]:
            st = "대책 서명 대기"
        elif f in cov["detected"]:
            st = "감지·점검됨 — 평가표에 대책 없음"
        else:
            st = "없음 — 평가표에 없는 요인"
        out.append({"factor": f, "status": st})
    return out


def radar(cases_cfg: dict, profile: dict, rows: list[dict], assessments: list[dict],
          ptw_checks: list[dict] | None = None) -> list[dict]:
    """
    관련도 순. 최고 경보가 난 행의 요인과 2개 이상 겹치는 사례에는 '경보 관련' 표시를 단다
    (같은 메커니즘으로 난 사고라는 뜻).
    """
    cov = our_coverage(rows, assessments, cases_cfg, ptw_checks)
    hot = set()
    for r in rows:
        if r.get("top_alert_count"):
            hot |= set(cases_cfg["our_factor_map"]["violation"].get(r["violation_type"], []))
    out = []
    for c in cases_cfg["cases"]:
        cmp = compare_case(c, cov)
        gaps = [x["factor"] for x in cmp if not x["status"].startswith(("대책 있음", "대책 서명"))]
        out.append({**c, "relevance": relevance(c, profile, cov["detected"]),
                    "linked_alert": len(hot & set(c.get("factors", []))) >= 2,
                    "compare": cmp, "gaps": gaps})
    out.sort(key=lambda x: -x["relevance"])
    return out
