import { Injectable } from '@angular/core';

import { PlotResponse } from './models';

declare global {
  interface Window {
    Plotly?: {
      newPlot: (target: HTMLElement, data: unknown[], layout: object, config?: object) => Promise<void>;
    };
  }
}

@Injectable({ providedIn: 'root' })
export class PlotlyService {
  async render(target: HTMLElement, payload: PlotResponse | null): Promise<void> {
    if (!payload?.success || !payload.plot || !window.Plotly) {
      const notice = document.createElement('div');
      notice.className = 'notice error';
      notice.textContent = payload?.error ?? 'Plot indisponivel.';
      target.replaceChildren(notice);
      return;
    }

    target.innerHTML = '';
    await window.Plotly.newPlot(target, payload.plot.data, payload.plot.layout, {
      responsive: true,
      displaylogo: false
    });
  }
}
