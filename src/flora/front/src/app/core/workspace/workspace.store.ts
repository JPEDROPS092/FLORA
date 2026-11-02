import { Injectable, effect, signal } from '@angular/core';

const THEME_KEY = 'flora.theme';
const SIDEBAR_KEY = 'flora.sidebar';

/** UI-wide state shared by the shell, command palette and AI copilot. */
@Injectable({ providedIn: 'root' })
export class WorkspaceStore {
  readonly dark = signal(this.read(THEME_KEY) === 'dark');
  readonly sidebarOpen = signal(this.read(SIDEBAR_KEY) !== 'closed');
  readonly copilotOpen = signal(false);
  readonly paletteOpen = signal(false);

  constructor() {
    effect(() => {
      const dark = this.dark();
      document.documentElement.classList.toggle('flora-dark', dark);
      this.write(THEME_KEY, dark ? 'dark' : 'light');
    });
    effect(() => this.write(SIDEBAR_KEY, this.sidebarOpen() ? 'open' : 'closed'));
  }

  toggleDark(): void { this.dark.update((v) => !v); }
  toggleSidebar(): void { this.sidebarOpen.update((v) => !v); }
  toggleCopilot(): void { this.copilotOpen.update((v) => !v); }
  openPalette(): void { this.paletteOpen.set(true); }

  private read(key: string): string | null {
    try { return localStorage.getItem(key); } catch { return null; }
  }
  private write(key: string, value: string): void {
    try { localStorage.setItem(key, value); } catch { /* storage unavailable */ }
  }
}
