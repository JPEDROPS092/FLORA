import { CommonModule } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';

import { ApiService } from '../../core/api.service';
import { ApiStatus } from '../../core/models';

@Component({
  selector: 'flora-overview-page',
  standalone: true,
  imports: [CommonModule],
  template: `
    <section class="hero">
      <div class="card hero-main">
        <p class="eyebrow">Operations cockpit</p>
        <h2>Sequencing analytics com frontend Angular e backend Python.</h2>
        <p>
          A SPA agora fica desacoplada da camada HTTP e consome a mesma API do
          comando <code>flora ui</code>. Isso reduz acoplamento e permite evoluir
          o frontend por features.
        </p>
        <div class="tags">
          <span>DuckDB analytics</span>
          <span>Python library preserved</span>
          <span>Angular SPA</span>
          <span>Same CLI contract</span>
        </div>
      </div>

      <div class="card hero-side">
        <div>
          <strong>Status atual</strong>
          <p>{{ status()?.status ?? 'carregando' }}</p>
        </div>
        <div>
          <strong>Frontend ativo</strong>
          <p>{{ status()?.frontend?.mode ?? 'unknown' }}</p>
        </div>
        <div>
          <strong>Workdir</strong>
          <p>{{ status()?.workdir ?? 'n/a' }}</p>
        </div>
      </div>
    </section>

    <section class="metric-grid">
      <article class="card metric" *ngFor="let metric of metrics()">
        <div class="label">{{ metric.label }}</div>
        <div class="value">{{ metric.value }}</div>
      </article>
    </section>

    <section class="card panel">
      <div class="section-header">
        <div>
          <h3>Runtime logs</h3>
          <p>Ultimas linhas expostas por <code>/api/logs</code>.</p>
        </div>
      </div>
      <div class="logs">{{ logText() }}</div>
    </section>
  `,
  styles: [`
    .hero { display: grid; grid-template-columns: 1.4fr 1fr; gap: 18px; margin-bottom: 18px; }
    .hero-main { padding: 30px; }
    .hero-side { padding: 24px; display: grid; gap: 12px; }
    .eyebrow {
      text-transform: uppercase;
      letter-spacing: 0.18em;
      color: var(--rust);
      font-size: 0.75rem;
      font-weight: 700;
    }
    h2 {
      margin: 10px 0 12px;
      font-family: "Gill Sans", "Trebuchet MS", sans-serif;
      font-size: clamp(2rem, 3vw, 3.35rem);
      line-height: 0.96;
      letter-spacing: -0.05em;
    }
    .hero p { color: var(--muted); line-height: 1.65; }
    .tags { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }
    .tags span {
      display: inline-flex;
      align-items: center;
      padding: 10px 14px;
      border-radius: 999px;
      background: rgba(15, 118, 110, 0.09);
      color: var(--forest);
      font-weight: 600;
      font-size: 0.92rem;
    }
    .panel { padding: 24px; margin-top: 18px; }
    .logs {
      min-height: 220px;
      white-space: pre-wrap;
      padding: 18px;
      border-radius: 16px;
      background: #101827;
      color: #d7e0ef;
      font-family: ui-monospace, monospace;
      font-size: 0.84rem;
      line-height: 1.5;
    }
    @media (max-width: 1100px) {
      .hero { grid-template-columns: 1fr; }
    }
  `]
})
export class OverviewPageComponent {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);

  readonly status = signal<ApiStatus | null>(null);
  readonly metrics = signal<{ label: string; value: string }[]>([]);
  readonly logText = signal('Carregando logs...');

  constructor() {
    void this.refresh();
    const timer = window.setInterval(() => void this.refresh(), 15000);
    this.destroyRef.onDestroy(() => window.clearInterval(timer));
  }

  private async refresh(): Promise<void> {
    const [status, logs] = await Promise.all([
      this.api.status().catch(() => null),
      this.api.logs().catch(() => null)
    ]);

    this.status.set(status);
    this.metrics.set([
      { label: 'Frontend', value: status?.frontend?.mode ?? 'unknown' },
      { label: 'Workdir', value: status?.workdir ?? 'n/a' },
      { label: 'Tables', value: String(Object.keys(status?.tables ?? {}).length) },
      { label: 'Status', value: status?.status ?? 'offline' }
    ]);
    const lines = logs?.['lines'];
    this.logText.set(Array.isArray(lines) ? lines.join('\n') : 'Nenhum log disponivel.');
  }
}
