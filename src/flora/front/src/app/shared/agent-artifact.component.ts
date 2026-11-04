import { Component, computed, inject, input } from '@angular/core';
import { Router } from '@angular/router';
import { ButtonModule } from 'primeng/button';

import { toSampleMap } from '../core/data/http/mappers';
import { OperatorArtifact } from '../core/llm/llm.models';
import { ChartResult } from '../core/models/domain';
import { PlotCardComponent } from './plot-card.component';
import { SampleMapComponent } from './sample-map.component';

/** One chart, table, map or shortcut produced by an operator tool, sized for the copilot drawer. */
@Component({
  selector: 'flora-agent-artifact',
  standalone: true,
  imports: [ButtonModule, PlotCardComponent, SampleMapComponent],
  template: `
    @switch (artifact().type) {
      @case ('plot') {
        <figure class="art"><figcaption>{{ title() }}</figcaption><flora-plot [result]="chart()" [height]="height()" /></figure>
      }
      @case ('table') {
        <figure class="art">
          <figcaption>{{ title() }}</figcaption>
          <div class="scroll">
            <table>
              <thead><tr>@for (c of columns(); track $index) { <th>{{ c }}</th> }</tr></thead>
              <tbody>@for (row of rows(); track $index) { <tr>@for (cell of row; track $index) { <td>{{ cell }}</td> }</tr> }</tbody>
            </table>
          </div>
        </figure>
      }
      @case ('map') {
        <figure class="art"><figcaption>{{ title() }}</figcaption><flora-sample-map [map]="map()" [height]="height()" /></figure>
      }
      @case ('navigate') {
        <p-button size="small" icon="pi pi-external-link" [label]="title()" [outlined]="true" (onClick)="go()" />
      }
    }
  `,
  styles: `
    .art { margin: 8px 0; border: 1px solid var(--flora-border); border-radius: var(--radius); padding: 8px; background: var(--flora-surface); }
    figcaption { font-size: .8rem; font-weight: 600; margin-bottom: 4px; }
    .scroll { overflow: auto; max-height: 240px; }
    table { border-collapse: collapse; font-size: .74rem; min-width: 100%; }
    th, td { border-bottom: 1px solid var(--flora-border); padding: 3px 6px; text-align: left; white-space: nowrap; }
  `
})
export class AgentArtifactComponent {
  private readonly router = inject(Router);
  readonly artifact = input.required<OperatorArtifact>();
  readonly wide = input(false);
  readonly height = computed(() => (this.wide() ? 420 : 280));

  readonly title = computed(() => {
    const a = this.artifact();
    return a.type === 'navigate' ? a.label : a.title;
  });

  readonly chart = computed<ChartResult>(() => {
    const a = this.artifact();
    if (a.type !== 'plot' || !a.figure.data.length) return { status: 'empty', error: '—' };
    // the backend sizes some figures for a full page; in the drawer let Plotly fit the container
    const { height: _h, width: _w, ...layout } = a.figure.layout as Record<string, unknown>;
    return { status: 'ok', figure: { data: a.figure.data, layout: { ...layout, autosize: true, margin: { t: 28, r: 8, b: 44, l: 48 } } } };
  });

  readonly columns = computed(() => (this.artifact().type === 'table' ? (this.artifact() as Extract<OperatorArtifact, { type: 'table' }>).columns : []));
  readonly rows = computed(() => (this.artifact().type === 'table' ? (this.artifact() as Extract<OperatorArtifact, { type: 'table' }>).rows : []));
  readonly map = computed(() => toSampleMap(this.artifact().type === 'map' ? (this.artifact() as Extract<OperatorArtifact, { type: 'map' }>).map : {}));

  go(): void {
    const a = this.artifact();
    if (a.type === 'navigate') void this.router.navigate([a.path], { queryParams: a.query });
  }
}
