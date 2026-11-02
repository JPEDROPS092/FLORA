import { Component, ElementRef, HostListener, afterNextRender, inject, signal, viewChild } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ButtonModule } from 'primeng/button';

import { WorkspaceStore } from '../../core/workspace/workspace.store';
import { INSTITUTIONS, TECH_GROUPS } from '../../shared/brand.data';
import { MascotComponent } from '../../shared/mascot.component';
import { TechBadgeComponent } from '../../shared/tech-badge.component';
import { TPipe } from '../../core/i18n/t.pipe';
import { t } from '../../core/i18n/i18n';

interface Slide { id: string; label: string }

/** Landing as a scroll-snap presentation. ←/→, PageUp/PageDown or the dots navigate. */

@Component({
  selector: 'flora-welcome',
  standalone: true,
  imports: [TPipe, RouterLink, ButtonModule, MascotComponent, TechBadgeComponent],
  template: `
    <div class="deck" #deck (scroll)="onScroll()" tabindex="0" [attr.aria-label]="'Apresentação do FLORA' | t">
      <!-- 1 · Hero -->
      <section class="slide hero" id="s-hero">
        <div class="copy">
          <img class="wordmark" src="branding/logo/wordmark.webp" [attr.alt]="'FLORA' | t" width="420" />
          <p class="tag">{{ 'Plataforma de análise de microbioma 16S, assistida por IA.' | t }}</p>
          <p class="lede">{{ 'Do dado bruto ao relatório reprodutível: ingestão, diversidade, taxonomia, modelos e agentes que explicam cada passo.' | t }}</p>
          <div class="cta">
            <p-button [label]="'Entrar no workspace' | t" icon="pi pi-arrow-right" iconPos="right" routerLink="/dashboard" />
            <p-button [label]="'Falar com o copiloto' | t" icon="pi pi-sparkles" [outlined]="true" (onClick)="store.copilotOpen.set(true)" />
          </div>
          <p class="hint"><kbd>←</kbd> <kbd>→</kbd> {{ 'navegam pela apresentação ·' | t }} <kbd>{{ 'Ctrl K' | t }}</kbd> {{ 'abre a paleta' | t }}</p>
        </div>
        <flora-mascot class="hero-mascot" name="wave" [size]="360" [alt]="'Mascote FLORA acenando' | t" />
      </section>

      <!-- 2 · Fluxo -->
      <section class="slide" id="s-flow">
        <header class="head"><p class="kicker">{{ 'O fluxo' | t }}</p><h2>{{ 'Cinco etapas, um só lugar' | t }}</h2>
          <p class="lede">{{ 'Cada etapa deixa proveniência: parâmetros, versões e seed.' | t }}</p></header>
        <ol class="flow">
          @for (s of flow; track s.t; let i = $index) {
            <li><span class="n">{{ i + 1 }}</span><i [class]="s.i"></i><strong>{{ s.t }}</strong><small>{{ s.d }}</small></li>
          }
        </ol>
        <flora-mascot class="corner" name="binoculars" [size]="190" />
      </section>

      <!-- 3 · Módulos -->
      <section class="slide" id="s-modules">
        <header class="head"><p class="kicker">{{ 'Módulos' | t }}</p><h2>{{ 'Tudo abre com um estudo de demonstração' | t }}</h2>
          <p class="lede">{{ '80 amostras, 1.842 ASVs, três grupos. Troque para a API Python em um único arquivo.' | t }}</p></header>
        <div class="mods">
          @for (m of modules; track m.to) {
            <a class="mod" [routerLink]="m.to"><i [class]="m.i"></i><strong>{{ m.t }}</strong><small>{{ m.d }}</small></a>
          }
        </div>
        <flora-mascot class="corner" name="laptop" [size]="200" />
      </section>

      <!-- 4 · IA -->
      <section class="slide ai" id="s-ai">
        <header class="head"><p class="kicker">{{ 'Agentes de IA' | t }}</p><h2>{{ 'Uma equipe que mostra o trabalho' | t }}</h2>
          <p class="lede">{{ 'Os agentes leem os dados, registram cada passo e' | t }} <b>{{ 'propõem' | t }}</b> {{ 'ações. Você confirma; nada muda sozinho.' | t }}</p></header>
        <div class="agents">
          @for (a of agentCards; track a.t) {
            <div class="agent"><i [class]="a.i"></i><strong>{{ a.t }}</strong><small>{{ a.d }}</small></div>
          }
        </div>
        <div class="cta"><p-button [label]="'Conhecer os agentes' | t" icon="pi pi-sparkles" routerLink="/agents" /></div>
        <flora-mascot class="corner" name="celebrate" [size]="190" />
      </section>

      <!-- 5 · Bibliotecas (2 slides) -->
      @for (part of stackParts; track part.id) {
        <section class="slide stack" [id]="part.id">
          <header class="head"><p class="kicker">{{ 'Construído com ·' | t }} {{ part.n }}/2</p><h2>{{ part.title }}</h2>
            <p class="lede">{{ 'Clique em qualquer uma para abrir a documentação.' | t }}</p></header>
          <div class="groups">
            @for (g of part.groups; track g.title) {
              <div class="group">
                <h3>{{ g.title }} <small>{{ g.blurb }}</small></h3>
                <div class="grid">@for (t of g.items; track t.name) { <flora-tech-badge [item]="t" /> }</div>
              </div>
            }
          </div>
        </section>
      }

      <!-- 6 · Fontes de dados -->
      <section class="slide data" id="s-data" [style.--bg]="'url(branding/scenes/sampling.webp)'">
        <header class="head"><p class="kicker">{{ 'Fontes de dados' | t }}</p><h2>{{ 'De onde vêm os datasets' | t }}</h2>
          <p class="lede">{{ 'Repositórios públicos mantidos por instituições de pesquisa. Os downloads entram direto no DuckDB.' | t }}</p></header>
        <div class="insts">@for (i of institutions; track i.name) { <flora-tech-badge [inst]="i" /> }</div>
        <p class="legal">{{ 'Siglas tipográficas ilustrativas; marcas e logotipos oficiais pertencem às respectivas instituições.' | t }}</p>
      </section>

      <!-- 7 · CTA -->
      <section class="slide end" id="s-end" [style.--bg]="'url(branding/scenes/camp.webp)'">
        <div class="end-card">
          <img src="branding/logo/badge.webp" alt="" width="96" height="96" />
          <h2>{{ 'Pronto para explorar?' | t }}</h2>
          <p class="lede">{{ 'Comece pelo painel ou pergunte ao copiloto o que investigar primeiro.' | t }}</p>
          <div class="cta">
            <p-button [label]="'Abrir painel' | t" icon="pi pi-th-large" routerLink="/dashboard" />
            <p-button [label]="'Pipeline Studio' | t" icon="pi pi-sitemap" [outlined]="true" routerLink="/pipeline" />
          </div>
        </div>
        <flora-mascot class="corner big" name="fishing" [size]="260" />
      </section>
    </div>

    <nav class="dots" [attr.aria-label]="'Slides' | t">
      @for (s of slides; track s.id; let i = $index) {
        <button type="button" [class.on]="i === current()" (click)="go(i)" [attr.aria-label]="s.label" [attr.aria-current]="i === current()" [title]="s.label"></button>
      }
    </nav>
  `,
  styleUrl: './welcome-page.component.css'
})
export class WelcomePageComponent {
  protected readonly store = inject(WorkspaceStore);
  private readonly deck = viewChild.required<ElementRef<HTMLElement>>('deck');
  protected readonly current = signal(0);
  protected readonly stackParts = [
    { id: 's-stack-1', n: 1, title: t('Interface e dados'), groups: TECH_GROUPS.slice(0, 2) },
    { id: 's-stack-2', n: 2, title: t('IA e pipeline de amplicons'), groups: TECH_GROUPS.slice(2) }
  ];
  protected readonly institutions = INSTITUTIONS;

