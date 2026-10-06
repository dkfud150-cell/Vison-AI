"""
영상 장면 — 화면에서 영상을 올리고, 첫 프레임 위에 구역(폴리곤)을 그려 장면으로 등록한다.

  영상     사업장 패키지 videos/ 에 저장한다 (scenario.json 의 video 경로가 가리키는 곳과 같다)
  장면     그 시나리오의 scenario.json scenes 에 한 줄 — 이름 · 시작 시각 · 카메라 · 영상 · 구역(polygons)
  구역     장면에 적힌 polygons 가 있으면 그 장면이 도는 동안 카메라 기본 구역(cameras/*.json) 대신 쓴다.
           없으면 예전처럼 카메라 기본 구역을 쓴다. 좌표는 화면 비율(0~1)이라 해상도가 달라도 같다.

판정은 폴리곤 이름이 아니라 종류(type)로 걸린다 — rules.json 의 checks 가 'work' · 'restricted' 를,
불꽃 탐지(detect.json flame.polygons)가 'hazard' · 'hazard_repair' 를 본다. 그래서 종류와 구역만 맞으면
새로 그린 구역에도 같은 규칙 · 판정표가 그대로 걸린다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from .common import package, package_changed, zone_name, zones

VIDEO_EXT = {".mp4", ".m4v", ".mov", ".avi", ".mkv", ".webm"}

# 구역 종류 — 화면에 보이는 이름 · 설명 · 색. 판정이 보는 종류는 monitor_engine 의 zones.py / rules.json 과 같다.
# 이 네 개는 판정에 쓰여 고정이고, 그 밖의 종류(통로 · 설비 위치 …)는 관리자가 화면에서 더한다 → 패키지 zone_types.json
TYPES = {
    "hazard": {"label": "위험구역 (상시)", "prefix": "E", "color": "#e5584a",
               "desc": "설비 때문에 늘 위험한 곳. 불꽃이 여기서 잡히면 점화원 축이 켜진다"},
    "hazard_repair": {"label": "위험구역 (작업 중)", "prefix": "ER", "color": "#ff6b5e",
                      "desc": "그 작업 때문에 한시적으로 위험한 곳. 불꽃도 본다 · 모드가 켜질 때 진하게 보인다"},
    "work": {"label": "작업 구역", "prefix": "W", "color": "#6cc3c8",
             "desc": "작업 인원 · 2인 1조 · 화재감시자를 세는 곳"},
    "restricted": {"label": "출입 제한", "prefix": "X", "color": "#e0a13a",
                   "desc": "모드가 켜지면 사람이 들어올 때 경보"},
}
HAZARD_TYPES = ("hazard", "hazard_repair")
TYPE_FILE = "zone_types.json"
_type_lock = threading.Lock()


# ====================================================================== 구역 종류 — 기본 넷 + 관리자가 더한 것
def all_types() -> dict[str, dict]:
    """key → {label, prefix, color, desc, builtin}. 기본 넷이 먼저, 관리자가 더한 것이 뒤."""
    out = {k: {**v, "builtin": True} for k, v in TYPES.items()}
    for t in package().zone_types:
        if t.get("key") and t["key"] not in out:
            out[t["key"]] = {"label": t.get("label") or t["key"], "prefix": t.get("prefix") or "P",
                             "color": t.get("color") or "#9aa4af", "desc": t.get("desc") or "", "builtin": False}
    return out


def type_usage() -> dict[str, list[str]]:
    """종류마다 어디서 쓰는지 — '시나리오/장면.구역' · 'cameras/카메라.구역'."""
    pkg = package()
    use: dict[str, list[str]] = {}
    for c in pkg.cameras.values():
        for q in c.get("polygons", []):
            use.setdefault(q.get("type", "work"), []).append(f"카메라 {c['camera_id']}.{q.get('name')}")
    for k in pkg.scenario_keys():
        for x in pkg.scenario(k).scenes():
            for q in x.get("polygons") or []:
                use.setdefault(q.get("type"), []).append(f"장면 ‘{x.get('name')}’.{q.get('name')}")
    return use


def _type_file() -> tuple[Path, dict]:
    p = package().root / TYPE_FILE
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {
        "_설명": "영상 장면 편집기 '구역 추가'에 나오는 종류 가운데 관리자가 더한 것. 기본 네 종류(hazard · hazard_repair · "
                 "work · restricted)는 판정에 쓰여서 여기 적지 않는다. 여기 종류는 화면 표시와 사람 위치 기록에 쓰이고, "
                 "판정에 쓰려면 rules.json 모드 checks 의 polygons 에 key 를 적는다.", "types": []}
    data.setdefault("types", [])
    return p, data


def _write_json(p: Path, data: dict):
    text = json.dumps(data, ensure_ascii=False, indent=2)
    json.loads(text)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(text + "\n", encoding="utf-8")
    tmp.replace(p)
    package_changed()


def save_type(body: dict) -> dict:
    """구역 종류 더하기 · 고치기 (관리자). key 를 비우면 영문으로 하나 만든다."""
    label = str(body.get("label") or "").strip()
    color = str(body.get("color") or "").strip().lower()
    desc = str(body.get("desc") or "").strip()
    key = str(body.get("key") or "").strip().lower()
    prefix = str(body.get("prefix") or "").strip().upper()
    if not label or len(label) > 30:
        raise ValueError("종류 이름을 30자 안으로 적는다 — 예: 통로 (작업자 이동)")
    if not re.fullmatch(r"#[0-9a-f]{6}", color):
        raise ValueError("색은 #RRGGBB 로 고른다")
    if len(desc) > 120:
        raise ValueError("설명은 120자 안으로")
    with _type_lock:
        p, data = _type_file()
        types = data["types"]
        have = all_types()
        cur = next((t for t in types if t.get("key") == key), None) if key else None
        if key and key in TYPES:
            raise ValueError(f"‘{key}’ 는 판정에 쓰는 기본 종류라 바꿀 수 없다")
        if cur is None:
            if any((t.get("label") or "") == label for t in types) or any(v["label"] == label for v in TYPES.values()):
                raise ValueError(f"같은 이름의 종류가 이미 있다 — ‘{label}’")
            if key:
                if not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", key):
                    raise ValueError("영문 키는 영문 소문자로 시작하는 영문 · 숫자 · _ (예: passage) — 비우면 저절로 만든다")
            else:
                n = 1
                while f"type{n}" in have:
                    n += 1
                key = f"type{n}"
            if not prefix:
                prefix = "".join(ch for ch in key.upper() if ch.isalpha())[:2] or "P"
            if not re.fullmatch(r"[A-Z]{1,3}", prefix):
                raise ValueError("구역 이름 앞글자는 영문 대문자 1~3자 (예: P → P1, P2)")
            types.append({"key": key, "label": label, "prefix": prefix, "color": color, "desc": desc})
            verb = "더했다"
        else:
            cur.update(label=label, color=color, desc=desc, **({"prefix": prefix} if prefix else {}))
            verb = "고쳤다"
        _write_json(p, data)
    return {"key": key, "msg": f"구역 종류 ‘{label}’ 를 {verb} ({key}) — 화면 표시 · 사람 위치 기록용. "
                               f"판정에 쓰려면 rules.json 의 polygons 에 ‘{key}’ 를 적는다"}


def remove_type(body: dict) -> dict:
    key = str(body.get("key") or "").strip()
    if key in TYPES:
        raise ValueError("판정에 쓰는 기본 종류는 지울 수 없다")
    used = type_usage().get(key, [])
    if used:
        raise ValueError(f"이 종류를 쓰는 구역이 {len(used)}개 있다 — {', '.join(used[:4])}" + (" …" if len(used) > 4 else "")
                         + ". 그 구역의 종류를 바꾸거나 지운 뒤 다시 한다")
    with _type_lock:
        p, data = _type_file()
        left = [t for t in data["types"] if t.get("key") != key]
        if len(left) == len(data["types"]):
            raise ValueError(f"없는 종류 ‘{key}’")
        data["types"] = left
        _write_json(p, data)
    return {"msg": f"구역 종류 ‘{key}’ 를 지웠다"}


# ====================================================================== 카메라 — 장면 편집기에서 한 대 더하기
def save_camera(body: dict) -> dict:
    """새 카메라 → cameras/<id>.json. 기본 구역 없이 만든다 — 장면마다 그린 구역으로 판정한다."""
    pkg = package()
    cid = str(body.get("camera_id") or "").strip()
    zone = body.get("zone") or ""
    label = str(body.get("label") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,39}", cid):
        raise ValueError("카메라 ID 는 영문 · 숫자 · - · _ 로 (예: CAM-Z8-02) — 파일 이름이 된다")
    if cid in pkg.cameras or (pkg.root / "cameras" / f"{cid}.json").exists():
        raise ValueError(f"이미 있는 카메라 ‘{cid}’")
    if zone not in zones():
        raise ValueError("카메라가 보는 구역을 고른다")
    if len(label) > 60:
        raise ValueError("설명은 60자 안으로")
    d = pkg.root / "cameras"
    d.mkdir(exist_ok=True)
    _write_json(d / f"{cid}.json", {
        "_설명": f"영상 장면 편집기에서 만든 카메라 ({datetime.now():%Y-%m-%d %H:%M}). 기본 구역이 없다 — 이 카메라를 쓰는 장면마다 "
                 "화면에서 그린 구역으로 판정한다. 기본 구역이 필요하면 calibrate.py 로 polygons 를 찍는다.",
        "camera_id": cid, "zone": zone, "label": label, "polygons": [], "floor_calib": None})
    return {"camera_id": cid, "msg": f"카메라 ‘{cid}’ 를 더했다 — {zone} {zone_name(zone)}" + (f" · {label}" if label else "")}


def remove_camera(body: dict) -> dict:
    """카메라 파일 지우기 — 어느 장면도 쓰지 않고 기본 구역도 없는 카메라만."""
    pkg = package()
    cid = str(body.get("camera_id") or "").strip()
    cam = pkg.cameras.get(cid)
    if not cam:
        raise ValueError(f"없는 카메라 ‘{cid}’")
    if cam.get("polygons"):
        raise ValueError(f"‘{cid}’ 에는 기본 구역이 {len(cam['polygons'])}개 있다 — 화면에서는 지우지 않는다 (cameras/{cid}.json)")
    used = [f"{k}/{x.get('name')}" for k in pkg.scenario_keys() for x in pkg.scenario(k).scenes() if x.get("camera") == cid]
    if used:
        raise ValueError(f"이 카메라를 쓰는 장면이 있다 — {', '.join(used[:4])}. 장면의 카메라를 바꾸거나 뺀 뒤 다시 한다")
    Path(cam["_path"]).unlink()
    package_changed()
    return {"msg": f"카메라 ‘{cid}’ 를 지웠다"}


# ====================================================================== 경로
def _scenario(schedule: str):
    if not schedule:
        raise ValueError("신호 스케줄을 먼저 고른다 — 영상 장면은 스케줄(시나리오)마다 따로 둔다")
    return package().scenario(schedule)


def videos_dir() -> Path:
    return package().root / "videos"


def resolve_video(video: str, schedule: str | None = None) -> Path:
    """장면의 video 경로 → 실제 파일. 패키지 폴더 밖은 열지 않는다."""
    pkg = package()
    if not video:
        raise ValueError("영상이 없다")
    if Path(video).suffix.lower() not in VIDEO_EXT:
        raise ValueError(f"영상 파일이 아니다 — {video}")
    bases = ([_scenario(schedule).dir] if schedule else []) + [pkg.root]
    for b in bases:
        p = (b / video).resolve()
        if p.exists() and (pkg.root.resolve() in p.parents):
            return p
    raise ValueError(f"영상 파일이 없다 — {video}")


def _rel(p: Path) -> str:
    return p.resolve().relative_to(package().root.resolve()).as_posix()


def _safe_name(filename: str) -> str:
    stem, ext = os.path.splitext(Path(filename or "").name)
    ext = ext.lower()
    if ext not in VIDEO_EXT:
        raise ValueError(f"영상 파일만 올린다 ({', '.join(sorted(VIDEO_EXT))}) — 받은 것: {ext or '확장자 없음'}")
    # OpenCV 가 윈도우 한글 경로를 못 여는 경우가 있어 파일 이름은 영문 · 숫자로만 둔다
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._-")[:60]
    return (stem or f"scene_{datetime.now():%Y%m%d_%H%M%S}") + ext


# ====================================================================== 영상 읽기
_lock = threading.Lock()
_frame_cache: dict[tuple[str, float], tuple[bytes, dict]] = {}


def _open(path: Path):
    """cv2.VideoCapture — 한글 경로에서 못 열면 영문 임시 파일로 복사해서 연다(돌고 있는 영상과 겹치지 않게 이름을 따로)."""
    import cv2
    cap = cv2.VideoCapture(str(path))
    if cap.isOpened():
        return cap, None
    fd, tmp = tempfile.mkstemp(suffix=path.suffix.lower() or ".mp4", prefix="sm_scene_")
    os.close(fd)
    shutil.copyfile(path, tmp)
    cap = cv2.VideoCapture(tmp)
    return cap, Path(tmp)


def first_frame(path: Path) -> tuple[bytes, dict]:
    """첫 프레임 JPEG 와 영상 정보(가로 · 세로 · fps · 길이). 못 읽으면 ValueError."""
    import cv2
    key = (str(path), path.stat().st_mtime)
    with _lock:
        if key in _frame_cache:
            return _frame_cache[key]
    cap, tmp = _open(path)
    try:
        if not cap.isOpened():
            raise ValueError(f"영상을 열지 못했다 — {path.name}. mp4(H.264)로 바꿔서 올린다")
        ok, frame = cap.read()
        if not ok or frame is None:
            raise ValueError(f"영상에서 프레임을 읽지 못했다 — {path.name}. mp4(H.264)로 바꿔서 올린다")
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        h, w = frame.shape[:2]
        ok, enc = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if not ok:
            raise ValueError("첫 프레임을 그림으로 바꾸지 못했다")
        info = {"w": int(w), "h": int(h), "fps": round(float(fps), 2),
                "seconds": round(n / fps, 1) if fps > 0 and n > 0 else None}
    finally:
        cap.release()
        if tmp:
            tmp.unlink(missing_ok=True)
    out = (enc.tobytes(), info)
    with _lock:
        if len(_frame_cache) > 40:
            _frame_cache.clear()
        _frame_cache[key] = out
    return out


def save_upload(schedule: str, filename: str, fileobj) -> dict:
    """올린 영상을 videos/ 에 저장하고 첫 프레임을 확인한다. 같은 이름이 있으면 뒤에 -2, -3 …"""
    _scenario(schedule)                              # 스케줄이 있는지 먼저
    name = _safe_name(filename)
    d = videos_dir()
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=Path(name).suffix, prefix="sm_up_", dir=d)
    os.close(fd)
    tmp = Path(tmp)
    try:
        with open(tmp, "wb") as f:
            shutil.copyfileobj(fileobj, f)
        if tmp.stat().st_size == 0:
            raise ValueError("빈 파일이다")
        _, info = first_frame(tmp)                   # 못 읽는 영상이면 여기서 멈춘다 — 저장하지 않는다
        stem, ext = os.path.splitext(name)
        dest, i = d / name, 2
        while dest.exists():
            if dest.stat().st_size == tmp.stat().st_size and dest.read_bytes() == tmp.read_bytes():
                tmp.unlink()                         # 같은 파일을 또 올렸다 — 있던 것을 쓴다
                break
            dest, i = d / f"{stem}-{i}{ext}", i + 1
        else:
            tmp.replace(dest)
            os.chmod(dest, 0o644)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return {"video": _rel(dest), "file": dest.name, **info}


# ====================================================================== 장면 읽기 · 쓰기
def _read(schedule: str) -> tuple[Path, dict]:
    sc = _scenario(schedule)
    p = sc.dir / "scenario.json"
    return p, json.loads(p.read_text(encoding="utf-8"))


def _write(p: Path, data: dict):
    """scenario.json 쓰기 — 사람이 읽는 파일이라 구역 좌표(points)는 한 줄로 둔다."""
    import copy
    d = copy.deepcopy(data)
    pts = []
    for sc in d.get("scenes", []):
        for poly in sc.get("polygons", []) or []:
            pts.append(json.dumps(poly.get("points", [])))
            poly["points"] = f"__PTS_{len(pts) - 1}__"
    text = json.dumps(d, ensure_ascii=False, indent=2)
    for i, t in enumerate(pts):
        text = text.replace(f'"__PTS_{i}__"', t)
    json.loads(text)                                   # 망가진 파일을 쓰지 않는다
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(text + "\n", encoding="utf-8")
    tmp.replace(p)
    package_changed()


def _cam_polys(cam: dict) -> list[dict]:
    return [{"name": p.get("name"), "type": p.get("type"), "zone": p.get("zone") or cam.get("zone"),
             "label": p.get("label"), "points": p.get("points")}
            for p in cam.get("polygons", []) if p.get("space", "image") == "image"]


def options(schedule: str) -> dict:
    """구역 그리기 창이 쓰는 값 — 카메라(기본 구역) · 구역 목록 · 종류 · 이 스케줄의 장면."""
    pkg = package()
    sc = _scenario(schedule)
    cams = [{"id": c["camera_id"], "zone": c.get("zone"), "label": c.get("label") or "", "polygons": _cam_polys(c)}
            for c in pkg.cameras.values()]
    scenes = []
    for x in sc.scenes():
        own = bool(x.get("polygons"))
        cam = pkg.cameras.get(x.get("camera") or "", {})
        scenes.append({"name": x.get("name"), "at": x.get("at"), "camera": x.get("camera"), "video": x.get("video"),
                       "own": own, "polygons": x["polygons"] if own else _cam_polys(cam)})
    vid = [x for x in sc.timeline() if x.source == "영상"]       # 영상이 대신 만드는 신호의 시각 = 영상을 붙일 시각
    use = type_usage()
    return {"schedule": schedule, "title": sc.title, "zone": sc.zone,
            "suggest_at": f"{vid[0].ts:%H:%M}" if vid else "",
            "cameras": cams, "scenes": scenes,
            "zones": [{"id": z, "name": zone_name(z)} for z in zones()],
            "types": [{"key": k, "used": len(use.get(k, [])), **v} for k, v in all_types().items()]}


def _clean_polys(polys: list, zs: set[str], cam_zone: str | None) -> list[dict]:
    if not polys:
        raise ValueError("구역을 하나 이상 그린다")
    out, names = [], set()
    kinds = all_types()
    for i, p in enumerate(polys, 1):
        name = str(p.get("name") or "").strip()
        label = str(p.get("label") or "").strip()
        t = p.get("type")
        zone = p.get("zone") or cam_zone
        pts = p.get("points") or []
        who = f"{i}번 구역" + (f" ({name})" if name else "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,20}", name):
            raise ValueError(f"{who}: 이름은 영문 · 숫자 20자 이내 (영상 위에 적힌다 — 예: E1, W1)")
        if name in names:
            raise ValueError(f"구역 이름 ‘{name}’ 가 두 번 나온다")
        names.add(name)
        if t not in kinds:
            raise ValueError(f"{who}: 종류를 고른다" + (f" — ‘{t}’ 는 지워진 종류다" if t else ""))
        if zone not in zs:
            raise ValueError(f"{who}: 없는 구역 ‘{zone}’")
        if len(pts) < 3:
            raise ValueError(f"{who}: 점이 3개 이상이어야 한다")
        try:
            pts = [[round(min(1.0, max(0.0, float(x))), 4), round(min(1.0, max(0.0, float(y))), 4)] for x, y in pts]
        except (TypeError, ValueError):
            raise ValueError(f"{who}: 점 좌표가 잘못됐다") from None
        out.append({"name": name, "type": t, "zone": zone, "label": label or f"{name} {kinds[t]['label']}",
                    "space": "image", "points": pts})
    if not any(p["type"] in HAZARD_TYPES for p in out):
        raise ValueError("위험구역(상시 또는 작업 중)을 하나 이상 그린다 — 없으면 영상 불꽃이 점화원으로 잡히지 않는다")
    return out


def save_scene(body: dict) -> dict:
    """장면 저장 — 같은 이름(또는 고치기 전 이름 orig)이 있으면 바꾸고, 없으면 덧붙인다."""
    from safety_monitor.signals import parse_clock
    schedule = body.get("schedule") or ""
    p, data = _read(schedule)
    pkg = package()
    name = str(body.get("name") or "").strip()
    orig = str(body.get("orig") or "").strip()
    at = str(body.get("at") or "").strip()
    cam_id = body.get("camera") or ""
    video = str(body.get("video") or "").strip()
    if not name:
        raise ValueError("장면 이름을 적는다")
    if not re.fullmatch(r"\d{1,2}:\d{2}", at):
        raise ValueError("시작 시각은 09:15 처럼 적는다 — 이 시각이 되면 영상이 붙는다")
    parse_clock(at, datetime.now().date())
    if cam_id not in pkg.cameras:
        raise ValueError(f"없는 카메라 ‘{cam_id}’")
    resolve_video(video, schedule)
    cam = pkg.cameras[cam_id]
    polys = _clean_polys(body.get("polygons") or [], set(zones()), cam.get("zone"))
    scenes = data.setdefault("scenes", [])
    if any(x.get("name") == name for x in scenes) and name != orig:
        raise ValueError(f"같은 이름의 장면이 이미 있다 — ‘{name}’")
    entry = {"name": name, "at": f"{int(at.split(':')[0]):02d}:{at.split(':')[1]}", "camera": cam_id, "video": video,
             "polygons": polys, "_구역": f"화면에서 그린 구역 ({datetime.now():%Y-%m-%d %H:%M}) — 이 장면이 도는 동안 카메라 기본 구역 대신 쓴다"}
    idx = next((i for i, x in enumerate(scenes) if x.get("name") == (orig or name)), None)
    if idx is None:
        scenes.append(entry)
        verb = "등록"
    else:
        old = scenes[idx]
        keep = {k: v for k, v in old.items() if k not in entry and not (k == "_설명" and old.get("video") != video)}
        scenes[idx] = {**entry, **keep}
        verb = "고침"
    _write(p, data)
    return {"name": name, "msg": f"장면 ‘{name}’ {verb} — {entry['at']} · {cam_id} · 구역 {len(polys)}개. "
                                 "관제 화면에서 틀려면 ⏭ 고른 장면 바로 재생"}


def remove_scene(body: dict) -> dict:
    """장면을 목록에서 뺀다. 영상 파일은 지우지 않는다(videos/ 에 남는다)."""
    schedule = body.get("schedule") or ""
    name = str(body.get("name") or "").strip()
    p, data = _read(schedule)
    scenes = data.get("scenes", [])
    left = [x for x in scenes if x.get("name") != name]
    if len(left) == len(scenes):
        raise ValueError(f"없는 장면 ‘{name}’")
    data["scenes"] = left
    _write(p, data)
    return {"msg": f"장면 ‘{name}’ 을 목록에서 뺐다 — 영상 파일은 videos/ 에 그대로 있다"}
