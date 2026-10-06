"""
한 프로그램의 틀 — 왼쪽 사이드바(메뉴 묶음) + 오른쪽에 화면 하나씩.

관제 대시보드와 문서 자동화는 별개 프로그램이 아니라 이 틀 하나에 메뉴 묶음으로 들어간다.

    from safety_docs.shell import Section, sidebar_app
    from safety_docs.ui import docgen_section

    from control.pages import control_section                                  # 관제 여섯 화면 (폴더 맨 위 control/)
    app = sidebar_app([control_section(), docgen_section()], title="트리거형 안전관제")
    app.demo.launch(**app.launch_kwargs)

묶음마다 build(ctx) 를 하나 준다. gr.Blocks 안에서 불리고, 화면마다 `with ctx.page("id"):` 안에 컴포넌트를 만든다.
    ctx.provider                       문장 생성(mock · Claude · OpenAI) 드롭다운 — 사이드바 아래에 하나
    ctx.on_show(pid, fn, inputs, outputs)   그 화면을 열 때마다 부를 함수 (차례대로 이어 부른다)
    ctx.link(button, pid, then=[...])  화면 안의 버튼으로 다른 화면 열기
    ctx.refs                           묶음끼리 주고받을 것 (예: 'docgen.open_handoff' — 관제 → 인계 화면 열기)
    ctx.after(fn)                      모든 묶음을 만든 뒤 fn(ctx) 를 부른다. 이때는 ctx.goto_event() 를 쓸 수 있다
"""
from __future__ import annotations

import html
import inspect
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable

import gradio as gr

from .config import ROOT, SAMPLE_ROOT, llm_provider

GR6 = int(gr.__version__.split(".")[0]) >= 6
e = html.escape


@dataclass
class Section:
    label: str                                   # 사이드바 묶음 이름 (관제 · 문서 자동화)
    pages: list[tuple[str, str]]                 # (화면 id, 메뉴 이름) — 순서대로 메뉴가 된다
    build: Callable[["Ctx"], None]               # 화면을 만드는 함수
    subtitle: Callable[[], str] | None = None    # 화면 제목 아래 한 줄 (기준일 · 기록 건수 등)
    badges: Callable[[], dict] | None = None     # 메뉴 옆 숫자 {화면 id: 건수} — 화면을 옮길 때마다 다시 센다


class Ctx:
    def __init__(self, provider, first: str):
        self.provider = provider
        self.first = first
        self.columns: dict[str, gr.Column] = {}
        self.shows: dict[str, list[tuple]] = {}
        self.links: list[tuple] = []
        self.refs: dict[str, object] = {}
        self._after: list[Callable[["Ctx"], None]] = []
        self.nav_outputs: list = []              # 틀이 채운다 (after 단계부터 쓸 수 있다)
        self.goto: Callable[[str], list] | None = None

    @contextmanager
    def page(self, pid: str):
        with gr.Column(visible=(pid == self.first)) as col:
            yield col
        self.columns[pid] = col

    def on_show(self, pid: str, fn, inputs=None, outputs=None):
        self.shows.setdefault(pid, []).append((fn, inputs, outputs))

    def link(self, button, pid: str, then: list[tuple] | None = None):
        self.links.append((button, pid, list(then or [])))

    def after(self, fn: Callable[["Ctx"], None]):
        self._after.append(fn)

    def goto_event(self, event, pid: str):
        """이어지는 이벤트가 성공하면 '그 화면 열기 + 화면을 열 때 부를 함수'를 붙인다 (실패하면 화면을 옮기지 않는다)."""
        ev = event.success(lambda: self.goto(pid), outputs=self.nav_outputs)
        for fn, inp, out in self.shows.get(pid, []):
            ev = ev.then(fn, inputs=inp, outputs=out)
        return ev


@dataclass
class App:
    demo: gr.Blocks
    ctx: Ctx
    launch_kwargs: dict = field(default_factory=dict)


