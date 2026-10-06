"""
영상 위 최소 표시 — 폴리곤 · 사람(접지점) · 검출 박스 · 윗줄 상태.
증거 클립과 --show 창에 쓴다. 관제 화면(대시보드)은 이 폴더의 일이 아니다.
OpenCV 는 한글을 못 그려서 윗줄은 영문 약어로 쓴다.
"""
from __future__ import annotations

import cv2
import numpy as np

from .judge import RANK
from .modes import active_poly_types
from .zones import HAZARD_TYPES

LEVEL_EN = {"정상": "NORMAL", "주의": "CAUTION", "경보": "ALARM", "최고 경보": "CRITICAL"}
LEVEL_BGR = {"정상": (60, 150, 60), "주의": (30, 170, 200), "경보": (20, 125, 230), "최고 경보": (40, 40, 210)}


def draw(frame: np.ndarray, eng, zones, camera_zone: str | None) -> np.ndarray:
    vis = frame.copy()
    present = {p.type for p in zones.polys}
    on = {z: active_poly_types(eng.rules, ms, present) for z, ms in eng.modes.items()}
    zones.draw(vis, {p.name: p.type in on.get(p.zone, {"hazard"}) for p in zones.polys})
    for p in eng.persons:
        x1, y1, x2, y2 = (int(v) for v in p.xyxy)
        types = {q.type for q in p.polys}
        col = (40, 40, 230) if types & set(HAZARD_TYPES) else (230, 140, 30) if types & {"work", "restricted"} else (80, 200, 80)
        cv2.rectangle(vis, (x1, y1), (x2, y2), col, 2)
        cv2.circle(vis, ((x1 + x2) // 2, y2), 5, col, -1)
        if p.track_id is not None:
            cv2.putText(vis, f"#{p.track_id}", (x1, max(14, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2, cv2.LINE_AA)
    for name, dets in eng.objects.items():
        for d in dets:
            x1, y1, x2, y2 = (int(v) for v in d.xyxy)
            cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 90, 255), 2)
            cv2.putText(vis, name, (x1, max(14, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 90, 255), 2, cv2.LINE_AA)
    zone = camera_zone or (zones.zones()[0] if zones.zones() else "")
    level, ls, table = eng.zone_level(zone)
    txt = f"{eng.now:%H:%M:%S}  {zone}  {LEVEL_EN[level]}" + (f" row {ls.row}" if ls and level != "정상" else "")
    txt += f"  modes {len([m for m, s in eng.modes.get(zone, []) if s is not None])}"
    if any(g.blocked for g in eng.gates.get(zone, [])):
        txt += "  GATE-BLOCKED"
    cv2.rectangle(vis, (0, 0), (vis.shape[1], 28), LEVEL_BGR[level], -1)
    cv2.putText(vis, txt, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    if RANK[level] >= 2:
        cv2.rectangle(vis, (0, 0), (vis.shape[1] - 1, vis.shape[0] - 1), LEVEL_BGR[level], 6)
    return vis
