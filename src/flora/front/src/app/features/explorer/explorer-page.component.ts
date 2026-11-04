import { DecimalPipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { AbstractControl, FormBuilder, FormsModule, ReactiveFormsModule, ValidationErrors, Validators } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, ParamMap, RouterLink } from '@angular/router';
import { TreeNode } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { MultiSelectModule } from 'primeng/multiselect';
import { SelectModule } from 'primeng/select';
import { TableModule, TableLazyLoadEvent } from 'primeng/table';
import { TabsModule } from 'primeng/tabs';
import { TagModule } from 'primeng/tag';
import { TreeModule } from 'primeng/tree';
import { PrimeTemplate } from 'primeng/api';

import { FloraRepository } from '../../core/data/flora.repository';
import { ChartResult, DatasetTable, ExploreSchema, ExplorationBundle, ExplorerView, ResearchProject, TablePage, TaxonNode } from '../../core/models/domain';
import { downloadBlob } from '../../shared/download';
import { PlotCardComponent } from '../../shared/plot-card.component';
import { AnalysisPanelComponent } from './analysis-panel.component';
import { TPipe } from '../../core/i18n/t.pipe';
import { t } from '../../core/i18n/i18n';

@Component({
  selector: 'flora-explorer',
  standalone: true,
  imports: [TPipe, 
    DecimalPipe,
    ReactiveFormsModule,
    FormsModule,
    ButtonModule,
    InputNumberModule,
    InputTextModule,
    RouterLink,
    MultiSelectModule,
    SelectModule,
    TableModule,
    TabsModule,
    TagModule,
    TreeModule,
    PrimeTemplate,
    PlotCardComponent,
    AnalysisPanelComponent
  ],
  template: `
    <section class="page">
      <header class="page-heading">
        <div>
          <p class="kicker">{{ 'Scientific Explorer' | t }}</p>
          <h1>{{ 'Ordenação, diversidade e composição' | t }}</h1>
          <p class="lede">{{ 'Os filtros valem para todas as vistas. A figura ativa ocupa o centro.' | t }}</p>
        </div>
        @if (bundle()?.mocked) { <p-tag [value]="'Dados mockados' | t" severity="secondary" /> }
      </header>

      <div class="surface context" [attr.aria-label]="'Projeto e dataset' | t">
        <div class="ctx-project">
          <label for="project">{{ 'Projeto' | t }}</label>
          <p-select inputId="project" [options]="projects()" [ngModel]="schema()?.project?.id" (ngModelChange)="switchProject($event)" optionLabel="name" optionValue="id" [placeholder]="'Nenhum projeto ativo' | t" appendTo="body" [style]="{ minWidth: '240px' }" />
        </div>
        @if (schema(); as sc) {
          <div class="ctx-stats">
            @if (sc.project) { <p-tag [value]="stageLabel(sc.project.stage)" [severity]="sc.project.stage === 'ingested' ? 'success' : 'warn'" /> }
            @if (sc.project?.synthetic) { <p-tag [value]="'Sintético' | t" severity="secondary" /> }
            <span><strong>{{ sc.counts.samples | number }}</strong> {{ 'amostras' | t }}</span>
            <span><strong>{{ sc.counts.asvs | number }}</strong> ASVs</span>
            <span><strong>{{ sc.counts.taxa | number }}</strong> {{ 'táxons' | t }}</span>
            @if (sc.reads) { <span>{{ 'reads por amostra:' | t }} <strong>{{ sc.reads.min | number }}</strong>–<strong>{{ sc.reads.max | number }}</strong></span> }
          </div>
        }
      </div>

      @if (schema() && schema()!.counts.samples === 0) {
        <article class="surface empty-state">
          <h2>{{ 'Este projeto ainda não tem dados para explorar.' | t }}</h2>
          <p>{{ 'Baixe um estudo na biblioteca ou escolha arquivos no pipeline; depois volte aqui.' | t }}</p>
          <div class="actions">
            <a routerLink="/downloads"><i class="pi pi-download"></i> {{ 'Biblioteca de estudos' | t }}</a>
            <a routerLink="/pipeline"><i class="pi pi-cog"></i> {{ 'Pipeline' | t }}</a>
            <a routerLink="/projects"><i class="pi pi-folder"></i> {{ 'Projetos' | t }}</a>
          </div>
        </article>
      } @else {

      <div class="explorer">
        <form class="surface filters" [formGroup]="filters" (ngSubmit)="apply()">
          <div class="field">
            <label for="groupBy">{{ 'Agrupar por' | t }}</label>
            <p-select inputId="groupBy" [options]="groupColumns()" formControlName="groupBy" optionLabel="name" optionValue="name" appendTo="body" [fluid]="true" [placeholder]="'Coluna de metadata' | t" />
          </div>
          <div class="field">
            <label for="groups">{{ 'Grupos' | t }}</label>
            <p-multiselect inputId="groups" [options]="groupOptions()" optionLabel="label" optionValue="value" formControlName="groups" display="chip" appendTo="body" [fluid]="true" />
            @if (filters.controls.groups.invalid && filters.controls.groups.touched) {
              <small class="field-error">{{ 'Selecione ao menos um grupo.' | t }}</small>
            }
          </div>
          <div class="field">
            <label for="metric">{{ 'Métrica alfa' | t }}</label>
            <p-select inputId="metric" [options]="metrics" formControlName="metric" optionLabel="label" optionValue="value" appendTo="body" [fluid]="true" />
          </div>
          <div class="field">
            <label for="normalize">{{ 'Transformação' | t }}</label>
            <p-select inputId="normalize" [options]="normalizations" formControlName="normalize" optionLabel="label" optionValue="value" appendTo="body" [fluid]="true" />
          </div>
          <div class="field">
            <label for="rank">{{ 'Rank taxonômico' | t }}</label>
            <p-select inputId="rank" [options]="ranks" formControlName="rank" optionLabel="label" optionValue="value" appendTo="body" [fluid]="true" />
          </div>
          <div class="field">
            <label for="distance">{{ 'Distância beta' | t }}</label>
            <p-select inputId="distance" [options]="distances" formControlName="distance" optionLabel="label" optionValue="value" appendTo="body" [fluid]="true" />
          </div>
          <div class="field">
            <label for="topN">{{ 'Top N' | t }}</label>
            <p-inputnumber inputId="topN" formControlName="topN" [min]="2" [max]="12" [fluid]="true" />
          </div>
          <div class="actions">
            <p-button type="submit" [label]="'Aplicar filtros' | t" icon="pi pi-filter" [loading]="busy()" />
            <p-button type="button" [label]="'Exportar tabela' | t" severity="secondary" [text]="true" (onClick)="exportTable()" />
          </div>
          <p class="note">{{ bundle()?.sampleCount | number }} {{ 'amostras na rarefação ·' | t }} {{ bundle()?.asvCount | number }} {{ 'ASVs no estudo.' | t }}</p>
        </form>

        <div class="stack">
          <p-tabs [value]="view()" (valueChange)="onView($event)">
            <p-tablist>
              <p-tab value="pcoa">{{ 'PCoA' | t }}</p-tab>
              <p-tab value="alpha">{{ 'Alfa' | t }}</p-tab>
              <p-tab value="beta">{{ 'Beta' | t }}</p-tab>
              <p-tab value="taxonomy">{{ 'Taxonomia' | t }}</p-tab>
              <p-tab value="relations">{{ 'Relações' | t }}</p-tab>
              <p-tab value="qc">{{ 'Qualidade' | t }}</p-tab>
              <p-tab value="rarefaction">{{ 'Rarefação' | t }}</p-tab>
              <p-tab value="stats">{{ 'Estatística' | t }}</p-tab>
              <p-tab value="data"><i class="pi pi-table"></i> {{ 'Dados' | t }}</p-tab>
            </p-tablist>
          </p-tabs>

          @if (view() === 'qc' || view() === 'rarefaction' || view() === 'stats') {
          <article class="surface">
            <div class="section-title"><h2>{{ viewTitle() }}</h2></div>
            <flora-analysis-panel [mode]="panelMode()" [groupColumns]="groupColumns()" [initialGroup]="groupBy()" [minReadsInput]="rarefactionDepth" (changed)="onDataChanged()" />
          </article>
          } @else if (view() === 'data') {
          <article class="surface">
            <div class="section-title"><h2>{{ 'Dataset carregado' | t }}</h2><p>{{ 'O que o projeto ativo tem no DuckDB: amostras, features e taxonomia.' | t }}</p></div>
            <div class="data-overview">
              <div class="stat"><strong>{{ schema()?.counts?.samples | number }}</strong><span>{{ 'amostras' | t }}</span></div>
              <div class="stat"><strong>{{ schema()?.counts?.asvs | number }}</strong><span>ASVs</span></div>
              <div class="stat"><strong>{{ schema()?.counts?.observations | number }}</strong><span>{{ 'observações' | t }}</span></div>
              <div class="stat"><strong>{{ schema()?.counts?.taxa | number }}</strong><span>{{ 'táxons' | t }}</span></div>
              @if (schema()?.reads; as r) { <div class="stat"><strong>{{ r.median | number:'1.0-0' }}</strong><span>{{ 'mediana de reads' | t }}</span></div> }
            </div>
            <div class="data-bar">
              @for (tab of dataTabs; track tab.id) {
                <button type="button" class="chip" [class.on]="dataTable() === tab.id" (click)="setDataTable(tab.id)">{{ tab.label | t }}</button>
              }
              <input pInputText [ngModel]="dataQuery()" (ngModelChange)="onDataQuery($event)" [placeholder]="'Buscar por amostra, bioma, gênero…' | t" [attr.aria-label]="'Buscar nos dados' | t" />
              <p-button type="button" severity="secondary" [text]="true" icon="pi pi-download" [label]="'Exportar CSV' | t" (onClick)="exportDataPage()" />
              <a class="export-link" [href]="exportUrl('features_tsv')" download>TSV</a>
              <a class="export-link" [href]="exportUrl('biom')" download>BIOM</a>
              <a class="export-link" [href]="exportUrl('taxonomy_tsv')" download>{{ 'Taxonomia' | t }}</a>
            </div>
            <p-table [value]="dataPage()?.rows ?? []" [lazy]="true" (onLazyLoad)="loadData($event)" [paginator]="true" [rows]="25" [totalRecords]="dataPage()?.total ?? 0" [loading]="dataLoading()" [scrollable]="true" styleClass="nowrap">
              <ng-template pTemplate="header">
                <tr>@for (c of dataPage()?.columns ?? []; track c) { <th>{{ c }}</th> }</tr>
              </ng-template>
              <ng-template pTemplate="body" let-row>
                <tr>@for (cell of row; track $index) { <td>{{ cell }}</td> }</tr>
              </ng-template>
              <ng-template pTemplate="emptymessage"><tr><td [attr.colspan]="(dataPage()?.columns?.length ?? 1)">{{ 'Nada encontrado.' | t }}</td></tr></ng-template>
            </p-table>
          </article>
          } @else {
          <article class="surface stage" [class.with-tree]="view() === 'taxonomy'">
            @if (view() === 'taxonomy') {
              <div class="tree-pane">
                <div class="section-title"><h2>{{ 'Árvore resumida' | t }}</h2></div>
                @if (tree().length) {
                  <p-tree [value]="tree()" />
                } @else {
                  <p class="note">{{ bundle()?.note || t('Sem árvore estruturada nesta fonte.') }}</p>
                }
              </div>
            }
            <div>
              <div class="section-title">
                <h2>{{ viewTitle() }}</h2>
                <p>{{ view() === 'beta' || view() === 'pcoa' ? bundle()?.distanceNote : '' }}</p>
                @if (view() !== 'beta') {
                  <div class="chart-group">
                    <label for="chartGroup">{{ 'Agrupar por' | t }}</label>
                    <p-select inputId="chartGroup" [options]="groupColumns()" optionLabel="name" optionValue="name" [ngModel]="groupBy()" (ngModelChange)="changeGroup($event)" appendTo="body" size="small" />
                  </div>
                }
              </div>
              <flora-plot [result]="activeChart()" [height]="560" />
            </div>
          </article>
          }

          @if (view() !== 'data' && view() !== 'qc' && view() !== 'rarefaction' && view() !== 'stats') {
          <article class="surface">
            <div class="section-title">
              <h2>{{ 'Comparação de grupos' | t }}</h2>
              <p>{{ 'Mesmos filtros da figura.' | t }}</p>
            </div>
            <p-table [value]="bundle()?.comparisons ?? []">
              <ng-template pTemplate="header">
                <tr><th>{{ 'Grupo' | t }}</th><th>{{ 'n' | t }}</th><th>{{ 'Shannon' | t }}</th><th>{{ 'DP' | t }}</th><th>{{ 'ASVs observados' | t }}</th></tr>
              </ng-template>
              <ng-template pTemplate="body" let-row>
                <tr>
                  <td>{{ row.group }}</td>
                  <td>{{ row.n }}</td>
                  <td>{{ row.shannonMean | number:'1.2-2' }}</td>
                  <td>{{ row.shannonSd | number:'1.2-2' }}</td>
                  <td>{{ row.observedMean | number }}</td>
                </tr>
              </ng-template>
              <ng-template pTemplate="emptymessage"><tr><td colspan="5">{{ 'Sem resumo numérico nesta fonte.' | t }}</td></tr></ng-template>
            </p-table>
          </article>

          <article class="surface">
            <div class="section-title">
              <h2>{{ 'Táxons diferenciais' | t }}</h2>
              <p>{{ 'log2 fold change mockado no rank selecionado, quando existir.' | t }}</p>
            </div>
            <p-table [value]="bundle()?.differential ?? []" [rows]="8" [paginator]="true">
              <ng-template pTemplate="header">
                <tr><th>{{ 'Táxon' | t }}</th><th>{{ 'log2FC' | t }}</th><th>{{ 'p' | t }}</th><th>{{ 'q' | t }}</th><th>{{ 'Maior em' | t }}</th><th>{{ 'Contraste' | t }}</th></tr>
              </ng-template>
              <ng-template pTemplate="body" let-row>
                <tr>
                  <td>{{ row.taxon }}</td>
                  <td>{{ row.log2FoldChange | number:'1.2-2' }}</td>
                  <td>{{ row.pValue | number:'1.4-4' }}</td>
                  <td>{{ row.qValue | number:'1.3-3' }}</td>
                  <td>{{ row.higherIn }}</td>
                  <td>{{ row.contrast }}</td>
                </tr>
              </ng-template>
              <ng-template pTemplate="emptymessage"><tr><td colspan="6">{{ bundle()?.note || t('Sem contrastes.') }}</td></tr></ng-template>
            </p-table>
          </article>
          }
        </div>
      </div>
      }
    </section>
  `,
  styles: `
    .context { display: flex; gap: 16px; align-items: end; flex-wrap: wrap; justify-content: space-between; }
    .ctx-project { display: grid; gap: 4px; }
    .ctx-project label { font-size: .78rem; color: var(--flora-muted); }
    .ctx-stats { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; font-size: .88rem; }
    .empty-state { text-align: center; padding: 32px 16px; display: grid; gap: 8px; justify-items: center; }
    .data-overview { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 12px; }
    .stat { border: 1px solid var(--flora-border); border-radius: var(--radius); padding: 10px 12px; display: grid; gap: 2px; }
    .stat strong { font-size: 1.25rem; }
    .stat span { color: var(--flora-muted); font-size: .76rem; }
    .data-bar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
    .chip { border: 1px solid var(--flora-border); background: var(--flora-surface); color: var(--flora-text); border-radius: 999px; padding: 5px 14px; cursor: pointer; font: inherit; font-size: .84rem; }
    .chip.on { background: var(--flora-primary-soft); border-color: var(--flora-primary); color: var(--flora-primary); font-weight: 600; }
    .data-bar input { flex: 1; min-width: 180px; }
    .nowrap td, .nowrap th { white-space: nowrap; }
    .chart-group { display: flex; gap: 8px; align-items: center; margin-top: 6px; }
    .chart-group label { font-size: .8rem; color: var(--flora-muted); }
    .export-link { font-size: .84rem; border: 1px solid var(--flora-border); border-radius: 999px; padding: 3px 12px; text-decoration: none; }
  `
})
export class ExplorerPageComponent {
  protected readonly t = t;
  private readonly repository = inject(FloraRepository);
  private readonly route = inject(ActivatedRoute);
  private readonly fb = inject(FormBuilder);

