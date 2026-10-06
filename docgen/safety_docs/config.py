"""
설정 파일과 기록 파일을 읽고 쓰는 곳.

이벤트는 두 곳에서 읽어 합친다.
  - 샘플        ../예시데이터_삭제가능/문서자동화/events.json   (기능 확인용. 폴더를 지우거나 .env 의 DOCGEN_SAMPLE_DATA=off 면 안 읽는다)
  - 관제 인계   records/monitor_events.jsonl       (관제 화면이 감지 내역을 넘기면 handoff.py 가 한 줄씩 추가한다)
DB로 바꿀 때는 load_events() 한 곳만 바꾸면 된다 (아래 load_events_mysql 예시).

기록(records/)은 전부 '추가 전용'이다. 한 줄씩 덧붙이기만 하고 고치거나 지우지 않는다.
같은 문서의 상태가 바뀌면 새 줄을 쓰고, 읽을 때 마지막 줄을 그 문서의 현재 상태로 본다.
"""
from __future__ import annotations

import csv
import io
import json
import os
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = ROOT / "outputs"
RECORD_DIR = ROOT / "records"
CACHE_DIR = ROOT / "cache"
MOCK_DIR = ROOT / "mock"

load_dotenv(ROOT / ".env")

# 기능 확인용 예시 데이터 — 시스템 코드와 따로 둔다. 실제 데이터를 받으면 이 폴더를 통째로 지운다.
#   ../예시데이터_삭제가능/문서자동화/  샘플 이벤트 · 프레임 · 허가서 · 제보 · 사업장 정보(시연 날짜 · 사고 · 마지막 실시일) · 담당자
# 폴더가 없으면 샘플 없이 돈다(기록 records/ 과 설정 config/ 만).
SAMPLE_ROOT = Path(os.getenv("SAMPLE_ROOT") or (ROOT.parent / "예시데이터_삭제가능")).resolve()
SAMPLE_DIR = SAMPLE_ROOT / "문서자동화"


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_scales() -> dict:
    return _load_json(CONFIG_DIR / "scales.json")


def site_package() -> Path | None:
    """
    사업장 패키지 폴더 (관제 엔진이 읽는 site.json 이 있는 곳). 한 프로그램(폴더 맨 위 app.py)이 SITE_PACKAGE 로 알려 준다.
    있으면 구역 이름 · 배관 계통도를 거기서 읽는다 — 관제와 문서 자동화가 같은 원본을 본다.
    없으면(문서 자동화만 따로 켤 때) config/ 의 파일을 쓴다.
    """
    p = os.getenv("SITE_PACKAGE", "").strip()
    if p and (Path(p) / "site.json").exists():
        return Path(p)
    return None


def _site() -> dict | None:
    pkg = site_package()
    return _load_json(pkg / "site.json") if pkg else None


def load_rulesets() -> dict:
    rs = _load_json(CONFIG_DIR / "rulesets.json")
    site = _site()
    if site:   # 구역 이름은 사업장 패키지가 원본 — 없는 구역만 채운다
        for z, meta in site.get("zones", {}).items():
            if not z.startswith("_"):
                rs.setdefault("zones", {}).setdefault(z, meta.get("name", z))
    return rs


def load_legal() -> dict:
    """조문 목록을 {id: 조문} 사전으로 돌려준다."""
    data = _load_json(CONFIG_DIR / "legal_articles.json")
    return {a["id"]: a for a in data["articles"]}


def load_documents() -> dict:
    """문서 종류별 법적 근거·보존 기간."""
    return _load_json(CONFIG_DIR / "documents.json")["documents"]


def load_piping() -> dict:
    """
    배관 계통도. 사업장 패키지가 있으면 site.json 의 references.piping 을 원본으로 읽어 이 모양으로 바꾼다
    ({구역: {equipment, lines: [{line_id, name, fluid, hazard_source}]}}). 인접 구역은 config/piping.json 에서.
    """
    local = _load_json(CONFIG_DIR / "piping.json")
    site = _site()
    ref = (site or {}).get("references", {}).get("piping")
    if not ref:
        return local
    equip = (site or {}).get("references", {}).get("equipment", {})
    out = {"_설명": "사업장 패키지 site.json 의 references.piping 에서 읽음", "adjacent_zones": local.get("adjacent_zones", {})}
    for z, items in ref.items():
        if z.startswith("_") or not isinstance(items, list):
            continue
        name = (equip.get(z) or [{}])[0].get("name") or local.get(z, {}).get("equipment") or z
        out[z] = {"equipment": name,
                  "lines": [{"line_id": i["id"], "name": i.get("name", ""), "fluid": i.get("fluid", ""),
                             "hazard_source": i.get("hazard")} for i in items]}
    return out


def load_cases() -> dict:
    return _load_json(CONFIG_DIR / "incident_cases.json")


