import { DecimalPipe } from '@angular/common';
import { Component, effect, inject, input, output, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MessageService, PrimeTemplate } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { InputNumberModule } from 'primeng/inputnumber';
import { SelectModule } from 'primeng/select';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';

import { FloraRepository } from '../../core/data/flora.repository';
import { AnalysisKind, ChartResult, GroupColumn } from '../../core/models/domain';
import { TPipe } from '../../core/i18n/t.pipe';
import { t } from '../../core/i18n/i18n';
import { PlotCardComponent } from '../../shared/plot-card.component';

type Json = Record<string, any>;
export type PanelMode = 'qc' | 'rarefaction' | 'stats';

const toChart = (plot: Json | undefined): ChartResult =>
  plot?.['data']?.length ? { status: 'ok', figure: { data: plot['data'], layout: plot['layout'] ?? {} } } : { status: 'empty', error: t('Sem dados para estes filtros.') };

/** Quality control, rarefaction curves and statistical tests, each with its own grouping variable. */
@Component({
  selector: 'flora-analysis-panel',
  standalone: true,
  imports: [DecimalPipe, FormsModule, TPipe, PrimeTemplate, ButtonModule, InputNumberModule, SelectModule, TableModule, TagModule, PlotCardComponent],
  template: `
    @if (mode() !== 'qc') {
      <div class="bar">
        <label for="panelGroup">{{ 'Agrupar por' | t }}</label>
        <p-select inputId="panelGroup" [options]="groupColumns()" optionLabel="name" optionValue="name" [ngModel]="groupBy()" (ngModelChange)="setGroup($event)" appendTo="body" [placeholder]="'Coluna de metadata' | t" />
      </div>
    }
    @if (error()) { <p class="field-error" role="alert">{{ error() }}</p> }
    @if (loading()) { <p class="muted">{{ 'Calculando…' | t }}</p> }

    @switch (mode()) {
      @case ('qc') {
        @if (qc(); as q) {
          <div class="chips">
            <span><strong>{{ q['summary'].samples }}</strong> {{ 'amostras' | t }}</span>
            <span [class.bad]="q['summary'].below_depth"><strong>{{ q['summary'].below_depth }}</strong> {{ 'abaixo do corte de' | t }} {{ q['summary'].min_reads | number }} {{ 'reads' | t }}</span>
            <span><strong>{{ q['summary'].organelle_features }}</strong> {{ 'features de cloroplasto/mitocôndria' | t }} ({{ q['summary'].organelle_reads_pct }}% {{ 'das reads' | t }})</span>
          </div>
          <div class="bar">
            <label for="cut">{{ 'Corte de profundidade (reads)' | t }}</label>
            <p-inputnumber inputId="cut" [ngModel]="minReads()" (ngModelChange)="minReads.set($event ?? 0)" [min]="0" />
            <p-button type="button" severity="secondary" [label]="'Recalcular' | t" (onClick)="load()" />
            <p-button type="button" severity="danger" [outlined]="true" icon="pi pi-trash" [label]="'Remover cloroplasto e mitocôndria' | t" (onClick)="apply({ remove_organelles: true })" [disabled]="!q['summary'].organelle_features" />
            <p-button type="button" severity="danger" [outlined]="true" icon="pi pi-trash" [label]="'Descartar amostras abaixo do corte' | t" (onClick)="apply({ drop_low_depth: true, min_reads: minReads() })" [disabled]="!q['summary'].below_depth" />
          </div>
          <flora-plot [result]="chart()" [height]="320" />
          <p-table [value]="q['samples']" [rows]="10" [paginator]="true" styleClass="nowrap">
            <ng-template pTemplate="header"><tr><th>{{ 'Amostra' | t }}</th><th>{{ 'Reads' | t }}</th><th>{{ 'Features' | t }}</th><th>{{ '% organelas' | t }}</th><th>{{ 'Estado' | t }}</th></tr></ng-template>
            <ng-template pTemplate="body" let-r><tr><td>{{ r.sample_id }}</td><td>{{ r.reads | number }}</td><td>{{ r.features | number }}</td><td>{{ r.organelle_pct }}</td><td [class]="'status-' + r.status">{{ r.status }}</td></tr></ng-template>
          </p-table>
        }
      }
      @case ('rarefaction') {
        @if (rare(); as r) {
          <flora-plot [result]="chart()" [height]="420" />
          <p class="muted">{{ r['note'] }}</p>
          <p-table [value]="r['samples']" [rows]="8" [paginator]="true">
            <ng-template pTemplate="header"><tr><th>{{ 'Amostra' | t }}</th><th>{{ 'Grupo' | t }}</th><th>{{ 'Reads' | t }}</th><th>{{ 'Observadas' | t }}</th><th>{{ 'Saturação' | t }}</th></tr></ng-template>
            <ng-template pTemplate="body" let-s><tr><td>{{ s.sample_id }}</td><td>{{ s.group || '—' }}</td><td>{{ s.reads | number }}</td><td>{{ s.observed | number }}</td><td>{{ s.saturation | number:'1.2-2' }}</td></tr></ng-template>
          </p-table>
        }
      }
      @case ('stats') {
        <h3>{{ 'Diversidade alfa' | t }}</h3>
        @if (alpha(); as a) {
          <p-table [value]="a['tests']">
            <ng-template pTemplate="header"><tr><th>{{ 'Métrica' | t }}</th><th>H</th><th>p</th><th>q (FDR)</th><th>ε²</th></tr></ng-template>
            <ng-template pTemplate="body" let-row><tr><td>{{ row.metric }}</td><td>{{ row.h | number:'1.2-2' }}</td><td>{{ row.p | number:'1.4-4' }}</td><td [class.sig]="row.q < 0.05">{{ row.q | number:'1.4-4' }}</td><td>{{ row.epsilon2 | number:'1.2-2' }}</td></tr></ng-template>
            <ng-template pTemplate="emptymessage"><tr><td colspan="5">{{ 'Nenhum teste pôde ser calculado.' | t }}</td></tr></ng-template>
          </p-table>
          <p class="muted">{{ a['notes'].join(' ') }}</p>
        }

        <h3>{{ 'Diversidade beta' | t }}</h3>
        <div class="bar">
          <p-select [options]="metrics" optionLabel="label" optionValue="value" [(ngModel)]="metric" appendTo="body" [style]="{ minWidth: '190px' }" [attr.aria-label]="'Distância' | t" />
          <p-inputnumber [(ngModel)]="permutations" [min]="99" [max]="9999" [step]="100" [attr.aria-label]="'Permutações' | t" />
          <p-button type="button" [label]="'Rodar PERMANOVA + PERMDISP' | t" [loading]="busyBeta()" (onClick)="runBeta()" />
        </div>
        @if (beta(); as b) {
          <div class="chips">
            <span>PERMANOVA: F=<strong>{{ b['permanova'].f | number:'1.2-2' }}</strong> · R²=<strong>{{ b['permanova'].r2 | number:'1.3-3' }}</strong> · p=<strong [class.sig]="b['permanova'].p < 0.05">{{ b['permanova'].p | number:'1.4-4' }}</strong></span>
            <span>PERMDISP: F=<strong>{{ b['permdisp'].f | number:'1.2-2' }}</strong> · p=<strong [class.sig]="b['permdisp'].p < 0.05">{{ b['permdisp'].p | number:'1.4-4' }}</strong></span>
            <span>{{ 'permutações:' | t }} {{ b['permanova'].permutations }}</span>
          </div>
          @for (n of b['notes']; track n) { <p class="note">{{ n }}</p> }
          <flora-plot [result]="betaChart()" [height]="340" />
        }

        <h3>{{ 'Abundância diferencial' | t }}</h3>
        <div class="bar">
          <p-select [options]="ranks" optionLabel="label" optionValue="value" [(ngModel)]="rank" appendTo="body" [attr.aria-label]="'Rank' | t" />
          <p-select [options]="values()" [(ngModel)]="contrastA" appendTo="body" [placeholder]="'Grupo A' | t" />
          <span>vs</span>
          <p-select [options]="values()" [(ngModel)]="contrastB" appendTo="body" [placeholder]="'Grupo B' | t" />
          <p-button type="button" [label]="'Gerar volcano' | t" [loading]="busyVolcano()" (onClick)="runVolcano()" />
        </div>
        @if (volcano(); as v) {
          <flora-plot [result]="volcanoChart()" [height]="380" />
          <p-table [value]="v['results']" [rows]="8" [paginator]="true">
            <ng-template pTemplate="header"><tr><th>{{ 'Táxon' | t }}</th><th>log2FC</th><th>p</th><th>q</th></tr></ng-template>
            <ng-template pTemplate="body" let-r><tr><td>{{ r.taxon }}</td><td>{{ r.log2fc | number:'1.2-2' }}</td><td>{{ r.p | number:'1.4-4' }}</td><td [class.sig]="r.significant">{{ r.q | number:'1.4-4' }}</td></tr></ng-template>
          </p-table>
          <p class="muted">{{ v['notes'].join(' ') }}</p>
        }
      }
    }
  `,
  styles: `
    .bar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 8px 0; }
    .bar label { font-size: .82rem; color: var(--flora-muted); }
    .chips { display: flex; gap: 14px; flex-wrap: wrap; font-size: .86rem; margin: 8px 0; }
    .chips .bad strong { color: var(--flora-fail); }
    .muted { color: var(--flora-muted); font-size: .84rem; }
    .sig { color: var(--flora-ok); font-weight: 700; }
    h3 { margin: 18px 0 4px; font-size: 1rem; }
  `
})
export class AnalysisPanelComponent {
  private readonly repository = inject(FloraRepository);
  private readonly messages = inject(MessageService);

