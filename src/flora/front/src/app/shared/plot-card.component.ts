import { Component, ElementRef, effect, inject, input, viewChild } from '@angular/core';

import { ChartResult, ThemeMode } from '../core/models/domain';
import { WorkspaceStore } from '../core/workspace/workspace.store';
import { PlotlyService } from '../core/plotly/plotly.service';

@Component({
  selector: 'flora-plot',
  standalone: true,
  template: `
    <div class="plot-frame">
      @if (result()?.status === 'ok') {
        <div #host class="plot-host"></div>
      } @else {
        <p class="plot-state">{{ result()?.error || 'A figura ainda não foi pedida.' }}</p>
      }
    </div>
  `,
  styles: [
    `
      .plot-frame { min-height: 280px; }
      .plot-host { width: 100%; height: 100%; min-height: 320px; }
      .plot-state { margin: 0; padding: 28px 8px; color: var(--flora-muted); font-size: 0.92rem; }
    `
  ]
})
export class PlotCardComponent {
  readonly result = input<ChartResult | null>(null);
  readonly theme = input<ThemeMode | null>(null);
  private readonly store = inject(WorkspaceStore);
  readonly height = input(360);

  private readonly host = viewChild<ElementRef<HTMLElement>>('host');
  private readonly plotly = inject(PlotlyService);
  private renderedKey = '';

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
