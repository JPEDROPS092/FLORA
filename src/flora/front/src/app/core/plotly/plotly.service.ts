import { Injectable } from '@angular/core';

import { PlotFigure, ThemeMode } from '../models/domain';
import { t } from '../i18n/i18n';

interface PlotlyApi {
  newPlot: (target: HTMLElement, data: unknown[], layout: object, config?: object) => Promise<void>;
  purge?: (target: HTMLElement) => void;
  downloadImage?: (target: HTMLElement, options: object) => Promise<string>;
}

declare global {
  interface Window {
    Plotly?: PlotlyApi;
  }
}

@Injectable({ providedIn: 'root' })
export class PlotlyService {
  /** Vector export for papers; Plotly draws it in the browser, so no server image engine is needed. */
  async exportSvg(target: HTMLElement, filename = 'flora-figura'): Promise<void> {
    await window.Plotly?.downloadImage?.(target, { format: 'svg', filename, width: 1000, height: 640 });
  }

  async render(target: HTMLElement, figure: PlotFigure, theme: ThemeMode): Promise<void> {
    if (!window.Plotly) {
      target.replaceChildren(notice(t('Plotly não está disponível neste navegador.')));
      return;
    }
    await window.Plotly.newPlot(target, figure.data, themedLayout(figure.layout, theme), {
      responsive: true,
      displaylogo: false
    });
  }
}

function notice(message: string): HTMLElement {
  const node = document.createElement('p');
  node.className = 'plot-state';
  node.textContent = message;
  return node;
}

function themedLayout(layout: Record<string, unknown>, theme: ThemeMode): Record<string, unknown> {
  const dark = theme === 'dark';
  const ink = dark ? '#E7F0EC' : '#22332F';
  const grid = dark ? '#2A3C36' : '#DCE5E1';
  return {
    ...layout,
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: 'Segoe UI, Helvetica Neue, Arial, sans-serif', color: ink, size: 12 },
    legend: {
      ...(asRecord(layout['legend'])),
      bgcolor: 'rgba(0,0,0,0)',
      font: { color: ink, size: 11 }
    },
    xaxis: axis(layout['xaxis'], grid, ink),
    yaxis: axis(layout['yaxis'], grid, ink)
  };
}

function axis(value: unknown, grid: string, ink: string): Record<string, unknown> {
  return {
    ...asRecord(value),
    gridcolor: grid,
    zerolinecolor: grid,
    linecolor: grid,
    tickfont: { color: ink, size: 11 },
    title: {
      ...asRecord(asRecord(value)['title']),
      font: { color: ink, size: 12 }
    }
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}
