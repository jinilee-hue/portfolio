#!/usr/bin/env python3
"""흐름 컷이 서로 같은 화면을 찍지 않았는지 검사한다.

슬라이드 뷰어는 쪽 번호를 넘겨도 실제 화면이 안 바뀌는 구간이 있어
(예: Further Practice 가 24~40 내내 같은 화면) 눈으로 보기 전에는
중복을 알아채기 어렵다. 축소 이미지의 평균 픽셀 차이로 판정한다.
"""
import itertools
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Pillow 없음 — 중복 검사 건너뜀")
    sys.exit(0)

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "assets" / "shots"
THRESHOLD = 30.0   # 평균 채널 차이. 이보다 작으면 사실상 같은 화면


def signature(path: Path):
    return list(Image.open(path).convert("RGB").resize((64, 40)).getdata())


def main() -> int:
    groups: dict[str, list[Path]] = {}
    for f in sorted(SHOTS.glob("*--f[0-9]*.jpg")):
        groups.setdefault(f.name.split("--")[0], []).append(f)

    bad = []
    for pid, files in groups.items():
        sigs = {f: signature(f) for f in files}
        for a, b in itertools.combinations(files, 2):
            pa, pb = sigs[a], sigs[b]
            diff = sum(abs(x[0] - y[0]) + abs(x[1] - y[1]) + abs(x[2] - y[2])
                       for x, y in zip(pa, pb)) / len(pa)
            if diff < THRESHOLD:
                bad.append(f"{a.name} ≈ {b.name} (차이 {diff:.1f})")

    if bad:
        print("흐름 컷 중복:")
        for line in bad:
            print("  ✗", line)
        return 1
    print(f"흐름 컷 중복 없음 ({sum(len(v) for v in groups.values())}장)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
