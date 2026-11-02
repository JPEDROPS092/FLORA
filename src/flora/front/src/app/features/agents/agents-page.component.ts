import { DatePipe } from '@angular/common';
import { Component, inject } from '@angular/core';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';

import { AgentService } from '../../core/agents/agent.service';
import { WorkspaceStore } from '../../core/workspace/workspace.store';

@Component({
  selector: 'flora-agents',
  standalone: true,
  imports: [DatePipe, ButtonModule, TagModule],
  template: `
    <section class="page">
      <header class="page-heading">
        <div>
          <p class="kicker">Agentes de IA</p>
          <h1>Equipe de análise assistida</h1>
          <p class="lede">Cada agente lê os dados do estudo, registra os passos e propõe ações. Nada muda sem sua confirmação.</p>
        </div>
        <p-tag value="Respostas simuladas · ancoradas nos dados" severity="secondary" />
      </header>

      <div class="agent-grid">
        @for (a of svc.agents; track a.id) {
          <article class="surface agent-card">
            <div class="agent-top"><i [class]="a.icon"></i><div><h2>{{ a.name }}</h2><p class="note">{{ a.role }}</p></div></div>
            <p>{{ a.description }}</p>
            <ul class="tools">@for (t of a.tools; track t) { <li><code>{{ t }}</code></li> }</ul>
            <div class="starters">
              @for (s of a.starters; track s) {
                <button type="button" (click)="run(a.id, s)">{{ s }}</button>
              }
            </div>
          </article>
        }
      </div>

      <article class="surface">
        <div class="section-title">
          <h2>Execuções desta sessão</h2>
          <p>{{ svc.pendingActions() }} ações propostas aguardando confirmação</p>
        </div>
        @for (r of svc.runs(); track r.id) {
          <details class="run">
            <summary>
              <span class="dot" [class]="r.status"></span>
              <strong>{{ svc.agentName(r.agentId) }}</strong>
              <span class="prompt">{{ r.prompt }}</span>
              <time>{{ r.startedAt | date:'HH:mm:ss' }}</time>
            </summary>
            <p>{{ r.summary || 'Em execução…' }}</p>
            <ol>@for (s of r.steps; track s.tool) { <li><code>{{ s.tool }}</code> {{ s.label }} <small>— {{ s.detail }}</small></li> }</ol>
            <div class="cp-actions">
              @for (a of r.actions; track a.id) { <p-button size="small" [label]="a.label" [icon]="a.icon" [outlined]="true" (onClick)="svc.apply(a)" /> }
            </div>
          </details>
        } @empty {
          <p class="note">Nenhuma execução ainda. Escolha uma pergunta inicial acima ou abra o copiloto (Ctrl+J).</p>
        }
      </article>
    </section>
  `
})
export class AgentsPageComponent {
  protected readonly svc = inject(AgentService);
  private readonly store = inject(WorkspaceStore);

  run(agent: Parameters<AgentService['selected']['set']>[0], prompt: string): void {
    this.svc.selected.set(agent);
    this.store.copilotOpen.set(true);
    void this.svc.ask(prompt);
  }
}
