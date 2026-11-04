import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { CheckboxModule } from 'primeng/checkbox';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { ProgressBarModule } from 'primeng/progressbar';
import { SelectModule } from 'primeng/select';
import { TagModule } from 'primeng/tag';
import { interval } from 'rxjs';

import { FloraRepository } from '../../core/data/flora.repository';
import { ChartResult, EngineConfig, EngineEnvironment, EngineInfo, EngineJob, EngineResults } from '../../core/models/domain';
import { TPipe } from '../../core/i18n/t.pipe';
import { t } from '../../core/i18n/i18n';
import { PlotCardComponent } from '../../shared/plot-card.component';

type Workflow = 'qiime2-dada2' | 'dada2-r' | 'aldex2' | 'ancombc2' | 'vegan' | 'cutadapt-trim' | 'vsearch-otu';

@Component({
  selector: 'flora-engines',
  standalone: true,
  imports: [FormsModule, TPipe, PlotCardComponent, ButtonModule, CheckboxModule, InputNumberModule, InputTextModule, ProgressBarModule, SelectModule, TagModule],
  template: `
    <section class="page">
      <header class="page-heading">
        <div>
          <p class="kicker">{{ 'Motores de análise' | t }}</p>
          <h1>{{ 'QIIME 2, DADA2 e outras ferramentas abertas' | t }}</h1>
          <p class="lede">{{ 'O FLORA analisa tabelas já processadas. Para partir de leituras brutas (FASTQ), ou para testes que ele não traz, ligue ferramentas instaladas nesta máquina.' | t }}</p>
        </div>
        <p-button [label]="'Detectar de novo' | t" icon="pi pi-refresh" severity="secondary" [loading]="detecting()" (onClick)="detect(true)" />
      </header>

      <div class="engine-grid">
        @for (engine of engines(); track engine.id) {
          <article class="surface engine" [class.off]="!engine.available">
            <div class="engine-head">
              <strong>{{ engine.name }}</strong>
              <p-tag [value]="engine.available ? engine.version : t('Não instalado')" [severity]="engine.available ? 'success' : 'secondary'" />
            </div>
            <div class="caps">@for (c of engine.capabilities; track c) { <span>{{ c }}</span> }</div>
            @if (!engine.available) { <small class="muted">{{ engine.install }}</small> }
          </article>
        } @empty {
          <p class="muted">{{ 'Nenhum motor detectado nesta fonte de dados.' | t }}</p>
        }
      </div>

      <article class="surface">
        <div class="section-title">
          <h2>{{ 'Ambientes (conda / Python)' | t }}</h2>
          <p>{{ 'O QIIME 2 e o DADA2 costumam viver em outro ambiente. Aponte para ele e o FLORA usa esses executáveis, sem precisar ativá-lo.' | t }}</p>
        </div>
        @for (env of environments(); track env.prefix) {
          <div class="env">
            <div>
              <strong>{{ env.name }}</strong> <small class="muted">{{ env.prefix }}</small>
              <div class="caps">
                @if (env.qiime) { <span>{{ 'QIIME 2 (CLI)' | t }}</span> }
                @if (env.qiime2PythonApi) { <span>{{ 'QIIME 2 (API Python)' | t }}</span> }
                @if (env.dada2RPackage) { <span>DADA2 (R)</span> }
                @if (env.rscript) { <span>Rscript</span> }
              </div>
            </div>
            <p-button [label]="isInUse(env) ? t('Em uso') : t('Usar este ambiente')" size="small" [severity]="isInUse(env) ? 'success' : 'secondary'" [disabled]="isInUse(env)" (onClick)="useEnvironment(env)" />
          </div>
        } @empty {
          <p class="muted">{{ 'Nenhum ambiente conda com QIIME 2 ou DADA2 foi encontrado nos locais usuais. Informe os caminhos abaixo.' | t }}</p>
        }
        <div class="form">
          <label>{{ 'Python do ambiente do QIIME 2 (API Python)' | t }}<input pInputText [(ngModel)]="cfgPython" placeholder="/home/voce/miniconda3/envs/qiime2/bin/python" /></label>
          <label>{{ 'Executável qiime (CLI)' | t }}<input pInputText [(ngModel)]="cfgQiime" placeholder="/home/voce/miniconda3/envs/qiime2/bin/qiime" /></label>
          <label>{{ 'Rscript (DADA2 em R)' | t }}<input pInputText [(ngModel)]="cfgRscript" placeholder="/usr/bin/Rscript" /></label>
          <div class="inline">
            <p-button [label]="'Salvar ambiente' | t" icon="pi pi-check" [loading]="savingEnv()" (onClick)="saveEnvironment({ qiime: cfgQiime, python: cfgPython, rscript: cfgRscript })" />
            <p-button [label]="'Limpar' | t" severity="secondary" [text]="true" (onClick)="saveEnvironment({})" />
          </div>
          <small class="muted">{{ 'Em uso:' | t }} qiime={{ effective().qiime || '—' }} · python={{ effective().python || '—' }} · Rscript={{ effective().rscript || '—' }}</small>
        </div>
      </article>

      <article class="surface">
        <div class="section-title"><h2>{{ 'Banco taxonômico' | t }}</h2><p>{{ 'Fica registrado no relatório, para quem for reproduzir a análise.' | t }}</p></div>
        <div class="row">
          <p-select [options]="taxonomyOptions()" [ngModel]="taxonomyDb()" (ngModelChange)="saveDb($event)" appendTo="body" [placeholder]="'Não informado' | t" [showClear]="true" [style]="{ minWidth: '240px' }" />
        </div>
      </article>

      <article class="surface">
        <div class="section-title"><h2>{{ 'Rodar um fluxo' | t }}</h2></div>
        <div class="row">
          <p-select [options]="workflows" optionLabel="label" optionValue="value" [(ngModel)]="workflow" appendTo="body" [style]="{ minWidth: '280px' }" />
          @if (!available()) { <p-tag [value]="t('Instale a ferramenta para usar este fluxo')" severity="warn" /> }
        </div>
        <div class="form">
          @switch (workflow) {
            @case ('qiime2-dada2') {
              <label>{{ 'Manifest do QIIME 2 (caminho)' | t }}<input pInputText [(ngModel)]="manifest" placeholder="/dados/manifest.tsv" /></label>
              <label>{{ 'Classificador treinado .qza (opcional)' | t }}<input pInputText [(ngModel)]="classifier" placeholder="/dados/silva-138-classifier.qza" /></label>
              <label>{{ 'Como conectar ao QIIME 2' | t }}
                <p-select [options]="backends" optionLabel="label" optionValue="value" [(ngModel)]="backend" appendTo="body" />
              </label>
              <div class="inline"><p-checkbox inputId="paired" [(ngModel)]="paired" [binary]="true" /><label for="paired">{{ 'Leituras pareadas' | t }}</label>
                <p-checkbox inputId="tree" [(ngModel)]="buildTree" [binary]="true" /><label for="tree">{{ 'Construir árvore (para UniFrac)' | t }}</label></div>
              <div class="inline">
                <label>{{ 'Truncar F' | t }}<p-inputnumber [(ngModel)]="truncF" [min]="0" /></label>
                <label>{{ 'Truncar R' | t }}<p-inputnumber [(ngModel)]="truncR" [min]="0" /></label>
              </div>
            }
            @case ('dada2-r') {
              <label>{{ 'Pasta com os FASTQ (_R1/_R2 ou _1/_2)' | t }}<input pInputText [(ngModel)]="fastqDir" placeholder="/dados/fastq" /></label>
              <label>{{ 'FASTA de referência (SILVA/GTDB para o DADA2)' | t }}<input pInputText [(ngModel)]="refFasta" placeholder="/dados/silva_nr99_v138_train_set.fa.gz" /></label>
              <div class="inline">
                <label>{{ 'Truncar F' | t }}<p-inputnumber [(ngModel)]="truncF" [min]="0" /></label>
                <label>{{ 'Truncar R' | t }}<p-inputnumber [(ngModel)]="truncR" [min]="0" /></label>
              </div>
            }
            @case ('cutadapt-trim') {
              <label>{{ 'Pasta com os FASTQ' | t }}<input pInputText [(ngModel)]="fastqDir" placeholder="/dados/fastq" /></label>
              <label>{{ 'Primer forward (IUPAC)' | t }}<input pInputText [(ngModel)]="fwdPrimer" placeholder="GTGYCAGCMGCCGCGGTAA" /></label>
              <label>{{ 'Primer reverse (opcional, para pareadas)' | t }}<input pInputText [(ngModel)]="revPrimer" placeholder="GGACTACNVGGGTWTCTAAT" /></label>
              <p class="muted">{{ 'Gera um manifest pronto para o fluxo QIIME 2 + DADA2.' | t }}</p>
            }
            @case ('vsearch-otu') {
              <p class="muted">{{ 'Agrupa os ASVs do projeto ativo em OTUs. O FASTA precisa ter os IDs dos ASVs como cabeçalhos.' | t }}</p>
              <label>{{ 'FASTA com as sequências dos ASVs' | t }}<input pInputText [(ngModel)]="fasta" placeholder="/dados/rep-seqs.fasta" /></label>
              <label>{{ 'Identidade' | t }}<p-inputnumber [(ngModel)]="identity" [min]="0.5" [max]="1" [step]="0.01" [minFractionDigits]="2" [maxFractionDigits]="2" /></label>
            }
            @default {
              <p class="muted">{{ 'Usa os dados do projeto ativo.' | t }}</p>
              <label>{{ 'Coluna de agrupamento' | t }}<input pInputText [(ngModel)]="groupBy" placeholder="biome" /></label>
              @if (workflow === 'vegan') {
                <div class="inline">
                  <p-select [options]="veganMetrics" [(ngModel)]="veganMetric" appendTo="body" />
                  <label>{{ 'Permutações' | t }}<p-inputnumber [(ngModel)]="permutations" [min]="99" [max]="99999" [step]="100" /></label>
                </div>
              } @else {
                <div class="inline">
                  <label>{{ 'Grupo A' | t }}<input pInputText [(ngModel)]="groupA" /></label>
                  <label>{{ 'Grupo B' | t }}<input pInputText [(ngModel)]="groupB" /></label>
                </div>
              }
            }
          }
          <div class="inline">
            <label>{{ 'Threads' | t }}<p-inputnumber [(ngModel)]="threads" [min]="1" [max]="64" /></label>
            @if (workflow === 'qiime2-dada2' || workflow === 'dada2-r') { <p-checkbox inputId="ingest" [(ngModel)]="ingest" [binary]="true" /><label for="ingest">{{ 'Ingerir no projeto ativo ao terminar' | t }}</label> }
          </div>
          <div><p-button [label]="'Iniciar' | t" icon="pi pi-play" [disabled]="!available()" [loading]="starting()" (onClick)="start()" /></div>
        </div>
      </article>

      <article class="surface">
        <div class="section-title"><h2>{{ 'Execuções' | t }}</h2></div>
        @for (job of jobs(); track job.id) {
          <div class="job">
            <div class="engine-head">
              <strong>{{ job.kind }}</strong>
              <p-tag [value]="job.status" [severity]="job.status === 'completed' ? 'success' : job.status === 'failed' ? 'danger' : job.status === 'cancelled' ? 'secondary' : 'info'" />
              <small class="muted">{{ job.createdAt }}</small>
              @if (job.status === 'running' || job.status === 'queued') { <p-button [label]="'Cancelar' | t" size="small" severity="danger" [text]="true" (onClick)="cancel(job.id)" /> }
            </div>
            @if (job.status === 'running') { <p-progressbar [value]="job.progress" /><small class="muted">{{ job.step }}</small> }
            @if (job.error) { <p class="field-error" role="alert">{{ job.error }}</p> }
            @if (job.status === 'completed') {
              <ul class="artifacts">@for (a of artifactList(job); track a[0]) { <li><strong>{{ a[0] }}</strong> {{ a[1] }}</li> }</ul>
              @if (job.artifacts['results']) {
                <p-button [label]="results()[job.id] ? t('Ocultar resultados') : t('Ver resultados')" size="small" severity="secondary" (onClick)="toggleResults(job.id)" />
                @if (results()[job.id]; as res) {
                  @if (res.plot) { <flora-plot [result]="plotOf(res)" [height]="320" /> }
                  <div class="table-wrap">
                    <table>
                      <thead><tr>@for (c of shownColumns(res); track c) { <th>{{ c }}</th> }</tr></thead>
                      <tbody>@for (row of res.rows.slice(0, 25); track $index) { <tr>@for (c of shownColumns(res); track c) { <td>{{ fmt(row[c]) }}</td> }</tr> }</tbody>
                    </table>
                  </div>
                  <small class="muted">{{ res.rows.length }} {{ 'de' | t }} {{ res.total }} {{ 'linhas' | t }}</small>
                }
              }
            }
            <details><summary>{{ 'Log' | t }}</summary><pre class="log">{{ job.log.join('\n') }}</pre></details>
          </div>
        } @empty {
          <p class="muted">{{ 'Nenhuma execução ainda.' | t }}</p>
        }
      </article>
    </section>
  `,
  styles: `
    .env { display: flex; justify-content: space-between; gap: 12px; align-items: center; border-top: 1px solid var(--flora-border); padding: 8px 0; }
    .engine-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }
    .engine { display: grid; gap: 6px; align-content: start; }
    .engine.off { opacity: .85; }
    .engine-head { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .caps { display: flex; gap: 6px; flex-wrap: wrap; }
    .caps span { font-size: .72rem; border: 1px solid var(--flora-border); border-radius: 999px; padding: 1px 8px; color: var(--flora-muted); }
    .muted { color: var(--flora-muted); font-size: .84rem; }
    .row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin: 6px 0; }
    .form { display: grid; gap: 10px; max-width: 640px; }
    .form label { display: grid; gap: 4px; font-size: .84rem; color: var(--flora-muted); }
    .inline { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
    .job { border-top: 1px solid var(--flora-border); padding: 10px 0; display: grid; gap: 6px; }
    .log { max-height: 240px; overflow: auto; background: var(--flora-bg); border: 1px solid var(--flora-border); border-radius: var(--radius); padding: 8px; font-size: .75rem; }
    .table-wrap { overflow: auto; max-height: 320px; border: 1px solid var(--flora-border); border-radius: var(--radius); }
    .table-wrap table { border-collapse: collapse; font-size: .78rem; min-width: 100%; }
    .table-wrap th, .table-wrap td { border-bottom: 1px solid var(--flora-border); padding: 4px 8px; text-align: left; white-space: nowrap; }
    .artifacts { margin: 0; padding-left: 18px; font-size: .82rem; word-break: break-all; }
  `
})
export class EnginesPageComponent {
  protected readonly t = t;
  private readonly repository = inject(FloraRepository);
  private readonly messages = inject(MessageService);

