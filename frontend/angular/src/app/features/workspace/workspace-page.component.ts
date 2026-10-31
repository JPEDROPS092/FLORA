import { CommonModule, JsonPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../../core/api.service';
import { ApiResponse } from '../../core/models';

@Component({
  selector: 'flora-workspace-page',
  standalone: true,
  imports: [CommonModule, FormsModule, JsonPipe],
  template: `
    <section class="section-header">
      <div>
        <h2>Workspace</h2>
        <p>Ingestao, diversidade e preview de matriz organizados por fluxo operacional.</p>
      </div>
    </section>

    <section class="grid-two">
      <article class="card pane">
        <div class="section-header">
          <div>
            <h3>Data ingestion</h3>
            <p>Carregue metadata, ASV e taxonomy sem sair da biblioteca.</p>
          </div>
        </div>

        <div class="field">
          <label>Metadata path</label>
          <input [(ngModel)]="metadataPath" placeholder="data/raw/metadata.tsv">
        </div>
        <div class="field">
          <label>Sample column</label>
          <input [(ngModel)]="sampleColumn" placeholder="sample_id">
        </div>
        <div class="field">
          <label>ASV path</label>
          <input [(ngModel)]="asvPath" placeholder="data/raw/asv_table.tsv">
        </div>
        <div class="field">
          <label>ASV format</label>
          <select [(ngModel)]="wideFormat">
            <option [ngValue]="true">Wide format</option>
            <option [ngValue]="false">Long format</option>
          </select>
        </div>
        <div class="field">
          <label>Taxonomy path</label>
          <input [(ngModel)]="taxonomyPath" placeholder="data/raw/taxonomy.tsv">
        </div>

        <div class="actions">
          <button class="btn btn-primary" [disabled]="busy()" (click)="ingestAll()">Ingerir tudo</button>
          <button class="btn btn-secondary" [disabled]="busy()" (click)="ingestMetadata()">Metadata</button>
          <button class="btn btn-secondary" [disabled]="busy()" (click)="ingestAsv()">ASV</button>
          <button class="btn btn-secondary" [disabled]="busy()" (click)="ingestTaxonomy()">Taxonomy</button>
        </div>

        <div class="notice" [class.ok]="result()?.success" [class.error]="result() && !result()?.success" *ngIf="result()">
          <pre>{{ result() | json }}</pre>
        </div>
      </article>

      <article class="card pane">
        <div class="section-header">
          <div>
            <h3>Diversity and matrix</h3>
            <p>Compute diversity e valide o contrato da feature matrix.</p>
          </div>
        </div>

        <div class="field">
          <label>Sampling depth</label>
          <input [(ngModel)]="samplingDepth" type="number" min="1">
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
          <label>Min prevalence</label>
          <input [(ngModel)]="minPrevalence" type="number" min="0" max="1" step="0.01">
        </div>

        <div class="actions">
          <button class="btn btn-primary" [disabled]="busy()" (click)="computeDiversity()">Compute diversity</button>
          <button class="btn btn-secondary" [disabled]="busy()" (click)="previewMatrix()">Preview matrix</button>
        </div>

        <div class="notice" [class.ok]="secondaryResult()?.success" [class.error]="secondaryResult() && !secondaryResult()?.success" *ngIf="secondaryResult()">
          <pre>{{ secondaryResult() | json }}</pre>
        </div>
      </article>
    </section>
  `,
  styles: [`
    .pane { padding: 24px; display: grid; gap: 14px; }
    pre {
      margin: 0;
      white-space: pre-wrap;
      font-size: 0.82rem;
      font-family: ui-monospace, monospace;
    }
  `]
})
export class WorkspacePageComponent {
  private readonly api = inject(ApiService);

  metadataPath = 'data/raw/metadata.tsv';
  sampleColumn = 'sample_id';
  asvPath = 'data/raw/asv_table.tsv';
  taxonomyPath = 'data/raw/taxonomy.tsv';
  wideFormat = true;
  samplingDepth = 10000;
  normalize = 'tss';
  minPrevalence = 0.05;

  readonly busy = signal(false);
  readonly result = signal<ApiResponse | null>(null);
  readonly secondaryResult = signal<ApiResponse | null>(null);

  async ingestMetadata(): Promise<void> {
    await this.run(async () => {
      this.result.set(
        await this.api.ingestMetadata({ path: this.metadataPath, sample_col: this.sampleColumn })
      );
    });
  }

  async ingestAsv(): Promise<void> {
    await this.run(async () => {
      this.result.set(
        await this.api.ingestAsv({ path: this.asvPath, wide_format: this.wideFormat })
      );
    });
  }

  async ingestTaxonomy(): Promise<void> {
    await this.run(async () => {
      this.result.set(await this.api.ingestTaxonomy({ path: this.taxonomyPath }));
    });
  }

  async ingestAll(): Promise<void> {
    await this.run(async () => {
      const metadata = await this.api.ingestMetadata({ path: this.metadataPath, sample_col: this.sampleColumn });
      const asv = await this.api.ingestAsv({ path: this.asvPath, wide_format: this.wideFormat });
      const taxonomy = await this.api.ingestTaxonomy({ path: this.taxonomyPath });
      this.result.set({ success: true, metadata, asv, taxonomy });
    });
  }

  async computeDiversity(): Promise<void> {
    await this.run(async () => {
      this.secondaryResult.set(
        await this.api.diversity({
          sampling_depth: this.samplingDepth,
          metrics: ['shannon', 'observed_features', 'chao1']
        })
      );
    });
  }

  async previewMatrix(): Promise<void> {
    await this.run(async () => {
      this.secondaryResult.set(await this.api.featureMatrix(this.normalize, this.minPrevalence));
    });
  }

  private async run(task: () => Promise<void>): Promise<void> {
    this.busy.set(true);
    try {
      await task();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unexpected error';
      this.result.set({ success: false, error: message });
    } finally {
      this.busy.set(false);
    }
  }
}
