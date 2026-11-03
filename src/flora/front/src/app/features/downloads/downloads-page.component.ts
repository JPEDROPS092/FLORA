import { Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { INSTITUTIONS } from '../../shared/brand.data';
import { MascotComponent } from '../../shared/mascot.component';
import { TechBadgeComponent } from '../../shared/tech-badge.component';
import { MessageService, PrimeTemplate } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';

import { FloraRepository } from '../../core/data/flora.repository';
import { DownloadJob, DownloadRequest, LibrarySource, StudyEntry } from '../../core/models/domain';
import { TPipe } from '../../core/i18n/t.pipe';
import { t } from '../../core/i18n/i18n';

@Component({
  selector: 'flora-downloads',
  standalone: true,
  imports: [FormsModule, TPipe, MascotComponent, TechBadgeComponent, ReactiveFormsModule, PrimeTemplate, ButtonModule, InputNumberModule, InputTextModule, TableModule, TagModule],
  template: `
    <section class="page">
      <header class="page-heading">
        <div>
          <p class="kicker">{{ 'Downloads' | t }}</p>
          <h1>{{ 'Fontes para o pipeline' | t }}</h1>
          <p class="lede">{{ 'Sintético, EMP, MGnify e SRA. No mock, o pedido é registrado e nenhum arquivo remoto é baixado.' | t }}</p>
        </div>
        <div class="head-side"><p-tag [value]="mocked() ? t('Dados mockados') : t('API HTTP')" severity="secondary" /><flora-mascot name="fishing" [size]="110" [alt]="'Mascote FLORA pescando dados' | t" /></div>
      </header>

      <div class="inst-row" [attr.aria-label]="'Instituições de origem dos datasets' | t">
        @for (i of institutions; track i.name) { <flora-tech-badge [inst]="i" /> }
      </div>

      <article class="surface library">
        <div class="section-title">
          <h2>{{ 'Biblioteca de estudos' | t }}</h2>
          <p class="muted">{{ 'Escolha um estudo pelo código (accession); nada é baixado até você confirmar.' | t }}</p>
        </div>
        <div class="lib-tabs" role="tablist" [attr.aria-label]="'Catálogo' | t">
          @for (tab of tabs; track tab.id) {
            <button type="button" role="tab" class="lib-tab" [class.on]="libSource() === tab.id" [attr.aria-selected]="libSource() === tab.id" (click)="setSource(tab.id)">{{ tab.label | t }}</button>
          }
        </div>
        <form class="lib-search" (ngSubmit)="searchLibrary()">
          <input pInputText name="q" [ngModel]="query()" (ngModelChange)="query.set($event)" [placeholder]="searchHint() | t" [attr.aria-label]="'Buscar estudos' | t" />
          <p-button type="submit" icon="pi pi-search" [label]="'Buscar' | t" [loading]="searching()" />
        </form>
        @if (libError()) { <p class="field-error" role="alert">{{ libError() }}</p> }
        <div class="lib-grid">
          @for (study of studies(); track study.source + study.accession) {
            <div class="study" [class.picked]="selected()?.accession === study.accession">
              <div class="study-head">
                <code class="acc">{{ study.accession }}</code>
                <p-button icon="pi pi-copy" [text]="true" size="small" [ariaLabel]="'Copiar código' | t" (onClick)="copy(study.accession)" />
                <p-tag [value]="study.source" severity="secondary" />
                @if (study.origin === 'curated') { <p-tag [value]="t('Curado')" severity="info" /> }
              </div>
              <h3>{{ study.title }}</h3>
              @if (study.description) { <p class="desc">{{ study.description }}</p> }
              <div class="meta">
                @if (study.samples) { <span>{{ study.samples }} {{ 'amostras' | t }}</span> }
                @if (study.biome) { <span>{{ study.biome }}</span> }
                @if (study.centre) { <span>{{ study.centre }}</span> }
                @if (study.bioproject) { <span>{{ study.bioproject }}</span> }
                @if (study.secondary) { <span>{{ study.secondary }}</span> }
                @if (study.updated) { <span>{{ study.updated }}</span> }
              </div>
              <div class="actions">
                @if (study.url) { <a [href]="study.url" target="_blank" rel="noopener noreferrer">{{ 'Ver na fonte' | t }}</a> }
                <p-button size="small" [label]="(selected()?.accession === study.accession ? 'Escolhido' : 'Escolher') | t" [disabled]="!study.importable" (onClick)="choose(study)" />
              </div>
            </div>
          } @empty {
            @if (!searching()) { <p class="muted">{{ 'Nenhum estudo encontrado. Tente outras palavras, como “16S soil Amazon”.' | t }}</p> }
          }
        </div>
        @if (selected(); as pick) {
          <div class="picked-bar" role="status">
            <div><strong>{{ pick.accession }}</strong> · {{ pick.title }}
              @if (pick.source === 'ena') { <small class="muted"> — {{ 'serão baixadas até 10 runs deste estudo' | t }}</small> }
            </div>
            <div class="picked-actions">
              <p-button [text]="true" [label]="'Limpar' | t" (onClick)="selected.set(null)" />
              <p-button icon="pi pi-download" [label]="'Baixar para o pipeline' | t" [loading]="busy()" (onClick)="downloadSelected()" />
            </div>
          </div>
        }
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
              <small class="field-error">{{ 'Informe o accession, por exemplo MGYS00001234.' | t }}</small>
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
              <td>{{ job.artifacts.map(item => item.path).join(', ') || '—' }}</td>
            </tr>
          </ng-template>
          <ng-template pTemplate="emptymessage"><tr><td colspan="5">{{ 'Nenhum pedido.' | t }}</td></tr></ng-template>
        </p-table>
      </article>
    </section>
  `,
  styles: `
    .library { display: grid; gap: 12px; }
    .muted { color: var(--flora-muted); font-size: .86rem; }
    .lib-tabs { display: flex; gap: 6px; flex-wrap: wrap; }
    .lib-tab { border: 1px solid var(--flora-border); background: var(--flora-surface); color: var(--flora-text); border-radius: 999px; padding: 5px 14px; cursor: pointer; font: inherit; font-size: .86rem; }
    .lib-tab.on { background: var(--flora-primary-soft); border-color: var(--flora-primary); color: var(--flora-primary); font-weight: 600; }
    .lib-search { display: flex; gap: 8px; }
    .lib-search input { flex: 1; }
    .lib-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 10px; }
    .study { border: 1px solid var(--flora-border); border-radius: var(--radius); padding: 12px; display: grid; gap: 6px; align-content: start; background: var(--flora-surface); }
    .study.picked { border-color: var(--flora-primary); box-shadow: 0 0 0 2px var(--flora-primary-soft); }
    .study-head { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
    .acc { font-weight: 650; color: var(--flora-primary); }
    .study h3 { font-size: .95rem; font-weight: 600; margin: 0; }
    .desc { margin: 0; font-size: .82rem; color: var(--flora-muted); display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
    .meta { display: flex; gap: 6px; flex-wrap: wrap; font-size: .76rem; color: var(--flora-muted); }
    .meta span { background: var(--flora-bg); border: 1px solid var(--flora-border); border-radius: 999px; padding: 1px 8px; }
    .actions { display: flex; justify-content: space-between; align-items: center; margin-top: 4px; font-size: .84rem; }
    .picked-bar { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; border: 1px solid var(--flora-primary); background: var(--flora-primary-soft); border-radius: var(--radius); padding: 10px 12px; }
    .picked-actions { display: flex; gap: 6px; }
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

  readonly tabs: { id: LibrarySource; label: string }[] = [
    { id: 'curated', label: 'Curados' },
    { id: 'mgnify', label: 'MGnify (busca ao vivo)' },
    { id: 'ena', label: 'ENA / NCBI SRA (busca ao vivo)' }
  ];
  readonly libSource = signal<LibrarySource>('curated');
  readonly query = signal('');
  readonly studies = signal<StudyEntry[]>([]);
  readonly searching = signal(false);
  readonly libError = signal('');
  readonly selected = signal<StudyEntry | null>(null);
  readonly searchHint = computed(() =>
    this.libSource() === 'curated' ? 'Filtrar por código, título ou bioma' : 'Ex.: 16S soil Amazon'
  );

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
    void this.searchLibrary();
  }

  setSource(source: LibrarySource): void {
    this.libSource.set(source);
    this.studies.set([]);
    this.libError.set('');
    // Live catalogues need a query; the curated one lists everything.
    if (source === 'curated' || this.query().trim()) void this.searchLibrary();
  }

  async searchLibrary(): Promise<void> {
    this.searching.set(true);
    this.libError.set('');
    try {
      this.studies.set(await this.repository.searchLibrary(this.libSource(), this.query().trim()));
    } catch (error) {
      this.studies.set([]);
      this.libError.set(error instanceof Error ? error.message : t('Falha na busca.'));
    } finally {
      this.searching.set(false);
    }
  }

  choose(study: StudyEntry): void {
    this.selected.set(study);
  }

  async copy(code: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(code);
      this.messages.add({ severity: 'success', summary: code, detail: t('Código copiado.') });
    } catch {
      this.messages.add({ severity: 'warn', summary: code, detail: t('Não foi possível copiar; selecione o código manualmente.') });
    }
  }

  async downloadSelected(): Promise<void> {
    const pick = this.selected();
    if (!pick) return;
    this.busy.set(true);
    try {
      let request: DownloadRequest;
      if (pick.source === 'synthetic') {
        request = { source: 'synthetic', ...this.synthetic.getRawValue() };
      } else if (pick.source === 'emp') {
        const v = this.emp.getRawValue();
        request = { source: 'emp', outputDir: v.outputDir, biome: v.biome, maxSamples: v.maxSamples };
      } else if (pick.source === 'mgnify') {
        const v = this.mgnify.getRawValue();
        request = { source: 'mgnify', outputDir: `results/raw/mgnify/${pick.accession}`, studyAccession: pick.accession, biome: v.biome, maxSamples: v.maxSamples };
      } else {
        const runs = await this.repository.resolveRuns(pick.accession);
        if (!runs.length) throw new Error(t('Este estudo não tem runs públicas no ENA.'));
        request = { source: 'sra', outputDir: `results/raw/sra/${pick.accession}`, accessions: runs };
      }
      await this.send(request);
    } catch (error) {
      this.messages.add({ severity: 'error', summary: pick.accession, detail: error instanceof Error ? error.message : t('Falha no download.') });
    } finally {
      this.busy.set(false);
    }
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
