"""
탐지 요약 — "이 영상에서 탐지가 도는가"를 숫자로 본다 (선검증용).
"""
from __future__ import annotations

import json
from pathlib import Path

from .zones import HAZARD_TYPES


class DetectStats:
    def __init__(self, fps: float, on_frames: int, stride: int = 1, flame_backend: str = "color"):
        self.fps, self.on_frames, self.stride = fps, on_frames, stride
        self.flame_backend = flame_backend
        self.frames = 0
        self.person_frames = 0
        self.person_sum = 0
        self.person_max = 0
        self.track_ids: set[int] = set()
        self.flame_raw_frames = 0
        self.flame_in_hazard_frames = 0
        self.flame_streak = 0
        self.flame_max_streak = 0
        self.flame_confirm_t: float | None = None
        self.poly_frames: dict[str, int] = {}

    def update(self, t: float, persons, flames, flame_confirmed: bool):
        self.frames += 1
        n = len(persons)
        if n:
            self.person_frames += 1
        self.person_sum += n
        self.person_max = max(self.person_max, n)
        for p in persons:
            if p.track_id is not None:
                self.track_ids.add(p.track_id)
        names = {q.name for p in persons for q in p.polys}
        for nm in names:
            self.poly_frames[nm] = self.poly_frames.get(nm, 0) + 1
        if flames:
            self.flame_raw_frames += 1
        in_h = any(q.type in HAZARD_TYPES for f in flames for q in f.polys)
        if in_h:
            self.flame_in_hazard_frames += 1
            self.flame_streak += 1
            self.flame_max_streak = max(self.flame_max_streak, self.flame_streak)
        else:
            self.flame_streak = 0
        if flame_confirmed and self.flame_confirm_t is None:
            self.flame_confirm_t = t

    def as_dict(self) -> dict:
        f = max(1, self.frames)
        return {
            "processed_frames": self.frames,
            "person_frames": self.person_frames,
            "person_frame_ratio": round(self.person_frames / f, 3),
            "person_avg": round(self.person_sum / f, 2),
            "person_max": self.person_max,
            "track_ids": len(self.track_ids),
            "person_in_polygon_frames": self.poly_frames,
            "flame_raw_frames": self.flame_raw_frames,
            "flame_in_hazard_frames": self.flame_in_hazard_frames,
            "flame_max_streak": self.flame_max_streak,
            "on_frames_required": self.on_frames,
            "flame_confirmed_at_s": round(self.flame_confirm_t, 2) if self.flame_confirm_t is not None else None,
        }

    def report(self) -> str:
        d = self.as_dict()
        lines = ["", "■ 탐지 요약 (처리한 프레임 기준)"]
        ok_p = d["person_frame_ratio"] >= 0.8
        lines.append(f"  사람   {d['person_frames']}/{self.frames} 프레임 ({d['person_frame_ratio']:.0%}) · 평균 {d['person_avg']}명 · "
                     f"최대 {d['person_max']}명 · 추적 ID {d['track_ids']}개  {'[OK]' if ok_p else '[확인 필요]'}")
        if self.poly_frames:
            lines.append("         폴리곤별 사람 있던 프레임: " + ", ".join(f"{k} {v}" for k, v in self.poly_frames.items()))
        if d["track_ids"] > max(3, d["person_max"] * 3):
            lines.append("         └ 추적 ID 가 사람 수보다 훨씬 많다 → 트래킹이 자주 끊긴다 (체류 시간 누적에 영향)")
        if self.flame_backend == "off":
            lines.append("  불꽃   보지 않음 (flame backend = off) — 점화원은 버튼 0 / 타임라인 sparks 로 넣는다")
            return "\n".join(lines)
        conf = d["flame_confirmed_at_s"]
        ok_f = conf is not None
        lines.append(f"  불꽃   원시 {d['flame_raw_frames']} 프레임 · hazard 폴리곤 안 {d['flame_in_hazard_frames']} 프레임 · "
                     f"최대 연속 {d['flame_max_streak']} (기준 {self.on_frames})  "
                     + (f"[OK] {conf:.1f}초에 확정" if ok_f else "[확인 필요] 확정 안 됨"))
        if not ok_f:
            if d["flame_raw_frames"] == 0:
                lines.append("         └ 불꽃 후보가 한 번도 없다 → detect.json flame.color 의 v_min · s_min 을 낮춘다")
            elif d["flame_in_hazard_frames"] == 0:
                lines.append("         └ 불꽃은 잡히는데 hazard 폴리곤 밖이다 → calibrate.py 로 hazard 폴리곤을 다시 그린다")
            else:
                lines.append("         └ 잡히다 끊긴다 → persistence.on_frames 를 줄이거나 flame.color.min_blobs 를 낮춘다")
        return "\n".join(lines)

    def save(self, path: Path):
        Path(path).write_text(json.dumps(self.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