  readonly view = signal<ExplorerView>('pcoa');
  readonly bundle = signal<ExplorationBundle | null>(null);
  readonly tree = signal<TreeNode[]>([]);
  readonly busy = signal(false);

  readonly schema = signal<ExploreSchema | null>(null);
  readonly projects = signal<ResearchProject[]>([]);
  readonly groupColumns = computed(() => this.schema()?.groupColumns ?? []);
  readonly groupBy = signal('');
  readonly groupOptions = computed(() => {
    const col = this.groupColumns().find((c) => c.name === this.groupBy());
    return (col?.values ?? []).map((v) => ({ label: `${v.value} (${v.count})`, value: v.value }));
  });
  readonly dataTabs: { id: DatasetTable; label: string }[] = [
    { id: 'samples', label: 'Amostras' },
    { id: 'features', label: 'Features (ASVs)' },
    { id: 'taxonomy', label: 'Taxonomia' }
  ];
  readonly dataTable = signal<DatasetTable>('samples');
  readonly dataQuery = signal('');
  readonly dataPage = signal<TablePage | null>(null);
  readonly dataLoading = signal(false);
  private dataOffset = 0;
  private dataTimer: ReturnType<typeof setTimeout> | undefined;
  readonly metrics = [
    { label: 'Shannon', value: 'shannon' },
    { label: 'Simpson', value: 'simpson' },
    { label: t('Observados'), value: 'observed' },
    { label: 'Chao1', value: 'chao1' }
  ];
  readonly normalizations = [
    { label: 'CLR', value: 'clr' },
    { label: 'TSS', value: 'tss' },
    { label: t('Sem transformação'), value: 'none' }
  ];
  readonly ranks = [
    { label: t('Filo'), value: 'phylum' },
    { label: t('Classe'), value: 'class' },
    { label: t('Ordem'), value: 'order' },
    { label: t('Família'), value: 'family' },
    { label: t('Gênero'), value: 'genus' }
  ];
  readonly distances = [
    { label: 'Bray–Curtis', value: 'braycurtis' },
    { label: 'Jaccard', value: 'jaccard' }
  ];