  readonly mode = input.required<PanelMode>();
  readonly groupColumns = input<GroupColumn[]>([]);
  readonly initialGroup = input('');
  readonly minReadsInput = input(1000);
  readonly changed = output<void>();

  readonly groupBy = signal('');
  readonly minReads = signal(1000);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly qc = signal<Json | null>(null);
  readonly rare = signal<Json | null>(null);
  readonly alpha = signal<Json | null>(null);
  readonly beta = signal<Json | null>(null);
  readonly volcano = signal<Json | null>(null);
  readonly busyBeta = signal(false);
  readonly busyVolcano = signal(false);

  metric = 'bray_curtis';
  permutations = 999;
  rank = 'genus';
  contrastA = '';
  contrastB = '';
  readonly metrics = [
    { label: 'Bray–Curtis', value: 'bray_curtis' },
    { label: 'Jaccard', value: 'jaccard' },
    { label: 'Aitchison (CLR)', value: 'aitchison' },
    { label: t('UniFrac (exige árvore, via QIIME 2)'), value: 'unifrac' }
  ];
  readonly ranks = [
    { label: t('Filo'), value: 'phylum' },
    { label: t('Classe'), value: 'class' },
    { label: t('Ordem'), value: 'order' },
    { label: t('Família'), value: 'family' },
    { label: t('Gênero'), value: 'genus' }
  ];

