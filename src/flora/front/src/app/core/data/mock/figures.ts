import { PlotFigure } from '../../models/domain';
import { GROUP_COLOR, MockSample, relationMatrix } from './mock-study';
import { t } from '../../i18n/i18n';

const AXIS = {
  mirror: false,
  showline: false,
  zeroline: false
};

function layout(partial: Record<string, unknown>): Record<string, unknown> {
  return {
    margin: { t: 28, r: 16, b: 48, l: 56 },
    showlegend: true,
    legend: { orientation: 'h', y: -0.18 },
    ...partial
  };
}

export function alphaBox(samples: MockSample[], metric: 'shannon' | 'simpson' | 'observed' | 'chao1'): PlotFigure {
  const groups = uniqueGroups(samples);
  return {
    data: groups.map((group) => ({
      type: 'box',
      name: group,
      y: samples.filter((sample) => sample.group === group).map((sample) => sample[metric]),
      boxpoints: 'all',
      jitter: 0.35,
      pointpos: -1.4,
      marker: { color: GROUP_COLOR[group] ?? '#155E53', size: 5 },
      line: { color: GROUP_COLOR[group] ?? '#155E53' },
      fillcolor: 'rgba(21, 94, 83, 0.08)'
    })),
    layout: layout({
      yaxis: { title: { text: metricLabel(metric) }, ...AXIS },
      xaxis: { ...AXIS }
    })
  };
}

export function pcoaScatter(samples: MockSample[]): PlotFigure {
  const groups = uniqueGroups(samples);
  return {
    data: groups.map((group) => {
      const rows = samples.filter((sample) => sample.group === group);
      return {
        type: 'scatter',
        mode: 'markers',
        name: group,
        x: rows.map((sample) => sample.pc1),
        y: rows.map((sample) => sample.pc2),
        text: rows.map((sample) => sample.id),
        hovertemplate: '%{text}<br>PC1 %{x:.3f}<br>PC2 %{y:.3f}<extra>' + group + '</extra>',
        marker: { color: GROUP_COLOR[group] ?? '#155E53', size: 9, line: { color: '#ffffff', width: 1 } }
      };
    }),
    layout: layout({
      xaxis: { title: { text: 'PC1 (28,4%)' }, ...AXIS },
      yaxis: { title: { text: 'PC2 (14,1%)' }, ...AXIS, scaleanchor: 'x' }
    })
  };
}

export function betaHeatmap(samples: MockSample[]): PlotFigure {
  const picked = pickRepresentatives(samples, 8);
  const ids = picked.map((sample) => sample.id);
  const z = picked.map((row) =>
    picked.map((column) => {
      if (row.id === column.id) {
        return 0;
      }
      const distance = Math.hypot(row.pc1 - column.pc1, row.pc2 - column.pc2);
      return Math.round(Math.min(0.92, distance / 0.85) * 100) / 100;
    })
  );
  return {
    data: [
      {
        type: 'heatmap',
        x: ids,
        y: ids,
        z,
        colorscale: [
          [0, '#F4FBF8'],
          [0.45, '#7FB8AE'],
          [1, '#155E53']
        ],
        colorbar: { title: { text: 'Bray–Curtis', side: 'right' }, thickness: 12 },
        hovertemplate: '%{y} × %{x}<br>%{z:.2f}<extra></extra>'
      }
    ],
    layout: layout({
      margin: { t: 24, r: 24, b: 88, l: 88 },
      showlegend: false,
      xaxis: { tickangle: -40, ...AXIS },
      yaxis: { autorange: 'reversed', ...AXIS }
    })
  };
}

export function taxonomyBar(
  rows: { name: string; values: Record<string, number> }[],
  groups: string[],
  rank: string
): PlotFigure {
  return {
    data: rows.map((row) => ({
      type: 'bar',
      name: row.name,
      x: groups,
      y: groups.map((group) => row.values[group] ?? 0),
      hovertemplate: '%{x}<br>' + row.name + ': %{y:.1f}%<extra></extra>'
    })),
    layout: layout({
      barmode: 'stack',
      yaxis: { title: { text: t('Abundância relativa (%) · {rank}', { rank }) }, ...AXIS },
      xaxis: { ...AXIS },
      legend: { orientation: 'v', x: 1.02, y: 1 },
      margin: { t: 24, r: 140, b: 48, l: 56 }
    })
  };
}

export function relationHeatmap(topN: number): PlotFigure {
  const { labels, matrix } = relationMatrix(topN);
  return {
    data: [
      {
        type: 'heatmap',
        x: labels,
        y: labels,
        z: matrix,
        zmin: -1,
        zmax: 1,
        colorscale: [
          [0, '#9F2D2D'],
          [0.5, '#F8FAF9'],
          [1, '#155E53']
        ],
        colorbar: { title: { text: 'Spearman', side: 'right' }, thickness: 12 }
      }
    ],
    layout: layout({
      margin: { t: 24, r: 24, b: 100, l: 120 },
      showlegend: false,
      xaxis: { tickangle: -35, ...AXIS },
      yaxis: { autorange: 'reversed', ...AXIS }
    })
  };
}

