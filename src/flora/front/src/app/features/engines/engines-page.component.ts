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
import { EngineInfo, EngineJob } from '../../core/models/domain';
import { TPipe } from '../../core/i18n/t.pipe';
import { t } from '../../core/i18n/i18n';

type Workflow = 'qiime2-dada2' | 'dada2-r' | 'aldex2';

@Component({
  selector: 'flora-engines',
  standalone: true,
  imports: [FormsModule, TPipe, ButtonModule, CheckboxModule, InputNumberModule, InputTextModule, ProgressBarModule, SelectModule, TagModule],
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
            @case ('aldex2') {
              <p class="muted">{{ 'Usa os dados do projeto ativo.' | t }}</p>
              <label>{{ 'Coluna de agrupamento' | t }}<input pInputText [(ngModel)]="groupBy" placeholder="biome" /></label>
              <div class="inline">
                <label>{{ 'Grupo A' | t }}<input pInputText [(ngModel)]="groupA" /></label>
                <label>{{ 'Grupo B' | t }}<input pInputText [(ngModel)]="groupB" /></label>
              </div>
            }
          }
          <div class="inline">
            <label>{{ 'Threads' | t }}<p-inputnumber [(ngModel)]="threads" [min]="1" [max]="64" /></label>
            @if (workflow !== 'aldex2') { <p-checkbox inputId="ingest" [(ngModel)]="ingest" [binary]="true" /><label for="ingest">{{ 'Ingerir no projeto ativo ao terminar' | t }}</label> }
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
    { label: t('ALDEx2 (abundância diferencial)'), value: 'aldex2' }
  ];
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
    const need = { 'qiime2-dada2': 'qiime2', 'dada2-r': 'dada2', aldex2: 'aldex2' }[this.workflow];
    return this.engines().some((e) => e.id === need && e.available);
  });

  constructor() {
    void this.detect(false);
    void this.refreshJobs();
    void this.repository.analysisSettings().then((s) => {
      this.taxonomyDb.set(s.taxonomyDb);
      this.taxonomyOptions.set(s.options.filter(Boolean));
    }).catch(() => undefined);
    interval(2500).pipe(takeUntilDestroyed(inject(DestroyRef))).subscribe(() => {
      if (this.jobs().some((j) => j.status === 'running' || j.status === 'queued')) void this.refreshJobs();
    });
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
        ? { ...common, manifest: this.manifest, classifier: this.classifier || undefined, paired: this.paired, build_tree: this.buildTree, trunc_len_f: this.truncF, trunc_len_r: this.truncR }
        : this.workflow === 'dada2-r'
          ? { ...common, fastq_dir: this.fastqDir, ref_fasta: this.refFasta, trunc_len_f: this.truncF, trunc_len_r: this.truncR }
          : { workflow: 'aldex2', group_by: this.groupBy, a: this.groupA, b: this.groupB, threads: this.threads };
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
