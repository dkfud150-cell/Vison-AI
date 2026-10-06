"""
관제 화면 조각 (HTML). 화면 시안(자료/안전관제_대시보드.html)의 모양을 따른다.
색은 통합 문서의 단계 색(정상 · 주의 · 경보 · 최고 경보)과 축 색(발생 · 축적 · 점화원 · 사람)을 그대로 쓴다.
"""
from __future__ import annotations

import base64
import html
from datetime import datetime

from .common import LEVEL_KIND, frame_file, zone_name

e = html.escape

CSS = """
.ctl{--ok:#2a6340;--ok-bg:#e3f0e7;--note:#6b5a00;--note-bg:#f5efcc;--warn:#865003;--warn-bg:#fcebcf;
 --crit:#9d2416;--crit-bg:#f8dfdb;--crit-strong:#c62828;--mute:#565d66;--mute-bg:#eceef1;
 --g:#a3620a;--g-bg:#fcf1de;--a:#3f5a7a;--a-bg:#e7eef6;--i:#b3261e;--i-bg:#fbeceb;--p:#2f6e73;--p-bg:#e6f2f2;
 --line:var(--border-color-primary);--ink2:var(--body-text-color-subdued);--panel2:var(--background-fill-secondary);
 --cam-bg:#2a2f36;--cam-floor:#3a4048;--cam-line:#5b636d}
.dark .ctl{--ok:#83d0a0;--ok-bg:#15291c;--note:#e2d27a;--note-bg:#2c2a14;--warn:#f1b660;--warn-bg:#302510;
 --crit:#f38f80;--crit-bg:#361a16;--crit-strong:#e5584a;--mute:#a9b0b8;--mute-bg:#24282d;
 --g:#f1b660;--g-bg:#302510;--a:#9db8d8;--a-bg:#1a2430;--i:#f38f80;--i-bg:#361a16;--p:#6cc3c8;--p-bg:#15282a}
.ctl{font-size:13.5px}
.ctl .lv{display:inline-block;font-size:12px;font-weight:600;padding:2px 9px;border-radius:999px;white-space:nowrap}
.ctl .lv.ok{background:var(--ok-bg);color:var(--ok)}.ctl .lv.note{background:var(--note-bg);color:var(--note)}
.ctl .lv.warn{background:var(--warn-bg);color:var(--warn)}.ctl .lv.crit{background:var(--crit-bg);color:var(--crit)}
.ctl .lv.mute{background:var(--mute-bg);color:var(--mute)}.ctl .lv.info{background:var(--a-bg);color:var(--a)}
.ctl .z{font:600 12px 'IBM Plex Mono',monospace;color:#6a5a12;background:#f6f2d9;padding:1px 5px;border-radius:3px;white-space:nowrap}
.dark .ctl .z{color:#d9c56a;background:#29261a}
.ctl .mono{font-family:'IBM Plex Mono',monospace}
.ctl .muted,.ctl .note{color:var(--ink2);font-size:12.5px}
.ctl .bar{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-top:8px;padding:8px 12px;border-radius:6px;font-size:13px;font-weight:600}
.ctl .bar.ok{background:var(--ok-bg);color:var(--ok)}.ctl .bar.note{background:var(--note-bg);color:var(--note)}
.ctl .bar.warn{background:var(--warn-bg);color:var(--warn)}.ctl .bar.crit{background:var(--crit-bg);color:var(--crit)}.ctl .bar.mute{background:var(--mute-bg);color:var(--mute)}
.ctl .status{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;font-size:13px;padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:var(--panel2)}
.ctl .status b{font-variant-numeric:tabular-nums}
.ctl .run{font-weight:700;color:var(--ok)}.ctl .stop{font-weight:700;color:var(--mute)}
.ctl .alarm{display:grid;grid-template-columns:auto 1fr;gap:14px;align-items:center;padding:12px 16px;border-radius:8px;background:var(--crit-bg);color:var(--crit);border-left:5px solid var(--crit-strong)}
.ctl .alarm.warn{background:var(--warn-bg);color:var(--warn);border-left-color:#d99a3c}
.ctl .alarm.note{background:var(--note-bg);color:var(--note);border-left-color:#b89b1a}
.ctl .alarm.calm{background:var(--ok-bg);color:var(--ok);border-left-color:#5aa37a}
.ctl .alarm .pill{font-weight:800;font-size:15px;padding:6px 12px;border-radius:6px;background:var(--crit-strong);color:#fff;white-space:nowrap}
.ctl .alarm.warn .pill{background:#c77d12}.ctl .alarm.note .pill{background:#9a820f}.ctl .alarm.calm .pill{background:#2a6340}
.ctl .alarm b{display:block;font-size:14.5px}.ctl .alarm em{font-style:normal;font-size:12.5px;opacity:.9}
.ctl .tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
.ctl .tile{border:1px solid var(--line);border-radius:8px;padding:8px 10px;display:flex;flex-direction:column;gap:2px}
.ctl .tile.crit{border-color:var(--crit-strong);background:var(--crit-bg)}.ctl .tile.warn{border-color:#d99a3c;background:var(--warn-bg)}
.ctl .tile.note{border-color:#b89b1a;background:var(--note-bg)}.ctl .tile.sel{outline:2px solid var(--body-text-color)}
.ctl .tile .zt{display:flex;justify-content:space-between;align-items:center;gap:6px}.ctl .tile .zn{font-weight:600}
.ctl .tile .zm,.ctl .tile .zp{font-size:12px;color:var(--ink2)}
.ctl .cam{position:relative;border-radius:8px;overflow:hidden;background:var(--cam-bg);line-height:0}
.ctl .cam img,.ctl .cam svg{width:100%;height:auto;display:block}
.ctl .cam .hud{position:absolute;left:0;right:0;top:0;display:flex;justify-content:space-between;padding:6px 10px;font:600 11.5px 'IBM Plex Mono',monospace;color:#e6e8eb;line-height:1.3;background:linear-gradient(#0009,#0000)}
.ctl .cam .empty{color:#9aa4af;padding:70px 18px;text-align:center;line-height:1.6;font-size:13px}
.ctl .axes{display:flex;flex-direction:column;gap:6px}
.ctl .ax{display:grid;grid-template-columns:62px 1fr auto;gap:10px;align-items:center;padding:8px 10px;border-radius:6px;border-left:4px solid}
.ctl .ax .nm{font-weight:700}.ctl .ax .st b{display:block;font-size:13.5px}.ctl .ax .st span{font-size:12px;opacity:.85}
.ctl .ax.g{background:var(--g-bg);color:var(--g);border-color:#e0a13a}.ctl .ax.a{background:var(--a-bg);color:var(--a);border-color:#5d7593}
.ctl .ax.i{background:var(--i-bg);color:var(--i);border-color:#c62828}.ctl .ax.p{background:var(--p-bg);color:var(--p);border-color:#2f6e73}
.ctl .ax.off{opacity:.55}
.ctl .dot{width:14px;height:14px;border-radius:50%;border:2px solid currentColor}.ctl .dot.on{background:currentColor}.ctl .dot.half{background:linear-gradient(90deg,currentColor 50%,transparent 50%)}
.ctl .judge{margin-top:10px;display:flex;flex-direction:column;gap:3px}
.ctl .judge .row{display:grid;grid-template-columns:24px 1fr auto;gap:8px;align-items:center;padding:4px 8px;border-radius:5px;font-size:12.5px;color:var(--ink2)}
.ctl .judge .row .n{font:600 12px 'IBM Plex Mono',monospace}
.ctl .judge .row.hit{background:var(--note-bg);color:var(--body-text-color);font-weight:600}.ctl .judge .row.hit.crit{background:var(--crit-bg)}.ctl .judge .row.hit.warn{background:var(--warn-bg)}
.ctl .judge .row.shadow{outline:1px dashed var(--ink2)}
.ctl .list{display:flex;flex-direction:column}
.ctl .list > div{display:grid;grid-template-columns:48px 1fr auto;gap:10px;align-items:center;padding:6px 2px;border-bottom:1px solid var(--line);font-size:13px}
.ctl .list .t{font:600 12px 'IBM Plex Mono',monospace;color:var(--ink2)}
.ctl .empty{color:var(--ink2);font-size:13px;padding:8px 0}
.ctl .cards2{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}
.ctl .hcard{border:1px solid var(--line);border-radius:8px;padding:10px 12px;display:flex;flex-direction:column;gap:4px}
.ctl .hcard.crit{border-color:var(--crit-strong);background:var(--crit-bg)}.ctl .hcard.warn{border-color:#d99a3c;background:var(--warn-bg)}
.ctl .hcard .hd{display:flex;justify-content:space-between;gap:8px;align-items:center}.ctl .hcard p{margin:0;font-size:13px}
.ctl .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
.ctl .kpi{border:1px solid var(--line);border-radius:8px;padding:10px 12px;display:flex;flex-direction:column}
.ctl .kpi span{font-size:12.5px;color:var(--ink2);font-weight:600}.ctl .kpi b{font-size:26px;line-height:1.25;font-variant-numeric:tabular-nums}
.ctl .kpi b.txt{font-size:17px}.ctl .kpi small{font-size:12px;color:var(--ink2)}
.ctl .kpi.crit{border-color:var(--crit-strong);background:var(--crit-bg)}.ctl .kpi.warn{border-color:#d99a3c;background:var(--warn-bg)}.ctl .kpi.ok{border-color:#5aa37a;background:var(--ok-bg)}
.ctl table.t{width:100%;border-collapse:collapse;font-size:13px}
.ctl table.t th{text-align:left;font-weight:600;font-size:12.5px;color:var(--ink2);border-bottom:1.5px solid var(--body-text-color);padding:6px 8px;white-space:nowrap}
.ctl table.t td{border-bottom:1px solid var(--line);padding:6px 8px;vertical-align:top}
.ctl table.t tr.hit td{background:var(--crit-bg)}.ctl table.t tr.gate td{background:var(--note-bg)}.ctl table.t tr.shadow td{color:var(--ink2)}
.ctl table.t tr.sel td{outline:2px solid var(--body-text-color)}
.ctl td.c{text-align:center;font-weight:700}.ctl td.c.y{color:var(--ok)}.ctl td.c.x{color:var(--crit)}.ctl td.c.d{color:var(--ink2)}
.ctl .svgwrap svg{width:100%;height:auto;display:block}
.ctl .stage-item{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:8px 10px;border:1px solid var(--line);border-radius:6px;margin-bottom:6px}
.ctl .stage-item.bad{border-color:var(--crit-strong);background:var(--crit-bg)}.ctl .stage-item .s{font-size:12px;color:var(--ink2)}
.ctl .versus{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
.ctl .vcard{border:1px solid var(--line);border-radius:8px;padding:10px 14px}.ctl .vcard.hot{border-color:#5aa37a;background:var(--ok-bg)}
.ctl .vcard.bad{border-color:var(--crit-strong);background:var(--crit-bg)}
.ctl .vcard .k{font-size:12.5px;color:var(--ink2);font-weight:600}.ctl .vcard .big{display:block;font-size:22px;font-weight:700;margin:2px 0}
.ctl .vcard p{margin:0;font-size:12.5px}
.ctl .expect > div{display:grid;grid-template-columns:22px 1fr;gap:8px;padding:5px 0;border-bottom:1px solid var(--line)}
.ctl .expect .y{color:var(--ok);font-weight:800}.ctl .expect .x{color:var(--crit);font-weight:800}
.ctl .diff{font:500 12.5px/1.6 'IBM Plex Mono',monospace;border:1px solid var(--line);border-radius:6px;padding:8px 10px;background:var(--panel2);overflow-x:auto}
.ctl .diff .add{color:var(--ok);background:var(--ok-bg)}.ctl .diff .del{color:var(--crit);background:var(--crit-bg)}.ctl .diff .ctx{color:var(--ink2)}
.ctl .steps{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:12.5px;color:var(--ink2)}
.ctl .steps span{padding:3px 9px;border-radius:999px;border:1px solid var(--line)}
.ctl .steps .done{background:var(--ok-bg);color:var(--ok);border-color:transparent}.ctl .steps .now{background:var(--warn-bg);color:var(--warn);border-color:transparent;font-weight:700}
.ctl .hbars{display:flex;flex-direction:column;gap:6px}
.ctl .hb{display:grid;grid-template-columns:150px 1fr 56px;gap:10px;align-items:center;font-size:13px}
.ctl .hb .tr{height:12px;border-radius:6px;background:var(--mute-bg);overflow:hidden}.ctl .hb .tr i{display:block;height:100%;background:#8b939d}
.ctl .hb .tr i.c{background:#d64532}.ctl .hb .tr i.w{background:#e0a13a}.ctl .hb .tr i.g{background:#4f9a6c}.ctl .hb b{text-align:right;font-variant-numeric:tabular-nums}
.ctl table.heat{border-collapse:separate;border-spacing:3px;font-size:12px}
.ctl table.heat th{font-weight:600;color:var(--ink2);padding:2px 4px}.ctl table.heat th.rh{text-align:left;white-space:nowrap}
.ctl table.heat td{width:34px;height:28px;text-align:center;border-radius:4px;font-variant-numeric:tabular-nums}
.ctl .h0{background:#f3f5f7;color:#8b939d}.ctl .h1{background:#fcebcf}.ctl .h2{background:#f6c98a}.ctl .h3{background:#e59052;color:#fff}.ctl .h4{background:#c0492e;color:#fff}
.dark .ctl .h0{background:#1c2126;color:#7a828b}.dark .ctl .h1{background:#302510;color:#f1b660}.dark .ctl .h2{background:#6b4a1a;color:#fff}
.ctl .legend{display:flex;gap:4px;align-items:center;font-size:12px;color:var(--ink2)}.ctl .legend i{width:18px;height:12px;border-radius:3px;display:inline-block}
.ctl .notes div{font-size:12.5px;padding:3px 0;border-bottom:1px dashed var(--line)}.ctl .notes .t{font:600 12px 'IBM Plex Mono',monospace;color:var(--ink2);margin-right:6px}
.ctl .sec{font-size:15px;font-weight:700;margin:6px 0 6px}
.ctl .ph{display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin-bottom:6px}.ctl .ph h3{margin:0;font-size:15px}.ctl .ph .sub{font-size:12.5px;color:var(--ink2)}
.ctl .rule{font:700 11.5px 'IBM Plex Mono',monospace;color:var(--a);background:var(--a-bg);padding:2px 6px;border-radius:4px}
.ctl-btns button{min-width:0!important}
.ctl table{border:none!important;margin:0}
.ctl table td,.ctl table th{border-left:none!important;border-right:none!important;border-top:none!important}
.ctl table.heat td,.ctl table.heat th{border:none!important}
.ctl td.mono,.ctl td .mono{white-space:nowrap}
"""

