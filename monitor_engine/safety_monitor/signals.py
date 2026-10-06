"""
신호 한 건의 모양과 시나리오 타임라인 읽기.

해커톤에서는 PLC · PTW · 센서 대신 CSV 와 키보드 버튼이 같은 Signal 을 만든다.
실제로 붙일 때는 그 시스템들이 이 Signal 을 만들면 된다 — 엔진 쪽은 바뀌지 않는다.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path


@dataclass
class Signal:
    ts: datetime                 # 시연 시계 기준 시각
    signal: str                  # 신호 이름 (패키지 signals.json 의 키)
    zone: str | None = None      # 구역 코드
    target: str | None = None    # 대상 (배관 ID · 측정 지점 등)
    value: str | None = None     # 값 (측정값 · 파일 이름 · 작업 종류)
    source: str = "버튼"         # CSV · 버튼 · 영상 · 자동
    note: str = ""
    label: str = ""              # 신호 사전의 이름표 (엔진이 채운다)
    extra: dict = field(default_factory=dict)

    def short(self) -> str:
        s = self.label or self.signal
        if self.target:
            s += f" {self.target}"
        if self.value and self.extra.get("measure"):
            s += f" {self.value}"
        return s


def read_csv(path: str | Path) -> list[dict]:
    """엑셀에서 저장한 CSV(UTF-8 BOM 또는 CP949)도 읽는다."""
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp949"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"CSV 인코딩을 읽을 수 없습니다: {path} (UTF-8 또는 CP949로 저장)")
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items() if k}
            for r in csv.DictReader(io.StringIO(text))]


def parse_clock(s: str, day: date) -> datetime:
    """'09:15' 또는 '09:15:30' → 그날의 시각."""
    parts = [int(x) for x in s.strip().split(":")]
    parts += [0] * (3 - len(parts))
    return datetime.combine(day, time(parts[0], parts[1], parts[2]))


def load_timeline(path: str | Path, day: date) -> list[Signal]:
    """시나리오 CSV (time,signal,zone,target,value,source,note) → 신호 목록 (시각 순)."""
    out = []
    for r in read_csv(path):
        if not r.get("time") or r["time"].startswith("#"):
            continue
        out.append(Signal(ts=parse_clock(r["time"], day), signal=r["signal"], zone=r.get("zone") or None,
                          target=r.get("target") or None, value=r.get("value") or None,
                          source=r.get("source") or "CSV", note=r.get("note") or ""))
    out.sort(key=lambda s: s.ts)
    return out
