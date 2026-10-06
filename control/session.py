"""
실시간 관제 세션 — 엔진 하나를 시연 시계에 맞춰 돌린다.

  시연 시계   1× · 10× · 60× 로 흐른다. 영상 장면이 도는 동안은 영상 시간으로 흐른다.
  신호        ① 오늘 신호 스케줄(시나리오 timeline.csv — PLC · PTW · 센서 대신) ② 화면 버튼(buttons.json)
              ③ 작업허가서 등록 · 격리 단계 입력(격리 목록 대조 화면) — 전부 같은 Signal 로 엔진에 들어간다
  영상        장면(scenario.json scenes)을 고르면 그 시각에 영상 탐지를 붙인다 (사람 · 불꽃 → 폴리곤 → 판정)
              장면에 그린 구역(polygons — 화면의 '영상 올리기 · 구역 설정')이 있으면 카메라 기본 구역 대신 쓴다
  기록        control/records/live/<세션>/events.jsonl (추가 전용) · clips/ · frames/ · modes.jsonl
  피드백      새 기록이 생길 때마다 이탈 조건을 보고 자동 조정을 건다(feedback.py). 조정 중인 구역의 기록에는 adj_id 가 붙는다
  자동 인계   기록할 때마다 문서 자동화로 넘긴다(집계 · 증빙 누적용) — docgen handoff.receive(auto=True)

프로그램 하나에 세션 하나다(관제실 화면). 화면은 1초마다 snapshot 을 읽어 그린다.
"""
from __future__ import annotations

import copy
import threading
import time
import traceback
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

from safety_monitor.engine import Engine
from safety_monitor.events import ClipRecorder, EventLog
from safety_monitor.judge import RANK, response
from safety_monitor.modes import alerting, label_mode
from safety_monitor.signals import Signal, parse_clock

from .common import LIVE_DIR, append_jsonl, dashboard, demo_day, live_sessions, load_config, package, read_jsonl


RULESETS = {"docgen": "문서 자동화 확정분", "none": "기본 규칙 (v1)", "all": "개정안 전부"}


def resolve_ruleset(ruleset: str, pkg, sc=None) -> tuple[list[str], str]:
    """
    세션 규칙셋.  docgen = 문서 자동화에서 위험성평가 확정으로 쌓인 개정안 (실제 운영과 같다)
                 none = 기본 규칙 · all = 개정안 전부 · 그 밖 = 시나리오 variants 이름 또는 'R1,R3'
    """
    from safety_monitor.package import docgen_confirmed_changes, resolve_changes
    if ruleset == "docgen":
        ids = [i for i in docgen_confirmed_changes() if i in pkg.change_ids()]
        return ids, f"문서 자동화 확정분 ({' '.join(ids) or '없음 — 기본 규칙'})"
    if ruleset in ("none", "", None):
        return [], "기본 규칙 (v1)"
    if ruleset == "all":
        return pkg.change_ids(), "개정안 전부"
    return resolve_changes(ruleset, pkg, sc)


# ====================================================================== 기록 — 조정 중이면 표시한다
class LiveEventLog(EventLog):
    """
    엔진의 EventLog 에 두 가지를 더한다.
      - 번호가 세션마다 처음부터 시작하지 않게 이어서 센다 (EV-10120915-017)
      - 자동 조정이 걸린 구역이면 adj_id 를 붙이고, '구역 규칙 임시 활성화'면 무음 기록을 경보로 올린다
    """

    def __init__(self, out_dir, rules, *, seq_start: int = 0, adjust=None, **kw):
        super().__init__(out_dir, rules, quiet=True, **kw)
        self._seq = seq_start
        self.adjust = adjust

    def emit(self, **kw):
        zone, ts = kw.get("zone"), kw.get("ts")
        extra = dict(kw.get("extra") or {})
        if self.adjust and zone and kw.get("kind") in ("stage", "check"):
            adj_id, enable = self.adjust(zone, ts)
            if adj_id:
                extra["adj_id"] = adj_id
                if enable and not kw.get("alerted") and kw.get("level") and kw.get("level") != "정상":
                    kw["alerted"] = True
                    kw["reason"] = (kw.get("reason") or "") + f" · 강화 중 {adj_id} — 꺼져 있던 구역 규칙을 임시로 켰다"
        kw["extra"] = extra
        ev = super().emit(**kw)
        if ev is not None and extra.get("adj_id"):
            ev["adj_id"] = extra["adj_id"]
        return ev


