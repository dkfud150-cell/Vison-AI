"""
관제 — 트리거형 안전관제 한 프로그램의 사이드바 메뉴 묶음 '관제'

  실시간 관제 · 격리 목록 대조 · 이벤트 로그 · 재생 비교 · 피드백 · 조정 로그 · 히트맵 · 통계

탐지 · 판정은 monitor_engine(엔진)이 하고, 여기는 엔진을 돌리고 보여 주고 기록을 넘기는 곳이다.
문서는 docgen(문서 자동화)이 만든다 — 관제는 감지 내역을 넘길 뿐이다(관제 인계).

  session.py    실시간 세션 — 시연 시계 · 신호 스케줄(CSV) · 버튼 · 영상 · 기록 · 자동 인계
  isolation.py  격리 목록 대조 — 허가서 등록(입력 창구) · 계통도 대조 · 맹판 · 퍼지 · 측정 단계 입력
  feedback.py   피드백 루프 — 이탈 조건 · 자동 조정(기한부 강화) · 조정 로그 · 승격 · 되돌리기
  replay.py     재생 비교 — 시나리오를 규칙셋별로 돌려 나란히 · 기대 결과 대조
  stats.py      히트맵 · 모드 대비 · 안전모
  views.py      화면 조각(HTML) — Gradio 화면용 (예비)
  pages.py      Gradio 화면 여섯 개 — control_section() (예비 · app_gradio.py)
기본 화면은 폴더 맨 위 web/ (화면 시안 그대로의 HTML) — web/api_control.py 가 여기 함수를 부른다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent            # 안전관제/
for _p in (ROOT / "docgen", ROOT / "monitor_engine"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
