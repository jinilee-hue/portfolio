#!/usr/bin/env python3
"""
data/projects.json 의 촬영 대상 URL을 실제로 열어 assets/shots/ 에 저장한다.

기기별로 여러 컷을 찍는다:
    <id>.jpg          데스크톱 1440×900   (대표 · 목록 썸네일)
    <id>--tablet.jpg  태블릿  834×1112
    <id>--mobile.jpg  모바일  390×844

기기 프레임(맥북 목업 등)은 씌우지 않는다. 실제 뷰포트로 찍은 화면을 실물 비율대로
나란히 두는 편이, 스톡 목업보다 반응형을 정직하게 증명한다.

로컬:  pip install playwright pillow && python3 -m playwright install chromium
       python3 scripts/shoot.py
CI  :  refresh.yml 이 호출

원칙
- 실패한 화면은 기존 파일을 남겨두고 건너뛴다(빈 이미지로 덮지 않는다).
- 결과가 이전 파일과 바이트 단위로 같으면 쓰지 않아 무의미한 커밋을 막는다.
- 캡처가 거의 단색이면(= 아직 안 그려졌거나 로그인 벽) 저장하지 않는다.
  포트폴리오에서 썸네일 품질은 곧 실력으로 읽히므로 회색 판을 올리느니 이전 것을 유지한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "assets" / "shots"

# 기본 기기 세트. overrides.json 의 shot_devices 로 프로젝트마다 바꿀 수 있다.
DEVICES = {
    "desktop": {"width": 1440, "height": 900, "mobile": False, "suffix": ""},
    "tablet": {"width": 834, "height": 1112, "mobile": True, "suffix": "--tablet"},
    "mobile": {"width": 390, "height": 844, "mobile": True, "suffix": "--mobile"},
}

SETTLE_MS = 4200
NETWORK_IDLE_MS = 12_000
BLANK_STDDEV = 7.0


def variance(png_bytes: bytes) -> float:
    """캡처가 사실상 단색인지 판정. 표준편차가 낮으면 빈 화면."""
    try:
        import io

        from PIL import Image, ImageStat

        im = Image.open(io.BytesIO(png_bytes)).convert("L").resize((160, 100))
        return ImageStat.Stat(im).stddev[0]
    except Exception:
        return 999.0  # PIL 없으면 검사를 건너뛴다(막지 않는다)


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright 미설치: pip install playwright && python3 -m playwright install chromium",
              file=sys.stderr)
        return 1

    SHOTS.mkdir(parents=True, exist_ok=True)
    data = json.loads((ROOT / "data" / "projects.json").read_text(encoding="utf-8"))

    jobs = []
    for p in data["projects"]:
        url = p.get("shot_url") or p["auto"].get("live")
        if not url:
            continue
        wanted = p.get("shot_devices") or list(DEVICES)
        jobs.append({
            "id": p["id"],
            "url": url,
            "wait": int(p.get("shot_wait") or 0),
            "devices": [d for d in wanted if d in DEVICES],
            # 프로토타입 뷰어처럼 셸이 화면을 감싸는 경우, 실제 화면 요소만 잘라낸다
            "selector": (p.get("shot_selector") or "").strip(),
        })

    ok = changed = 0
    blank: list[str] = []
    failed: list[tuple[str, str]] = []
    total = sum(len(j["devices"]) for j in jobs)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for job in jobs:
            for dev in job["devices"]:
                spec = DEVICES[dev]
                dest = SHOTS / f"{job['id']}{spec['suffix']}.jpg"
                ctx = browser.new_context(
                    viewport={"width": spec["width"], "height": spec["height"]},
                    device_scale_factor=2,
                    is_mobile=spec["mobile"],
                    has_touch=spec["mobile"],
                )
                page = ctx.new_page()
                page.set_default_timeout(30_000)
                try:
                    page.goto(job["url"], wait_until="load", timeout=30_000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_MS)
                    except Exception:
                        pass  # 영상 루프 등으로 idle 이 안 와도 계속 진행
                    page.wait_for_timeout(max(SETTLE_MS, job["wait"]))
                    target = page
                    if job["selector"]:
                        el = page.query_selector(job["selector"])
                        if el:
                            target = el          # 요소만 캡처 — 뷰어 셸과 여백이 빠진다
                    probe = target.screenshot(type="png")
                    shot = target.screenshot(type="jpeg", quality=84)
                except Exception as e:
                    failed.append((f"{job['id']}/{dev}", str(e)[:70]))
                    ctx.close()
                    continue
                ctx.close()

                if variance(probe) < BLANK_STDDEV:
                    blank.append(f"{job['id']}/{dev}")
                    continue

                ok += 1
                if not dest.exists() or dest.read_bytes() != shot:
                    dest.write_bytes(shot)
                    changed += 1
        browser.close()

    print(f"촬영 성공 {ok}/{total} · 파일 갱신 {changed}")
    if blank:
        print(f"  빈 화면으로 판정해 건너뜀(기존 유지): {', '.join(blank)}", file=sys.stderr)
    for name, err in failed:
        print(f"  실패: {name} — {err}", file=sys.stderr)
    return 1 if ok == 0 and total else 0


if __name__ == "__main__":
    raise SystemExit(main())
