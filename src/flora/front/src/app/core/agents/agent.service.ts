import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { t } from '../i18n/i18n';
import { LlmService } from '../llm/llm.service';
import { FloraRepository } from '../data/flora.repository';
import { AGENTS, agentById } from './agent.catalog';
import { nextId, routeAgent, runAgent } from './agent.engine';
import { AgentAction, AgentId, AgentMessage, AgentReply, AgentRun } from './agent.models';

const SESSION_KEY = 'flora.agent.session';

@Injectable({ providedIn: 'root' })
export class AgentService {
  private readonly repo = inject(FloraRepository);
  private readonly router = inject(Router);
  private readonly llm = inject(LlmService);

  readonly agents = AGENTS;
  readonly selected = signal<AgentId | 'auto'>('auto');
  readonly messages = signal<AgentMessage[]>(this.restore());
  readonly runs = signal<AgentRun[]>([]);
  readonly busy = signal(false);
  readonly pendingActions = computed(() =>
    this.messages().flatMap((m) => m.actions ?? []).filter((a) => !a.applied).length
  );

  /** Suggested prompts, tuned to the page the researcher is on. */
  suggestionsFor(url: string): string[] {
    if (url.startsWith('/pipeline')) return [t('Quais amostras falharam no QC?'), t('A ingestão está pronta para confirmar?')];
    if (url.startsWith('/ml')) return [t('Qual modelo está melhor e com que ressalvas?'), t('Resuma os táxons diferenciais')];
    if (url.startsWith('/reports')) return [t('O relatório está completo para exportar?'), t('Liste os parâmetros que entram em Métodos')];
    if (url.startsWith('/explorer')) return [t('Compare a diversidade entre os grupos'), t('Quais táxons diferem entre grupos?')];
    return [t('Dê um resumo do estudo'), t('Quais amostras falharam no QC?'), t('Compare a diversidade entre os grupos')];
  }

  async ask(prompt: string): Promise<void> {
    const text = prompt.trim();
    if (!text || this.busy()) return;
    const agentId = await this.pickAgent(text);
    const pending: AgentMessage = { id: nextId('msg'), role: 'agent', agentId, text: '', pending: true, at: new Date() };
    this.push({ id: nextId('msg'), role: 'user', text, at: new Date() }, pending);
    this.busy.set(true);

    const run: AgentRun = { id: nextId('run'), agentId, prompt: text, startedAt: new Date(), status: 'running', steps: [], summary: '', actions: [] };
    this.runs.update((r) => [run, ...r]);
    try {
      const reply: AgentReply = text.length < 4 ? this.helpReply(agentId) : await runAgent(this.repo, agentId, text);
      this.patch(pending.id, { text: reply.text, steps: reply.steps, actions: reply.actions, pending: false });
      this.patchRun(run.id, { status: 'done', steps: reply.steps, summary: reply.text, actions: reply.actions });
      if (this.llm.ready() && reply.steps.length) await this.interpret(pending.id, text, reply);
    } catch (err) {
      const msg = err instanceof Error ? err.message : t('erro desconhecido');
      this.patch(pending.id, { text: t('Não consegui concluir: {msg}. Nada foi alterado.', { msg }), pending: false });
      this.patchRun(run.id, { status: 'failed', summary: msg });
    } finally {
      this.busy.set(false);
    }
  }

  async apply(action: AgentAction): Promise<void> {
    await this.router.navigate([action.path], { queryParams: action.queryParams });
    this.markApplied(action.id);
  }

  clear(): void {
    this.messages.set([]);
    this.persist();
  }

  agentName(id: AgentId | undefined): string {
    return id ? agentById(id).name : t('Agente');
  }

  /** Keyword routing; with a light model configured, it classifies the intent instead. */
  private async pickAgent(text: string): Promise<AgentId> {
    const keyword = routeAgent(text, this.selected());
    if (this.selected() !== 'auto' || !this.llm.ready() || !this.llm.settings().routerModel || text.length < 4) return keyword;
    try {
      const id = await this.llm.classify(text, AGENTS.map((a) => ({ id: a.id, role: a.role })));
      return (id as AgentId | null) ?? keyword;
    } catch {
      return keyword;
    }
  }

  /** Optional step: a model explains the facts; failure never blocks the computed answer. */
  private async interpret(id: string, question: string, reply: AgentReply): Promise<void> {
    this.patch(id, { llm: { status: 'pending', model: this.llm.settings().model } });
    try {
      const out = await this.llm.interpret(question, reply.text, reply.steps.map((s) => `${s.tool}: ${s.detail}`));
      this.patch(id, { llm: { status: 'ok', model: out.model, text: out.text, ms: out.elapsedMs } });
    } catch (err) {
      this.patch(id, { llm: { status: 'error', model: this.llm.settings().model, error: err instanceof Error ? err.message : String(err) } });
    }
  }

  private helpReply(agentId: AgentId): AgentReply {
    return { agentId, steps: [], actions: [], text: t('Pergunte algo sobre diversidade, QC, táxons, modelos ou o relatório.') };
  }

  private markApplied(id: string): void {
    this.messages.update((list) =>
      list.map((m) => (m.actions ? { ...m, actions: m.actions.map((a) => (a.id === id ? { ...a, applied: true } : a)) } : m))
    );
    this.persist();
  }

  private push(...msgs: AgentMessage[]): void {
    this.messages.update((l) => [...l, ...msgs]);
    this.persist();
  }
  private patch(id: string, p: Partial<AgentMessage>): void {
    this.messages.update((l) => l.map((m) => (m.id === id ? { ...m, ...p } : m)));
    this.persist();
  }
  private patchRun(id: string, p: Partial<AgentRun>): void {
    this.runs.update((l) => l.map((r) => (r.id === id ? { ...r, ...p } : r)));
  }

  private persist(): void {
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(this.messages().filter((m) => !m.pending).slice(-40)));
    } catch { /* ignore */ }
  }
  private restore(): AgentMessage[] {
    try {
      const raw = sessionStorage.getItem(SESSION_KEY);
      return raw ? (JSON.parse(raw) as AgentMessage[]).map((m) => ({ ...m, at: new Date(m.at) })) : [];
    } catch { return []; }
  }
}
