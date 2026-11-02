import { DecimalPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MessageService, PrimeTemplate } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { FileUploadModule } from 'primeng/fileupload';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { StepperModule } from 'primeng/stepper';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ToggleSwitchModule } from 'primeng/toggleswitch';

import { FloraRepository } from '../../core/data/flora.repository';
import { IngestOutcome, IngestPreview, PipelineSnapshot } from '../../core/models/domain';
import { PlotCardComponent } from '../../shared/plot-card.component';
import { TPipe } from '../../core/i18n/t.pipe';
import { t } from '../../core/i18n/i18n';

@Component({
  selector: 'flora-pipeline',
  standalone: true,
  imports: [TPipe, 
    DecimalPipe,
    ReactiveFormsModule,
    RouterLink,
    PrimeTemplate,
    ButtonModule,
    FileUploadModule,
    InputNumberModule,
    InputTextModule,
    SelectModule,
    StepperModule,
    TableModule,
    TagModule,
    ToggleSwitchModule,
    PlotCardComponent
  ],
  template: `
    <section class="page">
      <header class="page-heading">
        <div>
          <p class="kicker">{{ 'Data Pipeline Studio' | t }}</p>
          <h1>{{ 'Importação, QC e normalização' | t }}</h1>
          <p class="lede">{{ 'O trilho segue a ordem QIIME2 / DADA2. A conferência de amostras acontece antes de aceitar a tabela.' | t }}</p>
        </div>
        <div class="actions">
          @if (pipeline()?.mocked) { <p-tag [value]="'Dados mockados' | t" severity="secondary" /> }
          <a routerLink="/downloads">{{ 'Fontes externas' | t }}</a>
        </div>
      </header>

      <ol class="workflow">
        @for (stage of pipeline()?.stages ?? []; track stage.id) {
          <li [class]="stage.status">
            <span class="tool">{{ stage.tool }}</span>
            <strong>{{ stage.name }}</strong>
            <em>{{ stage.detail }}</em>
          </li>
        }
      </ol>

      <section class="split">
        <article class="surface">
          <div class="section-title">
            <h2>{{ 'Normalização' | t }}</h2>
            <p>{{ 'Rarefação, transformação e prevalência mínima.' | t }}</p>
          </div>
          <form class="filters" [formGroup]="normForm" (ngSubmit)="applyNorm()">
            <div class="field">
              <label for="depth">{{ 'Rarefação (reads)' | t }}</label>
              <p-inputnumber inputId="depth" formControlName="rarefactionDepth" [min]="1000" [fluid]="true" />
              @if (normForm.controls.rarefactionDepth.invalid && normForm.controls.rarefactionDepth.touched) {
                <small class="field-error">{{ 'Informe uma profundidade de pelo menos 1.000 reads.' | t }}</small>
              }
            </div>
            <div class="field">
              <label for="method">{{ 'Transformação' | t }}</label>
              <p-select inputId="method" [options]="methods" formControlName="method" optionLabel="label" optionValue="value" appendTo="body" [fluid]="true" />
            </div>
            <div class="field">
              <label for="prevalence">{{ 'Prevalência mínima' | t }}</label>
              <p-inputnumber inputId="prevalence" formControlName="minPrevalence" [min]="0" [max]="1" [minFractionDigits]="2" [maxFractionDigits]="2" [fluid]="true" />
            </div>
            <div class="field">
              <label for="abundance">{{ 'Abundância mínima' | t }}</label>
              <p-inputnumber inputId="abundance" formControlName="minAbundance" [min]="0" [fluid]="true" />
            </div>
            <p-button type="submit" [label]="'Aplicar na matriz' | t" [loading]="busy()" />
          </form>
        </article>

        <article class="surface">
          <div class="section-title"><h2>{{ 'Correspondência' | t }}</h2></div>
          <p>{{ 'Pareadas:' | t }} {{ preview()?.summary?.matched | number }}</p>
          <p>{{ 'Só na metadata:' | t }} {{ preview()?.summary?.metadataOnly | number }}</p>
          <p>{{ 'Só na tabela ASV:' | t }} {{ preview()?.summary?.asvOnly | number }}</p>
          <p>{{ 'Abaixo da rarefação:' | t }} {{ preview()?.summary?.lowDepth | number }}</p>
          <p class="note">{{ 'ASVs declarados:' | t }} {{ preview()?.summary?.totalAsvs | number }}</p>
          @for (warning of preview()?.warnings ?? []; track warning) {
            <p class="note">{{ warning }}</p>
          }
        </article>
      </section>

      <article class="surface">
        <p-stepper [value]="step()" (valueChange)="onStep($event)" [linear]="true">
          <p-step-list>
            <p-step [value]="1">{{ 'Arquivos' | t }}</p-step>
            <p-step [value]="2">{{ 'Colunas' | t }}</p-step>
            <p-step [value]="3">{{ 'Amostras' | t }}</p-step>
            <p-step [value]="4">{{ 'Reads' | t }}</p-step>
            <p-step [value]="5">{{ 'Confirmar' | t }}</p-step>
          </p-step-list>
          <p-step-panels>
            <p-step-panel [value]="1">
              <ng-template pTemplate="content" let-activateCallback="activateCallback">
                <form class="filters" [formGroup]="uploadForm">
                  <p-fileupload
                    mode="advanced"
                    [customUpload]="true"
                    [multiple]="true"
                    accept=".tsv,.csv,.txt,.biom"
                    [chooseLabel]="'Selecionar arquivos' | t"
                    [showUploadButton]="false"
                    [showCancelButton]="false"
                    (onSelect)="onFiles($event)"
                  />
                  <div class="field">
                    <label for="metadataPath">{{ 'Metadata' | t }}</label>
                    <input id="metadataPath" pInputText formControlName="metadataPath" />
                  </div>
                  <div class="field">
                    <label for="asvPath">{{ 'Tabela ASV' | t }}</label>
                    <input id="asvPath" pInputText formControlName="asvPath" />
                  </div>
                  <div class="field">
                    <label for="taxonomyPath">{{ 'Taxonomia' | t }}</label>
                    <input id="taxonomyPath" pInputText formControlName="taxonomyPath" />
                  </div>
                  @if (uploadForm.invalid && uploadForm.touched) {
                    <small class="field-error">{{ 'Os três caminhos são obrigatórios. No mock, use fail-taxonomy para simular falha dessa etapa.' | t }}</small>
                  }
                  <div class="actions">
                    <p-button type="button" [label]="'Mapear colunas' | t" icon="pi pi-arrow-right" iconPos="right" (onClick)="goColumns(activateCallback)" />
                  </div>
                </form>
              </ng-template>
            </p-step-panel>
            <p-step-panel [value]="2">
              <ng-template pTemplate="content" let-activateCallback="activateCallback">
                <form class="filters" [formGroup]="uploadForm">
                  <div class="field">
                    <label for="sampleColumn">{{ 'Coluna da amostra' | t }}</label>
                    <p-select inputId="sampleColumn" [options]="columns()" formControlName="sampleColumn" appendTo="body" [fluid]="true" [editable]="true" />
                  </div>
                  <div class="field">
                    <label for="groupColumn">{{ 'Coluna do grupo' | t }}</label>
                    <p-select inputId="groupColumn" [options]="columns()" formControlName="groupColumn" appendTo="body" [fluid]="true" [editable]="true" />
                  </div>
                  <div class="field">
                    <label for="wide">{{ 'Tabela ASV larga' | t }}</label>
                    <p-toggleswitch inputId="wide" formControlName="wideFormat" />
                  </div>
                  <div class="actions">
                    <p-button type="button" [label]="'Voltar' | t" severity="secondary" (onClick)="activateCallback(1)" />
                    <p-button type="button" [label]="'Validar amostras' | t" (onClick)="goValidate(activateCallback)" />
                  </div>
                </form>
              </ng-template>
            </p-step-panel>
            <p-step-panel [value]="3">
              <ng-template pTemplate="content" let-activateCallback="activateCallback">
                <p-table [value]="problemRows()" [paginator]="true" [rows]="8">
                  <ng-template pTemplate="header">
                    <tr><th>{{ 'Amostra' | t }}</th><th>{{ 'Metadata' | t }}</th><th>{{ 'Grupo' | t }}</th><th>{{ 'ASV' | t }}</th><th>{{ 'Reads' | t }}</th><th>{{ 'Estado' | t }}</th><th>{{ 'Problema' | t }}</th></tr>
                  </ng-template>
                  <ng-template pTemplate="body" let-row>
                    <tr>
                      <td>{{ row.sampleId }}</td>
                      <td>{{ row.metadataId }}</td>
                      <td>{{ row.group || '—' }}</td>
                      <td>{{ row.inAsv ? t('sim') : t('não') }}</td>
                      <td>{{ row.reads === null ? '—' : (row.reads | number) }}</td>
                      <td [class]="'status-' + row.status">{{ row.status }}</td>
                      <td>{{ row.issues.join(' ') }}</td>
                    </tr>
                  </ng-template>
                  <ng-template pTemplate="emptymessage"><tr><td colspan="7">{{ 'Nenhuma divergência listada.' | t }}</td></tr></ng-template>
                </p-table>
                <div class="actions">
                  <p-button type="button" [label]="'Voltar' | t" severity="secondary" (onClick)="activateCallback(2)" />
                  <p-button type="button" [label]="'Ver distribuição' | t" (onClick)="activateCallback(4)" />
                </div>
              </ng-template>
            </p-step-panel>
            <p-step-panel [value]="4">
              <ng-template pTemplate="content" let-activateCallback="activateCallback">
                <flora-plot [result]="histogram()" [height]="320" />
                <div class="actions">
                  <p-button type="button" [label]="'Voltar' | t" severity="secondary" (onClick)="activateCallback(3)" />
                  <p-button type="button" [label]="'Confirmar ingestão' | t" (onClick)="activateCallback(5)" />
                </div>
              </ng-template>
            </p-step-panel>
            <p-step-panel [value]="5">
              <ng-template pTemplate="content" let-activateCallback="activateCallback">
                <p>{{ 'A ingestão só é aceita se metadata, ASV e taxonomia responderem com sucesso.' | t }}</p>
                @if (outcome(); as result) {
                  <ul class="limitations">
                    @for (item of result.steps; track item.step) {
                      <li [class]="item.success ? 'status-pass' : 'status-fail'">
                        {{ item.step }}: {{ item.success ? item.detail : item.error }}
                      </li>
                    }
                  </ul>
                  <p [class]="result.success ? 'status-pass' : 'status-fail'">
                    {{ result.success ? t('As três etapas foram aceitas.') : result.error }}
                  </p>
                }
                <div class="actions">
                  <p-button type="button" [label]="'Voltar' | t" severity="secondary" (onClick)="activateCallback(4)" />
                  <p-button type="button" [label]="'Confirmar' | t" icon="pi pi-check" [loading]="busy()" (onClick)="confirm()" />
                </div>
              </ng-template>
            </p-step-panel>
          </p-step-panels>
        </p-stepper>
      </article>
    </section>
  `
})
export class PipelinePageComponent {
  protected readonly t = t;
  private readonly repository = inject(FloraRepository);
  private readonly messages = inject(MessageService);
  private readonly fb = inject(FormBuilder);

