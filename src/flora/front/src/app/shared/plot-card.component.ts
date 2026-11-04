import { Component, ElementRef, effect, inject, input, viewChild } from '@angular/core';

import { ChartResult, ThemeMode } from '../core/models/domain';
import { WorkspaceStore } from '../core/workspace/workspace.store';
import { PlotlyService } from '../core/plotly/plotly.service';
import { TPipe } from '../core/i18n/t.pipe';
import { t } from '../core/i18n/i18n';

@Component({
  selector: 'flora-plot',
  standalone: true,
  imports: [TPipe],
  template: `
    <div class="plot-frame">
      @if (result()?.status === 'ok') {
        <div #host class="plot-host"></div>
        <button type="button" class="svg-btn" (click)="exportSvg()" [attr.aria-label]="'Baixar o gráfico em SVG' | t">SVG</button>
      } @else {
        <p class="plot-state">{{ result()?.error || t('A figura ainda não foi pedida.') }}</p>
      }
    </div>
  `,
  styles: [
    `
      .plot-frame { min-height: 280px; position: relative; }
      .svg-btn { position: absolute; top: 0; right: 0; font: inherit; font-size: .72rem; border: 1px solid var(--flora-border); background: var(--flora-surface); color: var(--flora-muted); border-radius: 6px; padding: 1px 8px; cursor: pointer; opacity: .6; }
      .svg-btn:hover { opacity: 1; }
      .plot-host { width: 100%; height: 100%; min-height: 320px; }
      .plot-state { margin: 0; padding: 28px 8px; color: var(--flora-muted); font-size: 0.92rem; }
    `
  ]
})
export class PlotCardComponent {
  protected readonly t = t;
  readonly result = input<ChartResult | null>(null);
  readonly theme = input<ThemeMode | null>(null);
  private readonly store = inject(WorkspaceStore);
  readonly height = input(360);

  private readonly host = viewChild<ElementRef<HTMLElement>>('host');
  private readonly plotly = inject(PlotlyService);
  private renderedKey = '';

  exportSvg(): void {
    const element = this.host()?.nativeElement;
    if (element) void this.plotly.exportSvg(element);
  }

  constructor() {
    effect(() => {
      const element = this.host()?.nativeElement;
      const result = this.result();
      const theme: ThemeMode = this.theme() ?? (this.store.dark() ? 'dark' : 'light');
      const height = this.height();
      if (!element || result?.status !== 'ok' || !result.figure) {
        return;
      }
      const key = `${theme}:${height}:${result.figure.data.length}:${result.figure.data.map((trace) => String(trace['name'] ?? '')).join('|')}`;
      if (key === this.renderedKey) {
        return;
      }
      this.renderedKey = key;
      element.style.minHeight = `${height}px`;
      void this.plotly.render(element, result.figure, theme);
    });
  }
}
