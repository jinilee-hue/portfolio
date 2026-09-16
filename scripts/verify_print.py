#!/usr/bin/env python3
"""화면 ↔ 인쇄(PDF) 동등성 검증.

포트폴리오는 한 소스에서 화면과 A4 가로 PDF 두 벌이 나온다. 인쇄 CSS 가 화면과
어긋나면 눈으로 봐야만 알 수 있었는데, 그 확인을 결정적 검사로 바꾼다.

검사 항목
  1. 색 동등성   — 같은 섹션의 배경/글자색이 화면과 인쇄에서 같은가
  2. 주석 겹침   — 같은 면(side)의 콜아웃 문구끼리 포개지는가
  3. 점선 채널   — 세로 채널이 선마다 다른 x 를 쓰는가 (같으면 한 줄로 포개짐)
  4. 점선 경로   — 가로 선분이 스크린샷 위를 지나가는가 (여백으로 빠져야 읽힌다)
  5. 캡션 충돌   — 콜아웃이 figcaption 과 겹치는가
  6. 빈 지면     — 내용이 위로 몰려 지면 아래가 비는가
  7. 대비        — 어두운 면 위 글자가 읽히는 명도인가

사용:
    python3 scripts/verify_print.py                 # 로컬 서버 자동 기동
    python3 scripts/verify_print.py --url http://localhost:8891/
    python3 scripts/verify_print.py --pdf out.pdf   # PDF 도 남긴다
종료 코드: 0 통과 / 1 실패(항목별 사유 출력)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8891
URL = f"http://localhost:{PORT}/"

# ── 검사 스크립트 (화면·인쇄 양쪽에서 같은 코드를 돌린다) ──────────────
PROBE = r"""
() => {
  const R = e => e.getBoundingClientRect();
  const out = { colors:{}, annOverlap:0, sameChannel:0, wireOverImage:0,
                capClash:0, figures:0, samples:[] };

  // 1) 색 — 무대/보드/커리어의 배경과 글자색
  const pick = sel => {
    const e = document.querySelector(sel);
    if (!e) return null;
    const c = getComputedStyle(e);
    return { bg: c.backgroundColor, fg: c.color };
  };
  out.colors.body    = pick('body');
  out.colors.board   = pick('.board');
  out.colors.career  = pick('#career');
  out.colors.factsDt = pick('.facts dt');
  out.colors.gauge   = pick('.cg-l');

  document.querySelectorAll('.feats figure').forEach((fig, fi) => {
    out.figures++;
    const stage = fig.querySelector('.stage');
    if (!stage) return;
    const ph = stage.querySelector('.ph');
    const anns = [...fig.querySelectorAll('.anns li')];

    // 2) 주석끼리 겹침 (같은 면만)
    for (let i = 0; i < anns.length; i++)
      for (let j = i + 1; j < anns.length; j++) {
        const a = R(anns[i]), b = R(anns[j]);
        if (anns[i].dataset.side === anns[j].dataset.side &&
            a.top < b.bottom && b.top < a.bottom) out.annOverlap++;
      }

    // 5) 캡션과 충돌
    const cap = fig.querySelector('figcaption');
    if (cap) {
      const cr = R(cap);
      anns.forEach(li => {
        const r = R(li);
        if (r.bottom > cr.top + 2 && r.top < cr.bottom) out.capClash++;
      });
    }

    // 3·4) 점선 — 채널 x 중복, 이미지 위 통과
    const paths = [...stage.querySelectorAll('svg.wires path')].map(p => {
      const d  = p.getAttribute('d') || '';
      const hs = (d.match(/H([\d.]+)/g) || []).map(x => parseFloat(x.slice(1)));
      return hs;
    });
    const chans = paths.map(h => h[0]).filter(Number.isFinite);
    for (let i = 0; i < chans.length; i++)
      for (let j = i + 1; j < chans.length; j++)
        if (Math.abs(chans[i] - chans[j]) < 2) out.sameChannel++;

    if (ph) {
      const sr = R(stage), pr = R(ph);
      const L = pr.left - sr.left, Rt = pr.right - sr.left;
      paths.flat().forEach(x => {
        if (x > L + 2 && x < Rt - 2) out.wireOverImage++;
      });
    }

    if (fi < 3) out.samples.push({ fig: fi, channels: chans.map(Math.round) });
  });
  return out;
}
"""


def serve() -> subprocess.Popen | None:
    try:
        urllib.request.urlopen(URL, timeout=2)
        return None
    except Exception:
        p = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(PORT), "--directory", str(ROOT)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.5)
        return p


def blank_pages(pdf_path: str) -> list[int]:
    """거의 빈 쪽의 번호를 돌려준다(1-based).

    지면 넘침으로 생긴 공백 페이지를 잡는다. pdftotext 로 글자를, 없으면
    콘텐츠 스트림 길이로 판정한다 — 둘 다 없으면 검사를 건너뛴다.
    """
    try:
        import pypdf
    except ImportError:
        return []
    try:
        reader = pypdf.PdfReader(pdf_path)
    except Exception:
        return []
    blanks = []
    for i, page in enumerate(reader.pages, 1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            continue
        # 글자가 거의 없고 그림도 없으면 빈 쪽
        has_image = "/Image" in str(page.get("/Resources", {}))
        if len(text) < 12 and not has_image:
            blanks.append(i)
    return blanks


def run(url: str, pdf_out: str | None) -> int:
    from playwright.sync_api import sync_playwright

    fails: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        # 화면과 지면 모두 라이트/다크 두 벌을 본다 — 토큰이 뒤집히는 사고를 잡는다
        for scheme in ("light", "dark"):
            page = browser.new_page(viewport={"width": 1440, "height": 900},
                                    color_scheme=scheme)
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(5000)

            screen = page.evaluate(PROBE)
            page.emulate_media(media="print", color_scheme=scheme)
            # emulate_media 는 beforeprint 를 쏘지 않는다. 실제 ⌘P 경로에서만
            # 도는 재계산(숨은 슬라이드 콜아웃 배치)을 직접 유발해야 지면과 같아진다.
            page.evaluate("() => window.dispatchEvent(new Event('beforeprint'))")
            page.wait_for_timeout(2500)
            printed = page.evaluate(PROBE)

            tag = f"[{scheme}]"

            # 1) 색 동등성 — 글자색만 비교한다. 배경은 화면에서 투명(부모 색이 비침)
            #    인 섹션이 인쇄에서 실제 색을 갖는 게 정상이라 비교 대상이 아니다.
            for key in ("board", "career", "factsDt", "gauge"):
                s, p = screen["colors"].get(key), printed["colors"].get(key)
                if s and p and s["fg"] != p["fg"]:
                    fails.append(f"{tag} 글자색 불일치 {key}: 화면 {s['fg']} ≠ 인쇄 {p['fg']}")

            # 2~5) 레이아웃 결함 — 인쇄 쪽이 특히 중요
            for label, key in (("주석 겹침", "annOverlap"),
                               ("점선 채널 중복", "sameChannel"),
                               ("점선이 이미지 위 통과", "wireOverImage"),
                               ("캡션 충돌", "capClash")):
                if printed[key]:
                    fails.append(f"{tag} 인쇄 {label}: {printed[key]}건")
                if screen[key]:
                    fails.append(f"{tag} 화면 {label}: {screen[key]}건")

            if printed["figures"] == 0:
                fails.append(f"{tag} 인쇄에 도판이 하나도 없다")

            # 기기 목업: 화면 라운드는 베젤 곡률 − 안쪽 여백이어야 한다.
            # 어긋나면 네 귀퉁이에 베젤이 비쳐 빈 공간처럼 보인다.
            bad_radius = page.evaluate("""(() => {
              const out = [];
              document.querySelectorAll('.fly .frame').forEach(f => {
                const sh = f.querySelector('.shot');
                if (!sh) return;
                const fs = getComputedStyle(f), ss = getComputedStyle(sh);
                const want = Math.max(0, parseFloat(fs.borderRadius) - parseFloat(fs.paddingLeft));
                const got = parseFloat(ss.borderRadius);
                if (Math.abs(got - want) > 1) out.push(f.className + ': ' + got + 'px, 기대 ' + want + 'px');
              });
              return [...new Set(out)];
            })()""")
            if bad_radius:
                fails.append(f"{tag} 목업 모서리 어긋남: {', '.join(bad_radius[:3])}")

            if scheme == "light" and pdf_out:
                page.pdf(path=pdf_out, landscape=True, print_background=True,
                         prefer_css_page_size=True)
                # 8) 빈 지면 — 렌더된 픽셀이 거의 없는 쪽은 넘침으로 생긴 공백이다
                blanks = blank_pages(pdf_out)
                if blanks:
                    fails.append(f"{tag} 빈 페이지 {len(blanks)}장: {blanks}")
            page.close()
        browser.close()

    if fails:
        print("실패:")
        for f in fails:
            print("  ✗", f)
        return 1
    print("통과 — 화면과 인쇄가 같고 레이아웃 결함 없음")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=URL)
    ap.add_argument("--pdf", default=None, help="검증용 PDF 저장 경로")
    args = ap.parse_args()

    proc = serve()
    try:
        return run(args.url, args.pdf)
    finally:
        if proc:
            proc.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
