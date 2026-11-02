import { Component, input } from '@angular/core';

import { Institution, TechItem } from './brand.data';

/** Icon chip for a library (brand icon or monogram) or an institution (monogram). */
@Component({
  selector: 'flora-tech-badge',
  standalone: true,
  template: `
    @if (item(); as t) {
      <a class="chip" [href]="t.url" target="_blank" rel="noopener noreferrer" [attr.aria-label]="t.name + ': ' + t.note">
        <span class="glyph">
          @if (t.icon) { <img [src]="'icons/' + t.icon" alt="" width="26" height="26" loading="lazy" /> }
          @else { <b>{{ t.mono }}</b> }
        </span>
        <span class="txt"><strong>{{ t.name }}</strong><small>{{ t.note }}</small></span>
      </a>
    }
    @if (inst(); as i) {
      <a class="chip" [href]="i.url" target="_blank" rel="noopener noreferrer" [attr.aria-label]="i.name + ', ' + i.org">
        <span class="glyph inst" [style.--c]="i.color">
          @if (i.logo) { <img [src]="i.logo" alt="" width="30" height="30" /> } @else { <b>{{ i.mono }}</b> }
        </span>
        <span class="txt"><strong>{{ i.name }}</strong><em>{{ i.org }}</em><small>{{ i.role }}</small></span>
      </a>
    }
  `,
  styles: [`
    .chip { display: flex; gap: 12px; align-items: flex-start; padding: 12px; text-decoration: none; color: inherit;
      border: 1px solid var(--flora-border); border-radius: 12px; background: var(--flora-surface); transition: transform .15s, border-color .15s; height: 100%; }
    .chip:hover { transform: translateY(-2px); border-color: var(--flora-primary); }
    .glyph { flex: none; width: 44px; height: 44px; border-radius: 10px; display: grid; place-items: center; background: #f1f5f3; border: 1px solid #dce5e1; }
    .glyph b { font-size: .8rem; letter-spacing: .03em; color: #155e53; }
    .glyph.inst { background: var(--c); border-color: transparent; }
    .glyph.inst b { color: #fff; font-size: .72rem; }
    .txt { display: grid; gap: 2px; min-width: 0; }
    .txt strong { font-size: .95rem; }
    .txt em { font-style: normal; font-size: .72rem; color: var(--flora-primary); font-weight: 650; letter-spacing: .03em; }
    .txt small { color: var(--flora-muted); font-size: .8rem; line-height: 1.4; }
  `]
})
export class TechBadgeComponent {
  readonly item = input<TechItem | null>(null);
  readonly inst = input<Institution | null>(null);
}