  readonly engines = signal<EngineInfo[]>([]);
  readonly jobs = signal<EngineJob[]>([]);
  readonly detecting = signal(false);
  readonly starting = signal(false);
  readonly taxonomyDb = signal('');
  readonly taxonomyOptions = signal<string[]>([]);

  workflow: Workflow = 'qiime2-dada2';
  readonly workflows: { label: string; value: Workflow }[] = [
    { label: 'QIIME 2 + DADA2 (FASTQ → ASVs → taxonomia)', value: 'qiime2-dada2' },
    { label: 'DADA2 em R (FASTQ → ASVs → taxonomia)', value: 'dada2-r' },
    { label: t('ALDEx2 (abundância diferencial)'), value: 'aldex2' },
    { label: t('ANCOM-BC2 (abundância diferencial)'), value: 'ancombc2' },
    { label: t('vegan: PERMANOVA + PERMDISP'), value: 'vegan' },
    { label: t('cutadapt: remover primers'), value: 'cutadapt-trim' },
    { label: t('VSEARCH: agrupar ASVs em OTUs'), value: 'vsearch-otu' }
  ];
  backend: 'cli' | 'python' = 'cli';
  readonly backends = [
    { label: t('CLI do QIIME 2 (comando qiime)'), value: 'cli' },
    { label: t('API Python do QIIME 2 (plugin DADA2)'), value: 'python' }
  ];
  readonly environments = signal<EngineEnvironment[]>([]);
  readonly effective = signal<EngineConfig>({});
  readonly savingEnv = signal(false);
  cfgPython = '';
  cfgQiime = '';
  cfgRscript = '';
  readonly veganMetrics = ['bray_curtis', 'jaccard', 'aitchison'];
  veganMetric = 'bray_curtis';
  permutations = 999;
  fwdPrimer = '';
  revPrimer = '';
  fasta = '';
  identity = 0.97;
  readonly results = signal<Record<string, EngineResults>>({});
  manifest = '';
  classifier = '';
  fastqDir = '';
  refFasta = '';
  groupBy = '';
  groupA = '';
  groupB = '';
  paired = true;
  buildTree = false;
  ingest = true;
  truncF = 240;
  truncR = 200;
  threads = 4;