LV_TEXT = {None: "무음 기록", "": "무음 기록"}


def lv(level, alerted=True) -> str:
    if not alerted and level not in (None, ""):
        return f"<span class='lv mute'>무음 · {e(level)}</span>"
    return f"<span class='lv {LEVEL_KIND.get(level, 'mute')}'>{e(LV_TEXT.get(level, level))}</span>"


def z(zone) -> str:
    return f"<span class='z'>{e(zone or '-')}</span>"


def wrap(inner: str) -> str:
    return f"<div class='ctl'>{inner}</div>"


# ====================================================================== 실시간 관제
def status_bar(s: dict) -> str:
    m = s["meta"]
    run = (f"<span class='run'>▶ {s['speed']:g}×</span>" if s["running"] else "<span class='stop'>⏸ 멈춤</span>") if s["sid"] \
        else "<span class='stop'>시작 전 — 미리 보기</span>"
    nxt = s["next"]
    nxt_t = f"다음 {nxt.ts:%H:%M} {e(nxt.note or nxt.short())}" if nxt else "스케줄 끝 — 버튼으로 계속"
    on = [(zz, st["modes"]) for zz, st in s["zones"].items() if st["modes"]]
    video = f"영상 {e(s['scene'].get('name'))} ({e(s['scene'].get('at') or '-')})" if s["scene"] else "영상 없음 — 신호로만 판정"
    if s["video"]:
        video = f"<b>영상 재생 중</b> · {e(s['scene'].get('name'))}" + (f" · {e(s['video_note'])}" if s["video_note"] else "")
    return wrap(
        f"<div class='status'>{run}<span>시연 시계 <b>{s['now']:%Y-%m-%d %H:%M:%S}</b></span>"
        f"<span>세션 <b class='mono'>{e(s['sid'] or '-')}</b></span>"
        f"<span>스케줄 {e(m.get('schedule_title', ''))} · {nxt_t}</span>"
        f"<span>규칙 <b>{e(m.get('rules_label', ''))}</b></span>"
        f"<span>켜진 모드 <b>{sum(len(x) for _, x in on)}</b> · {len(on)}개 구역</span><span>{video}</span></div>")


