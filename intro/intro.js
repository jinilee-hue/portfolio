/* 첫 화면 쇼릴 — 사이트를 열면 히어로 위에서 15초 쇼릴(intro/reel.html)을 음악과 함께 틀고,
   마지막 박자에 벤다이어그램 원 네 개와 한 줄 문장을 실제 히어로의 같은 자리로 날려 보낸 뒤
   그대로 실제 히어로로 바꿔 끼우고 멈춘다.

   - 켜짐 여부는 <head> 의 인라인 스크립트가 정한다(html.intro-on). 첫 페인트 전에 히어로를 숨겨야
     사진과 표제가 한 번 번쩍였다가 사라지는 일이 없다.
   - 소리 자동재생이 막히면(대부분의 첫 방문) 재생 버튼을 보여 준다. 쇼릴은 컷이 음악 박자에
     맞춰져 있어서 소리 없이 틀면 절반만 보여 주는 셈이다.
   - 스크롤·Esc·SKIP 은 바로 건너뛴다. 방문자를 15초 붙잡아 두지 않는다. */
(() => {
  const html = document.documentElement;
  if (!html.classList.contains('intro-on')) return;

  const FLIP0 = 11.84, SLAM = 12.36;          // reel.html 과 같은 값 — 날아가기 시작 / 착지
  const qs = new URLSearchParams(location.search);
  const TEST = qs.has('introtest');           // 검수용: 시계·소리 없이 __intro.seek(t) 로만 그린다
  const lang = localStorage.getItem('pf-lang') === 'en' ? 'en' : 'ko';

  let win = null, running = false, done = false, t0 = 0, raf = 0;

  try { history.scrollRestoration = 'manual'; } catch (e) {}
  scrollTo(0, 0);
  /* 해시(#AI-Studio)가 있으면 사이트 본문 스크립트가 그 작업으로 scrollIntoView 한다.
     html{overflow:hidden} 으로도 프로그램 스크롤은 막히지 않아 쇼릴 뒤 페이지가 중간에 가 있게 된다.
     쇼릴이 도는 동안은 맨 위에 고정하고, 해당 작업은 아래에 펼쳐진 채로 둔다. */
  const pin = () => { if (!done && (scrollX || scrollY)) scrollTo(0, 0); };
  addEventListener('scroll', pin, { passive: true });

  const ov = document.createElement('div');
  ov.id = 'intro';
  ov.innerHTML =
    `<iframe src="intro/reel.html?site=1&lang=${lang}" title="Showreel" tabindex="-1" aria-hidden="true"></iframe>` +
    `<button type="button" class="igate" hidden><span class="it">Showreel 2026</span><span class="ring" aria-hidden="true"></span>` +
    `<span class="ib">Play with sound</span><small>0:15</small></button>` +
    `<button type="button" class="iskip">Skip intro</button>`;
  document.body.appendChild(ov);
  const frame = ov.querySelector('iframe'), gate = ov.querySelector('.igate'), skipBtn = ov.querySelector('.iskip');

  const audio = new Audio('intro/reel.mp3');
  audio.preload = 'auto';

  /* ---- 착지 목표: 실제 히어로의 벤 원 네 개 · 리드 첫 줄 (뷰포트 px) ---- */
  function targets() {
    const vcs = [...document.querySelectorAll('.open .venn .vc')];
    const p = document.querySelector('#lede > p');
    if (vcs.length !== 4 || !p || !p.firstChild) return null;
    const r = document.createRange(); r.selectNodeContents(p);
    const tr = r.getBoundingClientRect();
    const ps = getComputedStyle(p), fs = parseFloat(ps.fontSize);
    const b = vcs[0].querySelector('b'), bs = b && getComputedStyle(b);
    return {
      vc: vcs.map(v => { const q = v.getBoundingClientRect(); return { x: q.left + q.width / 2, y: q.top + q.height / 2, d: q.width }; }),
      vcBg: getComputedStyle(vcs[0]).backgroundColor,
      lab: bs ? { fs: parseFloat(bs.fontSize), ls: (parseFloat(bs.letterSpacing) || 0) / parseFloat(bs.fontSize) } : null,
      text: { l: tr.left, cy: (tr.top + tr.bottom) / 2, fs, fw: parseFloat(ps.fontWeight) || 500,
              ls: (parseFloat(ps.letterSpacing) || 0) / fs, color: ps.color },
    };
  }
  const aim = () => { const T = targets(); if (T && win && win.__target) win.__target(T); };

  function draw(t) {
    if (!win || !win.__seek) return;
    if (t >= FLIP0 - 0.5) aim();
    // 실제 히어로 사진을 쇼릴 바탕이 걷히는 만큼 올린다 (reel.html 의 dis 와 같은 곡선)
    const u = Math.min(1, Math.max(0, (t - 11.95) / (SLAM - 11.95)));
    html.style.setProperty('--intro-photo', (-(Math.cos(Math.PI * u) - 1) / 2).toFixed(4));
    skipBtn.style.opacity = t > FLIP0 ? Math.max(0, 1 - (t - FLIP0) / 0.25).toFixed(3) : '';
    win.__seek(Math.min(t, SLAM - 0.001));
  }

  /* ---- 착지 ---- */
  function land(how) {
    if (done) return;
    done = true; running = false; cancelAnimationFrame(raf);
    off();
    try { sessionStorage.setItem('pf-intro', '1'); } catch (e) {}
    if (how === 'fail') how = 'skip';
    html.classList.add('intro-land');
    if (how === 'skip') html.classList.add('intro-skip');
    html.classList.remove('intro-on');
    html.style.removeProperty('--intro-photo');
    if (how === 'skip') {
      ov.classList.add('out');
      setTimeout(() => ov.remove(), 450);
      if (!audio.paused) fadeOut(0.4);
    } else {
      ov.remove();            // 날아온 원·문장이 실제와 같은 자리에 있다 — 그대로 바꿔 끼운다
    }
    // 등장 애니메이션이 끝나면 클래스를 걷는다(끝 상태 = 평상시 스타일이라 화면 변화 없음)
    setTimeout(() => html.classList.remove('intro-land', 'intro-skip'), 2600);
    audio.addEventListener('ended', () => audio.removeAttribute('src'), { once: true });
  }
  function fadeOut(sec) {
    const v0 = audio.volume, s = performance.now();
    const step = now => { const u = Math.min(1, (now - s) / (sec * 1000)); audio.volume = v0 * (1 - u);
      if (u < 1) requestAnimationFrame(step); else audio.pause(); };
    requestAnimationFrame(step);
  }

  /* ---- 시계: 소리가 나면 오디오 시간에 맞춘다 ---- */
  function tick(now) {
    if (!running) return;
    let t = (now - t0) / 1000;
    if (!audio.paused && audio.readyState >= 2) {
      const d = audio.currentTime - t;
      if (Math.abs(d) > 0.08) { t0 -= d * 1000; t = audio.currentTime; }
    }
    if (t >= SLAM) { draw(SLAM); land('slam'); return; }
    draw(t);
    raf = requestAnimationFrame(tick);
  }
  function run() { running = true; t0 = performance.now(); raf = requestAnimationFrame(tick); }

  async function playWithSound() {
    audio.currentTime = 0; audio.muted = false; audio.volume = 1;
    try { await audio.play(); return true; } catch (e) { return false; }
  }
  async function start() {
    if (await playWithSound()) { run(); return; }
    // 자동재생이 막혔다 — 첫 화면에서 한 번 눌러 달라고 한다
    gate.hidden = false;
    gate.focus({ preventScroll: true });
  }
  gate.addEventListener('click', async () => {
    gate.hidden = true;
    if (!(await playWithSound())) audio.pause();   // 소리 파일이 없거나 깨졌으면 그림만이라도
    run();
  });

  /* ---- 건너뛰기 ---- */
  const skip = () => land('skip');
  const onKey = e => {
    if (e.key === 'Escape' || ['PageDown', 'PageUp', 'End', 'Home', 'ArrowDown', 'ArrowUp'].includes(e.key) ||
        (e.key === ' ' && e.target === document.body)) skip();
  };
  function off() {
    removeEventListener('wheel', skip); removeEventListener('touchmove', skip); removeEventListener('keydown', onKey);
    removeEventListener('scroll', pin);
  }
  skipBtn.addEventListener('click', skip);
  addEventListener('wheel', skip, { passive: true });
  addEventListener('touchmove', skip, { passive: true });
  addEventListener('keydown', onKey);

  /* ---- 준비: 쇼릴 문서 · 히어로 내용(리드·벤)이 그려질 때까지 ---- */
  const t_boot = performance.now();
  (function wait() {
    if (done) return;
    try { win = frame.contentWindow; } catch (e) { win = null; }
    const ready = win && win.__ready === true && document.querySelector('#lede .venn .vc');
    if (ready) {
      ov.classList.add('ready');
      draw(0);
      if (TEST) { window.__intro = { seek: t => (t >= SLAM ? land('slam') : draw(t)), aim, targets }; return; }
      start();
      return;
    }
    if (performance.now() - t_boot > 9000) { land('fail'); return; }   // 너무 느리면 쇼릴 없이 히어로로
    setTimeout(wait, 60);
  })();
})();
