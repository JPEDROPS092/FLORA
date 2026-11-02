import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { FloraRepository } from '../data/flora.repository';
import { LANG, t } from '../i18n/i18n';
import { PROVIDERS } from './llm.catalog';
import { ChatMessage, ChatResult, LlmSettings, LlmStatus, PullJob } from './llm.models';

const KEY = 'flora.llm';
const DEFAULTS: LlmSettings = {
  enabled: false, provider: 'ollama', baseUrl: PROVIDERS[0].baseUrl, apiKey: '', hasApiKey: false,
  model: '', routerModel: '', temperature: 0.2, maxTokens: 700, nCtx: 4096, nGpuLayers: -1, vramGb: 6
};

/** Strips <think> blocks that reasoning models (Qwen3, …) may emit. */
export const stripReasoning = (s: string): string => s.replace(/<think>[\s\S]*?<\/think>/gi, '').trim();

/**
 * LLM gateway. With the Python backend (HTTP mode) calls go through `/api/llm/*` and the
 * API key stays on the server. With the mock study (no backend) the browser calls the
 * OpenAI-compatible endpoint directly, so local servers must allow this origin
 * (e.g. Ollama: OLLAMA_ORIGINS) and any key lives in this browser's localStorage.
 * Models only interpret facts computed by deterministic tools.
 */
@Injectable({ providedIn: 'root' })
export class LlmService {
  private readonly repo = inject(FloraRepository);
  private readonly http = inject(HttpClient);

  readonly mode: 'proxy' | 'direct' = this.repo.source.mocked ? 'direct' : 'proxy';
  readonly settings = signal<LlmSettings>(this.restore());
  readonly models = signal<string[]>([]);
  readonly status = signal<LlmStatus>('idle');
  readonly statusMessage = signal('');
  readonly latencyMs = signal<number | null>(null);
  readonly ready = computed(() => this.settings().enabled && !!this.settings().model.trim() && (!!this.settings().baseUrl || this.settings().provider === 'native'));

  constructor() {
    if (this.mode === 'proxy') void this.loadRemote();
  }

  // ---- settings ----------------------------------------------------------
  async save(patch: Partial<LlmSettings>): Promise<void> {
    const next = { ...this.settings(), ...patch };
    if (this.mode === 'direct') {
      this.settings.set(next);
      this.persist(next);
      return;
    }
    const body: Record<string, unknown> = {
      enabled: next.enabled, provider: next.provider, base_url: next.baseUrl, model: next.model,
      router_model: next.routerModel, temperature: next.temperature, max_tokens: next.maxTokens,
      n_ctx: next.nCtx, n_gpu_layers: next.nGpuLayers
    };
    if (patch.apiKey !== undefined) body['api_key'] = patch.apiKey;
    const res = await this.post<{ settings: Record<string, unknown> }>('/api/llm/config', body);
    this.settings.set(this.fromRemote(res.settings, next.vramGb));
    this.persist({ ...this.settings(), apiKey: '' });
  }

  async test(draft?: Partial<LlmSettings>): Promise<void> {
    const s = { ...this.settings(), ...draft };
    this.status.set('testing');
    this.statusMessage.set('');
    try {
      if (this.mode === 'proxy') {
        const res = await this.post<{ success: boolean; error?: string; latency_ms?: number; models?: string[]; model_available?: boolean; models_dir?: string }>(
          '/api/llm/test', { provider: s.provider, base_url: s.baseUrl, model: s.model, ...(draft?.apiKey ? { api_key: draft.apiKey } : {}) });
        if (!res.success) throw new Error(res.error || t('Sem resposta do servidor.'));
        this.models.set(res.models ?? []);
        this.latencyMs.set(res.latency_ms ?? null);
        this.finishTest(!!s.model, !!res.model_available, s.model);
        if (res.models_dir && this.status() !== 'error') this.statusMessage.set(`${this.statusMessage()} ${res.models_dir}`);
      } else {
        if (s.provider === 'native') throw new Error(t('O llama.cpp embutido exige o backend FLORA (flora ui). Sem backend, use o Ollama ou outro servidor.'));
        const started = performance.now();
        this.models.set(await this.listDirect(s));
        this.latencyMs.set(Math.round(performance.now() - started));
        this.finishTest(!!s.model, this.models().some((m) => m === s.model || m.split(':')[0] === s.model), s.model);
      }
    } catch (err) {
      this.status.set('error');
      this.statusMessage.set(this.explain(err, s));
    }
  }