  readonly pipeline = signal<PipelineSnapshot | null>(null);
  readonly preview = signal<IngestPreview | null>(null);
  readonly outcome = signal<IngestOutcome | null>(null);
  readonly columns = signal<string[]>(['sample_id', 'group', 'host', 'site']);
  readonly step = signal(1);
  readonly busy = signal(false);
  readonly methods = [
    { label: 'CLR', value: 'clr' },
    { label: 'TSS', value: 'tss' },
    { label: t('Sem transformação'), value: 'none' }
  ];

  readonly uploadForm = this.fb.nonNullable.group({
    metadataPath: ['results/raw/FL16S-SORGHUM-01/metadata.tsv', Validators.required],
    asvPath: ['results/raw/FL16S-SORGHUM-01/asv_table.tsv', Validators.required],
    taxonomyPath: ['results/raw/FL16S-SORGHUM-01/taxonomy.tsv', Validators.required],
    sampleColumn: ['sample_id', Validators.required],
    groupColumn: ['group', Validators.required],
    wideFormat: [true]
  });

  readonly normForm = this.fb.nonNullable.group({
    rarefactionDepth: [10000, [Validators.required, Validators.min(1000)]],
    method: this.fb.nonNullable.control<'clr' | 'tss' | 'none'>('clr', Validators.required),
    minPrevalence: [0.05, [Validators.required, Validators.min(0), Validators.max(1)]],
    minAbundance: [10, [Validators.required, Validators.min(0)]]
  });