  readonly filters = this.fb.nonNullable.group({
    groupBy: this.fb.nonNullable.control(''),
    groups: this.fb.nonNullable.control<string[]>([], { validators: [nonEmptyGroups] }),
    metric: this.fb.nonNullable.control<'shannon' | 'simpson' | 'observed' | 'chao1'>('shannon'),
    normalize: this.fb.nonNullable.control<'clr' | 'tss' | 'none'>('clr'),
    rank: this.fb.nonNullable.control<'phylum' | 'class' | 'order' | 'family' | 'genus'>('genus'),
    distance: this.fb.nonNullable.control<'braycurtis' | 'jaccard'>('braycurtis'),
    topN: this.fb.nonNullable.control(8, { validators: [Validators.required, Validators.min(2), Validators.max(12)] })
  });

  constructor() {
    const ready = this.loadContext();
    this.filters.controls.groupBy.valueChanges.pipe(takeUntilDestroyed()).subscribe((name) => {
      this.groupBy.set(name);
      this.filters.controls.groups.setValue(this.groupOptions().map((o) => o.value));
    });
    this.route.queryParamMap.pipe(takeUntilDestroyed()).subscribe((params) => {
      void ready.then(() => {
        this.applyParams(params);
        return this.apply();
      });
    });
  }

  readonly rarefactionDepth = 1000;

