import { Component, ElementRef, HostListener, afterNextRender, inject, signal, viewChild } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ButtonModule } from 'primeng/button';

import { WorkspaceStore } from '../../core/workspace/workspace.store';
import { INSTITUTIONS, TECH_GROUPS } from '../../shared/brand.data';
import { MascotComponent } from '../../shared/mascot.component';
import { TechBadgeComponent } from '../../shared/tech-badge.component';

interface Slide { id: string; label: string }

/** Landing as a scroll-snap presentation. ←/→, PageUp/PageDown or the dots navigate. */
@Component({
  selector: 'flora-welcome',
  standalone: true,
  imports: [RouterLink, ButtonModule, MascotComponent, TechBadgeComponent],
  template: `
    <div class="deck" #deck (scroll)="onScroll()" tabindex="0" aria-label="Apresentação do FLORA">
      <!-- 1 · Hero -->
      <section class="slide hero" id="s-hero">
        <div class="copy">
          <img class="wordmark" src="branding/logo/wordmark.webp" alt="FLORA" width="420" />
          <p class="tag">Plataforma de análise de microbioma 16S, assistida por IA.</p>
          <p class="lede">Do dado bruto ao relatório reprodutível: ingestão, diversidade, taxonomia, modelos e agentes que explicam cada passo.</p>
          <div class="cta">
            <p-button label="Entrar no workspace" icon="pi pi-arrow-right" iconPos="right" routerLink="/dashboard" />
            <p-button label="Falar com o copiloto" icon="pi pi-sparkles" [outlined]="true" (onClick)="store.copilotOpen.set(true)" />
          </div>
          <p class="hint"><kbd>←</kbd> <kbd>→</kbd> navegam pela apresentação · <kbd>Ctrl K</kbd> abre a paleta</p>
        </div>
        <flora-mascot class="hero-mascot" name="wave" [size]="360" alt="Mascote FLORA acenando" />
      </section>

      <!-- 2 · Fluxo -->
      <section class="slide" id="s-flow">
        <header class="head"><p class="kicker">O fluxo</p><h2>Cinco etapas, um só lugar</h2>
          <p class="lede">Cada etapa deixa proveniência: parâmetros, versões e seed.</p></header>
        <ol class="flow">
          @for (s of flow; track s.t; let i = $index) {
            <li><span class="n">{{ i + 1 }}</span><i [class]="s.i"></i><strong>{{ s.t }}</strong><small>{{ s.d }}</small></li>
          }
        </ol>
        <flora-mascot class="corner" name="binoculars" [size]="190" />
      </section>

      <!-- 3 · Módulos -->
      <section class="slide" id="s-modules">
        <header class="head"><p class="kicker">Módulos</p><h2>Tudo abre com um estudo de demonstração</h2>
          <p class="lede">80 amostras, 1.842 ASVs, três grupos. Troque para a API Python em um único arquivo.</p></header>
        <div class="mods">
          @for (m of modules; track m.to) {
            <a class="mod" [routerLink]="m.to"><i [class]="m.i"></i><strong>{{ m.t }}</strong><small>{{ m.d }}</small></a>
          }
        </div>
        <flora-mascot class="corner" name="laptop" [size]="200" />
      </section>

      <!-- 4 · IA -->
      <section class="slide ai" id="s-ai">
        <header class="head"><p class="kicker">Agentes de IA</p><h2>Uma equipe que mostra o trabalho</h2>
          <p class="lede">Os agentes leem os dados, registram cada passo e <b>propõem</b> ações. Você confirma; nada muda sozinho.</p></header>
        <div class="agents">
          @for (a of agentCards; track a.t) {
            <div class="agent"><i [class]="a.i"></i><strong>{{ a.t }}</strong><small>{{ a.d }}</small></div>
          }
        </div>
        <div class="cta"><p-button label="Conhecer os agentes" icon="pi pi-sparkles" routerLink="/agents" /></div>
        <flora-mascot class="corner" name="celebrate" [size]="190" />
      </section>

      <!-- 5 · Bibliotecas (2 slides) -->
      @for (part of stackParts; track part.id) {
        <section class="slide stack" [id]="part.id">
          <header class="head"><p class="kicker">Construído com · {{ part.n }}/2</p><h2>{{ part.title }}</h2>
            <p class="lede">Clique em qualquer uma para abrir a documentação.</p></header>
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
        <header class="head"><p class="kicker">Fontes de dados</p><h2>De onde vêm os datasets</h2>
          <p class="lede">Repositórios públicos mantidos por instituições de pesquisa. Os downloads entram direto no DuckDB.</p></header>
        <div class="insts">@for (i of institutions; track i.name) { <flora-tech-badge [inst]="i" /> }</div>
        <p class="legal">Siglas tipográficas ilustrativas; marcas e logotipos oficiais pertencem às respectivas instituições.</p>
      </section>

      <!-- 7 · CTA -->
      <section class="slide end" id="s-end" [style.--bg]="'url(branding/scenes/camp.webp)'">
        <div class="end-card">
          <img src="branding/logo/badge.webp" alt="" width="96" height="96" />
          <h2>Pronto para explorar?</h2>
          <p class="lede">Comece pelo painel ou pergunte ao copiloto o que investigar primeiro.</p>
          <div class="cta">
            <p-button label="Abrir painel" icon="pi pi-th-large" routerLink="/dashboard" />
            <p-button label="Pipeline Studio" icon="pi pi-sitemap" [outlined]="true" routerLink="/pipeline" />
          </div>
        </div>
        <flora-mascot class="corner big" name="fishing" [size]="260" />
      </section>
    </div>

    <nav class="dots" aria-label="Slides">
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
    { id: 's-stack-1', n: 1, title: 'Interface e dados', groups: TECH_GROUPS.slice(0, 2) },
    { id: 's-stack-2', n: 2, title: 'IA e pipeline de amplicons', groups: TECH_GROUPS.slice(2) }
  ];
  protected readonly institutions = INSTITUTIONS;

  protected readonly slides: Slide[] = [
    { id: 's-hero', label: 'Início' }, { id: 's-flow', label: 'Fluxo' }, { id: 's-modules', label: 'Módulos' },
    { id: 's-ai', label: 'Agentes de IA' }, { id: 's-stack-1', label: 'Bibliotecas: interface e dados' }, { id: 's-stack-2', label: 'Bibliotecas: IA e pipeline' }, { id: 's-data', label: 'Fontes de dados' }, { id: 's-end', label: 'Começar' }
  ];
  protected readonly flow = [
    { i: 'pi pi-upload', t: 'Ingestão', d: 'Metadata, tabela de ASVs e taxonomia reconciliadas, com QC por amostra.' },
    { i: 'pi pi-sliders-h', t: 'Normalização', d: 'Rarefação, TSS ou CLR com os parâmetros registrados.' },
    { i: 'pi pi-chart-scatter', t: 'Exploração', d: 'Alfa, beta, PCoA e taxonomia com filtros sincronizados.' },
    { i: 'pi pi-microchip', t: 'Modelagem', d: 'Random Forest e XGBoost, ROC e SHAP com ressalvas explícitas.' },
    { i: 'pi pi-file', t: 'Relatório', d: 'Seções editáveis, métodos e exportação HTML/PDF.' }
  ];
  protected readonly modules = [
    { to: '/dashboard', i: 'pi pi-th-large', t: 'Painel', d: 'Visão geral do estudo e diagnóstico.' },
    { to: '/explorer', i: 'pi pi-chart-scatter', t: 'Explorer', d: 'PCoA, diversidade, taxonomia, relações.' },
    { to: '/pipeline', i: 'pi pi-sitemap', t: 'Pipeline Studio', d: 'Ingestão guiada e QC.' },
    { to: '/ml', i: 'pi pi-microchip', t: 'AI & ML Lab', d: 'Modelos, SHAP e agrupamentos.' },
    { to: '/reports', i: 'pi pi-file', t: 'Relatório', d: 'Construtor científico exportável.' },
    { to: '/downloads', i: 'pi pi-download', t: 'Downloads', d: 'MGnify, SRA, EMP e sintéticos.' }
  ];
  protected readonly agentCards = [
    { i: 'pi pi-chart-scatter', t: 'Analista de diversidade', d: 'Compara grupos e abre a vista certa.' },
    { i: 'pi pi-shield', t: 'Auditor de qualidade', d: 'Lê o QC e diz se a ingestão pode fechar.' },
    { i: 'pi pi-microchip', t: 'Taxonomista & ML', d: 'Táxons diferenciais e modelos com ressalvas.' },
    { i: 'pi pi-file-edit', t: 'Redator científico', d: 'Checa seções, métodos e lacunas.' }
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
