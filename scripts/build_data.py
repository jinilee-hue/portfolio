#!/usr/bin/env python3
"""
GitHub 공개 저장소 → data/projects.json 생성.

- 사실(레포 이름, 설명, 언어, 최종 푸시일, Pages URL, README 첫 문단)은 GitHub API에서 가져온다.
- 사람이 쓴 내용(한/영 제목, 역할, AI 워크플로, 성과)은 data/overrides.json 에서 병합한다.
- 자동 수집한 값과 손으로 쓴 값을 섞지 않는다: 자동은 `auto`, 수동은 최상위 키로 덮어쓴다.

실행:  GH_TOKEN=... python3 scripts/build_data.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OWNER = os.environ.get("PORTFOLIO_OWNER", "jinilee-hue")
API = "https://api.github.com"

# 포트폴리오에 싣지 않을 저장소
EXCLUDE = {"portfolio"}


def token() -> str | None:
    for var in ("GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        out = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=15
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def api(path: str, tok: str | None):
    req = urllib.request.Request(f"{API}{path}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "portfolio-build")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def readme_summary(owner: str, repo: str, tok: str | None) -> tuple[str, str]:
    """README에서 (제목, 첫 서술 문단)을 뽑는다. 없으면 빈 문자열."""
    data = api(f"/repos/{owner}/{repo}/readme", tok)
    if not data:
        return "", ""
    import base64

    try:
        text = base64.b64decode(data.get("content", "")).decode("utf-8", "replace")
    except Exception:
        return "", ""
    title = ""
    para: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not title and line.startswith("# "):
            title = line[2:].strip()
            continue
        if not title:
            continue
        if not line:
            if para:
                break
            continue
        if line.startswith(("#", "|", "```", "-", "*", ">", "<!--")):
            if para:
                break
            continue
        para.append(line)
    body = " ".join(para)
    body = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", body)  # 링크 텍스트만 남김
    body = re.sub(r"[*`_]", "", body)
    return title, body[:400].strip()


def commit_span(owner: str, repo: str, tok: str | None) -> dict:
    """첫 커밋 ~ 마지막 커밋 날짜와 총 커밋 수. 작업 기간 표기에 쓴다."""
    req = urllib.request.Request(f"{API}/repos/{owner}/{repo}/commits?per_page=1")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "portfolio-build")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            first_page = json.loads(r.read().decode())
            link = r.headers.get("Link", "")
    except Exception:
        return {}
    if not first_page:
        return {}
    last_date = first_page[0]["commit"]["author"]["date"]

    # Link 헤더의 rel="last" 페이지 번호가 곧 총 커밋 수(per_page=1 이므로)
    total = 1
    m = re.search(r'[?&]page=(\d+)>;\s*rel="last"', link)
    if m:
        total = int(m.group(1))
    oldest = api(f"/repos/{owner}/{repo}/commits?per_page=1&page={total}", tok)
    first_date = oldest[0]["commit"]["author"]["date"] if oldest else last_date
    return {"first": first_date[:10], "last": last_date[:10], "commits": total}


def dependencies(owner: str, repo: str, tok: str | None) -> list[str]:
    """package.json 의 dependencies 키만 (버전 제외). 없으면 빈 리스트."""
    import base64

    data = api(f"/repos/{owner}/{repo}/contents/package.json", tok)
    if not data:
        return []
    try:
        pkg = json.loads(base64.b64decode(data.get("content", "")).decode("utf-8", "replace"))
    except Exception:
        return []
    deps = list((pkg.get("dependencies") or {}).keys())
    devs = list((pkg.get("devDependencies") or {}).keys())
    keep = [d for d in deps + devs if not d.startswith("@types/")]
    return sorted(keep)[:24]


def main() -> int:
    tok = token()
    if not tok:
        print("경고: 토큰 없음 — 미인증 레이트리밋으로 진행", file=sys.stderr)

    repos = []
    page = 1
    while True:
        chunk = api(f"/users/{OWNER}/repos?per_page=100&page={page}&sort=pushed", tok)
        if not chunk:
            break
        repos.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1

    projects = []
    for r in repos:
        name = r["name"]
        if r.get("fork") or r.get("private") or r.get("archived") or name in EXCLUDE:
            continue
        pages = api(f"/repos/{OWNER}/{name}/pages", tok)
        live = (pages or {}).get("html_url") or r.get("homepage") or ""
        langs = api(f"/repos/{OWNER}/{name}/languages", tok) or {}
        rm_title, rm_body = readme_summary(OWNER, name, tok)
        commits = api(f"/repos/{OWNER}/{name}/commits?per_page=1", tok)
        span = commit_span(OWNER, name, tok)
        deps = dependencies(OWNER, name, tok)
        projects.append(
            {
                "id": name,
                "auto": {
                    "repo": r["html_url"],
                    "live": live,
                    "description": r.get("description") or "",
                    "readme_title": rm_title,
                    "readme_summary": rm_body,
                    "languages": [k for k, _ in sorted(
                        langs.items(), key=lambda kv: kv[1], reverse=True)][:5],
                    "topics": r.get("topics") or [],
                    "pushed_at": r.get("pushed_at"),
                    "created_at": r.get("created_at"),
                    "size_kb": r.get("size"),
                    "has_pages": bool(live),
                    "span": span,
                    "deps": deps,
                    "last_commit": (commits[0]["commit"]["message"].splitlines()[0][:120]
                                    if commits else ""),
                },
            }
        )

    ov_path = ROOT / "data" / "overrides.json"
    overrides = json.loads(ov_path.read_text(encoding="utf-8")) if ov_path.exists() else {}

    merged = []
    for p in projects:
        o = overrides.get(p["id"], {})
        p.update({k: v for k, v in o.items() if k != "auto"})
        # 저장소 루트에 index.html 이 없는 경우 진입 파일을 붙인다 (예: LIO)
        entry = (p.get("entry") or "").strip()
        if entry and p["auto"]["live"]:
            p["auto"]["live"] = p["auto"]["live"].rstrip("/") + "/" + entry.lstrip("/")
        p["shot"] = f"assets/shots/{p['id']}.jpg"
        merged.append(p)

    # 정렬: overrides 의 order 우선(작을수록 앞), 없으면 최근 푸시순
    merged.sort(key=lambda p: (p.get("order", 999), p["auto"]["pushed_at"] or ""), reverse=False)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "owner": OWNER,
        "count": len(merged),
        "projects": merged,
    }
    dest = ROOT / "data" / "projects.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{dest} — 프로젝트 {len(merged)}개, 라이브 {sum(1 for m in merged if m['auto']['has_pages'])}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
