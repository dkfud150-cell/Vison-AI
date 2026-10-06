"""
구역 판정 — 이 사람(불꽃)이 어느 폴리곤 안에 있나.

  사람  : 바운딩 박스 하단 중앙 = 접지점(발 위치)으로 판정한다.
  불꽃  : 박스 중심으로 판정한다(불티는 바닥에 있지 않다).
  space : image = 화면 좌표(0~1 비율)로 그린 폴리곤
          floor = 바닥 좌표(m)로 그린 폴리곤. camera.json 의 floor_calib(바닥 네 점)으로 호모그래피를 구해
                  접지점을 탑뷰로 바꾼 뒤 판정한다 (통합 문서 4장 '구역 판정 방식').
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

TYPE_COLOR = {  # BGR
    "hazard": (40, 40, 220),
    "hazard_repair": (70, 70, 255),
    "work": (0, 200, 230),
    "restricted": (230, 140, 30),
}

# 위험구역 — hazard 는 설비 때문에 상시, hazard_repair 는 그 작업 때문에 한시적으로 위험한 구역.
HAZARD_TYPES = ("hazard", "hazard_repair")
# 판정에 쓰이는 기본 종류. 이 밖의 종류(통로 · 설비 위치 …)는 사업장 패키지 zone_types.json 에서 관리자가 더한다 —
# 화면 표시와 사람 위치 기록에 쓰이고, 판정에 쓰려면 rules.json 의 polygons 에 그 key 를 적는다.
BUILTIN_TYPES = ("hazard", "hazard_repair", "work", "restricted")


def hex_bgr(c: str) -> tuple[int, int, int] | None:
    """'#RRGGBB' → (B, G, R). 형식이 틀리면 None."""
    c = (c or "").lstrip("#")
    if len(c) != 6:
        return None
    try:
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except ValueError:
        return None
    return (b, g, r)

FILL_ALPHA = 0.07  # 폴리곤 칠하기 진하기. 넓은 구역을 쓰면 낮춘다(테두리만 남고 안쪽이 비친다).


@dataclass
class Poly:
    name: str
    type: str
    zone: str
    label: str
    px: np.ndarray                 # 화면 픽셀 좌표 (N,2) int32 — 그리기용
    floor: np.ndarray | None       # 바닥 좌표(m) — space=floor 일 때
    space: str = "image"


class Zones:
    def __init__(self, camera: dict, width: int, height: int):
        self.camera = camera
        self.w, self.h = width, height
        self.camera_zone = camera.get("zone")
        self.colors = dict(TYPE_COLOR)          # 관리자가 더한 종류의 색 (package.zone_types → camera['type_colors'])
        for k, v in (camera.get("type_colors") or {}).items():
            if k not in TYPE_COLOR and hex_bgr(v):
                self.colors[k] = hex_bgr(v)
        self.H = None       # 화면 → 바닥
        self.Hinv = None
        fc = camera.get("floor_calib")
        if fc and fc.get("image_pts") and fc.get("floor_pts"):
            src = np.float32([[x * width, y * height] for x, y in fc["image_pts"]])
            dst = np.float32(fc["floor_pts"])
            self.H = cv2.getPerspectiveTransform(src, dst)
            self.Hinv = np.linalg.inv(self.H)
        self.polys: list[Poly] = []
        for p in camera.get("polygons", []):
            space = p.get("space", "image")
            if space == "floor":
                if self.H is None:
                    raise ValueError(f"폴리곤 {p['name']} 은 floor 좌표인데 camera.json 에 floor_calib 가 없습니다")
                fl = np.float32(p["points"])
                px = cv2.perspectiveTransform(fl.reshape(-1, 1, 2), self.Hinv).reshape(-1, 2)
            else:
                fl = None
                px = np.float32([[x * width, y * height] for x, y in p["points"]])
            self.polys.append(Poly(p["name"], p.get("type", "work"), p.get("zone", self.camera_zone),
                                   p.get("label", p["name"]), px.astype(np.int32), fl, space))

    # -------------------------------------------------------------- 좌표
    @staticmethod
    def ground_point(xyxy) -> tuple[float, float]:
        x1, y1, x2, y2 = xyxy
        return ((x1 + x2) / 2, y2)

    @staticmethod
    def center(xyxy) -> tuple[float, float]:
        x1, y1, x2, y2 = xyxy
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    def to_floor(self, pt) -> tuple[float, float] | None:
        if self.H is None:
            return None
        v = cv2.perspectiveTransform(np.float32([[pt]]), self.H)[0, 0]
        return float(v[0]), float(v[1])

    # -------------------------------------------------------------- 판정
    def locate(self, pt) -> list[Poly]:
        out = []
        fpt = self.to_floor(pt) if self.H is not None else None
        for p in self.polys:
            if p.space == "floor" and fpt is not None:
                inside = cv2.pointPolygonTest(p.floor.reshape(-1, 1, 2), fpt, False) >= 0
            else:
                inside = cv2.pointPolygonTest(p.px.reshape(-1, 1, 2).astype(np.float32), (float(pt[0]), float(pt[1])), False) >= 0
            if inside:
                out.append(p)
        return out

    def zones(self) -> list[str]:
        return list(dict.fromkeys(p.zone for p in self.polys))

    def hazard_zones(self) -> list[str]:
        return list(dict.fromkeys(p.zone for p in self.polys if p.type in HAZARD_TYPES))

    def mask(self, types=HAZARD_TYPES, dilate_px: int = 0, scale: float = 1.0) -> np.ndarray | None:
        """불꽃 탐지 ROI 용 마스크."""
        sel = [p for p in self.polys if p.type in types]
        if not sel:
            return None
        m = np.zeros((int(self.h * scale), int(self.w * scale)), np.uint8)
        for p in sel:
            cv2.fillPoly(m, [(p.px * scale).astype(np.int32)], 255)
        if dilate_px > 0:
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_px * 2 + 1, dilate_px * 2 + 1))
            m = cv2.dilate(m, k)
        return m

    # -------------------------------------------------------------- 그리기
    def draw(self, img: np.ndarray, active_types: dict[str, bool] | None = None):
        """폴리곤을 반투명으로 그린다. active_types[이름]=True 면 진하게(그 구역 규칙이 켜짐)."""
        over = img.copy()
        for p in self.polys:
            col = self.colors.get(p.type, (200, 200, 200))
            on = (active_types or {}).get(p.name, p.type in HAZARD_TYPES)
            if on:
                cv2.fillPoly(over, [p.px], col)
        cv2.addWeighted(over, FILL_ALPHA, img, 1 - FILL_ALPHA, 0, img)
        for p in self.polys:
            col = self.colors.get(p.type, (200, 200, 200))
            on = (active_types or {}).get(p.name, p.type in HAZARD_TYPES)
            cv2.polylines(img, [p.px], True, col, 2 if on else 1, cv2.LINE_AA)
            x, y = p.px[:, 0].min(), p.px[:, 1].min()
            cv2.putText(img, p.name, (int(x) + 6, int(y) + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2, cv2.LINE_AA)
