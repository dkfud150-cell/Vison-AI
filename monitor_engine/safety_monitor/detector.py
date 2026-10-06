"""
탐지 — 사람과 불꽃 두 가지만 본다 (확정 시연이 쓰는 1순위 탐지 둘).

  PersonDetector : 공개 YOLO(COCO person) + ByteTrack 추적. 추가 학습 없음.
  FlameDetector  : backend = color (학습 없이 색 · 밝기 · 움직임) / yolo (불꽃 클래스 가중치) / off
                   color 는 사람 박스 · 작업복 같은 색 면을 빼고 본다 (노랑 · 주황 작업복 오탐 방지)
  Persistence    : N프레임 연속이어야 불꽃으로 확정 (오탐 억제)

가스 · 압력 · 배기 · 맹판 설치는 영상으로 보지 않는다 — CSV 와 버튼으로 들어온다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np


@dataclass
class Det:
    xyxy: tuple[float, float, float, float]
    conf: float
    cls: str
    track_id: int | None = None
    polys: list = field(default_factory=list)   # zones.Zones.locate 결과


# ---------------------------------------------------------------------- 사람
class PersonDetector:
    def __init__(self, cfg: dict, model_dir: Path | None = None):
        from ultralytics import YOLO   # 여기서 불러야 replay.py 가 ultralytics 없이도 돈다

        self.cfg = cfg
        self.model = None
        errors = []
        for w in (cfg.get("weights"), cfg.get("fallback_weights")):
            if not w:
                continue
            p = Path(w)
            if model_dir and not p.is_absolute() and (model_dir / p).exists():
                p = model_dir / p
            try:
                self.model = YOLO(str(p))
                self.weights = str(p)
                break
            except Exception as e:  # noqa: BLE001 — 가중치 이름이 버전마다 달라서 다음 후보로 넘어간다
                errors.append(f"{w}: {e}")
        if self.model is None:
            raise RuntimeError("사람 탐지 모델을 불러오지 못했습니다\n" + "\n".join(errors))
        self.use_track = True

    def __call__(self, frame: np.ndarray) -> list[Det]:
        kw = dict(classes=[0], conf=self.cfg.get("conf", 0.35), imgsz=self.cfg.get("imgsz", 640),
                  verbose=False, device=self.cfg.get("device"))
        res = None
        if self.use_track:
            try:
                res = self.model.track(frame, persist=True, tracker=self.cfg.get("tracker", "bytetrack.yaml"), **kw)[0]
            except Exception as e:  # noqa: BLE001 — lap 미설치 등. 프레임 단위 판정으로 폴백
                print(f"[안내] 추적을 끄고 프레임 단위로 판정합니다: {e}")
                self.use_track = False
        if res is None:
            res = self.model.predict(frame, **kw)[0]
        out = []
        b = res.boxes
        if b is None or len(b) == 0:
            return out
        ids = b.id.int().tolist() if getattr(b, "id", None) is not None else [None] * len(b)
        for xyxy, conf, tid in zip(b.xyxy.tolist(), b.conf.tolist(), ids):
            out.append(Det(tuple(xyxy), float(conf), "person", tid))
        return out


# ---------------------------------------------------------------------- 불꽃
class FlameDetector:
    def __init__(self, cfg: dict, roi_mask_fn=None, root: Path | None = None):
        """
        roi_mask_fn(scale) → uint8 마스크(작업 해상도). color 방식에서 roi='hazard' 일 때 hazard 폴리곤 근처만 본다.
        root: 가중치 상대 경로의 기준 폴더 (monitor/).
        """
        self.cfg = cfg
        self.backend = cfg.get("backend", "color")
        self.roi_mask_fn = roi_mask_fn
        self.prev = None
        self._roi = None
        self.model = None
        self.last_mask = None      # color 방식의 마지막 불티 후보 마스크 (조정할 때 들여다보는 용)
        self.last_scale = 1.0
        self.last: list[Det] = []  # 마지막 결과 — 똑같은 프레임이 다시 오면 그대로 돌려준다
        if self.backend == "yolo":
            from ultralytics import YOLO
            y = cfg["yolo"]
            p = Path(y["weights"])
            if root and not p.is_absolute():
                p = root / p
            if not p.exists():
                raise FileNotFoundError(f"불꽃 가중치가 없습니다: {p}  (detect.json 의 flame.backend 를 'color' 로 두면 학습 없이 돈다)")
            self.model = YOLO(str(p))
            names = {i: n.lower() for i, n in self.model.names.items()}
            want = {c.lower() for c in y.get("classes", [])}
            self.class_ids = [i for i, n in names.items() if n in want] or None
            print(f"[불꽃] {p.name} 클래스: {[names[i] for i in (self.class_ids or names)]}")

    def __call__(self, frame: np.ndarray, persons: list[Det] | None = None) -> list[Det]:
        """persons: 같은 프레임의 사람 탐지 결과. color 방식은 사람 박스 안을 불티 후보에서 뺀다(작업복 · 안전모)."""
        if self.backend == "off":
            return []
        if self.backend == "yolo":
            y = self.cfg["yolo"]
            r = self.model.predict(frame, conf=y.get("conf", 0.3), imgsz=y.get("imgsz", 640),
                                   classes=self.class_ids, verbose=False)[0]
            if r.boxes is None:
                return []
            return [Det(tuple(b), float(c), "flame") for b, c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist())]
        return self._color(frame, persons or [])

    def _color(self, frame: np.ndarray, persons: list[Det]) -> list[Det]:
        """
        그라인더 불티 = 작고 밝고 따뜻한 색(또는 흰빛)이면서 프레임마다 자리가 바뀌는 점들.
        정지된 조명 · 반사는 '움직임' 조건에서 빠진다. 첫 프레임은 비교 대상이 없어서 항상 0.

        노랑 · 주황 작업복과 안전모도 밝고 따뜻한 색이라, 사람이 움직이면 옷 가장자리가 불티 후보로 잡힌다.
        그래서 후보를 고른 뒤 아래를 뺀다 (값은 detect.json flame.color).
          skip_person      사람 박스 안 (사람 탐지가 있을 때)
          solid_*          채도 높은 따뜻한 색 '면'(작업복 · 안전모 · 주황 설비) — 불티는 가늘고 작아 면이 되지 않는다.
                           단 하얗게 타는 심지(hot_*)가 섞인 면은 불길로 보고 남긴다
          white_near_warm  흰빛은 따뜻한 색 바로 옆일 때만 — 흰 안전모 · 장갑 · 반사띠 · 조명을 빼고 불티 심지만 남긴다
          cluster_blobs    한 무리 안에 점이 이만큼 — 여기저기 흩어진 한두 점을 모아 불티로 치지 않는다
          max_motion_ratio 화면 대부분이 한꺼번에 바뀌면(장면 전환 · 섬광 · 카메라 흔들림) 그 프레임은 건너뛴다
          skip_repeat      앞 프레임과 똑같은 프레임(생성 영상에 흔하다)은 앞 결과를 그대로 쓴다
        """
        c = self.cfg["color"]
        H, W = frame.shape[:2]
        ww = int(c.get("work_width", 640))
        s = min(1.0, ww / W)
        small = cv2.resize(frame, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA) if s < 1 else frame
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        if self.prev is None or self.prev.shape != gray.shape:
            self.prev = gray
            self.last = []
            return []
        diff = cv2.absdiff(gray, self.prev)
        if c.get("skip_repeat", True) and float(diff.mean()) < 0.5:
            return list(self.last)
        self.prev = gray
        moving = (diff >= c["motion_min"]).astype(np.uint8) * 255
        mr = c.get("max_motion_ratio")
        if mr and np.count_nonzero(moving) > mr * moving.size:
            self.last_mask, self.last_scale, self.last = np.zeros_like(moving), s, []
            return []

        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        h, sat, val = cv2.split(hsv)
        warm_hue = (h <= c["hue_max"]) | (h >= c["hue_wrap_min"])
        warm = warm_hue & (sat >= c["s_min"]) & (val >= c["v_min"])
        white = (val >= c["white_v_min"]) & (sat <= c["white_s_max"])
        wn = int(c.get("white_near_warm", 0))
        if wn > 0:
            white &= cv2.dilate(warm.astype(np.uint8), _disk(2 * wn + 1)) > 0
        color = (warm | white).astype(np.uint8) * 255

        moving = cv2.dilate(moving, np.ones((3, 3), np.uint8))
        cand = cv2.bitwise_and(color, moving)

        if c.get("roi", "frame") == "hazard" and self.roi_mask_fn is not None:
            if self._roi is None or self._roi.shape != cand.shape:
                self._roi = self.roi_mask_fn(s)
            if self._roi is not None:
                cand = cv2.bitwise_and(cand, self._roi)

        if persons and c.get("skip_person", True):
            pad = float(c.get("person_pad", 0.08))
            ph, pw = cand.shape
            for p in persons:
                x0, y0, x1, y1 = p.xyxy
                dx, dy = (x1 - x0) * pad, (y1 - y0) * pad
                cand[max(0, int((y0 - dy) * s)):min(ph, int((y1 + dy) * s) + 1),
                     max(0, int((x0 - dx) * s)):min(pw, int((x1 + dx) * s) + 1)] = 0

        k = int(c.get("solid_px", 0))
        if k >= 3 and np.any(cand):
            cand = cv2.bitwise_and(cand, cv2.bitwise_not(self._solid(warm_hue, sat, val, c, k)))

        self.last_mask, self.last_scale = cand, s
        self.last = self._blobs(cand, c, s)
        return self.last

    def _solid(self, warm_hue, sat, val, c, k) -> np.ndarray:
        """채도 높은 따뜻한 색 면(작업복 · 안전모 · 주황 설비)을 칠한 마스크. 하얗게 타는 심지가 섞인 면(불길)은 뺀다."""
        surf = (warm_hue & (sat >= c.get("solid_s_min", 110)) & (val >= c.get("solid_v_min", 100))).astype(np.uint8) * 255
        surf = cv2.morphologyEx(surf, cv2.MORPH_OPEN, _disk(k))
        n, lab, st, _ = cv2.connectedComponentsWithStats(surf, connectivity=8)
        if n <= 1:
            return surf
        hot = (val >= c.get("hot_v_min", 250)) & (sat <= c.get("hot_s_max", 130))
        cnt = np.bincount(lab[hot].ravel(), minlength=n)
        fire = cnt / np.maximum(st[:, cv2.CC_STAT_AREA], 1) >= c.get("hot_ratio", 0.1)
        fire[0] = True
        sup = np.where(fire[lab], 0, 255).astype(np.uint8)
        pad = int(c.get("solid_pad", 5))
        return cv2.dilate(sup, _disk(2 * pad + 1)) if pad > 0 else sup

    @staticmethod
    def _blobs(cand: np.ndarray, c: dict, s: float) -> list[Det]:
        n, lab, stats, _ = cv2.connectedComponentsWithStats(cand, connectivity=8)
        big = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= c["min_blob_px"]]
        keep = np.isin(lab, big).astype(np.uint8) * 255 if big else np.zeros_like(cand)
        total = int(np.count_nonzero(keep))
        if len(big) < c.get("min_blobs", 3) or total < c["min_total_ratio"] * cand.size:
            return []
        # 흩어진 불티를 한 덩어리로 묶는다
        k = int(c.get("cluster_px", 25))
        grp = cv2.dilate(keep, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
        n2, lab2, st2, _ = cv2.connectedComponentsWithStats(grp, connectivity=8)
        per = np.zeros(n2, int)                      # 무리마다 점이 몇 개인가
        for i in big:
            x, y = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP]
            ys, xs = np.nonzero(lab[y:y + stats[i, cv2.CC_STAT_HEIGHT], x:x + stats[i, cv2.CC_STAT_WIDTH]] == i)
            per[lab2[y + ys[0], x + xs[0]]] += 1
        need = int(c.get("cluster_blobs", 1))
        out = []
        for i in range(1, n2):
            x, y, w, hh, _a = st2[i]
            px = int(np.count_nonzero(keep[y:y + hh, x:x + w]))
            if px < c["min_blob_px"] * c.get("min_blobs", 3) or per[i] < need:
                continue
            conf = min(1.0, px / (0.002 * cand.size) + 0.3)
            out.append(Det((x / s, y / s, (x + w) / s, (y + hh) / s), conf, "flame"))
        return out


def _disk(k: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))


def run_objects(dets: dict, frame: np.ndarray, persons: list[Det]) -> dict[str, list[Det]]:
    """물체 탐지를 돌린다. 불꽃 탐지에는 사람 박스를 넘겨 작업복 · 안전모를 불티로 잡지 않게 한다."""
    return {n: (d(frame, persons=persons) if isinstance(d, FlameDetector) else d(frame)) for n, d in dets.items()}


class Persistence:
    """N프레임 연속 검출이면 켜고, M프레임 연속 미검출이면 끈다."""

    def __init__(self, on_frames: int = 5, off_frames: int = 15):
        self.on_n, self.off_n = on_frames, off_frames
        self.hit = 0
        self.miss = 0
        self.on = False
        self.max_streak = 0

    def update(self, detected: bool) -> bool:
        if detected:
            self.hit += 1
            self.miss = 0
            self.max_streak = max(self.max_streak, self.hit)
            if self.hit >= self.on_n:
                self.on = True
        else:
            self.miss += 1
            self.hit = 0
            if self.miss >= self.off_n:
                self.on = False
        return self.on


# ---------------------------------------------------------------------- 그 밖의 물체 (패키지가 정한다)
class YoloObjectDetector:
    """
    detect.json 의 extra 에 적은 가중치로 물체를 찾는다 (사다리 · 보호구 · 적치물 …).
    결과는 이름(name)으로 엔진에 들어가고, 규칙에서 {"detect": 이름} 으로 쓴다.
    """

    def __init__(self, spec: dict, root: Path | None = None):
        from ultralytics import YOLO
        p = Path(spec["weights"])
        if root and not p.is_absolute():
            p = root / p
        if not p.exists():
            raise FileNotFoundError(f"[{spec['name']}] 가중치가 없습니다: {p}")
        self.spec = spec
        self.model = YOLO(str(p))
        names = {i: n.lower() for i, n in self.model.names.items()}
        want = {c.lower() for c in spec.get("classes", [])}
        self.class_ids = [i for i, n in names.items() if n in want] or None

    def __call__(self, frame: np.ndarray) -> list[Det]:
        r = self.model.predict(frame, conf=self.spec.get("conf", 0.4), imgsz=self.spec.get("imgsz", 640),
                               classes=self.class_ids, verbose=False)[0]
        if r.boxes is None:
            return []
        return [Det(tuple(b), float(c), self.spec["name"]) for b, c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist())]