def load_profile() -> dict:
    """
    사업장 정보 (config/site_profile.json). 예시 데이터를 쓰는 동안은 예시 폴더의 site_profile.json 을 덮어 읽는다
    — 시연 날짜(demo_today) · 샘플 사고 · 마지막 실시일. 예시 폴더를 지우면 이 파일 값과 진짜 시각으로 돈다.
    """
    prof = _load_json(CONFIG_DIR / "site_profile.json")
    if use_sample_data() and (SAMPLE_DIR / "site_profile.json").exists():
        prof.update({k: v for k, v in _load_json(SAMPLE_DIR / "site_profile.json").items() if not k.startswith("_")})
    return prof


def load_staff() -> list[dict]:
    """
    담당자 목록 (config/staff.json) — 예시 데이터를 쓰는 동안은 예시 담당자를 뒤에 붙인다.
    부를 때마다 파일을 다시 읽는다 — 고치면 바로 반영된다.
    """
    staff = list(_load_json(CONFIG_DIR / "staff.json")["staff"])
    if use_sample_data() and (SAMPLE_DIR / "staff.json").exists():
        have = {p["id"] for p in staff}
        staff += [p for p in _load_json(SAMPLE_DIR / "staff.json")["staff"] if p["id"] not in have]
    return staff


def staff_label(p: dict) -> str:
    return f"{p['name']} · {p.get('dept') or '-'} · {p.get('position') or '-'}"


MONITOR_EVENTS = RECORD_DIR / "monitor_events.jsonl"   # 관제에서 넘어온 감지 내역 (handoff.py 가 추가만 한다)
FP_MARKS = RECORD_DIR / "false_positive_marks.jsonl"   # 오탐 표시 (관제 이벤트 로그에서 누른 것) — 추가 전용


def false_positive_marks() -> dict[str, dict]:
    """오탐 표시의 마지막 상태. undo=true 인 줄이 마지막이면 표시가 풀린 것이다."""
    out: dict[str, dict] = {}
    for r in read_jsonl(FP_MARKS):
        if r.get("undo"):
            out.pop(r["event_id"], None)
        else:
            out[r["event_id"]] = r
    return out


def use_sample_data() -> bool:
    """
    예시 데이터(샘플 이벤트 · 허가서 · 제보 · 조정 · 시연 날짜)를 같이 읽을지.
    예시 폴더(../예시데이터_삭제가능/문서자동화)가 있고 .env 의 DOCGEN_SAMPLE_DATA 가 off 가 아닐 때만 읽는다.
    """
    if os.getenv("DOCGEN_SAMPLE_DATA", "on").strip().lower() in ("0", "off", "false", "no"):
        return False
    return SAMPLE_DIR.exists()


def sample_file(rel: str | None) -> str | None:
    """예시 데이터 안의 상대 경로(frames/… · ptw/…) → 절대 경로. 문서 자동화 폴더 밖에 있어도 그대로 열린다."""
    return str(SAMPLE_DIR / rel) if rel else None


def _naive(ts: str) -> datetime:
    """시각 문자열 → datetime. 시간대가 붙어 오면 떼어 낸다 (샘플 · 관제 기록은 모두 현지 시각)."""
    t = datetime.fromisoformat(ts)
    return t.replace(tzinfo=None) if t.tzinfo else t


def load_events(path: str | Path | None = None, include_received: bool = True) -> tuple[list[dict], datetime]:
    """
    이벤트 로그와 기준 시각(as_of)을 읽는다.
      - path 를 주면 그 파일만 읽는다 (run_demo.py --events).
      - 주지 않으면 예시 이벤트(예시데이터_삭제가능/문서자동화/events.json) + 관제에서 넘어온 감지 내역(records/monitor_events.jsonl).
    기준 시각은 파일에 적힌 as_of 와 가장 최근 이벤트 시각 중 늦은 쪽. 이벤트가 하나도 없으면 지금.
    부를 때마다 파일을 다시 읽는다 — 관제가 새로 넘긴 내역이 바로 반영된다.
    """
    events, stamps = [], []
    if path or use_sample_data():
        data = _load_json(Path(path) if path else SAMPLE_DIR / "events.json")
        rows = data["events"] if isinstance(data, dict) else data
        if not path:                            # 예시 프레임은 예시 폴더 기준 → 절대 경로로 바꿔 둔다
            rows = [{**e, "frame_path": sample_file(e.get("frame_path"))} for e in rows]
        events += rows
        if isinstance(data, dict) and data.get("as_of"):
            stamps.append(_naive(data["as_of"]))
    if include_received and not path:
        events += read_jsonl(MONITOR_EVENTS)
    fp = false_positive_marks()
    for e in events:
        e["_ts"] = _naive(e["ts"])
        if e["event_id"] in fp:                  # 오탐 표시는 따로 쌓아 두고 읽을 때 덮는다 (원본 기록은 고치지 않는다)
            e["false_positive"] = True
            e["fp_by"] = fp[e["event_id"]].get("by", "")
    if events:
        stamps.append(max(e["_ts"] for e in events))
    return events, (max(stamps) if stamps else now().replace(microsecond=0))