  panelMode(): 'qc' | 'rarefaction' | 'stats' {
    const v = this.view();
    return v === 'rarefaction' || v === 'stats' ? v : 'qc';
  }

  exportUrl(format: 'features_tsv' | 'biom' | 'taxonomy_tsv'): string {
    return `${this.repository.apiBase}/api/export/dataset?format=${format}`;
  }

  /** Switch the grouping variable straight from a chart and redraw with all of its values. */
  changeGroup(name: string): void {
    this.filters.controls.groupBy.setValue(name);
    void this.apply();
  }

  onDataChanged(): void {
    void this.loadContext().then(() => this.apply());
  }

  stageLabel(stage: string): string {
    return stage === 'ingested' ? t('Ingerido') : stage === 'raw_downloaded' ? t('Só arquivos brutos') : t('Vazio');
  }

  /** Loads the project list and the dataset schema, then seeds the group filters from the real data. */
  private async loadContext(): Promise<void> {
    const [projects, schema] = await Promise.all([this.repository.projects(), this.repository.exploreSchema()]);
    this.projects.set(projects);
    this.schema.set(schema);
    const first = schema.groupColumns[0];
    this.filters.controls.groupBy.setValue(first?.name ?? '', { emitEvent: false });
    this.groupBy.set(first?.name ?? '');
    this.filters.controls.groups.setValue(this.groupOptions().map((o) => o.value));
  }

