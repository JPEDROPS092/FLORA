import { Injectable, effect, signal } from '@angular/core';

const THEME_KEY = 'flora.theme';
const SIDEBAR_KEY = 'flora.sidebar';

/** UI-wide state shared by the shell, command palette and AI copilot. */
@Injectable({ providedIn: 'root' })
export class WorkspaceStore {
  readonly dark = signal(this.read(THEME_KEY) === 'dark');
  /** Narrow screens use an off-canvas drawer instead of the always-visible rail. */
  readonly mobile = signal(this.matches('(max-width: 900px)'));
  /** Desktop: expanded or the icon rail. Without a saved choice, medium screens start compact. */
  readonly sidebarOpen = signal(this.read(SIDEBAR_KEY) ? this.read(SIDEBAR_KEY) !== 'closed' : !this.matches('(max-width: 1180px)'));
  readonly mobileNavOpen = signal(false);
  readonly copilotOpen = signal(false);
  readonly paletteOpen = signal(false);
  readonly docsOpen = signal(false);
  /** Bumped when an action changed the project's data (ingest, QC…), so the header and cards can refresh. */
  readonly dataVersion = signal(0);
  readonly docsTopic = signal('overview');

  constructor() {
    if (typeof window !== 'undefined' && window.matchMedia) {
      const query = window.matchMedia('(max-width: 900px)');
      const sync = () => { this.mobile.set(query.matches); if (!query.matches) this.mobileNavOpen.set(false); };
      query.addEventListener('change', sync);
    }
    effect(() => {
      const dark = this.dark();
      document.documentElement.classList.toggle('flora-dark', dark);
      this.write(THEME_KEY, dark ? 'dark' : 'light');
    });
    effect(() => this.write(SIDEBAR_KEY, this.sidebarOpen() ? 'open' : 'closed'));
  }

  bumpData(): void { this.dataVersion.update((v) => v + 1); }
  toggleDark(): void { this.dark.update((v) => !v); }
  /** The topbar and sidebar buttons both call this: a drawer on phones, expand/collapse elsewhere. */
  toggleSidebar(): void { if (this.mobile()) this.mobileNavOpen.update((v) => !v); else this.sidebarOpen.update((v) => !v); }
  closeMobileNav(): void { this.mobileNavOpen.set(false); }
  toggleCopilot(): void { this.copilotOpen.update((v) => !v); }
  openPalette(): void { this.paletteOpen.set(true); }
  openDocs(topic = 'overview'): void { this.docsTopic.set(topic); this.docsOpen.set(true); }

  private matches(query: string): boolean {
    return typeof window !== 'undefined' && !!window.matchMedia && window.matchMedia(query).matches;
  }
  private read(key: string): string | null {
    try { return localStorage.getItem(key); } catch { return null; }
  }
  private write(key: string, value: string): void {
    try { localStorage.setItem(key, value); } catch { /* storage unavailable */ }
  }
}
