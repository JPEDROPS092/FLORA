import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, effect, inject, signal } from '@angular/core';
import { DomSanitizer } from '@angular/platform-browser';
import { DialogModule } from 'primeng/dialog';
import { firstValueFrom } from 'rxjs';

import { LANG, t } from '../core/i18n/i18n';
import { TPipe } from '../core/i18n/t.pipe';
import { WorkspaceStore } from '../core/workspace/workspace.store';
import { renderMarkdown } from './markdown';

/** In-app documentation: Markdown files under `public/docs/<lang>/<topic>.md`. */
@Component({
  selector: 'flora-docs-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DialogModule, TPipe],
  template: `
    <p-dialog [header]="'Documentação' | t" [visible]="store.docsOpen()" (visibleChange)="store.docsOpen.set($event)"
              [modal]="true" [dismissableMask]="true" [draggable]="false" [style]="{ width: 'min(900px, 94vw)' }" [contentStyle]="{ padding: 0 }">
      <div class="docs">
        <nav class="docs-nav" [attr.aria-label]="'Tópicos' | t">
          @for (topic of topics; track topic.id) {
            <button type="button" [class.active]="store.docsTopic() === topic.id" (click)="store.docsTopic.set(topic.id)">
              <i [class]="topic.icon" aria-hidden="true"></i>{{ topic.label }}
            </button>
          }
        </nav>
        <article class="docs-body" tabindex="0" [attr.aria-busy]="loading()">
          @if (loading()) { <p class="muted">{{ 'Carregando…' | t }}</p> }
          @else if (error()) { <p class="muted">{{ 'Não foi possível carregar este documento.' | t }}</p> }
          @else { <div class="md" [innerHTML]="html()"></div> }
        </article>
      </div>
    </p-dialog>
  `,
  styles: [`
    .docs { display: grid; grid-template-columns: 200px minmax(0, 1fr); min-height: 420px; max-height: 70vh; }
    .docs-nav { display: grid; align-content: start; gap: 2px; padding: 10px; border-right: 1px solid var(--flora-border); background: var(--flora-surface-2, transparent); }
    .docs-nav button { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border: 0; border-radius: 8px; background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; }
    .docs-nav button:hover { background: var(--flora-primary-soft); }
    .docs-nav button.active { background: var(--flora-primary-soft); color: var(--flora-primary); font-weight: 600; }
    .docs-body { padding: 18px 24px; overflow: auto; outline: none; }
    .muted { color: var(--flora-muted); }
    .md :is(h1, h2) { margin: 0 0 8px; }
    .md h2 { margin-top: 20px; font-size: 1.05rem; }
    .md p, .md li { line-height: 1.6; }
    .md code { padding: 1px 5px; border-radius: 5px; background: var(--flora-primary-soft); font-size: .85em; }
    .md blockquote { margin: 12px 0; padding: 8px 14px; border-left: 3px solid var(--flora-primary); background: var(--flora-primary-soft); border-radius: 0 8px 8px 0; }
    .md table { border-collapse: collapse; margin: 10px 0; }
    .md th, .md td { padding: 6px 12px; border: 1px solid var(--flora-border); text-align: left; }
    .md a { color: var(--flora-primary); }
    @media (max-width: 700px) { .docs { grid-template-columns: 1fr; } .docs-nav { grid-auto-flow: column; overflow-x: auto; border-right: 0; border-bottom: 1px solid var(--flora-border); } }
  `]
})
export class DocsDialogComponent {
  protected readonly store = inject(WorkspaceStore);
  private readonly http = inject(HttpClient);
  private readonly sanitizer = inject(DomSanitizer);
  private readonly cache = new Map<string, string>();

  protected readonly topics = [
    { id: 'overview', icon: 'pi pi-compass', label: t('Visão geral') },
    { id: 'ingestion', icon: 'pi pi-upload', label: t('Ingestão') },
    { id: 'normalization', icon: 'pi pi-sliders-h', label: t('Normalização') },
    { id: 'exploration', icon: 'pi pi-chart-scatter', label: t('Exploração') },
    { id: 'modelling', icon: 'pi pi-microchip', label: t('Modelagem') },
    { id: 'report', icon: 'pi pi-file', label: t('Relatório') }
  ];
  protected readonly loading = signal(false);
  protected readonly error = signal(false);
  private readonly source = signal('');
  protected readonly html = computed(() => this.sanitizer.sanitize(1, renderMarkdown(this.source())) ?? '');

  constructor() {
    effect(() => {
      if (!this.store.docsOpen()) return;
      void this.load(this.store.docsTopic());
    });
  }

  private async load(topic: string): Promise<void> {
    const cached = this.cache.get(topic);
    if (cached !== undefined) { this.source.set(cached); this.error.set(false); return; }
    this.loading.set(true);
    this.error.set(false);
    try {
      const text = await firstValueFrom(this.http.get(`docs/${LANG}/${topic}.md`, { responseType: 'text' }));
      this.cache.set(topic, text);
      if (this.store.docsTopic() === topic) this.source.set(text);
    } catch {
      this.error.set(true);
    } finally {
      this.loading.set(false);
    }
  }
}