  readonly available = computed(() => {
    const need = { 'qiime2-dada2': 'qiime2', 'dada2-r': 'dada2', aldex2: 'aldex2', ancombc2: 'ancombc2', vegan: 'vegan', 'cutadapt-trim': 'cutadapt', 'vsearch-otu': 'vsearch' }[this.workflow];
    return this.engines().some((e) => e.id === need && e.available);
  });

  constructor() {
    void this.detect(false);
    void this.refreshJobs();
    void this.loadEnvironments();
    void this.repository.analysisSettings().then((s) => {
      this.taxonomyDb.set(s.taxonomyDb);
      this.taxonomyOptions.set(s.options.filter(Boolean));
    }).catch(() => undefined);
    interval(2500).pipe(takeUntilDestroyed(inject(DestroyRef))).subscribe(() => {
      if (this.jobs().some((j) => j.status === 'running' || j.status === 'queued')) void this.refreshJobs();
    });
  }

  isInUse(env: EngineEnvironment): boolean {
    const e = this.effective();
    return !!env.python && e.python === env.python && (!env.qiime || e.qiime === env.qiime);
  }

  async useEnvironment(env: EngineEnvironment): Promise<void> {
    await this.saveEnvironment({ qiime: env.qiime ?? '', python: env.python ?? '', rscript: env.rscript ?? '' });
  }

