import { Component, DestroyRef, HostListener, OnInit, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { ToastModule } from 'primeng/toast';
import { TooltipModule } from 'primeng/tooltip';
import { filter, interval, map, startWith } from 'rxjs';

import { AgentService } from './core/agents/agent.service';
import { FloraRepository } from './core/data/flora.repository';
import { WorkspaceInfo } from './core/models/domain';
import { WorkspaceStore } from './core/workspace/workspace.store';
import { LanguageSwitchComponent } from './core/i18n/language-switch.component';
import { CommandPaletteComponent } from './shared/command-palette.component';
import { CopilotComponent } from './shared/copilot.component';
import { DocsDialogComponent } from './shared/docs-dialog.component';
import { TPipe } from './core/i18n/t.pipe';
import { LOCALE, t } from './core/i18n/i18n';

type Connection = 'mock' | 'checking' | 'online' | 'offline';

@Component({
  selector: 'flora-root',
  standalone: true,
  imports: [TPipe, LanguageSwitchComponent, RouterLink, RouterLinkActive, RouterOutlet, ToastModule, ButtonModule, TooltipModule, CommandPaletteComponent, CopilotComponent, DocsDialogComponent],
  template: `
    <a class="skip-link" href="#flora-content">{{ 'Pular para o conteúdo' | t }}</a>
    <div class="shell" [class.collapsed]="!store.sidebarOpen()">
      <aside class="sidebar" [attr.aria-label]="'Navegação principal' | t">
        <div class="brand">
          <img class="mark-img" src="branding/logo/badge.webp" alt="" width="34" height="34" />
          <div class="brand-text"><strong>{{ 'FLORA' | t }}</strong><span>{{ 'Microbiome Research' | t }}</span></div>
        </div>

        <nav class="nav" [attr.aria-label]="'Módulos' | t">
          @for (item of primary; track item.path) {
            <a [routerLink]="item.path" routerLinkActive="active" [routerLinkActiveOptions]="{ exact: true }"
               [pTooltip]="store.sidebarOpen() ? '' : item.label" tooltipPosition="right">
              <i [class]="item.icon" aria-hidden="true"></i><span>{{ item.label }}</span>
              @if (item.path === '/agents' && agents.pendingActions()) { <em class="badge">{{ agents.pendingActions() }}</em> }
            </a>
          }
        </nav>

        <p class="nav-label">{{ 'Biblioteca' | t }}</p>
        <nav class="nav secondary" [attr.aria-label]="'Biblioteca' | t">
          @for (item of library; track item.path) {
            <a [routerLink]="item.path" routerLinkActive="active" [pTooltip]="store.sidebarOpen() ? '' : item.label" tooltipPosition="right">
              <i [class]="item.icon" aria-hidden="true"></i><span>{{ item.label }}</span>
            </a>
          }
        </nav>

        <div class="source" [class]="'conn-' + connection()">
          <div class="source-head">
            <span class="source-kicker">{{ 'Fonte de dados' | t }}</span>
            <time class="source-clock" [attr.datetime]="now().toISOString()">{{ clock() }}</time>
          </div>
          <strong class="source-status"><span class="dot" aria-hidden="true"></span>{{ connectionLabel() }}</strong>
          <span class="source-label">{{ source.label }}</span>
          <span class="source-date">{{ dateLabel() }}</span>
          <button type="button" class="docs-btn" (click)="store.openDocs()" [pTooltip]="store.sidebarOpen() ? '' : t('Documentação')" tooltipPosition="right"
                  [attr.aria-label]="'Abrir a documentação' | t">
            <i class="pi pi-book" aria-hidden="true"></i><span>{{ 'Documentação' | t }}</span>
          </button>
        </div>
      </aside>

      <div class="workspace-col">
        <header class="topbar">
          <p-button icon="pi pi-bars" [text]="true" [rounded]="true" severity="secondary" (onClick)="store.toggleSidebar()"
                    [ariaLabel]="'Alternar menu lateral' | t" />
          <nav class="crumbs" [attr.aria-label]="'Localização' | t"><span>{{ 'FLORA' | t }}</span><i class="pi pi-angle-right"></i><strong>{{ title() }}</strong></nav>
          @if (workspace(); as ws) {
            <span class="ws-chip" [class.volatile]="!ws.persistent" [attr.title]="ws.dbPath">
              <i class="pi pi-folder-open" aria-hidden="true"></i>
              <b>{{ ws.project?.name || t('Sem projeto ativo') }}</b>
              <i class="pi pi-database" aria-hidden="true"></i>
              <span>{{ dbLabel(ws) }}</span>
            </span>
          }
          <button type="button" class="search-btn" (click)="store.openPalette()" [attr.aria-label]="'Abrir paleta de comandos' | t">
            <i class="pi pi-search"></i><span>{{ 'Buscar ou executar…' | t }}</span><kbd>{{ 'Ctrl K' | t }}</kbd>
          </button>
          <flora-language-switch />
          <p-button icon="pi pi-sparkles" [label]="'Copiloto' | t" size="small" [outlined]="!store.copilotOpen()"
                    (onClick)="store.toggleCopilot()" [pTooltip]="'Ctrl+J' | t" tooltipPosition="bottom" />
          <p-button [icon]="store.dark() ? 'pi pi-sun' : 'pi pi-moon'" [text]="true" [rounded]="true" severity="secondary"
                    (onClick)="store.toggleDark()" [ariaLabel]="store.dark() ? t('Tema claro') : t('Tema escuro')" />
        </header>

        <main class="workspace" id="flora-content" [class.lab-canvas]="lab()" tabindex="-1">
          <router-outlet />
        </main>
      </div>
    </div>
    <flora-copilot />
    <flora-command-palette />
    <flora-docs-dialog />
    <p-toast />
  `
})
export class AppComponent implements OnInit {
  protected readonly t = t;
  protected readonly store = inject(WorkspaceStore);
  protected readonly agents = inject(AgentService);
  private readonly repository = inject(FloraRepository);
  private readonly router = inject(Router);
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);

  readonly source = this.repository.source;
  readonly now = signal(new Date());
  readonly clock = computed(() => this.now().toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
  readonly dateLabel = computed(() => this.now().toLocaleDateString(LOCALE, { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' }));
  readonly lab = signal(this.router.url.startsWith('/ml'));
  readonly title = signal(t('Início'));
  readonly health = signal<'checking' | 'online' | 'offline'>('checking');
  readonly workspace = signal<WorkspaceInfo | null>(null);
  readonly connection = computed<Connection>(() => (this.source.mocked ? 'mock' : this.health()));
  readonly connectionLabel = computed(() => ({ mock: t('Mock 16S'), checking: t('Conectando…'), online: t('API conectada'), offline: t('API offline') })[this.connection()]);

  readonly primary = [
    { path: '/welcome', label: t('Início'), icon: 'pi pi-home' },
    { path: '/dashboard', label: t('Painel'), icon: 'pi pi-th-large' },
    { path: '/explorer', label: t('Explorer'), icon: 'pi pi-chart-scatter' },
    { path: '/pipeline', label: t('Pipeline'), icon: 'pi pi-sitemap' },
    { path: '/ml', label: t('ML Lab'), icon: 'pi pi-microchip' },
    { path: '/reports', label: t('Relatório'), icon: 'pi pi-file' },
    { path: '/agents', label: t('Agentes IA'), icon: 'pi pi-sparkles' }
  ];
  readonly library = [
    { path: '/projects', label: t('Projetos'), icon: 'pi pi-folder' },
    { path: '/downloads', label: t('Downloads'), icon: 'pi pi-download' },
    { path: '/engines', label: t('Motores de análise'), icon: 'pi pi-wrench' },
    { path: '/settings', label: t('Modelos de IA'), icon: 'pi pi-cog' }
  ];

  constructor() {
    this.router.events
      .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd), takeUntilDestroyed(this.destroyRef))
      .subscribe((e) => {
        this.lab.set(e.urlAfterRedirects.startsWith('/ml'));
        const path = '/' + e.urlAfterRedirects.split(/[/?#]/)[1];
        this.title.set([...this.primary, ...this.library].find((i) => i.path === path)?.label ?? 'FLORA');
        void this.refreshWorkspace();
      });
  }

  /** `:memory:` databases vanish on restart, so the header says so instead of showing a path. */
  dbLabel(ws: WorkspaceInfo): string {
    return ws.persistent ? ws.dbPath.split('/').pop() || ws.dbPath : t('em memória (não salvo)');
  }

  private async refreshWorkspace(): Promise<void> {
    try {
      this.workspace.set(await this.repository.workspaceInfo());
    } catch {
      this.workspace.set(null);
    }
  }

  ngOnInit(): void {
    interval(1000).pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.now.set(new Date()));
    if (this.source.mocked) return;
    interval(15_000).pipe(startWith(0), takeUntilDestroyed(this.destroyRef)).subscribe(() =>
      this.http.get(`${this.source.apiBaseUrl}/api/status`).subscribe({
        next: () => this.health.set('online'),
        error: () => this.health.set('offline')
      })
    );
  }

  @HostListener('document:keydown', ['$event'])
  onKey(e: KeyboardEvent): void {
    if (!(e.ctrlKey || e.metaKey)) return;
    if (e.key.toLowerCase() === 'k') { e.preventDefault(); this.store.paletteOpen.update((v) => !v); }
    else if (e.key.toLowerCase() === 'j') { e.preventDefault(); this.store.toggleCopilot(); }
  }
}
