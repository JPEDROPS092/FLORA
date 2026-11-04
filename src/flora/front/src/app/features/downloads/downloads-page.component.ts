import { NgTemplateOutlet } from '@angular/common';
import { RouterLink } from '@angular/router';
import { Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { INSTITUTIONS } from '../../shared/brand.data';
import { MascotComponent } from '../../shared/mascot.component';
import { TechBadgeComponent } from '../../shared/tech-badge.component';
import { MessageService, PrimeTemplate } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { DrawerModule } from 'primeng/drawer';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TableModule } from 'primeng/table';
import { TabsModule } from 'primeng/tabs';
import { TagModule } from 'primeng/tag';

import { FloraRepository } from '../../core/data/flora.repository';
import { CatalogEntry, LocalState, DownloadJob, DownloadRequest, MetadataPreview, SampleMap } from '../../core/models/domain';
import { SampleMapComponent } from '../../shared/sample-map.component';
import { TPipe } from '../../core/i18n/t.pipe';
import { t } from '../../core/i18n/i18n';

interface FilterOption {
  value: string;
  label: string;
}

@Component({
  selector: 'flora-downloads',
  standalone: true,
  imports: [
    RouterLink,
    SampleMapComponent,
    NgTemplateOutlet,
    FormsModule,
    PrimeTemplate,
    TPipe,
    MascotComponent,
    TechBadgeComponent,
    ReactiveFormsModule,
    ButtonModule,
    DrawerModule,
    InputNumberModule,
    InputTextModule,
    SelectModule,
    TableModule,
    TabsModule,
    TagModule
  ],
  template: `
    <section class="page">
      <header class="page-heading">
        <div>
          <p class="kicker">{{ 'Downloads' | t }}</p>
          <h1>{{ 'Biblioteca de datasets' | t }}</h1>
          <p class="lede">{{ 'Catálogo público com foco na Amazônia. A prévia mostra metadados; o download grava um job.' | t }}</p>
        </div>
        <div class="head-side">
          <p-tag [value]="mocked() ? t('Dados mockados') : t('API HTTP')" severity="secondary" />
          <flora-mascot name="fishing" [size]="110" [alt]="'Mascote FLORA pescando dados' | t" />
        </div>
      </header>

      <div class="inst-row" [attr.aria-label]="'Instituições de origem dos datasets' | t">
        @for (i of institutions; track i.name) { <flora-tech-badge [inst]="i" /> }
      </div>

      <p-tabs [value]="tab()" (valueChange)="setTab($event)">
        <p-tablist>
          <p-tab value="library">{{ 'Biblioteca' | t }}</p-tab>
          <p-tab value="history">{{ 'Histórico' | t }}</p-tab>
        </p-tablist>
      </p-tabs>

      @if (tab() === 'library') {
        <article class="surface library">
          <div class="filter-row">
            <form class="lib-search" (ngSubmit)="loadCatalog()">
              <input pInputText name="q" [ngModel]="query()" (ngModelChange)="query.set($event)" [placeholder]="'Buscar por título, acesso ou lugar' | t" [attr.aria-label]="'Buscar estudos' | t" />
              <p-button type="submit" icon="pi pi-search" [label]="'Buscar' | t" [loading]="loading()" />
            </form>
            <button type="button" class="amazon-chip" [class.on]="amazonia()" (click)="toggleAmazon()">{{ 'Amazônia' | t }}</button>
          </div>
          <div class="filter-row selects">
            <p-select [options]="biomeOptions" [ngModel]="biome()" (ngModelChange)="setFilter('biome', $event)" optionLabel="label" optionValue="value" appendTo="body" [placeholder]="'Bioma' | t" [attr.aria-label]="'Filtrar por bioma' | t" />
            <p-select [options]="hostOptions" [ngModel]="host()" (ngModelChange)="setFilter('host', $event)" optionLabel="label" optionValue="value" appendTo="body" [placeholder]="'Hospedeiro' | t" [attr.aria-label]="'Filtrar por hospedeiro' | t" />
            <p-select [options]="regionOptions" [ngModel]="region()" (ngModelChange)="setFilter('region', $event)" optionLabel="label" optionValue="value" appendTo="body" [placeholder]="'Região' | t" [attr.aria-label]="'Filtrar por região' | t" />
            <p-select [options]="seqOptions" [ngModel]="seqType()" (ngModelChange)="setFilter('seq', $event)" optionLabel="label" optionValue="value" appendTo="body" [placeholder]="'Sequenciamento' | t" [attr.aria-label]="'Filtrar por tipo de sequenciamento' | t" />
          </div>
          @if (libError()) { <p class="field-error" role="alert">{{ libError() }}</p> }

          @if (amazonStudies().length) {
            <section class="amazon-band">
              <div>
                <h2>{{ 'Amazônia' | t }}</h2>
                <p class="muted">{{ 'Estudos com amostras na bacia, conferidos na MGnify ou no ENA.' | t }}</p>
              </div>
              <div class="lib-grid">
                @for (study of amazonStudies(); track study.id) { <ng-container *ngTemplateOutlet="card; context: { $implicit: study }" /> }
              </div>
            </section>
          }

          @if (otherStudies().length) {
            <section class="other-band">
              @if (amazonStudies().length) { <h2>{{ 'Outros conjuntos' | t }}</h2> }
              <div class="lib-grid">
                @for (study of otherStudies(); track study.id) { <ng-container *ngTemplateOutlet="card; context: { $implicit: study }" /> }
              </div>
            </section>
          }

          @if (!loading() && !studies().length) {
            <div class="empty">
              <flora-mascot name="binoculars" [size]="120" [alt]="'Mascote FLORA procurando datasets' | t" />
              <p>{{ 'Nenhum dataset com esses filtros.' | t }}</p>
            </div>
          }
        </article>
      } @else {
        <article class="surface">
          <div class="section-title"><h2>{{ 'Pedidos' | t }}</h2></div>
          <p-table [value]="jobs()" dataKey="id">
            <ng-template pTemplate="header">
              <tr><th>{{ 'Fonte' | t }}</th><th>{{ 'Estado' | t }}</th><th>{{ 'Quando' | t }}</th><th>{{ 'Detalhe' | t }}</th><th>{{ 'Artefatos' | t }}</th></tr>
            </ng-template>
            <ng-template pTemplate="body" let-job>
              <tr>
                <td>{{ job.source }}</td>
                <td [class]="job.status === 'failed' ? 'status-fail' : 'status-pass'">{{ job.status }}</td>
                <td>{{ job.createdAt }}</td>
                <td>{{ job.detail }}</td>
                <td>{{ artifactPaths(job) }}</td>
              </tr>
            </ng-template>
            <ng-template pTemplate="emptymessage"><tr><td colspan="5">{{ 'Nenhum pedido.' | t }}</td></tr></ng-template>
          </p-table>
        </article>

        <details class="manual">
          <summary>{{ 'Pedido manual (avançado)' | t }}</summary>
          <section class="split">
            <form class="surface filters" [formGroup]="synthetic" (ngSubmit)="submit('synthetic')">
              <h2>{{ 'Sintético' | t }}</h2>
              <div class="field"><label for="synDir">{{ 'Diretório' | t }}</label><input id="synDir" pInputText formControlName="outputDir" /></div>
              <div class="field"><label for="synSamples">{{ 'Amostras' | t }}</label><p-inputnumber inputId="synSamples" formControlName="samples" [min]="4" [fluid]="true" /></div>
              <div class="field"><label for="synFeatures">{{ 'ASVs' | t }}</label><p-inputnumber inputId="synFeatures" formControlName="features" [min]="10" [fluid]="true" /></div>
              <div class="field"><label for="synSeed">{{ 'Seed' | t }}</label><p-inputnumber inputId="synSeed" formControlName="seed" [fluid]="true" /></div>
              <p-button type="submit" [label]="'Gerar' | t" [loading]="busy()" />
            </form>
            <form class="surface filters" [formGroup]="emp" (ngSubmit)="submit('emp')">
              <h2>{{ 'EMP' | t }}</h2>
              <div class="field"><label for="empDir">{{ 'Diretório' | t }}</label><input id="empDir" pInputText formControlName="outputDir" /></div>
              <div class="field"><label for="empBiome">{{ 'Filtro de bioma' | t }}</label><input id="empBiome" pInputText formControlName="biome" /></div>
              <div class="field"><label for="empMax">{{ 'Máximo de amostras' | t }}</label><p-inputnumber inputId="empMax" formControlName="maxSamples" [min]="1" [fluid]="true" /></div>
              <p-button type="submit" [label]="'Pedir EMP' | t" [loading]="busy()" />
            </form>
            <form class="surface filters" [formGroup]="mgnify" (ngSubmit)="submit('mgnify')">
              <h2>{{ 'MGnify' | t }}</h2>
              <div class="field">
                <label for="study">{{ 'Accession do estudo' | t }}</label>
                <input id="study" pInputText formControlName="studyAccession" />
                @if (mgnify.controls.studyAccession.invalid && mgnify.controls.studyAccession.touched) {
                  <small class="field-error">{{ 'Informe o accession, por exemplo MGYS00005779.' | t }}</small>
                }
              </div>
              <div class="field"><label for="mgBiome">{{ 'Bioma' | t }}</label><input id="mgBiome" pInputText formControlName="biome" /></div>
              <div class="field"><label for="mgDir">{{ 'Diretório' | t }}</label><input id="mgDir" pInputText formControlName="outputDir" /></div>
              <p-button type="submit" [label]="'Pedir MGnify' | t" [loading]="busy()" />
            </form>
            <form class="surface filters" [formGroup]="sra" (ngSubmit)="submit('sra')">
              <h2>{{ 'SRA' | t }}</h2>
              <div class="field">
                <label for="accessions">{{ 'Accessions' | t }}</label>
                <input id="accessions" pInputText formControlName="accessions" [placeholder]="'SRR000001, SRR000002' | t" />
                @if (sra.controls.accessions.invalid && sra.controls.accessions.touched) {
                  <small class="field-error">{{ 'Liste ao menos um accession.' | t }}</small>
                }
              </div>
              <div class="field"><label for="sraDir">{{ 'Diretório' | t }}</label><input id="sraDir" pInputText formControlName="outputDir" /></div>
              <p-button type="submit" [label]="'Pedir SRA' | t" [loading]="busy()" />
            </form>
          </section>
        </details>
      }

      <ng-template #card let-study>
        <button type="button" class="study" (click)="open(study)">
          <div class="study-head">
            <code class="acc">{{ study.accession }}</code>
            @if (study.highlight === 'amazonia') { <p-tag [value]="t('Amazônia')" severity="success" /> }
            <p-tag [value]="seqLabel(study.seqType)" severity="secondary" />
            @if (study.localState !== 'none') { <p-tag [value]="localLabel(study.localState)" [severity]="localSeverity(study.localState)" /> }
          </div>
          <h3>{{ study.titlePt }}</h3>
          <p class="official">{{ study.title }}</p>
          <div class="meta">
            <span>{{ study.nSamples }} {{ 'amostras' | t }}</span>
            @if (study.biomeLabel) { <span>{{ study.biomeLabel }}</span> }
            @if (study.regionLabel) { <span>{{ study.regionLabel }}</span> }
            @if (study.marker) { <span>{{ study.marker }}@if (study.markerRegion) { · {{ study.markerRegion }} }</span> }
          </div>
          <span class="verified">{{ 'Verificado em' | t }} {{ study.verifiedAt }}</span>
        </button>
      </ng-template>

      <p-drawer [visible]="selected() !== null" (visibleChange)="onDrawer($event)" [header]="selected()?.titlePt ?? ''" position="right" [style]="{ width: 'min(560px, 100vw)' }">
        @if (selected(); as study) {
          <div class="drawer">
            <p class="official">{{ study.title }}</p>
            <p>{{ study.description }}</p>
            <div class="meta">
              <span><code>{{ study.accession }}</code></span>
              @if (study.bioproject) { <span>{{ study.bioproject }}</span> }
              @if (study.secondary) { <span>{{ study.secondary }}</span> }
              @if (study.centre) { <span>{{ study.centre }}</span> }
              @if (study.platform) { <span>{{ study.platform }}</span> }
            </div>
            <p><strong>{{ 'Licença' | t }}.</strong> {{ study.license || study.licenseNote || t('Não informada.') }}</p>
            @if (study.citation || study.citationDoi) {
              <p>
                <strong>{{ 'Citação' | t }}.</strong> {{ study.citation }}
                @if (study.citationDoi) { <a [href]="'https://doi.org/' + study.citationDoi" target="_blank" rel="noopener noreferrer">{{ study.citationDoi }}</a> }
              </p>
            }
            <p class="muted">{{ study.downloadNote }}</p>
            @if (study.files.length) {
              <ul class="files">
                @for (file of study.files; track file.url) {
                  <li>{{ file.label }}@if (file.size) { <span class="muted"> · {{ formatSize(file.size) }}</span> }</li>
                }
              </ul>
            }
            @if (study.url) { <p><a [href]="study.url" target="_blank" rel="noopener noreferrer">{{ 'Ver na fonte' | t }}</a></p> }
            <div class="picked-actions">
              <p-button icon="pi pi-download" [label]="'Baixar' | t" [disabled]="!study.importable" [loading]="downloadState() === 'running'" (onClick)="downloadCurrent()" />
              @if (downloadState() === 'completed') { <span class="status-pass">{{ 'Download concluído' | t }}</span> }
              @if (downloadState() === 'failed') { <span class="status-fail">{{ downloadDetail() || t('Falha no download.') }}</span> }
              @if (study.localState !== 'none') { <p-tag [value]="localLabel(study.localState)" [severity]="localSeverity(study.localState)" /> }
            </div>
            @if (study.localState === 'ready') {
              <p class="ok-note">{{ 'Metadata, tabela de abundância e taxonomia já estão no disco.' | t }} <a routerLink="/pipeline">{{ 'Ingerir no Pipeline' | t }}</a></p>
            } @else if (study.localState === 'metadata_only' || study.localState === 'partial') {
              <p class="warn-note" role="status">{{ 'Só os metadados foram baixados: sem tabela de abundância e taxonomia não há o que analisar.' | t }}</p>
            }
            @if (study.source === 'ena' || study.localState === 'metadata_only') {
              <p class="warn-note" role="note">
                {{ 'Este estudo é de leituras brutas (FASTQ). O FLORA só analisa tabelas já processadas (ASV/OTU + taxonomia): processe com QIIME 2 ou DADA2 e depois ingira.' | t }}
                <a routerLink="/engines">{{ 'Motores de análise' | t }}</a>
              </p>
            }
            <h3>{{ 'Mapa das amostras' | t }}</h3>
            <flora-sample-map [map]="sampleMap()" [height]="340" />
            <h3>{{ 'Prévia dos metadados' | t }}</h3>
            @if (previewLoading()) { <p class="muted">{{ 'Carregando…' | t }}</p> }
            @if (previewError()) { <p class="field-error" role="alert">{{ previewError() }}</p> }
            @if (preview(); as table) {
              @if (table.truncated) { <p class="muted">{{ 'Mostrando as primeiras linhas. O arquivo pode ter mais.' | t }}</p> }
              <div class="preview-wrap">
                <table>
                  <thead><tr>@for (col of table.columns; track col) { <th>{{ col }}</th> }</tr></thead>
                  <tbody>
                    @for (row of table.rows; track $index) {
                      <tr>@for (col of table.columns; track col) { <td>{{ row[col] }}</td> }</tr>
                    }
                  </tbody>
                </table>
              </div>
            }
          </div>
        }
      </p-drawer>
    </section>
  `,
  styles: `
    .library { display: grid; gap: 14px; }
    .muted { color: var(--flora-muted); font-size: .86rem; }
    .ok-note { color: var(--flora-ok); font-size: .86rem; }
    .warn-note { color: var(--flora-warn); font-size: .86rem; border-left: 3px solid var(--flora-warn); padding-left: 8px; }
    .filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    .filter-row.selects p-select { min-width: 160px; flex: 1; }
    .lib-search { display: flex; gap: 8px; flex: 1; min-width: 240px; }
    .lib-search input { flex: 1; }
    .amazon-chip { border: 1px solid var(--flora-primary); background: var(--flora-surface); color: var(--flora-primary); border-radius: 999px; padding: 6px 14px; cursor: pointer; font: inherit; font-weight: 650; }
    .amazon-chip.on { background: var(--flora-primary); color: white; }
    .amazon-band { display: grid; gap: 10px; border: 1px solid color-mix(in srgb, var(--flora-primary) 45%, var(--flora-border)); background: var(--flora-primary-soft); border-radius: var(--radius); padding: 12px; }
    .amazon-band h2, .other-band h2 { font-size: 1rem; color: var(--flora-primary); }
    .other-band { display: grid; gap: 10px; }
    .lib-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }
    .study { border: 1px solid var(--flora-border); border-radius: var(--radius); padding: 12px; display: grid; gap: 6px; align-content: start; background: var(--flora-surface); text-align: left; cursor: pointer; width: 100%; }
    .study:hover { border-color: var(--flora-primary); }
    .study-head { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
    .acc { font-weight: 650; color: var(--flora-primary); }
    .study h3 { font-size: .95rem; font-weight: 650; margin: 0; }
    .official { margin: 0; font-size: .78rem; color: var(--flora-muted); }
    .meta { display: flex; gap: 6px; flex-wrap: wrap; font-size: .76rem; color: var(--flora-muted); }
    .meta span { background: var(--flora-bg); border: 1px solid var(--flora-border); border-radius: 999px; padding: 1px 8px; }
    .verified { font-size: .75rem; color: var(--flora-ok); }
    .empty { display: grid; justify-items: center; gap: 8px; padding: 12px; color: var(--flora-muted); }
    .drawer { display: grid; gap: 10px; }
    .drawer h3 { font-size: .95rem; }
    .files { margin: 0; padding-left: 18px; display: grid; gap: 4px; }
    .picked-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
    .preview-wrap { overflow: auto; max-height: 320px; border: 1px solid var(--flora-border); border-radius: var(--radius); }
    .preview-wrap table { border-collapse: collapse; font-size: .78rem; min-width: 100%; }
    .preview-wrap th, .preview-wrap td { border-bottom: 1px solid var(--flora-border); padding: 4px 8px; text-align: left; white-space: nowrap; }
    .manual { margin-top: 12px; }
    .manual > summary { cursor: pointer; font-weight: 600; margin-bottom: 10px; }
  `
})
export class DownloadsPageComponent {
  protected readonly t = t;
  protected readonly institutions = INSTITUTIONS;
  private readonly repository = inject(FloraRepository);
  private readonly messages = inject(MessageService);
  private readonly fb = inject(FormBuilder);

