import { DecimalPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TagModule } from 'primeng/tag';

import { FloraRepository } from '../../core/data/flora.repository';
import { ClusterSummary, MlExperiment, ModelComparisonRow } from '../../core/models/domain';
import { PlotCardComponent } from '../../shared/plot-card.component';
import { TPipe } from '../../core/i18n/t.pipe';
import { t } from '../../core/i18n/i18n';

@Component({
  selector: 'flora-ml-lab',
  standalone: true,
  host: { class: 'flora-dark lab-root' },
  imports: [TPipe, 
    DecimalPipe,
    ReactiveFormsModule,
    ButtonModule,
    InputNumberModule,
    InputTextModule,
    SelectModule,
    TagModule,
    PlotCardComponent
  ],
  template: `
    <section class="page">
      <header class="page-heading">
        <div>
          <p class="kicker">{{ 'AI & ML Lab' | t }}</p>
          <h1>{{ 'Predição de compartimento' | t }}</h1>
          <p class="lede">{{ 'Comparação de modelos, matriz de confusão, ROC e importância. O tema escuro fica só neste módulo.' | t }}</p>
        </div>
        @if (mocked()) { <p-tag [value]="'Dados mockados' | t" severity="secondary" /> }
      </header>

      <div class="lab-grid">
        <aside class="surface stack">
          <div class="section-title"><h2>{{ 'Experimentos' | t }}</h2></div>
          @for (experiment of experiments(); track experiment.id) {
            <button type="button" class="section-list" (click)="selected.set(experiment)" [class.active]="selected()?.id === experiment.id" style="display:grid;text-align:left;background:transparent;border:1px solid var(--flora-border);border-radius:8px;padding:8px;color:inherit;cursor:pointer">
              <strong>{{ experiment.name }}</strong>
              <span class="note">{{ experiment.status }} {{ '· acc' | t }} {{ experiment.accuracy | number:'1.2-2' }} {{ '· seed' | t }} {{ experiment.provenance.seed }}</span>
            </button>
          }
          @if (!experiments().length) {
            <p class="note">{{ 'Nenhum experimento nesta sessão. Treine um modelo para registrar a corrida.' | t }}</p>
          }
        </aside>

        <div class="stack">
          <article class="surface">
            <div class="section-title"><h2>{{ 'Comparação' | t }}</h2><p>{{ 'Última corrida concluída de cada modelo.' | t }}</p></div>
            <table class="comparison">
              <thead>
                <tr><th>{{ 'Modelo' | t }}</th><th>{{ 'Acurácia' | t }}</th><th>{{ 'F1 macro' | t }}</th><th>{{ 'ROC AUC' | t }}</th><th>{{ 'CV' | t }}</th><th>{{ 'Seed' | t }}</th><th>{{ 'Features' | t }}</th></tr>
              </thead>
              <tbody>
                @for (row of rows(); track row.experimentId) {
                  <tr>
                    <td>{{ row.model }}</td>
                    <td>{{ row.accuracy | number:'1.3-3' }}</td>
                    <td>{{ row.f1Macro | number:'1.3-3' }}</td>
                    <td>{{ row.rocAuc === null ? '—' : (row.rocAuc | number:'1.2-2') }}</td>
                    <td>{{ row.cvAccuracyMean | number:'1.3-3' }}</td>
                    <td>{{ row.seed }}</td>
                    <td>{{ row.features }}</td>
                  </tr>
                } @empty {
                  <tr><td colspan="7">{{ 'Sem métricas comparáveis.' | t }}</td></tr>
                }
              </tbody>
            </table>
          </article>

          <section class="split">
            <form class="surface filters" [formGroup]="trainForm" (ngSubmit)="train()">
              <div class="section-title"><h2>{{ 'Treinar' | t }}</h2></div>
              <div class="field">
                <label for="model">{{ 'Modelo' | t }}</label>
                <p-select inputId="model" [options]="models" formControlName="model" optionLabel="label" optionValue="value" appendTo="body" [fluid]="true" />
              </div>
              <div class="field">
                <label for="target">{{ 'Coluna alvo' | t }}</label>
                <input id="target" pInputText formControlName="targetColumn" />
              </div>
              <div class="field">
                <label for="trainFilter">{{ 'Filtro de treino' | t }}</label>
                <input id="trainFilter" pInputText formControlName="trainFilter" />
                @if (trainForm.controls.trainFilter.invalid && trainForm.controls.trainFilter.touched) {
                  <small class="field-error">{{ 'O filtro de treino é obrigatório.' | t }}</small>
                }
              </div>
              <div class="field">
                <label for="testFilter">{{ 'Filtro de teste' | t }}</label>
                <input id="testFilter" pInputText formControlName="testFilter" />
                @if (trainForm.controls.testFilter.invalid && trainForm.controls.testFilter.touched) {
                  <small class="field-error">{{ 'O filtro de teste é obrigatório.' | t }}</small>
                }
              </div>
              <div class="field">
                <label for="folds">{{ 'Dobras de CV' | t }}</label>
                <p-inputnumber inputId="folds" formControlName="cvFolds" [min]="2" [max]="10" [fluid]="true" />
              </div>
              <div class="field">
                <label for="seed">{{ 'Seed' | t }}</label>
                <p-inputnumber inputId="seed" formControlName="seed" [fluid]="true" />
              </div>
              <p-button type="submit" [label]="'Registrar experimento' | t" [loading]="busy()" />
            </form>

            <form class="surface filters" [formGroup]="clusterForm" (ngSubmit)="cluster()">
              <div class="section-title"><h2>{{ 'Agrupamento' | t }}</h2></div>
              <div class="field">
                <label for="clusterMethod">{{ 'Método' | t }}</label>
                <p-select inputId="clusterMethod" [options]="clusterMethods" formControlName="method" optionLabel="label" optionValue="value" appendTo="body" [fluid]="true" />
              </div>
              <div class="field">
                <label for="k">{{ 'Grupos' | t }}</label>
                <p-inputnumber inputId="k" formControlName="nClusters" [min]="2" [max]="8" [fluid]="true" />
              </div>
              <p-button type="submit" [label]="'Agrupar' | t" severity="secondary" [loading]="busy()" />
              @if (clusterResult(); as result) {
                <p [class]="result.success ? 'status-pass' : 'status-fail'">
                  @if (result.success) {
                    {{ result.method }} · k={{ result.nClusters }} · silhueta {{ result.silhouette | number:'1.2-2' }}
                    @if (result.daviesBouldin !== null) { · Davies–Bouldin {{ result.daviesBouldin | number:'1.2-2' }} }
                    @if (result.noiseFraction) { {{ '· ruído' | t }} {{ result.noiseFraction | number:'1.2-2' }} }
                  } @else {
                    {{ result.error }}
                  }
                </p>
              }
            </form>
          </section>

          @if (selected(); as experiment) {
            <section class="split">
              <article class="surface">
                <div class="section-title"><h2>{{ 'Matriz de confusão' | t }}</h2><p>{{ experiment.model }}</p></div>
                <flora-plot [result]="experiment.confusion" theme="dark" [height]="320" />
              </article>
              <article class="surface">
                <div class="section-title"><h2>{{ 'ROC' | t }}</h2><p>{{ 'Uma curva por classe' | t }}</p></div>
                <flora-plot [result]="experiment.roc" theme="dark" [height]="320" />
              </article>
            </section>
            <article class="surface">
              <div class="section-title">
                <h2>{{ experiment.importanceKind === 'shap' ? t('SHAP médio') : t('Importância do modelo') }}</h2>
                <p>{{ 'Valor assinado quando a fonte entrega SHAP.' | t }}</p>
              </div>
              <flora-plot [result]="experiment.importance" theme="dark" [height]="360" />
            </article>
            <section class="split">
              <article class="surface">
                <div class="section-title"><h2>{{ 'Configuração' | t }}</h2></div>
                <dl class="param-list">
                  @for (item of experiment.config; track item.label) {
                    <div><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></div>
                  }
                </dl>
              </article>
              <article class="surface">
                <div class="section-title"><h2>{{ 'Limitações' | t }}</h2></div>
                <ul class="limitations">
                  @for (item of experiment.limitations; track item) { <li>{{ item }}</li> }
                </ul>
                <h3>{{ 'Histórico' | t }}</h3>
                <ul class="limitations">
                  @for (event of experiment.provenance.history; track event.at + event.event) {
                    <li>{{ event.at }} — {{ event.event }}</li>
                  }
                </ul>
              </article>
            </section>
          }
        </div>
      </div>
    </section>
  `
})
export class MlLabPageComponent {
  protected readonly t = t;
  private readonly repository = inject(FloraRepository);
  private readonly messages = inject(MessageService);
  private readonly fb = inject(FormBuilder);

