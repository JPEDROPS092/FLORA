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
import { WorkspaceStore } from './core/workspace/workspace.store';
import { CommandPaletteComponent } from './shared/command-palette.component';
import { CopilotComponent } from './shared/copilot.component';

type Connection = 'mock' | 'checking' | 'online' | 'offline';

@Component({
  selector: 'flora-root',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, RouterOutlet, ToastModule, ButtonModule, TooltipModule, CommandPaletteComponent, CopilotComponent],
  template: `
    <a class="skip-link" href="#flora-content">Pular para o conteúdo</a>
    <div class="shell" [class.collapsed]="!store.sidebarOpen()">
      <aside class="sidebar" aria-label="Navegação principal">
        <div class="brand">
          <span class="mark" aria-hidden="true">FL</span>
          <div class="brand-text"><strong>FLORA</strong><span>Microbiome Research</span></div>
        </div>

        <nav class="nav" aria-label="Módulos">
          @for (item of primary; track item.path) {
            <a [routerLink]="item.path" routerLinkActive="active" [routerLinkActiveOptions]="{ exact: true }"
               [pTooltip]="store.sidebarOpen() ? '' : item.label" tooltipPosition="right">
              <i [class]="item.icon" aria-hidden="true"></i><span>{{ item.label }}</span>
              @if (item.path === '/agents' && agents.pendingActions()) { <em class="badge">{{ agents.pendingActions() }}</em> }
            </a>
          }
        </nav>

        <p class="nav-label">Biblioteca</p>
        <nav class="nav secondary" aria-label="Biblioteca">
          @for (item of library; track item.path) {
            <a [routerLink]="item.path" routerLinkActive="active" [pTooltip]="store.sidebarOpen() ? '' : item.label" tooltipPosition="right">
              <i [class]="item.icon" aria-hidden="true"></i><span>{{ item.label }}</span>
            </a>
          }
        </nav>

        <div class="source" [class]="'conn-' + connection()">
          <span class="source-kicker">Fonte de dados</span>
          <strong><span class="dot" aria-hidden="true"></span>{{ connectionLabel() }}</strong>
          <span>{{ source.label }}</span>
        </div>
      </aside>

      <div class="workspace-col">
        <header class="topbar">
          <p-button icon="pi pi-bars" [text]="true" [rounded]="true" severity="secondary" (onClick)="store.toggleSidebar()"
                    ariaLabel="Alternar menu lateral" />
          <nav class="crumbs" aria-label="Localização"><span>FLORA</span><i class="pi pi-angle-right"></i><strong>{{ title() }}</strong></nav>
          <button type="button" class="search-btn" (click)="store.openPalette()" aria-label="Abrir paleta de comandos">
            <i class="pi pi-search"></i><span>Buscar ou executar…</span><kbd>Ctrl K</kbd>
          </button>
          <p-button icon="pi pi-sparkles" label="Copiloto" size="small" [outlined]="!store.copilotOpen()"
                    (onClick)="store.toggleCopilot()" pTooltip="Ctrl+J" tooltipPosition="bottom" />
          <p-button [icon]="store.dark() ? 'pi pi-sun' : 'pi pi-moon'" [text]="true" [rounded]="true" severity="secondary"
                    (onClick)="store.toggleDark()" [ariaLabel]="store.dark() ? 'Tema claro' : 'Tema escuro'" />
        </header>

        <main class="workspace" id="flora-content" [class.lab-canvas]="lab()" tabindex="-1">
          <router-outlet />
        </main>
      </div>
    </div>
    <flora-copilot />
    <flora-command-palette />
    <p-toast />
  `
})
export class AppComponent implements OnInit {
  protected readonly store = inject(WorkspaceStore);
  protected readonly agents = inject(AgentService);
  private readonly repository = inject(FloraRepository);
  private readonly router = inject(Router);
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);

  readonly source = this.repository.source;
  readonly lab = signal(this.router.url.startsWith('/ml'));
  readonly title = signal('Painel');
  readonly health = signal<'checking' | 'online' | 'offline'>('checking');
  readonly connection = computed<Connection>(() => (this.source.mocked ? 'mock' : this.health()));
  readonly connectionLabel = computed(() => ({ mock: 'Mock 16S', checking: 'Conectando…', online: 'API conectada', offline: 'API offline' })[this.connection()]);

  readonly primary = [
    { path: '/dashboard', label: 'Painel', icon: 'pi pi-th-large' },
    { path: '/explorer', label: 'Explorer', icon: 'pi pi-chart-scatter' },
    { path: '/pipeline', label: 'Pipeline', icon: 'pi pi-sitemap' },
    { path: '/ml', label: 'ML Lab', icon: 'pi pi-microchip' },
    { path: '/reports', label: 'Relatório', icon: 'pi pi-file' },
    { path: '/agents', label: 'Agentes IA', icon: 'pi pi-sparkles' }
  ];
  readonly library = [
    { path: '/projects', label: 'Projetos', icon: 'pi pi-folder' },
    { path: '/downloads', label: 'Downloads', icon: 'pi pi-download' }
  ];

  constructor() {
    this.router.events
      .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd), takeUntilDestroyed(this.destroyRef))
      .subscribe((e) => {
        this.lab.set(e.urlAfterRedirects.startsWith('/ml'));
        const path = '/' + e.urlAfterRedirects.split(/[/?#]/)[1];
        this.title.set([...this.primary, ...this.library].find((i) => i.path === path)?.label ?? 'FLORA');
      });
  }

  ngOnInit(): void {
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
