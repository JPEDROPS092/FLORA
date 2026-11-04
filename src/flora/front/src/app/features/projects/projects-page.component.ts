import { DecimalPipe } from '@angular/common';
import { Component, OnDestroy, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { DrawerModule } from 'primeng/drawer';
import { InputTextModule } from 'primeng/inputtext';
import { ProgressBarModule } from 'primeng/progressbar';
import { SelectModule } from 'primeng/select';
import { TagModule } from 'primeng/tag';
import { TextareaModule } from 'primeng/textarea';

import { FloraRepository } from '../../core/data/flora.repository';
import { ExampleProject, ResearchProject, SyncJob, SyncSourceType } from '../../core/models/domain';
import { t } from '../../core/i18n/i18n';
import { TPipe } from '../../core/i18n/t.pipe';

@Component({
  selector: 'flora-projects',
  standalone: true,
  imports: [TPipe, DecimalPipe, ReactiveFormsModule, ButtonModule, DialogModule, DrawerModule, InputTextModule, ProgressBarModule, SelectModule, TagModule, TextareaModule],
  template: `
    <section class="page">
      <header class="page-heading">
        <div>
          <p class="kicker">{{ 'Projetos' | t }}</p>
          <h1>{{ 'Perguntas, datasets e resultados' | t }}</h1>
          <p class="lede">{{ 'Cada projeto guarda o dataset, as análises e o que já foi concluído.' | t }}</p>
        </div>
        <div class="actions">
          @if (repository.source.mocked) { <p-tag [value]="'Dados mockados' | t" severity="secondary" /> }
          <p-button [label]="'Conectar fonte' | t" icon="pi pi-link" severity="secondary" [outlined]="true" (onClick)="openConnect()" />
          <p-button [label]="'Novo projeto' | t" icon="pi pi-plus" (onClick)="creating.set(true)" />
        </div>
      </header>

      @if (error()) { <p class="field-error" role="alert">{{ error() }}</p> }

      @if (job(); as j) {
        <article class="surface sync-card" aria-live="polite">
          <div class="section-title">
            <h2>{{ 'Sincronização' | t }} · {{ j.source.type }}{{ j.source.accession ? ' · ' + j.source.accession : '' }}</h2>
            <p-tag [value]="statusLabel(j.status)" [severity]="j.status === 'failed' ? 'danger' : j.status === 'completed' ? 'success' : 'info'" />
          </div>
          <p-progressbar [value]="j.progress" [showValue]="true" />
          <p class="note">{{ j.error || j.message }}</p>
          @if (j.upToDate) { <p class="note">{{ 'Nada novo: os arquivos locais já conferem com o manifesto (SHA-256).' | t }}</p> }
          @if (active(j)) { <p-button [label]="'Cancelar' | t" icon="pi pi-times" severity="secondary" [text]="true" size="small" (onClick)="cancel()" /> }
        </article>
      }

      <article class="surface">
        <div class="section-title"><h2>{{ 'Meus projetos' | t }}</h2><span class="note">{{ projects().length }}</span></div>
        @if (loading()) {
          <p class="note">{{ 'Carregando…' | t }}</p>
        } @else if (!projects().length) {
          <div class="empty">
            <p>{{ 'Nenhum projeto ainda. Importe um exemplo abaixo, conecte uma fonte ou crie um projeto vazio.' | t }}</p>
          </div>
        } @else {
          <div class="proj-grid">
            @for (project of projects(); track project.id) {
              <div class="proj-card" [class.is-active]="project.active">
                <div class="proj-top">
                  <strong>{{ project.name }}</strong>
                  <span class="proj-tags">
                    @if (project.active) { <p-tag [value]="'Ativo' | t" severity="success" /> }
                    @if (project.synthetic) { <p-tag [value]="'Sintético' | t" severity="warn" /> }
                    <p-tag [value]="stageLabel(project)" [severity]="project.stage === 'ingested' ? 'success' : 'secondary'" />
                  </span>
                </div>
                <p class="note">{{ project.question || ('Sem pergunta definida.' | t) }}</p>
                <p class="note">{{ project.datasetName }} · {{ project.samples | number }} {{ 'amostras' | t }} · {{ project.asvs | number }} ASVs</p>
                <div class="proj-actions">
                  <p-button [label]="'Detalhes' | t" size="small" severity="secondary" [text]="true" (onClick)="selected.set(project)" />
                  @if (!project.active) { <p-button [label]="'Ativar' | t" size="small" severity="secondary" [outlined]="true" (onClick)="activate(project)" /> }
                  @if (project.stage === 'ingested') {
                    <p-button [label]="'Explorar' | t" icon="pi pi-chart-bar" size="small" (onClick)="open(project, '/explorer')" />
                  }
                </div>
              </div>
            }
          </div>
        }
      </article>

      <article class="surface">
        <div class="section-title"><h2>{{ 'Estudos de exemplo' | t }}</h2></div>
        <div class="proj-grid">
          @for (ex of examples(); track ex.id) {
            <div class="proj-card">
              <div class="proj-top">
                <strong>{{ ex.name }}</strong>
                <span class="proj-tags">
                  @if (ex.synthetic) { <p-tag [value]="'Sintético' | t" severity="warn" /> }
                  @if (!ex.verified && !ex.synthetic) { <p-tag [value]="'Template não verificado' | t" severity="secondary" /> }
                </span>
              </div>
              <p class="note">{{ ex.description }}</p>
              <p class="note">{{ ex.source.type }} · {{ ex.source.accession }}</p>
              <div class="proj-actions">
                <p-button [label]="'Importar' | t" icon="pi pi-download" size="small" [disabled]="!ex.installable || busy()" (onClick)="install(ex)" />
              </div>
            </div>
          }
        </div>
      </article>
    </section>

    <p-drawer [visible]="!!selected()" (visibleChange)="ifBlank($event)" [header]="'Projeto' | t" position="right" [style]="{ width: '440px' }">
      @if (selected(); as project) {
        <p>{{ project.question }}</p>
        <p class="note">{{ project.datasetName }} · {{ project.marker }} · {{ stageLabel(project) }}</p>
        @if (project.stage !== 'ingested') {
          <p class="note">{{ 'Este projeto ainda não tem matriz ASV ingerida; arquivos brutos (FASTQ) não bastam para análise.' | t }}</p>
        }
        <h3>{{ 'Análises' | t }}</h3>
        <ul class="limitations">
          @for (item of project.analyses; track item.id) { <li>{{ item.name }} · {{ item.status }}</li> }
          @if (!project.analyses.length) { <li>{{ 'Nenhuma análise ligada.' | t }}</li> }
        </ul>
        <h3>{{ 'Resultados' | t }}</h3>
        <ul class="limitations">
          @for (item of project.results; track item.id) { <li><strong>{{ item.title }}.</strong> {{ item.summary }}</li> }
          @if (!project.results.length) { <li>{{ 'Nenhum resultado registrado.' | t }}</li> }
        </ul>
      }
    </p-drawer>

    <p-dialog [visible]="creating()" (visibleChange)="creating.set($event)" [header]="'Novo projeto' | t" [modal]="true" [style]="{ width: '460px' }">
      <form class="filters" [formGroup]="form" (ngSubmit)="save()">
        <div class="field">
          <label for="name">{{ 'Nome' | t }}</label>
          <input id="name" pInputText formControlName="name" />
          @if (form.controls.name.invalid && form.controls.name.touched) {
            <small class="field-error">{{ 'Dê um nome ao projeto.' | t }}</small>
          }
        </div>
        <div class="field">
          <label for="question">{{ 'Pergunta' | t }}</label>
          <textarea id="question" pTextarea rows="4" formControlName="question"></textarea>
          @if (form.controls.question.invalid && form.controls.question.touched) {
            <small class="field-error">{{ 'Escreva a pergunta científica.' | t }}</small>
          }
        </div>
        <p-button type="submit" [label]="'Criar' | t" />
      </form>
    </p-dialog>

    <p-dialog [visible]="connecting()" (visibleChange)="connecting.set($event)" [header]="'Conectar fonte de dados' | t" [modal]="true" [style]="{ width: '480px' }">
      <form class="filters" [formGroup]="connect" (ngSubmit)="startConnect()">
        <div class="field"><label for="srcType">{{ 'Fonte' | t }}</label>
          <p-select inputId="srcType" [options]="sourceTypes" formControlName="type" optionLabel="label" optionValue="id" appendTo="body" [fluid]="true" /></div>
        @if (needsAccession()) {
          <div class="field"><label for="acc">{{ 'Accession do estudo' | t }}</label>
            <input id="acc" pInputText formControlName="accession" [placeholder]="connect.controls.type.value === 'mgnify' ? 'MGYS00005779' : 'PRJNA289633'" autocomplete="off" spellcheck="false" />
            @if (connect.controls.accession.invalid && connect.controls.accession.touched) { <small class="field-error">{{ 'Informe um accession válido.' | t }}</small> }</div>
        }
        <div class="field"><label for="target">{{ 'Projeto de destino' | t }}</label>
          <p-select inputId="target" [options]="targets()" formControlName="target" optionLabel="label" optionValue="id" appendTo="body" [fluid]="true" /></div>
        <p class="note">{{ srcHint() }}</p>
        <p-button type="submit" [label]="'Sincronizar' | t" icon="pi pi-sync" [disabled]="busy()" />
      </form>
    </p-dialog>
  `,
  styles: [`
    .proj-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; margin-top: 8px; }
    .proj-card { border: 1px solid var(--p-content-border-color, #d9e1d9); border-radius: 10px; padding: 12px 14px; display: grid; gap: 6px; background: var(--p-content-background, transparent); }
    .proj-card.is-active { border-color: var(--p-primary-color, #2f8f5b); box-shadow: 0 0 0 1px var(--p-primary-color, #2f8f5b) inset; }
    .proj-top { display: flex; justify-content: space-between; gap: 8px; align-items: flex-start; }
    .proj-tags { display: flex; gap: 4px; flex-wrap: wrap; justify-content: flex-end; }
    .proj-actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
    .sync-card { display: grid; gap: 8px; }
    .empty { padding: 12px 0; }
  `]
})
export class ProjectsPageComponent implements OnDestroy {
  readonly repository = inject(FloraRepository);
  private readonly messages = inject(MessageService);
  private readonly fb = inject(FormBuilder);
  private readonly router = inject(Router);

  readonly projects = signal<ResearchProject[]>([]);
  readonly examples = signal<ExampleProject[]>([]);
  readonly selected = signal<ResearchProject | null>(null);
  readonly creating = signal(false);
  readonly connecting = signal(false);
  readonly loading = signal(true);
  readonly error = signal('');
  readonly job = signal<SyncJob | null>(null);
  readonly busy = computed(() => !!this.job() && this.active(this.job()!));
  private timer: ReturnType<typeof setInterval> | null = null;

  readonly sourceTypes: { id: SyncSourceType; label: string }[] = [
    { id: 'mgnify', label: 'MGnify' },
    { id: 'sra', label: 'NCBI SRA' },
    { id: 'emp', label: 'Earth Microbiome Project' },
    { id: 'synthetic', label: t('Dados sintéticos (offline)') }
  ];
  readonly form = this.fb.nonNullable.group({
    name: ['', Validators.required],
    question: ['', Validators.required]
  });
  readonly connect = this.fb.nonNullable.group({
    type: 'mgnify' as SyncSourceType,
    accession: ['', [Validators.required, Validators.pattern(/^[A-Za-z0-9_.\-:]{3,64}$/)]],
    target: 'new'
  });
  private readonly connectType = signal<SyncSourceType>('mgnify');
  readonly needsAccession = computed(() => this.connectType() === 'mgnify' || this.connectType() === 'sra');
  readonly targets = computed(() => [
    { id: 'new', label: t('Novo projeto') },
    ...this.projects().filter((p) => p.stage !== 'ingested').map((p) => ({ id: p.id, label: p.name }))
  ]);

  constructor() {
    this.connect.controls.type.valueChanges.subscribe((v) => this.connectType.set(v));
    void this.reload();
    void this.repository.examples().then((e) => this.examples.set(e)).catch((e) => this.fail(e));
  }

  ngOnDestroy(): void {
    this.stopPolling();
  }

  ifBlank(visible: boolean): void {
    if (!visible) this.selected.set(null);
  }

  active(j: SyncJob): boolean {
    return j.status === 'queued' || j.status === 'running';
  }

  statusLabel(s: string): string {
    return ({ queued: t('na fila'), running: t('em andamento'), completed: t('concluído'), failed: t('falhou'), cancelled: t('cancelado') } as Record<string, string>)[s] ?? s;
  }

  stageLabel(p: ResearchProject): string {
    return ({ empty: t('Sem dados'), raw_downloaded: t('Arquivos brutos'), ingested: t('Pronto para análise') } as Record<string, string>)[p.stage ?? 'empty'] ?? '';
  }

  srcHint(): string {
    const type = this.connectType();
    if (type === 'synthetic') return t('Gera 80 amostras e 200 ASVs (seed 42) e ingere no projeto. Rotulado como sintético.');
    if (type === 'emp') return t('Baixa as tabelas do EMP e ingere metadata, ASV e taxonomia.');
    return t('Baixa os arquivos brutos do estudo. Eles ainda não são uma matriz ASV: o projeto só fica pronto para análise após a ingestão.');
  }

  openConnect(): void {
    this.connect.reset({ type: 'mgnify', accession: '', target: 'new' });
    this.connectType.set('mgnify');
    this.connecting.set(true);
  }

  async save(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    try {
      const project = await this.repository.saveProject(this.form.getRawValue());
      this.messages.add({ severity: 'success', summary: t('Projeto'), detail: project.name });
      this.creating.set(false);
      this.form.reset();
      await this.reload();
    } catch (e) {
      this.fail(e);
    }
  }

  async install(ex: ExampleProject): Promise<void> {
    this.error.set('');
    try {
      const { job } = await this.repository.installExample(ex.id);
      this.track(job);
      await this.reload();
    } catch (e) {
      this.fail(e);
    }
  }

  async startConnect(): Promise<void> {
    const v = this.connect.getRawValue();
    if (this.needsAccession() && this.connect.controls.accession.invalid) {
      this.connect.markAllAsTouched();
      return;
    }
    this.error.set('');
    try {
      let target = v.target;
      if (target === 'new') {
        const name = v.accession || this.sourceTypes.find((s) => s.id === v.type)?.label || 'Projeto';
        target = (await this.repository.saveProject({ name, question: '' })).id;
      }
      const job = await this.repository.startSync(target, { type: v.type, accession: this.needsAccession() ? v.accession.trim() : '' });
      this.connecting.set(false);
      this.track(job);
      await this.reload();
    } catch (e) {
      this.fail(e);
    }
  }

  async activate(project: ResearchProject): Promise<void> {
    try {
      await this.repository.activateProject(project.id);
      await this.reload();
    } catch (e) {
      this.fail(e);
    }
  }

  open(project: ResearchProject, path: string): void {
    void this.repository.activateProject(project.id).then(() => this.router.navigate([path])).catch((e) => this.fail(e));
  }

  async cancel(): Promise<void> {
    const j = this.job();
    if (!j) return;
    try {
      this.job.set(await this.repository.cancelSync(j.id));
    } catch (e) {
      this.fail(e);
    }
  }

  private track(job: SyncJob): void {
    this.job.set(job);
    this.stopPolling();
    this.timer = setInterval(async () => {
      try {
        const next = await this.repository.syncJob(job.id);
        this.job.set(next);
        if (!this.active(next)) {
          this.stopPolling();
          await this.reload();
          if (next.status === 'completed') this.messages.add({ severity: 'success', summary: t('Sincronização'), detail: next.message });
        }
      } catch (e) {
        this.stopPolling();
        this.fail(e);
      }
    }, 1000);
  }

  private stopPolling(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  private fail(e: unknown): void {
    this.error.set(e instanceof Error ? e.message : t('erro desconhecido'));
  }

  private async reload(): Promise<void> {
    try {
      this.projects.set(await this.repository.projects());
    } catch (e) {
      this.fail(e);
    } finally {
      this.loading.set(false);
    }
  }
}
