import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MessageService, PrimeTemplate } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';

import { FloraRepository } from '../../core/data/flora.repository';
import { DownloadJob, DownloadRequest } from '../../core/models/domain';

@Component({
  selector: 'flora-downloads',
  standalone: true,
  imports: [ReactiveFormsModule, PrimeTemplate, ButtonModule, InputNumberModule, InputTextModule, TableModule, TagModule],
  template: `
    <section class="page">
      <header class="page-heading">
        <div>
          <p class="kicker">Downloads</p>
          <h1>Fontes para o pipeline</h1>
          <p class="lede">Sintético, EMP, MGnify e SRA. No mock, o pedido é registrado e nenhum arquivo remoto é baixado.</p>
        </div>
        <p-tag [value]="mocked() ? 'Dados mockados' : 'API HTTP'" severity="secondary" />
      </header>

      <section class="split">
        <form class="surface filters" [formGroup]="synthetic" (ngSubmit)="submit('synthetic')">
          <h2>Sintético</h2>
          <div class="field"><label for="synDir">Diretório</label><input id="synDir" pInputText formControlName="outputDir" /></div>
          <div class="field"><label for="synSamples">Amostras</label><p-inputnumber inputId="synSamples" formControlName="samples" [min]="4" [fluid]="true" /></div>
          <div class="field"><label for="synFeatures">ASVs</label><p-inputnumber inputId="synFeatures" formControlName="features" [min]="10" [fluid]="true" /></div>
          <div class="field"><label for="synSeed">Seed</label><p-inputnumber inputId="synSeed" formControlName="seed" [fluid]="true" /></div>
          <p-button type="submit" label="Gerar" [loading]="busy()" />
        </form>
        <form class="surface filters" [formGroup]="emp" (ngSubmit)="submit('emp')">
          <h2>EMP</h2>
          <div class="field"><label for="empDir">Diretório</label><input id="empDir" pInputText formControlName="outputDir" /></div>
          <div class="field"><label for="empBiome">Filtro de bioma</label><input id="empBiome" pInputText formControlName="biome" /></div>
          <div class="field"><label for="empMax">Máximo de amostras</label><p-inputnumber inputId="empMax" formControlName="maxSamples" [min]="1" [fluid]="true" /></div>
          <p-button type="submit" label="Pedir EMP" [loading]="busy()" />
        </form>
        <form class="surface filters" [formGroup]="mgnify" (ngSubmit)="submit('mgnify')">
          <h2>MGnify</h2>
          <div class="field">
            <label for="study">Accession do estudo</label>
            <input id="study" pInputText formControlName="studyAccession" />
            @if (mgnify.controls.studyAccession.invalid && mgnify.controls.studyAccession.touched) {
              <small class="field-error">Informe o accession, por exemplo MGYS00001234.</small>
            }
          </div>
          <div class="field"><label for="mgBiome">Bioma</label><input id="mgBiome" pInputText formControlName="biome" /></div>
          <div class="field"><label for="mgDir">Diretório</label><input id="mgDir" pInputText formControlName="outputDir" /></div>
          <p-button type="submit" label="Pedir MGnify" [loading]="busy()" />
        </form>
        <form class="surface filters" [formGroup]="sra" (ngSubmit)="submit('sra')">
          <h2>SRA</h2>
          <div class="field">
            <label for="accessions">Accessions</label>
            <input id="accessions" pInputText formControlName="accessions" placeholder="SRR000001, SRR000002" />
            @if (sra.controls.accessions.invalid && sra.controls.accessions.touched) {
              <small class="field-error">Liste ao menos um accession.</small>
            }
          </div>
          <div class="field"><label for="sraDir">Diretório</label><input id="sraDir" pInputText formControlName="outputDir" /></div>
          <p-button type="submit" label="Pedir SRA" [loading]="busy()" />
        </form>
      </section>

      <article class="surface">
        <div class="section-title"><h2>Pedidos</h2></div>
        <p-table [value]="jobs()" dataKey="id">
          <ng-template pTemplate="header">
            <tr><th>Fonte</th><th>Estado</th><th>Quando</th><th>Detalhe</th><th>Artefatos</th></tr>
          </ng-template>
          <ng-template pTemplate="body" let-job>
            <tr>
              <td>{{ job.source }}</td>
              <td [class]="job.status === 'failed' ? 'status-fail' : 'status-pass'">{{ job.status }}</td>
              <td>{{ job.createdAt }}</td>
              <td>{{ job.detail }}</td>
              <td>{{ job.artifacts.map(item => item.path).join(', ') || '—' }}</td>
            </tr>
          </ng-template>
          <ng-template pTemplate="emptymessage"><tr><td colspan="5">Nenhum pedido.</td></tr></ng-template>
        </p-table>
      </article>
    </section>
  `
})
export class DownloadsPageComponent {
  private readonly repository = inject(FloraRepository);
  private readonly messages = inject(MessageService);
  private readonly fb = inject(FormBuilder);

  readonly jobs = signal<DownloadJob[]>([]);
  readonly busy = signal(false);
  readonly mocked = signal(true);

  readonly synthetic = this.fb.nonNullable.group({
    outputDir: ['results/raw/synthetic', Validators.required],
    samples: [80, [Validators.required, Validators.min(4)]],
    features: [200, [Validators.required, Validators.min(10)]],
    seed: [42, Validators.required]
  });
  readonly emp = this.fb.nonNullable.group({
    outputDir: ['results/raw/emp', Validators.required],
    biome: [''],
    maxSamples: [200, [Validators.required, Validators.min(1)]]
  });
  readonly mgnify = this.fb.nonNullable.group({
    outputDir: ['results/raw/mgnify', Validators.required],
    studyAccession: ['', Validators.required],
    biome: ['root:Environmental:Terrestrial'],
    maxSamples: [20, [Validators.required, Validators.min(1)]]
  });
  readonly sra = this.fb.nonNullable.group({
    outputDir: ['results/raw/sra', Validators.required],
    accessions: ['', Validators.required]
  });

  constructor() {
    void this.reload();
  }

  async submit(source: DownloadRequest['source']): Promise<void> {
    const form = source === 'synthetic' ? this.synthetic : source === 'emp' ? this.emp : source === 'mgnify' ? this.mgnify : this.sra;
    if (form.invalid) {
      form.markAllAsTouched();
      return;
    }
    this.busy.set(true);
    try {
      const value = form.getRawValue() as {
        outputDir: string;
        samples?: number;
        features?: number;
        seed?: number;
        biome?: string;
        maxSamples?: number;
        studyAccession?: string;
        accessions?: string;
      };
      const request: DownloadRequest = {
        source,
        outputDir: value.outputDir,
        samples: value.samples,
        features: value.features,
        seed: value.seed,
        biome: value.biome,
        maxSamples: value.maxSamples,
        studyAccession: value.studyAccession,
        accessions: value.accessions?.split(/[,\s]+/).filter(Boolean)
      };
      const job = await this.repository.requestDownload(request);
      this.messages.add({
        severity: job.status === 'failed' ? 'error' : 'success',
        summary: job.source,
        detail: job.detail
      });
      await this.reload();
    } finally {
      this.busy.set(false);
    }
  }

  private async reload(): Promise<void> {
    const jobs = await this.repository.downloads();
    this.jobs.set(jobs);
    this.mocked.set(jobs.every((job) => job.mocked));
  }
}