  // ---- GGUF download (backend only) -------------------------------------
  readonly pull = signal<PullJob | null>(null);
  private pullTimer: ReturnType<typeof setInterval> | null = null;

  async startPull(repo: string, file: string): Promise<void> {
    const res = await this.post<{ job: Record<string, unknown> }>('/api/llm/models/pull', { repo, file });
    this.pull.set(this.toJob(res.job));
    this.pullTimer ??= setInterval(() => void this.pollPull(), 1000);
  }

  async cancelPull(): Promise<void> {
    const id = this.pull()?.id;
    if (id) await this.post('/api/llm/models/pull/cancel', { id });
  }

  private async pollPull(): Promise<void> {
    const id = this.pull()?.id;
    if (!id) return;
    try {
      const res = await firstValueFrom(this.http.get<{ job: Record<string, unknown> }>(`${this.repo.source.apiBaseUrl}/api/llm/models/pull`, { params: { id } }));
      const job = this.toJob(res.job);
      this.pull.set(job);
      if (job.status !== 'queued' && job.status !== 'downloading') {
        if (this.pullTimer) { clearInterval(this.pullTimer); this.pullTimer = null; }
        if (job.status === 'done') void this.test();
      }
    } catch { /* keep polling; the job may be momentarily unavailable */ }
  }

  private toJob(r: Record<string, unknown>): PullJob {
    return { id: String(r['id']), repo: String(r['repo']), file: String(r['file']), status: r['status'] as PullJob['status'],
      bytesDone: Number(r['bytes_done'] ?? 0), bytesTotal: Number(r['bytes_total'] ?? 0), percent: Number(r['percent'] ?? 0), error: String(r['error'] ?? '') };
  }

  // ---- chat --------------------------------------------------------------
  async chat(messages: ChatMessage[], model?: string): Promise<ChatResult> {
    const s = this.settings();
    if (this.mode === 'proxy') {
      const r = await this.post<{ model: string; text: string; elapsed_ms: number }>('/api/llm/chat', {
        messages, model: model || undefined, temperature: s.temperature, max_tokens: s.maxTokens });
      return { model: r.model, text: r.text, elapsedMs: r.elapsed_ms };
    }
    if (s.provider === 'native') throw new Error(t('O llama.cpp embutido exige o backend FLORA (flora ui). Sem backend, use o Ollama ou outro servidor.'));
    const started = performance.now();
    const body = await this.direct<{ choices: { message: { content: string } }[] }>(s, '/chat/completions', {
      model: model || s.model, messages, temperature: s.temperature, max_tokens: s.maxTokens, stream: false });
    return { model: model || s.model, text: stripReasoning(body.choices?.[0]?.message?.content ?? ''), elapsedMs: Math.round(performance.now() - started) };
  }

  /** Ask the model to explain facts that deterministic tools already computed. */
  interpret(question: string, facts: string, steps: string[]): Promise<ChatResult> {
    const rules = LANG === 'pt'
      ? 'Você é o intérprete científico do FLORA (microbioma 16S). Use SOMENTE os fatos fornecidos. Não invente números, táxons nem referências. Não calcule resultados novos. Aponte limitações em uma frase. No máximo 110 palavras, texto corrido, sem títulos. Responda em português.'
      : 'You are FLORA\'s scientific interpreter (16S microbiome). Use ONLY the facts provided. Do not invent numbers, taxa or references. Do not compute new results. State limitations in one sentence. At most 110 words, plain prose, no headings. Answer in English.';
    return this.chat([
      { role: 'system', content: rules },
      { role: 'user', content: `${LANG === 'pt' ? 'Pergunta' : 'Question'}: ${question}\n\n${LANG === 'pt' ? 'Fatos calculados' : 'Computed facts'}:\n${facts}\n\n${LANG === 'pt' ? 'Passos executados' : 'Steps run'}: ${steps.join('; ')}` }
    ]);
  }