def worst_zone(s: dict):
    order = {"최고 경보": 3, "경보": 2, "주의": 1, "정상": 0}
    best = None
    for zz, st in s["zones"].items():
        if st["alerting"] and (best is None or order[st["level"]] > order[best[1]["level"]]):
            best = (zz, st)
    return best


def alarm(s: dict) -> str:
    w = worst_zone(s)
    if not w or w[1]["level"] == "정상":
        shadow = [zz for zz, st in s["zones"].items() if not st["alerting"] and st["computed"] != "정상"]
        extra = f" · 무음으로 판정 중인 구역 {', '.join(shadow)} (모드가 꺼져 있어 경보 없이 기록만)" if shadow else ""
        return wrap(f"<div class='alarm calm'><span class='pill'>전 구역 정상</span><div><b>켜진 모드 안에서 걸린 판정이 없다.</b>"
                    f"<em>모드가 꺼진 구역의 검출은 무음 기록으로 남는다{e(extra)}</em></div></div>")
    zz, st = w
    others = [f"{k} {v['level']}" for k, v in s["zones"].items() if v["alerting"] and k != zz and v["level"] != "정상"]
    adj = s["adjust"].get(zz, {})
    adj_t = f" · 알림 단계 {adj['level']} (강화 중 {', '.join(adj['adj_ids'])})" if adj.get("adj_ids") else ""
    kind = LEVEL_KIND.get(st["level"], "note")
    return wrap(
        f"<div class='alarm {'' if kind == 'crit' else kind}'><span class='pill'>{e(st['level'])}</span><div>"
        f"<b>{z(zz)} {e(zone_name(zz))} — {e(st['reason'] or st['violation'] or '')}</b>"
        f"<em>판정표 {st['row'] or '-'}번 줄 · {st['since']:%H:%M}부터 · 대응: {e(st['response'] or '-')}{e(adj_t)}"
        f"{(' · 다른 구역: ' + e(', '.join(others))) if others else ''}</em></div></div>")


def zone_label(zz: str, st: dict) -> str:
    dot = {"최고 경보": "🔴", "경보": "🟠", "주의": "🟡"}.get(st["level"], "⚪" if not st["alerting"] and st["computed"] != "정상" else "🟢")
    return f"{dot} {zz} {zone_name(zz)}"


def tiles(s: dict, sel: str) -> str:
    out = []
    for zz, st in s["zones"].items():
        k = LEVEL_KIND.get(st["level"]) if st["alerting"] else "ok"
        cams = [c for c in _cams() if c.get("zone") == zz]
        lvl = lv(st["level"]) if st["alerting"] else (lv(st["computed"], False) if st["computed"] != "정상" else lv("정상"))
        out.append(f"<div class='tile {k if k != 'ok' else ''}{' sel' if zz == sel else ''}'><span class='zt'>{z(zz)}{lvl}</span>"
                   f"<span class='zn'>{e(zone_name(zz))}</span><span class='zm'>{e(' · '.join(st['modes']) or '평상시')}</span>"
                   f"<span class='zp'>사람 {st['people']} · 카메라 {len(cams)}</span></div>")
    return wrap(f"<div class='tiles'>{''.join(out)}</div>")


def _cams() -> list[dict]:
    from .common import package
    return list(package().cameras.values())


def camera_svg(cam: dict, active: bool, ignition: bool, label: str) -> str:
    """영상이 없을 때의 카메라 자리 — 폴리곤(화면 비율 좌표)과 지금 켜진 것만 그린다."""
    W, H = 640, 360
    s = [f"<svg viewBox='0 0 {W} {H}' role='img' aria-label='{e(label)}'>",
         f"<rect width='{W}' height='{H}' fill='var(--cam-bg)'/><polygon points='0,160 {W},130 {W},{H} 0,{H}' fill='var(--cam-floor)'/>",
         "<g stroke='var(--cam-line)' stroke-width='1'><line x1='0' y1='220' x2='640' y2='190'/><line x1='0' y1='290' x2='640' y2='260'/></g>"]
    from .scenes import all_types
    col = {k: v["color"] for k, v in all_types().items()}     # 기본 넷 + 관리자가 더한 종류
    for p in cam.get("polygons", []):
        if p.get("space", "image") != "image":
            continue
        pts = " ".join(f"{x * W:.0f},{y * H:.0f}" for x, y in p["points"])
        c = col.get(p.get("type"), "#9aa4af")
        on = active or p.get("type") == "hazard"   # hazard 만 상시. 나머지는 모드가 켜져야 (draw.py 와 같은 기준)
        s.append(f"<polygon points='{pts}' fill='{c}' fill-opacity='{0.10 if on else 0.04}' stroke='{c}' stroke-width='2' stroke-dasharray='7 5'/>")
        x0, y0 = p["points"][0]
        s.append(f"<text x='{x0 * W + 6:.0f}' y='{y0 * H + 16:.0f}' font-size='12' font-weight='700' fill='{c}' "
                 f"font-family='IBM Plex Mono,monospace'>{e(p.get('label') or p.get('name'))}{'' if on else ' · 무음 기록'}</text>")
    if ignition:
        s.append("<circle cx='250' cy='250' r='16' fill='#ffb74d' opacity='.45'/><circle cx='250' cy='250' r='7' fill='#fff3c4'/>"
                 "<text x='272' y='255' font-size='12' fill='#ffcc66' font-family='IBM Plex Sans KR,sans-serif'>점화원 (신호 입력)</text>")
    s.append(f"<text x='{W / 2:.0f}' y='{H - 16}' font-size='12.5' fill='#9aa4af' text-anchor='middle' "
             "font-family='IBM Plex Sans KR,sans-serif'>영상이 연결되지 않았다 — 폴리곤만 표시 · 판정은 신호(CSV · 버튼)로</text>")
    return "".join(s) + "</svg>"


