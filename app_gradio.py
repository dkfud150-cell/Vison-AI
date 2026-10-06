"""
트리거형 안전관제 — Gradio 화면으로 켜기 (예전 화면 · 예비)

    python app_gradio.py      → http://127.0.0.1:7860

기본 화면은 app.py (화면 시안 그대로의 HTML · web/) 다. 이 파일은 같은 기능을 Gradio 부품으로 그린 예전 화면이다.
계산 · 판정 · 기록은 두 화면이 같은 코드(control/ · monitor_engine/ · docgen/safety_docs/)를 부른다.
Gradio 화면 파일: control/pages.py · control/views.py (관제) · docgen/safety_docs/ui.py · shell.py (문서 자동화)
HTML 화면에만 있는 것: 경보 팝업 · 작업중지 지시 버튼(SESSION.stop_order) — Gradio 로 옮길 때는 버튼만 달면 된다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in (ROOT / "monitor_engine", ROOT / "docgen", ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from control.common import PackageMissing, package_dir, setup_env  # noqa: E402

try:
    setup_env()
except PackageMissing as ex:
    sys.exit(f"\n[사업장 패키지 없음] {ex}\n")

from safety_docs.shell import sidebar_app  # noqa: E402
from safety_docs.ui import docgen_section  # noqa: E402

from control.pages import control_section  # noqa: E402
from control.views import CSS  # noqa: E402


def build_app():
    return sidebar_app([control_section(), docgen_section()], title="트리거형 안전관제", brand="트리거형 안전관제",
                       brand_sub="관제 대시보드 + 문서 자동화", css=CSS,
                       foot="기록은 추가만 된다 · 숫자는 코드, 문장은 AI 초안, 확정은 사람",
                       allowed_paths=[str(ROOT / "control" / "records"), str(package_dir())])


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="트리거형 안전관제 — Gradio 화면 (예비)")
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--share", action="store_true")
    a = ap.parse_args()
    app = build_app()
    app.demo.queue().launch(server_port=a.port, inbrowser=not a.no_browser, share=a.share, **app.launch_kwargs)