  // ---- internals ---------------------------------------------------------
  private finishTest(hasModel: boolean, available: boolean, model: string): void {
    if (hasModel && !available) {
      this.status.set('error');
      this.statusMessage.set(t('Conectado, mas o modelo "{model}" não está instalado neste servidor.', { model }));
    } else {
      this.status.set('ok');
      this.statusMessage.set(hasModel ? t('Conexão e modelo OK.') : t('Conexão OK. Escolha um modelo.'));
    }
  }

  private explain(err: unknown, s: LlmSettings): string {
    const msg = err instanceof Error ? err.message : String(err);
    if (this.mode === 'direct' && (err instanceof TypeError || /failed to fetch|networkerror|load failed/i.test(msg))) {
      return t('Não foi possível alcançar {url}. Confirme se o servidor está ativo e, no Ollama, defina OLLAMA_ORIGINS para esta origem.', { url: s.baseUrl });
    }
    return msg;
  }

  private async listDirect(s: LlmSettings): Promise<string[]> {
    const body = await this.direct<{ data?: { id: string }[] }>(s, '/models');
    return (body.data ?? []).map((m) => m.id.replace(/^models\//, '')).sort();
  }

  private async direct<T>(s: LlmSettings, path: string, payload?: unknown): Promise<T> {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 120_000);
    try {
      const res = await fetch(`${s.baseUrl.replace(/\/$/, '')}${path}`, {
        method: payload ? 'POST' : 'GET', signal: ctrl.signal,
        headers: { 'Content-Type': 'application/json', ...(s.apiKey ? { Authorization: `Bearer ${s.apiKey}` } : {}) },
        body: payload ? JSON.stringify(payload) : undefined
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${(await res.text()).slice(0, 200)}`);
      return (await res.json()) as T;
    } finally { clearTimeout(timer); }
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    try {
      return await firstValueFrom(this.http.post<T>(`${this.repo.source.apiBaseUrl}${path}`, body));
    } catch (err) {
      const e = err as { error?: { error?: string }; message?: string };
      throw new Error(e.error?.error || e.message || 'request failed');
    }
  }

  private async loadRemote(): Promise<void> {
    try {
      const res = await firstValueFrom(this.http.get<{ settings: Record<string, unknown> }>(`${this.repo.source.apiBaseUrl}/api/llm/config`));
      this.settings.set(this.fromRemote(res.settings, this.settings().vramGb));
    } catch { /* backend without LLM routes: keep defaults */ }
  }

  private fromRemote(r: Record<string, unknown>, vramGb: number): LlmSettings {
    return {
      enabled: !!r['enabled'], provider: (r['provider'] as LlmSettings['provider']) ?? 'ollama', baseUrl: String(r['base_url'] ?? ''),
      apiKey: '', hasApiKey: !!r['has_api_key'], model: String(r['model'] ?? ''), routerModel: String(r['router_model'] ?? ''),
      temperature: Number(r['temperature'] ?? 0.2), maxTokens: Number(r['max_tokens'] ?? 700),
      nCtx: Number(r['n_ctx'] ?? 4096), nGpuLayers: Number(r['n_gpu_layers'] ?? -1), vramGb
    };
  }

  private persist(s: LlmSettings): void {
    try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* ignore */ }
  }

  private restore(): LlmSettings {
    try {
      const raw = localStorage.getItem(KEY);
      return raw ? { ...DEFAULTS, ...(JSON.parse(raw) as Partial<LlmSettings>) } : { ...DEFAULTS };
    } catch { return { ...DEFAULTS }; }
  }
}
