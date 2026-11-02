import { EN } from './en';

export type Lang = 'pt' | 'en';
export const LANG_KEY = 'flora.lang';
export const LANGS: readonly { code: Lang; label: string; native: string }[] = [
  { code: 'pt', label: 'PT', native: 'Português' },
  { code: 'en', label: 'EN', native: 'English' }
];

function detect(): Lang {
  try {
    const stored = localStorage.getItem(LANG_KEY);
    if (stored === 'pt' || stored === 'en') return stored;
  } catch { /* storage unavailable */ }
  const nav = typeof navigator !== 'undefined' ? navigator.language ?? '' : '';
  return nav.toLowerCase().startsWith('pt') ? 'pt' : 'en';
}

/**
 * Active language. Fixed for the lifetime of the page: switching reloads the app,
 * so every number/date format, chart, mock record and agent reply is consistent.
 */
export const LANG: Lang = detect();
export const LOCALE = LANG === 'pt' ? 'pt-BR' : 'en-US';

const missing = new Set<string>();

/**
 * Translate a Portuguese source string. `{name}` placeholders are filled from `params`.
 * Portuguese is the source language, so `pt` returns the key untouched.
 */
export function t(source: string, params?: Record<string, string | number>): string {
  let out = source;
  if (LANG === 'en') {
    const hit = EN[source];
    if (hit === undefined) {
      if (!missing.has(source)) {
        missing.add(source);
        console.warn(`[i18n] missing EN translation: ${JSON.stringify(source)}`);
      }
    } else {
      out = hit;
    }
  }
  return params ? out.replace(/\{(\w+)\}/g, (m, k: string) => (k in params ? String(params[k]) : m)) : out;
}

export function setLang(lang: Lang): void {
  if (lang === LANG) return;
  try {
    localStorage.setItem(LANG_KEY, lang);
    sessionStorage.removeItem('flora.agent.session');
  } catch { /* ignore */ }
  location.reload();
}
