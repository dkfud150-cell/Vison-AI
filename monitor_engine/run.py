"""
실행 — 패키지(회사 파일)를 받아 시스템을 돌린다.

타임라인 (영상 없음 · 기대 결과가 있으면 대조)
  python run.py <패키지> <시나리오>                         variants 전부
  python run.py <패키지> <시나리오> --variant "개정 후"
  python run.py <패키지> <시나리오> --changes R1,R3         개정안을 직접 고른다 (none · all · docgen 도 됨)
  python run.py <패키지>                                    그 패키지 시나리오 전부
  python run.py --all                                       packages/ 전부

영상 (탐지 → 엔진 → 기록)
  python run.py <패키지> <시나리오> --scene <장면 이름>      scenario.json 의 scenes 대로
  python run.py <패키지> [<시나리오>] --video 파일 --at 09:15 [--camera ID]
  옵션: --show 창 · --save 표시 영상 저장 · --stride 2 · --flame color|yolo|off

<패키지> 는 packages/ 아래 이름 또는 아무 폴더 경로.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from safety_monitor.package import OUTPUT_DIR, PACKAGES_DIR, ROOT, PackageError, load_package, resolve_changes
from safety_monitor.runner import check_expect, print_trace, run_timeline

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def unique_dir(p: Path) -> Path:
    if not p.exists():
        return p
    n = 2
    while (p.parent / f"{p.name}-{n}").exists():
        n += 1
    return p.parent / f"{p.name}-{n}"


def timeline_mode(pkg, keys, args, base) -> list[tuple]:
    results = []
    for key in keys:
        sc = pkg.scenario(key)
        if args.changes is not None:
            ids, label = resolve_changes(args.changes, pkg, sc)
            plan = [(label, ids, [])]
        else:
            vs = sc.variants() or {"기본 규칙": {"changes": []}}
            plan = [(n, v.get("changes", []), v.get("expect", [])) for n, v in vs.items() if args.variant in (None, n)]
            if not plan:
                raise PackageError(f"variant 가 없습니다: {args.variant} (있는 것: {', '.join(vs)})")
        print(f"\n━━ {pkg.root.name} / {sc.title}  (구역 {sc.zone} · 판정표 {sc.data.get('table', '-')})")
        for name, ids, expect in plan:
            run = run_timeline(pkg, sc, ids, name, base / f"{pkg.root.name}_{key}" / name.replace(" ", ""))
            if not args.quiet:
                print(f"\n■ {name}" + (f" — 개정안 {' '.join(ids)}" if ids else ""))
                print_trace(run, pkg)
            if expect:
                checks = check_expect(run, expect)
                n_ok = sum(ok for ok, _ in checks)
                print(f"\n  기대 결과 · {name}: {n_ok}/{len(checks)}")
                for ok, msg in checks:
                    print(f"    [{'통과' if ok else '실패'}] {msg}")
                results.append((pkg.root.name, key, name, n_ok, len(checks)))
    return results


def video_mode(pkg, args, base):
    from safety_monitor.video import run_video

    sc = pkg.scenario(args.scenario) if args.scenario else None
    at, cam_id, video = args.at, args.camera, args.video
    scene = None
    if args.scene:
        if not sc:
            raise PackageError("--scene 은 시나리오와 같이 준다")
        scene = next((s for s in sc.scenes() if s.get("name") == args.scene), None)
        if scene is None:
            raise PackageError(f"장면이 없습니다: {args.scene} (있는 것: {', '.join(s.get('name', '') for s in sc.scenes())})")
        at = at or scene.get("at")
        cam_id = cam_id or scene.get("camera")
        video = video or scene.get("video")
    if not video:
        raise PackageError("--video 또는 --scene 이 필요하다")
    cands = [Path(video)] + ([sc.dir / video] if sc else []) + [pkg.root / video, ROOT / video]
    vpath = next((c for c in cands if c.exists()), None)
    if vpath is None:
        raise PackageError(f"영상 파일이 없습니다: {video}")
    ids, label = resolve_changes(args.changes, pkg, sc)
    rules = pkg.rules(ids)
    rules["_label"] = label
    out = base / f"{pkg.root.name}_{vpath.stem}" / label.replace(" ", "")
    print(f"영상 {vpath.name} · 패키지 {pkg.root.name} · 규칙 {label}" + (f" · 시각 {at}" if at else " · 시나리오 신호 없음"))
    cam = pkg.scene_camera({**scene, "camera": cam_id}) if scene and cam_id == scene.get("camera") else pkg.camera(cam_id)
    res = run_video(pkg, rules, vpath, cam, out, scenario=sc, at=at, show=args.show, save=args.save,
                    stride=args.stride, flame=args.flame, realtime=not args.fast)
    print(res["stats"].report())
    log = res["log"]
    n_alert = sum(1 for e in log.rows if e["alerted"])
    print(f"\n■ 기록  이벤트 {len(log.rows)}건 (경보 {n_alert} · 무음 {len(log.rows) - n_alert}) · 클립 {len(res['clips'].written)}개")
    eng = res["engine"]
    for (z, t), ls in sorted(eng.levels.items()):
        if ls.history:
            print(f"  {z} · {t}: " + " → ".join(f"{ts:%H:%M:%S} {lv}({row}줄)" for ts, lv, row in ls.history))
    print(f"\n저장: {out}")


def main():
    ap = argparse.ArgumentParser(description="패키지를 받아 시스템을 돌린다")
    ap.add_argument("package", nargs="?")
    ap.add_argument("scenario", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--variant")
    ap.add_argument("--changes")
    ap.add_argument("--quiet", action="store_true", help="추적표 없이 기대 결과만")
    ap.add_argument("--scene")
    ap.add_argument("--video")
    ap.add_argument("--at")
    ap.add_argument("--camera")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--stride", type=int)
    ap.add_argument("--flame", choices=["color", "yolo", "off"])
    ap.add_argument("--fast", action="store_true", help="--show 일 때 영상 속도에 맞추지 않는다")
    args = ap.parse_args()
    if not args.all and not args.package:
        ap.error("패키지를 주거나 --all")

    base = unique_dir(OUTPUT_DIR / datetime.now().strftime("%Y%m%d-%H%M%S"))
    if args.video or args.scene:
        video_mode(load_package(args.package), args, base)
        return

    results = []
    if args.all and not args.package:
        pkgs = [load_package(p) for p in sorted(PACKAGES_DIR.iterdir()) if (p / "site.json").exists()] if PACKAGES_DIR.exists() else []
        if not pkgs:
            raise PackageError(f"{PACKAGES_DIR} 에 패키지가 없습니다")
        for pkg in pkgs:
            results += timeline_mode(pkg, pkg.scenario_keys(), args, base)
    else:
        pkg = load_package(args.package)
        results += timeline_mode(pkg, [args.scenario] if args.scenario else pkg.scenario_keys(), args, base)

    if results:
        print("\n━━ 요약")
        for pk, key, name, ok, n in results:
            print(f"  {'통과' if ok == n else '실패'}  {pk} / {key} / {name}  {ok}/{n}")
    print(f"\n저장: {base}")
    if any(r[3] != r[4] for r in results):
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except PackageError as e:
        print(f"[패키지 오류] {e}")
        sys.exit(2)