UNDO_MAX = 20     # 되돌리기로 거슬러 갈 수 있는 현장 입력 수


class _Mute:
    """되돌리기에서 상태를 다시 맞추는 동안 쓰는 빈 기록 — 이미 events.jsonl 에 있는 단계 변화를 두 번 쓰지 않는다."""
    rows: list = []
    clips = None

    def emit(self, **kw):
        return None


# ====================================================================== 영상
class VideoRunner(threading.Thread):
    """장면 영상 하나를 프레임마다 탐지해 엔진에 넣는다. 도는 동안 시연 시계는 영상 시간으로 흐른다."""

    def __init__(self, session: "LiveSession", scene: dict, camera: dict, path: Path, start: datetime):
        super().__init__(daemon=True)
        self.s, self.scene, self.camera, self.path, self.start_ts = session, scene, camera, path, start
        self.stop_evt = threading.Event()
        self.error = None
        self.person_note = ""
        self.t, self.dur = 0.0, 0.0      # 영상 안의 지금 위치 · 길이 (초) — 화면의 진행 표시

    def run(self):
        import cv2
        from safety_monitor.detector import FlameDetector, PersonDetector, YoloObjectDetector, run_objects
        from safety_monitor.draw import draw
        from safety_monitor.package import MODEL_DIR, ROOT as ENGINE_ROOT
        from safety_monitor.video_io import open_video, resize_max_width
        from safety_monitor.zones import Zones

        s = self.s
        try:
            pkg = package()
            dcfg = pkg.detect
            cap = open_video(self.path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            self.dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("영상에서 프레임을 읽지 못했습니다")
            frame = resize_max_width(frame, dcfg.get("run", {}).get("work_width", 960))
            H, W = frame.shape[:2]
            zones = Zones(self.camera, W, H)
            try:
                person_det = PersonDetector(dcfg["person"], MODEL_DIR)
            except Exception as ex:  # noqa: BLE001 — ultralytics 가 없거나 가중치가 없다
                person_det = None
                self.person_note = f"사람 탐지 없이 돈다 — {str(ex).splitlines()[0][:120]}"
            dets = {}
            if dcfg.get("flame", {}).get("backend", "color") != "off":
                dets["flame"] = FlameDetector(dcfg["flame"], root=ENGINE_ROOT,
                                              roi_mask_fn=lambda sc: zones.mask(tuple(dcfg["flame"].get("polygons", ["hazard"])),
                                                                                dilate_px=int(30 * sc), scale=sc))
            for x in dcfg.get("extra", []):
                try:
                    dets[x["name"]] = YoloObjectDetector(x, root=ENGINE_ROOT)
                except Exception as ex:  # noqa: BLE001
                    self.person_note += f" · {x['name']} 탐지 없음({str(ex)[:60]})"
            ev = dcfg["event"]
            clips = ClipRecorder(s.out_dir, fps, ev["clip_pre_s"], ev["clip_post_s"], ev["clip_max_width"])
            stride = max(1, dcfg.get("run", {}).get("stride", 1))
            with s.lock:
                s.eng.zones = zones
                s.log.clips = clips
            cam_zone = self.camera.get("zone")
            persons, i, t0 = [], 0, time.time()
            while not self.stop_evt.is_set():
                if not s.running:
                    time.sleep(0.1)
                    t0 = time.time() - i / fps
                    continue
                if i > 0:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    frame = resize_max_width(frame, W)
                t = i / fps
                self.t = t
                now = self.start_ts + timedelta(seconds=t)
                if i % stride == 0:
                    persons = person_det(frame) if person_det else []
                    objects = run_objects(dets, frame, persons)
                    with s.lock:
                        s._apply_due(now)
                        s.eng.update_video(now, t, persons, objects)
                        vis = draw(frame, s.eng, zones, cam_zone)
                        for z, ppl in s.eng.store.people.items():
                            s.person_seconds[z] = s.person_seconds.get(z, 0.0) + len(ppl) * stride / fps
                        for d in objects.get("no_helmet", []):     # 안전모 미착용 탐지를 붙였을 때만 (detect.json extra)
                            for q in d.polys:
                                s.no_helmet_seconds[q.zone] = s.no_helmet_seconds.get(q.zone, 0.0) + stride / fps
                else:
                    with s.lock:
                        s.eng.tick(now)
                        vis = draw(frame, s.eng, zones, cam_zone)
                clips.push(t, vis)
                s._set_frame(self.camera["camera_id"], vis)
                s._after_step()
                i += 1
                wait = (t0 + i / fps) - time.time()          # 영상 속도(1×)에 맞춘다. 탐지가 느리면 그만큼 늦게 간다
                if wait > 0:
                    time.sleep(wait)
            cap.release()
            clips.flush()
        except Exception as ex:  # noqa: BLE001
            self.error = f"영상 실행 오류: {ex}"
            traceback.print_exc()
        finally:
            with s.lock:
                e = s.eng
                if e is not None:
                    e.video_on, e.video_t, e.persons, e.objects, e.zones = False, None, [], {}, None
                    e.store.people = {}
                    for rec in e.store.detections.values():
                        rec["on"] = False
                    e.evaluate()
                if s.log is not None:
                    s.log.clips = None
                s.video = None
                s.note(f"영상 장면 '{self.scene.get('name')}' 끝 — 신호로만 판정한다" + (f" · {self.error}" if self.error else ""))


# ====================================================================== 세션
class LiveSession:
    def __init__(self):
        self.lock = threading.RLock()
        self.eng: Engine | None = None
        self.log: LiveEventLog | None = None
        self.rules: dict | None = None
        self.out_dir: Path | None = None
        self.sid: str | None = None
        self.running = False
        self.speed = 10
        self.schedule: list[Signal] = []
        self.sched_i = 0
        self.scenario = None
        self.scene: dict | None = None
        self.scene_started = False
        self.video: VideoRunner | None = None
        self.frames: dict[str, bytes] = {}
        self.person_seconds: dict[str, float] = {}
        self.no_helmet_seconds: dict[str, float] = {}
        self.notes = deque(maxlen=40)
        self.meta: dict = {}
        self._mode_open: dict[tuple[str, str], datetime] = {}
        self._fb_seen = 0
        self._handoff_i = 0
        self._handoff_wall = 0.0
        self._undo: list[dict] = []         # 버튼 · 입력창으로 넣은 최근 입력 — 되돌리기용 (엔진 상태 사진)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------ 읽기
    def clock(self) -> datetime | None:
        with self.lock:
            return self.eng.now if self.eng is not None and self.sid else None

    def note(self, msg: str):
        t = self.eng.now if self.eng is not None else datetime.now()
        self.notes.appendleft((t, msg))

    def _set_frame(self, cam_id: str, vis):
        import cv2
        from safety_monitor.video_io import resize_max_width
        ok, enc = cv2.imencode(".jpg", resize_max_width(vis, 800), [cv2.IMWRITE_JPEG_QUALITY, 72])
        if ok:
            self.frames[cam_id] = enc.tobytes()

    # ------------------------------------------------------------------ 시작 · 멈춤
    def ensure(self):
        """화면이 처음 열릴 때 — 아직 시작 전이면 기록 없이 미리 보기 엔진을 만든다."""
        with self.lock:
            if self.eng is None:
                cfg = load_config()["live"]
                demo = dashboard().get("demo", {})
                sched = demo.get("schedule") or None
                if sched not in package().scenario_keys():
                    sched = None                    # 패키지에 없는 시나리오 — 스케줄 없이 버튼으로만
                self.reset(sched, cfg.get("ruleset", "docgen"), cfg.get("start", "07:55"),
                           (demo.get("scene") or None) if sched else None, cfg.get("speed", 10), record=False)

    def reset(self, schedule: str | None, ruleset: str, start: str, scene: str | None, speed: float,
              record: bool = True) -> str:
        """새 세션. record=True 면 기록 폴더를 만들고 시계를 돌린다."""
        from . import feedback
        self.stop_video()
        if self.sid:
            self._flush()
        with self.lock:
            if self.eng is not None and self.sid:
                self._save_counts()
            pkg = package()
            self.running = False
            sc = pkg.scenario(schedule) if schedule else None
            ids, label = resolve_ruleset(ruleset, pkg, sc)
            rules = pkg.rules(ids)
            rules["_label"] = label
            day = sc.day if sc else demo_day()
            t0 = parse_clock(start or "07:55", day)
            self.sid = None
            self.out_dir = None
            if record:
                n = len(live_sessions()) + 1
                self.sid = f"LIVE-{datetime.now():%Y%m%d-%H%M%S}"
                self.out_dir = LIVE_DIR / self.sid
                self.out_dir.mkdir(parents=True, exist_ok=True)
                seq = sum(len(read_jsonl(d / "events.jsonl")) for d in live_sessions())
            else:
                n, seq = 0, 0
            cooldown = pkg.detect.get("event", {}).get("cooldown_s", 30)
            self.log = LiveEventLog(self.out_dir, rules, seq_start=seq, cooldown_s=cooldown, adjust=feedback.lookup)
            self.eng = Engine(pkg, rules, t0, log=self.log, scenario_dir=sc.dir if sc else None)
            self.rules, self.scenario, self.speed = rules, sc, float(speed or 10)
            self.scene = next((x for x in sc.scenes() if x.get("name") == scene), None) if (sc and scene) else None
            self.scene_started = False
            tl = sc.timeline() if sc else []
            if self.scene and self.scene.get("at"):
                tl = [x for x in tl if x.source != "영상"]      # 영상 탐지가 대신 만든다
            self.schedule, self.sched_i = tl, 0
            self.frames, self.person_seconds, self.no_helmet_seconds = {}, {}, {}
            self._mode_open, self._handoff_i, self._handoff_wall = {}, 0, 0.0
            self._fb_seen = 0
            self._undo = []
            self.notes.clear()
            self.meta = {"schedule": schedule or "", "schedule_title": sc.title if sc else "스케줄 없음 — 버튼으로만",
                         "ruleset": ruleset, "rules_label": label, "applied": list(ids), "start": t0,
                         "scene": scene or "", "n": n}
            self._apply_due(t0)
            self.eng.tick(t0)
            self._track_modes()
            if record:
                append_jsonl(self.out_dir / "session.json", {**self.meta, "sid": self.sid, "start": t0.isoformat(),
                                                              "package": pkg.root.name})
                self.note(f"세션 시작 — {self.meta['schedule_title']} · 규칙 {label}")
            return self.sid or ""

    def start(self):
        with self.lock:
            if not self.sid:
                m = self.meta
                self.reset(m.get("schedule") or None, m.get("ruleset", "docgen"),
                           (m.get("start") or datetime.now()).strftime("%H:%M"), m.get("scene") or None, self.speed)
            self.running = True

    def pause(self):
        with self.lock:
            self.running = False
            self._save_counts()
        self._flush()

    def _flush(self):
        """멈추거나 새 세션으로 넘어갈 때 — 남은 기록을 자동 인계로 마저 넘긴다."""
        try:
            self._auto_handoff(force=True)
        except Exception:  # noqa: BLE001 — 인계가 실패해도 관제는 멈추지 않는다
            traceback.print_exc()

    def _save_counts(self):
        """영상에서 센 사람 시간 · 안전모 미착용 시간을 세션 파일에 누적값으로 한 줄 남긴다 (히트맵 · 통계)."""
        if self.out_dir and (self.person_seconds or self.no_helmet_seconds):
            append_jsonl(self.out_dir / "session.json", {"sid": self.sid, "ts": self.eng.now.isoformat(),
                                                          "person_seconds": dict(self.person_seconds),
                                                          "no_helmet_seconds": dict(self.no_helmet_seconds)})

    def set_speed(self, v: float):
        with self.lock:
            self.speed = float(v)

    def stop_video(self):
        v = self.video
        if v is not None:
            v.stop_evt.set()
            v.join(timeout=3)
        self.video = None

    # ------------------------------------------------------------------ 시계
    def _loop(self):
        last = time.time()
        while True:
            time.sleep(0.25)
            wall = time.time()
            dt, last = wall - last, wall
            try:
                if not self.running or self.video is not None or self.eng is None:
                    continue
                with self.lock:
                    target = self.eng.now + timedelta(seconds=dt * self.speed)
                    self._apply_due(target)
                    if self.video is None:
                        self.eng.tick(target)
                self._after_step()
            except Exception:  # noqa: BLE001 — 시계가 죽으면 화면이 멈춘다. 적고 계속 간다
                traceback.print_exc()

    def _apply_due(self, target: datetime):
        """스케줄에서 target 시각까지의 신호를 넣는다. 장면 시각이 되면 영상을 붙인다."""
        eng = self.eng
        while self.sched_i < len(self.schedule) and self.schedule[self.sched_i].ts <= target:
            sig = self.schedule[self.sched_i]
            self.sched_i += 1
            self._apply(sig)
        sc = self.scene
        if sc and not self.scene_started and sc.get("at") and self.sid:
            at = parse_clock(sc["at"], eng.now.date())
            if target >= at:
                self.scene_started = True
                self._start_video(at)

    def _apply(self, sig: Signal) -> list[str]:
        notes = self.eng.apply(sig)
        for n in notes:
            self.note(f"{sig.ts:%H:%M} {sig.label or sig.signal}: {n}")
        if not notes:
            self.note(f"{sig.ts:%H:%M} {sig.short()} ({sig.source})")
        return notes

    def _start_video(self, at: datetime):
        pkg = package()
        sc = self.scene
        try:
            cam = pkg.scene_camera(sc)              # 장면에 그린 구역이 있으면 그걸, 없으면 카메라 기본 구역
        except Exception as ex:  # noqa: BLE001
            self.note(f"영상 장면을 붙이지 못했다 — {ex}")
            return
        video = sc.get("video") or ""
        cands = [Path(video), self.scenario.dir / video, pkg.root / video]
        path = next((c for c in cands if c.exists()), None)
        if path is None:
            self.note(f"영상 파일이 없다 — {video}. 신호로만 판정한다")
            return
        self.eng.now = at
        self.video = VideoRunner(self, sc, cam, path, at)
        self.video.start()
        self.note(f"{at:%H:%M} 영상 장면 '{sc.get('name')}' 시작 — {cam['camera_id']}"
                  + (" · 장면에 그린 구역" if sc.get("polygons") else " · 카메라 기본 구역"))

    def play_scene_now(self) -> str:
        """
        세션에 붙은 영상 장면을 지금 튼다. 장면 시각(at)이 남았으면 그때까지 스케줄을 1분씩 빨리 감아
        (신호를 넣고 판정을 다시 하고) 그 시각에서 영상을 시작한다. 시각이 지났거나 없으면 지금 시각에서 시작한다.
        """
        with self.lock:
            if not self.sid:
                raise RuntimeError("세션을 시작해야 영상을 틀 수 있다 — 시연 제어에서 새 세션 시작")
            if self.video is not None:
                return f"이미 재생 중 — 영상 장면 '{self.scene.get('name')}'"
            self._reload_scene()
            sc = self.scene
            if not sc:
                raise RuntimeError("이 세션에는 영상 장면이 없다 — 시연 제어에서 장면을 고르고 새 세션을 시작한다")
            at = parse_clock(sc["at"], self.eng.now.date()) if sc.get("at") else None
            self.running = True
            if at and at > self.eng.now and not self.scene_started:
                t0 = self.eng.now
                self._fast_forward(at)                  # at 에 닿으면 _apply_due 가 영상을 붙인다
                skipped = f" — 시연 시계를 {t0:%H:%M} → {at:%H:%M} 로 빨리 감았다 (사이 신호는 다 넣었다)"
            else:
                skipped = ""
            if self.video is None:
                self.scene_started = True
                self._start_video(self.eng.now)
            msg = (f"영상 장면 '{sc.get('name')}' 재생 — {self.eng.now:%H:%M}부터" + skipped) if self.video else \
                  (self.notes[0][1] if self.notes else "영상을 붙이지 못했다")
        self._after_step()
        return msg

    def _fast_forward(self, target: datetime):
        """target 까지 1분씩 — 스케줄 신호를 넣고 판정을 다시 한다 (리플레이와 같은 걸음). 영상이 붙으면 거기서 멈춘다."""
        t = self.eng.now
        while t < target and self.video is None:
            t = min(target, t.replace(second=0, microsecond=0) + timedelta(minutes=1))
            self._apply_due(t)
            if self.video is None:
                self.eng.tick(t)
                self._track_modes()

    def _reload_scene(self):
        """영상 장면 편집기에서 고친 구역 · 영상을 다음 재생에 쓰도록 장면을 파일에서 다시 읽는다."""
        if self.scene and self.scenario is not None:
            try:
                fresh = package().scenario(self.scenario.key).scenes()
            except Exception:  # noqa: BLE001 — 시나리오가 사라졌으면 들고 있던 걸 쓴다
                return
            self.scene = next((x for x in fresh if x.get("name") == self.scene.get("name")), self.scene)

    def refresh_scene(self, schedule: str, name: str | None, orig: str | None = None):
        """장면을 저장 · 삭제했을 때 — 이 세션이 그 장면을 쓰고 있고 아직 재생 전이면 바로 바꿔 끼운다."""
        with self.lock:
            if self.video is not None or self.scenario is None or self.scenario.key != schedule or not self.scene:
                return
            cur = self.scene.get("name")
            if cur not in {name, orig}:
                return
            fresh = package().scenario(schedule).scenes()
            self.scene = next((x for x in fresh if x.get("name") == name), None) if name else None
            self.meta["scene"] = self.scene.get("name") if self.scene else ""
            self.note("영상 장면을 다시 읽었다 — " + (f"'{self.scene['name']}'" if self.scene else "장면이 빠졌다"))

    # ------------------------------------------------------------------ 신호 넣기 (버튼 · 입력창)
    def apply_signal(self, signal: str, zone: str | None = None, target: str | None = None,
                     value: str | None = None, source: str = "버튼", note: str = "",
                     ts: datetime | None = None) -> list[str]:
        with self.lock:
            if self.eng is None:
                self.ensure()
            if not self.sid:
                raise RuntimeError("세션을 시작해야 신호를 넣을 수 있다 — 시연 제어에서 ▶ 시작")
            sig = Signal(ts=ts or self.eng.now, signal=signal, zone=zone or None, target=target or None,
                         value=value or None, source=source, note=note)
            snap, rows0, sched0 = self._snapshot(), len(self.log.rows), self.sched_i
            notes = self._apply(sig)
            self.eng.tick(self.eng.now)
            self._undo.append({"sig": sig, "snap": snap, "rows0": rows0, "sched_i": sched0,
                               "label": note or self.eng.signals.get(signal, {}).get("label") or signal})
            del self._undo[:-UNDO_MAX]
        self._after_step()
        return notes

    # ------------------------------------------------------------------ 되돌리기 (버튼 · 입력창)
    _STATE = ("store", "levels", "mode_since", "modes", "gates", "_dwell", "persistence")

    def _snapshot(self) -> dict:
        """엔진의 판정 상태 사진 — 시계 · 영상 탐지 결과는 빼고 사실 · 단계 · 모드만."""
        return copy.deepcopy({k: getattr(self.eng, k) for k in self._STATE})

    def undo_info(self) -> dict | None:
        """되돌릴 수 있는 마지막 입력 — 화면의 '되돌리기' 버튼이 쓴다."""
        if not self._undo:
            return None
        u = self._undo[-1]
        return {"label": u["label"], "t": f"{u['sig'].ts:%H:%M:%S}", "zone": u["sig"].zone or "",
                "rows": len(self._rows_after(u["rows0"])), "n": len(self._undo)}

    def _rows_after(self, i: int) -> list[str]:
        """i 번째 뒤에 생긴 관제 기록 번호 — 앞서 덧붙인 '입력 취소' 기록은 뺀다."""
        rows = self.log.rows[i:] if self.log else []
        return [r["event_id"] for r in rows if r.get("event_id") and r.get("violation_type") != "입력_취소"]

    def undo_last(self) -> dict:
        """
        마지막 현장 입력(버튼 · 입력창)을 되돌린다. 엔진의 판정 상태를 그 입력 직전으로 돌리고,
        그 뒤 스케줄이 넣은 신호는 다시 넣는다. 시계는 그대로 간다.
        관제 기록(events.jsonl)은 추가 전용이라 지우지 않는다 — 그 입력 뒤에 생긴 기록이 있으면 '입력 취소' 기록을 덧붙인다.
        """
        with self.lock:
            if not self.sid or self.eng is None:
                raise RuntimeError("세션이 돌지 않는다")
            if not self._undo:
                raise RuntimeError("되돌릴 입력이 없다 — 이 세션에서 버튼 · 입력창으로 넣은 것만 되돌린다")
            u = self._undo.pop()
            e, now, sig = self.eng, self.eng.now, u["sig"]
            for k, v in u["snap"].items():
                setattr(e, k, v)
            redo = self.schedule[u["sched_i"]:self.sched_i]     # 그 입력 뒤에 스케줄이 넣은 신호
            real, e.log = e.log, _Mute()        # 다시 넣는 동안은 이미 남은 기록을 또 쓰지 않는다
            try:
                for x in redo:
                    e.apply(x)
                e.now = now
                e.tick(now)
            finally:
                e.log = real
            after = self._rows_after(u["rows0"])
            ev = None
            if after:
                st = self.zone_state(sig.zone) if sig.zone else {}
                ev = self.log.emit(kind="info", ts=now, zone=sig.zone, mode=st.get("mode_label"), violation_type="입력_취소",
                                   level=None, alerted=False,
                                   reason=(f"현장 입력 취소 — {sig.ts:%H:%M:%S} {u['label']} ({sig.source}). "
                                           f"그 뒤 기록 {', '.join(after[:6])}{' …' if len(after) > 6 else ''} 은 이 입력이 들어가 있던 상태에서 "
                                           "나왔다 — 기록은 지우지 않는다(추가 전용)")[:400],
                                   extra={"undone": {"ts": sig.ts.isoformat(timespec='seconds'), "signal": sig.signal, "zone": sig.zone,
                                                     "target": sig.target, "value": sig.value, "source": sig.source},
                                          "after": after})
            self.note(f"{now:%H:%M} 입력 취소 — {sig.ts:%H:%M:%S} {u['label']}"
                      + (f" · 그 뒤 기록 {len(after)}건은 남기고 '입력 취소' 기록을 덧붙였다" if after else "")
                      + (f" · 스케줄 신호 {len(redo)}건은 다시 넣었다" if redo else ""))
        self._after_step()
        msg = f"되돌렸다 — {sig.ts:%H:%M:%S} {u['label']}"
        if after:
            msg += f". 그 뒤 생긴 관제 기록 {len(after)}건은 지우지 않고 '입력 취소' 기록({ev['event_id'] if ev else '-'})을 덧붙였다"
        return {"msg": msg, "after": after}

    def stop_order(self, zone: str) -> dict:
        """
        작업중지 지시 — 관제실이 지시한 시각을 관제 기록(kind=info)으로 남긴다.
        방송 설비와의 연동은 아직 없다. 사고 경과(산업재해조사표)에서 '경보 뒤 지시가 나갔는지'를 확인하는 근거가 된다.
        """
        with self.lock:
            if not self.sid:
                raise RuntimeError("세션이 돌지 않는다 — 지시를 남길 관제 기록이 없다")
            st = self.zone_state(zone)
            ev = self.log.emit(kind="info", ts=self.eng.now, zone=zone, mode=st.get("mode_label"),
                               violation_type="작업중지_지시", level=st.get("level"), alerted=True,
                               reason=f"관제실 작업중지 지시 — {st.get('level')} · {st.get('reason') or ''}"[:200],
                               response=st.get("response") or "")
            self.note(f"{self.eng.now:%H:%M} {zone} 작업중지 지시 기록")
        return ev

    def press(self, key: str) -> list[str]:
        b = package().buttons.get(key)
        if not b:
            raise KeyError(key)
        return self.apply_signal(b["signal"], b.get("zone"), b.get("target"), b.get("value"), "버튼", b.get("label", ""))

    # ------------------------------------------------------------------ 한 걸음 뒤
    def _track_modes(self):
        """모드가 켜지고 꺼진 시각을 남긴다 — 히트맵 · 통계의 '모드가 켜졌을 때 vs 평상시'가 쓴다."""
        eng = self.eng
        now = eng.now
        cur = {(z, n) for z, act in eng.modes.items() for n, since in act if since is not None}
        for key in cur - set(self._mode_open):
            self._mode_open[key] = now
            if self.out_dir:
                append_jsonl(self.out_dir / "modes.jsonl", {"zone": key[0], "mode": key[1], "ts": now.isoformat(), "on": True})
        for key in set(self._mode_open) - cur:
            self._mode_open.pop(key)
            if self.out_dir:
                append_jsonl(self.out_dir / "modes.jsonl", {"zone": key[0], "mode": key[1], "ts": now.isoformat(), "on": False})

    def _after_step(self):
        from . import feedback
        with self.lock:
            if self.eng is None:
                return
            self._track_modes()
            rows = self.log.rows if self.log else []
            new = len(rows) > self._fb_seen
            self._fb_seen = len(rows)
            now = self.eng.now
        if new and self.sid:
            try:
                for a in feedback.evaluate(now=now):
                    self.note(f"{now:%H:%M} 자동 조정 {a['adj_id']} — {a['zone']} {feedback.reason_text(a)}")
            except Exception:  # noqa: BLE001
                traceback.print_exc()
        self._auto_handoff()

    def _auto_handoff(self, force: bool = False):
        cfg = load_config()["live"]
        if not self.sid or not cfg.get("auto_handoff", True):
            return
        if not force and time.time() - self._handoff_wall < cfg.get("auto_handoff_every_s", 10):
            return
        with self.lock:
            rows = self.log.rows[self._handoff_i:]
            ready = []
            for e in rows:                      # 프레임이 아직 안 써졌으면 다음 번에 넘긴다
                if e.get("frame_path") and not (self.out_dir / e["frame_path"]).exists() and not force:
                    break
                ready.append(e)
            if not ready:
                return
            self._handoff_i += len(ready)
            self._handoff_wall = time.time()
        from safety_docs.handoff import receive
        receive(ready, source=f"실시간 관제 · 자동 ({self.sid})", base_dir=self.out_dir, auto=True)

    def handoff(self, event_ids: list[str] | None = None, source: str = "실시간 관제") -> dict:
        """'문서 자동화로 넘기기' — 이 세션의 기록(또는 고른 것)을 넘긴다. 이미 넘긴 것은 인계 기록에 같이 보인다."""
        from safety_docs.handoff import receive
        with self.lock:
            if not self.sid:
                raise RuntimeError("시작한 세션이 없다 — 넘길 관제 기록이 없다")
            rows = [e for e in self.log.rows if not event_ids or e["event_id"] in event_ids]
        if not rows:
            raise RuntimeError("넘길 기록이 없다")
        self._auto_handoff(force=True)
        return receive(rows, source=f"{source} ({self.sid})", base_dir=self.out_dir)

    # ------------------------------------------------------------------ 화면용 요약
    def zone_state(self, zone: str) -> dict:
        """구역 하나의 지금 상태 — 단계 · 경보 여부 · 줄 · 이유 · 모드 · 축 · 사람."""
        eng = self.eng
        active = eng.modes.get(zone) or []
        on_modes = [n for n, since in active if since is not None]
        best = None
        for (z, t), ls in eng.levels.items():
            if z != zone:
                continue
            al = alerting(eng.rules, active, t)
            key = (RANK[ls.level] if al else -1, RANK[ls.level])
            if best is None or key > best[0]:
                best = (key, t, ls, al)
        people = eng.store.people.get(zone, [])
        if best is None:
            return {"zone": zone, "level": "정상", "alerting": False, "modes": on_modes, "table": None, "ls": None,
                    "people": len(people), "computed": "정상"}
        _, t, ls, al = best
        table = eng.tables[t]
        res = ls.result
        present = len(people) > 0 or (not eng.video_on and any(
            (f, zone) in eng.store.on for f in ("ptw", "hot_work_permit", "confined_permit")))
        return {"zone": zone, "table": t, "tdef": table, "ls": ls, "alerting": al,
                "level": ls.level if al else "정상", "computed": ls.level, "row": ls.row, "since": ls.raised_at,
                "reason": res.reason if res else "", "violation": ls.violation, "modes": on_modes,
                "axes": res.axes if res else {}, "people": len(people), "present": present,
                "response": response(table, ls.level, present) if al else "",
                "mode_label": label_mode(active)}

    def snapshot(self) -> dict:
        from . import feedback
        with self.lock:
            self.ensure()
            eng = self.eng
            zs = {z: self.zone_state(z) for z in eng.site.get("zones", {}) if not z.startswith("_")}
            nxt = self.schedule[self.sched_i] if self.sched_i < len(self.schedule) else None
            rows = list(self.log.rows) if self.log else []
            gates = {z: list(g) for z, g in eng.gates.items()}
            docs = {z: d for (f, z), d in eng.store.documents.items()}
            snap = {"sid": self.sid, "now": eng.now, "running": self.running, "speed": self.speed,
                    "meta": dict(self.meta), "zones": zs, "next": nxt, "rows": rows, "gates": gates, "docs": docs,
                    "video": bool(self.video), "video_note": self.video.person_note if self.video else "",
                    "video_pos": (self.video.t, self.video.dur) if self.video else None,
                    "scene_started": self.scene_started, "undo": self.undo_info(),
                    "scene": self.scene, "frames": dict(self.frames), "notes": list(self.notes),
                    "on": {k: v.ts for k, v in eng.store.on.items()}, "marks": {k: dict(v) for k, v in eng.store.marks.items()},
                    "measures": [(m.fact, m.zone, m.target, m.ts, m.value) for m in eng.store.measures],
                    "applied": list(self.rules.get("_applied", [])) if self.rules else []}
        snap["adjust"] = {z: feedback.zone_alert_level(z, snap["now"]) for z in zs}
        return snap


SESSION = LiveSession()