def camera(s: dict, zone: str, cam_id: str | None) -> str:
    cams = [c for c in _cams() if c.get("zone") == zone]
    if not cams:
        return wrap("<div class='cam'><div class='empty'>이 구역에는 카메라가 없다.<br>신호(CSV 스케줄 · 버튼 · 입력창)로만 판정한다.</div></div>")
    cam = next((c for c in cams if c["camera_id"] == cam_id), cams[0])
    sc = s.get("scene") or {}
    if sc.get("polygons") and sc.get("camera") == cam["camera_id"]:      # 장면에 그린 구역이 있으면 그것
        cam = {**cam, "polygons": sc["polygons"]}
    st = s["zones"][zone]
    rec = s["frames"].get(cam["camera_id"])
    hud = (f"<div class='hud'><span>{e(cam['camera_id'])} · {e(zone)}</span>"
           f"<span>{'● REC ' if rec else ''}{s['now']:%H:%M:%S}</span></div>")
    if rec:
        img = f"<img alt='{e(cam['camera_id'])} 영상' src='data:image/jpeg;base64,{base64.b64encode(rec).decode()}'>"
        return wrap(f"<div class='cam'>{img}{hud}</div>")
    ign = ("ignition_manual", zone) in s["on"]
    return wrap(f"<div class='cam'>{camera_svg(cam, bool(st['modes']), ign, cam['camera_id'])}{hud}</div>")


def zone_log(s: dict, zone: str) -> str:
    today = s["now"].date().isoformat()
    rows = [r for r in s["rows"] if r.get("zone") == zone and str(r["ts"]).startswith(today)]
    if not rows:
        return wrap("<p class='empty'>이 세션의 오늘 기록 없음</p>")
    items = []
    for r in reversed(rows[-12:]):
        tag = {"gate": "<span class='lv crit'>작업 전 차단</span>", "accident": "<span class='lv crit'>사고</span>",
               "info": "<span class='lv info'>참고</span>"}.get(r["kind"]) or lv(r.get("computed_level"), r.get("alerted"))
        adj = f" · <span class='mono'>{e(r['adj_id'])}</span>" if r.get("adj_id") else ""
        items.append(f"<div><span class='t'>{r['ts'][11:16]}</span><span>{e(r.get('violation_type') or '')} · "
                     f"{e(r.get('mode') or '-')}{adj}</span>{tag}</div>")
    return wrap(f"<div class='list'>{''.join(items)}</div>")


AX_CLS = ["g", "a", "i"]


def axes(s: dict, zone: str) -> str:
    st = s["zones"][zone]
    if not st.get("table"):
        return wrap(f"<p class='empty'>{e(zone)} 에는 판정표가 걸려 있지 않다 — 모드 규칙(영상)과 무음 기록만 돈다.</p>")
    act = st["alerting"]
    rows = []
    for i, (name, a) in enumerate(st["axes"].items()):
        cls = AX_CLS[i] if i < len(AX_CLS) else "p"
        dot = "on" if a.tone == "danger" else ("half" if a.tone == "warn" else "")
        why = " · ".join(dict.fromkeys(a.why)) or ("; ".join(a.why_not[:1]) if a.why_not else "")
        off = "" if (act and a.tone in ("danger", "warn")) else " off"
        state = {"●": "● 있음", "○": "○ 없음"}.get(a.state, a.state)
        rows.append(f"<div class='ax {cls}{off}'><span class='nm'>{e(name)}</span><div class='st'><b>{e(state)}</b>"
                    f"<span>{e(why[:140])}</span></div><span class='dot {dot}'></span></div>")
    ppl = f"{st['people']}명 (영상)" if s["video"] else ("허가 작업 중 — 사람이 있다고 본다" if st.get("present") else "영상 없음 · 허가 작업 없음")
    rows.append(f"<div class='ax p'><span class='nm'>사람</span><div class='st'><b>{e(ppl)}</b>"
                "<span>단계는 올리지 않고 대응만 바꾼다</span></div><span class='mono' style='font-weight:700'>"
                f"{st['people']}</span></div>")
    return wrap(f"<div class='axes'>{''.join(rows)}</div>")


def judge_table(s: dict, zone: str) -> str:
    st = s["zones"][zone]
    t = st.get("tdef")
    if not t:
        return ""
    hit = st.get("row")
    comp = st.get("computed")
    out = []
    for r in t.get("rows", []) + [t.get("default", {})]:
        n = r.get("row")
        is_hit = n is not None and n == hit and comp != "정상"
        cls = ""
        if is_hit:
            cls = " hit " + LEVEL_KIND.get(r.get("level", "정상"), "") + ("" if st["alerting"] else " shadow")
        out.append(f"<div class='row{cls}'><span class='n'>{n or ''}</span><span>{e(r.get('label') or r.get('violation') or '그 외')}</span>"
                   f"{lv(r.get('level', '정상'))}</div>")
    note = "" if st["alerting"] else "<p class='note'>모드가 꺼져 있어 판정은 무음 기록으로만 남는다 (점선이 계산된 줄).</p>"
    return wrap(f"<div class='judge'>{''.join(out)}</div>{note}")


def ptw_card(zone: str) -> str:
    from . import isolation
    ps = [p for p in isolation.ptws() if p["zone"] == zone]
    if not ps:
        return wrap("<p class='empty'>이 구역에 걸린 작업허가서가 없다.</p>")
    out = []
    for p in sorted(ps, key=lambda x: x.get("start", ""), reverse=True)[:3]:
        v = isolation.view(p)
        out.append(f"<div class='hcard {v['kind'] if v['kind'] in ('crit', 'warn') else ''}'><div class='hd'><b class='mono'>{e(p['ptw_id'])}</b>"
                   f"<span class='lv {v['kind']}'>{e(v['tag'])}</span></div><p>{e(p['work'])}</p>"
                   f"<p class='note'>{e(p.get('type', ''))} · {e(p.get('start', '')[5:16].replace('T', ' '))} ~ {e(p.get('end', '')[11:16])} · 발생 축 해제: <b>{e(v['clear'])}</b></p></div>")
    return wrap("".join(out))


