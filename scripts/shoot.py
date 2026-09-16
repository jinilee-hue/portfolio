#!/usr/bin/env python3
"""
data/projects.json 의 촬영 대상 URL을 실제로 열어 assets/shots/ 에 저장한다.

기기별로 여러 컷을 찍는다:
    <id>.jpg          데스크톱 1440×900   (대표 · 목록 썸네일)
    <id>--tablet.jpg  태블릿  834×1112 (가로형은 tablet-land, 1112×834)
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
import os
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "assets" / "shots"

# 기본 기기 세트. overrides.json 의 shot_devices 로 프로젝트마다 바꿀 수 있다.
DEVICES = {
    "desktop": {"width": 1440, "height": 900, "mobile": False, "suffix": ""},
    "tablet": {"width": 834, "height": 1112, "mobile": True, "suffix": "--tablet"},
    # 가로 태블릿 — 슬라이드형·가로 고정 화면용. 파일명은 tablet 과 같아서
    # 사이트는 그대로 '태블릿'으로 읽고, 비율만 실제 이미지에서 따라간다.
    "tablet-land": {"width": 1112, "height": 834, "mobile": True, "suffix": "--tablet"},
    "mobile": {"width": 390, "height": 844, "mobile": True, "suffix": "--mobile"},
}

SETTLE_MS = 4200
NETWORK_IDLE_MS = 12_000
BLANK_STDDEV = 7.0


def url_with_path(base: str, path: str) -> str:
    """라이브 URL 뒤에 경로를 붙인다. 한글·공백 파일명도 깨지지 않게 인코딩한다."""
    if not base:
        return ""
    path = (path or "").strip()
    if not path:
        return base
    enc = "/".join(quote(seg) for seg in path.split("/") if seg)
    return base.rstrip("/") + "/" + enc


def with_query(url: str, query: str) -> str:
    q = (query or "").strip().lstrip("?")
    if not url or not q:
        return url
    sep = "&" if "?" in url else "?"
    return url + sep + q


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
            "url": with_query(url, p.get("shot_query") or ""),
            "wait": int(p.get("shot_wait") or 0),
            "devices": [d for d in wanted if d in DEVICES],
            # 프로토타입 뷰어처럼 셸이 화면을 감싸는 경우, 실제 화면 요소만 잘라낸다
            "selector": (p.get("shot_selector") or "").strip(),
            # 스크롤이 있는 페이지는 전체를 찍어 목업 안에서 흘려보낸다
            "full": bool(p.get("shot_full")),
            "click": (p.get("shot_click") or "").strip(),
            "eval": (p.get("shot_eval") or "").strip(),
            "dest": None,
        })
        live = p["auto"].get("live") or ""
        for sc in p.get("scenes") or []:
            su = with_query(
                url_with_path(live, sc.get("path") or ""),
                sc.get("query") or p.get("shot_query") or "",
            )
            if not su:
                continue
            jobs.append({
                "id": f"{p['id']}/{sc['id']}",
                "url": su,
                "wait": int(sc.get("wait") or p.get("shot_wait") or 0),
                "devices": [sc.get("device") or "desktop"],
                "selector": (sc.get("selector") or "").strip(),
                "full": bool(sc.get("full")),
                "click": (sc.get("click") or p.get("shot_click") or "").strip(),
                "eval": (sc.get("eval") or "").strip(),
                "dest": f"{p['id']}--{sc['id']}.jpg",
            })

    only = os.environ.get("ONLY", "").strip()
    if only:
        jobs = [j for j in jobs if j["id"] == only or j["id"].startswith(only + "/")]
    if os.environ.get("SCENES_ONLY"):
        jobs = [j for j in jobs if j.get("dest")]
    ok = changed = 0
    blank: list[str] = []
    failed: list[tuple[str, str]] = []
    total = sum(len(j["devices"]) for j in jobs)

    with sync_playwright() as pw:
        chrome = os.environ.get("PLAYWRIGHT_CHROMIUM") or os.environ.get("CHROME_PATH")
        browser = pw.chromium.launch(executable_path=chrome) if chrome else pw.chromium.launch()
        for job in jobs:
            for dev in job["devices"]:
                spec = DEVICES[dev]
                dest = SHOTS / (job["dest"] if job.get("dest") else f"{job['id']}{spec['suffix']}.jpg")
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
                    click = job.get("click") or ""
                    if click:
                        try:
                            page.click(click, timeout=8000)
                            page.wait_for_timeout(700)
                        except Exception:
                            pass
                    script = job.get("eval") or ""
                    if script:
                        try:
                            page.evaluate(script)
                            page.wait_for_timeout(500)
                        except Exception:
                            pass
                    page.wait_for_timeout(max(SETTLE_MS, job["wait"]))
                    target = page
                    if job["selector"]:
                        el = page.query_selector(job["selector"])
                        if el:
                            target = el          # 요소만 캡처 — 뷰어 셸과 여백이 빠진다
                    full = job["full"] and target is page
                    probe = target.screenshot(type="png", full_page=full)
                    shot = target.screenshot(type="jpeg", quality=84, full_page=full)
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
