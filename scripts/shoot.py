#!/usr/bin/env python3
"""
data/projects.json 의 라이브 URL을 실제로 열어 assets/shots/<id>.jpg 로 저장.

로컬:  pip install playwright && python3 -m playwright install chromium
       python3 scripts/shoot.py
CI  :  refresh.yml 이 호출

원칙
- 실패한 페이지는 기존 썸네일을 남겨두고 건너뛴다(빈 이미지로 덮어쓰지 않는다).
- 결과가 이전 파일과 바이트 단위로 같으면 쓰지 않아 무의미한 커밋을 막는다.
- **빈 화면 방어**: 캡처가 거의 단색이면(= 아직 안 그려졌거나 로그인 벽) 저장하지 않는다.
  포트폴리오에서 썸네일 품질은 곧 실력으로 읽히므로, 회색 판을 올리느니 이전 것을 유지한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "assets" / "shots"
VIEWPORT = {"width": 1440, "height": 900}
SETTLE_MS = 4200          # 폰트·영상·차트가 그려질 시간
NETWORK_IDLE_MS = 12_000


def variance(png_bytes: bytes) -> float:
    """캡처가 사실상 단색인지 판정. 표준편차가 낮으면 빈 화면."""
    try:
        from PIL import Image, ImageStat
        import io

        im = Image.open(io.BytesIO(png_bytes)).convert("L").resize((160, 100))
        return ImageStat.Stat(im).stddev[0]
    except Exception:
        return 999.0      # PIL 없으면 검사를 건너뛴다(막지 않는다)


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright 미설치: pip install playwright && python3 -m playwright install chromium",
              file=sys.stderr)
        return 1

    SHOTS.mkdir(parents=True, exist_ok=True)
    data = json.loads((ROOT / "data" / "projects.json").read_text(encoding="utf-8"))
    targets = [
        (p["id"], p.get("shot_url") or p["auto"]["live"], int(p.get("shot_wait") or 0))
        for p in data["projects"] if p["auto"].get("live")
    ]

    ok, changed, blank, failed = 0, 0, [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=2)
        page.set_default_timeout(30_000)
        for pid, url, extra_wait in targets:
            dest = SHOTS / f"{pid}.jpg"
            try:
                page.goto(url, wait_until="load", timeout=30_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_MS)
                except Exception:
                    pass                      # 영상 루프 등으로 idle 이 안 와도 계속 진행
                page.wait_for_timeout(max(SETTLE_MS, extra_wait))
                probe = page.screenshot(type="png")
                shot = page.screenshot(type="jpeg", quality=84)
            except Exception as e:
                failed.append((pid, str(e)[:80]))
                continue

            if variance(probe) < 7.0:
                blank.append(pid)             # 거의 단색 → 기존 파일 유지
                continue

            ok += 1
            if not dest.exists() or dest.read_bytes() != shot:
                dest.write_bytes(shot)
                changed += 1
        browser.close()

    print(f"촬영 성공 {ok}/{len(targets)} · 파일 갱신 {changed}")
    if blank:
        print(f"  빈 화면으로 판정해 건너뜀(기존 유지): {', '.join(blank)}", file=sys.stderr)
    for pid, err in failed:
        print(f"  실패: {pid} — {err}", file=sys.stderr)
    return 1 if ok == 0 and targets else 0


if __name__ == "__main__":
    raise SystemExit(main())
