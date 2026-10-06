"""
카메라 폴리곤 찍기 — 영상 한 장면을 띄우고 마우스로 점을 찍어 패키지의 cameras/<카메라ID>.json 에 저장한다.

  python calibrate.py <패키지> --camera CAM-01 --video 파일 --name E5 --type hazard --zone Z8 [--label 이름]
  python calibrate.py <패키지> --camera CAM-01 --video 파일 --floor      바닥 네 점 (호모그래피, 선택)
  python calibrate.py <패키지> --camera CAM-01 --video 파일 --preview    지금 폴리곤을 그린 사진만 저장

  마우스 왼쪽 = 점 추가 · 오른쪽 = 되돌리기 · Enter = 저장 · c = 지우기 · q = 끝
폴리곤 type 은 규칙이 쓰는 이름과 맞춘다 (예: hazard · work · restricted · watch).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

from safety_monitor.package import OUTPUT_DIR, find_package
from safety_monitor.video_io import imwrite, open_video, resize_max_width
from safety_monitor.zones import Zones

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def main():
    ap = argparse.ArgumentParser(description="카메라 폴리곤 찍기")
    ap.add_argument("package")
    ap.add_argument("--camera", required=True, help="카메라 ID (파일 이름이 된다)")
    ap.add_argument("--video", required=True)
    ap.add_argument("--second", type=float, default=0.0)
    ap.add_argument("--name")
    ap.add_argument("--type", default="hazard")
    ap.add_argument("--zone")
    ap.add_argument("--label")
    ap.add_argument("--floor", action="store_true")
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args()

    root = find_package(args.package)
    path = root / "cameras" / f"{args.camera}.json"
    cam = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "camera_id": args.camera, "zone": args.zone, "polygons": [], "floor_calib": None}

    cap = open_video(Path(args.video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(args.second * fps))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit("프레임을 읽지 못했습니다")
    show = resize_max_width(frame, 1280)
    Hs, Ws = show.shape[:2]

    def existing(img):
        try:
            Zones(cam, img.shape[1], img.shape[0]).draw(img)
        except ValueError as e:
            print(f"[안내] {e}")

    if args.preview:
        img = show.copy()
        existing(img)
        print(f"저장: {imwrite(OUTPUT_DIR / f'polygons_{args.camera}.jpg', img)}")
        return
    if not args.floor and not (args.name and args.zone):
        raise SystemExit("--name 과 --zone 이 필요합니다")

    pts: list[tuple[int, int]] = []

    def on_mouse(ev, x, y, *_):
        if ev == cv2.EVENT_LBUTTONDOWN:
            pts.append((x, y))
        elif ev == cv2.EVENT_RBUTTONDOWN and pts:
            pts.pop()

    cv2.namedWindow("calibrate")
    cv2.setMouseCallback("calibrate", on_mouse)
    title = "floor 4 points" if args.floor else f"{args.name} ({args.type}, {args.zone})"
    while True:
        img = show.copy()
        existing(img)
        for i, p in enumerate(pts):
            cv2.circle(img, p, 5, (0, 255, 255), -1)
            cv2.putText(img, str(i + 1), (p[0] + 6, p[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        if len(pts) >= 2:
            cv2.polylines(img, [np.int32(pts)], not args.floor, (0, 255, 255), 2)
        cv2.putText(img, title + "  [Enter=save c=clear q=quit]", (10, Hs - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        cv2.imshow("calibrate", img)
        k = cv2.waitKey(30) & 0xFF
        if k in (ord("q"), 27):
            print("저장하지 않고 끝냈습니다")
            break
        if k == ord("c"):
            pts.clear()
        if k in (13, 10, ord("s")):
            norm = [[round(x / Ws, 4), round(y / Hs, 4)] for x, y in pts]
            if args.floor:
                if len(norm) != 4:
                    print("바닥 점은 4개")
                    continue
                floor = [[float(v) for v in input(f"{i + 1}번 점의 바닥 좌표(m) x,y : ").split(",")] for i in range(4)]
                cam["floor_calib"] = {"image_pts": norm, "floor_pts": floor}
            else:
                if len(norm) < 3:
                    print("점이 3개 이상이어야 합니다")
                    continue
                cam["polygons"] = [p for p in cam.get("polygons", []) if p["name"] != args.name] + [
                    {"name": args.name, "type": args.type, "zone": args.zone, "label": args.label or args.name,
                     "space": "image", "points": norm}]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(cam, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"저장: {path}")
            break
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