  readonly experiments = signal<MlExperiment[]>([]);
  readonly rows = signal<ModelComparisonRow[]>([]);
  readonly selected = signal<MlExperiment | null>(null);
  readonly clusterResult = signal<ClusterSummary | null>(null);
  readonly busy = signal(false);
  readonly mocked = signal(true);

  readonly models = [
    { label: 'Random Forest', value: 'random_forest' },
    { label: 'XGBoost', value: 'xgboost' }
  ];
  readonly clusterMethods = [
    { label: 'k-means', value: 'kmeans' },
    { label: 'HDBSCAN', value: 'hdbscan' }
  ];

  readonly trainForm = this.fb.nonNullable.group({
    model: ['random_forest' as const, Validators.required],
    targetColumn: ['group', Validators.required],
    trainFilter: ["site != 'Janaúba'", Validators.required],
    testFilter: ["site = 'Janaúba'", Validators.required],
    normalize: ['clr' as const],
    cvFolds: [5, [Validators.required, Validators.min(2), Validators.max(10)]],
    seed: [42, Validators.required]
  });

  readonly clusterForm = this.fb.nonNullable.group({
    method: ['kmeans' as const, Validators.required],
    nClusters: [3, [Validators.required, Validators.min(2)]],
    normalize: ['clr' as const],
    seed: [42, Validators.required]
  });

