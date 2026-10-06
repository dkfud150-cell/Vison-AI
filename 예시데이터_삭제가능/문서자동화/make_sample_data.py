"""
샘플 이벤트 로그와 샘플 프레임 이미지를 만든다.

실제 시스템에서는 ⑤ log_event()가 MySQL events 테이블에 쌓은 값을 쓴다.
해커톤 시연 전까지 문서 생성 쪽을 먼저 돌려 보려고 만든 가짜 데이터다.

기능 확인용 예시 데이터다 — 이 파일도 예시 폴더(예시데이터_삭제가능/문서자동화)에 있고, 폴더째 지워도 된다.

실행:  python make_sample_data.py          (이 폴더에서)
결과:  events.json, frames/*.jpg           (이 폴더에 덮어쓴다)
"""
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
OUT_EVENTS = ROOT / "events.json"
OUT_FRAMES = ROOT / "frames"

# 기준 시각 — 시연을 매번 같은 결과로 돌리려고 고정한다
AS_OF = datetime(2026, 10, 12, 18, 0)

random.seed(7)


def ts(days_ago: float, hour: int = 10) -> str:
    """기준 시각에서 며칠 전 시각을 ISO 문자열로."""
    t = AS_OF - timedelta(days=days_ago)
    t = t.replace(hour=hour, minute=random.randint(0, 59), second=random.randint(0, 59))
    return t.isoformat(timespec="seconds")


events = []
seq = 1000


def add(zone, mode, vtype, days_ago, *, level="경보", alerted=True, adj_id=None,
        false_positive=False, frame=None, hour=10, at=None):
    """
    이벤트 한 건 추가. 필드는 관제 쪽 MySQL events 설계를 따른다.
      level : 3축 판정 단계 — 주의 / 경보 / 최고 경보 (무음 기록이면 None)
      at    : 시각을 정확히 지정할 때 (시연 시나리오의 09:15 같은)
    """
    global seq
    seq += 1
    ev_id = f"EV-{seq}"
    events.append({
        "event_id": ev_id,
        "ts": at or ts(days_ago, hour),
        "zone": zone,
        "mode": mode,
        "violation_type": vtype,
        "level": level if alerted else None,
        "alerted": alerted,            # False = 무음(섀도) 기록 — 규칙이 꺼진 구간
        "adj_id": adj_id,              # 기록 시점에 활성 중이던 자동 조정 번호 (없으면 None)
        "false_positive": false_positive,
        "clip_path": f"clips/{ev_id}.mp4",
        "frame_path": f"frames/{frame}" if frame else None,       # 이 폴더 기준 (문서 자동화가 절대 경로로 바꿔 읽는다)
    })
    return ev_id


# ① 대수리 사전 작업 중 배관 구역 진입 — 가장 잦다 (위험도 12 → 수시평가 대상)
for d in [0.2, 0.9, 1.5, 2.3, 3.1, 4.4, 5.6, 9.2, 11.5]:
    add("Z10", "대수리 사전 작업", "배관구역_진입", d)
# 강화 기간(자동 조정 ADJ-...)에 잡힌 건 — 가능성 계산에서는 따로 센다
add("Z10", "대수리 사전 작업", "배관구역_진입", 0.5, adj_id="ADJ-20261011-001")
add("Z10", "대수리 사전 작업", "배관구역_진입", 0.4, adj_id="ADJ-20261011-001",
    frame="EV_pipe_zone.jpg", hour=14)
# 오탐 표시된 건 — 통계에서 제외
add("Z10", "대수리 사전 작업", "배관구역_진입", 2.0, false_positive=True)

# ② 평상시 같은 구역 통행 — 무음 기록. 위험성평가 빈도에 넣지 않는다
for i in range(25):
    add("Z10", "평상시", "배관구역_진입", random.uniform(0, 13.9), alerted=False)

# ③ 배소로 정비 — 대수리 사전 작업 모드에서 2인 1조 미준수
for d in [2.7, 8.1]:
    add("Z8", "대수리 사전 작업", "2인1조_미준수", d, level="주의")

# ④ 산세 구역 화기 — 배소로 주변 화기 작업에 화재감시자 없음
for d in [1.2, 3.8, 9.9]:
    add("Z8", "산세 구역 화기", "화재감시자_부재", d)
add("Z8", "산세 구역 화기", "화재감시자_부재", 0.4, frame="EV_fire_watch.jpg", hour=8)

