"""
기록 — 이벤트 로그와 전후 클립.

  events.jsonl  한 줄 = 한 이벤트. 추가 전용(고치거나 지우지 않는다).
                필드는 docgen 의 sample_data/events.json 과 같게 맞췄다
                (event_id · ts · zone · mode · violation_type · level · alerted · adj_id · false_positive · clip_path · frame_path)
                + 관제 쪽에서만 쓰는 필드(kind · row · reason · response · axes · ruleset …).
  kind          stage = 3축 판정 / check = 모드 규칙(영상) / gate = 작업 전 게이트 / accident = 사고 / info = 참고
  무음 기록      모드가 꺼져 있을 때의 위반은 alerted=false, level=null 로 남긴다(경보만 안 울린다).
  중복 억제      같은 (구역 · 위반 · 트랙)은 cooldown_s 안에 다시 쓰지 않는다.
"""
from __future__ import annotations

import json
from collections import deque
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from .video_io import SafeWriter, imwrite, resize_max_width


class ClipRecorder:
    """최근 pre_s 초를 JPEG 로 들고 있다가, 요청이 오면 post_s 초를 더 받아 mp4 로 쓴다."""

    def __init__(self, out_dir: Path, fps: float, pre_s: float, post_s: float, max_width: int):
        self.out_dir = Path(out_dir)
        self.fps = fps
        self.pre_s, self.post_s, self.max_width = pre_s, post_s, max_width
        self.buf: deque[tuple[float, bytes]] = deque()
        self.pending: list[dict] = []
        self.written: list[Path] = []

    def request(self, ev_id: str, t: float) -> tuple[str, str]:
        clip = self.out_dir / "clips" / f"{ev_id}.mp4"
        frame = self.out_dir / "frames" / f"{ev_id}.jpg"
        pre = [b for tt, b in self.buf if tt >= t - self.pre_s]
        self.pending.append({"id": ev_id, "end": t + self.post_s, "frames": pre, "clip": clip,
                             "frame": frame, "need_frame": True})
        return str(clip.relative_to(self.out_dir)), str(frame.relative_to(self.out_dir))

    def push(self, t: float, img: np.ndarray):
        small = resize_max_width(img, self.max_width)
        ok, enc = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            return
        b = enc.tobytes()
        self.buf.append((t, b))
        while self.buf and self.buf[0][0] < t - self.pre_s:
            self.buf.popleft()
        done = []
        for p in self.pending:
            if p["need_frame"]:
                imwrite(p["frame"], img)      # 위반 순간 프레임 1장 (docgen 시정지시서 · 이미지 분석이 쓴다)
                p["need_frame"] = False
            p["frames"].append(b)
            if t >= p["end"]:
                done.append(p)
        for p in done:
            self._write(p)
            self.pending.remove(p)

    def flush(self):
        for p in list(self.pending):
            self._write(p)
        self.pending.clear()

    def _write(self, p: dict):
        if not p["frames"]:
            return
        first = cv2.imdecode(np.frombuffer(p["frames"][0], np.uint8), cv2.IMREAD_COLOR)
        h, w = first.shape[:2]
        wr = SafeWriter(p["clip"], self.fps, (w, h))
        for b in p["frames"]:
            wr.write(cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR))
        self.written.append(wr.close())


class EventLog:
    def __init__(self, out_dir: Path | None, rs: dict, cooldown_s: float = 30, quiet: bool = False,
                 clips: ClipRecorder | None = None, save_shadow_clips: bool = False):
        self.out_dir = Path(out_dir) if out_dir else None
        self.path = self.out_dir / "events.jsonl" if self.out_dir else None
        if self.out_dir:
            self.out_dir.mkdir(parents=True, exist_ok=True)
        self.rs = rs
        self.cooldown = cooldown_s
        self.quiet = quiet
        self.clips = clips
        self.save_shadow_clips = save_shadow_clips
        self.rows: list[dict] = []
        self._last: dict[tuple, datetime] = {}
        self._seq = 0

    def emit(self, *, kind: str, ts: datetime, zone: str | None, mode: str | None, violation_type: str | None,
             level: str | None, alerted: bool, reason: str = "", row: int | None = None,
             response: str = "", track_id: int | None = None, axes: dict | None = None,
             dedup: tuple | None = None, video_t: float | None = None, extra: dict | None = None) -> dict | None:
        if dedup is not None:
            last = self._last.get(dedup)
            if last is not None and (ts - last).total_seconds() < self.cooldown:
                return None
            self._last[dedup] = ts
        self._seq += 1
        ev = {
            "event_id": f"EV-{ts:%m%d%H%M}-{self._seq:03d}",
            "ts": ts.isoformat(timespec="seconds"),
            "zone": zone,
            "mode": mode,
            "violation_type": violation_type,
            "level": level if alerted else None,
            "alerted": alerted,
            "adj_id": None,
            "false_positive": False,
            "clip_path": None,
            "frame_path": None,
            # --- 관제 쪽 필드
            "kind": kind,
            "row": row,
            "computed_level": level,
            "reason": reason,
            "response": response if alerted else "",
            "track_id": track_id,
            "axes": axes,
            "ruleset": self.rs.get("_label"),
            "applied_changes": self.rs.get("_applied", []),
            "video_t": round(video_t, 2) if video_t is not None else None,
        }
        if extra:
            ev.update(extra)
        if self.clips is not None and video_t is not None and kind in ("stage", "check") and (alerted or self.save_shadow_clips):
            ev["clip_path"], ev["frame_path"] = self.clips.request(ev["event_id"], video_t)
        self.rows.append(ev)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        if not self.quiet:
            print(format_event(ev))
        return ev

    def export_docgen(self, path: Path, as_of: datetime) -> Path:
        """docgen(법정 문서)이 읽는 모양 {"as_of", "events": [...]} 으로 내보낸다. 게이트 · 사고 · 참고는 뺀다."""
        evs = [{k: e[k] for k in ("event_id", "ts", "zone", "mode", "violation_type", "level", "alerted",
                                   "adj_id", "false_positive", "clip_path", "frame_path")}
               for e in self.rows if e["kind"] in ("stage", "check")]
        path = Path(path)
        path.write_text(json.dumps({"as_of": as_of.isoformat(timespec="seconds"), "events": evs},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def format_event(ev: dict) -> str:
    t = ev["ts"][11:19]
    lv = ev["computed_level"] or ev["kind"]
    tag = "" if ev["alerted"] else " [무음 기록]"
    row = f" ({ev['row']}번 줄)" if ev.get("row") else ""
    head = f"[{t}] {lv}{tag} · {ev['zone'] or '-'} · {ev['violation_type'] or ''}{row}"
    body = f" — {ev['reason']}" if ev.get("reason") else ""
    resp = f"\n           → 대응: {ev['response']}" if ev.get("response") else ""
    return head + body + resp
