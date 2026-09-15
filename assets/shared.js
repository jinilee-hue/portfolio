/* 변체 공통 데이터 로더 — 세 방향 모두 같은 실제 데이터를 쓴다 */
const LANG_KEY = 'pf-lang';

/* 사이트 루트를 이 모듈의 위치에서 계산한다.
   /assets/shared.js 든 /variants/shared.js 든 루트 한 단계 아래라 결과가 같다.
   상대경로를 HTML 에 적어두면 시안을 루트로 옮길 때마다 이미지가 깨진다. */
export const SITE_ROOT = new URL('../', import.meta.url);
export const asset = (p) => new URL(String(p).replace(/^\.?\//, ''), SITE_ROOT).href;

export function lang() {
  return localStorage.getItem(LANG_KEY) || 'ko';
}
export function setLang(v) {
  localStorage.setItem(LANG_KEY, v);
  document.documentElement.lang = v;
  render();
}
export function t(obj, fallback = '') {
  if (!obj) return fallback;
  if (typeof obj === 'string') return obj;
  return obj[lang()] || obj.ko || obj.en || fallback;
}

export async function loadProjects() {
  const res = await fetch(asset('data/projects.json'));
  if (!res.ok) throw new Error('projects.json ' + res.status);
  return res.json();
}

export function pick(p) {
  const a = p.auto || {};
  const span = a.span || {};
  return {
    id: p.id,
    title: t(p.title) || a.readme_title || p.id,
    kicker: t(p.kicker),
    summary: t(p.summary) || a.readme_summary || a.description || '',
    role: t(p.role),
    tags: p.tags || a.languages || [],
    live: a.live,
    repo: a.repo,
    shot: asset(p.shot),
    // 기기별 컷. 파일이 없을 수 있으므로 렌더 쪽에서 onerror 로 제거한다.
    shots: (p.shot_devices || ['desktop']).map(k => ({
      device: k,
      src: asset((p.shots || {})[k] || p.shot),
      long: !!p.shot_long,   // 전체 페이지 캡처 → 목업 안에서 스크롤
    })),
    scenes: (p.scenes || []).map(s => ({
      id: s.id,
      src: asset(s.src || `assets/shots/${p.id}--${s.id}.jpg`),
      label: t(s.label),
      note: t(s.note),
      device: s.device || 'desktop',
    })),
    // 기기별 '이 화면에서' 설명. {label, note} 또는 {ko,en} 문장만 와도 된다.
    shotNotes: Object.fromEntries(Object.entries(p.shot_notes || {}).map(([k, v]) => {
      if (!v) return [k, { label: '', note: '' }];
      if (typeof v === 'string') return [k, { label: '', note: v }];
      if (v.note || v.label) return [k, { label: t(v.label), note: t(v.note) }];
      return [k, { label: '', note: t(v) }];
    })),
    pushed: (a.pushed_at || '').slice(0, 10),
    langs: a.languages || [],
    featured: !!p.featured,
    // 케이스 스터디 (overrides.json 에서 사람이 쓴 값)
    intent: t(p.intent),
    concept: t(p.concept),
    flow: p.flow || [],
    stack: p.stack || [],
    decisions: p.decisions || [],
    // 작업 기간 — 수동 표기가 있으면 우선, 없으면 커밋 이력에서 산출
    period: t(p.period) || periodLabel(span),
    commits: span.commits || 0,
    deps: a.deps || [],
    langBytes: a.lang_bytes || {},
    contribution: p.contribution || null,   // 관여도 0~100 개별 (사람이 쓴 값)
    tools: p.tools || [],                    // 실제 사용한 AI 툴
    devices: p.shot_devices || [],           // 대응 기기 (반응형 표기용)
    also: a.also || [],   // 한 프로젝트로 합친 다른 저장소들
    first: (a.span || {}).first || '',
    last: (a.span || {}).last || '',
    hasCase: !!(p.intent || p.concept || (p.flow || []).length || (p.decisions || []).length),
  };
}

/** 첫 커밋~마지막 커밋을 '2026.06 – 08 · 2개월' 형태로. */
export function periodLabel(span, l = lang()) {
  if (!span || !span.first) return '';
  const [fy, fm] = span.first.split('-');
  const [ty, tm] = span.last.split('-');
  const months = (Number(ty) - Number(fy)) * 12 + (Number(tm) - Number(fm)) + 1;
  const dur = l === 'ko'
    ? (months <= 1 ? '1개월 미만' : `약 ${months}개월`)
    : (months <= 1 ? 'under a month' : `~${months} months`);
  const range = fy === ty
    ? (fm === tm ? `${fy}.${fm}` : `${fy}.${fm}–${tm}`)
    : `${fy}.${fm}–${ty}.${tm}`;
  return `${range} · ${dur}`;
}

export function fmtDate(iso, l = lang()) {
  if (!iso) return '';
  const d = new Date(iso);
  return l === 'ko'
    ? `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}`
    : d.toLocaleDateString('en-US', { year: 'numeric', month: 'short' });
}

let render = () => {};
export function onRender(fn) {
  render = fn;
}
