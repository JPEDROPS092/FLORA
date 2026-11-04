import { DatePipe } from '@angular/common';
import { AfterViewChecked, Component, ElementRef, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { NavigationEnd, Router } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { DrawerModule } from 'primeng/drawer';
import { filter, map } from 'rxjs';

import { AgentService } from '../core/agents/agent.service';
import { AgentArtifactComponent } from './agent-artifact.component';
import { MascotComponent } from './mascot.component';
import { LlmService } from '../core/llm/llm.service';
import { WorkspaceStore } from '../core/workspace/workspace.store';
import { TPipe } from '../core/i18n/t.pipe';

/** Right-hand AI copilot, available on every page. Agents propose; the researcher confirms. */

@Component({
  selector: 'flora-copilot',
  standalone: true,
  imports: [RouterLink, TPipe, MascotComponent, AgentArtifactComponent, DatePipe, FormsModule, ButtonModule, DrawerModule],
  template: `
    <p-drawer [visible]="store.copilotOpen()" (visibleChange)="store.copilotOpen.set($event)"
              position="right" [modal]="false" [style]="{ width: wide() ? 'min(900px, 100vw)' : 'min(440px, 100vw)' }" styleClass="copilot-drawer">
      <ng-template #header>
        <div class="cp-head"><i class="pi pi-sparkles"></i><strong>{{ 'Copiloto FLORA' | t }}</strong>
          <a class="cp-model" routerLink="/settings" [class.off]="!llm.ready()" [attr.title]="'Modelos de IA' | t">
            <i class="pi pi-microchip"></i>{{ llm.ready() ? llm.settings().model : ('Sem modelo' | t) }}</a>
          <button type="button" class="cp-wide" (click)="wide.set(!wide())" [attr.aria-pressed]="wide()"
                  [attr.title]="(wide() ? 'Recolher o painel' : 'Ampliar o painel') | t" [attr.aria-label]="(wide() ? 'Recolher o painel' : 'Ampliar o painel') | t">
            <i [class]="wide() ? 'pi pi-window-minimize' : 'pi pi-window-maximize'"></i></button></div>
      </ng-template>

      <div class="cp-mode" role="radiogroup" [attr.aria-label]="'Modo do copiloto' | t">
        <button type="button" role="radio" [attr.aria-checked]="svc.mode() === 'operator'" [class.on]="svc.mode() === 'operator'" [disabled]="!svc.operatorAvailable()"
                [attr.title]="(svc.operatorAvailable() ? 'O modelo opera o app: busca, baixa, ingere, analisa e faz gráficos' : 'Ative um modelo (API ou Ollama) em Modelos de IA') | t"
                (click)="svc.setMode('operator')"><i class="pi pi-bolt"></i>{{ 'Operador (LLM)' | t }}</button>
        <button type="button" role="radio" [attr.aria-checked]="svc.mode() === 'agents'" [class.on]="svc.mode() === 'agents'" (click)="svc.setMode('agents')"><i class="pi pi-users"></i>{{ 'Agentes' | t }}</button>
      </div>

      @if (!svc.usingOperator()) {
      <div class="cp-agents" role="radiogroup" [attr.aria-label]="'Agente' | t">
        <button type="button" role="radio" [attr.aria-checked]="svc.selected() === 'auto'"
                [class.on]="svc.selected() === 'auto'" (click)="svc.selected.set('auto')">{{ 'Auto' | t }}</button>
        @for (a of svc.agents; track a.id) {
          <button type="button" role="radio" [attr.aria-checked]="svc.selected() === a.id"
                  [class.on]="svc.selected() === a.id" [title]="a.role" (click)="svc.selected.set(a.id)">
            <i [class]="a.icon"></i>{{ a.name.split(' ')[0] }}
          </button>
        }
      </div>
      }

      <div class="cp-thread" #thread aria-live="polite">
        @if (!svc.messages().length) {
          <div class="cp-empty">
            <flora-mascot name="wave" [size]="130" />
            <p>{{ 'Pergunte sobre o estudo. Os agentes leem os dados, mostram os passos e' | t }} <b>{{ 'propõem' | t }}</b> {{ 'ações — você confirma.' | t }}</p>
          </div>
        }
        @for (m of svc.messages(); track m.id) {
          <article class="msg" [class.user]="m.role === 'user'">
            @if (m.role === 'agent') { <header><i class="pi pi-sparkles"></i>{{ m.operator ? ('Operador' | t) : svc.agentName(m.agentId) }}<time>{{ m.at | date:'HH:mm' }}</time></header> }
            @if (m.pending) {
              <p class="thinking"><span></span><span></span><span></span> {{ (m.operator ? 'operando o app…' : 'analisando dados…') | t }}</p>
            } @else {
              <p class="md">{{ m.text }}</p>
            }
            @for (a of m.artifacts ?? []; track $index) { <flora-agent-artifact [artifact]="a" [wide]="wide()" /> }
            @if (m.approvals?.length) {
              <div class="cp-approvals" role="group" [attr.aria-label]="'Ações que precisam da sua aprovação' | t">
                @for (ap of m.approvals; track ap.id) {
                  <div class="cp-approval" [class.done]="m.decided?.[ap.id]">
                    <div><strong><i class="pi pi-shield"></i> {{ ap.tool }}</strong><small>{{ ap.description }}</small>
                      <code>{{ argsText(ap.arguments) }}</code></div>
                    @if (m.decided?.[ap.id]; as d) {
                      <span class="cp-decision" [class.no]="d === 'rejected'">{{ (d === 'approved' ? 'Aprovado' : 'Recusado') | t }}</span>
                    } @else {
                      <div class="cp-approve-btns">
                        <p-button size="small" icon="pi pi-check" [label]="'Aprovar' | t" [disabled]="svc.busy()" (onClick)="svc.decide(m.id, ap, true)" />
                        <p-button size="small" icon="pi pi-times" [label]="'Recusar' | t" severity="secondary" [outlined]="true" [disabled]="svc.busy()" (onClick)="svc.decide(m.id, ap, false)" />
                      </div>
                    }
                  </div>
                }
              </div>
            }
            @if (m.llm; as l) {
              <div class="llm-note" [class.err]="l.status === 'error'">
                <header><i class="pi pi-microchip"></i>{{ 'Interpretação do modelo' | t }} · <code>{{ l.model }}</code>@if (l.ms) { <small>{{ l.ms }} ms</small> }</header>
                @if (m.operator) { <small>{{ 'Gerado por LLM chamando as ferramentas do FLORA; os números vêm do código, não do modelo.' | t }}</small> }
                @else if (l.status === 'pending') { <p class="thinking"><span></span><span></span><span></span> {{ 'o modelo está lendo os resultados…' | t }}</p> }
                @else if (l.status === 'ok') { <p>{{ l.text }}</p><small>{{ 'Gerado por LLM a partir dos resultados acima; não é evidência experimental.' | t }}</small> }
                @else { <small>{{ 'Modelo indisponível' | t }}: {{ l.error }}</small> }
              </div>
            }
            @if (m.steps?.length) {
              <details class="trace">
                <summary>{{ m.steps!.length }} {{ 'passos executados' | t }}</summary>
                <ol>
                  @for (s of m.steps; track s.tool) {
                    <li><code>{{ s.tool }}</code> {{ s.label }} <small>— {{ s.detail }} · {{ s.ms }} {{ 'ms' | t }}</small></li>
                  }
                </ol>
              </details>
            }
            @if (m.actions?.length) {
              <div class="cp-actions">
                @for (a of m.actions; track a.id) {
                  <p-button size="small" [icon]="a.applied ? 'pi pi-check' : a.icon" [label]="a.label"
                            [severity]="a.applied ? 'secondary' : 'primary'" [outlined]="!a.applied"
                            (onClick)="svc.apply(a)" />
                }
              </div>
            }
          </article>
        }
      </div>

      <div class="cp-foot">
        <div class="cp-suggest">
          @for (s of suggestions(); track s) { <button type="button" (click)="send(s)">{{ s }}</button> }
        </div>
        <form (ngSubmit)="send(draft())" class="cp-form">
          <textarea rows="2" name="draft" [ngModel]="draft()" (ngModelChange)="draft.set($event)"
                    (keydown.enter)="onEnter($event)" [placeholder]="'Pergunte ou peça uma análise…  (Enter envia)' | t"
                    [attr.aria-label]="'Mensagem para o agente' | t"></textarea>
          <p-button type="submit" icon="pi pi-send" [loading]="svc.busy()" [ariaLabel]="'Enviar' | t" />
        </form>
        <button type="button" class="cp-clear" (click)="svc.clear()" [disabled]="!svc.messages().length">{{ 'Limpar conversa' | t }}</button>
      </div>
    </p-drawer>
  `
})
export class CopilotComponent implements AfterViewChecked {
  protected readonly store = inject(WorkspaceStore);
  protected readonly svc = inject(AgentService);
  protected readonly llm = inject(LlmService);
  private readonly router = inject(Router);
  private readonly thread = viewChild<ElementRef<HTMLElement>>('thread');

  protected readonly draft = signal('');
  private readonly url = toSignal(
    this.router.events.pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd), map((e) => e.urlAfterRedirects)),
    { initialValue: this.router.url }
  );
  private lastCount = 0;

  protected readonly wide = signal(false);
  suggestions = () => (this.svc.usingOperator() ? this.svc.operatorSuggestions() : this.svc.suggestionsFor(this.url()));
  argsText(args: Record<string, unknown>): string {
    return Object.entries(args).map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`).join(' · ') || '—';
  }

  send(text: string): void {
    if (!text.trim()) return;
    this.draft.set('');
    void this.svc.ask(text);
  }
  onEnter(e: Event): void {
    const ev = e as KeyboardEvent;
    if (!ev.shiftKey) { ev.preventDefault(); this.send(this.draft()); }
  }
  ngAfterViewChecked(): void {
    const el = this.thread()?.nativeElement;
    const n = this.svc.messages().length;
    if (el && n !== this.lastCount) { this.lastCount = n; el.scrollTop = el.scrollHeight; }
  }
}
