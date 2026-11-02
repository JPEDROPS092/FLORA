import { Component, computed, effect, ElementRef, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { DialogModule } from 'primeng/dialog';

import { AgentService } from '../core/agents/agent.service';
import { WorkspaceStore } from '../core/workspace/workspace.store';
import { TPipe } from '../core/i18n/t.pipe';
import { t } from '../core/i18n/i18n';

interface Command {
  id: string;
  label: string;
  hint: string;
  icon: string;
  group: string;
  run: () => void;
}

/** Ctrl/Cmd+K launcher: navigate, tune the Explorer, talk to agents. */

@Component({
  selector: 'flora-command-palette',
  standalone: true,
  imports: [TPipe, FormsModule, DialogModule],
  template: `
    <p-dialog
      [visible]="store.paletteOpen()"
      (visibleChange)="store.paletteOpen.set($event)"
      [modal]="true" [dismissableMask]="true" [closable]="false" [draggable]="false"
      [showHeader]="false" [style]="{ width: 'min(620px, 94vw)' }" position="top" styleClass="palette-dialog"
      (onShow)="focusInput()"
    >
      <div class="palette" role="combobox" aria-expanded="true" aria-haspopup="listbox">
        <div class="palette-input">
          <i class="pi pi-search" aria-hidden="true"></i>
          <input #input type="text" [ngModel]="query()" (ngModelChange)="setQuery($event)"
                 (keydown)="onKey($event)" [placeholder]="'Buscar ação, ir para… ou pergunte aos agentes' | t"
                 [attr.aria-label]="'Paleta de comandos' | t" aria-controls="palette-list" />
          <kbd>{{ 'Esc' | t }}</kbd>
        </div>
        <ul id="palette-list" role="listbox" class="palette-list">
          @for (cmd of results(); track cmd.id; let i = $index) {
            <li role="option" [attr.aria-selected]="i === active()" [class.active]="i === active()"
                (mouseenter)="active.set(i)" (click)="exec(cmd)">
              <i [class]="cmd.icon" aria-hidden="true"></i>
              <span class="lbl">{{ cmd.label }}</span>
              <span class="hint">{{ cmd.hint }}</span>
              <span class="grp">{{ cmd.group }}</span>
            </li>
          } @empty {
            <li class="empty">{{ 'Nada encontrado.' | t }}</li>
          }
        </ul>
      </div>
    </p-dialog>
  `
})
export class CommandPaletteComponent {
  protected readonly t = t;
  protected readonly store = inject(WorkspaceStore);
  private readonly router = inject(Router);
  private readonly agents = inject(AgentService);
  private readonly input = viewChild<ElementRef<HTMLInputElement>>('input');

  protected readonly query = signal('');
  protected readonly active = signal(0);

  private readonly commands: Command[] = [
    this.nav(t('Painel'), '/dashboard', 'pi pi-th-large'),
    this.nav(t('Scientific Explorer'), '/explorer', 'pi pi-chart-scatter'),
    this.nav(t('Data Pipeline Studio'), '/pipeline', 'pi pi-sitemap'),
    this.nav(t('AI & ML Lab'), '/ml', 'pi pi-microchip'),
    this.nav(t('Report Builder'), '/reports', 'pi pi-file'),
    this.nav(t('Agentes de IA'), '/agents', 'pi pi-sparkles'),
    this.nav(t('Projetos'), '/projects', 'pi pi-folder'),
    this.nav(t('Downloads'), '/downloads', 'pi pi-download'),
    this.nav(t('Modelos de IA'), '/settings', 'pi pi-cog'),
    this.explore(t('PCoA Bray–Curtis'), { view: 'pcoa', distance: 'braycurtis' }),
    this.explore(t('Diversidade alfa · Shannon'), { view: 'alpha', metric: 'shannon' }),
    this.explore(t('Taxonomia por gênero'), { view: 'taxonomy', rank: 'genus' }),
    this.explore(t('Co-ocorrência entre gêneros'), { view: 'relations' }),
    { id: 'agent-copilot', label: t('Abrir copiloto de IA'), hint: 'Ctrl+J', icon: 'pi pi-sparkles', group: t('Agentes'), run: () => this.store.copilotOpen.set(true) },
    { id: 'theme', label: t('Alternar tema claro/escuro'), hint: '', icon: 'pi pi-moon', group: t('Interface'), run: () => this.store.toggleDark() },
    { id: 'sidebar', label: t('Recolher/expandir menu lateral'), hint: '', icon: 'pi pi-bars', group: t('Interface'), run: () => this.store.toggleSidebar() }
  ];

  protected readonly results = computed<Command[]>(() => {
    const q = this.query().trim().toLowerCase();
    const matched = q ? this.commands.filter((c) => `${c.label} ${c.group}`.toLowerCase().includes(q)) : this.commands;
    if (!q) return matched;
    const ask: Command = {
      id: 'ask', label: `Perguntar aos agentes: “${this.query().trim()}”`, hint: 'roteia ao agente certo',
      icon: 'pi pi-comment', group: t('Agentes'), run: () => { this.store.copilotOpen.set(true); void this.agents.ask(this.query()); }
    };
    return [...matched, ask];
  });

  constructor() {
    effect(() => { if (this.store.paletteOpen()) { this.query.set(''); this.active.set(0); } });
  }

  focusInput(): void { setTimeout(() => this.input()?.nativeElement.focus()); }
  setQuery(v: string): void { this.query.set(v); this.active.set(0); }

  onKey(e: KeyboardEvent): void {
    const n = this.results().length;
    if (e.key === 'ArrowDown') { e.preventDefault(); this.active.update((i) => (i + 1) % Math.max(n, 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); this.active.update((i) => (i - 1 + n) % Math.max(n, 1)); }
    else if (e.key === 'Enter') { e.preventDefault(); const c = this.results()[this.active()]; if (c) this.exec(c); }
  }

  exec(cmd: Command): void {
    this.store.paletteOpen.set(false);
    cmd.run();
  }

  private nav(label: string, path: string, icon: string): Command {
    return { id: `nav-${path}`, label, hint: path, icon, group: t('Ir para'), run: () => void this.router.navigate([path]) };
  }
  private explore(label: string, queryParams: Record<string, string>): Command {
    return { id: `ex-${label}`, label, hint: '/explorer', icon: 'pi pi-chart-line', group: t('Explorer'), run: () => void this.router.navigate(['/explorer'], { queryParams }) };
  }
}