export function readHistogram(reads: number[]): PlotFigure {
  const bins = [
    { label: '<1 mil', test: (value: number) => value < 1000 },
    { label: '1–5 mil', test: (value: number) => value >= 1000 && value < 5000 },
    { label: '5–10 mil', test: (value: number) => value >= 5000 && value < 10000 },
    { label: '10–20 mil', test: (value: number) => value >= 10000 && value < 20000 },
    { label: '20–40 mil', test: (value: number) => value >= 20000 && value < 40000 },
    { label: '≥40 mil', test: (value: number) => value >= 40000 }
  ];
  return {
    data: [
      {
        type: 'bar',
        name: t('Amostras'),
        x: bins.map((bin) => bin.label),
        y: bins.map((bin) => reads.filter((value) => bin.test(value)).length),
        marker: { color: '#155E53' },
        hovertemplate: t('%{x}<br>%{y} amostras<extra></extra>')
      }
    ],
    layout: layout({
      showlegend: false,
      yaxis: { title: { text: t('Amostras') }, ...AXIS },
      xaxis: { title: { text: t('Reads por amostra') }, ...AXIS },
      shapes: [
        {
          type: 'line',
          xref: 'paper',
          x0: 0,
          x1: 1,
          y0: 0,
          y1: 0,
          line: { width: 0 }
        }
      ]
    })
  };
}

export function confusionHeatmap(labels: string[], matrix: number[][], dark = false): PlotFigure {
  return {
    data: [
      {
        type: 'heatmap',
        x: labels,
        y: labels,
        z: matrix,
        text: matrix.map((row) => row.map((value) => String(value))),
        texttemplate: '%{text}',
        colorscale: dark
          ? [
              [0, '#15211D'],
              [1, '#7DCFC2']
            ]
          : [
              [0, '#F4FBF8'],
              [1, '#155E53']
            ],
        showscale: false,
        hovertemplate: 'Real %{y}<br>Predito %{x}<br>%{z}<extra></extra>'
      }
    ],
    layout: layout({
      showlegend: false,
      xaxis: { title: { text: 'Predito' }, ...AXIS },
      yaxis: { title: { text: 'Real' }, autorange: 'reversed', ...AXIS },
      margin: { t: 16, r: 16, b: 56, l: 110 }
    })
  };
}

export function rocFigure(dark = false): PlotFigure {
  const diagonal = [0, 0.25, 0.5, 0.75, 1];
  const rhizosphere = [0, 0.18, 0.55, 0.86, 1];
  const bulk = [0, 0.28, 0.7, 0.92, 1];
  const endosphere = [0, 0.42, 0.8, 0.96, 1];
  const color = dark ? '#D5E4DE' : '#8FA099';
  return {
    data: [
      { type: 'scatter', mode: 'lines', name: t('Referência'), x: diagonal, y: diagonal, line: { color, dash: 'dot' } },
      { type: 'scatter', mode: 'lines', name: 'Rhizosphere · AUC 0,91', x: diagonal, y: rhizosphere, line: { color: '#155E53', width: 2 } },
      { type: 'scatter', mode: 'lines', name: 'Bulk soil · AUC 0,94', x: diagonal, y: bulk, line: { color: '#C47B2B', width: 2 } },
      { type: 'scatter', mode: 'lines', name: 'Endosphere · AUC 0,96', x: diagonal, y: endosphere, line: { color: '#3D6B8C', width: 2 } }
    ],
    layout: layout({
      xaxis: { title: { text: t('Taxa de falso positivo') }, range: [0, 1], ...AXIS },
      yaxis: { title: { text: t('Taxa de verdadeiro positivo') }, range: [0, 1], ...AXIS },
      legend: { orientation: 'h', y: -0.22 }
    })
  };
}

export function importanceBars(features: { feature: string; value: number }[], kind: 'shap' | 'impurity'): PlotFigure {
  const ordered = [...features].sort((a, b) => Math.abs(a.value) - Math.abs(b.value));
  return {
    data: [
      {
        type: 'bar',
        orientation: 'h',
        x: ordered.map((item) => item.value),
        y: ordered.map((item) => item.feature),
        marker: {
          color: ordered.map((item) => (item.value >= 0 ? '#155E53' : '#9F2D2D'))
        },
        hovertemplate: '%{y}<br>%{x:.3f}<extra></extra>'
      }
    ],
    layout: layout({
      showlegend: false,
      xaxis: { title: { text: kind === 'shap' ? t('SHAP médio') : t('Importância') }, ...AXIS },
      yaxis: { ...AXIS, automargin: true },
      margin: { t: 12, r: 16, b: 48, l: 120 }
    })
  };
}

export function metricLabel(metric: string): string {
  switch (metric) {
    case 'shannon':
      return 'Shannon';
    case 'simpson':
      return 'Simpson (1 − D)';
    case 'observed':
      return 'ASVs observados';
    case 'chao1':
      return 'Chao1';
    default:
      return metric;
  }
}

function uniqueGroups(samples: MockSample[]): string[] {
  return [...new Set(samples.map((sample) => sample.group).filter((group): group is string => Boolean(group)))];
}

function pickRepresentatives(samples: MockSample[], perGroup: number): MockSample[] {
  const groups = uniqueGroups(samples);
  const picked: MockSample[] = [];
  for (const group of groups) {
    picked.push(...samples.filter((sample) => sample.group === group).slice(0, perGroup));
  }
  return picked;
}
