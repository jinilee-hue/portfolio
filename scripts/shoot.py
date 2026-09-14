#!/usr/bin/env python3
"""
data/projects.json 의 라이브 URL을 실제로 열어 assets/shots/<id>.jpg 로 저장.

로컬:  pip install playwright && python3 -m playwright install chromium
       python3 scripts/shoot.py
CI  :  refresh.yml 이 호출

- 실패한 페이지는 기존 썸네일을 남겨두고 건너뛴다(빈 이미지로 덮어쓰지 않는다).
- 결과가 이전 파일과 바이트 단위로 같으면 쓰지 않아 무의미한 커밋을 막는다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "assets" / "shots"
VIEWPORT = {"width": 1440, "height": 900}
SETTLE_MS = 2600


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright 미설치: pip install playwright && python3 -m playwright install chromium",
              file=sys.stderr)
        return 1

    SHOTS.mkdir(parents=True, exist_ok=True)
    data = json.loads((ROOT / "data" / "projects.json").read_text(encoding="utf-8"))
    targets = [(p["id"], p["auto"]["live"]) for p in data["projects"] if p["auto"].get("live")]

    ok, changed, failed = 0, 0, []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=2)
        page.set_default_timeout(30_000)
        for pid, url in targets:
            dest = SHOTS / f"{pid}.jpg"
            try:
                page.goto(url, wait_until="load", timeout=30_000)
                page.wait_for_timeout(SETTLE_MS)
                shot = page.screenshot(type="jpeg", quality=82)
            except Exception as e:
                failed.append((pid, str(e)[:80]))
                continue
            ok += 1
            if not dest.exists() or dest.read_bytes() != shot:
                dest.write_bytes(shot)
                changed += 1
        browser.close()

    print(f"촬영 성공 {ok}/{len(targets)} · 파일 갱신 {changed}")
    for pid, err in failed:
        print(f"  실패: {pid} — {err}", file=sys.stderr)
    # 일부 실패는 허용(사이트가 잠시 죽어도 워크플로를 깨뜨리지 않는다). 전부 실패면 에러.
    return 1 if ok == 0 and targets else 0


if __name__ == "__main__":
    raise SystemExit(main())
