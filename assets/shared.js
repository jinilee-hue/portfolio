/* 변체 공통 데이터 로더 — 세 방향 모두 같은 실제 데이터를 쓴다 */
const LANG_KEY = 'pf-lang';

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
  const res = await fetch('./data/projects.json');
  if (!res.ok) throw new Error('projects.json ' + res.status);
  return res.json();
}

export function pick(p) {
  const a = p.auto || {};
  return {
    id: p.id,
    title: t(p.title) || a.readme_title || p.id,
    kicker: t(p.kicker),
    summary: t(p.summary) || a.readme_summary || a.description || '',
    role: t(p.role),
    tags: p.tags || a.languages || [],
    live: a.live,
    repo: a.repo,
    shot: p.shot,
    pushed: (a.pushed_at || '').slice(0, 10),
    langs: a.languages || [],
    featured: !!p.featured,
  };
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
