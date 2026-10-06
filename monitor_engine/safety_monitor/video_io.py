"""
영상 읽기 · 쓰기 — 윈도우 한글 경로 대비.

OpenCV 는 윈도우에서 한글이 들어간 경로(바탕 화면\\안전관제 …)를 못 여는 경우가 있다.
열기에 실패하면 영문 임시 폴더로 복사해서 다시 열고, 쓰기는 영문 임시 경로에 쓴 뒤 옮긴다.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import cv2
import numpy as np


def open_video(path: str | Path) -> cv2.VideoCapture:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"영상 파일이 없습니다: {path}")
    cap = cv2.VideoCapture(str(path))
    if cap.isOpened():
        return cap
    tmp = Path(tempfile.gettempdir()) / f"sm_input{path.suffix.lower() or '.mp4'}"
    shutil.copyfile(path, tmp)
    cap = cv2.VideoCapture(str(tmp))
    if not cap.isOpened():
        raise RuntimeError(f"영상을 열 수 없습니다: {path} (코덱 확인 — mp4(H.264) 권장)")
    return cap


class SafeWriter:
    """cv2.VideoWriter 를 영문 임시 경로에 열고, close() 때 원하는 경로로 옮긴다."""

    def __init__(self, path: str | Path, fps: float, size: tuple[int, int]):
        self.final = Path(path)
        self.final.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(suffix=".mp4", prefix="sm_")
        os.close(fd)
        self.tmp = Path(tmp)
        self.size = size
        self.w = cv2.VideoWriter(str(self.tmp), cv2.VideoWriter_fourcc(*"mp4v"), max(1.0, float(fps)), size)
        if not self.w.isOpened():
            raise RuntimeError("VideoWriter 를 열 수 없습니다 (mp4v 코덱)")

    def write(self, frame: np.ndarray):
        if (frame.shape[1], frame.shape[0]) != self.size:
            frame = cv2.resize(frame, self.size)
        self.w.write(frame)

    def close(self) -> Path:
        self.w.release()
        shutil.move(str(self.tmp), str(self.final))
        return self.final


def imwrite(path: str | Path, img: np.ndarray, quality: int = 90) -> Path:
    """한글 경로에도 저장되는 imwrite."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("이미지 인코딩 실패")
    path.write_bytes(buf.tobytes())
    return path


def imread(path: str | Path) -> np.ndarray | None:
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def resize_max_width(img: np.ndarray, max_w: int) -> np.ndarray:
    h, w = img.shape[:2]
    if w <= max_w:
        return img
    s = max_w / w
    return cv2.resize(img, (max_w, int(round(h * s))), interpolation=cv2.INTER_AREA)
