import { Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';

import { FloraRepository } from '../core/data/flora.repository';
import { TPipe } from '../core/i18n/t.pipe';
import { t } from '../core/i18n/i18n';

type StepState = 'done' | 'todo' | 'blocked';

interface Step {
  id: string;
  title: string;
  detail: string;
  state: StepState;
  path: string;
  action: string;
}

/**
 * Download → Ingest → Analyse → Report, with the real state of each step, so nobody lands on empty charts
 * without knowing what is missing.
 */
@Component({
  selector: 'flora-workflow-steps',
  standalone: true,
  imports: [RouterLink, ButtonModule, TPipe],
  template: `
    <ol class="steps" [attr.aria-label]="'Fluxo de trabalho' | t">
      @for (step of steps(); track step.id; let i = $index) {
        <li [class]="step.state">
          <span class="num" aria-hidden="true">@if (step.state === 'done') { <i class="pi pi-check"></i> } @else if (step.state === 'blocked') { <i class="pi pi-lock"></i> } @else { {{ i + 1 }} }</span>
          <div class="body">
            <strong>{{ step.title }}</strong>
            <small>{{ step.detail }}</small>
            @if (step.state !== 'blocked') { <a [routerLink]="step.path">{{ step.action }}</a> }
          </div>
        </li>
      }
    </ol>
    @if (loaded() && !hasData()) {
      <div class="example">
        <span>{{ 'Quer só ver o FLORA funcionando?' | t }}</span>
        <p-button [label]="'Carregar exemplo' | t" icon="pi pi-bolt" size="small" [loading]="installing()" (onClick)="loadExample()" />
      </div>
    }
  `,
  styles: `
    .steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 8px; list-style: none; padding: 0; margin: 0; }
    .steps li { display: flex; gap: 10px; align-items: flex-start; border: 1px solid var(--flora-border); border-radius: var(--radius); padding: 10px 12px; background: var(--flora-surface); }
    .steps li.done { border-color: var(--flora-ok); }
    .steps li.blocked { opacity: .65; }
    .num { flex: none; width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; font-size: .78rem; font-weight: 700; background: var(--flora-primary-soft); color: var(--flora-primary); }
    .done .num { background: var(--flora-ok); color: #fff; }
    .body { display: grid; gap: 2px; font-size: .86rem; }
    .body small { color: var(--flora-muted); }
    .example { display: flex; gap: 12px; align-items: center; margin-top: 10px; font-size: .88rem; flex-wrap: wrap; }
  `
})
export class WorkflowStepsComponent {
  private readonly repository = inject(FloraRepository);
  private readonly router = inject(Router);
  private readonly messages = inject(MessageService);

  readonly loaded = signal(false);
  readonly samples = signal(0);
  readonly ready = signal(0);
  readonly installing = signal(false);
  readonly hasData = computed(() => this.samples() > 0);

  readonly steps = computed<Step[]>(() => {
    const ingested = this.samples() > 0;
    const downloaded = this.ready() > 0 || ingested;
    return [
      { id: 'download', title: t('1 · Baixar'), path: '/downloads', action: t('Abrir a biblioteca'), state: downloaded ? 'done' : 'todo',
        detail: downloaded ? t('{n} dataset(s) pronto(s) no disco', { n: this.ready() }) : t('Escolha um estudo na biblioteca') },
      { id: 'ingest', title: t('2 · Ingerir'), path: '/pipeline', action: t('Abrir o pipeline'), state: ingested ? 'done' : downloaded ? 'todo' : 'blocked',
        detail: ingested ? t('{n} amostras no projeto ativo', { n: this.samples() }) : downloaded ? t('Escolha o dataset baixado e confirme') : t('Baixe um dataset primeiro') },
      { id: 'analyse', title: t('3 · Analisar'), path: '/explorer', action: t('Abrir o Explorer'), state: ingested ? 'todo' : 'blocked',
        detail: ingested ? t('QC, diversidade, estatística e taxonomia') : t('Ingira os dados primeiro') },
      { id: 'report', title: t('4 · Relatório'), path: '/reports', action: t('Montar o relatório'), state: ingested ? 'todo' : 'blocked',
        detail: ingested ? t('Com versões, parâmetros e accessions') : t('Ingira os dados primeiro') }
    ];
  });

  constructor() {
    void this.refresh();
  }

  private async refresh(): Promise<void> {
    try {
      const [schema, datasets] = await Promise.all([this.repository.exploreSchema(), this.repository.datasets()]);
      this.samples.set(schema.counts.samples);
      this.ready.set(datasets.filter((d) => d.complete).length);
    } catch {
      /* without a reachable API the steps simply show the first one as pending */
    } finally {
      this.loaded.set(true);
    }
  }

  async loadExample(): Promise<void> {
    this.installing.set(true);
    try {
      const examples = await this.repository.examples();
      const demo = examples.find((e) => e.synthetic && e.installable) ?? examples.find((e) => e.installable);
      if (!demo) throw new Error(t('Nenhum exemplo disponível.'));
      await this.repository.installExample(demo.id);
      this.messages.add({ severity: 'success', summary: demo.name, detail: t('Exemplo em importação; acompanhe em Projetos.') });
      await this.router.navigateByUrl('/projects');
    } catch (error) {
      this.messages.add({ severity: 'error', summary: t('Exemplo'), detail: error instanceof Error ? error.message : t('Falha inesperada.') });
    } finally {
      this.installing.set(false);
    }
  }
}