  async saveEnvironment(config: EngineConfig): Promise<void> {
    this.savingEnv.set(true);
    try {
      this.engines.set(await this.repository.saveEngineEnvironment(config));
      await this.loadEnvironments();
      this.messages.add({ severity: 'success', summary: t('Ambientes (conda / Python)'), detail: t('Ambiente salvo.') });
    } catch (error) {
      this.messages.add({ severity: 'error', summary: t('Ambientes (conda / Python)'), detail: this.message(error) });
    } finally {
      this.savingEnv.set(false);
    }
  }

  private async loadEnvironments(): Promise<void> {
    try {
      const res = await this.repository.engineEnvironments();
      this.environments.set(res.environments);
      this.effective.set(res.effective);
      this.cfgQiime = res.config.qiime ?? '';
      this.cfgPython = res.config.python ?? '';
      this.cfgRscript = res.config.rscript ?? '';
    } catch {
      /* the page still works with whatever is on PATH */
    }
  }

  artifactList(job: EngineJob): [string, string][] {
    return Object.entries(job.artifacts);
  }

  async detect(fresh: boolean): Promise<void> {
    this.detecting.set(true);
    try {
      this.engines.set(await this.repository.engines(fresh));
    } catch (error) {
      this.messages.add({ severity: 'error', summary: t('Motores de análise'), detail: this.message(error) });
    } finally {
      this.detecting.set(false);
    }
  }

