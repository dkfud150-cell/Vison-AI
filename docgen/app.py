"""
문서 자동화 — 트리거형 안전관제 (한 프로그램의 사이드바 메뉴 묶음)

  홈 · 의무 이행 관리 · 안전 문서(관제 인계 · 위험성평가 · 시정지시서 · 작업허가서 점검 · 산업재해조사표)
  · 안전소통 · 기록

실행:  python app.py   →  브라우저에서 http://127.0.0.1:7860
       관제 화면 없이 문서 자동화 묶음만 띄운다. 관제에서 넘길 내역은
       안전 문서 › 관제 인계 › '관제 엔진 결과 파일로 넘기기' 로 넣어 볼 수 있다.

관제 대시보드와 합친 프로그램은 폴더 맨 위 app.py 다 (관제 화면 control/ + 이 묶음).
자세한 연결 방법은 README.md '한 프로그램 — 관제와 합친 진입점'.

원칙: 숫자는 코드가 계산하고, 문장만 AI가 쓰고, 확정은 사람이 한다.
"""
print("화면 준비 중... (처음엔 10~30초 걸릴 수 있어요)", flush=True)

from safety_docs.config import load_profile  # noqa: E402
from safety_docs.shell import sidebar_app  # noqa: E402
from safety_docs.ui import docgen_section  # noqa: E402

app = sidebar_app([docgen_section()], title="문서 자동화 — 트리거형 안전관제",
                  brand="트리거형 안전관제", brand_sub=f"{load_profile()['site_name']} · 문서 자동화만",
                  foot="관제까지 한 번에 띄우려면 폴더 맨 위 app.py")
demo = app.demo

if __name__ == "__main__":
    # 준비가 끝나면 브라우저가 자동으로 열린다. 이 창을 닫으면 화면도 꺼진다.
    demo.launch(inbrowser=True, **app.launch_kwargs)
