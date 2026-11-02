import { DecimalPipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule } from '@angular/forms';
import { MessageService, PrimeTemplate } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { TooltipModule } from 'primeng/tooltip';
import { ToggleSwitchModule } from 'primeng/toggleswitch';

import { t } from '../../core/i18n/i18n';
import { TPipe } from '../../core/i18n/t.pipe';
import { LOCAL_MODELS, PROVIDERS, Placement, isInstalled, placement } from '../../core/llm/llm.catalog';
import { LocalModel, ProviderId } from '../../core/llm/llm.models';
import { LlmService } from '../../core/llm/llm.service';
import { MascotComponent } from '../../shared/mascot.component';

@Component({
  selector: 'flora-ai-models',
  standalone: true,
  imports: [TPipe, DecimalPipe, FormsModule, ReactiveFormsModule, PrimeTemplate, TooltipModule, ButtonModule, InputNumberModule, InputTextModule, SelectModule, TableModule, TagModule, ToggleSwitchModule, MascotComponent],
  template: `
    <section class="page">
      <header class="page-heading">
        <div>
          <p class="kicker">{{ 'Modelos de IA' | t }}</p>
          <h1>{{ 'Modelos locais ou qualquer API compatível com OpenAI' | t }}</h1>
          <p class="lede">{{ 'Os modelos apenas interpretam resultados calculados pelas ferramentas determinísticas do FLORA. Eles nunca calculam diversidade, abundância ou estatística.' | t }}</p>
        </div>
        <flora-mascot name="laptop" [size]="90" [alt]="'Mascote FLORA com laptop' | t" />
      </header>

      <div class="ai-grid">
        <form class="surface filters" [formGroup]="form" (ngSubmit)="save()">
          <div class="section-title"><h2>{{ 'Conexão' | t }}</h2>
            <p-tag [value]="llm.mode === 'proxy' ? t('Via backend FLORA') : t('Direto do navegador')" severity="secondary" /></div>

          <label class="switch"><p-toggleswitch formControlName="enabled" inputId="llmOn" />
            <span>{{ 'Usar o modelo para interpretar as respostas dos agentes' | t }}</span></label>

          <div class="field"><label for="provider">{{ 'Provedor' | t }}</label>
            <p-select inputId="provider" [options]="providers" formControlName="provider" optionLabel="label" optionValue="id" appendTo="body" [fluid]="true" (onChange)="onProvider($event.value)" /></div>

          <div class="field"><label for="baseUrl">{{ 'URL base' | t }}</label>
            <input id="baseUrl" pInputText formControlName="baseUrl" placeholder="http://127.0.0.1:11434/v1" autocomplete="off" spellcheck="false" /></div>

          @if (needsKey()) {
            <div class="field"><label for="apiKey">{{ 'Chave de API' | t }}</label>
              <input id="apiKey" pInputText type="password" formControlName="apiKey" autocomplete="off"
                     [placeholder]="llm.settings().hasApiKey ? t('•••• guardada no servidor (deixe vazio para manter)') : 'sk-…'" />
              <small class="note">{{ 'Ou defina a variável de ambiente no servidor (GEMINI_API_KEY, OPENAI_API_KEY ou OPENROUTER_API_KEY).' | t }}</small>
              @if (llm.mode === 'direct') { <small class="warn">{{ 'Sem backend, a chave fica no localStorage deste navegador. Prefira rodar o backend FLORA.' | t }}</small> }
            </div>
          }

          <div class="two">
            <div class="field"><label for="model">{{ 'Modelo principal' | t }}</label>
              <p-select inputId="model" [options]="modelOptions()" formControlName="model" [editable]="true" appendTo="body" [fluid]="true" [placeholder]="'qwen3:4b'" /></div>
            <div class="field"><label for="router">{{ 'Modelo leve (roteamento)' | t }}</label>
              <p-select inputId="router" [options]="modelOptions()" formControlName="routerModel" [editable]="true" appendTo="body" [fluid]="true" [showClear]="true" [placeholder]="'qwen3:1.7b'" /></div>
          </div>

          <div class="two">
            <div class="field"><label for="temp">{{ 'Temperatura' | t }}</label>
              <p-inputnumber inputId="temp" formControlName="temperature" [min]="0" [max]="2" [step]="0.1" [minFractionDigits]="1" [maxFractionDigits]="2" [fluid]="true" /></div>
            <div class="field"><label for="tok">{{ 'Máx. de tokens' | t }}</label>
              <p-inputnumber inputId="tok" formControlName="maxTokens" [min]="16" [max]="8192" [fluid]="true" /></div>
          </div>

          <div class="actions">
            <p-button type="submit" [label]="'Salvar' | t" icon="pi pi-check" [loading]="saving()" />
            <p-button type="button" [label]="'Testar conexão' | t" icon="pi pi-bolt" severity="secondary" [outlined]="true" [loading]="llm.status() === 'testing'" (onClick)="test()" />
          </div>

          @if (llm.status() !== 'idle' && llm.status() !== 'testing') {
            <p class="state" [class.ok]="llm.status() === 'ok'" [class.bad]="llm.status() === 'error'" role="status">
              <i [class]="llm.status() === 'ok' ? 'pi pi-check-circle' : 'pi pi-exclamation-triangle'"></i>
              {{ llm.statusMessage() }}
              @if (llm.latencyMs() !== null && llm.status() === 'ok') { <small>· {{ llm.latencyMs() }} ms</small> }
            </p>
          }
        </form>

        <aside class="surface help">
          <h2>{{ 'Como ligar' | t }}</h2>
          <ol>
            <li>{{ 'Instale o Ollama e baixe um modelo:' | t }} <code>ollama pull qwen3:4b</code></li>
            <li>{{ 'Escolha o provedor Ollama, clique em Testar conexão e selecione o modelo.' | t }}</li>
            <li>{{ 'Ative "Usar o modelo" e pergunte algo ao copiloto: a interpretação do modelo aparece abaixo da resposta calculada.' | t }}</li>
          </ol>
          @if (llm.mode === 'direct') {
            <p class="note">{{ 'Modo direto: libere esta origem no servidor local, por exemplo' | t }} <code>OLLAMA_ORIGINS=http://localhost:4200 ollama serve</code>.</p>
          }
          <p class="note">{{ 'Qualquer servidor compatível com OpenAI funciona: LM Studio, llama.cpp, vLLM, OpenAI, OpenRouter ou um gateway próprio.' | t }}</p>
        </aside>
      </div>

      <article class="surface">
        <div class="section-title">
          <h2>{{ 'Modelos leves recomendados para teste' | t }}</h2>
          <div class="vram"><label for="vram">{{ 'VRAM da GPU (GB)' | t }}</label>
            <p-inputnumber inputId="vram" [ngModel]="vram()" (ngModelChange)="setVram($event)" [ngModelOptions]="{ standalone: true }" [min]="2" [max]="48" [step]="1" /></div>
        </div>
        <p class="note">{{ 'Tamanhos são estimativas de quantização de ~4 bits, sem o cache KV. As tags do Ollama são sugestões: confirme na biblioteca do Ollama.' | t }}</p>
        <p-table [value]="catalog()" dataKey="id" styleClass="flora-table">
          <ng-template pTemplate="header">
            <tr><th>{{ 'Modelo' | t }}</th><th>{{ 'Uso no FLORA' | t }}</th><th>~GB</th><th>{{ 'Na sua GPU' | t }}</th><th>{{ 'Estado' | t }}</th><th></th></tr>
          </ng-template>
          <ng-template pTemplate="body" let-m>
            <tr>
              <td><strong>{{ m.model.name }}</strong><br /><small class="note">{{ m.model.family }} · <code>{{ m.model.tag }}</code></small></td>
              <td>{{ m.model.role }}</td>
              <td>{{ m.model.sizeGb | number:'1.1-1' }}</td>
              <td><p-tag [value]="placementLabel(m.place)" [severity]="m.place === 'gpu' ? 'success' : m.place === 'tight' ? 'warn' : 'secondary'" /></td>
              <td>@if (m.installed) { <p-tag [value]="'Instalado' | t" severity="success" /> } @else { <small class="note">{{ 'não detectado' | t }}</small> }</td>
              <td class="row-actions">
                <p-button size="small" [label]="'Usar' | t" [outlined]="true" (onClick)="use(m.model, 'model')" />
                <p-button size="small" icon="pi pi-clone" [text]="true" severity="secondary" [pTooltip]="'Copiar comando' | t" [ariaLabel]="'Copiar comando' | t" (onClick)="copyPull(m.model)" />
              </td>
            </tr>
          </ng-template>
        </p-table>
      </article>
    </section>
  `,
  styles: [`
    .ai-grid { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); gap: 12px; align-items: start; }
    .two { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .switch { display: flex; align-items: center; gap: 10px; }
    .warn { color: var(--flora-warn); }
    .state { display: flex; gap: 8px; align-items: center; margin: 0; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--flora-border); }
    .state.ok { color: var(--flora-ok); } .state.bad { color: var(--flora-fail); }
    .help ol { padding-left: 18px; display: grid; gap: 6px; margin: 8px 0; }
    .vram { display: flex; align-items: center; gap: 8px; }
    .row-actions { display: flex; gap: 4px; justify-content: flex-end; }
    @media (max-width: 1000px) { .ai-grid, .two { grid-template-columns: 1fr; } }
  `]
})
export class AiModelsPageComponent {
  protected readonly llm = inject(LlmService);
  private readonly fb = inject(FormBuilder);
  private readonly messages = inject(MessageService);
  protected readonly t = t;
  protected readonly providers = [...PROVIDERS];
  protected readonly saving = signal(false);
  protected readonly vram = signal(this.llm.settings().vramGb);

