"""
패키지 검사기 — 회사가 만든 파일이 엔진이 읽을 수 있는 모양인지 본다.

  python validate.py                  packages/ 전부
  python validate.py steel_pickling   하나
  python validate.py 경로/회사패키지

오류 = 엔진이 돌지 않는다 (없는 구역 · 없는 조건 · 틀린 조건어 · 없는 문서 파일 …)
경고 = 돌기는 하지만 의도와 다를 수 있다 (사전에 없는 신호 · 영상 파일 없음 …)
"""
from __future__ import annotations

import sys

from safety_monitor.package import PACKAGES_DIR, PackageError, load_package, validate_package

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def main():
    args = sys.argv[1:]
    targets = args or [p.name for p in sorted(PACKAGES_DIR.iterdir()) if (p / "site.json").exists()]
    bad = 0
    for t in targets:
        try:
            pkg = load_package(t, strict=False)
        except PackageError as e:
            print(f"\n■ {t}\n  [오류] {e}")
            bad += 1
            continue
        errors, warnings = validate_package(pkg)
        n_modes = len([m for m in pkg.rules_base.get("modes", {}) if not m.startswith("_")])
        n_tables = len([t for t in pkg.rules_base.get("judgments", {}) if not t.startswith("_")])
        print(f"\n■ {pkg.root.name} — {pkg.name} ({pkg.site.get('industry', '-')})")
        print(f"  구역 {len(pkg.site.get('zones', {}))} · 신호 {len(pkg.signals)} · 판정표 {n_tables} · 모드 {n_modes} · "
              f"게이트 {len(pkg.rules_base.get('gates', []))} · 개정안 {len(pkg.change_ids())} · "
              f"카메라 {len(pkg.cameras)} · 시나리오 {len(pkg.scenario_keys())}")
        for e in errors:
            print(f"  [오류] {e}")
        for w in warnings:
            print(f"  [경고] {w}")
        if not errors and not warnings:
            print("  문제 없음")
        bad += bool(errors)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
