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
import { ExploreSchema, IngestOutcome, IngestPreview, LocalDataset, PipelineSnapshot, UploadKind } from '../../core/models/domain';
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

      <article class="surface project-bar">
        @if (schema()?.project; as project) {
          <p>{{ 'Projeto ativo' | t }}: <strong>{{ project.name }}</strong> · {{ stageLabel(project.stage) }} · <strong>{{ currentSamples() | number }}</strong> {{ 'amostras já no banco' | t }}</p>
        } @else {
          <p>{{ 'Nenhum projeto ativo. A ingestão grava no banco da pasta de trabalho.' | t }}</p>
        }
        <p-button type="button" severity="danger" [outlined]="true" icon="pi pi-trash" [label]="'Limpar dados do projeto' | t" [disabled]="currentSamples() === 0 || busy()" (onClick)="clearData()" />
      </article>

      <ol class="workflow">
        @for (stage of pipeline()?.stages ?? []; track stage.id) {
          <li [class]="stage.status">
            <span class="tool">{{ stage.tool }}</span>
            <strong>{{ stage.name }}</strong>
            <em>{{ stage.detail }}</em>
          </li>
        }
      </ol>

      <article class="surface">
        <div class="section-title">
          <h2>{{ 'Rodar tudo' | t }}</h2>
          <p>{{ 'QC, diversidade, rarefação, Kruskal-Wallis, PERMANOVA e volcano, com o tempo de cada etapa.' | t }}</p>
        </div>
        @if (groupValues().length > 2) {
          <p class="note" role="status">{{ 'Há {n} grupos. O volcano compara só dois: escolha o grupo A e o grupo B.' | t: { n: groupValues().length } }}</p>
          <div class="contrast">
            <label>{{ 'Grupo A' | t }}
              <select [value]="contrastA()" (change)="contrastA.set(selectValue($event))">
                <option value="">{{ 'escolher' | t }}</option>
                @for (group of groupValues(); track group) { <option [value]="group">{{ group }}</option> }
              </select>
            </label>
            <label>{{ 'Grupo B' | t }}
              <select [value]="contrastB()" (change)="contrastB.set(selectValue($event))">
                <option value="">{{ 'escolher' | t }}</option>
                @for (group of groupValues(); track group) { <option [value]="group">{{ group }}</option> }
              </select>
            </label>
          </div>
        }
        @if (currentSamples() > 0 && currentSamples() < 6) {
          <p class="note" role="status">{{ 'Há só {n} amostras. Testes com menos de 6 têm pouco poder.' | t: { n: currentSamples() } }}</p>
        }
        @if (groupValues().length > 0 && groupValues().length < 2) {
          <p class="note" role="status">{{ 'É preciso pelo menos 2 grupos para Kruskal-Wallis, PERMANOVA e volcano.' | t }}</p>
        }
        <div class="actions">
          <p-button type="button" icon="pi pi-play" [label]="'Rodar tudo' | t" [loading]="running()" [disabled]="!pipeline()?.ingested" (onClick)="runAll()" />
        </div>
        @if (runLog().length) {
          <ol class="run-log">
            @for (step of runLog(); track step.id) {
              <li [class]="step.status">
                <strong>{{ step.label }}</strong>
                <span>{{ step.status === 'running' ? ('em andamento' | t) : step.status }}</span>
                @if (step.ms) { <span>{{ step.ms | number }} ms</span> }
                @if (step.detail) { <em>{{ step.detail }}</em> }
              </li>
            }
          </ol>
        }
      </article>

      <section class="split">
        <article class="surface">
          <div class="section-title">
            <h2>{{ 'Normalização' | t }}</h2>
            <p>{{ 'Rarefação, transformação e prevalência mínima.' | t }}</p>
          </div>
          <form class="filters" [formGroup]="normForm" (ngSubmit)="applyNorm()">
            <div class="field">
              <label for="depth">{{ 'Rarefação (reads)' | t }}</label>
              <p-inputnumber inputId="depth" formControlName="rarefactionDepth" [min]="1" [fluid]="true" />
              @if (reads(); as depth) {
                <small class="note">{{ 'Reads por amostra: mínimo {min}, mediana {med}, máximo {max}. Sugestão: {sug} (o mínimo, para não descartar amostras).' | t: { min: depth.min, med: depth.median, max: depth.max, sug: suggestedDepth() } }}</small>
              }
              @if (normForm.controls.rarefactionDepth.invalid && normForm.controls.rarefactionDepth.touched) {
                <small class="field-error">{{ 'Informe uma profundidade de pelo menos 1 read.' | t }}</small>
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
                <div class="origin-tabs" role="tablist" [attr.aria-label]="'Origem dos dados' | t">
                  @for (tab of origins; track tab.id) {
                    <button type="button" role="tab" class="origin-tab" [class.on]="origin() === tab.id" [attr.aria-selected]="origin() === tab.id" (click)="origin.set(tab.id)">
                      <i [class]="tab.icon"></i> {{ tab.label | t }}
                    </button>
                  }
                </div>
                <form class="filters" [formGroup]="uploadForm">
                  @switch (origin()) {
                    @case ('library') {
                      <p class="note">{{ 'Datasets já baixados no projeto ativo ou na pasta de trabalho. Só os completos (metadata, ASV e taxonomia) podem ser ingeridos.' | t }}</p>
                      @if (hiddenDatasetCount()) {
                        <p class="note">{{ '{n} datasets só com metadata ou só com leituras brutas ficam ocultos: processe-os no QIIME 2 ou DADA2 antes de ingerir.' | t: { n: hiddenDatasetCount() } }}</p>
                      }
                      <div class="ds-list">
                        @for (ds of analyzableDatasets(); track ds.id) {
                          <button type="button" class="ds" [class.picked]="selectedDataset() === ds.id" [disabled]="!ds.complete" (click)="chooseDataset(ds)">
                            <span class="ds-head"><strong>{{ ds.label }}</strong>
                              <p-tag [value]="originLabel(ds.origin)" severity="secondary" />
                            </span>
                            <span class="ds-meta">
                              @if (ds.samples) { <span>{{ ds.samples }} {{ 'amostras' | t }}</span> }
                              <span [class.ok]="ds.files.metadata">{{ 'Metadata' | t }}</span>
                              <span [class.ok]="ds.files.asv">{{ 'Tabela ASV' | t }}</span>
                              <span [class.ok]="ds.files.taxonomy">{{ 'Taxonomia' | t }}</span>
                            </span>
                            @if (ds.rawReadsOnly) {
                              <small class="warn">{{ 'Só leituras brutas (FASTQ): precisam ser processadas no QIIME2/DADA2 antes de entrar aqui.' | t }}</small>
                            } @else if (!ds.complete) {
                              <small class="warn">{{ 'Faltam arquivos:' | t }} {{ ds.missing.join(', ') }}</small>
                            }
                          </button>
                        } @empty {
                          <p class="note">{{ loadingDatasets() ? t('Procurando datasets…') : t('Nenhum dataset baixado ainda.') }}</p>
                        }
                      </div>
                      <div class="actions">
                        <a routerLink="/downloads"><i class="pi pi-download"></i> {{ 'Baixar mais estudos na biblioteca' | t }}</a>
                        <p-button type="button" severity="secondary" icon="pi pi-refresh" [label]="'Atualizar' | t" (onClick)="loadDatasets()" />
                      </div>
                    }
                    @case ('computer') {
                      <p class="note">{{ 'Escolha os arquivos no seu computador (.tsv, .csv, .txt, .biom). Eles são copiados para a pasta de trabalho do FLORA.' | t }}</p>
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
                      @if (uploading()) { <small class="note">{{ 'Enviando…' | t }}</small> }
                    }
                    @case ('manual') {
                      <p class="note">{{ 'Informe caminhos que o servidor do FLORA consiga ler.' | t }}</p>
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
                    }
                  }
                  @if (origin() !== 'manual') {
                    <dl class="chosen" [attr.aria-label]="'Arquivos escolhidos' | t">
                      <dt>{{ 'Metadata' | t }}</dt><dd>{{ uploadForm.controls.metadataPath.value || '—' }}</dd>
                      <dt>{{ 'Tabela ASV' | t }}</dt><dd>{{ uploadForm.controls.asvPath.value || '—' }}</dd>
                      <dt>{{ 'Taxonomia' | t }}</dt><dd>{{ uploadForm.controls.taxonomyPath.value || '—' }}</dd>
                    </dl>
                  }
                  @if (uploadForm.invalid && uploadForm.touched) {
                    <small class="field-error">{{ 'Escolha metadata, tabela ASV e taxonomia para continuar.' | t }}</small>
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
                    <small class="note">{{ 'O formato (largo ou longo) é detectado pelo cabeçalho. O interruptor só vale quando os dois são possíveis.' | t }}</small>
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
                @if (currentSamples() > 0) {
                  <p class="replace-note" role="note">{{ 'Atenção: o projeto ativo já tem {n} amostras. Confirmar substitui esses dados pelos novos; se algo falhar, os dados atuais são mantidos.' | t: { n: currentSamples() } }}</p>
                }
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
  `,
  styles: `
    .origin-tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
    .origin-tab { border: 1px solid var(--flora-border); background: var(--flora-surface); color: var(--flora-text); border-radius: 999px; padding: 6px 14px; cursor: pointer; font: inherit; font-size: .86rem; }
    .origin-tab.on { background: var(--flora-primary-soft); border-color: var(--flora-primary); color: var(--flora-primary); font-weight: 600; }
    .ds-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 8px; }
    .ds { text-align: left; font: inherit; color: inherit; display: grid; gap: 6px; padding: 10px 12px; border: 1px solid var(--flora-border); border-radius: var(--radius); background: var(--flora-surface); cursor: pointer; }
    .ds:disabled { opacity: .6; cursor: not-allowed; }
    .ds.picked { border-color: var(--flora-primary); box-shadow: 0 0 0 2px var(--flora-primary-soft); }
    .ds-head { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
    .ds-meta { display: flex; gap: 6px; flex-wrap: wrap; font-size: .76rem; color: var(--flora-muted); }
    .ds-meta span { border: 1px solid var(--flora-border); border-radius: 999px; padding: 1px 8px; }
    .ds-meta span.ok { color: var(--flora-ok); border-color: var(--flora-ok); }
    .warn { color: var(--flora-warn); }
    .replace-note { color: var(--flora-warn); border-left: 3px solid var(--flora-warn); padding-left: 8px; font-size: .86rem; }
    .project-bar { display: flex; justify-content: space-between; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 16px; }
    .project-bar p { margin: 0; }
    .contrast { display: flex; gap: 12px; flex-wrap: wrap; margin: 8px 0; }
    .contrast label { display: grid; gap: 4px; font-size: .82rem; color: var(--flora-muted); }
    .contrast select { font: inherit; padding: 6px 8px; border-radius: 8px; border: 1px solid var(--flora-border); background: var(--flora-surface); color: inherit; }
    .run-log { list-style: none; padding: 0; margin: 12px 0 0; display: grid; gap: 6px; }
    .run-log li { display: flex; gap: 10px; flex-wrap: wrap; align-items: baseline; font-size: .86rem; border-left: 3px solid var(--flora-border); padding-left: 8px; }
    .run-log li.ok { border-color: var(--flora-ok); }
    .run-log li.erro, .run-log li.ignorado { border-color: var(--flora-warn); }
    .run-log em { color: var(--flora-muted); font-style: normal; }
    .chosen { display: grid; grid-template-columns: max-content 1fr; gap: 2px 12px; font-size: .82rem; margin: 6px 0 0; }
    .chosen dt { color: var(--flora-muted); }
    .chosen dd { margin: 0; word-break: break-all; }
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
  readonly schema = signal<ExploreSchema | null>(null);
  readonly running = signal(false);
  readonly runLog = signal<{ id: string; label: string; status: string; ms: number; detail: string }[]>([]);
  readonly contrastA = signal('');
  readonly contrastB = signal('');
  readonly columns = signal<string[]>(['sample_id', 'group', 'host', 'site']);
  readonly step = signal(1);
  readonly busy = signal(false);
  readonly currentSamples = signal(0);
  readonly origins: { id: 'library' | 'computer' | 'manual'; label: string; icon: string }[] = [
    { id: 'library', label: 'Biblioteca (baixados)', icon: 'pi pi-database' },
    { id: 'computer', label: 'Meu computador', icon: 'pi pi-upload' },
    { id: 'manual', label: 'Caminho manual', icon: 'pi pi-pencil' }
  ];
  readonly origin = signal<'library' | 'computer' | 'manual'>('library');
  readonly datasets = signal<LocalDataset[]>([]);
  readonly selectedDataset = signal('');
  readonly loadingDatasets = signal(false);
  readonly uploading = signal(false);
  readonly methods = [
    { label: 'CLR', value: 'clr' },
    { label: 'TSS', value: 'tss' },
    { label: t('Sem transformação'), value: 'none' }
  ];

  readonly uploadForm = this.fb.nonNullable.group({
    metadataPath: ['', Validators.required],
    asvPath: ['', Validators.required],
    taxonomyPath: ['', Validators.required],
    sampleColumn: ['sample_id', Validators.required],
    groupColumn: ['group', Validators.required],
    wideFormat: [true]
  });

  readonly normForm = this.fb.nonNullable.group({
    rarefactionDepth: [10000, [Validators.required, Validators.min(1)]],
    method: this.fb.nonNullable.control<'clr' | 'tss' | 'none'>('clr', Validators.required),
    minPrevalence: [0.05, [Validators.required, Validators.min(0), Validators.max(1)]],
    minAbundance: [10, [Validators.required, Validators.min(0)]]
  });

  constructor() {
    void this.reload();
    void this.loadDatasets();
  }

  reads(): ExploreSchema['reads'] {
    return this.schema()?.reads ?? null;
  }

  suggestedDepth(): number {
    const depth = this.reads();
    return depth && depth.min > 0 ? Math.max(1, Math.floor(depth.min)) : this.normForm.controls.rarefactionDepth.value;
  }

  stageLabel(stage: string): string {
    return stage === 'ingested' ? t('Pronto para análise') : stage === 'raw_downloaded' ? t('Arquivos brutos') : t('Sem dados');
  }

  analyzableDatasets(): LocalDataset[] {
    return this.datasets().filter((ds) => ds.analyzable !== false && ds.complete && !ds.rawReadsOnly && !ds.metadataOnly);
  }

  hiddenDatasetCount(): number {
    return this.datasets().length - this.analyzableDatasets().length;
  }

  groupValues(): string[] {
    const columns = this.schema()?.groupColumns ?? [];
    const wanted = this.uploadForm.controls.groupColumn.value;
    const column = columns.find((item) => item.name === wanted) ?? columns[0];
    return column?.values.map((value) => value.value) ?? [];
  }

  selectValue(event: Event): string {
    return (event.target as HTMLSelectElement).value;
  }

  originLabel(origin: LocalDataset['origin']): string {
    return origin === 'project' ? t('Projeto') : origin === 'upload' ? t('Enviado') : t('Baixado');
  }

  async loadDatasets(): Promise<void> {
    this.loadingDatasets.set(true);
    try {
      this.datasets.set(await this.repository.datasets());
    } catch (error) {
      this.datasets.set([]);
      this.messages.add({ severity: 'error', summary: t('Biblioteca'), detail: messageOf(error) });
    } finally {
      this.loadingDatasets.set(false);
    }
  }

  chooseDataset(ds: LocalDataset): void {
    if (!ds.complete) return;
    this.selectedDataset.set(ds.id);
    this.uploadForm.patchValue({
      metadataPath: ds.files.metadata ?? '',
      asvPath: ds.files.asv ?? '',
      taxonomyPath: ds.files.taxonomy ?? ''
    });
    this.applyColumns(ds.columns);
  }

  private applyColumns(header: string[]): void {
    if (!header.length) return;
    this.columns.set(header);
    this.uploadForm.controls.sampleColumn.setValue(header.includes('sample_id') ? 'sample_id' : header[0]);
    const group = header.find((column) => /group|biome|compartment/i.test(column));
    if (group) this.uploadForm.controls.groupColumn.setValue(group);
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
    this.uploading.set(true);
    try {
      for (const file of event.files ?? []) {
        const lower = file.name.toLowerCase();
        const kind: UploadKind = lower.includes('tax')
          ? 'taxonomy'
          : lower.includes('asv') || lower.includes('feature') || lower.includes('otu') || lower.endsWith('.biom')
            ? 'asv'
            : 'metadata';
        try {
          const stored = await this.repository.uploadFile(file, kind);
          if (kind === 'taxonomy') this.uploadForm.controls.taxonomyPath.setValue(stored.path);
          else if (kind === 'asv') this.uploadForm.controls.asvPath.setValue(stored.path);
          else {
            this.uploadForm.controls.metadataPath.setValue(stored.path);
            this.applyColumns(stored.columns);
          }
          this.selectedDataset.set('');
        } catch (error) {
          this.messages.add({ severity: 'error', summary: file.name, detail: messageOf(error) });
        }
      }
    } finally {
      this.uploading.set(false);
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

  async clearData(): Promise<void> {
    const count = this.currentSamples();
    const ok = window.confirm(t('Apagar metadata, ASV, taxonomia e diversidade das {n} amostras do projeto ativo? Os arquivos baixados permanecem.', { n: count }));
    if (!ok) return;
    this.busy.set(true);
    try {
      await this.repository.clearProjectData();
      this.outcome.set(null);
      this.messages.add({ severity: 'success', summary: t('Dados limpos'), detail: t('O banco do projeto foi esvaziado. Os arquivos baixados continuam na pasta.') });
      await this.reload();
    } catch (error) {
      this.messages.add({ severity: 'error', summary: t('Limpar dados'), detail: messageOf(error) });
    } finally {
      this.busy.set(false);
    }
  }

  async runAll(): Promise<void> {
    if (!this.pipeline()?.ingested) {
      this.messages.add({ severity: 'warn', summary: t('Rodar tudo'), detail: t('Ingira metadata, ASV e taxonomia antes de rodar a análise.') });
      return;
    }
    const samples = this.currentSamples();
    const groups = this.groupValues();
    if (samples > 0 && samples < 6) {
      const ok = window.confirm(t('Há só {n} amostras. Testes com menos de 6 têm pouco poder. Continuar mesmo assim?', { n: samples }));
      if (!ok) return;
    }
    if (groups.length > 2 && (!this.contrastA() || !this.contrastB() || this.contrastA() === this.contrastB())) {
      this.messages.add({ severity: 'warn', summary: t('Volcano'), detail: t('Há {n} grupos. Escolha dois diferentes para o volcano antes de rodar tudo.', { n: groups.length }) });
      return;
    }
    const columns = this.schema()?.groupColumns ?? [];
    const wanted = this.uploadForm.controls.groupColumn.value;
    const group = columns.find((column) => column.name === wanted)?.name ?? columns[0]?.name ?? (wanted || 'biome');
    const depth = this.normForm.controls.rarefactionDepth.value;
    const steps: { id: string; label: string; run: () => Promise<unknown> }[] = [
      { id: 'qc', label: t('Controle de qualidade'), run: () => this.repository.analysis('qc', { min_reads: depth }) },
      { id: 'diversity', label: t('Diversidade'), run: () => this.repository.computeDiversity(depth) },
      { id: 'rarefaction', label: t('Curvas de rarefação'), run: () => this.repository.analysis('rarefaction', { group_by: group, depth }) },
      { id: 'alpha', label: t('Kruskal-Wallis'), run: () => this.repository.analysis('alpha_stats', { group_by: group }) },
      { id: 'beta', label: t('PERMANOVA + PERMDISP'), run: () => this.repository.analysis('beta_stats', { group_by: group, permutations: 199 }) },
      {
        id: 'volcano', label: t('Volcano'), run: () => this.repository.analysis('volcano', {
          group_by: group, rank: 'genus', a: this.contrastA() || groups[0] || '', b: this.contrastB() || groups[1] || ''
        })
      }
    ];
    this.running.set(true);
    const log: { id: string; label: string; status: string; ms: number; detail: string }[] = [];
    try {
      for (const step of steps) {
        if (step.id !== 'qc' && step.id !== 'diversity' && step.id !== 'rarefaction' && groups.length < 2) {
          log.push({ id: step.id, label: step.label, status: 'ignorado', ms: 0, detail: t('É preciso pelo menos 2 grupos.') });
          this.runLog.set([...log]);
          continue;
        }
        const started = performance.now();
        this.runLog.set([...log, { id: step.id, label: step.label, status: 'running', ms: 0, detail: '' }]);
        try {
          const result = await step.run() as Record<string, unknown>;
          log.push({ id: step.id, label: step.label, status: 'ok', ms: Math.round(performance.now() - started), detail: summarizeStep(step.id, result) });
        } catch (error) {
          log.push({ id: step.id, label: step.label, status: 'erro', ms: Math.round(performance.now() - started), detail: messageOf(error) });
        }
        this.runLog.set([...log]);
      }
    } finally {
      this.running.set(false);
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
    const [schema, pipeline] = await Promise.all([
      this.repository.exploreSchema().catch(() => null),
      this.repository.pipeline()
    ]);
    this.schema.set(schema);
    this.currentSamples.set(schema?.counts.samples ?? 0);
    this.pipeline.set(pipeline);
    this.preview.set(pipeline.qc);
    const depth = this.normForm.controls.rarefactionDepth;
    const pristine = depth.pristine;
    this.normForm.patchValue(pipeline.normalization);
    if (pristine) depth.markAsPristine();
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
  const text = error instanceof Error ? error.message : t('Falha inesperada.');
  if (text.includes('Traceback') || text.length > 400) {
    return t('A etapa falhou. Confira se o projeto tem tabela ASV e pelo menos dois grupos. Detalhe: {d}', { d: text.split('\n')[0].slice(0, 180) });
  }
  return text;
}

function summarizeStep(id: string, result: Record<string, unknown>): string {
  if (id === 'qc') {
    const summary = (result['summary'] ?? {}) as Record<string, unknown>;
    return t('{n} amostras, corte {c}, {b} abaixo', { n: Number(summary['samples'] ?? 0), c: Number(summary['min_reads'] ?? 0), b: Number(summary['below_depth'] ?? 0) });
  }
  if (id === 'diversity') {
    const reads = (result['reads'] ?? {}) as Record<string, unknown>;
    return t('profundidade {d} ({s}), {k} mantidas, {x} descartadas', {
      d: Number(result['sampling_depth'] ?? 0), s: String(result['depth_source'] ?? ''), k: Number(result['retained'] ?? 0), x: Number(result['dropped_count'] ?? 0)
    }) + (reads['min'] ? t(' · reads {min}–{max}', { min: Number(reads['min']), max: Number(reads['max']) }) : '');
  }
  if (id === 'alpha') {
    const tests = (result['tests'] as unknown[]) ?? [];
    const caution = ((result['caution'] as string[]) ?? []).join(' ');
    return t('{n} testes', { n: tests.length }) + (caution ? ` · ${caution}` : '');
  }
  if (id === 'beta') {
    const perm = (result['permanova'] ?? {}) as Record<string, unknown>;
    return `PERMANOVA p=${Number(perm['p'] ?? 0).toFixed(4)}`;
  }
  if (id === 'volcano') return `${result['a'] ?? ''} vs ${result['b'] ?? ''}`;
  return '';
}
