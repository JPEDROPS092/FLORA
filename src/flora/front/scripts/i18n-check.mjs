// Extracts every translatable key (`| t` and t('...')) and verifies the EN dictionary.
// Usage: node scripts/i18n-check.mjs [--write-missing]
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const SRC = new URL('../src/app/', import.meta.url).pathname;
const walk = (d) => readdirSync(d).flatMap((n) => { const p = join(d, n); return statSync(p).isDirectory() ? walk(p) : [p]; });
const files = walk(SRC).filter((f) => f.endsWith('.ts') && !f.endsWith('.spec.ts') && !f.includes('/core/i18n/en') && !f.endsWith('/core/i18n/i18n.ts') && !f.endsWith('/core/i18n/t.pipe.ts'));

const keys = new Set();
const unesc = (s) => s.replace(/\\'/g, "'");
for (const f of files) {
  const s = readFileSync(f, 'utf8');
  for (const m of s.matchAll(/'((?:[^'\\\n]|\\.)*)'\s*\|\s*t\b/g)) keys.add(unesc(m[1]));
  for (const m of s.matchAll(/\bt\(\s*'((?:[^'\\\n]|\\.)*)'/g)) keys.add(unesc(m[1]));
}
const dict = new Set();
for (const f of walk(join(SRC, 'core/i18n/en'))) {
  const s = readFileSync(f, 'utf8');
  for (const m of s.matchAll(/^\s*'((?:[^'\\\n]|\\.)*)':/gm)) dict.add(unesc(m[1]));
}
const missing = [...keys].filter((k) => !dict.has(k));
const unused = [...dict].filter((k) => !keys.has(k));
console.log(`keys: ${keys.size}  dictionary: ${dict.size}  missing: ${missing.length}  unused: ${unused.length}`);
if (process.argv.includes('--list')) console.log(missing.map((k) => JSON.stringify(k)).join('\n'));
if (unused.length) console.log('unused:\n' + unused.map((k) => '  ' + JSON.stringify(k)).join('\n'));
process.exit(missing.length ? 1 : 0);