# 참고: MySQL에서 읽을 때의 모양 (pymysql 예시, 해커톤 DB가 준비되면 사용)
# def load_events_mysql(conn, days=90):
#     sql = """SELECT event_id, ts, zone, mode, violation_type, level, alerted, adj_id,
#                     false_positive, clip_path, frame_path
#              FROM events WHERE ts >= NOW() - INTERVAL %s DAY"""
#     with conn.cursor(pymysql.cursors.DictCursor) as cur:
#         cur.execute(sql, (days,))
#         rows = cur.fetchall()
#     for r in rows:
#         r["_ts"] = r["ts"]; r["ts"] = r["ts"].isoformat()
#     return rows, datetime.now()


# ------------------------------------------------------------------ 기록 (추가 전용)
def read_jsonl(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_jsonl(path: Path, row: dict) -> dict:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def latest_by(rows: list[dict], key: str) -> dict[str, dict]:
    """같은 키의 줄이 여러 개면 마지막 줄을 현재 상태로 본다."""
    out: dict[str, dict] = {}
    for r in rows:
        out[r[key]] = {**out.get(r[key], {}), **r}
    return out


def read_csv(path_or_bytes) -> list[dict]:
    """엑셀에서 저장한 CSV(UTF-8 BOM 또는 CP949)도 읽는다."""
    raw = Path(path_or_bytes).read_bytes() if not isinstance(path_or_bytes, bytes) else path_or_bytes
    for enc in ("utf-8-sig", "cp949"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("CSV 인코딩을 읽을 수 없습니다 (UTF-8 또는 CP949로 저장해 주세요).")
    return [{k.strip(): (v or "").strip() for k, v in row.items() if k} for row in csv.DictReader(io.StringIO(text))]


# ------------------------------------------------------------------ 표시
def legal_ref(a: dict) -> str:
    """조문 표시 문자열. 기준규칙은 공식 약칭(안전보건규칙)으로 줄인다."""
    law = {"산업안전보건기준에 관한 규칙": "안전보건규칙",
           "중대재해 처벌 등에 관한 법률 시행령": "중대재해처벌법 시행령"}.get(a["law"], a["law"])
    return f"{law} {a['article']}({a['title']})"


def zone_name(rulesets: dict, zone: str) -> str:
    return rulesets.get("zones", {}).get(zone, zone)


def llm_provider() -> str:
    """LLM_PROVIDER 환경변수: mock | claude | openai (기본 mock)"""
    return os.getenv("LLM_PROVIDER", "mock").strip().lower()


def now() -> datetime:
    """
    시스템 시각. 사업장 정보에 demo_today 가 있으면 그 날짜에 지금 시각을 붙인다.
    예시 데이터(2026-10-12 기준)와 서명 · 발행 날짜가 어긋나지 않게 하려는 것이다.
    demo_today 는 예시 폴더의 site_profile.json 에만 있다 — 예시 폴더를 지우면 진짜 시각을 쓴다.
    """
    real = datetime.now()
    try:
        demo = load_profile().get("demo_today")
    except (OSError, ValueError):
        demo = None
    if not demo:
        return real
    return datetime.combine(date.fromisoformat(demo), real.time()).replace(microsecond=0)


def parse_date(s, year: int | None = None) -> date:
    """
    손으로 친 날짜를 하나의 양식(YYYY-MM-DD)으로 맞춘다.
      2026-10-12 · 2026.10.12 · 2026/10/12 · 20261012 · 2026년 10월 12일 · 26.10.12 · 2026-10-12 00:00:00
      10.12 · 10/12 · 10월 12일 처럼 연도를 빼면 year(없으면 오늘의 연도)로 채운다.
    """
    import re
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    text = str(s or "").strip().rstrip(".")
    sep, sep2 = r"\s*[-./년]\s*", r"\s*[-./월]\s*"
    m = (re.match(rf"^(\d{{4}}){sep}(\d{{1,2}}){sep2}(\d{{1,2}})", text)
         or re.match(r"^(\d{4})(\d{2})(\d{2})$", text)
         or re.match(rf"^(\d{{2}}){sep}(\d{{1,2}}){sep2}(\d{{1,2}})\s*일?$", text))
    if m:
        y, mo, d = (int(g) for g in m.groups())
        y = y + 2000 if y < 100 else y
    else:
        m = re.match(rf"^(\d{{1,2}}){sep2}(\d{{1,2}})\s*일?$", text)
        if not m:
            raise ValueError(f"날짜를 읽을 수 없습니다: '{text}' (예: 2026-10-12)")
        y, (mo, d) = year or now().year, (int(g) for g in m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        raise ValueError(f"없는 날짜입니다: '{text}'") from None


def to_date(s) -> date | None:
    if not s:
        return None
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    return datetime.fromisoformat(str(s)[:10]).date()