  readonly jobs = signal<DownloadJob[]>([]);
  readonly busy = signal(false);
  readonly mocked = signal(true);
  readonly tab = signal<'library' | 'history'>('library');
  readonly query = signal('');
  readonly biome = signal('');
  readonly host = signal('');
  readonly region = signal('');
  readonly seqType = signal('');
  readonly amazonia = signal(false);
  readonly studies = signal<CatalogEntry[]>([]);
  readonly loading = signal(false);
  readonly libError = signal('');
  readonly selected = signal<CatalogEntry | null>(null);
  readonly preview = signal<MetadataPreview | null>(null);
  readonly previewLoading = signal(false);
  readonly sampleMap = signal<SampleMap | null>(null);
  readonly previewError = signal('');
  readonly downloadState = signal<'idle' | 'running' | 'completed' | 'failed'>('idle');
  readonly downloadDetail = signal('');

  readonly amazonStudies = computed(() => this.studies().filter((study) => study.highlight === 'amazonia'));
  readonly otherStudies = computed(() => this.studies().filter((study) => study.highlight !== 'amazonia'));

  readonly biomeOptions: FilterOption[] = [
    { value: '', label: t('Todos os biomas') },
    { value: 'solo', label: t('Solo') },
    { value: 'agua-doce', label: t('Água doce') },
    { value: 'sedimento', label: t('Sedimento') },
    { value: 'marinho', label: t('Marinho') },
    { value: 'humano', label: t('Humano') },
    { value: 'camundongo', label: t('Camundongo') },
    { value: 'global', label: t('Global') },
    { value: 'sintetico', label: t('Sintético') },
    { value: 'multiplo', label: t('Rio e pluma') }
  ];
  readonly hostOptions: FilterOption[] = [
    { value: '', label: t('Todos os hospedeiros') },
    { value: 'ambiental', label: t('Ambiental') },
    { value: 'humano', label: t('Humano') },
    { value: 'camundongo', label: t('Camundongo') },
    { value: 'zooplancton', label: t('Zooplâncton') }
  ];
  readonly regionOptions: FilterOption[] = [
    { value: '', label: t('Todas as regiões') },
    { value: 'amazonia', label: t('Amazônia') },
    { value: 'carajas', label: t('Carajás') },
    { value: 'pluma', label: t('Pluma do Amazonas') },
    { value: 'oceano', label: t('Oceano') },
    { value: 'atacama', label: t('Atacama') },
    { value: 'global', label: t('Global') },
    { value: 'brasil', label: t('Brasil (sintético)') }
  ];
  readonly seqOptions: FilterOption[] = [
    { value: '', label: t('Todos os tipos') },
    { value: 'amplicon', label: t('Amplicon') },
    { value: 'WGS', label: 'WGS' },
    { value: 'misto', label: t('Misto') }
  ];

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
    void this.loadCatalog();
  }

  setTab(value: string | number | undefined): void {
    this.tab.set(value === 'history' ? 'history' : 'library');
  }

  setFilter(kind: 'biome' | 'host' | 'region' | 'seq', value: string): void {
    if (kind === 'biome') this.biome.set(value ?? '');
    if (kind === 'host') this.host.set(value ?? '');
    if (kind === 'region') this.region.set(value ?? '');
    if (kind === 'seq') this.seqType.set(value ?? '');
    void this.loadCatalog();
  }

  toggleAmazon(): void {
    this.amazonia.update((on) => !on);
    void this.loadCatalog();
  }

  async loadCatalog(): Promise<void> {
    this.loading.set(true);
    this.libError.set('');
    try {
      this.studies.set(await this.repository.catalog({
        q: this.query().trim(),
        biome: this.biome(),
        host: this.host(),
        region: this.region(),
        seqType: this.seqType(),
        amazonia: this.amazonia()
      }));
    } catch (error) {
      this.studies.set([]);
      this.libError.set(error instanceof Error ? error.message : t('Falha na busca.'));
    } finally {
      this.loading.set(false);
    }
  }

  async open(study: CatalogEntry): Promise<void> {
    this.selected.set(study);
    this.preview.set(null);
    this.previewError.set('');
    this.downloadState.set('idle');
    this.downloadDetail.set('');
    this.previewLoading.set(true);
    this.sampleMap.set(null);
    void this.loadMap(study);
    try {
      this.preview.set(await this.repository.datasetMetadata(study.source, study.accession));
    } catch (error) {
      this.previewError.set(error instanceof Error ? error.message : t('Não foi possível carregar a prévia.'));
    } finally {
      this.previewLoading.set(false);
    }
  }

  /** Shown whenever the dataset is on disk and has coordinates; refreshed after each download. */
  private async loadMap(study: CatalogEntry): Promise<void> {
    try {
      const map = await this.repository.datasetMap(study.source, study.accession);
      if (this.selected()?.accession === study.accession) this.sampleMap.set(map);
    } catch {
      this.sampleMap.set(null);
    }
  }

  onDrawer(visible: boolean): void {
    if (!visible) this.selected.set(null);
  }

  async downloadCurrent(): Promise<void> {
    const study = this.selected();
    if (!study) return;
    this.downloadState.set('running');
    this.downloadDetail.set('');
    const job = await this.repository.downloadDataset(study.source, study.accession);
    const failed = job.status === 'failed';
    this.downloadState.set(failed ? 'failed' : 'completed');
    this.downloadDetail.set(job.detail);
    this.messages.add({
      severity: failed ? 'error' : 'success',
      summary: study.accession,
      detail: failed ? job.detail : t('Download concluído')
    });
    await this.reload();
    if (!failed) {
      await this.loadMap(study);
      await this.loadCatalog();
      const fresh = this.studies().find((item) => item.source === study.source && item.accession === study.accession);
      if (fresh) this.selected.set(fresh);
    }
  }

  artifactPaths(job: DownloadJob): string {
    const paths = job.artifacts.map((item) => item.path).filter(Boolean);
    return paths.length ? paths.join(', ') : '—';
  }

  localLabel(state: LocalState): string {
    return { ready: t('Pronto para análise'), metadata_only: t('Só metadados'), partial: t('Parcial'), none: t('Não baixado') }[state];
  }

  localSeverity(state: LocalState): 'success' | 'warn' | 'secondary' {
    return state === 'ready' ? 'success' : state === 'none' ? 'secondary' : 'warn';
  }

  seqLabel(value: string): string {
    if (value === 'amplicon') return t('Amplicon');
    if (value === 'misto') return t('Misto');
    return value || '—';
  }

  formatSize(bytes: number): string {
    if (bytes >= 1_000_000) return `${Math.round(bytes / 1_000_000)} MB`;
    if (bytes >= 1_000) return `${Math.round(bytes / 1_000)} KB`;
    return `${bytes} B`;
  }

  private async send(request: DownloadRequest): Promise<void> {
    const job = await this.repository.requestDownload(request);
    this.messages.add({ severity: job.status === 'failed' ? 'error' : 'success', summary: job.source, detail: job.detail });
    await this.reload();
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
      await this.send(request);
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
