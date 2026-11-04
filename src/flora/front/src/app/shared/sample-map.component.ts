import { Component, computed, input } from '@angular/core';

import { ChartResult, SampleMap } from '../core/models/domain';
import { TPipe } from '../core/i18n/t.pipe';
import { t } from '../core/i18n/i18n';
import { PlotCardComponent } from './plot-card.component';

const PALETTE = ['#155E53', '#D9822B', '#3B7DD8', '#B0436A', '#6B8E23', '#7A5BC0', '#2A9D8F', '#C8553D', '#5C6B73', '#A68A00', '#0E7C86', '#8E5572'];

/** World map of sample locations, one colour per group. Plotly `scattergeo`: no tiles, no API key. */
@Component({
  selector: 'flora-sample-map',
  standalone: true,
  imports: [TPipe, PlotCardComponent],
  template: `
    @if (map(); as m) {
      @if (m.available) {
        <p class="muted">
          {{ m.mapped }} {{ 'de' | t }} {{ m.total }} {{ 'amostras com coordenadas' | t }}@if (m.skipped) { · {{ m.skipped }} {{ 'sem coordenadas válidas' | t }} }
          @if (m.groupColumn) { · {{ 'cores:' | t }} {{ m.groupColumn }} }
        </p>
        <flora-plot [result]="chart()" [height]="height()" />
      } @else {
        <p class="muted">{{ message() }}</p>
      }
    }
  `,
  styles: `.muted { color: var(--flora-muted); font-size: .84rem; margin: 0 0 6px; }`
})
export class SampleMapComponent {
  readonly map = input<SampleMap | null>(null);
  readonly height = input(380);

  readonly message = computed(() => {
    switch (this.map()?.reason) {
      case 'not_downloaded':
        return t('Baixe o dataset para ver o mapa das amostras.');
      case 'no_coordinates':
        return t('Este dataset não traz latitude e longitude, então não há mapa.');
      default:
        return t('As coordenadas deste dataset estão vazias ou inválidas.');
    }
  });

  readonly chart = computed<ChartResult>(() => {
    const m = this.map();
    if (!m?.available) return { status: 'empty', error: this.message() };
    const names = m.groups.map((g) => g.name);
    const data = names.map((name, index) => {
      const pts = m.points.filter((p) => p.group === name);
      return {
        type: 'scattergeo',
        mode: 'markers',
        name,
        lat: pts.map((p) => p.lat),
        lon: pts.map((p) => p.lon),
        text: pts.map((p) => `${p.ids.join(', ')}${p.n > p.ids.length ? ` +${p.n - p.ids.length}` : ''}<br>${p.n} ${t('amostra(s)')}<br>${p.lat}, ${p.lon}`),
        hoverinfo: 'text+name',
        marker: { size: pts.map((p) => 7 + Math.min(Math.sqrt(p.n) * 3, 16)), color: PALETTE[index % PALETTE.length], opacity: 0.85, line: { width: 1, color: '#ffffff' } }
      } as Record<string, unknown>;
    });
    return {
      status: 'ok',
      figure: {
        data,
        layout: {
          margin: { t: 8, r: 8, b: 8, l: 8 },
          showlegend: names.length > 1,
          legend: { orientation: 'h', y: -0.05 },
          geo: {
            projection: { type: 'natural earth' },
            fitbounds: 'locations',
            showland: true,
            landcolor: '#eef2ee',
            showocean: true,
            oceancolor: '#dfeaf2',
            showrivers: true,
            rivercolor: '#9cc3e0',
            showcountries: true,
            countrycolor: '#b8c4bd',
            showframe: false
          }
        }
      }
    };
  });
}