  constructor() {
    effect(() => {
      const mode = this.mode();
      const initial = this.initialGroup();
      const columns = this.groupColumns();
      untracked(() => {
        this.minReads.set(this.minReadsInput());
        if (!this.groupBy() || !columns.some((c) => c.name === this.groupBy())) this.groupBy.set(initial || columns[0]?.name || '');
        void this.load(mode);
      });
    });
  }

  values(): string[] {
    return this.groupColumns().find((c) => c.name === this.groupBy())?.values.map((v) => v.value) ?? [];
  }

  setGroup(name: string): void {
    this.groupBy.set(name);
    this.contrastA = this.contrastB = '';
    this.beta.set(null);
    this.volcano.set(null);
    void this.load();
  }

  chart(): ChartResult {
    return toChart((this.mode() === 'qc' ? this.qc() : this.rare())?.['plot']);
  }

  betaChart(): ChartResult {
    return toChart(this.beta()?.['plot']);
  }

  volcanoChart(): ChartResult {
    return toChart(this.volcano()?.['plot']);
  }

  async load(mode: PanelMode = this.mode()): Promise<void> {
    this.error.set('');
    this.loading.set(true);
    try {
      if (mode === 'qc') this.qc.set(await this.repository.analysis('qc', { min_reads: this.minReads() }));
      else if (mode === 'rarefaction') this.rare.set(await this.repository.analysis('rarefaction', { group_by: this.groupBy(), depth: this.minReads() }));
      else this.alpha.set(await this.repository.analysis('alpha_stats', { group_by: this.groupBy() }));
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : t('Falha inesperada.'));
    } finally {
      this.loading.set(false);
    }
  }

  async runBeta(): Promise<void> {
    this.busyBeta.set(true);
    this.error.set('');
    try {
      this.beta.set(await this.repository.analysis('beta_stats', { group_by: this.groupBy(), metric: this.metric, permutations: this.permutations }));
    } catch (error) {
      this.beta.set(null);
      this.error.set(error instanceof Error ? error.message : t('Falha inesperada.'));
    } finally {
      this.busyBeta.set(false);
    }
  }

  async runVolcano(): Promise<void> {
    this.busyVolcano.set(true);
    this.error.set('');
    try {
      const params: Record<string, string | number> = { group_by: this.groupBy(), rank: this.rank };
      if (this.contrastA && this.contrastB) Object.assign(params, { a: this.contrastA, b: this.contrastB });
      this.volcano.set(await this.repository.analysis('volcano', params));
    } catch (error) {
      this.volcano.set(null);
      this.error.set(error instanceof Error ? error.message : t('Falha inesperada.'));
    } finally {
      this.busyVolcano.set(false);
    }
  }

  /** Dry-run first; the user sees what will be deleted and must confirm. */
  async apply(action: Record<string, unknown>): Promise<void> {
    try {
      const plan = (await this.repository.applyQc({ ...action, min_reads: this.minReads() }))['plan'] as Json;
      const text = t('Isto altera o banco do projeto ativo e não pode ser desfeito sem reingerir. {f} features, {r} reads e {s} amostras serão removidas. Continuar?', {
        f: plan['features_removed'], r: plan['reads_removed'], s: plan['samples_removed']
      });
      if (!window.confirm(text)) return;
      await this.repository.applyQc({ ...action, min_reads: this.minReads(), confirm: true });
      this.messages.add({ severity: 'success', summary: t('Controle de qualidade'), detail: t('Alteração aplicada.') });
      this.changed.emit();
      await this.load();
    } catch (error) {
      this.messages.add({ severity: 'error', summary: t('Controle de qualidade'), detail: error instanceof Error ? error.message : t('Falha inesperada.') });
    }
  }
}