  constructor() {
    void this.reload();
  }

  problemRows(): IngestPreview['rows'] {
    return (this.preview()?.rows ?? []).filter((row) => row.status !== 'pass');
  }

  histogram() {
    const figure = this.preview()?.histogram;
    if (!figure?.data.length) {
      return { status: 'empty' as const, error: this.preview()?.warnings[0] ?? t('Distribuição indisponível.') };
    }
    return { status: 'ok' as const, figure };
  }

  onStep(value: number | undefined): void {
    if (typeof value === 'number' && value !== this.step()) {
      this.step.set(value);
    }
  }

  async onFiles(event: { files?: File[] }): Promise<void> {
    const files = event.files ?? [];
    for (const file of files) {
      const header = await readHeader(file);
      if (!header.length) {
        continue;
      }
      const lower = file.name.toLowerCase();
      if (lower.includes('tax')) {
        this.uploadForm.controls.taxonomyPath.setValue(file.name);
      } else if (lower.includes('asv') || lower.includes('feature') || lower.includes('otu')) {
        this.uploadForm.controls.asvPath.setValue(file.name);
      } else {
        this.uploadForm.controls.metadataPath.setValue(file.name);
        this.columns.set(header);
        if (header.includes('sample_id')) {
          this.uploadForm.controls.sampleColumn.setValue('sample_id');
        } else if (header[0]) {
          this.uploadForm.controls.sampleColumn.setValue(header[0]);
        }
        const group = header.find((column) => /group|biome|compartment/i.test(column));
        if (group) {
          this.uploadForm.controls.groupColumn.setValue(group);
        }
      }
    }
  }