  async switchProject(id: string | undefined): Promise<void> {
    if (!id || id === this.schema()?.project?.id) return;
    this.busy.set(true);
    try {
      await this.repository.activateProject(id);
      this.bundle.set(null);
      this.dataPage.set(null);
      await this.loadContext();
      if (this.schema()?.counts.samples) await this.apply();
      if (this.view() === 'data') await this.fetchData();
    } finally {
      this.busy.set(false);
    }
  }

  setDataTable(id: DatasetTable): void {
    this.dataTable.set(id);
    this.dataOffset = 0;
    void this.fetchData();
  }

  onDataQuery(value: string): void {
    this.dataQuery.set(value);
    this.dataOffset = 0;
    clearTimeout(this.dataTimer);
    this.dataTimer = setTimeout(() => void this.fetchData(), 300);
  }

  loadData(event: TableLazyLoadEvent): void {
    this.dataOffset = event.first ?? 0;
    void this.fetchData();
  }

  private async fetchData(): Promise<void> {
    this.dataLoading.set(true);
    try {
      this.dataPage.set(await this.repository.exploreTable(this.dataTable(), this.dataQuery(), this.dataOffset, 25));
    } catch {
      this.dataPage.set({ name: this.dataTable(), columns: [], rows: [], total: 0, offset: 0 });
    } finally {
      this.dataLoading.set(false);
    }
  }