  async saveDb(value: string | null): Promise<void> {
    try {
      await this.repository.saveTaxonomyDb(value ?? '');
      this.taxonomyDb.set(value ?? '');
    } catch (error) {
      this.messages.add({ severity: 'error', summary: t('Banco taxonômico'), detail: this.message(error) });
    }
  }

  async start(): Promise<void> {
    const common = { workflow: this.workflow, threads: this.threads, ingest: this.ingest };
    const body: Record<string, unknown> =
      this.workflow === 'qiime2-dada2'
        ? { ...common, backend: this.backend, manifest: this.manifest, classifier: this.classifier || undefined, paired: this.paired, build_tree: this.buildTree, trunc_len_f: this.truncF, trunc_len_r: this.truncR }
        : this.workflow === 'dada2-r'
          ? { ...common, fastq_dir: this.fastqDir, ref_fasta: this.refFasta, trunc_len_f: this.truncF, trunc_len_r: this.truncR }
          : this.workflow === 'cutadapt-trim'
            ? { workflow: this.workflow, fastq_dir: this.fastqDir, fwd_primer: this.fwdPrimer, rev_primer: this.revPrimer || undefined, threads: this.threads }
            : this.workflow === 'vsearch-otu'
              ? { workflow: this.workflow, fasta: this.fasta, identity: this.identity, threads: this.threads }
              : this.workflow === 'vegan'
                ? { workflow: this.workflow, group_by: this.groupBy, metric: this.veganMetric, permutations: this.permutations }
                : { workflow: this.workflow, group_by: this.groupBy, a: this.groupA, b: this.groupB };
    this.starting.set(true);
    try {
      await this.repository.runEngine(body);
      await this.refreshJobs();
    } catch (error) {
      this.messages.add({ severity: 'error', summary: t('Não foi possível iniciar'), detail: this.message(error) });
    } finally {
      this.starting.set(false);
    }
  }