  constructor() {
    void this.reload();
  }

  async train(): Promise<void> {
    if (this.trainForm.invalid) {
      this.trainForm.markAllAsTouched();
      return;
    }
    this.busy.set(true);
    try {
      const experiment = await this.repository.trainModel(this.trainForm.getRawValue());
      this.messages.add({
        severity: experiment.status === 'completed' ? 'success' : 'error',
        summary: 'Experimento',
        detail: experiment.error ?? `${experiment.model} registrado.`
      });
      await this.reload(experiment.id);
    } finally {
      this.busy.set(false);
    }
  }

  async cluster(): Promise<void> {
    if (this.clusterForm.invalid) {
      this.clusterForm.markAllAsTouched();
      return;
    }
    this.busy.set(true);
    try {
      const result = await this.repository.clusterSamples(this.clusterForm.getRawValue());
      this.clusterResult.set(result);
      this.messages.add({
        severity: result.success ? 'success' : 'error',
        summary: 'Agrupamento',
        detail: result.success ? t('{method} concluído.', { method: result.method }) : result.error
      });
    } finally {
      this.busy.set(false);
    }
  }

  private async reload(selectId?: string): Promise<void> {
    const [experiments, rows] = await Promise.all([this.repository.experiments(), this.repository.comparison()]);
    this.experiments.set(experiments);
    this.rows.set(rows);
    this.mocked.set(experiments[0]?.mocked ?? true);
    const next = experiments.find((item) => item.id === selectId) ?? experiments[0] ?? null;
    this.selected.set(next);
  }
}
