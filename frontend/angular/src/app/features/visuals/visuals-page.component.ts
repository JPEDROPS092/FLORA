import { CommonModule } from '@angular/common';
import { AfterViewInit, Component, ElementRef, ViewChild, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../../core/api.service';
import { PlotlyService } from '../../core/plotly.service';

@Component({
  selector: 'flora-visuals-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <section class="section-header">
      <div>
        <h2>Visualization Studio</h2>
        <p>Plotly integrado a partir dos endpoints atuais do backend FLORA.</p>
      </div>
    </section>

    <section class="card pane">
      <div class="grid-four">
        <div class="field">
          <label>Normalize</label>
          <select [(ngModel)]="normalize">
            <option value="clr">CLR</option>
            <option value="tss">TSS</option>
            <option value="none">Raw</option>
          </select>
        </div>
        <div class="field">
          <label>Group by</label>
          <input [(ngModel)]="groupBy" placeholder="biome">
        </div>
        <div class="field">
          <label>Top N</label>
          <input [(ngModel)]="topN" type="number" min="1">
        </div>
        <div class="field">
          <label>Threshold</label>
          <input [(ngModel)]="threshold" type="number" min="0" max="1" step="0.01">
        </div>
      </div>

      <div class="actions">
        <button class="btn btn-primary" [disabled]="busy()" (click)="loadCoreVisuals()">Carregar core visuals</button>
        <button class="btn btn-secondary" [disabled]="busy()" (click)="loadAdvancedVisuals()">Carregar advanced visuals</button>
      </div>

      <div class="notice" *ngIf="message()" [class.error]="messageType() === 'error'" [class.ok]="messageType() === 'ok'">
        {{ message() }}
      </div>
    </section>

    <section class="grid-two">
      <article class="card plot-card"><div class="section-header"><h3>PCoA</h3></div><div #pcoaHost class="plot-host"></div></article>
      <article class="card plot-card"><div class="section-header"><h3>Alpha diversity</h3></div><div #alphaHost class="plot-host"></div></article>
      <article class="card plot-card"><div class="section-header"><h3>Taxonomy barplot</h3></div><div #taxonomyHost class="plot-host"></div></article>
      <article class="card plot-card"><div class="section-header"><h3>Taxonomy heatmap</h3></div><div #taxonomyHeatmapHost class="plot-host"></div></article>
      <article class="card plot-card"><div class="section-header"><h3>Beta heatmap</h3></div><div #betaHeatmapHost class="plot-host"></div></article>
      <article class="card plot-card"><div class="section-header"><h3>Krona</h3></div><div #kronaHost class="plot-host"></div></article>
      <article class="card plot-card"><div class="section-header"><h3>Tree</h3></div><div #treeHost class="plot-host"></div></article>
      <article class="card plot-card"><div class="section-header"><h3>Network</h3></div><div #networkHost class="plot-host"></div></article>
    </section>
  `,
  styles: [`
    .pane { padding: 24px; display: grid; gap: 14px; margin-bottom: 18px; }
    .plot-card { padding: 22px; }
  `]
})
export class VisualsPageComponent implements AfterViewInit {
  private readonly api = inject(ApiService);
  private readonly plotly = inject(PlotlyService);

  @ViewChild('pcoaHost') private pcoaHost?: ElementRef<HTMLElement>;
  @ViewChild('alphaHost') private alphaHost?: ElementRef<HTMLElement>;
  @ViewChild('taxonomyHost') private taxonomyHost?: ElementRef<HTMLElement>;
  @ViewChild('taxonomyHeatmapHost') private taxonomyHeatmapHost?: ElementRef<HTMLElement>;
  @ViewChild('betaHeatmapHost') private betaHeatmapHost?: ElementRef<HTMLElement>;
  @ViewChild('kronaHost') private kronaHost?: ElementRef<HTMLElement>;
  @ViewChild('treeHost') private treeHost?: ElementRef<HTMLElement>;
  @ViewChild('networkHost') private networkHost?: ElementRef<HTMLElement>;

  normalize = 'tss';
  groupBy = 'biome';
  topN = 25;
  threshold = 0.35;

  readonly busy = signal(false);
  readonly message = signal('');
  readonly messageType = signal<'ok' | 'error'>('ok');

  ngAfterViewInit(): void {
    const hosts = [
      this.pcoaHost,
      this.alphaHost,
      this.taxonomyHost,
      this.taxonomyHeatmapHost,
      this.betaHeatmapHost,
      this.kronaHost,
      this.treeHost,
      this.networkHost
    ];
    hosts.forEach((host) => {
      if (host?.nativeElement) {
        host.nativeElement.innerHTML = '<div class="notice">Carregue uma visualizacao para iniciar.</div>';
      }
    });
  }

  async loadCoreVisuals(): Promise<void> {
    await this.run(async () => {
      await Promise.all([
        this.render(this.pcoaHost, '/api/viz/pcoa', { normalize: this.normalize, color_by: this.groupBy }),
        this.render(this.alphaHost, '/api/viz/alpha', { metric: 'shannon', group_by: this.groupBy }),
        this.render(this.taxonomyHost, '/api/viz/taxonomy', { level: 'phylum', group_by: this.groupBy }),
        this.render(this.taxonomyHeatmapHost, '/api/viz/taxonomy_heatmap', { level: 'genus', top_n: this.topN })
      ]);
      this.messageType.set('ok');
      this.message.set('Core visuals carregados.');
    });
  }

  async loadAdvancedVisuals(): Promise<void> {
    await this.run(async () => {
      await Promise.all([
        this.render(this.betaHeatmapHost, '/api/viz/beta_heatmap', {
          normalize: this.normalize,
          metric: 'bray_curtis',
          max_samples: 60
        }),
        this.render(this.kronaHost, '/api/viz/krona', { group_by: this.groupBy, top_n: Math.max(this.topN, 120) }),
        this.render(this.treeHost, '/api/viz/tree', { group_by: this.groupBy, top_n: Math.max(this.topN, 120) }),
        this.render(this.networkHost, '/api/viz/network', {
          level: 'genus',
          top_n: Math.min(this.topN, 25),
          threshold: this.threshold
        })
      ]);
      this.messageType.set('ok');
      this.message.set('Advanced visuals carregados.');
    });
  }

  private async render(
    host: ElementRef<HTMLElement> | undefined,
    path: string,
    params: Record<string, string | number>
  ): Promise<void> {
    if (!host?.nativeElement) {
      return;
    }
    const payload = await this.api.plot(path, params);
    await this.plotly.render(host.nativeElement, payload);
  }

  private async run(task: () => Promise<void>): Promise<void> {
    this.busy.set(true);
    try {
      await task();
    } catch (error) {
      this.messageType.set('error');
      this.message.set(error instanceof Error ? error.message : 'Unexpected error');
    } finally {
      this.busy.set(false);
    }
  }
}
