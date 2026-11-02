import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TagModule } from 'primeng/tag';
import { TextareaModule } from 'primeng/textarea';

import { FloraRepository } from '../../core/data/flora.repository';
import { ReportDraft, ReportSection } from '../../core/models/domain';
import { decodeBase64, downloadBlob } from '../../shared/download';
import { PlotCardComponent } from '../../shared/plot-card.component';

@Component({
  selector: 'flora-report-builder',
  standalone: true,
  imports: [ReactiveFormsModule, ButtonModule, InputTextModule, SelectModule, TagModule, TextareaModule, PlotCardComponent],
  template: `
    <section class="page">
      <header class="page-heading">
        <div>
          <p class="kicker">Scientific Report Builder</p>
          <h1>Relatório com métodos e figuras</h1>
          <p class="lede">Edite o texto, mantenha os parâmetros e exporte HTML interativo ou PDF textual.</p>
        </div>
        @if (draft()?.mocked) { <p-tag value="Dados mockados" severity="secondary" /> }
      </header>

      <div class="builder">
        <nav class="surface section-list">
          @for (section of sections(); track section.id) {
            <button type="button" [class.active]="current()?.id === section.id" (click)="choose(section)">
              {{ section.included ? '' : '○ ' }}{{ section.title }}
            </button>
          }
        </nav>

        <article class="surface stack">
          @if (current(); as section) {
            <div class="section-title">
              <h2>{{ section.title }}</h2>
              <p-button
                type="button"
                [label]="section.included ? 'Incluída' : 'Omitida'"
                [severity]="section.included ? 'primary' : 'secondary'"
                (onClick)="toggle(section.id)"
              />
            </div>
            <form class="field" [formGroup]="editor">
              <label for="narrative">Texto</label>
              <textarea id="narrative" pTextarea rows="8" formControlName="narrative"></textarea>
            </form>
            @if (section.figure && figure(section.figure); as chart) {
              <flora-plot [result]="{ status: 'ok', figure: chart }" [height]="340" />
            }
            @if (section.table; as table) {
              <table class="comparison">
                <thead>
                  <tr>@for (column of table.columns; track column) { <th>{{ column }}</th> }</tr>
                </thead>
                <tbody>
                  @for (row of table.rows; track $index) {
                    <tr>@for (cell of row; track $index) { <td>{{ cell }}</td> }</tr>
                  }
                </tbody>
              </table>
            }
          }
        </article>

        <aside class="surface stack">
          <form class="filters" [formGroup]="meta" (ngSubmit)="exportReport('both')">
            <div class="field">
              <label for="title">Título</label>
              <input id="title" pInputText formControlName="title" />
              @if (meta.controls.title.invalid && meta.controls.title.touched) {
                <small class="field-error">O título é obrigatório.</small>
              }
            </div>
            <div class="field">
              <label for="groupBy">Agrupar relatório por</label>
              <p-select inputId="groupBy" [options]="groups" formControlName="groupBy" appendTo="body" [fluid]="true" />
            </div>
            <div class="actions">
              <p-button type="button" label="HTML" icon="pi pi-download" [loading]="busy()" (onClick)="exportReport('html')" />
              <p-button type="button" label="PDF" severity="secondary" [loading]="busy()" (onClick)="exportReport('pdf')" />
            </div>
          </form>
          <div>
            <h2>Parâmetros reprodutíveis</h2>
            <dl class="param-list">
              @for (item of draft()?.parameters ?? []; track item.label) {
                <div><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></div>
              }
            </dl>
          </div>
          @if (warnings().length) {
            <ul class="limitations">
              @for (warning of warnings(); track warning) { <li>{{ warning }}</li> }
            </ul>
          }
          @if (previewUrl()) {
            <a [href]="previewUrl()" target="_blank" rel="noopener">Prévia no backend</a>
          }
          <p class="note">{{ draft()?.note }}</p>
        </aside>
      </div>
    </section>
  `
})
export class ReportBuilderPageComponent {
  private readonly repository = inject(FloraRepository);
  private readonly messages = inject(MessageService);
  private readonly fb = inject(FormBuilder);

  readonly draft = signal<ReportDraft | null>(null);
  readonly sections = signal<ReportSection[]>([]);
  readonly current = signal<ReportSection | null>(null);
  readonly warnings = signal<string[]>([]);
  readonly previewUrl = signal('');
  readonly busy = signal(false);
  readonly groups = ['group', 'site', 'biome'];

  readonly meta = this.fb.nonNullable.group({
    title: ['', Validators.required],
    groupBy: ['group', Validators.required]
  });
  readonly editor = this.fb.nonNullable.group({
    narrative: ['']
  });

  constructor() {
    this.editor.controls.narrative.valueChanges.subscribe((narrative) => {
      const current = this.current();
      if (!current) {
        return;
      }
      this.sections.update((sections) => sections.map((section) => (section.id === current.id ? { ...section, narrative } : section)));
      this.current.update((section) => (section ? { ...section, narrative } : section));
    });
    void this.load();
  }

  figure(key: NonNullable<ReportSection['figure']>) {
    return this.draft()?.figures[key];
  }

  choose(section: ReportSection): void {
    this.current.set(section);
    this.editor.controls.narrative.setValue(section.narrative, { emitEvent: false });
  }

  toggle(id: string): void {
    this.sections.update((sections) => sections.map((section) => (section.id === id ? { ...section, included: !section.included } : section)));
    const current = this.sections().find((section) => section.id === id) ?? null;
    this.current.set(current);
  }

  async exportReport(format: 'html' | 'pdf' | 'both'): Promise<void> {
    if (this.meta.invalid) {
      this.meta.markAllAsTouched();
      return;
    }
    this.busy.set(true);
    try {
      const result = await this.repository.exportReport({
        title: this.meta.controls.title.value,
        format,
        sections: this.sections(),
        groupBy: this.meta.controls.groupBy.value
      });
      this.warnings.set(result.warnings);
      this.previewUrl.set(result.previewUrl ?? '');
      const slug = result.title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'flora-report';
      if (format !== 'pdf') {
        downloadBlob(`${slug}.html`, new Blob([result.html], { type: 'text/html;charset=utf-8' }));
      }
      if (format !== 'html') {
        const bytes = decodeBase64(result.pdfBase64);
        downloadBlob(`${slug}.pdf`, new Blob([bytes.buffer as ArrayBuffer], { type: 'application/pdf' }));
      }
      this.messages.add({ severity: result.success ? 'success' : 'warn', summary: 'Exportação', detail: 'Arquivo gerado nesta sessão.' });
    } catch (error) {
      this.messages.add({ severity: 'error', summary: 'Exportação', detail: error instanceof Error ? error.message : 'Falha ao exportar.' });
    } finally {
      this.busy.set(false);
    }
  }

  private async load(): Promise<void> {
    const draft = await this.repository.reportDraft();
    this.draft.set(draft);
    this.sections.set(draft.sections.map((section) => ({ ...section })));
    this.meta.controls.title.setValue(draft.title);
    const first = draft.sections[0] ?? null;
    this.current.set(first);
    this.editor.controls.narrative.setValue(first?.narrative ?? '', { emitEvent: false });
  }
}
