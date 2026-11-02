import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { ToastModule } from 'primeng/toast';

import { FloraRepository } from './core/data/flora.repository';

@Component({
  selector: 'flora-root',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, RouterOutlet, ToastModule],
  template: `
    <div class="shell">
      <aside class="sidebar">
        <div class="brand">
          <span class="mark">FL</span>
          <div>
            <strong>FLORA</strong>
            <span>Microbiome Research</span>
          </div>
        </div>

        <nav class="nav">
          @for (item of primary; track item.path) {
            <a [routerLink]="item.path" routerLinkActive="active" [routerLinkActiveOptions]="{ exact: true }">
              <i [class]="item.icon"></i>
              <span>{{ item.label }}</span>
            </a>
          }
        </nav>

        <p class="nav-label">Biblioteca</p>
        <nav class="secondary">
          <a routerLink="/projects" routerLinkActive="active">Projetos</a>
          <a routerLink="/downloads" routerLinkActive="active">Downloads</a>
        </nav>

        <div class="source">
          <span class="source-kicker">Fonte de dados</span>
          <strong>{{ source.mocked ? 'Mock 16S' : 'API HTTP' }}</strong>
          <span>{{ source.label }}</span>
        </div>
      </aside>

      <div class="workspace" [class.lab-canvas]="lab()">
        <router-outlet />
      </div>
    </div>
    <p-toast />
  `
})
export class AppComponent {
  private readonly repository = inject(FloraRepository);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly source = this.repository.source;
  readonly lab = signal(this.router.url.startsWith('/ml'));
  readonly primary = [
    { path: '/dashboard', label: 'Painel', icon: 'pi pi-th-large' },
    { path: '/explorer', label: 'Explorer', icon: 'pi pi-chart-scatter' },
    { path: '/pipeline', label: 'Pipeline', icon: 'pi pi-sitemap' },
    { path: '/ml', label: 'ML Lab', icon: 'pi pi-microchip' },
    { path: '/reports', label: 'Relatório', icon: 'pi pi-file' }
  ];

  constructor() {
    this.router.events
      .pipe(
        filter((event): event is NavigationEnd => event instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe((event) => this.lab.set(event.urlAfterRedirects.startsWith('/ml')));
  }
}
