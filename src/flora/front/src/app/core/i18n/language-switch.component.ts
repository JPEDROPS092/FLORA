import { Component } from '@angular/core';

import { LANG, LANGS, Lang, setLang } from './i18n';
import { TPipe } from './t.pipe';

/** PT | EN segmented switch. Changing language reloads the app. */
@Component({
  selector: 'flora-language-switch',
  standalone: true,
  imports: [TPipe],
  template: `
    <div class="lang" role="group" [attr.aria-label]="'Idioma' | t">
      @for (l of langs; track l.code) {
        <button type="button" [class.on]="l.code === current" [attr.aria-pressed]="l.code === current"
                [attr.lang]="l.code" [title]="l.native" (click)="pick(l.code)">{{ l.label }}</button>
      }
    </div>
  `,
  styles: [`
    .lang { display: inline-flex; border: 1px solid var(--flora-border); border-radius: 8px; overflow: hidden; }
    button { border: 0; background: transparent; padding: 5px 9px; font-size: .75rem; font-weight: 650; letter-spacing: .04em; cursor: pointer; color: var(--flora-muted); }
    button.on { background: var(--flora-primary-soft); color: var(--flora-primary); }
    button:not(.on):hover { color: var(--flora-text); }
  `]
})
export class LanguageSwitchComponent {
  protected readonly langs = LANGS;
  protected readonly current: Lang = LANG;
  pick(l: Lang): void { setLang(l); }
}