  exportDataPage(): void {
    const page = this.dataPage();
    if (!page) return;
    const esc = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`;
    const lines = [page.columns.map(esc).join(','), ...page.rows.map((r) => r.map(esc).join(','))];
    downloadBlob(`${page.name}.csv`, new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' }));
  }

  /** URL contract: ?view=&metric=&normalize=&rank=&distance=&topN=&groups=a,b&question= */
  private applyParams(params: ParamMap): void {
    const question = params.get('question');
    if (question === 'diversity') this.view.set('alpha');
    else if (question === 'differential') this.view.set('taxonomy');
    else if (question === 'clustering') this.view.set('pcoa');

    const view = params.get('view');
    if (view) this.onView(view);

    const patch: Partial<ReturnType<typeof this.filters.getRawValue>> = {};
    const pick = <T extends string>(key: string, allowed: readonly T[]): T | undefined => {
      const v = params.get(key);
      return v && (allowed as readonly string[]).includes(v) ? (v as T) : undefined;
    };
    patch.metric = pick('metric', ['shannon', 'simpson', 'observed', 'chao1']);
    patch.normalize = pick('normalize', ['clr', 'tss', 'none']);
    patch.rank = pick('rank', ['phylum', 'class', 'order', 'family', 'genus']);
    patch.distance = pick('distance', ['braycurtis', 'jaccard']);
    const topN = Number(params.get('topN'));
    if (Number.isFinite(topN) && topN >= 2 && topN <= 12) patch.topN = topN;
    const by = params.get('groupBy');
    if (by && this.groupColumns().some((c) => c.name === by)) {
      this.filters.controls.groupBy.setValue(by);
    }
    const groups = params.get('groups')?.split(',').filter((g) => this.groupOptions().some((o) => o.value === g));
    if (groups?.length) patch.groups = groups;
    const defined = Object.fromEntries(Object.entries(patch).filter(([, v]) => v !== undefined));
    this.filters.patchValue(defined);
  }

  activeChart(): ChartResult | null {
    const bundle = this.bundle();
    if (!bundle) {
      return null;
    }
    const view = this.view();
    return view === 'data' || view === 'qc' || view === 'rarefaction' || view === 'stats' ? null : bundle[view];
  }

  viewTitle(): string {
    switch (this.view()) {
      case 'alpha':
        return t('Diversidade alfa');
      case 'beta':
        return t('Matriz de distância');
      case 'taxonomy':
        return t('Abundância taxonômica');
      case 'relations':
        return t('Co-ocorrência entre gêneros');
      case 'data':
        return t('Dados');
      case 'qc':
        return t('Controle de qualidade');
      case 'rarefaction':
        return t('Curvas de rarefação');
      case 'stats':
        return t('Testes estatísticos');
      default:
        return t('PCoA');
    }
  }

  onView(value: string | number | undefined): void {
    if (value === 'pcoa' || value === 'alpha' || value === 'beta' || value === 'taxonomy' || value === 'relations' || value === 'data' || value === 'qc' || value === 'rarefaction' || value === 'stats') {
      this.view.set(value);
      if (value === 'data' && !this.dataPage()) void this.fetchData();
    }
  }

  async apply(): Promise<void> {
    if (!this.schema()?.counts.samples) return;
    if (this.filters.invalid) {
      this.filters.markAllAsTouched();
      return;
    }
    this.busy.set(true);
    try {
      const bundle = await this.repository.exploration(this.filters.getRawValue());
      this.bundle.set(bundle);
      this.tree.set(bundle.tree.map((node) => this.toNode(node)));
    } finally {
      this.busy.set(false);
    }
  }

  exportTable(): void {
    const rows = this.bundle()?.comparisons ?? [];
    const lines = ['group,n,shannon_mean,shannon_sd,observed_mean'];
    for (const row of rows) {
      lines.push(`${row.group},${row.n},${row.shannonMean},${row.shannonSd},${row.observedMean}`);
    }
    downloadBlob('comparacao-grupos.csv', new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' }));
  }

  private toNode(node: TaxonNode): TreeNode {
    return {
      key: node.key,
      label: node.label,
      expanded: true,
      children: node.children?.map((child) => this.toNode(child))
    };
  }
}

function nonEmptyGroups(control: AbstractControl): ValidationErrors | null {
  return Array.isArray(control.value) && control.value.length > 0 ? null : { required: true };
}