  async toggleResults(id: string): Promise<void> {
    if (this.results()[id]) {
      const { [id]: _drop, ...rest } = this.results();
      this.results.set(rest);
      return;
    }
    try {
      this.results.update((r) => ({ ...r, [id]: undefined as unknown as EngineResults }));
      const res = await this.repository.engineResults(id);
      this.results.update((r) => ({ ...r, [id]: res }));
    } catch (error) {
      const { [id]: _drop, ...rest } = this.results();
      this.results.set(rest);
      this.messages.add({ severity: 'error', summary: t('Resultados'), detail: this.message(error) });
    }
  }

  plotOf(res: EngineResults): ChartResult {
    return res.plot ? { status: 'ok', figure: { data: res.plot.data, layout: res.plot.layout } } : { status: 'empty' };
  }

  shownColumns(res: EngineResults): string[] {
    const cols = res.columns.filter((c) => c !== 'effect');
    return res.rows.some((r) => 'taxon' in r) ? ['taxon', ...cols] : cols;
  }

  fmt(value: string | undefined): string {
    const n = Number(value);
    return value !== undefined && value !== '' && Number.isFinite(n) && !Number.isInteger(n) ? n.toPrecision(4) : (value ?? '');
  }

  async cancel(id: string): Promise<void> {
    await this.repository.cancelEngineJob(id);
    await this.refreshJobs();
  }

  private async refreshJobs(): Promise<void> {
    try {
      this.jobs.set(await this.repository.engineJobs());
    } catch {
      /* the next tick retries */
    }
  }

  private message(error: unknown): string {
    return error instanceof Error ? error.message : t('Falha inesperada.');
  }
}