  protected readonly slides: Slide[] = [
    { id: 's-hero', label: t('Início') }, { id: 's-flow', label: t('Fluxo') }, { id: 's-modules', label: t('Módulos') },
    { id: 's-ai', label: t('Agentes de IA') }, { id: 's-stack-1', label: t('Bibliotecas: interface e dados') }, { id: 's-stack-2', label: t('Bibliotecas: IA e pipeline') }, { id: 's-data', label: t('Fontes de dados') }, { id: 's-end', label: t('Começar') }
  ];
  protected readonly flow = [
    { i: 'pi pi-upload', t: t('Ingestão'), d: t('Metadata, tabela de ASVs e taxonomia reconciliadas, com QC por amostra.') },
    { i: 'pi pi-sliders-h', t: t('Normalização'), d: t('Rarefação, TSS ou CLR com os parâmetros registrados.') },
    { i: 'pi pi-chart-scatter', t: t('Exploração'), d: t('Alfa, beta, PCoA e taxonomia com filtros sincronizados.') },
    { i: 'pi pi-microchip', t: t('Modelagem'), d: t('Random Forest e XGBoost, ROC e SHAP com ressalvas explícitas.') },
    { i: 'pi pi-file', t: t('Relatório'), d: t('Seções editáveis, métodos e exportação HTML/PDF.') }
  ];
  protected readonly modules = [
    { to: '/dashboard', i: 'pi pi-th-large', t: t('Painel'), d: t('Visão geral do estudo e diagnóstico.') },
    { to: '/explorer', i: 'pi pi-chart-scatter', t: t('Explorer'), d: t('PCoA, diversidade, taxonomia, relações.') },
    { to: '/pipeline', i: 'pi pi-sitemap', t: t('Pipeline Studio'), d: t('Ingestão guiada e QC.') },
    { to: '/ml', i: 'pi pi-microchip', t: t('AI & ML Lab'), d: t('Modelos, SHAP e agrupamentos.') },
    { to: '/reports', i: 'pi pi-file', t: t('Relatório'), d: t('Construtor científico exportável.') },
    { to: '/downloads', i: 'pi pi-download', t: t('Downloads'), d: t('MGnify, SRA, EMP e sintéticos.') }
  ];
  protected readonly agentCards = [
    { i: 'pi pi-chart-scatter', t: t('Analista de diversidade'), d: t('Compara grupos e abre a vista certa.') },
    { i: 'pi pi-shield', t: t('Auditor de qualidade'), d: t('Lê o QC e diz se a ingestão pode fechar.') },
    { i: 'pi pi-microchip', t: t('Taxonomista & ML'), d: t('Táxons diferenciais e modelos com ressalvas.') },
    { i: 'pi pi-file-edit', t: t('Redator científico'), d: t('Checa seções, métodos e lacunas.') }
  ];

  constructor() {
    afterNextRender(() => this.deck().nativeElement.focus({ preventScroll: true }));
  }

  onScroll(): void {
    const el = this.deck().nativeElement;
    this.current.set(Math.round(el.scrollTop / el.clientHeight));
  }

  go(i: number): void {
    const n = Math.max(0, Math.min(this.slides.length - 1, i));
    const el = this.deck().nativeElement;
    el.scrollTo({ top: n * el.clientHeight, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  }

  @HostListener('document:keydown', ['$event'])
  onKey(e: KeyboardEvent): void {
    const t = e.target as HTMLElement | null;
    if (e.ctrlKey || e.metaKey || e.altKey || t?.closest('input,textarea,select,[contenteditable]')) return;
    if (['ArrowRight', 'PageDown'].includes(e.key)) { e.preventDefault(); this.go(this.current() + 1); }
    else if (['ArrowLeft', 'PageUp'].includes(e.key)) { e.preventDefault(); this.go(this.current() - 1); }
    else if (e.key === 'Home') { this.go(0); }
    else if (e.key === 'End') { this.go(this.slides.length - 1); }
  }
}