def next_cards(s: dict, counts: dict) -> str:
    return wrap(
        "<div class='cards2'>"
        f"<div class='hcard'><div class='hd'><b>시정지시서 후보 {counts['alerts']}건</b><span class='lv note'>경보 이상</span></div>"
        "<p>이 세션의 경보 이상 기록. 넘기면 문서 자동화의 관제 인계 화면에서 골라 초안을 만든다. 발행은 사람이 한다.</p></div>"
        f"<div class='hcard {'crit' if counts['adhoc'] else ''}'><div class='hd'><b>수시 위험성평가 제안 {counts['adhoc']}건</b>"
        "<span class='lv crit'>위험도 12 · 중대성 4</span></div><p>넘어온 기록까지 합쳐 계산한다. 위험성평가 지침 제15조제2항.</p></div>"
        f"<div class='hcard'><div class='hd'><b>작업 전 게이트 {counts['gates']}건</b><span class='lv warn'>R1</span></div>"
        "<p>격리 목록 누락 등으로 작업 시작을 막은 기록 — 작업허가서 점검으로 같은 판정을 문서로 남긴다.</p></div></div>")


def notes(s: dict) -> str:
    if not s["notes"]:
        return wrap("<p class='empty'>엔진 메모 없음</p>")
    return wrap("<div class='notes'>" + "".join(f"<div><span class='t'>{t:%H:%M:%S}</span>{e(m)}</div>" for t, m in s["notes"][:14]) + "</div>")


# ====================================================================== 격리 목록 대조
def iso_kpis(v: dict) -> str:
    lines = v["check"]["lines"]
    inl = sum(1 for x in lines if x["in_list"])
    miss = len(v["miss"])
    return wrap(
        "<div class='kpis'>"
        f"<div class='kpi'><span>계통도 연결</span><b>{len(lines)}</b><small>사업장 패키지 site.json · {e(v['ptw']['zone'])}</small></div>"
        f"<div class='kpi'><span>목록에 적힌 배관</span><b>{'—' if v['no_list'] else inl}</b><small>{'첨부 안 됨' if v['no_list'] else '격리 목록 CSV'}</small></div>"
        f"<div class='kpi {'crit' if miss else ''}'><span>목록에 없는 연결</span><b>{'—' if v['no_list'] else miss}</b><small>작업 전 게이트 (R1)</small></div>"
        f"<div class='kpi {'ok' if v['clear'] == '인정' else 'warn'}'><span>발생 축 해제</span><b class='txt'>{e(v['clear'])}</b>"
        f"<small>퍼지 {v['purge_min'] if v['purge_min'] is not None else '—'}분 / 기준 {v['purge_need']}분</small></div></div>")


def iso_diagram(v: dict) -> str:
    lines = v["check"]["lines"]
    n = max(len(lines), 1)
    H = 70 + n * 60
    s = [f"<svg viewBox='0 0 600 {H}' role='img' aria-label='{e(v['check']['equipment'])} 배관 계통도'>",
         f"<rect x='10' y='30' width='80' height='{n * 60 - 10}' rx='6' fill='var(--panel2)' stroke='var(--line)'/>",
         f"<text x='50' y='{30 + (n * 60 - 10) / 2:.0f}' font-size='12' fill='var(--ink2)' text-anchor='middle'>공급 · 밸브</text>",
         f"<rect x='470' y='22' width='120' height='{n * 60 + 6}' rx='8' fill='var(--panel2)' stroke='var(--ink2)'/>",
         f"<text x='530' y='{30 + n * 30:.0f}' font-size='13.5' font-weight='700' fill='currentColor' text-anchor='middle'>{e(v['check']['equipment'])}</text>"]
    for i, ln in enumerate(lines):
        y = 60 + i * 60
        bad = not ln["in_list"] and not v["no_list"]
        col = "var(--ink2)" if v["no_list"] else ("var(--crit-strong)" if bad else "var(--p)")
        haz = " · 가연물" if ln.get("hazard_source") else ""
        s.append(f"<text x='104' y='{y - 12}' font-size='11.5' font-weight='600' fill='{'var(--crit)' if bad else 'var(--ink2)'}'>"
                 f"{e(ln['line_id'])} {e(ln['name'])}{haz}{' — 목록에 없음' if bad else ''}</text>")
        dash = " stroke-dasharray='7 5'" if bad or ln["blind"] == "none" else ""
        s.append(f"<line x1='90' y1='{y}' x2='190' y2='{y}' stroke='{col}' stroke-width='5'/>"
                 f"<line x1='190' y1='{y}' x2='470' y2='{y}' stroke='{col}' stroke-width='5'{dash}/>"
                 f"<path d='M178,{y - 10} L190,{y} L178,{y + 10} z' fill='var(--ink2)'/><path d='M202,{y - 10} L190,{y} L202,{y + 10} z' fill='var(--ink2)'/>")
        b = ln["blind"]
        if b == "done":
            s.append(f"<rect x='276' y='{y - 16}' width='9' height='32' fill='var(--ok)'/>")
            tx, tc = "맹판 설치" + (" (단계 입력)" if ln.get("blind_by_step") else ""), "var(--ok)"
        elif b == "pending":
            s.append(f"<rect x='274' y='{y - 16}' width='13' height='32' fill='none' stroke='var(--warn)' stroke-width='2'/>")
            tx, tc = "맹판 설치 대기", "var(--warn)"
        elif b == "valve":
            s.append(f"<rect x='272' y='{y - 18}' width='18' height='36' rx='3' fill='none' stroke='var(--crit-strong)' stroke-width='1.8' stroke-dasharray='4 3'/>")
            tx, tc = "밸브만 잠김", "var(--crit)"
        else:
            tx, tc = "미정 (목록 없음)", "var(--ink2)"
        s.append(f"<text x='298' y='{y + 22}' font-size='11' font-weight='700' fill='{tc}'>{tx}</text>")
    s.append(f"<text x='10' y='{H - 8}' font-size='10.5' fill='var(--ink2)'>◇ 차단밸브 · 초록 막대 맹판 · 점선은 맹판이 없는 구간</text></svg>")
    return wrap(f"<div class='svgwrap'>{''.join(s)}</div>")


def iso_list(v: dict) -> str:
    if v["no_list"]:
        return wrap(f"<p class='empty'>격리 목록이 첨부되지 않았다.</p><div class='bar {v['kind']}'><span>{e(v['bar'])}</span></div>")

    def ox(val):
        val = (val or "—").strip().upper()
        k = "y" if val in ("O", "○") else ("x" if val == "X" else "d")
        return f"<td class='c {k}'>{e(val)}</td>"
    rows = []
    for ln in v["check"]["lines"]:
        if not ln["in_list"]:
            rows.append(f"<tr class='hit'><td class='mono'>{e(ln['line_id'])}</td><td colspan='5'><b>{e(ln['name'])} — 계통도에는 있는데 목록에 없다</b></td></tr>")
            continue
        r = ln["row"] or {}
        rows.append(f"<tr><td class='mono'>{e(ln['line_id'])}</td><td>{e(r.get('배관') or ln['name'])}</td><td>{e(r.get('격리방법', '-'))}</td>"
                    f"<td class='c {'y' if ln['blind'] == 'done' else 'x'}'>{'O' if ln['blind'] == 'done' else '대기'}</td>"
                    f"{ox(r.get('벤트'))}{ox(r.get('가스측정'))}</tr>")
    rows += [f"<tr class='gate'><td colspan='2'>{e(x)}</td><td colspan='4'><b>목록에만 있다 — 계통도 확인 필요</b></td></tr>" for x in v["check"]["extra"]]
    return wrap("<table class='t'><thead><tr><th>line_id</th><th>배관</th><th>격리방법</th><th>맹판</th><th>벤트</th><th>측정</th></tr></thead>"
                f"<tbody>{''.join(rows)}</tbody></table><div class='bar {v['kind']}'><span>{e(v['bar'])}</span></div>")