  protected readonly form = this.fb.nonNullable.group({
    enabled: this.llm.settings().enabled,
    provider: this.llm.settings().provider as ProviderId,
    baseUrl: this.llm.settings().baseUrl,
    apiKey: '',
    model: this.llm.settings().model,
    routerModel: this.llm.settings().routerModel,
    temperature: this.llm.settings().temperature,
    maxTokens: this.llm.settings().maxTokens
  });

  protected readonly needsKey = computed(() => {
    const id = this.form.controls.provider.value;
    return PROVIDERS.find((p) => p.id === id)?.needsKey || id === 'custom';
  });
  protected readonly modelOptions = computed(() => this.llm.models());
  protected readonly catalog = computed(() =>
    LOCAL_MODELS.map((model) => ({ model, place: placement(model.sizeGb, this.vram()), installed: isInstalled(model.tag, this.llm.models()) })));

  constructor() {
    if (this.llm.settings().baseUrl) void this.llm.test();
  }

  protected onProvider(id: ProviderId): void {
    const preset = PROVIDERS.find((p) => p.id === id);
    if (preset?.baseUrl) this.form.controls.baseUrl.setValue(preset.baseUrl);
  }

  protected placementLabel(p: Placement): string {
    return p === 'gpu' ? t('Cabe na GPU') : p === 'tight' ? t('Justo') : t('Precisa de offload');
  }

