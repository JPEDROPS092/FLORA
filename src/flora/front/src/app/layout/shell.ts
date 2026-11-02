import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { ButtonModule } from 'primeng/button';
import { TooltipModule } from 'primeng/tooltip';
import { BehaviorSubject, Observable, catchError, interval, map, of, switchMap } from 'rxjs';

import { FloraApiService, FloraStatus } from '../core/api/flora-api.service';

export type ConnectionState =
  | { kind: 'checking' }
  | { kind: 'connected'; status: FloraStatus }
  | { kind: 'disconnected' };

interface NavItem {
  readonly label: string;
  readonly route?: string;
  readonly icon: string;
  readonly ready: boolean;
  readonly issue: string;
}

const NAV_ITEMS: readonly NavItem[] = [
  { label: 'Dashboard', route: '/dashboard', icon: 'pi pi-home', ready: true, issue: '#4' },
  { label: 'Acquisition', icon: 'pi pi-download', ready: false, issue: '#8' },
  { label: 'Ingestion', icon: 'pi pi-upload', ready: false, issue: '#8' },
  { label: 'Explorer', icon: 'pi pi-database', ready: false, issue: '#9' },
  { label: 'Features', icon: 'pi pi-sliders-h', ready: false, issue: '#10' },
  { label: 'Diversity', icon: 'pi pi-chart-bar', ready: false, issue: '#10' },
  { label: 'Machine Learning', icon: 'pi pi-bolt', ready: false, issue: '#12' },
  { label: 'Pipeline', icon: 'pi pi-sitemap', ready: false, issue: '#13' },
  { label: 'Reports', icon: 'pi pi-file', ready: false, issue: '#14' },
];

@Component({
  selector: 'flora-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, ButtonModule, TooltipModule],
  templateUrl: './shell.html',
  styleUrl: './shell.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Shell implements OnInit {
  private readonly api = inject(FloraApiService);
  private readonly refresh$ = new BehaviorSubject<void>(undefined);

  protected readonly navItems = NAV_ITEMS;
  protected readonly sidebarOpen = signal(true);
  protected readonly dark = signal(true);

  protected readonly connection = toSignal(
    this.refresh$.pipe(
      switchMap((): Observable<ConnectionState> =>
        this.api.getStatus().pipe(
          map((status): ConnectionState => ({ kind: 'connected', status })),
          catchError((): Observable<ConnectionState> => of({ kind: 'disconnected' })),
        ),
      ),
    ),
    { initialValue: { kind: 'checking' } as ConnectionState },
  );

  constructor() {
    interval(15_000)
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.refresh$.next());
  }

  ngOnInit(): void {
    this.applyTheme(this.dark());
    this.matchViewport();
  }

  refreshStatus(): void {
    this.refresh$.next();
  }

  toggleSidebar(): void {
    this.sidebarOpen.update((v) => !v);
  }

  toggleDark(): void {
    this.dark.update((v) => {
      this.applyTheme(!v);
      return !v;
    });
  }

  private applyTheme(dark: boolean): void {
    document.documentElement.classList.toggle('app-dark', dark);
  }

  private matchViewport(): void {
    if (typeof window.matchMedia === 'function') {
      this.sidebarOpen.set(window.matchMedia('(min-width: 768px)').matches);
    }
  }
}
