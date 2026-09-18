#!/usr/bin/env python3
"""콜아웃 핀이 실제로 무엇을 가리키는지 확인한다.

설명 상세의 점선은 스크린샷 위 % 좌표(`at`)에서 출발해 문구로 이어진다. 좌표가
조금만 어긋나도 '이 문구가 저것을 가리킨다'는 말이 틀린 말이 되는데, 이미지를
눈으로 보는 방식으로는 그것을 놓친다. 그래서 촬영과 같은 조건으로 페이지를 다시
열고, 각 핀 좌표에서 `elementFromPoint` 로 실제 요소를 읽어 온다.

출력은 핀마다 한 줄:
    프로젝트/도판  n. <문구>  →  <그 좌표에 실제로 있는 것>

판정은 사람이 한다. 이 스크립트는 '무엇이 있는가'만 사실대로 가져온다.

사용:
    python3 scripts/verify_pins.py                 # 전체
    python3 scripts/verify_pins.py AI-Studio       # 프로젝트 하나
종료 코드: 0 정상 / 1 촬영 재현 실패가 있음
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent

DEVICES = {
    "desktop": {"width": 1440, "height": 900, "mobile": False},
    "tablet": {"width": 834, "height": 1112, "mobile": True},
    "tablet-land": {"width": 1112, "height": 834, "mobile": True},
    "mobile": {"width": 390, "height": 844, "mobile": True},
}

# 좌표가 가리키는 요소를 사람 말로 옮긴다. 텍스트가 없으면 역할·라벨·클래스를 쓴다.
PROBE = r"""
([x, y]) => {
  const el = document.elementFromPoint(x, y);
  if (!el) return { hit: null };
  const name = e => {
    if (!e) return '';
    const aria = e.getAttribute?.('aria-label') || e.getAttribute?.('title') || '';
    const txt = (e.innerText || e.textContent || '').replace(/\s+/g, ' ').trim();
    const tag = e.tagName.toLowerCase();
    const cls = (e.getAttribute?.('class') || '').trim().split(/\s+/).filter(Boolean).slice(0, 6).join('.');
    return [tag + (cls ? '.' + cls : ''), aria && `[${aria}]`, txt && `"${txt.slice(0, 60)}"`]
      .filter(Boolean).join(' ');
  };
  // 가장 가까운 '의미 있는' 조상(버튼·링크·행·카드)도 같이 돌려준다.
  const own = name(el);
  const near = el.closest('button, a, [role="button"], th, td, tr, li, label, .card, [class*="card"], [class*="btn"], [class*="row"]');
  return { hit: own, near: near && near !== el ? name(near) : '' };
}
"""


def url_with_path(base: str, path: str) -> str:
    path = (path or "").strip()
    if not base or not path:
        return base
    enc = "/".join(quote(seg) for seg in path.split("/") if seg)
    return base.rstrip("/") + "/" + enc


def with_query(url: str, query: str) -> str:
    q = (query or "").strip().lstrip("?")
    if not url or not q:
        return url
    return url + ("&" if "?" in url else "?") + q


def targets(only: str):
    """검사할 도판 목록. (키, url, device, wait, eval, selector, full, features)"""
    data = json.loads((ROOT / "data" / "projects.json").read_text(encoding="utf-8"))
    out = []
    for p in data["projects"]:
        if only and p["id"] != only:
            continue
        live = p["auto"].get("live") or ""
        base = p.get("shot_url") or live
        if not base:
            continue
        devs = p.get("shot_devices") or ["desktop"]
        prim = devs[0]
        notes = (p.get("shot_notes") or {}).get(prim) or {}
        if notes.get("features"):
            out.append({
                "key": f"{p['id']} [{prim}]",
                "url": with_query(base, p.get("shot_query") or ""),
                "device": prim,
                "wait": int(p.get("shot_wait") or 0),
                "eval": ((p.get("shot_evals") or {}).get(prim)
                         or (p.get("shot_evals") or {}).get("tablet" if prim == "tablet-land" else prim)
                         or p.get("shot_eval") or ""),
                "selector": (p.get("shot_selector") or "").strip(),
                "full": bool(p.get("shot_full")),
                "click": (p.get("shot_click") or "").strip(),
                "features": notes["features"],
            })
        for sc in p.get("scenes") or []:
            if sc.get("flow") or not sc.get("features"):
                continue
            out.append({
                "key": f"{p['id']} / {sc['id']}",
                "url": with_query(url_with_path(live, sc.get("path") or ""),
                                  sc.get("query") or p.get("shot_query") or ""),
                "device": sc.get("device") or "desktop",
                "wait": int(sc.get("wait") or p.get("shot_wait") or 0),
                "eval": (sc.get("eval") or "").strip(),
                "selector": (sc.get("selector") or "").strip(),
                "full": bool(sc.get("full")),
                "click": (sc.get("click") or p.get("shot_click") or "").strip(),
                "features": sc["features"],
            })
    return out


def main() -> int:
    from playwright.sync_api import sync_playwright

    only = sys.argv[1] if len(sys.argv) > 1 else ""
    jobs = targets(only)
    if not jobs:
        print("대상 없음", file=sys.stderr)
        return 1

    failed = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for job in jobs:
            spec = DEVICES[job["device"]]
            ctx = browser.new_context(
                viewport={"width": spec["width"], "height": spec["height"]},
                device_scale_factor=1,
                is_mobile=spec["mobile"],
                has_touch=spec["mobile"],
            )
            page = ctx.new_page()
            page.set_default_timeout(30_000)
            print(f"\n■ {job['key']}")
            try:
                page.goto(job["url"], wait_until="load", timeout=30_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=12_000)
                except Exception:
                    pass
                if job.get("click"):
                    try:
                        page.click(job["click"], timeout=8000)
                        page.wait_for_timeout(700)
                    except Exception:
                        pass
                if job["eval"]:
                    try:
                        page.evaluate(job["eval"])
                    except Exception as e:
                        print(f"   (eval 실패: {str(e)[:60]})")
                page.wait_for_timeout(max(4200, job["wait"]))

                # 스크린샷이 덮은 영역 = 핀 좌표의 기준 박스
                if job["selector"]:
                    box = page.eval_on_selector(job["selector"], "e => { const r = e.getBoundingClientRect();"
                                                " return {x:r.x+scrollX, y:r.y+scrollY, w:r.width, h:r.height}; }")
                elif job["full"]:
                    box = page.evaluate("() => ({x:0, y:0, w:document.documentElement.scrollWidth,"
                                        " h:document.documentElement.scrollHeight})")
                else:
                    box = page.evaluate("() => ({x:scrollX, y:scrollY, w:innerWidth, h:innerHeight})")
            except Exception as e:
                print(f"   재현 실패 — {str(e)[:70]}")
                failed += 1
                ctx.close()
                continue

            for i, f in enumerate(job["features"], 1):
                at = f.get("at")
                label = (f.get("ko") or f.get("text") or "")[:44]
                if not at:
                    print(f"   {i}. {label}  →  (핀 없음 · 나열형)")
                    continue
                ax = box["x"] + box["w"] * at[0] / 100
                ay = box["y"] + box["h"] * at[1] / 100
                try:
                    page.evaluate("([x, y]) => scrollTo(0, Math.max(0, y - innerHeight / 2))", [ax, ay])
                    page.wait_for_timeout(200)
                    vx, vy = page.evaluate("([x, y]) => [x - scrollX, y - scrollY]", [ax, ay])
                    hit = page.evaluate(PROBE, [vx, vy])
                except Exception as e:
                    print(f"   {i}. {label}  →  (조회 실패 {str(e)[:40]})")
                    continue
                what = hit.get("hit") or "(빈 곳)"
                near = hit.get("near")
                print(f"   {i}. {label}")
                print(f"      @{at} → {what}" + (f"   ⤷ {near}" if near else ""))
            ctx.close()
        browser.close()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