CSS = """
.gradio-container{max-width:1360px!important}
.table-container td,.table-container th,.table-container .cell-wrap{font-family:var(--font)!important;font-size:13px}
.brand{padding:2px 4px 10px;border-bottom:1px solid var(--border-color-primary);margin-bottom:6px}
.brand b{display:block;font-size:16px;letter-spacing:-.01em}.brand span{font-size:12px;color:var(--body-text-color-subdued)}
.nav-h{font-size:11.5px;font-weight:700;letter-spacing:.06em;color:var(--body-text-color-subdued);margin:14px 4px 4px}
button.nav-btn{justify-content:flex-start!important;text-align:left!important;font-weight:500!important;box-shadow:none!important;min-height:34px}
button.nav-btn.secondary{background:transparent!important;border-color:transparent!important}
button.nav-btn.secondary:hover{background:var(--background-fill-secondary)!important}
.side-foot{margin-top:14px;font-size:12px;color:var(--body-text-color-subdued)}
.pg-hd{border-bottom:2px solid var(--body-text-color);padding:2px 2px 6px;margin-bottom:4px}
.pg-hd .crumb{font-size:12px;font-weight:600;color:var(--body-text-color-subdued)}
.pg-hd .t{font-size:22px;font-weight:700;letter-spacing:-.01em;line-height:1.3}
.pg-hd .s{font-size:13px;color:var(--body-text-color-subdued)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:4px 0 8px}
.card{border:1px solid var(--border-color-primary);border-radius:8px;padding:12px 16px;background:var(--block-background-fill)}
.card .t{font-size:13px;font-weight:600;color:var(--body-text-color-subdued)}
.card .n{font-size:30px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.2;margin:2px 0 4px}
.card ul{margin:0;padding-left:16px;font-size:13px}
.sec{font-size:15px;font-weight:700;margin:18px 0 8px}
.tbl{width:100%;border-collapse:collapse;font-size:13px}
.tbl th{text-align:left;font-weight:600;font-size:12.5px;color:var(--body-text-color-subdued);border-bottom:1.5px solid var(--body-text-color);padding:6px 8px;white-space:nowrap}
.tbl td{border-bottom:1px solid var(--border-color-primary);padding:7px 8px;vertical-align:top}
.two{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media (max-width:760px){.two{grid-template-columns:1fr}}
.strip{display:flex;gap:3px;margin:4px 0 8px}.strip i{width:18px;height:18px;border-radius:3px;background:#2a6340}.strip i.gap{background:#c0574a}
.chip{display:inline-block;font-size:12px;font-weight:600;padding:2px 8px;border-radius:999px;white-space:nowrap;margin:1px 2px 1px 0}
.chip.ok{background:#e3f0e7;color:#2a6340}.chip.warn{background:#fcebcf;color:#865003}.chip.crit{background:#f8dfdb;color:#9d2416}
.chip.note{background:#f5efcc;color:#6b5a00}.chip.mute{background:#eceef1;color:#565d66}
.muted{color:var(--body-text-color-subdued);font-size:12.5px}
"""

THEME = gr.themes.Base(
    font=[gr.themes.GoogleFont("IBM Plex Sans KR"), "Malgun Gothic", "Apple SD Gothic Neo", "sans-serif"],
    primary_hue=gr.themes.colors.slate, neutral_hue=gr.themes.colors.gray, radius_size="sm",
).set(button_primary_background_fill="#1c1f23", button_primary_text_color="#ffffff",
      button_primary_background_fill_hover="#3a3f45")


def _header(crumb: str, title: str, sub: str) -> str:
    return (f"<div class='pg-hd'><div class='crumb'>{e(crumb)}</div><div class='t'>{e(title)}</div>"
            + (f"<div class='s'>{sub}</div>" if sub else "") + "</div>")


