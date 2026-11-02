import { describe, expect, it } from 'vitest';

import { EN } from './en';
import { t } from './i18n';

const placeholders = (s: string): string[] => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe('i18n', () => {
  it('has a non-empty English value for every key', () => {
    for (const [key, value] of Object.entries(EN)) {
      expect(value.trim().length, key).toBeGreaterThan(0);
    }
  });

  it('keeps {placeholders} identical between Portuguese keys and English values', () => {
    for (const [key, value] of Object.entries(EN)) {
      expect(placeholders(value), key).toEqual(placeholders(key));
    }
  });

  it('interpolates params and leaves unknown placeholders untouched', () => {
    expect(t('{n} amostras', { n: 80 })).toMatch(/80/);
    expect(t('{n} amostras', {})).toContain('{n}');
  });
});