# ⑤ 확정 시연 09:15 — 인접 구역 그라인더 불티 + 배기 정지(축적) + 잔류 가스 → 최고 경보
#    건수는 1건이지만 중대성 4 · 최고 경보 → 수시평가 제안. 09:22 사고는 site_profile.json 에 있다.
add("Z8", "산세 구역 화기", "점화원_축적", 0, level="최고 경보",
    frame="EV_ignition.jpg", at=AS_OF.replace(hour=9, minute=15, second=0).isoformat(timespec="seconds"))

# ⑥ 산세조 화기 작업 전 가스 측정 기록 없음 — 판정표 4번 줄(경보)
for d in [4.9, 12.2]:
    add("Z3", "산세 구역 화기", "점화원_가스측정_없음", d)

# ⑦ 평상시 산 순환·저장 구역 안전모 미착용 (평상시에도 켜져 있는 기본 규칙)
for d in [0.6, 2.2, 3.5, 5.1, 10.3]:
    add("Z6", "평상시", "안전모_미착용", d, level="주의")

events.sort(key=lambda e: e["ts"])
OUT_EVENTS.parent.mkdir(parents=True, exist_ok=True)
OUT_EVENTS.write_text(json.dumps({"as_of": AS_OF.isoformat(), "events": events},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
print(f"이벤트 {len(events)}건 → {OUT_EVENTS}")


# ---------------------------------------------------------------------------
# 샘플 프레임 — 실제 CCTV 캡처로 바꿔 끼우는 자리표시 이미지
# ---------------------------------------------------------------------------
def load_font(size):
    for p in ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
              "C:/Windows/Fonts/malgun.ttf"]:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def frame(name, title, draw_fn):
    img = Image.new("RGB", (960, 540), (58, 62, 66))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 380, 960, 540], fill=(88, 90, 92))           # 바닥
    draw_fn(d)
    d.rectangle([0, 0, 960, 34], fill=(0, 0, 0))
    d.text((12, 6), f"CAM  {title}", font=load_font(18), fill=(230, 230, 230))
    d.text((12, 505), "샘플 프레임 — 실제 CCTV 캡처로 교체", font=load_font(16),
           fill=(255, 210, 90))
    OUT_FRAMES.mkdir(parents=True, exist_ok=True)
    img.save(OUT_FRAMES / name, quality=90)


def person(d, x, y, helmet=True, color=(40, 90, 200)):
    d.ellipse([x - 14, y - 90, x + 14, y - 62], fill=(230, 190, 160))       # 머리
    if helmet:
        d.chord([x - 18, y - 98, x + 18, y - 70], 180, 360, fill=(255, 200, 0))
    d.rectangle([x - 18, y - 60, x + 18, y - 10], fill=color)               # 몸
    d.rectangle([x - 16, y - 10, x - 3, y + 30], fill=(40, 40, 50))          # 다리
    d.rectangle([x + 3, y - 10, x + 16, y + 30], fill=(40, 40, 50))


def pipe_zone(d):
    for i, c in enumerate([(160, 160, 60), (170, 90, 60), (120, 150, 170)]):
        y = 400 + i * 28
        d.rectangle([0, y, 960, y + 16], fill=c)                           # 바닥 배관 3줄
    d.rectangle([640, 380, 960, 540], outline=(0, 220, 120), width=3)      # 지정 통로
    d.polygon([(40, 395), (560, 395), (560, 470), (40, 470)], outline=(255, 60, 60), width=3)
    person(d, 320, 420)


def fire_watch(d):
    d.rectangle([380, 150, 600, 380], fill=(110, 70, 50))                  # 배소로 버너부
    d.rectangle([600, 250, 960, 272], fill=(170, 170, 60))                 # 연료가스 배관
    person(d, 330, 400)
    for i in range(12):
        d.line([(372, 330), (372 + random.randint(-40, 40), 300 + random.randint(-40, 30))],
               fill=(255, 180, 40), width=2)                               # 용접 불꽃


def ignition(d):
    d.rectangle([80, 180, 360, 380], fill=(110, 70, 50))                   # 배소로
    d.rectangle([360, 260, 700, 280], fill=(170, 170, 60))                 # 맹판 작업 배관
    person(d, 430, 400)
    person(d, 800, 400, color=(200, 90, 40))                               # 인접 구역 작업자
    for i in range(18):
        d.line([(760, 360), (760 + random.randint(-70, 10), 330 + random.randint(-50, 30))],
               fill=(255, 150, 30), width=2)                               # 그라인더 불티


frame("EV_pipe_zone.jpg", "Z10 배관 구역 통로", pipe_zone)
frame("EV_fire_watch.jpg", "Z8 산 재생설비(배소로)", fire_watch)
frame("EV_ignition.jpg", "Z8 산 재생설비(배소로)", ignition)
print(f"샘플 프레임 3장 → {OUT_FRAMES}")