def sidebar_app(sections: list[Section], *, title: str = "트리거형 안전관제", brand: str = "트리거형 안전관제",
                brand_sub: str = "", foot: str = "", css: str = "", allowed_paths: list[str] | None = None) -> App:
    """
    allowed_paths  화면이 내려받기 · 그림으로 내보낼 수 있는 폴더. docgen 폴더(outputs · records)와 예시 데이터 폴더는
                   늘 들어간다 — 프로그램을 어느 폴더에서 켜도 워드 · 엑셀 · 프레임이 화면에 뜨게 하려는 것.
    """
    order = [(sec, pid, label) for sec in sections for pid, label in sec.pages]
    if not order:
        raise ValueError("메뉴가 비었습니다")
    pids = [pid for _, pid, _ in order]
    if len(set(pids)) != len(pids):
        raise ValueError(f"화면 id 가 겹칩니다: {pids}")
    first = pids[0]
    style = {"theme": THEME, "css": CSS + css}

    with gr.Blocks(title=title, **({} if GR6 else style)) as demo:
        # gr.Sidebar 는 Gradio 5.16 부터 있다 (requirements.txt). 폭 지정은 버전에 따라 없을 수 있어 있을 때만 준다
        side_kw = {"width": 250} if "width" in inspect.signature(gr.Sidebar.__init__).parameters else {}
        side = gr.Sidebar(open=True, **side_kw)
        with side:
            gr.HTML(f"<div class='brand'><b>{e(brand)}</b><span>{e(brand_sub)}</span></div>")
            buttons = {}
            for sec in sections:
                gr.HTML(f"<div class='nav-h'>{e(sec.label)}</div>")
                for pid, label in sec.pages:
                    buttons[pid] = gr.Button(label, size="sm", elem_classes="nav-btn",
                                             variant="primary" if pid == first else "secondary")
            gr.HTML("<div class='side-foot'>문장 생성 (문서 초안)</div>")
            provider = gr.Dropdown([("mock — API 키 없이", "mock"), ("Claude", "claude"), ("OpenAI", "openai")],
                                   value=llm_provider(), show_label=False, container=False)
            if foot:
                gr.HTML(f"<div class='side-foot'>{foot}</div>")

        header = gr.HTML(_header(order[0][0].label, order[0][2], ""))
        ctx = Ctx(provider, first)
        for sec in sections:
            sec.build(ctx)
        missing = [p for p in pids if p not in ctx.columns]
        if missing:
            raise ValueError(f"화면을 만들지 않은 메뉴가 있습니다: {missing} — build 안에서 ctx.page(id) 로 만든다")

        meta = {pid: (sec, label) for sec, pid, label in order}
        ctx.nav_outputs = [header] + [ctx.columns[p] for p in pids] + [buttons[p] for p in pids]

        def counts() -> dict:
            out = {}
            for sec in sections:
                if sec.badges:
                    try:
                        out.update(sec.badges())
                    except Exception:  # noqa: BLE001 — 숫자를 못 세도 화면은 옮긴다
                        pass
            return out

        def goto(target: str) -> list:
            sec, label = meta[target]
            sub = sec.subtitle() if sec.subtitle else ""
            n = counts()
            return ([_header(sec.label, label, sub)]
                    + [gr.update(visible=(p == target)) for p in pids]
                    + [gr.update(variant="primary" if p == target else "secondary",
                                 value=meta[p][1] + (f"  ({n[p]})" if n.get(p) else "")) for p in pids])

        ctx.goto = goto
        for fn in ctx._after:
            fn(ctx)

        def wire(event, target, then):
            ev = event(lambda: goto(target), outputs=ctx.nav_outputs)
            for fn, inp, out in ctx.shows.get(target, []) + then:
                ev = ev.then(fn, inputs=inp, outputs=out)

        for pid, b in buttons.items():
            wire(b.click, pid, [])
        for b, pid, then in ctx.links:
            wire(b.click, pid, then)
        wire(demo.load, first, [])

    launch = {"allowed_paths": [str(ROOT)] + ([str(SAMPLE_ROOT)] if SAMPLE_ROOT.exists() else [])
              + [str(p) for p in (allowed_paths or [])]}
    return App(demo=demo, ctx=ctx, launch_kwargs={**(style if GR6 else {}), **launch})
