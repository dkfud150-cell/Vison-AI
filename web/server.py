"""
화면 서버 — 화면 시안(자료 › 안전관제_대시보드.html)을 그대로 띄우고, 시안에 박혀 있던 예시 값 자리를
관제(control/) · 관제 엔진(monitor_engine/) · 문서 자동화(docgen/) 의 결과로 채운다.

  web/static/index.html   시안의 마크업 그대로 (사이드바 관제 6 · 문서 자동화 5 · 작업허가서 등록 창)
  web/static/dashboard.css 시안의 CSS 그대로
  web/static/app.css      시안에 없던 것만 — 경보 팝업 · 시연 제어 줄 · 확인 창
  web/static/app.js       시안의 그리기 함수 + /api 에서 값을 읽어 오는 부분
  web/api_control.py      관제 여섯 화면의 /api
  web/api_docs.py         문서 자동화 다섯 화면의 /api
"""
from __future__ import annotations

import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

STATIC = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    from safety_docs.llm import LLMError

    from control.common import PackageMissing

    from .api_control import router as control_router
    from .api_docs import router as docs_router

    app = FastAPI(title="트리거형 안전관제", docs_url=None, redoc_url=None)

    async def user_error(_: Request, ex: Exception):
        # 화면에서 고칠 수 있는 잘못(빈 칸 · 없는 번호 · 세션 없음 · 키 없음)은 문장 그대로 알림으로 보인다
        return JSONResponse({"error": str(ex).strip("'\"")}, status_code=400)

    for exc in (ValueError, RuntimeError, KeyError, LLMError, PackageMissing):
        app.add_exception_handler(exc, user_error)

    async def crash(_: Request, ex: Exception):
        traceback.print_exc()
        return JSONResponse({"error": f"처리 중 오류: {type(ex).__name__}: {ex}"}, status_code=500)

    app.add_exception_handler(Exception, crash)

    app.include_router(control_router)
    app.include_router(docs_router)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})

    return app
