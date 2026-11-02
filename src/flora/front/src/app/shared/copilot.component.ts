import { DatePipe } from '@angular/common';
import { AfterViewChecked, Component, ElementRef, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { NavigationEnd, Router } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { ButtonModule } from 'primeng/button';
import { DrawerModule } from 'primeng/drawer';
import { filter, map } from 'rxjs';

import { AgentService } from '../core/agents/agent.service';
import { MascotComponent } from './mascot.component';
import { WorkspaceStore } from '../core/workspace/workspace.store';
import { TPipe } from '../core/i18n/t.pipe';

/** Right-hand AI copilot, available on every page. Agents propose; the researcher confirms. */

@Component({
  selector: 'flora-copilot',
  standalone: true,
  imports: [TPipe, MascotComponent, DatePipe, FormsModule, ButtonModule, DrawerModule],
  template: `
    <p-drawer [visible]="store.copilotOpen()" (visibleChange)="store.copilotOpen.set($event)"
              position="right" [modal]="false" [style]="{ width: 'min(440px, 100vw)' }" styleClass="copilot-drawer">
      <ng-template #header>
        <div class="cp-head"><i class="pi pi-sparkles"></i><strong>{{ 'Copiloto FLORA' | t }}</strong></div>
      </ng-template>

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

      <div class="cp-thread" #thread aria-live="polite">
        @if (!svc.messages().length) {
          <div class="cp-empty">
            <flora-mascot name="wave" [size]="130" />
            <p>{{ 'Pergunte sobre o estudo. Os agentes leem os dados, mostram os passos e' | t }} <b>{{ 'propõem' | t }}</b> {{ 'ações — você confirma.' | t }}</p>
          </div>
        }
        @for (m of svc.messages(); track m.id) {
          <article class="msg" [class.user]="m.role === 'user'">
            @if (m.role === 'agent') { <header><i class="pi pi-sparkles"></i>{{ svc.agentName(m.agentId) }}<time>{{ m.at | date:'HH:mm' }}</time></header> }
            @if (m.pending) {
              <p class="thinking"><span></span><span></span><span></span> {{ 'analisando dados…' | t }}</p>
            } @else {
              <p>{{ m.text }}</p>
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
  private readonly router = inject(Router);
  private readonly thread = viewChild<ElementRef<HTMLElement>>('thread');

  protected readonly draft = signal('');
  private readonly url = toSignal(
    this.router.events.pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd), map((e) => e.urlAfterRedirects)),
    { initialValue: this.router.url }
  );
  private lastCount = 0;

  suggestions = () => this.svc.suggestionsFor(this.url());

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