  goColumns(activate: (step: number) => void): void {
    if (this.uploadForm.controls.metadataPath.invalid || this.uploadForm.controls.asvPath.invalid || this.uploadForm.controls.taxonomyPath.invalid) {
      this.uploadForm.markAllAsTouched();
      return;
    }
    activate(2);
  }

  async goValidate(activate: (step: number) => void): Promise<void> {
    if (this.uploadForm.controls.sampleColumn.invalid) {
      this.uploadForm.markAllAsTouched();
      return;
    }
    await this.loadPreview();
    activate(3);
  }

  async applyNorm(): Promise<void> {
    if (this.normForm.invalid) {
      this.normForm.markAllAsTouched();
      return;
    }
    this.busy.set(true);
    try {
      this.pipeline.set(await this.repository.applyNormalization(this.normForm.getRawValue()));
      this.messages.add({ severity: 'success', summary: t('Normalização'), detail: t('A configuração foi registrada.') });
    } catch (error) {
      this.messages.add({ severity: 'error', summary: t('Normalização'), detail: messageOf(error) });
    } finally {
      this.busy.set(false);
    }
  }

  async confirm(): Promise<void> {
    if (this.uploadForm.invalid) {
      this.uploadForm.markAllAsTouched();
      return;
    }
    this.busy.set(true);
    try {
      const raw = this.uploadForm.getRawValue();
      const outcome = await this.repository.confirmIngest({
        ...raw,
        metadataColumns: this.columns()
      });
      this.outcome.set(outcome);
      this.messages.add({
        severity: outcome.success ? 'success' : 'error',
        summary: t('Ingestão'),
        detail: outcome.success ? 'Metadata, ASV e taxonomia aceitos.' : outcome.error
      });
      await this.reload();
    } finally {
      this.busy.set(false);
    }
  }

  private async reload(): Promise<void> {
    const pipeline = await this.repository.pipeline();
    this.pipeline.set(pipeline);
    this.preview.set(pipeline.qc);
    this.normForm.patchValue(pipeline.normalization);
    if (pipeline.qc.columns.length) {
      this.columns.set(pipeline.qc.columns);
    }
  }

  private async loadPreview(): Promise<void> {
    const raw = this.uploadForm.getRawValue();
    this.preview.set(await this.repository.previewIngest({ ...raw, metadataColumns: this.columns() }));
  }
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : t('Falha inesperada.');
}

function readHeader(file: File): Promise<string[]> {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result ?? '');
      const line = text.split(/\r?\n/, 1)[0] ?? '';
      resolve(line.split(/[\t,]/).map((column) => column.trim()).filter(Boolean));
    };
    reader.onerror = () => resolve([]);
    reader.readAsText(file.slice(0, 8192));
  });
}