def iso_blinds(v: dict) -> str:
    out = []
    for ln in v["check"]["lines"]:
        if v["no_list"]:
            out.append(f"<div class='stage-item'><div><b>{e(ln['line_id'])} {e(ln['name'])}</b><br><span class='s'>목록이 없어 단계 입력을 받을 수 없다</span></div><span class='lv mute'>대기</span></div>")
        elif ln["blind"] == "done":
            out.append(f"<div class='stage-item'><div><b>{e(ln['line_id'])} 맹판 설치 완료</b><br><span class='s'>{'단계 입력됨' if ln.get('blind_by_step') else '격리 목록에 완료로 적힘'}</span></div><span class='lv ok'>완료</span></div>")
        elif ln["blind"] == "pending":
            out.append(f"<div class='stage-item'><div><b>{e(ln['line_id'])} 맹판 설치</b><br><span class='s'>입력 대기 — 아래에서 완료 입력</span></div><span class='lv note'>대기</span></div>")
        else:
            out.append(f"<div class='stage-item bad'><div><b>{e(ln['line_id'])} — 밸브만 잠김</b><br><span class='s'>밸브 단독 격리는 발생 해제가 아니다 (R2)</span></div><span class='lv crit'>발생 확인 유지</span></div>")
    return wrap("".join(out))


def iso_meas(v: dict) -> str:
    if not v["meas"]:
        return wrap("<p class='empty'>측정 지점 없음</p>")

    def verdict(m):
        if m["ok"]:
            return "<span class='lv ok'>기준 이하</span>"
        return "<span class='lv crit'>기준 초과</span>" if m["measured"] else "<span class='lv warn'>측정 없음</span>"
    rows = "".join(f"<tr><td>{e(m['point'])}</td><td class='mono'>{e(m['time'])}</td><td class='mono'>{e(m['value'])}</td>"
                   f"<td>{verdict(m)}</td></tr>" for m in v["meas"])
    ok = sum(1 for m in v["meas"] if m["ok"])
    return wrap(f"<table class='t'><thead><tr><th>측정 지점</th><th>시각</th><th>값</th><th>판정 (LEL ≤ {v['lel_max']}%)</th></tr></thead><tbody>{rows}</tbody></table>"
                f"<div class='bar {'ok' if v['clear'] == '인정' else 'warn'}'><span>퍼지 {v['purge_min'] if v['purge_min'] is not None else '—'}분 / 기준 {v['purge_need']}분 · 지점 {ok}/{len(v['meas'])}</span>"
                f"<span>해제 {e(v['clear'])}</span></div>")


def reg_preview(zone: str, chk: dict) -> str:
    if not chk["has_pid"]:
        return wrap(f"<div class='bar crit'><span>{e(zone)} 에는 배관 계통도가 없어 대조할 수 없다 — 사업장 패키지 site.json 의 piping 에 먼저 넣는다</span></div>")
    miss = [x for x in chk["lines"] if not x["in_list"]]
    rows = "".join(
        f"<tr class='{'' if x['in_list'] else 'hit'}'><td class='mono'>{e(x['line_id'])}</td><td>{e(x['name'])}</td><td>"
        + ("<span class='lv ok'>목록에 있음 · 맹판 O</span>" if x["blind"] == "done" else
           "<span class='lv note'>목록에 있음 · 맹판 대기</span>" if x["in_list"] else
           ("<span class='lv mute'>목록 없음</span>" if x["blind"] == "none" else "<span class='lv crit'>목록에 없음</span>"))
        + "</td></tr>" for x in chk["lines"])
    rows += "".join(f"<tr class='gate'><td colspan='2'>{e(x)}</td><td><span class='lv warn'>계통도에 없음 — 확인 필요</span></td></tr>" for x in chk["extra"])
    k = "crit" if miss and chk["lines"] and chk["lines"][0]["blind"] != "none" else "ok"
    return wrap(f"<table class='t'><thead><tr><th>line_id</th><th>배관</th><th>대조</th></tr></thead><tbody>{rows}</tbody></table>"
                f"<div class='bar {k}'><span>계통도 {len(chk['lines'])}건 · 목록에 없는 연결 {len(miss)}건"
                f"{' · 계통도에 없는 줄 ' + str(len(chk['extra'])) + '건' if chk['extra'] else ''}</span></div>")


# ====================================================================== 이벤트 로그
def event_detail(ev: dict | None) -> str:
    if not ev:
        return wrap("<p class='empty'>표에서 이벤트를 고르면 여기에 뜬다.</p>")
    f = frame_file(ev)
    frame = (f"<div class='cam'><img alt='{e(ev['event_id'])} 대표 프레임' src='data:image/jpeg;base64,{base64.b64encode(f.read_bytes()).decode()}'></div>"
             if f else "<div class='cam'><div class='empty'>프레임 없음 — 영상이 없던 기록(신호 판정)이거나 무음 기록이다</div></div>")
    kind = {"gate": "작업 전 게이트", "accident": "사고", "info": "참고", "stage": "3축 판정", "check": "모드 규칙(영상)"}.get(ev.get("kind"), ev.get("kind"))
    rows = [("일시", ev["ts"].replace("T", " ")), ("구역 · 모드", f"{ev['zone']} {zone_name(ev['zone'])} · {ev.get('mode') or '-'}"),
            ("위반 유형", ev.get("violation_type") or "-"), ("종류", kind),
            ("판정 근거", (f"{ev['row']}번 줄 · " if ev.get("row") else "") + (ev.get("reason") or "-")),
            ("대응", ev.get("response") or "-"), ("규칙셋", ev.get("ruleset") or "-"),
            ("강화 중", ev.get("adj_id") or "아님 — 기본 규칙"), ("클립", ev.get("clip_path") or "-"), ("출처", ev.get("_src", ""))]
    if ev.get("false_positive"):
        rows.append(("오탐 표시", ev.get("fp_by") or "예"))
    tbl = "".join(f"<tr><td class='muted' style='white-space:nowrap'>{e(k)}</td><td>{e(str(v))}</td></tr>" for k, v in rows)
    note = ("모드가 꺼진 구간의 검출이라 경보 없이 남았다. 통계와 사고 경과에 쓰인다." if not ev.get("alerted") and ev.get("kind") in ("stage", "check")
            else "오탐 표시는 표시자와 시각이 남고, 오탐을 근거로 한 완화는 사람이 승인해야 한다(피드백 2단).")
    return wrap(f"<div class='ph'><h3 class='mono'>{e(ev['event_id'])}</h3>{lv(ev.get('computed_level') or ev.get('level'), ev.get('alerted', True))}</div>"
                f"{frame}<table class='t' style='margin-top:8px'><tbody>{tbl}</tbody></table><p class='note'>{e(note)}</p>")


