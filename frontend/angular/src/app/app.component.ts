import { CommonModule } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { ApiService } from './core/api.service';
import { ApiStatus } from './core/models';

@Component({
  selector: 'flora-root',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterLinkActive, RouterOutlet],
  template: `
    <div class="shell">
      <aside class="sidebar">
        <div class="brand card">
          <p class="eyebrow">FLORA Platform</p>
          <h1>FLORA UI</h1>
          <p>Angular SPA integrada ao backend Python mantendo o fluxo do comando flora ui.</p>
          <div class="status-pill">
            <span class="status-dot" [class.live]="isLive()" [class.off]="!isLive()"></span>
            <span>{{ statusText() }}</span>
          </div>
        </div>

        <nav class="nav">
          <a routerLink="/overview" routerLinkActive="active">Overview</a>
          <a routerLink="/workspace" routerLinkActive="active">Workspace</a>
          <a routerLink="/downloads" routerLinkActive="active">Downloads</a>
          <a routerLink="/visuals" routerLinkActive="active">Visualization Studio</a>
          <a routerLink="/reporting" routerLinkActive="active">Relatorio e ML</a>
        </nav>

        <div class="sidebar-footer">
          <strong>Frontend mode:</strong> {{ frontendMode() }}<br>
          <strong>Workdir:</strong> {{ status()?.workdir ?? 'n/a' }}
        </div>
      </aside>

      <main class="content">
        <router-outlet></router-outlet>
      </main>
    </div>
  `,
  styles: [`
    .shell { display: grid; grid-template-columns: 280px minmax(0, 1fr); min-height: 100vh; }
    .sidebar {
      position: sticky;
      top: 0;
      height: 100vh;
      padding: 28px 22px;
      background: var(--panel-dark);
      color: #f8f4ec;
      border-right: 1px solid rgba(255, 255, 255, 0.08);
      backdrop-filter: blur(18px);
    }
    .brand {
      padding: 18px 18px 22px;
      background: linear-gradient(145deg, rgba(15, 118, 110, 0.36), rgba(40, 89, 67, 0.2));
      border-color: rgba(255, 255, 255, 0.08);
      margin-bottom: 22px;
    }
    .eyebrow {
      text-transform: uppercase;
      letter-spacing: 0.18em;
      color: #ffd89d;
      font-size: 0.74rem;
      font-weight: 700;
      margin: 0 0 10px;
    }
    h1 {
      margin: 0;
      font-family: "Gill Sans", "Trebuchet MS", sans-serif;
      letter-spacing: -0.04em;
      font-size: 2rem;
    }
    .brand p:last-of-type {
      margin: 10px 0 0;
      color: rgba(248, 244, 236, 0.78);
      line-height: 1.55;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      margin-top: 16px;
      background: rgba(255, 255, 255, 0.08);
      font-size: 0.9rem;
    }
    .status-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: #9ca3af;
      box-shadow: 0 0 0 5px rgba(156, 163, 175, 0.12);
    }
    .status-dot.live {
      background: #4ade80;
      box-shadow: 0 0 0 5px rgba(74, 222, 128, 0.16);
    }
    .status-dot.off {
      background: #fb7185;
      box-shadow: 0 0 0 5px rgba(251, 113, 133, 0.16);
    }
    .nav { display: grid; gap: 8px; margin-top: 18px; }
    .nav a {
      color: rgba(248, 244, 236, 0.82);
      text-decoration: none;
      padding: 12px 14px;
      border-radius: 14px;
      transition: 160ms ease;
      border: 1px solid transparent;
    }
    .nav a:hover,
    .nav a.active {
      color: #fff;
      background: rgba(255, 255, 255, 0.08);
      border-color: rgba(255, 255, 255, 0.08);
      transform: translateX(2px);
    }
    .sidebar-footer {
      position: absolute;
      left: 22px;
      right: 22px;
      bottom: 24px;
      padding: 14px 16px;
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.06);
      font-size: 0.88rem;
      color: rgba(248, 244, 236, 0.72);
      line-height: 1.6;
    }
    .content { padding: 28px; }
    @media (max-width: 980px) {
      .shell { grid-template-columns: 1fr; }
      .sidebar { position: static; height: auto; }
      .sidebar-footer { position: static; margin-top: 16px; }
    }
  `]
})
export class AppComponent {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);

  readonly status = signal<ApiStatus | null>(null);
  readonly statusText = signal('Verificando pipeline...');
  readonly frontendMode = signal('unknown');
  readonly isLive = signal(false);

  constructor() {
    void this.refreshStatus();
    const timer = window.setInterval(() => void this.refreshStatus(), 15000);
    this.destroyRef.onDestroy(() => window.clearInterval(timer));
  }

  private async refreshStatus(): Promise<void> {
    const response = await this.api.status().catch(() => null);
    this.status.set(response);
    this.isLive.set(Boolean(response?.success));
    this.frontendMode.set(response?.frontend?.mode ?? 'unknown');
    this.statusText.set(
      response?.success
        ? `Backend ${response.status} · ${response.frontend?.mode ?? 'ui'}`
        : 'Backend indisponivel'
    );
  }
}
