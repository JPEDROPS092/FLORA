import { CommonModule, JsonPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../../core/api.service';
import { ApiResponse } from '../../core/models';

@Component({
  selector: 'flora-reporting-page',
  standalone: true,
  imports: [CommonModule, FormsModule, JsonPipe],
  template: `
    <section class="section-header">
      <div>
        <h2>Relatorio e ML</h2>
        <p>Classificacao, clustering, preview e exportacao de relatorios analiticos.</p>
      </div>
    </section>

    <section class="grid-two">
      <article class="card pane">
        <div class="section-header">
          <div>
            <h3>Classification</h3>
            <p>Treino supervisionado sobre filtros SQL do backend. Preencha filtros validos para o dataset carregado.</p>
          </div>
        </div>

        <div class="grid-two">
          <div class="field">
            <label>Model</label>
            <select [(ngModel)]="model">
              <option value="random_forest">random_forest</option>
              <option value="xgboost">xgboost</option>
            </select>
          </div>
          <div class="field">
            <label>Target column</label>
            <input [(ngModel)]="targetColumn">
          </div>
          <div class="field">
            <label>Train filter</label>
            <input [(ngModel)]="trainFilter" placeholder="biome = 'Forest'">
          </div>
          <div class="field">
            <label>Test filter</label>
            <input [(ngModel)]="testFilter" placeholder="biome = 'Soil'">
          </div>
          <div class="field">
            <label>Normalize</label>
            <select [(ngModel)]="normalize">
              <option value="clr">CLR</option>
              <option value="tss">TSS</option>
              <option value="none">Raw</option>
            </select>
          </div>
          <div class="field">
            <label>CV folds</label>
            <input [(ngModel)]="cvFolds" type="number" min="2">
          </div>
        </div>

        <div class="actions">
          <button class="btn btn-primary" [disabled]="busy()" (click)="runClassification()">Executar classificacao</button>
        </div>
      </article>

      <article class="card pane">
        <div class="section-header">
          <div>
            <h3>Clustering and reporting</h3>
            <p>HTML e o artefato editavel. PDF vira export derivado quando a dependencia estiver disponivel.</p>
          </div>
        </div>

        <div class="grid-two">
          <div class="field">
            <label>Clustering method</label>
            <select [(ngModel)]="clusterMethod">
              <option value="kmeans">kmeans</option>
              <option value="hdbscan">hdbscan</option>
            </select>
          </div>
          <div class="field">
            <label>Clusters</label>
            <input [(ngModel)]="clusterCount" type="number" min="2">
          </div>
          <div class="field">
            <label>Report title</label>
            <input [(ngModel)]="reportTitle">
          </div>
          <div class="field">
            <label>HTML path</label>
            <input [(ngModel)]="reportOutput">
          </div>
          <div class="field">
            <label>Output format</label>
            <select [(ngModel)]="reportFormat">
              <option value="html">HTML only</option>
              <option value="both">HTML + PDF</option>
              <option value="pdf">PDF request + HTML source</option>
            </select>
          </div>
          <div class="field">
            <label>PDF path</label>
            <input [(ngModel)]="pdfOutput">
          </div>
          <div class="field">
            <label>Group by</label>
            <input [(ngModel)]="reportGroupBy" placeholder="biome">
          </div>
        </div>

        <div class="actions">
          <button class="btn btn-secondary" [disabled]="busy()" (click)="runCluster()">Executar clustering</button>
          <button class="btn btn-secondary" [disabled]="busy()" (click)="generateReport()">Gerar report</button>
        </div>

        <div class="notice ok">
          Preview e leitura acontecem no HTML gerado. Se o ambiente tiver suporte a PDF, a API devolve tambem o caminho do PDF.
        </div>
      </article>
    </section>

    <section class="card pane" *ngIf="previewUrl()">
      <div class="section-header">
        <div>
          <h3>Preview</h3>
          <p>Visualizacao imediata do relatorio gerado pelo backend.</p>
        </div>
      </div>

      <div class="report-actions">
        <a class="btn btn-primary" [href]="previewUrl()" target="_blank" rel="noopener">Abrir em nova aba</a>
      </div>
      <iframe class="report-frame" [src]="previewUrl()"></iframe>
    </section>

    <section class="card pane" *ngIf="result()">
      <div class="section-header">
        <div>
          <h3>Resultado</h3>
          <p>Payload retornado pela API.</p>
        </div>
      </div>
      <pre>{{ result() | json }}</pre>
    </section>
  `,
  styles: [`
    .pane { padding: 24px; display: grid; gap: 14px; }
    .report-actions { display: flex; gap: 12px; }
    .report-frame {
      width: 100%;
      min-height: 780px;
      border: 1px solid rgba(31, 41, 55, 0.12);
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.92);
    }
    pre {
      margin: 0;
      white-space: pre-wrap;
      font-size: 0.82rem;
      font-family: ui-monospace, monospace;
    }
  `]
})
export class ReportingPageComponent {
  private readonly api = inject(ApiService);

  model = 'random_forest';
  targetColumn = 'biome';
  trainFilter = '';
  testFilter = '';
  normalize = 'clr';
  cvFolds = 5;

  clusterMethod = 'kmeans';
  clusterCount = 4;
  reportTitle = 'FLORA Analysis Report';
  reportOutput = 'results/report.html';
  reportFormat = 'html';
  pdfOutput = 'results/report.pdf';
  reportGroupBy = 'biome';

  readonly busy = signal(false);
  readonly result = signal<ApiResponse | null>(null);
  readonly previewUrl = signal<string>('');

  async runClassification(): Promise<void> {
    await this.run(() =>
      this.api.classify({
        model: this.model,
        target_column: this.targetColumn,
        train_filter: this.trainFilter,
        test_filter: this.testFilter,
        normalize: this.normalize === 'none' ? null : this.normalize,
        cv_folds: this.cvFolds
      })
    );
  }

  async runCluster(): Promise<void> {
    await this.run(() =>
      this.api.cluster({
        method: this.clusterMethod,
        n_clusters: this.clusterCount,
        normalize: this.normalize
      })
    );
  }

  async generateReport(): Promise<void> {
    await this.run(async () => {
      const response = await this.api.generateReport({
        title: this.reportTitle,
        output_path: this.reportOutput,
        output_format: this.reportFormat,
        pdf_path: this.pdfOutput,
        group_by: this.reportGroupBy || null
      });
      const preview = response['report_preview_url'];
      if (typeof preview === 'string' && preview.length > 0) {
        this.previewUrl.set(`${preview}&ts=${Date.now()}`);
      }
      return response;
    });
  }

  private async run(task: () => Promise<ApiResponse>): Promise<void> {
    this.busy.set(true);
    try {
      this.result.set(await task());
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unexpected error';
      this.result.set({ success: false, error: message });
    } finally {
      this.busy.set(false);
    }
  }
}