# ====================================================================== 재생 비교
def versus(res: dict) -> str:
    from .replay import score
    ok, n = score(res)
    cards = []
    for name, v in res["variants"].items():
        sm = v["summary"]
        c_ok = sum(1 for c, _ in v["checks"] if c)
        cls = "hot" if sm["hot"] else ("bad" if sm["accident"] else "")
        cards.append(f"<div class='vcard {cls}'><span class='k'>{e(name)} · 개정안 {e(' '.join(v['changes']) or '없음')}</span>"
                     f"<span class='big'>{e(sm['head'])}</span><p>{e(sm['text'])}</p><p class='note'>기대 결과 {c_ok}/{len(v['checks'])}</p></div>")
    cards.append(f"<div class='vcard {'' if ok == n else 'bad'}'><span class='k'>기대 결과 대조</span><span class='big'>{ok} / {n}</span>"
                 f"<p>{'모두 일치한다.' if ok == n else '불일치가 있다 — 아래 기대 결과에서 이유를 본다. 시나리오나 규칙 중 하나를 고친다.'}</p></div>")
    return wrap(f"<div class='versus'>{''.join(cards)}</div>")


def merged_table(res: dict, cursor: str | None) -> str:
    from .replay import merged_rows
    names = list(res["variants"])
    head = "<th>시각</th><th>신호</th><th>입력</th>" + "".join(f"<th>{e(n)}</th>" for n in names)
    body = []
    for r in merged_rows(res):
        cells = []
        hot = False
        for n in names:
            k, t = r["cells"].get(n, ("", ""))
            if k in ("gate", "acc", "최고 경보"):
                hot = True
            tag = ("<span class='lv crit'>작업 전 차단</span> " if k == "gate" else "<span class='lv crit'>사고</span> " if k == "acc"
                   else lv(k) + " " if k in ("주의", "경보", "최고 경보") else "")
            cells.append(f"<td>{tag}<span class='muted'>{e(t if k not in ('gate', 'acc') else '')}</span></td>")
        future = cursor and r["t"] > cursor
        cls = "hit" if hot else ""
        style = " style='opacity:.35'" if future else ""
        body.append(f"<tr class='{cls}'{style}><td class='mono'>{r['t']}</td><td>{e(r['signals'] or '(시간 경과)')}</td><td>{e(r['source'])}</td>{''.join(cells)}</tr>")
    return wrap(f"<div style='overflow-x:auto'><table class='t' style='min-width:720px'><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>")


def expect_list(res: dict) -> str:
    out = []
    for name, v in res["variants"].items():
        for ok, msg in v["checks"]:
            out.append(f"<div><b class='{'y' if ok else 'x'}'>{'✓' if ok else '✗'}</b><span><b>{e(name)}</b> · {e(msg)}</span></div>")
    return wrap(f"<div class='expect'>{''.join(out) or '<p class=empty>이 시나리오에는 기대 결과가 없다.</p>'}</div>")


def cursor_cards(res: dict, t: str) -> str:
    from .replay import state_at
    cards = []
    for name in res["variants"]:
        st = state_at(res, name, t)
        ax = " · ".join(f"{k} {v}" for k, v in st.get("axes", {}).items())
        cards.append(f"<div class='vcard'><span class='k'>{e(name)} · {t}</span><span class='big'>{lv(st['level'])}"
                     f"{' · ' + str(st['row']) + '줄' if st.get('row') and st['level'] != '정상' else ''}</span>"
                     f"<p>{e(ax)}</p><p class='note'>모드 {e(' · '.join(st.get('modes', [])) or '평상시')}</p></div>")
    return wrap(f"<div class='versus'>{''.join(cards)}</div>")


# ====================================================================== 피드백
def fb_kpis(now, act, pend, n14, rs, fb_mode) -> str:
    zs = " · ".join(dict.fromkeys(a["zone"] for a in act)) or "—"
    return wrap(
        "<div class='kpis'>"
        f"<div class='kpi'><span>활성 자동 조정</span><b>{len(act)}</b><small>{e(zs)}</small></div>"
        f"<div class='kpi {'warn' if pend else ''}'><span>승인 대기 (짧은 루프)</span><b>{len(pend)}</b><small>{'승인형' if fb_mode == 'approval' else '자동 — 승인 없이 적용'}</small></div>"
        f"<div class='kpi'><span>최근 14일 조정</span><b>{n14}</b><small>승격 기준 같은 구역 3회</small></div>"
        f"<div class='kpi'><span>현재 규칙셋</span><b class='txt'>v{rs['version']}</b><small>{e(' · '.join(rs['ids']) or '개정 없음 — 기본 규칙')}</small></div></div>")


def adj_cards(items: list[dict], now) -> str:
    from .feedback import action_text, reason_text
    if not items:
        return wrap("<p class='empty'>걸려 있는 자동 조정이 없다.</p>")
    out = []
    for a in items:
        exp = a["expires_at"][5:16].replace("T", " ")
        st = "<span class='lv info'>applied</span>" if a["state"] == "applied" else "<span class='lv warn'>pending</span>"
        out.append(f"<div class='hcard {'crit' if (a.get('reason') or {}).get('type') == 'severe' else ''}'><div class='hd'><b class='mono'>{e(a['adj_id'])}</b>{st}</div>"
                   f"<p>{z(a['zone'])} {e(action_text(a))}</p><p class='note'>근거 {e(reason_text(a))} · 만료 {e(exp)} · {e(a.get('feedback_mode', ''))}</p></div>")
    return wrap(f"<div style='display:flex;flex-direction:column;gap:8px'>{''.join(out)}</div>")


def proposals_html(items: list[dict]) -> str:
    if not items:
        return wrap("<p class='empty'>긴 루프로 올릴 제안이 없다.</p>")
    rows = "".join(f"<tr class='{'hit' if p['kind'] in ('승격', '위험도') else ''}'><td style='white-space:nowrap'>{e(p['kind'])}</td>"
                   f"<td>{z(p['zone'])}</td><td>{e(p['text'])}</td>"
                   f"<td class='muted' style='font-size:11.5px'>{'<br>'.join(e(x) for x in (p.get('ref') or '').split(', ') if x)}</td></tr>"
                   for p in items)
    return wrap(f"<table class='t'><thead><tr><th>구분</th><th>구역</th><th>내용</th><th>근거</th></tr></thead><tbody>{rows}</tbody></table>")


def rc_view(rc: dict) -> str:
    names = ["제안", "관리자 서명", "근로자 확인", "규칙셋 반영"]
    steps = "→".join(f"<span class='{'done' if i < rc['step'] or rc['step'] == 3 else 'now' if i == rc['step'] else ''}'>{n}</span>"
                     for i, n in enumerate(names))
    diff = "".join(f"<div class='{k}'>{e(t)}</div>" for k, t in rc["diff"])
    return wrap(f"<p><b>{e(rc['id'])}</b> — {e(rc['text'])}</p><div class='diff'>{diff}</div>"
                f"<div class='steps' style='margin-top:8px'>{steps}</div><p class='note'>{e(rc['status'])}</p>")


def zone_bars(counts: dict[str, int]) -> str:
    from .common import zones
    mx = max(counts.values(), default=0) or 1
    rows = "".join(f"<div class='hb'><span>{e(zz)} {e(zone_name(zz))}</span><div class='tr'><i class='{'c' if counts.get(zz, 0) >= 3 else 'w' if counts.get(zz, 0) else ''}' "
                   f"style='width:{counts.get(zz, 0) / mx * 100:.0f}%'></i></div><b>{counts.get(zz, 0)}</b></div>" for zz in zones() if counts.get(zz))
    return wrap(f"<div class='hbars'>{rows or '<p class=empty>최근 14일 조정 없음</p>'}</div>"
                "<p class='note'>같은 구역 14일 안에 3회면 개정 제안으로 승격한다. 강화 기간의 기록은 기준선에서 뺀다.</p>")