  protected setVram(v: number | null): void {
    const value = v ?? 6;
    this.vram.set(value);
    void this.llm.save({ vramGb: value });
  }

  protected use(model: LocalModel, field: 'model' | 'routerModel'): void {
    this.form.controls[field].setValue(model.tag);
    this.form.controls.provider.setValue('ollama');
    this.onProvider('ollama');
  }

  protected async copyPull(model: LocalModel): Promise<void> {
    try {
      await navigator.clipboard.writeText(`ollama pull ${model.tag}`);
      this.messages.add({ severity: 'success', summary: t('Copiado'), detail: `ollama pull ${model.tag}` });
    } catch {
      this.messages.add({ severity: 'warn', summary: t('Copiar comando'), detail: `ollama pull ${model.tag}` });
    }
  }

  protected async test(): Promise<void> {
    const v = this.form.getRawValue();
    await this.llm.test({ baseUrl: v.baseUrl, model: v.model, apiKey: v.apiKey || undefined });
  }

  protected async save(): Promise<void> {
    const v = this.form.getRawValue();
    this.saving.set(true);
    try {
      await this.llm.save({
        enabled: v.enabled, provider: v.provider, baseUrl: v.baseUrl.trim(), model: v.model.trim(), routerModel: v.routerModel.trim(),
        temperature: v.temperature, maxTokens: v.maxTokens, ...(v.apiKey ? { apiKey: v.apiKey } : {})
      });
      this.form.controls.apiKey.setValue('');
      this.messages.add({ severity: 'success', summary: t('Modelos de IA'), detail: t('Configuração salva.') });
      await this.llm.test();
    } catch (err) {
      this.messages.add({ severity: 'error', summary: t('Modelos de IA'), detail: err instanceof Error ? err.message : t('Falha ao salvar.') });
    } finally {
      this.saving.set(false);
    }
  }
}
