import { DecimalPipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { PrimeTemplate } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { DrawerModule } from 'primeng/drawer';
import { ProgressBarModule } from 'primeng/progressbar';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { interval, startWith, switchMap } from 'rxjs';

import { FloraRepository } from '../../core/data/flora.repository';
import { DashboardSnapshot, DiagnosticEntry, RecentAnalysis, ResearchProject } from '../../core/models/domain';
import { PlotCardComponent } from '../../shared/plot-card.component';

import { MascotComponent } from '../../shared/mascot.component';
import { WorkflowStepsComponent } from '../../shared/workflow-steps.component';
import { TPipe } from '../../core/i18n/t.pipe';

@Component({
  selector: 'flora-dashboard',
  standalone: true,
  imports: [TPipe, 
    MascotComponent,
    WorkflowStepsComponent,
    DecimalPipe,
    RouterLink,
    PrimeTemplate,
    ButtonModule,
    DrawerModule,
    ProgressBarModule,
    TableModule,
    TagModule,
    PlotCardComponent
  ],
  template: `
    <section class="page">
      <header class="page-heading">
        <div>
          <p class="kicker">{{ 'Research Dashboard' | t }}</p>
          <h1>{{ snapshot()?.studyName || ('Carregando estudo' | t) }}</h1>
          <p class="lede">
            {{ snapshot()?.studyId }} · {{ snapshot()?.marker || '16S' }}
            @if (snapshot()?.mocked) { {{ '· coorte de demonstração, não é um ensaio publicado.' | t }} }
          </p>
        </div>
        <div class="head-side">
          @if (snapshot()?.mocked) { <p-tag [value]="'Dados mockados' | t" severity="secondary" /> }
          <flora-mascot name="binoculars" [size]="84" [alt]="'Mascote FLORA com binóculos' | t" />
        </div>
      </header>

      <flora-workflow-steps />

      <nav class="questions">
        <span>{{ 'O que você deseja investigar?' | t }}</span>
        <a routerLink="/explorer" [queryParams]="{ question: 'diversity' }">{{ 'Diversidade entre grupos' | t }}</a>
        <a routerLink="/explorer" [queryParams]="{ question: 'differential' }">{{ 'Táxons diferenciais' | t }}</a>
        <a routerLink="/explorer" [queryParams]="{ question: 'clustering' }">{{ 'Agrupamentos' | t }}</a>
        <a routerLink="/ml">{{ 'Predição via ML' | t }}</a>
        <a routerLink="/reports">{{ 'Exportação reprodutível' | t }}</a>
      </nav>

      <section class="metrics">
        <article class="surface metric">
          <div class="label">{{ 'Amostras' | t }}</div>
          <div class="value">{{ snapshot()?.samples | number }}</div>
          <div class="hint">{{ snapshot()?.quality?.pass }} {{ 'passam no QC' | t }}</div>
        </article>
        <article class="surface metric">
          <div class="label">{{ 'ASVs' | t }}</div>
          <div class="value">{{ snapshot()?.asvs | number }}</div>
          <div class="hint">{{ 'tabela de features 16S' | t }}</div>
        </article>
        <article class="surface metric">
          <div class="label">{{ 'Grupos' | t }}</div>
          <div class="value">{{ snapshot()?.groups | number }}</div>
          <div class="hint">{{ snapshot()?.groupNames?.join(' · ') }}</div>
        </article>
        <article class="surface metric">
          <div class="label">{{ 'Qualidade' | t }}</div>
          <div class="value">{{ passRate() | number:'1.0-0' }}%</div>
          <p-progressbar [value]="passRate()" [showValue]="false" />
          <div class="hint">{{ snapshot()?.quality?.warn }} {{ 'alertas ·' | t }} {{ snapshot()?.quality?.fail }} {{ 'falhas' | t }}</div>
        </article>
      </section>

      @if (snapshot()?.note) {
        <p class="note">{{ snapshot()?.note }}</p>
      }

      <section class="split">
        <article class="surface">
          <div class="section-title">
            <h2>{{ 'Diversidade alfa' | t }}</h2>
            <p>{{ 'Shannon, amostras acima da rarefação' | t }}</p>
          </div>
          <flora-plot [result]="snapshot()?.alpha ?? null" [height]="340" />
        </article>
        <article class="surface">
          <div class="section-title">
            <h2>{{ 'PCoA' | t }}</h2>
            <p>{{ 'Bray–Curtis · PC1 28,4% · PC2 14,1%' | t }}</p>
          </div>
          <flora-plot [result]="snapshot()?.pcoa ?? null" [height]="340" />
        </article>
      </section>

      <section class="split">
        <article class="surface">
          <div class="section-title">
            <h2>{{ 'Análises recentes' | t }}</h2>
            <a routerLink="/projects">{{ 'Projetos' | t }}</a>
          </div>
          <p-table [value]="snapshot()?.recent ?? []" [rows]="5" styleClass="flora-table" dataKey="id">
            <ng-template pTemplate="header">
              <tr>
                <th>{{ 'Análise' | t }}</th>
                <th>{{ 'Tipo' | t }}</th>
                <th>{{ 'Quando' | t }}</th>
                <th></th>
              </tr>
            </ng-template>
            <ng-template pTemplate="body" let-row>
              <tr>
                <td>{{ row.name }}<div class="note">{{ row.summary }}</div></td>
                <td>{{ row.kind }}</td>
                <td>{{ row.finishedAt }}</td>
                <td><p-button [label]="'Proveniência' | t" [text]="true" (onClick)="selected.set(row)" /></td>
              </tr>
            </ng-template>
            <ng-template pTemplate="emptymessage">
              <tr><td colspan="4">{{ 'Nenhuma análise registrada nesta fonte.' | t }}</td></tr>
            </ng-template>
          </p-table>
        </article>

        <article class="surface">
          <div class="section-title">
            <h2>{{ 'Projetos' | t }}</h2>
            <a routerLink="/projects">{{ 'Abrir biblioteca' | t }}</a>
          </div>
          <p-table [value]="projects()" dataKey="id">
            <ng-template pTemplate="header">
              <tr><th>{{ 'Projeto' | t }}</th><th>{{ 'Estado' | t }}</th><th>{{ 'Amostras' | t }}</th></tr>
            </ng-template>
            <ng-template pTemplate="body" let-project>
              <tr>
                <td>{{ project.name }}<div class="note">{{ project.question }}</div></td>
                <td>{{ project.status }}</td>
                <td>{{ project.samples | number }}</td>
              </tr>
            </ng-template>
          </p-table>
        </article>
      </section>

      <section class="surface" id="diagnostico">
        <div class="section-title">
          <div>
            <h2>{{ 'Diagnóstico' | t }}</h2>
            <p>{{ 'Log do workspace. Não é o resultado analítico.' | t }}</p>
          </div>
          <p-button [label]="'Atualizar' | t" [text]="true" icon="pi pi-refresh" (onClick)="reloadLogs()" />
        </div>
        <pre class="logs">@for (entry of logs(); track entry.timestamp + entry.message) {<span [class.log-warn]="entry.level === 'WARNING'" [class.log-error]="entry.level === 'ERROR'">{{ entry.timestamp }} {{ entry.level }} {{ entry.message }}
</span>}</pre>
      </section>
    </section>

    <p-drawer [visible]="!!selected()" (visibleChange)="selected.set($event ? selected() : null)" position="right" [style]="{ width: '420px' }" [header]="'Proveniência' | t">
      @if (selected(); as run) {
        <p class="note">{{ run.name }} {{ '· seed' | t }} {{ run.provenance.seed }} · {{ run.provenance.pipelineVersion }}</p>
        <dl class="param-list">
          @for (item of run.provenance.parameters; track item.label) {
            <div><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></div>
          }
        </dl>
        <h3>{{ 'Versões' | t }}</h3>
        <ul class="limitations">
          @for (pkg of run.provenance.packages; track pkg.name) {
            <li>{{ pkg.name }} {{ pkg.version }}</li>
          }
        </ul>
        <h3>{{ 'Histórico' | t }}</h3>
        <ul class="limitations">
          @for (event of run.provenance.history; track event.at + event.event) {
            <li>{{ event.at }} — {{ event.event }}</li>
          }
        </ul>
      }
    </p-drawer>
  `
})
export class DashboardPageComponent {
  private readonly repository = inject(FloraRepository);
  private readonly destroyRef = inject(DestroyRef);

  readonly snapshot = signal<DashboardSnapshot | null>(null);
  readonly projects = signal<ResearchProject[]>([]);
  readonly logs = signal<DiagnosticEntry[]>([]);
  readonly selected = signal<RecentAnalysis | null>(null);

  constructor() {
    void this.load();
    interval(30000)
      .pipe(
        startWith(0),
        switchMap(() => this.repository.diagnostics()),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe((entries) => this.logs.set(entries));
  }

  passRate(): number {
    const quality = this.snapshot()?.quality;
    const total = (quality?.pass ?? 0) + (quality?.warn ?? 0) + (quality?.fail ?? 0);
    if (!total) {
      return 0;
    }
    return (quality!.pass / total) * 100;
  }

  reloadLogs(): void {
    void this.repository.diagnostics().then((entries) => this.logs.set(entries));
  }

  private async load(): Promise<void> {
    const [snapshot, projects] = await Promise.all([this.repository.dashboard(), this.repository.projects()]);
    this.snapshot.set(snapshot);
    this.projects.set(projects);
  }
}
