# portfolio

이진희(Jinhee Lee) 개인 포트폴리오. **GitHub 공개 저장소에서 매일 자동으로 갱신된다.**

- 사이트: https://jinilee-hue.github.io/portfolio/
- 디자인 시안 비교: https://jinilee-hue.github.io/portfolio/variants/

## 어떻게 자동 갱신되는가

```
GitHub API ──► scripts/build_data.py ──► data/projects.json ──┐
                                                              ├──► index.html (fetch로 렌더)
배포된 페이지 ─► scripts/shoot.py ────► assets/shots/*.jpg ───┘
```

`.github/workflows/refresh.yml` 이 **매일 06:00 KST** 에 위 두 스크립트를 돌리고,
변경이 있을 때만 커밋한 뒤 Pages 에 배포한다. 수동 실행은 Actions 탭 → refresh → Run workflow.

새 프로젝트를 만들 때 해야 할 일은 **그 저장소에 GitHub Pages 를 켜는 것뿐**이다.
다음 갱신에서 목록·썸네일·스택·갱신일이 알아서 붙는다.

## 자동값 vs 손으로 쓴 값

| 파일 | 내용 | 누가 쓰나 |
|---|---|---|
| `data/projects.json` | 생성물. 직접 수정하지 말 것 | 스크립트 |
| `data/overrides.json` | 제목·설명·역할·태그·정렬 (한/영) | 사람 |

`overrides.json` 에 쓴 값이 자동 수집값을 덮어쓴다. 비워두면 저장소 설명과 README 첫 문단이 대신 쓰인다.
`summary` 가 비어 있는 프로젝트(Sound-Safari, phonics-wordmashup, poly-ai-agent, polyscoop)는
아직 설명을 안 쓴 것이니 채워 넣으면 사이트에 바로 반영된다.

### 저장소 루트에 index.html 이 없는 경우

`overrides.json` 의 `entry` 에 진입 파일명을 적는다. 예: LIO → `"entry": "lio-design-system.html"`.

## 디자인 시안 3종

| 시안 | 이름 | 성격 |
|---|---|---|
| A | Editorial Ink | 웜 페이퍼 + 세리프 표제, 에디토리얼 목록 |
| B | Spec Ledger | 다크 모노크롬 + 라임, 필터 가능한 원장 테이블 |
| C | **Screen Room** (현재 채택) | 근사 블랙 + 민트, 전면 스크린샷 스택 |

시안 교체는 `variants/<이름>.html` 을 루트 `index.html` 로 승격하면 된다
(경로를 `../data/` → `./data/`, `./shared.js` → `./assets/shared.js` 로 바꾸고 head 의 SEO/JSON-LD 블록을 옮긴다).

세 시안 모두 아래를 의도적으로 피했다 — 2026년 기준 'AI가 생성한 사이트' 판별 신호이기 때문:
인디고~퍼플 그래디언트, Inter 본문, 아이콘+제목+두 줄 3단 카드 그리드, 글래스모피즘, 4열 푸터.

한글 제목은 라틴 디스플레이 서체에 글리프가 없어 시스템 명조로 폴백되므로,
세 시안 모두 `:lang(ko)` 에서 Pretendard 굵기 대비로 전환한다. 언어 토글 시 자동 적용.

## 로컬에서 보기

```bash
python3 -m http.server 8891
# http://localhost:8891/           루트(채택안)
# http://localhost:8891/variants/  시안 비교
```

데이터만 다시 만들려면:

```bash
GH_TOKEN=$(gh auth token) python3 scripts/build_data.py
pip install playwright && python3 -m playwright install chromium
python3 scripts/shoot.py
```

## AI 가독성 레이어

리크루터가 ChatGPT·Perplexity 에 이름을 물어보는 경우를 대비해 다음을 둔다:
`llms.txt`, `schema.org` JSON-LD (Person / ItemList, 실제 프로젝트로 런타임 주입),
`sitemap.xml` (페이지별 실제 수정일), `robots.txt`.

## 남은 일

- [ ] 이메일·LinkedIn 을 `index.html` 푸터와 `llms.txt` 에 추가
- [ ] `assets/og.jpg` (1200×630) 만들기 — 링크 공유 시 첫인상
- [ ] 대표 프로젝트 2~3개에 케이스 스터디 페이지 (문제 → 역할 → AI 워크플로 → 기각안 → 결과)
- [ ] 배포 후 Lighthouse 로 LCP/INP/CLS 확인
