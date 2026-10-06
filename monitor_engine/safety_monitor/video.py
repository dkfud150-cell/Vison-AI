"""
영상 실행 — 프레임마다 탐지 → 엔진 → 기록.

  사람      : 항상 (detect.json person)
  불꽃      : flame.backend 가 off 가 아니면
  그 밖 물체 : detect.json extra (패키지 detect.json 으로 추가)
시나리오가 주어지면 at 시각 이전의 신호를 먼저 넣고, 영상이 흐르는 동안 그 뒤 신호를 시각에 맞춰 넣는다.
타임라인에서 source 가 '영상' 인 줄은 넣지 않는다 — 영상 탐지가 대신 만든다.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path

import cv2

from .detector import FlameDetector, PersonDetector, YoloObjectDetector, run_objects
from .draw import draw
from .engine import Engine
from .events import ClipRecorder, EventLog
from .package import MODEL_DIR, ROOT, Package, Scenario
from .signals import Signal, parse_clock
from .stats import DetectStats
from .video_io import SafeWriter, open_video, resize_max_width
from .zones import Zones


def run_video(pkg: Package, rules: dict, video: Path, camera: dict, out_dir: Path, *,
              scenario: Scenario | None = None, at: str | None = None, show: bool = False, save: bool = False,
              stride: int | None = None, flame: str | None = None, realtime: bool = True,
              max_seconds: float | None = None, day=None) -> dict:
    dcfg = pkg.detect
    if flame:
        dcfg["flame"]["backend"] = flame
    stride = max(1, stride or dcfg.get("run", {}).get("stride", 1))

    cap = open_video(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    ok, first = cap.read()
    if not ok:
        raise RuntimeError("영상에서 프레임을 읽지 못했습니다")
    first = resize_max_width(first, dcfg.get("run", {}).get("work_width", 960))
    H, W = first.shape[:2]
    zones = Zones(camera, W, H)

    day = day or (scenario.day if scenario else datetime.now().date())
    start = parse_clock(at, day) if at else datetime.combine(day, datetime.now().time()).replace(microsecond=0)
    before, pending = [], []
    if scenario and at:
        tl = [s for s in scenario.timeline() if s.source != "영상"]
        before = [s for s in tl if s.ts <= start]
        pending = [s for s in tl if s.ts > start]

    ev = dcfg["event"]
    clips = ClipRecorder(out_dir, fps, ev["clip_pre_s"], ev["clip_post_s"], ev["clip_max_width"])
    log = EventLog(out_dir, rules, cooldown_s=ev["cooldown_s"], clips=clips, save_shadow_clips=ev.get("save_shadow_clips", False))
    eng = Engine(pkg, rules, before[0].ts if before else start, log=log,
                 scenario_dir=scenario.dir if scenario else None, zones=zones, detect_cfg=dcfg)
    for s in before:
        for n in eng.apply(s):
            print(f"   {s.ts:%H:%M} {s.short()}: {n}")
    eng.tick(start)

    person_det = PersonDetector(dcfg["person"], MODEL_DIR)
    detectors = {}
    if dcfg.get("flame", {}).get("backend", "color") != "off":
        detectors["flame"] = FlameDetector(dcfg["flame"], root=ROOT,
                                           roi_mask_fn=lambda s: zones.mask(tuple(dcfg["flame"].get("polygons", ["hazard"])),
                                                                            dilate_px=int(30 * s), scale=s))
    for x in dcfg.get("extra", []):
        detectors[x["name"]] = YoloObjectDetector(x, root=ROOT)
    stats = DetectStats(fps, dcfg["persistence"]["on_frames"], stride, dcfg.get("flame", {}).get("backend", "color"))
    print(f"탐지: 사람 {Path(person_det.weights).name}" + "".join(f" · {n}" for n in detectors))

    writer = None
    i, paused, t_last = 0, False, time.time()
    frame = first
    try:
        while True:
            if not paused:
                if i > 0:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    frame = resize_max_width(frame, W)
                t = i / fps
                if max_seconds and t > max_seconds:
                    break
                now = start + timedelta(seconds=t)
                while pending and pending[0].ts <= now:
                    s = pending.pop(0)
                    for n in eng.apply(s):
                        print(f"   {s.ts:%H:%M} {s.short()}: {n}")
                if i % stride == 0:
                    persons = person_det(frame)
                    objects = run_objects(detectors, frame, persons)
                    eng.update_video(now, t, persons, objects)
                    stats.update(t, persons, objects.get("flame", []),
                                 any(r["on"] for (n, z), r in eng.store.detections.items() if n == "flame"))
                else:
                    eng.tick(now)
                vis = draw(frame, eng, zones, camera.get("zone"))
                clips.push(t, vis)
                if save:
                    writer = writer or SafeWriter(out_dir / "annotated.mp4", fps, (vis.shape[1], vis.shape[0]))
                    writer.write(vis)
                i += 1
            if not show:
                continue
            cv2.imshow("safety-monitor", vis)
            wait = 1 if (not realtime or paused) else max(1, int(1000 / fps - (time.time() - t_last) * 1000))
            t_last = time.time()
            k = cv2.waitKey(30 if paused else wait) & 0xFF
            if k in (ord("q"), 27):
                break
            if k == ord(" "):
                paused = not paused
            elif k != 255 and chr(k) in pkg.buttons:
                b = pkg.buttons[chr(k)]
                sig = Signal(ts=eng.now, signal=b["signal"], zone=b.get("zone"), target=b.get("target"),
                             value=b.get("value"), source="버튼", note=b.get("label", ""))
                print(f"[키 {chr(k)}] {eng.now:%H:%M:%S} {b.get('label', b['signal'])}")
                for n in eng.apply(sig):
                    print(f"   {n}")
    finally:
        cap.release()
        clips.flush()
        if writer:
            writer.close()
        if show:
            cv2.destroyAllWindows()
    stats.save(out_dir / "detect_summary.json")
    log.export_docgen(out_dir / "events_for_docgen.json", eng.now)
    return {"engine": eng, "log": log, "stats": stats, "clips": clips, "out_dir": out_dir}