def criteria_table(cfg: dict) -> str:
    sp = cfg["spike"]
    rows = [("중대", f"중대성 {cfg['severe']['severity']}등급 1건", "1단 즉시"),
            ("급증", f"{sp['window_h']}시간 ≥ {sp['baseline_days']}일 평균 × {sp['ratio']:g}, 최소 {sp['min_count']}건", "1단"),
            ("신규", "기준선 0건인 조합의 첫 발생", "1단"),
            ("승격", f"같은 구역 {cfg['promote']['within_days']}일 안에 조정 {cfg['promote']['count']}회", "2단"),
            ("절대 기준", f"주간 {cfg['absolute']['weekly_count']}건 초과 또는 위험도 {cfg['absolute']['risk_score']} 이상", "2단"),
            ("오탐 과다", f"오탐 표시 {cfg['false_positive']['ratio'] * 100:.0f}% 초과 (최소 {cfg['false_positive']['min_count']}건)", "2단 (완화 제안)"),
            ("급감", f"기준선의 {cfg['drop']['ratio'] * 100:.0f}% 이하", "카메라 점검 알림 · 완화하지 않음")]
    body = "".join(f"<tr><td>{e(a)}</td><td>{e(b)}</td><td>{e(c)}</td></tr>" for a, b, c in rows)
    return wrap(f"<table class='t'><tbody>{body}</tbody></table><p class='note'>자동 조정은 {cfg['expire_h']}시간 뒤 만료된다. "
                "값은 사업장 패키지 rules.json 의 feedback 블록.</p>")


def adj_log_table(adjs: dict, toggles: list[dict]) -> str:
    from .feedback import action_text, reason_text
    rows = []
    for a in sorted(adjs.values(), key=lambda x: x["ts"], reverse=True):
        k = {"applied": "info", "pending": "warn", "expired": "mute", "reverted": "warn", "rejected": "mute"}.get(a["state"], "mute")
        last = a["history"][-1]
        who = last.get("actor") or "system"
        if last.get("note") and a["state"] in ("reverted", "rejected"):
            who += f" · 사유: {last['note']}"
        rows.append(f"<tr><td class='mono'>{e(a['adj_id'])}</td><td class='mono'>{e(a['ts'][5:16].replace('T', ' '))}</td>"
                    f"<td><span class='lv {k}'>{e(a['state'])}</span></td><td>{z(a['zone'])}</td><td>{e(reason_text(a))}</td>"
                    f"<td>{e(action_text(a))}</td><td class='mono'>{e(a['expires_at'][5:16].replace('T', ' '))}</td><td>{e(who)}</td></tr>")
    for t in reversed(toggles):
        rows.append(f"<tr class='gate'><td class='mono'>{e(t['adj_id'])}</td><td class='mono'>{e(t['ts'][5:16].replace('T', ' '))}</td>"
                    f"<td><span class='lv info'>toggle</span></td><td>—</td><td>방식 → {e(t['feedback_mode'])}</td><td>—</td><td>—</td>"
                    f"<td>{e(t.get('actor', ''))} · 사유: {e(t.get('note', ''))}</td></tr>")
    return wrap("<div style='overflow-x:auto'><table class='t' style='min-width:860px'><thead><tr><th>adj_id</th><th>시각</th><th>상태</th><th>구역</th>"
                f"<th>사유</th><th>변경</th><th>만료</th><th>주체</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan=8 class=muted>기록 없음</td></tr>'}</tbody></table></div>"
                "<p class='note'>adjustments.jsonl · 이벤트 로그와 따로 둔다 · 추가만 되고 지워지지 않는다</p>")


# ====================================================================== 통계
def heat_table(h: dict) -> str:
    if not h["rows"]:
        return wrap("<p class='empty'>최근 14일 기록이 없다.</p>")
    head = "".join(f"<th>{x:02d}</th>" for x in h["hours"])
    body = []
    for zz, vals in h["rows"]:
        cells = "".join(f"<td class='h{0 if v == 0 else 1 if v <= 1 else 2 if v <= 2 else 3 if v <= 4 else 4}'>{v}</td>" for v in vals)
        body.append(f"<tr><th class='rh'>{e(zz)} {e(zone_name(zz))}</th>{cells}</tr>")
    return wrap(f"<div style='overflow-x:auto'><table class='heat'><thead><tr><th class='rh'>구역</th>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
                "<div class='legend' style='margin-top:6px'>적음 <i class='h0'></i><i class='h1'></i><i class='h2'></i><i class='h3'></i><i class='h4'></i> 많음 · 칸의 숫자가 건수</div>")


def rate_bars(rates: list[dict]) -> str:
    if not rates:
        return wrap("<p class='empty'>모드가 켜져 있던 시간 기록이 아직 없다. 실시간 관제 세션을 돌리면 모드가 켜지고 꺼진 시각이 쌓여 여기서 비교된다 "
                    "(샘플 기록에는 모드 시간이 없다).</p>")
    mx = max(r["rate"] for r in rates) or 1
    rows = "".join(f"<div class='hb'><span>{e(r['label'])}</span><div class='tr'><i class='{'c' if r['kind'] == 'on' else ''}' style='width:{r['rate'] / mx * 100:.0f}%'></i></div>"
                   f"<b>{r['rate']:.1f}</b></div><p class='note' style='margin:0 0 4px 160px'>{r['n']}건 / {r['hours']:.1f}시간</p>" for r in rates)
    return wrap(f"<div class='hbars'>{rows}</div><p class='note'>사고는 평소 안 하던 일을 할 때 몰린다. 규칙을 그 구간에만 강하게 켜는 근거다.</p>")


def helmet_panel(hm: dict) -> str:
    if hm["has_model"] and hm["rate"]:
        rows = "".join(f"<div class='hb'><span>{e(d)}</span><div class='tr'><i class='{'g' if r >= .9 else 'w'}' style='width:{r * 100:.0f}%'></i></div><b>{r * 100:.0f}%</b></div>"
                       for d, r in sorted(hm["rate"].items()))
        return wrap(f"<div class='hbars'>{rows}</div><p class='note'>사람이 보인 시간 중 안전모가 보인 시간. 기본 규칙(전 구역 안전모)이 도는지 보는 용도다.</p>")
    rows = "".join(f"<div class='hb'><span>{e(d)}</span><div class='tr'><i class='w' style='width:{min(100, v['n'] * 20)}%'></i></div><b>{v['n']}건</b></div>"
                   for d, v in sorted(hm["by_dep"].items()))
    why = ("안전모 탐지 모델이 아직 붙지 않았다 — 착용률 대신 안전모 미착용 기록 건수를 부서 · 협력사로 묶어 보인다. "
           "모델을 detect.json 의 extra 에 no_helmet 으로 붙이면 영상에서 센 시간으로 착용률이 나온다.")
    return wrap(f"<div class='hbars'>{rows or '<p class=empty>최근 14일 안전모 미착용 기록 없음</p>'}</div><p class='note'>{e(why)}</p>")


def when(dt: datetime | None) -> str:
    return f"{dt:%m-%d %H:%M}" if dt else "-"
