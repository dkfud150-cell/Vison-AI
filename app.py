"""
트리거형 안전관제 — 한 프로그램 (관제 대시보드 + 문서 자동화)

    python app.py            → 브라우저가 열린다 (http://127.0.0.1:7860)

화면은 화면 시안(자료 › 안전관제_대시보드.html)의 디자인 그대로다 — web/static/.
왼쪽 사이드바
  관제          실시간 관제 · 격리 목록 대조 · 이벤트 로그 · 재생 비교 · 피드백 · 조정 로그 · 히트맵 · 통계   (control/)
  문서 자동화   홈 · 의무 이행 관리 · 안전 문서 · 안전소통 · 기록                                              (docgen/)
관제 엔진(판정)은 monitor_engine/, 사업장 설정은 monitor_engine/packages/<사업장>/ 에 있다.
경보는 화면 오른쪽 위에 팝업으로 뜬다. 관제 화면에서 '문서 자동화로 넘기기'를 누르면 안전 문서 › 관제 인계가 열린다.
"""
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in (ROOT / "monitor_engine", ROOT / "docgen", ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from control.common import PackageMissing, setup_env  # noqa: E402

try:
    setup_env()      # 문서 자동화가 같은 사업장 패키지(구역 이름 · 배관 계통도)를 읽게 — 문서 자동화를 읽기 전에
except PackageMissing as ex:
    sys.exit(f"\n[사업장 패키지 없음] {ex}\n")

from web.server import create_app  # noqa: E402

app = create_app()


if __name__ == "__main__":
    import argparse

    import uvicorn
    ap = argparse.ArgumentParser(description="트리거형 안전관제 — 관제 대시보드 + 문서 자동화")
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--host", default="127.0.0.1", help="같은 망의 다른 PC 에서 보려면 0.0.0.0")
    ap.add_argument("--no-browser", action="store_true", help="브라우저를 열지 않는다")
    a = ap.parse_args()
    url = f"http://{'127.0.0.1' if a.host in ('0.0.0.0', '') else a.host}:{a.port}"
    print(f"\n  트리거형 안전관제 — {url}\n  끄려면 이 창에서 Ctrl+C\n")
    if not a.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
